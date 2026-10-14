"""Upload the portable archive to the matching GitHub release, with retries.

GitHub's asset endpoint has no resume support, and a proxy hiccup mid-transfer
leaves the release without its download. This entry point retries the upload and
verifies the result, so a release can be repaired as soon as the network is back.

Usage:
    python tools/upload_release_asset.py <release-tag> <file> [more files...]
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = "DZH166/Smart-Screening-Agent"
PROXY = os.environ.get("HSD_RELEASE_PROXY", "http://127.0.0.1:12000")
TOKEN = os.environ.get("GH_TOKEN", "").strip()
ATTEMPTS = int(os.environ.get("HSD_RELEASE_ATTEMPTS", "10"))


def opener():
    return urllib.request.build_opener(urllib.request.ProxyHandler({"http": PROXY, "https": PROXY}))


def call(method, url, payload=None, timeout=120, content_type=None):
    data = payload
    if isinstance(payload, dict):
        data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("Authorization", "Bearer " + TOKEN)
    request.add_header("Accept", "application/vnd.github+json")
    request.add_header("User-Agent", "hsd-release")
    if data is not None:
        request.add_header("Content-Type", content_type or "application/json")
    with opener().open(request, timeout=timeout) as response:
        body = response.read()
    return json.loads(body.decode("utf-8")) if body else {}


def main():
    if not TOKEN:
        raise SystemExit("请先设置 GH_TOKEN（从凭据管理器读取）。")
    if len(sys.argv) < 3:
        raise SystemExit("用法: python tools/upload_release_asset.py <release-tag> <file> [more files...]")
    tag = sys.argv[1]
    files = [Path(item) if Path(item).is_absolute() else ROOT / item for item in sys.argv[2:]]

    release = call("GET", f"https://api.github.com/repos/{REPO}/releases/tags/{tag}")
    release_id = release["id"]
    print(f"Release {tag} (id={release_id})")

    for path in files:
        payload = path.read_bytes()
        print(f"{path.name} · {len(payload)/1024**2:.1f} MB")
        for attempt in range(1, ATTEMPTS + 1):
            try:
                current = {a["name"]: a for a in call(
                    "GET", f"https://api.github.com/repos/{REPO}/releases/{release_id}")["assets"]}
            except Exception as exc:  # network down; wait and retry
                print(f"  [{attempt}/{ATTEMPTS}] 无法查询附件: {str(exc)[:70]}")
                time.sleep(20)
                continue
            if path.name in current and current[path.name]["size"] == len(payload):
                print("  已在远端就位，无需重传")
                break
            if path.name in current:
                call("DELETE", f"https://api.github.com/repos/{REPO}/releases/assets/{current[path.name]['id']}")
                print("  远端存在同名附件，已移除后重传")
            print(f"  [{attempt}/{ATTEMPTS}] 上传中 …", flush=True)
            started = time.monotonic()
            url = (f"https://uploads.github.com/repos/{REPO}/releases/{release_id}/assets"
                   f"?name={urllib.parse.quote(path.name)}")
            try:
                info = call("POST", url, payload, timeout=3600,
                            content_type="application/zip" if path.suffix == ".zip" else "text/plain")
                print(f"    成功 · {info.get('state')} · {info.get('size')} bytes · "
                      f"{time.monotonic()-started:.0f}s")
                print("   ", info.get("browser_download_url"))
                break
            except Exception as exc:
                print(f"    失败（{time.monotonic()-started:.0f}s）: {type(exc).__name__} {str(exc)[:80]}")
                time.sleep(20)
        else:
            print(f"  {path.name} 多次尝试仍未上传成功，请检查网络后重跑本脚本。")
            return 1

    final = {a["name"]: a for a in call(
        "GET", f"https://api.github.com/repos/{REPO}/releases/{release_id}")["assets"]}
    print("远端附件:")
    for name, asset in sorted(final.items()):
        print(f"  {name} · {asset['size']/1024**2:.1f} MB · {asset['state']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
