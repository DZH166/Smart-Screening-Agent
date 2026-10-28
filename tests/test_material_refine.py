"""Downloadable unverified results and one-click refinement; no provider calls."""
import json
import zipfile

import pytest
from werkzeug.exceptions import Conflict

from hsd_tool.material_ark import ArkProviderError
from hsd_tool.material_service import MaterialManager
from test_material_service import Settings, Provider, complete, png, upload, upload_two


@pytest.fixture
def refinement(tmp_path):
    class SmallProvider(Provider):
        def extract(self, raw, **kwargs):
            result = super().extract(raw, **kwargs)
            result.no_upscale = result.rectangular_crops = True
            return result
    provider = SmallProvider()
    manager = MaterialManager(tmp_path, Settings(), cloud=True, provider_factory=lambda config: provider)
    result = complete(manager, upload(manager))
    provider.entered.clear()
    yield manager, provider, result
    provider.release.set(); manager.close()


def refine(manager, state, **extra):
    return manager.refine(state["id"], "employee-a", {"expected_revision": state["revision"],
        "item_id": state["items"][0]["id"], **extra})


def test_refine_replaces_one_current_result_preserving_immediate_before_and_usage(refinement):
    manager, provider, state = refinement
    old = state["items"][0]
    before = manager.asset(state["id"], "employee-a", "item", old["id"])[0].read_bytes()
    refine(manager, state)
    current = complete(manager, state["id"])
    item = current["items"][0]
    assert len(current["items"]) == 1 and item["id"] != old["id"]
    assert item["status"] == "generated" and item["downloadable"] and item["refined"]
    assert "review" not in item and item["bounds"] == old["bounds"]
    assert item["previous_image"]["image_url"].endswith(item["id"] + "/before")
    assert manager.asset(state["id"], "employee-a", "before", item["id"])[0].read_bytes() == before
    with pytest.raises(KeyError):
        manager.asset(state["id"], "employee-a", "item", old["id"])
    assert provider.calls == 2 and provider.edit_raw == before
    attempts = manager.jobs[state["id"]]["attempts"]
    assert [row["operation"] for row in attempts] == ["extract", "refine"]
    assert attempts[-1]["state"] == "returned"
    archive, _ = manager.download(state["id"], "employee-a")
    with zipfile.ZipFile(archive) as contents:
        records = json.loads(contents.read("素材说明.json"))["items"]
        assert len(records) == 1 and records[0]["status"] == "generated"
    refine(manager, current)
    newest = complete(manager, state["id"])["items"][0]
    assert manager.jobs[state["id"]]["items"][-1]["previous_item_id"] == item["id"]
    assert newest["refined"] and provider.calls == 3


def test_refining_first_of_two_results_preserves_public_order_names_and_count(refinement):
    manager, provider, _ = refinement
    original = provider.extract
    def named(raw, **kwargs):
        result = original(raw, **kwargs)
        result.layers[0].label = "设计-%d" % provider.calls
        return result
    provider.extract = named
    state = upload_two(manager)
    old_items = state["items"]
    refine(manager, state)
    current = complete(manager, state["id"])
    assert len(current["items"]) == 2
    assert [row["name"] for row in current["items"]] == [row["name"] for row in old_items]
    assert current["items"][0]["id"] != old_items[0]["id"] and current["items"][0]["refined"]
    assert current["items"][1]["id"] == old_items[1]["id"]
    private = manager.jobs[state["id"]]["items"]
    assert len(private) == 3 and private[0]["status"] == "superseded"
    assert private[1]["previous_item_id"] == old_items[0]["id"]


@pytest.mark.parametrize("unknown", [False, True])
def test_refine_failure_never_retries_or_replaces_downloadable_result(refinement, unknown):
    manager, provider, state = refinement
    provider.failures = [ArkProviderError("submission_unknown" if unknown else "rate_limit", "secret provider text",
        settled=not unknown, safe_retry=True, usage={"images": 1})]
    refine(manager, state)
    failed = complete(manager, state["id"])
    item = failed["items"][0]
    assert item["id"] == state["items"][0]["id"] and item["downloadable"]
    assert item["refine_error"] and item["refine_submission_unknown"] is unknown
    assert "secret provider text" not in json.dumps(failed)
    assert provider.calls == 2
    assert manager.jobs[state["id"]]["attempts"][-1]["usage"] == {"images": 1}
    manager.asset(state["id"], "employee-a", "item", item["id"], download=True)
    if unknown:
        with pytest.raises(Conflict, match="可能重复计费"):
            refine(manager, failed)
        refine(manager, failed, acknowledge_unknown=True)
        assert complete(manager, state["id"])["items"][0]["id"] != item["id"]
        assert provider.calls == 3


def test_refine_busy_duplicate_revision_and_cancel_preserve_old_result(refinement):
    manager, provider, state = refinement
    provider.block = True
    queued = refine(manager, state)
    try:
        assert provider.entered.wait(10)
        with pytest.raises(Conflict):
            refine(manager, state)
        busy = manager.snapshot(state["id"], "employee-a")
        # The pre-refinement image is still on disk and untouched, so the design
        # stays downloadable while its new version is being produced.
        assert busy["items"][0]["downloadable"] is True and busy["download_url"]
        archive, _ = manager.download(state["id"], "employee-a")
        assert archive.is_file()
        manager.cancel(state["id"], "employee-a", busy["revision"])
        assert not manager.futures[state["id"]].done()
    finally:
        provider.release.set()
    stopped = complete(manager, state["id"])
    assert stopped["status"] == "cancelled"
    assert stopped["items"][0]["id"] == state["items"][0]["id"]
    assert stopped["items"][0]["downloadable"] and stopped["items"][0]["refine_error"]
    assert provider.calls == 2


@pytest.mark.parametrize("target", ["source", "current", "previous", "thumbnail"])
@pytest.mark.parametrize("thumbnail", [False, True])
def test_before_assets_validate_both_versions_source_and_requested_thumbnail(refinement, target, thumbnail):
    manager, _, state = refinement
    refine(manager, state)
    latest = complete(manager, state["id"]); item = latest["items"][0]
    job = manager.jobs[state["id"]]
    previous = job["items"][0]
    if target == "source":
        path = manager._directory(state["id"]) / (item["source_id"] + ".png")
    elif target == "current":
        path = manager._directory(state["id"]) / (item["id"] + ".png")
    else:
        path = manager._directory(state["id"]) / (previous["id"] + (".thumb.png" if target == "thumbnail" else ".png"))
    path.write_bytes(b"changed")
    if target == "thumbnail" and not thumbnail:
        manager.asset(state["id"], "employee-a", "before", item["id"])
    else:
        with pytest.raises(ValueError, match="发生变化"):
            manager.asset(state["id"], "employee-a", "before", item["id"], thumbnail=thumbnail)
    with pytest.raises(KeyError):
        manager.asset(state["id"], "employee-b", "before", item["id"])


def test_refine_rechecks_input_after_wait_and_never_publishes_over_changed_image(refinement):
    manager, provider, state = refinement
    provider.block = True
    refine(manager, state)
    try:
        assert provider.entered.wait(10)
        path = manager._directory(state["id"]) / (state["items"][0]["id"] + ".png")
        path.write_bytes(png((10, 20, 30, 255)))
    finally:
        provider.release.set()
    failed = complete(manager, state["id"])
    assert failed["items"][0]["id"] == state["items"][0]["id"] and failed["items"][0]["refine_error"]
    assert len(manager.jobs[state["id"]]["items"]) == 1 and provider.calls == 2


def test_refine_manifest_commit_failure_keeps_old_current(refinement, monkeypatch):
    manager, _, state = refinement
    save = manager._save
    failed = []
    def unavailable(job, **kwargs):
        if not failed and any(row["status"] == "superseded" for row in job["items"]):
            failed.append(True)
            raise OSError("synthetic write failure")
        return save(job, **kwargs)
    monkeypatch.setattr(manager, "_save", unavailable)
    refine(manager, state)
    result = complete(manager, state["id"])
    assert failed and len(result["items"]) == 1
    assert result["items"][0]["id"] == state["items"][0]["id"] and result["items"][0]["downloadable"]
    assert len(manager.jobs[state["id"]]["items"]) == 1


@pytest.mark.parametrize("stage", ["queued", "processing"])
def test_local_refine_start_save_failure_never_blocks_old_download_or_calls_model(refinement, monkeypatch, stage):
    manager, provider, state = refinement
    save = manager._save
    failed = []
    def unavailable(job, **kwargs):
        if not failed and job["status"] == stage:
            failed.append(True)
            raise OSError("synthetic local write failure")
        return save(job, **kwargs)
    monkeypatch.setattr(manager, "_save", unavailable)
    if stage == "queued":
        with pytest.raises(OSError):
            refine(manager, state)
        result = manager.snapshot(state["id"], "employee-a")
    else:
        refine(manager, state)
        result = complete(manager, state["id"])
    assert failed and result["items"][0]["downloadable"] and provider.calls == 1
    assert result["items"][0]["id"] == state["items"][0]["id"]


def test_executor_rejection_persists_terminal_revision_keeps_old_download_and_never_spends(refinement, monkeypatch):
    manager, provider, state = refinement
    assert manager.futures[state["id"]].done()
    def reject(*args, **kwargs):
        raise RuntimeError("private executor failure")
    monkeypatch.setattr(manager.executor, "submit", reject)
    with pytest.raises(Conflict, match="未能排队"):
        refine(manager, state)
    result = manager.snapshot(state["id"], "employee-a")
    assert result["status"] == "error" and result["revision"] == state["revision"] + 2
    assert len(result["items"]) == 1 and result["items"][0]["id"] == state["items"][0]["id"]
    assert result["items"][0]["downloadable"] and not result["items"][0]["refined"]
    assert result["items"][0]["refine_error"] and result["items"][0]["refine_submission_unknown"] is False
    assert provider.calls == 1 and state["id"] not in manager.futures
    persisted = manager._read(manager._directory(state["id"]))
    assert persisted["status"] == result["status"] and persisted["revision"] == result["revision"]
    assert len(persisted["attempts"]) == 1
    assert "private executor failure" not in json.dumps(result)
    manager.asset(state["id"], "employee-a", "item", result["items"][0]["id"], download=True)
    manager.download(state["id"], "employee-a")


def test_discard_restore_and_legacy_statuses_have_honest_download_qualification(refinement):
    manager, _, state = refinement
    item = state["items"][0]
    discarded = manager.resolve(state["id"], "employee-a", {"expected_revision": state["revision"], "item_id": item["id"], "action": "skip"})
    assert discarded["stats"]["downloadable"] == 0 and discarded["items"][0]["downloadable"] is False
    with pytest.raises(Conflict):
        manager.asset(state["id"], "employee-a", "item", item["id"], download=True)
    restored = manager.resolve(state["id"], "employee-a", {"expected_revision": discarded["revision"], "item_id": item["id"], "action": "restore"})
    assert restored["items"][0]["status"] == "generated" and "review" not in restored["items"][0]
    for status in ("needs_review", "ready", "confirmed"):
        job = manager.jobs[state["id"]]; job["items"][0]["status"] = status; manager._save(job)
        assert manager.snapshot(state["id"], "employee-a")["items"][0]["downloadable"]
        manager.asset(state["id"], "employee-a", "item", item["id"], download=True)


def test_batch_failures_stay_source_scoped_not_repeated_on_every_item(refinement):
    manager, provider, _ = refinement
    original = provider.extract
    def partial(raw, **kwargs):
        result = original(raw, **kwargs)
        result.warnings = ("第 2 个设计未能生成：服务繁忙。",)
        result.layers[0].warnings = ("本项需要核对文字。",)
        return result
    provider.extract = partial
    result = complete(manager, upload(manager))
    assert "第 2 个设计" in result["sources"][0]["warnings"][0]
    assert "第 2 个设计" not in " ".join(result["items"][0]["warnings"])
    assert "本项需要核对文字" in " ".join(result["items"][0]["warnings"])


def test_restarted_refinement_keeps_unknown_charge_acknowledgement_and_old_download(refinement):
    manager, provider, state = refinement
    job = manager.jobs[state["id"]]
    item = job["items"][0]
    job.update(status="processing", expires_at=None)
    job["sources"][0]["status"] = "processing"
    job["attempts"].append({"operation": "refine", "item_id": item["id"],
        "source_id": item["source_id"], "state": "submitted", "usage": {}, "number": 1})
    manager._save(job)
    manager.close()
    reopened = MaterialManager(manager.data_dir, Settings(), cloud=True, provider_factory=lambda config: provider)
    try:
        recovered = reopened.snapshot(state["id"], "employee-a")
        assert recovered["items"][0]["refine_submission_unknown"] is True
        assert recovered["items"][0]["downloadable"] and provider.calls == 1
        with pytest.raises(Conflict, match="可能重复计费"):
            refine(reopened, recovered)
    finally:
        reopened.close()


def test_refinement_needs_only_image_service_not_deepseek(refinement):
    manager, provider, state = refinement
    class DisabledDeepseek:
        def runtime(self):
            return {"enabled": False, "api_key": ""}
    manager.ai_settings = DisabledDeepseek()
    assert manager._deepseek_available() is False
    refine(manager, state)
    assert complete(manager, state["id"])["items"][0]["refined"]
    assert provider.calls == 2


def test_a_refinement_publishes_the_item_it_is_working_on(refinement):
    """The page needs to know which card is being redrawn to stay usable."""
    manager, provider, state = refinement
    item_id = state["items"][0]["id"]
    refine(manager, state)
    saved = manager.jobs[state["id"]]
    assert saved["status"] in {"queued", "processing"}
    assert saved["progress"]["item_id"] == item_id
    current = complete(manager, state["id"])
    assert current["status"] == "ready"
    # The marker only means "working on this card": the page ignores it once the
    # batch is no longer running, and a new upload clears it on the server.
    assert current["progress"]["stage_code"] != "refining"
    assert current["items"][0]["refined"] is True


def test_a_rectangle_redo_never_claims_to_be_a_refinement(refinement):
    manager, provider, state = refinement
    source = state["sources"][0]
    manager.redo(state["id"], "employee-a", {"expected_revision": state["revision"],
        "source_id": source["id"], "box": {"x": 0, "y": 0, "width": 12, "height": 12}})
    assert manager.jobs[state["id"]]["progress"]["item_id"] == ""
    complete(manager, state["id"])


def test_refining_one_design_keeps_the_other_results_downloadable(tmp_path):
    from test_material_service import upload_two
    provider = Provider()
    manager = MaterialManager(tmp_path, Settings(), cloud=True, provider_factory=lambda config: provider)
    try:
        state = upload_two(manager)
        assert len(state["items"]) == 2
        provider.entered.clear()
        provider.block = True
        manager.refine(state["id"], "employee-a", {"expected_revision": state["revision"],
                                                   "item_id": state["items"][0]["id"]})
        assert provider.entered.wait(10)
        # The batch is busy, but the second, finished design is still usable.
        live = manager.snapshot(state["id"], "employee-a")
        assert live["status"] in {"queued", "processing"}
        rows = {row["id"]: row for row in live["items"]}
        other = state["items"][1]["id"]
        assert rows[other]["downloadable"] and rows[other]["download_url"]
        assert live["stats"]["downloadable"] >= 1
        path, digest = manager.asset(state["id"], "employee-a", "item", other, download=True)
        assert path.is_file() and len(digest) == 64
        archive, _ = manager.download(state["id"], "employee-a")
        assert archive.is_file()
    finally:
        provider.block = False
        provider.release.set()
        manager.close()
