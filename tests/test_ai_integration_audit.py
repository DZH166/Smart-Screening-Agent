"""Independent boundary checks for image transport, activation and usage.

All image inputs and responses in this file are artificial and local.  No API
key, business sample or mock record is written to a running tool's data folder.
"""
import base64
from io import BytesIO
import json
from pathlib import Path

from PIL import Image, ImageDraw, PngImagePlugin
import pytest

from hsd_tool.ai_images import prepare_content
from hsd_tool.ai_policy import (_native_resolution_verified, CHECKS, POLICY_VERSION,
                                PROMPT_VERSION, evaluate_suggestion, select_review_case)
from hsd_tool.ai_registry import ValidationRegistry
from hsd_tool.ai_usage import UsageLedger, empty_usage, merge_usage


def decode_images(content):
    return [Image.open(BytesIO(base64.b64decode(item["image_url"]["url"].split(",", 1)[1]))).convert("RGB")
            for item in content if item["type"] == "image_url"]


def test_long_strip_has_complete_overview_and_gap_free_native_panels_without_private_names(tmp_path):
    image = Image.new("RGBA", (4000, 300), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    for index, color in enumerate(("red", "green", "blue", "orange", "purple")):
        draw.rectangle((index * 800, 0, (index + 1) * 800 - 1, 149), fill=color)
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("private", "do-not-send-path-or-employee-name")
    query = tmp_path / "客户机密表格图片.png"
    candidate = tmp_path / "绝不能依赖的原文件名.png"
    image.save(query, pnginfo=metadata)
    image.save(candidate)
    content = prepare_content({"candidate_ids": ["f0001"]}, {"image_path": str(query), "reason": "需比较完整内容"},
                              [{"id": "f0001", "preview_path": str(candidate), "name": "never transmit this.ai"}])
    text = " ".join(item["text"] for item in content if item["type"] == "text")
    assert str(tmp_path) not in text and query.name not in text and candidate.name not in text
    assert "never transmit" not in text and "private" not in text
    decoded = decode_images(content)
    assert len(decoded) == 12  # query and candidate each have one full + five panels
    overview, *panels = decoded[:6]
    assert overview.size == (2048, 154)
    assert all(panel.size == (800, 300) for panel in panels)
    rebuilt = Image.new("RGB", image.size)
    offset = 0
    for panel in panels:
        rebuilt.paste(panel, (offset, 0))
        offset += panel.width
    expected = Image.new("RGB", image.size, "white")
    expected.paste(image, mask=image.getchannel("A"))
    assert rebuilt.tobytes() == expected.tobytes()
    assert rebuilt.getpixel((3999, 299)) == (255, 255, 255)


@pytest.mark.parametrize("shape,verified", [
    ((2048, 1536), True), ((4000, 300), True), ((8000, 300), True),
    ((8001, 300), False), ((600, 1537), False), ((2049, 1200), False),
    ((5, 100), False), ((True, 100), False), ((10000, 5000), False),
])
def test_complete_native_resolution_rule_matches_transport_bounds(shape, verified):
    assert _native_resolution_verified({"width": shape[0], "height": shape[1]}) is verified


def test_large_picture_still_gets_suggestion_but_cannot_be_ai_auto_from_checkboxes(tmp_path):
    row_path, preview_path, source_path = [tmp_path / name for name in ("query.png", "preview.png", "source.ai")]
    Image.new("RGB", (8001, 300), "red").save(row_path)
    Image.new("RGB", (1400, 52), "red").save(preview_path)
    source_path.write_bytes(b"independent artificial original")
    import hashlib
    row = {"id": "r2", "image_path": str(row_path), "status": "review",
           "evidence": {"method": "texture", "colour": .01, "pixel_rms": .01, "changed": .001,
                        "major_changed": .0001, "worst": .1, "residual": .01},
           "candidates": [{"file_id": "f0001", "score": .9}]}
    files = [{"id": "f0001", "preview_path": str(preview_path), "source_path": str(source_path),
              "source_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(), "page_count": 1}]
    case = select_review_case(row, [row], files)
    assert case["eligible"]
    decision = {"verdict": "same", "candidate_id": "f0001", "reason": "all checks claimed",
                "checks": {key: True for key in CHECKS}, "differences": []}
    verdict = evaluate_suggestion(case, {"model": "actual-revision", "case_fingerprint": case["fingerprint"],
                                          "decision": decision},
                                  {"trusted": True, "model": "actual-revision", "policy_version": POLICY_VERSION,
                                   "prompt_version": PROMPT_VERSION, "categories": ["texture_review"],
                                   "approved_origins": ["independent_manual"]})
    assert not verdict["accepted"] and verdict["reason_code"] == "resolution_not_validated"


def test_registry_never_accepts_unsigned_browser_shaped_activation(tmp_path):
    registry = ValidationRegistry(tmp_path)
    registry.path.write_text(json.dumps({"trusted": True, "categories": ["texture_review"],
                                         "model": "pretend-validated"}), "utf-8")
    assert registry.load() == {}
    assert registry.snapshot()["mode"] == "evaluation"
    with pytest.raises(ValueError):
        registry.activate({"trusted": True, "source": "mock"}, {"cases": []})
    assert not registry.secret_path.exists()


def test_signed_registry_detects_record_and_secret_changes(tmp_path, monkeypatch):
    import hsd_tool.ai_policy as policy
    # Isolate signature correctness: qualification rules are separately measured
    # in test_ai_policy; this stub cannot escape the pytest temporary directory.
    measured = {"model": "unit-signature-only", "policy_version": POLICY_VERSION,
                "prompt_version": PROMPT_VERSION, "categories": ["texture_review"],
                "counts": {"texture_review": {"approved": True}}, "approved_origins": ["independent_manual"]}
    monkeypatch.setattr(policy, "build_validation_record", lambda observations, labels: dict(measured))
    registry = ValidationRegistry(tmp_path)
    assert registry.activate({}, {})["qualified"]
    assert registry.load()["trusted"] is True
    signed = registry.path.read_text("utf-8")
    payload = json.loads(signed)
    payload["record"]["categories"].append("geometry_review")
    registry.path.write_text(json.dumps(payload), "utf-8")
    assert registry.load() == {}
    registry.path.write_text(signed, "utf-8")
    registry.secret_path.write_bytes(b"a different secret, invalid size")
    assert registry.load() == {}


def test_implementation_hash_supports_frozen_loader_without_source_files(monkeypatch):
    import types
    import hsd_tool.ai_registry as registry_module
    revisions = {"hsd_tool.ai_policy": "POLICY = 1", "hsd_tool.ai_client": "CLIENT = 1",
                 "hsd_tool.ai_images": "IMAGES = 1"}
    seen = []
    class FrozenLoader:
        def get_code(self, fullname):
            seen.append(fullname)
            return compile(revisions[fullname], "frozen/" + fullname, "exec")
    monkeypatch.setattr(registry_module.importlib.util, "find_spec",
                        lambda fullname: types.SimpleNamespace(loader=FrozenLoader(), origin="frozen"))
    def no_source_files(path):
        raise AssertionError("Frozen implementations must not require .py source files")
    monkeypatch.setattr(Path, "read_bytes", no_source_files)
    first = ValidationRegistry._implementation()
    assert first == ValidationRegistry._implementation()
    assert set(first) == {"ai_policy", "ai_client", "ai_images"}
    assert all(len(value) == 64 for value in first.values()) and len(seen) == 6
    revisions["hsd_tool.ai_images"] = "IMAGES = 2"
    changed = ValidationRegistry._implementation()
    assert changed["ai_images"] != first["ai_images"]
    assert changed["ai_policy"] == first["ai_policy"]


def test_unavailable_frozen_module_cannot_qualify(monkeypatch):
    import types
    import hsd_tool.ai_registry as registry_module
    monkeypatch.setattr(registry_module.importlib.util, "find_spec",
                        lambda fullname: types.SimpleNamespace(loader=types.SimpleNamespace(get_code=lambda name: None)))
    with pytest.raises(ValueError, match="无法验证"):
        ValidationRegistry._implementation()


def test_implementation_hash_ignores_source_and_frozen_compilation_paths_recursively(monkeypatch):
    import types
    import hsd_tool.ai_registry as registry_module
    source = "def outer(value):\n    def inner(extra):\n        return value + extra\n    return lambda extra: inner(extra)\n"
    location = {"path": "D:/source-checkout/hsd_tool/"}
    class Loader:
        def get_code(self, fullname):
            return compile(source, location["path"] + fullname + ".py", "exec")
    monkeypatch.setattr(registry_module.importlib.util, "find_spec",
                        lambda fullname: types.SimpleNamespace(loader=Loader()))
    source_hashes = ValidationRegistry._implementation()
    location["path"] = "C:/portable/_internal/hsd_tool/"
    frozen_hashes = ValidationRegistry._implementation()
    assert source_hashes == frozen_hashes


@pytest.mark.parametrize("changed_source", [
    "def outer(value):\n    return value + 2\n",
    "def outer(value):\n    return value - 1\n",
])
def test_portable_implementation_hash_keeps_real_bytecode_and_constant_changes(monkeypatch, changed_source):
    import types
    import hsd_tool.ai_registry as registry_module
    implementation = {"source": "def outer(value):\n    return value + 1\n", "path": "D:/source/"}
    class Loader:
        def get_code(self, fullname):
            return compile(implementation["source"], implementation["path"] + fullname, "exec")
    monkeypatch.setattr(registry_module.importlib.util, "find_spec",
                        lambda fullname: types.SimpleNamespace(loader=Loader()))
    first = ValidationRegistry._implementation()
    implementation.update(source=changed_source, path="C:/portable/")
    assert ValidationRegistry._implementation() != first


def test_unknown_charges_survive_merging_and_restart(tmp_path):
    ledger = UsageLedger(tmp_path)
    ledger.add({"requests": 1, "failures": 1, "unknown_usage_requests": 1, "cost_incomplete": True})
    ledger.add({"requests": 1, "successes": 1, "prompt_tokens": 200, "completion_tokens": 20,
                "estimated_usd": .001, "cost_incomplete": False})
    restarted = UsageLedger(tmp_path).snapshot()
    assert restarted["requests"] == 2 and restarted["successes"] == restarted["failures"] == 1
    assert restarted["estimated_usd"] == .001
    assert restarted["cost_incomplete"] and restarted["estimated_usd_upper_bound"] is None


def test_bad_cost_numbers_do_not_turn_unknown_usage_into_known_zero():
    usage = empty_usage()
    merge_usage(usage, {"requests": True, "prompt_tokens": -2, "estimated_usd": float("nan"),
                        "unknown_usage_requests": 1})
    assert usage["requests"] == usage["prompt_tokens"] == 0 and usage["estimated_usd"] == 0
    assert usage["cost_incomplete"] and usage["estimated_usd_upper_bound"] is None
    json.dumps(usage, allow_nan=False)


def test_invalid_history_warns_instead_of_claiming_lifetime_total(tmp_path):
    (tmp_path / "ai_usage.json").write_text("not JSON", "utf-8")
    assert "仅统计本次运行" in UsageLedger(tmp_path).snapshot()["warning"]


def workflow_manager(tmp_path, monkeypatch):
    from hsd_tool.service import JobManager, sha256
    manager = JobManager(tmp_path / "state")
    work = tmp_path / "work"
    work.mkdir()
    files, rows = [], []
    for index, color in enumerate(("red", "blue"), 1):
        preview, query, source = [work / f"{kind}-{index}.{suffix}" for kind, suffix in
                                  (("preview", "png"), ("query", "png"), ("source", "ai"))]
        Image.new("RGB", (240, 60), color).save(preview)
        Image.new("RGB", (480, 120), color).save(query)
        source.write_bytes(f"artificial source {index}".encode())
        identity = f"f{index:04}"
        files.append({"id": identity, "preview_path": str(preview), "source_path": str(source),
                      "source_sha256": sha256(source), "page_count": 1, "issue": None})
        rows.append({"id": f"r{index+1}", "row_number": index+1, "number": "", "issue": None,
                     "image_path": str(query), "_status": "review", "_reason": "几何独特特征不足。",
                     "_file_id": None, "candidates": [{"file_id": identity, "score": .9}],
                     "evidence": {"method": "texture", "colour": .01, "pixel_rms": .01, "changed": .001,
                                  "major_changed": .0001, "worst": .1, "residual": .01}})
    job = {"id": "audit", "status": "matching", "rows": rows, "files": files, "_reserved": [],
           "start_number": 1, "warnings": [], "timings": {}, "revision": 0, "_work_dir": str(work)}
    manager.jobs["audit"] = job
    monkeypatch.setattr(manager.ai_settings, "runtime", lambda: {"enabled": True, "api_key": "unit-test-unused-key"})
    manager._plan(job)
    return manager, job


def model_answer(candidate):
    return {"model": "unit-test-revision", "request_id": "unit-test-unused-request",
            "usage": {**empty_usage(), "requests": 1, "successes": 1, "prompt_tokens": 12},
            "decision": {"verdict": "same", "candidate_id": candidate, "reason": "all checks claimed",
                         "checks": {key: True for key in CHECKS}, "differences": []}}


def test_actual_workflow_keeps_unqualified_model_agreement_in_manual_state(tmp_path, monkeypatch):
    import hsd_tool.ai_workflow as workflow
    manager, job = workflow_manager(tmp_path, monkeypatch)
    class Client:
        def __init__(self, key):
            self.count = 0
        def review(self, content):
            self.count += 1
            return model_answer(f"f{self.count:04}")
    monkeypatch.setattr(workflow, "DeepSeekClient", Client)
    try:
        workflow.review_job(manager, "audit")
        assert job["stats"]["review"] == 2 and job["stats"]["ai_auto"] == 0
        assert job["ai_review"]["suggested_same"] == 2
        assert all(row["ai_review"]["reason_code"] == "validation_required" for row in job["rows"])
        assert job["_ai_observation_artifact"]["planned_case_ids"] == ["r2", "r3"]
        assert manager.ai_usage.snapshot()["requests"] == 2
    finally:
        manager.close()


def test_auth_failure_stops_later_calls_and_records_every_planned_case(tmp_path, monkeypatch):
    import hsd_tool.ai_workflow as workflow
    from hsd_tool.ai_client import ReviewError
    manager, job = workflow_manager(tmp_path, monkeypatch)
    calls = []
    class Client:
        def __init__(self, key):
            pass
        def review(self, content):
            calls.append(content)
            raise ReviewError("authentication", "无权限", {**empty_usage(), "requests": 1, "failures": 1})
    monkeypatch.setattr(workflow, "DeepSeekClient", Client)
    try:
        workflow.review_job(manager, "audit")
        assert len(calls) == 1 and job["stats"]["review"] == 2
        artifact = job["_ai_observation_artifact"]
        assert artifact["planned_case_ids"] == ["r2", "r3"]
        assert len(artifact["cases"]) == 2 and all(case.get("error") for case in artifact["cases"])
        assert job["ai_review"]["usage"]["requests"] == 1
    finally:
        manager.close()


def test_source_changes_during_network_io_cannot_be_applied_even_with_qualified_profile(tmp_path, monkeypatch):
    import hsd_tool.ai_workflow as workflow
    manager, job = workflow_manager(tmp_path, monkeypatch)
    monkeypatch.setattr(manager.ai_validation, "load", lambda: {"trusted": True, "model": "unit-test-revision",
        "policy_version": POLICY_VERSION, "prompt_version": PROMPT_VERSION, "categories": ["texture_review"],
        "approved_origins": ["independent_manual"]})
    class Client:
        def __init__(self, key):
            self.count = 0
        def review(self, content):
            self.count += 1
            Path(job["files"][self.count-1]["source_path"]).write_bytes(b"changed during network call")
            return model_answer(f"f{self.count:04}")
    monkeypatch.setattr(workflow, "DeepSeekClient", Client)
    try:
        workflow.review_job(manager, "audit")
        assert job["stats"]["review"] == 2 and job["stats"]["ai_auto"] == 0
        assert all(row["ai_review"]["reason_code"] == "source_changed" for row in job["rows"])
    finally:
        manager.close()
