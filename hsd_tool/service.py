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
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from . import __version__

ACCEPTED = {"auto", "confirmed"}
BUSY = {"queued", "importing", "matching", "ai_review", "exporting"}
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
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="hsd")
        self.settings_path = self.data_dir / "settings.json"
        from .ai_settings import AiSettings
        shared_settings = Path(settings_dir) if settings_dir is not None else self.data_dir
        shared_settings.mkdir(parents=True, exist_ok=True)
        self.ai_settings = AiSettings(shared_settings)
        from .ai_usage import UsageLedger
        from .ai_registry import ValidationRegistry
        self.ai_usage = UsageLedger(shared_settings)
        self.ai_validation = ValidationRegistry(shared_settings)
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
        self.pool.shutdown(wait=True)
        self.jobs.clear()
        self.cleanup_cache()

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
        """Called under the manager lock; one worker serializes expensive jobs."""
        self._queue_sequence += 1
        job["_queue_order"] = self._queue_sequence
        job["_queued_perf"] = time.perf_counter()
        self.pool.submit(operation, job["id"])

    def _start_operation(self, identifier, status, message):
        with self.lock:
            job = self.jobs[identifier]
            queued_at = job.pop("_queued_perf", None)
            job.pop("_queue_order", None)
            if queued_at is not None:
                job.setdefault("timings", {})["queue_seconds"] = round(
                    job.get("timings", {}).get("queue_seconds", 0) + time.perf_counter() - queued_at, 3)
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
            from .matching import scan_and_match
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
            with self.lock:
                job["sheet_name"] = sheet["sheet_name"]
                job["rows"] = sheet["rows"]
                job["_reserved"] = sheet.get("reserved_numbers", [])
                job["status"] = "matching"
                job["timings"]["import_seconds"] = round(time.perf_counter() - job["_started_perf"], 3)
            matching_started = time.perf_counter()
            source_path = Path(job["_source_path"])
            if source_path.is_file():
                job["_source_archive_digest"] = job.get("_upload_digests", {}).get("source") or sha256(source_path)
            result = scan_and_match(job["_source_path"], sheet["rows"], str(Path(job["_work_dir"]) / "matching"),
                                    progress=lambda m, c=0, t=1: self._progress(identifier, m, c, t))
            if job.get("_source_archive_digest") and sha256(source_path) != job["_source_archive_digest"]:
                raise ValueError("读取时源压缩包发生了变化，请重新导入。")
            matches = {m["row_id"]: m for m in result["matches"]}
            with self.lock:
                job["files"] = result["files"]
                job["warnings"].extend(result.get("warnings", []))
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
                    hard_reasons = {"ownership_conflict", "source_issue", "duplicate_preview",
                                    "candidate_gap", "incomplete_candidate_validation"}
                    if row["_status"] == "review" and not failures.intersection(hard_reasons):
                        if "foreground_colours" in failures:
                            row["_reason"] = "局部颜色存在差异，请确认是否为同款不同色。"
                            row["_reason_code"] = "local_colour_difference"
                        elif "coherent_difference" in failures:
                            row["_reason"] = "局部内容尚未核实，请放大确认。"
                            row["_reason_code"] = "local_content_unverified"
                    if row.get("issue"):
                        row["_status"] = "unmatched"
                        row["_file_id"] = None
                        row["_reason_code"] = "workbook_image_issue"
                        row["_reason"] = row["issue"]
                    row["_initial_status"] = row["_status"]
                    row["_initial_file_id"] = row["_file_id"]
                    row["_initial_reason"] = row["_reason"]
                    row["_initial_reason_code"] = row["_reason_code"]
                self._plan(job)
                job["revision"] += 1
                job["timings"]["matching_seconds"] = round(time.perf_counter() - matching_started, 3)
                job["timings"]["processing_seconds"] = round(time.perf_counter() - job["_started_perf"], 3)
                job["progress"] = {"message": "自动验证完成", "current": len(job["rows"]), "total": len(job["rows"])}
            self._review_ai(identifier)
            with self.lock:
                job["status"] = "ready"
                job["timings"]["processing_seconds"] = round(time.perf_counter() - job["_started_perf"], 3)
        except Exception as exc:
            self._fail(identifier, exc)

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
            with self.lock:
                job = self.jobs[identifier]
                self._plan(job)
                job.setdefault("ai_review", {})["message"] = "AI复核暂未完成，本批保留原有匹配结果。"
                job["warnings"].append("AI复核未完成，疑难项仍需人工处理。")

    def review_ai(self, identifier):
        with self.lock:
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
            self._submit(job, self._rerun_ai)

    def _rerun_ai(self, identifier):
        try:
            self._start_operation(identifier, "ai_review", "正在进行 AI 复核…")
            self._review_ai(identifier)
        finally:
            with self.lock:
                self.jobs[identifier]["status"] = "ready"

    def resolve(self, identifier, row_id, file_id, revert=False):
        with self.lock:
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
        with self.lock:
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
        with self.lock:
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
            with (staging / "对应关系.csv").open("w", encoding="utf-8-sig", newline="") as stream:
                writer = csv.writer(stream)
                writer.writerow(["表格行号", "原编号", "输出编号", "原文件", "输出文件", "确认方式", "SHA256"])
                for entry in mapping:
                    writer.writerow([csv_safe(entry[k]) for k in ("row", "old_number", "number", "source", "output", "confirmation", "sha256")])
            with (staging / "待处理清单.csv").open("w", encoding="utf-8-sig", newline="") as stream:
                writer = csv.writer(stream)
                writer.writerow(["类型", "表格行号", "已有编号或文件名", "说明", "处理状态"])
                for item in pending:
                    label = {"review": "待人工审核", "unmatched": "无法处理", "skipped": "已跳过"}[item["status"]]
                    writer.writerow(["表格记录", item["row"], csv_safe(item["number"]), csv_safe(item["reason"]), label])
                for item in unused:
                    writer.writerow(["未使用文件", "", csv_safe(item["name"]), csv_safe(item["reason"]), "未使用"])
            timings = dict(job.get("timings", {}))
            timings["export_seconds"] = round(time.perf_counter() - job["_export_started_perf"], 3)
            if job.get("_started_perf"):
                timings["batch_elapsed_seconds"] = round(time.perf_counter() - job["_started_perf"], 3)
            report = {"exported": len(mapping), "new_numbers": len(assignments), "preserved_numbers": len(mapping) - len(assignments),
                      "pending": len(pending), "unused_files": len(unused), "workbook": workbook_out.name,
                      "input_sha256": job["_input_digest"], "sheet": job["sheet_name"], "version": __version__,
                      "stats": dict(job["stats"]), "timings": timings, "ai_review": job.get("ai_review")}
            decisions = [{key: row.get(key) for key in ("row_number", "status", "file_id", "reason", "reason_code", "diagnostics", "evidence", "ai_review")}
                         for row in job["rows"]]
            (staging / "处理记录.json").write_text(json.dumps({**report, "mapping": mapping, "pending_rows": pending,
                    "unused": unused, "decision_records": decisions,
                    "ai_observations": job.get("_ai_observation_artifact"),
                    "ai_observation_runs": job.get("_ai_observation_runs", [])}, ensure_ascii=False, indent=2, allow_nan=False), "utf-8")
            if final.exists():
                raise ValueError("输出文件夹已存在，请重新导入后重试。")
            staging.rename(final)
            if job.get("_downloadable"):
                job["_completed_export"] = {"path": str(final), "report": report, "timings": timings,
                    "revision": job.get("revision", 0), "plan": self._export_plan(job),
                    "manifest": self._output_manifest(job, final, verified_outputs)}
            self._finish_export(job, final, report, timings)
        except Exception as exc:
            # Only remove the exact staging directory created by this invocation.
            if staging_created and staging and staging.is_dir() and staging.name == f".HSD处理中_{identifier}" and staging.parent.resolve() == Path(job["_output_root"]).resolve():
                try:
                    shutil.rmtree(staging)
                except OSError:
                    logging.exception("Could not clean partial export %s", staging)
            with self.lock:
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
        """Only walk the exact output tree; reject links and escaping entries."""
        directory = Path(directory)
        root = directory.resolve(strict=True)
        if _is_link_or_reparse(directory) or _is_link_or_reparse(directory.parent) or root.parent != Path(job["_output_root"]).resolve():
            raise ValueError("结果目录位置异常，不能打包。")
        result = []
        for current, directories, files in os.walk(directory, followlinks=False):
            for name in directories + files:
                entry = Path(current) / name
                if _is_link_or_reparse(entry) or not entry.resolve(strict=True).is_relative_to(root):
                    raise ValueError("结果包含链接或目录之外的文件，不能打包。")
            for name in files:
                entry = Path(current) / name
                if not entry.is_file():
                    raise ValueError("结果包含不能读取的文件，不能打包。")
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

    def _package_download(self, job, directory):
        """Create an atomic, task-private archive of verified output copies only."""
        directory = Path(directory)
        manifest = job["_completed_export"]["manifest"]
        members = self._output_members(job, directory)
        if {p.relative_to(directory).as_posix() for p in members} != set(manifest):
            raise ValueError("导出结果文件发生变化，不能生成下载包。")
        work_root = self._task_work_root(job)
        target = work_root / "HSD编号结果.zip"
        if target.is_symlink() or (target.exists() and _is_link_or_reparse(target)):
            raise ValueError("任务下载文件位置异常。")
        temporary = work_root / (".download-" + uuid.uuid4().hex + ".tmp")
        self._progress(job["id"], "正在打包下载结果…", 0, len(members))
        try:
            with temporary.open("xb") as stream:
                with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=1) as archive:
                    for index, path in enumerate(members, 1):
                        relative = path.relative_to(directory).as_posix()
                        digest = hashlib.sha256()
                        with path.open("rb") as source, archive.open(directory.name + "/" + relative, "w", force_zip64=True) as destination:
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
            self._package_download(job, directory)
        with self.lock:
            job["output_dir"], job["report"], job["status"] = str(directory), report, "done"
            job["timings"] = timings
            job["error"] = None
            job["progress"] = {"message": "结果已打包，可直接下载" if job.get("_downloadable") else "导出完成，原文件已保留",
                "current": report["exported"] + 1, "total": report["exported"] + 1}

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
        with self.lock:
            job = self._get(identifier)
            result = {k: copy.deepcopy(v) for k, v in job.items() if not k.startswith("_")}
            result["output_root"] = job["_output_root"]
            result["can_undo"] = job["status"] == "ready" and bool(job.get("_history"))
            result["revision"] = job.get("revision", 0)
            if job["status"] == "queued":
                order = job.get("_queue_order", float("inf"))
                ahead = sum(j is not job and (j.get("_queue_order", float("inf")) < order
                    or ("_queue_order" not in j and j["status"] in BUSY and j["status"] != "queued"))
                    for j in self.jobs.values())
                result["queue_position"] = ahead + 1
            else:
                result["queue_position"] = 0
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
        with self.lock:
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
