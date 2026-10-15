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


class AiSettings:
    def __init__(self, data_dir: str | Path, *, protector=_DEFAULT, environ=None):
        self.path = Path(data_dir) / "ai_settings.json"
        self._protector = (_DPAPI() if os.name == "nt" else None) if protector is _DEFAULT else protector
        self._environ = os.environ if environ is None else environ
        self._lock = threading.RLock()
        self._enabled = False
        self._key = ""
        self._encrypted_key = ""
        self._storage_warning = ""
        self._load()

    def _load(self):
        try:
            if not self.path.exists():
                return
            if self.path.stat().st_size > 65536:
                raise ValueError("oversized settings")
            payload = json.loads(self.path.read_text("utf-8"))
            if not isinstance(payload, dict) or payload.get("version") != 1:
                raise ValueError("invalid settings")
            self._enabled = payload.get("enabled") is True
            encrypted = payload.get("encrypted_api_key", "")
            if not encrypted:
                return
            if not isinstance(encrypted, str) or self._protector is None:
                raise ValueError("unsupported credential protection")
            raw = self._protector.decrypt(base64.b64decode(encrypted, validate=True)).decode("ascii")
            if not _valid_key(raw):
                raise ValueError("invalid credential")
            self._key, self._encrypted_key = raw, encrypted
        except (OSError, ValueError, TypeError, UnicodeError):
            self._storage_warning = "本机密钥无法读取，请重新填写；原密钥未回显。"
            self._enabled = False
            self._key = self._encrypted_key = ""

    def _effective_key(self):
        if self._key:
            return self._key, "saved"
        environment_key = self._environ.get("DEEPSEEK_API_KEY", "")
        if _valid_key(environment_key):
            return environment_key, "environment"
        return "", "none"

    def snapshot(self) -> dict:
        with self._lock:
            key, source = self._effective_key()
            persistence = "windows_dpapi" if self._protector is not None else "session_only"
            return {"enabled": self._enabled, "configured": bool(key), "model": MODEL,
                    "mode": "evaluation", "key_source": source,
                    "key_persistence": persistence, "price_date": PRICE_DATE,
                    "prices": dict(PRICES), "price_basis": "peak_upper_bound",
                    "storage_warning": self._storage_warning}

    def runtime(self) -> dict:
        """Private process-only values. Never serialize this return value to a client."""
        with self._lock:
            key, _ = self._effective_key()
            return {"enabled": self._enabled, "api_key": key, "model": MODEL,
                    "prices": dict(PRICES), "price_date": PRICE_DATE}

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
            key = "" if payload.get("clear_key") else supplied_key or self._key
            encrypted = "" if not key else self._encrypted_key
            if key and self._protector is not None and (supplied_key or not encrypted):
                try:
                    encrypted = base64.b64encode(self._protector.encrypt(key.encode("ascii"))).decode("ascii")
                except Exception:
                    raise ValueError("Windows 无法加密密钥，本次设置未保存") from None
            if self._protector is None:
                encrypted = ""
            enabled = payload.get("enabled", self._enabled)
            record = {"version": 1, "enabled": enabled, "model": MODEL,
                      "encrypted_api_key": encrypted}
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = None
            try:
                descriptor, temporary = tempfile.mkstemp(prefix=".ai-settings-", suffix=".tmp", dir=self.path.parent)
                with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                    json.dump(record, stream, ensure_ascii=False, allow_nan=False)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, self.path)
            except OSError:
                raise ValueError("无法保存本机 DeepSeek 设置，本次设置未生效") from None
            finally:
                if temporary and os.path.exists(temporary):
                    os.unlink(temporary)
            self._key, self._encrypted_key, self._enabled = key, encrypted, enabled
            self._storage_warning = ""
            return self.snapshot()
