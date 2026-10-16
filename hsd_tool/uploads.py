"""Bounded employee uploads; original names never become filesystem paths."""
from __future__ import annotations

import re
import shutil
import stat
import uuid
import zipfile
from pathlib import Path

from werkzeug.exceptions import RequestEntityTooLarge

MAX_UPLOAD_BYTES = 2 * 1024**3
MAX_WORKBOOK_BYTES = 100 * 1024**2
MAX_SOURCE_BYTES = 1900 * 1024**2


def display_name(filename, extension):
    name = str(filename or "").replace("\\", "/").rsplit("/", 1)[-1]
    name = "".join(c for c in name if ord(c) >= 32 and ord(c) != 127)[:200]
    if not name or Path(name).suffix.lower() != extension:
        raise ValueError("请上传 .xlsx 表格和包含 AI 原稿的 .zip 压缩包。")
    return name


def checked_path(path, root):
    path, root = Path(path), Path(root).resolve()
    if not path.is_absolute() or str(path).startswith(("\\\\", "//")):
        raise ValueError("任务文件路径无效。")
    for part in (path, *path.parents):
        try:
            reparse = bool(getattr(part.lstat(), "st_file_attributes", 0) & 0x400)
        except FileNotFoundError:
            reparse = False
        if reparse or part.is_symlink() or (hasattr(part, "is_junction") and part.is_junction()):
            raise ValueError("任务文件不支持链接或目录联接。")
    resolved = path.resolve()
    if not resolved.is_relative_to(root):
        raise ValueError("任务文件超出允许范围。")
    return resolved


class EmployeeUploads:
    def __init__(self, data_dir):
        self.input_root = Path(data_dir).resolve() / "uploads"
        self.output_root = Path(data_dir).resolve() / "employee_outputs"
        self.input_root.mkdir(parents=True, exist_ok=True)
        self.output_root.mkdir(parents=True, exist_ok=True)

    def receive(self, files, form):
        if set(files) != {"workbook", "source"} or any(len(files.getlist(k)) != 1 for k in files):
            raise ValueError("请各上传一份 XLSX 表格和 AI 文件 ZIP 压缩包。")
        if set(form) - {"start_number"} or len(form.getlist("start_number")) != 1:
            raise ValueError("请确认本批起始流水号。")
        raw_start = form.get("start_number", "")
        if not re.fullmatch(r"[0-9]{1,4}", raw_start) or not 1 <= int(raw_start) <= 9999:
            raise ValueError("起始流水号必须是 1 到 9999 之间的整数。")
        names = {"workbook_name": display_name(files["workbook"].filename, ".xlsx"),
                 "source_name": display_name(files["source"].filename, ".zip")}
        batch_id = uuid.uuid4().hex
        directory = checked_path(self.input_root / batch_id, self.input_root)
        directory.mkdir()
        try:
            (directory / ".hsd-upload").write_text(batch_id, "ascii")
            for key, filename, limit in (("workbook", "workbook.xlsx", MAX_WORKBOOK_BYTES),
                                         ("source", "source.zip", MAX_SOURCE_BYTES)):
                total = 0
                with (directory / filename).open("xb") as stream:
                    while chunk := files[key].stream.read(1024 * 1024):
                        total += len(chunk)
                        if total > limit:
                            raise RequestEntityTooLarge("表格最大100MB，AI压缩包最大1900MB。")
                        if shutil.disk_usage(directory).free < len(chunk) + 64 * 1024**2:
                            raise ValueError("主机剩余空间不足，请联系管理员清理后再上传。")
                        stream.write(chunk)
                if total == 0:
                    raise ValueError("上传文件为空，请重新选择。")
            self._validate_archives(directory)
            payload = {"workbook_path": str(directory / "workbook.xlsx"),
                       "source_path": str(directory / "source.zip"),
                       "output_root": str(self.output_root / batch_id), "start_number": int(raw_start)}
            return directory, payload, names
        except BaseException:
            self.discard(directory)
            raise

    @staticmethod
    def _validate_archives(directory):
        try:
            from .workbook import _validate_archive
            with zipfile.ZipFile(directory / "workbook.xlsx") as workbook:
                _validate_archive(workbook)
                if not {"[Content_Types].xml", "xl/workbook.xml"}.issubset(workbook.namelist()):
                    raise ValueError("上传的表格不是有效的 XLSX 工作簿。")
            from .matching import (_safe_zip_name, _zip_name, MAX_ENTRIES, MAX_FILES,
                                   MAX_FILE_BYTES, MAX_TOTAL_BYTES, MAX_RATIO)
            with zipfile.ZipFile(directory / "source.zip") as source:
                infos = source.infolist()
                if len(infos) > MAX_ENTRIES:
                    raise ValueError("压缩包文件过多，请分批上传。")
                count, size, seen = 0, 0, set()
                for info in infos:
                    name = _zip_name(info)
                    _safe_zip_name(name)
                    identity = name.rstrip("/").casefold()
                    if identity in seen:
                        raise ValueError("压缩包包含重名文件，请整理后重新上传。")
                    seen.add(identity)
                    if stat.S_ISLNK(info.external_attr >> 16) or info.flag_bits & 1:
                        raise ValueError("压缩包包含链接或加密文件，请重新打包。")
                    if not info.is_dir() and name.lower().endswith(".ai"):
                        count += 1
                        size += info.file_size
                        if (info.file_size > MAX_FILE_BYTES or size > MAX_TOTAL_BYTES
                                or info.file_size > max(1, info.compress_size) * MAX_RATIO):
                            raise ValueError("AI 文件超过处理容量，请分批上传。")
                if not 1 <= count <= MAX_FILES:
                    raise ValueError(f"压缩包应包含1到{MAX_FILES}个 AI 原稿文件。")
        except (zipfile.BadZipFile, EOFError, RuntimeError) as exc:
            raise ValueError("上传文件损坏或不是真正的 XLSX / ZIP，请重新选择。") from exc

    def validate_job(self, job):
        directory = checked_path(job["_upload_dir"], self.input_root)
        if not re.fullmatch(r"[a-f0-9]{32}", directory.name):
            raise ValueError("上传任务目录无效。")
        expected = {"_workbook_path": directory / "workbook.xlsx", "_source_path": directory / "source.zip",
                    "_output_root": self.output_root / directory.name}
        for key, path in expected.items():
            root = self.output_root if key == "_output_root" else directory
            if checked_path(job[key], root) != path.resolve():
                raise ValueError("上传任务文件发生了变化，请重新上传。")

    def discard(self, directory):
        directory = checked_path(directory, self.input_root)
        if directory.parent != self.input_root or not re.fullmatch(r"[a-f0-9]{32}", directory.name):
            raise ValueError("不能清理此上传目录。")
        if directory.is_dir():
            shutil.rmtree(directory)
