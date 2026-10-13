"""Collect verified release notes and a portable archive after acceptance."""
from pathlib import Path
import hashlib
import json
import shutil
import zipfile

root = Path(__file__).resolve().parents[1]
bundle = root / "dist" / "HSD图号助手"
delivery = root / "交付"
delivery.mkdir(exist_ok=True)
result = json.loads((root / "tmp" / "packaged_validation" / "验收结果.json").read_text("utf-8"))
assert result["original_input_hashes_unchanged"]
assert result["only_target_worksheet_part_changed"]
assert result["report"]["new_numbers"] == 2
stats = result["initial_stats"]
notes = f"""HSD 图号助手 1.0 · 样本验收说明
验收日期：2026-10-13

交付：Windows 便携程序，全部文件解压到同一文件夹后双击 HSD图号助手.exe。
操作方法见 使用说明.txt。

自动测试：56 项通过。
打包运行验证：Windows exe 已启动；图片处理组件和原生文件选择依赖初始化成功。
真实样本：60 行图片、60 个 AI 文件；{stats['auto']} 自动通过、{stats['review']} 待人工复核、{stats['unmatched']} 无候选。
60 个首选候选与人工视觉核对记录一致，仅说明当前样本结果，不代表后续批次准确率。

缺号及导出验收：
在表格副本中清空 2 个编号，验证待复核行暂不占号。
确认第一个候选后，按表格顺序生成 HSD0001、HSD0002，其余已有编号原样保留。
成功导出 {result['report']['exported']} 个 AI 文件，剩余 {result['report']['pending']} 行保留原状并列入待处理。
每个导出 AI 的 SHA256 与对应原稿一致；只改变文件名。
输出表格只改变目标工作表内的目标编号；其他工作簿部件原字节保留。
原始 Excel 和 ZIP 的 SHA256 在验收前后一致。

第一版边界：
固定表格模板；含 PDF 兼容预览的 AI；相似图案需员工确认。
仅规避当前表格中的已用号，跨批次起始号由员工核对。
所有处理均在本机完成，无需登录或联网服务。
"""
(bundle / "验收说明.txt").write_text(notes, "utf-8-sig")
(delivery / "验收说明.txt").write_text(notes, "utf-8-sig")
shutil.copy2(root / "tools" / "verify_packaged.py", bundle / "源代码" / "tools" / "verify_packaged.py")
archive = delivery / "HSD图号助手_Windows_1.0.zip"
with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as out:
    for path in sorted(bundle.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts:
            out.write(path, path.relative_to(bundle.parent))
with zipfile.ZipFile(archive) as check:
    assert check.testzip() is None
digest = hashlib.sha256(archive.read_bytes()).hexdigest()
(delivery / "SHA256.txt").write_text(f"{digest}  {archive.name}\n", "utf-8")
print(json.dumps({"archive": str(archive), "size_mb": round(archive.stat().st_size / 1024**2, 1), "sha256": digest}, ensure_ascii=False))
