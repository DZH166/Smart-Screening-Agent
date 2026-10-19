"""Measure artificial AI waiting, never real DeepSeek or business accuracy.

Run each implementation sequentially, with the same case count and simulated
latency. Every raw repetition is kept. This measures scheduler overlap only;
it is not a claim about actual provider response time, throughput or account
quota. Development tests/pytest are required; no provider socket is opened.
"""
from __future__ import annotations

import argparse
import copy
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
from pathlib import Path
import statistics
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]


def synthetic_artifact(value, transport_attempts):
    """Correct fixture provenance without changing the production workflow."""
    artifact = copy.deepcopy(value)
    artifact.update(source="synthetic_mock", synthetic_transport=True, real_api_calls=0,
                    qualification_eligible=False, workflow_source_before_fixture_label=value.get("source"))
    artifact["synthetic_transport_attempts"] = copy.deepcopy(transport_attempts)
    for item in artifact.get("cases", []):
        item.update(source="synthetic_mock", synthetic_transport=True, real_api_calls=0,
                    validation_eligible=False)
        if "attempt_history" not in item:
            item["attempt_history"] = [{name: attempt[name] for name in
                ("attempt", "key_id", "code", "elapsed_ms", "usage") if name in attempt}
                for attempt in transport_attempts if attempt["case_id"] == item["case_id"]]
            item["attempt_history_origin"] = "synthetic_transport_capture"
    return artifact


class SyntheticArtifactJson:
    """A fixture-only module proxy: every on-disk workflow artifact is tagged."""
    def __init__(self, attempts, lock):
        self.attempts, self.lock = attempts, lock

    def __getattr__(self, name):
        return getattr(json, name)

    def dumps(self, value, *args, **kwargs):
        if isinstance(value, dict) and "planned_case_ids" in value and "cases" in value:
            with self.lock:
                value = synthetic_artifact(value, self.attempts)
        return json.dumps(value, *args, **kwargs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-root", type=Path, default=ROOT)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--cases", type=int, default=6)
    parser.add_argument("--delay", type=float, default=.2)
    parser.add_argument("--workers", type=int, choices=(1, 2), default=2)
    args = parser.parse_args()
    if not 1 <= args.repeats <= 20 or not 2 <= args.cases <= 6 or not 0 <= args.delay <= 10:
        parser.error("repeats 1..20, cases 2..6, delay 0..10 required")
    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=False)
    sys.path.insert(0, str(ROOT / "tests"))
    sys.path.insert(0, str(args.package_root.resolve()))
    import pytest
    import hsd_tool.ai_workflow as workflow
    from hsd_tool.ai_registry import IMPLEMENTATION_MODULES
    from test_ai_parallel import identity, synthetic_batch
    from test_ai_integration_audit import model_answer
    expected_package = args.package_root.resolve() / "hsd_tool"
    for name in (*IMPLEMENTATION_MODULES, "service"):
        spec = importlib.util.find_spec("hsd_tool." + name)
        if spec is None or not Path(spec.origin).resolve().is_relative_to(expected_package):
            raise RuntimeError("Benchmark package isolation check failed")
    measurements = []
    for iteration in range(args.repeats):
        trial = work / f"run-{iteration+1}"
        trial.mkdir()
        patches = pytest.MonkeyPatch()
        patches.delenv("DEEPSEEK_API_KEY", raising=False)
        manager, job = synthetic_batch(trial, patches, count=args.cases)
        injected_pool = None
        if not hasattr(manager, "ai_case_pool"):
            injected_pool = ThreadPoolExecutor(max_workers=args.workers)
            manager.ai_case_pool = injected_pool
        manager.ai_case_workers = args.workers
        state = {"active": 0, "peak": 0}
        lock = threading.Lock()
        transport_attempts = []
        key_ids = {row["api_key"]: row["id"] for row in manager.ai_settings.runtime()["keys"]}
        case_ids = {row["candidates"][0]["file_id"]: row["id"] for row in job["rows"]}
        patches.setattr(workflow, "json", SyntheticArtifactJson(transport_attempts, lock))
        class ArtificialClient:
            def __init__(self, key):
                self.key_id = key_ids[key]
            def review(self, content):
                candidate = identity(content)
                call_started = time.perf_counter()
                with lock:
                    state["active"] += 1
                    state["peak"] = max(state["peak"], state["active"])
                answer = model_answer(candidate)
                try:
                    time.sleep(args.delay)
                    return answer
                finally:
                    with lock:
                        state["active"] -= 1
                        transport_attempts.append({"case_id": case_ids[candidate], "candidate_id": candidate,
                            "attempt": 1, "key_id": self.key_id, "code": "ok",
                            "elapsed_ms": int((time.perf_counter()-call_started)*1000),
                            "usage": copy.deepcopy(answer["usage"]), "synthetic_transport": True, "real_api_calls": 0})
        patches.setattr(workflow, "DeepSeekClient", ArtificialClient)
        try:
            started = time.perf_counter()
            failure = None
            try:
                workflow.review_job(manager, "audit")
            except Exception as error:
                failure = type(error).__name__
            elapsed = time.perf_counter() - started
            original = job.get("_ai_observation_artifact") or {"source": "deepseek_live",
                "planned_case_ids": [row["id"] for row in job["rows"]],
                "cases": [{"case_id": row["id"], "source": "synthetic_mock",
                           "error": "workflow_failed_before_plan"} for row in job["rows"]],
                "benchmark_error": "workflow_failed_before_plan", "implementation_sha256": {}}
            with lock:
                artifact = synthetic_artifact(original, transport_attempts)
            if failure:
                artifact["benchmark_error_type"] = failure
            (trial / "synthetic-observations.json").write_text(json.dumps(artifact,
                ensure_ascii=False, allow_nan=False, indent=2), "utf-8")
            (trial / "synthetic-debug.json").write_text(json.dumps({"source": "synthetic_mock",
                "synthetic_transport": True, "real_api_calls": 0,
                "debug": manager.ai_debug.snapshot(after=0, limit=200)}, ensure_ascii=False,
                allow_nan=False, indent=2), "utf-8")
            # Both the separate archive and workflow's original ai_runs files
            # must remain visibly synthetic, including interrupted measurements.
            for directory in {Path(job["_work_dir"]), Path(job.get("_ai_records_dir", job["_work_dir"]))}:
                if not directory.resolve().is_relative_to(trial):
                    raise RuntimeError("Synthetic artifact escaped its isolated work directory")
                for path in directory.glob("ai_observations_*.json"):
                    stored = json.loads(path.read_text("utf-8"))
                    if stored.get("source") != "synthetic_mock" or stored.get("real_api_calls") != 0:
                        raise RuntimeError("Synthetic workflow record was not tagged at publication")
            requests = manager.ai_usage.snapshot()["requests"]
            case_failures = [item.get("error") for item in artifact["cases"] if item.get("error")]
            valid_run = (failure is None and len(artifact["cases"]) == args.cases and requests == args.cases
                         and len(transport_attempts) == args.cases and not case_failures
                         and job["stats"]["ai_auto"] == 0 and job["stats"]["review"] == args.cases)
            measurements.append({"iteration": iteration + 1, "seconds": elapsed,
                "valid_run": valid_run, "peak_mock_requests": state["peak"], "requests": requests,
                "ai_auto": job["stats"]["ai_auto"], "manual": job["stats"]["review"],
                "planned_case_ids": artifact["planned_case_ids"],
                "result_case_ids": [item["case_id"] for item in artifact["cases"]],
                "failures": case_failures,
                "implementation_sha256": artifact["implementation_sha256"],
                "artifact": f"run-{iteration+1}/synthetic-observations.json", "benchmark_error_type": failure})
        finally:
            manager.close()
            if injected_pool is not None:
                injected_pool.shutdown(wait=True)
            patches.undo()
    result = {"synthetic": True, "real_api_calls": 0, "purpose": "scheduler overlap only",
        "package_root": str(args.package_root.resolve()), "cases": args.cases,
        "simulated_wait_seconds_per_request": args.delay, "requested_workers": args.workers,
        "measurements": measurements, "median_seconds": statistics.median(item["seconds"] for item in measurements)}
    (work / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), "utf-8")
    print(json.dumps({"synthetic": True, "real_api_calls": 0, "median_seconds": result["median_seconds"],
                      "all_runs_valid": all(item["valid_run"] for item in measurements),
                      "raw_seconds": [item["seconds"] for item in measurements]}, ensure_ascii=True))
    if not all(item["valid_run"] for item in measurements):
        raise SystemExit(1)  # Keep every failure, but never report it as a valid speed result.


if __name__ == "__main__":
    main()
