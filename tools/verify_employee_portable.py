"""Exercise two employee sessions against an isolated real Windows portable build.

Only generated artwork is used. DeepSeek is disabled in a new settings directory;
the user's saved credentials and existing server processes are never accessed.
"""
from __future__ import annotations

import argparse
import hashlib
import http.cookiejar
import ipaddress
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
import xml.etree.ElementTree as ET
import zipfile
from acceptance_records import read_export_record
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


class Browser:
    def __init__(self, base):
        self.base = base
        self.token = None
        self.cookies = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}), urllib.request.HTTPCookieProcessor(self.cookies))

    def raw(self, path, *, data=None, content_type=None):
        headers = {}
        if data is not None:
            headers.update(Origin=self.base, **{"Content-Type": content_type})
            if self.token:
                headers["X-HSD-Token"] = self.token
        request = urllib.request.Request(self.base + path, data=data, headers=headers)
        with self.opener.open(request, timeout=60) as response:
            return response.read()

    def request(self, path, payload=None):
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        return json.loads(self.raw(path, data=data, content_type="application/json"))

    def login(self, code):
        self.request("/api/lan/login", {"code": code})
        html = self.raw("/").decode("utf-8")
        match = re.search(r'window\.HSD_TOKEN\s*=\s*("[^"\r\n]*")', html)
        assert match, "The actual app page did not contain its CSRF bootstrap"
        self.token = json.loads(match.group(1))

    def upload(self, workbook, source, start):
        boundary = "hsd-acceptance-" + uuid.uuid4().hex
        parts = []
        for field, filename, mime, data in (
                ("start_number", None, None, str(start).encode("ascii")),
                ("workbook", "employee-table.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", workbook),
                ("source", "employee-artwork.zip", "application/zip", source)):
            disposition = f'Content-Disposition: form-data; name="{field}"'
            if filename:
                disposition += f'; filename="{filename}"'
            header = "--" + boundary + "\r\n" + disposition + "\r\n"
            if mime:
                header += "Content-Type: " + mime + "\r\n"
            parts.extend((header.encode("ascii") + b"\r\n", data, b"\r\n"))
        parts.append(("--" + boundary + "--\r\n").encode("ascii"))
        return json.loads(self.raw("/api/jobs/upload", data=b"".join(parts),
            content_type="multipart/form-data; boundary=" + boundary))["id"]


def generated_inputs(directory):
    import pymupdf
    from PIL import Image, ImageDraw
    from test_workbook import image_cell, make_book

    directory.mkdir()
    image = Image.new("RGB", (900, 140), (250, 250, 250))
    draw = ImageDraw.Draw(image)
    palette = [(150, 60, 40), (236, 232, 232), (58, 118, 198), (96, 218, 238)]
    for index, x in enumerate(range(0, 900, 36)):
        draw.rectangle((x, 0, min(x + 36, 900), 140), fill=palette[index % len(palette)])
    stream = BytesIO()
    image.save(stream, "PNG")
    rows = '<row r="2"><c r="A2" s="1"/>' + image_cell(2) + "</row>"
    workbook = make_book(directory, rows, image_data=stream.getvalue(), second_sheet=True)
    # The workbook test builder intentionally omits the upload signature part.
    with zipfile.ZipFile(workbook, "a", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml",
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Default Extension="png" ContentType="image/png"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '</Types>')
    original_ai = directory / "pattern.ai"
    with pymupdf.open() as document:
        page = document.new_page(width=900, height=140)
        page.insert_image(page.rect, stream=stream.getvalue())
        document.save(original_ai)
    source = directory / "artwork.zip"
    with zipfile.ZipFile(source, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(original_ai, "pattern.ai")
    return workbook, source, original_ai


def assert_404(browser, path):
    try:
        browser.raw(path)
    except urllib.error.HTTPError as error:
        assert error.code == 404, f"Cross-session route returned HTTP {error.code}, expected 404"
    else:
        raise AssertionError("Another session's job was accessible")


def wait_job(browser, identifier, observed, *, timeout=240):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = browser.request("/api/jobs/" + identifier)
        observed.add(job["status"])
        if job["status"] not in {"queued", "importing", "matching", "ai_review", "exporting"}:
            return job
        time.sleep(.1)
    raise AssertionError("Employee processing timed out")


def check_download(payload, original_workbook, original_ai, expected_number):
    with zipfile.ZipFile(BytesIO(payload)) as archive:
        assert archive.testzip() is None, "Downloaded ZIP CRC failed"
        names = archive.namelist()
        assert all(not name.startswith(("/", "\\")) and ".." not in Path(name).parts for name in names)
        workbooks = [name for name in names if name.endswith(".xlsx")]
        ai_files = [name for name in names if name.endswith(".ai")]
        assert len(workbooks) == len(ai_files) == 1
        assert ai_files[0].endswith("/已编号AI/" + expected_number + ".ai")
        assert hashlib.sha256(archive.read(ai_files[0])).hexdigest() == digest(original_ai)
        assert len(names) == 2 and len(set(names)) == 2, 'Only one numbered AI and one Excel may be downloaded'
        assert not any("/matching/" in name or "/uploads/" in name or "settings" in name.lower() for name in names)
        workbook_data = archive.read(workbooks[0])
    with zipfile.ZipFile(original_workbook) as original, zipfile.ZipFile(BytesIO(workbook_data)) as numbered:
        assert original.namelist() == numbered.namelist()
        assert original.comment == numbered.comment
        changed = [name for name in original.namelist() if original.read(name) != numbered.read(name)]
        assert changed == ["xl/worksheets/sheet1.xml"], "Unexpected WPS workbook part changed"
        namespace = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        worksheet = ET.fromstring(numbered.read(changed[0]))
        assert worksheet.find('.//s:c[@r="A2"]/s:is/s:t', namespace).text == expected_number
        cell = rb'<c\b[^>]*\br="A2"[^>]*?(?:\s*/>|>.*?</c>)'
        before, count_before = re.subn(cell, b"TARGET_CELL", original.read(changed[0]), count=1, flags=re.S)
        after, count_after = re.subn(cell, b"TARGET_CELL", numbered.read(changed[0]), count=1, flags=re.S)
        assert count_before == count_after == 1 and before == after


def verify(args):
    from hsd_tool import __version__
    from build_manifest import inputs

    assert os.name == "nt", "This acceptance targets Windows portable executables"
    executable = args.exe.resolve(strict=True)
    manifest_path = executable.parent / "构建校验.json"
    manifest = json.loads(manifest_path.read_text("utf-8"))
    assert manifest["version"] == __version__
    assert manifest["inputs"] == inputs(ROOT), "Production inputs changed; rebuild first"
    assert all(digest(executable.parent / name) == value for name, value in manifest["runtime"].items())
    work = args.work.absolute()
    assert not work.is_symlink() and (not work.exists() or (work.is_dir() and not any(work.iterdir()))), "--work must be a new empty directory"
    work.mkdir(parents=True, exist_ok=True)
    state, settings = work / "state", work / "ai-disabled"
    host_inputs, host_outputs = work / "host_inputs", work / "host_outputs"
    host_inputs.mkdir()
    host_outputs.mkdir()
    settings.mkdir()
    workbook, source, original_ai = generated_inputs(work / "generated")
    original_hashes = {path: digest(path) for path in (workbook, source, original_ai)}
    base = f"http://{args.host}:{args.port}"
    # Fail before launching if the requested isolated port already belongs to anyone.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind((args.host, args.port))
    process = subprocess.Popen([str(executable), "--no-browser", "--port", str(args.port),
        "--data-dir", str(state), "--settings-dir", str(settings), "--lan", f"{args.host}/{args.prefix}",
        "--lan-input-root", str(host_inputs), "--lan-output-root", str(host_outputs)],
        creationflags=subprocess.CREATE_NO_WINDOW, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    browsers = [Browser(base), Browser(base)]
    owned_instance = False
    summary = {"ok": False, "version": __version__, "validation_scope":
        "Generated artwork, two independent cookie sessions, real frozen HTTP server via host LAN address; no independent business accuracy or second physical PC claim.",
        "real_api_calls": 0, "user_credentials_accessed": False}
    started = time.monotonic()
    try:
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            assert process.poll() is None, "The owned portable process exited before startup"
            try:
                instance = json.loads((state / "instance.json").read_text("utf-8"))
                health = browsers[0].request("/api/health")
                assert instance["url"] == base and instance["instance"] == health["instance"]
                owned_instance = True
                break
            except (OSError, ValueError, urllib.error.URLError):
                time.sleep(.25)
        assert owned_instance, "The isolated portable instance did not become ready"
        runtime = health["runtime"]
        assert runtime["frozen"] is True and runtime["version"] == __version__
        assert runtime["executable_sha256"] == digest(executable)
        assert runtime["build_manifest_sha256"] == digest(manifest_path)
        for browser in browsers:
            browser.login(instance["lan_access_code"])
            ai = browser.request("/api/ai/settings")
            assert ai["enabled"] is False and ai["configured"] is False
        identifiers, states = [], [set(), set()]
        for browser, start in zip(browsers, (7, 31)):
            identifiers.append(browser.upload(workbook.read_bytes(), source.read_bytes(), start))
        assert identifiers[0] != identifiers[1]
        uploads_before = {path: digest(path) for path in (state / "uploads").rglob("*")
            if path.is_file() and path.name in {"workbook.xlsx", "source.zip"}}
        assert len(uploads_before) == 4
        jobs = [wait_job(browser, identifier, observed)
            for browser, identifier, observed in zip(browsers, identifiers, states)]
        for job, number in zip(jobs, ("HSD0007", "HSD0031")):
            assert job["status"] == "ready", "Generated employee batch failed"
            assert len(job["rows"]) == len(job["files"]) == 1
            assert job["stats"]["auto"] == 1 and job["stats"]["confirmed"] == 0
            assert job["stats"]["needs_attention"] == 0 and job["stats"]["ai_auto"] == 0
            assert job["rows"][0]["planned_number"] == number
        isolation_checks = 0
        for index, browser in enumerate(browsers):
            other, other_job = identifiers[1 - index], jobs[1 - index]
            for route in (f"/api/jobs/{other}",
                    f"/api/jobs/{other}/image/row/{other_job['rows'][0]['id']}",
                    f"/api/jobs/{other}/image/file/{other_job['files'][0]['id']}",
                    f"/api/jobs/{other}/download"):
                assert_404(browser, route)
                isolation_checks += 1
        for browser, identifier, job in zip(browsers, identifiers, jobs):
            browser.request(f"/api/jobs/{identifier}/export", {"expected_revision": job["revision"]})
        results = [wait_job(browser, identifier, observed)
            for browser, identifier, observed in zip(browsers, identifiers, states)]
        downloads = []
        for index, (browser, identifier, result, number) in enumerate(zip(
                browsers, identifiers, results, ("HSD0007", "HSD0031")), 1):
            assert result["status"] == "done" and result["download_ready"], "Employee result did not finish"
            assert result["report"]["new_numbers"] == result["report"]["exported"] == 1
            assert result["report"]["pending"] == 0
            payload = browser.raw(f"/api/jobs/{identifier}/download")
            check_download(payload, workbook, original_ai, number)
            record = read_export_record(state, identifier)
            assert record['exported'] == record['new_numbers'] == 1 and record['pending'] == 0
            assert len(record['mapping']) == 1 and record['mapping'][0]['sha256'] == digest(original_ai)
            target = work / f"employee-{index}-result.zip"
            target.write_bytes(payload)
            downloads.append({"employee": index, "number": number, "bytes": len(payload),
                "sha256": digest(target), "auto": 1, "manual_confirmations": 0,
                "observed_states": sorted(states[index - 1])})
        # Verify ownership after the archive actually exists, not just while not ready.
        for index, browser in enumerate(browsers):
            assert_404(browser, f"/api/jobs/{identifiers[1-index]}/download")
            isolation_checks += 1
            assert browser.request("/api/ai/usage")["requests"] == 0
        assert all(digest(path) == value for path, value in original_hashes.items())
        assert all(digest(path) == value for path, value in uploads_before.items())
        assert not (settings / "ai_settings.json").exists()
        summary.update(ok=True, runtime=runtime, downloads=downloads,
            cross_session_denials=isolation_checks, source_inputs_unchanged=True,
            stored_uploads_unchanged=True, wps_other_parts_unchanged=True,
            original_ai_bytes_verified=True, zero_manual_reviews=True,
            queue_observed=any("queued" in observed for observed in states),
            elapsed_seconds=round(time.monotonic() - started, 3))
    except Exception as error:
        summary["failure_type"] = type(error).__name__
        raise
    finally:
        if owned_instance and process.poll() is None:
            try:
                browsers[0].request("/api/shutdown", {})
                process.wait(timeout=20)
            except (OSError, ValueError, urllib.error.URLError, subprocess.TimeoutExpired):
                pass
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
        summary["owned_process_exit_code"] = process.returncode
        summary["owned_process_stopped"] = process.poll() is not None
        (work / "验收结果.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), "utf-8")
    print("PASS " + json.dumps({key: summary[key] for key in (
        "version", "downloads", "cross_session_denials", "queue_observed", "elapsed_seconds",
        "owned_process_exit_code", "real_api_calls")}, ensure_ascii=False), flush=True)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--host", default="192.168.0.160")
    parser.add_argument("--prefix", type=int, default=24)
    parser.add_argument("--port", type=int, default=8808)
    parser.add_argument("--work", type=Path, required=True)
    args = parser.parse_args()
    ipaddress.IPv4Interface(f"{args.host}/{args.prefix}")
    assert 1024 <= args.port <= 65535, "Use an isolated unprivileged port"
    verify(args)


if __name__ == "__main__":
    main()
