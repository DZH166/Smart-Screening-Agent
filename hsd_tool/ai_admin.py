"""Bounded, metadata-only live diagnostics for the host administrator.

Never retain provider bodies, images, prompt text, paths or exception messages.
This is operational telemetry, not model reasoning or qualification evidence.
"""
from __future__ import annotations

from collections import deque
import copy
from datetime import datetime, timezone
import re
import threading
import time
import uuid

STAGES = {
    "run_started": "开始本批 AI 复核", "run_finished": "本批 AI 复核结束",
    "disabled": "AI 未启用或尚未配置可用 Key", "no_cases": "没有符合条件的疑难项",
    "ineligible": "本项不符合 AI 复核条件", "preparing": "检查原件并准备预览",
    "requesting": "正在等待 DeepSeek 返回", "retrying": "等待后重试请求",
    "returned": "已收到并检查结构化结果", "verifying": "重新校验原件与放行条件",
    "manual": "本项保留人工确认", "auto": "本项通过全部限定条件",
    "failed": "本次复核未完成，保留人工处理", "skipped": "接口不可用，本项未调用",
    "pool_unavailable": "没有可用 Key，请检查配置或等待冷却",
}
ERROR_CODES = {"authentication", "insufficient_balance", "rate_limit", "network_error", "provider_error",
               "request_rejected", "redirect_blocked", "implementation_changed", "source_changed",
               "invalid_response", "invalid_decision", "invalid_input", "not_configured", "pool_unavailable",
               "review_unavailable", "validation_required", "case_invalidated_after_request", "stale_case"}
SAFE_ID = re.compile(r"[A-Za-z0-9_-]{1,80}\Z")
GATE_REASONS = {
    "validation_required": "未取得独立验证资格，仅供人工参考",
    "validation_mismatch": "当前模型或类别未取得对应资格",
    "resolution_not_validated": "关键图片细节尚未充分验证",
    "model_protocol_inconsistent": "模型结论与检查项矛盾",
    "model_uncertain": "模型未完整确认一致性和唯一性",
    "candidate_change_requires_review": "模型建议更换候选，需人工确认",
    "competition_not_verified": "竞争候选尚未完整核验",
    "coverage_not_verified": "仍有重要区域未完整核验",
    "local_evidence_conflict": "本地图案或颜色证据存在差异",
    "stale_case": "复核内容已经变化", "source_changed": "原稿或预览已经变化",
    "ai_validated_identity": "模型、完整内容和唯一性均满足限定条件",
    "hard_conflict": "文件归属或编号存在冲突", "query_unreadable": "表格图片无法读取",
    "no_trusted_candidate": "没有可信候选", "too_many_competitors": "接近候选超过五个",
    "invalid_candidates": "候选原文件记录不完整", "duplicate_preview": "不同文件存在相同预览",
}


class AiDebugTrace:
    def __init__(self, capacity=2000, *, clock=time.monotonic):
        if type(capacity) is not int or not 1 <= capacity <= 10000:
            raise ValueError("调试缓冲数量无效。")
        self._events = deque(maxlen=capacity)
        self._active = {}
        self._sequence = 0
        self._clock = clock
        self._lock = threading.RLock()
        self.instance = uuid.uuid4().hex

    def emit(self, stage, *, job_id=None, row_id=None, **fields):
        if stage not in STAGES:
            return
        event = {"stage": stage, "message": STAGES[stage],
                 "time": datetime.now(timezone.utc).isoformat(timespec="milliseconds")}
        # IDs are local transport identifiers, never file names or provider IDs.
        for name, value in (("job_id", job_id), ("row_id", row_id), ("key_id", fields.get("key_id"))):
            if isinstance(value, str) and SAFE_ID.fullmatch(value) and not value.startswith("sk-"):
                event[name] = value
        # Aliases are resolved from safe local configuration by the browser;
        # deliberately never retain arbitrary key_label/message/result strings.
        for name in ("attempt", "elapsed_ms", "candidate_count", "image_count", "eligible", "reviewed"):
            value = fields.get(name)
            if type(value) is int and 0 <= value <= 1_000_000_000:
                event[name] = value
        if isinstance(fields.get("verdict"), str) and fields["verdict"] in {"same", "different", "uncertain"}:
            event["verdict"] = fields["verdict"]
        candidate = fields.get("candidate_id")
        if isinstance(candidate, str) and re.fullmatch(r"f[0-9]{4,8}", candidate):
            event["candidate_id"] = candidate
        code = fields.get("error_code") or fields.get("reason_code")
        if code is not None:
            event["error_code"] = code if isinstance(code, str) and code in ERROR_CODES else "review_unavailable"
        reason = fields.get("reason_code")
        if isinstance(reason, str) and reason in GATE_REASONS:
            event.pop("error_code", None)
            event["reason_code"] = reason
            reasons = [reason]
            for item in fields.get("gate_failures", []) if isinstance(fields.get("gate_failures"), list) else []:
                if isinstance(item, str) and item in GATE_REASONS and item not in reasons:
                    reasons.append(item)
            event["gate_reason"] = "；".join(GATE_REASONS[item] for item in reasons)
        if fields.get("model") == "deepseek-flash":
            event["model"] = "deepseek-flash"
        # Only valid counters/estimates; no unrestricted dictionaries or text.
        usage = fields.get("usage")
        if isinstance(usage, dict):
            from .ai_usage import empty_usage, merge_usage
            clean = merge_usage(empty_usage(), usage)
            event["usage"] = {k: clean[k] for k in ("requests", "successes", "failures", "prompt_tokens",
                "completion_tokens", "unknown_usage_requests", "estimated_usd", "estimated_usd_upper_bound", "currency")}
        now = self._clock()
        with self._lock:
            self._sequence += 1
            event["seq"] = self._sequence
            self._events.append(event)
            identity = (event.get("job_id"), event.get("row_id"))
            if stage in {"preparing", "requesting", "retrying", "returned", "verifying"}:
                self._active[identity] = (copy.deepcopy(event), now)
            else:
                self._active.pop(identity, None)
            if stage in {"run_finished", "disabled", "no_cases"}:
                self._active = {k: v for k, v in self._active.items() if k[0] != event.get("job_id")}

    def snapshot(self, after=0, limit=100):
        if type(after) is not int or after < 0 or type(limit) is not int or not 1 <= limit <= 200:
            raise ValueError("调试记录游标或条数无效。")
        with self._lock:
            reset = after > self._sequence
            if reset:
                after = 0
            oldest = self._events[0]["seq"] if self._events else 0
            selected = [event for event in self._events if event["seq"] > after][:limit]
            active = [{**event, "elapsed_ms": max(0, int((self._clock()-started)*1000))}
                      for event, started in self._active.values()]
            return copy.deepcopy({"instance": self.instance, "events": selected,
                "cursor": selected[-1]["seq"] if selected else after,
                "last_seq": self._sequence, "oldest_seq": oldest,
                "dropped": max(0, oldest-after-1) if oldest else 0, "reset": reset, "active": active})
