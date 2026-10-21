"""Synthetic cancellation and complete-input checks; no provider or business data."""
import copy
import threading
import time

import pytest

from hsd_tool.service import JobManager, sha256
from test_service import prepared
from test_ai_first_service import scenario


def settled(manager, identifier, timeout=6):
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        with manager.lock:
            job = manager.jobs[identifier]
            if job['status'] not in {'queued', 'importing', 'matching', 'ai_review', 'exporting', 'cancelling'} and not manager.task_has_work(identifier):
                return job
        time.sleep(.005)
    pytest.fail('Synthetic task did not settle')


def test_cancel_running_and_queued_jobs_only_after_their_work_drains(tmp_path):
    manager, job = prepared(tmp_path, [''])
    entered, release = threading.Event(), threading.Event()
    completed = []
    def process(identifier):
        manager._start_operation(identifier, 'matching', 'synthetic work')
        entered.set()
        assert release.wait(4)
        manager._progress(identifier, 'checkpoint')
        completed.append(identifier)
    manager._process = process
    try:
        with manager.lock:
            job['status'] = 'queued'
            manager._submit(job, manager._process)
        assert entered.wait(2)
        queued = copy.deepcopy(job)
        queued.update(id='other', status='queued', revision=0)
        manager.jobs['other'] = queued
        with manager.lock:
            manager._submit(queued, manager._process)
        result = manager.cancel('other', 0)
        assert settled(manager, 'other')['status'] == 'cancelled'
        assert job['status'] == 'matching'
        result = manager.cancel('sample', 0)
        assert result['status'] == 'cancelling'
        assert manager.task_has_work('sample')
        with pytest.raises(ValueError):
            manager.export('sample')
        release.set()
        assert settled(manager, 'sample')['status'] == 'cancelled'
        assert completed == []
        assert manager.cancel('sample')['status'] == 'cancelled'
    finally:
        release.set()
        manager.close()


def test_cancelled_operation_does_not_overwrite_final_done_result(tmp_path):
    manager, job = prepared(tmp_path, [''])
    job['status'] = 'done'
    try:
        with pytest.raises(ValueError, match='已经结束'):
            manager.cancel('sample')
        assert job['status'] == 'done' and not job.get('cancel_requested')
    finally:
        manager.close()


def test_stop_during_fake_paid_request_records_usage_and_does_not_commit(scenario):
    value = scenario(count=1)
    entered, release = threading.Event(), threading.Event()
    def respond(request, body):
        entered.set()
        assert release.wait(4)
        from test_ai_first import payload
        return payload(body)
    value.opener.outcome = respond
    identifier = value.create()
    try:
        assert entered.wait(3)
        value.manager.cancel(identifier)
        assert value.manager.jobs[identifier]['status'] == 'cancelling'
    finally:
        release.set()
    job = settled(value.manager, identifier)
    assert job['status'] == 'cancelled'
    assert len(value.opener.calls) == 1
    assert value.manager.ai_usage.snapshot()['requests'] == 1
    assert not job.get('_download_path')
    with pytest.raises(ValueError):
        value.manager.export(identifier)
    records = list((value.manager.data_dir / 'task_records' / identifier / 'ai_first_runs').glob('*.json'))
    assert records and '"requests": 1' in records[0].read_text('utf-8')


@pytest.mark.parametrize('changed', ['snapshot', 'preview', 'unused_competitor'])
def test_export_rechecks_all_bound_inputs(tmp_path, changed):
    manager, job = prepared(tmp_path, [''])
    try:
        if changed == 'snapshot':
            snapshot = tmp_path / 'snapshot.xlsx'
            snapshot.write_bytes(open(job['_workbook_path'], 'rb').read())
            job['_snapshot_workbook'] = str(snapshot)
            job['_snapshot_digest'] = sha256(snapshot)
            target = snapshot
        else:
            target = tmp_path / (changed + '.bin')
            target.write_bytes(b'unchanged synthetic comparison')
            job['_comparison_bindings'] = {str(target): sha256(target)}
        target.write_bytes(b'changed after matching')
        manager.export('sample')
        result = settled(manager, 'sample')
        assert result['status'] == 'ready' and '变化' in result['error']
        assert result['output_dir'] is None
    finally:
        manager.close()


def test_cancel_during_workbook_export_never_publishes_completed_result(tmp_path, monkeypatch):
    manager, job = prepared(tmp_path, [''])
    entered, release = threading.Event(), threading.Event()
    import hsd_tool.workbook as workbook
    original = workbook.write_numbered_workbook
    def pause(*args):
        entered.set()
        assert release.wait(4)
        return original(*args)
    monkeypatch.setattr(workbook, 'write_numbered_workbook', pause)
    try:
        manager.export('sample')
        assert entered.wait(3)
        assert manager.cancel('sample')['status'] == 'cancelling'
        release.set()
        assert settled(manager, 'sample')['status'] == 'cancelled'
        assert not job.get('_download_path') and job['output_dir'] is None
        assert not list((tmp_path / 'output').glob('.HSD处理中_*'))
    finally:
        release.set()
        manager.close()


def test_texture_worker_inherits_task_cancel_context(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from hsd_tool.cancellation import TaskCancelled, scope
    import hsd_tool.matching as matching
    calls = []
    monkeypatch.setattr(matching, '_texture', lambda *a, **k: calls.append(True))
    def cancelled():
        raise TaskCancelled('synthetic cancellation')
    with ThreadPoolExecutor(max_workers=1) as pool, scope(cancelled):
        with pytest.raises(TaskCancelled):
            list(matching._texture_results(None, ['x'], {}, False, None, pool))
    assert calls == []


def test_cancel_queued_cpu_child_does_not_wait_for_unrelated_cpu_job(scenario):
    value = scenario(count=1)
    occupied, release_cpu, provider, release_provider = (threading.Event() for _ in range(4))
    original = value.manager._retrieve_ai_first
    def blocker():
        occupied.set()
        assert release_cpu.wait(5)
    def coordinator(identifier):
        value.manager.pool.submit(blocker)
        assert occupied.wait(3)
        return original(identifier)
    value.manager._retrieve_ai_first = coordinator
    def respond(request, body):
        provider.set()
        assert release_provider.wait(4)
        from test_ai_first import payload
        return payload(body)
    value.opener.outcome = respond
    identifier = value.create()
    try:
        assert provider.wait(4)
        assert value.manager.jobs[identifier]['_cpu_future'].running() is False
        value.manager.cancel(identifier)
        release_provider.set()
        assert settled(value.manager, identifier, timeout=2)['status'] == 'cancelled'
        assert not release_cpu.is_set()
        assert value.manager.ai_usage.snapshot()['requests'] == 1
    finally:
        release_provider.set()
        release_cpu.set()
