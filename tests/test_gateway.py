"""The internal gateway must forward with the host key and never expose it."""
import json

import pytest

from hsd_tool.ai_settings import AiSettings
from hsd_tool.gateway import TOKEN_NAME, create_app, load_token, valid_bind

KEY = "sk-gateway-test-credential-not-real"
BIND = "192.168.0.160"


class FakeProtector:
    def encrypt(self, value):
        return b"protected:" + bytes(character ^ 129 for character in value)

    def decrypt(self, value):
        if not value.startswith(b"protected:"):
            raise ValueError("cannot decrypt")
        return bytes(character ^ 129 for character in value[10:])


class FakeResponse:
    def __init__(self, body: bytes, status=200, url="https://api.deepseek.com/chat/completions"):
        self._body, self.status, self._url = body, status, url

    def __enter__(self):
        return self

    def __exit__(self, *info):
        return False

    def read(self, size=-1):
        return self._body[:size] if size >= 0 else self._body

    def geturl(self):
        return self._url


class FakeOpener:
    def __init__(self, response):
        self.response = response
        self.requests = []

    def open(self, request, timeout=None):
        self.requests.append(request)
        return self.response


def make_settings(tmp_path, *, with_key=True):
    settings = AiSettings(tmp_path, protector=FakeProtector(), environ={})
    if with_key:
        settings.save({"api_key": KEY, "enabled": True})
    return settings


def make_client(tmp_path, *, with_key=True, response=None, upstream=None):
    settings = make_settings(tmp_path, with_key=with_key)
    opener = FakeOpener(response or FakeResponse(b'{"ok":true}'))
    app = create_app(tmp_path, bind=BIND, settings=settings, opener=opener, upstream=upstream)
    return app.test_client(), opener, settings


def token(tmp_path) -> str:
    return load_token(tmp_path)


def test_bind_must_be_private_ipv4():
    assert valid_bind(BIND) == BIND
    for rejected in ("127.0.0.1", "8.8.8.8", "0.0.0.0", "not-an-ip", "192.168.0.160/24"):
        with pytest.raises(ValueError):
            valid_bind(rejected)


def test_token_is_persisted_and_reused(tmp_path):
    first = load_token(tmp_path)
    assert first == load_token(tmp_path)
    assert (tmp_path / TOKEN_NAME).read_text("ascii") == first
    assert 10 <= len(first) <= 512


def test_missing_token_is_rejected(tmp_path):
    client, opener, _ = make_client(tmp_path)
    response = client.post("/v1/chat/completions", json={"model": "x"})
    assert response.status_code == 401
    assert opener.requests == []


def test_forwarding_uses_host_key_and_relays_body(tmp_path):
    client, opener, _ = make_client(tmp_path, response=FakeResponse(b'{"choices":[]}'))
    payload = {"model": "deepseek-flash", "messages": []}
    response = client.post("/v1/chat/completions", json=payload,
                           headers={"Authorization": f"Bearer {token(tmp_path)}"})
    assert response.status_code == 200
    assert response.get_json() == {"choices": []}
    sent = opener.requests[0]
    assert sent.full_url == "https://api.deepseek.com/chat/completions"
    assert sent.get_header("Authorization") == f"Bearer {KEY}"
    assert json.loads(sent.data) == payload


def test_gateway_without_key_refuses_requests(tmp_path):
    client, opener, _ = make_client(tmp_path, with_key=False)
    response = client.post("/v1/chat/completions", json={"model": "x"},
                           headers={"Authorization": f"Bearer {token(tmp_path)}"})
    assert response.status_code == 503
    assert opener.requests == []


def test_upstream_redirect_is_refused(tmp_path):
    redirected = FakeResponse(b'{"ok":true}', url="https://elsewhere.example/collect")
    client, _, _ = make_client(tmp_path, response=redirected)
    response = client.post("/v1/chat/completions", json={"model": "x"},
                           headers={"Authorization": f"Bearer {token(tmp_path)}"})
    assert response.status_code == 502


def test_upstream_error_status_is_relayed(tmp_path):
    client, _, _ = make_client(tmp_path, response=FakeResponse(b'{"error":{}}', status=429))
    response = client.post("/v1/chat/completions", json={"model": "x"},
                           headers={"Authorization": f"Bearer {token(tmp_path)}"})
    assert response.status_code == 429


def test_status_page_never_renders_the_key(tmp_path):
    client, _, _ = make_client(tmp_path)
    page = client.get("/", environ_base={"REMOTE_ADDR": BIND}).get_data(as_text=True)
    assert KEY not in page
    assert token(tmp_path) in page


def test_status_page_is_host_only(tmp_path):
    client, _, _ = make_client(tmp_path)
    response = client.get("/", environ_base={"REMOTE_ADDR": "192.168.0.222"})
    assert response.status_code == 403


def test_configure_is_host_only(tmp_path):
    client, _, settings = make_client(tmp_path, with_key=False)
    body = {"api_key": KEY, "enabled": True}
    assert client.post("/configure", json=body,
                       environ_base={"REMOTE_ADDR": "192.168.0.222"}).status_code == 403
    assert settings.runtime()["api_key"] == ""
    saved = client.post("/configure", json=body, environ_base={"REMOTE_ADDR": "127.0.0.1"})
    assert saved.status_code == 200
    assert settings.runtime()["api_key"] == KEY
    assert KEY not in saved.get_data(as_text=True)


def test_health_reports_configuration_without_secrets(tmp_path):
    client, _, _ = make_client(tmp_path)
    payload = client.get("/health").get_json()
    assert payload["configured"] is True and payload["ok"] is True
    assert KEY not in json.dumps(payload)


def test_a_rebound_name_cannot_read_the_status_page_or_config(tmp_path):
    """A DNS-rebound page reaches the LAN listener from a local address.

    The address check alone would admit it, and the old same-origin test
    compared against the request's own Host, so the attacker's name vouched for
    itself. The fixed host list must refuse both the page and the write.
    """
    client, _, settings = make_client(tmp_path)
    rebound = {"Host": "attacker.example:8800", "Origin": "http://attacker.example:8800"}
    page = client.get("/", headers={"Host": "attacker.example:8800"})
    assert page.status_code == 403
    assert token(tmp_path) not in page.get_data(as_text=True)
    saved = client.post("/configure", json={"api_key": "sk-synthetic-attacker", "enabled": True},
                        headers=rebound)
    assert saved.status_code == 403
    assert settings.runtime()["api_key"] == KEY


def test_a_foreign_origin_cannot_rewrite_the_key(tmp_path):
    client, _, settings = make_client(tmp_path)
    response = client.post("/configure", json={"api_key": "sk-synthetic-attacker", "enabled": True},
                           headers={"Origin": "http://attacker.example"})
    assert response.status_code == 403
    assert settings.runtime()["api_key"] == KEY


def test_the_local_host_name_still_works(tmp_path):
    client, opener, _ = make_client(tmp_path)
    assert client.get("/", headers={"Host": f"{BIND}:8800"}).status_code == 200
    assert client.get("/health", headers={"Host": "localhost:8800"}).status_code == 200
