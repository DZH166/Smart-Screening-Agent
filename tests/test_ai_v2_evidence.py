"""Content-bound all-file competition and complete-coverage acceptance gates."""
import copy
import hashlib
from pathlib import Path

from PIL import Image
import pytest

from hsd_tool.ai_policy import evaluate_suggestion, select_review_case
from test_ai_policy import make_job, competition_for, positive, trusted, measured_evidence


def verdict(case, decision=None, validation=None):
    return evaluate_suggestion(case, {"model": "revision-verified", "case_fingerprint": case["fingerprint"],
                                     "decision": positive() if decision is None else decision},
                               trusted() if validation is None else validation)


def test_only_actual_competitors_are_sent_but_all_preview_bytes_are_bound(tmp_path):
    row, rows, files = make_job(tmp_path)
    row["candidates"][1]["score"] = .14
    row["evidence"]["competition"] = competition_for(row, files)
    before = select_review_case(row, rows, files)
    assert before["candidate_ids"] == ["f0001"]
    assert len(before["image_digests"]["comparison_inputs"]) == 3
    assert verdict(before)["accepted"]
    Image.new("RGB", (240, 60), "orange").save(files[2]["preview_path"])
    after = select_review_case(row, rows, files)
    assert after["candidate_ids"] == ["f0001"] and after["fingerprint"] != before["fingerprint"]
    files[2]["source_sha256"] = hashlib.sha256(b"a different source").hexdigest()
    assert select_review_case(row, rows, files)["fingerprint"] != after["fingerprint"]


def test_score_gap_uncertainty_can_be_complemented_but_incomplete_global_search_cannot(tmp_path):
    row, rows, files = make_job(tmp_path)
    assert row["evidence"]["competition"]["unique"] is False
    case = select_review_case(row, rows, files)
    assert case["candidate_ids"] == ["f0001", "f0002"] and verdict(case)["accepted"]
    row["evidence"]["competition"]["complete"] = False
    case = select_review_case(row, rows, files)
    assert case["eligible"] and not verdict(case)["accepted"]
    assert "competition_not_verified" in {item["code"] for item in verdict(case)["failed_checks"]}


def test_hidden_competitor_is_restored_from_all_file_evidence(tmp_path):
    row, rows, files = make_job(tmp_path)
    row["evidence"]["competition"]["scores"][2].update(score=.89, pattern_supported=True)
    # The UI's shorter ranking is not the authoritative candidate universe.
    case = select_review_case(row, rows, files)
    assert "f0003" in case["candidate_ids"]


def test_hard_indistinguishable_or_too_many_real_competitors_stay_manual(tmp_path):
    row, rows, files = make_job(tmp_path)
    row["evidence"]["competition"]["hard_ambiguity"] = True
    assert select_review_case(row, rows, files)["reason_code"] == "indistinguishable_candidates"
    row["evidence"]["competition"].pop("hard_ambiguity")
    for index in range(4, 8):
        preview, source = tmp_path / f"extra-{index}.png", tmp_path / f"extra-{index}.ai"
        Image.new("RGB", (240, 60), (index * 25, 40, 90)).save(preview)
        source.write_bytes(str(index).encode())
        files.append({"id": f"f{index:04}", "preview_path": str(preview), "source_path": str(source),
                      "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(), "page_count": 1})
        row["candidates"].append({"file_id": f"f{index:04}", "score": .9 - index * .001})
    row["evidence"]["competition"] = competition_for(row, files)
    assert select_review_case(row, rows, files)["reason_code"] == "too_many_competitors"


@pytest.mark.parametrize("change", [
    lambda source: source.pop("competition"),
    lambda source: source["competition"]["evaluated_file_ids"].pop(),
    lambda source: source["competition"]["scores"][0].update(pattern_supported=False),
])
def test_missing_or_incomplete_positive_identity_evidence_only_allows_suggestions(tmp_path, change):
    row, rows, files = make_job(tmp_path)
    change(row["evidence"])
    case = select_review_case(row, rows, files)
    assert case["eligible"] and not verdict(case)["accepted"]


@pytest.mark.parametrize("coverage", [{"query_coverage": .8}, {"candidate_coverage": .2, "candidate_ink_coverage": .2},
                                       {"geometry_verified": False}])
def test_model_cannot_prove_important_unobserved_regions_by_checkboxes(tmp_path, coverage):
    row, rows, files = make_job(tmp_path)
    row["evidence"]["alignment"].update(coverage)
    result = verdict(select_review_case(row, rows, files))
    assert not result["accepted"] and result["reason_code"] == "coverage_not_verified"


def test_selected_channel_and_palette_guard_cannot_be_bypassed_by_good_flat_values(tmp_path):
    row, rows, files = make_job(tmp_path)
    flat = row["evidence"]
    flat.update(evidence_version=2, selected_channel="texture", channels={
        "texture": {"metrics": {**measured_evidence(), "rms": .08,
                                "palette_applicable": True, "palette_mismatch": .02},
                    "alignment": flat["alignment"]},
        "features": {"metrics": measured_evidence("features"), "alignment": flat["alignment"]}})
    result = verdict(select_review_case(row, rows, files))
    assert not result["accepted"] and result["reason_code"] == "local_evidence_conflict"


def test_all_independent_failures_remain_explainable_when_qualification_is_missing(tmp_path):
    row, rows, files = make_job(tmp_path)
    row["evidence"]["colour"] = .6
    row["evidence"]["alignment"]["candidate_coverage"] = .1
    row["evidence"]["alignment"]["candidate_ink_coverage"] = .1
    decision = positive()
    decision.update(verdict="uncertain", protocol_diagnostics={"inconsistent": True})
    result = verdict(select_review_case(row, rows, files), decision, {"trusted": False})
    assert result["reason_code"] == "validation_required"
    assert {item["code"] for item in result["failed_checks"]} == {
        "validation_required", "model_protocol_inconsistent", "coverage_not_verified", "local_evidence_conflict"}


@pytest.mark.parametrize("metric,value", [("coherent_difference", .0005), ("coherent_difference", float("nan")),
                                          ("coherent_difference", "0"), ("global_mae", .061), ("global_changed", .121)])
def test_new_local_coherent_and_global_content_guards_survive_ai_handoff(tmp_path, metric, value):
    row, rows, files = make_job(tmp_path)
    method = "features" if metric.startswith("global") else "texture"
    flat = row["evidence"]
    metrics = {**measured_evidence(method), "coherent_difference": 0., metric: value}
    flat.update(method=method, evidence_version=2, selected_channel=method,
                channels={method: {"metrics": metrics, "alignment": flat["alignment"], "failed_checks": []}})
    result = verdict(select_review_case(row, rows, files), validation={**trusted(), "categories": ["geometry_review", "texture_review"]})
    assert not result["accepted"] and result["reason_code"] == "local_evidence_conflict"


def test_selected_channel_failed_content_flag_is_not_lost_in_scalar_projection(tmp_path):
    row, rows, files = make_job(tmp_path)
    flat = row["evidence"]
    flat.update(evidence_version=2, selected_channel="texture", channels={
        "texture": {"metrics": {**measured_evidence(), "coherent_difference": 0.},
                    "alignment": flat["alignment"], "failed_checks": ["foreground_colours"]}})
    case = select_review_case(row, rows, files)
    assert case["image_digests"]["local_evidence"]["channel_failed_checks"] == ["foreground_colours"]
    assert not verdict(case)["accepted"]
