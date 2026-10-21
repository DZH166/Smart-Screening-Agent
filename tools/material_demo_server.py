"""Read-only, loopback-only server for the material extraction UI demo.

This runner deliberately does not import the HSD application or accept uploads.
"""

from __future__ import annotations

import argparse
import mimetypes
import shutil
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit


DEMO_ROOT = Path(__file__).resolve().parent / "material_demo"


class DemoHandler(BaseHTTPRequestHandler):
    """Serve only existing files within the demo directory."""

    server_version = "MaterialDemo"
    sys_version = ""

    def do_GET(self) -> None:
        self._serve_file(include_body=True)

    def do_HEAD(self) -> None:
        self._serve_file(include_body=False)

    def _serve_file(self, *, include_body: bool) -> None:
        # Binding to loopback limits network access; checking Host also avoids
        # treating a page addressed by an unrelated hostname as this demo.
        port = self.server.server_port
        if self.headers.get("Host", "") not in {
            f"127.0.0.1:{port}", f"localhost:{port}"
        }:
            self.send_error(HTTPStatus.BAD_REQUEST, "Use the local demo address")
            return

        try:
            request_url = urlsplit(self.path)
            if request_url.scheme or request_url.netloc:
                raise ValueError("An absolute URL is not a demo file path")
            path = unquote(request_url.path, errors="strict")
            if "\x00" in path or "\\" in path:
                raise ValueError("Invalid file path")
            target = (DEMO_ROOT / (path.lstrip("/") or "index.html")).resolve()
            if not target.is_relative_to(DEMO_ROOT.resolve()) or not target.is_file():
                self.send_error(HTTPStatus.NOT_FOUND, "Demo file not found")
                return
            source = target.open("rb")
        except (OSError, UnicodeError, ValueError):
            self.send_error(HTTPStatus.NOT_FOUND, "Demo file not found")
            return

        with source:
            self.send_response(HTTPStatus.OK)
            content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            if content_type.startswith("text/") or content_type in {
                "application/javascript", "application/json", "image/svg+xml"
            }:
                content_type += "; charset=utf-8"
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(target.stat().st_size))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            if include_body:
                try:
                    shutil.copyfileobj(source, self.wfile)
                except (BrokenPipeError, ConnectionResetError):
                    pass

    def _reject_write(self) -> None:
        self.close_connection = True
        self.send_response(HTTPStatus.METHOD_NOT_ALLOWED)
        self.send_header("Allow", "GET, HEAD")
        self.send_header("Content-Length", "0")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()

    do_POST = _reject_write
    do_PUT = _reject_write
    do_PATCH = _reject_write
    do_DELETE = _reject_write
    do_OPTIONS = _reject_write

    def log_message(self, format: str, *args: object) -> None:
        # No request logs or uploaded-file records are created by this runner.
        pass


def local_port(value: str) -> int:
    port = int(value)
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("Port must be between 1 and 65535")
    return port


def main() -> None:
    parser = argparse.ArgumentParser(description="仅本机查看素材提取界面演示")
    parser.add_argument("--port", type=local_port, default=8870)
    args = parser.parse_args()
    if not (DEMO_ROOT / "index.html").is_file():
        parser.error("演示页面尚未准备好：tools/material_demo/index.html")
    with ThreadingHTTPServer(("127.0.0.1", args.port), DemoHandler) as server:
        server.daemon_threads = True
        print(f"素材提取界面演示：http://127.0.0.1:{args.port}/", flush=True)
        print("仅本机演示，不是生产上线；没有真实 AI 处理，也不会读取 HSD 凭据。", flush=True)
        print("选图只在浏览器预览，不上传；结果和下载均为内置合成示例。", flush=True)
        print("按 Ctrl+C 关闭演示。", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
