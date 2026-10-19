"""The gateway must work as a first-class credential in the key-pool dispatch path."""
from hsd_tool.ai_dispatch import ManagedReviewClient
from hsd_tool.ai_key_pool import ApiKeyPool
from hsd_tool.ai_settings import OFFICIAL_ENDPOINT, AiSettings
from hsd_tool.ai_usage import empty_usage

KEY = "sk-dispatch-gateway-test-not-real"
TOKEN = "gateway-dispatch-token-0123456789"
ENDPOINT = "http://192.168.0.160:8899/v1/chat/completions"


class FakeProtector:
    def encrypt(self, value):
        return b"protected:" + bytes(character ^ 129 for character in value)

    def decrypt(self, value):
        if not value.startswith(b"protected:"):
            raise ValueError("cannot decrypt")
        return bytes(character ^ 129 for character in value[10:])


class StubDebug:
    def emit(self, *args, **kwargs):
        pass


class StubManager:
    def __init__(self, settings, pool):
        self.ai_settings = settings
        self.ai_key_pool = pool
        self.ai_debug = StubDebug()


class FakeClient:
    def __init__(self):
        self.attempts = 1

    def review(self, content):
        return {"model": "deepseek-flash", "request_id": "fake-request",
                "usage": {**empty_usage(), "requests": 1, "successes": 1},
                "decision": {"verdict": "same", "candidate_id": "x"}}


def settings(tmp_path, **kwargs):
    kwargs.setdefault("environ", {})
    return AiSettings(tmp_path, protector=FakeProtector(), **kwargs)


def test_gateway_credential_is_sent_to_the_gateway_endpoint(tmp_path):
    managed = settings(tmp_path, gateway={"endpoint": ENDPOINT, "token": TOKEN})
    pool = ApiKeyPool(managed)
    manager = StubManager(managed, pool)
    seen = {}

    def factory(api_key, endpoint=None):
        seen.update(api_key=api_key, endpoint=endpoint)
        return FakeClient()

    result = ManagedReviewClient(manager, factory, "job").review(
        [{"type": "text", "text": '{"candidate_ids":["x"]}'}], row_id="r1")
    assert seen == {"api_key": TOKEN, "endpoint": ENDPOINT}
    # The gateway stays out of the administrator key list.
    assert "key_id" not in result["attempt_history"][0]
    assert pool.snapshot()["configured"] is False
    assert managed.snapshot()["configured"] is True


def test_gateway_does_not_appear_as_a_pooled_key(tmp_path):
    managed = settings(tmp_path, gateway={"endpoint": ENDPOINT, "token": TOKEN})
    assert managed.snapshot()["key_count"] == 0
    assert managed.snapshot()["key_source"] == "gateway"
    assert managed.runtime()["keys"] == []


def test_saved_key_keeps_the_official_endpoint(tmp_path):
    managed = settings(tmp_path)
    managed.save({"api_key": KEY, "enabled": True})
    pool = ApiKeyPool(managed)
    manager = StubManager(managed, pool)
    seen = {}

    def factory(api_key, **kwargs):
        seen.update(api_key=api_key, extra=kwargs)
        return FakeClient()

    ManagedReviewClient(manager, factory, "job").review(
        [{"type": "text", "text": '{"candidate_ids":["x"]}'}], row_id="r1")
    assert seen["api_key"] == KEY
    assert seen["extra"] == {}
    assert managed.runtime()["endpoint"] == OFFICIAL_ENDPOINT
    assert managed.runtime()["via_gateway"] is False


def test_saved_key_still_wins_over_a_gateway(tmp_path):
    managed = settings(tmp_path, gateway={"endpoint": ENDPOINT, "token": TOKEN})
    managed.save({"api_key": KEY, "enabled": True})
    assert managed.runtime()["api_key"] == KEY
    assert managed.runtime()["via_gateway"] is False
    assert [row["source"] for row in managed.runtime()["keys"]] == ["saved"]
