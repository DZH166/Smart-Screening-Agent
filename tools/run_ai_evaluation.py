"""Run auditable, synthetic known-truth DeepSeek visual holdouts.

Example (makes real, potentially billable calls):
  python tools/run_ai_evaluation.py --synthetic --out tmp/ai-evaluation/run1 \
      --settings-dir <local-application-data-directory>

Use --prepare-only to check fixture/eligibility generation without any API call.
Credentials are read exclusively from AiSettings; no CLI key option exists.
Synthetic success never activates an automatic-acceptance profile.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from io import BytesIO
import json
from pathlib import Path
import random
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PIL import Image, ImageDraw, ImageOps
import pymupdf

from hsd_tool.ai_client import DeepSeekClient, ReviewError
from hsd_tool.ai_images import prepare_content
from hsd_tool.ai_policy import CHECKS, POLICY_VERSION, PROMPT_VERSION, build_validation_record, select_review_case
from hsd_tool.ai_settings import AiSettings
from hsd_tool.ai_usage import UsageLedger, empty_usage, merge_usage

SEEDS = (25783, 918271)


def _json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), "utf-8")
    temporary.replace(path)


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _pattern(seed):
    """Seeded repeated artwork, independent of production samples/matcher tests."""
    generator = random.Random(seed)
    background = tuple(generator.randrange(224, 245) for _ in range(3))
    palette = [tuple(generator.randrange(25, 195) for _ in range(3)) for _ in range(4)]
    image = Image.new("RGB", (1024, 256), background)
    drawing = ImageDraw.Draw(image)
    for y in (8, 25, 223, 241):
        drawing.rectangle((0, y, 1023, y + 5), fill=palette[(y // 8) % 4])
    phase = generator.randrange(10, 35)
    for index, x in enumerate(range(phase - 64, 1088, 128)):
        color = palette[index % 4]
        drawing.line((x - 45, 128, x + 54, 128), fill=palette[(index + 1) % 4], width=9)
        for dx, dy in ((-24, -28), (24, -28), (-24, 28), (24, 28)):
            drawing.ellipse((x + dx - 21, 128 + dy - 21, x + dx + 21, 128 + dy + 21), fill=color)
        drawing.ellipse((x - 13, 115, x + 13, 141), fill=palette[(index + 2) % 4])
        drawing.polygon(((x + 48, 65), (x + 63, 80), (x + 48, 95), (x + 33, 80)), fill=palette[3])
        drawing.polygon(((x + 48, 162), (x + 63, 177), (x + 48, 192), (x + 33, 177)), fill=palette[1])
    return image


def _pdf_ai(image, path):
    stream = BytesIO()
    image.save(stream, "PNG")
    with pymupdf.open() as document:
        page = document.new_page(width=image.width, height=image.height)
        page.insert_image(page.rect, stream=stream.getvalue())
        document.set_metadata({"title": "Synthetic known-truth visual review artwork",
                               "subject": "Generated holdout; not a business sample"})
        document.save(path, garbage=4, deflate=True)


def _ambiguous_pair(base):
    """Two distinct originals collapse to the exact same smaller query.

    Every differing 2x2 cell has the same average RGB in both originals. BOX
    reduction therefore erases the only identifying region; no unique source
    can be inferred from the query. Assert this instead of guessing ambiguity.
    """
    first, second = base.copy(), base.copy()
    for y in range(112, 144, 2):
        for x in range(480, 512, 2):
            for dy in (0, 1):
                for dx in (0, 1):
                    color = (10, 10, 10) if dx == dy else (246, 246, 246)
                    opposite = (246, 246, 246) if dx == dy else (10, 10, 10)
                    first.putpixel((x + dx, y + dy), color)
                    second.putpixel((x + dx, y + dy), opposite)
    query = first.resize((512, 128), Image.Resampling.BOX)
    assert query.tobytes() == second.resize((512, 128), Image.Resampling.BOX).tobytes()
    assert first.tobytes() != second.tobytes()
    return query, first, second


def _definitions(seed):
    base = _pattern(seed)
    reduced = base.resize((768, 192), Image.Resampling.LANCZOS)
    different_color = Image.merge("RGB", (base.getchannel("B"), base.getchannel("R"), base.getchannel("G")))
    replacement = base.copy()
    ImageDraw.Draw(replacement).rectangle((430, 55, 585, 205), fill=(105, 105, 105), outline=(25, 25, 25), width=4)
    extra = Image.new("RGB", (1024, 336), "white")
    extra.paste(base, (0, 0))
    ImageDraw.Draw(extra).polygon(((370, 270), (654, 270), (512, 326)), fill=(240, 30, 25))
    subset = _pattern(seed + 103)
    subset.paste(base.crop((0, 0, 256, 256)), (0, 0))
    uncertain, near_first, near_second = _ambiguous_pair(base)
    return [
        ("scaled", reduced, [base], "same", "f0001", []),
        ("white_margin", ImageOps.expand(reduced, border=(24, 16, 24, 16), fill="white"),
         [base], "same", "f0001", []),
        ("color_change", base, [different_color], "different", None, ["color_change"]),
        ("local_replacement", base, [replacement], "different", None, ["local_replacement"]),
        ("extra_content", base, [extra], "different", None, ["extra_content"]),
        ("shared_subset", base, [subset], "different", None, ["shared_subset"]),
        ("near_duplicate", uncertain, [near_first, near_second], "uncertain", None, ["near_duplicate"]),
    ]


def prepare_cases(directory, run_id):
    records, labels = [], []
    for batch_index, seed in enumerate(SEEDS, 1):
        batch = f"synthetic-holdout-{batch_index}-seed-{seed}"
        for name, query, candidates, label, expected, controls in _definitions(seed):
            identity = f"{run_id}-{batch_index}-{name}"
            folder = directory / "fixtures" / f"batch-{batch_index}" / name
            folder.mkdir(parents=True, exist_ok=False)
            query_path = folder / "query.png"
            query.save(query_path)
            files = []
            for index, picture in enumerate(candidates, 1):
                candidate_id = f"f{index:04d}"
                preview, original = folder / f"{candidate_id}.png", folder / f"{candidate_id}.ai"
                picture.save(preview)
                _pdf_ai(picture, original)
                with pymupdf.open(original) as document:
                    page_count = len(document)
                files.append({"id": candidate_id, "preview_path": str(preview), "source_path": str(original),
                              "source_sha256": _sha(original), "page_count": page_count, "issue": ""})
            row = {"id": "r2", "status": "review", "image_path": str(query_path), "issue": "",
                   "reason": "请复核完整图案、颜色和候选唯一性。",
                   "candidates": [{"file_id": file["id"], "score": .88 - index * .01}
                                  for index, file in enumerate(files)],
                   "evidence": {"method": "texture"}}
            case = select_review_case(row, [row], files)
            # Eligibility is an independent safety step, never a label filter.
            category = case.get("category", "texture_review")
            candidates = case.get("candidate_ids") or [file["id"] for file in files]
            labels.append({"case_id": identity, "batch_id": batch, "split": "holdout",
                           "label": label, "expected_candidate_id": expected,
                           "candidate_ids": candidates, "category": category,
                           "case_fingerprint": case.get("fingerprint"),
                           "origin": "synthetic_known_truth", "controls": controls})
            records.append({"case_id": identity, "row": row, "files": files, "case": case})
    return records, {"schema_version": 1, "cases": labels}


def _model_positive(case, decision):
    return (isinstance(decision, dict) and decision.get("verdict") == "same"
            and decision.get("candidate_id") in case.get("candidate_ids", [])
            and isinstance(decision.get("checks"), dict)
            and set(decision["checks"]) == set(CHECKS)
            and all(decision["checks"][key] is True for key in CHECKS)
            and decision.get("differences") == [])


def _summary(observations, labels, elapsed):
    lookup = {item["case_id"]: item for item in labels["cases"]}
    cases, usage = [], empty_usage()
    for observation in observations["cases"]:
        label = lookup[observation["case_id"]]
        positive = _model_positive(observation.get("case", {}), observation.get("decision"))
        false = positive and (label["label"] != "same" or
                              observation["decision"].get("candidate_id") != label["expected_candidate_id"])
        merge_usage(usage, observation.get("usage") or {})
        cases.append({"case_id": label["case_id"], "batch_id": label["batch_id"],
                      "label": label["label"], "controls": label["controls"],
                      "status": observation.get("status"),
                      "model_verdict": (observation.get("decision") or {}).get("verdict"),
                      "model_candidate_id": (observation.get("decision") or {}).get("candidate_id"),
                      "strict_model_positive": positive, "false_accept": bool(false),
                      "elapsed_seconds": observation.get("elapsed_seconds", 0),
                      "error": observation.get("error")})
    try:
        build_validation_record(observations, labels)
        qualification = {"qualified": False, "activated": False,
                         "reason": "此工具只评估，不激活任何自动通过资格。"}
    except ValueError as error:
        qualification = {"qualified": False, "activated": False, "reason": str(error)}
    return {"schema_version": 1, "run_id": observations["run_id"],
            "source": observations["source"], "origin": "synthetic_known_truth",
            "scope": "两批程序生成的已知真值留出案例；不是独立人工标注的业务批次，不代表通用准确率。",
            "planned_cases": len(cases), "completed_cases": sum(case["status"] == "completed" for case in cases),
            "failed_cases": sum(case["status"] == "failed" for case in cases),
            "not_called_cases": sum(case["status"] == "not_called" for case in cases),
            "eligibility_skips": sum(case["status"] == "ineligible" for case in cases),
            "strict_positive_decisions": sum(case["strict_model_positive"] for case in cases),
            "production_auto_accepted": 0,
            "metric_definition": "false_accepts 统计模型严格宣称同图但违背已知真值的案例；本验证工具不改变生产匹配状态。",
            "accepted_correct_positives": sum(case["strict_model_positive"] and not case["false_accept"]
                                              and case["label"] == "same" for case in cases),
            "false_accepts": sum(case["false_accept"] for case in cases),
            "elapsed_seconds": round(elapsed, 3), "usage": usage,
            "qualification": qualification, "cases": cases}


def run(directory, settings_directory, *, prepare_only=False, client_factory=DeepSeekClient):
    directory = Path(directory).resolve()
    if directory.is_relative_to(ROOT) and directory.relative_to(ROOT).parts[:1] != ("tmp",):
        raise ValueError("仓库内验证产物必须保存到已忽略的 tmp 目录。")
    if directory.exists() and any(directory.iterdir()):
        raise ValueError("输出目录必须为空，避免覆盖上一轮标签与真实调用记录。")
    directory.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    run_id = "synthetic-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    records, labels = prepare_cases(directory, run_id)
    _json(directory / "labels.json", labels)  # Freeze truth before any API call.
    observations = {"schema_version": 1, "source": "deepseek_live" if client_factory is DeepSeekClient else "mock_test", "run_id": run_id,
                    "policy_version": POLICY_VERSION, "prompt_version": PROMPT_VERSION,
                    "planned_case_ids": [record["case_id"] for record in records], "cases": []}
    for record in records:
        case = record["case"]
        observations["cases"].append({
            "case_id": record["case_id"], "case_fingerprint": case.get("fingerprint"),
            "model": None, "request_id": None, "decision": None, "usage": empty_usage(),
            "case": {key: case.get(key) for key in ("category", "candidate_ids", "image_digests")},
            "status": "not_called", "elapsed_seconds": 0,
            "error": {"code": "not_started", "message": "本轮计划已冻结，此案例尚未调用。"}})
    _json(directory / "observations.json", observations)
    settings = AiSettings(settings_directory)
    private = settings.runtime()
    client, ledger = None, None
    circuit_reason = None
    if not prepare_only:
        if not private.get("enabled") or not private.get("api_key"):
            circuit_reason = {"code": "not_configured", "message": "未启用或未配置本机 DeepSeek 密钥，本轮未调用。"}
        else:
            client = client_factory(private["api_key"])
            ledger = UsageLedger(settings_directory)
    consecutive_failures = 0
    for position, record in enumerate(records):
        case = record["case"]
        observation = observations["cases"][position]
        if not case.get("eligible"):
            observation.update(status="ineligible", error={"code": case.get("reason_code"), "message": case.get("reason")})
        elif prepare_only:
            observation["error"] = {"code": "prepare_only", "message": "仅生成与检查案例，未调用接口。"}
        elif circuit_reason:
            observation["error"] = dict(circuit_reason)
        else:
            case_started = time.perf_counter()
            try:
                content = prepare_content(case, record["row"], record["files"])
                result = client.review(content)
                observation.update({key: result[key] for key in ("model", "request_id", "decision", "usage")})
                observation["status"] = "completed"
                observation.pop("error", None)
                consecutive_failures = 0
            except ReviewError as error:
                observation.update(status="failed", error={"code": error.code, "message": error.message}, usage=error.usage)
                consecutive_failures += 1
                if error.code in {"authentication", "insufficient_balance", "redirect_blocked", "not_configured"}:
                    circuit_reason = {"code": "circuit_open", "message": "接口配置或权限异常，本轮其余案例未调用。"}
            except Exception:
                observation.update(status="failed", error={"code": "local_error", "message": "本机复核准备异常，已停止后续调用。"})
                circuit_reason = {"code": "circuit_open", "message": "本机处理异常，本轮其余案例未调用。"}
            observation["elapsed_seconds"] = round(time.perf_counter() - case_started, 3)
            if ledger is not None:
                ledger.add(observation["usage"])
                if ledger.snapshot().get("warning"):
                    circuit_reason = {"code": "usage_not_persisted", "message": "用量无法持久保存，本轮其余案例未调用。"}
            if consecutive_failures >= 2:
                circuit_reason = {"code": "circuit_open", "message": "连续两项复核失败，本轮其余案例未调用。"}
        _json(directory / "observations.json", observations)
        print(f"{position + 1}/{len(records)} {record['case_id']} {observation['status']}", flush=True)
    summary = _summary(observations, labels, time.perf_counter() - started)
    summary["prepare_only"] = prepare_only
    _json(directory / "summary.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--synthetic", action="store_true", required=True,
                        help="仅使用程序生成的两批已知真值案例，不读取业务样本")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--settings-dir", type=Path, required=True,
                        help="工具本机设置目录；密钥只通过 AiSettings 读取")
    parser.add_argument("--prepare-only", action="store_true", help="仅生成案例，不调用接口、不产生费用")
    options = parser.parse_args()
    try:
        summary = run(options.out, options.settings_dir, prepare_only=options.prepare_only)
    except (ValueError, OSError):
        print("验证准备失败：请检查输出目录是否为空及本机文件权限。未显示凭据或远端响应。", file=sys.stderr)
        return 2
    print(json.dumps({key: summary[key] for key in ("planned_cases", "completed_cases", "failed_cases",
          "not_called_cases", "eligibility_skips", "strict_positive_decisions", "false_accepts", "usage", "qualification")},
          ensure_ascii=False, indent=2))
    return 0 if options.prepare_only or summary["completed_cases"] == summary["planned_cases"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
