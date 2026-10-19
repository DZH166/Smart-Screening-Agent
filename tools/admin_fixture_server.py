"""Source-only administrator UI fixture: artificial jobs, zero real API calls.

Run with the development Python/pytest dependencies, for example::

    .venv\\Scripts\\python.exe tools/admin_fixture_server.py --port 8821 --work tmp/admin-demo-new

The work directory must not exist. This tool binds only 127.0.0.1, uses isolated
session-only fake credentials, and injects an unmistakable demonstration banner.
It exercises the real server, workflow, dispatcher, client parser and admin UI.
Its transport never opens a socket. It cannot establish AI business qualification.
"""
from __future__ import annotations

import argparse
import atexit
from io import BytesIO
import json
import os
from pathlib import Path
import secrets
import sys
import threading
import time
import urllib.error
import uuid
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))


def create_fixture(work, *, delay=2):
    """Create a development fixture app without reading the user's settings."""
    from flask import jsonify, request
    from PIL import Image
    from hsd_tool.ai_client import DeepSeekClient, ENDPOINT, PAIR_CHECKS
    from hsd_tool.ai_key_pool import ApiKeyPool
    from hsd_tool.ai_settings import AiSettings
    from hsd_tool.server import create_app
    import hsd_tool.ai_workflow as workflow
    from test_ai_policy import alignment_for, competition_for, measured_evidence
    from test_service import prepared

    work = Path(work).resolve()
    work.mkdir(parents=True, exist_ok=False)
    # Never inherit a real provider credential, even when one is in the shell's
    # environment. The temporary replacement affects only this fixture process.
    with patch.dict(os.environ, {"DEEPSEEK_API_KEY": ""}):
        app = create_app(work / "data", token=secrets.token_urlsafe(32),
                         settings_dir=work / "unused-isolated-settings")
    manager = app.config["HSD_MANAGER"]
    manager.ai_settings = AiSettings(work / "session-settings", protector=None, environ={})
    manager.ai_settings.save_pool({"expected_revision": 0, "add": [
        {"api_key": "sk-synthetic-admin-demo-a-never-real", "label": "演示 Key A"},
        {"api_key": "sk-synthetic-admin-demo-b-never-real", "label": "演示 Key B"}]})
    manager.ai_settings.save({"enabled": True})
    manager.ai_key_pool = ApiKeyPool(manager.ai_settings)
    control = {"running": False, "last_job": None, "scenario": None,
               "mock_requests": 0, "error": ""}
    lock = threading.RLock()

    class Response(BytesIO):
        def geturl(self):
            return ENDPOINT

    class ArtificialTransport:
        """No urllib opener is reachable from this transport."""
        def __init__(self, status):
            self.statuses = [status, 200]

        def open(self, outgoing, timeout=None):
            assert outgoing.full_url == ENDPOINT
            # Parse only artificial local content to bind the fake pair reply.
            payload = json.loads(outgoing.data)
            content = payload["messages"][1]["content"]
            identities = json.loads(content[0]["text"])["candidate_ids"]
            with lock:
                control["mock_requests"] += 1
                status = self.statuses.pop(0) if self.statuses else 200
            time.sleep(delay)
            if status != 200:
                raise urllib.error.HTTPError(ENDPOINT, status, "synthetic fixture", {}, BytesIO())
            reviews = []
            for index, identity in enumerate(identities):
                reviews.append({"candidate_id": identity,
                    "verdict": "same" if index == 0 else "different",
                    "reason": "合成演示：首候选相同" if index == 0 else "合成演示：备选颜色不同",
                    "checks": {name: index == 0 for name in PAIR_CHECKS},
                    "differences": [] if index == 0 else ["合成演示颜色差异"]})
            result = {"id": "synthetic-demo-not-provider", "model": "deepseek-flash",
                "usage": {"prompt_tokens": 100, "completion_tokens": 50},
                "choices": [{"finish_reason": "stop", "message": {"content":
                    json.dumps({"candidate_reviews": reviews}, ensure_ascii=False)}}]}
            return Response(json.dumps(result, ensure_ascii=False).encode("utf-8"))

    def make_job():
        case_dir = work / ("case-" + uuid.uuid4().hex)
        case_dir.mkdir()
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": ""}):
            fixture_manager, job = prepared(case_dir, ["", "KEEP0001"])
        fixture_manager.close()
        for index, (file, color) in enumerate(zip(job["files"], ("red", "blue")), 1):
            file["id"], file["page_count"] = f"f{index:04}", 1
            Image.new("RGB", (240, 60), color).save(file["preview_path"])
            job["rows"][index - 1]["_file_id"] = file["id"]
        row = job["rows"][0]
        row.update(_status="review", _file_id=None, _reason="合成演示：需要二次复核",
                   _reason_code="not_verified", evidence=measured_evidence(),
                   candidates=[{"file_id": "f0001", "score": .92}, {"file_id": "f0002", "score": .65}])
        row["evidence"]["competition"] = competition_for(row, job["files"])
        row["evidence"]["alignment"] = alignment_for(row, job["files"])
        identifier = "demo-" + uuid.uuid4().hex
        job.update(id=identifier, status="ai_review", revision=0, timings={})
        with manager.lock:
            manager.jobs[identifier] = job
            manager._plan(job)
        return identifier

    def run(identifier, scenario):
        transport = ArtificialTransport(401 if scenario == "authentication" else 503)
        try:
            # Inject only this fixture process's workflow factory. Every client
            # request still goes through ManagedReviewClient and strict parsing.
            with patch.object(workflow, "DeepSeekClient",
                              lambda key: DeepSeekClient(key, opener=transport)):
                workflow.review_job(manager, identifier)
        except Exception:
            with lock:
                control["error"] = "合成演示执行失败，请查看源测试；未调用真实接口。"
        finally:
            with manager.lock:
                manager.jobs[identifier]["status"] = "ready"
            with lock:
                control["running"] = False

    @app.post("/fixture/run")
    def fixture_run():
        scenario = request.get_json().get("scenario")
        if scenario not in {"authentication", "provider"}:
            return jsonify(error="请选择合成演示场景。"), 400
        with lock:
            if control["running"]:
                return jsonify(error="合成演示正在运行，请等待完成。"), 409
            identifier = make_job()
            control.update(running=True, last_job=identifier, scenario=scenario, error="")
            manager.pool.submit(run, identifier, scenario)
        return jsonify(ok=True, job_id=identifier, synthetic=True, real_api_calls=0)

    @app.get("/fixture/status")
    def fixture_status():
        with lock:
            result = {**control, "synthetic": True, "real_api_calls": 0}
        if result["last_job"]:
            result["stats"] = manager.snapshot(result["last_job"])["stats"]
        return jsonify(result)

    banner = '''<section id="fixture-banner" style="border:3px solid #b45309;background:#fff7d6;padding:14px;margin:12px;font:16px sans-serif;color:#643b00"><strong>合成演示 · 0 真实 API</strong><p>隔离测试服务，仅使用虚构图片、虚构 Key 和本进程模拟响应。此演示不构成 AI 业务准确率或放行资格。</p><button type="button" id="fixture-auth">演示：401 后换 Key</button> <button type="button" id="fixture-provider">演示：503 后同 Key 重试</button><p id="fixture-status" role="status">点击演示按钮，在下方实时调试区观察调用、重试、返回与保留人工确认。</p></section><script>
    (() => { const auth=document.getElementById('fixture-auth'), provider=document.getElementById('fixture-provider'), status=document.getElementById('fixture-status'); let timer=null;
      async function update(){try{const r=await fetch('/fixture/status',{cache:'no-store'});const d=await r.json();auth.disabled=provider.disabled=d.running;status.textContent=d.error|| (d.running?'合成演示运行中：请查看下方实时调试区…':`合成演示就绪 · 模拟请求 ${d.mock_requests} 次 · 真实 API 0 次${d.stats?' · AI 自动通过 '+d.stats.ai_auto+'，保留人工 '+d.stats.review+' 项':''}`);if(!d.running){clearInterval(timer);timer=null;}}catch(_){status.textContent='演示状态读取失败，可刷新页面重试。';}}
      async function start(scenario){auth.disabled=provider.disabled=true;status.textContent='正在启动合成演示…';try{const r=await fetch('/fixture/run',{method:'POST',headers:{'Content-Type':'application/json','X-HSD-Token':window.HSD_TOKEN},body:JSON.stringify({scenario})});const d=await r.json();if(!r.ok)throw new Error(d.error||'启动失败');if(!timer)timer=setInterval(update,500);await update();}catch(e){status.textContent=e.message;auth.disabled=provider.disabled=false;}}
      auth.addEventListener('click',()=>start('authentication'));provider.addEventListener('click',()=>start('provider'));update();
    })();</script>'''

    @app.after_request
    def mark_demonstration(response):
        if request.path == "/admin" and response.status_code == 200:
            response.set_data(response.get_data(as_text=True).replace("<body>", "<body>" + banner, 1))
        return response

    atexit.register(manager.close)
    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8821)
    parser.add_argument("--work", type=Path, required=True)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("port must be between 1024 and 65535")
    app = create_fixture(args.work)
    app.config["HSD_PORT"] = args.port
    print(f"Synthetic admin fixture only: http://127.0.0.1:{args.port}/admin ; real API calls = 0", flush=True)
    from werkzeug.serving import make_server
    server = make_server("127.0.0.1", args.port, app, threaded=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()
        app.config["HSD_MANAGER"].close()


if __name__ == "__main__":
    main()
