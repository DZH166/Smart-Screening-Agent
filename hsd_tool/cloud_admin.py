"""Explicit cloud administrator credentials, separate from the desktop account.

Only the salted PBKDF2 hash is stored in this service-private file. Provisioning
and password delivery are deployment responsibilities, never HTTP parameters or
application logs. A missing/unsafe file must abort cloud startup.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import stat

from .credential_store import _absolute_path, _private_directory, _read_private


_ERROR = "云端管理员凭据不可用，请检查专用凭据文件及权限；未启用默认管理员口令。"
MIN_ITERATIONS = 600_000
MAX_ITERATIONS = 2_000_000
MAX_CREDENTIAL_BYTES = 4096


def _read_admin_file(path):
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
        raise ValueError(_ERROR)
    try:
        target = _absolute_path(path)
        with _private_directory(target.parent) as directory:
            metadata = os.stat(target.name, dir_fd=directory, follow_symlinks=False)
            if stat.S_IMODE(metadata.st_mode) != 0o600:
                raise ValueError(_ERROR)
            return _read_private(directory, target.name, MAX_CREDENTIAL_BYTES)
    except (OSError, TypeError, ValueError):
        raise ValueError(_ERROR) from None


class CloudAdminCredentials:
    """Verify a private cloud account without falling back to desktop secrets."""

    def __init__(self, path):
        try:
            record = json.loads(_read_admin_file(path).decode("utf-8"))
            if not isinstance(record, dict) or set(record) != {"username", "salt_hex", "digest_hex", "iterations"}:
                raise ValueError(_ERROR)
            username, salt_hex, digest_hex, iterations = (
                record[name] for name in ("username", "salt_hex", "digest_hex", "iterations"))
            if (not isinstance(username, str) or not re.fullmatch(r"[A-Za-z0-9_.@-]{1,64}", username)
                    or not isinstance(salt_hex, str) or not re.fullmatch(r"[0-9a-f]{32,128}", salt_hex)
                    or len(salt_hex) % 2
                    or not isinstance(digest_hex, str) or not re.fullmatch(r"[0-9a-f]{64}", digest_hex)
                    or type(iterations) is not int or not MIN_ITERATIONS <= iterations <= MAX_ITERATIONS):
                raise ValueError(_ERROR)
            self._username_hash = hashlib.sha256(username.encode("ascii")).digest()
            self._salt = bytes.fromhex(salt_hex)
            self._digest = bytes.fromhex(digest_hex)
            self._iterations = iterations
        except (OSError, UnicodeError, ValueError, TypeError, KeyError):
            raise ValueError(_ERROR) from None

    def verify(self, username, password) -> bool:
        """Hash both values on valid-shaped attempts; never log or retain input."""
        if not isinstance(username, str) or not isinstance(password, str):
            return False
        if not 1 <= len(username) <= 128 or not 1 <= len(password) <= 256:
            return False
        try:
            name = hashlib.sha256(username.encode("utf-8")).digest()
            candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                                           self._salt, self._iterations)
            name_ok = hmac.compare_digest(name, self._username_hash)
            password_ok = hmac.compare_digest(candidate, self._digest)
            return name_ok and password_ok
        except (ValueError, UnicodeError):
            return False
