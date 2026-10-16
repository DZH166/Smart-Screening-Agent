"""Desktop HTTP interface, with an explicit authenticated LAN test mode."""
from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
import tempfile
import threading
from datetime import timedelta
from pathlib import Path

from flask import Flask, jsonify, request, send_file, session
from werkzeug.exceptions import Conflict

from .service import JobManager
from . import __version__


def create_app(data_dir: str | Path, token: str | None = None, *, lan=None):
    static = Path(__file__).resolve().parent / "static"
    app = Flask(__name__, static_folder=str(static), static_url_path="/static")
    app.config.update(MAX_CONTENT_LENGTH=64 * 1024, JSON_AS_ASCII=False)
    if lan:
        app.config.update(SECRET_KEY=secrets.token_bytes(32), SESSION_COOKIE_HTTPONLY=True,
                          SESSION_COOKIE_SAMESITE="Strict", SESSION_COOKIE_NAME="hsd_lan_" + secrets.token_hex(6),
                          PERMANENT_SESSION_LIFETIME=timedelta(hours=8), SESSION_REFRESH_EACH_REQUEST=False)
    manager = JobManager(data_dir)
    token = token or secrets.token_urlsafe(32)
    app.config["HSD_TOKEN"] = token
    app.config["HSD_MANAGER"] = manager
    app.config["HSD_INSTANCE"] = secrets.token_hex(16)
    app.config["HSD_SHUTDOWN"] = None
    runtime = {"frozen": bool(getattr(sys, "frozen", False)), "version": __version__}
    if runtime["frozen"]:
        from .service import sha256
        runtime["executable_sha256"] = sha256(sys.executable)
        manifest = Path(sys.executable).parent / "构建校验.json"
        runtime["build_manifest_sha256"] = sha256(manifest) if manifest.is_file() else None
    dialog_lock = threading.Lock()

    @app.before_request
    def guard_local():
        if lan and not lan.allows(request.remote_addr):
            return jsonify(error="仅允许指定局域网内的电脑访问。"), 403
        if not lan and request.remote_addr not in {"127.0.0.1", "::1", None}:
            return jsonify(error="仅支持本机访问。"), 403
        hosts = {"127.0.0.1", "localhost"} | ({lan.host} if lan else set())
        if request.host.split(":", 1)[0] not in hosts:
            return jsonify(error="不支持此访问地址。"), 403
        port = app.config.get("HSD_PORT")
        if lan and port and request.host not in {f"{host}:{port}" for host in hosts}:
            return jsonify(error="不支持此访问地址。"), 403
        remote = bool(lan and not lan.is_host(request.remote_addr))
        if request.method == "POST":
            origin = request.headers.get("Origin")
            if (origin and origin != request.host_url.rstrip("/")) or (remote and not origin):
                return jsonify(error="请求来源不匹配。"), 403
            if not request.is_json or not isinstance(request.get_json(silent=True), dict):
                return jsonify(error="请求必须使用 JSON 对象。"), 400
        if lan and request.endpoint == "lan_login":
            return None
        if remote and not session.get("lan_authenticated"):
            if request.endpoint == "index" and request.method == "GET":
                return (static / "lan-login.html").read_text("utf-8")
            return jsonify(error="请先输入局域网访问码。"), 401
        if remote and (request.endpoint in {"pick", "open_output", "shutdown"}
                       or (request.endpoint == "save_ai_settings")):
            return jsonify(error="此操作只能在主机上完成。"), 403
        if lan and (request.view_args or {}).get("identifier"):
            with manager.lock:
                job = manager._get(request.view_args["identifier"])
                lan.validate_paths({"workbook_path": job["_workbook_path"], "source_path": job["_source_path"],
                                    "output_root": job["_output_root"]})
        if request.method == "POST":
            provided = request.headers.get("X-HSD-Token", "")
            if not secrets.compare_digest(provided, token):
                return jsonify(error="会话已失效，请重新打开工具页面。"), 403

    @app.after_request
    def response_headers(response):
        if request.endpoint != "image" or response.status_code not in {200, 304}:
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

    @app.errorhandler(Conflict)
    def conflict(exc):
        return jsonify(error=exc.description), 409

    @app.errorhandler(KeyError)
    def missing(exc):
        return jsonify(error=str(exc.args[0])), 404

    @app.errorhandler(OSError)
    def file_error(exc):
        return jsonify(error=f"无法访问文件或文件夹：{exc}"), 400

    @app.get("/")
    def index():
        html = (static / "index.html").read_text("utf-8")
        access = {"lan": bool(lan), "remote": bool(lan and not lan.is_host(request.remote_addr))}
        return html.replace("__HSD_TOKEN__", json.dumps(token)).replace("__HSD_ACCESS__", json.dumps(access))

    @app.post("/api/lan/login")
    def lan_login():
        if not lan:
            raise KeyError("未启用局域网测试。")
        if request.headers.get("Origin") != request.host_url.rstrip("/"):
            return jsonify(error="请求来源不匹配。"), 403
        accepted = lan.login(request.remote_addr, request.get_json().get("code"))
        if accepted is None:
            return jsonify(error="尝试过多，请一分钟后重试。"), 429
        if not accepted:
            return jsonify(error="访问码不正确。"), 403
        session.clear()
        session.permanent = True
        session["lan_authenticated"] = True
        return jsonify(ok=True)

    @app.post("/api/lan/logout")
    def lan_logout():
        if not lan:
            raise KeyError("未启用局域网测试。")
        session.clear()
        return jsonify(ok=True)

    @app.get("/api/health")
    def health():
        return jsonify(app="hsd-number-tool", instance=app.config["HSD_INSTANCE"], runtime=runtime)

    @app.get("/api/config")
    def config():
        result = manager.config()
        if lan:
            result["access"] = {"lan": True, "remote": not lan.is_host(request.remote_addr),
                                "input_root": str(lan.input_root), "output_root": str(lan.output_root)}
            if lan.is_host(request.remote_addr):
                result["access"]["code"] = lan.code
            for key in ("last_workbook", "last_source"):
                if result.get(key) and not Path(result[key]).resolve().is_relative_to(lan.input_root):
                    result[key] = ""
            result["last_output"] = str(lan.output_root)
            with manager.lock:
                result["active_job_id"] = next(reversed(manager.jobs), None)
        return jsonify(result)

    @app.get("/api/ai/settings")
    def ai_settings():
        settings = manager.ai_config()
        if lan and not lan.is_host(request.remote_addr):
            settings = {key: settings[key] for key in ("enabled", "configured", "model", "mode")}
        return jsonify(settings)

    @app.post("/api/ai/settings")
    def save_ai_settings():
        with manager.lock:
            if any(j["status"] in {"importing", "matching", "ai_review", "exporting"} for j in manager.jobs.values()):
                raise ValueError("当前任务正在处理，请完成后再修改AI设置。")
            manager.ai_settings.save(request.get_json())
        return jsonify(manager.ai_config())

    @app.get("/api/ai/usage")
    def ai_usage():
        return jsonify(manager.ai_usage.snapshot())

    @app.post("/api/jobs/<identifier>/ai-review")
    def review_ai_job(identifier):
        manager.review_ai(identifier)
        return jsonify(id=identifier)

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
        payload = request.get_json()
        if lan:
            payload = lan.validate_paths(payload)
        return jsonify(id=manager.create(payload))

    @app.get("/api/jobs/<identifier>")
    def read_job(identifier):
        return jsonify(manager.snapshot(identifier))

    @app.post("/api/jobs/<identifier>/resolve")
    def resolve(identifier):
        payload = request.get_json()
        revert = payload.get("revert", False)
        if not isinstance(revert, bool):
            raise ValueError("恢复操作参数无效。")
        with manager.lock:
            check_revision(identifier, payload)
            return jsonify(manager.resolve(identifier, payload.get("row_id"), payload.get("file_id"), revert=revert))

    @app.post("/api/jobs/<identifier>/export")
    def export(identifier):
        with manager.lock:
            if lan:
                check_revision(identifier, request.get_json())
            manager.export(identifier, request.get_json().get("expected_revision"))
        return jsonify(id=identifier)

    @app.post("/api/jobs/<identifier>/undo")
    def undo(identifier):
        with manager.lock:
            check_revision(identifier, request.get_json())
            return jsonify(manager.undo(identifier))

    def check_revision(identifier, payload):
        expected = payload.get("expected_revision")
        if (lan or expected is not None) and (isinstance(expected, bool) or not isinstance(expected, int)
                or expected != manager._get(identifier).get("revision", 0)):
            raise Conflict("匹配结果已在其他页面更新，请刷新当前结果后重试。")

    @app.get("/api/jobs/<identifier>/image/<kind>/<item_id>")
    def image(identifier, kind, item_id):
        if kind not in {"row", "file"}:
            raise KeyError("不存在的图片类型。")
        variant = request.args.get("size", "full")
        if variant not in {"full", "thumb"}:
            raise ValueError("不支持的图片尺寸。")
        path, digest = manager.image_asset(identifier, kind, item_id, thumbnail=variant == "thumb")
        response = send_file(path, etag=digest, conditional=True, max_age=86400)
        response.headers["Cache-Control"] = "private, max-age=86400, immutable"
        return response

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
            if any(j["status"] in {"importing", "matching", "ai_review", "exporting"} for j in manager.jobs.values()):
                raise ValueError("任务正在处理，请完成后再退出工具。")
        callback = app.config.get("HSD_SHUTDOWN")
        if callback:
            threading.Timer(0.3, callback).start()
        return jsonify(ok=True)

    return app
