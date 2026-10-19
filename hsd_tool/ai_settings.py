"""Local DeepSeek configuration; API credentials never enter public snapshots.

Windows persists credentials with DPAPI CurrentUser. Other platforms retain a
new key in memory only rather than silently falling back to plaintext storage.
"""
from __future__ import annotations

import base64
import ctypes
import json
import os
import tempfile
import threading
import uuid
from pathlib import Path

MODEL = "deepseek-flash"
PRICE_DATE = "2026-10-15"
PRICES = {"cache_hit_usd_per_million": 0.006,
          "cache_miss_usd_per_million": 0.3,
          "output_usd_per_million": 1.2}


def _valid_key(value) -> bool:
    return (isinstance(value, str) and 10 <= len(value) <= 512
            and value.isascii() and all(33 <= ord(character) <= 126 for character in value))


class _DPAPI:
    """Current-user protection without displaying any Windows prompts."""

    def _transform(self, value: bytes, encrypt: bool) -> bytes:
        from ctypes import wintypes

        class Blob(ctypes.Structure):
            _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]

        buffer = (ctypes.c_ubyte * len(value)).from_buffer_copy(value)
        source = Blob(len(value), buffer)
        target = Blob()
        crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        kernel32.LocalFree.restype = ctypes.c_void_p
        if encrypt:
            function = crypt32.CryptProtectData
            function.argtypes = [ctypes.POINTER(Blob), wintypes.LPCWSTR, ctypes.POINTER(Blob),
                                 ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD,
                                 ctypes.POINTER(Blob)]
            arguments = (ctypes.byref(source), "HSD DeepSeek API credential", None,
                         None, None, 1, ctypes.byref(target))
        else:
            function = crypt32.CryptUnprotectData
            function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.POINTER(Blob),
                                 ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD,
                                 ctypes.POINTER(Blob)]
            arguments = (ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target))
        function.restype = wintypes.BOOL
        if not function(*arguments):
            raise ValueError("无法使用当前 Windows 用户保护密钥")
        try:
            return ctypes.string_at(target.data, target.size)
        finally:
            kernel32.LocalFree(target.data)

    def encrypt(self, value: bytes) -> bytes:
        return self._transform(value, True)

    def decrypt(self, value: bytes) -> bytes:
        return self._transform(value, False)


_DEFAULT = object()


class AiSettingsConflict(ValueError):
    code = "revision_conflict"


MAX_KEYS = 100
MAX_SETTINGS_BYTES = 1024 * 1024


def _label(value):
    if (not isinstance(value, str) or len(value) > 64
            or any(ord(character) < 32 or ord(character) == 127 for character in value)):
        raise ValueError("密钥名称最多 64 个字符，不能包含换行或控制字符")
    return value.strip()


def _valid_id(value):
    return isinstance(value, str) and (value == "legacy" or value == "environment"
                                     or len(value) == 32 and all(c in "0123456789abcdef" for c in value))


class AiSettings:
    def __init__(self, data_dir: str | Path, *, protector=_DEFAULT, environ=None):
        self.path = Path(data_dir) / "ai_settings.json"
        self._protector = (_DPAPI() if os.name == "nt" else None) if protector is _DEFAULT else protector
        self._environ = os.environ if environ is None else environ
        self._lock = threading.RLock()
        self._enabled = False
        self._keys = []
        self._revision = 0
        self._environment_enabled = True
        self._storage_warning = ""
        self._load()

    def _decrypt(self, encrypted):
        if not isinstance(encrypted, str) or self._protector is None:
            raise ValueError("unsupported credential protection")
        raw = self._protector.decrypt(base64.b64decode(encrypted, validate=True)).decode("ascii")
        if not _valid_key(raw):
            raise ValueError("invalid credential")
        return raw

    def _load(self):
        try:
            if not self.path.exists():
                return
            if self.path.stat().st_size > MAX_SETTINGS_BYTES:
                raise ValueError("oversized settings")
            payload = json.loads(self.path.read_text("utf-8"))
            if not isinstance(payload, dict) or payload.get("version") not in (1, 2):
                raise ValueError("invalid settings")
            enabled = payload.get("enabled") is True
            keys = []
            revision = 0
            environment_enabled = True
            if payload["version"] == 1:
                encrypted = payload.get("encrypted_api_key", "")
                if encrypted:
                    keys.append({"id": "legacy", "label": "原有密钥", "enabled": True,
                                 "api_key": self._decrypt(encrypted), "encrypted_api_key": encrypted})
            else:
                rows = payload.get("keys")
                revision = payload.get("key_revision")
                environment_enabled = payload.get("environment_enabled", True)
                if (not isinstance(rows, list) or len(rows) > MAX_KEYS
                        or type(revision) is not int or revision < 0
                        or type(environment_enabled) is not bool):
                    raise ValueError("invalid pool settings")
                seen_ids, seen_keys = set(), set()
                for row in rows:
                    if (not isinstance(row, dict) or not _valid_id(row.get("id"))
                            or row["id"] == "environment" or row["id"] in seen_ids
                            or type(row.get("enabled")) is not bool):
                        raise ValueError("invalid pool entry")
                    seen_ids.add(row["id"])
                    label = _label(row.get("label", ""))
                    encrypted = row.get("encrypted_api_key", "")
                    if not encrypted:
                        if not isinstance(encrypted, str):
                            raise ValueError("invalid credential")
                        continue  # A non-Windows session never persists a plaintext fallback.
                    key = self._decrypt(encrypted)
                    if key in seen_keys:
                        raise ValueError("duplicate credential")
                    seen_keys.add(key)
                    keys.append({"id": row["id"], "label": label, "enabled": row["enabled"],
                                 "api_key": key, "encrypted_api_key": encrypted})
            self._validate_labels(keys)
            self._enabled, self._keys = enabled, keys
            self._revision, self._environment_enabled = revision, environment_enabled
        except Exception:
            # Protectors may raise OS-specific errors. Neither their messages nor
            # malformed storage content are safe to publish to an administrator.
            self._storage_warning = "本机密钥无法读取，请重新填写；原密钥未回显。"
            self._enabled, self._keys, self._revision = False, [], 0

    def _effective_keys(self):
        if self._keys:
            return [{"id": row["id"], "label": row["label"], "enabled": row["enabled"],
                     "api_key": row["api_key"], "source": "saved"} for row in self._keys]
        environment_key = self._environ.get("DEEPSEEK_API_KEY", "")
        if _valid_key(environment_key):
            return [{"id": "environment", "label": "环境变量密钥", "enabled": self._environment_enabled,
                     "api_key": environment_key, "source": "environment"}]
        return []

    def _validate_labels(self, rows):
        # Also reject a removed/replaced credential pasted as a new label in the
        # same transaction, before the old runtime is replaced.
        secrets = [row["api_key"] for row in rows] + [row["api_key"] for row in self._keys]
        environment_key = self._environ.get("DEEPSEEK_API_KEY", "")
        if _valid_key(environment_key):
            secrets.append(environment_key)
        if any(key in row["label"] for key in secrets for row in rows):
            raise ValueError("密钥名称不能包含 API Key")

    def snapshot(self) -> dict:
        with self._lock:
            keys = self._effective_keys()
            source = keys[0]["source"] if keys else "none"
            persistence = "windows_dpapi" if self._protector is not None else "session_only"
            return {"enabled": self._enabled, "configured": bool(keys), "model": MODEL,
                    "mode": "evaluation", "key_source": source,
                    "key_persistence": persistence, "price_date": PRICE_DATE,
                    "prices": dict(PRICES), "price_basis": "peak_upper_bound",
                    "storage_warning": self._storage_warning,
                    "key_revision": self._revision, "key_count": len(keys),
                    "keys": [{name: row[name] for name in ("id", "label", "enabled", "source")}
                             for row in keys]}

    def runtime(self) -> dict:
        """Private process-only values. Never serialize this return value to a client."""
        with self._lock:
            keys = self._effective_keys()
            key = next((row["api_key"] for row in keys if row["enabled"]), "")
            return {"enabled": self._enabled, "api_key": key, "model": MODEL,
                    "keys": keys, "key_revision": self._revision,
                    "prices": dict(PRICES), "price_date": PRICE_DATE}

    def _commit(self, rows, enabled, environment_enabled):
        """Write first; only publish a new runtime after the atomic replacement."""
        self._validate_labels(rows)
        next_rows = []
        for row in rows:
            row = dict(row)
            if self._protector is not None:
                if not row.get("encrypted_api_key"):
                    try:
                        row["encrypted_api_key"] = base64.b64encode(
                            self._protector.encrypt(row["api_key"].encode("ascii"))).decode("ascii")
                    except Exception:
                        raise ValueError("Windows 无法加密密钥，本次设置未保存") from None
            else:
                row["encrypted_api_key"] = ""
            next_rows.append(row)
        changed = (next_rows != self._keys or environment_enabled != self._environment_enabled)
        revision = self._revision + int(changed)
        record = {"version": 2, "enabled": enabled, "model": MODEL,
                  "key_revision": revision, "environment_enabled": environment_enabled,
                  "keys": [{name: row[name] for name in ("id", "label", "enabled", "encrypted_api_key")}
                           for row in next_rows]}
        temporary = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary = tempfile.mkstemp(prefix=".ai-settings-", suffix=".tmp", dir=self.path.parent)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(record, stream, ensure_ascii=False, allow_nan=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        except OSError:
            raise ValueError("无法保存本机 DeepSeek 设置，本次设置未生效") from None
        finally:
            if temporary:
                try:
                    os.unlink(temporary)
                except OSError:
                    pass
        self._keys, self._enabled = next_rows, enabled
        self._revision, self._environment_enabled = revision, environment_enabled
        self._storage_warning = ""
        return self.snapshot()

    def save(self, payload: dict) -> dict:
        if not isinstance(payload, dict) or set(payload) - {"enabled", "api_key", "clear_key"}:
            raise ValueError("DeepSeek 设置格式不正确")
        if "enabled" in payload and type(payload["enabled"]) is not bool:
            raise ValueError("是否启用必须为布尔值")
        if "clear_key" in payload and type(payload["clear_key"]) is not bool:
            raise ValueError("清除密钥选项不正确")
        supplied_key = payload.get("api_key", "")
        if not isinstance(supplied_key, str) or supplied_key and not _valid_key(supplied_key):
            raise ValueError("API Key 格式不正确，请检查是否包含空格或换行")
        if supplied_key and payload.get("clear_key"):
            raise ValueError("不能同时填写与清除密钥")
        with self._lock:
            rows = [dict(row) for row in self._keys]
            if payload.get("clear_key") and rows:
                rows.pop(0)
            elif supplied_key:
                if rows and rows[0]["api_key"] != supplied_key:
                    if any(row["api_key"] == supplied_key for row in rows[1:]):
                        raise ValueError("此密钥已在密钥池中，请从管理分区调整")
                    rows[0].update(id=uuid.uuid4().hex, api_key=supplied_key, encrypted_api_key="")
                elif not rows:
                    rows.append({"id": uuid.uuid4().hex, "label": "默认密钥", "enabled": True,
                                 "api_key": supplied_key, "encrypted_api_key": ""})
            return self._commit(rows, payload.get("enabled", self._enabled), self._environment_enabled)

    def save_pool(self, payload: dict) -> dict:
        if (not isinstance(payload, dict)
                or set(payload) - {"add", "update", "remove", "expected_revision"}
                or type(payload.get("expected_revision")) is not int
                or payload["expected_revision"] < 0):
            raise ValueError("密钥池设置格式不正确，请刷新后重试")
        add, update, remove = (payload.get(name, []) for name in ("add", "update", "remove"))
        if (any(not isinstance(value, list) for value in (add, update, remove))
                or any(len(value) > MAX_KEYS for value in (add, update, remove))):
            raise ValueError("每次最多管理 100 个密钥")
        with self._lock:
            if payload["expected_revision"] != self._revision:
                raise AiSettingsConflict("密钥池已在其他页面修改，请刷新后重试")
            rows = [dict(row) for row in self._keys]
            environment_enabled = self._environment_enabled
            existing = {row["id"]: row for row in rows}
            environment_exists = not rows and bool(self._effective_keys())
            if any(not _valid_id(identity) for identity in remove) or len(set(remove)) != len(remove):
                raise ValueError("删除密钥的标识不正确")
            if any(identity not in existing for identity in remove):
                raise ValueError("密钥已不存在；环境变量密钥须从主机环境中移除")
            rows = [row for row in rows if row["id"] not in remove]
            existing = {row["id"]: row for row in rows}
            updated = set()
            for change in update:
                if (not isinstance(change, dict) or set(change) - {"id", "label", "enabled"}
                        or not _valid_id(change.get("id")) or change["id"] in updated):
                    raise ValueError("更新密钥的格式不正确")
                identity = change["id"]
                updated.add(identity)
                if identity == "environment" and environment_exists:
                    if "label" in change:
                        raise ValueError("环境变量密钥名称不能修改")
                    if "enabled" in change:
                        if type(change["enabled"]) is not bool:
                            raise ValueError("密钥启用选项必须为布尔值")
                        environment_enabled = change["enabled"]
                    continue
                if identity not in existing:
                    raise ValueError("密钥已不存在，请刷新后重试")
                if "label" in change:
                    existing[identity]["label"] = _label(change["label"])
                if "enabled" in change:
                    if type(change["enabled"]) is not bool:
                        raise ValueError("密钥启用选项必须为布尔值")
                    existing[identity]["enabled"] = change["enabled"]
            seen = {row["api_key"] for row in rows}
            for entry in add:
                if (not isinstance(entry, dict) or set(entry) - {"label", "api_key"}
                        or not _valid_key(entry.get("api_key"))):
                    raise ValueError("新增 API Key 格式不正确，请检查空格或换行")
                label = _label(entry.get("label", ""))
                key = entry["api_key"]
                if key in seen:
                    continue
                seen.add(key)
                rows.append({"id": uuid.uuid4().hex, "label": label or "密钥 " + str(len(rows) + 1),
                             "enabled": True, "api_key": key, "encrypted_api_key": ""})
            if len(rows) > MAX_KEYS:
                raise ValueError("密钥池最多保存 100 个密钥，请先移除不用的密钥")
            return self._commit(rows, self._enabled, environment_enabled)
