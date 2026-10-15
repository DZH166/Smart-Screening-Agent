"""Archive a versioned portable build only after recorded packaged acceptance."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import zipfile
from build_manifest import digest, inputs

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from hsd_tool import __version__


def prepare(result_path: Path, notes_path: Path):
    bundle = ROOT / "dist" / ("v" + __version__) / "HSD图号助手"
    delivery = ROOT / "交付" / ("v" + __version__)
    delivery.mkdir(parents=True, exist_ok=True)
    result = json.loads(result_path.read_text("utf-8"))
    assert result["version"] == __version__
    assert result["original_input_hashes_unchanged"] and result["only_target_worksheet_part_changed"]
    assert result["report"]["new_numbers"] == 2 and not result["reference_false_auto"]
    assert (bundle / "HSD图号助手.exe").is_file()
    manifest_path = bundle / "构建校验.json"
    manifest = json.loads(manifest_path.read_text("utf-8"))
    assert result["frozen_runtime"]["frozen"]
    assert result["build_manifest_sha256"] == digest(manifest_path)
    assert manifest["inputs"] == inputs(ROOT)
    assert all(digest(bundle / name) == value for name, value in manifest["runtime"].items())
    assert result["independent_original_ai_hashes_verified"]
    assert result["exact_target_cells_and_other_sheet_bytes_verified"]
    notes = notes_path.read_text("utf-8-sig")
    (bundle / "验收说明.txt").write_text(notes, "utf-8-sig")
    (delivery / "验收说明.txt").write_text(notes, "utf-8-sig")
    archive = delivery / f"HSD-Image-Numbering-Windows-v{__version__}.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as out:
        for path in sorted(bundle.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                out.write(path, path.relative_to(bundle.parent))
    with zipfile.ZipFile(archive) as check:
        assert check.testzip() is None
        assert not any("测试样本/" in name or "/tmp/" in name for name in check.namelist())
    with archive.open("rb") as stream:
        archive_digest = hashlib.file_digest(stream, "sha256").hexdigest()
    (delivery / "SHA256.txt").write_text(f"{archive_digest}  {archive.name}\n", "utf-8")
    print(json.dumps({"archive": str(archive), "bytes": archive.stat().st_size, "sha256": archive_digest}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--notes", type=Path, required=True)
    args = parser.parse_args()
    prepare(args.result, args.notes)
