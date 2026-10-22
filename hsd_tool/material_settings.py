"""Private credentials for material-extraction validation, separate from DeepSeek.

Only an administrator API may call ``save``. Public snapshots never contain a
credential or suffix; ``runtime`` is process-only and must not be serialized.
There is deliberately no environment-key or session-only fallback.
"""
from __future__ import annotations

import base64
import json
import os
import re
from pathlib import Path
import stat
import tempfile
import threading

from .ai_settings import _DPAPI, _valid_key


_DEFAULT = object()
_PREFIX = b"HSD-MATERIAL-ARK-1\x00"
PROVIDER = "volcengine_ark"
_MODEL_ID = re.compile(r"(?:doubao-(?:seedream|seededit)-[A-Za-z0-9][A-Za-z0-9._-]*|ep-[A-Za-z0-9][A-Za-z0-9_-]*)")


def _valid_model(value):
    return isinstance(value, str) and (value == "" or len(value) <= 128 and _MODEL_ID.fullmatch(value) is not None)


MAX_SETTINGS_BYTES = 16 * 1024
_STORAGE_ERROR = "无法安全保存素材服务设置，本次设置未生效。"
_READ_WARNING = "素材服务设置无法读取，请重新保存；原密钥不会显示。"


class MaterialSettingsConflict(ValueError):
    code = "revision_conflict"


class MaterialSettings:
    def __init__(self, data_dir: str | Path, *, protector=_DEFAULT, environ=None,
                 credential_key_file=None):
        # A different provider must never inherit a fal credential or switch.
        # Leave the previous private file untouched, and never read it here.
        self.path = Path(data_dir).absolute() / "material_volcengine_settings.json"
        source = os.environ if environ is None else environ
        key_file = (source.get("HSD_CREDENTIAL_KEY_FILE", "")
                    if credential_key_file is None else credential_key_file)
        self._server_store = None
        if key_file:
            if protector is not _DEFAULT:
                raise ValueError("服务器主密钥配置不能与其他加密方式同时使用。")
            from .credential_store import LinuxCredentialStore
            self._server_store = LinuxCredentialStore(key_file, self.path)
            self._protector = self._server_store
        else:
            self._protector = (_DPAPI() if os.name == "nt" else None) if protector is _DEFAULT else protector
        self._lock = threading.RLock()
        self._enabled = False
        self._ark_key = ""
        self._model_id = ""
        self._encrypted = ""
        self._revision = 0
        self._warning = ""
        self._load()

    def _local_parent(self, *, create=False):
        # Linux production uses LinuxCredentialStore's descriptor-pinned I/O.
        # DPAPI storage preserves the existing settings directory's ACL and
        # rejects redirecting reparse points, links and non-private files.
        if create:
            self._local_parent()
            self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        for part in (*reversed(self.path.parent.parents), self.path.parent):
            try:
                info = part.lstat()
            except FileNotFoundError:
                continue
            if (not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode)
                    or getattr(info, "st_file_attributes", 0) & 0x400):
                raise ValueError(_STORAGE_ERROR)
        if os.name == "posix" and self.path.parent.exists():
            info = self.path.parent.stat()
            if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
                raise ValueError(_STORAGE_ERROR)

    def _local_file(self):
        try:
            info = self.path.lstat()
        except FileNotFoundError:
            return None
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or getattr(info, "st_file_attributes", 0) & 0x400):
            raise ValueError(_STORAGE_ERROR)
        if os.name == "posix" and (info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) not in {0o400, 0o600}):
            raise ValueError(_STORAGE_ERROR)
        return info

    def _read(self):
        if self._server_store is not None:
            return self._server_store.read_settings(MAX_SETTINGS_BYTES)
        self._local_parent()
        original = self._local_file()
        if original is None:
            return None
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        with os.fdopen(os.open(self.path, flags), "rb") as stream:
            opened = os.fstat(stream.fileno())
            if (opened.st_ino != original.st_ino or opened.st_dev != original.st_dev
                    or not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1):
                raise ValueError(_STORAGE_ERROR)
            content = stream.read(MAX_SETTINGS_BYTES + 1)
        if len(content) > MAX_SETTINGS_BYTES:
            raise ValueError(_STORAGE_ERROR)
        return content

    def _load(self):
        try:
            content = self._read()
            if content is None:
                return
            record = json.loads(content.decode("utf-8"))
            if (not isinstance(record, dict) or set(record) != {
                    "version", "provider", "enabled", "revision", "model_id", "encrypted_ark_key"}
                    or type(record.get("version")) is not int or record["version"] != 1
                    or record.get("provider") != PROVIDER
                    or not _valid_model(record.get("model_id"))
                    or type(record.get("enabled")) is not bool
                    or type(record.get("revision")) is not int or record["revision"] < 0
                    or not isinstance(record.get("encrypted_ark_key"), str)):
                raise ValueError(_STORAGE_ERROR)
            encrypted = record["encrypted_ark_key"]
            key = ""
            if encrypted:
                if self._protector is None:
                    raise ValueError(_STORAGE_ERROR)
                raw = self._protector.decrypt(base64.b64decode(encrypted, validate=True))
                if not isinstance(raw, bytes) or not raw.startswith(_PREFIX):
                    raise ValueError(_STORAGE_ERROR)
                key = raw[len(_PREFIX):].decode("ascii")
                if not _valid_key(key):
                    raise ValueError(_STORAGE_ERROR)
            if key and record["model_id"] and key in record["model_id"]:
                raise ValueError(_STORAGE_ERROR)
            if record["enabled"] and (not key or not record["model_id"]):
                raise ValueError(_STORAGE_ERROR)
            self._ark_key, self._encrypted = key, encrypted
            self._model_id = record["model_id"]
            self._enabled, self._revision = record["enabled"], record["revision"]
        except Exception:
            # Neither corrupt records nor OS/protector errors are safe to echo.
            self._ark_key = self._encrypted = self._model_id = ""
            self._enabled, self._revision = False, 0
            self._warning = _READ_WARNING

    def snapshot(self) -> dict:
        with self._lock:
            return {"provider": PROVIDER, "model_id": self._model_id,
                    "enabled": self._enabled, "configured": bool(self._ark_key),
                    "key_persistence": ("linux_aesgcm" if self._server_store is not None else
                                        "windows_dpapi" if self._protector is not None else "unavailable"),
                    "revision": self._revision, "warning": self._warning}

    def runtime(self) -> dict:
        """Private process-only configuration. Never return through an API."""
        with self._lock:
            return {"provider": PROVIDER, "model_id": self._model_id,
                    "enabled": self._enabled, "ark_key": self._ark_key, "revision": self._revision}

    def _write(self, record):
        if self._server_store is not None:
            self._server_store.write_settings(record)
            return
        temporary = None
        try:
            self._local_parent(create=True)
            self._local_file()
            descriptor, temporary = tempfile.mkstemp(prefix=".material-settings-", suffix=".tmp",
                                                      dir=self.path.parent)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(record, stream, ensure_ascii=False, allow_nan=False)
                stream.flush()
                os.fsync(stream.fileno())
            self._local_parent()
            self._local_file()
            os.replace(temporary, self.path)
        finally:
            if temporary is not None:
                try:
                    os.unlink(temporary)
                except FileNotFoundError:
                    pass

    def save(self, payload: dict) -> dict:
        if (not isinstance(payload, dict)
                or set(payload) - {"expected_revision", "api_key", "clear_key", "enabled", "model_id"}
                or type(payload.get("expected_revision")) is not int
                or payload["expected_revision"] < 0):
            raise ValueError("素材服务设置格式不正确，请重新读取后保存。")
        if "enabled" in payload and type(payload["enabled"]) is not bool:
            raise ValueError("是否启用必须选择开启或关闭。")
        if "clear_key" in payload and type(payload["clear_key"]) is not bool:
            raise ValueError("清除密钥选项不正确。")
        supplied_key = payload.get("api_key", "")
        if not isinstance(supplied_key, str) or supplied_key and not _valid_key(supplied_key):
            raise ValueError("API Key 格式不正确，请检查空格或换行。")
        if supplied_key and payload.get("clear_key"):
            raise ValueError("不能同时填写和清除密钥。")
        if "model_id" in payload and not _valid_model(payload["model_id"]):
            raise ValueError("请从火山方舟复制图片模型 ID 或接入点 ID，不要填写网址、密钥或空格。")
        with self._lock:
            if payload["expected_revision"] != self._revision:
                raise MaterialSettingsConflict("素材服务设置已在其他页面修改，请重新读取后保存。")
            key = "" if payload.get("clear_key") else supplied_key or self._ark_key
            model_id = "" if payload.get("clear_key") else payload.get("model_id", self._model_id)
            if key and model_id and key in model_id:
                raise ValueError("模型 ID 不能包含 API Key。")
            enabled = payload.get("enabled", self._enabled)
            if payload.get("clear_key"):
                enabled = False
            if enabled and not key:
                raise ValueError("请先保存素材服务 API Key，再开启。")
            if enabled and not model_id:
                raise ValueError("请先填写火山方舟图片模型 ID，再开启。")
            if key and self._protector is None:
                raise ValueError("本机暂不支持安全保存密钥，请配置服务器加密存储。")
            if key == self._ark_key and model_id == self._model_id and enabled == self._enabled and not self._warning:
                return self.snapshot()
            encrypted = self._encrypted if key == self._ark_key else ""
            try:
                if key and not encrypted:
                    encrypted = base64.b64encode(
                        self._protector.encrypt(_PREFIX + key.encode("ascii"))).decode("ascii")
                record = {"version": 1, "provider": PROVIDER, "model_id": model_id,
                          "enabled": enabled, "revision": self._revision + 1,
                          "encrypted_ark_key": encrypted}
                self._write(record)
            except Exception:
                raise ValueError(_STORAGE_ERROR) from None
            # Publish only after durable replacement, never optimistically.
            self._ark_key, self._encrypted, self._model_id = key, encrypted, model_id
            self._enabled, self._revision = enabled, record["revision"]
            self._warning = ""
            return self.snapshot()

    def save_ark_key(self, key: str, *, expected_revision: int, model_id=None) -> dict:
        update = {"api_key": key, "expected_revision": expected_revision}
        if model_id is not None:
            update["model_id"] = model_id
        return self.save(update)

    def remove_ark_key(self, *, expected_revision: int) -> dict:
        return self.save({"clear_key": True, "expected_revision": expected_revision})

    def set_enabled(self, enabled: bool, *, expected_revision: int) -> dict:
        return self.save({"enabled": enabled, "expected_revision": expected_revision})
