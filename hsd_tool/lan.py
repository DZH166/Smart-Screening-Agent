"""Explicit, subnet-limited access for a shared LAN test session."""
from __future__ import annotations

import ipaddress
import secrets
import threading
import time
from collections import defaultdict, deque
from pathlib import Path

DEFAULT_CODE = "HSD"


class LanAccess:
    def __init__(self, interface: str, input_root: Path, output_root: Path, *, code: str | None = None):
        try:
            address = ipaddress.IPv4Interface(interface)
        except ValueError as exc:
            raise ValueError("局域网地址必须包含 IPv4 地址与网段，例如 192.168.0.160/24。") from exc
        private = [ipaddress.IPv4Network(value) for value in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")]
        if "/" not in interface or not any(address.network.subnet_of(net) for net in private):
            raise ValueError("局域网模式仅支持明确指定的内网地址和子网。")
        if address.ip in {address.network.network_address, address.network.broadcast_address}:
            raise ValueError("请使用这台主机的有效局域网地址。")
        self.host = str(address.ip)
        self.network = address.network
        self.input_root = Path(input_root).resolve()
        self.output_root = Path(output_root).resolve()
        if not self.input_root.is_dir():
            raise ValueError("局域网测试素材目录不存在。")
        if self.output_root.is_relative_to(self.input_root):
            raise ValueError("局域网输出目录必须位于素材目录之外。")
        self.output_root.mkdir(parents=True, exist_ok=True)
        self.code = self._code(code if code is not None else DEFAULT_CODE)
        self.min_code_length = 1
        self.access_codes = None
        self._attempts = defaultdict(deque)
        self._lock = threading.Lock()

    @staticmethod
    def _code(value) -> str:
        if not isinstance(value, str):
            raise ValueError("局域网访问码格式不正确。")
        value = value.strip()
        if not 1 <= len(value) <= 64 or any(not 33 <= ord(character) <= 126 for character in value):
            raise ValueError("局域网访问码只能是 1–64 位可见字符。")
        return value

    def is_host(self, address: str | None) -> bool:
        return address in {self.host, "127.0.0.1", "::1"}

    def allows(self, address: str | None) -> bool:
        try:
            value = ipaddress.ip_address(address)
            return value.is_loopback or (value.version == 4 and value in self.network)
        except (ValueError, TypeError):
            return False

    def login(self, address: str, supplied) -> bool | None:
        """None means throttled. Neither the code nor submitted text is logged."""
        now = time.monotonic()
        with self._lock:
            attempts = self._attempts.get(address)
            if attempts is None:
                attempts = deque()
            while attempts and now - attempts[0] >= 60:
                attempts.popleft()
            if len(attempts) >= 10:
                return None
            attempts.append(now)
            self._attempts[address] = attempts
            if len(self._attempts) > 1024:
                for key in [key for key, value in self._attempts.items()
                            if not value or now - value[-1] >= 60]:
                    self._attempts.pop(key, None)
                if len(self._attempts) > 1024:
                    # Hard bound; an evicted address gets a fresh budget.
                    for key, _ in sorted(self._attempts.items(), key=lambda item: item[1][-1])[
                            :len(self._attempts) - 1024]:
                        self._attempts.pop(key, None)
            valid_shape = (isinstance(supplied, str) and 1 <= len(supplied) <= 64
                           and all(33 <= ord(character) <= 126 for character in supplied))
            if self.access_codes is not None:
                # The same per-address budget covers every configured code.
                # Verification errors fail closed; never retry via the old code.
                valid = valid_shape and self.access_codes.verify(supplied)
            else:
                valid = valid_shape and secrets.compare_digest(supplied.encode("ascii"), self.code.encode("ascii"))
            if valid:
                # A successful login clears the budget for this address; keep no
                # dead key behind for it.
                self._attempts.pop(address, None)
            return valid

    def validate_paths(self, payload: dict) -> dict:
        """Return canonical paths so later resolution cannot reinterpret relative input."""
        result = dict(payload)
        for key, root in (("workbook_path", self.input_root), ("source_path", self.input_root),
                          ("output_root", self.output_root)):
            raw = str(payload.get(key, "")).strip().strip('"')
            if not raw and key == "output_root":
                raw = str(self.output_root)
            if not raw or raw.startswith(("\\\\", "//")):
                raise ValueError("请填写主机指定测试目录中的本机完整路径，不支持网络共享路径。")
            path = Path(raw)
            if not path.is_absolute():
                raise ValueError("局域网测试请使用主机上的完整路径。")
            for part in (path, *path.parents):
                if part.is_symlink() or (hasattr(part, "is_junction") and part.is_junction()):
                    raise ValueError("局域网测试不支持符号链接或目录联接路径。")
            resolved = path.resolve()
            if not resolved.is_relative_to(root) or str(resolved).startswith(("\\\\", "//")):
                raise ValueError("文件或结果位置超出主机指定的局域网测试目录。")
            result[key] = str(resolved)
        return result
