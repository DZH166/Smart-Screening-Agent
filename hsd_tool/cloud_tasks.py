"""Private signed cloud checkpoints and browser-scoped upload reservations.

No request body, provider credential or model transport object enters this
store. Restoring a checkpoint never submits work to an executor.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import stat
import threading
import time

from . import __version__
from .uploads import checked_path

_ID = re.compile(r"[0-9a-f]{32}")
_TOKEN = re.compile(r"[A-Za-z0-9_-]{43}")
_OWNER = re.compile(r"[0-9a-f]{64}")
_SETTLED = {"ready", "done", "error", "cancelled"}
# Explicit schema: caches, arrays, Futures, settings and provider keys are not
# serializable task state. New service fields must be consciously added here.
_FIELDS = frozenset("""id status progress error sheet_name workbook_name source_name
start_number prefix rows files warnings output_dir output_target report stats
revision timings matching_mode ai_retrieval ai_review cancellation_requested cancel_requested
_workbook_path _source_path _output_root _work_dir _reserved _input_digest
_upload_digests _owner_id _downloadable _upload_managed _upload_dir
_snapshot_workbook _snapshot_digest _source_archive_digest _history _operation_token
_completed_export _export_members _download_path _download_sha256
_records_dir _record_manifest _comparison_bindings _ai_runs _ai_records_dir
_ai_observation_artifact _ai_observation_runs _ai_first_runs _upload_request_id
""".split())
_PATH_FIELDS = frozenset("""_workbook_path _source_path _output_root _work_dir
_upload_dir _snapshot_workbook _download_path output_dir output_target _records_dir
_ai_records_dir image_path preview_path source_path path records_dir""".split())


def upload_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{32}|[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", value):
        raise ValueError("上传请求标识无效，请重新选择文件。")
    return value.replace("-", "")


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode("ascii")


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate checkpoint field")
        result[key] = value
    return result


class UploadClaims:
    """An ID is claimed before multipart parsing, including cancellation races."""
    def __init__(self):
        self.lock = threading.RLock()
        self.claims = {}
        self.live = set()

    def _read_claim(self, identifier):
        return self.claims.get(identifier)

    def _write_claim(self, identifier, payload):
        if payload is None:
            self.claims.pop(identifier, None)
        else:
            self.claims[identifier] = payload

    def lookup(self, identifier, owner):
        identifier = upload_id(identifier)
        with self.lock:
            record = self._read_claim(identifier)
            if record is None:
                return {"state": "missing"}
            if record["owner"] != owner:
                raise KeyError("找不到此上传请求。")
            result = {"state": "missing" if record["state"] == "retry" else record["state"]}
            for key in ("job_id", "cancellation_requested"):
                if key in record:
                    result[key] = record[key]
            return result

    def reserve(self, identifier, owner):
        identifier = upload_id(identifier)
        with self.lock:
            current = self.lookup(identifier, owner)
            if current["state"] != "missing":
                return current
            self._write_claim(identifier, {"owner": owner, "state": "pending", "created_at": time.time()})
            self.live.add(identifier)
            return {"state": "reserved"}

    def commit(self, identifier, owner, job_id):
        with self.lock:
            record = self._read_claim(identifier)
            if (record is None or record["owner"] != owner or record["state"] != "pending"
                    or record.get("cancellation_requested")):
                raise ValueError("本次上传已停止，请重新选择文件。")
            self._write_claim(identifier, {**record, "state": "completed", "job_id": job_id})

    def finish(self, identifier, owner):
        with self.lock:
            self.live.discard(identifier)
            record = self._read_claim(identifier)
            if record and record["owner"] == owner and record["state"] == "pending":
                self._write_claim(identifier, {**record, "state": "cancelled"}
                                  if record.get("cancellation_requested") else None)

    def ensure_active(self, identifier, owner):
        state = self.lookup(identifier, owner)
        if state["state"] != "pending" or state.get("cancellation_requested"):
            raise ValueError("本次上传已停止，请重新选择文件。")

    def bind_directory(self, identifier, owner, directory):
        with self.lock:
            self.ensure_active(identifier, owner)
            batch = Path(directory).name
            if not _ID.fullmatch(batch):
                raise ValueError("上传暂存标识无效。")
            record = self._read_claim(identifier)
            self._write_claim(identifier, {**record, "batch_id": batch})

    def cancel(self, identifier, owner):
        identifier = upload_id(identifier)
        with self.lock:
            current = self.lookup(identifier, owner)
            if current["state"] == "completed":
                return current
            record = self._read_claim(identifier) or {"owner": owner, "created_at": time.time()}
            state = "pending" if identifier in self.live else "cancelled"
            self._write_claim(identifier, {**record, "state": state, "cancellation_requested": True})
            return self.lookup(identifier, owner)


class CloudTaskStore(UploadClaims):
    def __init__(self, manager, origin):
        super().__init__()
        self.manager = manager
        self.data = manager.data_dir.absolute()
        self.root = checked_path(self.data / "cloud_recovery", self.data)
        self.root.mkdir(mode=0o700, exist_ok=True)
        self.claim_root = self.root / "uploads"
        self.claim_root.mkdir(mode=0o700, exist_ok=True)
        self.key = self._key()
        self.cookie_name = "hsd_recovery_" + hashlib.sha256(origin.encode()).hexdigest()[:12]
        self.implementation = self._implementation()
        self.instance = secrets.token_hex(16)

    def _key(self):
        target = checked_path(self.root / "signing.key", self.data)
        if not target.exists():
            # Losing this key must not silently re-baseline old signed files.
            if any(self.claim_root.iterdir()) or any((self.data / "task_records").glob("*/cloud-state.json")):
                raise ValueError("云任务恢复签名密钥缺失，原任务已保留，请联系管理员。")
            fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(secrets.token_bytes(32)); stream.flush(); os.fsync(stream.fileno())
        raw = self._private_read(target, 32)
        if len(raw) != 32:
            raise ValueError("云任务恢复签名密钥无效。")
        return raw

    @staticmethod
    def _implementation():
        result = hashlib.sha256(__version__.encode())
        root = Path(__file__).parent
        for source in sorted(root.glob("*.py")):
            result.update(source.name.encode()); result.update(source.read_bytes())
        return result.hexdigest()

    def owner(self, token):
        if not isinstance(token, str) or not _TOKEN.fullmatch(token):
            raise ValueError("浏览器恢复凭据无效。")
        return hmac.new(self.key, b"browser-owner:" + token.encode("ascii"), hashlib.sha256).hexdigest()

    @staticmethod
    def new_token():
        return secrets.token_urlsafe(32)

    def _private_read(self, target, maximum=64 * 1024**2):
        target = checked_path(target, self.data)
        info = target.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError("云任务恢复文件无效。")
        if os.name != "nt" and (info.st_uid != os.getuid() or info.st_mode & 0o077):
            raise ValueError("云任务恢复文件必须为服务用户私有。")
        fd = os.open(target, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(fd, "rb") as stream:
            opened = os.fstat(stream.fileno())
            if (opened.st_ino, opened.st_dev) != (info.st_ino, info.st_dev) or opened.st_size > maximum:
                raise ValueError("云任务恢复文件已变化或过大。")
            raw = stream.read(maximum + 1)
        if len(raw) > maximum:
            raise ValueError("云任务恢复文件过大。")
        return raw

    def _read(self, path):
        envelope = json.loads(self._private_read(path), object_pairs_hook=_unique)
        if not isinstance(envelope, dict) or set(envelope) != {"payload", "signature"}:
            raise ValueError("云任务恢复记录无效。")
        expected = hmac.new(self.key, _canonical(envelope["payload"]), hashlib.sha256).hexdigest()
        if not isinstance(envelope["signature"], str) or not hmac.compare_digest(expected, envelope["signature"]):
            raise ValueError("云任务恢复记录签名不一致，已保留原件。")
        return envelope["payload"]

    def _write(self, path, payload):
        checked_path(path, self.data)
        path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        temporary = path.with_name(".state-" + secrets.token_hex(16))
        signature = hmac.new(self.key, _canonical(payload), hashlib.sha256).hexdigest()
        try:
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(_canonical({"payload": payload, "signature": signature}))
                stream.flush(); os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def _read_claim(self, identifier):
        # Streaming writes check cancellation for each chunk. Only the first
        # lookup after a process restart needs filesystem/HMAC work; mutations
        # are serialized by this store and publish cache state after fsync.
        if identifier in self.claims:
            return self.claims[identifier]
        path = self.claim_root / (identifier + ".json")
        if not path.exists():
            return None
        record = self._read(path)
        if (not isinstance(record, dict) or record.get("id") != identifier
                or not _OWNER.fullmatch(str(record.get("owner", "")))
                or record.get("state") not in {"pending", "completed", "cancelled", "retry"}):
            raise ValueError("上传恢复记录无效。")
        if record["state"] == "pending" and record.get("instance") != self.instance:
            # The previous process cannot accept more body bytes. Never restart
            # its CPU/AI work; a retry with the same ID may upload afresh.
            record = {**record, "state": "cancelled" if record.get("cancellation_requested") else "retry"}
            self._write_claim(identifier, record)
        self.claims[identifier] = record
        return record

    def _write_claim(self, identifier, payload):
        path = self.claim_root / (identifier + ".json")
        if payload is None:
            checked_path(path, self.data).unlink(missing_ok=True)
            self.claims.pop(identifier, None)
        else:
            record = {**payload, "id": identifier, "instance": self.instance}
            self._write(path, record)
            self.claims[identifier] = record

    def reserve(self, identifier, owner):
        identifier = upload_id(identifier)
        with self.lock:
            previous = self._read_claim(identifier)
            if (previous and previous["owner"] == owner and previous["state"] == "retry"
                    and previous.get("batch_id")):
                # Preserve the signed ownership of a crashed partial transfer
                # even when its original request ID is retried successfully.
                self._write_claim(secrets.token_hex(16), {**previous, "state": "cancelled"})
                previous = {key: value for key, value in previous.items() if key != "batch_id"}
                self._write_claim(identifier, previous)
            return super().reserve(identifier, owner)

    def _state_path(self, identifier):
        if not isinstance(identifier, str) or not _ID.fullmatch(identifier):
            raise ValueError("云任务标识无效。")
        return checked_path(self.data / "task_records" / identifier / "cloud-state.json", self.data)

    def _allowed_path(self, value, identifier, batch):
        path = Path(value)
        roots = [self.data / "uploads" / batch, self.data / "employee_outputs" / batch,
                 self.data / "jobs" / identifier, self.data / "task_records" / identifier]
        checked_path(path, self.data)
        if not any(path.is_relative_to(root) for root in roots):
            raise ValueError("云任务恢复路径越界。")
        return path

    def _encode(self, value, identifier, batch, field=None):
        if isinstance(value, Path) or (field in _PATH_FIELDS and isinstance(value, str) and Path(value).is_absolute()):
            path = self._allowed_path(value, identifier, batch)
            return {"$hsd_path": path.relative_to(self.data).parts}
        if isinstance(value, tuple):
            return {"$hsd_tuple": [self._encode(item, identifier, batch) for item in value]}
        if isinstance(value, list):
            return [self._encode(item, identifier, batch) for item in value]
        if isinstance(value, dict):
            if any(not isinstance(key, str) or key.startswith("$hsd_") for key in value):
                raise ValueError("云任务恢复字段无效。")
            return {key: self._encode(item, identifier, batch, key) for key, item in value.items()}
        if value is None or type(value) in {str, int, float, bool}:
            return value
        raise ValueError("云任务包含不能保存的运行对象。")

    def _decode(self, value, identifier, batch, field=None):
        if isinstance(value, dict):
            if set(value) == {"$hsd_path"}:
                parts = value["$hsd_path"]
                if (not isinstance(parts, list) or not parts
                        or any(not isinstance(part, str) or part in {"", ".", ".."} or "/" in part or "\\" in part or ":" in part for part in parts)):
                    raise ValueError("云任务恢复路径无效。")
                return str(self._allowed_path(self.data.joinpath(*parts), identifier, batch))
            if set(value) == {"$hsd_tuple"}:
                return tuple(self._decode(item, identifier, batch) for item in value["$hsd_tuple"])
            return {key: self._decode(item, identifier, batch, key) for key, item in value.items()}
        if isinstance(value, list):
            return [self._decode(item, identifier, batch) for item in value]
        if field in _PATH_FIELDS and isinstance(value, str) and value:
            raise ValueError("云任务路径必须由本批标识派生。")
        return value

    def save_job(self, job):
        if not job.get("_upload_managed") or not _OWNER.fullmatch(str(job.get("_owner_id", ""))):
            return
        identifier, batch = job["id"], Path(job["_upload_dir"]).name
        if not _ID.fullmatch(batch):
            raise ValueError("云任务上传归属无效。")
        state = {key: job[key] for key in _FIELDS if key in job}
        if "_comparison_bindings" in state:
            state["_comparison_bindings"] = [(Path(path), digest) for path, digest in state["_comparison_bindings"].items()]
        encoded = self._encode(state, identifier, batch)
        payload = {"schema": 1, "implementation": self.implementation, "id": identifier,
                   "batch": batch, "owner": job["_owner_id"], "saved_at": time.time(), "job": encoded}
        with self.lock:
            self._write(self._state_path(identifier), payload)
        retention = getattr(self, "retention", None)
        if retention is not None:
            with self.manager.lock:
                prior = retention._records.get(identifier)
                if prior is not None:
                    retention._observe(prior, job, time.time())

    def save_all(self):
        with self.manager.lock:
            jobs = list(self.manager.jobs.values())
        for job in jobs:
            self.save_job(job)

    def restore(self, identifier, owner, retention):
        with self.manager.lock:
            existing = self.manager.jobs.get(identifier)
            if existing is not None:
                if existing.get("_owner_id") != owner:
                    raise KeyError("找不到此任务。")
                return existing
            record = retention._records.get(identifier)
            if (record is None or identifier in getattr(retention, "_expiring", set())
                    or record.get("expires_at") is None or record["expires_at"] <= time.time()):
                raise KeyError("任务已过期或不能恢复，请重新上传。")
            retention.job_leases[identifier] = retention.job_leases.get(identifier, 0) + 1
        try:
            payload = self._read(self._state_path(identifier))
            if (payload.get("schema") != 1 or payload.get("implementation") != self.implementation
                    or payload.get("id") != identifier or payload.get("owner") != owner
                    or payload.get("batch") != record["batch_id"]):
                raise KeyError("找不到可安全恢复的任务。")
            job = self._decode(payload["job"], identifier, record["batch_id"])
            if "_comparison_bindings" in job:
                job["_comparison_bindings"] = dict(job["_comparison_bindings"])
            if (set(job) - _FIELDS or job.get("id") != identifier or job.get("_owner_id") != owner
                    or job.get("_upload_managed") is not True):
                raise ValueError("云任务恢复记录无效。")
            retention._job_paths(job)
            if job.get("status") not in _SETTLED:
                job.update(status="error", error="服务中断，本批未继续运行；请重新上传处理。",
                           progress={"message": "服务中断，请重新上传", "current": 0, "total": 1})
            elif job["status"] in {"ready", "done"}:
                try:
                    self.manager._check_import_sources(job)
                    self.manager._verify_comparison_sources(job, check_cancellation=False)
                    if job["status"] == "done":
                        self.manager._verify_export_records(job)
                except (OSError, ValueError, KeyError):
                    job.update(status="error", error="任务文件已变化或缺失，不能恢复导出；请重新上传。")
            job["_image_assets"] = {}
            job.setdefault("_history", [])
            job["restored"] = True
            with self.manager.lock:
                existing = self.manager.jobs.get(identifier)
                if existing is not None:
                    if existing.get("_owner_id") != owner:
                        raise KeyError("找不到此任务。")
                    return existing
                # A browser opening a retained result is not a new processing
                # event and must not renew its three-day retention window.
                if record["status"] != job["status"]:
                    retention._save({**record, "status": job["status"],
                                     "revision": job.get("revision", 0),
                                     "operation_token": job.get("_operation_token") or ""})
                self.manager.jobs[identifier] = job
                return job
        finally:
            with self.manager.lock:
                left = retention.job_leases.get(identifier, 1) - 1
                if left:
                    retention.job_leases[identifier] = left
                else:
                    retention.job_leases.pop(identifier, None)

    def restore_owner(self, owner, retention):
        restored = []
        with self.manager.lock:
            identifiers = list(retention._records)
        owned = []
        for identifier in identifiers:
            try:
                path = self._state_path(identifier)
                if path.exists():
                    payload = self._read(path)
                    if payload.get("owner") == owner:
                        owned.append((payload.get("saved_at", 0), identifier))
            except (OSError, ValueError, KeyError, TypeError):
                continue  # Invalid records never disclose or re-baseline data.
        for _, identifier in sorted(owned):
            try:
                self.restore(identifier, owner, retention)
                restored.append(identifier)
            except (OSError, ValueError, KeyError, TypeError):
                continue
        return restored

    def forget_job(self, identifier):
        """Remove only signed upload pointers to an already-expired task."""
        with self.lock:
            for path in self.claim_root.glob("*.json"):
                try:
                    record = self._read_claim(path.stem)
                    if record and record.get("job_id") == identifier:
                        self._write_claim(path.stem, None)
                except (OSError, ValueError, TypeError):
                    continue

    def sweep_uploads(self, now=None):
        """Expire signed abandoned uploads; unknown directories stay untouched."""
        now = time.time() if now is None else now
        with self.lock:
            for path in self.claim_root.glob("*.json"):
                try:
                    identifier = upload_id(path.stem)
                    record = self._read_claim(identifier)
                    if (record is None or identifier in self.live or record["state"] == "completed"
                            or record.get("created_at", now) + 259200 > now):
                        continue
                    batch = record.get("batch_id")
                    if batch is not None:
                        if not isinstance(batch, str) or not _ID.fullmatch(batch):
                            raise ValueError("Invalid abandoned upload")
                        directory = checked_path(self.data / "uploads" / batch, self.data)
                        if directory.exists():
                            marker = checked_path(directory / ".hsd-upload", self.data)
                            if marker.read_text("ascii") != batch:
                                raise ValueError("Invalid abandoned upload marker")
                            for parent, dirs, files in os.walk(directory, followlinks=False):
                                for name in dirs + files:
                                    checked_path(Path(parent) / name, directory)
                            shutil.rmtree(directory)
                    self._write_claim(identifier, None)
                except (OSError, ValueError, TypeError):
                    continue
