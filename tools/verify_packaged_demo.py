"""Exercise the packaged app on generated artwork when the business sample is absent.

The real-sample acceptance lives in verify_packaged.py and needs 测试样本/.
This companion script builds a disposable workbook plus one AI file with the same
programmatic artwork, then drives the packaged executable through the whole flow:
match -> summary numbers -> export -> hash checks. It never replaces the real
acceptance; it only proves the frozen build runs and stays non-destructive.
"""
import hashlib
import json
import re
import subprocess
import sys
import time
import urllib.request
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import cv2
import numpy as np
import pymupdf
from PIL import Image
from test_workbook import image_cell, make_book

EXE = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "dist" / "HSD图号助手" / "HSD图号助手.exe"
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 8792
WORK = ROOT / "tmp" / "packaged_demo"
WORK.mkdir(parents=True, exist_ok=True)


def stripes(width=900, height=140, period=36):
    image = np.full((height, width, 3), 250, np.uint8)
    palette = [(40, 60, 150), (232, 232, 236), (198, 118, 58), (238, 218, 96)]
    x, index = 0, 0
    while x < width:
        cv2.rectangle(image, (x, 0), (min(x + period, width), height), palette[index % len(palette)], -1)
        x += period
        index += 1
    return image


pattern = stripes()
stream = BytesIO()
Image.fromarray(cv2.cvtColor(pattern, cv2.COLOR_BGR2RGB)).save(stream, "PNG")
rows = '<row r="2"><c r="A2" s="1"/>' + image_cell(2) + "</row>"
book = make_book(WORK, rows, image_data=stream.getvalue())
ai_dir = WORK / "ai"
ai_dir.mkdir(exist_ok=True)
encoded = cv2.imencode(".png", pattern)[1].tobytes()
with pymupdf.open() as doc:
    page = doc.new_page(width=pattern.shape[1], height=pattern.shape[0])
    page.insert_image(page.rect, stream=encoded)
    doc.save(ai_dir / "line_a.ai")

book_before = hashlib.sha256(book.read_bytes()).hexdigest()
ai_before = hashlib.sha256((ai_dir / "line_a.ai").read_bytes()).hexdigest()

process = subprocess.Popen([str(EXE), "--no-browser", "--port", str(PORT), "--data-dir", str(WORK / "state")])
base = f"http://127.0.0.1:{PORT}"
try:
    ready = False
    for _ in range(80):
        time.sleep(0.5)
        try:
            with urllib.request.urlopen(base + "/api/health", timeout=2) as response:
                json.load(response)
            ready = True
            break
        except Exception:
            continue
    assert ready, "packaged app did not start"

    with urllib.request.urlopen(base + "/", timeout=5) as response:
        html = response.read().decode("utf-8")
    token = json.loads(re.search(r"window\.HSD_TOKEN\s*=\s*('[^']+'|\"[^\"]+\")", html).group(1))

    def request(path, payload=None):
        headers, body = {}, None
        if payload is not None:
            headers = {"Content-Type": "application/json", "X-HSD-Token": token}
            body = json.dumps(payload).encode()
        return json.load(urllib.request.urlopen(urllib.request.Request(base + path, data=body, headers=headers), timeout=60))

    identifier = request("/api/jobs", {"workbook_path": str(book), "source_path": str(ai_dir),
                                       "output_root": str(WORK / "输出结果"), "start_number": 1})["id"]
    for _ in range(240):
        job = request("/api/jobs/" + identifier)
        if job["status"] in {"ready", "error"}:
            break
        time.sleep(0.5)
    assert job["status"] == "ready", job.get("error")
    assert len(job["rows"]) == 1 and len(job["files"]) == 1
    assert job["stats"]["auto"] == 1 and job["stats"]["needs_attention"] == 0, job["stats"]
    print("MATCH", job["stats"], flush=True)

    request("/api/jobs/" + identifier + "/export", {})
    for _ in range(240):
        result = request("/api/jobs/" + identifier)
        if result["status"] != "exporting":
            break
        time.sleep(0.5)
    assert result["status"] == "done", result.get("error")
    output = Path(result["output_dir"])
    report = json.loads((output / "处理记录.json").read_text("utf-8"))
    for mapping in report["mapping"]:
        digest = hashlib.sha256((output / "已编号AI" / mapping["output"]).read_bytes()).hexdigest()
        assert digest == mapping["sha256"]
    assert hashlib.sha256(book.read_bytes()).hexdigest() == book_before
    assert hashlib.sha256((ai_dir / "line_a.ai").read_bytes()).hexdigest() == ai_before
    summary = {"packaged_app": str(EXE), "job_id": identifier, "stats": job["stats"],
               "report": report, "originals_unchanged": True, "output_dir": str(output)}
    (WORK / "验收结果.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), "utf-8")
    print("PASS", json.dumps({"stats": job["stats"], "exported": report["exported"],
                              "pending": report["pending"]}, ensure_ascii=False), flush=True)
finally:
    process.terminate()
    try:
        process.wait(timeout=10)
    except Exception:
        process.kill()
