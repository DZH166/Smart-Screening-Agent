"""Legacy shortlist uses bounded previews, never thumbnail identity as a merge decision."""
from io import BytesIO
from pathlib import Path

from PIL import Image

from test_asset_dedupe_design_delete import actor, record, service, upload


def image_bytes(color='#778899', size=(1024, 1024), icc=None, changed_pixel=False):
    with Image.new('RGBA', size, color) as image:
        if changed_pixel:
            image.putpixel((size[0] // 2, size[1] // 2), (129, 128, 128, 255))
        encoded = BytesIO()
        options = {'icc_profile': icc} if icc is not None else {}
        image.save(encoded, format='PNG', compress_level=3, **options)
        return encoded.getvalue()


def unindex(service, ids, without_preview=False):
    with service.db.transaction() as db:
        for asset_id in ids:
            db.execute('UPDATE assets SET pixel_sha256=NULL,thumbnail_pixel_sha256=NULL WHERE id=?', (asset_id,))
            if without_preview:
                db.execute('UPDATE assets SET thumbnail_path=NULL,thumbnail_sha256=NULL WHERE id=?', (asset_id,))


def test_unrelated_new_upload_reads_only_legacy_previews_then_reuses_cached_fingerprints(service, monkeypatch):
    legacy = [upload(service, data=image_bytes(color=(30 + n * 12, 40, 80, 255))) for n in range(8)]
    unindex(service, [a['id'] for a in legacy])
    def forbidden_original(*args):
        raise AssertionError('Unrelated legacy originals must not be decoded')
    monkeypatch.setattr(service, 'legacy_upload_pixel_digest', forbidden_original)
    first = upload(service, data=image_bytes(color='#77dd66'))
    assert not first['deduplicated']
    for asset in legacy:
        indexed = record(service, asset['id'])
        assert indexed['pixel_sha256'] is None and indexed['thumbnail_pixel_sha256']
    def forbidden_preview(*args):
        raise AssertionError('A previously cached negative shortlist must not decode previews again')
    monkeypatch.setattr(service, 'legacy_preview_pixel_digest', forbidden_preview)
    second = upload(service, data=image_bytes(color='#dd66dd'))
    assert not second['deduplicated'] and second['id'] != first['id']


def test_equal_640px_preview_does_not_merge_different_original_pixels(service, monkeypatch):
    first = upload(service, data=image_bytes(color=(128, 128, 128, 255), size=(2048, 2048)))
    saved = record(service, first['id'])
    unindex(service, [first['id']])
    original = service.legacy_upload_pixel_digest
    calls = []
    def observe(asset):
        calls.append(asset['id'])
        return original(asset)
    monkeypatch.setattr(service, 'legacy_upload_pixel_digest', observe)
    changed = upload(service, data=image_bytes(color=(128, 128, 128, 255), size=(2048, 2048), changed_pixel=True))
    other = record(service, changed['id'])
    assert saved['thumbnail_pixel_sha256'] == other['thumbnail_pixel_sha256']
    assert saved['pixel_sha256'] != other['pixel_sha256']
    assert not changed['deduplicated'] and changed['id'] != first['id']
    assert calls == [first['id']]


def test_legacy_icc_encoding_difference_does_not_hide_identical_original_rgba(service, monkeypatch):
    first = upload(service, data=image_bytes(size=(512, 512), icc=b'synthetic-profile-one'))
    saved = record(service, first['id'])
    source_bytes = Path(saved['path']).read_bytes()
    unindex(service, [first['id']])
    original = service.legacy_upload_pixel_digest
    calls = []
    def observe(asset):
        calls.append(asset['id'])
        return original(asset)
    monkeypatch.setattr(service, 'legacy_upload_pixel_digest', observe)
    second = upload(service, data=image_bytes(size=(512, 512), icc=b'synthetic-profile-two'))
    assert second['deduplicated'] and second['id'] == first['id']
    assert calls == [first['id']]
    indexed = record(service, first['id'])
    assert indexed['pixel_sha256'] == saved['pixel_sha256']
    assert indexed['thumbnail_pixel_sha256'] == saved['thumbnail_pixel_sha256']
    assert indexed['sha256'] == saved['sha256'] and indexed['thumbnail_sha256'] == saved['thumbnail_sha256']
    assert Path(saved['path']).read_bytes() == source_bytes


def test_no_preview_legacy_row_with_identical_normalized_bytes_is_indexed_immediately(service, monkeypatch):
    data = image_bytes()
    first = upload(service, data=data)
    saved = record(service, first['id'])
    unindex(service, [first['id']], without_preview=True)
    def forbidden(*args):
        raise AssertionError('Equal verified PNG bytes need no additional original decode')
    monkeypatch.setattr(service, 'legacy_upload_pixel_digest', forbidden)
    second = upload(service, data=data)
    assert second['deduplicated'] and second['id'] == first['id']
    assert record(service, first['id'])['pixel_sha256'] == saved['pixel_sha256']


def test_no_preview_different_encoding_is_deferred_until_normal_preview_derivation(service):
    first = upload(service, data=image_bytes(size=(512, 512), icc=b'synthetic-profile-one'))
    saved = record(service, first['id'])
    unindex(service, [first['id']], without_preview=True)
    incoming = image_bytes(size=(512, 512), icc=b'synthetic-profile-two')
    second = upload(service, data=incoming)
    # This explicit legacy boundary is deferred, rather than forcing every
    # unknown original in the gallery to be decoded on an unrelated upload.
    assert not second['deduplicated'] and second['id'] != first['id']
    assert record(service, first['id'])['pixel_sha256'] is None
    service.verified_asset_preview(actor(service)['id'], first['id'])
    indexed = record(service, first['id'])
    assert indexed['pixel_sha256'] == saved['pixel_sha256']
    assert indexed['thumbnail_pixel_sha256'] == saved['thumbnail_pixel_sha256']
    third = upload(service, data=incoming)
    assert third['deduplicated'] and third['id'] == first['id']
