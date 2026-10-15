import base64
import copy
import io
import json
import socket
import urllib.error

import pytest

from hsd_tool.ai_client import CHECKS, DeepSeekClient, ENDPOINT, MAX_RESPONSE_BYTES, ReviewError, _NoRedirect

KEY = "sk-client-test-credential-not-real"
CONTENT = [{"type": "text", "text": "表格图与候选 f0001，请比较全部区域"},
           {"type": "image_url", "image_url": {"url": "data:image/png;base64," +
                base64.b64encode(b"\x89PNG\r\n\x1a\nsynthetic-test-preview").decode()}}]
DECISION = {"verdict": "same", "candidate_id": "f0001", "reason": "整幅图案与颜色一致",
            "checks": {key: True for key in CHECKS}, "differences": []}


def response(decision=None, **updates):
    payload = {"id": "chatcmpl-test", "model": "deepseek-v4.1-flash",
               "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(
                   DECISION if decision is None else decision)}}],
               "usage": {"prompt_tokens": 1000, "completion_tokens": 200,
                         "prompt_cache_hit_tokens": 100, "prompt_cache_miss_tokens": 900}}
    payload.update(updates)
    return json.dumps(payload).encode()


class Reply(io.BytesIO):
    def geturl(self):
        return ENDPOINT


class Opener:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def open(self, request, timeout):
        self.calls.append((request, timeout))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome if isinstance(outcome, Reply) else Reply(outcome)


def http_error(code):
    return urllib.error.HTTPError(ENDPOINT, code, "remote-secret " + KEY, {}, io.BytesIO(KEY.encode()))


def test_fixed_api_shape_and_conservative_complete_usage():
    opener = Opener([response()])
    result = DeepSeekClient(KEY, opener=opener).review(CONTENT)
    request, timeout = opener.calls[0]
    sent = json.loads(request.data)
    assert request.full_url == ENDPOINT and request.method == "POST"
    assert request.headers["Authorization"] == "Bearer " + KEY
    assert timeout == 30
    assert sent["model"] == "deepseek-flash" and sent["thinking"] == {"type": "disabled"}
    assert sent["response_format"] == {"type": "json_object"}
    assert sent["max_tokens"] == 1600 and sent["stream"] is False
    assert "JSON" in sent["messages"][0]["content"]
    assert result["decision"] == DECISION
    assert result["model"] == "deepseek-v4.1-flash"
    usage = result["usage"]
    assert usage["requests"] == usage["successes"] == 1 and usage["failures"] == 0
    assert usage["estimated_usd"] == pytest.approx(0.0005106)
    assert usage["estimated_usd_upper_bound"] == usage["estimated_usd"]
    assert not usage["cost_incomplete"] and usage["cost_is_upper_bound"]
    assert KEY not in json.dumps(result)


@pytest.mark.parametrize("first", [http_error(429), http_error(503), socket.timeout("slow " + KEY),
                                    urllib.error.URLError(socket.timeout("slow " + KEY))])
def test_only_bounded_retry_and_attempt_accounting(first):
    opener = Opener([first, response()])
    waits = []
    result = DeepSeekClient(KEY, opener=opener, sleeper=waits.append).review(CONTENT)
    assert len(opener.calls) == 2 and waits == [0.5]
    assert result["usage"]["requests"] == 2
    assert result["usage"]["successes"] == 1 and result["usage"]["failures"] == 1
    if isinstance(first, urllib.error.HTTPError) and first.code == 429:
        assert result["usage"]["unknown_usage_requests"] == 0
    else:
        assert result["usage"]["unknown_usage_requests"] == 1
        assert result["usage"]["estimated_usd_upper_bound"] is None
        assert result["usage"]["cost_incomplete"]


@pytest.mark.parametrize("failure,code", [(http_error(401), "authentication"),
    (http_error(402), "insufficient_balance"), (http_error(400), "request_rejected"),
    (http_error(307), "redirect_blocked"),
    (urllib.error.URLError("DNS error " + KEY), "network_error")])
def test_nonretryable_failures_are_sanitized(failure, code):
    opener = Opener([failure, response()])
    with pytest.raises(ReviewError) as result:
        DeepSeekClient(KEY, opener=opener).review(CONTENT)
    assert result.value.code == code
    assert result.value.usage["requests"] == result.value.usage["failures"] == 1
    assert len(opener.calls) == 1 and KEY not in str(result.value)


def test_repeated_timeout_stops_after_two_attempts_without_zero_cost_claim():
    opener = Opener([socket.timeout(), socket.timeout(), response()])
    with pytest.raises(ReviewError) as result:
        DeepSeekClient(KEY, opener=opener, sleeper=lambda _: None).review(CONTENT)
    usage = result.value.usage
    assert len(opener.calls) == 2
    assert usage["requests"] == usage["failures"] == usage["unknown_usage_requests"] == 2
    assert usage["cost_incomplete"] and usage["estimated_usd_upper_bound"] is None


def test_redirect_handler_never_constructs_redirected_credential_request():
    assert _NoRedirect().redirect_request(None, None, 307, "redirect", {}, "https://evil.invalid") is None
    class ChangedURL(Reply):
        def geturl(self):
            return "https://evil.invalid/chat/completions"
    with pytest.raises(ReviewError, match="重定向"):
        DeepSeekClient(KEY, opener=Opener([ChangedURL(response())])).review(CONTENT)


@pytest.mark.parametrize("change", [
    lambda d: d.update(verdict="probably"), lambda d: d.update(candidate_id=None),
    lambda d: d.update(candidate_id="file/name.ai"), lambda d: d.update(reason=""),
    lambda d: d.update(candidate_id=KEY),
    lambda d: d.update(reason="x" * 501), lambda d: d.update(differences="none"),
    lambda d: d.update(differences=[False]), lambda d: d.update(extra="unexpected"),
    lambda d: d["checks"].update(content_same="true"),
    lambda d: d["checks"].update(content_same=1), lambda d: d["checks"].pop("colors_same"),
])
def test_invalid_model_decision_is_never_successful_or_retried(change):
    decision = copy.deepcopy(DECISION)
    change(decision)
    opener = Opener([response(decision), response()])
    with pytest.raises(ReviewError) as result:
        DeepSeekClient(KEY, opener=opener).review(CONTENT)
    assert result.value.code == "invalid_decision" and len(opener.calls) == 1
    assert result.value.usage["failures"] == 1
    assert result.value.usage["prompt_tokens"] == 1000


def test_unknown_usage_is_not_fabricated_as_zero_dollars():
    result = DeepSeekClient(KEY, opener=Opener([response(usage={})])).review(CONTENT)
    assert result["usage"]["unknown_usage_requests"] == 1
    assert result["usage"]["estimated_usd_upper_bound"] is None
    assert result["usage"]["cost_incomplete"]


def test_missing_cache_breakdown_uses_input_upper_bound():
    result = DeepSeekClient(KEY, opener=Opener([response(usage={"prompt_tokens": 1000,
                  "completion_tokens": 200})])).review(CONTENT)
    assert result["usage"]["cache_miss_tokens"] == 1000
    assert result["usage"]["estimated_usd"] == pytest.approx(0.00054)


@pytest.mark.parametrize("raw", [b"not json", b'{"choices": NaN}',
                                    b'{"choices":[],"choices":[]}', b"x" * (MAX_RESPONSE_BYTES + 1)],
                         ids=["malformed", "nonfinite", "duplicate-key", "oversized"])
def test_malformed_or_oversized_responses_fail_without_retry(raw):
    opener = Opener([raw, response()])
    with pytest.raises(ReviewError) as result:
        DeepSeekClient(KEY, opener=opener).review(CONTENT)
    assert len(opener.calls) == 1
    assert result.value.usage["unknown_usage_requests"] == 1


def test_truncated_completion_keeps_known_usage_but_rejects_decision():
    payload = json.loads(response())
    payload["choices"][0]["finish_reason"] = "length"
    with pytest.raises(ReviewError) as result:
        DeepSeekClient(KEY, opener=Opener([json.dumps(payload).encode()])).review(CONTENT)
    assert result.value.code == "invalid_decision"
    assert result.value.usage["completion_tokens"] == 200


def test_api_key_echo_is_redacted_from_decision():
    decision = copy.deepcopy(DECISION)
    decision["reason"] = "remote echo " + KEY
    decision["differences"] = [KEY]
    result = DeepSeekClient(KEY, opener=Opener([response(decision)])).review(CONTENT)
    assert KEY not in json.dumps(result)


@pytest.mark.parametrize("content", [[], [{"type": "text", "text": "no image"}],
    [{"type": "image_url", "image_url": {"url": "https://example.invalid/secret.png"}}],
    [{"type": "image_url", "image_url": {"url": "data:image/png;base64,bm90LWltYWdl"}}],
    [{"type": "text", "text": KEY}] + CONTENT])
def test_invalid_inputs_never_send_requests(content):
    opener = Opener([])
    with pytest.raises(ReviewError) as result:
        DeepSeekClient(KEY, opener=opener).review(content)
    assert result.value.code == "invalid_input" and not opener.calls
    assert result.value.usage["requests"] == 0
