"""Integrity checked, local validation qualification; no browser approval toggle."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import importlib.util
import marshal
from types import CodeType
from datetime import datetime, timedelta, timezone

IMPLEMENTATION_MODULES = ("ai_policy", "ai_client", "ai_images", "matching", "matching_verification", "archive_io")


class ValidationRegistry:
    def __init__(self, data_dir):
        self.directory = Path(data_dir)
        self.path = self.directory / "ai_validation.json"
        self.secret_path = self.directory / "ai_validation.secret"

    @staticmethod
    def _bytes(value):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()

    @staticmethod
    def _implementation():
        # Source and frozen loaders may compile the identical implementation at
        # different absolute paths.  Normalize every nested code object's path,
        # while preserving bytecode, constants and all behavioural metadata.
        def portable_code(code):
            return code.replace(co_filename="<hsd-ai-implementation>",
                                co_consts=tuple(portable_code(value) if isinstance(value, CodeType) else value
                                                for value in code.co_consts))

        signatures = {}
        for name in IMPLEMENTATION_MODULES:
            spec = importlib.util.find_spec("hsd_tool." + name)
            code = spec.loader.get_code("hsd_tool." + name) if spec and spec.loader else None
            if code is None:
                raise ValueError("无法验证当前复核模块。")
            signatures[name] = hashlib.sha256(marshal.dumps(portable_code(code))).hexdigest()
        return signatures

    def load(self):
        try:
            if self.path.stat().st_size > 262144 or self.secret_path.stat().st_size != 32:
                return {}
            payload = json.loads(self.path.read_text("utf-8"))
            expected = hmac.new(self.secret_path.read_bytes(), self._bytes(payload["record"]), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(expected, payload["signature"]):
                return {}
            record = payload["record"]
            from .ai_policy import POLICY_VERSION, PROMPT_VERSION
            if record.get("policy_version") != POLICY_VERSION or record.get("prompt_version") != PROMPT_VERSION:
                return {}
            if (record.get("implementation_sha256") != self._implementation()
                    or datetime.fromisoformat(record["expires_at"]) <= datetime.now(timezone.utc)):
                return {}
            return {**record, "trusted": True}
        except (OSError, ValueError, TypeError, KeyError):
            return {}

    def snapshot(self):
        record = self.load()
        return {"qualified": bool(record), "mode": "validated" if record else "evaluation",
                "model": record.get("model"), "categories": record.get("categories", []),
                "counts": record.get("counts", {}),
                "message": "已完成限定场景验证，仍逐项检查文件与编号。" if record else "验证未完成，AI先给出复核建议，仍需人工确认。"}

    def activate(self, observations, labels):
        from .ai_policy import build_validation_record
        record = build_validation_record(observations, labels)
        if record.get("implementation_sha256") != self._implementation():
            raise ValueError("调用时的复核实现与当前版本不同，不能重新激活旧记录。")
        now = datetime.now(timezone.utc)
        record.update(issued_at=now.isoformat(), expires_at=(now + timedelta(days=7)).isoformat())
        self.directory.mkdir(parents=True, exist_ok=True)
        if not self.secret_path.exists():
            with self.secret_path.open("xb") as stream:
                stream.write(secrets.token_bytes(32))
        signature = hmac.new(self.secret_path.read_bytes(), self._bytes(record), hashlib.sha256).hexdigest()
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps({"record": record, "signature": signature}, ensure_ascii=False, allow_nan=False), "utf-8")
        os.replace(temporary, self.path)
        return self.snapshot()
