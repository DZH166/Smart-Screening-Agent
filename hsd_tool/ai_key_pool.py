"""Process-local, thread-safe random credential selection and safe diagnostics.

This pool does not increase concurrency or request budgets. A caller must enforce
the provider's account limits and the existing per-case retry budget.
"""
from __future__ import annotations

import hashlib
import math
import secrets
import threading
import time

from .ai_usage import COUNTERS, _nonnegative_number, empty_usage, merge_usage


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
        self._usage = empty_usage()
        self._cooldown_until = 0

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
        """Choose uniformly from usable keys, or raise a safe exception.

        Each acquisition is independent; consecutive calls may select one key.
        Authentication/balance suspension persists until explicit disable/enable,
        credential replacement, or process restart. No background retry enables it.
        """
        with self._lock:
            runtime, keys = self._current()
            if not keys:
                raise KeyPoolUnavailable("not_configured")
            if not runtime.get("enabled"):
                raise KeyPoolUnavailable("pool_unavailable")
            if self._cooldown_until > self._clock():
                # Keys can share an account. A 429 must not make another case
                # immediately rotate to a different key and evade its limit.
                raise KeyPoolUnavailable("pool_unavailable")
            excluded = set(exclude_ids)
            now = self._clock()
            available = []
            for row in keys:
                state = self._states[row["id"]]
                if (row["enabled"] and row["id"] not in excluded and not state["paused"]
                        and state["cooldown_until"] <= now):
                    available.append(row)
            if not available:
                raise KeyPoolUnavailable("pool_unavailable")
            row = secrets.choice(available)
            return {name: row[name] for name in ("id", "label", "api_key")}

    def report(self, key_id, *, code="ok", usage=None):
        """Record one completed attempt; never retain raw provider messages."""
        with self._lock:
            self._current()
            state = self._states.get(key_id)
            known_codes = {"ok", "authentication", "insufficient_balance", "rate_limit",
                           "network_error", "provider_error", "invalid_response",
                           "invalid_decision", "invalid_request", "unsupported_vision"}
            safe_code = code if isinstance(code, str) and code in known_codes else "request_failed"
            if state is not None:
                state["last_code"] = safe_code
                if safe_code in {"authentication", "insufficient_balance"}:
                    state["paused"] = safe_code
                elif safe_code == "rate_limit":
                    state["cooldown_until"] = max(state["cooldown_until"], self._clock() + 60)
            if safe_code == "rate_limit":
                self._cooldown_until = max(self._cooldown_until, self._clock() + 60)
            known_usage = (isinstance(usage, dict)
                           and all(type(usage.get(name)) is int and usage[name] >= 0 for name in COUNTERS)
                           and _nonnegative_number(usage.get("estimated_usd"))
                           and type(usage.get("cost_incomplete")) is bool)
            if known_usage:
                incoming = usage
            else:
                incoming = empty_usage()
                incoming.update(requests=1, successes=int(safe_code == "ok"),
                                failures=int(safe_code != "ok"), unknown_usage_requests=1,
                                cost_incomplete=True, estimated_usd_upper_bound=None)
            # Removed credentials are never resurrected. Their completed and
            # potentially charged requests still belong to process-wide totals.
            if state is not None:
                merge_usage(state["usage"], incoming)
            merge_usage(self._usage, incoming)

    def validate_credential(self, key_id, api_key):
        """Recheck an admitted private credential immediately before dispatch.

        Constructing a client must not let a disabled credential or an account
        cooldown turn into a later HTTP request from a stale local snapshot.
        """
        with self._lock:
            runtime, keys = self._current()
            now = self._clock()
            if not runtime.get("enabled") or self._cooldown_until > now:
                return False
            for row in keys:
                if row["id"] == key_id:
                    state = self._states[key_id]
                    return (row["api_key"] == api_key and row["enabled"] and not state["paused"]
                            and state["cooldown_until"] <= now)
            return False

    def snapshot(self):
        with self._lock:
            runtime, keys = self._current()
            now = self._clock()
            rows = []
            for row in keys:
                state = self._states[row["id"]]
                retry_after = max(0, math.ceil(max(state["cooldown_until"], self._cooldown_until) - now))
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
                    "cooldown_seconds": max(0, math.ceil(self._cooldown_until - now)),
                    "currency": "USD", "cost_basis": "estimated_peak_upper_bound"}
