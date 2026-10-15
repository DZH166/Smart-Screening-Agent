"""Verify the running portable app with a disposable missing-number sample copy.

Optional expected counts are measured source-run results, not production inputs.
Business inputs and reports stay outside Git.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import time
import zipfile
import xml.etree.ElementTree as ET

from acceptance_client import Client
from build_manifest import digest, inputs

ROOT = Path(__file__).resolve().parents[1]


def verify(base, work, bundle, expected_counts=None):
    work.mkdir(parents=True, exist_ok=True)
    original = ROOT / "测试样本" / "10月表格.xlsx"
    ai_zip = ROOT / "测试样本" / "10.10.zip"
    before = {str(p): digest(p) for p in (original, ai_zip)}
    test_book = work / "10月表格_缺号验证.xlsx"
    with zipfile.ZipFile(original) as src, zipfile.ZipFile(test_book, "w") as dst:
        for info in src.infolist():
            data = src.read(info)
            if info.filename == "xl/worksheets/sheet1.xml":
                for cell in (b"A2", b"A3"):
                    data, count = re.subn(rb'<c\b[^>]*\br="' + cell + rb'"[^>]*>.*?</c>',
                                          b'<c r="' + cell + b'"/>', data, count=1, flags=re.S)
                    assert count == 1
            dst.writestr(info, data)
    client = Client(base)
    manifest_path = bundle / "构建校验.json"
    manifest = json.loads(manifest_path.read_text("utf-8"))
    assert manifest["inputs"] == inputs(ROOT), "Build inputs changed; rebuild before accepting"
    assert all(digest(bundle / name) == value for name, value in manifest["runtime"].items())
    runtime = client.request("/api/health")["runtime"]
    assert runtime["frozen"] is True, "Acceptance must target the packaged executable"
    assert runtime["executable_sha256"] == manifest["runtime"]["HSD图号助手.exe"]
    assert runtime["build_manifest_sha256"] == digest(manifest_path)
    start = time.monotonic()
    identifier = client.request("/api/jobs", {"workbook_path": str(test_book), "source_path": str(ai_zip),
        "output_root": str(work / "输出结果"), "start_number": 1})["id"]
    (work / "job_id.txt").write_text(identifier)
    job = client.wait(identifier)
    assert job["status"] == "ready" and len(job["rows"]) == 60 and len(job["files"]) == 60
    processing_seconds = time.monotonic() - start
    reference = json.loads((ROOT / "tests" / "sample_visual_reference.json").read_text("utf-8"))["row_to_ai_index"]
    mismatches, false_auto = [], []
    for row in job["rows"]:
        expected = f"f{reference[str(row['row_number'])]:04d}"
        if not row["candidates"] or row["candidates"][0]["file_id"] != expected:
            mismatches.append(row["id"])
        if row["status"] == "auto" and row["file_id"] != expected:
            false_auto.append(row["id"])
    assert not false_auto, false_auto
    assert not mismatches, mismatches
    initial_stats = dict(job["stats"])
    if expected_counts:
        for state in ("auto", "review", "unmatched"):
            assert initial_stats[state] == expected_counts[state], (state, initial_stats, expected_counts)
    # Only export acceptance uses the reference for an explicit resolution if
    # a missing-number row is still ambiguous; initial auto counts stay intact.
    acceptance_confirmations = []
    for row in job["rows"][:2]:
        if row["status"] not in {"auto", "confirmed"}:
            job = client.request(f"/api/jobs/{identifier}/resolve", {
                "row_id": row["id"], "file_id": f"f{reference[str(row['row_number'])]:04d}"})
            acceptance_confirmations.append(row["id"])
    assert [r["planned_number"] for r in job["rows"][:2]] == ["HSD0001", "HSD0002"]
    assert all(r["planned_number"] == r["number"] for r in job["rows"][2:])
    client.request(f"/api/jobs/{identifier}/export", {"expected_revision": job["revision"]})
    result = client.wait(identifier, timeout=180)
    assert result["status"] == "done"
    output = Path(result["output_dir"])
    report = json.loads((output / "处理记录.json").read_text("utf-8"))
    assert report["new_numbers"] == 2
    assert report["exported"] == job["stats"]["exportable"]
    assert report["pending"] == 60 - report["exported"]
    # Independent byte comparison against the original archive, rather than
    # trusting the export's own self-consistent checksum report.
    with zipfile.ZipFile(ai_zip) as archive:
        from hsd_tool.matching import _zip_name
        original_entries = {_zip_name(info): info for info in archive.infolist() if not info.is_dir()}
        original_ids = {file["id"]: file["relative_path"] for file in job["files"]}
        for mapping in report["mapping"]:
            expected_id = f"f{reference[str(mapping['row'])]:04d}"
            assert mapping["source"] == original_ids[expected_id]
            with archive.open(original_entries[mapping["source"]]) as stream:
                original_sha = hashlib.file_digest(stream, "sha256").hexdigest()
            assert digest(output / "已编号AI" / mapping["output"]) == original_sha == mapping["sha256"]
    with zipfile.ZipFile(test_book) as a, zipfile.ZipFile(output / report["workbook"]) as b:
        assert a.namelist() == b.namelist()
        changed = [name for name in a.namelist() if a.read(name) != b.read(name)]
        assert changed == ["xl/worksheets/sheet1.xml"], changed
        before_xml, after_xml = a.read(changed[0]), b.read(changed[0])
        namespace = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        for address, number in (("A2", "HSD0001"), ("A3", "HSD0002")):
            # Parse only the target cells; the real sheet has a huge formatted
            # trailing region. Then prove every byte outside them is identical.
            pattern = rb'<c\b[^>]*\br="' + address.encode() + rb'"[^>]*?(?:\s*/>|>.*?</c>)'
            cell = re.search(pattern, after_xml, re.S).group(0)
            element = ET.fromstring(b'<root xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">' + cell + b'</root>')
            assert element.find("s:c/s:is/s:t", namespace).text == number
            before_xml, count = re.subn(pattern, b"TARGET_CELL", before_xml, count=1, flags=re.S)
            assert count == 1
            after_xml, count = re.subn(pattern, b"TARGET_CELL", after_xml, count=1, flags=re.S)
            assert count == 1
        assert before_xml == after_xml, "Other worksheet content changed"
    assert all(digest(Path(path)) == value for path, value in before.items())
    summary = {"packaged_app": base, "version": client.request("/api/config")["version"],
               "job_id": identifier, "processing_wall_seconds": round(processing_seconds, 3),
               "timings": result["timings"], "initial_stats": initial_stats, "stats": job["stats"],
               "report": report, "reference_top_candidate_deviations": mismatches,
               "reference_false_auto": false_auto, "acceptance_only_confirmations": acceptance_confirmations,
               "validation_boundary": "Existing 60-row reference is a regression oracle, not an independent accuracy estimate.",
               "original_input_hashes_unchanged": True, "only_target_worksheet_part_changed": True,
               "output_dir": str(output)}
    summary["frozen_runtime"] = runtime
    summary["build_manifest_sha256"] = digest(manifest_path)
    summary["independent_original_ai_hashes_verified"] = True
    summary["exact_target_cells_and_other_sheet_bytes_verified"] = True
    (work / "验收结果.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False), "utf-8")
    print("PASS", json.dumps({"initial_stats": initial_stats, "new_numbers": 2,
                               "output": str(output), "timings": result["timings"]}, ensure_ascii=False), flush=True)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base", nargs="?", default="http://127.0.0.1:8804")
    parser.add_argument("--work", type=Path, default=ROOT / "tmp" / "v12_packaged_validation")
    parser.add_argument("--expected-counts", type=Path)
    parser.add_argument("--bundle", type=Path, required=True)
    args = parser.parse_args()
    expected = json.loads(args.expected_counts.read_text("utf-8"))["counts"] if args.expected_counts else None
    import sys
    sys.path.insert(0, str(ROOT))
    verify(args.base, args.work, args.bundle.resolve(), expected)
