from pathlib import Path
import hashlib
import json
from types import SimpleNamespace

import pytest

from tools.validate_matching_generalization import assess_match, load_matching, run_dataset, verify_dataset


def frozen_case(tmp_path, *, forbidden=False):
    root = tmp_path / "dataset"
    source = root / "inputs" / "opaque" / "source"
    source.mkdir(parents=True)
    (source / "9c07.ai").write_bytes(b"frozen original bytes")
    query = source.parent / "query.png"
    query.write_bytes(b"frozen query bytes")
    labels = {"rows": [{"case_id": "opaque", "row_id": "query",
                       "auto_forbidden": forbidden,
                       "expected_files": [] if forbidden else ["9c07.ai"]}]}
    (root / "labels.json").write_text(json.dumps(labels), encoding="utf-8")
    sha256 = {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in [source / "9c07.ai", query, root / "labels.json"]}
    manifest = {"schema": "hsd-matching-generalization-1", "frozen_at": "2026-10-15T00:00:00Z",
                "labels": "labels.json", "sha256": sha256,
                "cases": [{"id": "opaque", "family": "not_for_matcher", "batch_id": "holdout",
                           "control": "not_for_matcher", "source": "inputs/opaque/source",
                           "rows": [{"id": "query", "image": "inputs/opaque/query.png"}]}]}
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return root


def test_negative_and_wrong_identity_auto_are_counted_as_false():
    files = {"one": {"relative_path": "a.ai"}, "two": {"relative_path": "b.ai"}}
    match = {"status": "auto", "file_id": "one"}
    assert assess_match(match, files, {"auto_forbidden": True})["false_auto"]
    assert assess_match(match, files, {"expected_files": ["b.ai"]})["false_auto"]
    assert assess_match(match, files, {"expected_files": ["a.ai"]})["correct_positive_auto"]
    assert not assess_match({"status": "review"}, files, {"auto_forbidden": True})["false_auto"]


@pytest.mark.parametrize("relative", ["labels.json", "inputs/opaque/query.png", "inputs/opaque/source/9c07.ai"])
def test_changed_frozen_evidence_invalidates_dataset(tmp_path, relative):
    root = frozen_case(tmp_path)
    (root / relative).write_bytes(b"changed")
    with pytest.raises(ValueError, match="Frozen input has changed"):
        verify_dataset(root)


def test_unhashed_source_cannot_enter_matching(tmp_path):
    root = frozen_case(tmp_path)
    (root / "inputs/opaque/source/new.ai").write_bytes(b"unplanned")
    with pytest.raises(ValueError, match="Unhashed source"):
        verify_dataset(root)


def test_runner_passes_only_production_row_data_and_counts_errors(tmp_path, monkeypatch):
    root = frozen_case(tmp_path)
    implementation = tmp_path / "hsd_tool" / "matching.py"
    implementation.parent.mkdir()
    implementation.write_text("# fixed implementation", encoding="utf-8")
    calls = []

    def scan(source, rows, work):
        calls.append(rows)
        assert set(rows[0]) == {"id", "row_number", "number", "issue", "image_path"}
        assert rows[0]["id"] == "query"
        return {"files": [{"id": "f1", "relative_path": "9c07.ai"}],
                "matches": [{"row_id": "query", "status": "auto", "file_id": "f1"}]}

    monkeypatch.setattr("tools.validate_matching_generalization.load_matching",
                        lambda _: (SimpleNamespace(scan_and_match=scan), implementation))
    result = run_dataset(root, tmp_path, tmp_path / "output.json")
    assert len(calls) == 1
    assert result["summary"]["auto"] == result["summary"]["correct_positive_auto"] == 1
    assert result["summary"]["false_auto"] == result["summary"]["errors"] == 0
    assert result["scope"] == "frozen_synthetic_controls_not_independent_business_accuracy"


def test_failed_cases_remain_in_complete_denominator(tmp_path, monkeypatch):
    root = frozen_case(tmp_path)
    implementation = tmp_path / "hsd_tool" / "matching.py"
    implementation.parent.mkdir()
    implementation.write_text("# fixed", encoding="utf-8")

    def fail(*args):
        raise RuntimeError("controlled failure")

    monkeypatch.setattr("tools.validate_matching_generalization.load_matching",
                        lambda _: (SimpleNamespace(scan_and_match=fail), implementation))
    result = run_dataset(root, tmp_path, tmp_path / "output.json")
    assert result["rows"] == result["cases"] == result["summary"]["errors"] == 1
    assert result["summary"]["case_errors"] == 1
    assert "controlled failure" in result["results"][0]["error"]


def test_label_overwrite_is_rejected_before_matching(tmp_path):
    root = frozen_case(tmp_path)
    with pytest.raises(ValueError, match="overwrite frozen evidence"):
        run_dataset(root, tmp_path, root / "labels.json")


def test_relative_imports_are_isolated_between_code_roots(tmp_path):
    roots = [tmp_path / "old", tmp_path / "new"]
    for root, token in zip(roots, ["old-helper", "new-helper"]):
        package = root / "hsd_tool"
        package.mkdir(parents=True)
        (package / "matching_verification.py").write_text(f"TOKEN = {token!r}\n", encoding="utf-8")
        (package / "matching.py").write_text(
            "from .matching_verification import TOKEN\ndef value(): return TOKEN\n", encoding="utf-8")
    old, _ = load_matching(roots[0])
    new, _ = load_matching(roots[1])
    assert old.value() == "old-helper"
    assert new.value() == "new-helper"
    assert old.__package__ != new.__package__
    assert not old.__package__.startswith("hsd_tool")
    assert load_matching(roots[0])[0].value() == "old-helper"


@pytest.mark.parametrize("mutation", ["change", "add", "remove"])
def test_helper_mutation_during_validation_invalidates_result(tmp_path, monkeypatch, mutation):
    root = frozen_case(tmp_path)
    package = tmp_path / "hsd_tool"
    package.mkdir()
    implementation = package / "matching.py"
    implementation.write_text("# fixed matching", encoding="utf-8")
    helper = package / "matching_verification.py"
    if mutation != "add":
        helper.write_text("TOKEN = 1\n", encoding="utf-8")

    def scan(*args):
        if mutation == "remove":
            helper.unlink()
        else:
            helper.write_text("TOKEN = 2\n", encoding="utf-8")
        return {"files": [], "matches": [{"row_id": "query", "status": "review"}]}

    monkeypatch.setattr("tools.validate_matching_generalization.load_matching",
                        lambda _: (SimpleNamespace(scan_and_match=scan), implementation))
    output = tmp_path / "invalid.json"
    with pytest.raises(ValueError, match="Implementation changed during validation"):
        run_dataset(root, tmp_path, output)
    assert not output.exists()
