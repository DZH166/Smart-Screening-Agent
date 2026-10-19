"""Background-only AI review. A suggestion is never an export permission."""
from __future__ import annotations

import copy
from contextlib import contextmanager, nullcontext
import json
import os
from pathlib import Path
import time
import threading
import tempfile
import uuid

from .ai_client import DeepSeekClient, ReviewError
from .ai_images import prepare_content
from .ai_policy import POLICY_VERSION, PROMPT_VERSION, select_review_case, evaluate_suggestion
from .ai_usage import empty_usage, merge_usage
from .ai_registry import ValidationRegistry


def _sources_unchanged(case, files, digest):
    lookup = {file["id"]: file for file in files}
    comparisons = (case.get("image_digests") or {}).get("comparison_inputs")
    expected = ({item["candidate_id"]: item["source_sha256"] for item in comparisons}
                if comparisons else {identity: lookup[identity]["source_sha256"]
                                     for identity in case["candidate_ids"]})
    try:
        return all(digest(lookup[identity]["source_path"]) == source_hash
                   for identity, source_hash in expected.items())
    except OSError:
        return False


def review_job(manager, identifier):
    started = time.perf_counter()
    try:
        return _review_job(manager, identifier)
    finally:
        manager.ai_debug.emit("run_finished", job_id=identifier,
                             elapsed_ms=int((time.perf_counter()-started)*1000))


@contextmanager
def _locked_job(manager, identifier):
    operation = getattr(manager, "job_operation", None)
    with operation(identifier, internal=True) if operation is not None else nullcontext():
        with manager.lock:
            yield


def _plan_input(job):
    """Copy only planner inputs; a job can also contain Futures and locks."""
    return {"rows": copy.deepcopy(job["rows"]), "files": copy.deepcopy(job["files"]),
            "_reserved": list(job["_reserved"]), "start_number": job["start_number"]}


def _apply_plan(job, plan):
    # Retain row objects used by the API and callers; only the planner's derived
    # fields are applied. Expensive validation has already run without the lock.
    derived = ("status", "reason", "reason_code", "file_id", "planned_number")
    planned = {row["id"]: row for row in plan["rows"]}
    for row in job["rows"]:
        for field in derived:
            row[field] = planned[row["id"]].get(field)
    job["stats"] = plan["stats"]


def _row_binding(row):
    ignored = {"status", "reason", "reason_code", "file_id", "planned_number", "ai_review"}
    return {key: copy.deepcopy(value) for key, value in row.items() if key not in ignored}


_STOP_CODES = {"authentication", "insufficient_balance", "rate_limit", "network_error", "provider_error",
               "request_rejected", "redirect_blocked", "implementation_changed", "pool_unavailable", "not_configured"}


def _review_job(manager, identifier):
    from .service import sha256
    started = time.perf_counter()
    trace = lambda stage, **values: manager.ai_debug.emit(stage, job_id=identifier, **values)
    trace("run_started")
    with _locked_job(manager, identifier):
        job = manager.jobs[identifier]
        initial_revision = job.get("revision", 0)
        initial_status = job["status"]
        plan = _plan_input(job)
        prior_usage = copy.deepcopy(job.get("ai_review", {}).get("usage") or empty_usage())
    manager._plan(plan)
    runtime = manager.ai_settings.runtime()
    summary = {"mode": manager.ai_validation.snapshot()["mode"], "eligible": 0,
               "reviewed": 0, "suggested_same": 0, "auto_passed": 0,
               "unresolved": 0, "skipped": 0, "usage": prior_usage, "message": "正在准备AI复核。",
               "can_retry": False}
    cases, ineligible, cache = [], [], {}
    for row in plan["rows"]:
        case = select_review_case(row, plan["rows"], plan["files"], cache)
        if case["eligible"]:
            cases.append((row, case))
        elif row["status"] == "review":
            ineligible.append((row["id"], case))
    summary["eligible"] = len(cases)
    with _locked_job(manager, identifier):
        if (manager.jobs.get(identifier) is not job or job.get("revision", 0) != initial_revision
                or job["status"] != initial_status or initial_status not in {"matching", "ai_review", "ready"}):
            return
        _apply_plan(job, plan)
        job["ai_review"] = summary
        row_lookup = {row["id"]: row for row in job["rows"]}
        for row_id, case in ineligible:
            row_lookup[row_id]["ai_review"] = {"outcome": "skipped", "reason_code": case["reason_code"], "reason": case["reason"]}
        summary["skipped"] = len(ineligible)
    for row_id, case in ineligible:
        trace("ineligible", row_id=row_id, reason_code=case["reason_code"])
    if not runtime["enabled"] or not runtime["api_key"]:
        trace("disabled")
        with _locked_job(manager, identifier):
            summary.update(message="AI复核未启用；可在设置中填写密钥后运行。", unresolved=len(cases))
        return
    if not cases:
        trace("no_cases")
        with _locked_job(manager, identifier):
            summary["message"] = "没有适合AI复核的疑难项；原有可靠匹配可直接导出。"
        return
    run_id = uuid.uuid4().hex
    run = {"revision": initial_revision}
    stop = threading.Event()
    observations = [{"case_id": row["id"], "case_fingerprint": case["fingerprint"],
                     "source": "deepseek_live", "error": "not_called_yet"} for row, case in cases]
    artifact = {"schema_version": 1, "source": "deepseek_live", "policy_version": POLICY_VERSION,
                "prompt_version": PROMPT_VERSION, "run_id": run_id,
                "implementation_sha256": ValidationRegistry._implementation(),
                "planned_case_ids": [row["id"] for row, _ in cases], "cases": observations}
    with _locked_job(manager, identifier):
        if job.get("revision", 0) != initial_revision or job["status"] != initial_status:
            return
        job["status"] = "ai_review"
        job["_ai_runs"] = job.get("_ai_runs", 0) + 1
        job["_ai_active_run"] = run_id
        job["_ai_observations"], job["_ai_observation_artifact"] = observations, artifact
        job.setdefault("_ai_observation_runs", []).append(artifact)
    records = manager.record_directory(identifier, "ai_runs")
    path = records / f"ai_observations_{run_id}.json"
    with _locked_job(manager, identifier):
        job["_ai_records_dir"] = str(records)
    artifact_lock = threading.RLock()
    checkpoint_lock = threading.Lock()

    def checkpoint():
        # Attempt callbacks and the coordinator serialize publication through a
        # dedicated lock, outside task/global locks. All planned cases exist
        # before any Future starts, and every started call is drained.
        temporary = None
        try:
            with checkpoint_lock:
                current_records = manager.record_directory(identifier, "ai_runs")
                if current_records != records:
                    raise ValueError("private record directory changed")
                with artifact_lock:
                    serialized = json.dumps(artifact, ensure_ascii=False, allow_nan=False, indent=2)
                descriptor, temporary = tempfile.mkstemp(prefix=".ai-run-", suffix=".tmp", dir=records)
                with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                    stream.write(serialized)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, path)
        except (OSError, ValueError, TypeError):
            with _locked_job(manager, identifier):
                warning = "AI复核验证记录未能完整保存，本次结果仍可查看。"
                if warning not in job["warnings"]:
                    job["warnings"].append(warning)
        finally:
            if temporary is not None:
                try:
                    os.unlink(temporary)
                except OSError:
                    pass

    def current(row_id=None, binding=None):
        # manager.lock must be held by the caller. Our own commits update the
        # expected revision; an API/user/scheduler update does not.
        if (manager.jobs.get(identifier) is not job or job.get("_ai_active_run") != run_id
                or job["status"] != "ai_review" or job.get("revision", 0) != run["revision"]):
            return False
        if row_id is not None:
            row = next((item for item in job["rows"] if item["id"] == row_id), None)
            return row is not None and _row_binding(row) == binding
        return True

    from .ai_dispatch import ManagedReviewClient
    legacy_client = ManagedReviewClient(manager, DeepSeekClient, identifier)

    def record_attempt(index, history):
        with artifact_lock:
            observations[index]["attempt_history"] = history
            observations[index]["error"] = "in_progress"
        checkpoint()

    def compare(index, row, original_case, submitted_at):
        entered = time.perf_counter()
        timings = {"case_queue_seconds": entered-submitted_at, "prepare_seconds": 0.,
                   "request_seconds": 0., "verify_seconds": 0.}
        request_started = verification_started = None
        def outcome(**values):
            now = time.perf_counter()
            if request_started is None:
                timings["prepare_seconds"] = now-entered
            elif verification_started is None:
                timings["request_seconds"] = now-request_started
            else:
                timings["verify_seconds"] = now-verification_started
            return {**values, "timings": {name: round(value, 6) for name, value in timings.items()}}
        result = None
        row_id, binding = row["id"], _row_binding(row)
        try:
            if stop.is_set():
                return outcome(not_called=True)
            trace("preparing", row_id=row_id, candidate_count=len(original_case["candidate_ids"]))
            with _locked_job(manager, identifier):
                if not current(row_id, binding):
                    raise ReviewError("stale_case", "记录已更新，本次回包不会覆盖当前选择。")
                frozen = _plan_input(job)
            frozen_row = next(item for item in frozen["rows"] if item["id"] == row_id)
            if ValidationRegistry._implementation() != artifact["implementation_sha256"]:
                raise ReviewError("implementation_changed", "复核实现已更新，请重新启动工具后导入。")
            case = select_review_case(frozen_row, frozen["rows"], frozen["files"])
            if (not case["eligible"] or case["fingerprint"] != original_case["fingerprint"]
                    or not _sources_unchanged(case, frozen["files"], sha256)):
                raise ReviewError("source_changed", "原文件或预览已变化，仍需重新导入核对。")
            content = prepare_content(case, frozen_row, frozen["files"])
            with _locked_job(manager, identifier):
                if not current(row_id, binding):
                    raise ReviewError("stale_case", "记录已更新，本次回包不会覆盖当前选择。")
            if stop.is_set():
                return outcome(not_called=True)
            timings["prepare_seconds"] = time.perf_counter()-entered
            request_started = time.perf_counter()
            # Legacy evaluation stubs can deliberately keep state in one client.
            # Production uses an independent dispatcher per concurrent case.
            client = legacy_client if "keys" not in runtime else ManagedReviewClient(manager, DeepSeekClient, identifier)
            client.on_attempt = lambda history: record_attempt(index, history)
            result = client.review(content, row_id=row_id)
            verification_started = time.perf_counter()
            timings["request_seconds"] = verification_started-request_started
            trace("verifying", row_id=row_id)
            with _locked_job(manager, identifier):
                valid_binding = current(row_id, binding)
                fresh_plan = _plan_input(job)
            fresh_row = next(item for item in fresh_plan["rows"] if item["id"] == row_id)
            fresh = select_review_case(fresh_row, fresh_plan["rows"], fresh_plan["files"])
            still_valid = (valid_binding and fresh.get("eligible")
                           and fresh.get("fingerprint") == case["fingerprint"]
                           and ValidationRegistry._implementation() == artifact["implementation_sha256"]
                           and _sources_unchanged(case, fresh_plan["files"], sha256))
            if not still_valid:
                fresh = {"eligible": False, "reason_code": "source_changed", "reason": "复核期间原稿或记录发生变化，请重新核对。"}
            envelope = {"model": result["model"], "case_fingerprint": case["fingerprint"], "decision": result["decision"]}
            verdict = evaluate_suggestion(fresh, envelope, manager.ai_validation.load())
            return outcome(result=result, case=case, envelope=envelope,
                           verdict=verdict, still_valid=still_valid, binding=binding)
        except ReviewError as error:
            if error.code in _STOP_CODES:
                stop.set()
            return outcome(error=error, result=result, binding=binding)
        except Exception:
            return outcome(error=ReviewError("review_unavailable", "本项AI复核未完成，已保留人工审核。"),
                           result=result, binding=binding)

    checkpoint()
    manager._progress(identifier, f"DeepSeek正在复核 0/{len(cases)} 张疑难图片…", 0, len(cases))
    shared_pool = getattr(manager, "ai_case_pool", None)
    width = min(2, max(1, getattr(manager, "ai_case_workers", 1))) if shared_pool and "keys" in runtime else 1
    # Candidate overlap is deliberately serialized: shared rivals and possible
    # ownership interactions must never become completion-order allocations.
    pending, next_submit, completed, stop_code = {}, 0, 0, None
    accounted = set()

    def account(index, outcome):
        result, error = outcome.get("result"), outcome.get("error")
        if index in accounted or result is None and error is None:
            return
        incoming = result["usage"] if result is not None else error.usage
        updated = dict(prior_usage)
        merge_usage(updated, incoming)
        accounted.add(index)
        with _locked_job(manager, identifier):
            prior_usage.update(updated)
        manager.ai_usage.add(incoming)

    def fill():
        nonlocal next_submit
        while not stop.is_set() and next_submit < len(cases) and len(pending) < width:
            row, case = cases[next_submit]
            occupied = set().union(*(set(cases[index][1]["candidate_ids"]) for index in pending)) if pending else set()
            if occupied.intersection(case["candidate_ids"]):
                break
            if shared_pool is not None and width > 1:
                future = shared_pool.submit(compare, next_submit, row, case, time.perf_counter())
            else:
                from concurrent.futures import Future
                future = Future()
                try:
                    future.set_result(compare(next_submit, row, case, time.perf_counter()))
                except BaseException as error:
                    future.set_exception(error)
            pending[next_submit] = future
            next_submit += 1

    try:
        fill()
        for index, (row, original_case) in enumerate(cases):
            row_id = row["id"]
            if index in pending:
                future = pending[index]
                try:
                    outcome = future.result()
                except Exception:
                    outcome = {"error": ReviewError("review_unavailable", "本项AI复核未完成，已保留人工审核。"), "binding": _row_binding(row)}
            else:
                outcome = {"not_called": True}
            if outcome.get("not_called"):
                reason = stop_code or "review_unavailable"
                trace("skipped", row_id=row_id, error_code=reason)
                with artifact_lock:
                    observations[index] = {"case_id": row_id, "case_fingerprint": original_case["fingerprint"],
                                           "source": "deepseek_live", "error": "not_called_after_" + reason}
                with _locked_job(manager, identifier):
                    if current(row_id, _row_binding(row)):
                        next(item for item in job["rows"] if item["id"] == row_id)["ai_review"] = {
                            "outcome": "skipped", "reason_code": reason, "reason": "接口暂不可用，已保留人工审核。"}
                summary["skipped"] += 1
            else:
                result, error = outcome.get("result"), outcome.get("error")
                incoming = result["usage"] if result is not None else error.usage
                account(index, outcome)
                observation = {"case_id": row_id, "case_fingerprint": original_case["fingerprint"],
                               "source": "deepseek_live", "usage": incoming, "timings": outcome.get("timings", {}),
                               "attempt_history": copy.deepcopy(result.get("attempt_history", []) if result is not None
                                                                    else getattr(error, "attempt_history", []))}
                if error is not None:
                    trace("failed", row_id=row_id, error_code=error.code)
                    observation["error"] = error.code
                    if result is None and incoming.get("requests", 0) == 0:
                        observation["not_called"] = True
                        summary["skipped"] += 1
                    if result is not None:
                        observation.update({key: result[key] for key in ("decision", "model", "request_id")})
                        observation["validation_eligible"] = False
                    with _locked_job(manager, identifier):
                        if current(row_id, outcome["binding"]):
                            next(item for item in job["rows"] if item["id"] == row_id)["ai_review"] = {
                                "outcome": "error", "reason_code": error.code, "reason": error.message}
                    if error.code in _STOP_CODES and (stop_code is None or error.code == "rate_limit"):
                        stop_code = error.code
                else:
                    case, decision, verdict = outcome["case"], result["decision"], outcome["verdict"]
                    observation.update(outcome["envelope"], request_id=result["request_id"], category=case["category"],
                        candidate_ids=case["candidate_ids"], image_digests=case["image_digests"],
                        case={key: case[key] for key in ("category", "candidate_ids", "image_digests")})
                    if not outcome["still_valid"]:
                        observation.update(error="case_invalidated_after_request", validation_eligible=False)
                    with _locked_job(manager, identifier):
                        can_apply = current(row_id, outcome["binding"])
                        proposed = _plan_input(job) if can_apply else None
                    changes = {"ai_review": {**decision, "model": result["model"], "request_id": result["request_id"],
                        "category": case["category"], "reason_code": verdict["reason_code"],
                        "outcome": "auto_passed" if verdict["accepted"] else "evaluation_suggestion" if verdict["reason_code"] == "validation_required" else "manual_review",
                        "gate_reason": verdict["reason"], "gate_failures": verdict.get("failed_checks", [])}}
                    if verdict["accepted"]:
                        changes.update(_status="auto", _file_id=decision["candidate_id"], _reason=verdict["reason"],
                                       _reason_code=verdict["reason_code"], _accepted_by="ai", _ai_envelope=outcome["envelope"])
                    if proposed is not None:
                        proposed_row = next(item for item in proposed["rows"] if item["id"] == row_id)
                        proposed_row.update(changes)
                        manager._plan(proposed)
                        if verdict["accepted"] and proposed_row["status"] != "auto":
                            # Qualification/ownership may change between the
                            # post-request check and final plan calculation.
                            verdict = {"accepted": False, "reason_code": proposed_row["reason_code"],
                                "reason": proposed_row["reason"], "failed_checks": [{
                                    "code": proposed_row["reason_code"], "reason": proposed_row["reason"]}]}
                            changes["ai_review"].update(outcome="manual_review", reason_code=verdict["reason_code"],
                                gate_reason=verdict["reason"], gate_failures=verdict["failed_checks"])
                            observation.update(error="case_invalidated_after_request", validation_eligible=False)
                    with _locked_job(manager, identifier):
                        if proposed is not None and current(row_id, outcome["binding"]):
                            next(item for item in job["rows"] if item["id"] == row_id).update(changes)
                            _apply_plan(job, proposed)
                            job["revision"] = job.get("revision", 0) + 1
                            run["revision"] = job["revision"]
                            summary["reviewed"] += 1
                            summary["suggested_same"] += decision["verdict"] == "same"
                            applied = True
                        else:
                            applied = False
                    if not applied:
                        observation.update(error="case_invalidated_after_request", validation_eligible=False)
                        trace("manual", row_id=row_id, reason_code="stale_case")
                    else:
                        trace("auto" if verdict["accepted"] else "manual", row_id=row_id,
                              verdict=decision["verdict"], candidate_id=decision.get("candidate_id"),
                              reason_code=verdict.get("reason_code"),
                              gate_failures=[item["code"] for item in verdict.get("failed_checks", [])])
                with artifact_lock:
                    observations[index] = observation
            completed += 1
            manager._progress(identifier, f"DeepSeek正在复核 {completed}/{len(cases)} 张疑难图片…", completed, len(cases))
            checkpoint()
            pending.pop(index, None)
            fill()
    finally:
        # Unexpected coordinator errors must not let background requests outlive
        # the batch's run_finished event or produce an unrecorded paid request.
        stop.set()
        for index, future in sorted(pending.items()):
            try:
                outcome = future.result()
                result, error = outcome.get("result"), outcome.get("error")
                if result is not None or error is not None:
                    incoming = result["usage"] if result is not None else error.usage
                    account(index, outcome)
                    with artifact_lock:
                        previous_error = observations[index].get("error")
                        original_error = (error.code if error is not None else previous_error
                                          if previous_error not in {None, "not_called_yet", "in_progress"} else None)
                        observations[index] = {"case_id": cases[index][0]["id"], "source": "deepseek_live",
                            "case_fingerprint": cases[index][1]["fingerprint"],
                            "error": original_error or "coordinator_interrupted",
                            "interrupted": True, "usage": incoming, "validation_eligible": False,
                            "timings": outcome.get("timings", {}), "attempt_history": copy.deepcopy(result.get("attempt_history", []) if result is not None
                                                                else getattr(error, "attempt_history", []))}
                        if result is not None:
                            observations[index].update({key: result[key] for key in ("decision", "model", "request_id")})
                        if original_error is not None:
                            observations[index]["original_error"] = original_error
                trace("failed", row_id=cases[index][0]["id"], error_code="review_unavailable")
            except Exception:
                with artifact_lock:
                    observations[index].update(error="review_unavailable", interrupted=True)
        with artifact_lock:
            for index, observation in enumerate(observations):
                if observation.get("error") == "not_called_yet":
                    observation["error"] = "not_called_after_coordinator_interrupted"
                    trace("skipped", row_id=cases[index][0]["id"], error_code="review_unavailable")
        with _locked_job(manager, identifier):
            if current():
                final_plan = _plan_input(job)
            else:
                final_plan = None
        if final_plan is not None:
            try:
                manager._plan(final_plan)
            except Exception:
                final_plan = None
                with _locked_job(manager, identifier):
                    warning = "AI复核结束时未能重新计算计划，已保留所有接口记录，请重新导入核对。"
                    if warning not in job["warnings"]:
                        job["warnings"].append(warning)
        with _locked_job(manager, identifier):
            if final_plan is not None and current():
                _apply_plan(job, final_plan)
            summary["auto_passed"] = job["stats"]["ai_auto"]
            summary["unresolved"] = sum(item["status"] == "review" for item in job["rows"] if item["id"] in artifact["planned_case_ids"])
            summary["message"] = ("评估复核完成：AI建议供员工确认，尚未开放自动通过。" if summary["mode"] == "evaluation"
                                  else "AI复核完成，剩余疑难项仍需人工确认。")
            job["timings"]["ai_review_seconds"] = round(time.perf_counter() - started, 3)
            for phase in ("case_queue", "prepare", "request", "verify"):
                # Work sums may exceed wall time when two independent cases
                # overlap; never present them as an end-to-end percentage.
                job["timings"]["ai_" + phase + "_work_seconds"] = round(sum(
                    item.get("timings", {}).get(phase + "_seconds", 0.) for item in observations), 6)
            if job.get("_ai_active_run") == run_id:
                job.pop("_ai_active_run", None)
        checkpoint()
