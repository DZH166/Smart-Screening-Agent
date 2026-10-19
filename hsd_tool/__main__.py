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
    parser.add_argument("--settings-dir", type=Path, help="复用主机的 DeepSeek 加密设置与用量目录")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--lan", help="显式开启局域网测试，例：192.168.0.160/24")
    parser.add_argument("--lan-code", help="局域网上传访问码，默认 HSD")
    parser.add_argument("--gateway", action="store_true", help="作为内网 AI 网关运行，Key 只保存在本机")
    parser.add_argument("--gateway-bind", help="网关监听的本机内网 IPv4 地址")
    parser.add_argument("--lan-input-root", type=Path, help="允许远程测试使用的主机素材目录")
    parser.add_argument("--lan-output-root", type=Path, help="允许远程测试导出的主机结果目录")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--self-check", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.pick:
        native_picker(args.pick, args.result)
        return
    if args.gateway:
        from .gateway import default_bind, run_gateway, valid_bind
        try:
            bind = valid_bind(args.gateway_bind) if args.gateway_bind else default_bind()
        except ValueError as exc:
            parser.error(str(exc))
        gateway_data = Path(args.data_dir) if args.data_dir else (
            Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "HSD图片编号工具-网关")
        gateway_data.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(filename=str(gateway_data / "运行日志.log"), level=logging.INFO,
                            format="%(asctime)s %(levelname)s %(message)s", encoding="utf-8")
        try:
            run_gateway(gateway_data, bind=bind, port=args.port or 8899,
                        open_browser=not args.no_browser)
        except Exception:
            logging.exception("Gateway failed")
            if os.name == "nt":
                ctypes.windll.user32.MessageBoxW(
                    None, f"网关启动失败，请查看：{gateway_data / '运行日志.log'}", "智筛 Agent 内网网关", 16)
            raise
        return
    lan = None
    if args.lan:
        if not args.lan_input_root or not args.lan_output_root:
            parser.error("局域网测试需要指定 --lan-input-root 和 --lan-output-root。")
        from .lan import LanAccess
        try:
            lan = LanAccess(args.lan, args.lan_input_root, args.lan_output_root, code=args.lan_code)
        except ValueError as exc:
            parser.error(str(exc))
    elif args.lan_input_root or args.lan_output_root:
        parser.error("指定局域网目录时还需要 --lan。")
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
                    if bool(lan) != bool(instance.get("lan")):
                        parser.error("工具已在另一种访问模式运行，请先在主机保存结果并正常退出。")
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
        app = create_app(data, lan=lan, settings_dir=args.settings_dir)
        server = make_server(lan.host if lan else "127.0.0.1", args.port, app, threaded=True)
        app.config["HSD_PORT"] = server.server_port
        app.config["HSD_SHUTDOWN"] = server.shutdown
        url = f"http://{lan.host if lan else '127.0.0.1'}:{server.server_port}"
        instance = {"url": url, "instance": app.config["HSD_INSTANCE"], "pid": os.getpid(), "lan": bool(lan)}
        if lan:
            instance.update(lan_access_code=lan.code, lan_network=str(lan.network))
        instance_path.write_text(json.dumps(instance), "utf-8")
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
