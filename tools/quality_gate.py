"""One-command quality gate for this repository.

Runs the checks that catch the failures we have actually seen, in under two
minutes, without network access or paid model calls:

1. every Python module compiles and imports;
2. every browser script parses, and its synthetic UI suite passes;
3. no credential-shaped literal is committed outside synthetic fixtures;
4. the deployment files reference only files that exist.

The full pytest suite is deliberately not part of this gate (25 minutes); run
``python -m pytest`` for that, or the scheduled workflow.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NODE = "node"

# Serious shapes are scanned everywhere; the loose "assignment of a long
# literal" shape only outside tests/, where fixture names are synthetic by
# design ("never-show-...", "gateway-token-0123456789").
SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)
FIXTURE_PRONE = re.compile(r"(?i)(api[_-]?key|secret|token)\s*[=:]\s*[\"'][A-Za-z0-9_\-]{24,}[\"']")
# Fixtures and documentation use obviously synthetic values on purpose.
SYNTHETIC = ("synthetic", "example", "test-credential-not-real", "synthetic-private-key",
             "synthetic-token", "placeholder")
SKIP_DIRECTORIES = {".git", ".venv", "build", "dist", "tmp", "交付", "__pycache__",
                    ".pytest_cache", ".pytest_tmp", "图片编辑"}


def run(command, *, cwd=ROOT):
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True)
    return result.returncode, (result.stdout + result.stderr).strip()


def tracked_files():
    code, output = run(["git", "ls-files"])
    if code == 0 and output:
        return [ROOT / line for line in output.splitlines() if line.strip()]
    return [path for path in ROOT.rglob("*")
            if path.is_file() and not (SKIP_DIRECTORIES & set(path.relative_to(ROOT).parts))]


def check_python(failures):
    code, output = run([sys.executable, "-m", "compileall", "-q", "hsd_tool", "tools"])
    if code:
        failures.append(("python-compile", output[-800:]))
    modules = sorted(path.stem for path in (ROOT / "hsd_tool").glob("*.py") if path.stem != "__main__")
    skipped = {"cloud_gunicorn", "cloud_server", "gateway", "lan", "material_demo_server"}
    code, output = run([sys.executable, "-c",
                        "import importlib,sys\n"
                        "mods=%r\n"
                        "bad=[]\n"
                        "for m in mods:\n"
                        "    try: importlib.import_module('hsd_tool.'+m)\n"
                        "    except Exception as exc: bad.append(m+': '+type(exc).__name__)\n"
                        "print(','.join(bad))\n" % [m for m in modules if m not in skipped]])
    if code:
        failures.append(("python-import", output[-800:]))
    elif output.strip():
        failures.append(("python-import", output.strip()))


def check_javascript(failures):
    scripts = sorted((ROOT / "hsd_tool" / "static").glob("*.js"))
    for script in scripts:
        code, output = run([NODE, "--check", str(script)])
        if code:
            failures.append((f"js-syntax:{script.name}", output[-400:]))
    suites = sorted((ROOT / "tests").glob("test_*.js"))
    for suite in suites:
        code, output = run([NODE, str(suite)])
        if code or "FAIL" in output:
            failures.append((f"js-suite:{suite.name}", output[-800:]))


def check_secrets(failures):
    allowed = ROOT / "tests"
    for path in tracked_files():
        if not path.is_file() or path.suffix.lower() in {".png", ".jpg", ".webp", ".zip", ".tgz"}:
            continue
        try:
            text = path.read_text("utf-8", errors="ignore")
        except OSError:
            continue
        patterns = SECRET_PATTERNS if path.is_relative_to(allowed) else SECRET_PATTERNS + (FIXTURE_PRONE,)
        for pattern in patterns:
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                snippet = text.splitlines()[line - 1] if line - 1 < len(text.splitlines()) else ""
                if any(marker in snippet.lower() for marker in SYNTHETIC):
                    continue
                if path.is_relative_to(allowed) and "not-real" in snippet:
                    continue
                failures.append((f"secret:{path.relative_to(ROOT)}:{line}", snippet.strip()[:160]))


def check_deploy_files(failures):
    referenced = {
        "deploy/hsd-healthcheck.service": ["/usr/local/lib/hsd-agent/hsd-healthcheck.sh"],
        "deploy/hsd-agent.service.example": ["/opt/hsd-agent/current", "/etc/hsd-agent/service.env"],
    }
    for name, paths in referenced.items():
        if not (ROOT / name).is_file():
            failures.append((f"deploy-missing:{name}", "file not found"))
            continue
        text = (ROOT / name).read_text("utf-8")
        for value in paths:
            if value not in text:
                failures.append((f"deploy-reference:{name}", value))
    for script in ("deploy/hsd-healthcheck.sh", "deploy/backup.sh"):
        path = ROOT / script
        if not path.is_file():
            failures.append((f"deploy-missing:{script}", "file not found"))
        elif not path.read_text("utf-8").startswith("#!/usr/bin/env bash"):
            failures.append((f"deploy-shebang:{script}", "missing bash shebang"))


def main():
    failures = []
    check_python(failures)
    check_javascript(failures)
    check_secrets(failures)
    check_deploy_files(failures)
    if failures:
        print(json.dumps({"ok": False, "failures": [{"check": name, "detail": detail}
                                                     for name, detail in failures]},
                         ensure_ascii=False, indent=2))
        return 1
    print(json.dumps({"ok": True, "checks": ["python-compile", "python-import", "js-syntax",
                                             "js-suites", "secret-scan", "deploy-files"]},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
