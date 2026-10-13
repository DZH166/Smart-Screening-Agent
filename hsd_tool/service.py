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
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from . import __version__

ACCEPTED = {"auto", "confirmed"}
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


class JobManager:
    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.jobs = {}
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="hsd")
        self.settings_path = self.data_dir / "settings.json"
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

    def _save_config(self, job):
        values = {"last_start": job["start_number"], "last_workbook": job["_workbook_path"],
                  "last_source": job["_source_path"], "last_output": job["_output_root"]}
        temporary = self.settings_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(values, ensure_ascii=False, indent=2), "utf-8")
        os.replace(temporary, self.settings_path)

    def create(self, payload: dict):
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
            if any(j["status"] in {"importing", "matching", "exporting"} for j in self.jobs.values()):
                raise ValueError("当前任务仍在处理，请完成后再导入。")
            identifier = uuid.uuid4().hex
            work_dir = self.data_dir / "jobs" / identifier
            work_dir.mkdir(parents=True)
            (work_dir / ".hsd-job").write_text(identifier, "ascii")
            job = {"id": identifier, "status": "importing", "progress": {"message": "正在读取表格…", "current": 0, "total": 1},
                   "error": None, "sheet_name": "", "workbook_name": workbook.name, "source_name": source.name,
                   "start_number": start, "prefix": "HSD", "rows": [], "files": [], "warnings": [],
                   "output_dir": None, "report": None, "stats": {}, "_workbook_path": str(workbook),
                   "_source_path": str(source), "_output_root": str(output), "_work_dir": str(work_dir),
                   "_reserved": [], "_input_digest": None}
            self.jobs[identifier] = job
            try:
                self._save_config(job)
            except OSError:
                logging.exception("Could not save input preferences")
                job["warnings"].append("本机设置未能保存，本次处理仍会继续；下次可能需要重新选择路径。")
            self.pool.submit(self._process, identifier)
        return identifier

    def _progress(self, identifier, message, current=0, total=1):
        with self.lock:
            self.jobs[identifier]["progress"] = {"message": message, "current": current, "total": total}

    def _process(self, identifier):
        try:
            from .workbook import inspect_workbook
            from .matching import scan_and_match
            job = self.jobs[identifier]
            workbook_path = job["_workbook_path"]
            job["_input_digest"] = sha256(workbook_path)
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
            result = scan_and_match(job["_source_path"], sheet["rows"], str(Path(job["_work_dir"]) / "matching"),
                                    progress=lambda m, c=0, t=1: self._progress(identifier, m, c, t))
            matches = {m["row_id"]: m for m in result["matches"]}
            with self.lock:
                job["files"] = result["files"]
                job["warnings"].extend(result.get("warnings", []))
                for row in job["rows"]:
                    match = matches.get(row["id"], {})
                    row["_status"] = match.get("status", "unmatched")
                    row["_reason"] = match.get("reason", row.get("issue") or "没有找到对应文件")
                    row["_file_id"] = match.get("file_id")
                    row["candidates"] = match.get("candidates", [])
                    if row.get("issue"):
                        row["_status"] = "review"
                        row["_reason"] = row["issue"]
                self._plan(job)
                job["status"] = "ready"
                job["progress"] = {"message": "匹配完成，请检查待处理项", "current": len(job["rows"]), "total": len(job["rows"])}
        except Exception as exc:
            self._fail(identifier, exc)

    def _plan(self, job):
        rows = job["rows"]
        reserved = {str(n).casefold() for n in job["_reserved"] if str(n)}
        for row in rows:
            row["status"] = row.get("_status", "unmatched")
            row["reason"] = row.get("_reason", "")
            row["file_id"] = row.get("_file_id")
            row["planned_number"] = row.get("number", "")
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
        next_number = job["start_number"]
        for row in sorted(rows, key=lambda r: r["row_number"]):
            if row["status"] not in ACCEPTED:
                continue
            if not row.get("file_id"):
                row["status"], row["reason"] = "review", "缺少已确认的对应文件。"
                continue
            if row.get("number"):
                if not valid_number(row["number"]):
                    row["status"], row["reason"] = "review", "已有编号包含 Windows 文件名不允许的字符，请在源表修正后重新导入，或跳过此行。"
                continue
            while next_number <= 9999 and f"HSD{next_number:04d}".casefold() in reserved:
                next_number += 1
            if next_number > 9999:
                row["status"], row["reason"] = "review", "4 位流水号已用完，请调整起始号后重新导入，或跳过此行。"
                continue
            number = f"HSD{next_number:04d}"
            row["planned_number"] = number
            reserved.add(number.casefold())
            next_number += 1
        counts = collections.Counter(r["status"] for r in rows)
        job["stats"] = {"total": len(rows), **{s: counts[s] for s in ("auto", "confirmed", "review", "unmatched", "skipped")},
                        "exportable": counts["auto"] + counts["confirmed"]}

    def resolve(self, identifier, row_id, file_id):
        with self.lock:
            job = self._get(identifier)
            if job["status"] != "ready":
                raise ValueError("当前任务不能修改匹配结果。")
            row = next((r for r in job["rows"] if r["id"] == row_id), None)
            if row is None:
                raise ValueError("找不到这条表格记录。")
            if file_id is None:
                row["_status"], row["_file_id"], row["_reason"] = "skipped", None, "员工选择跳过；该行保留原状。"
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
            self._plan(job)
            return self.snapshot(identifier)

    def export(self, identifier):
        with self.lock:
            job = self._get(identifier)
            if job["status"] != "ready":
                raise ValueError("当前任务不能导出；已完成的结果可直接打开输出文件夹。")
            self._plan(job)
            if not job["stats"]["exportable"]:
                raise ValueError("还没有可导出的对应关系，请先确认至少一项匹配。")
            job["status"] = "exporting"
            job["error"] = None
            self.pool.submit(self._export, identifier)

    def _export(self, identifier):
        job = self.jobs[identifier]
        staging = None
        staging_created = False
        try:
            from .workbook import write_numbered_workbook
            if sha256(job["_workbook_path"]) != job["_input_digest"]:
                raise ValueError("导入后源表格发生了变化，请重新导入，避免把编号填到错误的记录。")
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
                if not row["number"]:
                    assignments[row["row_number"]] = number
                mapping.append({"row": row["row_number"], "old_number": row["number"], "number": number,
                                "source": files[row["file_id"]]["relative_path"], "output": destination.name,
                                "confirmation": "人工确认" if row["status"] == "confirmed" else "自动匹配", "sha256": copied_digest})
            workbook_out = staging / (Path(job["_workbook_path"]).stem + "_已编号.xlsx")
            write_numbered_workbook(job["_snapshot_workbook"], str(workbook_out), job["sheet_name"], assignments)
            if sha256(job["_workbook_path"]) != job["_input_digest"]:
                raise ValueError("导出期间源表格发生了变化，请重新导入后再处理。")
            pending = [{"row": r["row_number"], "number": r["number"], "reason": r["reason"] or "没有已确认的对应文件"}
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
                writer.writerow(["类型", "表格行号", "已有编号或文件名", "说明"])
                for item in pending:
                    writer.writerow(["表格记录", item["row"], csv_safe(item["number"]), csv_safe(item["reason"])])
                for item in unused:
                    writer.writerow(["未使用文件", "", csv_safe(item["name"]), csv_safe(item["reason"])])
            report = {"exported": len(mapping), "new_numbers": len(assignments), "preserved_numbers": len(mapping) - len(assignments),
                      "pending": len(pending), "unused_files": len(unused), "workbook": workbook_out.name,
                      "input_sha256": job["_input_digest"], "sheet": job["sheet_name"], "version": __version__}
            (staging / "处理记录.json").write_text(json.dumps({**report, "mapping": mapping, "pending_rows": pending, "unused": unused}, ensure_ascii=False, indent=2), "utf-8")
            if final.exists():
                raise ValueError("输出文件夹已存在，请重新导入后重试。")
            staging.rename(final)
            with self.lock:
                job["output_dir"], job["report"], job["status"] = str(final), report, "done"
                job["progress"] = {"message": "导出完成，原文件已保留", "current": len(rows) + 1, "total": len(rows) + 1}
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
