"""Background-only AI review. A suggestion is never an export permission."""
from __future__ import annotations

import json
from pathlib import Path
import time
import uuid

from .ai_client import DeepSeekClient, ReviewError
from .ai_images import prepare_content
from .ai_policy import POLICY_VERSION, PROMPT_VERSION, select_review_case, evaluate_suggestion
from .ai_usage import empty_usage, merge_usage


def _sources_unchanged(case, files, digest):
    lookup = {file["id"]: file for file in files}
    return all(digest(lookup[identity]["source_path"]) == lookup[identity]["source_sha256"]
               for identity in case["candidate_ids"])


def review_job(manager, identifier):
    from .service import sha256
    job = manager.jobs[identifier]
    started = time.perf_counter()
    runtime = manager.ai_settings.runtime()
    prior = job.get("ai_review", {})
    usage = dict(prior.get("usage") or empty_usage())
    summary = {"mode": manager.ai_validation.snapshot()["mode"], "eligible": 0,
               "reviewed": 0, "suggested_same": 0, "auto_passed": 0,
               "unresolved": 0, "skipped": 0, "usage": usage, "message": "正在准备AI复核。",
               "can_retry": False}
    with manager.lock:
        job["ai_review"] = summary
        manager._plan(job)
    cases = []
    cache = {}
    for row in job["rows"]:
        case = select_review_case(row, job["rows"], job["files"], cache)
        if case["eligible"]:
            cases.append((row, case))
        elif row["status"] == "review":
            with manager.lock:
                row["ai_review"] = {"outcome": "skipped", "reason_code": case["reason_code"], "reason": case["reason"]}
                summary["skipped"] += 1
    with manager.lock:
        summary["eligible"] = len(cases)
    if not runtime["enabled"] or not runtime["api_key"]:
        with manager.lock:
            summary.update(message="AI复核未启用；可在设置中填写密钥后运行。", unresolved=len(cases))
        return
    if not cases:
        with manager.lock:
            summary["message"] = "没有适合AI复核的疑难项；原有可靠匹配可直接导出。"
        return
    with manager.lock:
        job["status"] = "ai_review"
        job["_ai_runs"] = job.get("_ai_runs", 0) + 1
    observations = []
    job["_ai_observations"] = observations
    run_id = uuid.uuid4().hex
    planned_case_ids = [row["id"] for row, _ in cases]
    client = DeepSeekClient(runtime["api_key"])
    stop_code = None
    for index, (row, original_case) in enumerate(cases, 1):
        manager._progress(identifier, f"DeepSeek正在复核 {index}/{len(cases)} 张疑难图片…", index - 1, len(cases))
        if stop_code:
            with manager.lock:
                row["ai_review"] = {"outcome": "skipped", "reason_code": stop_code,
                                    "reason": "接口暂不可用，已保留人工审核。"}
                observations.append({"case_id": row["id"], "case_fingerprint": original_case["fingerprint"],
                                     "source": "deepseek_live", "error": "not_called_after_" + stop_code})
            continue
        result = None
        try:
            case = select_review_case(row, job["rows"], job["files"])
            if not case["eligible"] or case["fingerprint"] != original_case["fingerprint"] or not _sources_unchanged(case, job["files"], sha256):
                raise ReviewError("source_changed", "原文件或预览已变化，仍需重新导入核对。")
            result = client.review(prepare_content(case, row, job["files"]))
            with manager.lock:
                merge_usage(usage, result["usage"])
            manager.ai_usage.add(result["usage"])
            # Envelope fields come from local content and actual API metadata,
            # not from the model's text. Rebuild the content-bound case after IO.
            envelope = {"model": result["model"], "case_fingerprint": case["fingerprint"], "decision": result["decision"]}
            fresh = select_review_case(row, job["rows"], job["files"])
            if not fresh["eligible"] or not _sources_unchanged(case, job["files"], sha256):
                fresh = {"eligible": False, "reason_code": "source_changed", "reason": "复核期间原稿发生变化，请重新导入。"}
            verdict = evaluate_suggestion(fresh, envelope, manager.ai_validation.load())
            decision = result["decision"]
            with manager.lock:
                summary["reviewed"] += 1
                summary["suggested_same"] += decision["verdict"] == "same"
                row["ai_review"] = {**decision, "model": result["model"], "request_id": result["request_id"],
                    "category": case["category"], "reason_code": verdict["reason_code"],
                    "outcome": "auto_passed" if verdict["accepted"] else "evaluation_suggestion" if verdict["reason_code"] == "validation_required" else "manual_review",
                    "gate_reason": verdict["reason"]}
                if verdict["accepted"]:
                    row.update(_status="auto", _file_id=decision["candidate_id"], _reason=verdict["reason"],
                               _reason_code=verdict["reason_code"], _accepted_by="ai", _ai_envelope=envelope)
                manager._plan(job)
                job["revision"] = job.get("revision", 0) + 1
                observations.append({"case_id": row["id"], **envelope,
                    "request_id": result["request_id"], "source": "deepseek_live",
                    "case": {key: case[key] for key in ("category", "candidate_ids", "image_digests")},
                    "usage": result["usage"], "category": case["category"],
                    "candidate_ids": case["candidate_ids"], "image_digests": case["image_digests"]})
        except ReviewError as error:
            if result is None:
                with manager.lock:
                    merge_usage(usage, error.usage)
                manager.ai_usage.add(error.usage)
            with manager.lock:
                row["ai_review"] = {"outcome": "error", "reason_code": error.code, "reason": error.message}
                observations.append({"case_id": row["id"], "case_fingerprint": original_case["fingerprint"],
                    "source": "deepseek_live", "error": error.code, "usage": error.usage})
            if error.code in {"authentication", "insufficient_balance", "rate_limit", "network_error", "provider_error", "request_rejected", "redirect_blocked"}:
                stop_code = error.code
        except Exception:
            # Never serialize exception text: it may include private paths or
            # provider request data. A local failure affects this row only.
            with manager.lock:
                row["ai_review"] = {"outcome": "error", "reason_code": "review_unavailable",
                                    "reason": "本项AI复核未完成，已保留人工审核。"}
                observations.append({"case_id": row["id"], "case_fingerprint": original_case["fingerprint"],
                                     "source": "deepseek_live", "error": "review_unavailable"})
    with manager.lock:
        manager._plan(job)
        summary["auto_passed"] = job["stats"]["ai_auto"]
        summary["unresolved"] = sum(row["status"] == "review" for row, _ in cases)
        summary["message"] = ("评估复核完成：AI建议供员工确认，尚未开放自动通过。" if summary["mode"] == "evaluation"
                              else "AI复核完成，剩余疑难项仍需人工确认。")
        job["timings"]["ai_review_seconds"] = round(time.perf_counter() - started, 3)
    try:
        path = Path(job["_work_dir"]) / f"ai_observations_{run_id}.json"
        artifact = {"schema_version": 1, "source": "deepseek_live", "policy_version": POLICY_VERSION,
            "prompt_version": PROMPT_VERSION, "run_id": run_id, "planned_case_ids": planned_case_ids, "cases": observations}
        path.write_text(json.dumps(artifact, ensure_ascii=False, allow_nan=False, indent=2), "utf-8")
        job["_ai_observation_artifact"] = artifact
    except OSError:
        with manager.lock:
            job["warnings"].append("AI复核验证记录未能保存，本次结果仍可查看。")
