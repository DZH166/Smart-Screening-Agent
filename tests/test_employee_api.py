"""Employee upload/download isolation, using generated containers and no AI API."""
from io import BytesIO
import hashlib
from pathlib import Path
import zipfile

import pytest
from werkzeug.datastructures import MultiDict

from hsd_tool.lan import LanAccess
from hsd_tool.server import create_app


HOST = "192.168.0.160"
REMOTE = "192.168.0.25"
ORIGIN = f"http://{HOST}:8805"
CODE = "synthetic-employee-code"
TOKEN = "synthetic-employee-token"


def zip_bytes(parts):
    result = BytesIO()
    with zipfile.ZipFile(result, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in parts.items():
            archive.writestr(name, data)
    return result.getvalue()


def workbook_bytes():
    return zip_bytes({
        "[Content_Types].xml": '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/></Types>',
        "_rels/.rels": '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        "xl/workbook.xml": '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Generated" sheetId="1" r:id="rId1"/></sheets></workbook>',
        "xl/_rels/workbook.xml.rels": '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>',
        "xl/worksheets/sheet1.xml": '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData/></worksheet>',
    })


def request(client, path, *, method="GET", address=REMOTE, origin=ORIGIN,
            token=TOKEN, payload=None, **kwargs):
    headers = dict(kwargs.pop("headers", {}))
    if origin is not None:
        headers["Origin"] = origin
    if token is not None:
        headers["X-HSD-Token"] = token
    if payload is not None:
        kwargs["json"] = payload
    return client.open(path, method=method, base_url=ORIGIN, headers=headers,
                       environ_overrides={"REMOTE_ADDR": address}, **kwargs)


def login(client):
    response = request(client, "/api/lan/login", method="POST", payload={"code": CODE})
    assert response.status_code == 200


def upload(client, *, workbook=None, source=None, workbook_name="员工表格.xlsx",
           source_name="员工原稿.zip", start="1", **kwargs):
    data = {"start_number": start}
    if workbook is not False:
        data["workbook"] = (BytesIO(workbook_bytes() if workbook is None else workbook), workbook_name)
    if source is not False:
        data["source"] = (BytesIO(zip_bytes({"pattern.ai": b"synthetic-ai"}) if source is None else source), source_name)
    return request(client, "/api/jobs/upload", method="POST", data=data,
                   content_type="multipart/form-data", **kwargs)


@pytest.fixture
def employee_app(tmp_path):
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    lan = LanAccess(f"{HOST}/24", inputs, tmp_path / "outputs", code=CODE)
    application = create_app(tmp_path / "state", token=TOKEN, lan=lan,
                             settings_dir=tmp_path / "shared-settings")
    application.config.update(TESTING=True, HSD_PORT=8805)
    yield application
    application.config["HSD_MANAGER"].close()


@pytest.fixture
def captured_jobs(employee_app, monkeypatch):
    manager = employee_app.config["HSD_MANAGER"]
    calls = []

    def create(payload, *, owner_id=None, downloadable=False, display_names=None, input_digests=None):
        identifier = f"employee{len(calls) + 1}"
        captured = {"payload": dict(payload), "owner_id": owner_id,
                    "downloadable": downloadable, "display_names": display_names, "input_digests": input_digests}
        calls.append(captured)
        work = manager.data_dir / "jobs" / identifier
        work.mkdir(parents=True)
        manager.jobs[identifier] = {
            "id": identifier, "status": "ready", "progress": {}, "error": None,
            "start_number": payload["start_number"], "prefix": "HSD",
            "sheet_name": "Generated", "workbook_name": display_names["workbook_name"],
            "source_name": display_names["source_name"], "rows": [], "files": [],
            "stats": {}, "warnings": [], "output_dir": None, "report": None,
            "output_target": payload["output_root"], "revision": 0,
            "_owner_id": owner_id, "_downloadable": downloadable,
            "_workbook_path": payload["workbook_path"], "_source_path": payload["source_path"],
            "_output_root": payload["output_root"], "_work_dir": str(work),
        }
        return identifier

    monkeypatch.setattr(manager, "create", create)
    return calls


def test_upload_requires_lan_login_before_accepting_files(employee_app, captured_jobs):
    response = upload(employee_app.test_client())
    assert response.status_code == 401
    assert captured_jobs == []
    assert not list((employee_app.config["HSD_MANAGER"].data_dir / "uploads").glob("*"))


@pytest.mark.parametrize("token", [None, "wrong"])
def test_upload_requires_current_application_token(employee_app, captured_jobs, token):
    client = employee_app.test_client()
    login(client)
    assert upload(client, token=token).status_code == 403
    assert captured_jobs == []


@pytest.mark.parametrize("origin", [None, "https://evil.invalid", f"http://{HOST}:8806", "null"])
def test_upload_requires_same_origin(employee_app, captured_jobs, origin):
    client = employee_app.test_client()
    login(client)
    assert upload(client, origin=origin).status_code == 403
    assert captured_jobs == []


def test_upload_stores_fixed_private_filenames_and_tags_browser_owner(employee_app, captured_jobs):
    client = employee_app.test_client()
    login(client)
    response = upload(client, workbook_name="../../outside/员工.xlsx", source_name="C:/private/原稿.zip", start="23")
    assert response.status_code == 200, response.get_data(as_text=True)
    assert response.json["id"] == "employee1"
    call = captured_jobs[0]
    payload = call["payload"]
    upload_root = (employee_app.config["HSD_MANAGER"].data_dir / "uploads").resolve()
    workbook, source = Path(payload["workbook_path"]), Path(payload["source_path"])
    assert workbook.name == "workbook.xlsx" and source.name == "source.zip"
    assert workbook.parent == source.parent and workbook.parent.parent == upload_root
    assert workbook.read_bytes() == workbook_bytes()
    assert zipfile.is_zipfile(source)
    assert payload["start_number"] == 23
    assert call["owner_id"] and call["downloadable"] is True
    assert call["display_names"]["workbook_name"] == "员工.xlsx"
    assert call["display_names"]["source_name"] == "原稿.zip"
    assert set(call["display_names"]) == {"workbook_name", "source_name"}
    assert call["input_digests"] == {"workbook": hashlib.sha256(workbook.read_bytes()).hexdigest(),
                                     "source": hashlib.sha256(source.read_bytes()).hexdigest()}
    assert "_input_digests" not in request(client, "/api/jobs/employee1").get_data(as_text=True)
    assert not (upload_root.parent.parent / "outside").exists()


@pytest.mark.parametrize("fields", [
    {"workbook": False}, {"source": False},
    {"workbook_name": "input.csv"}, {"source_name": "originals.rar"},
    {"workbook": b"not a zip"}, {"source": b"not a zip"},
    {"workbook": zip_bytes({"picture.png": b"not a workbook"})},
    {"start": "0"}, {"start": "10000"}, {"start": "1.5"}, {"start": ""},
])
def test_invalid_upload_is_rejected_and_removed(employee_app, captured_jobs, fields):
    client = employee_app.test_client()
    login(client)
    response = upload(client, **fields)
    assert response.status_code == 400, response.get_data(as_text=True)
    assert captured_jobs == []
    assert not list((employee_app.config["HSD_MANAGER"].data_dir / "uploads").glob("*"))


def test_manager_creation_failure_removes_uploaded_files(employee_app, captured_jobs, monkeypatch):
    client = employee_app.test_client()
    login(client)
    manager = employee_app.config["HSD_MANAGER"]

    def fail(payload, **kwargs):
        assert Path(payload["workbook_path"]).is_file()
        assert Path(payload["source_path"]).is_file()
        raise ValueError("synthetic create failure")

    monkeypatch.setattr(manager, "create", fail)
    response = upload(client)
    assert response.status_code == 400 and "synthetic create failure" in response.json["error"]
    assert not list((manager.data_dir / "uploads").glob("*"))


def test_only_upload_endpoint_accepts_multipart(employee_app, captured_jobs):
    client = employee_app.test_client()
    login(client)
    for path in ("/api/jobs", "/api/lan/logout", "/api/jobs/missing/export"):
        response = request(client, path, method="POST", data={"start_number": "1"},
                           content_type="multipart/form-data")
        assert response.status_code == 400
    assert captured_jobs == []


def test_remote_cannot_import_paths_on_the_host(employee_app, captured_jobs):
    client = employee_app.test_client()
    login(client)
    response = request(client, "/api/jobs", method="POST", payload={
        "workbook_path": "C:/private/batch.xlsx", "source_path": "C:/private/originals",
        "output_root": "C:/private/results", "start_number": 1})
    assert response.status_code == 403 and captured_jobs == []


@pytest.mark.parametrize("path,method", [
    ("/api/jobs/employee1", "GET"),
    ("/api/jobs/employee1/image/row/r2", "GET"),
    ("/api/jobs/employee1/image/file/f2?size=thumb", "GET"),
    ("/api/jobs/employee1/download", "GET"),
    ("/api/jobs/employee1/resolve", "POST"),
    ("/api/jobs/employee1/undo", "POST"),
    ("/api/jobs/employee1/export", "POST"),
    ("/api/jobs/employee1/ai-review", "POST"),
])
def test_other_browser_cannot_read_or_modify_a_job(employee_app, captured_jobs, path, method):
    first, other = employee_app.test_client(), employee_app.test_client()
    login(first)
    assert upload(first).status_code == 200
    login(other)
    assert request(first, "/api/jobs/employee1").status_code == 200
    response = request(other, path, method=method, payload={} if method == "POST" else None)
    assert response.status_code == 404


def test_host_browser_does_not_implicitly_own_employee_jobs(employee_app, captured_jobs):
    employee, host = employee_app.test_client(), employee_app.test_client()
    login(employee)
    assert upload(employee).status_code == 200
    assert request(host, "/api/config", address=HOST).status_code == 200
    assert request(host, "/api/jobs/employee1", address=HOST).status_code == 404


def test_browser_owner_persists_but_is_different_for_each_login(employee_app, captured_jobs):
    first, other = employee_app.test_client(), employee_app.test_client()
    login(first)
    assert upload(first).status_code == 200
    assert request(first, "/api/config").status_code == 200
    assert upload(first).status_code == 200
    login(other)
    assert upload(other).status_code == 200
    assert captured_jobs[0]["owner_id"] == captured_jobs[1]["owner_id"]
    assert captured_jobs[0]["owner_id"] != captured_jobs[2]["owner_id"]
    assert request(first, "/api/lan/logout", method="POST", payload={}).status_code == 200
    login(first)
    assert request(first, "/api/jobs/employee1").status_code == 404


def test_config_restores_only_the_current_browsers_job(employee_app, captured_jobs):
    first, second, empty = [employee_app.test_client() for _ in range(3)]
    for client in (first, second, empty):
        login(client)
    assert upload(first).status_code == 200
    assert upload(second).status_code == 200
    assert request(first, "/api/config").json["active_job_id"] == "employee1"
    assert request(second, "/api/config").json["active_job_id"] == "employee2"
    assert request(empty, "/api/config").json.get("active_job_id") is None


def test_uploaded_snapshot_does_not_disclose_host_storage_paths(employee_app, captured_jobs):
    client = employee_app.test_client()
    login(client)
    assert upload(client).status_code == 200
    response = request(client, "/api/jobs/employee1")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    for value in captured_jobs[0]["payload"].values():
        if isinstance(value, str):
            assert value not in body
            assert value.replace("\\", "\\\\") not in body
    assert response.json["workbook_name"] == "员工表格.xlsx"
    assert response.json["source_name"] == "员工原稿.zip"
    assert "_owner_id" not in response.json


def test_employee_error_warning_and_nested_diagnostics_do_not_disclose_host_paths(employee_app, captured_jobs):
    client = employee_app.test_client()
    login(client)
    assert upload(client).status_code == 200
    manager = employee_app.config["HSD_MANAGER"]
    job = manager.jobs["employee1"]
    workbook = job["_workbook_path"]
    source = job["_source_path"]
    work = str(Path(job["_work_dir"]) / "private-preview.png")
    output = str(Path(job["_output_root"]) / "private-result")
    job["error"] = "无法读取 " + workbook
    job["warnings"] = ["源文件 " + source.replace("\\", "/"), "缓存 " + work.replace("\\", "\\\\")]
    job["rows"] = [{"id": "r2", "diagnostics": {"detail": "结果 " + output}}]
    response = request(client, "/api/jobs/employee1")
    assert response.status_code == 200
    assert "任务文件" in response.json["error"]
    body = response.get_data(as_text=True)
    for private in (str(manager.data_dir.resolve()), workbook, source, work, output):
        assert private not in body
        assert private.replace("\\", "/") not in body
        assert private.replace("\\", "\\\\") not in body
    assert "private-preview.png" in response.json["warnings"][1]
    assert "private-result" in response.json["rows"][0]["diagnostics"]["detail"]


def test_download_requires_finished_export_and_cannot_choose_a_path(employee_app, captured_jobs, tmp_path):
    client = employee_app.test_client()
    login(client)
    assert upload(client).status_code == 200
    private = tmp_path / "private-secret.zip"
    private.write_bytes(b"must not be downloadable")
    for suffix in ("", "?path=" + str(private), "?filename=" + str(private)):
        response = request(client, "/api/jobs/employee1/download" + suffix)
        assert response.status_code in {400, 404, 409}
        assert private.read_bytes() not in response.data


def test_remote_uses_host_ai_configuration_without_receiving_credentials(employee_app, monkeypatch):
    client = employee_app.test_client()
    login(client)
    secret = "synthetic-secret-not-a-real-key"
    monkeypatch.setattr(employee_app.config["HSD_MANAGER"], "ai_config", lambda: {
        "enabled": True, "configured": True, "model": "synthetic-vision-model",
        "mode": "advisory", "api_key": secret, "key_path": "C:/private/key", "validation": {"private": True}})
    response = request(client, "/api/ai/settings")
    assert response.status_code == 200
    assert response.json == {"enabled": True, "configured": True,
                             "model": "synthetic-vision-model", "mode": "advisory"}
    assert secret not in response.get_data(as_text=True)
    assert request(client, "/api/ai/settings", method="POST", payload={"api_key": "replace"}).status_code == 403


def completed_download(app, client):
    from hsd_tool.service import sha256

    assert upload(client).status_code == 200
    job = app.config["HSD_MANAGER"].jobs["employee1"]
    asset = Path(job["_work_dir"]) / "result.zip"
    asset.write_bytes(zip_bytes({"已编号AI/HSD0023.ai": b"synthetic-original", "对应关系.csv": "synthetic mapping"}))
    job.update(status="done", _download_path=str(asset), _download_sha256=sha256(asset))
    return job, asset


def test_finished_result_is_downloaded_by_its_owner_without_a_post_token(employee_app, captured_jobs):
    client = employee_app.test_client()
    login(client)
    _, asset = completed_download(employee_app, client)
    snapshot = request(client, "/api/jobs/employee1").json
    assert snapshot["download_ready"] is True
    response = request(client, "/api/jobs/employee1/download", token=None)
    assert response.status_code == 200
    assert response.data == asset.read_bytes()
    assert "attachment" in response.headers["Content-Disposition"]
    assert "zip" in response.headers["Content-Type"]
    assert response.headers["Cache-Control"] == "no-store"
    with zipfile.ZipFile(BytesIO(response.data)) as archive:
        assert archive.read("已编号AI/HSD0023.ai") == b"synthetic-original"


def test_finished_download_still_requires_the_owner_and_login(employee_app, captured_jobs):
    owner, other, anonymous = [employee_app.test_client() for _ in range(3)]
    login(owner)
    _, asset = completed_download(employee_app, owner)
    login(other)
    assert request(other, "/api/jobs/employee1/download").status_code == 404
    assert request(anonymous, "/api/jobs/employee1/download").status_code == 401
    assert request(employee_app.test_client(), "/api/jobs/employee1/download", address=HOST).status_code == 404
    assert request(owner, "/api/jobs/employee1/download").data == asset.read_bytes()


def test_modified_download_archive_is_rejected(employee_app, captured_jobs):
    client = employee_app.test_client()
    login(client)
    _, asset = completed_download(employee_app, client)
    asset.write_bytes(b"replaced-after-export")
    response = request(client, "/api/jobs/employee1/download")
    assert response.status_code in {400, 404, 409}
    assert asset.read_bytes() not in response.data


def test_download_cannot_follow_a_private_path_even_with_a_matching_digest(employee_app, captured_jobs, tmp_path):
    from hsd_tool.service import sha256

    client = employee_app.test_client()
    login(client)
    job, _ = completed_download(employee_app, client)
    private = tmp_path / "private.zip"
    private.write_bytes(b"private content")
    job.update(_download_path=str(private), _download_sha256=sha256(private))
    response = request(client, "/api/jobs/employee1/download")
    assert response.status_code in {400, 404, 409}
    assert private.read_bytes() not in response.data


def test_download_cannot_follow_a_link_to_another_directory(employee_app, captured_jobs, tmp_path):
    from hsd_tool.service import sha256

    client = employee_app.test_client()
    login(client)
    job, asset = completed_download(employee_app, client)
    private = tmp_path / "private.zip"
    private.write_bytes(b"private symlink content")
    asset.unlink()
    try:
        asset.symlink_to(private)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"Symlink creation unavailable: {exc}")
    job["_download_sha256"] = sha256(private)
    response = request(client, "/api/jobs/employee1/download")
    assert response.status_code in {400, 404, 409}
    assert private.read_bytes() not in response.data


def test_upload_configuration_explicitly_has_no_file_or_total_byte_limit(employee_app, captured_jobs):
    client = employee_app.test_client()
    login(client)
    assert request(client, "/api/config").json["access"]["upload_limits"] == {
        "workbook_bytes": None, "source_bytes": None, "total_bytes": None}
    assert upload(client).status_code == 200


def test_json_requests_still_have_a_small_body_limit(employee_app, captured_jobs):
    client = employee_app.test_client()
    login(client)
    response = request(client, "/api/lan/logout", method="POST", payload={"oversized": "x" * (65 * 1024)})
    assert response.status_code == 413
    assert response.is_json and response.json.get("error")
    assert captured_jobs == []
    assert not list((employee_app.config["HSD_MANAGER"].data_dir / "uploads").glob("*"))


@pytest.mark.parametrize("field", ["input_digests", "_input_digests"])
def test_upload_digest_cannot_be_supplied_through_json_or_form(employee_app, captured_jobs, field):
    client = employee_app.test_client()
    login(client)
    response = request(client, "/api/jobs", method="POST", address=HOST, payload={field: {"workbook": "0" * 64, "source": "1" * 64}})
    assert response.status_code == 400
    data = {"start_number": "1", field: '{"workbook":"forged"}',
            "workbook": (BytesIO(workbook_bytes()), "test.xlsx"),
            "source": (BytesIO(zip_bytes({"pattern.ai": b"synthetic-ai"})), "test.zip")}
    response = request(client, "/api/jobs/upload", method="POST", data=data, content_type="multipart/form-data")
    assert response.status_code == 400
    assert captured_jobs == []
    assert not list((employee_app.config["HSD_MANAGER"].data_dir / "uploads").glob("*"))


@pytest.mark.parametrize("source", [
    zip_bytes({}), zip_bytes({"picture.png": b"not an AI original"}),
    zip_bytes({"../escaped.ai": b"synthetic-ai"}),
    zip_bytes({"/absolute.ai": b"synthetic-ai"}),
    zip_bytes({"C:/outside/escaped.ai": b"synthetic-ai"}),
])
def test_unusable_or_escaping_source_archive_is_rejected_before_job_creation(employee_app, captured_jobs, source):
    client = employee_app.test_client()
    login(client)
    response = upload(client, source=source)
    assert response.status_code == 400
    assert captured_jobs == []
    assert not list((employee_app.config["HSD_MANAGER"].data_dir / "uploads").glob("*"))


@pytest.mark.parametrize("extra", ["duplicate_workbook", "duplicate_start", "output_path", "unexpected_file"])
def test_ambiguous_or_unexpected_form_parts_are_rejected(employee_app, captured_jobs, extra):
    client = employee_app.test_client()
    login(client)
    data = MultiDict([
        ("workbook", (BytesIO(workbook_bytes()), "generated.xlsx")),
        ("source", (BytesIO(zip_bytes({"pattern.ai": b"synthetic-ai"})), "generated.zip")),
        ("start_number", "1"),
    ])
    if extra == "duplicate_workbook":
        data.add("workbook", (BytesIO(workbook_bytes()), "different.xlsx"))
    elif extra == "duplicate_start":
        data.add("start_number", "2")
    elif extra == "output_path":
        data.add("output_root", "C:/private/output")
    else:
        data.add("key", (BytesIO(b"synthetic-not-a-real-key"), "credentials.txt"))
    response = request(client, "/api/jobs/upload", method="POST", data=data,
                       content_type="multipart/form-data")
    assert response.status_code == 400
    assert captured_jobs == []
    assert not list((employee_app.config["HSD_MANAGER"].data_dir / "uploads").glob("*"))


def test_interrupted_multipart_body_does_not_leave_a_task_or_upload_directory(employee_app, captured_jobs):
    client = employee_app.test_client()
    login(client)
    boundary = "hsd-synthetic-interrupted-upload"
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"workbook\"; filename=\"test.xlsx\"\r\n"
            "Content-Type: application/octet-stream\r\n\r\n").encode() + workbook_bytes()
    expected_length = len(body) + 1024
    response = client.open("/api/jobs/upload", method="POST", base_url=ORIGIN,
        headers={"Origin": ORIGIN, "X-HSD-Token": TOKEN,
                 "Content-Type": f"multipart/form-data; boundary={boundary}"},
        environ_overrides={"REMOTE_ADDR": REMOTE, "wsgi.input": BytesIO(body),
                           "CONTENT_LENGTH": str(expected_length)})
    assert response.status_code == 400
    assert captured_jobs == []
    assert not list((employee_app.config["HSD_MANAGER"].data_dir / "uploads").glob("*"))
