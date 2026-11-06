"""Stable, instance-bound signing for the cloud browser session only.

The encryption master key is never used directly as a Flask signing key. Normal
single-worker restarts may preserve a still-valid session; changing the machine
key, deployment identity or primary credentials invalidates its signature.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path

from .credential_store import _absolute_path, _private_directory, _read_private


_ERROR = "服务器登录凭据不可用，请检查专用主密钥及配置；未启用临时登录凭据。"
_SIGNING_DOMAIN = b"HSD cloud browser session signing; version=1\x00"
_COOKIE_DOMAIN = b"HSD cloud browser cookie namespace; version=1\x00"


def _read_signing_seed(key_file):
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
        raise ValueError(_ERROR)
    try:
        path = _absolute_path(key_file)
        with _private_directory(path.parent) as directory:
            value = _read_private(directory, path.name, 32)
        if len(value) != 32:
            raise ValueError(_ERROR)
        return value
    except (OSError, TypeError, ValueError):
        raise ValueError(_ERROR) from None


def cloud_session_config(*, key_file, origin, data_dir, settings_dir,
                         employee_code, admin_credentials):
    """Return only the cloud SECRET_KEY and stable cookie namespace.

    Call after CloudAccess and CloudAdminCredentials have validated their
    configuration, before creating application managers. Code-pool edits retain
    the existing eight-hour session policy; replacing primary credentials does
    not. There is deliberately no generated or plaintext-file fallback.
    """
    try:
        seed = _read_signing_seed(key_file)
        if not isinstance(seed, bytes) or len(seed) != 32:
            raise ValueError(_ERROR)
        data, settings = Path(data_dir), Path(settings_dir)
        if not data.is_absolute() or not settings.is_absolute():
            raise ValueError(_ERROR)
        if not isinstance(origin, str) or not origin.startswith("https://"):
            raise ValueError(_ERROR)
        if not isinstance(employee_code, str) or not employee_code:
            raise ValueError(_ERROR)
        admin_generation = admin_credentials.session_fingerprint()
        if not isinstance(admin_generation, bytes) or len(admin_generation) != 32:
            raise ValueError(_ERROR)
        deployment = json.dumps({
            "origin": origin, "data": str(data.resolve()),
            "settings": str(settings.resolve()),
        }, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("ascii")
        authority = json.dumps({
            "deployment": deployment.decode("ascii"),
            "employee": hashlib.sha256(employee_code.encode("ascii")).hexdigest(),
            "admin": admin_generation.hex(),
        }, sort_keys=True, separators=(",", ":")).encode("ascii")
        return {
            "SECRET_KEY": hmac.digest(seed, _SIGNING_DOMAIN + authority, "sha256"),
            "SESSION_COOKIE_NAME": "hsd_cloud_" + hashlib.sha256(
                _COOKIE_DOMAIN + deployment).hexdigest()[:24],
        }
    except (OSError, AttributeError, TypeError, ValueError, UnicodeError):
        raise ValueError(_ERROR) from None
