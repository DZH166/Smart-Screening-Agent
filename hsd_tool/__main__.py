"""Windows launcher and isolated native file dialogs."""
from __future__ import annotations

import argparse
import ctypes
import json
import logging
import os
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path


def native_picker(kind, result_path):
    result = {"path": ""}
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        root.update()
        if kind == "workbook":
            selected = filedialog.askopenfilename(parent=root, title="选择图片编号表格", filetypes=[("Excel 表格", "*.xlsx")])
        elif kind == "zip":
            selected = filedialog.askopenfilename(parent=root, title="选择 AI 文件压缩包", filetypes=[("ZIP 压缩包", "*.zip")])
        else:
            selected = filedialog.askdirectory(parent=root, title="选择输出位置" if kind == "output" else "选择 AI 文件夹", mustexist=kind != "output")
        result["path"] = selected or ""
        root.destroy()
    except Exception as exc:
        result["error"] = f"无法打开文件选择窗口，可改为粘贴路径：{exc}"
    Path(result_path).write_text(json.dumps(result, ensure_ascii=False), "utf-8")


def main():
    parser = argparse.ArgumentParser(description="HSD 图片编号工具")
    parser.add_argument("--pick", choices=["workbook", "zip", "folder", "output"])
    parser.add_argument("--result")
    parser.add_argument("--data-dir")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--self-check", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.pick:
        native_picker(args.pick, args.result)
        return
    if args.self_check:
        import tkinter as tk
        import cv2
        import numpy
        import pymupdf
        from PIL import Image
        root = tk.Tk()
        root.withdraw()
        root.update()
        tk_version = root.tk.call("info", "patchlevel")
        root.destroy()
        check = {"ok": True, "frozen": bool(getattr(sys, "frozen", False)), "tk": tk_version,
                 "opencv": cv2.__version__, "numpy": numpy.__version__, "pymupdf": pymupdf.VersionBind,
                 "pillow": Image.__version__}
        from . import __version__
        from .ai_registry import ValidationRegistry
        from .ai_policy import POLICY_VERSION
        check.update(version=__version__, ai_policy=POLICY_VERSION,
                     ai_implementation=ValidationRegistry._implementation())
        Path(args.result).write_text(json.dumps(check), "utf-8")
        return
    data = Path(args.data_dir) if args.data_dir else Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "HSD图片编号工具"
    data.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=str(data / "运行日志.log"), level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", encoding="utf-8")
    instance_path = data / "instance.json"
    mutex = None
    if os.name == "nt" and not args.data_dir:
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
        kernel.CreateMutexW.restype = wintypes.HANDLE
        mutex = kernel.CreateMutexW(None, False, "Local\\HSDPictureNumberingTool")
        if ctypes.get_last_error() == 183:
            for _ in range(20):
                try:
                    instance = json.loads(instance_path.read_text("utf-8"))
                    with urllib.request.urlopen(instance["url"] + "/api/health", timeout=1) as response:
                        health = json.load(response)
                    if health.get("instance") == instance["instance"]:
                        webbrowser.open(instance["url"])
                        return
                except (OSError, ValueError, KeyError):
                    time.sleep(0.25)
            ctypes.windll.user32.MessageBoxW(None, "工具正在启动或退出，请稍后再试。", "HSD 图片编号工具", 0)
            return
    try:
        from werkzeug.serving import make_server
        from .server import create_app
        app = create_app(data)
        server = make_server("127.0.0.1", args.port, app, threaded=True)
        app.config["HSD_SHUTDOWN"] = server.shutdown
        url = f"http://127.0.0.1:{server.server_port}"
        instance_path.write_text(json.dumps({"url": url, "instance": app.config["HSD_INSTANCE"], "pid": os.getpid()}), "utf-8")
        if sys.stdout:
            print(url, flush=True)
        logging.info("Started %s", url)
        if not args.no_browser:
            webbrowser.open(url)
        try:
            server.serve_forever()
        finally:
            server.server_close()
            app.config["HSD_MANAGER"].close()
            instance_path.unlink(missing_ok=True)
    except Exception:
        logging.exception("Startup failed")
        if os.name == "nt" and not args.no_browser:
            ctypes.windll.user32.MessageBoxW(None, f"启动失败，请查看：{data / '运行日志.log'}", "HSD 图片编号工具", 16)
        raise
    finally:
        if mutex:
            kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            kernel.CloseHandle.restype = wintypes.BOOL
            kernel.CloseHandle(mutex)


if __name__ == "__main__":
    main()
