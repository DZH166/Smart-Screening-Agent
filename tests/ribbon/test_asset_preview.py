"""Screen derivatives preserve original assets, ownership and cleanup fencing."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import hashlib
import io
from pathlib import Path
import sqlite3
import time

from fastapi.testclient import TestClient
from PIL import Image, ImageDraw, ImageOps
import pytest

from ribbon_backend.app import create_app
from ribbon_backend.config import Settings
from ribbon_backend.service import ServiceError


def picture(size=(128, 96)):
    im = Image.new('RGBA', size, (0, 0, 0, 0))
    ImageDraw.Draw(im).ellipse((size[0]//8, size[1]//8, size[0]*7//8, size[1]*7//8), fill='#E987AB')
    output = io.BytesIO(); im.save(output, format='PNG'); im.close()
    return output.getvalue()


@pytest.fixture
def setup(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, auth_mode='demo', provider='test'))
    with TestClient(app) as client:
        user = client.post('/api/auth/login', json={'username':'demo', 'password':'demo12345'}).json()
        yield app.state.service, app, client, user


def upload(client, value=None):
    response = client.post('/api/assets', files={'file': ('own.png', value or picture(), 'image/png')},
                           data={'kind':'pattern','name':'own test pattern'})
    assert response.status_code == 201, response.text
    return response.json()


def row(service, identifier):
    with service.db.connect() as db:
        return dict(db.execute('SELECT * FROM assets WHERE id=?', (identifier,)).fetchone())


def test_upload_original_pixels_and_bounded_alpha_preview(setup):
    service, app, client, user = setup
    value = picture((1200, 800)); asset = upload(client, value)
    assert asset['url'].endswith('/file') and '/thumbnail?v=asset-preview-v1-' in asset['thumbnail_url']
    original = client.get(asset['url']); preview = client.get(asset['thumbnail_url'])
    assert original.status_code == preview.status_code == 200
    with Image.open(io.BytesIO(value)) as expected, Image.open(io.BytesIO(original.content)) as actual:
        assert actual.size == expected.size and actual.convert('RGBA').tobytes() == expected.convert('RGBA').tobytes()
    with Image.open(io.BytesIO(preview.content)) as image:
        assert image.size == (640, 427) and image.mode == 'RGBA'
        assert image.getchannel('A').getextrema() == (0, 255)
    saved = row(service, asset['id'])
    assert hashlib.sha256(preview.content).hexdigest() == saved['thumbnail_sha256']
    assert preview.headers['cache-control'] == 'private, no-cache, must-revalidate'
    assert preview.headers['vary'] == 'Cookie'
    assert preview.headers['cross-origin-resource-policy'] == 'same-origin'


@pytest.mark.parametrize('format', ['PNG', 'WEBP'])
def test_animated_inputs_rejected_without_storing_first_frame(setup, format):
    service, app, client, user = setup
    first = Image.new('RGBA',(20,20),'red'); second = Image.new('RGBA',(20,20),'blue')
    data=io.BytesIO();first.save(data, format=format, save_all=True, append_images=[second], duration=100, loop=0)
    first.close();second.close()
    response=client.post('/api/assets',files={'file':('moving.'+format.lower(),data.getvalue())})
    assert response.status_code == 422 and '动态图像' in response.json()['detail']
    assert not list((service.root/'assets').glob('*.png'))


def test_upload_exif_orientation_survives_lossless_normalization(setup):
    service, app, client, user = setup
    image=Image.new('RGB',(32,20),'#123456');ImageDraw.Draw(image).rectangle((0,0,10,10),fill='red')
    exif=Image.Exif();exif[274]=6;data=io.BytesIO();image.save(data,format='JPEG',exif=exif);image.close()
    with Image.open(io.BytesIO(data.getvalue())) as source:
        expected=ImageOps.exif_transpose(source).convert('RGBA')
    asset=upload(client,data.getvalue())
    with Image.open(io.BytesIO(client.get(asset['url']).content)) as saved:
        assert saved.size==(20,32) and saved.convert('RGBA').tobytes()==expected.tobytes()
    expected.close()


@pytest.mark.parametrize('mutate', ['source', 'thumbnail', 'none'])
def test_etag_checked_only_after_original_and_preview_integrity(setup, mutate):
    service, app, client, user=setup;asset=upload(client)
    first=client.get(asset['thumbnail_url']);etag=first.headers['etag'];saved=row(service,asset['id'])
    head=client.head(asset['thumbnail_url']);assert head.status_code==200 and not head.content
    if mutate!='none':
        Path(saved['path' if mutate=='source' else 'thumbnail_path']).write_bytes(b'changed')
    reply=client.get(asset['thumbnail_url'],headers={'If-None-Match':etag})
    assert reply.status_code==(304 if mutate=='none' else 409)
    assert not reply.content if mutate=='none' else '校验失败' in reply.json()['detail']


def test_thumbnail_etag_does_not_bypass_other_owner_logout_or_wrong_content_version(setup):
    service,app,client,user=setup;asset=upload(client)
    etag=client.get(asset['thumbnail_url']).headers['etag']
    bad=asset['thumbnail_url'].split('?')[0]+'?v=old-content'
    assert client.get(bad,headers={'If-None-Match':etag}).status_code==404
    client.post('/api/auth/login',json={'username':'client','password':'client12345'})
    assert client.get(asset['thumbnail_url'],headers={'If-None-Match':etag}).status_code==404
    assert client.head(asset['thumbnail_url'],headers={'If-None-Match':etag}).status_code==404
    client.post('/api/auth/logout')
    assert client.get(asset['thumbnail_url'],headers={'If-None-Match':etag}).status_code==401


def test_legacy_shared_asset_preview_created_once_for_concurrent_requests(setup, monkeypatch):
    service,app,client,user=setup
    asset=service.assets(user['id'])[0];calls=[];original=service.create_asset_preview
    def create(*args):
        calls.append(1);return original(*args)
    monkeypatch.setattr(service,'create_asset_preview',create)
    with ThreadPoolExecutor(max_workers=3) as pool:
        results=list(pool.map(lambda _:service.verified_asset_preview(user['id'],asset['id']),range(3)))
    assert len(calls)==1 and len(set(results))==1
    saved=row(service,asset['id'])
    assert saved['sha256'] and saved['thumbnail_sha256']==results[0][1]


def test_preview_expires_with_its_private_unreferenced_asset(setup):
    service,app,client,user=setup;asset=upload(client);saved=row(service,asset['id'])
    with service.db.transaction() as db:
        db.execute('UPDATE assets SET retained_at=? WHERE id=?',(time.time()-service.settings.retention_seconds-60,asset['id']))
    counts=service.cleanup_expired()
    assert counts['assets']==1
    assert not Path(saved['path']).exists() and not Path(saved['thumbnail_path']).exists()
    assert client.get(asset['thumbnail_url'],headers={'If-None-Match':'*'}).status_code==404


def test_failed_database_insert_removes_only_uncommitted_upload_files(setup, monkeypatch):
    service,app,client,user=setup
    def fail(*args):raise sqlite3.OperationalError('synthetic insert failure')
    monkeypatch.setattr(service,'insert_asset',fail)
    with pytest.raises(sqlite3.OperationalError):service.upload(user,picture(),'failure','pattern')
    assert not list((service.root/'assets').glob('*.png'))
    with service.db.connect() as db:assert db.execute('SELECT COUNT(*) FROM cleanup_paths').fetchone()[0]==0


def test_commit_succeeded_then_error_never_deletes_referenced_upload(setup, monkeypatch):
    service,app,client,user=setup;transaction=service.db.transaction;calls=[]
    @contextmanager
    def uncertain():
        with transaction() as db:yield db
        calls.append(1)
        if len(calls)==1:raise sqlite3.OperationalError('synthetic post-commit error')
    monkeypatch.setattr(service.db,'transaction',uncertain)
    with pytest.raises(sqlite3.OperationalError):service.upload(user,picture(),'committed','pattern')
    with service.db.connect() as db:saved=dict(db.execute("SELECT * FROM assets WHERE name='committed'").fetchone())
    assert Path(saved['path']).is_file() and Path(saved['thumbnail_path']).is_file()
    assert service.verified_asset_preview(user['id'],saved['id'])[1]==saved['thumbnail_sha256']


def test_unlink_failure_queued_and_later_safe_cleanup_retries(setup, monkeypatch):
    service,app,client,user=setup;unlink=Path.unlink
    def fail_insert(*args):raise sqlite3.OperationalError('synthetic insert failure')
    def blocked(path,*args,**kwargs):
        if path.parent==service.root/'assets' and path.suffix=='.png':raise PermissionError('synthetic file busy')
        return unlink(path,*args,**kwargs)
    monkeypatch.setattr(service,'insert_asset',fail_insert);monkeypatch.setattr(Path,'unlink',blocked)
    with pytest.raises(sqlite3.OperationalError):service.upload(user,picture(),'failure','pattern')
    with service.db.connect() as db:assert db.execute('SELECT COUNT(*) FROM cleanup_paths').fetchone()[0]==2
    assert len(list((service.root/'assets').glob('*.png')))==2
    monkeypatch.setattr(Path,'unlink',unlink);service.cleanup_expired()
    assert not list((service.root/'assets').glob('*.png'))


def test_unavailable_database_conservatively_keeps_files(setup, monkeypatch):
    service,app,client,user=setup
    @contextmanager
    def unavailable():
        raise sqlite3.OperationalError('synthetic unavailable database');yield
    monkeypatch.setattr(service.db,'transaction',unavailable)
    with pytest.raises(sqlite3.OperationalError):service.upload(user,picture(),'unavailable','pattern')
    assert len(list((service.root/'assets').glob('*.png')))==2


def test_host_identity_read_fast_path_and_role_transitions_remain_authoritative(tmp_path, monkeypatch):
    from ribbon_backend.service import Service
    service=Service(Settings(data_dir=tmp_path,auth_mode='hsd',provider='test'))
    owner='hsd:'+'a'*64;customer=service.ensure_external_user(owner,'customer')
    original=service.db.transaction;calls=[]
    @contextmanager
    def observe():
        calls.append(1)
        with original() as db:yield db
    monkeypatch.setattr(service.db,'transaction',observe)
    assert service.ensure_external_user(owner,'customer')==customer and not calls
    assert service.ensure_external_user(owner,'admin')['role']=='admin' and len(calls)==1
    assert service.ensure_external_user(owner,'customer')['role']=='customer' and len(calls)==2
    with original() as db:db.execute('UPDATE users SET username=? WHERE id=?',('unexpected-collision',owner))
    with pytest.raises(ServiceError) as failure:service.ensure_external_user(owner,'customer')
    assert failure.value.status==409 and len(calls)==2
