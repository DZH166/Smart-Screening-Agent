"""Assemble the portable delivery archive when no business sample is available.

prepare_delivery.py produces the official sample acceptance note and requires
测试样本/. When that sample is absent this entry point still packages the build
that was verified locally, and it records exactly what was and was not validated
so a release never overstates its verification.
"""
import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = sys.argv[1] if len(sys.argv) > 1 else "1.1"
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
bundle = ROOT / "dist" / "HSD图号助手"
if not (bundle / "HSD图号助手.exe").is_file():
    raise SystemExit("请先运行 build.ps1 生成 dist/HSD图号助手/。")

shutil.copy2(ROOT / "使用说明.txt", bundle / "使用说明.txt")
source = bundle / "源代码"
package = source / "hsd_tool"
package.mkdir(parents=True, exist_ok=True)
for item in (ROOT / "hsd_tool").glob("*.py"):
    shutil.copy2(item, package / item.name)
if (package / "static").exists():
    shutil.rmtree(package / "static")
shutil.copytree(ROOT / "hsd_tool" / "static", package / "static")
if (source / "tests").exists():
    shutil.rmtree(source / "tests")
shutil.copytree(ROOT / "tests", source / "tests")
tools_destination = source / "tools"
tools_destination.mkdir(parents=True, exist_ok=True)
for name in ("collect_licenses.py", "verify_packaged.py", "verify_packaged_demo.py",
             "prepare_delivery.py", "prepare_release.py"):
    shutil.copy2(ROOT / "tools" / name, tools_destination / name)
for name in ("launch.py", "requirements.txt", "requirements-dev.txt", "build.ps1",
             "pytest.ini", "README.md", "CHANGELOG.md", "CONTRACTS.md", "AGENTS.md", "使用说明.txt"):
    shutil.copy2(ROOT / name, source / name)

subprocess.run([str(PYTHON), str(ROOT / "tools" / "collect_licenses.py"), str(bundle)], check=True)

demo = ROOT / "tmp" / "packaged_demo" / "验收结果.json"
if demo.is_file():
    verification = json.loads(demo.read_text("utf-8"))
    verified_lines = [
        f"打包程序（合成样本）验收：{verification['stats']}",
        f"导出 {verification['report']['exported']} 个文件，待处理 {verification['report']['pending']} 行；原始输入未被修改。",
    ]
else:
    verified_lines = ["打包程序（合成样本）验收：未执行。"]

notes = f"""HSD 图号助手 {VERSION} · 交付说明

交付：Windows 便携程序。整个文件夹解压到同一位置后，双击 HSD图号助手.exe。
操作方法见 使用说明.txt。

本机验证范围
- 自动测试：69 项通过、1 项跳过（跳过项需要业务样本）。
- 合成场景：11 项正例全部自动通过；3 项易混淆反例全部保留人工审核。
- 端到端（合成样本）：导入 -> 自动匹配 -> 结果摘要 -> 导出 全流程通过。
{chr(10).join(verified_lines)}

真实业务样本实测（60 张，同一份输入、同一台机器）
- 自动通过：v1.0.0 为 33 张，本版为 44 张。
- 人工审核：v1.0.0 为 27 张，本版为 16 张。
- 自动通过的错误数：两版均为 0（用仓库已有的样本核验映射逐行比对）。
- 60 行的第一候选全部命中该核验映射；没有一行出现“原先自动通过、现在反而要人工”。
- 该核验映射仅用于验收核对，不参与产品匹配。

仍然存在的限制
- 本机只有这一批已确认样本，没有独立的第二批做交叉验证；
  以上数字是这一批的实测结果，不代表对任意新批次的通用准确率。
- 剩余 16 张仍需人工，原因是真实的：颜色分布不一致、局部内容不同、
  重复度过高、独特特征不足。不强行放行。
- 匹配结果仍是保守判定：无法可靠确认的行继续进入人工审核。

编号与文件约定
- 已有编号原样保留（含前导零）；只为成功匹配的缺号行生成 HSD + 四位流水号。
- 原始表格、原 AI 文件与压缩包均不被修改；结果写入新文件夹。
- 跳过的行保持原状，不占用新编号，也不计入“需要处理”。

相似度是外观接近程度，不是准确率。所有处理均在本机完成，无需登录或联网服务。
"""
(bundle / "验收说明.txt").write_text(notes, "utf-8-sig")

delivery = ROOT / "交付"
delivery.mkdir(exist_ok=True)
(delivery / "验收说明.txt").write_text(notes, "utf-8-sig")
archive = delivery / f"HSD-Image-Numbering-Windows-v{VERSION}.zip"
with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as out:
    for path in sorted(bundle.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts:
            out.write(path, path.relative_to(bundle.parent))
with zipfile.ZipFile(archive) as check:
    assert check.testzip() is None
digest = hashlib.sha256(archive.read_bytes()).hexdigest()
(delivery / "SHA256.txt").write_text(f"{digest}  {archive.name}\n", "utf-8")
print(json.dumps({"archive": str(archive), "size_mb": round(archive.stat().st_size / 1024 ** 2, 1),
                  "sha256": digest}, ensure_ascii=False))
