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

from flask import Flask, Request, current_app, jsonify, request, send_file, session
from werkzeug.exceptions import BadRequest, Conflict, RequestEntityTooLarge

from .service import JobManager
from .uploads import EmployeeUploads, DiskBudget, UploadWriteError, MAX_UPLOAD_BYTES, MAX_WORKBOOK_BYTES, MAX_SOURCE_BYTES, disk_full
from . import __version__
from . import admin_auth


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
        uploads = current_app.config["HSD_UPLOADS"]
        if not getattr(self, "_hsd_upload_directory", None):
            self._hsd_upload_directory = uploads.begin()
            self._hsd_upload_budget = DiskBudget(self._hsd_upload_directory)
            self._hsd_upload_streams = []
        stream = uploads.open_stream(self._hsd_upload_directory, self._hsd_upload_budget)
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
                current_app.config["HSD_UPLOADS"].discard(directory)
            except (OSError, ValueError) as exc:
                failure = failure or exc
        if failure is not None:
            raise failure
        self._hsd_upload_released = True


def create_app(data_dir: str | Path, token: str | None = None, *, lan=None, settings_dir=None):
    static = Path(__file__).resolve().parent / "static"
    app = Flask(__name__, static_folder=str(static), static_url_path="/static")
    app.request_class = EmployeeUploadRequest
    app.config.update(MAX_CONTENT_LENGTH=64 * 1024, JSON_AS_ASCII=False,
                      SECRET_KEY=secrets.token_bytes(32))
    if lan:
        app.config.update(SESSION_COOKIE_HTTPONLY=True,
                          SESSION_COOKIE_SAMESITE="Strict", SESSION_COOKIE_NAME="hsd_lan_" + secrets.token_hex(6),
                          PERMANENT_SESSION_LIFETIME=timedelta(hours=8), SESSION_REFRESH_EACH_REQUEST=False)
    admin_limiter = admin_auth.LoginLimiter()
    manager = JobManager(data_dir, settings_dir=settings_dir)
    uploads = EmployeeUploads(data_dir) if lan else None
    app.config["HSD_UPLOADS"] = uploads
    app.config["HSD_ACTIVE_UPLOADS"] = 0
    app.config["HSD_ACTIVE_DOWNLOADS"] = 0
    app.config["HSD_STOPPING"] = False
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
        hosts = {"127.0.0.1", "localhost"} | ({lan.host} if lan else set())
        if request.host.split(":", 1)[0] not in hosts:
            return jsonify(error="不支持此访问地址。"), 403
        port = app.config.get("HSD_PORT")
        if lan and port and request.host not in {f"{host}:{port}" for host in hosts}:
            return jsonify(error="不支持此访问地址。"), 403
        remote = bool(lan and not lan.is_host(request.remote_addr))
        is_upload = request.endpoint == "upload_job"
        if request.method == "POST":
            origin = request.headers.get("Origin")
            if (origin and origin != request.host_url.rstrip("/")) or (remote and not origin):
                return jsonify(error="请求来源不匹配。"), 403
            if not is_upload and (not request.is_json or not isinstance(request.get_json(silent=True), dict)):
                return jsonify(error="请求必须使用 JSON 对象。"), 400
        if lan and request.endpoint == "lan_login":
            return None
        admin_area = request.path == "/admin" or request.path.startswith("/api/admin/")
        protected_static = (request.endpoint == "static" and
            Path(str((request.view_args or {}).get("filename", "")).replace("\\", "/")).name.split(":", 1)[0].rstrip(" .").casefold()
            in {"admin.html", "admin.js", "admin.css"})
        # The admin area authenticates itself: an operator may open it from
        # another computer on the LAN with the account/password, without the
        # employee access code. Employee-only paths still require that code.
        admin_entry = (admin_area or protected_static
                       or request.endpoint in {"admin_login_page", "admin_login", "admin_logout"})
        if remote and not session.get("lan_authenticated") and not admin_entry:
            if request.endpoint == "index" and request.method == "GET":
                return (static / "lan-login.html").read_text("utf-8")
            return jsonify(error="请先输入局域网访问码。"), 401
        if remote and (request.endpoint in {"pick", "open_output", "shutdown"}
                       or (request.endpoint == "save_ai_settings")):
            return jsonify(error="此操作只能在主机上完成。"), 403
        if admin_area:
            if not admin_auth.authenticated(session):
                if request.path.startswith("/api/admin/"):
                    return jsonify(error="请先登录管理员分区。"), 401
                return (static / "admin-login.html").read_text("utf-8")
        if lan:
            employee_id()
        if lan and (request.view_args or {}).get("identifier"):
            with manager.lock:
                job = manager._get(request.view_args["identifier"])
                if job.get("_owner_id") != employee_id():
                    raise KeyError("找不到此任务，请在上传时使用的浏览器中打开。")
                if job.get("_upload_managed"):
                    uploads.validate_job(job)
                else:
                    lan.validate_paths({"workbook_path": job["_workbook_path"], "source_path": job["_source_path"],
                                        "output_root": job["_output_root"]})
        if request.method == "POST" and request.endpoint != "admin_login":
            provided = request.headers.get("X-HSD-Token", "")
            if not secrets.compare_digest(provided.encode(), token.encode()):
                return jsonify(error="会话已失效，请重新打开工具页面。"), 403
            with manager.lock:
                if app.config["HSD_STOPPING"] and request.endpoint != "shutdown":
                    raise Conflict("主机正在退出，请稍后重新打开员工入口。")
        if is_upload:
            request._hsd_upload_unlimited = True
            request.max_content_length = None
            request.max_form_memory_size = 512 * 1024
            request.max_form_parts = 8

    @app.teardown_request
    def release_upload_streams(exc):
        try:
            request.release_upload()
        except (OSError, ValueError):
            # Do not mask an interrupted/malformed request or follow a replaced
            # link during cleanup. No path, file contents or credentials logged.
            app.logger.warning("上传临时文件未能清理，请管理员检查磁盘空间与权限。")

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

    @app.errorhandler(UploadWriteError)
    def upload_write_error(exc):
        return jsonify(error=str(exc)), 400

    @app.errorhandler(Conflict)
    def conflict(exc):
        return jsonify(error=exc.description), 409

    @app.errorhandler(RequestEntityTooLarge)
    def too_large(exc):
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

    @app.get("/admin")
    def admin_page():
        return (static / "admin.html").read_text("utf-8").replace("__HSD_TOKEN__", json.dumps(token))

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
        if not admin_auth.verify_credentials(payload.get("username"), payload.get("password")):
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

        This is the one place credentials are returned to a page. It is limited
        to the password-protected, host-only admin area, responses are marked
        no-store by the global header policy, and nothing here is logged.
        """
        runtime = manager.ai_settings.runtime()
        return jsonify(keys=[{"id": row["id"], "label": row["label"],
                              "enabled": row["enabled"],
                              "source": row.get("source", "saved"),
                              "api_key": row["api_key"]}
                             for row in runtime.get("keys", []) if row.get("api_key")])

    @app.post("/api/admin/keys")
    def admin_keys():
        with manager.lock:
            if manager.has_active_operations():
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
        session["employee_id"] = secrets.token_hex(16)
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
        with manager.lock:
            if manager.has_active_operations():
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
                identifier = manager.create(payload, owner_id=employee_id(), downloadable=True, display_names=names, input_digests=input_digests)
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
            return jsonify(public)

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
        response.direct_passthrough = False
        @response.call_on_close
        def download_finished():
            with manager.lock:
                app.config["HSD_ACTIVE_DOWNLOADS"] -= 1
        response.headers["Cache-Control"] = "private, no-store"
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
            if app.config["HSD_ACTIVE_UPLOADS"] or app.config["HSD_ACTIVE_DOWNLOADS"]:
                raise ValueError("员工正在上传或下载文件，请传输完成后再退出。")
            if manager.has_active_operations():
                raise ValueError("任务正在处理，请完成后再退出工具。")
            app.config["HSD_STOPPING"] = True
        callback = app.config.get("HSD_SHUTDOWN")
        if callback:
            threading.Timer(0.3, callback).start()
        return jsonify(ok=True)

    return app
