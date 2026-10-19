"""Internal AI gateway that owns the one shared DeepSeek credential.

Installed clients keep no API key. They send their normal chat-completions
requests here with a local bearer token; this process forwards the body to the
official endpoint with the real key. The key never leaves this machine and is
never rendered, logged, or returned by any route.

Only explicit, size-bounded forwarding is implemented. Redirects are refused,
and the status/configuration pages are limited to the host itself.
"""
from __future__ import annotations

import html
import ipaddress
import json
import logging
import secrets
import threading
import urllib.error
import urllib.request
from pathlib import Path

from flask import Flask, Response, jsonify, request

from .ai_client import ENDPOINT as UPSTREAM
from .ai_client import MAX_REQUEST_BYTES, MAX_RESPONSE_BYTES, _NoRedirect
from .ai_settings import MODEL, AiSettings

TOKEN_NAME = "网关访问令牌.txt"
INFO_NAME = "网关信息.json"
LOCAL_ADDRESSES = {"127.0.0.1", "::1"}


def valid_bind(value) -> str:
    """A gateway must listen on one explicit private IPv4 address."""
    try:
        address = ipaddress.IPv4Address(str(value))
    except ValueError as exc:
        raise ValueError("网关监听地址必须是有效的 IPv4 地址，例如 192.168.0.160。") from exc
    if not address.is_private or address.is_loopback or address.is_unspecified:
        raise ValueError("网关监听地址必须是本机的内网地址，不能使用公网、回环或 0.0.0.0。")
    return str(address)


def default_bind() -> str:
    """Pick one private IPv4 when the operator omits --gateway-bind."""
    import socket

    candidates = []
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            probe.connect(("223.5.5.5", 80))
            candidates.append(probe.getsockname()[0])
        finally:
            probe.close()
    except OSError:
        pass
    try:
        candidates.extend(info[4][0] for info in
                          socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET))
    except OSError:
        pass
    for value in candidates:
        try:
            return valid_bind(value)
        except ValueError:
            continue
    raise ValueError("没有找到可用的内网 IPv4 地址，请用 --gateway-bind 明确指定。")


def load_token(data_dir) -> str:
    """Persist one LAN bearer token; it is a shared secret, never a DeepSeek key."""
    path = Path(data_dir) / TOKEN_NAME
    try:
        existing = path.read_text("ascii").strip()
        if 10 <= len(existing) <= 512:
            return existing
    except (OSError, UnicodeError):
        pass
    token = secrets.token_urlsafe(24)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(token, "ascii")
    return token


def _same_origin() -> bool:
    """Browsers send Origin for cross-site posts; refuse anything not ours."""
    origin = request.headers.get("Origin")
    if not origin:
        return True
    return origin.rstrip("/") in {
        f"http://{request.host}", f"http://{request.host}/"}


def create_app(data_dir, *, bind: str, port: int = 0, settings=None, opener=None, upstream=None):
    bind = valid_bind(bind)
    settings = settings if settings is not None else AiSettings(Path(data_dir))
    upstream = upstream or UPSTREAM
    token = load_token(data_dir)
    app = Flask("hsd_gateway")
    app.config.update(MAX_CONTENT_LENGTH=MAX_REQUEST_BYTES, JSON_AS_ASCII=False,
                      HSD_GATEWAY_BIND=bind, HSD_GATEWAY_PORT=port)
    stats = {"requests": 0, "ok": 0, "errors": 0, "last_error": ""}
    lock = threading.Lock()
    opener = opener or urllib.request.build_opener(_NoRedirect())

    def is_host() -> bool:
        return request.remote_addr in LOCAL_ADDRESSES | {bind}

    def authorized() -> bool:
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return False
        return secrets.compare_digest(header[7:].strip().encode(), token.encode("ascii"))

    def count(**changes):
        with lock:
            for key, value in changes.items():
                if key == "last_error":
                    stats["last_error"] = value
                else:
                    stats[key] += value

    @app.get("/health")
    def health():
        runtime = settings.runtime()
        with lock:
            snapshot = dict(stats)
        return jsonify(ok=runtime["via_gateway"] is False and bool(runtime["api_key"]),
                       model=MODEL, configured=bool(runtime["api_key"]),
                       listening=f"{request.host}", requests=snapshot["requests"])

    @app.post("/v1/chat/completions")
    def completions():
        if not authorized():
            count(requests=1, errors=1, last_error="未通过令牌校验")
            return jsonify({"error": {"message": "网关访问令牌无效"}}), 401
        runtime = settings.runtime()
        if runtime["via_gateway"] or not runtime["api_key"]:
            count(requests=1, errors=1, last_error="网关未保存 DeepSeek 密钥")
            return jsonify({"error": {"message": "网关未保存 DeepSeek 密钥"}}), 503
        body = request.get_data(cache=False)
        if not body or len(body) > MAX_REQUEST_BYTES:
            count(requests=1, errors=1, last_error="请求体大小不正确")
            return jsonify({"error": {"message": "请求体大小不正确"}}), 413
        forwarded = urllib.request.Request(upstream, data=body, method="POST", headers={
            "Authorization": "Bearer " + runtime["api_key"], "Content-Type": "application/json",
            "Accept": "application/json", "User-Agent": "HSD-Gateway/DeepSeek"})
        status, raw = 502, b""
        try:
            with opener.open(forwarded, timeout=120) as response:
                if response.geturl() != upstream:
                    raise ValueError("redirect")
                raw, status = response.read(MAX_RESPONSE_BYTES + 1), response.status
        except urllib.error.HTTPError as error:
            status = error.code
            try:
                raw = error.read(MAX_RESPONSE_BYTES + 1)
            finally:
                error.close()
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as error:
            count(requests=1, errors=1, last_error=type(error).__name__)
            logging.warning("gateway upstream failure: %s", type(error).__name__)
            return jsonify({"error": {"message": "上游接口暂不可达，请稍后重试"}}), 502
        if len(raw) > MAX_RESPONSE_BYTES:
            count(requests=1, errors=1, last_error="上游响应过大")
            return jsonify({"error": {"message": "上游响应过大"}}), 502
        if 200 <= status < 300:
            count(requests=1, ok=1)
            return Response(raw, status=status, mimetype="application/json")
        count(requests=1, errors=1, last_error=f"上游返回 {status}")
        return Response(raw, status=status, mimetype="application/json")

    @app.post("/configure")
    def configure():
        """Host-only: the one place the real key is entered, saved with DPAPI."""
        if not is_host():
            return jsonify({"error": {"message": "只允许主机操作"}}), 403
        if not _same_origin():
            return jsonify({"error": {"message": "请求来源不正确"}}), 403
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify({"error": {"message": "设置格式不正确"}}), 400
        try:
            settings.save({"api_key": str(payload.get("api_key", "")),
                           "enabled": bool(payload.get("enabled", True))})
        except ValueError as exc:
            return jsonify({"error": {"message": str(exc)}}), 400
        return jsonify(settings.snapshot())

    @app.get("/")
    def status_page():
        if not is_host():
            return Response("只允许在主机上查看网关状态页。", status=403, mimetype="text/plain")
        runtime = settings.runtime()
        with lock:
            snapshot = dict(stats)
        configured = "已保存" if runtime["api_key"] else "未保存"
        client_config = json.dumps({"endpoint": f"http://{bind}:{request.host.split(':')[-1]}/v1/chat/completions",
                                    "token": token}, ensure_ascii=False, indent=2)
        page = f"""<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<title>智筛 Agent · 内网 AI 网关</title>
<style>body{{font-family:system-ui,"Microsoft YaHei";max-width:760px;margin:40px auto;line-height:1.7;padding:0 18px}}
code,pre{{background:#f4f4f5;padding:2px 6px;border-radius:4px}}pre{{padding:12px;overflow:auto}}
.warn{{color:#a15c00}}</style>
<h1>内网 AI 网关</h1>
<p>监听地址：<code>http://{html.escape(bind)}:{html.escape(str(request.host.split(':')[-1]))}</code>　
模型：<code>{html.escape(MODEL)}</code>　DeepSeek 密钥：<b>{configured}</b></p>
<p>请求：{snapshot['requests']} 次，成功 {snapshot['ok']} 次，失败 {snapshot['errors']} 次。
最近错误：{html.escape(snapshot['last_error'] or '无')}</p>
<p class="warn">密钥只保存在这台机器，客户端不会拿到。以下内容给员工机器上的
<code>gateway.json</code> 使用：</p><pre>{html.escape(client_config)}</pre>
<h2>填写或更换 DeepSeek 密钥</h2>
<form id="f"><input id="k" type="password" size="60" placeholder="sk-..." autocomplete="off">
<button type="submit">保存到本机</button></form>
<p id="m"></p>
<script>
document.getElementById('f').addEventListener('submit', async (e) => {{
  e.preventDefault();
  const key = document.getElementById('k').value;
  const r = await fetch('/configure', {{method:'POST',headers:{{'Content-Type':'application/json'}},
    body: JSON.stringify({{api_key:key, enabled:true}})}});
  document.getElementById('k').value = '';
  document.getElementById('m').textContent = r.ok ? '已保存（不回显）。' : '保存失败：' +
    ((await r.json()).error?.message || r.status);
}});
</script></html>"""
        return Response(page, mimetype="text/html")

    return app


def run_gateway(data_dir, *, bind: str, port: int, open_browser: bool = True) -> None:
    import webbrowser

    from werkzeug.serving import make_server

    app = create_app(data_dir, bind=bind, port=port)
    server = make_server(bind, port, app, threaded=True)
    url = f"http://{bind}:{server.server_port}"
    app.config["HSD_GATEWAY_PORT"] = server.server_port
    data = Path(data_dir)
    data.mkdir(parents=True, exist_ok=True)
    (data / INFO_NAME).write_text(json.dumps(
        {"url": url, "model": MODEL, "token_file": str(data / TOKEN_NAME)}, ensure_ascii=False), "utf-8")
    logging.info("Gateway listening on %s", url)
    try:
        if open_browser:
            webbrowser.open(url + "/")
        server.serve_forever()
    finally:
        server.server_close()
