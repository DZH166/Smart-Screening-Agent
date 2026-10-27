"""Deterministic timing/lifecycle controls, not image-quality validation."""
from concurrent.futures import Future
from copy import deepcopy
from io import BytesIO

import pytest
from PIL import Image
from werkzeug.datastructures import FileStorage, MultiDict

from hsd_tool.material_ark import ArkLayer, ArkResult
from hsd_tool.material_service import MaterialManager
from test_material_service import Provider, Settings, png, upload


class Clock:
    def __init__(self):
        self.now = 1_000_000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class ManualExecutor:
    """Control acceptance versus execution without sleeps or background races."""
    def __init__(self):
        self.pending = []

    def submit(self, function, *args):
        future = Future()
        self.pending.append((future, function, args))
        return future

    def run_next(self):
        future, function, args = self.pending.pop(0)
        future.set_running_or_notify_cancel()
        try:
            future.set_result(function(*args))
        except BaseException as exc:
            future.set_exception(exc)
        return future.result()

    def shutdown(self, **kwargs):
        # Pending work can deliberately represent a process interruption.
        pass


@pytest.fixture
def controlled(tmp_path):
    clock, provider = Clock(), Provider()
    original = provider.extract

    def small_output(*args, **kwargs):
        result = original(*args, **kwargs)
        result.no_upscale = True
        return result

    provider.extract = small_output
    manager = MaterialManager(tmp_path, Settings(), cloud=True, clock=clock,
                              provider_factory=lambda config: provider)
    manager.executor.shutdown(wait=True)
    manager.executor = ManualExecutor()
    yield manager, provider, clock
    manager.close()


def snapshot(manager, identifier):
    return manager.snapshot(identifier, "employee-a")


def finish(manager, identifier):
    manager.executor.run_next()
    return snapshot(manager, identifier)


def test_batch_clock_spans_queue_stages_design_updates_and_multiple_sources(controlled):
    manager, provider, clock = controlled
    original = provider.extract
    provider.supports_progress = True
    records = []

    def staged(raw, **kwargs):
        for stage, completed, total in [("cleanup", None, None), ("locating", None, None),
                                        ("designs", 0, 41), ("designs", 39, 41),
                                        ("designs", 41, 41), ("complete", None, None)]:
            clock.advance(3)
            kwargs["on_progress"](stage, current=completed, total=total)
            records.append(snapshot(manager, identifier))
        return original(raw, **kwargs)

    provider.extract = staged
    files = MultiDict([("files", FileStorage(BytesIO(png()), filename=f"{i}.png")) for i in range(2)])
    identifier = manager.receive(files, MultiDict(), owner="employee-a")
    accepted = snapshot(manager, identifier)
    clock.advance(7)
    assert snapshot(manager, identifier)["progress"]["task_elapsed_seconds"] == 7
    result = finish(manager, identifier)
    assert result["status"] == "ready" and len(result["items"]) == 2
    progress = [record["progress"] for record in records]
    assert [p["task_elapsed_seconds"] for p in progress] == list(range(10, 44, 3))
    assert {p["run_id"] for p in progress} == {accepted["progress"]["run_id"]}
    assert {p["run_started_at"] for p in progress} == {1_000_000.0}
    assert progress[3]["designs_completed"] == 39 and progress[3]["designs_total"] == 41
    assert progress[5]["stage_code"] == "saving" and progress[5]["designs_completed"] == 41
    assert progress[6]["source_id"] != progress[5]["source_id"]
    assert "designs_total" not in progress[6]  # Next original has an unknown total.
    assert progress[6]["current"] == 1 and progress[6]["total"] == 2
    assert result["progress"]["task_elapsed_seconds"] == 43
    clock.advance(100)
    assert snapshot(manager, identifier)["progress"]["task_elapsed_seconds"] == 43


def test_out_of_order_design_counts_do_not_regress_and_new_source_clears_counts(controlled):
    manager, _, clock = controlled
    identifier = upload(manager)
    job = manager.jobs[identifier]
    source = job["sources"][0]["id"]
    manager._progress(job, "designs", source_id=source, done=39, of=41)
    started_at = job["progress"]["started_at"]
    clock.advance(5)
    manager._progress(job, "designs", source_id=source, done=38, of=41)
    assert job["progress"]["designs_completed"] == 39
    assert job["progress"]["started_at"] == started_at
    manager._progress(job, "saving", source_id=source)
    assert job["progress"]["designs_completed"] == 39
    manager._progress(job, "source_done", source_id=source)
    assert job["progress"]["designs_total"] == 41
    manager._progress(job, "preparing", source_id="another-source")
    assert "designs_total" not in job["progress"]
    manager._progress(job, "designs", source_id="another-source", done=0, of=3)
    assert job["progress"]["designs_completed"] == 0 and job["progress"]["designs_total"] == 3


@pytest.mark.parametrize("action", ["confirm", "skip", "batch_undo"])
def test_review_and_retention_touches_never_extend_finished_processing_time(controlled, action):
    manager, _, clock = controlled
    identifier = upload(manager)
    clock.advance(13)
    result = finish(manager, identifier)
    run_id = result["progress"]["run_id"]
    finished_at = manager.jobs[identifier]["run_finished_at"]
    first_expiry = manager.jobs[identifier]["expires_at"]
    clock.advance(100)
    if action == "batch_undo":
        result = manager.resolve_batch(identifier, "employee-a", {
            "expected_revision": result["revision"], "item_ids": [result["items"][0]["id"]]})
        assert result["progress"]["task_elapsed_seconds"] == 13
        clock.advance(200)
        result = manager.undo_batch(identifier, "employee-a", {"expected_revision": result["revision"]})
        assert result["stats"]["downloadable"] == 1 and result["items"][0]["status"] == "generated"
    else:
        result = manager.resolve(identifier, "employee-a", {"expected_revision": result["revision"],
            "item_id": result["items"][0]["id"], "action": action})
    assert manager.jobs[identifier]["expires_at"] > first_expiry
    assert manager.jobs[identifier]["run_finished_at"] == finished_at
    assert result["progress"]["run_id"] == run_id
    assert result["progress"]["task_elapsed_seconds"] == 13
    clock.advance(400)
    assert snapshot(manager, identifier)["progress"]["task_elapsed_seconds"] == 13


def test_redo_starts_a_new_run_at_acceptance_and_includes_queue_wait(controlled):
    manager, _, clock = controlled
    identifier = upload(manager)
    clock.advance(13)
    before = finish(manager, identifier)
    clock.advance(100)
    after = manager.redo(identifier, "employee-a", {"expected_revision": before["revision"],
        "source_id": before["sources"][0]["id"], "box": {"x": 0, "y": 0, "width": 32, "height": 24}})
    assert after["status"] == "queued"
    assert after["progress"]["run_id"] != before["progress"]["run_id"]
    assert after["progress"]["run_started_at"] == clock()
    assert after["progress"]["task_elapsed_seconds"] == 0
    assert manager.jobs[identifier]["run_finished_at"] is None
    assert "designs_total" not in after["progress"]
    clock.advance(8)
    assert snapshot(manager, identifier)["progress"]["task_elapsed_seconds"] == 8
    final = finish(manager, identifier)
    assert final["progress"]["run_id"] == after["progress"]["run_id"]
    assert final["progress"]["task_elapsed_seconds"] == 8


def test_queued_cancel_freezes_only_when_accepted_work_has_settled(controlled):
    manager, provider, clock = controlled
    identifier = upload(manager)
    clock.advance(5)
    current = snapshot(manager, identifier)
    cancelled = manager.cancel(identifier, "employee-a", current["revision"])
    assert cancelled["status"] == "cancelling"
    assert manager.jobs[identifier]["run_finished_at"] is None
    clock.advance(4)
    assert snapshot(manager, identifier)["progress"]["task_elapsed_seconds"] == 9
    final = finish(manager, identifier)
    assert final["status"] == "cancelled" and provider.calls == 0
    assert final["progress"]["task_elapsed_seconds"] == 9
    clock.advance(100)
    assert snapshot(manager, identifier)["progress"]["task_elapsed_seconds"] == 9


@pytest.mark.parametrize("interrupted_state", ["queued", "processing", "cancelling"])
def test_interrupted_restore_records_terminal_time_once_without_resubmission(controlled, interrupted_state):
    manager, provider, clock = controlled
    identifier = upload(manager)
    accepted = snapshot(manager, identifier)
    job = manager.jobs[identifier]
    job["status"] = interrupted_state
    job["sources"][0]["status"] = "processing" if interrupted_state != "queued" else "queued"
    manager._save(job)
    manager.close()
    clock.advance(20)
    reopened = MaterialManager(manager.data_dir, manager.settings, cloud=True, clock=clock,
                               provider_factory=lambda config: provider)
    try:
        restored = snapshot(reopened, identifier)
        assert restored["status"] == "error" and provider.calls == 0
        assert restored["progress"]["run_id"] == accepted["progress"]["run_id"]
        assert restored["progress"]["task_elapsed_seconds"] == 20
        persisted = deepcopy(reopened._read(reopened._directory(identifier)))
        assert persisted["run_finished_at"] == clock()
        clock.advance(90)
        assert snapshot(reopened, identifier)["progress"]["task_elapsed_seconds"] == 20
        assert reopened._read(reopened._directory(identifier)) == persisted
    finally:
        reopened.close()


def test_service_preserves_native_canvas_soft_alpha_and_separate_edge_details(controlled):
    manager, provider, _ = controlled
    native = Image.new("RGBA", (128, 96), (8, 12, 16, 0))
    native.paste((90, 140, 220, 255), (40, 20, 80, 70))
    # White ornament, detached shoe/text pixels and soft edges must survive.
    for point, rgba in [((0, 0), (255, 255, 255, 255)), ((127, 95), (1, 2, 3, 128)),
                        ((15, 80), (20, 30, 40, 1)), ((100, 10), (230, 240, 250, 200))]:
        native.putpixel(point, rgba)
    buffer = BytesIO()
    native.save(buffer, "PNG")
    result = ArkResult(
        layers=(ArkLayer(buffer.getvalue(), "完整设计", "合成画布保存测试",
                         {"x": 0, "y": 0, "width": 32, "height": 24}, 1),),
        usage={"images": 1}, warnings=(), base_png=b"", base_size=(32, 24),
        rectangular_crops=True, no_upscale=True)
    provider.extract = lambda *args, **kwargs: result
    # Even an unrelated quality hook cannot grant native material auto-pass.
    manager.quality_hook = lambda *args, **kwargs: {"auto_ready": True, "warnings": [], "evidence": {}}
    identifier = upload(manager)
    completed = finish(manager, identifier)
    item = completed["items"][0]
    assert (item["width"], item["height"]) == native.size
    assert (item["native_width"], item["native_height"]) == native.size
    assert item["status"] == "generated" and completed["download_url"] and "review" not in item
    assert not any("4096" in warning for warning in item["warnings"])
    internal_item = manager.jobs[identifier]["items"][0]
    assert internal_item["evidence"] == {"version": "material-preserved-canvas-1",
                                         "scope": "unverified_generated_content"}
    stored, _ = manager.asset(identifier, "employee-a", "item", item["id"])
    with Image.open(stored) as saved:
        assert saved.mode == "RGBA" and saved.size == native.size
        assert saved.tobytes() == native.tobytes()
