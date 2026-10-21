"""Isolated, synthetic-only UI acceptance server (never loads jobs, keys or AI).

Example: python tools/ui_fixture_server.py --port 8812 --static-dir tmp/ui_v150/baseline/static
Open /?scenario=review&count=500&mode=employee. Keep this test server private.
The real static assets and their event handlers are used without modification.
"""
from __future__ import annotations

import argparse
import copy
import io
import json
import secrets
import socket
import time
import zipfile
from collections import Counter
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_file, session
from PIL import Image, ImageDraw


SCENARIOS = {"review", "mixed", "auto", "partial", "done", "queued", "matching", "ai-review",
             "ai-failed", "ai-off", "error", "conflict", "save-failed", "import-local", "import-employee",
             "cancelling", "cancelled", "cancel-failed", "download-failed", "download-auth",
             "upload-lost", "upload-pending"}
ROOT = Path(__file__).resolve().parents[1]
MEASUREMENT = r"""
(() => {
  const metrics={fetches:0, table_mutations:0, table_replacements:0, detail_mutations:0, actions:[]};
  window.__fixtureMetrics=metrics;
  const publish=()=>document.documentElement.dataset.fixtureMetrics=JSON.stringify(metrics);
  const original=window.fetch;
  let pending=null;
  window.fetch=async(...args)=>{
    metrics.fetches++;publish();const action=pending;
    const response=await original(...args);
    if(action && /\/(resolve|undo|export)$/.test(String(args[0]))){action.response=performance.now();action.status=response.status;}
    return response;
  };
  document.addEventListener('click',event=>{
    const el=event.target.closest('[data-row-id],[data-candidate-id],#confirm-row-button,#skip-row-button,#undo-button,#summary-undo-button,#candidate-toggle,[data-filter],#summary-export-button');
    if(!el)return;
    pending={action:el.id||Object.keys(el.dataset).join(','),start:performance.now(),network:['confirm-row-button','skip-row-button','undo-button','summary-undo-button','summary-export-button'].includes(el.id)};
  },true);
  document.addEventListener('DOMContentLoaded',()=>{
    const observer=new MutationObserver(records=>{
      for(const record of records){
        if(record.target.id==='rows-body'){metrics.table_mutations++;if(record.addedNodes.length>1&&record.removedNodes.length>1)metrics.table_replacements++;}
        if(record.target.id==='review-panel')metrics.detail_mutations++;
      }
      if(pending){
        const action=pending;if(!action.feedback)action.feedback=performance.now();
        if(!action.network||action.response){pending=null;requestAnimationFrame(()=>requestAnimationFrame(()=>{
          metrics.actions.push({action:action.action,first_feedback_ms:Math.round((action.feedback-action.start)*100)/100,
            response_ms:action.response?Math.round((action.response-action.start)*100)/100:null,
            response_status:action.status||null,until_render_ms:Math.round((performance.now()-action.start)*100)/100});publish();
        }));}
      }
      publish();
    });
    observer.observe(document.body,{subtree:true,childList:true});publish();
  });
})();
"""


def synthetic_png(identifier: str, thumb: bool = False) -> bytes:
    """Deliberately artificial long strips, visibly labelled as UI test data."""
    index = int("".join(c for c in identifier if c.isdigit()) or "1")
    width, height = (320, 80) if thumb else (1280, 260)
    image = Image.new("RGB", (width, height), "#f5f0df")
    draw = ImageDraw.Draw(image)
    colors = ["#136f73", "#d67948", "#768b36", "#8d518e"]
    color = colors[index % len(colors)]
    step = max(25, width // 12)
    for x in range(0, width, step):
        if index % 2:
            draw.rectangle((x, 0, x + step // 3, height), fill=color)
        else:
            for y in range(step // 2, height, step):
                draw.ellipse((x, y, x + step // 3, y + step // 3), fill=color)
    draw.rectangle((8, 8, min(width-8, 300), 33), fill="white")
    draw.text((12, 13), f"SYNTHETIC UI TEST - {identifier}", fill="black")
    output = io.BytesIO()
    image.save(output, "PNG")
    return output.getvalue()


def make_job(scenario: str, count: int, identifier: str) -> dict:
    rows, files = [], []
    for index in range(1, count + 1):
        fid = f"f{index}"
        for file_id in (fid, f"g{index}"):
            files.append({"id": file_id, "name": f"界面测试-{file_id}.ai", "relative_path": f"合成素材/{file_id}.ai", "issue": ""})
        status = "auto" if scenario in {"auto", "done", "download-failed", "download-auth"} else "review"
        if scenario in {"mixed", "partial"}:
            status = "auto" if index < count-4 else "review" if index < count-1 else "unmatched" if index == count-1 else "skipped"
        row = {"id": f"r{index}", "row_number": index+1, "number": f"HSD{index:04}" if index % 3 else "",
               "planned_number": f"HSD{index:04}" if status == "auto" else "", "status": status,
               "file_id": fid if status == "auto" else None,
               "reason": "两个文件图案接近" if status == "review" else "没有可信候选，请查找或跳过" if status == "unmatched" else "",
               "candidates": [{"file_id": fid, "score": .91, "evidence": {"method": "texture"}},
                              {"file_id": f"g{index}", "score": .89, "evidence": {"method": "texture"}}]}
        if scenario not in {"ai-off", "auto", "done"} and index % 3 == 1:
            row["ai_review"] = {"verdict": "same", "candidate_id": fid, "outcome": "suggestion",
                                "reason": "图案排列接近；右侧局部细节尚需对照。", "differences": ["右侧局部细节尚需对照"],
                                "gate_reason": "尚无独立业务验证资格", "checks": {"content_same": True, "colors_same": True, "complete_coverage": False}}
        if scenario == "ai-failed":
            row["ai_review"] = {"verdict": "error", "outcome": "error", "candidate_id": fid,
                                "reason": "复核连接超时，请人工对照图片；本机匹配结果仍然保留。"}
        rows.append(row)
    status = {"done": "done", "queued": "queued", "matching": "matching", "ai-review": "ai_review", "error": "error",
              "cancelling": "cancelling", "cancelled": "cancelled", "cancel-failed": "matching",
              "download-failed": "done", "download-auth": "done"}.get(scenario, "ready")
    usage = {"requests": 3, "successes": 2, "failures": 1, "unknown_usage_requests": 1,
             "estimated_usd": .0023, "cost_incomplete": True}
    job = {"id": identifier, "status": status, "revision": 1, "can_undo": False,
           "workbook_name": "界面测试数据-编号表.xlsx", "sheet_name": "合成展示", "source_name": "界面测试数据.zip",
           "output_target": "D:/界面测试数据/输出", "output_root": "D:/界面测试数据/输出", "output_dir": "D:/界面测试数据/输出/结果",
           "download_ready": status == "done", "rows": rows, "files": files, "warnings": [],
           "progress": {"message": "正在比对合成预览，仅供界面验收", "current": 8, "total": 20}, "queue_position": 2,
           "error": "AI 压缩包内没有可读取的文件，请重新选择 ZIP。" if status == "error" else None,
           "_history": [], "_scenario": scenario, "_failed_once": False,
           "cancel_requested": status in {"cancelling", "cancelled"}, "_cancel_polls": 2,
           "ai_review": None if scenario == "ai-off" else {"mode": "evaluation", "reviewed": 3, "suggested_same": 2,
               "auto_passed": 0, "usage": usage, "can_retry": scenario == "ai-failed", "message": "正在复核合成预览"}}
    return job


def create_fixture_app(static_dir: Path, host: str = "127.0.0.1") -> Flask:
    app = Flask(__name__, static_folder=str(static_dir.resolve()), static_url_path="/static")
    app.secret_key = secrets.token_bytes(32)
    app.config.update(SESSION_COOKIE_NAME="hsd_ui_fixture_" + secrets.token_hex(4), SESSION_COOKIE_HTTPONLY=True,
                      SESSION_COOKIE_SAMESITE="Strict", MAX_CONTENT_LENGTH=4*1024*1024)
    jobs: dict[str, dict] = {}
    uploads: dict[str, dict] = {}
    metrics: Counter = Counter()
    local = {"127.0.0.1", "::1", host}
    local.update(socket.gethostbyname_ex(socket.gethostname())[2])

    @app.before_request
    def local_only():
        if request.remote_addr not in local:
            return jsonify(error="界面测试服务只允许主机本地访问。"), 403
        metrics[f"{request.method} {request.path}"] += 1

    def current_job(identifier):
        if identifier != session.get("job") or identifier not in jobs:
            return None
        return jobs[identifier]

    def snapshot(job):
        result = {key: copy.deepcopy(value) for key, value in job.items() if not key.startswith("_")}
        result["can_undo"] = bool(job["_history"])
        result["stats"] = {status: sum(row["status"] == status for row in job["rows"]) for status in ("auto", "confirmed", "review", "unmatched", "skipped")}
        result["stats"]["ai_auto"] = 0
        if session.get("employee"):
            result.update(output_target="完成后下载结果 ZIP", output_root="", output_dir="结果已就绪，可下载")
        return result

    @app.get("/")
    def index():
        scenario = request.args.get("scenario", "review")
        if scenario not in SCENARIOS:
            return jsonify(error="未知的合成测试场景"), 400
        count = min(500, max(1, request.args.get("count", 20, type=int)))
        employee = request.args.get("mode", "employee") == "employee"
        if scenario == "import-local":
            employee = False
        if scenario == "import-employee":
            employee = True
        session.clear()
        session["employee"] = employee
        session["delay_ms"] = min(500, max(0, request.args.get("delay", 60, type=int)))
        session["scenario"] = scenario
        session["fixture_owner"] = secrets.token_hex(12)
        if not scenario.startswith(("import-", "upload-")):
            identifier = "synthetic-" + secrets.token_hex(6)
            session["job"] = identifier
            jobs[identifier] = make_job(scenario, count, identifier)
        html = (static_dir / "index.html").read_text("utf-8")
        access = {"lan": employee, "remote": employee}
        html = html.replace("__HSD_TOKEN__", json.dumps("synthetic-test-token")).replace("__HSD_ACCESS__", json.dumps(access))
        remembered = f"sessionStorage.setItem('hsd-active-job',{json.dumps(session['job'])});" if session.get("job") else "sessionStorage.removeItem('hsd-active-job');"
        html = html.replace("</head>", f"<script>{remembered}{MEASUREMENT}</script></head>")
        html = html.replace("</body>", '<div style="position:fixed;bottom:0;left:4px;z-index:9999;background:#fff3bd;color:#513a00;font:12px sans-serif;padding:3px 7px;pointer-events:none">界面测试数据 · 合成图片／模拟接口 · 非业务验收</div></body>')
        return html

    @app.get("/_fixture/metrics")
    def fixture_metrics():
        return jsonify(dict(metrics))

    @app.get("/api/config")
    def config():
        employee = session.get("employee", True)
        return jsonify(version="UI-TEST", access={"lan": employee, "remote": employee},
                       active_job_id=session.get("job"), last_workbook="D:/界面测试数据/编号表.xlsx" if not employee else "",
                       last_source="D:/界面测试数据/素材.zip" if not employee else "", last_output="D:/界面测试数据/输出" if not employee else "", last_start=1)

    @app.route("/api/ai/settings", methods=["GET", "POST"])
    def settings():
        if request.method == "POST" and session.get("employee"):
            return jsonify(error="此操作只能在主机上完成。"), 403
        return jsonify(enabled=session.get("scenario") != "ai-off", configured=True, mode="evaluation", model="synthetic-model-NOT-REAL")

    @app.get("/api/ai/usage")
    def usage():
        if session.get("employee"):
            return jsonify(error="累计费用仅在主机查看。"), 403
        return jsonify(requests=3, successes=2, failures=1, estimated_usd=.0023, unknown_usage_requests=1, cost_incomplete=True)

    @app.get("/api/jobs/<identifier>")
    def get_job(identifier):
        job = current_job(identifier)
        if not job:
            return jsonify(error="不存在此合成测试任务"), 404
        if job["status"] == "exporting":
            job.update(status="done", download_ready=True)
        if job["status"] == "cancelling":
            if job["_cancel_polls"]:
                job["_cancel_polls"] -= 1
            else:
                job.update(status="cancelled", progress={"message": "合成任务已停止", "current": 0, "total": 0})
        return jsonify(snapshot(job))

    @app.post("/api/jobs/<identifier>/<action>")
    def action(identifier, action):
        job = current_job(identifier)
        if not job:
            return jsonify(error="不存在此合成测试任务"), 404
        time.sleep(session.get("delay_ms", 60)/1000)
        data = request.get_json(silent=True) or {}
        if action == "cancel":
            if type(data.get("expected_revision")) is not int or data["expected_revision"] != job["revision"]:
                return jsonify(error="其他页面已更新本批记录，请刷新后重试。"), 409
            if job["_scenario"] == "cancel-failed" and not job["_failed_once"]:
                job["_failed_once"] = True
                return jsonify(error="模拟停止连接失败，请重试。"), 503
            if job["status"] not in {"queued", "importing", "matching", "ai_review", "exporting", "cancelling", "cancelled"}:
                return jsonify(error="本批已经结束，无需停止。"), 400
            if job["status"] != "cancelled":
                job.update(status="cancelling", cancel_requested=True)
                job["revision"] += 1
            return jsonify(snapshot(job))
        if job["status"] in {"cancelling", "cancelled"}:
            return jsonify(error="本批已请求停止，不能继续操作。"), 409
        if job["_scenario"] in {"conflict", "save-failed"} and not job["_failed_once"]:
            job["_failed_once"] = True
            if job["_scenario"] == "conflict":
                job["revision"] += 1
                return jsonify(error="其他页面已更新本批记录，已刷新，请核对后重试。"), 409
            return jsonify(error="模拟保存失败，记录未改变，请重试。"), 503
        if data.get("expected_revision", job["revision"]) != job["revision"]:
            return jsonify(error="其他页面已更新本批记录，请刷新后重试。"), 409
        if action == "resolve":
            row = next((row for row in job["rows"] if row["id"] == data.get("row_id")), None)
            if not row:
                return jsonify(error="测试记录不存在"), 400
            job["_history"].append(copy.deepcopy(row))
            row["status"] = "confirmed" if data.get("file_id") else "skipped"
            row["file_id"] = data.get("file_id")
            row["planned_number"] = row["number"] or (f"HSD{row['row_number']:04}" if row["file_id"] else "")
            row["reason"] = "员工已确认" if row["file_id"] else "员工已跳过"
        elif action == "undo":
            if not job["_history"]:
                return jsonify(error="没有可撤销记录"), 400
            original = job["_history"].pop()
            index = next(i for i, row in enumerate(job["rows"]) if row["id"] == original["id"])
            job["rows"][index] = original
            job["last_undone_row_id"] = original["id"]
        elif action == "export":
            job["status"] = "exporting"
            job["progress"] = {"message": "正在生成合成测试结果", "current": 0, "total": 0}
        elif action == "ai-review":
            return jsonify(error="界面测试不调用模型，请人工处理。"), 503
        elif action == "open-output":
            if session.get("employee"):
                return jsonify(error="此操作只能在主机上完成。"), 403
        else:
            return jsonify(error="未知测试操作"), 404
        job["revision"] += 1
        return jsonify(snapshot(job))

    @app.post("/api/jobs")
    @app.post("/api/jobs/upload")
    def create():
        request_id = request.headers.get("X-HSD-Upload-ID")
        if request_id and request_id in uploads:
            claim = uploads[request_id]
            if claim["owner"] != session.get("fixture_owner"):
                return jsonify(error="不存在此合成上传"), 404
            if claim["state"] == "completed":
                return jsonify(id=claim["job_id"], reused=True)
            return jsonify(error="本次上传仍待确认或已经停止。"), 409
        identifier = "synthetic-" + secrets.token_hex(6)
        session["job"] = identifier
        jobs[identifier] = make_job("mixed", 20, identifier)
        if request_id:
            uploads[request_id] = {"owner": session.get("fixture_owner"), "state": "completed", "job_id": identifier, "polls": 2}
            if session.get("scenario") == "upload-pending":
                uploads[request_id]["state"] = "pending"
            if session.get("scenario") in {"upload-lost", "upload-pending"}:
                return jsonify(error="模拟上传已受理但回包失败，请核对状态。"), 503
        return jsonify(id=identifier)

    @app.get("/api/jobs/upload-status/<request_id>")
    def upload_status(request_id):
        claim = uploads.get(request_id)
        if not claim:
            return jsonify(state="missing")
        if claim["owner"] != session.get("fixture_owner"):
            return jsonify(error="不存在此合成上传"), 404
        if claim["state"] == "pending":
            if claim["polls"]:
                claim["polls"] -= 1
            else:
                claim["state"] = "cancelled" if claim.get("cancellation_requested") else "completed"
        result = {key: claim[key] for key in ("state", "job_id", "cancellation_requested") if key in claim}
        return jsonify(result)

    @app.post("/api/jobs/upload-status/<request_id>/cancel")
    def cancel_upload(request_id):
        claim = uploads.get(request_id)
        if not claim:
            uploads[request_id] = {"owner": session.get("fixture_owner"), "state": "cancelled"}
            return jsonify(state="cancelled")
        if claim["owner"] != session.get("fixture_owner"):
            return jsonify(error="不存在此合成上传"), 404
        if claim["state"] == "pending":
            claim["cancellation_requested"] = True
        elif claim["state"] == "completed":
            job = jobs[claim["job_id"]]
            if job["status"] in {"queued", "importing", "matching", "ai_review", "exporting"}:
                job.update(status="cancelling", cancel_requested=True)
                job["revision"] += 1
        return jsonify({key: claim[key] for key in ("state", "job_id", "cancellation_requested") if key in claim})

    @app.get("/api/jobs/<identifier>/image/<kind>/<image_id>")
    def image(identifier, kind, image_id):
        job = current_job(identifier)
        if not job:
            return jsonify(error="不存在此合成测试任务"), 404
        etag = f"synthetic-{identifier}-{kind}-{image_id}-{request.args.get('size','full')}"
        if request.if_none_match.contains(etag):
            return Response(status=304)
        response = Response(synthetic_png(image_id, request.args.get("size") == "thumb"), mimetype="image/png")
        response.set_etag(etag)
        response.headers["Cache-Control"] = "private, max-age=86400, immutable"
        return response

    @app.get("/api/jobs/<identifier>/download-status")
    def download_status(identifier):
        job = current_job(identifier)
        if not job or job["status"] != "done":
            return jsonify(error="合成测试结果未完成"), 400
        return jsonify(ready=True, download_url=f"/api/jobs/{identifier}/download")

    @app.get("/api/jobs/<identifier>/download")
    def download(identifier):
        job = current_job(identifier)
        if not job or job["status"] != "done":
            return jsonify(error="合成测试结果未完成"), 400
        if job["_scenario"] == "download-failed":
            return jsonify(error="模拟下载校验失败，请重新处理。"), 400
        if job["_scenario"] == "download-auth":
            return jsonify(error="模拟登录已失效，请先输入员工访问码。"), 401
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            archive.writestr("界面测试数据.txt", "此文件仅用于UI下载展示，不含真实业务数据，不是AI资格验证。")
        output.seek(0)
        return send_file(output, mimetype="application/zip", as_attachment=True, download_name="界面测试数据.zip")

    @app.errorhandler(404)
    def not_found(_):
        return jsonify(error="界面测试接口未实现"), 404

    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8812, type=int)
    parser.add_argument("--static-dir", type=Path, default=ROOT / "hsd_tool" / "static")
    args = parser.parse_args()
    if args.port in {8805, 8807}:
        parser.error("禁止占用实际员工服务端口")
    if args.host not in {"127.0.0.1", *socket.gethostbyname_ex(socket.gethostname())[2]}:
        parser.error("只能绑定本机现有地址")
    create_fixture_app(args.static_dir.resolve(), args.host).run(host=args.host, port=args.port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
