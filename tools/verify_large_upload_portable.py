"""Stream real large synthetic inputs through an isolated Windows portable build.

This creates a >100 MiB XLSX, a >256 MiB PDF-compatible AI, and a real
>2 GiB ZIP64 container with a zero preamble. No GiB-sized bytes object is built.
Only a new workspace tmp directory and this tool's own process are touched.
The user's settings, business samples, existing ports and DeepSeek are not used.
"""
from __future__ import annotations

import argparse
import hashlib
import http.client
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from verify_employee_portable import Browser, assert_404, digest, generated_inputs, wait_job

CHUNK = 1024 * 1024
MIB = 1024 ** 2
GIB = 1024 ** 3
XLSX_PADDING = 101 * MIB
AI_WHITESPACE = 257 * MIB
ZIP_PREAMBLE = 2 * GIB + 4 * MIB


def copy_blocks(source, destination):
    copied = 0
    while block := source.read(CHUNK):
        destination.write(block)
        copied += len(block)
    return copied


def member_digest(archive, name):
    hasher = hashlib.sha256()
    with archive.open(name) as source:
        while block := source.read(CHUNK):
            hasher.update(block)
    return hasher.hexdigest()


def repeat_to(stream, value, count):
    block = value * CHUNK
    while count:
        take = min(count, len(block))
        stream.write(block[:take])
        count -= take


def generate_large_inputs(work):
    import pymupdf

    seed_workbook, _, seed_ai = generated_inputs(work / "seed")
    target = work / "generated"
    target.mkdir()
    workbook, original_ai, source = target / "large.xlsx", target / "large.ai", target / "large.zip"
    shutil.copyfile(seed_workbook, workbook)
    # A valid unused XML part uses the fixture's existing XML content type.
    # Its ZIP_STORED payload is real on-disk data, not a claimed HTTP length.
    with zipfile.ZipFile(workbook, "a", allowZip64=True) as archive:
        info = zipfile.ZipInfo("hsd-synthetic-acceptance/padding.xml")
        info.compress_type = zipfile.ZIP_STORED
        with archive.open(info, "w") as stream:
            stream.write(b"<synthetic><!--")
            repeat_to(stream, b" ", XLSX_PADDING)
            stream.write(b"--></synthetic>")
    assert workbook.stat().st_size > 100 * MIB

    assert seed_ai.stat().st_size < MIB, "The seed is deliberately small"
    seed = seed_ai.read_bytes()
    start = re.search(rb"startxref\s+([0-9]+)\s+%%EOF\s*$", seed)
    assert start, "The generated PDF needs a conventional cross-reference table"
    xref = int(start.group(1))
    assert seed[xref:xref + 4] == b"xref"
    tail, changes = re.subn(rb"startxref\s+[0-9]+\s+%%EOF\s*$",
                            b"startxref\n" + str(xref + AI_WHITESPACE).encode() + b"\n%%EOF\n",
                            seed[xref:])
    assert changes == 1
    with original_ai.open("xb") as stream:
        stream.write(seed[:xref])
        # Whitespace between PDF tokens is legal. Keeping startxref correct and
        # EOF at the actual end avoids relying on MuPDF repair of trailing data.
        repeat_to(stream, b" ", AI_WHITESPACE)
        stream.write(tail)
    assert original_ai.stat().st_size > 256 * MIB
    with pymupdf.open(seed_ai) as before, pymupdf.open(original_ai) as after:
        assert not after.is_repaired and after.page_count == before.page_count == 1
        assert before[0].get_pixmap().digest == after[0].get_pixmap().digest

    # A ZIP may have a self-extracting-style preamble. The gap reads as actual
    # zero bytes and is included in the upload iterator and source SHA256.
    # Large offsets produce real ZIP64 end records, not fake metadata lengths.
    with source.open("x+b") as stream:
        stream.seek(ZIP_PREAMBLE)
        stream.truncate()
        with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED,
                             compresslevel=6, allowZip64=True) as archive:
            info = zipfile.ZipInfo("large.ai")
            info.file_size = original_ai.stat().st_size
            info.compress_type = zipfile.ZIP_DEFLATED
            with archive.open(info, "w", force_zip64=True) as destination, original_ai.open("rb") as ai:
                assert copy_blocks(ai, destination) == info.file_size
    assert source.stat().st_size > 2 * GIB
    with zipfile.ZipFile(source) as archive:
        info = archive.getinfo("large.ai")
        assert info.header_offset == ZIP_PREAMBLE
        assert info.file_size == original_ai.stat().st_size
        assert member_digest(archive, info.filename) == digest(original_ai)
    with source.open("rb") as stream:
        stream.seek(-128, os.SEEK_END)
        footer = stream.read(128)
    assert b"PK\x06\x06" in footer and b"PK\x06\x07" in footer
    return workbook, source, original_ai


class MultipartStream:
    """Exact Content-Length plus reusable bounded file reads, never bytes.join."""
    def __init__(self, workbook, source, start):
        self.boundary = "hsd-large-acceptance-" + uuid.uuid4().hex
        self.parts = []
        for field, filename, mime, value in (
                ("start_number", None, None, str(start).encode("ascii")),
                ("workbook", "large.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", workbook),
                ("source", "large.zip", "application/zip", source)):
            header = f'--{self.boundary}\r\nContent-Disposition: form-data; name="{field}"'
            if filename:
                header += f'; filename="{filename}"'
            header += "\r\n"
            if mime:
                header += f"Content-Type: {mime}\r\n"
            self.parts.extend((header.encode("ascii") + b"\r\n", value, b"\r\n"))
        self.parts.append(f"--{self.boundary}--\r\n".encode("ascii"))
        self.length = sum(part.stat().st_size if isinstance(part, Path) else len(part)
                          for part in self.parts)
        self.sent = 0

    def __iter__(self):
        self.sent = 0
        for part in self.parts:
            if isinstance(part, Path):
                with part.open("rb") as stream:
                    while block := stream.read(CHUNK):
                        self.sent += len(block)
                        yield block
            else:
                self.sent += len(part)
                yield part
        assert self.sent == self.length, "An input changed while constructing its HTTP body"

    def headers(self, browser):
        request = urllib.request.Request(browser.base + "/api/jobs/upload", data=b"")
        browser.cookies.add_cookie_header(request)
        return {"Origin": browser.base, "X-HSD-Token": browser.token,
                "Cookie": request.get_header("Cookie", ""),
                "Content-Type": "multipart/form-data; boundary=" + self.boundary,
                "Content-Length": str(self.length)}


def stream_upload(browser, workbook, source, start, *, timeout):
    body = MultipartStream(workbook, source, start)
    address = urllib.parse.urlsplit(browser.base)
    connection = http.client.HTTPConnection(address.hostname, address.port, timeout=timeout)
    try:
        connection.request("POST", "/api/jobs/upload", body=body, headers=body.headers(browser))
        response = connection.getresponse()
        payload = response.read(64 * 1024 + 1)
        assert len(payload) <= 64 * 1024, "Unexpectedly large upload response"
        data = json.loads(payload)
        assert response.status == 200 and data.get("id"), f"Upload failed with HTTP {response.status}"
        assert body.sent == body.length and body.sent > 2 * GIB
        return data["id"], body.sent
    finally:
        connection.close()


def interrupt_upload(browser, workbook, source, directory):
    body = MultipartStream(workbook, source, 1)
    address = urllib.parse.urlsplit(browser.base)
    connection = http.client.HTTPConnection(address.hostname, address.port, timeout=60)
    iterator = iter(body)
    baseline = set(directory.iterdir())
    observed = False
    try:
        connection.putrequest("POST", "/api/jobs/upload")
        for name, value in body.headers(browser).items():
            connection.putheader(name, value)
        connection.endheaders()
        for block in iterator:
            connection.send(block)
            if body.sent >= 2 * MIB:
                break
        # Observe a real partially written server stream before disconnecting.
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            current = set(directory.iterdir()) - baseline
            if any(part.stat().st_size > 0 for folder in current for part in folder.glob("part-*")):
                observed = True
                break
            time.sleep(.05)
        assert observed, "The interruption test never reached server-side file streaming"
        if connection.sock is not None:
            connection.sock.shutdown(socket.SHUT_RDWR)
    finally:
        iterator.close()
        connection.close()
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if set(directory.iterdir()) == baseline:
            assert browser.request("/api/config").get("active_job_id") is None
            return {"sent_bytes": body.sent, "declared_bytes": body.length,
                    "server_partial_stream_observed": True, "uncommitted_upload_cleaned": True}
        time.sleep(.1)
    raise AssertionError("The interrupted upload left an uncommitted directory")


def stream_download(browser, identifier, destination):
    request = urllib.request.Request(browser.base + f"/api/jobs/{identifier}/download")
    with browser.opener.open(request, timeout=300) as response, destination.open("xb") as output:
        copied = copy_blocks(response, output)
    assert copied == destination.stat().st_size
    return copied


def check_download_file(download, workbook, original_ai, numbered, expected):
    with zipfile.ZipFile(download) as archive:
        assert archive.testzip() is None
        names = archive.namelist()
        assert all(not name.startswith(("/", "\\")) and ".." not in Path(name).parts for name in names)
        ai_files = [name for name in names if name.endswith(".ai")]
        workbooks = [name for name in names if name.endswith(".xlsx")]
        assert len(ai_files) == len(workbooks) == 1
        assert ai_files[0].endswith("/已编号AI/" + expected + ".ai")
        assert archive.getinfo(ai_files[0]).file_size == original_ai.stat().st_size
        assert member_digest(archive, ai_files[0]) == digest(original_ai)
        assert any(name.endswith("/待处理清单.csv") for name in names)
        assert not any("/matching/" in name or "/uploads/" in name or "settings" in name.lower() for name in names)
        expected_size = archive.getinfo(workbooks[0]).file_size
        with archive.open(workbooks[0]) as source, numbered.open("xb") as output:
            assert copy_blocks(source, output) == expected_size
        assert numbered.stat().st_size == expected_size and expected_size > 100 * MIB
    with zipfile.ZipFile(workbook) as original, zipfile.ZipFile(numbered) as result:
        assert original.namelist() == result.namelist() and original.comment == result.comment
        changed = [name for name in original.namelist()
                   if member_digest(original, name) != member_digest(result, name)]
        assert changed == ["xl/worksheets/sheet1.xml"]
        assert original.getinfo("hsd-synthetic-acceptance/padding.xml").compress_type == zipfile.ZIP_STORED
        assert result.getinfo("hsd-synthetic-acceptance/padding.xml").file_size > 100 * MIB
        assert result.getinfo(changed[0]).file_size < 64 * 1024
        before, after = original.read(changed[0]), result.read(changed[0])
        namespace = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        worksheet = ET.fromstring(after)
        assert worksheet.find('.//s:c[@r="A2"]/s:is/s:t', namespace).text == expected
        cell = rb'<c\b[^>]*\br="A2"[^>]*?(?:\s*/>|>.*?</c>)'
        before, first = re.subn(cell, b"TARGET_CELL", before, count=1, flags=re.S)
        after, second = re.subn(cell, b"TARGET_CELL", after, count=1, flags=re.S)
        assert first == second == 1 and before == after


def verify(args):
    from hsd_tool import __version__
    from build_manifest import inputs

    assert os.name == "nt", "This checks the real Windows portable executable"
    assert args.port not in {8805, 8807, 8815}, "Do not use an existing employee service port"
    assert 1024 <= args.port <= 65535
    executable = args.exe.resolve(strict=True)
    manifest_path = executable.parent / "构建校验.json"
    manifest = json.loads(manifest_path.read_text("utf-8"))
    assert manifest["version"] == __version__ and manifest["inputs"] == inputs(ROOT)
    assert all(digest(executable.parent / name) == value for name, value in manifest["runtime"].items())
    work = args.work.absolute()
    assert not work.is_symlink() and not (hasattr(work, "is_junction") and work.is_junction())
    work = work.resolve()
    assert work.is_relative_to((ROOT / "tmp").resolve()) and work != (ROOT / "tmp").resolve()
    assert not work.exists() or (work.is_dir() and not any(work.iterdir())), "--work must be new and empty"
    work.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(work).free
    assert free >= 16 * GIB, "This large synthetic acceptance needs at least 16 GiB free"
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind((args.host, args.port))
    settings, state = work / "ai-disabled", work / "state"
    settings.mkdir()
    host_inputs, host_outputs = work / "host_inputs", work / "host_outputs"
    host_inputs.mkdir(); host_outputs.mkdir()
    summary = {"ok": False, "version": __version__, "real_api_calls": 0,
               "user_credentials_accessed": False, "free_bytes_before": free,
               "validation_scope": "Real Windows portable, actual >2GiB streamed synthetic payload; not a second physical PC or independent business accuracy check.",
               "timings": {}}
    process, owned, browser = None, False, Browser(f"http://{args.host}:{args.port}")
    started = time.monotonic()
    try:
        phase = time.monotonic()
        workbook, source, original_ai = generate_large_inputs(work)
        summary["timings"]["generate_seconds"] = round(time.monotonic() - phase, 3)
        original_hashes = {path: digest(path) for path in (workbook, source, original_ai)}
        summary["inputs"] = {path.name: {"bytes": path.stat().st_size, "sha256": value}
                             for path, value in original_hashes.items()}
        summary["zip64_zero_preamble_bytes"] = ZIP_PREAMBLE
        environment = os.environ.copy()
        environment.pop("DEEPSEEK_API_KEY", None)
        phase = time.monotonic()
        process = subprocess.Popen([str(executable), "--no-browser", "--port", str(args.port),
            "--data-dir", str(state), "--settings-dir", str(settings),
            "--lan", f"{args.host}/{args.prefix}", "--lan-input-root", str(host_inputs),
            "--lan-output-root", str(host_outputs)], env=environment,
            creationflags=subprocess.CREATE_NO_WINDOW, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            assert process.poll() is None, "The isolated owned process exited before startup"
            try:
                instance = json.loads((state / "instance.json").read_text("utf-8"))
                health = browser.request("/api/health")
                assert instance["url"] == browser.base and instance["instance"] == health["instance"]
                owned = True
                break
            except (OSError, ValueError, urllib.error.URLError):
                time.sleep(.25)
        assert owned
        runtime = health["runtime"]
        assert runtime["frozen"] and runtime["version"] == __version__
        assert runtime["executable_sha256"] == digest(executable)
        assert runtime["build_manifest_sha256"] == digest(manifest_path)
        browser.login(instance["lan_access_code"])
        ai = browser.request("/api/ai/settings")
        assert ai["enabled"] is False and ai["configured"] is False
        assert browser.request("/api/ai/usage")["requests"] == 0
        limits = browser.request("/api/config")["access"]["upload_limits"]
        assert limits == {"workbook_bytes": None, "source_bytes": None, "total_bytes": None}
        summary["timings"]["startup_seconds"] = round(time.monotonic() - phase, 3)
        summary["runtime"] = runtime
        phase = time.monotonic()
        summary["interrupted_upload"] = interrupt_upload(browser, workbook, source, state / "uploads")
        summary["timings"]["interrupt_and_cleanup_seconds"] = round(time.monotonic() - phase, 3)
        phase = time.monotonic()
        identifier, sent = stream_upload(browser, workbook, source, 7, timeout=args.timeout)
        summary["timings"]["upload_seconds"] = round(time.monotonic() - phase, 3)
        summary["actual_multipart_bytes_sent"] = sent
        phase = time.monotonic(); observed = set()
        job = wait_job(browser, identifier, observed, timeout=args.timeout)
        assert job["status"] == "ready", "The large generated inputs did not process successfully"
        assert job["stats"]["auto"] == 1 and job["stats"]["confirmed"] == job["stats"]["ai_auto"] == 0
        assert job["stats"]["needs_attention"] == 0 and job["rows"][0]["planned_number"] == "HSD0007"
        summary["timings"]["post_upload_processing_seconds"] = round(time.monotonic() - phase, 3)
        phase = time.monotonic()
        browser.request(f"/api/jobs/{identifier}/export", {"expected_revision": job["revision"]})
        result = wait_job(browser, identifier, observed, timeout=args.timeout)
        assert result["status"] == "done" and result["download_ready"]
        assert result["report"]["exported"] == result["report"]["new_numbers"] == 1
        assert result["report"]["pending"] == 0
        summary["timings"]["export_seconds"] = round(time.monotonic() - phase, 3)
        phase = time.monotonic(); download = work / "large-result.zip"
        summary["download_bytes"] = stream_download(browser, identifier, download)
        summary["timings"]["download_seconds"] = round(time.monotonic() - phase, 3)
        phase = time.monotonic()
        check_download_file(download, workbook, original_ai, work / "numbered-large.xlsx", "HSD0007")
        upload_directories = list((state / "uploads").iterdir())
        assert len(upload_directories) == 1
        assert digest(upload_directories[0] / "workbook.xlsx") == original_hashes[workbook]
        assert digest(upload_directories[0] / "source.zip") == original_hashes[source]
        assert all(digest(path) == value for path, value in original_hashes.items())
        stranger = Browser(browser.base); stranger.login(instance["lan_access_code"])
        assert_404(stranger, f"/api/jobs/{identifier}/download")
        assert browser.request("/api/ai/usage")["requests"] == 0
        assert not (settings / "ai_settings.json").exists()
        summary["timings"]["integrity_checks_seconds"] = round(time.monotonic() - phase, 3)
        summary.update(ok=True, auto=1, manual_confirmations=0, number="HSD0007",
            source_inputs_unchanged=True, stored_uploads_unchanged=True,
            wps_other_parts_unchanged=True, original_ai_bytes_verified=True,
            download_sha256=digest(download), observed_states=sorted(observed),
            cross_session_download_denied=True, elapsed_seconds=round(time.monotonic() - started, 3))
    except BaseException as error:
        summary["failure_type"] = type(error).__name__
        raise
    finally:
        if process is not None:
            if owned and process.poll() is None:
                try:
                    browser.request("/api/shutdown", {})
                    process.wait(timeout=20)
                except (OSError, ValueError, urllib.error.URLError, subprocess.TimeoutExpired):
                    pass
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait(timeout=10)
            summary["owned_process_exit_code"] = process.returncode
            summary["owned_process_stopped"] = process.poll() is not None
        (work / "验收结果.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), "utf-8")
    print("PASS " + json.dumps(summary, ensure_ascii=False), flush=True)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--host", default="192.168.0.160")
    parser.add_argument("--prefix", type=int, default=24)
    parser.add_argument("--port", type=int, default=8817)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=1200)
    args = parser.parse_args()
    ipaddress.IPv4Interface(f"{args.host}/{args.prefix}")
    assert args.timeout > 0
    verify(args)


if __name__ == "__main__":
    main()
