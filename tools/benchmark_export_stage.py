"""Actual asynchronous export, beginning from an already measured match snapshot.

This is an export-stage microbenchmark, not end-to-end matching or independent
business validation. Original statuses/candidates/evidence are injected unchanged
only into the benchmark manager; production matching code is never replaced.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def wait_ready(manager, identifier):
    deadline = time.monotonic()+300
    while time.monotonic() < deadline:
        result = manager.snapshot(identifier)
        if result["status"] not in {"queued", "importing", "matching", "ai_review", "exporting"}:
            return result
        time.sleep(.01)
    raise AssertionError("Real export-stage operation timed out")


def check_archive(path, job, workbook, frozen, mode):
    files = {item["id"]: item for item in frozen["matches"]["files"]}
    accepted = [row for row in job["rows"] if row["status"] in {"auto", "confirmed"}]
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        compression_counts = {"stored": sum(item.compress_type == zipfile.ZIP_STORED for item in archive.infolist()),
                              "deflate": sum(item.compress_type == zipfile.ZIP_DEFLATED for item in archive.infolist())}
        roots = {name.split("/", 1)[0] for name in names}
        assert len(roots) == 1
        prefix = next(iter(roots))+"/"
        tables = [name for name in names if name.endswith(".xlsx")]
        assert len(tables) == 1
        expected = {prefix+"已编号AI/"+row["planned_number"]+".ai" for row in accepted} | set(tables)
        if mode == "baseline":
            expected |= {prefix+name for name in ("处理记录.json", "对应关系.csv", "待处理清单.csv")}
        assert set(names) == expected
        for row in accepted:
            expected_hash = files[row["file_id"]]["source_sha256"]
            with archive.open(prefix+"已编号AI/"+row["planned_number"]+".ai") as stream:
                assert hashlib.file_digest(stream, "sha256").hexdigest() == expected_hash
        data = archive.read(tables[0])
    with zipfile.ZipFile(workbook) as original, zipfile.ZipFile(BytesIO(data)) as numbered:
        assert original.namelist() == numbered.namelist()
        changed = [name for name in original.namelist() if original.read(name) != numbered.read(name)]
        assert changed == (["xl/worksheets/sheet1.xml"] if any(not row["number"] for row in accepted) else [])
        sheet = ET.fromstring(numbered.read("xl/worksheets/sheet1.xml"))
        namespace = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        for row in job["rows"]:
            cell = sheet.find(f'.//s:c[@r="A{row["row_number"]}"]/s:is/s:t', namespace)
            # Existing non-inline number cells retain their complete original
            # XML; only blank accepted cells must become inline assignments.
            if row["status"] in {"auto", "confirmed"} and not row["number"]:
                assert cell is not None and cell.text == row["planned_number"]
    return {"member_count": len(names), "ai_files": len(accepted), "excel_files": 1,
            "compression_counts": compression_counts,
            "member_contract": "legacy_records_included" if mode == "baseline" else "ai_and_one_workbook_only",
            "all_ai_bytes_verified": True, "wps_parts_preserved": True}


def worker(args):
    selected = args.package_root.resolve()
    sys.path.insert(0, str(selected))
    os.environ.pop("DEEPSEEK_API_KEY", None)
    import hsd_tool.service as service
    import hsd_tool.matching as matching
    for module in (service, matching):
        assert Path(module.__file__).resolve().parent == (selected/"hsd_tool").resolve()
    frozen = json.loads(args.frozen.read_text("utf-8"))
    assert digest(args.workbook) == frozen["workbook_sha256"]
    assert digest(args.source) == frozen["source_sha256"]
    args.work.mkdir(parents=True, exist_ok=False)
    manager = service.JobManager(args.work / "state", settings_dir=args.work / "ai-disabled")
    report = {"ok": False, "mode": args.mode, "real_api_calls": 0,
        "scope": "Actual export/packaging from an unchanged previously measured 53-auto/7-review match snapshot; workbook preparation and matching are excluded, not an end-to-end or independent business accuracy claim.",
        "snapshot_sha256": digest(args.frozen), "service_sha256": digest(selected/"hsd_tool/service.py")}
    def inject(identifier):
        job = manager._start_operation(identifier, "importing", "measured snapshot setup; outside export timer")
        snapshot = Path(job["_work_dir"]) / "source.xlsx"
        shutil.copyfile(args.workbook, snapshot)
        assert digest(snapshot) == frozen["workbook_sha256"]
        prepared = dict(_input_digest=frozen["workbook_sha256"], _source_archive_digest=frozen["source_sha256"],
            _snapshot_workbook=str(snapshot), sheet_name=frozen["table"]["sheet_name"],
            rows=copy.deepcopy(frozen["table"]["rows"]), files=copy.deepcopy(frozen["matches"]["files"]),
            _reserved=list(frozen["table"].get("reserved_numbers", [])), warnings=list(frozen["matches"].get("warnings", [])))
        matched = {item["row_id"]: item for item in frozen["matches"]["matches"]}
        for row in prepared["rows"]:
            result = matched[row["id"]]
            row.update(_status=result["status"], _file_id=result.get("file_id"), _reason=result.get("reason", ""),
                _reason_code=result.get("reason_code", "not_verified"), evidence=copy.deepcopy(result.get("evidence")),
                diagnostics=copy.deepcopy(result.get("diagnostics", {})), candidates=copy.deepcopy(result["candidates"]))
        # Snapshot polling must observe the old state or the complete injected
        # state. Match the selected implementation's real snapshot lock; the
        # frozen baseline predates per-task operation locks.
        operation = (manager.job_operation(identifier, internal=True)
                     if args.mode == "optimized" else manager.lock)
        with operation:
            job.update(prepared)
            manager._plan(job)
            assert {name: job["stats"][name] for name in ("auto", "review", "unmatched")} == frozen["counts"]
            job.update(status="ready", revision=1)
    def safe_inject(identifier):
        try:
            return inject(identifier)
        except Exception as error:
            manager._fail(identifier, error)
            raise
    manager._process = safe_inject
    try:
        identifier = manager.create({"workbook_path": str(args.workbook.resolve()), "source_path": str(args.source.resolve()),
            "output_root": str((args.work/"outputs").resolve()), "start_number": 1},
            owner_id="synthetic-export-benchmark", downloadable=True)
        job = wait_ready(manager, identifier)
        assert job["status"] == "ready"
        started, cpu_started = time.perf_counter(), time.process_time()
        manager.export(identifier, expected_revision=job["revision"])
        result = wait_ready(manager, identifier)
        export_ready = time.perf_counter()-started
        assert result["status"] == "done", result.get("error")
        download_started = time.perf_counter()
        path, expected_hash = manager.download_asset(identifier)
        download_validation = time.perf_counter()-download_started
        total, cpu = time.perf_counter()-started, time.process_time()-cpu_started
        assert digest(path) == expected_hash
        contract = check_archive(path, result, args.workbook, frozen, args.mode)
        private_job = manager.jobs[identifier]
        record_path = (Path(private_job["_records_dir"]) if args.mode == "optimized" else Path(result["output_dir"])) / "处理记录.json"
        record = json.loads(record_path.read_text("utf-8"))
        assert len(record["decision_records"]) == len(frozen["table"]["rows"])
        assert record["pending"] == frozen["counts"]["review"] + frozen["counts"]["unmatched"]
        assert record["exported"] == frozen["counts"]["auto"]
        assert record.get("ai_observation_runs", []) == []
        assert manager.ai_usage.snapshot()["requests"] == 0
        assert digest(args.workbook) == frozen["workbook_sha256"] and digest(args.source) == frozen["source_sha256"]
        report.update(ok=True, export_ready_seconds=export_ready,
            download_integrity_check_seconds=download_validation, export_to_download_ready_seconds=total,
            process_cpu_seconds=cpu, zip_bytes=path.stat().st_size, zip_sha256=expected_hash,
            stats=result["stats"], timings=result["timings"], archive_contract=contract,
            private_record_complete=True, source_inputs_unchanged=True)
    finally:
        manager.close()
        report["private_record_survives_shutdown"] = record_path.is_file() if "record_path" in locals() else False
        (args.work/"results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
    print(json.dumps(report, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-root", type=Path)
    parser.add_argument("--package-root", type=Path)
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--workbook", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--frozen", type=Path)
    parser.add_argument("--mode", choices=("baseline", "optimized"))
    parser.add_argument("--worker", action="store_true")
    args = parser.parse_args()
    if args.worker:
        return worker(args)
    assert args.baseline_root and args.snapshot
    assert not args.work.exists() or not any(args.work.iterdir())
    args.work.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(ROOT))
    from hsd_tool.workbook import inspect_workbook
    frozen = {"matches": json.loads(args.snapshot.read_text("utf-8")),
        "table": inspect_workbook(str(args.workbook.resolve()), str((args.work/"prepared-workbook").resolve())),
        "workbook_sha256": digest(args.workbook), "source_sha256": digest(args.source)}
    frozen["counts"] = {name: sum(item["status"] == name for item in frozen["matches"]["matches"])
                         for name in ("auto", "review", "unmatched")}
    assert frozen["counts"] == {"auto": 53, "review": 7, "unmatched": 0}
    frozen_path = args.work / "frozen-export-inputs.json"
    frozen_path.write_text(json.dumps(frozen, ensure_ascii=False, indent=2), "utf-8")
    runs = []
    for repeat in range(1, 4):
        for mode, package in (("baseline", args.baseline_root), ("optimized", ROOT)):
            destination = args.work/f"{mode}-{repeat}"
            completed = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--worker", "--mode", mode,
                "--package-root", str(package.resolve()), "--frozen", str(frozen_path.resolve()),
                "--workbook", str(args.workbook.resolve()), "--source", str(args.source.resolve()),
                "--work", str(destination.resolve())], cwd=ROOT, capture_output=True, text=True, check=False, timeout=600)
            (args.work/f"{mode}-{repeat}-stdout.txt").write_text(completed.stdout, "utf-8")
            (args.work/f"{mode}-{repeat}-stderr.txt").write_text(completed.stderr, "utf-8")
            if completed.returncode:
                runs.append({"ok": False, "mode": mode, "repeat": repeat, "returncode": completed.returncode})
                (args.work/"results-in-progress.json").write_text(json.dumps({"planned_trials": 6, "runs": runs}, indent=2), "utf-8")
                raise RuntimeError("Export-stage trial failed; isolated report/stdout/stderr were retained")
            result = json.loads(completed.stdout)
            result["repeat"] = repeat
            runs.append(result)
            (args.work/"results-in-progress.json").write_text(json.dumps({"planned_trials": 6, "runs": runs}, ensure_ascii=False, indent=2), "utf-8")
            print(json.dumps({"mode": mode, "repeat": repeat, "export_to_download_ready_seconds": result["export_to_download_ready_seconds"], "zip_bytes": result["zip_bytes"]}), flush=True)
    report = {"scope": "Six actual export-stage trials from the same frozen measured matches; preparation and matching are excluded.",
        "runs": runs, "medians": {mode: {key: statistics.median(item[key] for item in runs if item["mode"] == mode)
            for key in ("export_ready_seconds", "download_integrity_check_seconds", "export_to_download_ready_seconds", "process_cpu_seconds", "zip_bytes")}
            for mode in ("baseline", "optimized")}}
    (args.work/"results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
    print(json.dumps(report["medians"], indent=2))


if __name__ == "__main__":
    main()
