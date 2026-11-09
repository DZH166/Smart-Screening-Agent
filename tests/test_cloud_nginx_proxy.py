"""Exercise the deployed proxy policy with actual TLS, nginx and four HTTP threads.

Only the task payload/response bodies are synthetic. Cloud auth, transfer
admission, multipart streaming and disk checks use the application routes.
"""
from __future__ import annotations

from contextlib import ExitStack, closing
import hashlib
import http.client
from http.cookies import SimpleCookie
import json
import os
from pathlib import Path
import shutil
import socket
import ssl
import subprocess
import sys
import time
from types import SimpleNamespace
from uuid import uuid4

import pytest


ROOT = Path(__file__).resolve().parents[1]
TEST_CODE = "synthetic-proxy-test-code"
TEST_TOKEN = "synthetic-proxy-page-token"
TEST_JOB = "a" * 32
STREAM_EVENT = b"event: snapshot\ndata: {}\n\n"
STREAM_FILE = b"synthetic-download-start\n"


def backend():
    """Gunicorn fixture entrypoint; no providers or production files."""
    from flask import Response, jsonify, request
    from hsd_tool import uploads
    from hsd_tool.cloud_server import CloudAccess
    from hsd_tool.server import create_app

    private = Path(os.environ["HSD_QA_PROXY_ROOT"])
    origin = os.environ["HSD_QA_PROXY_ORIGIN"]
    app = create_app(private / "data", TEST_TOKEN, cloud=CloudAccess(origin, TEST_CODE),
                     settings_dir=private / "settings")
    original = app.wsgi_app
    real_disk_usage = uploads.shutil.disk_usage

    def observe(environ, start_response):
        marker = environ.get("HTTP_X_QA_REQUEST", "")
        if marker.isascii() and marker.isalnum() and len(marker) <= 32:
            (private / ("seen-" + marker)).touch()
        return original(environ, start_response)

    def disk_usage(path):
        if Path(path).is_relative_to(private / "data") and (private / "simulate-low-space").exists():
            return SimpleNamespace(free=0)
        return real_disk_usage(path)

    def receive():
        parts = request.files.getlist("file")
        assert len(parts) == 1
        stream = parts[0].stream
        return jsonify(bytes=stream.bytes_written, sha256=stream.hexdigest)

    def stream(prefix, mimetype):
        def body():
            yield prefix
            until(lambda: (private / "release-response").exists())
            yield b"done\n"
        return Response(body(), mimetype=mimetype)

    def events(material_id):
        assert material_id == TEST_JOB
        return stream(STREAM_EVENT, "text/event-stream")

    def download(material_id, item_id=None):
        assert material_id == TEST_JOB and item_id is None
        return stream(STREAM_FILE, "application/octet-stream")

    def acquire_material(identifier, owner):
        assert identifier == TEST_JOB and owner
        return lambda: None

    uploads.shutil.disk_usage = disk_usage
    app.wsgi_app = observe
    app.config["HSD_MATERIAL_MANAGER"].acquire = acquire_material
    app.view_functions.update(upload_job=receive, material_upload_job=receive,
                              material_events=events, material_download=download)
    return app


def until(condition, *, timeout=8):
    end = time.monotonic() + timeout
    while not condition():
        if time.monotonic() >= end:
            raise AssertionError("Timed out waiting for the isolated proxy fixture")
        time.sleep(.025)


def local_port():
    with closing(socket.socket()) as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


class Client:
    def __init__(self, port, certificate):
        self.port = port
        self.origin = f"https://127.0.0.1:{port}"
        self.context = ssl.create_default_context(cafile=str(certificate))
        self.cookie = ""

    def open(self, path, *, method="GET", headers=None):
        raw = socket.create_connection(("127.0.0.1", self.port), timeout=8)
        try:
            tls = self.context.wrap_socket(raw, server_hostname="127.0.0.1")
        except BaseException:
            raw.close()
            raise
        headers = {"Host": f"127.0.0.1:{self.port}", "Origin": self.origin,
                   "Connection": "close", **(headers or {})}
        if self.cookie:
            headers.update(Cookie=self.cookie)
            headers["X-HSD-Token"] = TEST_TOKEN
        request = [f"{method} {path} HTTP/1.1", *(f"{name}: {value}" for name, value in headers.items()), "", ""]
        try:
            tls.sendall("\r\n".join(request).encode("ascii"))
            return tls
        except BaseException:
            tls.close()
            raise

    @staticmethod
    def reply(tls):
        response = http.client.HTTPResponse(tls)
        response.begin()
        return response

    def request(self, path, *, method="GET", data=None, headers=None):
        headers = dict(headers or {})
        if data is not None:
            headers.update({"Content-Type": headers.get("Content-Type", "application/json"),
                            "Content-Length": len(data)})
        with self.open(path, method=method, headers=headers) as tls:
            if data is not None:
                tls.sendall(data)
            with self.reply(tls) as response:
                return response.status, response.headers, response.read()

    def login(self):
        status, headers, _ = self.request("/api/lan/login", method="POST",
                                          data=json.dumps({"code": TEST_CODE}).encode())
        assert status == 200
        jar = SimpleCookie()
        for header in headers.get_all("Set-Cookie", []):
            jar.load(header)
        assert jar
        self.cookie = "; ".join(f"{key}={value.value}" for key, value in jar.items())


@pytest.fixture
def proxy(tmp_path):
    if sys.platform != "linux" or not shutil.which("nginx") or not shutil.which("openssl"):
        pytest.skip("Linux nginx/OpenSSL acceptance requires both executables")
    pytest.importorskip("gunicorn")
    nginx = shutil.which("nginx")
    upstream, port = local_port(), local_port()
    assert upstream != port
    key, cert = tmp_path / "cert.key", tmp_path / "cert.pem"
    subprocess.run(["openssl", "req", "-x509", "-nodes", "-newkey", "rsa:2048", "-days", "1",
                    "-subj", "/CN=127.0.0.1", "-addext", "subjectAltName=IP:127.0.0.1",
                    "-keyout", str(key), "-out", str(cert)], capture_output=True, check=True, timeout=10)
    for directory in ("body", "proxy"):
        (tmp_path / directory).mkdir()
    site = (ROOT / "deploy/nginx-hsd.conf.example").read_text(encoding="utf-8")
    site = site.replace("listen 8443 ssl;", f"listen 127.0.0.1:{port} ssl;")
    site = site.replace("your-host.example;", "127.0.0.1;")
    site = site.replace("/etc/letsencrypt/live/your-host.example/fullchain.pem", str(cert))
    site = site.replace("/etc/letsencrypt/live/your-host.example/privkey.pem", str(key))
    site = site.replace("/var/log/hsd-agent/nginx-error.log", str(tmp_path / "site-error.log"))
    site = site.replace("/var/lib/hsd-agent/storage/nginx-body", str(tmp_path / "body"))
    site = site.replace("127.0.0.1:8830", f"127.0.0.1:{upstream}")
    config = tmp_path / "nginx.conf"
    config.write_text(
        f"pid {tmp_path}/nginx.pid;\nerror_log {tmp_path}/nginx-error.log;\n"
        f"events {{ worker_connections 128; }}\nhttp {{ proxy_temp_path {tmp_path}/proxy;\n{site}\n}}\n",
        encoding="utf-8")
    nginx_args = [nginx, "-p", str(tmp_path), "-c", str(config)]
    subprocess.run([*nginx_args, "-t"], capture_output=True, check=True, timeout=10)
    client = Client(port, cert)
    env = os.environ.copy()
    for name in ("OPENAI_API_KEY", "DEEPSEEK_API_KEY", "ARK_API_KEY", "HSD_CREDENTIAL_KEY_FILE"):
        env.pop(name, None)
    env.update(HSD_QA_PROXY_ROOT=str(tmp_path), HSD_QA_PROXY_ORIGIN=client.origin,
               PYTHONPATH=os.pathsep.join((str(ROOT), str(Path(__file__).resolve().parent))))
    with ExitStack() as stack:
        log = stack.enter_context((tmp_path / "gunicorn.log").open("wb"))
        commands = [[sys.executable, "-m", "gunicorn", "--workers", "1", "--worker-class", "gthread",
                     "--threads", "4", "--bind", f"127.0.0.1:{upstream}", f"{Path(__file__).stem}:backend()"],
                    [*nginx_args, "-g", "daemon off;"]]
        for command in commands:
            process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=log, stderr=log)

            def stop(process=process):
                if process.poll() is None:
                    process.terminate()
                try:
                    process.wait(timeout=6)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)

            stack.callback(stop)
        def ready():
            try:
                return client.request("/healthz")[0] == 200
            except OSError:
                return False
        until(ready)
        yield client, tmp_path


def multipart(value):
    begin = (b'--testboundary\r\nContent-Disposition: form-data; name="file"; filename="fixture.bin"\r\n'
             b'Content-Type: application/octet-stream\r\n\r\n')
    return begin + value + b"\r\n--testboundary--\r\n"


def chunk(tls, data):
    tls.sendall(f"{len(data):x}\r\n".encode() + data + b"\r\n")


def test_small_json_waits_at_proxy_but_large_routes_stream_and_controls_stay_available(proxy):
    client, private = proxy
    invalid = b'{"code":"invalid-code"}'
    with ExitStack() as stack:
        slow = []
        for i in range(4):
            tls = stack.enter_context(client.open("/api/lan/login", method="POST", headers={
                "Content-Type": "application/json", "Content-Length": len(invalid), "X-QA-Request": f"slow{i}"}))
            tls.sendall(invalid[:5])
            slow.append(tls)
        assert client.request("/healthz")[0] == 200
        assert not list(private.glob("seen-slow*"))
        for tls in slow:
            tls.sendall(invalid[5:])
        for tls in slow:
            with client.reply(tls) as response:
                assert response.status == 403
        assert len(list(private.glob("seen-slow*"))) == 4

    for path, size in [("/api/lan/login", 65537), ("/api/jobs/upload-extra", 65537),
                       ("/api/ribbon/assets", 21 * 1024**2 + 1)]:
        marker = "oversize" + uuid4().hex[:8]
        with client.open(path, method="POST", headers={"Content-Length": size, "X-QA-Request": marker}) as tls:
            with client.reply(tls) as response:
                assert response.status == 413
        assert not (private / ("seen-" + marker)).exists()
    for path in ("/api/jobs/upload", "/api/material/jobs", "/api/ribbon/assets"):
        with client.open(path, method="PUT", headers={"Content-Length": 64}) as tls:
            with client.reply(tls) as response:
                assert response.status == 405

    client.login()
    payload = b"x" * (1024 * 1024) + b"z" * 32
    form = multipart(payload)
    headers = {"Content-Type": "multipart/form-data; boundary=testboundary"}
    number_id, material_id = uuid4().hex, uuid4().hex
    with ExitStack() as stack:
        number = stack.enter_context(client.open("/api/jobs/upload", method="POST", headers={
            **headers, "Content-Length": len(form), "X-HSD-Upload-ID": number_id}))
        material = stack.enter_context(client.open("/api/material/jobs", method="POST", headers={
            **headers, "Transfer-Encoding": "chunked", "X-HSD-Upload-ID": material_id}))
        number.sendall(form[:-64])
        chunk(material, form[:-64])
        data = private / "data"
        for staging in (data / "uploads", data / "material_tasks/uploads"):
            until(lambda: any(p.is_file() and p.stat().st_size >= 64 * 1024
                              for p in staging.glob("*/*") if not p.name.startswith(".")))
        assert not any((private / "body").iterdir())
        assert client.request("/healthz")[0] == 200
        assert client.request("/api/config")[0] == 200
        state = client.request(f"/api/jobs/upload-status/{number_id}")
        assert state[0] == 200 and json.loads(state[2])["state"] == "pending"
        unused = uuid4().hex
        assert client.request(f"/api/jobs/upload-status/{unused}/cancel", method="POST", data=b"{}")[0] == 200
        rejected = client.request(f"/api/material/jobs/{TEST_JOB}/events")
        assert rejected[0] == 429 and rejected[1]["Retry-After"] == "2"
        assert json.loads(rejected[2])["code"] == "transfer_busy"
        number.sendall(form[-64:])
        chunk(material, form[-64:])
        material.sendall(b"0\r\n\r\n")
        expected = {"bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}
        for tls in (number, material):
            with client.reply(tls) as response:
                assert response.status == 200 and json.loads(response.read()) == expected

    (private / "simulate-low-space").touch()
    result = client.request("/api/jobs/upload", method="POST", data=multipart(b"x" * 131072), headers=headers)
    assert result[0] == 400 and "\u78c1\u76d8\u7a7a\u95f4\u4e0d\u8db3" in json.loads(result[2])["error"]
    assert not list((private / "data/uploads").iterdir())


def test_sse_and_download_flush_while_sharing_two_transfer_slots(proxy):
    client, private = proxy
    client.login()
    with ExitStack() as stack:
        for path, prefix in [(f"/api/material/jobs/{TEST_JOB}/events", STREAM_EVENT),
                             (f"/api/material/jobs/{TEST_JOB}/download", STREAM_FILE)]:
            tls = stack.enter_context(client.open(path))
            response = stack.enter_context(client.reply(tls))
            assert response.status == 200 and response.read(len(prefix)) == prefix
        assert client.request("/healthz")[0] == 200
        third = client.request("/api/material/jobs", method="POST", data=multipart(b"x"), headers={
            "Content-Type": "multipart/form-data; boundary=testboundary"})
        assert third[0] == 429 and json.loads(third[2])["code"] == "transfer_busy"
        (private / "release-response").touch()
