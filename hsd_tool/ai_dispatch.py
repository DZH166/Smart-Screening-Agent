"""Bounded key selection and live metadata around the unchanged AI protocol."""
from __future__ import annotations

import time

from .ai_client import ReviewError
from .ai_usage import empty_usage, merge_usage


class ManagedReviewClient:
    def __init__(self, manager, factory, job_id, *, sleeper=time.sleep):
        self.manager, self.factory, self.job_id = manager, factory, job_id
        self.sleep = sleeper
        self._legacy = None

    def _emit(self, stage, row_id, **fields):
        self.manager.ai_debug.emit(stage, job_id=self.job_id, row_id=row_id, **fields)

    def review(self, content, *, row_id):
        runtime = self.manager.ai_settings.runtime()
        # Compatibility for old local evaluation harnesses that provide only a
        # single private runtime key. Production settings always provide keys.
        if "keys" not in runtime:
            self._emit("requesting", row_id, attempt=1)
            started = time.monotonic()
            if self._legacy is None:
                self._legacy = self.factory(runtime["api_key"])
            result = self._legacy.review(content)
            self._emit("returned", row_id, elapsed_ms=int((time.monotonic()-started)*1000),
                       model=result.get("model"), verdict=result.get("decision", {}).get("verdict"),
                       usage=result.get("usage"))
            return result
        from .ai_key_pool import KeyPoolUnavailable
        usage = empty_usage()
        excluded = set()
        retry_key = None
        last_error = None
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
                    raise ReviewError(last_error.code, last_error.message, usage) from None
                raise ReviewError(error.code, "没有可用的 DeepSeek Key，请在管理员分区检查。", usage) from None
            key_id = credential["id"]
            self._emit("requesting", row_id, key_id=key_id, attempt=attempt,
                       image_count=sum(item.get("type") == "image_url" for item in content))
            started = time.monotonic()
            try:
                client = self.factory(credential["api_key"])
                # The old budget was two attempts. Pool rotation shares that
                # budget instead of multiplying retries by key count.
                client.attempts = 1
                result = client.review(content)
            except ReviewError as error:
                merge_usage(usage, error.usage)
                self.manager.ai_key_pool.report(key_id, code=error.code, usage=error.usage)
                self._emit("failed", row_id, key_id=key_id, attempt=attempt, error_code=error.code,
                           elapsed_ms=int((time.monotonic()-started)*1000), usage=error.usage)
                last_error = error
                if attempt == 2 or error.code not in {
                        "authentication", "insufficient_balance", "network_error", "provider_error"}:
                    # In particular 429 ends this case. Account-level limits
                    # cannot be bypassed by immediately trying another key.
                    raise ReviewError(error.code, error.message, usage) from None
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
                unknown.update(requests=1, failures=1, unknown_usage_requests=1)
                merge_usage(usage, unknown)
                self.manager.ai_key_pool.report(key_id, code="review_unavailable", usage=unknown)
                self._emit("failed", row_id, key_id=key_id, attempt=attempt, error_code="review_unavailable", usage=unknown)
                raise ReviewError("review_unavailable", "本次复核未完成，请人工确认。", usage) from None
            merge_usage(usage, result["usage"])
            self.manager.ai_key_pool.report(key_id, code="ok", usage=result["usage"])
            self._emit("returned", row_id, key_id=key_id, attempt=attempt,
                       elapsed_ms=int((time.monotonic()-started)*1000), model=result.get("model"),
                       verdict=result.get("decision", {}).get("verdict"), usage=result["usage"])
            return {**result, "usage": usage}
        raise AssertionError("unreachable")
