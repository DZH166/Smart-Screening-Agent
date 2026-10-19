"""Local DeepSeek configuration; API credentials never enter public snapshots.

Windows persists credentials with DPAPI CurrentUser. Other platforms retain a
new key in memory only rather than silently falling back to plaintext storage.
"""
from __future__ import annotations

import base64
import ctypes
import ipaddress
import json
import os
import sys
import tempfile
import threading
import urllib.parse
from pathlib import Path

MODEL = "deepseek-flash"
OFFICIAL_ENDPOINT = "https://api.deepseek.com/chat/completions"
GATEWAY_CONFIG = "gateway.json"
PRICE_DATE = "2026-10-15"
PRICES = {"cache_hit_usd_per_million": 0.006,
          "cache_miss_usd_per_million": 0.3,
          "output_usd_per_million": 1.2}


def _valid_key(value) -> bool:
    return (isinstance(value, str) and 10 <= len(value) <= 512
            and value.isascii() and all(33 <= ord(character) <= 126 for character in value))


def _private_host(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return address.is_loopback or address.is_private


def _valid_endpoint(value) -> bool:
    """The public origin must stay https; an internal gateway may be http."""
    if not isinstance(value, str) or not 12 <= len(value) <= 300 or not value.isascii():
        return False
    try:
        parsed = urllib.parse.urlsplit(value)
    except ValueError:
        return False
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        return False
    return parsed.scheme == "https" or _private_host(parsed.hostname)


def _gateway_config_path() -> Path | None:
    """Only a frozen build looks beside the executable; source trees never do."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent / GATEWAY_CONFIG
    return None


def load_gateway(environ=None, path=None) -> dict:
    """Resolve the optional internal AI gateway; the environment wins over the file."""
    source = os.environ if environ is None else environ
    endpoint = str(source.get("HSD_AI_GATEWAY", "") or "").strip()
    token = str(source.get("HSD_AI_GATEWAY_TOKEN", "") or "").strip()
    if not endpoint:
        target = Path(path) if path is not None else _gateway_config_path()
        if target is not None and target.is_file():
            try:
                if target.stat().st_size <= 8192:
                    payload = json.loads(target.read_text("utf-8"))
                    if isinstance(payload, dict):
                        endpoint = str(payload.get("endpoint", "") or "").strip()
                        token = token or str(payload.get("token", "") or "").strip()
            except (OSError, ValueError, TypeError):
                endpoint = token = ""
    if not _valid_endpoint(endpoint) or not _valid_key(token):
        return {}
    return {"endpoint": endpoint, "token": token}


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
    def __init__(self, data_dir: str | Path, *, protector=_DEFAULT, environ=None, gateway=None):
        self.path = Path(data_dir) / "ai_settings.json"
        self._protector = (_DPAPI() if os.name == "nt" else None) if protector is _DEFAULT else protector
        self._environ = os.environ if environ is None else environ
        self._gateway = load_gateway(self._environ) if gateway is None else dict(gateway or {})
        self._lock = threading.RLock()
        self._enabled = False
        self._key = ""
        self._encrypted_key = ""
        self._storage_warning = ""
        self._load()

    def _load(self):
        try:
            if not self.path.exists():
                # A machine deployed with a gateway has no local key to enter.
                self._enabled = bool(self._gateway)
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

    def _effective(self):
        """A locally saved key always wins; otherwise an internal gateway is used."""
        if self._key:
            return self._key, "saved", None
        environment_key = self._environ.get("DEEPSEEK_API_KEY", "")
        if _valid_key(environment_key):
            return environment_key, "environment", None
        if self._gateway:
            return self._gateway["token"], "gateway", self._gateway["endpoint"]
        return "", "none", None

    def snapshot(self) -> dict:
        with self._lock:
            key, source, endpoint = self._effective()
            persistence = "gateway" if endpoint else (
                "windows_dpapi" if self._protector is not None else "session_only")
            return {"enabled": self._enabled, "configured": bool(key), "model": MODEL,
                    "mode": "evaluation", "key_source": source, "via_gateway": bool(endpoint),
                    "key_persistence": persistence, "price_date": PRICE_DATE,
                    "prices": dict(PRICES), "price_basis": "peak_upper_bound",
                    "storage_warning": self._storage_warning}

    def runtime(self) -> dict:
        """Private process-only values. Never serialize this return value to a client."""
        with self._lock:
            key, _, endpoint = self._effective()
            return {"enabled": self._enabled, "api_key": key, "model": MODEL,
                    "endpoint": endpoint or OFFICIAL_ENDPOINT, "via_gateway": bool(endpoint),
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
