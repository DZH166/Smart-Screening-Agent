import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from PIL import Image, PngImagePlugin
import pytest

from hsd_tool.ai_policy import (CHECKS, POLICY_VERSION, PROMPT_VERSION, _case_fingerprint,
                                build_validation_record, evaluate_suggestion,
                                select_review_case)


def measured_evidence(method="texture"):
    if method == "features":
        return {"method": method, "colour": .01, "mae": .01,
                "changed": .01, "major_changed": .001}
    return {"method": method, "colour": .01, "pixel_rms": .01,
            "changed": .001, "major_changed": .0001, "worst": .1, "residual": .01}


def competition_for(row, files):
    ranked = {item["file_id"]: item["score"] for item in row["candidates"]}
    credible = [item["file_id"] for item in row["candidates"] if item["score"] >= .55]
    return {"version": "local-competition-1", "complete": True, "unique": len(credible) == 1,
            "evaluated_file_ids": [file["id"] for file in files], "credible_candidate_ids": credible,
            "scores": [{"file_id": file["id"], "score": ranked.get(file["id"], .1),
                        "pattern_supported": file["id"] in credible} for file in files]}


def alignment_for(row, files):
    with Image.open(row["image_path"]) as query:
        query_size = list(query.size)
    with Image.open(files[0]["preview_path"]) as candidate:
        candidate_size = list(candidate.size)
    matrix = [[query_size[0] / candidate_size[0], 0., 0.], [0., query_size[1] / candidate_size[1], 0.]]
    # Artificial fixture: exact full-frame scale correspondence, never a live
    # qualification or a replacement for the matcher's measured coverage.
    return {"kind": "affine", "direction": "candidate_to_query", "query_size": query_size,
            "candidate_size": candidate_size, "matrix": matrix, "matrices": [matrix],
            "geometry_verified": True, "query_coverage": 1., "candidate_coverage": 1.,
            "candidate_ink_coverage": 1., "unverified_query": 0., "unverified_candidate": 0.}


def make_job(tmp_path):
    files = []
    for index, color in enumerate(("red", "blue", "green"), 1):
        preview = tmp_path / f"preview-{index}.png"
        Image.new("RGB", (240, 60), color).save(preview)
        source = tmp_path / f"original-{index}.ai"
        source.write_bytes(f"verified source {index}".encode())
        files.append({"id": f"f{index:04}", "preview_path": str(preview),
                      "source_path": str(source), "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                      "page_count": 1, "issue": None})
    query = tmp_path / "query.png"
    Image.new("RGB", (480, 120), "red").save(query)
    row = {"id": "r2", "status": "review", "image_path": str(query), "issue": None,
           "candidates": [{"file_id": "f0001", "score": .91}, {"file_id": "f0002", "score": .65}],
           "evidence": measured_evidence()}
    row["evidence"]["competition"] = competition_for(row, files)
    row["evidence"]["alignment"] = alignment_for(row, files)
    return row, [row], files


def positive(candidate="f0001"):
    return {"verdict": "same", "candidate_id": candidate, "reason": "完整图案及颜色一致。",
            "checks": {key: True for key in CHECKS}, "differences": []}


def trusted():
    return {"trusted": True, "policy_version": POLICY_VERSION, "prompt_version": PROMPT_VERSION,
            "model": "revision-verified", "categories": ["texture_review"],
            "approved_origins": ["independent_manual", "synthetic_known_truth"]}


def test_case_contains_competitors_and_content_only_fingerprint(tmp_path):
    row, rows, files = make_job(tmp_path)
    case = select_review_case(row, rows, files)
    assert case["eligible"]
    assert case["candidate_ids"] == ["f0001", "f0002"]
    assert len(case["images"]["candidates"]) == 2
    assert len(case["fingerprint"]) == 64
    files[0]["name"] = "answer says wrong file.ai"
    row["row_number"] = 999
    row["number"] = "HSD9999"
    assert select_review_case(row, rows, files)["fingerprint"] == case["fingerprint"]
    Image.new("RGB", (240, 60), "orange").save(files[0]["preview_path"])
    assert select_review_case(row, rows, files)["fingerprint"] != case["fingerprint"]


@pytest.mark.parametrize("status", ["auto", "confirmed", "unmatched", "skipped"])
def test_only_review_rows_are_eligible(tmp_path, status):
    row, rows, files = make_job(tmp_path)
    row["status"] = status
    assert select_review_case(row, rows, files)["reason_code"] == "not_review"


@pytest.mark.parametrize("mutation,code", [
    (lambda row, files: row.update(issue="missing"), "query_unreadable"),
    (lambda row, files: row.update(image_path="nonexistent"), "query_unreadable"),
    (lambda row, files: row["candidates"][0].update(score=.54), "no_trusted_candidate"),
    (lambda row, files: row["candidates"][0].update(score=float("nan")), "no_trusted_candidate"),
    (lambda row, files: row.update(reason_code="ownership_or_number_conflict"), "hard_conflict"),
    (lambda row, files: files[0].update(page_count=2), "candidate_anomaly"),
    (lambda row, files: files[0].update(page_count=True), "candidate_anomaly"),
    (lambda row, files: files[0].update(issue="damaged"), "candidate_anomaly"),
    (lambda row, files: files[0].update(source_sha256=None), "source_unverified"),
    (lambda row, files: files[0].update(source_path="missing.ai"), "source_unverified"),
])
def test_hard_anomalies_never_reach_ai_acceptance(tmp_path, mutation, code):
    row, rows, files = make_job(tmp_path)
    mutation(row, files)
    case = select_review_case(row, rows, files)
    assert not case["eligible"]
    assert case["reason_code"] == code
    assert not evaluate_suggestion(case, {}, trusted())["accepted"]


def test_corrupt_candidate_preview_is_not_eligible(tmp_path):
    row, rows, files = make_job(tmp_path)
    Path(files[0]["preview_path"]).write_bytes(b"not an image")
    assert select_review_case(row, rows, files)["reason_code"] == "candidate_anomaly"


def test_duplicate_pixels_with_different_png_metadata_block_even_outside_top_five(tmp_path):
    row, rows, files = make_job(tmp_path)
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("untrusted", "a different file, same picture")
    Image.new("RGB", (240, 60), "red").save(files[2]["preview_path"], pnginfo=metadata)
    assert select_review_case(row, rows, files)["reason_code"] == "duplicate_previews"


def test_duplicate_rows_and_true_competitors_are_blocked_but_weak_score_is_not(tmp_path):
    row, rows, files = make_job(tmp_path)
    other = {"id": "r3", "status": "review", "candidates": [{"file_id": "f0001", "score": .56}]}
    rows.append(other)
    assert select_review_case(row, rows, files)["eligible"]
    other["candidates"][0]["score"] = .88
    assert select_review_case(row, rows, files)["reason_code"] == "ownership_conflict"
    other["candidates"][0]["score"] = .56
    other.update(status="auto", file_id="f0001")
    assert select_review_case(row, rows, files)["reason_code"] == "ownership_conflict"
    other.update(status="skipped", file_id=None, image_path=row["image_path"])
    assert select_review_case(row, rows, files)["reason_code"] == "duplicate_queries"


@pytest.mark.parametrize("owner_status", ["auto", "confirmed"])
@pytest.mark.parametrize("alternative_score", [.56, .90])
def test_owned_lower_rank_candidate_stays_visible_without_blocking_independent_top(tmp_path, owner_status, alternative_score):
    row, rows, files = make_job(tmp_path)
    row["candidates"][1]["score"] = alternative_score
    rows.append({"id": "r3", "status": owner_status, "file_id": "f0002",
                 "candidates": [{"file_id": "f0002", "score": .99}]})
    case = select_review_case(row, rows, files)
    assert case["eligible"]
    assert case["candidate_ids"] == ["f0001", "f0002"]
    assert [image["candidate_id"] for image in case["images"]["candidates"]] == ["f0001", "f0002"]
    envelope = {"model": "revision-verified", "case_fingerprint": case["fingerprint"], "decision": positive("f0002")}
    verdict = evaluate_suggestion(case, envelope, trusted())
    assert not verdict["accepted"] and verdict["reason_code"] == "candidate_change_requires_review"


@pytest.mark.parametrize("owner_status", ["auto", "confirmed"])
def test_owned_top_remains_a_hard_identity_conflict(tmp_path, owner_status):
    row, rows, files = make_job(tmp_path)
    rows.append({"id": "r3", "status": owner_status, "file_id": "f0001", "candidates": []})
    assert select_review_case(row, rows, files)["reason_code"] == "ownership_conflict"


def test_validated_positive_only_accepts_with_matching_server_envelope(tmp_path):
    row, rows, files = make_job(tmp_path)
    case = select_review_case(row, rows, files)
    envelope = {"model": "revision-verified", "case_fingerprint": case["fingerprint"], "decision": positive()}
    assert evaluate_suggestion(case, envelope, trusted())["accepted"]
    assert not evaluate_suggestion(case, envelope, None)["accepted"]
    assert not evaluate_suggestion(case, envelope, {**trusted(), "trusted": False})["accepted"]
    for key, value in (("model", "different-revision"), ("policy_version", "old"),
                       ("prompt_version", "old"), ("categories", ["geometry_review"]),
                       ("approved_origins", ["synthetic_known_truth"])):
        assert not evaluate_suggestion(case, envelope, {**trusted(), key: value})["accepted"]
    envelope["case_fingerprint"] = "unrelated"
    assert evaluate_suggestion(case, envelope, trusted())["reason_code"] == "stale_case"


@pytest.mark.parametrize("method,measure,value,accepted", [
    ("texture", "colour", .251, False), ("texture", "major_changed", .004, False),
    ("texture", "residual", .081, False), ("texture", "pixel_rms", .046, False),
    ("features", "major_changed", .010, True), ("features", "major_changed", .016, False),
    ("features", "changed", .070, True), ("features", "changed", .081, False),
])
def test_local_content_and_colour_contradictions_cannot_be_overridden_by_checkboxes(tmp_path, method, measure, value, accepted):
    row, rows, files = make_job(tmp_path)
    row["evidence"] = {**measured_evidence(method), measure: value,
                       "thresholds": {"major_changed": .003, "changed": .015},
                       "competition": competition_for(row, files), "alignment": alignment_for(row, files)}
    case = select_review_case(row, rows, files)
    validation = {**trusted(), "categories": [case["category"]]}
    envelope = {"model": "revision-verified", "case_fingerprint": case["fingerprint"], "decision": positive()}
    result = evaluate_suggestion(case, envelope, validation)
    assert result["accepted"] is accepted
    if not accepted:
        assert result["reason_code"] == "local_evidence_conflict"


def test_ai_can_recommend_other_candidate_but_only_employee_may_apply_it(tmp_path):
    row, rows, files = make_job(tmp_path)
    case = select_review_case(row, rows, files)
    envelope = {"model": "revision-verified", "case_fingerprint": case["fingerprint"], "decision": positive("f0002")}
    result = evaluate_suggestion(case, envelope, trusted())
    assert not result["accepted"] and result["reason_code"] == "candidate_change_requires_review"


def test_evidence_changes_invalidate_existing_case_fingerprint(tmp_path):
    row, rows, files = make_job(tmp_path)
    old = select_review_case(row, rows, files)
    row["evidence"]["colour"] = .7
    assert select_review_case(row, rows, files)["fingerprint"] != old["fingerprint"]


@pytest.mark.parametrize("method,missing", [
    ("texture", None), ("features", None),
    *(("texture", name) for name in ("colour", "pixel_rms", "changed", "major_changed", "worst", "residual")),
    *(("features", name) for name in ("colour", "mae", "changed", "major_changed")),
])
def test_missing_colour_or_content_measurement_cannot_be_filled_by_model_checkboxes(tmp_path, method, missing):
    row, rows, files = make_job(tmp_path)
    row["evidence"] = {**measured_evidence(method), "competition": competition_for(row, files),
                       "alignment": alignment_for(row, files)}
    if missing is None:
        row["evidence"] = {"method": method, "competition": competition_for(row, files),
                           "alignment": alignment_for(row, files)}
    else:
        row["evidence"][missing] = None
    case = select_review_case(row, rows, files)
    result = evaluate_suggestion(case, {"model": "revision-verified", "case_fingerprint": case["fingerprint"],
                                       "decision": positive()},
                                  {**trusted(), "categories": [case["category"]]})
    assert not result["accepted"] and result["reason_code"] == "local_evidence_conflict"


@pytest.mark.parametrize("mutation", [
    lambda decision: decision.update(verdict="uncertain", confidence=1),
    lambda decision: decision.update(verdict="different"),
    lambda decision: decision.update(candidate_id="not-supplied"),
    lambda decision: decision.update(differences=["extra orange dot"]),
    lambda decision: decision["checks"].update(complete_coverage=False),
    lambda decision: decision["checks"].update(colors_same="true"),
    lambda decision: decision["checks"].update(extra_content_absent=1),
    lambda decision: decision["checks"].pop("unique_candidate"),
])
def test_confidence_cannot_replace_complete_evidence(tmp_path, mutation):
    row, rows, files = make_job(tmp_path)
    case = select_review_case(row, rows, files)
    decision = positive()
    mutation(decision)
    envelope = {"model": "revision-verified", "case_fingerprint": case["fingerprint"], "decision": decision}
    assert not evaluate_suggestion(case, envelope, trusted())["accepted"]


def validation_data():
    from hsd_tool.ai_registry import ValidationRegistry
    labels, observations = [], []
    # Independent known-truth batches have distinct image fingerprints.  This is
    # a unit-test manifest, never a stored production activation or API response.
    controls = ["color_change", "local_replacement", "extra_content", "shared_subset", "near_duplicate"]
    for index, control in enumerate([None, *controls, None, *controls]):
        identity = f"case-{index}"
        same = control is None
        digests = {"query": hashlib.sha256(identity.encode()).hexdigest(),
                   "candidates": [{"candidate_id": f"f{j:04}",
                                   "preview_sha256": hashlib.sha256(f"{identity}-preview-{j}".encode()).hexdigest(),
                                   "source_sha256": hashlib.sha256(f"{identity}-source-{j}".encode()).hexdigest()}
                                  for j in range(1, 3)],
                   "geometry": {"query": {"width": 480, "height": 120},
                                "candidates": [{"candidate_id": f"f{j:04}", "width": 240, "height": 60}
                                               for j in range(1, 3)]},
                   "local_evidence": {**measured_evidence(), "valid": True, "thresholds": {}},
                   "competition_evidence": {"version": "local-competition-1", "complete": True, "unique": False,
                       "evaluated_file_ids": ["f0001", "f0002"], "credible_candidate_ids": ["f0001", "f0002"],
                       "scores": [{"file_id": "f0001", "score": .9, "pattern_supported": True},
                                  {"file_id": "f0002", "score": .65, "pattern_supported": True}]}}
        digests["comparison_inputs"] = copy.deepcopy(digests["candidates"])
        digests["alignment_evidence"] = {"kind": "affine", "direction": "candidate_to_query",
            "query_size": [480, 120], "candidate_size": [240, 60], "matrices": [[[2., 0., 0.], [0., 2., 0.]]],
            "geometry_verified": True, "query_coverage": 1., "candidate_coverage": 1., "candidate_ink_coverage": 1.}
        fingerprint = _case_fingerprint("texture_review", digests)
        labels.append({"case_id": identity, "batch_id": f"independent-{index // 6}",
                       "split": "holdout", "label": "same" if same else "different",
                       "expected_candidate_id": "f0001" if same else None,
                       "candidate_ids": ["f0001", "f0002"], "category": "texture_review",
                       "case_fingerprint": fingerprint,
                       "origin": "synthetic_known_truth" if index < 6 else "independent_manual",
                       "controls": [control] if control else []})
        decision = positive() if same else {**positive(), "verdict": "different", "candidate_id": None,
                                          "differences": [control]}
        observations.append({"case_id": identity, "case_fingerprint": fingerprint,
                             "model": "revision-verified", "request_id": f"actual-request-{index}",
                             "case": {"category": "texture_review", "candidate_ids": ["f0001", "f0002"],
                                      "image_digests": digests},
                             "decision": decision})
    return ({"schema_version": 1, "cases": labels},
            {"schema_version": 1, "source": "deepseek_live", "policy_version": POLICY_VERSION,
             "prompt_version": PROMPT_VERSION, "cases": observations,
             "implementation_sha256": ValidationRegistry._implementation(),
             "planned_case_ids": [item["case_id"] for item in observations]})


def test_independent_validation_record_is_measured_and_untrusted_until_registry_signs():
    labels, observations = validation_data()
    result = build_validation_record(observations, labels)
    assert result["categories"] == ["texture_review"]
    assert result.get("trusted") is not True
    assert result["implementation_sha256"] == observations["implementation_sha256"]
    assert result["counts"]["texture_review"]["accepted_positives"] == 2
    assert result["counts"]["texture_review"]["negative_controls"] == 10
    assert result["origins"] == ["independent_manual", "synthetic_known_truth"]
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("mutation", [
    lambda obs: obs.pop("implementation_sha256"),
    lambda obs: obs.update(implementation_sha256={}),
    lambda obs: obs["implementation_sha256"].pop("matching"),
    lambda obs: obs["implementation_sha256"].update(unknown_module="0" * 64),
    lambda obs: obs["implementation_sha256"].update(ai_client="not-a-digest"),
])
def test_unsigned_or_malformed_call_implementation_cannot_be_backfilled(mutation):
    labels, observations = validation_data()
    mutation(observations)
    before = copy.deepcopy(observations)
    with pytest.raises(ValueError, match="实现签名|实现已变化"):
        build_validation_record(observations, labels)
    assert observations == before


@pytest.mark.parametrize("module", ["ai_policy", "ai_client", "ai_images", "matching", "matching_verification", "archive_io"])
def test_same_protocol_old_observations_cannot_be_reactivated_under_new_implementation(tmp_path, monkeypatch, module):
    from hsd_tool.ai_registry import ValidationRegistry
    labels, observations = validation_data()
    recorded = copy.deepcopy(observations["implementation_sha256"])
    current = {**recorded, module: "0" * 64}
    monkeypatch.setattr(ValidationRegistry, "_implementation", staticmethod(lambda: dict(current)))
    registry = ValidationRegistry(tmp_path)
    with pytest.raises(ValueError, match="实现签名|实现已变化"):
        registry.activate(observations, labels)
    assert observations["implementation_sha256"] == recorded
    assert not registry.path.exists() and not registry.secret_path.exists()


@pytest.mark.parametrize("mutation", [
    lambda labels, obs: obs.update(source="mock"),
    lambda labels, obs: obs["cases"][0].update(request_id=""),
    lambda labels, obs: obs["cases"][0].update(error="timeout"),
    lambda labels, obs: obs["cases"][0].update(model="another-model"),
    lambda labels, obs: obs["cases"][0].update(case_fingerprint="0" * 64),
    lambda labels, obs: obs["cases"].pop(),
    lambda labels, obs: obs.update(planned_case_ids=[]),
    lambda labels, obs: labels["cases"][0].update(split="calibration"),
    lambda labels, obs: [item.update(origin="reference_map") for item in labels["cases"]],
    lambda labels, obs: [item.update(origin="synthetic_known_truth") for item in labels["cases"]],
    lambda labels, obs: obs["cases"][0]["case"]["image_digests"].update(query="0" * 64),
    lambda labels, obs: obs["cases"][0].update(request_id=obs["cases"][1]["request_id"]),
    lambda labels, obs: [item.update(controls=[]) for item in labels["cases"]],
    lambda labels, obs: [item.update(batch_id="same-batch") for item in labels["cases"]],
    lambda labels, obs: obs["cases"][1].update(decision=positive()),
    lambda labels, obs: obs["cases"][0].update(decision=positive("f0002")),
    lambda labels, obs: obs["cases"][0]["decision"]["checks"].update(colors_same="true"),
])
def test_validation_cannot_be_activated_from_missing_controls_leakage_or_wrong_accepts(mutation):
    labels, observations = validation_data()
    mutation(labels, observations)
    with pytest.raises(ValueError):
        build_validation_record(observations, labels)


def test_validation_cli_defaults_to_report_without_activating(tmp_path):
    labels, observations = validation_data()
    labels_path, observations_path, report = [tmp_path / name for name in ("labels.json", "responses.json", "report.json")]
    labels_path.write_text(json.dumps(labels), "utf-8")
    observations_path.write_text(json.dumps(observations), "utf-8")
    result = subprocess.run([sys.executable, "tools/validate_ai_review.py", "--labels", str(labels_path),
                             "--observations", str(observations_path), "--output", str(report)],
                            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    saved = json.loads(report.read_text("utf-8"))
    assert saved["status"] == "validated_not_activated"
    assert saved["validation"].get("trusted") is not True
    assert not (tmp_path / "ai-validation.json").exists()
