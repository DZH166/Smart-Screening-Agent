"""Application workflow, numbering and non-destructive exports."""
from __future__ import annotations

import collections
import copy
import csv
import hashlib
import json
import logging
import os
import re
import shutil
import threading
import time
import uuid
import zipfile
import zlib
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from . import __version__

ACCEPTED = {"auto", "confirmed"}
BUSY = {"queued", "importing", "matching", "ai_review", "exporting"}
COMPRESSION_SAMPLE_BYTES = 64 * 1024
COMPRESSION_SAMPLE_BUDGET = 3 * COMPRESSION_SAMPLE_BYTES


def _download_compression(path):
    """Choose compression only; sampled bytes never establish file identity.

    Highly compressed artwork should avoid another full DEFLATE pass. Retain
    level 1 when every bounded head/middle/tail sample saves at least ten
    percent independently. Text headers cannot mask an already encoded body
    or borrow repeated bytes from another sample to inflate estimated savings.
    Every actual member still receives its complete manifest SHA256 check.
    """
    size = path.stat().st_size
    if not size:
        return zipfile.ZIP_STORED
    with path.open("rb") as stream:
        if size <= COMPRESSION_SAMPLE_BUDGET:
            samples = [stream.read(COMPRESSION_SAMPLE_BUDGET)]
        else:
            samples = []
            for position in (0, (size-COMPRESSION_SAMPLE_BYTES)//2, size-COMPRESSION_SAMPLE_BYTES):
                stream.seek(position)
                samples.append(stream.read(COMPRESSION_SAMPLE_BYTES))
    for sample in samples:
        if not sample or len(zlib.compress(sample, 1))*10 > len(sample)*9:
            return zipfile.ZIP_STORED
    return zipfile.ZIP_DEFLATED
INVALID_NAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
RESERVED_NAME = re.compile(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", re.I)


def valid_number(value: str) -> bool:
    return bool(value and len(value) <= 180 and not INVALID_NAME.search(value)
                and value[-1] not in " ." and not RESERVED_NAME.match(value))


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def csv_safe(value):
    value = str(value or "")
    return "'" + value if value.startswith(("=", "+", "-", "@", "\t", "\r")) else value


def _is_link_or_reparse(path):
    path = Path(path)
    return path.is_symlink() or bool(getattr(path.lstat(), "st_file_attributes", 0) & 0x400)


class JobManager:
    def __init__(self, data_dir: str | Path, *, settings_dir: str | Path | None = None):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.jobs = {}
        self._queue_sequence = 0
        self._job_locks = {}
        self._active_operations = 0
        self._inflight_futures = set()
        self._operation_condition = threading.Condition(self.lock)
        self._closing = False
        # Different resources have different queues. CPU work stays bounded;
        # provider waiting and one output writer cannot monopolize that worker.
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="hsd-cpu")
        self.ai_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="hsd-ai-batch")
        self.ai_case_workers = 2
        self.ai_case_pool = ThreadPoolExecutor(max_workers=self.ai_case_workers, thread_name_prefix="hsd-ai-case")
        self.export_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="hsd-export")
        self.settings_path = self.data_dir / "settings.json"
        from .ai_settings import AiSettings
        shared_settings = Path(settings_dir) if settings_dir is not None else self.data_dir
        shared_settings.mkdir(parents=True, exist_ok=True)
        self.ai_settings = AiSettings(shared_settings)
        from .ai_usage import UsageLedger
        from .ai_registry import ValidationRegistry
        self.ai_usage = UsageLedger(shared_settings)
        self.ai_validation = ValidationRegistry(shared_settings)
        from .ai_admin import AiDebugTrace
        self.ai_debug = AiDebugTrace()
        from .ai_key_pool import ApiKeyPool
        self.ai_key_pool = ApiKeyPool(self.ai_settings)
        self.cleanup_cache()

    def cleanup_cache(self):
        """Delete only self-marked, inactive work folders, never user outputs."""
        cache_root = (self.data_dir / "jobs").resolve()
        if not cache_root.is_dir():
            return
        for directory in cache_root.iterdir():
            if directory.name in self.jobs or not re.fullmatch(r"[0-9a-f]{32}", directory.name):
                continue
            if directory.is_symlink() or directory.resolve().parent != cache_root:
                continue
            marker = directory / ".hsd-job"
            try:
                if marker.read_text("ascii") == directory.name:
                    shutil.rmtree(directory)
            except OSError:
                pass

    def close(self):
        with self._operation_condition:
            self._closing = True
            # An accepted API operation may still be planning before its pool
            # submission. Let it finish while every executor remains open;
            # new external operations are rejected by job_operation above.
            while self._active_operations or self._inflight_futures:
                self._operation_condition.wait()
        # CPU jobs may hand off to AI, and AI coordinators may submit cases.
        # Drain in that order instead of rejecting already accepted work.
        self.pool.shutdown(wait=True)
        self.ai_pool.shutdown(wait=True)
        self.ai_case_pool.shutdown(wait=True)
        self.export_pool.shutdown(wait=True)
        with self._operation_condition:
            while self._active_operations:
                self._operation_condition.wait()
            self.jobs.clear()
            self._job_locks.clear()
        self.cleanup_cache()

    @contextmanager
    def job_operation(self, identifier, *, internal=False):
        """Serialize this task's edits without holding the global map lock."""
        with self.lock:
            if self._closing and not internal:
                raise ValueError("工具正在退出，不能再修改任务。")
            self._get(identifier)
            operation_lock = self._job_locks.setdefault(identifier, threading.RLock())
            # Count operations waiting for this task's lock as well. Shutdown
            # cannot miss a user action which already passed its entry check.
            self._active_operations += 1
        try:
            with operation_lock:
                yield
        finally:
            with self._operation_condition:
                self._active_operations -= 1
                self._operation_condition.notify_all()

    def has_active_operations(self):
        with self.lock:
            return bool(self._active_operations or any(job["status"] in BUSY for job in self.jobs.values()))

    def config(self):
        result = {"prefix": "HSD", "digits": 4, "last_start": 1,
                  "last_workbook": "", "last_source": "", "last_output": "", "version": __version__}
        try:
            stored = json.loads(self.settings_path.read_text("utf-8"))
            for key in ("last_start", "last_workbook", "last_source", "last_output"):
                if key in stored:
                    result[key] = stored[key]
        except (OSError, ValueError):
            pass
        return result

    def ai_config(self):
        settings = self.ai_settings.snapshot()
        validation = self.ai_validation.snapshot()
        return {**settings, "mode": validation["mode"], "validation": validation}

    def _save_config(self, job):
        values = {"last_start": job["start_number"], "last_workbook": job["_workbook_path"],
                  "last_source": job["_source_path"], "last_output": job["_output_root"]}
        temporary = self.settings_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(values, ensure_ascii=False, indent=2), "utf-8")
        os.replace(temporary, self.settings_path)

    def create(self, payload: dict, *, owner_id=None, downloadable=False, display_names=None,
               input_digests=None):
        # Only the authenticated multipart receiver supplies these hashes. They
        # are never read from the JSON payload or exposed in public snapshots.
        upload_digests = {}
        if input_digests is not None:
            if (not downloadable or owner_id is None or not isinstance(input_digests, dict)
                    or set(input_digests) != {"workbook", "source"}
                    or any(not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value)
                           for value in input_digests.values())):
                raise ValueError("上传文件校验信息无效，请重新上传。")
            upload_digests = dict(input_digests)
        workbook = Path(str(payload.get("workbook_path", "")).strip().strip('"')).resolve()
        source = Path(str(payload.get("source_path", "")).strip().strip('"')).resolve()
        output_text = str(payload.get("output_root", "")).strip().strip('"')
        output = Path(output_text).resolve() if output_text else workbook.parent / "编号结果"
        if not output_text and source.is_dir() and output.is_relative_to(source):
            output = source.parent / (source.name + "_编号结果")
        start = payload.get("start_number")
        if isinstance(start, bool) or not isinstance(start, int) or not 1 <= start <= 9999:
            raise ValueError("起始流水号必须是 1 到 9999 之间的整数。")
        if not workbook.is_file() or workbook.suffix.lower() != ".xlsx" or workbook.name.startswith("~$"):
            raise ValueError("请选择有效的 .xlsx 表格文件。")
        if not source.exists() or not (source.is_dir() or source.suffix.lower() == ".zip"):
            raise ValueError("请选择 AI 文件夹或 ZIP 压缩包。")
        if output.exists() and not output.is_dir():
            raise ValueError("输出位置必须是文件夹。")
        if output.is_relative_to((self.data_dir / "jobs").resolve()):
            raise ValueError("请将结果保存在工具临时目录之外。")
        if source.is_dir() and output.is_relative_to(source):
            raise ValueError("结果保存位置不能在 AI 源文件夹内部，请选择旁边的文件夹，避免下次把历史结果重复导入。")
        with self.lock:
            if self._closing:
                raise ValueError("工具正在退出，不能再导入新任务。")
            if owner_id is None and any(j["status"] in BUSY for j in self.jobs.values()):
                raise ValueError("当前任务仍在处理，请完成后再导入。")
            identifier = uuid.uuid4().hex
            work_dir = self.data_dir / "jobs" / identifier
            work_dir.mkdir(parents=True)
            (work_dir / ".hsd-job").write_text(identifier, "ascii")
            display_names = display_names or {}
            job = {"id": identifier, "status": "queued" if owner_id is not None else "importing", "progress": {"message": "正在排队，轮到本批后会自动处理…" if owner_id is not None else "正在读取表格…", "current": 0, "total": 1},
                   "error": None, "sheet_name": "", "workbook_name": display_names.get("workbook_name", workbook.name), "source_name": display_names.get("source_name", source.name),
                   "start_number": start, "prefix": "HSD", "rows": [], "files": [], "warnings": [],
                   "output_dir": None, "output_target": str(output), "report": None, "stats": {}, "_workbook_path": str(workbook),
                   "_source_path": str(source), "_output_root": str(output), "_work_dir": str(work_dir),
                   "_reserved": [], "_input_digest": None, "_upload_digests": upload_digests, "revision": 0,
                   "timings": {}, "_history": [], "_image_assets": {}, "_started_perf": time.perf_counter(),
                   "_owner_id": owner_id, "_downloadable": bool(downloadable)}
            job["_batch_started_perf"] = job["_started_perf"]
            self.jobs[identifier] = job
            try:
                if owner_id is None:
                    self._save_config(job)
            except OSError:
                logging.exception("Could not save input preferences")
                job["warnings"].append("本机设置未能保存，本次处理仍会继续；下次可能需要重新选择路径。")
            self._submit(job, self._process)
        return identifier

    def _submit(self, job, operation):
        """Called under the map lock; retain a separate FIFO per resource."""
        stage = ("cpu" if operation == self._process
                 else "export" if operation == self._export else "ai")
        executor = {"cpu": self.pool, "ai": self.ai_pool, "export": self.export_pool}[stage]
        self._queue_sequence += 1
        job["_queue_order"] = self._queue_sequence
        job["_queue_stage"] = stage
        job.pop("_active_stage", None)
        job["_queued_perf"] = time.perf_counter()
        operation_token = uuid.uuid4().hex
        job["_pending_operation_token"] = operation_token
        job["_operation_token"] = operation_token
        future = executor.submit(operation, job["id"])
        if hasattr(future, "add_done_callback"):
            self._inflight_futures.add(future)
            def completed(result):
                try:
                    try:
                        error = result.exception()
                    except BaseException as exc:
                        error = exc
                    if error is not None:
                        with self.lock:
                            if (self.jobs.get(job["id"]) is job and job.get("_operation_token") == operation_token
                                    and job.get("status") in BUSY):
                                self._fail(job["id"], error)
                finally:
                    with self._operation_condition:
                        self._inflight_futures.discard(result)
                        self._operation_condition.notify_all()
            future.add_done_callback(completed)

    def _start_operation(self, identifier, status, message):
        with self.job_operation(identifier, internal=True), self.lock:
            job = self.jobs[identifier]
            queued_at = job.pop("_queued_perf", None)
            job.pop("_queue_order", None)
            stage = job.pop("_queue_stage", self._stage_for(job))
            job["_active_stage"] = stage
            job["_operation_token"] = job.pop("_pending_operation_token", None) or uuid.uuid4().hex
            if queued_at is not None:
                waited = time.perf_counter() - queued_at
                timings = job.setdefault("timings", {})
                for name in ("queue_seconds", f"queue_{stage}_seconds"):
                    timings[name] = round(timings.get(name, 0) + waited, 3)
            job["status"] = status
            job["progress"] = {"message": message, "current": 0, "total": 1}
            return job

    def _progress(self, identifier, message, current=0, total=1):
        with self.lock:
            self.jobs[identifier]["progress"] = {"message": message, "current": current, "total": total}

    def _process(self, identifier):
        try:
            job = self._start_operation(identifier, "importing", "正在读取表格…")
            job["_started_perf"] = time.perf_counter()
            from .workbook import inspect_workbook
            from .matching import scan_and_match, prepare_matching
            workbook_path = job["_workbook_path"]
            job["_input_digest"] = job.get("_upload_digests", {}).get("workbook") or sha256(workbook_path)
            snapshot_path = Path(job["_work_dir"]) / "source.xlsx"
            shutil.copyfile(workbook_path, snapshot_path)
            if sha256(snapshot_path) != job["_input_digest"]:
                raise ValueError("读取时源表格发生了变化，请保存表格后重新导入。")
            job["_snapshot_workbook"] = str(snapshot_path)
            sheet = inspect_workbook(str(snapshot_path), str(Path(job["_work_dir"]) / "workbook"))
            if not sheet["rows"]:
                raise ValueError("当前工作表的 B 列没有可读取的图片，请使用约定的表格模板。")
            with self.job_operation(identifier, internal=True), self.lock:
                job["sheet_name"] = sheet["sheet_name"]
                job["rows"] = sheet["rows"]
                job["_reserved"] = sheet.get("reserved_numbers", [])
                job["status"] = "matching"
                job["timings"]["import_seconds"] = round(time.perf_counter() - job["_started_perf"], 3)
            matching_started = time.perf_counter()
            source_path = Path(job["_source_path"])
            if source_path.is_file():
                job["_source_archive_digest"] = job.get("_upload_digests", {}).get("source") or sha256(source_path)
            runtime = self.ai_settings.runtime()
            if (runtime.get("enabled") and runtime.get("api_key")
                    and runtime.get("matching_workflow") == "ai_first"):
                prepared = prepare_matching(job["_source_path"], sheet["rows"],
                    str(Path(job["_work_dir"]) / "matching"),
                    progress=lambda m, c=0, t=1: self._progress(identifier, m, c, t))
                self._check_import_sources(job)
                with self.job_operation(identifier, internal=True), self.lock:
                    job["matching_mode"] = "ai_first"
                    job["files"] = prepared.files
                    job["warnings"].extend(prepared.warnings)
                    job["_prepared_matching"] = prepared
                    job["timings"]["preview_prepare_seconds"] = round(time.perf_counter()-matching_started, 3)
                    job["ai_retrieval"] = {"status": "queued", "message": "等待 AI 查找对应图片。"}
                    job["status"] = "queued"
                    job["progress"] = {"message": "预览已准备，正在等待 AI 查找对应图片…",
                        "phase": "ai_retrieval", "step_label": "AI 查找对应图片", "current": 0, "total": 1}
                    self._submit(job, self._retrieve_ai_first)
                return
            job["matching_mode"] = "local"
            result = scan_and_match(job["_source_path"], sheet["rows"], str(Path(job["_work_dir"]) / "matching"),
                                    progress=lambda m, c=0, t=1: self._progress(identifier, m, c, t))
            if job.get("_source_archive_digest") and sha256(source_path) != job["_source_archive_digest"]:
                raise ValueError("读取时源压缩包发生了变化，请重新导入。")
            with self.job_operation(identifier, internal=True):
                self._apply_match_result(job, result)
                job["revision"] += 1
                job["timings"]["matching_seconds"] = round(time.perf_counter() - matching_started, 3)
                job["timings"]["processing_seconds"] = round(time.perf_counter() - job["_started_perf"], 3)
                job["progress"] = {"message": "自动验证完成", "current": len(job["rows"]), "total": len(job["rows"])}
            runtime = self.ai_settings.runtime()
            if not runtime["enabled"] or not runtime["api_key"] or not job["stats"]["review"]:
                # No possible network request: do not queue a fully local
                # result behind other employees' slow provider responses.
                self._after_match_ai(identifier)
            else:
                with self.job_operation(identifier, internal=True), self.lock:
                    job["status"] = "queued"
                    job["progress"] = {"message": "本机匹配完成，正在等待 AI 复核阶段…", "current": 0, "total": 1}
                    self._submit(job, self._after_match_ai)
        except Exception as exc:
            self._fail(identifier, exc)

    def _check_import_sources(self, job):
        if (sha256(job["_workbook_path"]) != job["_input_digest"]
                or sha256(job["_snapshot_workbook"]) != job["_input_digest"]):
            raise ValueError("源表格发生变化，请保存后重新导入。")
        if job.get("_source_archive_digest") and sha256(job["_source_path"]) != job["_source_archive_digest"]:
            raise ValueError("源压缩包发生变化，请重新导入。")

    def _apply_match_result(self, job, result):
        matches = {m["row_id"]: m for m in result["matches"]}
        job["files"] = result["files"]
        job["warnings"].extend(message for message in result.get("warnings", []) if message not in job["warnings"])
        for row in job["rows"]:
            match = matches.get(row["id"], {})
            row["_status"] = match.get("status", "unmatched")
            row["_reason"] = match.get("reason", row.get("issue") or "没有找到对应文件")
            row["_file_id"] = match.get("file_id")
            row["_reason_code"] = match.get("reason_code", "not_verified")
            row["diagnostics"] = match.get("diagnostics", {})
            row["evidence"] = match.get("evidence")
            row["candidates"] = match.get("candidates", [])
            failures = set((row["evidence"] or {}).get("failed_checks", []))
            hard = {"ownership_conflict", "source_issue", "duplicate_preview", "candidate_gap", "incomplete_candidate_validation"}
            if row["_status"] == "review" and not failures.intersection(hard):
                if "foreground_colours" in failures:
                    row.update(_reason="局部颜色存在差异，请确认是否为同款不同色。", _reason_code="local_colour_difference")
                elif "coherent_difference" in failures:
                    row.update(_reason="局部内容尚未核实，请放大确认。", _reason_code="local_content_unverified")
            if row.get("issue"):
                row.update(_status="unmatched", _file_id=None, _reason_code="workbook_image_issue", _reason=row["issue"])
            for field in ("status", "file_id", "reason", "reason_code"):
                row["_initial_"+field] = row["_"+field]
        self._plan(job)

    def _retrieve_ai_first(self, identifier):
        from .ai_first import retrieve
        from .ai_usage import empty_usage
        from .matching import _verify_prepared_bindings
        job = self._start_operation(identifier, "ai_review", "AI 正在查找对应图片…")
        token, revision = job["_operation_token"], job.get("revision", 0)
        prepared = job["_prepared_matching"]
        with self.job_operation(identifier, internal=True), self.lock:
            rows, files = copy.deepcopy(job["rows"]), copy.deepcopy(job["files"])
            leg = {"state": "queued"}
            job["_parallel_progress"] = {"ai": {"done": 0, "total": 0, "finished": False},
                "cpu": {"done": 0, "total": 0, "finished": False}}
        def current():
            with self.lock:
                return (self.jobs.get(identifier) is job and job.get("_operation_token") == token
                        and job.get("revision", 0) == revision and job.get("status") == "ai_review")
        def phase_progress(phase, done=0, total=0, *, finished=False):
            with self.lock:
                if not current():
                    return
                stages = job["_parallel_progress"]
                stages[phase] = {"done": done, "total": total, "finished": finished}
                cpu, ai = stages["cpu"], stages["ai"]
                if not cpu["finished"] and not ai["finished"]:
                    # These are independent stages; there is no meaningful
                    # shared percentage or sum of their denominators.
                    job["progress"] = {"phase": "parallel_verification", "step_label": "AI 查找与本机核验",
                        "message": (f"AI 查找 {ai['done']} / {ai['total']} 组；" if ai["total"] else "AI 正在准备图片；")
                            + (f"本机已核验 {cpu['done']} / {cpu['total']} 张。" if cpu["total"] else "本机核验等待开始。"),
                        "current": 0, "total": 0}
                else:
                    remaining, name, label = (ai, "ai_retrieval", "AI 查找对应图片") if cpu["finished"] else (cpu, "local_verification", "本机核验图案与文件")
                    job["progress"] = {"phase": name, "step_label": label,
                        "message": "本机核验完成，正在等待 AI 查找结果…" if cpu["finished"] else "AI 查找已结束，本机正在核验图案与文件…",
                        "current": remaining["done"], "total": remaining["total"]}
        def checkpoint(artifact):
            if not current():
                return
            with self.job_operation(identifier, internal=True):
                if current():
                    job["_ai_first_artifact"] = artifact
        def progress(done, total):
            phase_progress("ai", done, total)
        def verify():
            started = time.perf_counter()
            with self.lock:
                leg.update(state="running")
                if current():
                    waited = started-leg["queued_at"]
                    for name in ("queue_seconds", "queue_cpu_seconds"):
                        job["timings"][name] = round(job["timings"].get(name, 0)+waited, 3)
            try:
                if not current():
                    return None
                self._check_import_sources(job)
                from .matching import match_prepared
                # Full independent validation proceeds while the provider is
                # working. Model rankings never omit a competing source.
                matched = match_prepared(prepared,
                    lambda message, c=0, t=1: phase_progress("cpu", c, t))
                self._check_import_sources(job)
                return matched
            except Exception:
                with self.lock:
                    leg["failed"] = True
                raise
            finally:
                with self.lock:
                    leg.update(state="finished", elapsed=time.perf_counter()-started)
                phase_progress("cpu", len(rows), len(rows), finished=True)
        verification = None
        started = time.perf_counter()
        try:
            with self.lock:
                # Reserve the resource order and enqueue atomically, just as
                # _submit does for normal jobs. A concurrent import cannot
                # overtake this leg while its displayed position says otherwise.
                self._queue_sequence += 1
                leg.update(order=self._queue_sequence, queued_at=time.perf_counter())
                job["_cpu_leg"] = leg
                verification = self.pool.submit(verify)
            phase_progress("ai")
            try:
                result = retrieve(self, identifier, rows, files, progress=progress,
                    checkpoint=checkpoint, is_current=lambda: current() and not leg.get("failed"))
            except Exception:
                artifact = job.get("_ai_first_artifact", {})
                result = {"status": "failed", "error_code": "review_unavailable", "proposals": [],
                          "usage": artifact.get("usage") or empty_usage(), "artifact": artifact}
            elapsed_ai = time.perf_counter()-started
            phase_progress("ai", finished=True)
            with self.job_operation(identifier, internal=True), self.lock:
                if current():
                    job["_ai_first_result"] = result
                    job["_ai_first_artifact"] = result.get("artifact", {})
                    job.setdefault("_ai_first_runs", []).append(copy.deepcopy(result.get("artifact", {})))
                    # Only local fixed diagnostics are exposed. Never surface
                    # provider text or raw exception payloads as job warnings.
                    for warning in result.get("artifact", {}).get("warnings", []):
                        if warning in {
                            "候选检索记录未能完整保存，请保留本批任务并联系管理员。",
                            "候选检索状态更新未完成，请联系管理员核对记录。",
                            "候选检索累计用量保存未完成，费用可能不完整。",
                        } and warning not in job["warnings"]:
                            job["warnings"].append(warning)
                    job["ai_retrieval"] = {"status": result["status"], "usage": result.get("usage", empty_usage()),
                        "proposed": len(result.get("proposals", [])), "error_code": result.get("error_code"),
                        "message": "AI 查找已结束，等待本机核验。"}
                    job["timings"]["ai_retrieval_seconds"] = round(elapsed_ai, 3)
            matched = verification.result()
            if not current():
                return
            # CPU may have finished before the network response. Recheck the
            # complete inputs at join as well as inside each independent leg.
            self._check_import_sources(job)
            _verify_prepared_bindings(prepared)
            proposals = result.get("proposals", [])
            counts = collections.Counter(p.get("file_id") for p in proposals if p.get("file_id"))
            with self.job_operation(identifier, internal=True), self.lock:
                if not current():
                    return
                self._apply_match_result(job, matched)
                suggested = {p["row_id"]: p for p in proposals}
                for row in job["rows"]:
                    proposal = suggested.get(row["id"])
                    if proposal:
                        row["ai_retrieval"] = {"candidate_id": proposal.get("file_id"),
                            "verdict": proposal.get("verdict", "uncertain"), "reason": proposal.get("reason", ""),
                            "model": proposal.get("model"), "outcome": "suggestion",
                            "reason_code": "retrieval_conflict" if counts.get(proposal.get("file_id"), 0) > 1 else "retrieval_suggestion"}
                job["revision"] += 1
                job["timings"]["local_verification_seconds"] = round(leg["elapsed"], 3)
                job["timings"]["processing_seconds"] = round(time.perf_counter()-job["_started_perf"], 3)
                job["ai_retrieval"]["message"] = ("AI 查找完成；通过项均经过本机独立核验。"
                    if result.get("status") == "completed" else "AI 查找未完整完成，已由本机完成匹配。")
                job["ai_review"] = {"mode": self.ai_validation.snapshot()["mode"], "eligible": 0,
                    "reviewed": 0, "suggested_same": 0, "auto_passed": 0, "unresolved": job["stats"]["review"],
                    "skipped": 0, "usage": empty_usage(), "can_retry": False,
                    "message": "AI 全库查找建议见图片对照；剩余疑难项可按需补充二次复核。"}
                job["progress"] = {"message": "核验完成", "current": len(job["rows"]), "total": len(job["rows"])}
                job["status"] = "ready"
        except Exception as exc:
            with self.lock:
                if current():
                    self._fail(identifier, exc)
        finally:
            # The tracked parent cannot finish while an untracked CPU child
            # still touches previews; close() keeps all pools alive until here.
            if verification is not None:
                try:
                    verification.result()
                except Exception:
                    pass
            with self.lock:
                if (self.jobs.get(identifier) is job and job.get("_operation_token") == token
                        and job.get("_prepared_matching") is prepared):
                    job.pop("_prepared_matching", None)
                    job.pop("_cpu_leg", None)
                    job.pop("_parallel_progress", None)

    def _after_match_ai(self, identifier):
        job = self._start_operation(identifier, "ai_review", "正在检查 AI 复核条件…")
        token = job["_operation_token"]
        try:
            self._review_ai(identifier)
        except Exception as error:
            self._end_ai_operation(identifier, job, token, error)
            return
        self._end_ai_operation(identifier, job, token)

    def _end_ai_operation(self, identifier, expected_job, token, error=None):
        """A late phase must not restore ready over replacement/error/cancel."""
        with self.lock:
            if self.jobs.get(identifier) is not expected_job:
                return
        try:
            with self.job_operation(identifier, internal=True), self.lock:
                job = self.jobs.get(identifier)
                if (job is not expected_job or job.get("_operation_token") != token
                        or job.get("status") != "ai_review"):
                    return
                if error is not None:
                    job.update(status="error", error=str(error) or type(error).__name__)
                else:
                    job["status"] = "ready"
                if job.get("_started_perf"):
                    job["timings"]["processing_seconds"] = round(time.perf_counter() - job["_started_perf"], 3)
        except KeyError:
            # The task may have been removed between the identity precheck and
            # acquiring its lock. There is no current task to update.
            return

    @staticmethod
    def _stage_for(job):
        if job.get("_queue_stage"):
            return job["_queue_stage"]
        return {"ai_review": "ai", "exporting": "export"}.get(job.get("status"), "cpu")

    def _queue_ahead(self, job, stage, order):
        """Count each resource leg, including CPU checks during an AI wait."""
        with self.lock:
            ahead = 0
            for other in self.jobs.values():
                if other is job:
                    continue
                normal = (self._stage_for(other) == stage and other["status"] in BUSY
                    and (other.get("_queue_order", float("inf")) < order
                    or ("_queue_order" not in other and other["status"] != "queued")))
                leg = other.get("_cpu_leg", {})
                parallel = (stage == "cpu" and leg.get("state") in {"queued", "running"}
                    and (leg.get("state") == "running" or leg.get("order", float("inf")) < order))
                ahead += bool(normal or parallel)
            return ahead

    def _plan(self, job):
        rows = job["rows"]
        files = {f["id"]: f for f in job["files"]}
        ai_cache = {}
        reserved = {str(n).casefold() for n in job["_reserved"] if str(n)}
        for row in rows:
            row["status"] = row.get("_status", "unmatched")
            row["reason"] = row.get("_reason", "")
            row["reason_code"] = row.get("_reason_code", "not_verified")
            row["file_id"] = row.get("_file_id")
            row["planned_number"] = row.get("number", "")
            if row["status"] not in ACCEPTED:
                continue
            selected = files.get(row["file_id"])
            if row.get("issue"):
                row.update(status="unmatched", file_id=None, reason=row["issue"], reason_code="workbook_image_issue")
            elif not selected or not selected.get("preview_path"):
                row.update(status="unmatched", file_id=None, reason="对应文件没有可读取的预览。", reason_code="preview_unavailable")
            elif row["status"] == "auto" and (selected.get("issue") or selected.get("page_count", 1) != 1):
                row.update(status="review", file_id=None, reason=selected.get("issue") or "多个画板尚未完整验证。", reason_code="file_requires_review")
            elif row["status"] == "auto" and row.get("_accepted_by") == "ai":
                from .ai_policy import select_review_case, evaluate_suggestion
                case = select_review_case({**row, "status": "review"}, rows, job["files"], ai_cache)
                verdict = evaluate_suggestion(case, row.get("_ai_envelope"), self.ai_validation.load())
                if not verdict["accepted"]:
                    row.update(status="review", file_id=None, reason=verdict["reason"], reason_code=verdict["reason_code"])
        accepted = [r for r in rows if r["status"] in ACCEPTED]
        by_file = collections.defaultdict(list)
        by_number = collections.defaultdict(list)
        for row in accepted:
            by_file[row["file_id"]].append(row)
            if row.get("number"):
                by_number[row["number"].casefold()].append(row)
        for group in list(by_file.values()) + list(by_number.values()):
            if len(group) > 1:
                for row in group:
                    row["status"] = "review"
                    row["reason"] = "多行使用了相同文件或相同编号，请保留一个对应关系，其余跳过。"
                    row["reason_code"] = "ownership_or_number_conflict"
        next_number = job["start_number"]
        for row in sorted(rows, key=lambda r: r["row_number"]):
            if row["status"] not in ACCEPTED:
                continue
            if not row.get("file_id"):
                row["status"], row["reason"] = "review", "缺少已确认的对应文件。"
                row["reason_code"] = "missing_assignment"
                continue
            if row.get("number"):
                if not valid_number(row["number"]):
                    row["status"], row["reason"] = "review", "已有编号包含 Windows 文件名不允许的字符，请在源表修正后重新导入，或跳过此行。"
                    row["reason_code"] = "invalid_number"
                continue
            while next_number <= 9999 and f"HSD{next_number:04d}".casefold() in reserved:
                next_number += 1
            if next_number > 9999:
                row["status"], row["reason"] = "review", "4 位流水号已用完，请调整起始号后重新导入，或跳过此行。"
                row["reason_code"] = "number_exhausted"
                continue
            number = f"HSD{next_number:04d}"
            row["planned_number"] = number
            reserved.add(number.casefold())
            next_number += 1
        counts = collections.Counter(r["status"] for r in rows)
        job["stats"] = {"total": len(rows), **{s: counts[s] for s in ("auto", "confirmed", "review", "unmatched", "skipped")},
                        "exportable": counts["auto"] + counts["confirmed"],
                        "pending": counts["review"] + counts["unmatched"] + counts["skipped"],
                        "needs_attention": counts["review"] + counts["unmatched"],
                        "ai_auto": sum(r["status"] == "auto" and r.get("_accepted_by") == "ai" for r in rows),
                        "new_numbers": sum(r["status"] in ACCEPTED and not r.get("number") for r in rows)}

    def _review_ai(self, identifier):
        from .ai_workflow import review_job
        try:
            review_job(self, identifier)
        except Exception:
            with self.job_operation(identifier, internal=True):
                job = self.jobs[identifier]
                # A workflow-wide failure cannot retain AI acceptance whose
                # final proof was not committed. Local/human decisions remain.
                # Downgrade first so planning has no AI proof IO to repeat.
                for row in job["rows"]:
                    if row.get("_accepted_by") == "ai" and row.get("_status") == "auto":
                        row.update(_status="review", _file_id=None,
                                   _reason="AI复核未完整结束，请人工核对。", _reason_code="review_unavailable")
                self._plan(job)
                job.setdefault("ai_review", {})["message"] = "AI复核暂未完成，本批保留原有匹配结果。"
                job["warnings"].append("AI复核未完成，疑难项仍需人工处理。")

    def review_ai(self, identifier):
        with self.job_operation(identifier):
            job = self._get(identifier)
            if job["status"] != "ready":
                raise ValueError("当前任务不能重新运行AI复核。")
            settings = self.ai_settings.snapshot()
            if not settings["enabled"] or not settings["configured"]:
                raise ValueError("请先在AI设置中填写密钥并启用复核。")
            if job.get("_ai_runs", 0) >= 3:
                raise ValueError("本批已完成多次复核，请人工处理剩余项，或重新导入。")
            if job.get("_owner_id") is None and any(j["status"] in BUSY for j in self.jobs.values()):
                raise ValueError("当前仍有任务正在处理。")
            job["status"] = "queued" if job.get("_owner_id") is not None else "ai_review"
            job["progress"] = {"message": "正在排队等待 AI 复核…", "current": 0, "total": 1}
            with self.lock:
                self._submit(job, self._rerun_ai)

    def _rerun_ai(self, identifier):
        job = self._start_operation(identifier, "ai_review", "正在进行 AI 复核…")
        token = job["_operation_token"]
        try:
            self._review_ai(identifier)
        except Exception as error:
            self._end_ai_operation(identifier, job, token, error)
            return
        self._end_ai_operation(identifier, job, token)

    def resolve(self, identifier, row_id, file_id, revert=False):
        with self.job_operation(identifier):
            job = self._get(identifier)
            if job["status"] != "ready":
                raise ValueError("当前任务不能修改匹配结果。")
            row = next((r for r in job["rows"] if r["id"] == row_id), None)
            if row is None:
                raise ValueError("找不到这条表格记录。")
            previous = {key: row.get(key) for key in ("_status", "_file_id", "_reason", "_reason_code", "_accepted_by")}
            if revert:
                for key in ("status", "file_id", "reason", "reason_code"):
                    row["_" + key] = row.get("_initial_" + key, "review" if key == "status" else None)
                row["_accepted_by"] = row.get("_initial_accepted_by", "local")
            elif file_id is None:
                row["_status"], row["_file_id"], row["_reason"] = "skipped", None, "员工选择跳过；该行保留原状。"
                row["_reason_code"] = "user_skipped"
                row["_accepted_by"] = "human"
            else:
                if row.get("issue"):
                    raise ValueError(f"该行表格有问题：{row['issue']}。请修正后重新导入，或跳过此行。")
                selected = next((f for f in job["files"] if f["id"] == file_id), None)
                if selected is None or not selected.get("preview_path") or not Path(selected["preview_path"]).is_file():
                    raise ValueError("该文件没有可用预览，不能确认匹配。")
                owner = next((r for r in job["rows"] if r is not row and r["_status"] in ACCEPTED and r.get("_file_id") == file_id), None)
                if owner:
                    raise ValueError(f"此文件已对应表格第 {owner['row_number']} 行。请先跳过原对应行，再重新选择。")
                row["_status"], row["_file_id"], row["_reason"] = "confirmed", file_id, "员工已确认对应关系。"
                row["_reason_code"] = "user_confirmed"
                row["_accepted_by"] = "human"
            if any(row.get(key) != value for key, value in previous.items()):
                history = job.setdefault("_history", [])
                history.append({"row_id": row_id, "previous": previous})
                del history[:-100]
                job["revision"] = job.get("revision", 0) + 1
            self._plan(job)
            return self.snapshot(identifier)

    def undo(self, identifier):
        with self.job_operation(identifier):
            job = self._get(identifier)
            if job["status"] != "ready":
                raise ValueError("当前任务不能撤销操作。")
            history = job.get("_history", [])
            if not history:
                raise ValueError("没有可撤销的操作。")
            action = history.pop()
            row = next(r for r in job["rows"] if r["id"] == action["row_id"])
            row.update(action["previous"])
            job["revision"] = job.get("revision", 0) + 1
            self._plan(job)
            result = self.snapshot(identifier)
            result["last_undone_row_id"] = row["id"]
            return result

    def export(self, identifier, expected_revision=None):
        with self.job_operation(identifier):
            job = self._get(identifier)
            if job["status"] != "ready":
                raise ValueError("当前任务不能导出；已完成的结果可直接打开输出文件夹。")
            if expected_revision is not None and (isinstance(expected_revision, bool)
                    or expected_revision != job.get("revision", 0)):
                raise ValueError("匹配结果已在其他页面更新，请重新查看摘要后导出。")
            self._plan(job)
            if not job["stats"]["exportable"]:
                raise ValueError("还没有可导出的对应关系，请先确认至少一项匹配。")
            job["status"] = "queued" if job.get("_owner_id") is not None else "exporting"
            job["progress"] = {"message": "正在排队等待导出…", "current": 0, "total": 1}
            job["error"] = None
            job["_export_started_perf"] = time.perf_counter()
            with self.lock:
                self._submit(job, self._export)

    def _export(self, identifier):
        job = self._start_operation(identifier, "exporting", "正在导出结果…")
        staging = None
        staging_created = False

        def verify_ai_comparison_sources():
            # An excluded rival is still part of the uniqueness proof. Verify
            # all originals behind that proof, even if they are not exported.
            from .ai_policy import select_review_case, evaluate_suggestion
            from .ai_workflow import _sources_unchanged
            digests = {}

            def current_digest(path):
                if path not in digests:
                    digests[path] = sha256(path)
                return digests[path]

            for row in job["rows"]:
                if row["status"] != "auto" or row.get("_accepted_by") != "ai":
                    continue
                case = select_review_case({**row, "status": "review"}, job["rows"], job["files"])
                if not case.get("eligible") or not _sources_unchanged(case, job["files"], current_digest):
                    raise ValueError("AI复核所依据的原文件发生了变化，请重新导入再导出。")
                verdict = evaluate_suggestion(case, row.get("_ai_envelope"), self.ai_validation.load())
                if not verdict["accepted"]:
                    raise ValueError("导出期间AI复核依据或验证资格发生变化，请重新导入并核对结果。")

        try:
            from .workbook import write_numbered_workbook
            if sha256(job["_workbook_path"]) != job["_input_digest"]:
                raise ValueError("导入后源表格发生了变化，请重新导入，避免把编号填到错误的记录。")
            if job.get("_source_archive_digest") and sha256(job["_source_path"]) != job["_source_archive_digest"]:
                raise ValueError("导入后源压缩包发生了变化，请重新导入再导出。")
            verify_ai_comparison_sources()
            completed = job.get("_completed_export")
            if (completed and completed["revision"] == job.get("revision", 0)
                    and completed["plan"] == self._export_plan(job)):
                files = {f["id"]: f for f in job["files"]}
                for row in job["rows"]:
                    if row["status"] in ACCEPTED:
                        source = files[row["file_id"]]
                        if source.get("source_sha256") and sha256(source["source_path"]) != source["source_sha256"]:
                            raise ValueError("匹配后源文件发生了变化，请重新导入再导出。")
                self._finish_export(job, Path(completed["path"]), completed["report"], completed["timings"])
                return
            job.pop("_completed_export", None)
            root = Path(job["_output_root"])
            root.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            final = root / f"HSD编号结果_{stamp}_{identifier[:6]}"
            staging = root / f".HSD处理中_{identifier}"
            staging.mkdir(exist_ok=False)
            staging_created = True
            target_files = staging / "已编号AI"
            target_files.mkdir()
            files = {f["id"]: f for f in job["files"]}
            rows = [r for r in job["rows"] if r["status"] in ACCEPTED]
            assignments = {}
            mapping = []
            verified_outputs = {}
            for index, row in enumerate(rows, 1):
                self._progress(identifier, f"正在导出 {index}/{len(rows)} 个文件…", index, len(rows) + 1)
                source = Path(files[row["file_id"]]["source_path"])
                expected_digest = files[row["file_id"]].get("source_sha256")
                number = row["planned_number"]
                if not valid_number(number):
                    raise ValueError(f"第 {row['row_number']} 行编号不能用作文件名。")
                destination = target_files / (number + ".ai")
                # Exclusive creation also catches Windows case-insensitive name collisions.
                digest = hashlib.sha256()
                with source.open("rb") as src, destination.open("xb") as dst:
                    for chunk in iter(lambda: src.read(4 * 1024 * 1024), b""):
                        dst.write(chunk)
                        digest.update(chunk)
                copied_digest = sha256(destination)
                if copied_digest != digest.hexdigest():
                    raise ValueError("导出文件校验失败，请检查磁盘空间后重试。")
                if expected_digest and copied_digest != expected_digest:
                    raise ValueError(f"文件 {source.name} 在匹配后发生了变化，请重新导入再导出。")
                verified_outputs[destination.relative_to(staging).as_posix()] = copied_digest
                if not row["number"]:
                    assignments[row["row_number"]] = number
                mapping.append({"row": row["row_number"], "old_number": row["number"], "number": number,
                                "source": files[row["file_id"]]["relative_path"], "output": destination.name,
                                "confirmation": "人工确认" if row["status"] == "confirmed" else "AI复核通过" if row.get("_accepted_by") == "ai" else "自动匹配", "sha256": copied_digest})
            workbook_out = staging / (Path(job["_workbook_path"]).stem + "_已编号.xlsx")
            write_numbered_workbook(job["_snapshot_workbook"], str(workbook_out), job["sheet_name"], assignments)
            # The plan, rather than files discovered in an output directory,
            # defines every allowed download member.
            job["_export_members"] = [*(f"已编号AI/{entry['output']}" for entry in mapping), workbook_out.name]
            if sha256(job["_workbook_path"]) != job["_input_digest"]:
                raise ValueError("导出期间源表格发生了变化，请重新导入后再处理。")
            if job.get("_source_archive_digest") and sha256(job["_source_path"]) != job["_source_archive_digest"]:
                raise ValueError("导出期间源压缩包发生了变化，请重新导入后再处理。")
            verify_ai_comparison_sources()
            pending = [{"row": r["row_number"], "number": r["number"], "status": r["status"],
                        "reason_code": r.get("reason_code"), "reason": r["reason"] or "没有已确认的对应文件"}
                       for r in job["rows"] if r["status"] not in ACCEPTED]
            used = {r["file_id"] for r in rows}
            unused = [{"name": f["relative_path"], "reason": f.get("issue") or "未用于本批导出"} for f in job["files"] if f["id"] not in used]
            records_root = self.record_directory(identifier, "export_records")
            records = records_root / uuid.uuid4().hex
            records.mkdir()
            with (records / "对应关系.csv").open("w", encoding="utf-8-sig", newline="") as stream:
                writer = csv.writer(stream)
                writer.writerow(["表格行号", "原编号", "输出编号", "原文件", "输出文件", "确认方式", "SHA256"])
                for entry in mapping:
                    writer.writerow([csv_safe(entry[k]) for k in ("row", "old_number", "number", "source", "output", "confirmation", "sha256")])
            with (records / "待处理清单.csv").open("w", encoding="utf-8-sig", newline="") as stream:
                writer = csv.writer(stream)
                writer.writerow(["类型", "表格行号", "已有编号或文件名", "说明", "处理状态"])
                for item in pending:
                    label = {"review": "待人工审核", "unmatched": "无法处理", "skipped": "已跳过"}[item["status"]]
                    writer.writerow(["表格记录", item["row"], csv_safe(item["number"]), csv_safe(item["reason"]), label])
                for item in unused:
                    writer.writerow(["未使用文件", "", csv_safe(item["name"]), csv_safe(item["reason"]), "未使用"])
            timings = dict(job.get("timings", {}))
            timings["export_seconds"] = round(time.perf_counter() - job["_export_started_perf"], 3)
            batch_started = job.get("_batch_started_perf", job.get("_started_perf"))
            if batch_started:
                timings["batch_elapsed_seconds"] = round(time.perf_counter() - batch_started, 3)
            report = {"exported": len(mapping), "new_numbers": len(assignments), "preserved_numbers": len(mapping) - len(assignments),
                      "pending": len(pending), "unused_files": len(unused), "workbook": workbook_out.name,
                      "input_sha256": job["_input_digest"], "sheet": job["sheet_name"], "version": __version__,
                      "stats": dict(job["stats"]), "timings": timings, "ai_review": job.get("ai_review"),
                      "matching_mode": job.get("matching_mode", "local"), "ai_retrieval": job.get("ai_retrieval")}
            decisions = [{key: row.get(key) for key in ("row_number", "status", "file_id", "reason", "reason_code", "diagnostics", "evidence", "ai_review", "ai_retrieval")}
                         for row in job["rows"]]
            (records / "处理记录.json").write_text(json.dumps({**report, "mapping": mapping, "pending_rows": pending,
                    "unused": unused, "decision_records": decisions,
                    "ai_observations": job.get("_ai_observation_artifact"),
                    "ai_observation_runs": job.get("_ai_observation_runs", []),
                    "ai_first_runs": job.get("_ai_first_runs", [])}, ensure_ascii=False, indent=2, allow_nan=False), "utf-8")
            if final.exists():
                raise ValueError("输出文件夹已存在，请重新导入后重试。")
            staging.rename(final)
            job["_records_dir"] = str(records)
            job["_record_manifest"] = {name: sha256(records / name) for name in
                                      ("处理记录.json", "对应关系.csv", "待处理清单.csv")}
            job["_completed_export"] = {"path": str(final), "report": report, "timings": timings,
                "revision": job.get("revision", 0), "plan": self._export_plan(job),
                "members": list(job["_export_members"]),
                "records_dir": str(records),
                "record_manifest": job["_record_manifest"],
                "manifest": self._output_manifest(job, final, verified_outputs)}
            self._finish_export(job, final, report, timings)
        except Exception as exc:
            # Only remove the exact staging directory created by this invocation.
            if staging_created and staging and staging.is_dir() and staging.name == f".HSD处理中_{identifier}" and staging.parent.resolve() == Path(job["_output_root"]).resolve():
                try:
                    shutil.rmtree(staging)
                except OSError:
                    logging.exception("Could not clean partial export %s", staging)
            with self.job_operation(identifier, internal=True), self.lock:
                job["status"] = "ready"
                job["error"] = str(exc)
                if staging_created and staging and staging.exists():
                    job["error"] += f" 未完成的临时结果暂被占用：{staging}。关闭占用它的程序后，重新导入再导出。"
                job["progress"] = {"message": "导出未完成，可以修正问题后重试", "current": 0, "total": 1}

    @staticmethod
    def _export_plan(job):
        return [(r["id"], r["status"], r.get("file_id"), r.get("planned_number"), r.get("_accepted_by"))
                for r in job["rows"]]

    def _output_members(self, job, directory):
        """Resolve only the final server plan's AI names and one workbook."""
        directory = Path(directory)
        root = directory.resolve(strict=True)
        if _is_link_or_reparse(directory) or _is_link_or_reparse(directory.parent) or root.parent != Path(job["_output_root"]).resolve():
            raise ValueError("结果目录位置异常，不能打包。")
        expected = [*(f"已编号AI/{row['planned_number']}.ai" for row in job["rows"] if row["status"] in ACCEPTED),
                    Path(job["_workbook_path"]).stem + "_已编号.xlsx"]
        declared = job.get("_export_members", expected)
        if (len(declared) != len(set(item.casefold() for item in declared))
                or set(declared) != set(expected)):
            raise ValueError("导出计划文件发生变化，不能生成下载包。")
        result = []
        for relative in declared:
            entry = directory / relative
            for part in (entry, entry.parent):
                if part.exists() and (_is_link_or_reparse(part) or not part.resolve(strict=True).is_relative_to(root)):
                    raise ValueError("结果包含链接或目录之外的文件，不能打包。")
            if not entry.is_file():
                raise ValueError("导出结果文件发生变化，不能生成下载包。")
            result.append(entry)
        return sorted(result)

    def _output_manifest(self, job, directory, verified_outputs=None):
        # AI copies were independently reread immediately after copying. Reuse
        # that verified digest; packaging still hashes every byte against it,
        # so edits between copy and packaging cannot become the new baseline.
        verified_outputs = verified_outputs or {}
        result = {}
        for path in self._output_members(job, directory):
            relative = path.relative_to(directory).as_posix()
            result[relative] = verified_outputs.get(relative) or sha256(path)
        if not set(verified_outputs).issubset(result):
            raise ValueError("导出结果文件发生变化，不能生成下载包。")
        return result

    def _task_work_root(self, job):
        identifier = job["id"]
        if Path(identifier).name != identifier or identifier in {".", ".."}:
            raise ValueError("任务下载目录异常。")
        expected = self.data_dir.absolute() / "jobs" / identifier
        work_dir = Path(job["_work_dir"]).absolute()
        if (work_dir != expected or _is_link_or_reparse(work_dir) or _is_link_or_reparse(work_dir.parent)
                or work_dir.resolve(strict=True) != expected):
            raise ValueError("任务下载目录异常。")
        return expected

    def task_records_root(self, identifier):
        """Persistent private records, separate from disposable task caches."""
        if not isinstance(identifier, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", identifier):
            raise ValueError("任务记录目录异常。")
        root = self.data_dir.absolute() / "task_records"
        root.mkdir(exist_ok=True)
        if _is_link_or_reparse(root) or root.resolve().parent != self.data_dir.resolve():
            raise ValueError("任务记录目录异常。")
        expected = root / identifier
        expected.mkdir(exist_ok=True)
        if _is_link_or_reparse(expected) or expected.resolve().parent != root.resolve():
            raise ValueError("任务记录目录异常。")
        return expected

    def record_directory(self, identifier, section):
        if section not in {"ai_runs", "ai_first_runs", "export_records"}:
            raise ValueError("任务记录类型无效。")
        root = self.task_records_root(identifier)
        path = root / section
        path.mkdir(exist_ok=True)
        if _is_link_or_reparse(path) or path.resolve().parent != root.resolve():
            raise ValueError("任务记录目录异常。")
        return path

    def _package_download(self, job, directory):
        """Create an atomic, task-private archive of verified output copies only."""
        directory = Path(directory)
        manifest = job["_completed_export"]["manifest"]
        members = self._output_members(job, directory)
        if {p.relative_to(directory).as_posix() for p in members} != set(manifest):
            raise ValueError("导出结果文件发生变化，不能生成下载包。")
        if set(job["_completed_export"].get("members", [])) != set(manifest):
            raise ValueError("已完成导出计划发生变化，不能生成下载包。")
        self._verify_export_records(job)
        work_root = self._task_work_root(job)
        target = work_root / "HSD编号结果.zip"
        if target.is_symlink() or (target.exists() and _is_link_or_reparse(target)):
            raise ValueError("任务下载文件位置异常。")
        temporary = work_root / (".download-" + uuid.uuid4().hex + ".tmp")
        self._progress(job["id"], "正在打包下载结果…", 0, len(members))
        try:
            with temporary.open("xb") as stream:
                with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as archive:
                    for index, path in enumerate(members, 1):
                        relative = path.relative_to(directory).as_posix()
                        digest = hashlib.sha256()
                        member = zipfile.ZipInfo(directory.name + "/" + relative)
                        member.compress_type = _download_compression(path)
                        # Python 3.12 exposes per-member level through this
                        # ZipInfo slot; retain the previously measured level 1.
                        member._compresslevel = 1 if member.compress_type == zipfile.ZIP_DEFLATED else None
                        with path.open("rb") as source, archive.open(member, "w", force_zip64=True) as destination:
                            for chunk in iter(lambda: source.read(4 * 1024 * 1024), b""):
                                digest.update(chunk)
                                destination.write(chunk)
                        if digest.hexdigest() != manifest[relative] or _is_link_or_reparse(path) or not path.resolve().is_relative_to(directory.resolve()):
                            raise ValueError("打包期间导出结果发生变化，请检查结果后重试。")
                        self._progress(job["id"], "正在打包下载结果…", index, len(members))
                stream.flush()
                os.fsync(stream.fileno())
            digest = sha256(temporary)
            os.replace(temporary, target)
            with self.lock:
                job["_download_path"], job["_download_sha256"] = str(target), digest
        finally:
            temporary.unlink(missing_ok=True)

    def _finish_export(self, job, directory, report, timings):
        if job.get("_downloadable"):
            started = time.perf_counter()
            self._package_download(job, directory)
            timings["packaging_seconds"] = round(time.perf_counter() - started, 3)
        timings["export_total_seconds"] = round(time.perf_counter() - job["_export_started_perf"], 3)
        batch_started = job.get("_batch_started_perf", job.get("_started_perf"))
        if batch_started:
            timings["batch_elapsed_seconds"] = round(time.perf_counter() - batch_started, 3)
        self._record_export_timings(job, timings)
        with self.job_operation(job["id"], internal=True), self.lock:
            job["output_dir"], job["report"], job["status"] = str(directory), report, "done"
            job["timings"] = timings
            job["error"] = None
            job["progress"] = {"message": "结果已打包，可直接下载" if job.get("_downloadable") else "导出完成，原文件已保留",
                "current": report["exported"] + 1, "total": report["exported"] + 1}

    def _verify_export_records(self, job):
        completed = job.get("_completed_export") or {
            "records_dir": job.get("_records_dir"), "record_manifest": job.get("_record_manifest")}
        if not isinstance(completed.get("records_dir"), str) or not isinstance(completed.get("record_manifest"), dict):
            raise ValueError("导出验证记录发生变化，不能重用此前结果。")
        records = Path(completed["records_dir"])
        root = self.record_directory(job["id"], "export_records")
        manifest = completed.get("record_manifest", {})
        if (not records.is_dir() or records.parent != root or _is_link_or_reparse(records)
                or _is_link_or_reparse(root) or set(manifest) != {"处理记录.json", "对应关系.csv", "待处理清单.csv"}):
            raise ValueError("导出验证记录发生变化，不能重用此前结果。")
        for name, expected in manifest.items():
            path = records / name
            if not path.is_file() or _is_link_or_reparse(path) or sha256(path) != expected:
                raise ValueError("导出验证记录发生变化，不能重用此前结果。")

    def _record_export_timings(self, job, timings):
        """Append measured packaging timings only to the verified private log.

        Never re-baseline arbitrary changed record bytes: the previous manifest
        must match both the bytes read and the file immediately before replace.
        """
        self._verify_export_records(job)
        path = Path(job["_records_dir"]) / "处理记录.json"
        manifest = job["_record_manifest"]
        original = path.read_bytes()
        if hashlib.sha256(original).hexdigest() != manifest[path.name]:
            raise ValueError("导出验证记录发生变化，不能更新计时。")
        payload = json.loads(original)
        payload["timings"] = dict(timings)
        encoded = json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8")
        temporary = path.with_name(".timings-" + uuid.uuid4().hex + ".tmp")
        try:
            with temporary.open("xb") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            expected = hashlib.sha256(encoded).hexdigest()
            if sha256(temporary) != expected or sha256(path) != manifest[path.name] or _is_link_or_reparse(path):
                raise ValueError("导出验证记录发生变化，不能更新计时。")
            os.replace(temporary, path)
            manifest[path.name] = expected
        finally:
            temporary.unlink(missing_ok=True)

    def download_asset(self, identifier):
        with self.lock:
            job = self._get(identifier)
            if job["status"] != "done" or not job.get("_downloadable") or not job.get("_download_path"):
                raise KeyError("结果尚未准备好，请等待导出完成。")
            path = Path(job["_download_path"])
            root = self._task_work_root(job)
            if not path.is_file() or _is_link_or_reparse(path) or path.absolute().parent != root or path.resolve().parent != root:
                raise KeyError("结果下载文件不可用。")
            expected = job.get("_download_sha256")
        if not expected or sha256(path) != expected:
            raise ValueError("下载结果发生变化，请重新处理。")
        return path, expected

    def _get(self, identifier):
        if identifier not in self.jobs:
            raise KeyError("找不到该任务，请重新导入。")
        return self.jobs[identifier]

    def _fail(self, identifier, exc):
        with self.lock:
            self.jobs[identifier]["status"] = "error"
            self.jobs[identifier]["error"] = str(exc) or type(exc).__name__

    def snapshot(self, identifier):
        with self.job_operation(identifier):
            job = self._get(identifier)
            result = {k: copy.deepcopy(v) for k, v in job.items() if not k.startswith("_")}
            result["output_root"] = job["_output_root"]
            result["can_undo"] = job["status"] == "ready" and bool(job.get("_history"))
            result["revision"] = job.get("revision", 0)
            if job["status"] == "queued":
                order = job.get("_queue_order", float("inf"))
                stage = self._stage_for(job)
                ahead = self._queue_ahead(job, stage, order)
                result["queue_position"] = ahead + 1
                result["queue_stage"] = stage
            else:
                result["queue_position"] = 0
            cpu_leg = job.get("_cpu_leg", {})
            if cpu_leg.get("state") == "queued":
                position = self._queue_ahead(job, "cpu", cpu_leg["order"])+1
                result["verification_queue_position"] = position
                result["progress"]["message"] += f" 本机核验队列第 {position} 位。"
            result["download_ready"] = bool(job["status"] == "done" and job.get("_downloadable")
                and job.get("_download_path") and Path(job["_download_path"]).is_file())
            result["download_name"] = "HSD编号结果.zip" if job.get("_downloadable") else None
            if result.get("ai_review"):
                config = self.ai_settings.snapshot()
                result["ai_review"]["can_retry"] = bool(job["status"] == "ready" and config["enabled"]
                    and config["configured"] and job.get("_ai_runs", 0) < 3 and job["stats"].get("review"))
            for row in result["rows"]:
                for key in list(row):
                    if key.startswith("_") or key == "image_path":
                        del row[key]
            result["files"] = [{k: v for k, v in f.items() if k in {"id", "name", "relative_path", "issue"}} for f in result["files"]]
            return result

    def image_path(self, identifier, kind, item_id):
        with self.lock:
            job = self._get(identifier)
            collection, path_key = (job["rows"], "image_path") if kind == "row" else (job["files"], "preview_path")
            item = next((i for i in collection if i["id"] == item_id), None)
            if not item or not item.get(path_key):
                raise KeyError("没有可用的图片预览。")
            image = Path(item[path_key]).resolve()
            if not image.is_relative_to(Path(job["_work_dir"]).resolve()) or not image.is_file():
                raise KeyError("图片预览不可用。")
            return image

    def image_asset(self, identifier, kind, item_id, thumbnail=False):
        """Generate each task-scoped thumbnail/hash once; previews never change in a job."""
        with self.job_operation(identifier):
            job = self._get(identifier)
            source = self.image_path(identifier, kind, item_id)
            key = (kind, item_id, thumbnail)
            cached = job.setdefault("_image_assets", {}).get(key)
            if cached:
                return cached
            if thumbnail:
                from PIL import Image, ImageOps
                target = Path(job["_work_dir"]) / "thumbnails"
                target.mkdir(exist_ok=True)
                destination = target / f"{kind}_{item_id}.png"
                with Image.open(source) as original:
                    preview = ImageOps.exif_transpose(original).convert("RGBA")
                    preview.thumbnail((320, 120), Image.Resampling.LANCZOS)
                    preview.save(destination)
            else:
                destination = source
            asset = (destination, sha256(destination))
            job["_image_assets"][key] = asset
            return asset
