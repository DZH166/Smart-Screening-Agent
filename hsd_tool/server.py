"""Loopback-only HTTP interface for the desktop application."""
from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

from flask import Flask, jsonify, request, send_file

from .service import JobManager


def create_app(data_dir: str | Path, token: str | None = None):
    static = Path(__file__).resolve().parent / "static"
    app = Flask(__name__, static_folder=str(static), static_url_path="/static")
    app.config.update(MAX_CONTENT_LENGTH=64 * 1024, JSON_AS_ASCII=False)
    manager = JobManager(data_dir)
    token = token or secrets.token_urlsafe(32)
    app.config["HSD_TOKEN"] = token
    app.config["HSD_MANAGER"] = manager
    app.config["HSD_INSTANCE"] = secrets.token_hex(16)
    app.config["HSD_SHUTDOWN"] = None
    dialog_lock = threading.Lock()

    @app.before_request
    def guard_local():
        if request.remote_addr not in {"127.0.0.1", "::1", None}:
            return jsonify(error="仅支持本机访问。"), 403
        if request.host.split(":", 1)[0] not in {"127.0.0.1", "localhost"}:
            return jsonify(error="不支持此访问地址。"), 403
        if request.method == "POST":
            provided = request.headers.get("X-HSD-Token", "")
            if not secrets.compare_digest(provided, token):
                return jsonify(error="会话已失效，请重新打开工具页面。"), 403
            origin = request.headers.get("Origin")
            if origin and origin != request.host_url.rstrip("/"):
                return jsonify(error="请求来源不匹配。"), 403
            if not request.is_json:
                return jsonify(error="请求必须使用 JSON 格式。"), 400

    @app.after_request
    def response_headers(response):
        if "Cache-Control" not in response.headers:
            response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        # The inline token/bootstrap is the only inline script; UI does not load external resources.
        response.headers["Content-Security-Policy"] = "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'"
        return response

    @app.errorhandler(ValueError)
    def invalid(exc):
        return jsonify(error=str(exc)), 400

    @app.errorhandler(KeyError)
    def missing(exc):
        return jsonify(error=str(exc.args[0])), 404

    @app.errorhandler(OSError)
    def file_error(exc):
        return jsonify(error=f"无法访问文件或文件夹：{exc}"), 400

    @app.get("/")
    def index():
        html = (static / "index.html").read_text("utf-8")
        return html.replace("__HSD_TOKEN__", json.dumps(token))

    @app.get("/api/health")
    def health():
        return jsonify(app="hsd-number-tool", instance=app.config["HSD_INSTANCE"])

    @app.get("/api/config")
    def config():
        return jsonify(manager.config())

    @app.post("/api/pick")
    def pick():
        kind = request.get_json().get("kind")
        if kind not in {"workbook", "zip", "folder", "output"}:
            raise ValueError("不支持的选择类型。")
        if not dialog_lock.acquire(blocking=False):
            raise ValueError("文件选择窗口已打开，请先完成选择。")
        try:
            with tempfile.TemporaryDirectory(prefix="hsd_picker_", dir=data_dir) as temporary:
                result_path = Path(temporary) / "selection.json"
                command = [sys.executable]
                if not getattr(sys, "frozen", False):
                    command += ["-m", "hsd_tool"]
                command += ["--pick", kind, "--result", str(result_path)]
                kwargs = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
                subprocess.run(command, check=True, **kwargs)
                result = json.loads(result_path.read_text("utf-8"))
                if result.get("error"):
                    raise ValueError(result["error"])
                return jsonify(path=result.get("path", ""))
        except subprocess.CalledProcessError:
            raise ValueError("文件选择窗口启动失败。可以将文件或文件夹路径直接粘贴到输入框。")
        finally:
            dialog_lock.release()

    @app.post("/api/jobs")
    def create_job():
        return jsonify(id=manager.create(request.get_json()))

    @app.get("/api/jobs/<identifier>")
    def read_job(identifier):
        return jsonify(manager.snapshot(identifier))

    @app.post("/api/jobs/<identifier>/resolve")
    def resolve(identifier):
        payload = request.get_json()
        return jsonify(manager.resolve(identifier, payload.get("row_id"), payload.get("file_id"),
                                       revert=bool(payload.get("revert"))))

    @app.post("/api/jobs/<identifier>/export")
    def export(identifier):
        manager.export(identifier)
        return jsonify(id=identifier)

    @app.get("/api/jobs/<identifier>/image/<kind>/<item_id>")
    def image(identifier, kind, item_id):
        if kind not in {"row", "file"}:
            raise KeyError("不存在的图片类型。")
        sent = send_file(manager.image_path(identifier, kind, item_id), conditional=True)
        # A preview never changes inside one job and the URL already carries the
        # job id, so the browser may reuse it instead of re-downloading the same
        # picture after every list re-render. Conditional requests still
        # revalidate, so a new job can never show a stale picture.
        sent.headers["Cache-Control"] = "private, max-age=86400, immutable"
        return sent

    @app.post("/api/jobs/<identifier>/open-output")
    def open_output(identifier):
        job = manager.snapshot(identifier)
        if job["status"] != "done" or not job["output_dir"]:
            raise ValueError("结果尚未导出。")
        if os.name == "nt":
            os.startfile(job["output_dir"])
        return jsonify(ok=True)

    @app.post("/api/shutdown")
    def shutdown():
        with manager.lock:
            if any(j["status"] in {"importing", "matching", "exporting"} for j in manager.jobs.values()):
                raise ValueError("任务正在处理，请完成后再退出工具。")
        callback = app.config.get("HSD_SHUTDOWN")
        if callback:
            threading.Timer(0.3, callback).start()
        return jsonify(ok=True)

    return app
