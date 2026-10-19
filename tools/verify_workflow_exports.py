"""Check the outputs produced by the browser workflow fixtures, without rematching."""
import hashlib
import json
from pathlib import Path
import sys
from zipfile import ZipFile


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify(root, data_dir):
    checks = []
    for name, exported, new_numbers, pending in [("all_reliable", 3, 2, 0), ("ambiguous", 2, 1, 2)]:
        folder = root / name
        outputs = sorted((folder / "ui_export").glob("HSD编号结果_*"))
        assert outputs, f"Complete the {name} browser workflow first"
        output_dir = outputs[-1]
        candidates = list((data_dir / 'task_records').glob('*/export_records/*/处理记录.json'))
        reports = [(path, json.loads(path.read_text('utf-8'))) for path in candidates]
        reports = [(path, item) for path, item in reports if item['input_sha256'] == digest(folder / 'input.xlsx')]
        assert len(reports) == 1, 'Use an isolated test data directory with one export per synthetic batch'
        report_path, report = reports[0]
        assert (report["exported"], report["new_numbers"], report["pending"]) == (exported, new_numbers, pending)
        assert digest(folder / "input.xlsx") == report["input_sha256"]
        for item in report["mapping"]:
            assert digest(folder / "AI" / item["source"]) == item["sha256"]
            assert digest(output_dir / "已编号AI" / item["output"]) == item["sha256"]
        if name == "ambiguous":
            assert report["stats"]["review"] == 0
            assert report["stats"]["skipped"] == report["stats"]["unmatched"] == 1
            assert {r["row"] for r in report["pending_rows"]} == {4, 5}
        else:
            assert report["stats"]["auto"] == 3 and report["stats"]["confirmed"] == 0
        with ZipFile(folder / "input.xlsx") as source, ZipFile(output_dir / report["workbook"]) as output:
            assert source.namelist() == output.namelist()
            changed = [name for name in source.namelist() if source.read(name) != output.read(name)]
            assert changed == ["xl/worksheets/sheet1.xml"]
            xml = output.read(changed[0]).decode()
            assert "KEEP0001" in xml and "HSD0001" in xml
            if name == "ambiguous":
                assert "MISSING0004" in xml and "HSD0002" not in xml
            else:
                assert "HSD0002" in xml
        checks.append({"batch": name, "stats": report["stats"], "timings": report["timings"],
                       "source_and_export_hashes_verified": True, "only_numbered_sheet_changed": True})
    (root / "browser_export_checks.json").write_text(json.dumps(checks, ensure_ascii=False, indent=2), "utf-8")
    print(json.dumps(checks, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    assert len(sys.argv) == 3, 'Usage: verify_workflow_exports.py fixtures_root isolated_test_data_dir'
    verify(Path(sys.argv[1]), Path(sys.argv[2]))
