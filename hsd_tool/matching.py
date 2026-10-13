"""Local, conservative matching of workbook pictures and PDF-compatible AI files.

File names and workbook row numbers are deliberately never matching evidence.
Scores are appearance similarities, not probabilities. Ambiguous identities are
left for a person; this module never fills a missing assignment by elimination.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import hashlib
import math
import os
from pathlib import Path, PurePosixPath
import stat
import tempfile
import zipfile

import cv2
import numpy as np
from PIL import Image
import pymupdf

MAX_FILES = 500
MAX_ENTRIES = 10000
MAX_FILE_BYTES = 256 * 1024 * 1024
MAX_TOTAL_BYTES = 4 * 1024 * 1024 * 1024
MAX_RATIO = 1000
MAX_IMAGE_PIXELS = 40_000_000
PREVIEW_SIZE = 1400


def _is_link(path: Path) -> bool:
    info = path.lstat()
    return path.is_symlink() or bool(getattr(info, 'st_file_attributes', 0) & 0x400)


def _zip_name(info: zipfile.ZipInfo) -> str:
    name = info.filename
    if not info.flag_bits & 0x800:
        # Common Windows-created archives contain GBK bytes marked as CP437.
        try:
            decoded = name.encode('cp437').decode('gb18030')
            if any('\u3400' <= char <= '\u9fff' for char in decoded):
                name = decoded
        except (UnicodeError, ValueError):
            pass
    return name.replace('\\', '/')


def _safe_zip_name(name: str) -> None:
    parts = name.split('/')
    if (name.startswith('/') or '\x00' in name or ':' in name
            or any(part in ('.', '..') for part in parts)
            or any(part.rstrip(' .') != part for part in parts if part)):
        raise ValueError('压缩包包含不安全路径，已停止读取。请重新打包正常的 AI 文件夹。')


def _file_record(index: int, relative: str, source: Path) -> dict:
    return {'id': f'f{index:04d}', 'name': PurePosixPath(relative).name,
            'relative_path': relative, 'source_path': str(source.resolve()),
            'preview_path': None, 'issue': None}


def _collect(source: Path, directory: Path, warnings: list[str]) -> list[dict]:
    if not source.exists():
        raise ValueError('找不到 AI 文件夹或压缩包，请重新选择。')
    if _is_link(source):
        raise ValueError('请选择真实文件夹或压缩包，不支持符号链接与目录联接。')
    if source.is_dir():
        entries = []
        count, total = 0, 0
        for base, dirs, names in os.walk(source, followlinks=False):
            # Junctions are reparse points on Windows, not necessarily symlinks.
            for name in list(dirs):
                p = Path(base) / name
                if _is_link(p):
                    dirs.remove(name)
                    warnings.append(f'已跳过链接目录：{p.relative_to(source)}')
            for name in names:
                count += 1
                if count > MAX_ENTRIES:
                    raise ValueError('文件夹内文件过多，请把本批次 AI 文件单独放入一个文件夹。')
                p = Path(base) / name
                if p.suffix.lower() != '.ai':
                    continue
                if _is_link(p):
                    warnings.append(f'已跳过链接文件：{p.relative_to(source)}')
                    continue
                size = p.stat().st_size
                total += size
                if size > MAX_FILE_BYTES or total > MAX_TOTAL_BYTES:
                    raise ValueError('AI 文件超过本地处理容量：单文件 256 MB，每批总计 4 GB。')
                entries.append((p.relative_to(source).as_posix(), p))
        if len(entries) > MAX_FILES:
            raise ValueError(f'每批最多支持 {MAX_FILES} 个 AI 文件，请分批处理。')
        entries.sort(key=lambda pair: (pair[0].casefold(), pair[0]))
        return [_file_record(i, name, p) for i, (name, p) in enumerate(entries, 1)]
    if source.suffix.lower() != '.zip':
        raise ValueError('请选择 AI 文件夹或 ZIP 压缩包。')
    try:
        with zipfile.ZipFile(source) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_ENTRIES:
                raise ValueError('压缩包条目过多，请仅打包本批次 AI 文件。')
            entries, total = [], 0
            for info in infos:
                name = _zip_name(info)
                _safe_zip_name(name)
                mode = info.external_attr >> 16
                if stat.S_ISLNK(mode):
                    raise ValueError('压缩包包含符号链接，已停止读取。请重新打包实际文件。')
                if info.is_dir() or not name.lower().endswith('.ai'):
                    continue
                if info.flag_bits & 1:
                    raise ValueError('暂不支持加密 ZIP，请先解压后选择 AI 文件夹。')
                total += info.file_size
                if info.file_size > MAX_FILE_BYTES or total > MAX_TOTAL_BYTES:
                    raise ValueError('AI 文件超过本地处理容量：单文件 256 MB，每批总计 4 GB。')
                if info.file_size > max(1, info.compress_size) * MAX_RATIO:
                    raise ValueError('压缩包展开比例异常，已停止读取。请先在本地解压并检查。')
                entries.append((name, info))
            if len(entries) > MAX_FILES:
                raise ValueError(f'每批最多支持 {MAX_FILES} 个 AI 文件，请分批处理。')
            entries.sort(key=lambda pair: (pair[0].casefold(), pair[0]))
            files = []
            for i, (name, info) in enumerate(entries, 1):
                destination = directory / f'f{i:04d}.ai'
                record = _file_record(i, name, destination)
                digest = hashlib.sha256()
                written = 0
                with archive.open(info) as stream, destination.open('xb') as output:
                    while block := stream.read(1024 * 1024):
                        written += len(block)
                        if written > min(MAX_FILE_BYTES, info.file_size):
                            raise ValueError('压缩包实际展开容量不符，已停止读取。')
                        digest.update(block)
                        output.write(block)
                record['source_sha256'] = digest.hexdigest()
                files.append(record)
            if any('\ufffd' in name for name, _ in entries):
                warnings.append('压缩包中的部分原文件名已包含乱码；图像匹配不依赖原文件名，导出时使用表格编号。')
            return files
    except (zipfile.BadZipFile, EOFError) as exc:
        raise ValueError('ZIP 压缩包损坏或不是有效压缩包，请重新获取文件。') from exc


def _render(record: dict, previews: Path) -> None:
    path = Path(record['source_path'])
    # Render the exact bytes hashed, so export can detect subsequent input edits.
    with path.open('rb') as stream:
        data = stream.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise ValueError('AI 文件超过 256 MB，请单独处理。')
    digest = hashlib.sha256(data).hexdigest()
    if record.get('source_sha256') and record['source_sha256'] != digest:
        raise ValueError('读取过程中源文件发生变化，请重新导入。')
    record['source_sha256'] = digest
    if b'%PDF-' not in data[:1024]:
        raise ValueError('此 AI 未包含 PDF 兼容预览；请在 Illustrator 中启用“创建 PDF 兼容文件”后另存。')
    with pymupdf.open(stream=data, filetype='pdf') as doc:
        if doc.needs_pass:
            raise ValueError('文件预览已加密，无法读取。')
        if not doc.page_count:
            raise ValueError('AI 文件没有可读取的画板。')
        record['page_count'] = doc.page_count
        page = doc[0]
        # Illustrator's media box usually includes printing bleed. Its declared
        # trim box is the actual artwork boundary represented in the workbook.
        # Respect that explicit document metadata; never guess a crop from art.
        trim = page.trimbox
        if not trim.is_empty and not trim.is_infinite and trim != page.cropbox:
            try:
                page.set_cropbox(trim)
                record['uses_trimbox'] = True
            except ValueError:
                record['uses_trimbox'] = False
        rect = page.rect
        if not all(math.isfinite(n) and n > 0 for n in (rect.width, rect.height)):
            raise ValueError('AI 画板尺寸异常，无法生成预览。')
        scale = PREVIEW_SIZE / max(rect.width, rect.height)
        destination = previews / f"{record['id']}.png"
        page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), colorspace=pymupdf.csRGB,
                        alpha=False).save(destination)
        record['preview_path'] = str(destination.resolve())
        if doc.page_count > 1:
            record['issue'] = f'含 {doc.page_count} 个画板，目前仅预览第 1 个，须人工确认整个 AI 文件。'


def _read_image(path: str) -> np.ndarray:
    with Image.open(path) as image:
        if image.width * image.height > MAX_IMAGE_PIXELS:
            raise ValueError('图片像素过大，请缩小表格图片后重试。')
        image = image.convert('RGBA')
        background = Image.new('RGBA', image.size, 'white')
        background.alpha_composite(image)
        array = np.asarray(background.convert('RGB'))[:, :, ::-1].copy()
    if min(array.shape[:2]) < 8:
        raise ValueError('图片尺寸过小，无法可靠匹配。')
    scale = min(1, PREVIEW_SIZE / max(array.shape[:2]))
    if scale < 1:
        array = cv2.resize(array, (max(8, round(array.shape[1] * scale)),
                                   max(8, round(array.shape[0] * scale))),
                           interpolation=cv2.INTER_AREA)
    return array


def _resize_height(array: np.ndarray, height: int) -> np.ndarray:
    width = max(2, round(array.shape[1] * height / array.shape[0]))
    # Extremely thin strips are supported as candidates, but not unbounded arrays.
    return cv2.resize(array, (min(width, 4096), height), interpolation=cv2.INTER_AREA)


@dataclass
class _Appearance:
    image: np.ndarray
    keypoints: list
    descriptors: np.ndarray | None
    histogram: np.ndarray
    digest: str


def _appearance(array: np.ndarray, detector) -> _Appearance:
    gray = cv2.cvtColor(array, cv2.COLOR_BGR2GRAY)
    keypoints, descriptors = detector.detectAndCompute(gray, None)
    lab = cv2.cvtColor(_resize_height(array, 96), cv2.COLOR_BGR2LAB)
    histogram = cv2.calcHist([lab], [0, 1, 2], None, [12, 16, 16], [0, 256] * 3)
    cv2.normalize(histogram, histogram, norm_type=cv2.NORM_L1)
    return _Appearance(array, keypoints, descriptors, histogram,
                       hashlib.sha256(array.tobytes()).hexdigest())


def _features(query: _Appearance, candidate: _Appearance) -> dict:
    result = {'score': 0., 'strong': False, 'method': 'features'}
    if (query.descriptors is None or candidate.descriptors is None
            or min(len(query.descriptors), len(candidate.descriptors)) < 6):
        return result
    pairs = cv2.BFMatcher().knnMatch(query.descriptors, candidate.descriptors, k=2)
    good = [pair[0] for pair in pairs if len(pair) == 2 and pair[0].distance < .75 * pair[1].distance]
    source_coordinates = [candidate.keypoints[m.trainIdx].pt for m in good]
    query_coordinates = [query.keypoints[m.queryIdx].pt for m in good]
    source_wider = (candidate.image.shape[1] / candidate.image.shape[0]
                    > query.image.shape[1] / query.image.shape[0] * 1.05)
    if len(good) < 14 or source_wider:
        # Two identical repeats within the source can make every forward ratio
        # ambiguous. The reverse direction can independently evidence each copy.
        reverse = cv2.BFMatcher().knnMatch(candidate.descriptors, query.descriptors, k=2)
        seen_pairs = set(zip(source_coordinates, query_coordinates))
        for pair in reverse:
            if len(pair) == 2 and pair[0].distance < .75 * pair[1].distance:
                source_point = candidate.keypoints[pair[0].queryIdx].pt
                query_point = query.keypoints[pair[0].trainIdx].pt
                if (source_point, query_point) not in seen_pairs:
                    seen_pairs.add((source_point, query_point))
                    source_coordinates.append(source_point)
                    query_coordinates.append(query_point)
    if len(source_coordinates) < 6:
        return result
    source_points = np.float32(source_coordinates)
    query_points = np.float32(query_coordinates)
    transform, mask = cv2.estimateAffine2D(source_points, query_points, method=cv2.RANSAC,
                                         ransacReprojThreshold=3, maxIters=2000, confidence=.995)
    if transform is None or not np.isfinite(transform).all():
        return result
    determinant = np.linalg.det(transform[:, :2])
    if determinant <= .0001:
        return result
    mask = mask.ravel().astype(bool)
    points = source_points[mask]
    inliers = int(mask.sum())
    ai, qi = candidate.image, query.image
    coverage = float(cv2.contourArea(cv2.convexHull(points)) / (ai.shape[0] * ai.shape[1]))
    if inliers < 6 or coverage < .025:
        return result
    warped = cv2.warpAffine(ai, transform, (qi.shape[1], qi.shape[0]))
    region = cv2.warpAffine(np.ones(ai.shape[:2], np.uint8), transform,
                            (qi.shape[1], qi.shape[0]), flags=cv2.INTER_NEAREST)
    region = cv2.erode(region, np.ones((5, 5), np.uint8)).astype(bool)
    overlap = float(region.mean())
    if region.sum() < 100 or overlap < .06:
        return result
    first = cv2.GaussianBlur(qi, (3, 3), .6)
    second = cv2.GaussianBlur(warped, (3, 3), .6)
    diff = np.abs(first.astype(np.float32) - second.astype(np.float32))[region] / 255
    mae = float(diff.mean())
    changed = float(np.mean(np.max(diff, axis=1) > .2))
    major_changed = float(np.mean(np.max(diff, axis=1) > .45))
    score = max(0, 1 - 2 * mae) * min(1, inliers / 14) * min(1, coverage / .18)
    # The same isolated logo on otherwise different artwork is not sufficient.
    # Find separate geometrically verified copies of the art instead of assuming
    # the PDF artboard edge equals the pattern-repeat boundary. AI artboards can
    # include extra trim, so blindly wrapping their pixels creates false seams.
    global_mae, global_changed = 1., 1.
    verified_coverage = overlap
    source_region = cv2.warpAffine(np.ones(qi.shape[:2], np.uint8),
        cv2.invertAffineTransform(transform), (ai.shape[1], ai.shape[0]), flags=cv2.INTER_NEAREST)
    source_region = cv2.erode(source_region, np.ones((3, 3), np.uint8)).astype(bool)
    source_accepted = source_region.copy()
    if overlap >= .95:
        global_mae, global_changed = mae, changed
    if ((overlap < .95 or source_accepted.mean() < .95) and inliers >= 14
            and mae <= .045 and changed <= .08 and major_changed <= .015):
        full_error = np.full(qi.shape, np.inf, dtype=np.float32)
        full_error[region] = diff
        accepted = region.copy()
        unused = ~mask
        for _ in range(9):
            if unused.sum() < 8:
                break
            other, local_inliers = cv2.estimateAffine2D(source_points[unused], query_points[unused],
                method=cv2.RANSAC, ransacReprojThreshold=3, maxIters=2000, confidence=.995)
            if other is None:
                break
            local_inliers = local_inliers.ravel().astype(bool)
            unused[np.flatnonzero(unused)[local_inliers]] = False
            if local_inliers.sum() < 8:
                break
            # Multiple copies must have the same scale/orientation as the first.
            relative_error = np.linalg.norm(other[:, :2] - transform[:, :2]) / np.linalg.norm(transform[:, :2])
            if relative_error > .04:
                continue
            other_warp = cv2.warpAffine(ai, other, (qi.shape[1], qi.shape[0]))
            other_region = cv2.warpAffine(np.ones(ai.shape[:2], np.uint8), other,
                (qi.shape[1], qi.shape[0]), flags=cv2.INTER_NEAREST)
            other_region = cv2.erode(other_region, np.ones((5, 5), np.uint8)).astype(bool)
            if other_region.sum() < 100:
                continue
            other_diff = np.abs(first.astype(np.float32) - cv2.GaussianBlur(other_warp,
                (3, 3), .6).astype(np.float32)) / 255
            values = other_diff[other_region]
            if (float(values.mean()) > .045 or float(np.mean(np.max(values, axis=1) > .2)) > .08
                    or float(np.mean(np.max(values, axis=1) > .45)) > .015):
                continue
            full_error[other_region] = np.minimum(full_error[other_region], values)
            accepted |= other_region
            other_source = cv2.warpAffine(np.ones(qi.shape[:2], np.uint8),
                cv2.invertAffineTransform(other), (ai.shape[1], ai.shape[0]), flags=cv2.INTER_NEAREST)
            source_accepted |= cv2.erode(other_source, np.ones((3, 3), np.uint8)).astype(bool)
            if accepted.mean() >= .95 and source_accepted.mean() >= .95:
                break
        verified_coverage = float(accepted.mean())
        if verified_coverage >= .95:
            global_mae = float(full_error[accepted].mean())
            global_changed = float(np.mean(np.max(full_error[accepted], axis=1) > .2))
    singular = np.linalg.svd(transform[:, :2], compute_uv=False)
    plausible = singular[0] / max(.0001, singular[1]) < 1.7
    source_coverage = float(source_accepted.mean())
    # White Illustrator margins need not appear in the workbook thumbnail, but
    # actual unobserved art is not proven identical merely because the query is.
    source_ink = np.min(ai, axis=2) < 235
    source_ink_coverage = (float(source_accepted[source_ink].mean())
                           if source_ink.any() else source_coverage)
    strong = (inliers >= 14 and coverage >= .18 and mae <= .045 and changed <= .08 and major_changed <= .015
              and global_mae <= .06 and global_changed <= .12 and plausible
              and (source_coverage >= .95 or source_ink_coverage >= .98))
    result.update(score=score, strong=bool(strong), inliers=inliers, coverage=coverage,
                  mae=mae, changed=changed, major_changed=major_changed, global_mae=global_mae,
                  global_changed=global_changed, overlap=overlap, verified_coverage=verified_coverage,
                  source_coverage=source_coverage, source_ink_coverage=source_ink_coverage)
    return result


def _texture(query: _Appearance, candidate: _Appearance) -> dict:
    """Whole strip comparison, with scale/translation and horizontal repetition.

    Useful for lines/dots which have too few unique keypoints. Its output remains
    review-only: low-detail designs can have indistinguishable preview patterns.
    """
    q = _resize_height(query.image, 64)
    best = {'score': 0., 'strong': False, 'method': 'texture'}
    # Source artboard can include a little extra trim compared with the table.
    for height in range(58, 96, 2):
        tile = _resize_height(candidate.image, height)
        count = max(2, math.ceil(q.shape[1] / tile.shape[1]) + 1)
        big = np.tile(tile, (2, count, 1))
        differences = cv2.matchTemplate(big, q, cv2.TM_SQDIFF)
        _, _, location, _ = cv2.minMaxLoc(differences)
        x, y = location
        diff = np.abs(q.astype(np.float32) - big[y:y + q.shape[0], x:x + q.shape[1]]) / 255
        # RMS penalizes large errors in small but significant colored details.
        score = 1 - float(np.mean(diff ** 2)) ** .5
        if score > best['score']:
            best.update(score=score, changed=float(np.mean(np.max(diff, axis=2) > .2)))
    # Keep textured fallback below a geometrically verified near-exact match.
    best['score'] *= .94
    return best


def _match_appearances(rows: list[dict], files: list[dict], row_images: dict,
                       file_images: dict, progress=None) -> list[dict]:
    results = []
    readable = [f for f in files if f['id'] in file_images]
    duplicate_previews = Counter(a.digest for a in file_images.values())
    for i, row in enumerate(rows, 1):
        if progress:
            progress(f'正在比对第 {i} / {len(rows)} 张表格图片', i, len(rows))
        base = {'row_id': row['id'], 'status': 'unmatched', 'file_id': None,
                'candidates': [], 'reason': '未找到足够相似的 AI 文件，可人工选择或跳过。'}
        if row.get('issue') or row['id'] not in row_images:
            base['reason'] = row.get('issue') or '表格图片无法读取，请检查原表。'
            results.append(base)
            continue
        if not readable:
            base['reason'] = '没有可读取预览的 AI 文件，请检查文件格式。'
            results.append(base)
            continue
        query = row_images[row['id']]
        scores, histograms = {}, {}
        for file in readable:
            identity = file['id']
            candidate = file_images[identity]
            histograms[identity] = float(cv2.compareHist(query.histogram, candidate.histogram,
                                                        cv2.HISTCMP_BHATTACHARYYA))
            scores[identity] = _features(query, candidate)
            scores[identity]['score'] = max(scores[identity]['score'],
                                             .4 * (1 - histograms[identity]))
        best_feature = max(scores, key=lambda identity: scores[identity]['score'])
        if not scores[best_feature]['strong']:
            shortlist = sorted(histograms, key=histograms.get)[:6]
            shortlist += sorted(scores, key=lambda identity: scores[identity]['score'], reverse=True)[:2]
            for identity in dict.fromkeys(shortlist):
                texture = _texture(query, file_images[identity])
                if texture['score'] > scores[identity]['score']:
                    scores[identity] = texture
        ranking = sorted(scores, key=lambda identity: (-scores[identity]['score'], identity))
        base['candidates'] = [{'file_id': identity, 'score': round(scores[identity]['score'], 4)}
                              for identity in ranking[:5]]
        top = ranking[0]
        top_score = scores[top]['score']
        runner_up = scores[ranking[1]]['score'] if len(ranking) > 1 else 0
        top_file = next(file for file in readable if file['id'] == top)
        if top_score < .55:
            base['reason'] = '相似度不足，未自动选择文件；候选仅供人工查看。'
        else:
            base['status'] = 'review'
            base['reason'] = '纹样相似，但缺少足够独特的图像细节，请并排确认。'
            if top_file.get('issue'):
                base['reason'] = top_file['issue']
            elif duplicate_previews[file_images[top].digest] > 1:
                base['reason'] = '多个 AI 文件有相同预览，无法自动确定唯一原文件。'
            elif top_score - runner_up < .045:
                base['reason'] = '存在十分接近的候选，请确认具体颜色、图案及文件。'
            elif scores[top]['strong'] and top_score >= .91:
                base.update(status='auto', file_id=top,
                            reason='图像细节、排列和颜色一致，且本批次没有接近的其他候选。')
        results.append(base)
    # A weak competing row is still evidence of conflicting ownership; never
    # silently allocate a shared best file to whichever row happened to run first.
    contenders = defaultdict(list)
    for result in results:
        if result['candidates'] and result['candidates'][0]['score'] >= .55:
            contenders[result['candidates'][0]['file_id']].append(result)
    for group in contenders.values():
        if len(group) > 1:
            for result in group:
                result.update(status='review', file_id=None,
                              reason='多行图片指向同一个 AI 文件，请人工确认一一对应关系。')
    return results


def scan_and_match(source_path: str, rows: list[dict], work_dir: str, progress=None) -> dict:
    """Inspect originals read-only and return conservative per-row candidates."""
    work = Path(work_dir).resolve()
    work.mkdir(parents=True, exist_ok=True)
    session = Path(tempfile.mkdtemp(prefix='matching_', dir=work))
    originals = session / 'source_files'
    previews = session / 'previews'
    originals.mkdir()
    previews.mkdir()
    warnings = []
    if progress:
        progress('正在读取 AI 文件并检查压缩包', 0, 1)
    files = _collect(Path(source_path).absolute(), originals, warnings)
    if not files:
        warnings.append('所选位置没有 .ai 文件，请确认文件夹或压缩包内容。')
    detector = cv2.SIFT_create(nfeatures=1600, contrastThreshold=.025)
    file_images, row_images = {}, {}
    for i, record in enumerate(files, 1):
        if progress:
            progress(f'正在生成 AI 预览 {i} / {len(files)}', i, len(files))
        try:
            _render(record, previews)
            file_images[record['id']] = _appearance(_read_image(record['preview_path']), detector)
        except Exception as exc:
            record['issue'] = str(exc) if isinstance(exc, ValueError) else 'AI 文件损坏或预览无法读取，请单独检查。'
    for row in rows:
        if not row.get('image_path') or row.get('issue'):
            continue
        try:
            row_images[row['id']] = _appearance(_read_image(row['image_path']), detector)
        except (OSError, ValueError, cv2.error):
            warnings.append(f"第 {row.get('row_number', row['id'])} 行图片无法读取，已留待处理。")
    cv2.setRNGSeed(42)
    matches = _match_appearances(rows, files, row_images, file_images, progress)
    bad_count = sum(bool(file['issue']) for file in files)
    if bad_count:
        warnings.append(f'{bad_count} 个 AI 文件预览有问题或含多个画板，请查看原文件列表。')
    return {'files': files, 'matches': matches, 'warnings': warnings}
