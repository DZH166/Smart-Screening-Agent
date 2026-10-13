"""Include bundled third-party notices in the portable application."""
from importlib import metadata
from pathlib import Path
import shutil
import sys

destination = Path(sys.argv[1]) / "第三方组件说明"
destination.mkdir(parents=True, exist_ok=True)
components = ["Flask", "Werkzeug", "Jinja2", "MarkupSafe", "itsdangerous", "click", "blinker",
              "PyMuPDF", "opencv-python-headless", "numpy", "Pillow", "pyinstaller"]
lines = ["HSD 图号助手使用的第三方组件", ""]
for name in components:
    dist = metadata.distribution(name)
    license_name = dist.metadata.get("License-Expression") or dist.metadata.get("License") or "参见组件许可证"
    if len(license_name) > 200:
        license_name = "参见组件许可证"
    lines.extend([f"{name} {dist.version}", f"许可证：{license_name}"])
    urls = dist.metadata.get_all("Project-URL") or [dist.metadata.get("Home-page", "")]
    lines.extend(url for url in urls if url)
    for item in dist.files or []:
        if any(word in item.name.lower() for word in ["license", "copying", "notice"]):
            src = Path(dist.locate_file(item))
            if src.is_file():
                target = destination / name / str(item)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src, target)
    lines.append("")
(destination / "组件列表.txt").write_text("\n".join(lines), "utf-8-sig")
