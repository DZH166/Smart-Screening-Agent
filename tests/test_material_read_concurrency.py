"""Synthetic read/ZIP isolation; never calls an image model."""
from io import BytesIO
from pathlib import Path
import threading
from types import SimpleNamespace
import zipfile

from PIL import Image
import pytest
from werkzeug.datastructures import FileStorage, MultiDict
from werkzeug.exceptions import Conflict

from hsd_tool import material_service as module
from hsd_tool.retention_window import RETENTION_SECONDS


def png(color=(240, 90, 120, 255)):
    image = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    image.paste(color, (5, 5, 27, 27))
    output = BytesIO(); image.save(output, "PNG"); image.close()
    return output.getvalue()


class Settings:
    def runtime(self):
        return {"enabled": True, "ark_key": "synthetic-placeholder", "model_id": "synthetic-model"}
    def snapshot(self):
        return {"enabled": True, "configured": True, "model_id": "synthetic-model"}


class Provider:
    def __init__(self):
        self.calls = 0
    def extract(self, raw, **kwargs):
        self.calls += 1
        return SimpleNamespace(no_upscale=True, warnings=(), usage={}, layers=[
            SimpleNamespace(png=png(), label="test", warnings=(), bounds={}) for _ in range(2)])
    def refine(self, raw, **kwargs):
        self.calls += 1
        return SimpleNamespace(no_upscale=True, warnings=(), usage={}, layers=[
            SimpleNamespace(png=png((10, 160, 90, 255)), label="refined", warnings=(), bounds={})])


@pytest.fixture
def service(tmp_path):
    provider = Provider()
    manager = module.MaterialManager(tmp_path, Settings(), cloud=True, provider_factory=lambda _: provider)
    manager._synthetic_provider = provider
    yield manager
    manager.close()


def completed(manager, owner="employee-a"):
    files = MultiDict([("files", FileStorage(BytesIO(png()), filename="synthetic.png"))])
    identifier = manager.receive(files, MultiDict(), owner=owner)
    manager.futures[identifier].result(10)
    return manager.snapshot(identifier, owner)


def pause_read(monkeypatch, path):
    entered, release = threading.Event(), threading.Event()
    original = module._digest
    def slow(value):
        if threading.current_thread().name == "material-reader" and Path(value) == path:
            entered.set()
            assert release.wait(5)
        return original(value)
    monkeypatch.setattr(module, "_digest", slow)
    return entered, release


def start(function):
    result, errors = [], []
    def execute():
        try:
            result.append(function())
        except BaseException as error:
            errors.append(error)
    thread = threading.Thread(target=execute, name="material-reader")
    thread.start()
    return thread, result, errors


@pytest.mark.parametrize("operation", ["asset", "download"])
def test_slow_read_does_not_block_other_employee_state_and_pins_retention(service, monkeypatch, operation):
    a, b = completed(service), completed(service, "employee-b")
    item = a["items"][0]
    path = service._directory(a["id"]) / (item["id"] + ".png")
    entered, release = pause_read(monkeypatch, path)
    call = (lambda: service.download(a["id"], "employee-a")) if operation == "download" else (
        lambda: service.asset(a["id"], "employee-a", "item", item["id"], thumbnail=True))
    thread, result, errors = start(call)
    try:
        assert entered.wait(3)
        assert service.leases[a["id"]] > 0
        # Completion while the I/O is still paused proves independent state is
        # not waiting on the global lock, without a machine-speed threshold.
        finished = threading.Event()
        other = threading.Thread(target=lambda: (service.snapshot(b["id"], "employee-b"), finished.set()))
        other.start()
        assert finished.wait(1)
        other.join(1)
        now = service.clock()
        service.clock = lambda: now + RETENTION_SECONDS + 10
        assert a["id"] not in service.retention_sweep()
        assert service._directory(a["id"]).exists()
    finally:
        release.set(); thread.join(5)
    assert not thread.is_alive() and result and not errors
    assert not service.leases and not service._packing


def test_asset_rechecks_source_changes_during_output_io(service, monkeypatch):
    state = completed(service); item = state["items"][0]
    path = service._directory(state["id"]) / (item["id"] + ".png")
    entered, release = pause_read(monkeypatch, path)
    thread, result, errors = start(lambda: service.asset(state["id"], "employee-a", "item", item["id"], thumbnail=True))
    try:
        assert entered.wait(3)
        source = service._directory(state["id"]) / (state["sources"][0]["id"] + ".png")
        source.write_bytes(png((1, 2, 3, 255)))
    finally:
        release.set(); thread.join(5)
    assert not result and isinstance(errors[0], ValueError)
    assert not service.leases


def test_asset_rechecks_current_and_previous_references(service, monkeypatch):
    state = completed(service)
    service.refine(state["id"], "employee-a", {"expected_revision": state["revision"], "item_id": state["items"][0]["id"]})
    service.futures[state["id"]].result(10)
    state = service.snapshot(state["id"], "employee-a")
    item = next(row for row in state["items"] if row["refined"])
    old = service.jobs[state["id"]]["items"][0]
    path = service._directory(state["id"]) / (old["id"] + ".png")
    entered, release = pause_read(monkeypatch, path)
    thread, result, errors = start(lambda: service.asset(state["id"], "employee-a", "before", item["id"], thumbnail=True))
    try:
        assert entered.wait(3)
        with service.lock:
            job = service.jobs[state["id"]]
            current = next(row for row in job["items"] if row["id"] == item["id"])
            current["previous_item_id"] = "0" * 32
            job["revision"] += 1; service._save(job)
    finally:
        release.set(); thread.join(5)
    assert not result and isinstance(errors[0], (KeyError, Conflict))
    assert not service.leases


def test_download_rejects_changed_selection_and_releases_packing_slot(service, monkeypatch):
    state = completed(service); item = state["items"][0]
    path = service._directory(state["id"]) / (item["id"] + ".png")
    entered, release = pause_read(monkeypatch, path)
    thread, result, errors = start(lambda: service.download(state["id"], "employee-a"))
    try:
        assert entered.wait(3)
        with pytest.raises(Conflict, match="正在打包"):
            service.download(state["id"], "employee-a")
        service.resolve(state["id"], "employee-a", {"expected_revision": state["revision"], "item_id": item["id"], "action": "skip"})
    finally:
        release.set(); thread.join(5)
    assert not result and isinstance(errors[0], Conflict)
    assert not service.leases and not service._packing
    assert not list(service._directory(state["id"]).glob(".zip-*"))


def test_zip_cache_is_bound_to_selection_and_preserves_previous_download(service):
    state = completed(service)
    first, first_digest = service.download(state["id"], "employee-a")
    original = first.read_bytes()
    assert service.download(state["id"], "employee-a") == (first, first_digest)
    state = service.resolve(state["id"], "employee-a", {"expected_revision": state["revision"], "item_id": state["items"][0]["id"], "action": "skip"})
    second, second_digest = service.download(state["id"], "employee-a")
    assert second != first and second_digest != first_digest
    assert first.read_bytes() == original
    with zipfile.ZipFile(second) as archive:
        assert archive.namelist() == ["素材-001.png", "素材说明.json"]
    assert not service.leases and not service._packing


@pytest.mark.parametrize("kind", ["source", "item", "zip"])
def test_cache_never_trusts_changed_input_output_or_archive(service, kind):
    state = completed(service)
    path, _ = service.download(state["id"], "employee-a")
    if kind != "zip":
        row = state["sources"][0] if kind == "source" else state["items"][0]
        path = service._directory(state["id"]) / (row["id"] + ".png")
    path.write_bytes(b"changed-synthetic-file")
    with pytest.raises(ValueError):
        service.download(state["id"], "employee-a")
    assert not service.leases and not service._packing


@pytest.mark.parametrize("kind", ["source", "item", "before", "thumb", "zip", "new_zip"])
def test_hash_result_cannot_be_bound_to_replaced_file(service, monkeypatch, kind):
    state = completed(service)
    item = state["items"][0]
    if kind == "before":
        service.refine(state["id"], "employee-a", {"expected_revision": state["revision"], "item_id": item["id"]})
        service.futures[state["id"]].result(10)
        state = service.snapshot(state["id"], "employee-a")
        previous_id = item["id"]
        item = next(row for row in state["items"] if row["refined"])
        target = service._directory(state["id"]) / (previous_id + ".png")
    elif kind == "zip":
        target, _ = service.download(state["id"], "employee-a")
    elif kind == "new_zip":
        target = None
    else:
        row = state["sources"][0] if kind == "source" else item
        target = service._directory(state["id"]) / (row["id"] + (".thumb.png" if kind == "thumb" else ".png"))
    original, changed = module._digest, []
    def swapped(path):
        digest = original(path)
        if not changed and (Path(path) == target or kind == "new_zip" and Path(path).name.startswith("materials-")):
            Path(path).write_bytes(b"replaced-after-old-hash")
            changed.append(path)
        return digest
    monkeypatch.setattr(module, "_digest", swapped)
    with pytest.raises(ValueError):
        if kind in {"zip", "new_zip"}:
            service.download(state["id"], "employee-a")
        else:
            service.asset(state["id"], "employee-a", "before" if kind == "before" else "item", item["id"], thumbnail=True)
    assert len(changed) == 1
    assert not service.leases and not service._packing
    assert not list(service._directory(state["id"]).glob(".zip-*"))


def test_zip_cache_revalidates_on_restart_without_replacing_download(service):
    state = completed(service)
    path, digest = service.download(state["id"], "employee-a")
    original, token = path.read_bytes(), service._read_token(path)
    # Recreate only the in-memory trusted cache, as after process restart.
    service._archive_cache.clear()
    rebuilt, rebuilt_digest = service.download(state["id"], "employee-a")
    assert rebuilt != path and rebuilt_digest == digest
    assert path.read_bytes() == original and service._read_token(path) == token


def test_exclusive_archive_collision_preserves_existing_file(service, monkeypatch):
    state = completed(service)
    monkeypatch.setattr(module.secrets, "token_hex", lambda _: "a" * 32)
    path, _ = service.download(state["id"], "employee-a")
    service._archive_cache.clear()
    path.write_bytes(b"existing-collision-preserved")
    with pytest.raises(FileExistsError):
        service.download(state["id"], "employee-a")
    assert path.read_bytes() == b"existing-collision-preserved"
    assert not service.leases and not service._packing


def test_failed_candidate_cleanup_cannot_leave_packing_slot_stuck(service, monkeypatch):
    state = completed(service)
    digest, unlink = module._digest, Path.unlink
    def cannot_hash(path):
        if Path(path).name.startswith("materials-"):
            raise OSError("synthetic-archive-check-failure")
        return digest(path)
    def cannot_unlink(path, *args, **kwargs):
        if path.name.startswith("materials-"):
            raise PermissionError("synthetic-cleanup-denied")
        return unlink(path, *args, **kwargs)
    monkeypatch.setattr(module, "_digest", cannot_hash)
    monkeypatch.setattr(Path, "unlink", cannot_unlink)
    with pytest.raises(PermissionError):
        service.download(state["id"], "employee-a")
    assert not service.leases and not service._packing and not service._archive_cache
    assert all(path.stat().st_nlink == 1 for path in service._directory(state["id"]).glob("materials-*.zip"))
    monkeypatch.setattr(module, "_digest", digest)
    monkeypatch.setattr(Path, "unlink", unlink)
    assert service.download(state["id"], "employee-a")[0].is_file()


def test_crash_orphan_is_single_link_and_normal_retention_can_clean(service):
    state = completed(service)
    archive, _ = service.download(state["id"], "employee-a")
    service._archive_cache.clear()
    orphan = service._directory(state["id"]) / "materials-simulated-crash.zip"
    orphan.write_bytes(b"incomplete-unpublished-candidate")
    assert archive.stat().st_nlink == orphan.stat().st_nlink == 1
    now = service.clock()
    service.clock = lambda: now + RETENTION_SECONDS + 10
    assert state["id"] in service.retention_sweep()
    assert not service._directory(state["id"]).exists()


@pytest.mark.parametrize("operation", ["asset", "download"])
def test_nonvisual_progress_does_not_invalidate_completed_files(service, monkeypatch, operation):
    state = completed(service); item = state["items"][0]
    entered, release = pause_read(monkeypatch, service._directory(state["id"]) / (item["id"] + ".png"))
    call = (lambda: service.download(state["id"], "employee-a")) if operation == "download" else (
        lambda: service.asset(state["id"], "employee-a", "item", item["id"], thumbnail=True))
    thread, result, errors = start(call)
    try:
        assert entered.wait(3)
        with service.lock:
            job = service.jobs[state["id"]]
            job["progress"]["message"] = "synthetic-nonvisual-progress"
            service._save(job)
    finally:
        release.set(); thread.join(5)
    assert result and not errors
    assert not service.leases and not service._packing


def test_shared_source_is_verified_once_per_cached_read(service, monkeypatch):
    state = completed(service)
    service.download(state["id"], "employee-a")
    source = service._directory(state["id"]) / (state["sources"][0]["id"] + ".png")
    original, calls = module._digest, []
    def observed(path):
        if Path(path) == source:
            calls.append(path)
        return original(path)
    monkeypatch.setattr(module, "_digest", observed)
    service.download(state["id"], "employee-a")
    assert len(calls) == 1


def test_retention_config_uses_current_window(service):
    config = service.config("employee-a")
    assert config["retention_seconds"] == RETENTION_SECONDS
    assert config["retention_hours"] == 50
    assert config["retention_days"] == RETENTION_SECONDS / 86400


@pytest.mark.parametrize("failed_terminal_write", [False, True])
@pytest.mark.parametrize("was_unknown", [False, True])
def test_redo_rejected_queue_preserves_old_images_without_sticking_busy(service, monkeypatch, failed_terminal_write, was_unknown):
    state = completed(service)
    job = service.jobs[state["id"]]
    job["sources"][0]["submission_unknown"] = was_unknown
    service._save(job)
    originals = {row["id"]: (service._directory(state["id"]) / (row["id"] + ".png")).read_bytes() for row in state["items"]}
    before_calls = service._synthetic_provider.calls
    save = service._save
    pending = []
    submit = service.executor.submit
    def rejected(function, *args):
        pending.append((function, args))
        raise RuntimeError("synthetic-executor-rejected")
    def unavailable(value, **kwargs):
        if failed_terminal_write and value["status"] == "error":
            raise OSError("synthetic-terminal-save-rejected")
        return save(value, **kwargs)
    monkeypatch.setattr(service.executor, "submit", rejected)
    monkeypatch.setattr(service, "_save", unavailable)
    payload = {"expected_revision": state["revision"], "source_id": state["sources"][0]["id"],
               "box": {"x": 0, "y": 0, "width": 32, "height": 32}, "acknowledge_unknown": True}
    with pytest.raises(Exception):
        service.redo(state["id"], "employee-a", payload)
    for function, args in pending:
        submit(function, *args).result(5)
    current = service.snapshot(state["id"], "employee-a")
    assert current["status"] == "error" and "排队" in current["error"]
    assert current["revision"] == state["revision"] + 2
    assert service._synthetic_provider.calls == before_calls
    assert service.jobs[state["id"]]["sources"][0]["submission_unknown"] is was_unknown
    assert not service.has_active_operations()
    assert all(row["downloadable"] for row in current["items"])
    for row in current["items"]:
        path, _ = service.asset(state["id"], "employee-a", "item", row["id"], download=True)
        assert path.read_bytes() == originals[row["id"]]
