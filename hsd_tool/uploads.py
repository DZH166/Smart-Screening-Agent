"""Streaming employee uploads; original names never become filesystem paths."""
from __future__ import annotations

from contextlib import contextmanager
import errno
import hashlib
import os
import re
import shutil
import stat
import threading
import time
import uuid
import zipfile
from pathlib import Path
from weakref import WeakValueDictionary

# Public configuration uses null for unlimited. Structural and disk checks remain.
MAX_UPLOAD_BYTES = None
MAX_WORKBOOK_BYTES = None
MAX_SOURCE_BYTES = None
COPY_BUFFER_BYTES = 1024 * 1024
DISK_CHECK_INTERVAL = 64 * 1024**2
DISK_REFRESH_SECONDS = 2
CLOUD_UPLOAD_HEADROOM = 256 * 1024**2
_VOLUME_LOCK = threading.Lock()
_VOLUME_BUDGETS = WeakValueDictionary()


class UploadWriteError(RuntimeError):
    """Do not use ValueError: Werkzeug silently treats it as malformed form data."""


def disk_full(exc):
    return getattr(exc, "errno", None) in {errno.ENOSPC, errno.EDQUOT} or getattr(exc, "winerror", None) in {39, 112}


class _VolumeBudget:
    def __init__(self):
        self.lock = threading.Lock()
        self.free = 0
        self.pending = 0
        self.since_check = 0
        self.checked_at = 0


class DiskBudget:
    """Share checked disk capacity and in-flight writes on each volume."""
    def __init__(self, directory, *, headroom=0):
        self.directory = Path(directory).resolve()
        self.headroom = headroom
        self._fresh = True
        key = (self.directory.anchor, self.directory.stat().st_dev)
        with _VOLUME_LOCK:
            volume = _VOLUME_BUDGETS.get(key)
            if volume is None:
                volume = _VolumeBudget()
                _VOLUME_BUDGETS[key] = volume
            self._volume = volume

    def _check(self, count, *, refresh=False):
        volume = self._volume
        needed = volume.pending + count + self.headroom
        now = time.monotonic()
        if (refresh or self._fresh or volume.since_check >= DISK_CHECK_INTERVAL
                or now - volume.checked_at >= DISK_REFRESH_SECONDS or volume.free < needed):
            volume.free = shutil.disk_usage(self.directory).free
            volume.since_check = 0
            volume.checked_at = now
            self._fresh = False
        if volume.free < needed:
            raise UploadWriteError("主机磁盘空间不足，请联系管理员清理后再上传。")

    def reserve(self, count):
        # Check-only callers perform their own writes outside this budget.
        with self._volume.lock:
            self._check(count, refresh=True)

    @contextmanager
    def writing(self, count):
        volume = self._volume
        with volume.lock:
            self._check(count)
            volume.pending += count
        try:
            yield
        finally:
            with volume.lock:
                volume.pending -= count
                # Account conservatively even if a write only partly succeeded.
                # The next physical refresh recovers any unused capacity.
                volume.free -= count
                volume.since_check += count


class UploadFile:
    """Werkzeug-compatible disk stream with write-time SHA and physical checks."""
    def __init__(self, path, budget):
        self.path = Path(path)
        self.directory = self.path.parent
        self.budget = budget
        self._file = self.path.open("x+b", buffering=0)
        self._digest = hashlib.sha256()
        self.bytes_written = 0

    @property
    def closed(self):
        return self._file.closed

    @property
    def hexdigest(self):
        return self._digest.hexdigest()

    def write(self, data):
        with self.budget.writing(len(data)):
            try:
                written = self._file.write(data)
            except OSError as exc:
                if disk_full(exc):
                    raise UploadWriteError("主机磁盘空间不足，请联系管理员清理后再上传。") from exc
                raise
        if written:
            self._digest.update(memoryview(data)[:written])
            self.bytes_written += written
        if written != len(data):
            raise UploadWriteError("上传文件未完整写入主机，请检查磁盘空间后重试。")
        return written

    def close(self):
        self._file.close()

    def __getattr__(self, name):
        return getattr(self._file, name)


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

    def begin(self):
        batch_id = uuid.uuid4().hex
        directory = checked_path(self.input_root / batch_id, self.input_root)
        directory.mkdir()
        try:
            (directory / ".hsd-upload").write_text(batch_id, "ascii")
        except BaseException:
            self.discard(directory)
            raise
        return directory

    def open_stream(self, directory, budget):
        directory = checked_path(directory, self.input_root)
        path = checked_path(directory / ("part-" + uuid.uuid4().hex), directory)
        return UploadFile(path, budget)

    def receive(self, files, form, *, directory=None):
        if set(files) != {"workbook", "source"} or any(len(files.getlist(k)) != 1 for k in files):
            raise ValueError("请各上传一份 XLSX 表格和 AI 文件 ZIP 压缩包。")
        if set(form) - {"start_number"} or len(form.getlist("start_number")) != 1:
            raise ValueError("请确认本批起始流水号。")
        raw_start = form.get("start_number", "")
        if not re.fullmatch(r"[0-9]{1,4}", raw_start) or not 1 <= int(raw_start) <= 9999:
            raise ValueError("起始流水号必须是 1 到 9999 之间的整数。")
        names = {"workbook_name": display_name(files["workbook"].filename, ".xlsx"),
                 "source_name": display_name(files["source"].filename, ".zip")}
        directory = self.begin() if directory is None else checked_path(directory, self.input_root)
        batch_id = directory.name
        if directory.parent != self.input_root or not re.fullmatch(r"[a-f0-9]{32}", batch_id):
            raise ValueError("上传任务目录无效。")
        marker = checked_path(directory / ".hsd-upload", directory)
        if marker.read_text("ascii") != batch_id:
            raise ValueError("上传任务目录无效。")
        budget = DiskBudget(directory)
        digests = {}
        try:
            for key, filename in (("workbook", "workbook.xlsx"), ("source", "source.zip")):
                original = files[key].stream
                target = checked_path(directory / filename, directory)
                if isinstance(original, UploadFile):
                    if original.directory != directory or checked_path(original.path, directory).parent != directory:
                        raise ValueError("上传任务文件归属无效。")
                    total = original.bytes_written
                    original.close()
                    os.replace(original.path, target)
                    digests[key] = original.hexdigest
                else:
                    stream = UploadFile(target, budget)
                    try:
                        while chunk := original.read(COPY_BUFFER_BYTES):
                            stream.write(chunk)
                        total = stream.bytes_written
                        digests[key] = stream.hexdigest
                    finally:
                        stream.close()
                if total == 0:
                    raise ValueError("上传文件为空，请重新选择。")
            self._validate_archives(directory)
            payload = {"workbook_path": str(directory / "workbook.xlsx"),
                       "source_path": str(directory / "source.zip"),
                       "output_root": str(self.output_root / batch_id), "start_number": int(raw_start)}
            names["_input_digests"] = digests
            return directory, payload, names
        except BaseException as exc:
            for value in files.values():
                if isinstance(value.stream, UploadFile):
                    value.close()
            self.discard(directory)
            if isinstance(exc, OSError) and disk_full(exc):
                raise ValueError("主机磁盘空间不足，请联系管理员清理后再上传。") from exc
            raise

    @staticmethod
    def _validate_archives(directory):
        try:
            from .archive_io import check_directory_size
            from .matching import _safe_zip_name, _zip_name, MAX_ENTRIES, MAX_FILES
            from .workbook import _validate_archive
            # Refuse an over-full directory before zipfile materialises one
            # ZipInfo per entry in the single worker. A structurally broken
            # archive keeps its existing 422 path.
            for name, cap, message in (("workbook.xlsx", 20_000, "表格内部文件过多，无法安全读取。"),
                                       ("source.zip", MAX_ENTRIES, "压缩包文件过多，请分批上传。")):
                try:
                    check_directory_size(directory / name, max_entries=cap, too_many=message)
                except zipfile.BadZipFile as exc:
                    raise ValueError(str(exc)) from exc
            with zipfile.ZipFile(directory / "workbook.xlsx") as workbook:
                _validate_archive(workbook)
                if not {"[Content_Types].xml", "xl/workbook.xml"}.issubset(workbook.namelist()):
                    raise ValueError("上传的表格不是有效的 XLSX 工作簿。")
            from .matching import _safe_zip_name, _zip_name, MAX_ENTRIES, MAX_FILES
            with zipfile.ZipFile(directory / "source.zip") as source:
                infos = source.infolist()
                if len(infos) > MAX_ENTRIES:
                    raise ValueError("压缩包文件过多，请分批上传。")
                count, seen = 0, set()
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
