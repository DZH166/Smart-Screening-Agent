"""Process-local, thread-safe credential rotation and sanitized diagnostics.

This pool does not increase concurrency or request budgets. A caller must enforce
the provider's account limits and the existing per-case retry budget.
"""
from __future__ import annotations

import hashlib
import math
import threading
import time

from .ai_usage import COUNTERS, empty_usage, merge_usage


class KeyPoolUnavailable(ValueError):
    def __init__(self, code):
        self.code = code
        message = ("尚未配置 DeepSeek API Key" if code == "not_configured"
                   else "暂无可用密钥，请检查启用状态、余额或稍后重试")
        super().__init__(message)


class ApiKeyPool:
    """Read current settings on every acquisition; never expose credentials."""

    def __init__(self, settings, *, clock=time.monotonic):
        self.settings = settings
        self._clock = clock
        self._lock = threading.RLock()
        self._states = {}
        self._last_id = None
        self._usage = empty_usage()

    def _current(self):
        runtime = self.settings.runtime()
        keys = runtime.get("keys", [])
        # A small compatibility path for integrations which supply only the
        # original single-key runtime contract.
        if "keys" not in runtime and runtime.get("api_key"):
            keys = [{"id": "legacy", "label": "原有密钥", "enabled": True,
                     "source": "saved", "api_key": runtime["api_key"]}]
        current = {}
        for row in keys:
            identity = row["id"]
            fingerprint = hashlib.sha256(row["api_key"].encode("ascii")).digest()
            state = self._states.get(identity)
            if state is None or state["_fingerprint"] != fingerprint:
                state = {"_fingerprint": fingerprint, "paused": "", "cooldown_until": 0,
                         "last_code": "", "usage": empty_usage(), "_enabled": row["enabled"]}
                self._states[identity] = state
            elif state["_enabled"] is False and row["enabled"] is True:
                # Explicit administrator action, never an elapsed-time retry.
                state["paused"] = ""
            state["_enabled"] = row["enabled"]
            current[identity] = row
        for identity in list(self._states):
            if identity not in current:
                del self._states[identity]
        return runtime, keys

    def acquire(self, exclude_ids=()):
        """Return a private credential, or a safe and actionable exception.

        Authentication/balance suspension persists until explicit disable/enable,
        credential replacement, or process restart. No background retry enables it.
        """
        with self._lock:
            runtime, keys = self._current()
            if not keys:
                raise KeyPoolUnavailable("not_configured")
            if not runtime.get("enabled"):
                raise KeyPoolUnavailable("pool_unavailable")
            excluded = set(exclude_ids)
            identities = [row["id"] for row in keys]
            start = ((identities.index(self._last_id) + 1) % len(keys)
                     if self._last_id in identities else 0)
            now = self._clock()
            for offset in range(len(keys)):
                row = keys[(start + offset) % len(keys)]
                state = self._states[row["id"]]
                if (row["enabled"] and row["id"] not in excluded and not state["paused"]
                        and state["cooldown_until"] <= now):
                    self._last_id = row["id"]
                    return {name: row[name] for name in ("id", "label", "api_key")}
            raise KeyPoolUnavailable("pool_unavailable")

    def report(self, key_id, *, code="ok", usage=None):
        """Record one completed attempt; never retain raw provider messages."""
        with self._lock:
            self._current()
            state = self._states.get(key_id)
            if state is None:
                return  # An administrator removed it while a request was active.
            known_codes = {"ok", "authentication", "insufficient_balance", "rate_limit",
                           "network_error", "provider_error", "invalid_response",
                           "invalid_decision", "invalid_request", "unsupported_vision"}
            safe_code = code if isinstance(code, str) and code in known_codes else "request_failed"
            state["last_code"] = safe_code
            if safe_code in {"authentication", "insufficient_balance"}:
                state["paused"] = safe_code
            elif safe_code == "rate_limit":
                state["cooldown_until"] = max(state["cooldown_until"], self._clock() + 60)
            known_usage = (isinstance(usage, dict)
                           and all(type(usage.get(name)) is int and usage[name] >= 0 for name in COUNTERS)
                           and type(usage.get("estimated_usd")) in (float, int)
                           and math.isfinite(usage["estimated_usd"]) and usage["estimated_usd"] >= 0
                           and type(usage.get("cost_incomplete")) is bool)
            if known_usage:
                # Keep only the existing ledger's allowlisted numeric fields.
                merge_usage(state["usage"], usage)
                merge_usage(self._usage, usage)
            else:
                unknown = empty_usage()
                unknown.update(requests=1, successes=int(safe_code == "ok"),
                               failures=int(safe_code != "ok"), unknown_usage_requests=1,
                               cost_incomplete=True, estimated_usd_upper_bound=None)
                merge_usage(state["usage"], unknown)
                merge_usage(self._usage, unknown)

    def snapshot(self):
        with self._lock:
            runtime, keys = self._current()
            now = self._clock()
            rows = []
            for row in keys:
                state = self._states[row["id"]]
                retry_after = max(0, math.ceil(state["cooldown_until"] - now))
                if not row["enabled"]:
                    status = "disabled"
                elif state["paused"]:
                    status = "paused_" + state["paused"]
                elif retry_after:
                    status = "cooldown"
                elif not runtime.get("enabled"):
                    status = "service_disabled"
                else:
                    status = "available"
                usage = dict(state["usage"])
                rows.append({"id": row["id"], "label": row["label"],
                             "enabled": row["enabled"], "source": row.get("source", "saved"),
                             "status": status, "retry_after_seconds": retry_after,
                             "cooldown_seconds": retry_after,
                             "last_code": state["last_code"], "usage": usage,
                             **{name: usage[name] for name in ("requests", "successes", "failures",
                                 "unknown_usage_requests", "estimated_usd", "estimated_usd_upper_bound")}})
            return {"enabled": bool(runtime.get("enabled")), "configured": bool(keys),
                    "key_revision": runtime.get("key_revision", 0), "key_count": len(keys),
                    "keys": rows, "usage": dict(self._usage), "scope": "current_process",
                    "currency": "USD", "cost_basis": "estimated_peak_upper_bound"}
