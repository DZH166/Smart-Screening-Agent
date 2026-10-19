"""Bounded key selection and live metadata around the unchanged AI protocol."""
from __future__ import annotations

import time
import copy

from .ai_client import ReviewError
from .ai_usage import empty_usage, merge_usage


class ManagedReviewClient:
    def __init__(self, manager, factory, job_id, *, sleeper=time.sleep, on_attempt=None):
        self.manager, self.factory, self.job_id = manager, factory, job_id
        self.sleep = sleeper
        self._legacy = None
        self.on_attempt = on_attempt

    def _emit(self, stage, row_id, **fields):
        self.manager.ai_debug.emit(stage, job_id=self.job_id, row_id=row_id, **fields)

    def _record(self, history, attempt, key_id, code, started, usage):
        from .ai_admin import ERROR_CODES, SAFE_ID
        safe_code = code if code == "ok" or code in ERROR_CODES else "review_unavailable"
        entry = {"attempt": attempt, "code": safe_code,
                 "elapsed_ms": min(1_000_000_000, max(0, int((time.monotonic()-started)*1000))),
                 "usage": merge_usage(empty_usage(), usage)}
        if not entry["usage"]["requests"]:
            entry["not_called"] = True
        if isinstance(key_id, str) and SAFE_ID.fullmatch(key_id) and not key_id.startswith("sk-"):
            entry["key_id"] = key_id
        history.append(entry)
        if self.on_attempt is not None:
            # A local diagnostic-write fault cannot turn a received/charged
            # response into an invented network failure and trigger a retry.
            try:
                self.on_attempt(copy.deepcopy(history))
            except Exception:
                pass

    @staticmethod
    def _error(code, message, usage, history):
        error = ReviewError(code, message, usage)
        error.attempt_history = copy.deepcopy(history)
        return error

    def review(self, content, *, row_id):
        runtime = self.manager.ai_settings.runtime()
        # Only a gateway deployment redirects transport; direct keys keep the
        # official origin, and factories that ignore the option stay compatible.
        endpoint = runtime.get("endpoint") if runtime.get("via_gateway") else None
        routed = {"endpoint": endpoint} if endpoint else {}
        # The gateway is a single credentialed hop, not a pool member: it keeps
        # the administrator key list empty on client machines.
        if "keys" not in runtime or runtime.get("via_gateway"):
            self._emit("requesting", row_id, attempt=1)
            started = time.monotonic()
            if self._legacy is None:
                self._legacy = self.factory(runtime["api_key"], **routed)
            history = []
            try:
                result = self._legacy.review(content)
            except ReviewError as error:
                self._record(history, 1, None, error.code, started, error.usage)
                raise self._error(error.code, error.message, error.usage, history) from None
            self._record(history, 1, None, "ok", started, result.get("usage") or empty_usage())
            self._emit("returned", row_id, elapsed_ms=int((time.monotonic()-started)*1000),
                       model=result.get("model"), verdict=result.get("decision", {}).get("verdict"),
                       usage=result.get("usage"))
            return {**result, "attempt_history": history}
        from .ai_key_pool import KeyPoolUnavailable
        usage = empty_usage()
        excluded = set()
        retry_key = None
        last_error = None
        history = []
        for attempt in (1, 2):
            try:
                omit = set(excluded)
                if retry_key is not None:
                    # Retry a transient network/provider failure on the same
                    # still-enabled credential; do not fan it across accounts.
                    omit.update(item["id"] for item in self.manager.ai_settings.runtime()["keys"]
                                if item["id"] != retry_key)
                credential = self.manager.ai_key_pool.acquire(exclude_ids=omit)
            except KeyPoolUnavailable as error:
                self._emit("pool_unavailable", row_id, error_code=error.code)
                if last_error is not None:
                    raise self._error(last_error.code, last_error.message, usage, history) from None
                raise self._error(error.code, "没有可用的 DeepSeek Key，请在管理员分区检查。", usage, history) from None
            key_id = credential["id"]
            self._emit("requesting", row_id, key_id=key_id, attempt=attempt,
                       image_count=sum(item.get("type") == "image_url" for item in content))
            started = time.monotonic()
            dispatched = False
            try:
                client = self.factory(credential["api_key"], **routed)
                # The old budget was two attempts. Pool rotation shares that
                # budget instead of multiplying retries by key count.
                client.attempts = 1
                if not self.manager.ai_key_pool.validate_credential(key_id, credential["api_key"]):
                    raise ReviewError("pool_unavailable", "Key 已停用或正在冷却，本项未发送请求。")
                dispatched = True
                result = client.review(content)
            except ReviewError as error:
                merge_usage(usage, error.usage)
                if error.usage.get("requests", 0):
                    self.manager.ai_key_pool.report(key_id, code=error.code, usage=error.usage)
                self._record(history, attempt, key_id, error.code, started, error.usage)
                self._emit("failed", row_id, key_id=key_id, attempt=attempt, error_code=error.code,
                           elapsed_ms=int((time.monotonic()-started)*1000), usage=error.usage)
                last_error = error
                if attempt == 2 or error.code not in {
                        "authentication", "insufficient_balance", "network_error", "provider_error"}:
                    # In particular 429 ends this case. Account-level limits
                    # cannot be bypassed by immediately trying another key.
                    raise self._error(error.code, error.message, usage, history) from None
                if error.code in {"authentication", "insufficient_balance"}:
                    excluded.add(key_id)
                    retry_key = None
                else:
                    retry_key = key_id
                self._emit("retrying", row_id, key_id=key_id, attempt=attempt+1, error_code=error.code)
                self.sleep(.5)
                continue
            except Exception:
                unknown = empty_usage()
                unknown.update(requests=int(dispatched), failures=int(dispatched),
                               unknown_usage_requests=int(dispatched))
                merge_usage(usage, unknown)
                if dispatched:
                    self.manager.ai_key_pool.report(key_id, code="review_unavailable", usage=unknown)
                self._record(history, attempt, key_id, "review_unavailable", started, unknown)
                self._emit("failed", row_id, key_id=key_id, attempt=attempt, error_code="review_unavailable", usage=unknown)
                raise self._error("review_unavailable", "本次复核未完成，请人工确认。", usage, history) from None
            merge_usage(usage, result["usage"])
            self.manager.ai_key_pool.report(key_id, code="ok", usage=result["usage"])
            self._record(history, attempt, key_id, "ok", started, result["usage"])
            self._emit("returned", row_id, key_id=key_id, attempt=attempt,
                       elapsed_ms=int((time.monotonic()-started)*1000), model=result.get("model"),
                       verdict=result.get("decision", {}).get("verdict"), usage=result["usage"])
            return {**result, "usage": usage, "attempt_history": history}
        raise AssertionError("unreachable")
