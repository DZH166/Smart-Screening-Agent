"""Cloud expiry uses managed namespaces, signed clocks and live request leases."""
import json
import os
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from hsd_tool.cloud_retention import RETENTION_SECONDS, CloudRetention
from hsd_tool.service import JobManager
from hsd_tool.uploads import EmployeeUploads


JOB = "1" * 32
BATCH = "2" * 32


def manager_at(path):
    path.mkdir(parents=True, exist_ok=True)
    manager = SimpleNamespace(data_dir=path, lock=threading.RLock(), jobs={},
                              _active_operations=0, _inflight_futures=set(), _job_locks={})
    manager._get = lambda identifier: manager.jobs[identifier]
    return manager


def test_cloud_timer_also_sweeps_isolated_material_namespace_and_survives_failure(tmp_path):
    manager = manager_at(tmp_path / "service")
    calls = []
    companion = SimpleNamespace(retention_sweep=lambda: calls.append("materials"))
    retention = CloudRetention(manager, {}, companion=companion)
    retention._cycle()
    assert calls == ["materials"]
    companion.retention_sweep = lambda: (_ for _ in ()).throw(ValueError("synthetic failure"))
    retention._cycle()  # A deferred material deletion cannot stop the timer.


def add_upload(manager, status="ready", identifier=JOB, batch=BATCH):
    root = manager.data_dir
    for name, identity in (("uploads", batch), ("employee_outputs", batch),
                           ("jobs", identifier), ("task_records", identifier)):
        path = root / name / identity
        path.mkdir(parents=True)
        (path / "private.bin").write_bytes(b"synthetic private business bytes")
    (root / "uploads" / batch / ".hsd-upload").write_text(batch, "ascii")
    (root / "jobs" / identifier / ".hsd-job").write_text(identifier, "ascii")
    job = {"id": identifier, "status": status, "revision": 0, "_owner_id": "employee",
           "_upload_managed": True, "_upload_dir": str(root / "uploads" / batch),
           "_output_root": str(root / "employee_outputs" / batch),
           "_work_dir": str(root / "jobs" / identifier), "_operation_token": "operation-1"}
    manager.jobs[identifier] = job
    return job


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr("hsd_tool.cloud_retention.time.time", lambda: 1000.)
    manager = manager_at(tmp_path / "service")
    job = add_upload(manager)
    leases = {}
    retention = CloudRetention(manager, leases, retention_seconds=100, interval_seconds=1)
    retention.register(JOB)
    return manager, job, leases, retention


@pytest.mark.parametrize("status", ["ready", "done", "error"])
def test_default_window_and_settled_expiry_removes_only_its_four_namespaces(setup, status):
    manager, job, _, retention = setup
    job["status"] = status
    retention.sweep(now=1000)
    # Other tasks, accounting and settings must survive the cloud batch expiry.
    for name in ("settings.json", "ai-credentials.enc", "ai-usage.json"):
        (manager.data_dir / name).write_text("preserve")
    stranger = manager.data_dir / "jobs" / ("a" * 32)
    stranger.mkdir()
    (stranger / "unknown.bin").write_text("preserve")
    assert retention.sweep(now=1099) == []
    assert retention.sweep(now=1100) == [JOB]
    assert JOB not in manager.jobs
    for name, identity in (("uploads", BATCH), ("employee_outputs", BATCH),
                           ("jobs", JOB), ("task_records", JOB)):
        assert not (manager.data_dir / name / identity).exists()
    assert stranger.is_dir()
    assert all((manager.data_dir / name).read_text() == "preserve"
               for name in ("settings.json", "ai-credentials.enc", "ai-usage.json"))
    # The product window is 50 hours, not three days.
    assert CloudRetention(manager, {}).retention_seconds == RETENTION_SECONDS == 50 * 60 * 60


def test_a_manifest_from_the_three_day_window_is_shortened_on_startup(tmp_path, monkeypatch):
    """Changing the policy must not strand old manifests on disk.

    A 72-hour manifest would fail validation under a 50-hour policy, be ignored,
    and its files would never be swept. Loading it must re-stamp the expiry.
    """
    monkeypatch.setattr("hsd_tool.cloud_retention.time.time", lambda: 1000.)
    manager = manager_at(tmp_path / "service")
    job = add_upload(manager)
    job["status"] = "done"
    older = CloudRetention(manager, {}, retention_seconds=3 * 24 * 60 * 60, interval_seconds=1)
    older.register(JOB)
    older.sweep(now=1000)
    assert older._records[JOB]["expires_at"] == 1000 + 3 * 24 * 60 * 60
    manager.jobs.pop(JOB, None)

    current = CloudRetention(manager, {}, interval_seconds=1)
    record = current._records[JOB]
    assert record["retention_seconds"] == RETENTION_SECONDS
    assert record["expires_at"] == 1000 + RETENTION_SECONDS
    # Nothing is deleted before the shorter window, and it is enforced exactly.
    assert current.sweep(now=1000 + RETENTION_SECONDS - 1) == []
    assert current.sweep(now=1000 + RETENTION_SECONDS) == [JOB]


@pytest.mark.parametrize("status", ["queued", "importing", "matching", "ai_review", "exporting"])
def test_busy_phase_never_expires_and_terminal_transition_starts_fresh_window(setup, status):
    manager, job, _, retention = setup
    job["status"] = status
    assert retention.sweep(now=1200) == []
    assert retention.sweep(now=9999) == []
    job["status"] = "ready"
    assert retention.sweep(now=10000) == []
    assert retention.sweep(now=10099) == []
    assert retention.sweep(now=10100) == [JOB]


@pytest.mark.parametrize("change", ["revision", "_operation_token", "status"])
def test_successful_edits_or_phase_changes_refresh_expiry(setup, change):
    _, job, _, retention = setup
    job[change] = {"revision": 1, "_operation_token": "operation-2", "status": "done"}[change]
    assert retention.sweep(now=1090) == []
    assert retention.sweep(now=1100) == []
    assert retention.sweep(now=1190) == [JOB]


@pytest.mark.parametrize("protection", ["lease", "operation", "future"])
def test_preview_download_or_accepted_background_work_blocks_expiry(setup, protection):
    manager, _, leases, retention = setup
    if protection == "lease":
        leases[JOB] = 1
    elif protection == "operation":
        manager._active_operations = 1
    else:
        manager._inflight_futures.add(object())
    assert retention.sweep(now=1200) == []
    assert JOB in manager.jobs
    leases.clear()
    manager._active_operations = 0
    manager._inflight_futures.clear()
    assert retention.sweep(now=1201) == [JOB]


def test_restart_cleans_only_signed_expired_orphans_and_does_not_restore_jobs(setup):
    manager, _, _, _ = setup
    restarted = manager_at(manager.data_dir)
    retention = CloudRetention(restarted, {}, retention_seconds=100)
    assert restarted.jobs == {}
    assert retention.sweep(now=1099) == []
    assert retention.sweep(now=1100) == [JOB]


def test_crashed_busy_task_starts_retention_at_restart_not_old_upload_time(setup):
    manager, job, _, retention = setup
    job["status"] = "matching"
    retention.sweep(now=1050)
    restarted = CloudRetention(manager_at(manager.data_dir), {}, retention_seconds=100)
    assert restarted.sweep(now=2000) == []
    assert restarted._records[JOB]["status"] == "orphaned"
    assert restarted.sweep(now=2099) == []
    assert restarted.sweep(now=2100) == [JOB]


@pytest.mark.parametrize("tamper", ["time", "path", "identity", "signature", "duplicate"])
def test_manifest_tampering_preserves_files_both_running_and_after_restart(setup, tamper):
    manager, _, _, retention = setup
    manifest = manager.data_dir / "cloud_retention" / "manifests" / (JOB + ".json")
    body = json.loads(manifest.read_text())
    if tamper == "time":
        body["payload"]["expires_at"] = 1
    elif tamper == "path":
        body["payload"]["path"] = str(manager.data_dir.parent)
    elif tamper == "identity":
        body["payload"]["batch_id"] = "a" * 32
    elif tamper == "signature":
        body["hmac_sha256"] = "0" * 64
    raw = json.dumps(body)
    if tamper == "duplicate":
        raw = raw.replace('"schema": 1', '"schema": 1, "schema": 1')
    manifest.write_text(raw)
    assert retention.sweep(now=2000) == []
    assert JOB in manager.jobs
    restarted = CloudRetention(manager_at(manager.data_dir), {}, retention_seconds=100)
    assert restarted.sweep(now=2000) == []
    assert (manager.data_dir / "uploads" / BATCH / "private.bin").exists()


def test_changed_upload_marker_or_outside_job_path_never_deletes(setup, tmp_path):
    manager, job, _, retention = setup
    outside = tmp_path / "unrelated-website"
    outside.mkdir()
    (outside / "index.html").write_text("untouched")
    job["_output_root"] = str(outside)
    assert retention.sweep(now=2000) == []
    job["_output_root"] = str(manager.data_dir / "employee_outputs" / BATCH)
    (manager.data_dir / "uploads" / BATCH / ".hsd-upload").write_text("wrong")
    assert retention.sweep(now=2000) == []
    assert (outside / "index.html").read_text() == "untouched"
    assert (manager.data_dir / "task_records" / JOB).is_dir()


def test_symlink_in_any_cleanup_target_preserves_all_directories(setup, tmp_path):
    manager, _, _, retention = setup
    outside = tmp_path / "other-site"
    outside.mkdir()
    (outside / "index.html").write_text("untouched")
    link = manager.data_dir / "employee_outputs" / BATCH / "unsafe"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("This host cannot create directory symlinks")
    assert retention.sweep(now=2000) == []
    assert (manager.data_dir / "uploads" / BATCH).is_dir()
    assert (outside / "index.html").read_text() == "untouched"


def test_interrupted_cleanup_can_resume_without_restoring_task(setup, monkeypatch):
    manager, _, _, retention = setup
    import hsd_tool.cloud_retention as module
    original = module.shutil.rmtree
    blocked = manager.data_dir / "employee_outputs" / BATCH
    def fail_once(path):
        if path == blocked:
            raise OSError("synthetic disk failure")
        return original(path)
    monkeypatch.setattr(module.shutil, "rmtree", fail_once)
    assert retention.sweep(now=2000) == []
    assert JOB not in manager.jobs
    assert retention._path(JOB).is_file()
    monkeypatch.setattr(module.shutil, "rmtree", original)
    restarted = CloudRetention(manager_at(manager.data_dir), {}, retention_seconds=100)
    assert restarted.sweep(now=2001) == [JOB]


def test_worker_start_stop_is_idempotent_and_does_not_delete_at_exit(setup):
    manager, _, _, retention = setup
    assert retention.start() is retention
    thread = retention._thread
    assert retention.start()._thread is thread and thread.is_alive()
    retention.stop()
    retention.stop()
    assert not thread.is_alive()
    assert JOB in manager.jobs


def test_clock_adjustment_backwards_never_shortens_retention(setup):
    _, job, _, retention = setup
    job["revision"] = 1
    assert retention.sweep(now=900) == []
    assert retention._records[JOB]["expires_at"] == 1100


def test_missing_signing_key_does_not_retrust_existing_manifests(setup):
    manager, _, _, _ = setup
    (manager.data_dir / "cloud_retention" / "retention-signing.key").unlink()
    with pytest.raises(ValueError, match="signing key is missing"):
        CloudRetention(manager_at(manager.data_dir), {}, retention_seconds=100)
    assert (manager.data_dir / "uploads" / BATCH).exists()


def test_signing_material_and_manifests_are_private_on_linux(setup):
    manager, _, _, retention = setup
    key = manager.data_dir / "cloud_retention" / "retention-signing.key"
    if os.name == "nt":
        return
    assert key.stat().st_mode & 0o077 == 0
    assert retention._path(JOB).stat().st_mode & 0o077 == 0
    key.chmod(0o644)
    with pytest.raises(ValueError, match="private"):
        CloudRetention(manager_at(manager.data_dir), {}, retention_seconds=100)


def test_cloud_cache_survives_close_and_restart_while_default_lan_cleanup_is_unchanged(tmp_path):
    root = tmp_path / "state"
    manager = JobManager(root, preserve_cache=True)
    cache = root / "jobs" / JOB
    cache.mkdir(parents=True)
    (cache / ".hsd-job").write_text(JOB)
    (cache / "synthetic.bin").write_bytes(b"keep for cloud retention")
    records = root / "task_records" / JOB
    records.mkdir(parents=True)
    (records / "private.json").write_text("keep")
    manager.close()
    assert cache.is_dir()
    cloud = JobManager(root, preserve_cache=True)
    assert cache.is_dir()
    cloud.close()
    ordinary = JobManager(root)
    assert not cache.exists()
    ordinary.close()
    assert (records / "private.json").read_text() == "keep"


def test_unmanaged_or_unsafe_registration_cannot_create_deletion_manifest(setup):
    manager, job, _, retention = setup
    retention._path(JOB).unlink()
    retention._records.clear()
    job["_upload_managed"] = False
    with pytest.raises(ValueError, match="managed upload"):
        retention.register(JOB)
    assert not retention._path(JOB).exists()


def test_same_upload_cannot_be_registered_to_two_tasks(setup):
    manager, job, _, retention = setup
    another = "b" * 32
    work = manager.data_dir / "jobs" / another
    work.mkdir()
    (work / ".hsd-job").write_text(another)
    manager.jobs[another] = {**job, "id": another, "_work_dir": str(work)}
    with pytest.raises(ValueError, match="not unique"):
        retention.register(another)
    assert not retention._path(another).exists()


def real_upload_manager(tmp_path):
    manager = JobManager(tmp_path / "service", preserve_cache=True)
    uploads = EmployeeUploads(manager.data_dir)
    directory = uploads.begin()
    (directory / "workbook.xlsx").write_bytes(b"synthetic-workbook-for-planning")
    (directory / "source.zip").write_bytes(b"synthetic-archive-for-planning")
    payload = {"workbook_path": str(directory / "workbook.xlsx"),
               "source_path": str(directory / "source.zip"),
               "output_root": str(uploads.output_root / directory.name), "start_number": 1}
    return manager, directory, payload


@pytest.mark.parametrize("failure", [OSError("synthetic full volume"), ValueError("synthetic unsafe registration")])
def test_failed_cloud_registration_never_submits_cpu_or_ai_and_keeps_upload_for_receiver_cleanup(tmp_path, monkeypatch, failure):
    manager, directory, payload = real_upload_manager(tmp_path)
    retention = CloudRetention(manager, {})
    submitted, seen = [], []
    monkeypatch.setattr(manager, "_submit", lambda *args: submitted.append(args))
    def fail_register(identifier):
        seen.append(identifier)
        raise failure
    monkeypatch.setattr(retention, "register", fail_register)
    def before_submit(job):
        assert manager.jobs[job["id"]] is job
        manager._job_locks[job["id"]] = threading.RLock()
        job.update(_upload_managed=True, _upload_dir=str(directory))
        retention.register(job["id"])
    try:
        with pytest.raises(type(failure), match="synthetic"):
            manager.create(payload, owner_id="employee", downloadable=True, before_submit=before_submit)
        assert len(seen) == 1 and submitted == []
        assert manager.jobs == {} and manager._job_locks == {}
        assert list((manager.data_dir / "jobs").iterdir()) == []
        assert (directory / "workbook.xlsx").is_file()
        assert (directory / "source.zip").is_file()
        assert not retention._path(seen[0]).exists()
    finally:
        manager.close()


def test_cloud_registration_is_persistent_before_any_background_submission(tmp_path, monkeypatch):
    manager, directory, payload = real_upload_manager(tmp_path)
    retention = CloudRetention(manager, {})
    submitted = []
    def before_submit(job):
        job.update(_upload_managed=True, _upload_dir=str(directory))
        retention.register(job["id"])
    def submit(job, operation):
        assert retention._read(job["id"])["status"] == "queued"
        submitted.append(job["id"])
    monkeypatch.setattr(manager, "_submit", submit)
    try:
        identifier = manager.create(payload, owner_id="employee", downloadable=True, before_submit=before_submit)
        assert submitted == [identifier]
        assert retention._read(identifier)["batch_id"] == directory.name
    finally:
        manager.close()


def test_normal_shutdown_records_final_settled_state_after_background_drain(tmp_path, monkeypatch):
    clock = [1000.]
    monkeypatch.setattr("hsd_tool.cloud_retention.time.time", lambda: clock[0])
    manager, directory, payload = real_upload_manager(tmp_path)
    retention = CloudRetention(manager, {}, retention_seconds=100)
    entered, finish, closed = threading.Event(), threading.Event(), threading.Event()
    observed = []
    def process(identifier):
        manager._start_operation(identifier, "matching", "synthetic")
        entered.set()
        assert finish.wait(5)
        with manager.lock:
            manager.jobs[identifier]["status"] = "done"
    monkeypatch.setattr(manager, "_process", process)
    def before_submit(job):
        job.update(_upload_managed=True, _upload_dir=str(directory))
        retention.register(job["id"])
    identifier = manager.create(payload, owner_id="employee", downloadable=True, before_submit=before_submit)
    assert entered.wait(5)
    retention.stop()  # Persist BUSY, as the worker starts its graceful close.
    assert retention._read(identifier)["status"] == "matching"
    def after_drain():
        # Another thread can acquire manager.lock: callback is outside it.
        available = threading.Event()
        def take_lock():
            with manager.lock:
                available.set()
        probe = threading.Thread(target=take_lock)
        probe.start()
        assert available.wait(2)
        probe.join()
        assert manager.jobs[identifier]["status"] == "done"
        assert not manager._inflight_futures and manager._active_operations == 0
        observed.append(identifier)
        retention.sweep(delete=False)
    def shutdown():
        manager.close(on_drained=after_drain)
        closed.set()
    closer = threading.Thread(target=shutdown)
    closer.start()
    assert not closed.wait(.05)
    clock[0] = 1050.
    finish.set()
    closer.join(5)
    assert not closer.is_alive() and closed.is_set() and observed == [identifier]
    final = retention._read(identifier)
    assert final["status"] == "done" and final["settled_at"] == 1050 and final["expires_at"] == 1150
    restarted = CloudRetention(manager_at(manager.data_dir), {}, retention_seconds=100)
    assert restarted.sweep(now=1149) == []
    assert restarted.sweep(now=1150) == [identifier]
