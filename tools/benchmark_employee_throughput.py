"""Real two-cookie HTTP/matching/export benchmark on fixed synthetic artwork.

Three sequential trials per implementation. No CPU or provider sleep mocks;
poll sleeps only wait for actual work. AI is disabled in isolated settings.
"""
from __future__ import annotations

import argparse
from io import BytesIO
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import threading
import time
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def generate(directory):
    from workflow_fixtures import artwork, workbook, ai_file
    from PIL import Image, ImageDraw
    directory.mkdir(parents=True)
    pictures = [artwork(seed) for seed in (1800101, 1800107, 1800113, 1800121)]
    for kind in ("stripes", "dots"):
        image = Image.new("RGB", (1000, 190), (246, 241, 233))
        draw = ImageDraw.Draw(image)
        if kind == "stripes":
            palette = ((151, 62, 43), (232, 216, 186), (32, 103, 145), (230, 178, 51))
            for index, x in enumerate(range(0, 1000, 25)):
                draw.rectangle((x, 0, x+24, 190), fill=palette[index % len(palette)])
        else:
            for row, y in enumerate(range(-4, 210, 31)):
                for column, x in enumerate(range(-5, 1030, 37)):
                    draw.ellipse((x+row%2*15, y, x+row%2*15+15, y+15),
                                 fill=((34, 114, 125) if (row+column)%3 else (179, 72, 86)))
        stream = BytesIO()
        image.save(stream, "PNG")
        pictures.append(stream.getvalue())
    table = directory / "input.xlsx"
    workbook(table, [("KEEP0018" if index == 0 else "", picture) for index, picture in enumerate(pictures)])
    source = directory / "artwork.zip"
    sources, expected_rows = {}, {}
    with zipfile.ZipFile(source, "w", zipfile.ZIP_DEFLATED) as archive:
        for index, picture in enumerate(pictures, 1):
            path = directory / f"design_{index:02}.ai"
            ai_file(path, picture)
            archive.write(path, path.name)
            sources[path.name] = digest(path)
            expected_rows[f"r{index+1}"] = sources[path.name]
    manifest = {"origin": "fixed_generated_synthetic_not_business", "row_count": len(pictures),
        "workbook_sha256": digest(table), "source_sha256": digest(source), "source_ai_sha256": sources,
        "expected_row_source_sha256": expected_rows}
    (directory / "frozen-inputs.json").write_text(json.dumps(manifest, indent=2), "utf-8")
    return manifest


def check_archive(payload, job, inputs, manifest, mode):
    accepted = [row for row in job["rows"] if row["status"] in {"auto", "confirmed"}]
    assert accepted and all(row["status"] != "confirmed" for row in accepted)
    files = {item["id"]: item for item in job["files"]}
    with zipfile.ZipFile(BytesIO(payload)) as archive:
        assert archive.testzip() is None
        names = archive.namelist()
        roots = {name.split("/", 1)[0] for name in names}
        assert len(roots) == 1
        prefix = next(iter(roots)) + "/"
        numbered = [name for name in names if name.endswith(".xlsx")]
        assert len(numbered) == 1
        expected_ai = {prefix + "已编号AI/" + row["planned_number"] + ".ai" for row in accepted}
        expected = expected_ai | set(numbered)
        if mode == "baseline":
            expected |= {prefix + name for name in ("处理记录.json", "对应关系.csv", "待处理清单.csv")}
        assert set(names) == expected, "Unexpected downloaded members"
        for row in accepted:
            name = files[row["file_id"]]["relative_path"].replace("\\", "/")
            expected_hash = manifest["source_ai_sha256"][name]
            assert expected_hash == manifest["expected_row_source_sha256"][row["id"]], "Synthetic auto match disagreed with frozen generated truth"
            content = archive.read(prefix + "已编号AI/" + row["planned_number"] + ".ai")
            assert hashlib.sha256(content).hexdigest() == expected_hash
        numbered_bytes = archive.read(numbered[0])
    with zipfile.ZipFile(inputs / "input.xlsx") as original, zipfile.ZipFile(BytesIO(numbered_bytes)) as output:
        assert original.namelist() == output.namelist()
        changed = [name for name in original.namelist() if original.read(name) != output.read(name)]
        expected_changes = ["xl/worksheets/sheet1.xml"] if any(not row["number"] for row in accepted) else []
        assert changed == expected_changes
        namespace = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        sheet = ET.fromstring(output.read("xl/worksheets/sheet1.xml"))
        for row in job["rows"]:
            cell = sheet.find(f'.//s:c[@r="A{row["row_number"]}"]/s:is/s:t', namespace)
            actual = "" if cell is None or cell.text is None else cell.text
            expected_number = row["planned_number"] if row["status"] in {"auto", "confirmed"} else row["number"]
            assert actual == expected_number
    return {"members": len(names), "ai_files": len(accepted), "workbooks": 1,
            "member_contract": "legacy_records_included" if mode == "baseline" else "ai_and_one_workbook_only",
            "ai_original_bytes_verified": True, "wps_other_parts_preserved": True, "unprocessed_rows_unchanged": True}


def worker(args):
    # Import helper first: it prepends current repo paths. Select the package
    # only afterwards, before *any* hsd_tool module import, then prove isolation.
    from verify_employee_portable import Browser
    assert not any(name == "hsd_tool" or name.startswith("hsd_tool.") for name in sys.modules)
    selected = args.package_root.resolve()
    sys.path.insert(0, str(selected))
    os.environ.pop("DEEPSEEK_API_KEY", None)
    import hsd_tool.service as service
    import hsd_tool.matching as matching
    from hsd_tool.server import create_app
    from hsd_tool.lan import LanAccess
    from werkzeug.serving import make_server, WSGIRequestHandler
    for module in (service, matching):
        assert Path(module.__file__).resolve().parent == (selected / "hsd_tool").resolve(), "Implementation isolation failed"
    manifest = json.loads((args.inputs / "frozen-inputs.json").read_text("utf-8"))
    workbook, source = args.inputs / "input.xlsx", args.inputs / "artwork.zip"
    assert digest(workbook) == manifest["workbook_sha256"] and digest(source) == manifest["source_sha256"]
    args.work.mkdir(parents=True, exist_ok=False)
    state, settings = args.work / "state", args.work / "ai-disabled-settings"
    host_inputs, host_outputs = args.work / "host-inputs", args.work / "host-outputs"
    host_inputs.mkdir()
    settings.mkdir()
    lan = LanAccess(f"{args.host}/24", host_inputs, host_outputs, code="synthetic-throughput-access")
    app = create_app(state, token="synthetic-throughput-token", lan=lan, settings_dir=settings)
    class QuietHandler(WSGIRequestHandler):
        def log_request(self, *params):
            pass
    server = make_server(args.host, 0, app, threaded=True, request_handler=QuietHandler)
    app.config["HSD_PORT"] = server.server_port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://{args.host}:{server.server_port}"
    browsers = [Browser(base), Browser(base)]
    manager = app.config["HSD_MANAGER"]
    report = {"ok": False, "mode": args.mode, "real_api_calls": 0,
        "validation_scope": "Real source HTTP/CPU matching/export on fixed six-row generated artwork; two cookies on one host, not independent business accuracy or a second physical computer.",
        "input_sha256": {"workbook": manifest["workbook_sha256"], "source": manifest["source_sha256"]},
        "implementation_sha256": {name: digest(selected / "hsd_tool" / name) for name in
            ("service.py", "matching.py", "matching_verification.py")},
        "employee_runs": []}
    try:
        for browser in browsers:
            browser.login(lan.code)
            ai = browser.request("/api/ai/settings")
            assert not ai["enabled"] and not ai["configured"]
        start, cpu_start = time.perf_counter(), time.process_time()
        records = []
        for index, browser in enumerate(browsers):
            upload_started = time.perf_counter()
            identifier = browser.upload(workbook.read_bytes(), source.read_bytes(), 7 if index == 0 else 31)
            records.append({"employee": index+1, "id": identifier,
                "input_repetition": "first task in fresh process" if index == 0 else "same input, independent employee task; cache hit not presumed",
                "upload_start_seconds": upload_started-start,
                "upload_seconds": time.perf_counter()-upload_started,
                "states": [], "export_requested": False, "downloaded": False})
        assert records[0]["id"] != records[1]["id"]
        deadline = time.monotonic()+600
        while time.monotonic() < deadline and not all(record["downloaded"] for record in records):
            for browser, record in zip(browsers, records):
                if record["downloaded"]:
                    continue
                job = browser.request("/api/jobs/" + record["id"])
                if not record["states"] or record["states"][-1] != job["status"]:
                    record["states"].append(job["status"])
                assert job["status"] != "error", "Real synthetic batch failed"
                if job["status"] == "ready" and not record["export_requested"]:
                    record["ready_seconds"] = time.perf_counter()-start
                    record["stats_before_export"] = dict(job["stats"])
                    record["decisions"] = [{"row_id": row["id"], "status": row["status"], "file_id": row.get("file_id"),
                        "first_candidate": row["candidates"][0]["file_id"] if row["candidates"] else None}
                        for row in job["rows"]]
                    assert job["stats"]["exportable"] > 0 and job["stats"]["confirmed"] == 0
                    export_started = time.perf_counter()
                    browser.request(f'/api/jobs/{record["id"]}/export', {"expected_revision": job["revision"]})
                    record["export_submit_seconds"] = time.perf_counter()-export_started
                    record["export_requested"] = True
                elif job["status"] == "done":
                    transfer_started = time.perf_counter()
                    data = browser.raw(f'/api/jobs/{record["id"]}/download')
                    record["transfer_seconds"] = time.perf_counter()-transfer_started
                    record["download_finished_seconds"] = time.perf_counter()-start
                    record["download_bytes"] = len(data)
                    record["download_contract"] = check_archive(data, job, args.inputs, manifest, args.mode)
                    record["timings"] = dict(job["timings"])
                    record["downloaded"] = True
            if not all(record["downloaded"] for record in records):
                time.sleep(.03)  # Polling only; actual matcher/exporter do the work.
        assert all(record["downloaded"] for record in records), "Real throughput run timed out"
        makespan, cpu = time.perf_counter()-start, time.process_time()-cpu_start
        assert manager.ai_usage.snapshot()["requests"] == 0
        assert digest(workbook) == manifest["workbook_sha256"] and digest(source) == manifest["source_sha256"]
        report.update(ok=True, employee_runs=records, makespan_seconds=makespan,
            process_cpu_seconds=cpu, cpu_scope="Current worker process including source HTTP/server/matcher/client; not child-process CPU if introduced.",
            first_employee_download_seconds=records[0]["download_finished_seconds"],
            second_employee_download_seconds=records[1]["download_finished_seconds"],
            inputs_unchanged=True, manual_resolutions=0)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)
        manager.close()
        report["owned_server_stopped"] = not thread.is_alive()
        (args.work / "results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
    print(json.dumps(report, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-root", type=Path)
    parser.add_argument("--package-root", type=Path)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--inputs", type=Path)
    parser.add_argument("--host", required=True)
    parser.add_argument("--mode", choices=("baseline", "optimized"))
    parser.add_argument("--worker", action="store_true")
    args = parser.parse_args()
    if args.worker:
        return worker(args)
    assert args.baseline_root and args.baseline_root.is_dir()
    assert not args.work.exists() or not any(args.work.iterdir())
    args.work.mkdir(parents=True, exist_ok=True)
    inputs = args.work / "fixed-inputs"
    manifest = generate(inputs)
    runs = []
    for repeat in range(1, 4):
        for mode, package in (("baseline", args.baseline_root), ("optimized", ROOT)):
            destination = args.work / f"{mode}-{repeat}"
            completed = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--worker",
                "--mode", mode, "--package-root", str(package.resolve()), "--inputs", str(inputs.resolve()),
                "--host", args.host, "--work", str(destination.resolve())],
                cwd=ROOT, capture_output=True, text=True, check=False, timeout=660)
            (args.work / f"{mode}-{repeat}-stdout.txt").write_text(completed.stdout, "utf-8")
            (args.work / f"{mode}-{repeat}-stderr.txt").write_text(completed.stderr, "utf-8")
            if completed.returncode:
                runs.append({"ok": False, "mode": mode, "repeat": repeat, "returncode": completed.returncode})
                (args.work / "results-in-progress.json").write_text(json.dumps({"planned_trials": 6, "runs": runs}, indent=2), "utf-8")
                raise RuntimeError("Throughput trial failed; isolated report/stdout/stderr were retained")
            result = json.loads(completed.stdout)
            result["repeat"] = repeat
            runs.append(result)
            (args.work / "results-in-progress.json").write_text(json.dumps({"planned_trials": 6, "runs": runs}, ensure_ascii=False, indent=2), "utf-8")
            print(json.dumps({"mode": mode, "repeat": repeat, "makespan_seconds": result["makespan_seconds"]}), flush=True)
    reference = runs[0]["employee_runs"][0]["decisions"]
    assert all(employee["decisions"] == reference for run in runs for employee in run["employee_runs"]), "Candidate/status decisions changed across implementations or ordering"
    report = {"scope": "Six independent real-matching HTTP runs, three per implementation, on the same frozen generated six-row batch; no real provider or business accuracy claim.",
        "fixed_inputs": manifest, "runs": runs,
        "medians": {mode: {key: statistics.median(run[key] for run in runs if run["mode"] == mode)
            for key in ("makespan_seconds", "process_cpu_seconds", "first_employee_download_seconds", "second_employee_download_seconds")}
            for mode in ("baseline", "optimized")}}
    (args.work / "results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
    print(json.dumps(report["medians"], indent=2))


if __name__ == "__main__":
    main()
