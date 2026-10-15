"""Fail-closed eligibility and independently measured gates for AI review.

This module never calls a model, renames a file, or upgrades a row's state.  A
model's confidence is deliberately not an acceptance signal.  The service must
also recheck ownership and source integrity before applying/exporting a result.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path

from PIL import Image, ImageOps

POLICY_VERSION = "hsd-ai-review-1"
PROMPT_VERSION = "hsd-ai-review-1"
CHECKS = ("content_same", "colors_same", "complete_coverage",
          "extra_content_absent", "unique_candidate")
CATEGORIES = frozenset({"geometry_review", "texture_review"})
NEGATIVE_CONTROLS = frozenset({"color_change", "local_replacement", "extra_content",
                               "shared_subset", "near_duplicate"})
MAX_PIXELS = 40_000_000


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()


def _case_fingerprint(category, images):
    return _digest({"policy_version": POLICY_VERSION, "prompt_version": PROMPT_VERSION,
                    "category": category, "images": images})


def _sha256_string(value):
    return (isinstance(value, str) and len(value) == 64
            and all(c in "0123456789abcdef" for c in value))


def _native_resolution_verified(geometry):
    """Mirror ai_images' overview/panel bounds; never trust a model checkbox.

    A full overview or the complete, nonoverlapping panel set must preserve
    native pixel resolution.  Larger images may still receive suggestions but
    cannot be automatically accepted under this protocol.
    """
    if not isinstance(geometry, dict):
        return False
    width, height = geometry.get("width"), geometry.get("height")
    if (type(width) is not int or type(height) is not int or min(width, height) < 8
            or width * height > MAX_PIXELS):
        return False
    if width <= 2048 and height <= 1536:
        return True
    if width > height * 3:
        count = min(5, max(2, math.ceil(width / max(600, height * 3))))
        return math.ceil(width / count) <= 1600 and height <= 1200
    return False


def _complete_native_resolution(digests):
    geometry = digests.get("geometry") if isinstance(digests, dict) else None
    return (isinstance(geometry, dict) and _native_resolution_verified(geometry.get("query"))
            and isinstance(geometry.get("candidates"), list)
            and len(geometry["candidates"]) == len(digests.get("candidates", []))
            and all(isinstance(shape, dict) and shape.get("candidate_id") == image.get("candidate_id")
                    and _native_resolution_verified(shape)
                    for image, shape in zip(digests["candidates"], geometry["candidates"])))


def _local_evidence(row):
    source = row.get("evidence") or row.get("diagnostics") or {}
    if not isinstance(source, dict):
        return {"method": "unknown", "valid": False}
    result = {"method": source.get("method", "unknown"), "valid": True}
    for name in ("colour", "pixel_rms", "changed", "major_changed", "worst", "residual", "mae"):
        value = source.get(name)
        if value is None:
            result[name] = None
        elif type(value) in (int, float) and math.isfinite(value) and value >= 0:
            result[name] = float(value)
        else:
            result["valid"] = False
    limits = source.get("thresholds", {})
    result["thresholds"] = {key: float(value) for key, value in limits.items()
                            if key in {"rms", "changed", "major_changed", "worst", "colour", "residual"}
                            and type(value) in (int, float) and math.isfinite(value) and value >= 0} if isinstance(limits, dict) else {}
    return result


def _local_evidence_consistent(evidence):
    """Do not let model checkboxes override measured colour/content differences.

    These are the existing matcher's bounds, with feature and texture metrics
    kept separate.  Low keypoint count/coverage alone is not a contradiction.
    An absent measurement is not silently converted to a zero-error result.
    """
    if not isinstance(evidence, dict) or evidence.get("valid") is not True:
        return False
    method = evidence.get("method")
    if not isinstance(method, str) or method not in {"features", "texture"}:
        return False
    thresholds = evidence.get("thresholds", {})
    if not isinstance(thresholds, dict):
        return False
    if method == "texture":
        required = ("colour", "pixel_rms", "changed", "major_changed", "worst", "residual")
        limits = {"colour": ("colour", .25), "pixel_rms": ("rms", .045),
                  "changed": ("changed", .015), "major_changed": ("major_changed", .003),
                  "worst": ("worst", .55), "residual": ("residual", .08)}
    else:
        required = ("colour", "mae", "major_changed", "changed")
        # _evidence.thresholds is texture-oriented even for a features result;
        # use _features' actual .015 major-change and .08 changed-area bounds.
        limits = {"colour": ("colour", .25), "mae": (None, .045),
                  "changed": (None, .08), "major_changed": (None, .015),
                  "residual": ("residual", .08)}
    # Low-detail geometry may be independently resolved by a model, but missing
    # colour/content measurements cannot be invented by affirmative checkboxes.
    if any(type(evidence.get(name)) not in (int, float)
           or not math.isfinite(evidence[name]) or evidence[name] < 0 for name in required):
        return False
    for name, (threshold_name, maximum) in limits.items():
        value = evidence.get(name)
        provided = thresholds.get(threshold_name) if threshold_name is not None else None
        limit = min(provided, maximum) if type(provided) in (int, float) and math.isfinite(provided) and provided >= 0 else maximum
        if value is not None and (type(value) not in (int, float) or not math.isfinite(value) or value > limit):
            return False
    return True


def _image_record(path, cache):
    path = Path(path)
    stat = path.stat()
    key = (str(path.resolve()), stat.st_size, stat.st_mtime_ns)
    if key in cache:
        return cache[key]
    with Image.open(path) as opened:
        if min(opened.size) < 8 or opened.width * opened.height > MAX_PIXELS:
            raise ValueError("图片尺寸不适合可靠复核")
        picture = ImageOps.exif_transpose(opened).convert("RGBA")
        background = Image.new("RGBA", picture.size, "white")
        background.alpha_composite(picture)
        rgb = background.convert("RGB")
        pixel_digest = hashlib.sha256(str(rgb.size).encode("ascii") + rgb.tobytes()).hexdigest()
    result = {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
              "pixel_sha256": pixel_digest, "width": rgb.width, "height": rgb.height}
    cache[key] = result
    return result


def _score(candidate):
    score = candidate.get("score")
    return float(score) if (not isinstance(score, bool) and isinstance(score, (int, float))
                            and math.isfinite(score) and 0 <= score <= 1) else -1.0


def _refusal(code, reason):
    return {"eligible": False, "reason_code": code, "reason": reason,
            "candidate_ids": [], "fingerprint": None,
            "policy_version": POLICY_VERSION, "prompt_version": PROMPT_VERSION}


def select_review_case(row, rows, files, image_cache=None):
    """Build an internal, content-bound case, excluding hard identity anomalies.

    Paths are only transport inputs for the local client.  Filenames, row
    numbers, directory order and sample answer maps are absent from evidence.
    The optional cache belongs to one immutable job; it must not be reused for
    a different import.  Returned paths must not be sent as prompt text.
    """
    cache = image_cache if image_cache is not None else {}
    if row.get("status", row.get("_status")) != "review":
        return _refusal("not_review", "此项不需要模型复核。")
    if row.get("issue") or not row.get("image_path"):
        return _refusal("query_unreadable", "表格图片无法读取，仍需人工处理。")
    code = row.get("reason_code", row.get("_reason_code", "")) or ""
    if any(word in code for word in ("conflict", "number", "overflow", "ownership")):
        return _refusal("hard_conflict", "文件归属或编号异常，不能由模型放行。")
    ranking = row.get("candidates") or []
    if not ranking or _score(ranking[0]) < .55:
        return _refusal("no_trusted_candidate", "没有可信候选，仍需人工处理。")
    selected = ranking[:5]
    identities = [candidate.get("file_id") for candidate in selected]
    if (any(not isinstance(identity, str) or not identity for identity in identities)
            or len(set(identities)) != len(identities) or any(_score(c) < 0 for c in selected)):
        return _refusal("invalid_candidates", "候选记录不完整，仍需人工处理。")
    lookup = {file.get("id"): file for file in files}
    if len(lookup) != len(files) or any(identity not in lookup for identity in identities):
        return _refusal("invalid_candidates", "候选原文件记录不完整，仍需人工处理。")
    try:
        query = _image_record(row["image_path"], cache)
    except (OSError, ValueError, Image.DecompressionBombError):
        return _refusal("query_unreadable", "表格图片无法读取，仍需人工处理。")
    # Exact duplicate previews anywhere in the import invalidate source identity,
    # including a duplicate just outside the five displayed candidates.
    duplicates = Counter()
    previews = {}
    for file in files:
        if file.get("preview_path"):
            try:
                previews[file["id"]] = _image_record(file["preview_path"], cache)
                duplicates[previews[file["id"]]["pixel_sha256"]] += 1
            except (OSError, ValueError, Image.DecompressionBombError):
                pass
    images = []
    for candidate in selected:
        file = lookup[candidate["file_id"]]
        page_count = file.get("page_count")
        if (file.get("issue") or isinstance(page_count, bool) or page_count != 1
                or file["id"] not in previews):
            return _refusal("candidate_anomaly", "候选预览异常或含多个画板，仍需人工确认。")
        source_digest = file.get("source_sha256")
        if (not isinstance(source_digest, str) or len(source_digest) != 64
                or any(c not in "0123456789abcdef" for c in source_digest)
                or not file.get("source_path") or not Path(file["source_path"]).is_file()):
            return _refusal("source_unverified", "候选原文件尚未完整验证，仍需人工确认。")
        preview = previews[file["id"]]
        if duplicates[preview["pixel_sha256"]] > 1:
            return _refusal("duplicate_previews", "不同文件有相同预览，无法确定唯一原文件。")
        images.append({"candidate_id": file["id"], "image_path": file["preview_path"],
                       "preview_sha256": preview["sha256"], "source_sha256": source_digest})
    top = identities[0]
    for other in rows:
        if other.get("id") == row.get("id"):
            continue
        if other.get("image_path") and not other.get("issue"):
            try:
                if _image_record(other["image_path"], cache)["pixel_sha256"] == query["pixel_sha256"]:
                    return _refusal("duplicate_queries", "多行包含相同图片，需先确认文件归属。")
            except (OSError, ValueError, Image.DecompressionBombError):
                pass
        other_status = other.get("status", other.get("_status"))
        owned = other.get("file_id") or other.get("_file_id")
        # Only the proposed top file would be eligible for AI acceptance.  An
        # already-owned alternative must remain visible for visual comparison,
        # but its ownership does not create a claim against this row's top.
        if other_status in {"auto", "confirmed"} and owned == top:
            return _refusal("ownership_conflict", "第一候选已归属其他图片，需人工确认。")
        competing = other.get("candidates") or []
        # A weak incidental candidate is not itself an ownership claim.  A close
        # credible competing top choice is, even if neither row is yet accepted.
        if (competing and competing[0].get("file_id") == top
                and _score(competing[0]) >= max(.75, _score(selected[0]) - .12)):
            return _refusal("ownership_conflict", "多行对同一原文件存在实际竞争，需人工确认。")
    method = (row.get("evidence") or row.get("diagnostics") or {}).get("method")
    category = "texture_review" if method == "texture" else "geometry_review"
    digests = {"query": query["sha256"],
               "candidates": [{k: item[k] for k in ("candidate_id", "preview_sha256", "source_sha256")}
                              for item in images],
               "geometry": {"query": {"width": query["width"], "height": query["height"]},
                            "candidates": [{"candidate_id": identity,
                                            "width": previews[identity]["width"],
                                            "height": previews[identity]["height"]}
                                           for identity in identities]},
               "local_evidence": _local_evidence(row)}
    fingerprint = _case_fingerprint(category, digests)
    return {"eligible": True, "reason_code": "eligible", "reason": "可进行图片二次复核。",
            "category": category, "candidate_ids": identities, "fingerprint": fingerprint,
            "policy_version": POLICY_VERSION, "prompt_version": PROMPT_VERSION,
            "image_digests": digests,
            "images": {"query_path": row["image_path"], "candidates": images}}


def _positive_decision(case, decision):
    return (isinstance(decision, dict) and decision.get("verdict") == "same"
            and decision.get("candidate_id") in case.get("candidate_ids", [])
            and isinstance(decision.get("checks"), dict)
            and set(decision["checks"]) == set(CHECKS)
            and all(decision["checks"][key] is True for key in CHECKS)
            and decision.get("differences") == [])


def evaluate_suggestion(case, decision, validation):
    """Accept only a strictly positive suggestion covered by trusted validation.

    ``decision`` is the local envelope containing the model response, not text
    supplied by the model: {model, case_fingerprint, decision:{...}}.  The
    registry adds ``trusted`` only after verifying the stored local signature.
    """
    def reject(code, reason):
        return {"accepted": False, "reason_code": code, "reason": reason}
    if not case.get("eligible"):
        return reject(case.get("reason_code", "ineligible"), case.get("reason", "需人工确认。"))
    if (not isinstance(decision, dict) or decision.get("case_fingerprint") != case.get("fingerprint")):
        return reject("stale_case", "复核内容已变化，仍需人工确认。")
    if not isinstance(validation, dict) or validation.get("trusted") is not True:
        return reject("validation_required", "模型结果尚未通过独立验证，仅供人工参考。")
    if (validation.get("policy_version") != POLICY_VERSION
            or validation.get("prompt_version") != PROMPT_VERSION
            or validation.get("model") != decision.get("model")
            or not isinstance(decision.get("model"), str) or not decision["model"]
            or case.get("category") not in validation.get("categories", [])
            or "independent_manual" not in validation.get("approved_origins", [])):
        return reject("validation_mismatch", "当前模型或复核场景未通过相应验证，仅供人工参考。")
    if not _complete_native_resolution(case.get("image_digests")):
        return reject("resolution_not_validated", "图片仍需缩小才能展示，关键细节尚未充分验证，需人工确认。")
    if not _positive_decision(case, decision.get("decision")):
        return reject("model_uncertain", "模型未完整确认图案、颜色、覆盖及唯一性，仍需人工确认。")
    if decision["decision"]["candidate_id"] != case["candidate_ids"][0]:
        return reject("candidate_change_requires_review", "模型建议改选候选，仍需员工确认。")
    if not _local_evidence_consistent((case.get("image_digests") or {}).get("local_evidence")):
        return reject("local_evidence_conflict", "本地图案或颜色证据仍有差异，模型建议不能直接放行。")
    return {"accepted": True, "reason_code": "ai_validated_identity",
            "reason": "已验证的模型复核确认图案、颜色、完整内容及唯一候选。"}


def build_validation_record(observations, labels):
    """Evaluate live, independently labelled holdouts without manufacturing data.

    This is an activation prerequisite, not an accuracy estimate.  Reference-map
    regressions are reported but cannot qualify a category.  Each approved
    category needs two independently labelled holdout batches, including a
    separately manually checked real business batch, useful positive decisions,
    every specified hard negative control, and zero false accepts.  Synthetic
    known-truth batches alone cannot qualify real business cases.
    The caller must sign/store the result before the service can trust it.
    """
    if (not isinstance(observations, dict) or not isinstance(labels, dict)
            or observations.get("schema_version") != 1 or labels.get("schema_version") != 1
            or observations.get("source") != "deepseek_live"
            or observations.get("policy_version") != POLICY_VERSION
            or observations.get("prompt_version") != PROMPT_VERSION):
        raise ValueError("验证必须使用当前协议的真实 DeepSeek 调用记录。")
    labelled = labels.get("cases")
    observed = observations.get("cases")
    if not isinstance(labelled, list) or not labelled or not isinstance(observed, list):
        raise ValueError("验证数据为空或格式不正确。")
    label_by_id = {item.get("case_id"): item for item in labelled if isinstance(item, dict)}
    observation_by_id = {item.get("case_id"): item for item in observed if isinstance(item, dict)}
    if (len(label_by_id) != len(labelled) or len(observation_by_id) != len(observed)
            or not all(isinstance(key, str) and key for key in label_by_id)
            or set(label_by_id) != set(observation_by_id)):
        raise ValueError("标签与真实调用必须按唯一 case_id 完整对应，不能遗漏失败案例。")
    planned = observations.get("planned_case_ids")
    if (not isinstance(planned, list) or len(planned) != len(observed)
            or not all(isinstance(value, str) and value for value in planned)
            or len(set(planned)) != len(planned) or set(planned) != set(observation_by_id)):
        raise ValueError("验证记录必须保留本轮计划的全部案例，不能跳过失败项或挑选有利结果。")
    fingerprints = set()
    request_ids = set()
    query_batches = defaultdict(set)
    models = set()
    category_cases = defaultdict(list)
    rows = []
    for identity, label in label_by_id.items():
        observation = observation_by_id[identity]
        fingerprint = label.get("case_fingerprint")
        if (not _sha256_string(fingerprint)
                or observation.get("case_fingerprint") != fingerprint or fingerprint in fingerprints):
            raise ValueError("验证图片指纹缺失、重复或不一致，不能把同一案例用于多个数据分组。")
        fingerprints.add(fingerprint)
        if (not isinstance(observation.get("request_id"), str) or not observation["request_id"].strip()
                or observation["request_id"] in request_ids or observation.get("error")
                or observation.get("source", "deepseek_live") != "deepseek_live"):
            raise ValueError("存在未完成的真实接口调用，不能激活自动通过。")
        request_ids.add(observation["request_id"])
        model = observation.get("model")
        if not isinstance(model, str) or not model:
            raise ValueError("真实接口记录缺少实际模型版本。")
        models.add(model)
        category, split, origin = label.get("category"), label.get("split"), label.get("origin")
        if (not isinstance(category, str) or category not in CATEGORIES
                or not isinstance(split, str) or split not in {"calibration", "holdout"}
                or not isinstance(origin, str)
                or origin not in {"independent_manual", "synthetic_known_truth", "reference_map"}
                or label.get("label") not in {"same", "different", "uncertain"}
                or not isinstance(label.get("batch_id"), str) or not label["batch_id"]
                or not isinstance(label.get("controls"), list)
                or not all(isinstance(value, str) for value in label["controls"])):
            raise ValueError("标签需明确独立批次、分组、标签来源及反例种类。")
        candidates = label.get("candidate_ids")
        if (not isinstance(candidates, list) or not candidates
                or not all(isinstance(value, str) and value for value in candidates)
                or len(set(candidates)) != len(candidates)):
            raise ValueError("验证标签必须绑定实际提供给模型的候选集合。")
        bound_case = observation.get("case")
        digests = bound_case.get("image_digests") if isinstance(bound_case, dict) else None
        bound_candidates = digests.get("candidates") if isinstance(digests, dict) else None
        if (not isinstance(bound_case, dict) or bound_case.get("category") != category
                or bound_case.get("candidate_ids") != candidates or not isinstance(digests, dict)
                or not _sha256_string(digests.get("query")) or not isinstance(bound_candidates, list)
                or len(bound_candidates) != len(candidates)
                or any(not isinstance(item, dict) or item.get("candidate_id") != candidate
                       or not _sha256_string(item.get("preview_sha256"))
                       or not _sha256_string(item.get("source_sha256"))
                       for candidate, item in zip(candidates, bound_candidates))
                or _case_fingerprint(category, digests) != fingerprint):
            raise ValueError("真实调用记录需绑定实际图片、候选及源文件指纹，不能只按案例名称关联。")
        query_batches[digests["query"]].add(label["batch_id"])
        if not _complete_native_resolution(digests):
            raise ValueError("验证图片的完整细节无法按原像素展示，不能据此激活自动通过。")
        expected = label.get("expected_candidate_id")
        if ((label["label"] == "same" and expected not in candidates)
                or (label["label"] != "same" and expected is not None)):
            raise ValueError("正例需指定唯一正确候选，反例或不确定项不能指定正确候选。")
        decision = observation.get("decision")
        if (not isinstance(decision, dict) or decision.get("verdict") not in {"same", "different", "uncertain"}
                or not isinstance(decision.get("checks"), dict)
                or set(decision["checks"]) != set(CHECKS)
                or any(type(decision["checks"][key]) is not bool for key in CHECKS)
                or not isinstance(decision.get("differences"), list)
                or not all(isinstance(value, str) for value in decision["differences"])):
            raise ValueError("真实模型响应不完整，不能激活自动通过。")
        accepted = (_positive_decision({"candidate_ids": candidates}, decision)
                    and decision.get("candidate_id") == candidates[0]
                    and _local_evidence_consistent(digests.get("local_evidence")))
        false_accept = accepted and (label["label"] != "same" or decision["candidate_id"] != expected)
        record = {"case_id": identity, "category": category, "batch_id": label["batch_id"],
                  "split": split, "origin": origin, "label": label["label"],
                  "accepted": bool(accepted), "false_accept": bool(false_accept),
                  "controls": label["controls"], "case_fingerprint": fingerprint}
        rows.append(record)
        category_cases[category].append(record)
    if len(models) != 1:
        raise ValueError("验证结果混用了模型版本，必须分别验证。")
    if any(len(batches) > 1 for batches in query_batches.values()):
        raise ValueError("同一张查询图片不能被计入多个独立批次。")
    # A batch cannot be calibration and heldout at the same time.
    batch_splits = defaultdict(set)
    for record in rows:
        batch_splits[record["batch_id"]].add(record["split"])
    if any(len(splits) > 1 for splits in batch_splits.values()):
        raise ValueError("同一批次不能同时用于调试和独立验证。")
    approved, counts = [], {}
    for category, group in category_cases.items():
        holdout = [row for row in group if row["split"] == "holdout" and row["origin"] != "reference_map"]
        batches = sorted({row["batch_id"] for row in holdout})
        positives = sum(row["label"] == "same" for row in holdout)
        useful = sum(row["label"] == "same" and row["accepted"] and not row["false_accept"] for row in holdout)
        negative = [row for row in holdout if row["label"] != "same"]
        controls = {value for row in negative for value in row["controls"]}
        false = sum(row["false_accept"] for row in group)
        # Each independently heldout batch must test both a genuine match and a
        # nonmatch/uncertainty, rather than declaring separate all-positive data.
        balanced_batches = all(any(r["label"] == "same" for r in holdout if r["batch_id"] == batch)
                               and any(r["label"] != "same" for r in holdout if r["batch_id"] == batch)
                               and any(r["accepted"] and not r["false_accept"] and r["label"] == "same"
                                       for r in holdout if r["batch_id"] == batch)
                               for batch in batches)
        manual_batches = sorted({r["batch_id"] for r in holdout if r["origin"] == "independent_manual"})
        manual_balanced = any(any(r["origin"] == "independent_manual" and r["label"] == "same"
                                  and r["accepted"] and not r["false_accept"]
                                  for r in holdout if r["batch_id"] == batch)
                              and any(r["origin"] == "independent_manual" and r["label"] != "same"
                                      for r in holdout if r["batch_id"] == batch)
                              for batch in manual_batches)
        passed = (len(batches) >= 2 and positives >= 2 and useful >= 2 and len(negative) >= 5
                  and NEGATIVE_CONTROLS <= controls and false == 0 and balanced_batches and manual_balanced)
        if passed:
            approved.append(category)
        counts[category] = {"total": len(group), "holdout": len(holdout), "holdout_batches": batches,
                            "positives": positives, "accepted_positives": useful,
                            "negative_controls": len(negative), "control_types": sorted(controls),
                            "false_accepts": false, "approved": passed,
                            "independent_manual_batches": manual_batches,
                            "origins": sorted({r["origin"] for r in group})}
    if not approved:
        raise ValueError("独立验证尚未达标：需两个独立留出批次（含人工独立核验的真实业务批次）、完整正反例覆盖、有效正例和零错误自动通过。")
    return {"schema_version": 1, "model": next(iter(models)),
            "policy_version": POLICY_VERSION, "prompt_version": PROMPT_VERSION,
            "categories": sorted(approved), "counts": counts,
            "dataset_fingerprints": {"labels": _digest(labels), "observations": _digest(observations)},
            "case_fingerprints": sorted(fingerprints),
            "approved_origins": sorted({r["origin"] for r in rows if r["category"] in approved
                                         and r["split"] == "holdout" and r["origin"] != "reference_map"}),
            "validation_scope": "仅验证所列场景和批次，不代表通用准确率。",
            "origins": sorted({row["origin"] for row in rows})}
