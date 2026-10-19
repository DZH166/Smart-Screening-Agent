"""Verify the real Windows admin build with isolated synthetic credentials/data.

No provider requests, user settings or business samples are accessed. Two cookie
sessions test ownership. Remote-only permissions are exercised over HTTP only
when --employee-source names a distinct locally assigned IPv4; otherwise the
report explicitly relies on separate API unit tests for that permission branch.
"""
from __future__ import annotations

import argparse
import base64
import http.client
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from verify_employee_portable import Browser, check_download, digest, generated_inputs, wait_job

SYNTHETIC_KEYS = tuple(f"sk-admin-portable-synthetic-{index}-never-valid" for index in range(3))
ADMIN_PATHS = ("/admin", "/api/admin/overview", "/api/admin/debug",
               "/static/admin.html", "/static/admin.js", "/static/admin.css",
               "/static/Admin.js", "/static/./admin.js", "/static/admin.js.",
               "/static/admin.js%20", "/static/admin.js::$DATA")


class BoundHTTPHandler(urllib.request.HTTPHandler):
    def __init__(self, source):
        super().__init__()
        self.source = source

    def http_open(self, request):
        return self.do_open(lambda host, **kwargs: http.client.HTTPConnection(
            host, source_address=(self.source, 0), **kwargs), request)


class AdminBrowser(Browser):
    def __init__(self, base, source=None):
        super().__init__(base)
        if source:
            self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                urllib.request.HTTPCookieProcessor(self.cookies), BoundHTTPHandler(source))

    def bootstrap(self):
        html = self.raw("/").decode("utf-8")
        match = re.search(r'window\.HSD_TOKEN\s*=\s*("[^"\r\n]*")', html)
        assert match, "Actual application CSRF bootstrap missing"
        self.token = json.loads(match.group(1))


def assert_sanitized(value):
    text = json.dumps(value, ensure_ascii=False)
    assert not any(key in text for key in SYNTHETIC_KEYS), "Synthetic credential was exposed"
    assert "encrypted_api_key" not in text and '"api_key"' not in text


def expected_error(browser, path, status, payload=None):
    try:
        browser.request(path, payload)
    except urllib.error.HTTPError as error:
        assert error.code == status, f"Unexpected HTTP status for {path}: {error.code}"
        result = json.loads(error.read())
        assert_sanitized(result)
        return
    raise AssertionError(f"Expected HTTP {status} for {path}")


def verify(args):
    from build_manifest import inputs
    from hsd_tool import __version__
    from hsd_tool.ai_settings import _DPAPI

    assert os.name == "nt", "This verifier targets Windows portable executables"
    executable = args.exe.resolve(strict=True)
    manifest_path = executable.parent / "构建校验.json"
    manifest = json.loads(manifest_path.read_text("utf-8"))
    assert manifest["version"] == __version__
    assert manifest["inputs"] == inputs(ROOT), "Production inputs changed; rebuild first"
    assert all(digest(executable.parent / name) == value for name, value in manifest["runtime"].items())
    work = args.work.absolute()
    assert not work.is_symlink() and (not work.exists() or work.is_dir() and not any(work.iterdir())), "--work must be empty"
    work.mkdir(parents=True, exist_ok=True)
    state, settings = work / "state", work / "synthetic-settings"
    host_inputs, host_outputs = work / "host-inputs", work / "host-outputs"
    for directory in (settings, host_inputs, host_outputs):
        directory.mkdir()
    # Start from an actual v1 DPAPI record to exercise migration, not a new pool.
    encrypted = base64.b64encode(_DPAPI().encrypt(SYNTHETIC_KEYS[0].encode("ascii"))).decode("ascii")
    settings_path = settings / "ai_settings.json"
    settings_path.write_text(json.dumps({"version": 1, "enabled": False,
        "encrypted_api_key": encrypted, "model": "deepseek-flash"}), "utf-8")
    child_env = dict(os.environ)
    child_env.pop("DEEPSEEK_API_KEY", None)
    selfchecks = {}
    for label, command in (("source", [sys.executable, "-m", "hsd_tool"]),
                           ("frozen", [str(executable)])):
        output = work / f"{label}-self-check.json"
        completed = subprocess.run(command + ["--self-check", "--result", str(output)],
            cwd=ROOT, env=child_env, creationflags=subprocess.CREATE_NO_WINDOW,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=90)
        assert completed.returncode == 0 and output.is_file(), f"{label} self-check failed"
        selfchecks[label] = json.loads(output.read_text("utf-8"))
        assert selfchecks[label]["ok"] and selfchecks[label]["version"] == __version__
    assert selfchecks["source"]["frozen"] is False and selfchecks["frozen"]["frozen"] is True
    assert selfchecks["source"]["ai_implementation"] == selfchecks["frozen"]["ai_implementation"]
    workbook, source, original_ai = generated_inputs(work / "generated")
    original_hashes = {path: digest(path) for path in (workbook, source, original_ai)}
    base = f"http://{args.host}:{args.port}"
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind((args.host, args.port))
    process = subprocess.Popen([str(executable), "--no-browser", "--port", str(args.port),
        "--data-dir", str(state), "--settings-dir", str(settings),
        "--lan", f"{args.host}/{args.prefix}", "--lan-input-root", str(host_inputs),
        "--lan-output-root", str(host_outputs)], cwd=ROOT, env=child_env,
        creationflags=subprocess.CREATE_NO_WINDOW, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    host = AdminBrowser(base)
    employees = [AdminBrowser(base, args.employee_source) for _ in range(2)]
    owned_instance = False
    started = time.monotonic()
    report = {"ok": False, "version": __version__, "real_api_calls": 0,
        "user_credentials_accessed": False, "data_origin": "synthetic_only",
        "second_physical_pc_tested": False,
        "remote_http_permissions_tested": bool(args.employee_source),
        "remote_permission_boundary": "actual distinct source address" if args.employee_source else
            "Not tested over network; separate tests/test_admin_api.py covers remote 401/403. Cookie sessions below originate on host.",
        "source_frozen_signatures_equal": True,
        "implementation_modules": sorted(selfchecks["source"]["ai_implementation"]),
        "manifest_input_count": len(manifest["inputs"]), "manifest_runtime_count": len(manifest["runtime"])}
    try:
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            assert process.poll() is None, "Owned portable process exited during startup"
            try:
                instance = json.loads((state / "instance.json").read_text("utf-8"))
                health = host.request("/api/health")
                assert instance["url"] == base and instance["instance"] == health["instance"]
                owned_instance = True
                break
            except (OSError, ValueError, urllib.error.URLError):
                time.sleep(.25)
        assert owned_instance, "Owned portable process did not become ready"
        runtime = health["runtime"]
        assert runtime["frozen"] and runtime["version"] == __version__
        assert runtime["executable_sha256"] == digest(executable)
        assert runtime["build_manifest_sha256"] == digest(manifest_path)
        host.bootstrap()
        assert b"DeepSeek" in host.raw("/admin")
        overview = host.request("/api/admin/overview")
        assert_sanitized(overview)
        assert overview["settings"]["enabled"] is False and overview["settings"]["configured"] is True
        assert overview["settings"]["key_persistence"] == "windows_dpapi"
        assert overview["pool"]["key_count"] == 1
        assert overview["pool"]["keys"][0]["id"] == "legacy"
        stale_revision = overview["settings"]["key_revision"]
        added = host.request("/api/admin/keys", {"expected_revision": stale_revision,
            "add": [{"label": "合成 Key 二", "api_key": SYNTHETIC_KEYS[1]},
                    {"label": "合成 Key 三", "api_key": SYNTHETIC_KEYS[2]}]})
        assert_sanitized(added)
        assert added["pool"]["key_count"] == 3
        saved = json.loads(settings_path.read_text("utf-8"))
        assert saved["version"] == 2 and len(saved["keys"]) == 3
        assert all(row["encrypted_api_key"] for row in saved["keys"])
        assert not any(key in settings_path.read_text("utf-8") for key in SYNTHETIC_KEYS)
        expected_error(host, "/api/admin/keys", 409,
            {"expected_revision": stale_revision, "remove": ["legacy"]})
        expected_error(host, "/api/admin/keys", 400,
            {"expected_revision": added["settings"]["key_revision"], "add": [{"api_key": "bad"}]})
        original_token, host.token = host.token, None
        expected_error(host, "/api/admin/keys", 403,
            {"expected_revision": added["settings"]["key_revision"]})
        host.token = original_token
        changed = host.request("/api/admin/keys", {"expected_revision": added["settings"]["key_revision"],
            "update": [{"id": "legacy", "label": "已迁移合成 Key", "enabled": False}]})
        assert changed["pool"]["keys"][0]["status"] == "disabled"
        changed = host.request("/api/admin/keys", {"expected_revision": changed["settings"]["key_revision"],
            "update": [{"id": "legacy", "enabled": True}]})
        remove_id = next(row["id"] for row in changed["pool"]["keys"] if row["id"] != "legacy")
        changed = host.request("/api/admin/keys", {"expected_revision": changed["settings"]["key_revision"],
            "remove": [remove_id]})
        assert changed["pool"]["key_count"] == 2
        assert_sanitized(changed)
        permission_checks = 0
        for employee in employees:
            if args.employee_source:
                expected_error(employee, "/api/admin/overview", 401)
            employee.login(instance["lan_access_code"])
            ai = employee.request("/api/ai/settings")
            assert ai["enabled"] is False
            if args.employee_source:
                assert set(ai) == {"enabled", "configured", "model", "mode"}
                for path in ADMIN_PATHS:
                    expected_error(employee, path, 403)
                    permission_checks += 1
                expected_error(employee, "/api/admin/keys", 403, {"expected_revision": 0})
                expected_error(employee, "/api/ai/usage", 403)
                permission_checks += 2
        identifiers = [employee.upload(workbook.read_bytes(), source.read_bytes(), number)
                       for employee, number in zip(employees, (7, 31))]
        assert identifiers[0] != identifiers[1]
        observed = [set(), set()]
        jobs = [wait_job(employee, identifier, states)
                for employee, identifier, states in zip(employees, identifiers, observed)]
        for job, number in zip(jobs, ("HSD0007", "HSD0031")):
            assert job["status"] == "ready" and job["stats"]["auto"] == 1
            assert job["stats"]["needs_attention"] == job["stats"]["ai_auto"] == 0
            assert job["stats"]["confirmed"] == 0 and job["rows"][0]["planned_number"] == number
        ownership_checks = 0
        for index, employee in enumerate(employees):
            other, other_job = identifiers[1-index], jobs[1-index]
            for path in (f"/api/jobs/{other}", f"/api/jobs/{other}/download",
                         f"/api/jobs/{other}/image/row/{other_job['rows'][0]['id']}"):
                expected_error(employee, path, 404)
                ownership_checks += 1
            expected_error(host, f"/api/jobs/{identifiers[index]}", 404)
            ownership_checks += 1
        events, cursor = [], 0
        while True:
            page = host.request(f"/api/admin/debug?after={cursor}&limit=2")
            assert_sanitized(page)
            assert page["active"] == [] and not page["reset"]
            events.extend(page["events"])
            assert page["cursor"] >= cursor
            cursor = page["cursor"]
            if cursor == page["last_seq"]:
                break
        assert len({event["seq"] for event in events}) == len(events)
        for identifier in identifiers:
            assert [event["stage"] for event in events if event.get("job_id") == identifier] == [
                "run_started", "disabled", "run_finished"]
        assert not any(event["stage"] in {"requesting", "returned"} for event in events)
        assert host.request(f"/api/admin/debug?after={cursor}&limit=2")["events"] == []
        downloads = []
        for employee, identifier, job, states, number in zip(employees, identifiers, jobs, observed, ("HSD0007", "HSD0031")):
            employee.request(f"/api/jobs/{identifier}/export", {"expected_revision": job["revision"]})
            result = wait_job(employee, identifier, states)
            assert result["status"] == "done" and result["download_ready"]
            payload = employee.raw(f"/api/jobs/{identifier}/download")
            check_download(payload, workbook, original_ai, number)
            downloads.append({"number": number, "bytes": len(payload), "auto": 1,
                              "manual_confirmations": 0, "observed_states": sorted(states)})
        final = host.request("/api/admin/overview")
        assert_sanitized(final)
        assert final["usage"]["requests"] == final["pool"]["usage"]["requests"] == 0
        assert final["settings"]["validation"]["qualified"] is False
        assert all(digest(path) == value for path, value in original_hashes.items())
        assert not any(key in (state / "运行日志.log").read_text("utf-8") for key in SYNTHETIC_KEYS)
        report.update(ok=True, runtime=runtime, legacy_dpapi_migration=True,
            bulk_add_count=2, renamed_disabled_enabled_removed=True,
            stale_write_409=True, invalid_write_400=True, missing_token_403=True,
            credentials_not_returned=True, dpapi_no_plaintext=True,
            remote_http_denials=permission_checks, ownership_denials=ownership_checks,
            debug_events=len(events), debug_incremental_pagination=True,
            debug_stages=["run_started", "disabled", "run_finished"],
            downloads=downloads, input_originals_unchanged=True,
            wps_other_parts_unchanged=True, ai_bytes_unchanged=True,
            elapsed_seconds=round(time.monotonic()-started, 3))
    except Exception as error:
        report["failure_type"] = type(error).__name__
        raise
    finally:
        shutdown_requested = False
        if owned_instance and process.poll() is None:
            try:
                host.request("/api/shutdown", {})
                shutdown_requested = True
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
        report.update(normal_shutdown_requested=shutdown_requested,
                      owned_process_exit_code=process.returncode,
                      owned_process_stopped=process.poll() is not None)
        (work / "验收结果.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
    print("PASS " + json.dumps({key: report[key] for key in (
        "version", "bulk_add_count", "debug_events", "ownership_denials", "remote_http_denials",
        "real_api_calls", "elapsed_seconds", "normal_shutdown_requested")}, ensure_ascii=False), flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--host", required=True)
    parser.add_argument("--prefix", type=int, default=24)
    parser.add_argument("--port", type=int, default=8820)
    parser.add_argument("--employee-source", help="Optional distinct locally assigned IPv4 for real remote-policy HTTP checks")
    parser.add_argument("--work", type=Path, required=True)
    args = parser.parse_args()
    interface = ipaddress.IPv4Interface(f"{args.host}/{args.prefix}")
    if args.employee_source:
        source = ipaddress.IPv4Address(args.employee_source)
        assert source != interface.ip and (source in interface.network or source.is_loopback)
    assert 1024 <= args.port <= 65535
    verify(args)


if __name__ == "__main__":
    main()
