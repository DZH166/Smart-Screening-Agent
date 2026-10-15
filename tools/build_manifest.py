"""Bind portable acceptance to immutable runtime bytes and build inputs."""
import hashlib
import json
from pathlib import Path
import sys


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def inputs(root):
    paths = [root / name for name in ("launch.py", "build.ps1", "requirements.txt", "requirements-dev.txt")]
    paths += [path for path in (root / "hsd_tool").rglob("*") if path.is_file()
              and path.suffix in {".py", ".js", ".css", ".html"} and "__pycache__" not in path.parts]
    return {path.relative_to(root).as_posix(): digest(path) for path in sorted(paths)}


def create(bundle):
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    from hsd_tool import __version__
    runtime = [bundle / "HSD图号助手.exe"] + [path for path in (bundle / "_internal").rglob("*") if path.is_file()]
    manifest = {"version": __version__, "inputs": inputs(root),
                "runtime": {path.relative_to(bundle).as_posix(): digest(path) for path in sorted(runtime)}}
    (bundle / "构建校验.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), "utf-8")
    print("Runtime manifest:", len(runtime), "files")


if __name__ == "__main__":
    create(Path(sys.argv[1]))
