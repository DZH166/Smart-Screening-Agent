"""Private, browser-owned material jobs; no credentials enter task records.

The independent namespace uses signed manifests and derived paths. Unknown or
changed manifests are preserved, never guessed at by the retention sweeper.
Generated output is an unverified, downloadable proposal. Downloads never imply
an employee review or a quality qualification.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import hmac
from io import BytesIO
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import stat
import threading
import time
import warnings
import zipfile

from PIL import Image
from werkzeug.exceptions import Conflict

from . import __version__
from .cancellation import TaskCancelled
from .material_ark import normalise_rgba
from .uploads import DiskBudget, UploadFile, checked_path

_ID = re.compile(r"[a-f0-9]{32}")
_BUSY = {"queued", "processing", "cancelling"}
_TERMINAL = {"ready", "cancelled", "error"}
_MAX_PIXELS = 36_000_000
_MAX_FILES = 100
_RETENTION = 3 * 86400
_THUMBNAIL_EDGE = 640
_DOWNLOADABLE = {"generated", "needs_review", "ready", "confirmed"}
_STAGES = {
    "queued": ("排队", "等待开始处理"),
    "preparing": ("准备图片", "正在检查图片"),
    "cleanup": ("清理整图", "正在清理水印和杂质，等待图片服务返回"),
    "locating": ("识别设计范围", "正在识别完整设计的位置，等待识别服务返回"),
    "designs": ("生成素材", "正在逐个生成高清素材，等待图片服务返回"),
    "refining": ("精修素材", "正在精修这一张素材，等待图片服务返回"),
    "cropping": ("裁剪素材", "正在按设计范围裁剪素材"),
    "saving": ("保存素材", "正在保存本张图片的结果"),
    "source_done": ("本张已完成", "本张素材已生成，继续处理其余图片"),
    "source_error": ("本张未完成", "本张处理遇到问题，继续处理其余图片"),
    "cancelling": ("正在停止", "已发出的请求返回或超时后，本批才会停止"),
    "cancelled": ("已停止", "未发送的图片不再处理"),
    "done": ("处理完成", "素材已生成，可直接下载或按需精修"),
    "error": ("处理未完成", "请查看提示后重试或联系管理员"),
}


def _canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("ascii")


def _digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while block := stream.read(1024 * 1024):
            result.update(block)
    return result.hexdigest()


def _identifier(value):
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise KeyError("找不到此素材任务。")
    return value


def _safe_name(value):
    name = str(value or "").replace("\\", "/").rsplit("/", 1)[-1]
    name = "".join(char for char in name if ord(char) >= 32 and ord(char) != 127)[:160]
    if Path(name).suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise ValueError("请选择 PNG、JPG 或 WebP 图片。")
    return name


def _decode(raw):
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(raw if hasattr(raw, "read") else BytesIO(raw)) as check:
                if check.format not in {"PNG", "JPEG", "WEBP"}:
                    raise ValueError("图片格式不支持，请使用 PNG、JPG 或 WebP。")
                if getattr(check, "n_frames", 1) != 1:
                    raise ValueError("暂不处理动图，请先保存为单张图片。")
                width, height = check.size
                if width * height > _MAX_PIXELS or min(width, height) < 1:
                    raise ValueError("图片像素过大，请缩小后重试。")
                check.load()
                return normalise_rgba(check)
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ValueError("图片像素过大，请缩小后重试。") from None
    except (OSError, SyntaxError):
        raise ValueError("图片无法读取或已损坏，请重新选择。") from None


def _png(image):
    result = BytesIO()
    # Keep the color profile, never camera/GPS/text metadata or a source path.
    clean = image.copy()
    profile = clean.info.get("icc_profile")
    clean.info.clear()
    clean.save(result, "PNG", **({"icc_profile": profile} if profile else {}))
    return result.getvalue()


def _thumbnail(image):
    """Display-only derivative; never resize or overwrite a downloadable PNG."""
    preview = image.copy()
    preview.thumbnail((_THUMBNAIL_EDGE, _THUMBNAIL_EDGE), Image.Resampling.LANCZOS)
    return _png(preview)


class MaterialManager:
    """A single provider queue with response-bound leases and graceful drain."""

    def __init__(self, data_dir, settings, *, cloud=False, provider_factory=None, ai_settings=None, ai_key_pool=None,
                 quality_hook=None, clock=time.time):
        self.data_dir = Path(data_dir).absolute()
        self.root = checked_path(self.data_dir / "material_tasks", self.data_dir)
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.tasks_root = self.root / "tasks"
        self.upload_root = self.root / "uploads"
        for path in (self.tasks_root, self.upload_root):
            checked_path(path, self.root).mkdir(mode=0o700, exist_ok=True)
        self.settings, self.cloud, self.clock = settings, bool(cloud), clock
        self.provider_factory = provider_factory
        self.ai_settings = ai_settings
        self.ai_key_pool = ai_key_pool
        self.quality_hook = quality_hook
        self.lock = threading.RLock()
        self.jobs, self.leases, self.futures = {}, {}, {}
        self.upload_leases = set()
        self._closed = False
        self._key = self._load_key()
        implementation = hashlib.sha256(__version__.encode())
        for name in ("material_service.py", "material_ark.py", "material_quality.py", "material_pipeline.py", "material_locate.py", "material_design.py"):
            if not Path(__file__).with_name(name).exists():
                continue
            implementation.update(name.encode()); implementation.update(Path(__file__).with_name(name).read_bytes())
        self.implementation = implementation.hexdigest()
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="hsd-material")
        self._load()

    def start(self):
        """Lifecycle compatibility: workers are submitted only after acceptance."""
        return self

    def _private(self, path):
        path = checked_path(path, self.root)
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError("素材记录文件不安全，原文件已保留。")
        if os.name != "nt" and (info.st_uid != os.getuid() or info.st_mode & 0o077):
            raise ValueError("素材记录权限不安全，原文件已保留。")
        return path

    def _load_key(self):
        path = self.root / "signing.key"
        if not path.exists():
            if any(self.tasks_root.iterdir()):
                raise ValueError("素材签名密钥缺失，已有素材任务已保留，请联系管理员。")
            with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                                  getattr(os, "O_NOFOLLOW", 0), 0o600), "wb") as stream:
                stream.write(secrets.token_bytes(32)); stream.flush(); os.fsync(stream.fileno())
        raw = self._private(path).read_bytes()
        if len(raw) != 32:
            raise ValueError("素材签名密钥无效。")
        return raw

    def _directory(self, identifier):
        return checked_path(self.tasks_root / _identifier(identifier), self.tasks_root)

    def _write(self, path, raw):
        path = checked_path(path, self.root)
        DiskBudget(path.parent).reserve(len(raw))
        temporary = path.parent / (".write-" + secrets.token_hex(16))
        try:
            with os.fdopen(os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                                  getattr(os, "O_NOFOLLOW", 0), 0o600), "wb") as stream:
                stream.write(raw); stream.flush(); os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def _save(self, job, *, touch=False):
        job["update_seq"] = job.get("update_seq", 0) + 1
        job["updated_at"] = self.clock()
        job["progress"]["updated_at"] = job["updated_at"]
        if touch and job["status"] in _TERMINAL:
            job["settled_at"] = self.clock()
            job["expires_at"] = job["settled_at"] + _RETENTION
        target = self._directory(job["id"]) / "manifest.json"
        if target.exists() or target.is_symlink():
            self._read(self._directory(job["id"]))
        payload = deepcopy(job)
        signature = hmac.new(self._key, _canonical(payload), hashlib.sha256).hexdigest()
        self._write(self._directory(job["id"]) / "manifest.json",
                    _canonical({"payload": payload, "hmac_sha256": signature}))

    def _progress(self, job, stage, *, current=None, total=None, source_id=None, done=None, of=None):
        """Only real work boundaries advance the stream; waiting is not percent."""
        phase, message = _STAGES[stage]
        # Provider text is never forwarded; a provider may only report a count
        # of finished items and the server words it.
        previous = job.get("progress", {})
        now = self.clock()
        source = source_id if source_id is not None else previous.get("source_id")
        same_stage = previous.get("stage_code") == stage and previous.get("source_id") == source
        # Keep generation counts as data. They describe this source's completed
        # attempts (including failed ones), never the provider's internal time.
        counts = {}
        if stage == "designs" and type(done) is int and type(of) is int and 0 < of and 0 <= done <= of:
            if same_stage and previous.get("designs_total") == of:
                done = max(done, previous.get("designs_completed", 0))
            counts = {"designs_completed": done, "designs_total": of}
            message = "已处理 %d / %d 个素材。" % (done, of)
        elif same_stage or (stage in {"saving", "source_done", "source_error", "cancelling", "cancelled", "done", "error"}
                            and source == previous.get("source_id")):
            counts = {key: previous[key] for key in ("designs_completed", "designs_total") if key in previous}
        job["progress"] = {"stage_code": stage, "phase": phase, "message": message,
                           "current": previous.get("current", 0) if current is None else current,
                           "total": previous.get("total", len(job["sources"])) if total is None else total,
                           "source_id": source,
                           "started_at": previous.get("started_at", now) if same_stage else now, "updated_at": now,
                           "indeterminate": stage in {"cleanup", "locating", "cancelling"}
                           or (stage == "designs" and not counts), **counts}
        # A short, private stage history survives reconnects and is never model
        # chain-of-thought. It contains no credentials or upstream response text.
        history = job.setdefault("stage_history", [])
        history.append({"stage_code": stage, "at": now,
                        "source_id": job["progress"]["source_id"]})
        del history[:-800]

    def _read(self, directory):
        path = self._private(directory / "manifest.json")
        if path.stat().st_size > 16 * 1024 * 1024:
            raise ValueError("素材任务记录过大。")
        envelope = json.loads(path.read_text("utf-8"))
        if set(envelope) != {"payload", "hmac_sha256"}:
            raise ValueError("素材任务记录无效。")
        payload = envelope["payload"]
        signature = hmac.new(self._key, _canonical(payload), hashlib.sha256).hexdigest()
        if (not isinstance(envelope["hmac_sha256"], str)
                or not hmac.compare_digest(signature, envelope["hmac_sha256"])
                or payload.get("schema") != 1 or payload.get("id") != directory.name
                or not isinstance(payload.get("owner"), str) or not payload["owner"]
                or payload.get("status") not in _BUSY | _TERMINAL):
            raise ValueError("素材任务记录已改变。")
        return payload

    def _load(self):
        for directory in self.tasks_root.iterdir():
            if not _ID.fullmatch(directory.name):
                continue
            try:
                checked_path(directory, self.tasks_root)
                job = self._read(directory)
                if job.get("implementation") != self.implementation:
                    continue
                if self.cloud and type(job.get("expires_at")) in {int, float} and job["expires_at"] <= self.clock():
                    continue
                if job["status"] in _BUSY:
                    job.update(status="error", error="上次处理被中断，未自动重复调用。请检查已有结果后重新处理。",
                               revision=job["revision"] + 1, run_finished_at=self.clock())
                    self._progress(job, "error")
                    for source in job["sources"]:
                        if source["status"] == "processing":
                            unknown = self._source_submission_unknown(job, source["id"], include_pending=True)
                            source.update(status="error", submission_unknown=unknown,
                                          error="上次请求是否完成和扣费尚未确定；未自动重发，请核对后再重试。" if unknown else
                                                "上次处理被中断，尚未发送这张图片，可重新处理。")
                        elif source["status"] == "queued":
                            source.update(status="error", submission_unknown=False,
                                          error="上次处理被中断，尚未发送这张图片，可重新处理。")
                    for attempt in job["attempts"]:
                        if attempt["state"] == "submitted":
                            attempt["state"] = "unknown"
                    for item in job["items"]:
                        if item["status"] != "superseded" and self._refine_submission_unknown(job, item["id"]):
                            item.update(refine_submission_unknown=True,
                                refine_error="上次精修被中断，是否扣费尚未确定；原素材已保留，重新精修前请先核对。")
                    self._save(job, touch=True)
                self.jobs[job["id"]] = job
            except (OSError, ValueError, KeyError, TypeError):
                # Unknown ownership or malformed data are never deleted/reused.
                continue

    def begin_upload(self, *, owner=None):
        with self.lock:
            if self._closed:
                raise Conflict("服务正在退出，请稍后重试。")
            directory = self.upload_root / secrets.token_hex(16)
            checked_path(directory, self.upload_root).mkdir(mode=0o700)
            payload = {"schema": 1, "id": directory.name, "owner": str(owner or "local"),
                       "created_at": self.clock(), "orphaned_at": None}
            signature = hmac.new(self._key, _canonical(payload), hashlib.sha256).hexdigest()
            self._write(directory / ".material-upload", _canonical({"payload": payload, "hmac_sha256": signature}))
            self.upload_leases.add(directory.name)
            return directory

    begin = begin_upload

    def open_stream(self, directory, budget):
        directory = self._upload_directory(directory)
        return UploadFile(directory / ("part-" + secrets.token_hex(16)), budget)

    def _upload_directory(self, directory):
        directory = checked_path(directory, self.upload_root)
        if directory.parent != self.upload_root or not _ID.fullmatch(directory.name):
            raise ValueError("素材上传目录无效。")
        self._upload_marker(directory)
        return directory

    def _upload_marker(self, directory):
        path = self._private(directory / ".material-upload")
        if path.stat().st_size > 8192:
            raise ValueError("素材上传目录归属无效。")
        envelope = json.loads(path.read_text("ascii"))
        if not isinstance(envelope, dict) or set(envelope) != {"payload", "hmac_sha256"}:
            raise ValueError("素材上传目录归属无效。")
        payload = envelope["payload"]
        signature = hmac.new(self._key, _canonical(payload), hashlib.sha256).hexdigest()
        if (not isinstance(envelope["hmac_sha256"], str)
                or not hmac.compare_digest(signature, envelope["hmac_sha256"])
                or not isinstance(payload, dict) or set(payload) != {"schema", "id", "owner", "created_at", "orphaned_at"}
                or payload["schema"] != 1 or payload["id"] != directory.name
                or not isinstance(payload["owner"], str) or not payload["owner"]
                or type(payload["created_at"]) not in {int, float}
                or not 0 < payload["created_at"] <= self.clock()
                or (payload["orphaned_at"] is not None and
                    (type(payload["orphaned_at"]) not in {int, float} or
                     not payload["created_at"] <= payload["orphaned_at"] <= self.clock()))):
            raise ValueError("素材上传目录归属无效。")
        return payload

    def discard(self, directory):
        candidate = checked_path(directory, self.upload_root)
        if candidate.parent == self.upload_root and _ID.fullmatch(candidate.name) and not candidate.exists():
            self.upload_leases.discard(candidate.name)
            return
        directory = self._upload_directory(directory)
        self._remove_tree(directory)
        self.upload_leases.discard(directory.name)

    def receive(self, files, form, *, owner, directory=None, before_submit=None, upload_request_id="",
                ensure_active=None):
        if set(files) != {"files"} or form or not 1 <= len(files.getlist("files")) <= _MAX_FILES:
            raise ValueError("请一次选择 1 到 100 张 PNG、JPG 或 WebP 图片。")
        self._runtime()
        directory = self.begin_upload(owner=owner) if directory is None else self._upload_directory(directory)
        sources = []
        try:
            for value in files.getlist("files"):
                if ensure_active:
                    ensure_active()
                source_id = secrets.token_hex(16)
                name = _safe_name(value.filename)
                stream = value.stream
                # Multipart bytes have already streamed to the disk budget.
                stream.seek(0)
                image = _decode(stream)
                raw = _png(image)
                self._write(directory / (source_id + ".png"), raw)
                thumbnail = _thumbnail(image)
                self._write(directory / (source_id + ".thumb.png"), thumbnail)
                sources.append({"id": source_id, "name": name, "width": image.width,
                                "height": image.height, "sha256": hashlib.sha256(raw).hexdigest(),
                                "thumbnail_sha256": hashlib.sha256(thumbnail).hexdigest(),
                                "status": "queued", "error": ""})
            if ensure_active:
                ensure_active()
            with self.lock:
                if self._closed:
                    raise Conflict("服务正在退出，请稍后重试。")
                identifier = secrets.token_hex(16)
                target = self._directory(identifier)
                target.mkdir(mode=0o700)
                try:
                    for source in sources:
                        os.replace(directory / (source["id"] + ".png"), target / (source["id"] + ".png"))
                        os.replace(directory / (source["id"] + ".thumb.png"), target / (source["id"] + ".thumb.png"))
                    now = self.clock()
                    job = {"schema": 1, "implementation": self.implementation, "id": identifier,
                           "owner": str(owner or "local"), "revision": 0, "status": "queued",
                           "progress": {"phase": "排队", "current": 0, "total": len(sources),
                                        "message": "等待素材处理"}, "created_at": now,
                           "settled_at": None, "expires_at": None, "sources": sources,
                           "run_id": secrets.token_hex(16), "run_started_at": now, "run_finished_at": None,
                           "items": [], "warnings": [], "error": "", "cancel_requested": False,
                           "attempts": [], "upload_id": str(upload_request_id)}
                    self._progress(job, "queued")
                    self.jobs[identifier] = job
                    self._save(job)
                    if before_submit:
                        before_submit(job)
                    self.futures[identifier] = self.executor.submit(self._run, identifier)
                    return identifier
                except BaseException:
                    self.jobs.pop(identifier, None)
                    self._remove_tree(target)
                    raise
        finally:
            for value in files.getlist("files"):
                value.close()
            self.discard(directory)

    def _runtime(self, *, require_locator=True):
        config = self.settings.runtime()
        if not config.get("ark_key") or not config.get("model_id"):
            raise ValueError("素材服务尚未配置，请联系管理员。")
        if not config.get("enabled"):
            raise ValueError("素材处理尚未开启，请联系管理员开启后再试。")
        if require_locator and not self._deepseek_available():
            raise ValueError("素材范围识别需要可用的 DeepSeek 服务，请联系管理员配置并开启。")
        return config

    def _deepseek_available(self):
        # Explicit injected providers are isolated controls; production always
        # requires the actual enabled credential runtime, not a UI-only flag.
        if self.provider_factory is not None and self.ai_settings is None:
            return True
        if self.ai_settings is None:
            return False
        runtime = self.ai_settings.runtime()
        if not runtime.get("enabled") or not runtime.get("api_key"):
            return False
        if runtime.get("via_gateway"):
            # The legacy gateway only understands numbering requests and must
            # never receive a new material image payload by accidental reuse.
            return False
        if self.ai_key_pool is not None:
            return any(row.get("status") == "available" for row in self.ai_key_pool.snapshot().get("keys", ()))
        return True

    def _provider(self, config):
        if self.provider_factory:
            return self.provider_factory(config)
        from .material_design import MaterialDesignProvider
        return MaterialDesignProvider(config, self.ai_settings, key_pool=self.ai_key_pool)

    def _check(self, job):
        if job.get("cancel_requested"):
            raise TaskCancelled()

    def _source_path(self, job, source):
        path = self._private(self._directory(job["id"]) / (source["id"] + ".png"))
        if _digest(path) != source["sha256"]:
            raise ValueError("原图发生变化，请重新上传；本次结果不能下载。")
        return path

    def _source(self, job, source_id):
        return next((row for row in job["sources"] if row["id"] == source_id), None)

    @staticmethod
    def _source_submission_unknown(job, source_id, *, include_pending=False):
        """A successful source may still contain an unsettled per-design call.

        Pipeline callbacks upsert each call by ID, so only its latest state is
        examined. Never let another source's uncertainty block this source.
        """
        states = {"unknown", "submitted"} if include_pending else {"unknown"}
        for attempt in job.get("attempts", ()):
            if attempt.get("source_id") != source_id:
                continue
            if attempt.get("state") in states or any(
                    call.get("state") in states for call in attempt.get("pipeline_attempts", ())):
                return True
        return False

    @staticmethod
    def _refine_submission_unknown(job, item_id):
        attempt = next((row for row in reversed(job.get("attempts", ()))
                        if row.get("operation") == "refine" and row.get("item_id") == item_id), None)
        return bool(attempt and (attempt.get("state") in {"unknown", "submitted"}
            or any(row.get("state") in {"unknown", "submitted"} for row in attempt.get("pipeline_attempts", ()))))

    def _invoke(self, job, provider, raw, instructions, edit=False, bounds=None, source_id="", refine=False, item_id=""):
        # Retry only a definite provider rejection marked safe by the adapter.
        for number in range(1 if refine else 2):
            self._check(job)
            attempt = {"at": self.clock(), "operation": "refine" if refine else "edit" if edit else "extract",
                       "number": number + 1, "state": "submitted", "usage": {}, "source_id": source_id}
            if refine:
                attempt["item_id"] = item_id
            with self.lock:
                job["attempts"].append(attempt); self._save(job)
            try:
                kwargs = {"instructions": instructions, "check_cancel": lambda: self._check(job)}
                if getattr(provider, "supports_progress", False):
                    def progress(stage_code, message="", *, current=None, total=None):
                        stage = {"prepare": "preparing", "locate": "locating", "crop": "cropping",
                                 "complete": "saving"}.get(stage_code, stage_code)
                        if stage not in _STAGES:
                            return
                        with self.lock:
                            if not job.get("cancel_requested"):
                                self._progress(job, stage, source_id=source_id, done=current, of=total)
                                self._save(job)
                    def record(update):
                        with self.lock:
                            calls = attempt.setdefault("pipeline_attempts", [])
                            identifier = str(update.get("id", ""))
                            existing = next((row for row in calls if row["id"] == identifier), None)
                            data = {key: deepcopy(update[key]) for key in
                                    ("id", "provider", "operation", "number", "state", "usage", "request_id", "settled", "code")
                                    if key in update}
                            if existing is None:
                                calls.append(data)
                            else:
                                existing.update(data)
                            self._save(job)
                    kwargs.update(on_progress=progress, on_attempt=record)
                if refine:
                    kwargs.pop("instructions")
                    result = provider.refine(raw, **kwargs)
                elif edit:
                    result = provider.edit(raw, bounds=bounds, **kwargs)
                else:
                    result = provider.extract(raw, **kwargs)
                attempt.update(state="returned", usage=dict(getattr(result, "usage", {}) or {}),
                               request_id=str(getattr(result, "request_id", "")))
                attempt["provider_usage"] = deepcopy(getattr(result, "provider_usage", {}) or {})
                with self.lock:
                    self._save(job)
                return result
            except TaskCancelled as exc:
                settled = bool(getattr(exc, "settled", False))
                attempt.update(state="cancelled" if settled else "unknown", usage=dict(getattr(exc, "usage", {}) or {}),
                               settled=settled, request_id=str(getattr(exc, "request_id", "")))
                attempt["provider_usage"] = deepcopy(getattr(exc, "provider_usage", {}) or {})
                if not settled:
                    job["warnings"].append("本机已结束等待，但上游请求和扣费状态尚未确定；本次未重复提交。")
                with self.lock:
                    self._save(job)
                raise
            except Exception as exc:
                retry = bool(getattr(exc, "safe_retry", False)) and bool(getattr(exc, "settled", False))
                attempt.update(state="failed" if getattr(exc, "settled", False) else "unknown",
                               usage=dict(getattr(exc, "usage", {}) or {}),
                               request_id=str(getattr(exc, "request_id", "")),
                               code=str(getattr(exc, "code", "processing_failed"))[:80])
                attempt["provider_usage"] = deepcopy(getattr(exc, "provider_usage", {}) or {})
                with self.lock:
                    self._save(job)
                if refine or number or not retry:
                    raise

    def _run(self, identifier, redo=None):
        refining = bool(redo and redo.get("_refine"))
        with self.lock:
            job = self.jobs[identifier]
            if job["cancel_requested"]:
                job["status"] = "cancelled"
                job["revision"] += 1
                job["run_finished_at"] = self.clock()
                self._progress(job, "cancelled")
                for source in job["sources"]:
                    if source["status"] == "queued":
                        source["status"] = "cancelled"
                if refining:
                    self._refine_failure(job, redo, "本次精修已停止，仍保留精修前的素材。", False)
                self._save(job, touch=True); return
            job["status"] = "processing"; job["revision"] += 1
            # Accepted/queued time is part of this run. Do not restart its clock
            # when execution begins, or when switching sources/stages/designs.
            self._progress(job, "preparing")
            try:
                self._save(job)
            except Exception as exc:
                if not refining:
                    raise
                # No provider has been called. A failed local transition must
                # not leave the previous downloadable image stuck in "busy".
                job.update(status="error", error="精修未能开始，原素材已保留，请稍后重试。", run_finished_at=self.clock())
                self._refine_failure(job, redo, job["error"], self._refine_submission_unknown(job, redo["item_id"]))
                self._progress(job, "error")
                job["revision"] += 1
                try:
                    self._save(job, touch=True)
                except (OSError, ValueError):
                    pass  # Preserve files; a later restart treats the saved queued operation as interrupted.
                return
        try:
            provider = self._provider(self._runtime(require_locator=not refining))
            # A committed candidate replaces nested objects. Keep stable IDs,
            # then reacquire the current source before every mutation.
            source_ids = [redo["source_id"]] if redo else [source["id"] for source in job["sources"]]
            for index, source_id in enumerate(source_ids):
                source = self._source(job, source_id)
                self._check(job)
                with self.lock:
                    source["status"] = "processing"
                    self._progress(job, "preparing", current=index, total=len(source_ids), source_id=source["id"])
                    self._save(job)
                try:
                    original = self._source_path(job, source).read_bytes()
                    raw, offset, edit_bounds, old_item = original, (0, 0), None, None
                    if redo and redo.get("item_id"):
                        old_item = next(row for row in job["items"] if row["id"] == redo["item_id"])
                        raw = self._item_path(job, old_item).read_bytes()
                        if redo.get("box"):
                            box, area = redo["box"], old_item["bounds"]
                            left, top = max(box["x"], area["x"]), max(box["y"], area["y"])
                            right = min(box["x"] + box["width"], area["x"] + area["width"])
                            bottom = min(box["y"] + box["height"], area["y"] + area["height"])
                            if right <= left or bottom <= top:
                                raise ValueError("标记范围没有覆盖当前素材。")
                            edit_bounds = {"x": round((left - area["x"]) * old_item["width"] / area["width"]),
                                           "y": round((top - area["y"]) * old_item["height"] / area["height"]),
                                           "width": max(1, round((right - left) * old_item["width"] / area["width"])),
                                           "height": max(1, round((bottom - top) * old_item["height"] / area["height"]))}
                            edit_bounds["x"] = min(edit_bounds["x"], old_item["width"] - 1)
                            edit_bounds["y"] = min(edit_bounds["y"], old_item["height"] - 1)
                            edit_bounds["width"] = min(edit_bounds["width"], old_item["width"] - edit_bounds["x"])
                            edit_bounds["height"] = min(edit_bounds["height"], old_item["height"] - edit_bounds["y"])
                    elif redo and redo.get("box"):
                        box = redo["box"]
                        image = _decode(original)
                        raw = _png(image.crop((box["x"], box["y"], box["x"] + box["width"],
                                               box["y"] + box["height"])))
                        offset = (box["x"], box["y"])
                    if refining:
                        with self.lock:
                            self._progress(job, "refining", current=0, total=1, source_id=source["id"])
                            self._save(job)
                    result = self._invoke(job, provider, raw, (redo or {}).get("instruction", ""),
                                          edit=bool(old_item), bounds=edit_bounds, source_id=source["id"], refine=refining,
                                          item_id=old_item["id"] if refining else "")
                    self._check(job)
                    self._source_path(job, source)
                    if old_item:
                        self._item_path(job, old_item)
                    if refining and len(getattr(result, "layers", ())) != 1:
                        raise ValueError("精修没有返回唯一素材，原素材已保留。")
                    with self.lock:
                        self._check(job)
                        self._progress(job, "saving", source_id=source["id"])
                        self._save(job)
                    new_items = self._outputs(job, source, result, raw, offset, corrected=bool(redo))
                    if old_item:
                        for item in new_items:
                            item["bounds"] = deepcopy(old_item["bounds"])
                            if refining:
                                item.update(name=old_item["name"], previous_item_id=old_item["id"])
                    with self.lock:
                        self._check(job)
                        self._source_path(job, source)
                        if old_item:
                            self._item_path(job, old_item)
                        candidate = deepcopy(job)
                        replacement_index = None
                        if redo and redo.get("item_id"):
                            for position, old in enumerate(candidate["items"]):
                                if old["id"] == redo["item_id"]:
                                    old["status"] = "superseded"
                                    if refining:
                                        replacement_index = position + 1
                        if replacement_index is not None:
                            candidate["items"][replacement_index:replacement_index] = new_items
                        else:
                            candidate["items"].extend(new_items)
                        updated_source = self._source(candidate, source["id"])
                        unknown = self._source_submission_unknown(candidate, source["id"])
                        common = list(getattr(result, "warnings", ()) or ())
                        if len(new_items) >= (128 if getattr(result, "rectangular_crops", False) else 16):
                            common.append("本图设计较多，可能还有漏提取；请查看原图并框选补提取。")
                        updated_source.update(status="done", submission_unknown=unknown,
                            warnings=list(dict.fromkeys(list(updated_source.get("warnings", ())) + common)),
                            error="部分调用结果尚未确认，已完成素材可下载；重新处理前请先核对，可能重复计费。" if unknown else "")
                        self._progress(candidate, "source_done", current=index + 1, total=len(source_ids), source_id=source["id"])
                        candidate["revision"] += 1
                        self._save(candidate)
                        job.clear(); job.update(candidate)
                except TaskCancelled:
                    raise
                except Exception as exc:
                    with self.lock:
                        # Never return upstream exception text (may contain a
                        # credential, base64 request or internal filesystem path).
                        unknown = (getattr(exc, "settled", True) is False or
                                   self._source_submission_unknown(job, source["id"]))
                        message = ("接口返回中断，是否扣费尚未确定；未自动重发。请联系管理员核对后再重做。"
                                   if unknown else self._public_error(exc))
                        refine_unknown = self._refine_submission_unknown(job, redo["item_id"]) if refining else False
                        if refining and not refine_unknown:
                            message = self._public_error(exc)
                        source.update(status="error", error=message, submission_unknown=unknown)
                        if refining:
                            self._refine_failure(job, redo, message, refine_unknown)
                        self._progress(job, "source_error", current=index + 1, total=len(source_ids), source_id=source["id"])
                        job["revision"] += 1
                        self._save(job)
            with self.lock:
                self._check(job)
                job["status"] = "ready" if any(s["status"] == "done" for s in job["sources"]) else "error"
                job["error"] = "" if job["status"] == "ready" else (
                    "本次精修未完成，原素材已保留，可下载原结果。" if refining else "本批未能生成素材，请查看图片旁的原因后重试。")
                job["run_finished_at"] = self.clock()
                self._progress(job, "done" if job["status"] == "ready" else "error", current=len(source_ids), total=len(source_ids))
                job["revision"] += 1; self._save(job, touch=True)
        except TaskCancelled:
            with self.lock:
                job["status"] = "cancelled"
                job["run_finished_at"] = self.clock()
                self._progress(job, "cancelled")
                for source in job["sources"]:
                    if source["status"] in {"queued", "processing"}:
                        if source["status"] == "processing" and self._source_submission_unknown(job, source["id"]):
                            source["submission_unknown"] = True
                            source["error"] = "上次已发送请求的结果和扣费尚未确定；重新提交前请先核对。"
                        source["status"] = "cancelled"
                if refining:
                    unknown = self._refine_submission_unknown(job, redo["item_id"])
                    self._refine_failure(job, redo, "本次精修已停止，仍保留精修前的素材。" if not unknown else
                        "精修返回中断，是否扣费尚未确定；原素材已保留，重新精修前请先核对。", unknown)
                job["revision"] += 1; self._save(job, touch=True)
        except Exception as exc:
            with self.lock:
                if refining:
                    self._refine_failure(job, redo, self._public_error(exc),
                        self._refine_submission_unknown(job, redo["item_id"]))
                job["status"] = "error"; job["error"] = self._public_error(exc)
                job["run_finished_at"] = self.clock()
                self._progress(job, "error")
                job["revision"] += 1; self._save(job, touch=True)

    @staticmethod
    def _refine_failure(job, redo, message, unknown):
        item = next((row for row in job["items"] if row["id"] == redo["item_id"] and row["status"] != "superseded"), None)
        if item is not None:
            item.update(refine_error=message, refine_submission_unknown=bool(unknown))

    @staticmethod
    def _public_error(exc):
        if getattr(exc, "settled", True) is False:
            return "接口返回中断，是否扣费尚未确定；未自动重发。请联系管理员核对后再重做。"
        return {"authentication": "素材服务的 Key 无效，请联系管理员。",
                "deepseek_unavailable": "DeepSeek 暂不可用，请联系管理员检查 Key、开关或稍后重试。",
                "invalid_decision": "未能可靠确定设计范围，请在原图框选后重试。",
                "empty_crop": "识别范围内没有有效图案，请重新框选完整设计。",
                "provider_auth": "素材服务的 Key 或模型权限不正确，请联系管理员检查。",
                "unsupported_model": "当前图片模型不支持整图清理，请联系管理员更换模型。",
                "provider_busy": "素材服务暂时繁忙，请稍后重试。",
                "missing_alpha": "没有生成有效透明背景，请调整范围或联系管理员。",
                "invalid_image": "素材服务无法读取这张图片，请更换图片或缩小范围。",
                "rate_limit": "素材服务暂时繁忙，请稍后重试。",
                "content_policy": "这张图未通过素材服务检查，请更换图片或联系管理员。"}.get(
                    str(getattr(exc, "code", "")), "这张图片未能处理，请重试或联系管理员。")

    def _outputs(self, job, source, result, raw, offset, *, corrected):
        layers = list(getattr(result, "layers", ()))
        rectangular = getattr(result, "rectangular_crops", False) is True
        if not layers or len(layers) > (128 if rectangular else 16):
            raise ValueError("素材服务未返回有效设计。")
        items = []
        for layer in layers:
            self._check(job)
            image = _decode(layer.png)
            alpha = image.getchannel("A")
            if (not rectangular and alpha.getextrema()[0] == 255) or not alpha.getbbox():
                raise ValueError("素材没有有效透明背景，未生成可下载结果。")
            bounds = dict(getattr(layer, "bounds", {}) or {})
            quality = {"auto_ready": False, "warnings": ["请核对文字、配色和设计是否完整；修补细节可能与原图不同。"], "evidence": {}}
            if self.quality_hook and not rectangular:
                quality = self.quality_hook(raw, layer.png, bounds, corrected=corrected)
            # Rectangular image proposals have no validated automatic quality
            # qualification. Neither model certainty nor a pixel check replaces
            # the employee's explicit single/batch decision.
            if rectangular:
                quality["auto_ready"] = False
                quality["evidence"] = {"version": ("material-preserved-canvas-1" if getattr(result, "no_upscale", False)
                                                   else "material-rectangular-crop-1"),
                                       "scope": "unverified_generated_content"}
            notices = list(dict.fromkeys(list(getattr(layer, "warnings", ()) or ()) +
                                        list(quality.get("warnings", ()))))
            original_size = image.size
            if getattr(result, "no_upscale", False):
                # One design already received the whole generation budget; a
                # synthetic 4096 stretch would only inflate files and time.
                size = image.size
            else:
                scale = 4096 / max(image.size)
                size = tuple(max(1, round(value * scale)) for value in image.size)
            if size != image.size:
                image = image.resize(size, Image.Resampling.LANCZOS)
                notices.append("已按比例输出长边 4096 像素；放大不等于恢复原图细节。")
            identifier = secrets.token_hex(16)
            content = _png(image)
            self._write(self._directory(job["id"]) / (identifier + ".png"), content)
            thumbnail = _thumbnail(image)
            self._write(self._directory(job["id"]) / (identifier + ".thumb.png"), thumbnail)
            if set(bounds) == {"x", "y", "width", "height"}:
                bounds = {**bounds, "x": bounds["x"] + offset[0], "y": bounds["y"] + offset[1]}
            label = str(getattr(layer, "label", "素材"))[:80]
            items.append({"id": identifier, "source_id": source["id"], "name": label or "素材",
                          "status": "generated",
                          "warnings": notices, "width": image.width, "height": image.height,
                          "native_width": original_size[0], "native_height": original_size[1],
                          "bounds": bounds, "sha256": hashlib.sha256(content).hexdigest(),
                          "thumbnail_sha256": hashlib.sha256(thumbnail).hexdigest(),
                          "rectangular_crop": rectangular,
                          "evidence": quality.get("evidence", {})})
        return items

    def _get(self, identifier, owner):
        job = self.jobs.get(_identifier(identifier))
        if job is None or job["owner"] != str(owner or "local"):
            raise KeyError("找不到此素材任务，请使用上传时的浏览器。")
        if (self.cloud and type(job.get("expires_at")) in {int, float} and
                job["expires_at"] <= self.clock() and not self.leases.get(identifier)):
            raise KeyError("此素材任务已过期，请重新上传。")
        persisted = self._read(self._directory(identifier))
        if persisted["owner"] != job["owner"]:
            raise ValueError("素材任务归属记录已改变，请联系管理员。")
        return job

    @contextmanager
    def lease(self, identifier, owner):
        with self.lock:
            job = self._get(identifier, owner)
            self.leases[identifier] = self.leases.get(identifier, 0) + 1
        try:
            yield job
        finally:
            with self.lock:
                self.leases[identifier] -= 1
                if not self.leases[identifier]:
                    del self.leases[identifier]

    def acquire(self, identifier, owner):
        context = self.lease(identifier, owner)
        context.__enter__()
        released = False
        def release():
            nonlocal released
            if not released:
                released = True
                context.__exit__(None, None, None)
        return release

    def config(self, owner):
        setting = self.settings.snapshot()
        deepseek_available = self._deepseek_available()
        with self.lock:
            own = [job for job in self.jobs.values() if job["owner"] == str(owner or "local") and
                   (not self.cloud or job.get("expires_at") is None or job["expires_at"] > self.clock())]
            own.sort(key=lambda job: job["created_at"])
            return {"available": bool(setting["enabled"] and setting["configured"] and setting["model_id"] and deepseek_available),
                    "enabled": setting["enabled"], "configured": setting["configured"],
                    "deepseek_available": deepseek_available,
                    "unavailable_reason": ("请联系管理员配置并开启素材图片服务。" if not (
                        setting["enabled"] and setting["configured"] and setting["model_id"]) else
                        "识别设计范围需要可用的 DeepSeek 服务，请联系管理员配置并开启。" if not deepseek_available else ""),
                    "active_job_id": own[-1]["id"] if own else None,
                    "retention_days": 3 if self.cloud else None}

    def restore_upload_claims(self, claims):
        """Replaying an accepted UUID after a lost reply must not pay twice."""
        with self.lock, claims.lock:
            for job in self.jobs.values():
                identifier = job.get("upload_id")
                if isinstance(identifier, str) and _ID.fullmatch(identifier):
                    owner = None if job["owner"] == "local" else job["owner"]
                    claims._write_claim(identifier, {"owner": owner, "state": "completed", "job_id": job["id"]})

    def snapshot(self, identifier, owner):
        with self.lock:
            job = self._get(identifier, owner)
            result = {key: deepcopy(job[key]) for key in ("id", "revision", "status", "progress", "warnings", "error")}
            result["update_seq"] = job.get("update_seq", 0)
            result["has_generation_failures"] = any(
                call.get("operation") == "extract_design" and call.get("state") in {"failed", "unknown"}
                for attempt in job.get("attempts", ()) for call in attempt.get("pipeline_attempts", ()))
            result["can_undo_batch"] = bool(job.get("batch_undo") and
                                           job["batch_undo"]["revision"] == job["revision"] and job["status"] not in _BUSY)
            end = (self.clock() if job["status"] in _BUSY else
                   job.get("run_finished_at") or job.get("settled_at") or self.clock())
            result["progress"]["elapsed_seconds"] = max(0, int(end - job["progress"].get("started_at", job["created_at"])))
            result["progress"]["task_elapsed_seconds"] = max(0, int(end - job.get("run_started_at", job["created_at"])))
            result["progress"].update(run_id=job.get("run_id", identifier),
                                       run_started_at=job.get("run_started_at", job["created_at"]))
            result["sources"] = []
            for source in job["sources"]:
                row = {key: deepcopy(value) for key, value in source.items() if key not in {"sha256", "thumbnail_sha256"}}
                row["image_url"] = f"/api/material/jobs/{identifier}/source/{row['id']}"
                row["thumbnail_url"] = row["image_url"] + "?variant=thumb&v=" + source["thumbnail_sha256"][:16]
                result["sources"].append(row)
            result["items"] = []
            for item in job["items"]:
                if item["status"] == "superseded":
                    continue
                row = {key: deepcopy(value) for key, value in item.items() if key not in {"sha256", "thumbnail_sha256", "evidence", "previous_item_id"}}
                row["image_url"] = f"/api/material/jobs/{identifier}/item/{row['id']}"
                row["thumbnail_url"] = row["image_url"] + "?variant=thumb&v=" + item["thumbnail_sha256"][:16]
                row["downloadable"] = item["status"] in _DOWNLOADABLE and job["status"] not in _BUSY
                row["download_url"] = (f"/api/material/jobs/{identifier}/download/{row['id']}" if row["downloadable"] else None)
                previous = next((value for value in job["items"] if value["id"] == item.get("previous_item_id")
                                 and value["source_id"] == item["source_id"] and value["status"] == "superseded"), None)
                row["refined"] = previous is not None
                if previous:
                    before = f"/api/material/jobs/{identifier}/item/{item['id']}/before"
                    row["previous_image"] = {"image_url": before,
                        "thumbnail_url": before + "?variant=thumb&v=" + previous["thumbnail_sha256"][:16],
                        "width": previous["width"], "height": previous["height"]}
                result["items"].append(row)
            items = result["items"]
            result["stats"] = {"total": len(items), "ready": sum(row["status"] in {"ready", "confirmed"} for row in items),
                               "downloadable": sum(row["downloadable"] for row in items),
                               "needs_review": sum(row["status"] == "needs_review" for row in items),
                               "skipped": sum(row["status"] == "skipped" for row in items),
                               "failed": sum(row["status"] == "error" for row in job["sources"])}
            result["download_url"] = f"/api/material/jobs/{identifier}/download" if result["stats"]["downloadable"] else None
            if job["status"] == "queued":
                result["progress"]["queue_position"] = 1 + sum(
                    row["status"] in _BUSY and row["created_at"] < job["created_at"] for row in self.jobs.values())
            return result

    def _editable(self, job, revision):
        if type(revision) is not int or revision != job["revision"]:
            raise Conflict("素材结果已在其他页面更新，请刷新后重试。")
        if job["status"] in _BUSY:
            raise Conflict("素材仍在处理中，请等待完成后再修改。")
        if self._closed:
            raise Conflict("服务正在退出，请稍后重试。")

    def resolve(self, identifier, owner, payload):
        with self.lease(identifier, owner), self.lock:
            job = self._get(identifier, owner); self._editable(job, payload.get("expected_revision"))
            if set(payload) != {"expected_revision", "item_id", "action"} or payload["action"] not in {"confirm", "skip", "restore"}:
                raise ValueError("请选择舍弃或恢复。")
            item = next((row for row in job["items"] if row["id"] == payload["item_id"] and row["status"] != "superseded"), None)
            if item is None:
                raise KeyError("找不到此素材。")
            self._source_path(job, self._source(job, item["source_id"]))
            self._item_path(job, item)
            candidate = deepcopy(job)
            changed = next(row for row in candidate["items"] if row["id"] == item["id"])
            changed["status"] = {"confirm": "confirmed", "skip": "skipped", "restore": "generated"}[payload["action"]]
            if payload["action"] == "restore":
                changed.pop("review", None)
            else:
                changed["review"] = {"method": "employee_single", "action": payload["action"], "at": self.clock()}
            candidate.pop("batch_undo", None)
            candidate["revision"] += 1
            self._save(candidate, touch=True)
            self.jobs[identifier] = candidate
            return self.snapshot(identifier, owner)

    def resolve_batch(self, identifier, owner, payload):
        """One explicit employee decision, committed atomically after checks."""
        with self.lease(identifier, owner), self.lock:
            if not isinstance(payload, dict) or set(payload) != {"expected_revision", "item_ids"}:
                raise ValueError("请选择需要确认的素材。")
            job = self._get(identifier, owner); self._editable(job, payload["expected_revision"])
            identifiers = payload["item_ids"]
            if (not isinstance(identifiers, list) or not identifiers or len(identifiers) > len(job["items"])
                    or any(not isinstance(value, str) or not _ID.fullmatch(value) for value in identifiers)
                    or len(set(identifiers)) != len(identifiers)):
                raise ValueError("请选择不重复的待确认素材。")
            items = {row["id"]: row for row in job["items"]}
            verified_sources = set()
            for item_id in identifiers:
                item = items.get(item_id)
                if item is None:
                    raise KeyError("所选素材不存在，请刷新后重试。")
                if item["status"] not in {"needs_review", "generated"}:
                    raise Conflict("所选素材状态已改变，请重新选择待确认素材。")
                if item["source_id"] not in verified_sources:
                    self._source_path(job, self._source(job, item["source_id"]))
                    verified_sources.add(item["source_id"])
                self._item_path(job, item)
            candidate = deepcopy(job)
            at, group = self.clock(), secrets.token_hex(16)
            selected = set(identifiers)
            previous = []
            for item in candidate["items"]:
                if item["id"] in selected:
                    previous.append({"id": item["id"], "status": item["status"], "review": item.get("review")})
                    item.update(status="confirmed", review={"method": "employee_batch", "action": "confirm", "at": at, "group": group})
            candidate["revision"] += 1
            candidate["batch_undo"] = {"revision": candidate["revision"], "items": previous, "group": group}
            candidate.setdefault("review_actions", []).append({"method": "employee_batch", "at": at, "group": group, "item_ids": identifiers})
            self._save(candidate, touch=True)
            self.jobs[identifier] = candidate
            return self.snapshot(identifier, owner)

    def undo_batch(self, identifier, owner, payload):
        with self.lease(identifier, owner), self.lock:
            if not isinstance(payload, dict) or set(payload) != {"expected_revision"}:
                raise ValueError("撤销参数无效。")
            job = self._get(identifier, owner); self._editable(job, payload["expected_revision"])
            undo = job.get("batch_undo")
            if not undo or undo["revision"] != job["revision"]:
                raise Conflict("这次批量确认已不能直接撤销，请逐项更正。")
            current = {row["id"]: row for row in job["items"]}
            for previous in undo["items"]:
                item = current.get(previous["id"])
                if item is None or item["status"] != "confirmed" or item.get("review", {}).get("group") != undo["group"]:
                    raise Conflict("素材已改变，未撤销任何确认。")
                self._source_path(job, self._source(job, item["source_id"]))
                self._item_path(job, item)
            candidate = deepcopy(job)
            restore = {row["id"]: row for row in undo["items"]}
            for item in candidate["items"]:
                if item["id"] in restore:
                    previous = restore[item["id"]]
                    item["status"] = previous["status"]
                    if previous["review"] is None:
                        item.pop("review", None)
                    else:
                        item["review"] = previous["review"]
            candidate.pop("batch_undo")
            candidate.setdefault("review_actions", []).append({"method": "employee_batch_undo", "at": self.clock(), "group": undo["group"]})
            candidate["revision"] += 1
            self._save(candidate, touch=True)
            self.jobs[identifier] = candidate
            return self.snapshot(identifier, owner)

    def refine(self, identifier, owner, payload):
        """One explicit refinement request; never locate or retry a paid call."""
        if (not isinstance(payload, dict) or set(payload) - {"expected_revision", "item_id", "acknowledge_unknown"}
                or not {"expected_revision", "item_id"} <= set(payload)):
            raise ValueError("精修参数无效。")
        with self.lease(identifier, owner), self.lock:
            job = self._get(identifier, owner); self._editable(job, payload["expected_revision"])
            item = next((row for row in job["items"] if row["id"] == payload["item_id"] and row["status"] in _DOWNLOADABLE), None)
            if item is None:
                raise KeyError("找不到可精修的素材，请先恢复已舍弃的素材。")
            if "acknowledge_unknown" in payload and type(payload["acknowledge_unknown"]) is not bool:
                raise ValueError("请明确确认未知请求是否重新提交。")
            if item.get("refine_submission_unknown") and payload.get("acknowledge_unknown") is not True:
                raise Conflict("上次精修是否扣费尚未确定，请核对后明确确认重新提交，可能重复计费。")
            source = self._source(job, item["source_id"])
            self._source_path(job, source); self._item_path(job, item)
            self._runtime(require_locator=False)
            candidate = deepcopy(job)
            candidate.pop("batch_undo", None)
            candidate.update(status="queued", cancel_requested=False, error="", settled_at=None, expires_at=None,
                       run_id=secrets.token_hex(16), run_started_at=self.clock(), run_finished_at=None)
            self._progress(candidate, "queued", current=0, total=1, source_id=source["id"])
            candidate["revision"] += 1; self._save(candidate)
            job.clear(); job.update(candidate)
            operation = {"source_id": source["id"], "item_id": item["id"], "_refine": True}
            try:
                future = self.executor.submit(self._run, identifier, operation)
            except Exception:
                # The queue rejected the work: no provider request was sent.
                # Publish a new terminal revision rather than leaving the saved
                # queued state (or a previous completed future) looking active.
                message = "精修未能排队，原素材已保留，请稍后重试。"
                rejected = deepcopy(job)
                rejected.update(status="error", error=message, run_finished_at=self.clock())
                self._refine_failure(rejected, operation, message, bool(item.get("refine_submission_unknown")))
                self._progress(rejected, "error")
                rejected["revision"] += 1
                try:
                    self._save(rejected, touch=True)
                finally:
                    # Even a second local write failure must not lock the old
                    # image in memory. Saved queued work is recovered as an
                    # interrupted, never-replayed operation after restart.
                    job.clear(); job.update(rejected)
                    previous_future = self.futures.get(identifier)
                    if previous_future is not None and previous_future.done():
                        self.futures.pop(identifier, None)
                raise Conflict(message) from None
            self.futures[identifier] = future
            return self.snapshot(identifier, owner)

    def redo(self, identifier, owner, payload):
        with self.lease(identifier, owner), self.lock:
            job = self._get(identifier, owner); self._editable(job, payload.get("expected_revision"))
            if set(payload) - {"expected_revision", "source_id", "item_id", "box", "instruction", "acknowledge_unknown"}:
                raise ValueError("重做参数无效。")
            source = self._source(job, payload.get("source_id"))
            if source is None:
                raise KeyError("找不到此原图。")
            if "acknowledge_unknown" in payload and type(payload["acknowledge_unknown"]) is not bool:
                raise ValueError("请明确确认未知请求是否重新提交。")
            if source.get("submission_unknown") and payload.get("acknowledge_unknown") is not True:
                raise Conflict("上次请求是否扣费尚未确定，请核对后明确确认重新提交，可能重复计费。")
            self._source_path(job, source)
            instruction = payload.get("instruction", "")
            if not isinstance(instruction, str) or len(instruction) > 800:
                raise ValueError("修改要求请控制在 800 字以内。")
            if payload.get("item_id") and not instruction.strip():
                raise ValueError("请选择或填写需要修改的内容。")
            box = payload.get("box")
            if box is not None:
                if (not isinstance(box, dict) or set(box) != {"x", "y", "width", "height"}
                        or any(type(value) is not int for value in box.values())
                        or min(box["x"], box["y"]) < 0 or min(box["width"], box["height"]) < 8
                        or box["x"] + box["width"] > source["width"]
                        or box["y"] + box["height"] > source["height"]):
                    raise ValueError("请在原图内框出完整设计，范围至少 8 × 8 像素。")
            if payload.get("item_id") and not any(row["id"] == payload["item_id"] and row["source_id"] == source["id"] and row["status"] != "superseded" for row in job["items"]):
                raise KeyError("找不到要修改的素材。")
            if box is None and not payload.get("item_id"):
                # Source failures can be retried without a rectangle.
                if source["status"] != "error":
                    raise ValueError("请先框出要补提取的范围。")
            self._runtime()
            job.pop("batch_undo", None)
            job.update(status="queued", cancel_requested=False, error="", settled_at=None, expires_at=None,
                       run_id=secrets.token_hex(16), run_started_at=self.clock(), run_finished_at=None)
            self._progress(job, "queued", current=0, total=1, source_id=source["id"])
            job["revision"] += 1; self._save(job)
            self.futures[identifier] = self.executor.submit(self._run, identifier, deepcopy(payload))
            return self.snapshot(identifier, owner)

    def cancel(self, identifier, owner, revision):
        with self.lock:
            job = self._get(identifier, owner)
            if type(revision) is not int or revision != job["revision"]:
                raise Conflict("处理进度已更新，请刷新后再停止。")
            if job["status"] in _BUSY:
                job.update(cancel_requested=True, status="cancelling")
                self._progress(job, "cancelling")
                job["revision"] += 1; self._save(job)
            return self.snapshot(identifier, owner)

    def _item_path(self, job, item):
        path = self._private(self._directory(job["id"]) / (item["id"] + ".png"))
        if _digest(path) != item["sha256"]:
            raise ValueError("素材文件发生变化，请重新处理。")
        return path

    def asset(self, identifier, owner, kind, item_id, *, download=False, thumbnail=False, content_version=None):
        with self.lock:
            if kind not in {"source", "item", "before"} or (download and thumbnail) or (download and kind == "before"):
                raise ValueError("图片预览参数无效。")
            job = self._get(identifier, owner)
            rows = job["sources"] if kind == "source" else job["items"]
            item = next((row for row in rows if row["id"] == item_id and row.get("status") != "superseded"), None)
            if item is None:
                raise KeyError("找不到此图片。")
            if download and (job["status"] in _BUSY or item["status"] not in _DOWNLOADABLE):
                raise Conflict("这张素材正在处理或已舍弃，暂不能下载。")
            if kind == "source":
                original = self._source_path(job, item)
            else:
                self._source_path(job, self._source(job, item["source_id"]))
                original = self._item_path(job, item)
                if kind == "before":
                    previous = next((row for row in job["items"] if row["id"] == item.get("previous_item_id")
                                     and row["source_id"] == item["source_id"] and row["status"] == "superseded"), None)
                    if previous is None:
                        raise KeyError("这张素材还没有精修前的对照图。")
                    original = self._item_path(job, previous)
                    item = previous
            if not thumbnail:
                return original, item["sha256"]
            # Keep all original integrity checks above even for a cached/304
            # derivative. A stale thumbnail cannot hide a changed source/result.
            digest = item["thumbnail_sha256"]
            if content_version is not None and content_version != digest[:16]:
                raise KeyError("图片预览已更新，请刷新页面。")
            path = self._private(self._directory(identifier) / (item["id"] + ".thumb.png"))
            if _digest(path) != digest:
                raise ValueError("图片预览发生变化，请重新处理。")
            return path, digest

    def download(self, identifier, owner):
        with self.lease(identifier, owner), self.lock:
            job = self._get(identifier, owner)
            if job["status"] in _BUSY:
                raise Conflict("素材仍在处理中，请稍候再下载。")
            items = [row for row in job["items"] if row["status"] in _DOWNLOADABLE]
            if not items:
                raise ValueError("还没有可下载的素材，请等待生成完成或恢复已舍弃的素材。")
            target = self._directory(identifier) / "materials.zip"
            temporary = self._directory(identifier) / (".zip-" + secrets.token_hex(16))
            try:
                with zipfile.ZipFile(temporary, "x", compression=zipfile.ZIP_STORED) as archive:
                    records = []
                    for index, item in enumerate(items, 1):
                        self._source_path(job, self._source(job, item["source_id"]))
                        path = self._item_path(job, item)
                        DiskBudget(target.parent).reserve(path.stat().st_size + 8192)
                        archive.write(path, f"素材-{index:03d}.png")
                        records.append({"file": f"素材-{index:03d}.png", "name": item["name"],
                                        "source": self._source(job, item["source_id"])["name"],
                                        "bounds": item["bounds"], "status": item["status"], "warnings": item["warnings"]})
                    archive.writestr("素材说明.json", json.dumps({"note": "生成素材未经质量核验；下载不代表人工确认，请检查文字、配色和设计完整性。",
                                    "items": records, "unhandled": sum(row["status"] == "skipped" for row in job["items"]),
                                    "failed_sources": sum(row["status"] == "error" for row in job["sources"]),
                                    "unprocessed_sources": sum(row["status"] in {"queued", "processing", "cancelled"} for row in job["sources"])}, ensure_ascii=False, indent=2))
                os.chmod(temporary, 0o600); os.replace(temporary, target)
            finally:
                temporary.unlink(missing_ok=True)
            return target, _digest(target)

    def has_active_operations(self):
        with self.lock:
            return any(not future.done() for future in self.futures.values()) or bool(self.leases) or bool(self.upload_leases)

    def close(self):
        with self.lock:
            self._closed = True
        self.executor.shutdown(wait=True, cancel_futures=False)

    def _remove_tree(self, directory):
        checked_path(directory, self.root)
        for path in directory.rglob("*"):
            checked_path(path, directory)
            if path.is_file() and path.stat().st_nlink != 1:
                raise ValueError("素材目录含异常文件，未清理。")
        shutil.rmtree(directory)

    def retention_sweep(self):
        """Only cloud instances expire signed, settled, idle, owned tasks."""
        if not self.cloud:
            return []
        removed = []
        with self.lock:
            for directory in self.upload_root.iterdir():
                try:
                    if not _ID.fullmatch(directory.name) or directory.name in self.upload_leases:
                        continue
                    marker = self._upload_marker(checked_path(directory, self.upload_root))
                    if marker["orphaned_at"] is None:
                        # A crash may have happened long after upload start.
                        # Start retention only after observing that it is idle.
                        marker["orphaned_at"] = self.clock()
                        signature = hmac.new(self._key, _canonical(marker), hashlib.sha256).hexdigest()
                        self._write(directory / ".material-upload", _canonical({"payload": marker, "hmac_sha256": signature}))
                    elif marker["orphaned_at"] + _RETENTION <= self.clock():
                        self._remove_tree(directory)
                        removed.append("upload:" + directory.name)
                except (OSError, ValueError, KeyError, TypeError):
                    continue
            for directory in self.tasks_root.iterdir():
                try:
                    if not _ID.fullmatch(directory.name):
                        continue
                    job = self._read(directory)
                    expiry = job.get("expires_at")
                    if (job["status"] not in _TERMINAL or type(expiry) not in {int, float}
                            or expiry > self.clock() or self.leases.get(job["id"])
                            or (job["id"] in self.futures and not self.futures[job["id"]].done())):
                        continue
                    # Re-read authenticated ownership at the destructive boundary.
                    if self._read(directory) != job:
                        continue
                    self._remove_tree(directory)
                    self.jobs.pop(job["id"], None); self.futures.pop(job["id"], None)
                    removed.append(job["id"])
                except (OSError, ValueError, KeyError, TypeError):
                    continue
        return removed
