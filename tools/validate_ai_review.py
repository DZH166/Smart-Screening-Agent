r"""Measure labelled live AI observations; activation is always explicit.

Usage (PowerShell)::

    .venv\Scripts\python tools\validate_ai_review.py --labels labels.json \
        --observations observations.json --output validation-report.json

Only after reviewing the measured report, add --activate --data-dir <tool data
directory> to sign/store that same validation record.  This tool does not make
API calls and never reads an API key.  Business image paths and filenames are
unnecessary: the manifest binds image/candidate content with case fingerprints.
Synthetic known-truth batches must say synthetic_known_truth; an existing
regression answer map must say reference_map and cannot qualify a heldout batch.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from hsd_tool.ai_policy import build_validation_record


def main(argv=None):
    parser = argparse.ArgumentParser(description="独立验证真实 DeepSeek 图片复核记录；默认不会启用自动通过。")
    parser.add_argument("--labels", required=True, type=Path, help="独立标签 JSON")
    parser.add_argument("--observations", required=True, type=Path, help="真实接口响应 JSON")
    parser.add_argument("--output", required=True, type=Path, help="本机验证报告 JSON（不提交 Git）")
    parser.add_argument("--activate", action="store_true", help="验证达标后显式签名激活相应场景")
    parser.add_argument("--data-dir", type=Path, help="当前工具的数据目录，仅 --activate 时必填")
    args = parser.parse_args(argv)
    if args.activate and not args.data_dir:
        parser.error("--activate 需要 --data-dir，不能自动猜测员工正在使用的数据目录。")
    if args.output.resolve() in {args.labels.resolve(), args.observations.resolve()}:
        parser.error("输出报告不能覆盖标签或真实响应。")
    try:
        labels = json.loads(args.labels.read_text("utf-8"))
        observations = json.loads(args.observations.read_text("utf-8"))
        record = build_validation_record(observations, labels)
        activated = False
        if args.activate:
            # The local registry, not a JSON field or UI payload, supplies the
            # trusted flag after its integrity-checked persisted signature.
            from hsd_tool.ai_registry import ValidationRegistry
            registry = ValidationRegistry(args.data_dir)
            result = registry.activate(observations, labels)
            if not result.get("qualified"):
                raise ValueError("验证记录未能通过本机完整性校验，自动通过未激活。")
            activated = True
        report = {"status": "activated" if activated else "validated_not_activated",
                  "validation": record,
                  "note": "独立测试范围见 origins/counts；不是通用准确率。"}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), "utf-8")
        print(json.dumps({"status": report["status"], "categories": record["categories"],
                          "counts": record["counts"], "output": str(args.output.resolve())},
                         ensure_ascii=False))
        return 0
    except (OSError, ValueError, TypeError, ImportError) as exc:
        print(f"验证未激活：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
