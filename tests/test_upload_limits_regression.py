"""Independent upload-size and cleanup regression checks; generated inputs only.

No live server, user settings, business files or DeepSeek calls are involved.
"""
from __future__ import annotations

import errno
from io import BytesIO
from pathlib import Path
import zipfile

from flask import Flask
import pytest

from hsd_tool import matching, uploads
from hsd_tool.lan import LanAccess
from hsd_tool.server import EmployeeUploadRequest, create_app


HOST = "192.168.99.10"
REMOTE = "192.168.99.11"
ORIGIN = f"http://{HOST}:8844"
TOKEN = "synthetic-size-regression-token"
CODE = "synthetic-size-regression-code"


class CloseProbe:
    def __init__(self, *, fail_once=False):
        self.calls = 0
        self.fail_once = fail_once
        self.closed = False

    def close(self):
        self.calls += 1
        if self.fail_once and self.calls == 1:
            raise OSError(errno.ENOSPC, "synthetic close/flush failure")
        self.closed = True


def cleanup_request(tmp_path, *, committed=False):
    app = Flask(__name__)
    receiver = uploads.EmployeeUploads(tmp_path)
    app.config["HSD_UPLOADS"] = receiver
    directory = receiver.begin()
    (directory / "part-synthetic").write_bytes(b"synthetic incomplete upload")
    request = EmployeeUploadRequest.from_values()
    request._hsd_upload_directory = directory
    request._hsd_upload_committed = committed
    return app, receiver, directory, request


def test_close_failure_does_not_skip_other_streams_or_uncommitted_directory(tmp_path):
    app, _, directory, request = cleanup_request(tmp_path)
    first, second = CloseProbe(fail_once=True), CloseProbe()
    request._hsd_upload_streams = [first, second]
    with app.app_context():
        with pytest.raises(OSError, match="close/flush"):
            request.release_upload()
        assert second.closed, "one failed close must not leak later streams"
        assert not directory.exists(), "uncommitted files must still be discarded"
        assert not getattr(request, "_hsd_upload_released", False)
        request.release_upload()
        assert first.closed
        assert request._hsd_upload_released
        counts = first.calls, second.calls
        request.release_upload()
        assert (first.calls, second.calls) == counts


def test_discard_failure_can_be_retried_by_teardown(tmp_path, monkeypatch):
    app, receiver, directory, request = cleanup_request(tmp_path)
    probe = CloseProbe()
    request._hsd_upload_streams = [probe]
    discard = receiver.discard
    attempts = []

    def temporarily_locked(path):
        attempts.append(Path(path))
        if len(attempts) == 1:
            raise PermissionError(errno.EACCES, "synthetic temporary lock")
        discard(path)

    monkeypatch.setattr(receiver, "discard", temporarily_locked)
    with app.app_context():
        with pytest.raises(PermissionError):
            request.release_upload()
        assert probe.closed and directory.exists()
        assert not getattr(request, "_hsd_upload_released", False)
        request.release_upload()
        assert not directory.exists()
        assert len(attempts) == 2
        assert request._hsd_upload_released


def test_committed_upload_keeps_originals_even_when_close_needs_retry(tmp_path):
    app, _, directory, request = cleanup_request(tmp_path, committed=True)
    request._hsd_upload_streams = [CloseProbe(fail_once=True), CloseProbe()]
    with app.app_context():
        with pytest.raises(OSError):
            request.release_upload()
        assert request._hsd_upload_streams[1].closed
        request.release_upload()
    assert (directory / "part-synthetic").read_bytes() == b"synthetic incomplete upload"


def zip_data(parts, compression=zipfile.ZIP_STORED):
    result = BytesIO()
    with zipfile.ZipFile(result, "w", compression=compression) as archive:
        for name, data in parts.items():
            archive.writestr(name, data)
    return result.getvalue()


@pytest.fixture
def isolated_employee_app(tmp_path, monkeypatch):
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    lan = LanAccess(f"{HOST}/24", inputs, tmp_path / "outputs", code=CODE)
    app = create_app(tmp_path / "state", token=TOKEN, lan=lan,
                     settings_dir=tmp_path / "isolated-ai-settings")
    app.config.update(TESTING=True, HSD_PORT=8844)
    manager = app.config["HSD_MANAGER"]
    monkeypatch.setattr(manager, "_submit", lambda *_: None)
    yield app
    manager.close()


def open_request(client, path, *, method="GET", **kwargs):
    return client.open(path, method=method, base_url=ORIGIN,
                       environ_overrides={"REMOTE_ADDR": REMOTE},
                       headers={"Origin": ORIGIN, "X-HSD-Token": TOKEN}, **kwargs)


def logged_client(app):
    client = app.test_client()
    assert open_request(client, "/api/lan/login", method="POST", json={"code": CODE}).status_code == 200
    return client


def test_null_caps_bypass_only_upload_limit_not_json_request_limit(isolated_employee_app):
    app = isolated_employee_app
    client = logged_client(app)
    config = open_request(client, "/api/config").get_json()
    assert config["access"]["upload_limits"] == {
        "workbook_bytes": None, "source_bytes": None, "total_bytes": None}
    workbook = zip_data({"[Content_Types].xml": b"<Types/>",
                         "xl/workbook.xml": b"<workbook/>",
                         "synthetic-padding.bin": b"x" * (96 * 1024)})
    response = open_request(client, "/api/jobs/upload", method="POST", data={
        "workbook": (BytesIO(workbook), "synthetic.xlsx"),
        "source": (BytesIO(zip_data({"synthetic.ai": b"synthetic"})), "synthetic.zip"),
        "start_number": "7"}, content_type="multipart/form-data")
    assert response.status_code == 200, response.get_json()
    assert len(workbook) > app.config["MAX_CONTENT_LENGTH"]
    identifier = response.get_json()["id"]
    assert open_request(client, f"/api/jobs/{identifier}").status_code == 200
    denied = open_request(client, "/api/jobs", method="POST", json={"padding": "x" * (70 * 1024)})
    assert denied.status_code == 413


@pytest.mark.parametrize("oversized_field", [False, True])
def test_incomplete_or_oversized_field_cleans_started_file_stream(isolated_employee_app, monkeypatch,
                                                                oversized_field):
    app = isolated_employee_app
    client = logged_client(app)
    receiver = app.config["HSD_UPLOADS"]
    started, begin = [], receiver.begin

    def track_begin():
        path = begin()
        started.append(path)
        return path

    monkeypatch.setattr(receiver, "begin", track_begin)
    boundary = "synthetic-stream-cleanup-boundary"
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="workbook"; '
            'filename="synthetic.xlsx"\r\nContent-Type: application/octet-stream\r\n\r\n').encode()
    body += b"x" * (96 * 1024)
    if oversized_field:
        body += (f'\r\n--{boundary}\r\nContent-Disposition: form-data; name="start_number"\r\n\r\n').encode()
        body += b"1" * (600 * 1024)
        body += f"\r\n--{boundary}--\r\n".encode()
    response = open_request(client, "/api/jobs/upload", method="POST", data=body,
                            content_type=f"multipart/form-data; boundary={boundary}")
    assert response.status_code == (413 if oversized_field else 400), response.get_json()
    assert started, "the test must reach file streaming before its later failure"
    assert not any(path.exists() for path in started)
    assert not list(receiver.input_root.iterdir())
    assert app.config["HSD_ACTIVE_UPLOADS"] == 0
    assert not app.config["HSD_MANAGER"].jobs


def test_high_compression_ratio_is_not_an_implicit_file_size_limit(tmp_path):
    assert matching.MAX_FILE_BYTES is None
    assert matching.MAX_TOTAL_BYTES is None
    assert matching.MAX_RATIO is None
    source, destination = tmp_path / "synthetic.zip", tmp_path / "extracted"
    destination.mkdir()
    data = b"%PDF-synthetic-header\n" + b"0" * (2 * 1024 * 1024)
    source.write_bytes(zip_data({"synthetic.ai": data}, zipfile.ZIP_DEFLATED))
    with zipfile.ZipFile(source) as archive:
        entry = archive.getinfo("synthetic.ai")
        assert entry.file_size / entry.compress_size > 1000
    files = matching._collect(source, destination, [])
    assert len(files) == 1
    assert Path(files[0]["source_path"]).read_bytes() == data
