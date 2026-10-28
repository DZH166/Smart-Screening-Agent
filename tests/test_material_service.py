"""Synthetic task/lifecycle controls; these do not validate generated quality."""
from io import BytesIO
import json
from pathlib import Path
from types import SimpleNamespace
import threading
import time
import zipfile

import pytest
from PIL import Image
from werkzeug.datastructures import FileStorage, MultiDict
from werkzeug.exceptions import Conflict

from hsd_tool.material_service import MaterialManager
from hsd_tool.material_ark import ArkProviderError


def png(color=(200, 20, 30, 255), size=(32, 24)):
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    image.paste(color, (4, 4, size[0] - 4, size[1] - 4))
    result = BytesIO(); image.save(result, "PNG")
    return result.getvalue()


class Settings:
    enabled = True
    def runtime(self):
        return {"enabled": self.enabled, "ark_key": "synthetic-private-key", "model_id": "synthetic-model"}
    def snapshot(self):
        return {"enabled": self.enabled, "configured": True, "model_id": "synthetic-model"}


class Provider:
    def __init__(self):
        self.calls = 0
        self.entered, self.release = threading.Event(), threading.Event()
        self.block = False
        self.failures = []
        self.edit_raw = None

    def extract(self, raw, **kwargs):
        self.calls += 1
        self.entered.set()
        if self.block:
            assert self.release.wait(10)
        if self.failures:
            raise self.failures.pop(0)
        kwargs["check_cancel"]()
        return SimpleNamespace(layers=(SimpleNamespace(png=png(), label="完整设计", warnings=("测试生成保真未验证",),
                     bounds={"x": 0, "y": 0, "width": 32, "height": 24}),),
                     warnings=(), usage={"images": 1}, request_id="synthetic-request")

    def edit(self, raw, **kwargs):
        self.edit_raw = raw
        return self.extract(raw, **kwargs)

    def refine(self, raw, **kwargs):
        self.edit_raw = raw
        return self.extract(raw, **kwargs)


@pytest.fixture
def service(tmp_path):
    provider = Provider()
    manager = MaterialManager(tmp_path, Settings(), cloud=True, provider_factory=lambda config: provider)
    yield manager, provider
    provider.release.set()
    manager.close()


def upload(manager, *, owner="employee-a", name="画稿.png", data=None):
    files = MultiDict([("files", FileStorage(BytesIO(png() if data is None else data), filename=name))])
    return manager.receive(files, MultiDict(), owner=owner)


def complete(manager, identifier):
    manager.futures[identifier].result(20)
    return manager.snapshot(identifier, "employee-a")


def test_generated_proposal_downloads_without_claiming_employee_or_quality_review(service):
    manager, provider = service
    result = complete(manager, upload(manager))
    assert result["status"] == "ready"
    assert result["stats"] == {"total": 1, "ready": 0, "downloadable": 1, "needs_review": 0, "skipped": 0, "failed": 0}
    assert result["download_url"]
    item = result["items"][0]
    assert max(item["width"], item["height"]) == 4096
    assert "放大不等于恢复" in " ".join(item["warnings"])
    assert item["status"] == "generated" and item["downloadable"] is True and "review" not in item
    manager.asset(result["id"], "employee-a", "item", item["id"], download=True)
    manager.download(result["id"], "employee-a")
    assert "review" not in manager.jobs[result["id"]]["items"][0]
    updated = manager.resolve(result["id"], "employee-a", {"expected_revision": result["revision"], "item_id": item["id"], "action": "confirm"})
    assert updated["stats"]["ready"] == 1
    path, digest = manager.download(result["id"], "employee-a")
    with zipfile.ZipFile(path) as archive:
        assert len(archive.namelist()) == 2
        notes = json.loads(archive.read("素材说明.json"))
        assert notes["items"][0]["warnings"]
    assert len(digest) == 64
    assert "synthetic-private-key" not in (manager._directory(result["id"]) / "manifest.json").read_text()


def test_owner_isolation_including_same_name_uploads(service):
    manager, _ = service
    result = complete(manager, upload(manager))
    with pytest.raises(KeyError):
        manager.snapshot(result["id"], "employee-b")
    with pytest.raises(KeyError):
        manager.asset(result["id"], "employee-b", "source", result["sources"][0]["id"])
    assert manager.config("employee-b")["active_job_id"] is None


def test_skip_is_not_still_review_and_revision_conflict(service):
    manager, _ = service
    result = complete(manager, upload(manager)); item = result["items"][0]
    payload = {"expected_revision": result["revision"], "item_id": item["id"], "action": "skip"}
    updated = manager.resolve(result["id"], "employee-a", payload)
    assert updated["stats"]["needs_review"] == 0
    assert updated["stats"]["skipped"] == 1
    with pytest.raises(Conflict):
        manager.resolve(result["id"], "employee-a", payload)


def test_stop_waits_for_sent_call_and_does_not_start_next_source(service):
    manager, provider = service
    provider.block = True
    files = MultiDict([("files", FileStorage(BytesIO(png()), filename=f"{i}.png")) for i in range(2)])
    identifier = manager.receive(files, MultiDict(), owner="employee-a")
    assert provider.entered.wait(10)
    result = manager.snapshot(identifier, "employee-a")
    stopped = manager.cancel(identifier, "employee-a", result["revision"])
    assert stopped["status"] == "cancelling"
    assert not manager.futures[identifier].done()
    provider.release.set()
    assert complete(manager, identifier)["status"] == "cancelled"
    assert provider.calls == 1


def test_definite_failure_retries_once_unknown_submission_never_retries(service):
    manager, provider = service
    provider.failures = [ArkProviderError("rate_limit", "safe", retryable=True, settled=True)]
    assert complete(manager, upload(manager))["status"] == "ready"
    assert provider.calls == 2
    provider.failures = [ArkProviderError("submission_unknown", "private upstream text", settled=False)]
    result = complete(manager, upload(manager))
    assert result["status"] == "error"
    assert provider.calls == 3
    assert "未自动重发" in result["sources"][0]["error"]
    assert "private upstream text" not in json.dumps(result)


@pytest.mark.parametrize("name,data", [("bad.svg", b"<svg/>"), ("x.png", b"broken"), ("x.gif", b"GIF89a")])
def test_invalid_inputs_never_call_provider(service, name, data):
    manager, provider = service
    with pytest.raises(ValueError):
        upload(manager, name=name, data=data)
    assert provider.calls == 0
    assert list(manager.upload_root.iterdir()) == []


def test_disabled_service_does_not_submit(service):
    manager, provider = service
    manager.settings.enabled = False
    with pytest.raises(ValueError, match="尚未开启"):
        upload(manager)
    assert provider.calls == 0


def test_source_and_output_changes_block_export(service):
    manager, _ = service
    result = complete(manager, upload(manager)); item = result["items"][0]
    manager.resolve(result["id"], "employee-a", {"expected_revision": result["revision"], "item_id": item["id"], "action": "confirm"})
    path = manager._directory(result["id"]) / (item["id"] + ".png")
    path.write_bytes(b"changed")
    with pytest.raises(ValueError, match="发生变化"):
        manager.download(result["id"], "employee-a")


def test_retention_lease_and_signed_ownership(service):
    manager, _ = service
    result = complete(manager, upload(manager)); identifier = result["id"]
    release = manager.acquire(identifier, "employee-a")
    manager.clock = lambda: time.time() + 4 * 86400
    assert manager.retention_sweep() == []
    release(); release()
    assert manager.retention_sweep() == [identifier]
    assert not manager._directory(identifier).exists()


def test_cloud_abandoned_upload_cleanup_requires_signature_and_no_live_lease(service):
    manager, _ = service
    directory = manager.begin_upload(owner="employee-a")
    (directory / "part-test").write_bytes(b"synthetic partial upload")
    manager.clock = lambda: time.time() + 4 * 86400
    assert manager.retention_sweep() == []
    manager.upload_leases.discard(directory.name)  # Simulated interrupted process.
    assert manager.retention_sweep() == []  # Retention starts after idle is proven.
    manager.clock = lambda: time.time() + 8 * 86400
    assert manager.retention_sweep() == ["upload:" + directory.name]
    assert not directory.exists()
    unproven = manager.upload_root / ("f" * 32)
    unproven.mkdir(); (unproven / "data").write_bytes(b"unknown owner")
    assert manager.retention_sweep() == []
    assert unproven.exists()


def test_a_manifest_from_the_three_day_window_expires_under_the_shorter_one(service):
    """The window is policy: old records must not outlive the new promise."""
    from hsd_tool.retention_window import RETENTION_SECONDS
    manager, _ = service
    result = complete(manager, upload(manager)); identifier = result["id"]
    job = manager.jobs[identifier]
    settled = job.get("settled_at")
    assert isinstance(settled, float) and settled > 0
    job["expires_at"] = settled + 3 * 86400          # what v1.19.3 would have written
    manager._save(job)
    manager.clock = lambda: settled + RETENTION_SECONDS - 60
    assert manager.retention_sweep() == []
    manager.clock = lambda: settled + RETENTION_SECONDS + 1
    assert manager.retention_sweep() == [identifier]
    assert not manager._directory(identifier).exists()


def test_tampered_manifest_is_never_deleted_or_resigned(service):
    manager, _ = service
    result = complete(manager, upload(manager)); identifier = result["id"]
    path = manager._directory(identifier) / "manifest.json"
    original = path.read_bytes()
    document = json.loads(original); document["payload"]["expires_at"] = 1
    path.write_text(json.dumps(document))
    tampered = path.read_bytes()
    # Before expiry, the signature check independently blocks a write. After
    # expiry, the task must also stay unreadable and conservative cleanup must
    # preserve the untrusted manifest rather than re-sign or delete it.
    with pytest.raises(ValueError):
        manager.resolve(identifier, "employee-a", {"expected_revision": result["revision"], "item_id": result["items"][0]["id"], "action": "confirm"})
    assert path.read_bytes() == tampered
    manager.clock = lambda: time.time() + 4 * 86400
    with pytest.raises(KeyError, match="已过期"):
        manager.snapshot(identifier, "employee-a")
    assert manager.retention_sweep() == []
    assert path.read_bytes() == tampered != original


def test_reopen_same_implementation_restores_same_owner_only(service):
    manager, provider = service
    result = complete(manager, upload(manager))
    manager.close()
    reopened = MaterialManager(manager.data_dir, manager.settings, cloud=True,
                               provider_factory=lambda config: provider)
    try:
        assert reopened.snapshot(result["id"], "employee-a")["items"] == result["items"]
        with pytest.raises(KeyError):
            reopened.snapshot(result["id"], "other-browser")
        assert provider.calls == 1
    finally:
        reopened.close()


def test_reopened_signed_upload_claim_prevents_paid_replay(service):
    from hsd_tool.cloud_tasks import UploadClaims
    manager, provider = service
    request_id = "1" * 32
    files = MultiDict([("files", FileStorage(BytesIO(png()), filename="image.png"))])
    identifier = manager.receive(files, MultiDict(), owner="employee-a", upload_request_id=request_id)
    complete(manager, identifier)
    manager.close()
    reopened = MaterialManager(manager.data_dir, manager.settings, cloud=True, provider_factory=lambda config: provider)
    try:
        claims = UploadClaims(); reopened.restore_upload_claims(claims)
        assert claims.reserve(request_id, "employee-a") == {"state": "completed", "job_id": identifier}
        with pytest.raises(KeyError):
            claims.reserve(request_id, "employee-b")
        assert provider.calls == 1
    finally:
        reopened.close()


def test_interrupted_submitted_call_restores_unknown_source_without_resubmitting(service):
    manager, provider = service
    result = complete(manager, upload(manager))
    job = manager.jobs[result["id"]]
    job.update(status="processing", settled_at=None, expires_at=None)
    job["sources"][0]["status"] = "processing"
    job["attempts"][-1]["state"] = "submitted"
    manager._save(job)
    manager.close()
    reopened = MaterialManager(manager.data_dir, manager.settings, cloud=True, provider_factory=lambda config: provider)
    try:
        restored = reopened.snapshot(result["id"], "employee-a")
        assert restored["status"] == "error"
        assert restored["sources"][0]["status"] == "error"
        assert restored["sources"][0]["submission_unknown"] is True
        assert provider.calls == 1
        with pytest.raises(Conflict, match="可能重复计费"):
            reopened.redo(result["id"], "employee-a", {"expected_revision": restored["revision"], "source_id": restored["sources"][0]["id"]})
    finally:
        reopened.close()


def test_expired_task_cannot_be_opened_or_restored(service):
    manager, provider = service
    result = complete(manager, upload(manager))
    later = lambda: time.time() + 4 * 86400
    manager.clock = later
    with pytest.raises(KeyError, match="已过期"):
        manager.snapshot(result["id"], "employee-a")
    assert manager.config("employee-a")["active_job_id"] is None
    manager.close()
    reopened = MaterialManager(manager.data_dir, manager.settings, cloud=True,
                               provider_factory=lambda config: provider, clock=later)
    try:
        assert result["id"] not in reopened.jobs
        assert reopened.retention_sweep() == [result["id"]]
    finally:
        reopened.close()


def test_unknown_submission_requires_explicit_acknowledgement_before_redo(service):
    manager, provider = service
    provider.failures = [ArkProviderError("submission_unknown", "hidden", settled=False)]
    result = complete(manager, upload(manager))
    assert result["sources"][0]["submission_unknown"] is True
    payload = {"expected_revision": result["revision"], "source_id": result["sources"][0]["id"]}
    with pytest.raises(Conflict, match="可能重复计费"):
        manager.redo(result["id"], "employee-a", payload)
    assert provider.calls == 1
    manager.redo(result["id"], "employee-a", {**payload, "acknowledge_unknown": True})
    assert complete(manager, result["id"])["status"] == "ready"
    assert provider.calls == 2


def test_redo_edits_verified_transparent_result_and_preserves_source_bounds(service):
    manager, provider = service
    result = complete(manager, upload(manager)); item = result["items"][0]
    updated = manager.redo(result["id"], "employee-a", {"expected_revision": result["revision"],
         "source_id": item["source_id"], "item_id": item["id"], "instruction": "清理边缘",
         "box": {"x": 8, "y": 8, "width": 8, "height": 8}})
    assert updated["status"] in {"queued", "processing"}
    final = complete(manager, result["id"])
    assert len(final["items"]) == 1
    assert final["items"][0]["bounds"] == item["bounds"]
    with Image.open(BytesIO(provider.edit_raw)) as image:
        assert max(image.size) == 4096
        assert image.getchannel("A").getextrema()[0] < 255


def upload_two(manager):
    files = MultiDict([("files", FileStorage(BytesIO(png()), filename=f"{i}.png")) for i in range(2)])
    return complete(manager, manager.receive(files, MultiDict(), owner="employee-a"))


def test_batch_confirm_is_explicit_employee_decision_and_undo_is_atomic(service):
    manager, _ = service
    result = upload_two(manager)
    identifiers = [row["id"] for row in result["items"]]
    updated = manager.resolve_batch(result["id"], "employee-a", {
        "expected_revision": result["revision"], "item_ids": identifiers})
    assert updated["revision"] == result["revision"] + 1
    assert updated["stats"]["ready"] == 2 and updated["stats"]["needs_review"] == 0
    assert updated["can_undo_batch"] is True
    assert all(row["status"] == "confirmed" and row["review"]["method"] == "employee_batch" for row in updated["items"])
    assert [row["warnings"] for row in updated["items"]] == [row["warnings"] for row in result["items"]]
    restored = manager.undo_batch(result["id"], "employee-a", {"expected_revision": updated["revision"]})
    assert restored["stats"]["ready"] == 0 and restored["stats"]["downloadable"] == 2
    assert restored["can_undo_batch"] is False
    assert all("review" not in row for row in restored["items"])
    with pytest.raises(Conflict):
        manager.undo_batch(result["id"], "employee-a", {"expected_revision": restored["revision"]})


@pytest.mark.parametrize("problem", ["source", "output", "already_confirmed", "duplicate", "other_owner", "old_revision", "missing"])
def test_batch_failure_never_confirms_other_selected_rows(service, problem):
    manager, _ = service
    result = upload_two(manager)
    identifiers = [row["id"] for row in result["items"]]
    owner, revision = "employee-a", result["revision"]
    if problem == "source":
        (manager._directory(result["id"]) / (result["items"][1]["source_id"] + ".png")).write_bytes(b"changed")
    elif problem == "output":
        (manager._directory(result["id"]) / (identifiers[1] + ".png")).write_bytes(b"changed")
    elif problem == "already_confirmed":
        modified = manager.resolve(result["id"], owner, {"expected_revision": revision, "item_id": identifiers[1], "action": "confirm"})
        revision = modified["revision"]
    elif problem == "duplicate":
        identifiers = [identifiers[0], identifiers[0]]
    elif problem == "other_owner":
        owner = "employee-b"
    elif problem == "old_revision":
        revision -= 1
    elif problem == "missing":
        identifiers[1] = "f" * 32
    before = (manager._directory(result["id"]) / "manifest.json").read_bytes()
    with pytest.raises((KeyError, ValueError, Conflict)):
        manager.resolve_batch(result["id"], owner, {"expected_revision": revision, "item_ids": identifiers})
    assert manager.snapshot(result["id"], "employee-a")["items"][0]["status"] == "generated"
    assert (manager._directory(result["id"]) / "manifest.json").read_bytes() == before


def test_batch_save_failure_does_not_publish_success_and_retry_still_works(service, monkeypatch):
    manager, _ = service
    result = upload_two(manager)
    payload = {"expected_revision": result["revision"], "item_ids": [row["id"] for row in result["items"]]}
    original = manager._write
    def fail_manifest(path, raw):
        if path.name == "manifest.json":
            raise OSError("synthetic disk full")
        return original(path, raw)
    monkeypatch.setattr(manager, "_write", fail_manifest)
    with pytest.raises(OSError):
        manager.resolve_batch(result["id"], "employee-a", payload)
    assert manager.snapshot(result["id"], "employee-a")["stats"]["downloadable"] == 2
    assert manager.snapshot(result["id"], "employee-a")["revision"] == result["revision"]
    monkeypatch.setattr(manager, "_write", original)
    assert manager.resolve_batch(result["id"], "employee-a", payload)["stats"]["ready"] == 2


def test_single_correction_invalidates_batch_undo(service):
    manager, _ = service
    result = upload_two(manager)
    updated = manager.resolve_batch(result["id"], "employee-a", {
        "expected_revision": result["revision"], "item_ids": [row["id"] for row in result["items"]]})
    changed = manager.resolve(result["id"], "employee-a", {
        "expected_revision": updated["revision"], "item_id": result["items"][0]["id"], "action": "skip"})
    assert changed["can_undo_batch"] is False
    with pytest.raises(Conflict):
        manager.undo_batch(result["id"], "employee-a", {"expected_revision": changed["revision"]})
    assert manager.snapshot(result["id"], "employee-a")["stats"]["skipped"] == 1


def test_stage_stream_tracks_real_work_and_completed_sources_arrive_incrementally(service):
    manager, provider = service
    provider.supports_progress = True
    cleanup, locate = threading.Event(), threading.Event()
    release_cleanup, release_locate = threading.Event(), threading.Event()
    old_extract = provider.extract
    counter = 0
    def staged(raw, **kwargs):
        nonlocal counter
        counter += 1
        kwargs["on_progress"]("cleanup", "not forwarded: raw provider text")
        kwargs["on_attempt"]({"id": f"attempt-{counter}", "provider": "seedream", "operation": "cleanup", "state": "submitted", "usage": {}})
        if counter == 1:
            cleanup.set(); assert release_cleanup.wait(10)
        kwargs["on_progress"]("locating", "not forwarded")
        if counter == 2:
            locate.set(); assert release_locate.wait(10)
        result = old_extract(raw, **kwargs)
        kwargs["on_attempt"]({"id": f"attempt-{counter}", "provider": "seedream", "state": "returned", "usage": {"images": 1}, "settled": True})
        return result
    provider.extract = staged
    files = MultiDict([("files", FileStorage(BytesIO(png()), filename=f"{i}.png")) for i in range(2)])
    identifier = manager.receive(files, MultiDict(), owner="employee-a")
    try:
        assert cleanup.wait(10)
        snapshot = manager.snapshot(identifier, "employee-a")
        assert snapshot["progress"]["stage_code"] == "cleanup"
        assert snapshot["progress"]["indeterminate"] is True
        assert "not forwarded" not in json.dumps(snapshot)
        assert snapshot["progress"]["current"] == 0
        assert snapshot["progress"]["total"] == 2
        # Merely waiting does not claim model progress or create new events.
        assert manager.snapshot(identifier, "employee-a")["update_seq"] == snapshot["update_seq"]
        release_cleanup.set(); assert locate.wait(10)
        during = manager.snapshot(identifier, "employee-a")
        assert during["status"] == "processing" and len(during["items"]) == 1
        assert during["progress"]["current"] == 1
        assert during["update_seq"] > snapshot["update_seq"]
        with pytest.raises(Conflict):
            manager.resolve_batch(identifier, "employee-a", {"expected_revision": during["revision"], "item_ids": [during["items"][0]["id"]]})
    finally:
        release_cleanup.set(); release_locate.set()
    final = complete(manager, identifier)
    assert final["progress"]["stage_code"] == "done" and len(final["items"]) == 2
    attempts = manager.jobs[identifier]["attempts"]
    assert len(attempts[0]["pipeline_attempts"]) == 1
    assert attempts[0]["pipeline_attempts"][0]["state"] == "returned"


def test_production_requires_enabled_deepseek_and_does_not_expose_credentials(tmp_path):
    class AiSettings:
        enabled = False
        def runtime(self):
            return {"enabled": self.enabled, "api_key": "never-public"}
    ai = AiSettings()
    manager = MaterialManager(tmp_path, Settings(), ai_settings=ai, provider_factory=lambda config: Provider())
    try:
        assert manager.config("employee-a")["available"] is False
        with pytest.raises(ValueError, match="DeepSeek"):
            upload(manager)
        ai.enabled = True
        assert manager.config("employee-a")["available"] is True
        assert "never-public" not in json.dumps(manager.config("employee-a"))
    finally:
        manager.close()


def test_new_pipeline_opaque_crops_are_not_mislabeled_transparent_or_auto_ready(service):
    manager, provider = service
    old = provider.extract
    def opaque(raw, **kwargs):
        result = old(raw, **kwargs)
        image = Image.new("RGBA", (40, 30), (255, 255, 255, 255))
        output = BytesIO(); image.save(output, "PNG")
        result.layers[0].png = output.getvalue()
        result.layers[0].warnings = ("此结果保留矩形范围内的背景，未做透明抠图。",)
        result.rectangular_crops = True
        return result
    provider.extract = opaque
    manager.quality_hook = lambda *args, **kwargs: {"auto_ready": True, "warnings": [], "evidence": {}}
    result = complete(manager, upload(manager))
    assert result["status"] == "ready" and result["stats"]["downloadable"] == 1
    item = result["items"][0]
    assert item["rectangular_crop"] is True and "未做透明抠图" in " ".join(item["warnings"])


def test_unexpected_sent_call_error_stays_unknown_for_manual_redo(service):
    manager, provider = service
    provider.failures = [RuntimeError("unknown after sending")]
    result = complete(manager, upload(manager))
    assert result["sources"][0]["submission_unknown"] is True
    assert "是否扣费尚未确定" in result["sources"][0]["error"]
    with pytest.raises(Conflict, match="可能重复计费"):
        manager.redo(result["id"], "employee-a", {"expected_revision": result["revision"],
                                                "source_id": result["sources"][0]["id"]})
    assert provider.calls == 1


def test_stop_during_local_output_save_does_not_publish_ready(service, monkeypatch):
    manager, _ = service
    entered, release = threading.Event(), threading.Event()
    original = manager._outputs
    def wait_to_publish(*args, **kwargs):
        results = original(*args, **kwargs)
        entered.set(); assert release.wait(10)
        return results
    monkeypatch.setattr(manager, "_outputs", wait_to_publish)
    identifier = upload(manager)
    try:
        assert entered.wait(10)
        snapshot = manager.snapshot(identifier, "employee-a")
        manager.cancel(identifier, "employee-a", snapshot["revision"])
    finally:
        release.set()
    final = complete(manager, identifier)
    assert final["status"] == "cancelled" and final["items"] == []
    assert final["sources"][0].get("submission_unknown") is not True


def test_material_availability_honors_shared_key_pool_pause_and_rejects_legacy_gateway(tmp_path):
    class AiSettings:
        gateway = False
        def runtime(self):
            return {"enabled": True, "api_key": "never-public", "via_gateway": self.gateway}
    class Pool:
        status = "paused_authentication"
        def snapshot(self):
            return {"keys": [{"status": self.status}]}
    ai, pool = AiSettings(), Pool()
    manager = MaterialManager(tmp_path, Settings(), ai_settings=ai, ai_key_pool=pool,
                              provider_factory=lambda config: Provider())
    try:
        assert not manager.config("employee-a")["available"]
        with pytest.raises(ValueError, match="DeepSeek"):
            upload(manager)
        pool.status = "available"
        assert manager.config("employee-a")["available"]
        ai.gateway = True
        assert not manager.config("employee-a")["available"]
        with pytest.raises(ValueError, match="DeepSeek"):
            upload(manager)
    finally:
        manager.close()


@pytest.mark.parametrize("failure_index", [1, 2], ids=["first-fails", "second-fails"])
@pytest.mark.parametrize("unknown", [False, True], ids=["settled", "unknown"])
def test_multisource_candidate_commit_keeps_later_source_state_and_failure_counts(service, failure_index, unknown):
    manager, provider = service
    original = provider.extract
    def staged(raw, **kwargs):
        if provider.calls + 1 == failure_index:
            provider.failures.append(ArkProviderError("submission_unknown" if unknown else "provider_busy",
                "private provider text", settled=not unknown, usage={"images": 1}))
        result = original(raw, **kwargs)
        result.no_upscale = result.rectangular_crops = True
        return result
    provider.extract = staged
    result = upload_two(manager)
    expected = ["error" if index == failure_index else "done" for index in (1, 2)]
    assert [source["status"] for source in result["sources"]] == expected
    assert result["status"] == "ready" and result["stats"]["failed"] == 1
    assert result["stats"]["downloadable"] == 1 and provider.calls == 2
    assert result["sources"][failure_index - 1]["submission_unknown"] is unknown
    assert result["sources"][2 - failure_index]["submission_unknown"] is False
    persisted = manager._read(manager._directory(result["id"]))
    assert [source["status"] for source in persisted["sources"]] == expected
    assert len(persisted["attempts"]) == 2
    assert persisted["attempts"][failure_index - 1]["state"] == ("unknown" if unknown else "failed")
    assert [item["source_id"] for item in result["items"]] == [result["sources"][2 - failure_index]["id"]]
