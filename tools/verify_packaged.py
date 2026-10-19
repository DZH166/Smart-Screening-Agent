"""Exercise the packaged app against a disposable missing-number sample copy."""
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
import urllib.request
import zipfile
from acceptance_records import read_export_record

ROOT = Path(__file__).resolve().parents[1]
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8790"
# The business sample never enters the repository, so its location is supplied by
# the machine running the acceptance: argv 2/3, then HSD_SAMPLE_DIR, then 测试样本/.
SAMPLE = Path(sys.argv[2] if len(sys.argv) > 2 else os.environ.get("HSD_SAMPLE_DIR",
                                                                 str(ROOT / "测试样本")))
WORK = Path(os.environ.get("HSD_VERIFY_WORK", str(ROOT / "tmp" / "packaged_validation")))
WORK.mkdir(parents=True, exist_ok=True)
DATA = Path(os.environ['HSD_VERIFY_DATA_DIR'])  # Explicit isolated instance; never search user settings.
original = SAMPLE / (sys.argv[3] if len(sys.argv) > 3 else "10月表格.xlsx")
ai_zip = SAMPLE / (sys.argv[4] if len(sys.argv) > 4 else "10.10.zip")
assert original.is_file(), f"找不到图片编号表：{original}"
assert ai_zip.is_file(), f"找不到 AI 压缩包：{ai_zip}"


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


before = {str(p): digest(p) for p in (original, ai_zip)}
test_book = WORK / "10月表格_缺号验证.xlsx"
with zipfile.ZipFile(original) as src, zipfile.ZipFile(test_book, "w") as dst:
    for info in src.infolist():
        data = src.read(info)
        if info.filename == "xl/worksheets/sheet1.xml":
            for cell in (b"A2", b"A3"):
                data, count = re.subn(rb'<c\b[^>]*\br="' + cell + rb'"[^>]*>.*?</c>', b'<c r="' + cell + b'"/>', data, count=1, flags=re.S)
                assert count == 1
        dst.writestr(info, data)

html = urllib.request.urlopen(BASE, timeout=10).read().decode()
token = json.loads(re.search(r'window.HSD_TOKEN\s*=\s*("[^"]+")', html).group(1))


def request(path, payload=None):
    headers = {}
    body = None
    if payload is not None:
        headers = {"Content-Type": "application/json", "X-HSD-Token": token}
        body = json.dumps(payload).encode()
    req = urllib.request.Request(BASE + path, data=body, headers=headers)
    return json.load(urllib.request.urlopen(req, timeout=30))


start = time.monotonic()
identifier = request("/api/jobs", {"workbook_path": str(test_book), "source_path": str(ai_zip),
                                  "output_root": str(WORK / "输出结果"), "start_number": 1})["id"]
(WORK / "job_id.txt").write_text(identifier)
deadline = time.monotonic() + 300
previous_phase = None
while time.monotonic() < deadline:
    job = request("/api/jobs/" + identifier)
    if job["status"] != previous_phase:
        print(job["status"], job["progress"]["message"], flush=True)
        previous_phase = job["status"]
    if job["status"] in {"ready", "error"}:
        break
    time.sleep(1)
assert job["status"] == "ready", job.get("error")
assert len(job["rows"]) == 60 and len(job["files"]) == 60
match_seconds = time.monotonic() - start
expected = json.loads((ROOT / "tests" / "sample_visual_reference.json").read_text("utf-8"))["row_to_ai_index"]
for row in job["rows"]:
    assert row["candidates"][0]["file_id"] == f"f{expected[str(row['row_number'])]:04d}", row
    if row["status"] in {"auto", "confirmed"}:
        assert row["file_id"] == row["candidates"][0]["file_id"]
initial_stats = dict(job["stats"])
# Measured on the 60-picture sample: 44 automatic, 16 requiring a person.
assert initial_stats["auto"] == 44 and initial_stats["review"] == 16, initial_stats
assert job["rows"][0]["status"] == "review"
assert job["rows"][0]["planned_number"] == ""
assert job["rows"][1]["planned_number"] == "HSD0001"
# The independently visually checked first picture needs human confirmation.
job = request("/api/jobs/" + identifier + "/resolve", {"row_id": "r2", "file_id": "f0001"})
assert job["rows"][0]["planned_number"] == "HSD0001"
assert job["rows"][1]["planned_number"] == "HSD0002"
assert all(r["planned_number"] == r["number"] for r in job["rows"][2:])
print("MATCH", job["stats"], round(match_seconds, 2), flush=True)
request("/api/jobs/" + identifier + "/export", {})
deadline = time.monotonic() + 120
while time.monotonic() < deadline:
    result = request("/api/jobs/" + identifier)
    if result["status"] != "exporting":
        break
    time.sleep(0.5)
assert result["status"] == "done", result.get("error")
output = Path(result["output_dir"])
report = read_export_record(DATA, identifier)
assert report["new_numbers"] == 2
assert report["exported"] == job["stats"]["exportable"]
assert report["pending"] == 60 - report["exported"]
for mapping in report["mapping"]:
    assert digest(output / "已编号AI" / mapping["output"]) == mapping["sha256"]
with zipfile.ZipFile(test_book) as a, zipfile.ZipFile(output / report["workbook"]) as b:
    assert a.namelist() == b.namelist()
    changed = [n for n in a.namelist() if a.read(n) != b.read(n)]
    assert changed == ["xl/worksheets/sheet1.xml"], changed
    sheet = b.read(changed[0]).decode()
    for number in ("HSD0001", "HSD0002"):
        assert number in sheet
for path, value in before.items():
    assert digest(path) == value, f"Original changed: {path}"
summary = {"packaged_app": BASE, "sample_dir": str(SAMPLE),
           "job_id": identifier, "matching_seconds": round(match_seconds, 2),
           "initial_stats": initial_stats,
           "stats": job["stats"], "report": report, "all_60_top_candidates_visually_referenced": True,
           "original_input_hashes_unchanged": True, "only_target_worksheet_part_changed": True,
           "output_dir": str(output)}
(WORK / "验收结果.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), "utf-8")
print("PASS", json.dumps({"stats": job["stats"], "new_numbers": report["new_numbers"], "pending": report["pending"], "output": str(output)}, ensure_ascii=False), flush=True)
