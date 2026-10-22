"""Private employee access-code registry, separate from administrator access.

One random store salt permits a single expensive derivation per login, followed
by constant-time comparisons against the configured and saved codes. Neither
codes nor their suffixes are returned by public snapshots. This store follows
the service's single-worker requirement; instances in that worker share a lock.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import stat
import threading

from .credential_store import _private_directory, _private_stat, _read_private


MIN_ITERATIONS = 600_000
MAX_ITERATIONS = 2_000_000
MAX_CODES = 100
MAX_CODE_LENGTH = 64
MAX_LABEL_LENGTH = 40
MAX_STORE_BYTES = 64 * 1024
_ERROR = "员工访问码设置的读取或保存结果未能确认，请刷新核对；仍失败请联系管理员检查。"
_FORMAT_ERROR = "访问码设置格式不正确，请刷新后重试。"
_LOCKS: dict[str, threading.RLock] = {}
_LOCKS_LOCK = threading.Lock()


class AccessCodesConflict(ValueError):
    code = "revision_conflict"


def _valid_code(value, minimum):
    return (isinstance(value, str) and minimum <= len(value) <= MAX_CODE_LENGTH
            and all(33 <= ord(character) <= 126 for character in value))


def _valid_label(value):
    return (isinstance(value, str) and len(value) <= MAX_LABEL_LENGTH
            and all(character.isprintable() and not 0xD800 <= ord(character) <= 0xDFFF
                    for character in value))


def _json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(_ERROR)
        result[key] = value
    return result


class AccessCodeStore:
    def __init__(self, directory, *, min_length=1, bootstrap_code=None):
        if type(min_length) is not int or not 1 <= min_length <= MAX_CODE_LENGTH:
            raise ValueError("员工访问码长度设置不正确。")
        if bootstrap_code is not None and not _valid_code(bootstrap_code, min_length):
            raise ValueError("原有员工访问码格式不正确，请检查运行设置。")
        try:
            self.path = Path(directory).absolute() / "access_codes.json"
            if ".." in self.path.parts:
                raise ValueError(_ERROR)
            key = os.path.normcase(str(self.path))
        except (TypeError, ValueError, OSError):
            raise ValueError(_ERROR) from None
        with _LOCKS_LOCK:
            self._lock = _LOCKS.setdefault(key, threading.RLock())
        self.min_length = min_length
        self._record = None
        self._configured_digest = None
        try:
            with self._lock:
                content = self._read(create=True)
                if content is None:
                    record = {"version": 1, "revision": 0,
                              "salt_hex": secrets.token_bytes(32).hex(),
                              "iterations": MIN_ITERATIONS, "codes": []}
                    self._write(record, initial=True)
                    content = self._read()
                self._record = self._parse(content)
                if bootstrap_code is not None:
                    self._configured_digest = self._derive(bootstrap_code, self._record)
        except Exception:
            raise ValueError(_ERROR) from None

    def _create_directory(self):
        if os.name == "posix":
            # Open each parent without following links, creating only missing
            # directories. Existing ancestors may belong to root; the dedicated
            # final settings directory must belong to the service and be 0700.
            descriptor = None
            flags = (getattr(os, "O_PATH", os.O_RDONLY) | os.O_DIRECTORY
                     | os.O_NOFOLLOW | os.O_CLOEXEC)
            try:
                descriptor = os.open(self.path.anchor, flags)
                for part in self.path.parent.parts[1:]:
                    try:
                        child = os.open(part, flags, dir_fd=descriptor)
                    except FileNotFoundError:
                        try:
                            os.mkdir(part, mode=0o700, dir_fd=descriptor)
                        except FileExistsError:
                            pass
                        child = os.open(part, flags, dir_fd=descriptor)
                    os.close(descriptor)
                    descriptor = child
                _private_stat(os.fstat(descriptor), directory=True)
            finally:
                if descriptor is not None:
                    os.close(descriptor)
        else:
            self._local_directory()
            self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            self._local_directory()

    def _local_directory(self):
        for part in (*reversed(self.path.parent.parents), self.path.parent):
            try:
                info = part.lstat()
            except FileNotFoundError:
                continue
            if (not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode)
                    or getattr(info, "st_file_attributes", 0) & 0x400):
                raise ValueError(_ERROR)

    @contextmanager
    def _directory(self, *, create=False):
        if create:
            self._create_directory()
        if os.name == "posix":
            with _private_directory(self.path.parent) as descriptor:
                yield descriptor
        else:
            self._local_directory()
            if not self.path.parent.is_dir():
                raise ValueError(_ERROR)
            yield None

    def _file_stat(self, directory):
        try:
            info = (os.stat(self.path.name, dir_fd=directory, follow_symlinks=False)
                    if directory is not None else self.path.lstat())
        except FileNotFoundError:
            return None
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or getattr(info, "st_file_attributes", 0) & 0x400):
            raise ValueError(_ERROR)
        if directory is not None:
            _private_stat(info, directory=False)
            if stat.S_IMODE(info.st_mode) != 0o600:
                raise ValueError(_ERROR)
        return info

    def _read(self, *, create=False):
        with self._directory(create=create) as directory:
            info = self._file_stat(directory)
            if info is None:
                return None
            if directory is not None:
                return _read_private(directory, self.path.name, MAX_STORE_BYTES)
            flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
            with os.fdopen(os.open(self.path, flags), "rb") as stream:
                opened = os.fstat(stream.fileno())
                if (opened.st_dev != info.st_dev or opened.st_ino != info.st_ino
                        or not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1):
                    raise ValueError(_ERROR)
                content = stream.read(MAX_STORE_BYTES + 1)
            if len(content) > MAX_STORE_BYTES:
                raise ValueError(_ERROR)
            return content

    def _write(self, record, *, initial=False):
        content = json.dumps(record, ensure_ascii=False, allow_nan=False).encode("utf-8")
        if len(content) > MAX_STORE_BYTES:
            raise ValueError(_ERROR)
        temporary = ".access-codes-" + secrets.token_hex(16) + ".tmp"
        with self._directory() as directory:
            if self._file_stat(directory) is None and not initial:
                raise ValueError(_ERROR)
            destination = temporary if directory is not None else self.path.parent / temporary
            flags = (os.O_WRONLY | os.O_CREAT | os.O_EXCL
                     | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
                     | getattr(os, "O_BINARY", 0))
            try:
                descriptor = os.open(destination, flags, 0o600, dir_fd=directory)
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(content)
                    stream.flush()
                    os.fsync(stream.fileno())
                if self._file_stat(directory) is None and not initial:
                    raise ValueError(_ERROR)
                if directory is not None:
                    # Do not silently create an unrelated replacement when a
                    # parent is renamed while the descriptor is held open.
                    with _private_directory(self.path.parent) as current:
                        before, after = os.fstat(directory), os.fstat(current)
                        if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
                            raise ValueError(_ERROR)
                if initial:
                    # link+unlink installs a complete initial file without
                    # overwriting one created by another process at startup.
                    os.link(destination, self.path.name if directory is not None else self.path,
                            src_dir_fd=directory, dst_dir_fd=directory, follow_symlinks=False)
                    os.unlink(destination, dir_fd=directory)
                else:
                    os.replace(destination, self.path.name if directory is not None else self.path,
                               src_dir_fd=directory, dst_dir_fd=directory)
                if directory is not None:
                    os.fsync(directory)
            finally:
                try:
                    os.unlink(destination, dir_fd=directory)
                except FileNotFoundError:
                    pass

    def _parse(self, content):
        if content is None:
            raise ValueError(_ERROR)
        record = json.loads(content.decode("utf-8"), object_pairs_hook=_json_object)
        if (not isinstance(record, dict) or set(record) != {
                "version", "revision", "salt_hex", "iterations", "codes"}
                or type(record["version"]) is not int or record["version"] != 1
                or type(record["revision"]) is not int or record["revision"] < 0
                or not isinstance(record["salt_hex"], str)
                or not re.fullmatch(r"[0-9a-f]{64}", record["salt_hex"])
                or type(record["iterations"]) is not int
                or not MIN_ITERATIONS <= record["iterations"] <= MAX_ITERATIONS
                or not isinstance(record["codes"], list) or len(record["codes"]) > MAX_CODES):
            raise ValueError(_ERROR)
        ids, digests = set(), set()
        for entry in record["codes"]:
            if (not isinstance(entry, dict) or set(entry) != {"id", "label", "enabled", "digest_hex"}
                    or not isinstance(entry["id"], str) or not re.fullmatch(r"[0-9a-f]{32}", entry["id"])
                    or not _valid_label(entry["label"]) or not entry["label"].strip()
                    or type(entry["enabled"]) is not bool
                    or not isinstance(entry["digest_hex"], str)
                    or not re.fullmatch(r"[0-9a-f]{64}", entry["digest_hex"])
                    or entry["id"] in ids or entry["digest_hex"] in digests):
                raise ValueError(_ERROR)
            ids.add(entry["id"])
            digests.add(entry["digest_hex"])
        return record

    def _reload(self):
        try:
            record = self._parse(self._read())
            previous = self._record
            if previous is not None and (
                    record["salt_hex"] != previous["salt_hex"]
                    or record["iterations"] != previous["iterations"]
                    or record["revision"] < previous["revision"]
                    or record["revision"] == previous["revision"] and record != previous):
                raise ValueError(_ERROR)
            self._record = record
        except Exception:
            raise ValueError(_ERROR) from None

    @staticmethod
    def _derive(code, record):
        return hashlib.pbkdf2_hmac("sha256", code.encode("ascii"),
                                   bytes.fromhex(record["salt_hex"]), record["iterations"])

    def _snapshot(self):
        codes = ([{"id": "configured", "label": "原有访问码", "enabled": True,
                   "source": "configured"}] if self._configured_digest is not None else [])
        codes.extend({"id": entry["id"], "label": entry["label"],
                      "enabled": entry["enabled"], "source": "saved"}
                     for entry in self._record["codes"])
        return {"revision": self._record["revision"], "min_length": self.min_length,
                "max_length": MAX_CODE_LENGTH, "codes": codes}

    def snapshot(self):
        with self._lock:
            self._reload()
            return self._snapshot()

    def verify(self, supplied):
        if not _valid_code(supplied, self.min_length):
            return False
        with self._lock:
            try:
                self._reload()
                candidate = self._derive(supplied, self._record)
                valid = (hmac.compare_digest(candidate, self._configured_digest)
                         if self._configured_digest is not None else False)
                for entry in self._record["codes"]:
                    matches = hmac.compare_digest(candidate, bytes.fromhex(entry["digest_hex"]))
                    valid = bool(valid | (matches & entry["enabled"]))
                return valid
            except Exception:
                # No configured-code fallback after unreadable or corrupt data.
                return False

    def save(self, payload):
        if (not isinstance(payload, dict) or set(payload) - {"expected_revision", "add", "update", "remove"}
                or type(payload.get("expected_revision")) is not int or payload["expected_revision"] < 0):
            raise ValueError(_FORMAT_ERROR)
        adding, updating, removing = (payload.get(name, []) for name in ("add", "update", "remove"))
        if any(not isinstance(value, list) or len(value) > MAX_CODES for value in (adding, updating, removing)):
            raise ValueError(_FORMAT_ERROR)
        for entry in adding:
            if (not isinstance(entry, dict) or set(entry) - {"code", "label"}
                    or not _valid_code(entry.get("code"), self.min_length)):
                raise ValueError(f"访问码须为 {self.min_length}–64 位英文字母、数字或符号，不能有空格或换行。")
            if "label" in entry and (not _valid_label(entry["label"])
                                     or entry["code"] in entry["label"]):
                raise ValueError("备注最多 40 个字，不能包含访问码、换行或不可见字符。")
        for entry in updating:
            if (not isinstance(entry, dict) or set(entry) != {"id", "enabled"}
                    or not isinstance(entry["id"], str) or type(entry["enabled"]) is not bool):
                raise ValueError(_FORMAT_ERROR)
        if any(not isinstance(value, str) for value in removing):
            raise ValueError(_FORMAT_ERROR)
        changed_ids = [entry["id"] for entry in updating] + removing
        if len(changed_ids) != len(set(changed_ids)):
            raise ValueError("同一访问码不能重复修改或同时删除。")
        if "configured" in changed_ids:
            raise ValueError("原有访问码由运行设置管理，不能在此停用或删除。")
        with self._lock:
            self._reload()
            if payload["expected_revision"] != self._record["revision"]:
                raise AccessCodesConflict("访问码已在其他页面修改，请刷新后重试。")
            known = {entry["id"] for entry in self._record["codes"]}
            if set(changed_ids) - known:
                raise ValueError("找不到该访问码，请刷新后重试。")
            if len(self._record["codes"]) - len(removing) + len(adding) > MAX_CODES:
                raise ValueError("最多保存 100 个新增访问码，请先删除不再使用的访问码。")
            by_id = {entry["id"]: dict(entry) for entry in self._record["codes"]}
            digests = {entry["digest_hex"] for entry in self._record["codes"]}
            if self._configured_digest is not None:
                digests.add(self._configured_digest.hex())
            new_codes = []
            for entry in adding:
                digest = self._derive(entry["code"], self._record).hex()
                if digest in digests:
                    raise ValueError("访问码已存在（包括已停用的访问码），本次未新增。")
                digests.add(digest)
                identifier = secrets.token_hex(16)
                while identifier in known:
                    identifier = secrets.token_hex(16)
                known.add(identifier)
                new_codes.append({"id": identifier, "label": entry.get("label", "").strip() or "新增访问码",
                                  "enabled": True, "digest_hex": digest})
            for entry in updating:
                by_id[entry["id"]]["enabled"] = entry["enabled"]
            for identifier in removing:
                del by_id[identifier]
            codes = list(by_id.values()) + new_codes
            if len(codes) > MAX_CODES:
                raise ValueError("最多保存 100 个新增访问码，请先删除不再使用的访问码。")
            if codes == self._record["codes"]:
                return self._snapshot()
            record = dict(self._record, revision=self._record["revision"] + 1, codes=codes)
            try:
                self._write(record)
            except Exception:
                raise ValueError(_ERROR) from None
            self._record = record
            return self._snapshot()
