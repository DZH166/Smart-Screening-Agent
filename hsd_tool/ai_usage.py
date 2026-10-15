"""Task and lifetime API usage; unknown charges never masquerade as zero cost."""
from __future__ import annotations

import json
import math
import os
import errno
from contextlib import contextmanager
from pathlib import Path
import tempfile
import threading
import time

COUNTERS = ("requests", "successes", "failures", "prompt_tokens", "completion_tokens",
            "cache_hit_tokens", "cache_miss_tokens", "unknown_usage_requests")


def _nonnegative_number(value):
    try:
        return type(value) in (int, float) and math.isfinite(value) and value >= 0
    except OverflowError:
        return False


def empty_usage():
    return {**dict.fromkeys(COUNTERS, 0), "estimated_usd": 0.0,
            "estimated_usd_upper_bound": 0.0, "cost_is_upper_bound": True,
            "cost_incomplete": False, "currency": "USD", "price_date": "2026-10-15"}


def merge_usage(target, incoming):
    for name in COUNTERS:
        value = incoming.get(name, 0)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            target[name] = target.get(name, 0) + value
    amount = incoming.get("estimated_usd", 0)
    if _nonnegative_number(amount):
        combined = target.get("estimated_usd", 0) + amount
        if _nonnegative_number(combined):
            target["estimated_usd"] = round(combined, 10)
        else:
            target["cost_incomplete"] = True
    target["cost_incomplete"] = bool(target.get("cost_incomplete") or incoming.get("cost_incomplete")
                                     or target["unknown_usage_requests"])
    target["estimated_usd_upper_bound"] = None if target["cost_incomplete"] else target["estimated_usd"]
    return target


class UsageLedger:
    def __init__(self, data_dir):
        self.path = Path(data_dir) / "ai_usage.json"
        self.lock_path = self.path.with_suffix(".lock")
        self.lock = threading.RLock()
        self.values = empty_usage()
        self._disk_values = empty_usage()
        self._pending = empty_usage()
        self._seen_disk = False
        self._history_incomplete = False
        self._persistence_warning = ""
        self._read_warning = ""
        self._refresh_failed = False
        self.warning = ""
        self._refresh()

    @contextmanager
    def _file_lock(self):
        """Lock a stable sidecar, not the JSON inode replaced on each save."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+b") as stream:
            stream.seek(0, os.SEEK_END)
            if stream.tell() == 0:
                stream.write(b"\0")
                stream.flush()
            deadline = time.monotonic() + 2
            while True:
                try:
                    stream.seek(0)
                    if os.name == "nt":
                        import msvcrt
                        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError as error:
                    if error.errno not in {errno.EACCES, errno.EAGAIN, errno.EDEADLK} or time.monotonic() >= deadline:
                        raise
                    time.sleep(.01)
            try:
                yield
            finally:
                stream.seek(0)
                try:
                    if os.name == "nt":
                        import msvcrt
                        msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
                except OSError:
                    pass  # Closing the descriptor also releases its lock.

    def _read_disk(self):
        if self.path.stat().st_size > 32768:
            raise ValueError("invalid ledger")
        record = json.loads(self.path.read_text("utf-8"))
        if (not isinstance(record, dict) or not set(COUNTERS) <= set(record)
                or any(type(record[name]) is not int or record[name] < 0 for name in COUNTERS)
                or not _nonnegative_number(record.get("estimated_usd"))
                or type(record.get("cost_incomplete")) is not bool
                or "history_incomplete" in record and type(record["history_incomplete"]) is not bool):
            raise ValueError("invalid ledger")
        values = empty_usage()
        merge_usage(values, record)
        values["history_incomplete"] = record.get("history_incomplete", False)
        if values["history_incomplete"]:
            values.update(cost_incomplete=True, estimated_usd_upper_bound=None)
        return values

    def _publish(self):
        self.values = dict(self._disk_values)
        merge_usage(self.values, self._pending)
        self.values["history_incomplete"] = self._history_incomplete
        if self._history_incomplete or self._refresh_failed:
            self.values.update(cost_incomplete=True, estimated_usd_upper_bound=None)
        history_warning = "历史用量无法读取；以下仅统计本次运行及仍可保留的已知用量，用量可能不完整。" if self._history_incomplete else ""
        self.warning = " ".join(value for value in (history_warning, self._persistence_warning, self._read_warning) if value)

    def _refresh_locked(self):
        try:
            values = self._read_disk()
            # A counter rollback means historical data was removed/replaced.
            # Preserve known lower bounds and flag the loss explicitly.
            if self._seen_disk and (any(values[name] < self._disk_values[name] for name in COUNTERS)
                                    or values["estimated_usd"] < self._disk_values["estimated_usd"]):
                self._history_incomplete = True
                for name in COUNTERS:
                    values[name] = max(values[name], self._disk_values[name])
                values["estimated_usd"] = max(values["estimated_usd"], self._disk_values["estimated_usd"])
            self._disk_values = values
            self._seen_disk = True
            self._history_incomplete = self._history_incomplete or values["history_incomplete"]
        except FileNotFoundError:
            if self._seen_disk:
                self._history_incomplete = True
        except (OSError, ValueError, TypeError):
            self._history_incomplete = True
        self._publish()

    def _write_locked(self):
        descriptor, temporary = tempfile.mkstemp(prefix=".ai-usage-", suffix=".tmp", dir=self.path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(self.values, stream, allow_nan=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
            except OSError:
                pass

    def add(self, usage):
        with self.lock:
            if not isinstance(usage, dict):
                self._persistence_warning = "本次用量格式异常，统计可能不完整。"
                self._publish()
                return
            # Unsaved increments remain separate so refreshing another process's
            # contribution cannot discard or double-count a failed local save.
            merge_usage(self._pending, usage)
            try:
                with self._file_lock():
                    self._read_warning = ""
                    self._refresh_failed = False
                    self._refresh_locked()
                    self._write_locked()
                    self._disk_values = dict(self.values)
                    self._pending = empty_usage()
                    self._seen_disk = True
                    self._persistence_warning = ""
                    self._publish()
            except OSError:
                self._persistence_warning = "用量未能保存，已保留本次内存记录；退出后未保存统计可能丢失。"
                self._publish()

    def snapshot(self):
        with self.lock:
            self._refresh()
            return {**self.values, "warning": self.warning}

    def _refresh(self):
        with self.lock:
            try:
                with self._file_lock():
                    self._read_warning = ""
                    self._refresh_failed = False
                    self._refresh_locked()
            except OSError:
                self._read_warning = "历史用量暂不可读；已保留内存已知用量，统计可能不完整。"
                self._refresh_failed = True
                self._publish()
