from pathlib import Path
import hashlib
import stat
import zipfile

import cv2
import numpy as np
import pymupdf
import pytest

from hsd_tool.matching import scan_and_match
import hsd_tool.matching as matching


def artwork(seed=9):
    rng = np.random.default_rng(seed)
    image = np.full((280, 800, 3), 245, np.uint8)
    for i in range(95):
        x, y = int(rng.integers(5, 770)), int(rng.integers(5, 250))
        color = tuple(int(x) for x in rng.integers(0, 215, 3))
        cv2.circle(image, (x, y), int(rng.integers(4, 23)), color, -1)
        cv2.putText(image, str(i), (x, y), cv2.FONT_HERSHEY_SIMPLEX, .35, (15, 20, 25), 1)
    return image


def save_png(path, image):
    cv2.imencode('.png', image)[1].tofile(str(path))
    return str(path)


def save_ai(path, image, pages=1):
    encoded = cv2.imencode('.png', image)[1].tobytes()
    with pymupdf.open() as doc:
        for _ in range(pages):
            page = doc.new_page(width=image.shape[1], height=image.shape[0])
            page.insert_image(page.rect, stream=encoded)
        doc.save(path)
    return path


def setup_case(tmp_path, originals, queries=None, pages=1):
    source = tmp_path / 'source'
    source.mkdir()
    for i, image in enumerate(originals):
        save_ai(source / f'original_{i}.ai', image, pages=pages)
    rows = []
    for i, image in enumerate(queries or [originals[0]]):
        rows.append({'id': f'r{i + 2}', 'row_number': i + 2, 'number': '',
                     'issue': None, 'image_path': save_png(tmp_path / f'row_{i}.png', image)})
    return source, rows


def test_same_picture_is_auto_and_sources_are_unchanged(tmp_path):
    image = artwork()
    query = cv2.resize(image, (1200, 420))
    source, rows = setup_case(tmp_path, [image, artwork(17)], [query])
    original = source / 'original_0.ai'
    before = original.read_bytes()
    result = scan_and_match(str(source), rows, str(tmp_path / 'work'))
    assert result['matches'][0]['status'] == 'auto'
    assert result['matches'][0]['file_id'] == 'f0001'
    assert original.read_bytes() == before
    assert result['files'][0]['source_sha256'] == hashlib.sha256(before).hexdigest()
    assert Path(result['files'][0]['preview_path']).is_relative_to(tmp_path / 'work')


def test_duplicate_ai_previews_require_review(tmp_path):
    image = artwork()
    source, rows = setup_case(tmp_path, [image, image])
    result = scan_and_match(str(source), rows, str(tmp_path / 'work'))
    assert result['matches'][0]['status'] == 'review'
    assert result['matches'][0]['file_id'] is None
    assert len(result['matches'][0]['candidates']) == 2


def test_nearly_identical_files_require_review(tmp_path):
    image = artwork()
    near = image.copy()
    cv2.circle(near, (610, 180), 9, (80, 50, 120), -1)
    source, rows = setup_case(tmp_path, [image, near])
    result = scan_and_match(str(source), rows, str(tmp_path / 'work'))
    assert result['matches'][0]['status'] == 'review'


def test_same_file_claimed_by_two_rows_requires_review(tmp_path):
    image = artwork()
    source, rows = setup_case(tmp_path, [image], [image, image])
    result = scan_and_match(str(source), rows, str(tmp_path / 'work'))
    assert [m['status'] for m in result['matches']] == ['review', 'review']
    assert all(m['file_id'] is None for m in result['matches'])


def test_unrelated_artwork_is_not_assigned(tmp_path):
    source, rows = setup_case(tmp_path, [artwork(1)], [artwork(70)])
    result = scan_and_match(str(source), rows, str(tmp_path / 'work'))
    assert result['matches'][0]['status'] != 'auto'
    assert result['matches'][0]['file_id'] is None


def test_color_variant_is_never_auto(tmp_path):
    image = artwork()
    changed = image.copy()
    changed[:, :, [0, 2]] = changed[:, :, [2, 0]]
    source, rows = setup_case(tmp_path, [changed], [image])
    result = scan_and_match(str(source), rows, str(tmp_path / 'work'))
    assert result['matches'][0]['status'] != 'auto'


def test_repeated_strip_is_verified_across_all_copies(tmp_path):
    image = artwork()
    repeated = np.tile(image, (1, 3, 1))[:, :2000]
    source, rows = setup_case(tmp_path, [image], [repeated])
    result = scan_and_match(str(source), rows, str(tmp_path / 'work'))
    assert result['matches'][0]['status'] == 'auto'


def test_shared_picture_with_unrelated_extra_content_needs_review(tmp_path):
    image = artwork()
    composite = np.concatenate([image, artwork(99)[:, :200]], axis=1)
    source, rows = setup_case(tmp_path, [image], [composite])
    result = scan_and_match(str(source), rows, str(tmp_path / 'work'))
    assert result['matches'][0]['status'] != 'auto'


def test_ai_with_unrelated_extra_content_needs_review(tmp_path):
    image = artwork()
    composite = np.concatenate([image, artwork(99)[:, :200]], axis=1)
    source, rows = setup_case(tmp_path, [composite], [image])
    result = scan_and_match(str(source), rows, str(tmp_path / 'work'))
    assert result['matches'][0]['status'] != 'auto'


def test_ai_with_extra_verified_repeat_can_match(tmp_path):
    image = artwork()
    composite = np.concatenate([image, image], axis=1)
    source, rows = setup_case(tmp_path, [composite], [image])
    result = scan_and_match(str(source), rows, str(tmp_path / 'work'))
    assert result['matches'][0]['status'] == 'auto'


def test_ai_with_white_margin_can_match(tmp_path):
    image = artwork()
    bordered = cv2.copyMakeBorder(image, 0, 0, 80, 80, cv2.BORDER_CONSTANT, value=(255, 255, 255))
    source, rows = setup_case(tmp_path, [bordered], [image])
    result = scan_and_match(str(source), rows, str(tmp_path / 'work'))
    assert result['matches'][0]['status'] == 'auto'


def test_declared_ai_trimbox_excludes_printing_bleed(tmp_path):
    image = artwork()
    source, rows = setup_case(tmp_path, [image], [image[18:-18]])
    path = source / 'original_0.ai'
    with pymupdf.open(path) as doc:
        doc[0].set_trimbox(pymupdf.Rect(0, 18, image.shape[1], image.shape[0] - 18))
        payload = doc.tobytes()
    path.write_bytes(payload)
    before = path.read_bytes()
    result = scan_and_match(str(source), rows, str(tmp_path / 'work'))
    assert result['matches'][0]['status'] == 'auto'
    assert result['files'][0]['uses_trimbox'] is True
    assert path.read_bytes() == before


def test_local_design_alteration_is_not_auto(tmp_path):
    image = artwork()
    changed = image.copy()
    cv2.rectangle(changed, (400, 100), (540, 170), (0, 0, 0), -1)
    source, rows = setup_case(tmp_path, [changed], [image])
    result = scan_and_match(str(source), rows, str(tmp_path / 'work'))
    assert result['matches'][0]['status'] != 'auto'


def test_multi_page_file_needs_manual_review(tmp_path):
    source, rows = setup_case(tmp_path, [artwork()], pages=2)
    result = scan_and_match(str(source), rows, str(tmp_path / 'work'))
    assert result['files'][0]['page_count'] == 2
    assert result['files'][0]['issue']
    assert result['matches'][0]['status'] == 'review'


def test_corrupt_and_non_pdf_ai_report_individually(tmp_path):
    source, rows = setup_case(tmp_path, [artwork()])
    (source / 'bad.ai').write_bytes(b'%PDF-1.4 corrupt data')
    (source / 'legacy.ai').write_bytes(b'%!PS-Adobe EPS AI')
    result = scan_and_match(str(source), rows, str(tmp_path / 'work'))
    assert len(result['files']) == 3
    assert sum(bool(f['issue']) for f in result['files']) == 2
    assert result['matches'][0]['status'] == 'auto'


@pytest.mark.parametrize('name', ['../escape.ai', '/root.ai', 'C:/drive.ai',
                                  'folder/../../escape.ai', 'folder\\..\\escape.ai',
                                  'folder/name.ai:stream', 'folder /file.ai'])
def test_zip_traversal_is_rejected(tmp_path, name):
    archive = tmp_path / 'bad.zip'
    with zipfile.ZipFile(archive, 'w') as z:
        z.writestr(name, b'not read')
    with pytest.raises(ValueError, match='不安全路径'):
        scan_and_match(str(archive), [], str(tmp_path / 'work'))
    assert not (tmp_path / 'escape.ai').exists()


def test_zip_symlink_is_rejected(tmp_path):
    archive = tmp_path / 'link.zip'
    info = zipfile.ZipInfo('link.ai')
    info.create_system = 3
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(archive, 'w') as z:
        z.writestr(info, '../outside.ai')
    with pytest.raises(ValueError, match='符号链接'):
        scan_and_match(str(archive), [], str(tmp_path / 'work'))


def test_zip_resource_limit_before_extraction(tmp_path, monkeypatch):
    archive = tmp_path / 'oversize.zip'
    with zipfile.ZipFile(archive, 'w') as z:
        z.writestr('large.ai', b'x' * 200)
    monkeypatch.setattr(matching, 'MAX_FILE_BYTES', 100)
    with pytest.raises(ValueError, match='容量'):
        scan_and_match(str(archive), [], str(tmp_path / 'work'))
    assert not list((tmp_path / 'work').rglob('*.ai'))


def test_zip_extracts_private_names_and_original_remains_intact(tmp_path):
    image = artwork()
    source, rows = setup_case(tmp_path, [image])
    archive = tmp_path / 'input.zip'
    payload = (source / 'original_0.ai').read_bytes()
    with zipfile.ZipFile(archive, 'w') as z:
        z.writestr('设计图/相同名字.ai', payload)
        z.writestr('另一目录/相同名字.ai', payload)
    before = archive.read_bytes()
    result = scan_and_match(str(archive), rows, str(tmp_path / 'work'))
    assert len(result['files']) == 2
    assert len({f['source_path'] for f in result['files']}) == 2
    assert all(Path(f['source_path']).read_bytes() == payload for f in result['files'])
    assert archive.read_bytes() == before
    assert result['matches'][0]['status'] == 'review'


def test_workbook_issue_blocks_automatic_matching(tmp_path):
    source, rows = setup_case(tmp_path, [artwork()])
    rows[0]['issue'] = '多张图片歧义'
    result = scan_and_match(str(source), rows, str(tmp_path / 'work'))
    assert result['matches'][0]['status'] != 'auto'
    assert not result['matches'][0]['candidates']


# ---------- 长条图案与重复纹样：可靠匹配直接自动通过 ----------

def stripes(width=900, height=140, period=36):
    """Horizontal repeat: a long strip with few unique features."""
    image = np.full((height, width, 3), 250, np.uint8)
    palette = [(40, 60, 150), (232, 232, 236), (198, 118, 58), (238, 218, 96)]
    x, index = 0, 0
    while x < width:
        cv2.rectangle(image, (x, 0), (min(x + period, width), height), palette[index % len(palette)], -1)
        x += period
        index += 1
    return image


def dots(width=800, height=300, spacing=46, radius=12):
    """Regularly repeated dots: repetitive and low in unique detail."""
    image = np.full((height, width, 3), 248, np.uint8)
    for y in range(spacing // 2, height, spacing):
        for x in range(spacing // 2, width, spacing):
            cv2.circle(image, (x, y), radius, (70, 110, 180), -1)
    return image


def test_repeated_stripe_crop_is_auto(tmp_path):
    strip = stripes()
    source, rows = setup_case(tmp_path, [strip], [strip[:, 210:690].copy()])
    result = scan_and_match(str(source), rows, str(tmp_path / 'work'))
    assert result['matches'][0]['status'] == 'auto'
    assert result['matches'][0]['file_id'] == 'f0001'


def test_repeated_stripe_scaled_is_auto(tmp_path):
    strip = stripes()
    query = cv2.resize(strip, None, fx=.7, fy=.7, interpolation=cv2.INTER_AREA)
    source, rows = setup_case(tmp_path, [strip], [query])
    result = scan_and_match(str(source), rows, str(tmp_path / 'work'))
    assert result['matches'][0]['status'] == 'auto'


def test_repeated_stripe_longer_artboard_is_auto(tmp_path):
    strip = stripes()
    source, rows = setup_case(tmp_path, [np.tile(strip, (1, 2, 1))], [strip])
    result = scan_and_match(str(source), rows, str(tmp_path / 'work'))
    assert result['matches'][0]['status'] == 'auto'


def test_dotted_motif_with_artboard_padding_is_auto(tmp_path):
    motif = dots()
    padded = cv2.copyMakeBorder(motif, 50, 50, 50, 50, cv2.BORDER_CONSTANT, value=(255, 255, 255))
    source, rows = setup_case(tmp_path, [padded], [motif])
    result = scan_and_match(str(source), rows, str(tmp_path / 'work'))
    assert result['matches'][0]['status'] == 'auto'


def test_dotted_motif_crop_is_auto(tmp_path):
    motif = dots()
    source, rows = setup_case(tmp_path, [motif], [motif[60:240, 150:610].copy()])
    result = scan_and_match(str(source), rows, str(tmp_path / 'work'))
    assert result['matches'][0]['status'] == 'auto'


def test_recoloured_repeat_is_not_auto(tmp_path):
    strip = stripes()
    recoloured = strip[:, :, ::-1].copy()
    source, rows = setup_case(tmp_path, [strip], [recoloured])
    result = scan_and_match(str(source), rows, str(tmp_path / 'work'))
    assert result['matches'][0]['status'] != 'auto'
    assert result['matches'][0]['file_id'] is None


def test_altered_repeat_is_not_auto(tmp_path):
    motif = dots()
    altered = motif.copy()
    cv2.rectangle(altered, (300, 120), (420, 190), (30, 30, 200), -1)
    source, rows = setup_case(tmp_path, [motif], [altered])
    result = scan_and_match(str(source), rows, str(tmp_path / 'work'))
    assert result['matches'][0]['status'] != 'auto'


def test_artboard_with_extra_different_motif_needs_review(tmp_path):
    """A locally identical match must not auto-accept unexplained artwork."""
    motif = dots()
    composite = np.concatenate([motif, stripes(400, 300)], axis=1)
    source, rows = setup_case(tmp_path, [composite], [motif])
    result = scan_and_match(str(source), rows, str(tmp_path / 'work'))
    assert result['matches'][0]['status'] != 'auto'


def test_review_reason_names_the_missing_evidence(tmp_path):
    """Reasons must say which evidence is missing, never a generic hint."""
    motif = dots()
    recoloured = motif[:, :, ::-1].copy()
    source, rows = setup_case(tmp_path, [motif], [recoloured])
    result = scan_and_match(str(source), rows, str(tmp_path / 'work'))
    reason = result['matches'][0]['reason']
    assert '缺少足够独特的图像细节' not in reason
    assert '颜色' in reason or '图案' in reason or '差异' in reason


def test_automatic_decision_records_its_evidence(tmp_path):
    strip = stripes()
    source, rows = setup_case(tmp_path, [strip], [strip])
    result = scan_and_match(str(source), rows, str(tmp_path / 'work'))
    match = result['matches'][0]
    assert match['status'] == 'auto'
    assert match['evidence']['method'] in {'features', 'texture'}
    assert match['evidence']['checked']
