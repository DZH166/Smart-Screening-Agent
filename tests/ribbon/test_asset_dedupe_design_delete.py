"""Exact upload identity and recoverable work deletion; synthetic local images only."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
from pathlib import Path
import threading
from uuid import uuid4

from fastapi.testclient import TestClient
from PIL import Image, ImageOps, PngImagePlugin
import pytest

from ribbon_backend.app import create_app
from ribbon_backend.config import Settings
from ribbon_backend.service import Service, ServiceError


@pytest.fixture
def service(tmp_path):
    instance = Service(Settings(data_dir=tmp_path, auth_mode='demo', provider='test', start_worker=False))
    yield instance
    instance.stop()


def actor(service, username='demo'):
    with service.db.connect() as db:
        return dict(db.execute('SELECT id,username,role FROM users WHERE username=?', (username,)).fetchone())


def picture(*, variant=0, format='PNG', compression=6, metadata=False, size=(40, 24)):
    with Image.new('RGBA', size, '#35a78f') as image:
        image.putpixel((3, 4), (120, 20, 45 + variant, 255))
        data = io.BytesIO()
        info = PngImagePlugin.PngInfo()
        if metadata:
            info.add_text('synthetic-comment', 'Encoding and filenames do not define image identity')
        image.save(data, format=format, compress_level=compression, pnginfo=info)
        return data.getvalue()


def upload(service, who=None, **kwargs):
    return service.upload(who or actor(service), kwargs.pop('data', picture()), kwargs.pop('name', 'synthetic'),
                          kwargs.pop('kind', 'pattern'), **kwargs)


def choices(service, owner, pattern_id=None):
    return dict(asset_ids=[pattern_id or service.assets(owner, 'pattern')[0]['id']],
                background_id=service.assets(owner, 'background')[0]['id'], template_id='grid')


def generated(service, owner, pattern_id=None):
    design = service.create_design(owner, 'synthetic work')
    job = service.submit(owner, 'generate', dict(idempotency_key=str(uuid4()), **choices(service, owner, pattern_id)), design['id'])
    assert service.run_once()
    assert service.job(owner, job['id'])['status'] == 'SUCCEEDED'
    return service.design(owner, design['id'])


def record(service, asset_id):
    with service.db.connect() as db:
        return dict(db.execute('SELECT * FROM assets WHERE id=?', (asset_id,)).fetchone())


def test_reupload_uses_exact_normalized_pixels_without_reencoding_or_renaming(service, monkeypatch):
    first = upload(service, data=picture(compression=0), name='original name')
    saved = record(service, first['id'])
    original_bytes = Path(saved['path']).read_bytes()
    def forbidden(*args, **kwargs):
        raise AssertionError('A duplicate must not encode or write a new preview')
    monkeypatch.setattr('ribbon_backend.service._save_png', forbidden)
    monkeypatch.setattr(service, 'write_asset_preview', forbidden)
    again = upload(service, data=picture(compression=9, metadata=True), name='different filename')
    assert first['deduplicated'] is False and again['deduplicated'] is True
    assert again['id'] == first['id'] and again['name'] == 'original name'
    assert Path(saved['path']).read_bytes() == original_bytes
    assert len(list((service.root / 'assets').glob('*.png'))) == 2


def test_exif_oriented_jpeg_matches_decoded_oriented_png(service):
    with Image.new('RGB', (24, 16), '#123456') as image:
        image.putpixel((3, 4), (255, 0, 0))
        exif = Image.Exif(); exif[274] = 6
        jpeg = io.BytesIO(); image.save(jpeg, format='JPEG', exif=exif)
    first = upload(service, data=jpeg.getvalue())
    with Image.open(io.BytesIO(jpeg.getvalue())) as source, ImageOps.exif_transpose(source) as oriented:
        png = io.BytesIO(); oriented.convert('RGBA').save(png, format='PNG')
    second = upload(service, data=png.getvalue())
    assert first['id'] == second['id'] and second['deduplicated']


def test_one_pixel_canvas_kind_owner_and_shared_boundaries_do_not_merge(service):
    first = upload(service)
    changed = upload(service, data=picture(variant=1))
    canvas = upload(service, data=picture(size=(24, 40)))
    background = upload(service, kind='background')
    other = upload(service, actor(service, 'client'))
    admin = actor(service, 'admin')
    private = upload(service, admin)
    shared = upload(service, admin, shared=True)
    assert len({a['id'] for a in (first, changed, canvas, background, other, private, shared)}) == 7
    assert upload(service, admin, shared=True)['id'] == shared['id']
    assert upload(service, admin)['id'] == private['id']
    with pytest.raises(ServiceError) as denied:
        upload(service, shared=True)
    assert denied.value.status == 403


def test_legacy_pixel_index_and_hidden_reupload_preserve_referenced_asset(service):
    who = actor(service); owner = who['id']
    first = upload(service)
    saved = record(service, first['id'])
    work = generated(service, owner, first['id'])
    version = work['versions'][0]
    master = service.version_file(owner, version['id']).read_bytes()
    with service.db.transaction() as db:
        db.execute('UPDATE assets SET pixel_sha256=NULL WHERE id=?', (first['id'],))
    service.hide_asset(who, first['id'])
    second = upload(service, data=picture(metadata=True))
    assert second['id'] == first['id'] and second['deduplicated']
    indexed = record(service, first['id'])
    assert indexed['enabled'] == 1 and indexed['pixel_sha256']
    assert all(indexed[k] == saved[k] for k in ('path', 'sha256', 'name', 'thumbnail_path', 'thumbnail_sha256'))
    assert service.design(owner, work['id'])['versions'][0] == version
    assert service.version_file(owner, version['id']).read_bytes() == master


@pytest.mark.parametrize('defer_cleanup', [False, True])
def test_concurrent_same_owner_uploads_commit_one_asset_and_clean_losing_files(service, monkeypatch, defer_cleanup):
    other = Service(service.settings)
    original = Service.store_uploaded_image
    ready = threading.Barrier(2)
    def prepare(*args, **kwargs):
        result = original(*args, **kwargs)
        ready.wait(timeout=10)
        return result
    monkeypatch.setattr(Service, 'store_uploaded_image', prepare)
    if defer_cleanup:
        monkeypatch.setattr(Service, 'cleanup_uncommitted_asset_files', lambda *args: None)
    who = actor(service)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda instance: upload(instance, who), (service, other)))
    assert len({r['id'] for r in results}) == 1
    assert sorted(r['deduplicated'] for r in results) == [False, True]
    if defer_cleanup:
        with service.db.connect() as db:
            assert db.execute('SELECT COUNT(*) FROM cleanup_paths').fetchone()[0] == 2
        assert len(list((service.root / 'assets').glob('*.png'))) == 4
        assert service.cleanup_expired()['files_failed'] == 0
    with service.db.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM assets WHERE owner_id=? AND source='upload'", (who['id'],)).fetchone()[0] == 1
        assert db.execute('SELECT COUNT(*) FROM cleanup_paths').fetchone()[0] == 0
    assert len(list((service.root / 'assets').glob('*.png'))) == 2
    assert service.verified_asset_preview(who['id'], results[0]['id'])


def test_existing_duplicate_rows_and_their_versions_are_never_merged_or_deleted(service):
    owner = actor(service)['id']
    first = upload(service)
    saved = record(service, first['id'])
    legacy_id = uuid4().hex
    legacy_path = service.root / 'assets' / f'{legacy_id}.png'
    legacy_path.write_bytes(Path(saved['path']).read_bytes())
    with service.db.transaction() as db:
        service.insert_asset(db, {**saved, 'id': legacy_id, 'path': str(legacy_path), 'name': 'legacy duplicate', 'created_at': '2099-01-01'})
        db.execute('UPDATE assets SET pixel_sha256=NULL WHERE id=?', (first['id'],))
    first_work = generated(service, owner, first['id'])
    legacy_work = generated(service, owner, legacy_id)
    snapshots = [work['versions'] for work in (first_work, legacy_work)]
    assert upload(service)['id'] == first['id']
    with service.db.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM assets WHERE owner_id=? AND source='upload'", (owner,)).fetchone()[0] == 2
    assert legacy_path.is_file()
    assert [service.design(owner, work['id'])['versions'] for work in (first_work, legacy_work)] == snapshots


@pytest.mark.parametrize('damaged_part', ['source', 'thumbnail'])
def test_damaged_earliest_duplicate_is_skipped_for_a_later_valid_candidate(service, damaged_part):
    who = actor(service)
    first = upload(service)
    saved = record(service, first['id'])
    good_id = uuid4().hex
    good_path = service.root / 'assets' / f'{good_id}.png'
    good_path.write_bytes(Path(saved['path']).read_bytes())
    with service.db.transaction() as db:
        service.insert_asset(db, {**saved, 'id': good_id, 'path': str(good_path), 'name': 'valid legacy duplicate', 'created_at': '2099-01-01'})
    broken_path = Path(saved['path' if damaged_part == 'source' else 'thumbnail_path'])
    broken_path.write_bytes(b'original damaged bytes must remain untouched')
    before = record(service, first['id'])
    result = upload(service, data=picture(metadata=True))
    assert result['deduplicated'] and result['id'] == good_id
    assert record(service, first['id']) == before
    assert broken_path.read_bytes() == b'original damaged bytes must remain untouched'
    assert service.verified_asset_path(who['id'], good_id) == good_path
    assert service.verified_asset_preview(who['id'], good_id)
    with service.db.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM assets WHERE owner_id=? AND source='upload'", (who['id'],)).fetchone()[0] == 2


@pytest.mark.parametrize('damage', ['missing', 'corrupt'])
def test_only_damaged_hidden_candidate_allows_a_new_upload_without_repairing_old_references(service, damage):
    who = actor(service); owner = who['id']
    first = upload(service)
    saved = record(service, first['id'])
    work = generated(service, owner, first['id'])
    version = work['versions'][0]
    master = service.version_file(owner, version['id']).read_bytes()
    service.hide_asset(who, first['id'])
    old_path = Path(saved['path'])
    if damage == 'missing':
        old_path.unlink()
    else:
        old_path.write_bytes(b'old corrupted source remains corrupted')
    before = record(service, first['id'])
    result = upload(service, data=picture(metadata=True))
    assert not result['deduplicated'] and result['id'] != first['id']
    assert record(service, first['id']) == before and before['enabled'] == 0
    assert (not old_path.exists()) if damage == 'missing' else old_path.read_bytes() == b'old corrupted source remains corrupted'
    with pytest.raises(ServiceError) as old_download:
        service.verified_asset_path(owner, first['id'])
    assert old_download.value.status == (404 if damage == 'missing' else 409)
    assert service.verified_asset_path(owner, result['id']).is_file()
    assert upload(service)['id'] == result['id']
    # Existing masters are separate immutable files; their saved source IDs
    # are not repaired, remapped or silently replaced by the new upload.
    assert service.design(owner, work['id'])['versions'][0] == version
    assert service.version_file(owner, version['id']).read_bytes() == master


def test_fast_candidate_corrupted_before_commit_is_reencoded_outside_write_transaction(service, monkeypatch):
    first = upload(service)
    saved = record(service, first['id'])
    original = service.store_uploaded_image
    calls = []
    def prepare(*args, **kwargs):
        result = original(*args, **kwargs)
        calls.append(1)
        if len(calls) == 1:
            assert 'thumbnail_path' not in result
            Path(saved['path']).write_bytes(b'changed between lookup and transaction')
        return result
    monkeypatch.setattr(service, 'store_uploaded_image', prepare)
    result = upload(service)
    assert len(calls) == 2 and result['id'] != first['id'] and not result['deduplicated']
    assert Path(saved['path']).read_bytes() == b'changed between lookup and transaction'
    assert service.verified_asset_preview(actor(service)['id'], result['id'])


def test_delete_restore_preserves_branches_quota_requests_and_exact_download(service):
    who = actor(service); owner = who['id']
    asset = upload(service)
    work = generated(service, owner, asset['id'])
    initial = work['current_version_id']
    job = service.submit(owner, 'refine', dict(idempotency_key=str(uuid4()), base_version_id=initial,
        prompt='应用所选配置', selection={**choices(service, owner, asset['id']), 'template_id': 'single'}), work['id'])
    assert service.run_once() and service.job(owner, job['id'])['status'] == 'SUCCEEDED'
    edited = service.design(owner, work['id'])
    work = service.rollback(owner, work['id'], edited['current_version_id'])
    payloads = {v['id']: service.version_file(owner, v['id']).read_bytes() for v in work['versions']}
    with service.db.connect() as db:
        before = {table: [tuple(r) for r in db.execute(f'SELECT * FROM {table} ORDER BY 1')] for table in ('assets', 'versions', 'quota_events', 'jobs')}
    deleted = service.delete_design(owner, work['id'])
    assert service.delete_design(owner, work['id']) == deleted  # Retry does not extend retention.
    assert service.designs(owner) == []
    assert service.designs(owner, deleted=True)[0]['deleted_at'] == deleted['deleted_at']
    with pytest.raises(ServiceError) as hidden:
        service.design(owner, work['id'])
    assert hidden.value.status == 404
    with pytest.raises(ServiceError) as blocked:
        service.rollback(owner, work['id'], initial)
    assert blocked.value.status == 404
    with pytest.raises(ServiceError) as blocked:
        service.submit(owner, 'refine', dict(idempotency_key=str(uuid4()), base_version_id=initial, prompt='旋转'), work['id'])
    assert blocked.value.status == 404
    for version_id, content in payloads.items():
        assert service.version_file(owner, version_id).read_bytes() == content
    restored = service.restore_design(owner, work['id'])
    assert restored['deleted_at'] is None and restored['current_version_id'] == initial
    assert restored['versions'] == work['versions'] and restored['successful_refinement_count'] == 1
    assert service.designs(owner, deleted=True) == []
    with service.db.connect() as db:
        assert all([tuple(r) for r in db.execute(f'SELECT * FROM {table} ORDER BY 1')] == expected for table, expected in before.items())
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []


@pytest.mark.parametrize('status', ['QUEUED', 'RUNNING', 'RECONCILING'])
def test_busy_work_cannot_be_deleted_even_if_active_pointer_is_missing(service, status):
    owner = actor(service)['id']
    work = service.create_design(owner, 'busy synthetic')
    job = service.submit(owner, 'generate', dict(idempotency_key=str(uuid4()), **choices(service, owner)), work['id'])
    with service.db.transaction() as db:
        db.execute('UPDATE jobs SET status=? WHERE id=?', (status, job['id']))
        db.execute('UPDATE designs SET active_job_id=NULL WHERE id=?', (work['id'],))
    with pytest.raises(ServiceError) as busy:
        service.delete_design(owner, work['id'])
    assert busy.value.status == 409 and service.design(owner, work['id'])['deleted_at'] is None


def test_delete_submit_race_serializes_without_deleted_running_work(service):
    owner = actor(service)['id']
    work = service.create_design(owner, 'racing synthetic')
    ready = threading.Barrier(2)
    def perform(delete):
        ready.wait(timeout=10)
        try:
            if delete:
                return service.delete_design(owner, work['id'])
            return service.submit(owner, 'generate', dict(idempotency_key=str(uuid4()), **choices(service, owner)), work['id'])
        except ServiceError as error:
            return error.status
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(perform, [True, False]))
    with service.db.connect() as db:
        row = db.execute('SELECT * FROM designs WHERE id=?', (work['id'],)).fetchone()
        jobs = db.execute('SELECT * FROM jobs WHERE design_id=?', (work['id'],)).fetchall()
    assert not (row['deleted_at'] is not None and jobs)
    assert sorted(r for r in results if isinstance(r, int)) in ([404], [409])


def test_deleted_work_retention_download_lease_and_live_asset_reference(service):
    who = actor(service); owner = who['id']; asset = upload(service)
    work = generated(service, owner, asset['id'])
    deleted = service.delete_design(owner, work['id'])
    saved = record(service, asset['id'])
    # Deletion grants its own ordinary 50-hour recovery window.
    assert service.cleanup_expired(now=deleted['deleted_at'] + service.settings.retention_seconds - 1)['designs'] == 0
    with service.resource_lease(owner, version_id=work['current_version_id']):
        assert service.cleanup_expired(now=deleted['deleted_at'] + service.settings.retention_seconds + 1)['designs'] == 0
        assert service.version_file(owner, work['current_version_id']).is_file()
    # A newer work using the deduplicated source keeps it after the old work expires.
    newer = generated(service, owner, asset['id'])
    future = deleted['deleted_at'] + service.settings.retention_seconds + 2
    with service.db.transaction() as db:
        db.execute('UPDATE designs SET retained_at=? WHERE id=?', (future, newer['id']))
    assert service.cleanup_expired(now=future)['designs'] == 1
    assert Path(saved['path']).is_file() and service.version_file(owner, newer['current_version_id']).is_file()
    with pytest.raises(ServiceError) as gone:
        service.restore_design(owner, work['id'])
    assert gone.value.status == 404


def test_api_delete_restore_and_deleted_lists_are_owner_isolated(service):
    app = create_app(service.settings, service=service)
    with TestClient(app) as client:
        owner = client.post('/api/auth/login', json=dict(username='demo', password='demo12345')).json()['id']
        work = generated(service, owner)
        version = work['versions'][0]
        expected = hashlib.sha256(service.version_file(owner, version['id']).read_bytes()).hexdigest()
        assert client.delete('/api/designs/' + work['id']).status_code == 200
        assert client.get('/api/designs').json() == []
        assert client.get('/api/designs?deleted=true').json()[0]['id'] == work['id']
        assert hashlib.sha256(client.get(version['download_url']).content).hexdigest() == expected
        for username in ('client', 'admin'):
            client.post('/api/auth/login', json=dict(username=username, password=username + '12345'))
            assert client.get('/api/designs?deleted=true').json() == []
            assert client.delete('/api/designs/' + work['id']).status_code == 404
            assert client.post('/api/designs/' + work['id'] + '/restore').status_code == 404
            assert client.get(version['download_url']).status_code == 404
        client.post('/api/auth/login', json=dict(username='demo', password='demo12345'))
        restored = client.post('/api/designs/' + work['id'] + '/restore')
        assert restored.status_code == 200 and restored.json()['deleted_at'] is None
