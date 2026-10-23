"""Signed, cloud-only expiry of this service's managed employee task files.

There are no supplied filesystem paths in a manifest. UUIDs identify the four
private service namespaces; settings and accounting never enter the deletion
plan. Local/LAN JobManager instances do not create or invoke this component.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import math
import os
import re
import secrets
import shutil
import stat
import threading
import time
from pathlib import Path

from .service import BUSY

_UUID = re.compile(r"[0-9a-f]{32}")
_FINISHED = {"ready", "done", "error", "cancelled"}
_STATES = BUSY | _FINISHED | {"orphaned"}
_FIELDS = {"schema", "job_id", "batch_id", "registered_at", "observed_at",
           "settled_at", "expires_at", "retention_seconds", "status", "revision",
           "operation_token"}
_LOG = logging.getLogger(__name__)


def _linked(path):
    return path.is_symlink() or bool(getattr(path.lstat(), "st_file_attributes", 0) & 0x400)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode("ascii")


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate retention field")
        result[key] = value
    return result


class CloudRetention:
    """Expire settled cloud uploads after three days, never during a lease.

    All observations and leases are serialized by manager.lock. The conservative
    global operation/future check also protects a phase which has just published
    ready/error while its accepted background work has not finished unwinding.
    """

    def __init__(self, manager, job_leases: dict, retention_seconds=259200,
                 interval_seconds=60, *, companion=None):
        if (isinstance(retention_seconds, bool) or not isinstance(retention_seconds, (int, float))
                or not math.isfinite(retention_seconds) or retention_seconds <= 0
                or isinstance(interval_seconds, bool) or not isinstance(interval_seconds, (int, float))
                or not math.isfinite(interval_seconds) or interval_seconds <= 0):
            raise ValueError("Invalid cloud retention interval")
        self.manager, self.job_leases = manager, job_leases
        self.companion = companion
        self.retention_seconds = float(retention_seconds)
        self.interval_seconds = float(interval_seconds)
        self.data = manager.data_dir.absolute()
        self._safe_directory(self.data)
        self.root = self.data / "cloud_retention"
        self._make_directory(self.root)
        self.manifests = self.root / "manifests"
        self._make_directory(self.manifests)
        self._key = self._signing_key()
        self._records = {}
        self._event = threading.Event()
        self._thread = None
        self._sweep_lock = threading.Lock()
        self._expiring = set()
        manager._expiring_tasks = self._expiring
        self._load()
        persistence = getattr(manager, "task_persistence", None)
        if persistence is not None:
            persistence.retention = self

    @staticmethod
    def _safe_directory(path):
        for part in (path, *path.parents):
            if part.is_symlink() or (part.exists() and (_linked(part) or not part.is_dir())):
                raise ValueError("Unsafe cloud retention directory")
        if path.resolve() != path:
            raise ValueError("Unsafe cloud retention directory")

    def _make_directory(self, path):
        self._safe_directory(path)
        path.mkdir(mode=0o700, exist_ok=True)
        self._safe_directory(path)

    def _signing_key(self):
        target = self.root / "retention-signing.key"
        if not target.exists():
            if any(self.manifests.iterdir()):
                raise ValueError("Cloud retention signing key is missing; existing files were preserved")
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
            with os.fdopen(os.open(target, flags, 0o600), "wb") as stream:
                stream.write(secrets.token_bytes(32))
                stream.flush()
                os.fsync(stream.fileno())
        self._private_file(target)
        key = target.read_bytes()
        if len(key) != 32:
            raise ValueError("Invalid cloud retention signing key")
        return key

    @staticmethod
    def _private_file(path):
        info = path.lstat()
        if _linked(path) or not stat.S_ISREG(info.st_mode):
            raise ValueError("Unsafe cloud retention file")
        if os.name != "nt" and (info.st_mode & 0o077 or info.st_uid != os.getuid()):
            raise ValueError("Cloud retention files must be private to the service user")

    def _path(self, identifier):
        if not isinstance(identifier, str) or not _UUID.fullmatch(identifier):
            raise ValueError("Invalid cloud retention task")
        return self.manifests / (identifier + ".json")

    def _validate(self, payload, identifier):
        if not isinstance(payload, dict) or set(payload) != _FIELDS:
            raise ValueError("Invalid cloud retention manifest")
        if (payload["schema"] != 1 or type(payload["schema"]) is not int
                or payload["job_id"] != identifier or not _UUID.fullmatch(identifier)
                or not isinstance(payload["batch_id"], str) or not _UUID.fullmatch(payload["batch_id"])
                or payload["status"] not in _STATES
                or type(payload["revision"]) is not int or payload["revision"] < 0
                or not isinstance(payload["operation_token"], str) or len(payload["operation_token"]) > 128
                or payload["retention_seconds"] != self.retention_seconds):
            raise ValueError("Invalid cloud retention manifest")
        for field in ("registered_at", "observed_at"):
            value = payload[field]
            if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
                raise ValueError("Invalid cloud retention time")
        if payload["observed_at"] < payload["registered_at"]:
            raise ValueError("Invalid cloud retention time")
        settled, expires = payload["settled_at"], payload["expires_at"]
        if payload["status"] in BUSY:
            if settled is not None or expires is not None:
                raise ValueError("Invalid cloud retention expiry")
        elif (type(settled) not in (int, float) or type(expires) not in (int, float)
              or not math.isfinite(settled) or not math.isfinite(expires)
              or settled < payload["registered_at"] or settled > payload["observed_at"]
              or expires != settled + self.retention_seconds):
            raise ValueError("Invalid cloud retention expiry")
        return payload

    def _load(self):
        for target in self.manifests.iterdir():
            if not target.name.endswith(".json"):
                continue
            try:
                identifier = target.stem
                self._records[identifier] = self._read(identifier)
            except (OSError, ValueError, TypeError, OverflowError):
                _LOG.warning("An unsafe cloud retention manifest was ignored; task files were preserved")

    def _read(self, identifier):
        target = self._path(identifier)
        self._safe_directory(self.manifests)
        self._private_file(target)
        if target.stat().st_size > 8192:
            raise ValueError("Oversized cloud retention manifest")
        envelope = json.loads(target.read_text("utf-8"), object_pairs_hook=_pairs)
        if not isinstance(envelope, dict) or set(envelope) != {"payload", "hmac_sha256"}:
            raise ValueError("Invalid cloud retention envelope")
        signature = hmac.new(self._key, _canonical(envelope["payload"]), hashlib.sha256).hexdigest()
        supplied = envelope["hmac_sha256"]
        if not isinstance(supplied, str) or not hmac.compare_digest(signature, supplied):
            raise ValueError("Cloud retention manifest changed")
        return self._validate(envelope["payload"], identifier)

    def _save(self, payload):
        identifier = payload["job_id"]
        self._validate(payload, identifier)
        self._safe_directory(self.manifests)
        target = self._path(identifier)
        if target.exists() or target.is_symlink():
            self._private_file(target)
            prior = self._records.get(identifier)
            if prior is None or self._read(identifier) != prior:
                raise ValueError("Cloud retention manifest changed")
        signature = hmac.new(self._key, _canonical(payload), hashlib.sha256).hexdigest()
        temporary = self.manifests / (".write-" + secrets.token_hex(16))
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        try:
            with os.fdopen(os.open(temporary, flags, 0o600), "wb") as stream:
                stream.write(_canonical({"payload": payload, "hmac_sha256": signature}))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
            self._records[identifier] = payload
        finally:
            temporary.unlink(missing_ok=True)

    def _job_paths(self, job):
        identifier = job.get("id")
        if not isinstance(identifier, str) or not _UUID.fullmatch(identifier):
            raise ValueError("Invalid cloud task identity")
        upload = Path(job.get("_upload_dir", "")).absolute()
        batch = upload.name
        if (job.get("_upload_managed") is not True or not job.get("_owner_id")
                or not isinstance(batch, str) or not _UUID.fullmatch(batch)
                or upload != self.data / "uploads" / batch
                or Path(job.get("_work_dir", "")).absolute() != self.data / "jobs" / identifier
                or Path(job.get("_output_root", "")).absolute() != self.data / "employee_outputs" / batch):
            raise ValueError("Cloud retention requires an isolated managed upload")
        for path in (self.data / "uploads" / batch, self.data / "jobs" / identifier):
            self._safe_directory(path)
        for path, marker, content in ((upload, ".hsd-upload", batch),
                                      (self.data / "jobs" / identifier, ".hsd-job", identifier)):
            target = path / marker
            if _linked(target) or target.read_text("ascii") != content:
                raise ValueError("Invalid cloud retention ownership marker")
        return batch

    def register(self, identifier):
        """Called under the manager's RLock after multipart upload commit."""
        with self.manager.lock:
            job = self.manager._get(identifier)
            batch = self._job_paths(job)
            if job["id"] != identifier or any(
                    record["batch_id"] == batch and owner != identifier
                    for owner, record in self._records.items()):
                raise ValueError("Cloud retention upload ownership is not unique")
            if identifier in self._records:
                if self._records[identifier]["batch_id"] != batch:
                    raise ValueError("Cloud retention task ownership changed")
                return
            now = time.time()
            status = job.get("status")
            if status not in BUSY | _FINISHED:
                raise ValueError("Invalid cloud retention task status")
            settled = None if status in BUSY else now
            payload = {"schema": 1, "job_id": identifier, "batch_id": batch,
                       "registered_at": now, "observed_at": now,
                       "settled_at": settled, "expires_at": None if settled is None else now + self.retention_seconds,
                       "retention_seconds": self.retention_seconds, "status": status,
                       "revision": job.get("revision", 0), "operation_token": job.get("_operation_token") or ""}
            self._save(payload)

    def _observe(self, payload, job, now):
        status = job.get("status")
        if status not in BUSY | _FINISHED:
            raise ValueError("Invalid cloud retention task state")
        if self._job_paths(job) != payload["batch_id"]:
            raise ValueError("Cloud retention task ownership changed")
        if job["id"] != payload["job_id"]:
            raise ValueError("Cloud retention task identity changed")
        revision, token = job.get("revision", 0), job.get("_operation_token") or ""
        changed = (status != payload["status"] or revision != payload["revision"]
                   or token != payload["operation_token"])
        if not changed:
            return payload
        # A backwards system-clock adjustment must never shorten preservation.
        now = max(now, payload["observed_at"])
        settled = None if status in BUSY else now
        updated = {**payload, "observed_at": now, "status": status, "revision": revision,
                   "operation_token": token, "settled_at": settled,
                   "expires_at": None if settled is None else settled + self.retention_seconds}
        self._save(updated)
        return updated

    def _targets(self, payload):
        identifier, batch = payload["job_id"], payload["batch_id"]
        targets = (self.data / "uploads" / batch, self.data / "employee_outputs" / batch,
                   self.data / "jobs" / identifier, self.data / "task_records" / identifier)
        # Validate the entire plan before removing anything. Never follow links,
        # including nested links, even though shutil.rmtree itself avoids them.
        for target in targets:
            self._safe_directory(target.parent)
            if not target.exists() and not target.is_symlink():
                continue
            self._safe_directory(target)
            for directory, dirs, files in os.walk(target, followlinks=False):
                for name in dirs + files:
                    if _linked(Path(directory) / name):
                        raise ValueError("Cloud task contains an unsafe link")
        for target, marker, identity in ((targets[0], ".hsd-upload", batch),
                                         (targets[2], ".hsd-job", identifier)):
            if target.exists() and (target / marker).read_text("ascii") != identity:
                raise ValueError("Cloud task ownership marker changed")
        return targets

    def sweep(self, now=None, *, delete=True):
        """Observe and expire eligible tasks; public for deterministic QA."""
        now = time.time() if now is None else float(now)
        if not math.isfinite(now) or now <= 0:
            raise ValueError("Invalid cloud retention clock")
        removed = []
        with self._sweep_lock:
            with self.manager.lock:
                identifiers = list(self._records)
            for identifier in identifiers:
                try:
                    # Reserve this task while locked, then inspect its tree
                    # without holding up other employees' status/preview calls.
                    with self.manager.lock:
                        payload = self._records[identifier]
                        if self._read(identifier) != payload:
                            raise ValueError("Cloud retention manifest changed")
                        job = self.manager.jobs.get(identifier)
                        if job is not None:
                            payload = self._observe(payload, job, now)
                        elif payload["status"] in BUSY:
                            settled = max(now, payload["observed_at"])
                            payload = {**payload, "status": "orphaned", "observed_at": settled,
                                       "settled_at": settled, "expires_at": settled + self.retention_seconds}
                            self._save(payload)
                        if (not delete or payload["status"] in BUSY or payload["expires_at"] > now
                                or self.job_leases.get(identifier, 0) or self._has_work(identifier)):
                            continue
                        self._expiring.add(identifier)
                        reserved_job = job
                        reserved = (payload["status"], payload["revision"], payload["operation_token"])
                    targets = self._targets(payload)
                    with self.manager.lock:
                        job = self.manager.jobs.get(identifier)
                        if job is not reserved_job or self.job_leases.get(identifier, 0) or self._has_work(identifier):
                            continue
                        if job is not None and (job.get("status"), job.get("revision", 0),
                                                job.get("_operation_token") or "") != reserved:
                            continue
                        manifest = self._path(identifier)
                        if job is not None:
                            self.manager.jobs.pop(identifier, None)
                            self.manager._job_locks.pop(identifier, None)
                    # Deleting a large batch must not hold the global UI lock.
                    # A signed manifest remains until every directory is gone,
                    # so interrupted cleanup can safely resume after restart.
                    for target in targets:
                        if target.exists():
                            shutil.rmtree(target)
                    persistence = getattr(self.manager, "task_persistence", None)
                    if persistence is not None:
                        persistence.forget_job(identifier)
                    manifest.unlink()
                    with self.manager.lock:
                        self._records.pop(identifier, None)
                    removed.append(identifier)
                except (OSError, ValueError, TypeError, OverflowError):
                    _LOG.warning("Cloud task expiry was deferred because its files or state could not be verified")
                finally:
                    with self.manager.lock:
                        self._expiring.discard(identifier)
            if delete:
                persistence = getattr(self.manager, "task_persistence", None)
                if persistence is not None:
                    persistence.sweep_uploads(now=now)
        return removed

    def _has_work(self, identifier):
        checker = getattr(self.manager, "task_has_work", None)
        if checker is not None:
            return checker(identifier)
        # Older standalone managers/fixtures remain conservative. Production
        # JobManager tracks each task rather than requiring the entire service
        # to be idle before an unrelated old batch can expire.
        return bool(self.manager._active_operations or self.manager._inflight_futures)

    def start(self):
        if self._thread is not None:
            return self
        self._cycle()
        self._event.clear()
        def run():
            while not self._event.wait(self.interval_seconds):
                self._cycle()
        self._thread = threading.Thread(target=run, name="hsd-cloud-retention", daemon=True)
        self._thread.start()
        return self

    def _cycle(self):
        self.sweep()
        if self.companion is not None:
            try:
                self.companion.retention_sweep()
            except Exception:
                # A separate task namespace must not disable numbering expiry
                # or leak filenames/provider details through the service log.
                _LOG.warning("Material expiry was deferred; task files were preserved")

    def stop(self):
        self._event.set()
        thread, self._thread = self._thread, None
        if thread is not None and thread is not threading.current_thread():
            thread.join()
        # Persist the last terminal state without deleting at service exit.
        self.sweep(delete=False)
