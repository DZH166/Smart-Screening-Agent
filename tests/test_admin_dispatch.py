"""Real client protocol with synthetic transports; never calls a provider."""
import json
from types import SimpleNamespace

import pytest

from hsd_tool.ai_admin import AiDebugTrace
from hsd_tool.ai_client import DeepSeekClient, ReviewError
from hsd_tool.ai_dispatch import ManagedReviewClient
from hsd_tool.ai_key_pool import ApiKeyPool
from test_ai_client import CONTENT, Opener, http_error, response


class Settings:
    def __init__(self, count=3):
        self.keys = [{"id": "test-key-"+str(index), "label": "密钥"+str(index), "enabled": True,
                      "api_key": "synthetic-private-key-"+str(index), "source": "saved"} for index in range(count)]
    def runtime(self):
        return {"enabled": True, "keys": self.keys, "api_key": self.keys[0]["api_key"] if self.keys else ""}


def manager_and_client(outcomes):
    settings = Settings(len(outcomes))
    manager = SimpleNamespace(ai_settings=settings, ai_debug=AiDebugTrace(), ai_key_pool=ApiKeyPool(settings))
    openers = {row["api_key"]: Opener(values) for row, values in zip(settings.keys, outcomes)}
    factory = lambda key: DeepSeekClient(key, opener=openers[key], sleeper=lambda _: None)
    waits = []
    client = ManagedReviewClient(manager, factory, "job1", sleeper=waits.append)
    return manager, client, openers, waits


def test_auth_failure_switches_keys_within_two_actual_requests_and_keeps_usage():
    manager, client, openers, waits = manager_and_client([[http_error(401)], [response()]])
    result = client.review(CONTENT, row_id="r2")
    assert result["usage"]["requests"] == 2 and result["usage"]["failures"] == 1
    assert result["usage"]["successes"] == 1
    assert [len(opener.calls) for opener in openers.values()] == [1, 1]
    keys = manager.ai_key_pool.snapshot()["keys"]
    assert keys[0]["status"] == "paused_authentication"
    assert keys[1]["status"] == "available"
    assert waits == [.5]
    events = manager.ai_debug.snapshot()["events"]
    assert [event["key_id"] for event in events if event["stage"] == "requesting"] == ["test-key-0", "test-key-1"]
    text = json.dumps({"events":events,"pool":manager.ai_key_pool.snapshot()})
    assert all(row["api_key"] not in text for row in manager.ai_settings.keys)


def test_three_bad_keys_do_not_multiply_the_original_attempt_budget():
    manager, client, openers, _ = manager_and_client([[http_error(401)], [http_error(402)], [response()]])
    with pytest.raises(ReviewError) as caught:
        client.review(CONTENT, row_id="r2")
    assert caught.value.usage["requests"] == 2 and caught.value.usage["failures"] == 2
    assert [len(opener.calls) for opener in openers.values()] == [1,1,0]


def test_account_rate_limit_is_not_evaded_by_immediately_switching_keys():
    manager, client, openers, waits = manager_and_client([[http_error(429)], [response()]])
    with pytest.raises(ReviewError) as caught:
        client.review(CONTENT, row_id="r2")
    assert caught.value.code == "rate_limit" and caught.value.usage["requests"] == 1
    assert [len(opener.calls) for opener in openers.values()] == [1,0]
    assert waits == [] and manager.ai_key_pool.snapshot()["keys"][0]["status"] == "cooldown"


def test_provider_retry_uses_same_enabled_key_and_retains_unknown_cost():
    manager, client, openers, waits = manager_and_client([[http_error(503), response()], [response()]])
    result = client.review(CONTENT, row_id="r2")
    usage = result["usage"]
    assert usage["requests"] == 2 and usage["successes"] == usage["failures"] == 1
    assert usage["unknown_usage_requests"] == 1 and usage["estimated_usd_upper_bound"] is None
    assert [len(opener.calls) for opener in openers.values()] == [2,0] and waits == [.5]


def test_disabling_key_during_backoff_prevents_reusing_a_stale_credential():
    manager, client, openers, _ = manager_and_client([[http_error(503), response()]])
    client.sleep = lambda _: manager.ai_settings.keys[0].update(enabled=False)
    with pytest.raises(ReviewError) as caught:
        client.review(CONTENT, row_id="r2")
    assert caught.value.usage["requests"] == 1 and caught.value.usage["unknown_usage_requests"] == 1
    assert len(next(iter(openers.values())).calls) == 1


def test_rotation_occurs_between_cases_and_not_by_sending_parallel_duplicates():
    manager, client, openers, _ = manager_and_client([[response()], [response()]])
    client.review(CONTENT, row_id="r2")
    client.review(CONTENT, row_id="r3")
    assert [len(opener.calls) for opener in openers.values()] == [1,1]


def test_debug_rejects_unstructured_data_and_reports_all_local_gate_reasons():
    trace = AiDebugTrace()
    secret = "never-show-private-provider-body"
    trace.emit("manual", job_id="job1", row_id="r2", message=secret, key_label=secret,
               prompt=secret, response=secret, reason_code="validation_required",
               gate_failures=["coverage_not_verified", "local_evidence_conflict", secret])
    event = trace.snapshot()["events"][0]
    assert secret not in json.dumps(event)
    assert "独立验证资格" in event["gate_reason"] and "重要区域" in event["gate_reason"] and "颜色" in event["gate_reason"]
