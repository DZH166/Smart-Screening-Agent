"""Explicit Linux server credential storage; never a plaintext fallback.

The deployment creates a random 32-byte master key outside the application data
directory. This module only reads it. Keys, key paths and OS exception details
are never included in its public errors.
"""
from __future__ import annotations

from contextlib import contextmanager
import hmac
import json
import os
from pathlib import Path
import secrets
import stat


_ERROR = "服务器密钥存储不可用，请检查专用目录、权限及主密钥文件；未保存密钥。"
_MAGIC = b"HSD-AESGCM-1\x00"
_AAD = b"HSD DeepSeek credential; aes256gcm; version=1"


def _absolute_path(value):
    try:
        path = Path(value)
    except (TypeError, ValueError):
        raise ValueError(_ERROR) from None
    if not path.is_absolute() or ".." in path.parts or path.name in {"", ".", ".."}:
        raise ValueError(_ERROR)
    return path


def _private_stat(info, *, directory):
    """An unrelated Unix account must not read or replace these files."""
    mode = stat.S_IMODE(info.st_mode)
    correct_type = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
    if not correct_type or info.st_uid != os.geteuid() or mode & 0o077:
        raise ValueError(_ERROR)
    if directory:
        if mode != 0o700:
            raise ValueError(_ERROR)
    elif mode not in {0o400, 0o600} or info.st_nlink != 1:
        raise ValueError(_ERROR)


@contextmanager
def _private_directory(path):
    """Traverse with openat/O_NOFOLLOW so even ancestor symlinks are rejected."""
    path = _absolute_path(path)
    descriptor = None
    try:
        # Traversal requires search permission, not directory listing. Linux
        # O_PATH also supports a service-user's private directory below a
        # root-owned 0711 mount without weakening any ancestor permissions.
        flags = getattr(os, "O_PATH", os.O_RDONLY) | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
        descriptor = os.open(path.anchor, flags)
        for part in path.parts[1:]:
            child = os.open(part, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        # O_PATH descriptors cannot read files or fsync. Reopen the pinned
        # final directory, not its pathname, before private I/O and validation.
        child = os.open(".", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                        dir_fd=descriptor)
        os.close(descriptor)
        descriptor = child
        _private_stat(os.fstat(descriptor), directory=True)
        yield descriptor
    except (OSError, ValueError):
        raise ValueError(_ERROR) from None
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _read_private(directory, name, limit):
    descriptor = None
    try:
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK,
                             dir_fd=directory)
        _private_stat(os.fstat(descriptor), directory=False)
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = None
            value = stream.read(limit + 1)
        if len(value) > limit:
            raise ValueError(_ERROR)
        return value
    finally:
        if descriptor is not None:
            os.close(descriptor)


class LinuxCredentialStore:
    """AES-256-GCM plus private, symlink-resistant settings I/O on Linux.

    This is enabled only by an explicit master-key filename. The key is neither
    created nor rotated automatically; replacing it during a running process
    fails closed rather than silently writing an unreadable mixed-key pool.
    """

    persistence = "linux_aesgcm"

    def __init__(self, key_file, settings_file):
        if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
            raise ValueError("服务器文件加密仅适用于支持安全文件权限的 Linux 环境")
        self.key_file = _absolute_path(key_file)
        self.settings_file = _absolute_path(settings_file)
        if self.key_file.is_relative_to(self.settings_file.parent):
            raise ValueError("服务器主密钥必须与设置目录分开保存")
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        except ImportError:
            raise ValueError("服务器缺少加密依赖，请安装 requirements-cloud.txt") from None
        self._cipher_class = AESGCM
        self._key = self._read_key()
        with _private_directory(self.settings_file.parent):
            pass

    def _read_key(self):
        try:
            with _private_directory(self.key_file.parent) as directory:
                key = _read_private(directory, self.key_file.name, 32)
            if len(key) != 32:
                raise ValueError(_ERROR)
            return key
        except (OSError, ValueError):
            raise ValueError(_ERROR) from None

    def _cipher(self):
        if not hmac.compare_digest(self._read_key(), self._key):
            raise ValueError(_ERROR)
        return self._cipher_class(self._key)

    def encrypt(self, value):
        nonce = secrets.token_bytes(12)
        return _MAGIC + nonce + self._cipher().encrypt(nonce, value, _AAD)

    def decrypt(self, value):
        if not isinstance(value, bytes) or not value.startswith(_MAGIC) or len(value) < len(_MAGIC) + 28:
            raise ValueError(_ERROR)
        start = len(_MAGIC)
        try:
            return self._cipher().decrypt(value[start:start + 12], value[start + 12:], _AAD)
        except Exception:
            # InvalidTag and OS errors must not expose ciphertext, paths or keys.
            raise ValueError(_ERROR) from None

    def read_settings(self, limit):
        """Return None only for an absent file, never for unsafe permissions."""
        self._cipher()
        try:
            with _private_directory(self.settings_file.parent) as directory:
                try:
                    return _read_private(directory, self.settings_file.name, limit)
                except FileNotFoundError:
                    return None
        except (OSError, ValueError):
            raise ValueError(_ERROR) from None

    def write_settings(self, record):
        """Atomic replacement inside a verified private directory, mode 0600."""
        self._cipher()
        temporary = ".ai-settings-" + secrets.token_hex(16) + ".tmp"
        with _private_directory(self.settings_file.parent) as directory:
            try:
                # Reject existing symlinks/hardlinks/foreign files even though
                # replace itself would not follow them.
                try:
                    info = os.stat(self.settings_file.name, dir_fd=directory, follow_symlinks=False)
                except FileNotFoundError:
                    pass
                else:
                    _private_stat(info, directory=False)
                flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC
                descriptor = os.open(temporary, flags, 0o600, dir_fd=directory)
                with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                    json.dump(record, stream, ensure_ascii=False, allow_nan=False)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, self.settings_file.name,
                           src_dir_fd=directory, dst_dir_fd=directory)
                os.fsync(directory)
            except (OSError, ValueError):
                raise ValueError(_ERROR) from None
            finally:
                try:
                    os.unlink(temporary, dir_fd=directory)
                except FileNotFoundError:
                    pass
