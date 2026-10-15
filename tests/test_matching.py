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


def test_texture_scale_search_never_asserts_on_short_tiles():
    """A tile below half the query height used to make cv2.matchTemplate assert.

    The coarse scale pass can nominate its smallest step for near-uniform art, and
    the refinement window then asked for a tile shorter than the 64 px query. That
    raised an OpenCV assertion and aborted the entire batch instead of simply
    reporting no evidence at that scale.
    """
    strip = stripes()
    query = matching._resize_height(strip, 64)
    for height in (2, 18, 30, 31):
        best = {}
        matching._texture_scan(query, strip, height, best)
        assert 'score' not in best


def test_uniform_low_detail_artwork_does_not_break_the_batch(tmp_path):
    """Near-uniform artwork used to abort the whole batch inside the texture pass."""
    flat = cv2.GaussianBlur(np.full((120, 1000, 3), 250, np.uint8), (3, 3), 0)
    source, rows = setup_case(tmp_path, [flat], [flat])
    result = scan_and_match(str(source), rows, str(tmp_path / 'work'))
    match = result['matches'][0]
    assert match['status'] in {'auto', 'review'}, match['reason']
    assert match['candidates'], '低细节图案仍应给出候选供人工查看'


@pytest.mark.parametrize('different_half', ['top', 'bottom'])
def test_matching_horizontal_band_cannot_hide_vertical_extra_art(tmp_path, different_half):
    """Same palette/area and a perfect local match do not prove the original."""
    query = np.full((64, 256, 3), 255, np.uint8)
    query[np.arange(64) % 16 < 8] = 0
    original = np.tile(query[:, :128], (2, 1, 1))
    vertical = np.full((64, 128, 3), 255, np.uint8)
    vertical[:, np.arange(128) % 16 < 8] = 0
    original[:64] = vertical if different_half == 'top' else original[:64]
    original[64:] = vertical if different_half == 'bottom' else original[64:]
    source, rows = setup_case(tmp_path, [original], [query])
    result = scan_and_match(str(source), rows, str(tmp_path / 'work'))
    match = result['matches'][0]
    assert match['status'] != 'auto'
    texture = match['evidence']['channels'].get('texture')
    assert texture and 'candidate_coverage' in texture['failed_checks']
    assert texture['metrics']['source_coverage'] < .95


def test_independently_measured_period_can_explain_nonperiodic_canvas_edge(tmp_path):
    """A canvas ending mid-repeat is not itself a legitimate tiling boundary."""
    original = stripes(width=1147, height=173, period=29)
    query = original[:, 183:847].copy()
    source, rows = setup_case(tmp_path, [original], [query])
    result = scan_and_match(str(source), rows, str(tmp_path / 'work'))
    assert result['matches'][0]['status'] == 'auto'


def test_edge_coverage_requires_independent_pixels_not_only_a_larger_mask():
    from hsd_tool.matching_verification import affine_coverage
    source = np.full((66, 360, 3), 180, np.uint8)
    cv2.circle(source, (170, 32), 12, (80, 40, 120), -1)
    query = source[1:-1].copy()
    transform = np.array([[1., 0., 0.], [0., 1., -1.]], np.float64)
    proven = affine_coverage(query, source, [transform])
    assert proven['candidate_coverage'] > .95
    assert proven['candidate_edge_verified_coverage'] > 0
    assert proven['edge_checks'][0]['candidate']['mae'] < .045
    changed = query.copy()
    changed[-1] = 0
    rejected = affine_coverage(changed, source, [transform])
    assert rejected['candidate_coverage'] < proven['candidate_coverage']
    assert not rejected['edge_checks'][0].get('accepted') or rejected['edge_checks'][0]['candidate']['changed'] > .08


def test_evidence_keeps_independent_channel_and_competition_records(tmp_path):
    image = dots(width=704, height=264, spacing=43, radius=10)
    source, rows = setup_case(tmp_path, [image, stripes(width=704, height=264)])
    result = scan_and_match(str(source), rows, str(tmp_path / 'work'))
    evidence = result['matches'][0]['evidence']
    assert evidence['evidence_version'] == 2
    assert evidence['selected_channel'] == evidence['method']
    selected = evidence['channels'][evidence['selected_channel']]
    assert isinstance(selected['failed_checks'], list)
    assert selected['alignment']['direction'] == 'candidate_to_query'
    assert selected['alignment']['query_size'] == [704, 264]
    competition = evidence['competition']
    assert competition['complete'] is True
    assert set(competition['evaluated_file_ids']) == {'f0001', 'f0002'}
    assert {item['file_id'] for item in competition['scores']} == {'f0001', 'f0002'}
    assert 'source_path' not in str(evidence)


def test_small_foreground_colour_change_is_not_hidden_by_large_background(tmp_path):
    image = np.full((180, 960, 3), 244, np.uint8)
    for x in range(45, 930, 95):
        cv2.putText(image, f'X{x}', (x, 55), cv2.FONT_HERSHEY_SIMPLEX, .45, (30, 30, 30), 1)
        cv2.circle(image, (x + 10, 125), 10, (40, 45, 190), -1)
    changed = image.copy()
    foreground = (image == (40, 45, 190)).all(axis=2)
    changed[foreground] = (40, 120, 190)
    assert foreground.mean() < .03
    source, rows = setup_case(tmp_path, [changed], [image])
    result = scan_and_match(str(source), rows, str(tmp_path / 'work'))
    assert result['matches'][0]['status'] != 'auto'
    channels = result['matches'][0]['evidence']['channels']
    assert any('foreground_colours' in item['failed_checks'] for item in channels.values())


def test_near_white_colour_is_not_trimmed_as_blank_padding():
    image = np.full((100, 150, 3), 255, np.uint8)
    image[10:30, 20:80] = (60, 60, 60)
    image[90:95, 30:100] = (240, 255, 255)
    assert matching._content_bounds(image) == (20, 10, 100, 95)


def test_partial_shared_artwork_does_not_take_ownership_from_complete_match(tmp_path):
    image = artwork(42)
    incomplete = np.concatenate([image, artwork(73)], axis=1)
    source, rows = setup_case(tmp_path, [image], [image, incomplete])
    result = scan_and_match(str(source), rows, str(tmp_path / 'work'))
    assert result['matches'][0]['status'] == 'auto'
    assert result['matches'][0]['file_id'] == 'f0001'
    assert result['matches'][1]['status'] != 'auto'
    assert result['matches'][1]['file_id'] is None
    assert result['matches'][1]['evidence']['claim_strength'] == 'weak'


@pytest.mark.parametrize('contrast', [12, 95])
def test_small_solid_local_replacement_is_not_averaged_away(tmp_path, contrast):
    image = artwork(61)
    # Keep the replacement below one percent of the complete image, in a plain
    # region of the design. A low average error is expected, not sufficient.
    image[230:270, 700:775] = 200
    changed = image.copy()
    changed[240:263, 718:756] = 200 - contrast
    source, rows = setup_case(tmp_path, [changed], [image])
    result = scan_and_match(str(source), rows, str(tmp_path / 'work'))
    assert result['matches'][0]['status'] != 'auto'
    channels = result['matches'][0]['evidence']['channels']
    assert any('coherent_difference' in item['failed_checks'] for item in channels.values())


@pytest.mark.parametrize('period', [31, 43])
def test_resampled_stripe_edges_are_not_fictitious_foreground_colours(tmp_path, period):
    image = np.full((257, 941, 3), 255, np.uint8)
    image[np.arange(257) % period < period // 2] = (79, 26, 16)
    query = cv2.resize(image, (781, 213), interpolation=cv2.INTER_AREA)
    source, rows = setup_case(tmp_path, [image], [query])
    result = scan_and_match(str(source), rows, str(tmp_path / 'work'))
    match = result['matches'][0]
    assert match['status'] == 'auto', match['evidence']
    assert not any('foreground_colours' in item['failed_checks']
                   for item in match['evidence']['channels'].values())


def test_recoloured_fine_lines_are_not_auto_even_without_flat_foreground(tmp_path):
    image = np.full((180, 540, 3), 255, np.uint8)
    image[3::13] = (85, 35, 20)
    changed = image.copy()
    changed[3::13] = (20, 35, 125)
    source, rows = setup_case(tmp_path, [changed], [image])
    result = scan_and_match(str(source), rows, str(tmp_path / 'work'))
    assert result['matches'][0]['status'] != 'auto'


def test_texture_scale_search_never_asserts_on_short_tiles():
    """A tile below half the query height used to make cv2.matchTemplate assert.

    The coarse scale pass can nominate its smallest step for near-uniform art, and
    the refinement window then asked for a tile shorter than the 64 px query. That
    raised an OpenCV assertion and aborted the entire batch instead of simply
    reporting no evidence at that scale.
    """
    strip = stripes()
    query = matching._resize_height(strip, 64)
    for height in (2, 18, 30, 31):
        best = {}
        matching._texture_scan(query, strip, height, best)
        assert 'score' not in best


def test_uniform_low_detail_artwork_does_not_break_the_batch(tmp_path):
    """Near-uniform artwork used to abort the whole batch inside the texture pass."""
    flat = cv2.GaussianBlur(np.full((120, 1000, 3), 250, np.uint8), (3, 3), 0)
    source, rows = setup_case(tmp_path, [flat], [flat])
    result = scan_and_match(str(source), rows, str(tmp_path / 'work'))
    match = result['matches'][0]
    assert match['status'] in {'auto', 'review'}, match['reason']
    assert match['candidates'], '低细节图案仍应给出候选供人工查看'
