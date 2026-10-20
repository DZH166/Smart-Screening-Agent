"""AI-first experiment schema and outbound privacy; no actual network/Key."""
import json
import importlib.util
import base64
from io import BytesIO
import urllib.error
from pathlib import Path

import pytest
from PIL import Image

TOOL = Path(__file__).resolve().parents[1] / "tools" / "benchmark_deepseek_first.py"
SPEC = importlib.util.spec_from_file_location("benchmark_deepseek_first", TOOL)
bulk = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bulk)


def row(query="qA", candidate="cA", verdict="same"):
    return {"query_id": query, "candidate_id": candidate, "verdict": verdict, "reason": "图案相符"}


def test_schema_accepts_only_suggestions_and_detects_ownership_conflict():
    result = bulk.parse_matches({"matches": [row(), row("qB")]}, ["qA", "qB"], ["cA"])
    assert result["automatic_passes"] == 0
    assert result["ownership_conflicts"] == [{"candidate_id": "cA", "query_ids": ["qA", "qB"]}]
    assert result["verdict"] == "experimental_suggestions_only"


@pytest.mark.parametrize("matches", [[], [row(), row()], [row("unknown")], [row(candidate="unknown")],
                                      [row(candidate=None)], [{**row(), "extra": 1}],
                                      [{**row(), "reason": ""}]])
def test_schema_rejects_missing_duplicate_unknown_or_malformed(matches):
    with pytest.raises(ValueError):
        bulk.parse_matches({"matches": matches}, ["qA"], ["cA"])


def test_null_uncertain_is_retained_and_reference_not_qualification():
    decision = bulk.parse_matches({"matches": [row(candidate=None, verdict="uncertain")]}, ["qA"], ["cA"])
    score = bulk.score_result(decision, {"origin": "reference_map", "expected": {"qA": "cA"}}, ["qA"], {"cA"})
    assert score["null_suggestions"] == 1 and score["matching_reference"] == 0
    assert score["automatic_passes"] == 0 and score["qualification_granted"] is False


def test_complete_previews_and_panels_without_path_filename_or_labels(tmp_path):
    image = tmp_path / "private-secret-HSD1234.png"
    Image.new("RGB", (1800, 120), "red").save(image)
    manifest = {"queries": [{"id": "qOpaque", "image_path": str(image)}],
                "candidates": [{"id": "cOpaque", "image_path": str(image), "source_path": "private.ai",
                                "expected": "do-not-send", "rank": 1}]}
    content = bulk.prepare_content(manifest)
    serialized = json.dumps(content)
    assert "qOpaque" in serialized and "cOpaque" in serialized
    assert str(tmp_path) not in serialized and image.name not in serialized
    assert "private.ai" not in serialized and "do-not-send" not in serialized and '"rank"' not in serialized
    assert sum(item["type"] == "image_url" for item in content) > 2
    original = bulk._images(image, "查询 qOpaque")
    converted = [item for item in content if item["type"] == "image_url"]
    for before, after in zip([item for item in original if item["type"] == "image_url"], converted):
        assert after["image_url"]["url"].startswith("data:image/webp;base64,")
        with Image.open(BytesIO(base64.b64decode(before["image_url"]["url"].split(",", 1)[1]))) as a:
            with Image.open(BytesIO(base64.b64decode(after["image_url"]["url"].split(",", 1)[1]))) as b:
                assert a.size == b.size and a.convert("RGB").tobytes() == b.convert("RGB").tobytes()
    body = json.loads(bulk.BulkClient("experiment-test-public-dummy", attempts=1).body(content))
    assert body["max_tokens"] == 8192 and body["thinking"] == {"type": "disabled"}
    assert bulk.PROTOCOL in body["messages"][1]["content"][0]["text"]


def test_larger_image_count_is_isolated_from_production(tmp_path):
    image = tmp_path / "one.png"
    Image.new("RGB", (10, 10), "red").save(image)
    block = bulk._images(image, "匿名")[1]
    content = [{"type": "text", "text": "{}"}] + [block] * 41
    assert len(bulk.BulkClient("experiment-test-public-dummy")._content(content)) == 42
    from hsd_tool.ai_client import DeepSeekClient, ReviewError
    with pytest.raises(ReviewError):
        DeepSeekClient("experiment-test-public-dummy")._content(content)
    with pytest.raises(ReviewError):
        bulk.BulkClient("experiment-test-public-dummy")._content([block] * 601)


def test_query_groups_keep_complete_candidate_library_and_no_query_omissions(tmp_path):
    image = tmp_path / "one.png"
    Image.new("RGB", (10, 10), "red").save(image)
    manifest = {"queries": [{"id": "q" + str(i), "image_path": str(image)} for i in range(5)],
                "candidates": [{"id": "c" + str(i), "image_path": str(image)} for i in range(3)]}
    sections = bulk.prepare_sections(manifest)
    groups = bulk.request_groups(manifest, sections, 2)
    assert len(groups) == 3
    instructions = [json.loads(group[0]["text"]) for group in groups]
    assert [q for group in instructions for q in group["query_ids"]] == ["q0", "q1", "q2", "q3", "q4"]
    assert all(group["candidate_ids"] == ["c0", "c1", "c2"] for group in instructions)


def test_manifest_rejects_changed_source_and_hard_anomaly(tmp_path):
    image = tmp_path / "one.png"
    Image.new("RGB", (10, 10), "red").save(image)
    source = tmp_path / "one.ai"
    source.write_bytes(b"test source")
    candidate = {"id": "cA", "image_path": str(image), "source_path": str(source),
                 "source_sha256": bulk.sha(source), "page_count": 1, "issue": None}
    data = {"queries": [{"id": "qA", "image_path": str(image)}], "candidates": [candidate]}
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(data))
    assert bulk.load_manifest(path)["candidates"][0]["source_sha256"] == bulk.sha(source)
    candidate["page_count"] = 2
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        bulk.load_manifest(path)
    candidate["page_count"] = 1
    source.write_bytes(b"changed")
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        bulk.load_manifest(path)


class Response:
    def __init__(self, data):
        self.data = json.dumps(data).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def geturl(self):
        return bulk.ENDPOINT

    def read(self, limit):
        return self.data[:limit]


def content_for_transport(tmp_path):
    image = tmp_path / "test.png"
    Image.new("RGB", (10, 10), "red").save(image)
    return bulk.prepare_content({"queries": [{"id": "qA", "image_path": str(image)}],
                                 "candidates": [{"id": "cA", "image_path": str(image)}]})


def test_transport_binds_complete_strict_results_and_usage(tmp_path):
    class Opener:
        def open(self, request, timeout):
            assert request.full_url == bulk.ENDPOINT and timeout == 30
            sent = json.loads(request.data)
            assert sent["max_tokens"] == 8192
            return Response({"model": "deepseek-flash", "choices": [{"finish_reason": "stop", "message": {
                "content": json.dumps({"matches": [row()]})}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 20}})
    result = bulk.BulkClient("experiment-test-public-dummy", opener=Opener(), attempts=1).review(content_for_transport(tmp_path))
    assert result["usage"]["requests"] == result["usage"]["successes"] == 1
    assert result["usage"]["prompt_tokens"] == 100
    assert result["decision"]["automatic_passes"] == 0


def test_http_failure_does_not_expose_provider_body(tmp_path):
    class Opener:
        def open(self, request, timeout):
            raise urllib.error.HTTPError(bulk.ENDPOINT, 429, "private-provider-message", {}, BytesIO(b"secret-provider-body"))
    with pytest.raises(bulk.ReviewError) as caught:
        bulk.BulkClient("experiment-test-public-dummy", opener=Opener(), attempts=1).review(content_for_transport(tmp_path))
    assert caught.value.code == "rate_limit"
    assert caught.value.usage["requests"] == caught.value.usage["failures"] == 1
    assert "private-provider-message" not in str(caught.value) and "secret-provider-body" not in str(caught.value)
