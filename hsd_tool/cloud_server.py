"""Explicit HTTPS reverse-proxy service; desktop/LAN startup is unchanged.

Only an administrator-configured local reverse proxy is transport-trusted.
Its address never grants employee authentication or host-machine privileges.
Run with ``python -m hsd_tool.cloud_server`` using a private service environment.
"""
from __future__ import annotations

import ipaddress
import os
import re
import stat
import threading
from collections import defaultdict, deque
from pathlib import Path
from urllib.parse import urlsplit

from .lan import LanAccess


def _private_file(path: Path) -> bytes:
    """Read a service-owned secret file; error messages never include contents."""
    if not path.is_absolute() or any(part.is_symlink() for part in (path, *path.parents)):
        raise ValueError("服务器凭据必须使用独立私有文件的绝对路径。")
    try:
        metadata = path.stat()
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise ValueError("服务器凭据必须是普通文件。")
        if os.name != "nt":
            parent = path.parent.stat()
            if (metadata.st_uid != os.geteuid() or stat.S_IMODE(metadata.st_mode) != 0o600
                    or parent.st_uid != os.geteuid() or stat.S_IMODE(parent.st_mode) != 0o700):
                raise ValueError("服务器凭据目录与文件必须属于服务用户且权限为0700/0600。")
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(descriptor, "rb") as stream:
            opened = os.fstat(stream.fileno())
            if (opened.st_ino, opened.st_dev) != (metadata.st_ino, metadata.st_dev):
                raise ValueError("服务器凭据文件已变化，请重新启动。")
            if (not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1
                    or (os.name != "nt" and (opened.st_uid != os.geteuid()
                                             or stat.S_IMODE(opened.st_mode) != 0o600))):
                raise ValueError("服务器凭据文件权限已变化，请重新启动。")
            raw = stream.read(4097)
        if len(raw) > 4096:
            raise ValueError("服务器凭据文件格式无效。")
        return raw
    except OSError:
        raise ValueError("服务器凭据文件无法读取，请检查服务用户与权限。") from None


class CloudAccess(LanAccess):
    """Reuse employee sessions/ownership without any host access exception."""

    def __init__(self, origin: str, code: str, *, admin_credentials=None, min_code_length=16):
        if type(min_code_length) is not int or not 1 <= min_code_length <= 64:
            raise ValueError("服务器员工访问码最短长度必须为1–64之间的整数。")
        try:
            parsed = urlsplit(origin)
            port = parsed.port
            hostname = parsed.hostname
        except (ValueError, TypeError):
            raise ValueError("请设置完整的HTTPS员工访问地址。") from None
        if (parsed.scheme != "https" or not hostname or parsed.username is not None
                or parsed.password is not None or parsed.path not in {"", "/"}
                or parsed.query or parsed.fragment or not re.fullmatch(r"[A-Za-z0-9.\-:\[\]]+", parsed.netloc)
                or (port is not None and not 1 <= port <= 65535)):
            raise ValueError("服务器公开地址必须是HTTPS源地址，不含路径、账号或查询参数。")
        host = hostname.lower()
        try:
            address = ipaddress.ip_address(host)
            host = f"[{address.compressed}]" if address.version == 6 else address.compressed
        except ValueError:
            if (len(host) > 253 or any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
                                       for label in host.split("."))):
                raise ValueError("服务器域名格式无效。") from None
        self.host = host
        self.authority = host + (f":{port}" if port not in {None, 443} else "")
        self.origin = "https://" + self.authority
        self.code = self._code(code)
        self.min_code_length = min_code_length
        self.access_codes = None
        self.admin_credentials = admin_credentials
        if len(self.code) < min_code_length:
            raise ValueError(f"服务器员工访问码至少需要{min_code_length}位，请通过私有文件配置。")
        self._attempts = defaultdict(deque)
        self._lock = threading.Lock()

    def is_host(self, address):
        return False

    def allows(self, address):
        try:
            ipaddress.ip_address(address)
            return True
        except (ValueError, TypeError):
            return False

    def validate_paths(self, payload):
        raise ValueError("服务器只接受浏览器上传，不接受主机文件路径。")

    def middleware(self, app):
        return CloudProxyBoundary(app, self)


class CloudProxyBoundary:
    """Trust one local proxy only; it must overwrite client IP/protocol headers.

    Gunicorn's own forwarded-header handling is disabled. This checks the real
    socket peer before replacing REMOTE_ADDR and never trusts an arbitrary
    Forwarded, X-Real-IP, forwarded host or comma-separated proxy chain.
    """
    def __init__(self, app, access):
        self.app, self.access = app, access

    def __call__(self, environ, start_response):
        try:
            peer = ipaddress.ip_address(environ.get("REMOTE_ADDR", ""))
            raw_client = environ.get("HTTP_X_FORWARDED_FOR", "")
            if raw_client != raw_client.strip() or "," in raw_client:
                raise ValueError()
            client = ipaddress.ip_address(raw_client)
            if (not peer.is_loopback or environ.get("HTTP_X_FORWARDED_PROTO") != "https"
                    or environ.get("HTTP_HOST", "").lower() != self.access.authority):
                raise ValueError()
        except (ValueError, TypeError):
            body = '{"error":"访问入口配置无效，请通过正式HTTPS网址访问。"}'.encode("utf-8")
            start_response("403 Forbidden", [("Content-Type", "application/json; charset=utf-8"),
                                            ("Content-Length", str(len(body))), ("Cache-Control", "no-store"),
                                            ("X-Content-Type-Options", "nosniff")])
            return [body]
        clean = environ.copy()
        for key in list(clean):
            if key in {"HTTP_FORWARDED", "HTTP_X_REAL_IP"} or key.startswith("HTTP_X_FORWARDED_"):
                clean.pop(key)
        clean["REMOTE_ADDR"] = str(client)
        clean["wsgi.url_scheme"] = "https"
        clean["HTTP_HOST"] = self.access.authority
        clean["SERVER_NAME"] = self.access.host.strip("[]")
        clean["SERVER_PORT"] = str(urlsplit(self.access.origin).port or 443)
        return self.app(clean, start_response)


def create_cloud_app(environ=None):
    env = os.environ if environ is None else environ
    required = ("HSD_PUBLIC_ORIGIN", "HSD_DATA_DIR", "HSD_SETTINGS_DIR",
                "HSD_EMPLOYEE_CODE_FILE", "HSD_CREDENTIAL_KEY_FILE", "HSD_ADMIN_CREDENTIAL_FILE")
    if any(not env.get(name) for name in required):
        raise ValueError("服务器缺少公开地址、数据目录或私有凭据文件配置。")
    # Default policy remains unchanged. A deliberately configured instance may
    # accept its operator-selected shorter code; request data cannot set this.
    minimum = env.get("HSD_EMPLOYEE_CODE_MIN_LENGTH", "16")
    if (not isinstance(minimum, str)
            or not re.fullmatch(r"(?:[1-9]|[1-5][0-9]|6[0-4])", minimum)):
        raise ValueError("服务器员工访问码最短长度配置必须为1–64之间的正整数。")
    minimum = int(minimum)
    data, settings = Path(env["HSD_DATA_DIR"]), Path(env["HSD_SETTINGS_DIR"])
    if not data.is_absolute() or not settings.is_absolute():
        raise ValueError("服务器数据与设置目录必须使用绝对路径。")
    try:
        code = _private_file(Path(env["HSD_EMPLOYEE_CODE_FILE"])).decode("ascii").strip()
    except UnicodeError:
        raise ValueError("员工访问码文件必须使用可见ASCII字符。") from None
    from .cloud_admin import CloudAdminCredentials
    access = CloudAccess(env["HSD_PUBLIC_ORIGIN"], code,
                         admin_credentials=CloudAdminCredentials(Path(env["HSD_ADMIN_CREDENTIAL_FILE"])),
                         min_code_length=minimum)
    # AiSettings independently validates ownership/permissions and encrypts the
    # provider keys. No plaintext/Windows-DPAPI fallback is enabled here.
    if not Path(env["HSD_CREDENTIAL_KEY_FILE"]).is_absolute():
        raise ValueError("服务器加密主密钥文件必须使用绝对路径。")
    from .server import create_app
    app = create_app(data, cloud=access, settings_dir=settings)
    from .cloud_retention import CloudRetention
    try:
        if app.config["HSD_MANAGER"].ai_settings.snapshot().get("key_persistence") != "linux_aesgcm":
            raise ValueError("云服务必须启用Linux加密密钥存储，不能降级为会话内保存。")
        retention = CloudRetention(app.config["HSD_MANAGER"], app.config["HSD_JOB_LEASES"],
                                   companion=app.config.get("HSD_MATERIAL_MANAGER")).start()
        app.config["HSD_RETENTION"] = retention
    except BaseException:
        materials = app.config.get("HSD_MATERIAL_MANAGER")
        if materials is not None:
            materials.close()
        app.config["HSD_MANAGER"].close()
        raise
    return app


def main():
    if os.name == "nt":
        raise SystemExit("云服务入口用于Linux；Windows请使用原本机或局域网入口。")
    os.umask(0o077)
    from .cloud_gunicorn import run
    run()


if __name__ == "__main__":
    main()
