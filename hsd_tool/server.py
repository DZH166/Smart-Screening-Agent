"""Desktop HTTP interface, with an explicit authenticated LAN test mode."""
from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
import tempfile
import threading
import time
from datetime import timedelta
from pathlib import Path

from flask import Flask, Request, Response, current_app, g, jsonify, redirect, request, send_file, session
from werkzeug.exceptions import BadRequest, Conflict, RequestEntityTooLarge

from .service import JobManager
from .uploads import EmployeeUploads, DiskBudget, UploadWriteError, MAX_UPLOAD_BYTES, MAX_WORKBOOK_BYTES, MAX_SOURCE_BYTES, disk_full
from . import __version__
from . import admin_auth
from .cloud_tasks import CloudTaskStore, UploadClaims, upload_id
from . import material_demo
from .material_settings import MaterialSettings, MaterialSettingsConflict
from .material_service import MaterialManager
from .material_quality import quality_hook
from .access_codes import AccessCodeStore, AccessCodesConflict


class EmployeeUploadRequest(Request):
    """Stream authenticated file parts directly into their isolated upload batch."""
    @property
    def max_content_length(self):
        # Flask's None setter normally falls back to the app's JSON limit.
        if getattr(self, "_hsd_upload_unlimited", False):
            return None
        return Request.max_content_length.fget(self)

    @max_content_length.setter
    def max_content_length(self, value):
        Request.max_content_length.fset(self, value)

    def _get_file_stream(self, total_content_length, content_type, filename=None, content_length=None):
        if not getattr(self, "_hsd_upload_unlimited", False):
            return super()._get_file_stream(total_content_length, content_type, filename, content_length)
        uploads = current_app.config[getattr(self, "_hsd_upload_manager_key", "HSD_UPLOADS")]
        if not getattr(self, "_hsd_upload_directory", None):
            self._hsd_upload_directory = (uploads.begin(owner=getattr(g, "hsd_upload_claim", (None, None))[1])
                if getattr(self, "_hsd_upload_manager_key", "") == "HSD_MATERIAL_MANAGER" else uploads.begin())
            claim = getattr(g, "hsd_upload_claim", None)
            if claim is not None:
                current_app.config[getattr(self, "_hsd_upload_claims_key", "HSD_UPLOAD_CLAIMS")].bind_directory(*claim, self._hsd_upload_directory)
            self._hsd_upload_budget = DiskBudget(self._hsd_upload_directory)
            self._hsd_upload_streams = []
        stream = uploads.open_stream(self._hsd_upload_directory, self._hsd_upload_budget)
        claim = getattr(g, "hsd_upload_claim", None)
        if claim is not None:
            original_write = stream.write
            def checked_write(data):
                try:
                    current_app.config[getattr(self, "_hsd_upload_claims_key", "HSD_UPLOAD_CLAIMS")].ensure_active(*claim)
                except ValueError as exc:
                    raise UploadWriteError(str(exc)) from None
                return original_write(data)
            stream.write = checked_write
        self._hsd_upload_streams.append(stream)
        return stream

    def release_upload(self):
        if getattr(self, "_hsd_upload_released", False):
            return
        failure = None
        for stream in getattr(self, "_hsd_upload_streams", ()):
            try:
                stream.close()
            except OSError as exc:
                failure = failure or exc
        directory = getattr(self, "_hsd_upload_directory", None)
        if directory is not None and not getattr(self, "_hsd_upload_committed", False):
            try:
                current_app.config[getattr(self, "_hsd_upload_manager_key", "HSD_UPLOADS")].discard(directory)
            except (OSError, ValueError) as exc:
                failure = failure or exc
        if failure is not None:
            raise failure
        self._hsd_upload_released = True


def create_app(data_dir: str | Path, token: str | None = None, *, lan=None, settings_dir=None, cloud=None):
    if lan is not None and cloud is not None:
        raise ValueError("云服务器与局域网模式不能同时启用。")
    # CloudAccess intentionally never recognizes a host client: a loopback
    # reverse proxy is transport, not permission to operate this machine.
    lan = cloud if cloud is not None else lan
    static = Path(__file__).resolve().parent / "static"
    app = Flask(__name__, static_folder=str(static), static_url_path="/static")
    app.request_class = EmployeeUploadRequest
    app.config.update(MAX_CONTENT_LENGTH=64 * 1024, JSON_AS_ASCII=False,
                      SECRET_KEY=secrets.token_bytes(32))
    if lan:
        app.config.update(SESSION_COOKIE_HTTPONLY=True,
                          SESSION_COOKIE_SAMESITE="Strict", SESSION_COOKIE_NAME="hsd_lan_" + secrets.token_hex(6),
                          PERMANENT_SESSION_LIFETIME=timedelta(hours=8), SESSION_REFRESH_EACH_REQUEST=False)
    if cloud:
        app.config.update(SESSION_COOKIE_SECURE=True)
        app.wsgi_app = cloud.middleware(app.wsgi_app)
    admin_limiter = admin_auth.LoginLimiter()
    manager = JobManager(data_dir, settings_dir=settings_dir, **({"preserve_cache": True} if cloud else {}))
    uploads = EmployeeUploads(data_dir) if lan else None
    app.config["HSD_UPLOADS"] = uploads
    app.config["HSD_ACTIVE_UPLOADS"] = 0
    app.config["HSD_ACTIVE_DOWNLOADS"] = 0
    app.config["HSD_DOWNLOAD_LEASES"] = {}
    app.config["HSD_JOB_LEASES"] = {}
    app.config["HSD_CLOUD"] = bool(cloud)
    app.config["HSD_STOPPING"] = False
    token = token or secrets.token_urlsafe(32)
    app.config["HSD_TOKEN"] = token
    app.config["HSD_MANAGER"] = manager
    material_settings = MaterialSettings(manager.ai_settings.path.parent)
    app.config["HSD_MATERIAL_SETTINGS"] = material_settings
    material_manager = MaterialManager(data_dir, material_settings, cloud=bool(cloud),
                                       quality_hook=quality_hook, ai_settings=manager.ai_settings,
                                       ai_key_pool=manager.ai_key_pool)
    app.config["HSD_MATERIAL_MANAGER"] = material_manager
    material_streams = threading.BoundedSemaphore(2)
    material_claims = UploadClaims()
    material_manager.restore_upload_claims(material_claims)
    app.config["HSD_MATERIAL_UPLOAD_CLAIMS"] = material_claims
    access_codes = None
    if lan:
        try:
            access_codes = AccessCodeStore(manager.ai_settings.path.parent / "employee_access",
                                          min_length=lan.min_code_length,
                                          bootstrap_code=lan.code)
        except BaseException:
            material_manager.close()
            manager.close()
            raise
        lan.access_codes = access_codes
    app.config["HSD_ACCESS_CODES"] = access_codes
    try:
        claims = CloudTaskStore(manager, cloud.origin) if cloud else UploadClaims()
    except BaseException:
        material_manager.close()
        manager.close()
        raise
    app.config["HSD_UPLOAD_CLAIMS"] = claims
    if cloud:
        manager.task_persistence = claims
    app.config["HSD_INSTANCE"] = secrets.token_hex(16)
    app.config["HSD_SHUTDOWN"] = None
    runtime = {"frozen": bool(getattr(sys, "frozen", False)), "version": __version__}
    if runtime["frozen"]:
        from .service import sha256
        runtime["executable_sha256"] = sha256(sys.executable)
        manifest = Path(sys.executable).parent / "构建校验.json"
        runtime["build_manifest_sha256"] = sha256(manifest) if manifest.is_file() else None
    dialog_lock = threading.Lock()

    def employee_id():
        if not lan:
            return None
        if not session.get("employee_id"):
            session["employee_id"] = secrets.token_hex(16)
            session.permanent = True
        return session["employee_id"]

    def public_job(identifier):
        result = manager.snapshot(identifier)
        if lan:
            result.update(output_root="", output_target="处理完成后下载到你的电脑",
                          output_dir="结果已就绪，可下载" if result["status"] == "done" else None)
            roots = {str(manager.data_dir.resolve())}
            with manager.lock:
                job = manager._get(identifier)
                roots.update(str(Path(job[key]).resolve()) for key in ("_work_dir", "_upload_dir", "_output_root") if job.get(key))
            variants = set()
            for root in roots:
                variants.update((root, root.replace("\\", "/"), root.replace("\\", "\\\\")))
            def redact(value):
                if isinstance(value, str):
                    for root in sorted(variants, key=len, reverse=True):
                        value = value.replace(root, "任务文件")
                    return value
                if isinstance(value, list):
                    return [redact(item) for item in value]
                if isinstance(value, dict):
                    return {key: redact(item) for key, item in value.items()}
                return value
            result = redact(result)
        return result

    @app.before_request
    def guard_local():
        if lan and not lan.allows(request.remote_addr):
            return jsonify(error="仅允许指定局域网内的电脑访问。"), 403
        if not lan and request.remote_addr not in {"127.0.0.1", "::1", None}:
            return jsonify(error="仅支持本机访问。"), 403
        if cloud:
            if request.host_url.rstrip("/") != cloud.origin:
                return jsonify(error="不支持此访问地址。"), 403
        else:
            hosts = {"127.0.0.1", "localhost"} | ({lan.host} if lan else set())
            if request.host.split(":", 1)[0] not in hosts:
                return jsonify(error="不支持此访问地址。"), 403
            port = app.config.get("HSD_PORT")
            if lan and port and request.host not in {f"{host}:{port}" for host in hosts}:
                return jsonify(error="不支持此访问地址。"), 403
        remote = bool(lan and not lan.is_host(request.remote_addr))
        is_upload = request.endpoint in {"upload_job", "material_upload_job"}
        is_ribbon = request.endpoint == "ribbon_api"
        ribbon_upload = is_ribbon and request.method == "POST" and request.path == "/api/ribbon/assets"
        mutating = request.method == "POST" or (is_ribbon and request.method in {"PUT", "PATCH", "DELETE"})
        if mutating:
            origin = request.headers.get("Origin")
            if (origin and origin != request.host_url.rstrip("/")) or (remote and not origin):
                return jsonify(error="请求来源不匹配。"), 403
            empty_delete = is_ribbon and request.method == "DELETE" and not request.content_length
            if not is_upload and not ribbon_upload and not empty_delete and (not request.is_json or not isinstance(request.get_json(silent=True), dict)):
                return jsonify(error="请求必须使用 JSON 对象。"), 400
        if lan and request.endpoint == "lan_login":
            return None
        if request.endpoint == "healthz" and request.method == "GET":
            # Liveness for the service manager and monitoring. Deliberately
            # says nothing: no version, instance, options, or usage data.
            return None
        admin_area = (request.path in {"/admin", "/admin/material", "/admin/access-codes"}
                      or request.path.startswith(("/api/admin/", "/api/ribbon/admin/")))
        material_admin_static = (request.endpoint == "static" and
            Path(str((request.view_args or {}).get("filename", "")).replace("\\", "/")).name.split(":", 1)[0].rstrip(" .").casefold()
            in {"material-settings.html", "material-settings.js", "access-codes.html", "access-codes.js", "access-codes.css"})
        protected_static = (request.endpoint == "static" and
            Path(str((request.view_args or {}).get("filename", "")).replace("\\", "/")).name.split(":", 1)[0].rstrip(" .").casefold()
            in {"admin.html", "admin.js", "admin.css"})
        # The admin area authenticates itself: an operator may open it from
        # another computer on the LAN with the account/password, without the
        # employee access code. Employee-only paths still require that code.
        admin_entry = (admin_area or protected_static or material_admin_static
                       or request.endpoint in {"admin_login_page", "admin_login", "admin_logout"})
        if remote and not session.get("lan_authenticated") and not admin_entry:
            if request.endpoint in {"index", "material_demo_redirect", "material_demo_page"} and request.method == "GET":
                html = (static / "lan-login.html").read_text("utf-8")
                if cloud:
                    html = (html.replace("员工入口 · 输入主机提供的访问码。", "员工入口 · 输入管理员提供的访问码。")
                            .replace("DeepSeek 沿用主机配置", "DeepSeek 沿用服务器配置")
                            .replace("请连接公司局域网。没有访问码或无法连接时，请联系主机管理员。",
                                     "请使用管理员提供的 HTTPS 网址。文件处理结束后在服务器暂存 50 小时，请及时下载；没有访问码或无法连接时请联系管理员。")
                            .replace("无法连接主机，请确认主机工具仍在运行后重试。", "无法连接服务器，请检查网络后重试。"))
                if request.endpoint in {"material_demo_redirect", "material_demo_page"}:
                    html = (html.replace("HSD 图号助手", "素材提取（demo内测）")
                            .replace("进入后上传自己的表格和 AI 压缩包，处理完成即可下载结果。DeepSeek 沿用服务器配置，无需填写密钥。",
                                     "本次仅体验操作界面，不调用 AI，也不上传文件；下载内容是内置示例。")
                            .replace("进入后上传自己的表格和 AI 压缩包，处理完成即可下载结果。DeepSeek 沿用主机配置，无需填写密钥。",
                                     "本次仅体验操作界面，不调用 AI，也不上传文件；下载内容是内置示例。"))
                return html
            return jsonify(error="请先输入员工访问码。" if cloud else "请先输入局域网访问码。"), 401
        if cloud and request.endpoint in {"pick", "create_job", "open_output", "shutdown", "save_ai_settings"}:
            return jsonify(error="服务器只接受员工上传与结果下载，不提供主机文件或进程操作。"), 403
        if remote and (request.endpoint in {"pick", "open_output", "shutdown"}
                       or (request.endpoint == "save_ai_settings")):
            return jsonify(error="此操作只能在主机上完成。"), 403
        if admin_area or material_admin_static or (cloud and protected_static):
            if not admin_auth.authenticated(session):
                if request.path.startswith(("/api/admin/", "/api/ribbon/admin/")) or protected_static or material_admin_static:
                    return jsonify(error="请先登录管理员分区。"), 401
                return (static / "admin-login.html").read_text("utf-8")
        if lan:
            employee_id()
        if lan and (request.view_args or {}).get("identifier"):
            identifier = request.view_args["identifier"]
            if cloud:
                with manager.lock:
                    missing = identifier not in manager.jobs
                if missing:
                    claims.restore(identifier, employee_id(), app.config["HSD_RETENTION"])
            with manager.lock:
                if identifier in getattr(manager, "_expiring_tasks", set()):
                    raise KeyError("任务已过期，请重新上传。")
                job = manager._get(identifier)
                if job.get("_owner_id") != employee_id():
                    raise KeyError("找不到此任务，请在上传时使用的浏览器中打开。")
                if cloud:
                    identifier = request.view_args["identifier"]
                    leases = app.config["HSD_JOB_LEASES"]
                    leases[identifier] = leases.get(identifier, 0) + 1
                    g.hsd_job_lease = identifier
                    g.hsd_lease_state = {"released": False, "bound": False}
                if job.get("_upload_managed"):
                    uploads.validate_job(job)
                else:
                    lan.validate_paths({"workbook_path": job["_workbook_path"], "source_path": job["_source_path"],
                                        "output_root": job["_output_root"]})
        if mutating and request.endpoint != "admin_login":
            provided = request.headers.get("X-HSD-Token", "")
            if not secrets.compare_digest(provided.encode(), token.encode()):
                return jsonify(error="会话已失效，请重新打开工具页面。"), 403
            with manager.lock:
                if app.config["HSD_STOPPING"] and request.endpoint != "shutdown":
                    raise Conflict("主机正在退出，请稍后重新打开员工入口。")
        if ribbon_upload:
            # Ribbon receives individual images, separate from the unlimited
            # numbering ZIP uploader. FastAPI bounds decoding to 40 MP/20 MiB.
            request.max_content_length = 21 * 1024 * 1024
            if request.content_length is None or request.content_length > request.max_content_length:
                return jsonify(error="丝带单张素材需小于20 MB，请缩小图片后重试。"), 413
        if is_upload:
            active_claims = material_claims if request.endpoint == "material_upload_job" else claims
            identifier = upload_id(request.headers.get("X-HSD-Upload-ID") or secrets.token_hex(16))
            state = active_claims.reserve(identifier, employee_id())
            if state["state"] == "completed":
                return jsonify(id=state["job_id"], reused=True)
            if state["state"] != "reserved":
                raise Conflict("本次上传仍在处理或已停止，请查询上传状态。")
            g.hsd_upload_claim = (identifier, employee_id())
            if request.endpoint == "material_upload_job":
                request._hsd_upload_manager_key = "HSD_MATERIAL_MANAGER"
                request._hsd_upload_claims_key = "HSD_MATERIAL_UPLOAD_CLAIMS"
            request._hsd_upload_unlimited = True
            request.max_content_length = None
            request.max_form_memory_size = 512 * 1024
            request.max_form_parts = 100 if request.endpoint == "material_upload_job" else 8

    @app.teardown_request
    def release_upload_streams(exc):
        state = getattr(g, "hsd_lease_state", None)
        if state is not None and not state["bound"]:
            release_job_lease(g.hsd_job_lease, state)
        try:
            request.release_upload()
        except (OSError, ValueError):
            # Do not mask an interrupted/malformed request or follow a replaced
            # link during cleanup. No path, file contents or credentials logged.
            app.logger.warning("上传临时文件未能清理，请管理员检查磁盘空间与权限。")
        claim = getattr(g, "hsd_upload_claim", None)
        if claim is not None:
            (material_claims if request.endpoint == "material_upload_job" else claims).finish(*claim)

    def release_job_lease(identifier, state):
        with manager.lock:
            if state["released"]:
                return
            state["released"] = True
            leases = app.config["HSD_JOB_LEASES"]
            remaining = leases.get(identifier, 1) - 1
            if remaining:
                leases[identifier] = remaining
            else:
                leases.pop(identifier, None)

    @app.after_request
    def response_headers(response):
        if cloud and getattr(g, "hsd_recovery_token", None):
            response.set_cookie(claims.cookie_name, g.hsd_recovery_token, max_age=30 * 86400,
                                secure=True, httponly=True, samesite="Strict", path="/")
        state = getattr(g, "hsd_lease_state", None)
        if state is not None:
            identifier = g.hsd_job_lease
            # send_file's passthrough iterator bypasses Response.close. Keep
            # streaming, but wrap it so image/HEAD/304 leases are released too.
            response.direct_passthrough = False
            response.call_on_close(lambda: release_job_lease(identifier, state))
            state["bound"] = True
        if request.endpoint not in {"image", "material_image"} or response.status_code not in {200, 304}:
            response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        download_frame = request.endpoint in {"download", "material_download"} and request.args.get("frame") == "1"
        response.headers["X-Frame-Options"] = "SAMEORIGIN" if download_frame else "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        # The inline token/bootstrap is the only inline script; UI does not load external resources.
        response.headers["Content-Security-Policy"] = "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'"
        if request.endpoint == "index":
            # Local selected-file thumbnails need object URLs. Scope this to
            # the employee document; admin pages and API frames stay closed.
            response.headers["Content-Security-Policy"] = response.headers["Content-Security-Policy"].replace(
                "img-src 'self' data:;", "img-src 'self' data: blob:;")
        if getattr(g, "hsd_material_demo", False):
            # The prototype operates entirely in this browser. Its local file
            # preview needs blob images, but it has no reason to call any API.
            response.headers["Content-Security-Policy"] = material_demo.CSP
        if download_frame:
            response.headers["Content-Security-Policy"] = response.headers["Content-Security-Policy"].replace("frame-ancestors 'none'", "frame-ancestors 'self'")
        return response

    @app.before_request
    def material_task_lease():
        identifier = (request.view_args or {}).get("material_id")
        if identifier:
            release = material_manager.acquire(identifier, employee_id())
            g.hsd_material_release = release
            g.hsd_material_bound = False

    @app.after_request
    def bind_material_task_lease(response):
        release = getattr(g, "hsd_material_release", None)
        if release is not None:
            response.direct_passthrough = False
            response.call_on_close(release)
            g.hsd_material_bound = True
        return response

    @app.teardown_request
    def release_material_task_lease(exc):
        release = getattr(g, "hsd_material_release", None)
        if release is not None and not getattr(g, "hsd_material_bound", False):
            release()

    @app.errorhandler(ValueError)
    def invalid(exc):
        return jsonify(error=str(exc)), 400

    @app.errorhandler(UploadWriteError)
    def upload_write_error(exc):
        return jsonify(error=str(exc)), 400

    @app.errorhandler(Conflict)
    def conflict(exc):
        return jsonify(error=exc.description), 409

    @app.errorhandler(RequestEntityTooLarge)
    def too_large(exc):
        if request.endpoint == "material_upload_job":
            message = "上传表单字段过多或过长，请一次只选择 1 到 100 张图片。"
        else:
            message = "上传表单字段过多或过长，请只选择表格、ZIP和本批起始号。" if request.endpoint == "upload_job" else "请求内容过大，请缩短输入后重试。"
        return jsonify(error=message), 413

    @app.errorhandler(BadRequest)
    def bad_request(exc):
        return jsonify(error="文件上传中断或请求格式不完整，请重新上传。"), 400

    @app.errorhandler(KeyError)
    def missing(exc):
        return jsonify(error=str(exc.args[0])), 404

    @app.errorhandler(OSError)
    def file_error(exc):
        if disk_full(exc):
            return jsonify(error="主机磁盘空间不足，请联系管理员清理后再上传。"), 400
        if lan:
            return jsonify(error="任务文件无法读取或写入，请重新上传；若仍失败，请联系主机管理员检查磁盘空间与权限。"), 400
        return jsonify(error=f"无法访问文件或文件夹：{exc}"), 400

    @app.get("/")
    def index():
        html = (static / "index.html").read_text("utf-8")
        access = {"lan": bool(lan), "remote": bool(lan and not lan.is_host(request.remote_addr))}
        return html.replace("__HSD_TOKEN__", json.dumps(token)).replace("__HSD_ACCESS__", json.dumps(access))

    @app.get("/material-demo")
    def material_demo_redirect():
        return redirect("/material-demo/", code=308)

    @app.get("/material-demo/")
    @app.get("/material-demo/index.html")
    def material_demo_page():
        g.hsd_material_demo = True
        return material_demo.asset_response("index.html")

    @app.get("/material-demo/<path:filename>")
    def material_demo_asset(filename):
        g.hsd_material_demo = True
        return material_demo.asset_response(filename)

    @app.get("/admin")
    def admin_page():
        return (static / "admin.html").read_text("utf-8").replace("__HSD_TOKEN__", json.dumps(token))

    @app.get("/admin/material")
    def material_settings_page():
        return (static / "material-settings.html").read_text("utf-8").replace("__HSD_TOKEN__", json.dumps(token))

    def material_settings_snapshot():
        existing = manager.ai_config()
        return {"settings": material_settings.snapshot(),
                "deepseek": {"enabled": existing["enabled"], "configured": existing["configured"]},
                "validation_ready": False,
                "processing_available": material_manager.config(employee_id())["available"]}

    @app.get("/api/admin/material-settings")
    def material_settings_get():
        return jsonify(material_settings_snapshot())

    @app.get("/api/admin/material-key")
    def material_key_get():
        # Admin session is enforced before routing; require the page token too.
        # No credential belongs in a query string, log, or regular snapshot.
        provided = request.headers.get("X-HSD-Token", "")
        if not secrets.compare_digest(provided.encode(), token.encode()):
            return jsonify(error="会话已失效，请重新打开管理员页面。"), 403
        origin = request.headers.get("Origin")
        if origin and origin != request.host_url.rstrip("/"):
            return jsonify(error="请求来源不匹配。"), 403
        values = request.args.getlist("revision")
        if (set(request.args) != {"revision"} or len(values) != 1
                or not values[0].isascii() or not values[0].isdigit() or len(values[0]) > 16):
            raise ValueError("配置版本不正确，请刷新后重试。")
        try:
            return jsonify(material_settings.admin_key(int(values[0])))
        except MaterialSettingsConflict:
            raise Conflict("配置已在其他页面更新，请刷新后重新查看。") from None

    @app.post("/api/admin/material-settings")
    def material_settings_save():
        if request.headers.get("Origin") != request.host_url.rstrip("/"):
            raise ValueError("请求来源不匹配。")
        payload = request.get_json()
        action = payload.get("action")
        allowed = {"set_config": {"api_key", "model_id"}, "remove_key": set(), "set_enabled": {"enabled"}}
        if (payload.get("provider") != "volcengine_ark" or not isinstance(action, str)
                or action not in allowed
                or set(payload) != allowed[action] | {"action", "provider", "expected_revision"}):
            raise ValueError("素材设置格式不正确。")
        update = {name: payload[name] for name in allowed[action]}
        update["expected_revision"] = payload["expected_revision"]
        if action == "remove_key":
            update["clear_key"] = True
        try:
            with material_manager.lock:
                if material_manager.has_active_operations():
                    raise ValueError("素材正在处理，请完成后再修改设置。")
                material_settings.save(update)
        except MaterialSettingsConflict:
            raise Conflict("素材设置已在其他页面更新，请刷新后再保存。") from None
        return jsonify(material_settings_snapshot())

    @app.get("/admin/login")
    def admin_login_page():
        return (static / "admin-login.html").read_text("utf-8")

    @app.post("/admin/login")
    def admin_login():
        """Single operator account; failures are throttled, nothing is logged."""
        address = request.remote_addr or ""
        if admin_limiter.blocked(address):
            return jsonify(error="尝试次数过多，请一分钟后重试。"), 429
        origin = request.headers.get("Origin")
        if origin and origin != request.host_url.rstrip("/"):
            return jsonify(error="请求来源不匹配。"), 403
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify(error="登录请求格式不正确。"), 400
        credentials = cloud.admin_credentials if cloud else None
        accepted = (credentials.verify(payload.get("username"), payload.get("password"))
                    if credentials is not None else
                    (not cloud and admin_auth.verify_credentials(payload.get("username"), payload.get("password"))))
        if not accepted:
            admin_limiter.fail(address)
            return jsonify(error="账号或密码不正确。"), 401
        admin_limiter.reset(address)
        admin_auth.grant_session(session)
        return jsonify(ok=True)

    @app.post("/admin/logout")
    def admin_logout():
        admin_auth.revoke_session(session)
        return jsonify(ok=True)

    @app.get("/api/admin/overview")
    def admin_overview():
        return jsonify(settings=manager.ai_config(), pool=manager.ai_key_pool.snapshot(),
                       usage=manager.ai_usage.snapshot(), debug=manager.ai_debug.snapshot())

    @app.get("/api/admin/keys")
    def admin_key_settings():
        return jsonify(settings=manager.ai_config(), pool=manager.ai_key_pool.snapshot())

    @app.get("/admin/access-codes")
    def admin_access_codes_page():
        return (static / "access-codes.html").read_text("utf-8").replace("__HSD_TOKEN__", json.dumps(token))

    def access_codes_snapshot():
        if access_codes is None:
            return {"supported": False, "revision": 0, "min_length": 1, "max_length": 64, "codes": []}
        return {"supported": True, **access_codes.snapshot()}

    @app.get("/api/admin/access-codes")
    def admin_access_codes_get():
        if request.args:
            raise ValueError("访问码设置不接受查询参数。")
        return jsonify(access_codes_snapshot())

    @app.post("/api/admin/access-codes")
    def admin_access_codes_save():
        if request.headers.get("Origin") != request.host_url.rstrip("/"):
            return jsonify(error="请求来源不匹配。"), 403
        if access_codes is None:
            raise ValueError("当前是本机模式，无需访问码；启用员工入口后再设置。")
        try:
            access_codes.save(request.get_json())
        except AccessCodesConflict:
            raise Conflict("访问码设置已在其他页面更新，请刷新后再保存。") from None
        return jsonify(access_codes_snapshot())

    @app.post("/api/admin/settings")
    def admin_processing_settings():
        # This narrow administrator route is safe for an authenticated LAN or
        # cloud operator. The legacy host-only API remains unchanged and this
        # endpoint cannot replace/clear provider credentials or grant a gate.
        if request.headers.get("Origin") != request.host_url.rstrip("/"):
            return jsonify(error="请求来源不匹配。"), 403
        payload = request.get_json()
        if set(payload) - {"enabled", "expected_revision"} or type(payload.get("enabled")) is not bool:
            raise ValueError("管理员设置仅接受是否启用AI的布尔值。")
        revision = payload.get("expected_revision")
        if type(revision) is not int or revision < 0:
            raise ValueError("设置版本无效，请重新读取后再保存。")
        with manager.lock, material_manager.lock:
            if manager.has_active_operations() or material_manager.has_active_operations():
                raise ValueError("当前任务正在处理，请完成后再修改AI设置。")
            if revision != manager.ai_settings.snapshot()["key_revision"]:
                raise Conflict("AI设置已在其他页面更新，请重新读取后再保存。")
            manager.ai_settings.save({"enabled": payload["enabled"]})
        return jsonify(settings=manager.ai_config(), pool=manager.ai_key_pool.snapshot())

    @app.get("/api/admin/debug")
    def admin_debug():
        if set(request.args) - {"after", "limit"}:
            raise ValueError("调试查询参数无效。")
        try:
            if any(len(request.args.getlist(key)) != 1 for key in request.args):
                raise ValueError()
            after, limit = int(request.args.get("after", "0")), int(request.args.get("limit", "100"))
        except (TypeError, ValueError):
            raise ValueError("调试记录游标或条数无效。") from None
        return jsonify(manager.ai_debug.snapshot(after, limit))

    @app.get("/api/admin/ledger")
    def admin_ledger():
        """Full key values for the host operator's own reuse, explicitly requested.

        This is the one explicitly authorized place credentials are returned to
        a page. It requires the independent administrator session, including on
        LAN/HTTPS cloud entries. Responses are no-store and never logged here.
        """
        runtime = manager.ai_settings.runtime()
        return jsonify(keys=[{"id": row["id"], "label": row["label"],
                              "enabled": row["enabled"],
                              "source": row.get("source", "saved"),
                              "api_key": row["api_key"]}
                             for row in runtime.get("keys", []) if row.get("api_key")])

    @app.post("/api/admin/keys")
    def admin_keys():
        with manager.lock, material_manager.lock:
            if manager.has_active_operations() or material_manager.has_active_operations():
                raise ValueError("当前任务正在处理，请完成后再修改 Key。")
            payload = request.get_json()
            if type(payload.get("expected_revision")) is not int:
                raise ValueError("请先读取当前 Key 配置后再保存。")
            if payload["expected_revision"] != manager.ai_settings.snapshot()["key_revision"]:
                raise Conflict("Key 配置已在其他页面更新，请重新读取后再保存。")
            manager.ai_settings.save_pool(payload)
        return jsonify(settings=manager.ai_config(), pool=manager.ai_key_pool.snapshot())

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
        if cloud:
            recovery = request.cookies.get(claims.cookie_name)
            try:
                owner = claims.owner(recovery)
            except ValueError:
                recovery = claims.new_token()
                owner = claims.owner(recovery)
            g.hsd_recovery_token = recovery
            session["employee_id"] = owner
            retention = app.config.get("HSD_RETENTION")
            if retention is not None and hasattr(retention, "_records"):
                claims.restore_owner(owner, retention)
        else:
            session["employee_id"] = secrets.token_hex(16)
        return jsonify(ok=True)

    @app.post("/api/lan/logout")
    def lan_logout():
        if not lan:
            raise KeyError("未启用局域网测试。")
        session.clear()
        return jsonify(ok=True)

    @app.get("/healthz")
    def healthz():
        """Unauthenticated liveness probe; returns no deployment details."""
        response = Response("ok", mimetype="text/plain")
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/api/health")
    def health():
        return jsonify(app="hsd-number-tool", instance=app.config["HSD_INSTANCE"], runtime=runtime)

    @app.get("/api/config")
    def config():
        result = manager.config()
        if lan:
            result["access"] = {"lan": True, "remote": not lan.is_host(request.remote_addr),
                                "upload": True, "upload_limits": {"workbook_bytes": MAX_WORKBOOK_BYTES,
                                "source_bytes": MAX_SOURCE_BYTES, "total_bytes": MAX_UPLOAD_BYTES}}
            if lan.is_host(request.remote_addr):
                result["access"]["code"] = lan.code
            for key in ("last_workbook", "last_source", "last_output"):
                result[key] = ""
            result["last_start"] = 1
            with manager.lock:
                own_jobs = [job for job in manager.jobs.values() if job.get("_owner_id") == employee_id()]
                result["active_job_id"] = own_jobs[-1]["id"] if own_jobs else None
                if own_jobs:
                    result["last_start"] = own_jobs[-1]["start_number"]
        return jsonify(result)

    @app.get("/api/ai/settings")
    def ai_settings():
        settings = manager.ai_config()
        if lan and not lan.is_host(request.remote_addr):
            settings = {key: settings[key] for key in ("enabled", "configured", "model", "mode")}
        return jsonify(settings)

    @app.post("/api/ai/settings")
    def save_ai_settings():
        with manager.lock, material_manager.lock:
            if manager.has_active_operations() or material_manager.has_active_operations():
                raise ValueError("当前任务正在处理，请完成后再修改AI设置。")
            manager.ai_settings.save(request.get_json())
        return jsonify(manager.ai_config())

    @app.get("/api/ai/usage")
    def ai_usage():
        if lan and not lan.is_host(request.remote_addr):
            return jsonify(error="累计费用仅在主机查看；本批用量可在结果摘要查看。"), 403
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
        if {"input_digests", "_input_digests"}.intersection(payload):
            raise ValueError("文件校验信息只能由主机接收上传时生成。")
        if lan:
            if not lan.is_host(request.remote_addr):
                return jsonify(error="请直接上传本机的表格和 AI 压缩包。"), 403
            payload = lan.validate_paths(payload)
        if lan:
            return jsonify(id=manager.create(payload, owner_id=employee_id()))
        return jsonify(id=manager.create(payload))

    @app.get("/api/material/config")
    def material_config():
        return jsonify(material_manager.config(employee_id()))

    @app.post("/api/material/jobs")
    def material_upload_job():
        if request.mimetype != "multipart/form-data":
            raise ValueError("请使用图片上传表单。")
        committed = False
        with manager.lock:
            if app.config["HSD_STOPPING"]:
                raise Conflict("服务正在退出，请稍后重新打开员工入口。")
            app.config["HSD_ACTIVE_UPLOADS"] += 1
        try:
            def commit(job):
                material_claims.ensure_active(*g.hsd_upload_claim)
                material_claims.commit(*g.hsd_upload_claim, job["id"])
            identifier = material_manager.receive(
                request.files, request.form, owner=employee_id(),
                directory=getattr(request, "_hsd_upload_directory", None), before_submit=commit,
                upload_request_id=g.hsd_upload_claim[0],
                ensure_active=lambda: material_claims.ensure_active(*g.hsd_upload_claim))
            committed = True
            request._hsd_upload_committed = True
            return jsonify(id=identifier)
        finally:
            with manager.lock:
                app.config["HSD_ACTIVE_UPLOADS"] -= 1
            # receive owns cleanup after parsing; malformed multipart is cleaned
            # by the request teardown using this endpoint's private namespace.
            if committed:
                request.release_upload()

    @app.get("/api/material/upload-status/<request_id>")
    def material_upload_status(request_id):
        return jsonify(material_claims.lookup(request_id, employee_id()))

    @app.post("/api/material/upload-status/<request_id>/cancel")
    def material_cancel_upload(request_id):
        state = material_claims.cancel(request_id, employee_id())
        if state["state"] == "completed":
            identifier = state["job_id"]
            with material_manager.lock:
                result = material_manager.snapshot(identifier, employee_id())
                material_manager.cancel(identifier, employee_id(), result["revision"])
        return jsonify(state)

    @app.get("/api/material/jobs/<material_id>")
    def material_read_job(material_id):
        return jsonify(material_manager.snapshot(material_id, employee_id()))

    @app.get("/api/material/jobs/<material_id>/events")
    def material_events(material_id):
        # Reserve two of the four HTTP threads for ordinary operations. A
        # bounded connection renews authentication, and polling is a fallback.
        if not material_streams.acquire(blocking=False):
            return jsonify(error="实时通道繁忙，已切换普通进度刷新。"), 429
        owner = employee_id()
        try:
            initial = material_manager.snapshot(material_id, owner)
        except BaseException:
            material_streams.release()
            raise
        released = False
        def release_slot():
            nonlocal released
            if not released:
                released = True
                material_streams.release()
        def events():
            deadline, last_sequence, last_heartbeat = time.monotonic() + 12, None, 0
            state = initial
            try:
                yield "retry: 1500\n\n"
                while True:
                    sequence = state.get("update_seq", state["revision"])
                    if sequence != last_sequence:
                        yield "event: snapshot\ndata: " + json.dumps(state, ensure_ascii=False, allow_nan=False) + "\n\n"
                        last_sequence = sequence
                    if state["status"] not in {"queued", "processing", "cancelling"}:
                        yield "event: end\ndata: {}\n\n"
                        return
                    now = time.monotonic()
                    if app.config["HSD_STOPPING"]:
                        return
                    if now >= deadline:
                        yield "event: renew\ndata: {}\n\n"
                        return
                    if now - last_heartbeat >= 3:
                        yield ": waiting\n\n"
                        last_heartbeat = now
                    time.sleep(.5)
                    state = material_manager.snapshot(material_id, owner)
            except (KeyError, ValueError, Conflict):
                yield 'event: unavailable\ndata: {"error":"本批状态已变化，请刷新页面。"}\n\n'
            finally:
                release_slot()
        response = Response(events(), mimetype="text/event-stream", headers={
            "Cache-Control": "private, no-store", "X-Accel-Buffering": "no"})
        response.call_on_close(release_slot)
        return response

    @app.post("/api/material/jobs/<material_id>/cancel")
    def material_cancel_job(material_id):
        payload = request.get_json()
        if set(payload) != {"expected_revision"}:
            raise ValueError("停止处理参数无效。")
        return jsonify(material_manager.cancel(material_id, employee_id(), payload.get("expected_revision")))

    @app.post("/api/material/jobs/<material_id>/resolve")
    def material_resolve_job(material_id):
        return jsonify(material_manager.resolve(material_id, employee_id(), request.get_json()))

    @app.post("/api/material/jobs/<material_id>/resolve-batch")
    def material_resolve_batch(material_id):
        return jsonify(material_manager.resolve_batch(material_id, employee_id(), request.get_json()))

    @app.post("/api/material/jobs/<material_id>/undo-batch")
    def material_undo_batch(material_id):
        return jsonify(material_manager.undo_batch(material_id, employee_id(), request.get_json()))

    @app.post("/api/material/jobs/<material_id>/redo")
    def material_redo_job(material_id):
        return jsonify(material_manager.redo(material_id, employee_id(), request.get_json()))

    @app.post("/api/material/jobs/<material_id>/refine")
    def material_refine_job(material_id):
        return jsonify(material_manager.refine(material_id, employee_id(), request.get_json()))

    @app.get("/api/material/jobs/<material_id>/source/<item_id>")
    @app.get("/api/material/jobs/<material_id>/item/<item_id>")
    @app.get("/api/material/jobs/<material_id>/item/<item_id>/before")
    def material_image(material_id, item_id):
        kind = "source" if "/source/" in request.path else "before" if request.path.endswith("/before") else "item"
        variant = request.args.get("variant", "full")
        if (variant not in {"full", "thumb"} or set(request.args) - {"variant", "v"}
                or any(len(values) != 1 for _, values in request.args.lists())):
            raise ValueError("图片预览参数无效。")
        path, digest = material_manager.asset(material_id, employee_id(), kind, item_id,
            thumbnail=variant == "thumb", content_version=request.args.get("v"))
        response = send_file(path, etag=digest, conditional=True, max_age=0)
        response.headers["Cache-Control"] = "private, no-cache, must-revalidate"
        return response

    @app.get("/api/material/jobs/<material_id>/download")
    @app.get("/api/material/jobs/<material_id>/download/<item_id>")
    def material_download(material_id, item_id=None):
        if item_id is None:
            path, digest = material_manager.download(material_id, employee_id())
            filename = "素材提取结果.zip"
        else:
            path, digest = material_manager.asset(material_id, employee_id(), "item", item_id, download=True)
            filename = "素材.png"
        response = send_file(path, as_attachment=True, download_name=filename, etag=digest, conditional=True)
        response.headers["Cache-Control"] = "private, no-store"
        return response

    @app.post("/api/jobs/upload")
    def upload_job():
        if not lan:
            raise KeyError("员工上传需要开启局域网模式。")
        if request.mimetype != "multipart/form-data":
            raise ValueError("请使用文件上传表单提交表格和压缩包。")
        directory = None
        committed = False
        with manager.lock:
            if app.config["HSD_STOPPING"]:
                raise Conflict("主机正在退出，请稍后重新打开员工入口。")
            app.config["HSD_ACTIVE_UPLOADS"] += 1
        try:
            directory, payload, names = uploads.receive(request.files, request.form, directory=getattr(request, "_hsd_upload_directory", None))
            input_digests = names.pop("_input_digests")
            with manager.lock:
                def register_before_submit(job):
                    job.update(_upload_managed=True, _upload_dir=str(directory),
                               _upload_request_id=g.hsd_upload_claim[0])
                    if cloud:
                        retention = app.config.get("HSD_RETENTION")
                        if retention is None:
                            raise ValueError("服务器暂存管理尚未就绪，请稍后重试。")
                        retention.register(job["id"])
                        claims.save_job(job)
                    # Both LAN and cloud must commit the reservation before
                    # CPU/AI submission. A concurrent stop can then either
                    # prevent submission or cancel an accepted task by ID.
                    claims.commit(*g.hsd_upload_claim, job["id"])
                claims.ensure_active(*g.hsd_upload_claim)
                identifier = manager.create(payload, owner_id=employee_id(), downloadable=True,
                    display_names=names, input_digests=input_digests, before_submit=register_before_submit)
                job = manager._get(identifier)
                job.update(_upload_managed=True, _upload_dir=str(directory))
                committed = True
                request._hsd_upload_committed = True
            return jsonify(id=identifier)
        finally:
            with manager.lock:
                app.config["HSD_ACTIVE_UPLOADS"] -= 1
            if directory is not None and not committed:
                uploads.discard(directory)
            request.release_upload()

    @app.get("/api/jobs/upload-status/<request_id>")
    def upload_status(request_id):
        if not lan:
            raise KeyError("未启用员工上传。")
        return jsonify(claims.lookup(request_id, employee_id()))

    @app.post("/api/jobs/upload-status/<request_id>/cancel")
    def cancel_upload(request_id):
        if not lan:
            raise KeyError("未启用员工上传。")
        state = claims.cancel(request_id, employee_id())
        if state["state"] == "completed":
            identifier = state["job_id"]
            with manager.lock:
                if cloud and identifier not in manager.jobs:
                    claims.restore(identifier, employee_id(), app.config["HSD_RETENTION"])
                job = manager._get(identifier)
                if job.get("_owner_id") != employee_id():
                    raise KeyError("找不到此任务。")
            if job["status"] in {"queued", "importing", "matching", "ai_review", "exporting", "cancelling"}:
                manager.cancel(identifier)
        return jsonify(state)

    @app.get("/api/jobs/<identifier>")
    def read_job(identifier):
        return jsonify(public_job(identifier))

    @app.post("/api/jobs/<identifier>/resolve")
    def resolve(identifier):
        payload = request.get_json()
        revert = payload.get("revert", False)
        if not isinstance(revert, bool):
            raise ValueError("恢复操作参数无效。")
        with manager.job_operation(identifier):
            check_revision(identifier, payload)
            manager.resolve(identifier, payload.get("row_id"), payload.get("file_id"), revert=revert)
            return jsonify(public_job(identifier))

    @app.post("/api/jobs/<identifier>/resolve-batch")
    def resolve_batch(identifier):
        payload = request.get_json()
        if set(payload) != {"expected_revision", "items"}:
            raise ValueError("批量确认参数无效。")
        if type(payload["expected_revision"]) is not int or payload["expected_revision"] < 0:
            raise Conflict("请刷新当前结果后再批量确认。")
        with manager.job_operation(identifier):
            check_revision(identifier, payload)
            manager.resolve_batch(identifier, payload["items"])
            return jsonify(public_job(identifier))

    @app.post("/api/jobs/<identifier>/export")
    def export(identifier):
        with manager.job_operation(identifier):
            if lan:
                check_revision(identifier, request.get_json())
            manager.export(identifier, request.get_json().get("expected_revision"))
        return jsonify(id=identifier)

    @app.post("/api/jobs/<identifier>/undo")
    def undo(identifier):
        with manager.job_operation(identifier):
            check_revision(identifier, request.get_json())
            result = manager.undo(identifier)
            public = public_job(identifier)
            if result.get("last_undone_row_id"):
                public["last_undone_row_id"] = result["last_undone_row_id"]
                public["last_undone_count"] = result.get("last_undone_count", 1)
            return jsonify(public)

    @app.post("/api/jobs/<identifier>/cancel")
    def cancel_job(identifier):
        payload = request.get_json()
        with manager.job_operation(identifier):
            check_revision(identifier, payload)
            manager.cancel(identifier, payload.get("expected_revision"))
        return jsonify(public_job(identifier))

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
        response.headers["Cache-Control"] = "private, no-cache, must-revalidate" if lan else "private, max-age=86400, immutable"
        return response

    @app.get("/api/jobs/<identifier>/download")
    def download(identifier):
        if not lan:
            raise KeyError("此任务不提供浏览器下载。")
        path, digest = manager.download_asset(identifier)
        with manager.lock:
            if app.config["HSD_STOPPING"]:
                raise Conflict("主机正在退出，请稍后再下载。")
            response = send_file(path, as_attachment=True, download_name="HSD编号结果.zip", etag=digest, conditional=True)
            app.config["HSD_ACTIVE_DOWNLOADS"] += 1
            leases = app.config["HSD_DOWNLOAD_LEASES"]
            leases[identifier] = leases.get(identifier, 0) + 1
        response.direct_passthrough = False
        closed = False
        @response.call_on_close
        def download_finished():
            nonlocal closed
            with manager.lock:
                if closed:
                    return
                closed = True
                app.config["HSD_ACTIVE_DOWNLOADS"] -= 1
                remaining = app.config["HSD_DOWNLOAD_LEASES"].get(identifier, 1) - 1
                if remaining:
                    app.config["HSD_DOWNLOAD_LEASES"][identifier] = remaining
                else:
                    app.config["HSD_DOWNLOAD_LEASES"].pop(identifier, None)
        response.headers["Cache-Control"] = "private, no-store"
        return response

    @app.get("/api/jobs/<identifier>/download-status")
    def download_status(identifier):
        if not lan:
            raise KeyError("此任务不提供浏览器下载。")
        manager.download_asset(identifier)
        return jsonify(ready=True, download_url=f"/api/jobs/{identifier}/download")

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
            if app.config["HSD_ACTIVE_UPLOADS"] or app.config["HSD_ACTIVE_DOWNLOADS"]:
                raise ValueError("员工正在上传或下载文件，请传输完成后再退出。")
            if manager.has_active_operations() or material_manager.has_active_operations():
                raise ValueError("任务正在处理，请完成后再退出工具。")
            app.config["HSD_STOPPING"] = True
        callback = app.config.get("HSD_SHUTDOWN")
        if callback:
            threading.Timer(0.3, callback).start()
        return jsonify(ok=True)

    from .ribbon_gateway import register_ribbon
    register_ribbon(app, manager, material_settings, employee_id)
    return app
