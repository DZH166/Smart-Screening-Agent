"""Check the outputs produced by the browser workflow fixtures, without rematching."""
import hashlib
import json
from pathlib import Path
import sys
from zipfile import ZipFile


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify(root):
    checks = []
    for name, exported, new_numbers, pending in [("all_reliable", 3, 2, 0), ("ambiguous", 2, 1, 2)]:
        folder = root / name
        outputs = sorted((folder / "ui_export").glob("HSD编号结果_*/处理记录.json"))
        assert outputs, f"Complete the {name} browser workflow first"
        report_path = outputs[-1]
        report = json.loads(report_path.read_text("utf-8"))
        assert (report["exported"], report["new_numbers"], report["pending"]) == (exported, new_numbers, pending)
        assert digest(folder / "input.xlsx") == report["input_sha256"]
        for item in report["mapping"]:
            assert digest(folder / "AI" / item["source"]) == item["sha256"]
            assert digest(report_path.parent / "已编号AI" / item["output"]) == item["sha256"]
        if name == "ambiguous":
            assert report["stats"]["review"] == 0
            assert report["stats"]["skipped"] == report["stats"]["unmatched"] == 1
            assert {r["row"] for r in report["pending_rows"]} == {4, 5}
        else:
            assert report["stats"]["auto"] == 3 and report["stats"]["confirmed"] == 0
        with ZipFile(folder / "input.xlsx") as source, ZipFile(report_path.parent / report["workbook"]) as output:
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
    verify(Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "tmp/v11_workflow_fixtures")
