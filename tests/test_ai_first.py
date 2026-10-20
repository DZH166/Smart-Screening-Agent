"""Artificial retrieval controls. No network, qualification, or business labels."""
import base64
import copy
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
import json
from pathlib import Path
import threading
import urllib.error
import socket

from PIL import Image, ImageDraw
import pytest

import hsd_tool.ai_first as first
from hsd_tool.ai_admin import AiDebugTrace
from hsd_tool.ai_client import ENDPOINT, ReviewError
from hsd_tool.ai_images import _images
from hsd_tool.ai_key_pool import ApiKeyPool
from hsd_tool.ai_settings import AiSettings
from hsd_tool.ai_usage import UsageLedger, empty_usage


def digest(path):
    return first._sha(path)


class Manager:
    def __init__(self, root, keys=2):
        self.root = root
        self.ai_settings = AiSettings(root / "settings", protector=None, environ={})
        self.ai_settings.save_pool({"expected_revision": 0, "add": [
            {"api_key": "public-artificial-retrieval-credential-%d" % index} for index in range(keys)]})
        self.ai_settings.save({"enabled": True})
        self.ai_key_pool = ApiKeyPool(self.ai_settings)
        self.ai_debug = AiDebugTrace()
        self.ai_usage = UsageLedger(root / "settings")
        self.ai_case_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="retrieval-shared-case")

    def record_directory(self, job_id, section):
        path = self.root / "task_records" / job_id / section
        path.mkdir(parents=True, exist_ok=True)
        return path

    def close(self):
        self.ai_case_pool.shutdown(wait=True)


@pytest.fixture
def manager(tmp_path):
    value = Manager(tmp_path)
    yield value
    value.close()


def batch(tmp_path, count=3):
    rows, files = [], []
    for index in range(count):
        preview = tmp_path / f"secret-customer-source-{index}.png"
        query = tmp_path / f"private-workbook-row-{index}.png"
        source = tmp_path / f"private-HSD777{index}.ai"
        image = Image.new("RGB", (240, 60), ((index * 73) % 256, 50, (index * 43 + 80) % 256))
        ImageDraw.Draw(image).ellipse((10 + index * 5, 10, 45 + index * 5, 45), fill="white")
        image.save(preview)
        image.resize((480, 120)).save(query)
        source.write_bytes(f"public synthetic source content {index}".encode())
        rows.append({"id": f"r{index+2}", "row_number": index+2, "image_path": str(query),
                     "number": "HSD8888", "issue": None})
        files.append({"id": f"f{index+1:04d}", "name": source.name, "source_path": str(source),
                      "source_sha256": digest(source), "preview_path": str(preview), "page_count": 1, "issue": None})
    return rows, files


class Reply(BytesIO):
    def geturl(self):
        return ENDPOINT


def payload(body):
    instruction = json.loads(body["messages"][1]["content"][0]["text"])
    result = {"matches": [{"query_id": query, "candidate_id": instruction["candidate_ids"][0],
                            "verdict": "same", "reason": "人工构造的模型响应，不代表业务核验"}
                           for query in instruction["query_ids"]]}
    return {"model": "deepseek-flash", "id": "synthetic-provider-id",
            "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(result)}}],
            "usage": {"prompt_tokens": 30, "completion_tokens": 10}}


class Opener:
    def __init__(self, outcome=None):
        self.outcome = outcome
        self.calls = []
        self.threads = []
        self.keys = []

    def open(self, request, timeout):
        body = json.loads(request.data)
        self.calls.append(body)
        self.threads.append(threading.current_thread().name)
        self.keys.append(request.headers["Authorization"])
        assert request.full_url == ENDPOINT and timeout <= 30
        value = self.outcome(request, body) if self.outcome else payload(body)
        if isinstance(value, BaseException):
            raise value
        return Reply(json.dumps(value).encode())


def run(manager, rows, files, opener, **kwargs):
    return first.retrieve(manager, "synthetic-task", rows, files,
                          client_factory=lambda key: first.RetrievalClient(key, opener=opener, attempts=1), **kwargs)


@pytest.mark.parametrize("mode,size", [("RGB", (200, 180)), ("RGBA", (3500, 100)),
                                      ("RGB", (5001, 300)), ("L", (1200, 70))])
def test_direct_lossless_webp_equals_existing_complete_overview_and_every_panel(tmp_path, mode, size):
    path = tmp_path / "generated.png"
    color = {"RGB": (111, 33, 202), "RGBA": (111, 33, 202, 120), "L": 145}[mode]
    image = Image.new(mode, size, color)
    draw = ImageDraw.Draw(image)
    for x in range(0, size[0], 71):
        draw.rectangle((x, 0, x + 15, size[1] - 1), fill=0)
    image.save(path)
    previous = _images(path, "查询 Q-test")
    raw_digest, prepared = first._image(path, {})
    current = first._section("Q-test", prepared, "查询")
    assert raw_digest == digest(path)
    assert len(previous) == len(current)
    for old, new in zip(previous, current):
        assert old["type"] == new["type"]
        if old["type"] == "text":
            assert old == new
        else:
            with Image.open(BytesIO(base64.b64decode(old["image_url"]["url"].split(",", 1)[1]))) as old_image:
                with Image.open(BytesIO(base64.b64decode(new["image_url"]["url"].split(",", 1)[1]))) as new_image:
                    assert old_image.size == new_image.size
                    assert old_image.convert("RGB").tobytes() == new_image.convert("RGB").tobytes()


def test_image_cache_reuses_only_identical_encoded_input_and_detects_changed_pixels(tmp_path):
    image = tmp_path / "synthetic.png"
    Image.new("RGB", (100, 100), "red").save(image)
    cache = {}
    old_digest, old = first._image(image, cache)
    assert first._image(image, cache)[1] is old
    Image.new("RGB", (100, 100), "blue").save(image)
    changed_digest, changed = first._image(image, cache)
    assert old_digest != changed_digest and old["pixels_sha256"] != changed["pixels_sha256"]


def test_short_random_aliases_retry_collisions_without_positional_fallback(monkeypatch):
    outcomes = iter(("deadbeef", "deadbeef", "00112233", "deadbeef"))
    sizes = []
    def token(size):
        sizes.append(size)
        return next(outcomes)
    monkeypatch.setattr(first.secrets, "token_hex", token)
    used = set()
    assert first._alias("Q", used) == "Qdeadbeef"
    assert first._alias("Q", used) == "Q00112233"
    assert first._alias("C", used) == "Cdeadbeef"
    assert len(used) == 3 and sizes == [4, 4, 4, 4]


def test_broken_random_source_fails_instead_of_inventing_order_based_aliases(monkeypatch):
    monkeypatch.setattr(first.secrets, "token_hex", lambda size: "deadbeef")
    with pytest.raises(ValueError):
        first._alias("Q", {"Qdeadbeef"})


@pytest.mark.parametrize("change", ["omitted", "duplicate", "invented-query", "invented-candidate", "extra-field",
                                    "bad-verdict", "null-same", "bad-reason"])
def test_result_schema_rejects_omissions_duplicates_or_invented_ids(change):
    item = {"query_id": "q1", "candidate_id": "c1", "verdict": "same", "reason": "synthetic"}
    value = {"matches": [item]}
    if change == "omitted":
        value["matches"] = []
    elif change == "duplicate":
        value["matches"].append(copy.deepcopy(item))
    elif change == "invented-query":
        item["query_id"] = "invented"
    elif change == "invented-candidate":
        item["candidate_id"] = "invented"
    elif change == "extra-field":
        item["confidence"] = 1
    elif change == "bad-verdict":
        item["verdict"] = "auto"
    elif change == "null-same":
        item["candidate_id"] = None
    else:
        item["reason"] = " "
    with pytest.raises(ValueError):
        first.parse_matches(value, ["q1"], ["c1"])


def test_model_collision_remains_a_collision_without_forced_assignment():
    value = {"matches": [{"query_id": query, "candidate_id": "c1", "verdict": "same", "reason": "synthetic"}
                          for query in ("q1", "q2")]}
    result = first.parse_matches(value, ["q2", "q1"], ["c1", "c2"])
    assert [row["query_id"] for row in result["matches"]] == ["q2", "q1"]
    assert result["ownership_conflicts"] == [{"candidate_id": "c1", "query_ids": ["q1", "q2"]}]
    assert result["automatic_passes"] == 0


def test_pair_checks_or_confidence_cannot_be_substituted_for_required_retrieval_schema():
    with pytest.raises(ValueError):
        first.parse_matches({"candidate_reviews": []}, ["q1"], ["c1"])


def test_anonymous_full_library_requests_usage_persisted_no_job_mutation(manager, tmp_path):
    rows, files = batch(tmp_path)
    frozen = copy.deepcopy((rows, files))
    opener = Opener()
    checkpoints = []
    result = run(manager, rows, files, opener, checkpoint=checkpoints.append)
    assert result["status"] == "completed" and len(result["proposals"]) == 3
    assert (rows, files) == frozen
    assert all(item["suggestion_only"] and not item["automatic_pass"] for item in result["proposals"])
    assert len(result["ownership_conflicts"]) == 1
    assert set(result["ownership_conflicts"][0]["row_ids"]) == {row["id"] for row in rows}
    assert manager.ai_usage.snapshot()["requests"] == result["usage"]["requests"] == 1
    assert manager.ai_key_pool.snapshot()["usage"]["requests"] == 1
    assert all(thread.startswith("retrieval-shared-case") for thread in opener.threads)
    sent = " ".join(block["text"] for body in opener.calls for block in body["messages"][1]["content"]
                    if block["type"] == "text")
    for item in [str(tmp_path), "private-workbook", "secret-customer", "HSD8888", *[row["id"] for row in rows],
                 *[file["id"] for file in files]]:
        assert item not in sent
    for body in opener.calls:
        instruction = json.loads(body["messages"][1]["content"][0]["text"])
        assert len(instruction["candidate_ids"]) == 3
        assert all(value.startswith("C") for value in instruction["candidate_ids"])
        assert all(value.startswith("Q") for value in instruction["query_ids"])
        assert all(len(value) == 9 for value in instruction["candidate_ids"] + instruction["query_ids"])
        assert len(set(instruction["candidate_ids"] + instruction["query_ids"])) == 6
        assert body["thinking"] == {"type": "disabled"} and body["max_tokens"] == 8192
    saved = json.loads(Path(result["record_path"]).read_text("utf-8"))
    assert saved["status"] == "completed" and saved["automatic_passes"] == 0
    assert not saved["qualification_granted"]
    assert len(saved["groups"][0]["attempt_history"]) == 1
    assert any(checkpoint["groups"] and checkpoint["groups"][0]["status"] == "planned" for checkpoint in checkpoints)
    trace = json.dumps(manager.ai_debug.snapshot())
    assert "secret-customer" not in trace and "人工构造" not in trace and "Authorization" not in trace
    assert manager.ai_debug.snapshot()["active"] == []


def test_query_groups_serialize_and_retain_cross_group_ownership_conflicts(manager, tmp_path, monkeypatch):
    rows, files = batch(tmp_path, 3)
    monkeypatch.setattr(first, "QUERY_GROUP_SIZE", 1)
    opener = Opener()
    result = run(manager, rows, files, opener)
    assert result["status"] == "completed" and len(opener.calls) == 3
    libraries = [json.loads(body["messages"][1]["content"][0]["text"])["candidate_ids"] for body in opener.calls]
    assert all(library == libraries[0] and len(library) == 3 for library in libraries)
    assert len(result["ownership_conflicts"][0]["row_ids"]) == 3
    assert manager.ai_usage.snapshot()["requests"] == 3


def test_oversized_group_bisects_only_queries_and_never_drops_candidates(monkeypatch):
    queries = [{"alias": f"Q{i}"} for i in range(4)]
    candidates = [{"alias": "C0"}, {"alias": "C1"}]
    sections = {item["alias"]: [{"type": "text", "text": item["alias"] + "x" * 800}]
                for item in queries + candidates}
    whole = first.prepare_groups(queries, candidates, sections)[0]["request_bytes"]
    monkeypatch.setattr(first, "MAX_REQUEST_BYTES", whole - 1000)
    split = first.prepare_groups(queries, candidates, sections)
    assert len(split) == 2
    assert [identity for group in split for identity in group["query_ids"]] == [item["alias"] for item in queries]
    assert all(group["candidate_ids"] == ["C0", "C1"] and group["status"] == "planned" for group in split)
    monkeypatch.setattr(first, "MAX_REQUEST_BYTES", 1)
    oversized = first.prepare_groups(queries, candidates, sections)
    assert len(oversized) == 4 and all(group["status"] == "oversized" for group in oversized)
    assert all(group["candidate_ids"] == ["C0", "C1"] for group in oversized)


@pytest.mark.parametrize("code,rotates", [(401, True), (402, True), (503, False)])
def test_shared_dispatcher_owns_two_attempt_budget_and_records_every_charge(manager, tmp_path, code, rotates):
    rows, files = batch(tmp_path, 1)
    opener = Opener()
    def outcome(request, body):
        if len(opener.calls) == 1:
            return urllib.error.HTTPError(ENDPOINT, code, "untrusted remote body", {}, BytesIO(b"private remote text"))
        return payload(body)
    opener.outcome = outcome
    result = run(manager, rows, files, opener)
    assert result["status"] == "completed" and len(opener.calls) == 2
    assert (opener.keys[0] != opener.keys[1]) is rotates
    attempts = result["artifact"]["groups"][0]["attempt_history"]
    assert len(attempts) == 2 and attempts[0]["code"] != "ok" and attempts[1]["code"] == "ok"
    assert manager.ai_usage.snapshot()["requests"] == result["usage"]["requests"] == 2
    assert result["usage"]["unknown_usage_requests"] == int(code >= 500)
    assert "private remote" not in json.dumps(result)


def test_429_stops_all_groups_and_next_batch_cannot_bypass_shared_pool(manager, tmp_path, monkeypatch):
    rows, files = batch(tmp_path, 3)
    monkeypatch.setattr(first, "QUERY_GROUP_SIZE", 1)
    opener = Opener(lambda request, body: urllib.error.HTTPError(ENDPOINT, 429, "remote", {}, BytesIO(b"")))
    result = run(manager, rows, files, opener)
    assert result["status"] == "failed" and result["error_code"] == "rate_limit"
    assert len(opener.calls) == result["usage"]["requests"] == 1
    assert [group["status"] for group in result["artifact"]["groups"]] == ["failed", "not_called", "not_called"]
    second = run(manager, rows, files, opener)
    assert second["status"] == "failed" and second["usage"]["requests"] == 0
    assert len(opener.calls) == manager.ai_usage.snapshot()["requests"] == 1


def test_network_retry_uses_same_enabled_key_and_preserves_unknown_first_usage(manager, tmp_path):
    rows, files = batch(tmp_path, 1)
    opener = Opener()
    opener.outcome = lambda request, body: socket.timeout() if len(opener.calls) == 1 else payload(body)
    result = run(manager, rows, files, opener)
    assert result["status"] == "completed" and len(opener.calls) == 2
    assert opener.keys[0] == opener.keys[1]
    assert result["usage"]["requests"] == 2 and result["usage"]["unknown_usage_requests"] == 1
    assert result["usage"]["cost_incomplete"] and result["usage"]["estimated_usd_upper_bound"] is None


@pytest.mark.parametrize("target", ["source_path", "preview_path", "image_path"])
def test_source_or_preview_change_discards_all_proposals_but_keeps_paid_result(manager, tmp_path, target):
    rows, files = batch(tmp_path, 1)
    selected = rows[0] if target == "image_path" else files[0]
    def changed(request, body):
        Path(selected[target]).write_bytes(b"changed after dispatch")
        return payload(body)
    result = run(manager, rows, files, Opener(changed))
    assert result["status"] == "failed" and result["error_code"] == "source_changed"
    assert result["proposals"] == [] and result["usage"]["requests"] == 1
    assert result["artifact"]["groups"][0]["status"] == "completed"
    assert result["artifact"]["groups"][0]["decision"]["matches"]


def test_late_return_cannot_apply_after_coordinator_binding_changes(manager, tmp_path, monkeypatch):
    rows, files = batch(tmp_path, 2)
    monkeypatch.setattr(first, "QUERY_GROUP_SIZE", 1)
    valid = [True]
    def changed(request, body):
        valid[0] = False
        return payload(body)
    opener = Opener(changed)
    result = run(manager, rows, files, opener, is_current=lambda: valid[0])
    assert result["status"] == "stale" and result["proposals"] == []
    assert len(opener.calls) == result["usage"]["requests"] == 1
    assert result["artifact"]["groups"][1]["status"] == "not_called"


def test_hard_anomalies_and_duplicate_previews_are_not_sent_to_model(manager, tmp_path):
    rows, files = batch(tmp_path, 4)
    files[1]["page_count"] = 2
    files[2]["issue"] = "synthetic damaged source"
    Path(files[3]["preview_path"]).write_bytes(Path(files[0]["preview_path"]).read_bytes())
    opener = Opener()
    result = run(manager, rows, files, opener)
    assert result["status"] == "failed" and opener.calls == []
    rejected = {item["id"]: item["reason_code"] for item in result["rejected_files"]}
    assert rejected == {"f0001": "duplicate_preview", "f0002": "hard_conflict", "f0003": "hard_conflict", "f0004": "duplicate_preview"}
    assert result["usage"]["requests"] == 0
    assert json.loads(Path(result["record_path"]).read_text("utf-8"))["planned_file_ids"] == [file["id"] for file in files]


def test_disabled_and_preexisting_source_change_do_not_call_provider(manager, tmp_path):
    rows, files = batch(tmp_path, 1)
    manager.ai_settings.save({"enabled": False})
    opener = Opener()
    assert run(manager, rows, files, opener)["status"] == "disabled"
    manager.ai_settings.save({"enabled": True})
    Path(files[0]["source_path"]).write_bytes(b"modified before retrieval")
    result = run(manager, rows, files, opener)
    assert result["rejected_files"] == [{"id": "f0001", "reason_code": "source_changed"}]
    assert opener.calls == []


@pytest.mark.parametrize("page_count", [None, True, 0, 2])
def test_missing_or_noninteger_artboard_metadata_cannot_be_sent_as_single_artboard(manager, tmp_path, page_count):
    rows, files = batch(tmp_path, 1)
    files[0]["page_count"] = page_count
    opener = Opener()
    result = run(manager, rows, files, opener)
    assert result["rejected_files"] == [{"id": "f0001", "reason_code": "hard_conflict"}]
    assert opener.calls == []


def test_runtime_implementation_change_discards_proposals_and_keeps_response(manager, tmp_path, monkeypatch):
    rows, files = batch(tmp_path, 1)
    implementation = {"synthetic": "before"}
    monkeypatch.setattr(first, "_implementation", lambda: dict(implementation))
    def changed(request, body):
        implementation["synthetic"] = "after"
        return payload(body)
    result = run(manager, rows, files, Opener(changed))
    assert result["status"] == "failed" and result["error_code"] == "implementation_changed"
    assert result["proposals"] == [] and result["usage"]["requests"] == 1
    assert result["artifact"]["groups"][0]["decision"]["matches"]


def test_checkpoint_failure_does_not_retry_received_response_or_double_charge(manager, tmp_path):
    rows, files = batch(tmp_path, 1)
    opener = Opener()
    def failing(_):
        raise OSError("synthetic local checkpoint failure")
    result = run(manager, rows, files, opener, checkpoint=failing)
    assert result["status"] == "completed" and len(opener.calls) == 1
    assert manager.ai_usage.snapshot()["requests"] == result["usage"]["requests"] == 1
    assert result["artifact"]["warnings"]


def test_invalid_response_retained_without_disguising_it_as_automatic_match(manager, tmp_path):
    rows, files = batch(tmp_path, 1)
    def malformed(request, body):
        answer = payload(body)
        answer["choices"][0]["message"]["content"] = '{"matches": []}'
        return answer
    result = run(manager, rows, files, Opener(malformed))
    assert result["status"] == "failed" and result["proposals"] == []
    assert result["artifact"]["groups"][0]["error_code"] == "invalid_decision"
    assert result["artifact"]["groups"][0]["failure_details"] == [{"code": "missing_query"}]
    assert result["usage"]["requests"] == result["usage"]["failures"] == 1
    assert result["usage"]["unknown_usage_requests"] == 0


@pytest.mark.parametrize("model", ["deepseek-chat", "deepseek-v4.1-flash", "deepseek-flash-new-revision", "other-provider"])
def test_unexpected_response_model_is_rejected_without_losing_known_charged_usage(manager, tmp_path, model):
    rows, files = batch(tmp_path, 1)
    def changed_model(request, body):
        answer = payload(body)
        answer["model"] = model
        return answer
    opener = Opener(changed_model)
    result = run(manager, rows, files, opener)
    assert result["status"] == "failed" and result["proposals"] == [] and len(opener.calls) == 1
    group = result["artifact"]["groups"][0]
    assert group["error_code"] == "invalid_decision" and group["failure_details"] == [{"code": "invalid_model"}]
    assert result["usage"]["requests"] == result["usage"]["failures"] == 1
    assert result["usage"]["prompt_tokens"] == 30 and result["usage"]["completion_tokens"] == 10
    assert result["usage"]["estimated_usd"] > 0 and not result["usage"]["cost_incomplete"]
    assert manager.ai_usage.snapshot()["requests"] == manager.ai_key_pool.snapshot()["usage"]["requests"] == 1


@pytest.mark.parametrize("detail", ["unknown_query", "unknown_candidate", "duplicate_query", "invalid_schema"])
def test_safe_failure_detail_never_repairs_unknown_id_or_reveals_remote_text(manager, tmp_path, detail):
    rows, files = batch(tmp_path, 1)
    def malformed(request, body):
        answer = payload(body)
        parsed = json.loads(answer["choices"][0]["message"]["content"])
        if detail == "unknown_query":
            parsed["matches"][0]["query_id"] = "remote-untrusted-private-value"
        elif detail == "unknown_candidate":
            parsed["matches"][0]["candidate_id"] = "remote-untrusted-private-value"
        elif detail == "duplicate_query":
            parsed["matches"].append(copy.deepcopy(parsed["matches"][0]))
        else:
            parsed["unexpected"] = "remote-untrusted-private-value"
        answer["choices"][0]["message"]["content"] = json.dumps(parsed)
        return answer
    result = run(manager, rows, files, Opener(malformed))
    assert result["status"] == "failed" and result["proposals"] == []
    group = result["artifact"]["groups"][0]
    assert group["error_code"] == "invalid_decision" and group["failure_details"] == [{"code": detail}]
    assert "remote-untrusted-private-value" not in json.dumps(result)
    assert result["usage"]["requests"] == result["usage"]["failures"] == 1


def test_one_query_plus_full_library_too_large_is_explicit_and_never_sent(manager, tmp_path, monkeypatch):
    rows, files = batch(tmp_path, 2)
    monkeypatch.setattr(first, "MAX_REQUEST_BYTES", 1)
    opener = Opener()
    result = run(manager, rows, files, opener)
    assert result["status"] == "failed" and result["error_code"] == "invalid_input"
    assert len(result["artifact"]["groups"]) == 2
    assert all(len(group["candidate_ids"]) == 2 and group["status"] == "oversized" for group in result["artifact"]["groups"])
    assert opener.calls == [] and result["usage"]["requests"] == 0
