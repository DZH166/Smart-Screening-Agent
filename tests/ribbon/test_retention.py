"""Private-data expiry, authenticated ownership and immutable download checks.

All images and provider responses here are explicitly synthetic test evidence.
"""
import io
import time
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from PIL import Image

from ribbon_backend.config import Settings
from ribbon_backend.service import Service, ServiceError, MODES
from hsd_tool.retention_window import RETENTION_SECONDS


@pytest.fixture
def service(tmp_path):
    instance = Service(Settings(data_dir=tmp_path, auth_mode='demo', provider='test'))
    yield instance
    instance.stop()


def user(service, name='demo'):
    with service.db.connect() as db:
        return dict(db.execute('SELECT id,username,role FROM users WHERE username=?', (name,)).fetchone())


def selection(service, owner):
    return dict(asset_ids=[service.assets(owner, 'pattern')[0]['id']],
                background_id=service.assets(owner, 'background')[0]['id'], template_id='grid')


def generate(service, owner, choices=None):
    design = service.create_design(owner, '合成验收作品')
    job = service.submit(owner, 'generate', dict(idempotency_key=str(uuid4()), **(choices or selection(service, owner))), design['id'])
    assert service.run_once()
    assert service.job(owner, job['id'])['status'] == 'SUCCEEDED'
    return service.design(owner, design['id'])


def expire(service, owner):
    old = time.time() - RETENTION_SECONDS - 3600
    with service.db.transaction() as db:
        db.execute('UPDATE designs SET retained_at=? WHERE owner_id=?', (old, owner))
        db.execute('UPDATE assets SET retained_at=? WHERE owner_id=?', (old, owner))
        db.execute("UPDATE jobs SET settled_at=? WHERE owner_id=? AND status IN ('SUCCEEDED','FAILED')", (old, owner))


def upload(service, actor, shared=False):
    output = io.BytesIO()
    Image.new('RGBA', (16, 16), 'red').save(output, 'PNG')
    return service.upload(actor, output.getvalue(), '测试图片', 'pattern', shared=shared)


def test_cleanup_only_expired_private_work(service):
    actor = user(service)
    owner = actor['id']
    uploaded = upload(service, actor)
    choices = selection(service, owner)
    choices['asset_ids'] = [uploaded['id']]
    design = generate(service, owner, choices)
    path = service.version_file(owner, design['current_version_id'])
    shared = upload(service, user(service, 'admin'), shared=True)
    expire(service, owner)
    result = service.cleanup_expired()
    assert result == dict(designs=1, versions=1, assets=1, jobs=1, files_failed=0)
    assert not path.exists()
    assert service.designs(owner) == []
    assert any(a['id'] == shared['id'] for a in service.assets(owner))
    assert {item['mode'] for item in service.templates()} == set(MODES)
    assert service.config()['output_profile']['is_demo']
    with service.db.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM output_profiles').fetchone()[0] == 1
        assert db.execute('SELECT COUNT(*) FROM users').fetchone()[0] == 3
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []


def test_response_lease_can_close_on_another_thread_and_other_owner_expires(service):
    first, second = user(service)['id'], user(service, 'client')['id']
    design = generate(service, first)
    generate(service, second)
    expire(service, first)
    expire(service, second)
    lease = service.resource_lease(first, version_id=design['current_version_id'])
    lease.__enter__()
    with ThreadPoolExecutor(max_workers=1) as pool:
        assert pool.submit(service.cleanup_expired).result()['designs'] == 1
        assert service.design(first, design['id'])
        pool.submit(lease.__exit__, None, None, None).result()
    assert service.cleanup_expired()['designs'] == 1


@pytest.mark.parametrize('status', ['QUEUED', 'RUNNING', 'RECONCILING'])
def test_queued_running_and_reconciling_protect_owner(service, status):
    owner = user(service)['id']
    generate(service, owner)
    expire(service, owner)
    job = service.submit(owner, 'background', dict(idempotency_key=str(uuid4()), prompt='合成底图'))
    with service.db.transaction() as db:
        db.execute('UPDATE jobs SET status=? WHERE id=?', (status, job['id']))
    assert service.cleanup_expired()['designs'] == 0


def test_successful_edit_refreshes_retention_without_resetting_quota(service):
    owner = user(service)['id']
    design = generate(service, owner)
    expire(service, owner)
    job = service.submit(owner, 'refine', dict(idempotency_key=str(uuid4()), base_version_id=design['current_version_id'],
        prompt='应用所选配置', selection=selection(service, owner)), design['id'])
    service.run_once()
    assert service.job(owner, job['id'])['status'] == 'SUCCEEDED'
    assert service.cleanup_expired()['designs'] == 0
    final = service.design(owner, design['id'])
    assert final['successful_refinement_count'] == 1
    assert len(final['versions']) == 2
    service.rollback(owner, design['id'], final['current_version_id'])
    assert service.design(owner, design['id'])['successful_refinement_count'] == 1
    expire(service, owner)
    result = service.cleanup_expired()
    assert result['versions'] == 2


def test_successful_rollback_renews_retention_without_refunding_quota(service):
    owner = user(service)['id']
    design = generate(service, owner)
    v0 = design['current_version_id']
    job = service.submit(owner, 'refine', dict(idempotency_key=str(uuid4()), base_version_id=v0,
        prompt='应用所选配置', selection=selection(service, owner)), design['id'])
    service.run_once()
    assert service.job(owner, job['id'])['status'] == 'SUCCEEDED'
    v1 = service.design(owner, design['id'])['current_version_id']
    expire(service, owner)
    before = time.time()
    restored = service.rollback(owner, design['id'], v1)
    assert restored['current_version_id'] == v0
    assert restored['successful_refinement_count'] == 1
    with service.db.connect() as db:
        renewed = db.execute('SELECT retained_at FROM designs WHERE id=?', (design['id'],)).fetchone()[0]
    assert renewed >= before
    assert service.cleanup_expired(now=renewed + RETENTION_SECONDS - 60)['designs'] == 0
    assert service.cleanup_expired(now=renewed + RETENTION_SECONDS)['versions'] == 2


def test_failed_rollback_does_not_renew_retention(service):
    owner = user(service)['id']
    design = generate(service, owner)
    expire(service, owner)
    with service.db.connect() as db:
        previous = db.execute('SELECT retained_at FROM designs WHERE id=?', (design['id'],)).fetchone()[0]
    with pytest.raises(ServiceError, match='当前版本已变化'):
        service.rollback(owner, design['id'], 'not-the-current-version')
    with service.db.connect() as db:
        assert db.execute('SELECT retained_at FROM designs WHERE id=?', (design['id'],)).fetchone()[0] == previous
    assert service.cleanup_expired()['designs'] == 1


def test_fifty_hour_boundary_keeps_shared_resources(service):
    assert service.settings.retention_seconds == RETENTION_SECONDS == 50 * 3600
    assert service.config()['retention_hours'] == 50
    actor = user(service)
    owner = actor['id']
    private = upload(service, actor)
    choices = selection(service, owner)
    choices['asset_ids'] = [private['id']]
    design = generate(service, owner, choices)
    shared = upload(service, user(service, 'admin'), shared=True)
    settled = time.time()
    with service.db.transaction() as db:
        db.execute('UPDATE designs SET retained_at=? WHERE id=?', (settled, design['id']))
        db.execute('UPDATE assets SET retained_at=? WHERE id=?', (settled, private['id']))
        db.execute('UPDATE jobs SET settled_at=? WHERE design_id=?', (settled, design['id']))
    assert service.cleanup_expired(now=settled + 49 * 3600 + 59 * 60)['designs'] == 0
    result = service.cleanup_expired(now=settled + 50 * 3600)
    assert result['designs'] == 1 and result['assets'] == 1
    assert any(a['id'] == shared['id'] for a in service.assets(owner))
    assert {item['mode'] for item in service.templates()} == set(MODES)
    assert service.config()['output_profile']['is_demo']


def test_new_shared_window_tightens_existing_seventy_two_hour_work(service):
    owner = user(service)['id']
    # A previous instance could have used the old 72-hour policy. Only the
    # retained timestamp is stored; reopening must use today's shared window.
    service.settings.retention_seconds = 72 * 3600
    assert service.config()['retention_hours'] == 72
    generate(service, owner)
    old = time.time() - 51 * 3600
    with service.db.transaction() as db:
        db.execute('UPDATE designs SET retained_at=? WHERE owner_id=?', (old, owner))
        db.execute('UPDATE jobs SET settled_at=? WHERE owner_id=?', (old, owner))
    assert service.cleanup_expired()['designs'] == 0
    reopened = Service(Settings(data_dir=service.root, auth_mode='demo', provider='test'))
    try:
        assert reopened.settings.retention_seconds == 50 * 3600
        assert reopened.config()['retention_hours'] == 50
        assert reopened.cleanup_expired()['designs'] == 1
    finally:
        reopened.stop()


@pytest.mark.parametrize('preview', [False, True])
def test_download_rejects_modified_version_bytes(service, preview):
    owner = user(service)['id']
    design = generate(service, owner)
    path = service.version_file(owner, design['current_version_id'], preview)
    path.write_bytes(b'changed-after-commit')
    with pytest.raises(ServiceError, match='校验失败') as failure:
        service.version_file(owner, design['current_version_id'], preview)
    assert failure.value.status == 409


def test_retention_does_not_guess_unknown_legacy_age(service):
    owner = user(service)['id']
    design = generate(service, owner)
    expire(service, owner)
    with service.db.transaction() as db:
        db.execute('UPDATE designs SET retained_at=NULL WHERE id=?', (design['id'],))
    assert service.cleanup_expired()['designs'] == 0


def test_private_asset_reused_by_live_work_is_kept(service):
    actor = user(service)
    owner = actor['id']
    asset = upload(service, actor)
    choices = selection(service, owner)
    choices['asset_ids'] = [asset['id']]
    generate(service, owner, choices)
    expire(service, owner)
    live = generate(service, owner, choices)
    result = service.cleanup_expired()
    assert result['designs'] == 1 and result['assets'] == 0
    assert service.version_file(owner, live['current_version_id']).exists()
    assert any(a['id'] == asset['id'] for a in service.assets(owner))


def test_expired_idempotency_key_never_reissues_paid_background(service):
    owner = user(service)['id']
    payload = dict(idempotency_key=str(uuid4()), prompt='测试底图')
    job = service.submit(owner, 'background', payload)
    # A settled failure is enough: expiry must not turn an old POST into a new call.
    claimed = service.claim_job()
    service.fail_job(claimed, '模拟失败')
    expire(service, owner)
    assert service.cleanup_expired()['jobs'] == 1
    with pytest.raises(ServiceError) as failure:
        service.submit(owner, 'background', payload)
    assert failure.value.status == 410
    with service.db.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0] == 0


def test_hsd_identity_is_idempotent_and_no_local_accounts(tmp_path):
    settings = Settings(data_dir=tmp_path, auth_mode='local', provider='test')
    settings.auth_mode = 'hsd'
    settings.api_prefix = '/api/ribbon'
    instance = Service(settings)
    with instance.db.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM users').fetchone()[0] == 0
    first = instance.ensure_external_user('employee:trusted-id', 'employee')
    assert instance.ensure_external_user(first['id'], 'customer') == first
    assert first['role'] == 'customer'
    with pytest.raises(ServiceError):
        instance.login(first['username'], 'arbitrary')
    assert instance.assets(first['id'])[0]['url'].startswith('/api/ribbon/')
    assert all(t['rules']['is_demo'] for t in instance.templates())
    with pytest.raises(ServiceError):
        with instance.resource_lease('browser-invented-id'):
            pass
    second = instance.ensure_external_user('employee:other', 'employee')
    design = generate(instance, first['id'])
    with pytest.raises(ServiceError):
        with instance.resource_lease(second['id'], design_id=design['id']):
            pass
    job = instance.submit(first['id'], 'background', dict(idempotency_key=str(uuid4()), prompt='不要伪成功'))
    instance.run_once()
    assert instance.job(first['id'], job['id'])['status'] == 'FAILED'


def test_two_service_instances_share_resource_leases(service):
    owner = user(service)['id']
    design = generate(service, owner)
    expire(service, owner)
    second = Service(service.settings)
    with service.resource_lease(owner, design_id=design['id']):
        assert second.cleanup_expired()['designs'] == 0
    assert second.cleanup_expired()['designs'] == 1


def test_cleanup_refuses_unexpected_private_asset_path(service, tmp_path):
    actor = user(service)
    asset = upload(service, actor)
    protected = tmp_path / 'configuration.json'
    protected.write_text('retain administrative data', encoding='utf-8')
    with service.db.transaction() as db:
        db.execute('UPDATE assets SET path=? WHERE id=?', (str(protected), asset['id']))
    expire(service, actor['id'])
    assert service.cleanup_expired()['assets'] == 0
    assert protected.read_text(encoding='utf-8') == 'retain administrative data'


def test_cleanup_preserves_generated_asset_provenance_used_by_newer_work(service):
    owner = user(service)['id']
    old = generate(service, owner)
    job = service.submit(owner, 'refine', dict(idempotency_key=str(uuid4()), base_version_id=old['current_version_id'], prompt='给第一个图案添加笑脸'), old['id'])
    service.run_once()
    assert service.job(owner, job['id'])['status'] == 'SUCCEEDED'
    updated = service.design(owner, old['id'])
    latest = next(v for v in updated['versions'] if v['id'] == updated['current_version_id'])
    derived = latest['snapshot']['asset_refs'][0]
    with service.db.connect() as db:
        row = db.execute('SELECT * FROM assets WHERE id=?', (derived,)).fetchone()
        assert row['owner_id'] == owner and row['derived_from']
    expire(service, owner)
    choices = selection(service, owner)
    choices['asset_ids'] = [derived]
    generate(service, owner, choices)
    assert service.cleanup_expired()['designs'] == 0
    assert service.version_file(owner, updated['current_version_id']).exists()


def test_failed_file_deletion_is_persisted_and_retried(service, monkeypatch):
    actor = user(service)
    asset = upload(service, actor)
    with service.db.connect() as db:
        path = Path(db.execute('SELECT path FROM assets WHERE id=?', (asset['id'],)).fetchone()[0])
    expire(service, actor['id'])
    original = Path.unlink

    def temporarily_locked(self, *args, **kwargs):
        if self == path:
            raise PermissionError('simulated file lock')
        return original(self, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, 'unlink', temporarily_locked)
        result = service.cleanup_expired()
    assert result['assets'] == 1 and result['files_failed'] == 1
    assert path.exists()
    with service.db.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM cleanup_paths').fetchone()[0] == 1
    assert service.cleanup_expired()['files_failed'] == 0
    assert not path.exists()


def test_lease_is_released_when_operation_fails(service):
    actor = user(service)
    asset = upload(service, actor)
    expire(service, actor['id'])
    with pytest.raises(ServiceError):
        service.upload(actor, b'not an image', 'bad', 'pattern')
    assert service.cleanup_expired()['assets'] == 1


def test_graceful_stop_waits_for_already_accepted_operation(service, monkeypatch):
    entered, release, stopped = threading.Event(), threading.Event(), threading.Event()

    def in_flight():
        entered.set()
        assert release.wait(5)
        return True

    monkeypatch.setattr(service, 'run_once', in_flight)
    service.start()
    assert entered.wait(5)
    first_thread = service.thread
    service.start()
    assert service.thread is first_thread

    def stop():
        service.stop()
        stopped.set()

    stopper = threading.Thread(target=stop)
    stopper.start()
    try:
        assert not stopped.wait(.05)
    finally:
        release.set()
        stopper.join(5)
    assert stopped.is_set() and not first_thread.is_alive()


def test_upload_pixel_decode_waits_for_renderer_allocation(service, monkeypatch, tmp_path):
    from ribbon_backend import imaging
    actor = user(service)
    owner = actor['id']
    with service.db.connect() as db:
        snapshot = service.selection_snapshot(db, owner, selection(service, owner))
        paths = {r['id']: Path(r['path']) for r in db.execute('SELECT id,path FROM assets')}
    first = paths[snapshot['asset_refs'][0]]
    entered, release, upload_started, upload_done = (threading.Event() for _ in range(4))
    real_read = imaging.read_image

    def delayed_read(path):
        if path == first:
            entered.set()
            assert release.wait(5)
        return real_read(path)

    def another_upload():
        upload_started.set()
        result = upload(service, actor)
        upload_done.set()
        return result

    monkeypatch.setattr(imaging, 'read_image', delayed_read)
    with ThreadPoolExecutor(max_workers=2) as pool:
        rendering = pool.submit(imaging.render, snapshot, paths.__getitem__, tmp_path/'out.png', tmp_path/'preview.png')
        assert entered.wait(5)
        uploading = pool.submit(another_upload)
        assert upload_started.wait(5)
        try:
            assert not upload_done.wait(.05)
        finally:
            release.set()
        assert rendering.result()['width'] == snapshot['output_profile']['width']
        assert uploading.result()['id']


def test_upload_releases_pixel_lock_before_database_write(service, monkeypatch):
    from ribbon_backend import imaging
    insert = service.insert_asset

    def can_allocate_on_other_thread():
        locked = imaging._IMAGE_MEMORY_LOCK.acquire(timeout=.2)
        if locked:
            imaging._IMAGE_MEMORY_LOCK.release()
        return locked

    def checked_insert(db, asset):
        # A concurrent template save may hold the DB transaction while rendering.
        # Upload must not hold the inverse lock order at its insert point.
        with ThreadPoolExecutor(max_workers=1) as pool:
            assert pool.submit(can_allocate_on_other_thread).result()
        return insert(db, asset)

    monkeypatch.setattr(service, 'insert_asset', checked_insert)
    assert upload(service, user(service))['id']


def test_insufficient_disk_rejects_upload_before_publishing_asset(service):
    actor = user(service)
    before = len(service.assets(actor['id']))

    def no_space(directory, required):
        assert directory.is_relative_to(service.root) and required > 0
        raise OSError(28, 'synthetic no space')

    service.settings.space_reserver = no_space
    with pytest.raises(ServiceError, match='空间') as error:
        upload(service, actor)
    assert error.value.status == 507
    assert len(service.assets(actor['id'])) == before
    assert not list((service.root/'assets').glob('*.png'))


def test_insufficient_space_before_model_call_preserves_version_and_quota(service):
    owner = user(service)['id']
    design = generate(service, owner)
    original = service.version_file(owner, design['current_version_id']).read_bytes()

    def metadata_only(directory, required):
        if required > 1024 * 1024:
            raise OSError(28, 'synthetic insufficient model space')

    service.settings.space_reserver = metadata_only
    job = service.submit(owner, 'refine', dict(idempotency_key=str(uuid4()), base_version_id=design['current_version_id'], prompt='图案缩小一些'), design['id'])
    assert service.run_once()
    result = service.job(owner, job['id'])
    assert result['status'] == 'FAILED' and '空间' in result['error']
    after = service.design(owner, design['id'])
    assert after['successful_refinement_count'] == 0 and after['current_version_id'] == design['current_version_id']
    assert service.version_file(owner, design['current_version_id']).read_bytes() == original
    with service.db.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM provider_calls WHERE job_id=?', (job['id'],)).fetchone()[0] == 0


def test_model_result_save_rechecks_space_and_keeps_previous_version(service, monkeypatch):
    from ribbon_backend.providers import TestProvider
    owner = user(service)['id']
    design = generate(service, owner)
    original = service.version_file(owner, design['current_version_id']).read_bytes()
    exhausted = False

    def reserve(directory, required):
        assert directory.is_relative_to(service.root)
        if exhausted:
            raise OSError(28, 'synthetic disk filled during request')

    edit = TestProvider.edit_image

    def result_arrives(provider, *args, **kwargs):
        nonlocal exhausted
        exhausted = True
        return edit(provider, *args, **kwargs)

    service.settings.space_reserver = reserve
    monkeypatch.setattr(TestProvider, 'edit_image', result_arrives)
    job = service.submit(owner, 'refine', dict(idempotency_key=str(uuid4()), base_version_id=design['current_version_id'], prompt='背景添加波点'), design['id'])
    assert service.run_once()
    result = service.job(owner, job['id'])
    assert result['status'] == 'FAILED' and '空间' in result['error']
    after = service.design(owner, design['id'])
    assert after['successful_refinement_count'] == 0 and after['current_version_id'] == design['current_version_id']
    assert service.version_file(owner, design['current_version_id']).read_bytes() == original


def test_space_checker_cannot_target_parent_volume_or_link(service, tmp_path):
    with pytest.raises(ServiceError, match='目录'):
        service.check_space(service.root.parent, 1)
    outside = tmp_path.parent / (tmp_path.name + '-outside')
    outside.mkdir(exist_ok=True)
    link = service.root / 'redirect'
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip('Creating a symlink is unavailable in this Windows session')
    with pytest.raises(ServiceError, match='链接'):
        service.check_space(link, 1)


def test_service_rejects_volume_root_before_any_write(tmp_path, monkeypatch):
    settings = Settings(data_dir=Path(tmp_path.anchor), auth_mode='local', provider='test')

    def no_directory_write(*args, **kwargs):
        raise AssertionError('No root-directory writes are permitted')

    monkeypatch.setattr(Path, 'mkdir', no_directory_write)
    with pytest.raises(ServiceError, match='根目录'):
        Service(settings)
