"""Compare resource scheduling with labelled synthetic delays, never AI calls."""
import argparse
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import threading
import time


def worker(args):
    sys.path.insert(0, str(args.package_root))
    os.environ.pop("DEEPSEEK_API_KEY", None)
    from hsd_tool.service import JobManager
    manager = JobManager(args.work)
    events, finished = [], threading.Event()
    started = time.perf_counter()
    def mark(name, identifier):
        with manager.lock:
            events.append({"stage": name, "job": identifier, "seconds": time.perf_counter()-started})
    def ai(identifier):
        manager._start_operation(identifier, "ai_review", "synthetic provider wait")
        mark("ai_started", identifier)
        time.sleep(.4)
        mark("ai_finished", identifier)
        with manager.lock:
            manager.jobs[identifier]["status"] = "ready"
    def cpu(identifier):
        manager._start_operation(identifier, "matching", "synthetic CPU delay")
        mark("cpu_started", identifier)
        time.sleep(.15)
        mark("cpu_finished", identifier)
        if args.mode == "baseline":
            ai(identifier)
        else:
            with manager.lock:
                manager.jobs[identifier]["status"] = "queued"
                manager._submit(manager.jobs[identifier], ai)
    def export(identifier):
        manager._start_operation(identifier, "exporting", "synthetic disk delay")
        mark("export_started", identifier)
        time.sleep(.1)
        mark("export_finished", identifier)
        manager.jobs[identifier]["status"] = "done"
    manager._process, manager._export = cpu, export
    for identifier in ("employee_a", "employee_b", "existing_export"):
        manager.jobs[identifier] = {"id": identifier, "status": "queued", "timings": {}}
    try:
        with manager.lock:
            for identifier in ("employee_a", "employee_b"):
                manager._submit(manager.jobs[identifier], cpu)
            manager._submit(manager.jobs["existing_export"], export)
        deadline = time.monotonic()+10
        while time.monotonic() < deadline:
            with manager.lock:
                done = all(job["status"] in {"ready", "done"} for job in manager.jobs.values())
            if done:
                break
            time.sleep(.005)
        assert done, "Synthetic scheduling did not drain"
        elapsed = time.perf_counter()-started
        result = {"mode": args.mode, "elapsed_seconds": elapsed, "events": events,
            "second_cpu_started_seconds": next(event["seconds"] for event in events if event["stage"] == "cpu_started" and event["job"] == "employee_b"),
            "export_finished_seconds": next(event["seconds"] for event in events if event["stage"] == "export_finished"),
            "queue_timings": {identity: dict(job["timings"]) for identity, job in manager.jobs.items()}}
        print(json.dumps(result))
    finally:
        manager.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-root", type=Path)
    parser.add_argument("--package-root", type=Path)
    parser.add_argument("--work", required=True, type=Path)
    parser.add_argument("--mode", choices=("baseline", "optimized"))
    parser.add_argument("--worker", action="store_true")
    args = parser.parse_args()
    if args.worker:
        return worker(args)
    assert args.baseline_root and args.baseline_root.is_dir()
    assert not args.work.exists() or not any(args.work.iterdir())
    args.work.mkdir(parents=True, exist_ok=True)
    root = Path(__file__).resolve().parents[1]
    results = []
    for repeat in range(1, 4):
        for mode, package in (("baseline", args.baseline_root), ("optimized", root)):
            completed = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--worker",
                "--mode", mode, "--package-root", str(package.resolve()),
                "--work", str((args.work / f"{mode}-{repeat}").resolve())],
                check=True, capture_output=True, text=True)
            result = json.loads(completed.stdout)
            result["repeat"] = repeat
            results.append(result)
            (args.work / "results-in-progress.json").write_text(json.dumps({
                "planned_trials": 6, "scope": "synthetic delays only", "runs": results}, indent=2), "utf-8")
    report = {"scope": "Synthetic CPU .15 s / AI .4 s / export .1 s delays, two new employees and an existing export; no real provider or business throughput claim.",
        "real_api_calls": 0, "runs": results, "medians": {mode: {
            key: statistics.median(result[key] for result in results if result["mode"] == mode)
            for key in ("elapsed_seconds", "second_cpu_started_seconds", "export_finished_seconds")}
            for mode in ("baseline", "optimized")}}
    (args.work / "results.json").write_text(json.dumps(report, indent=2), "utf-8")
    print(json.dumps(report["medians"], indent=2))


if __name__ == "__main__":
    main()
