import concurrent.futures
import json

import pytest

from hsd_tool.ai_key_pool import ApiKeyPool, KeyPoolUnavailable
from hsd_tool.ai_settings import AiSettings
from hsd_tool.ai_usage import empty_usage


def prepared(tmp_path, count=3):
    settings = AiSettings(tmp_path, protector=None, environ={})
    settings.save_pool({"expected_revision": 0, "add": [
        {"api_key": "sk-pool-test-%02d-not-real" % i, "label": "账户 %d" % i}
        for i in range(count)]})
    settings.save({"enabled": True})
    now = [10.0]
    pool = ApiKeyPool(settings, clock=lambda: now[0])
    return settings, pool, now


def change(settings, **kwargs):
    return settings.save_pool({"expected_revision": settings.snapshot()["key_revision"], **kwargs})


def test_rotation_excludes_attempted_keys_and_is_thread_safe(tmp_path):
    settings, pool, _ = prepared(tmp_path)
    first, second, third = [pool.acquire() for _ in range(3)]
    assert len({first["id"], second["id"], third["id"]}) == 3
    assert pool.acquire()["id"] == first["id"]
    assert pool.acquire(exclude_ids=[second["id"], third["id"]])["id"] == first["id"]
    with pytest.raises(KeyPoolUnavailable) as error:
        pool.acquire(exclude_ids=[first["id"], second["id"], third["id"]])
    assert error.value.code == "pool_unavailable"
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as threads:
        selections = list(threads.map(lambda _: pool.acquire()["id"], range(90)))
    assert all(selections.count(row["id"]) == 30 for row in settings.snapshot()["keys"])


@pytest.mark.parametrize("code", ["authentication", "insufficient_balance"])
def test_auth_and_balance_pause_until_explicit_admin_reenable(tmp_path, code):
    settings, pool, now = prepared(tmp_path, 1)
    first = pool.acquire()
    pool.report(first["id"], code=code)
    now[0] += 100000
    with pytest.raises(KeyPoolUnavailable):
        pool.acquire()
    assert pool.snapshot()["keys"][0]["status"] == "paused_" + code
    change(settings, update=[{"id": first["id"], "enabled": False}])
    assert pool.snapshot()["keys"][0]["status"] == "disabled"
    change(settings, update=[{"id": first["id"], "enabled": True}])
    assert pool.acquire()["id"] == first["id"]


def test_rate_limit_cools_60_seconds_and_network_failure_does_not_pause(tmp_path):
    settings, pool, now = prepared(tmp_path, 1)
    first = pool.acquire()
    pool.report(first["id"], code="rate_limit")
    assert pool.snapshot()["keys"][0]["cooldown_seconds"] == 60
    now[0] += 59.5
    with pytest.raises(KeyPoolUnavailable):
        pool.acquire()
    assert pool.snapshot()["keys"][0]["retry_after_seconds"] == 1
    # Explicit enable is not a way to clear account rate limiting.
    change(settings, update=[{"id": first["id"], "enabled": False}])
    pool.snapshot()
    change(settings, update=[{"id": first["id"], "enabled": True}])
    with pytest.raises(KeyPoolUnavailable):
        pool.acquire()
    now[0] += 0.5
    assert pool.acquire()["id"] == first["id"]
    pool.report(first["id"], code="network_error")
    assert pool.acquire()["id"] == first["id"]


def test_disable_delete_and_global_disable_immediately_affect_acquire(tmp_path):
    settings, pool, _ = prepared(tmp_path, 2)
    first = pool.acquire()
    change(settings, update=[{"id": first["id"], "enabled": False}])
    assert pool.acquire()["id"] != first["id"]
    change(settings, remove=[first["id"]])
    assert first["id"] not in {row["id"] for row in pool.snapshot()["keys"]}
    pool.report(first["id"], code="authentication")  # Removed in-flight result is ignored.
    settings.save({"enabled": False})
    with pytest.raises(KeyPoolUnavailable) as error:
        pool.acquire()
    assert error.value.code == "pool_unavailable"
    assert pool.snapshot()["keys"][0]["status"] == "service_disabled"


def test_unconfigured_is_distinct_from_disabled_and_credentials_never_in_snapshot(tmp_path):
    settings = AiSettings(tmp_path, protector=None, environ={})
    pool = ApiKeyPool(settings)
    with pytest.raises(KeyPoolUnavailable) as error:
        pool.acquire()
    assert error.value.code == "not_configured"
    settings.save_pool({"expected_revision": 0, "add": [{"api_key": "sk-private-pool-credential"}]})
    public = json.dumps(pool.snapshot())
    assert "sk-private" not in public and "api_key" not in public and "_fingerprint" not in public


def test_usage_known_unknown_usd_and_totals_survive_removal(tmp_path):
    settings, pool, _ = prepared(tmp_path, 2)
    first = pool.acquire()
    usage = empty_usage()
    usage.update(requests=1, successes=1, prompt_tokens=10, completion_tokens=20,
                 estimated_usd=0.123, estimated_usd_upper_bound=0.123)
    pool.report(first["id"], usage=usage)
    snapshot = pool.snapshot()
    assert snapshot["currency"] == "USD" and snapshot["scope"] == "current_process"
    assert snapshot["keys"][0]["requests"] == 1
    assert snapshot["keys"][0]["estimated_usd_upper_bound"] == 0.123
    pool.report(first["id"], code="network_error")
    snapshot = pool.snapshot()
    assert snapshot["usage"]["requests"] == 2
    assert snapshot["usage"]["unknown_usage_requests"] == 1
    assert snapshot["usage"]["estimated_usd"] == 0.123
    assert snapshot["usage"]["estimated_usd_upper_bound"] is None
    assert snapshot["keys"][0]["usage"]["cost_incomplete"] is True
    change(settings, remove=[first["id"]])
    assert pool.snapshot()["usage"]["requests"] == 2


def test_provider_raw_error_never_recorded_and_malformed_usage_not_trusted(tmp_path):
    _, pool, _ = prepared(tmp_path, 1)
    key = pool.acquire()
    pool.report(key["id"], code="unsafe message " + key["api_key"], usage={"api_key": key["api_key"]})
    public = json.dumps(pool.snapshot())
    assert key["api_key"] not in public and "unsafe message" not in public
    assert pool.snapshot()["usage"]["unknown_usage_requests"] == 1


def test_replacing_single_legacy_key_does_not_let_old_request_pause_new_key(tmp_path):
    settings, pool, _ = prepared(tmp_path, 1)
    old = pool.acquire()
    settings.save({"api_key": "sk-new-private-pool-test-key"})
    pool.report(old["id"], code="authentication")
    new = pool.acquire()
    assert new["id"] != old["id"] and new["api_key"] != old["api_key"]


def test_environment_key_disabled_persists_and_cannot_be_restarted_by_pool(tmp_path):
    environment = {"DEEPSEEK_API_KEY": "sk-env-pool-credential-not-real"}
    settings = AiSettings(tmp_path, protector=None, environ=environment)
    settings.save({"enabled": True})
    pool = ApiKeyPool(settings)
    assert pool.acquire()["id"] == "environment"
    change(settings, update=[{"id": "environment", "enabled": False}])
    with pytest.raises(KeyPoolUnavailable):
        pool.acquire()
    restored = AiSettings(tmp_path, protector=None, environ=environment)
    assert restored.snapshot()["keys"][0]["enabled"] is False
    with pytest.raises(KeyPoolUnavailable):
        ApiKeyPool(restored).acquire()
