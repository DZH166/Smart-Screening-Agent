"""Local, conservative matching of workbook pictures and PDF-compatible AI files.

File names and workbook row numbers are deliberately never matching evidence.
Scores are appearance similarities, not probabilities. Ambiguous identities are
left for a person; this module never fills a missing assignment by elimination.
"""
from __future__ import annotations

from collections import Counter, OrderedDict, defaultdict
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass
import errno
import hashlib
import copy
import math
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import tempfile
import threading
import zipfile

import cv2
import numpy as np
from PIL import Image
import pymupdf

from .matching_verification import (affine_coverage, phase_coverage, periodic_extension,
                                    pixel_metrics, pixel_rms, coherent_difference,
                                    _pixel_error, _channel_max)
from .archive_io import member_blocks
from .cancellation import (check as cancellation_check, TaskCancelled,
                           current_check, scope as cancellation_scope)

MAX_FILES = 500
MAX_ENTRIES = 10000
# Kept for import compatibility; file bytes and compression ratios are not
# product limits. Real storage availability, structure and decoded pixels are.
MAX_FILE_BYTES = None
MAX_TOTAL_BYTES = None
MAX_RATIO = None
MAX_IMAGE_PIXELS = 40_000_000
PREVIEW_SIZE = 1400
IO_CHUNK_BYTES = 1024 * 1024


def _require_space(directory: Path, needed: int) -> None:
    if needed > shutil.disk_usage(directory).free:
        raise ValueError('磁盘空间不足，请清理主机磁盘空间后重新处理。')


def _file_signature(info) -> tuple:
    # Python 3.12 Windows stat/fstat differ in the legacy ctime field; the
    # explicit birth time is consistent, while full hashes detect byte edits.
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns,
            getattr(info, 'st_birthtime_ns', info.st_ctime_ns))


@contextmanager
def _source_reader(path: Path):
    if os.name != 'nt':
        with path.open('rb') as stream:
            yield stream, False
        return
    # Prevent concurrent Windows writers/replacements while MuPDF separately
    # opens the same path. No file bytes, credentials or process state is copied.
    import ctypes
    from ctypes import wintypes
    import msvcrt
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    create = kernel.CreateFileW
    create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                       ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    create.restype = wintypes.HANDLE
    handle = create(str(path), 0x80000000, 0x1, None, 3, 0x08000000, None)
    if handle == wintypes.HANDLE(-1).value:
        raise OSError(ctypes.get_last_error(), '原稿正在被占用或无法读取，请关闭编辑后重新导入。')
    try:
        descriptor = msvcrt.open_osfhandle(int(handle), os.O_RDONLY | os.O_BINARY)
    except BaseException:
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle(handle)
        raise
    with os.fdopen(descriptor, 'rb') as stream:
        yield stream, True


def _source_digest(stream) -> tuple[str, bytes]:
    stream.seek(0)
    prefix = stream.read(1024)
    digest = hashlib.sha256(prefix)
    while block := stream.read(IO_CHUNK_BYTES):
        cancellation_check()
        digest.update(block)
    return digest.hexdigest(), prefix


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
        count = 0
        for base, dirs, names in os.walk(source, followlinks=False):
            # Junctions are reparse points on Windows, not necessarily symlinks.
            for name in list(dirs):
                p = Path(base) / name
                if _is_link(p):
                    dirs.remove(name)
                    warnings.append(f'已跳过链接目录：{p.relative_to(source)}')
            for name in names:
                cancellation_check()
                count += 1
                if count > MAX_ENTRIES:
                    raise ValueError('文件夹内文件过多，请把本批次 AI 文件单独放入一个文件夹。')
                p = Path(base) / name
                if p.suffix.lower() != '.ai':
                    continue
                if _is_link(p):
                    warnings.append(f'已跳过链接文件：{p.relative_to(source)}')
                    continue
                entries.append((p.relative_to(source).as_posix(), p))
        if len(entries) > MAX_FILES:
            raise ValueError(f'每批最多支持 {MAX_FILES} 个 AI 文件，请分批处理。')
        entries.sort(key=lambda pair: (pair[0].casefold(), pair[0]))
        return [_file_record(i, name, p) for i, (name, p) in enumerate(entries, 1)]
    if source.suffix.lower() != '.zip':
        raise ValueError('请选择 AI 文件夹或 ZIP 压缩包。')
    try:
        from .archive_io import check_directory_size
        check_directory_size(source, max_entries=MAX_ENTRIES,
                             too_many='压缩包条目过多，请仅打包本批次 AI 文件。')
        with zipfile.ZipFile(source) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_ENTRIES:
                raise ValueError('压缩包条目过多，请仅打包本批次 AI 文件。')
            entries, total = [], 0
            for info in infos:
                cancellation_check()
                name = _zip_name(info)
                _safe_zip_name(name)
                mode = info.external_attr >> 16
                if stat.S_ISLNK(mode):
                    raise ValueError('压缩包包含符号链接，已停止读取。请重新打包实际文件。')
                if info.is_dir() or not name.lower().endswith('.ai'):
                    continue
                if info.flag_bits & 1:
                    raise ValueError('暂不支持加密 ZIP，请先解压后选择 AI 文件夹。')
                if info.file_size < 0 or info.compress_size < 0:
                    raise ValueError('压缩包文件长度无效，请重新打包。')
                total += info.file_size
                entries.append((name, info))
            if len(entries) > MAX_FILES:
                raise ValueError(f'每批最多支持 {MAX_FILES} 个 AI 文件，请分批处理。')
            entries.sort(key=lambda pair: (pair[0].casefold(), pair[0]))
            _require_space(directory, total)
            files = []
            space_check = 0
            for i, (name, info) in enumerate(entries, 1):
                destination = directory / f'f{i:04d}.ai'
                record = _file_record(i, name, destination)
                digest = hashlib.sha256()
                written = 0
                try:
                    with destination.open('xb') as output:
                        for block in member_blocks(archive, info):
                            written += len(block)
                            if written > info.file_size:
                                raise ValueError('压缩包实际展开长度不符，已停止读取。')
                            if space_check <= 0:
                                _require_space(directory, min(64 * IO_CHUNK_BYTES, total))
                                space_check = 64 * IO_CHUNK_BYTES
                            digest.update(block)
                            output.write(block)
                            space_check -= len(block)
                            total -= len(block)
                        if written != info.file_size:
                            raise ValueError('压缩包实际展开长度不符，文件未完整读取。')
                except BaseException as exc:
                    destination.unlink(missing_ok=True)
                    if isinstance(exc, OSError) and exc.errno in {errno.ENOSPC, getattr(errno, 'EDQUOT', errno.ENOSPC)}:
                        raise ValueError('磁盘空间不足，请清理主机磁盘空间后重新处理。') from exc
                    raise
                record['source_sha256'] = digest.hexdigest()
                files.append(record)
            if any('\ufffd' in name for name, _ in entries):
                warnings.append('压缩包中的部分原文件名已包含乱码；图像匹配不依赖原文件名，导出时使用表格编号。')
            return files
    except (zipfile.BadZipFile, EOFError) as exc:
        raise ValueError('ZIP 压缩包损坏或不是有效压缩包，请重新获取文件。') from exc


def _render(record: dict, previews: Path) -> None:
    path = Path(record['source_path'])
    destination = previews / f"{record['id']}.png"
    try:
        # MuPDF reads a path on demand; hashing uses fixed-size buffers. Hold a
        # read-only Windows lease and check both identity and all bytes again
        # before publishing the preview, retaining source-change protection.
        with _source_reader(path) as (stream, write_locked):
            signature = _file_signature(os.fstat(stream.fileno()))
            digest, prefix = _source_digest(stream)
            if (_file_signature(os.fstat(stream.fileno())) != signature
                    or _file_signature(path.stat()) != signature
                    or record.get('source_sha256') not in {None, digest}):
                raise ValueError('读取过程中源文件发生变化，请重新导入。')
            record['source_sha256'] = digest
            if b'%PDF-' not in prefix:
                raise ValueError('此 AI 未包含 PDF 兼容预览；请在 Illustrator 中启用“创建 PDF 兼容文件”后另存。')
            with pymupdf.open(filename=str(path), filetype='pdf') as doc:
                if doc.needs_pass:
                    raise ValueError('文件预览已加密，无法读取。')
                if not doc.page_count:
                    raise ValueError('AI 文件没有可读取的画板。')
                record['page_count'] = doc.page_count
                page = doc[0]
                # Keep the same explicit trimbox and rendering parameters.
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
                page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), colorspace=pymupdf.csRGB,
                                alpha=False).save(destination)
                if doc.page_count > 1:
                    record['issue'] = f'含 {doc.page_count} 个画板，目前仅预览第 1 个，须人工确认整个 AI 文件。'
            # Windows denies existing/new writers and replacements throughout
            # the lease, so a second full read adds no protection. Other OSes
            # rehash after rendering because their ordinary read is not a lease.
            checked = digest if write_locked else _source_digest(stream)[0]
            if (checked != digest or _file_signature(os.fstat(stream.fileno())) != signature
                    or _file_signature(path.stat()) != signature):
                raise ValueError('生成预览期间源文件发生变化，请重新导入。')
        record['preview_path'] = str(destination.resolve())
    except BaseException:
        destination.unlink(missing_ok=True)
        record['preview_path'] = None
        raise


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


def _resized_width(array: np.ndarray, height: int) -> int:
    return min(max(2, round(array.shape[1] * height / array.shape[0])), 4096)


def _resize_height(array: np.ndarray, height: int) -> np.ndarray:
    width = _resized_width(array, height)
    # Extremely thin strips are supported as candidates, but not unbounded arrays.
    return cv2.resize(array, (width, height), interpolation=cv2.INTER_AREA)


class _TextureCache:
    """Bounded scratch data owned by one matching call, never a disk cache.

    Tokens contain prepared pixel SHA256, dimensions and transformation
    parameters. They never use paths, filenames, mtimes or a prior case answer.
    This cache dies before scan_and_match returns and cannot reuse old AI advice
    or replace any later source-integrity check.
    """
    VERSION = 'texture-scratch-1'

    def __init__(self, max_bytes=64 * 1024 * 1024, max_entries=512):
        self.max_bytes, self.max_entries = max_bytes, max_entries
        self.bytes = 0
        self._items = OrderedDict()
        self._lock = threading.RLock()

    @staticmethod
    def _is_coarse(key):
        return key[1][0] == 'coarse'

    def _remove(self, key):
        _, size = self._items.pop(key)
        self.bytes -= size

    def get(self, token, factory):
        key = (self.VERSION, token)
        with self._lock:
            if key in self._items:
                value, size = self._items.pop(key)
                self._items[key] = value, size
                return value
        # Independent candidates can prepare scales concurrently. A duplicate
        # miss may compute twice, but expensive CV work never holds the LRU lock.
        value = factory()
        size = value.nbytes if isinstance(value, np.ndarray) else 512
        with self._lock:
            if key in self._items:
                existing, existing_size = self._items.pop(key)
                self._items[key] = existing, existing_size
                return existing
            if size > self.max_bytes:
                return value
            if self._is_coarse(key):
                coarse_keys = [item for item in self._items if self._is_coarse(item)]
                if len(coarse_keys) >= min(16, self.max_entries):
                    self._remove(coarse_keys[0])
            while self._items and (len(self._items) >= self.max_entries
                                   or self.bytes + size > self.max_bytes):
                # A raw coarse result is tiny and needed again for precision in
                # the current row. Do not evict it merely to retain old scales.
                victim = next((item for item in self._items if not self._is_coarse(item)),
                              next(iter(self._items)))
                self._remove(victim)
            self._items[key] = value, size
            self.bytes += size
        return value

    def resized(self, image, token, height):
        return self.get(('resize', token, image.shape, height, cv2.INTER_AREA),
                        lambda: _resize_height(image, height))


@dataclass(frozen=True)
class _Appearance:
    image: np.ndarray
    keypoints: list
    descriptors: np.ndarray | None
    histogram: np.ndarray
    digest: str
    palette: dict


def _appearance(array: np.ndarray, detector) -> _Appearance:
    gray = cv2.cvtColor(array, cv2.COLOR_BGR2GRAY)
    keypoints, descriptors = detector.detectAndCompute(gray, None)
    lab = cv2.cvtColor(_resize_height(array, 96), cv2.COLOR_BGR2LAB)
    histogram = cv2.calcHist([lab], [0, 1, 2], None, [12, 16, 16], [0, 256] * 3)
    cv2.normalize(histogram, histogram, norm_type=cv2.NORM_L1)
    bounds = _content_bounds(array)
    body = array[bounds[1]:bounds[3], bounds[0]:bounds[2]] if bounds else array
    kernel = np.ones((3, 3), np.uint8)
    local_range = (cv2.dilate(body, kernel).astype(np.int16)
                   - cv2.erode(body, kernel).astype(np.int16)).max(axis=2)
    flat = cv2.erode((local_range <= 2).astype(np.uint8), kernel,
                     borderType=cv2.BORDER_CONSTANT, borderValue=0).astype(bool)
    flat_pixels = body[flat]
    # Stable real interiors, not resampled anti-alias mixtures. Sampling limits
    # work only after flat-region selection, so a one-row mixed stripe edge
    # cannot become a fictitious one-percent foreground colour.
    if len(flat_pixels) > 65536:
        flat_pixels = flat_pixels[::math.ceil(len(flat_pixels) / 65536)]
    colours, counts = np.unique(flat_pixels, axis=0, return_counts=True)
    order = np.argsort(counts)[::-1]
    weights = counts[order] / counts.sum() if counts.size else np.zeros(0)
    dominant = weights >= .005
    encoded = ((body[:, :, 0].astype(np.uint32) << 16)
               | (body[:, :, 1].astype(np.uint32) << 8) | body[:, :, 2])
    observed, observed_counts = np.unique(encoded, return_counts=True)
    observed = observed[np.argsort(observed_counts)[-256:]]
    observed_colours = np.column_stack(((observed >> 16) & 255,
                                       (observed >> 8) & 255, observed & 255)).astype(np.float32)
    palette = {'colours': colours[order][dominant].astype(np.float32),
               'weights': weights[dominant], 'concentration': float(weights[dominant].sum()),
               'flat_coverage': float(flat.mean()), 'observed_colours': observed_colours}
    digest = hashlib.sha256(array.tobytes()).hexdigest()
    # Production inputs come from _read_image's own decoded arrays and stay
    # private to this call. Guard accidental in-place edits after binding the
    # pixel digest; CV receives these arrays only as read-only source images.
    array.setflags(write=False)
    return _Appearance(array, keypoints, descriptors, histogram, digest, palette)


def _palette_difference(query: _Appearance, candidate: _Appearance) -> dict:
    first, second = query.palette, candidate.palette
    applicable = bool(first['flat_coverage'] >= .6 and second['flat_coverage'] >= .6
                      and first['concentration'] >= .9 and second['concentration'] >= .9
                      and 0 < len(first['colours']) <= 16 and 0 < len(second['colours']) <= 16)
    mismatch = 0.
    if applicable:
        # The same real colour can occupy a thin line on one side and a wider
        # rendered line on the other. It need not itself have a 3x3 interior on
        # both sides, but must be an actual observed colour, not an inferred mix.
        forward = np.max(np.abs(first['colours'][:, None] - second['observed_colours'][None]), axis=2)
        reverse = np.max(np.abs(second['colours'][:, None] - first['observed_colours'][None]), axis=2)
        mismatch = max(float(first['weights'][np.min(forward, axis=1) > 8].sum()),
                       float(second['weights'][np.min(reverse, axis=1) > 8].sum()))
    return {'palette_applicable': applicable, 'palette_mismatch': mismatch,
            'palette_query_flat_coverage': first['flat_coverage'],
            'palette_candidate_flat_coverage': second['flat_coverage']}


def _feature_correspondences(query: _Appearance, candidate: _Appearance):
    """The original bidirectional ratio test, without geometric/pixel work."""
    if (query.descriptors is None or candidate.descriptors is None
            or min(len(query.descriptors), len(candidate.descriptors)) < 6):
        return [], []
    pairs = cv2.BFMatcher().knnMatch(query.descriptors, candidate.descriptors, k=2)
    good = [pair[0] for pair in pairs if len(pair) == 2 and pair[0].distance < .75 * pair[1].distance]
    source_coordinates = [candidate.keypoints[m.trainIdx].pt for m in good]
    query_coordinates = [query.keypoints[m.queryIdx].pt for m in good]
    source_wider = (candidate.image.shape[1] / candidate.image.shape[0]
                    > query.image.shape[1] / query.image.shape[0] * 1.05)
    if len(good) < 14 or source_wider:
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
    return source_coordinates, query_coordinates


def _geometric_score_upper_bound(source_coordinates, candidate: _Appearance) -> float:
    """Bound the existing feature score using *all* possible inlier points.

    RANSAC can only select a subset of these points. Its inlier count and convex
    hull coverage cannot exceed the complete set, and its pixel factor is at
    most one. This is an exclusion bound, never positive matching evidence.
    """
    if len(source_coordinates) < 6:
        return 0.
    area = cv2.contourArea(cv2.convexHull(np.float32(source_coordinates)))
    coverage = area / (candidate.image.shape[0] * candidate.image.shape[1])
    # Round conservatively away from exclusion at floating-point boundaries.
    return min(1., min(1., len(source_coordinates) / 14) * min(1., coverage / .18) + 1e-6)


def _features(query: _Appearance, candidate: _Appearance, *, score_cutoff=None) -> dict:
    result = {'score': 0., 'strong': False, 'method': 'features',
              'failed_checks': ['insufficient_geometric_support']}
    source_coordinates, query_coordinates = _feature_correspondences(query, candidate)
    if len(source_coordinates) < 6:
        return result
    if score_cutoff is not None:
        bound = _geometric_score_upper_bound(source_coordinates, candidate)
        if bound < score_cutoff:
            result.update(score=bound, score_upper_bound=bound,
                          evaluated_by='geometric_score_upper_bound')
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
    coherent = coherent_difference(first, second, region)
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
    transforms = [transform]
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
            if coherent_difference(first, cv2.GaussianBlur(other_warp, (3, 3), .6), other_region) > 0:
                continue
            full_error[other_region] = np.minimum(full_error[other_region], values)
            accepted |= other_region
            transforms.append(other)
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
    source_ink = np.min(ai, axis=2) < 250
    source_ink_coverage = (float(source_accepted[source_ink].mean())
                           if source_ink.any() else source_coverage)
    edge_proof = None
    # Erosion is an interpolation guard, not evidence of missing artwork. Check
    # those excluded pixels independently in both coordinate planes before they
    # may contribute to coverage; keep the original interior tests unchanged.
    geometry_verified = (inliers >= 14 and coverage >= .18 and plausible
                         and mae <= .045 and changed <= .08 and major_changed <= .015)
    if geometry_verified:
        edge_proof = affine_coverage(qi, ai, transforms)
        verified_coverage = max(verified_coverage, edge_proof['query_coverage'])
        source_coverage = max(source_coverage, edge_proof['candidate_coverage'])
        source_ink_coverage = max(source_ink_coverage, edge_proof['candidate_ink_coverage'])
        if edge_proof['query_coverage'] >= .95:
            global_mae, global_changed = edge_proof['global_mae'], edge_proof['global_changed']
        coherent = max(coherent, edge_proof.get('unverified_query_coherent', 0.),
                       edge_proof.get('unverified_candidate_coherent', 0.))
    palette = _palette_difference(query, candidate)
    strong = (inliers >= 14 and coverage >= .18 and mae <= .045 and changed <= .08 and major_changed <= .015
              and global_mae <= .06 and global_changed <= .12 and plausible
              and (source_coverage >= .95 or source_ink_coverage >= .98)
              and palette['palette_mismatch'] <= .005 and coherent == 0)
    result.update(score=score, strong=bool(strong), inliers=inliers, coverage=coverage,
                  mae=mae, changed=changed, major_changed=major_changed, global_mae=global_mae,
                  global_changed=global_changed, overlap=overlap, verified_coverage=verified_coverage,
                  source_coverage=source_coverage, source_ink_coverage=source_ink_coverage,
                  plausible=bool(plausible), edge_proof=edge_proof,
                  coherent_difference=coherent)
    result.update(palette)
    limits = {'inliers': inliers >= 14, 'feature_coverage': coverage >= .18,
              'pixel_mae': mae <= .045, 'changed_area': changed <= .08,
              'major_change': major_changed <= .015, 'query_coverage': verified_coverage >= .95,
              'global_mae': global_mae <= .06, 'global_changed': global_changed <= .12,
              'plausible_geometry': bool(plausible),
              'candidate_coverage': source_coverage >= .95 or source_ink_coverage >= .98,
              'feature_score': score >= .91, 'foreground_colours': palette['palette_mismatch'] <= .005,
              'coherent_difference': coherent == 0}
    result['failed_checks'] = [key for key, okay in limits.items() if not okay]
    result['alignment'] = {
        'kind': 'affine', 'direction': 'candidate_to_query',
        'matrix': transforms[0].tolist(), 'matrices': [t.tolist() for t in transforms],
        'query_size': [qi.shape[1], qi.shape[0]], 'candidate_size': [ai.shape[1], ai.shape[0]],
        'query_coverage': verified_coverage, 'candidate_coverage': source_coverage,
        'candidate_ink_coverage': source_ink_coverage,
        'unverified_query': 1 - verified_coverage, 'unverified_candidate': 1 - source_coverage,
        'edge_verified_coverage': edge_proof['edge_verified_coverage'] if edge_proof else 0.,
        'geometry_verified': bool(geometry_verified), 'verified': bool(strong and score >= .91)}
    return result


def _content_bounds(image: np.ndarray) -> tuple[int, int, int, int] | None:
    """Bounding box of inked pixels, or None when no outer margin can be trimmed.

    Illustrator artboards may carry uniform padding that the workbook thumbnail
    does not show. Only the outer uniform border is trimmed, so every inked
    pixel - including real extra artwork - stays inside the comparison.
    """
    # A bright coloured mark is still artwork. Luminance alone would classify a
    # pale yellow addition as blank, so only near-white pixels form the border.
    ink = image.min(axis=2) < 250
    if not ink.any():
        return None
    rows = np.flatnonzero(ink.any(axis=1))
    columns = np.flatnonzero(ink.any(axis=0))
    top, bottom = int(rows[0]), int(rows[-1]) + 1
    left, right = int(columns[0]), int(columns[-1]) + 1
    if bottom - top < 8 or right - left < 8:
        return None
    if (top, left, bottom, right) == (0, 0, image.shape[0], image.shape[1]):
        return None
    return left, top, right, bottom


def _unexplained_content(tiled: np.ndarray, query: np.ndarray, y: int) -> float:
    """Share of inked pixels the matched picture cannot account for.

    The band the match landed on is scanned again for every phase at which the
    matched picture reproduces it - a repeated motif legitimately appears at
    several phases, and a workbook thumbnail is often a crop of the artboard.
    Inked pixels that no accepted phase covers are content the match cannot
    explain: extra artwork, a second design, or a genuinely different motif.
    Blank areas count as explained, because a declared artboard padding is a
    legitimate difference the workbook thumbnail never shows.
    """
    height, width = tiled.shape[:2]
    if query.shape[0] != min(height, query.shape[0]) or query.shape[1] > width:
        return 1.
    rows = np.arange(y, y + query.shape[0]) % height
    band = tiled[rows]
    ink = band.min(axis=2) < 235
    if ink.sum() < 50:
        return 0.
    result = cv2.matchTemplate(band, query, cv2.TM_SQDIFF)
    area = float(query.shape[0] * query.shape[1] * 3)
    limit = (.20 * 255) ** 2 * area
    covered = np.zeros(band.shape[1], bool)
    for offset in np.flatnonzero(result[0] <= limit):
        covered[offset:offset + query.shape[1]] = True
    return float((ink & ~covered[None, :]).sum() / ink.sum())


def _texture_scan(query: np.ndarray, body: np.ndarray, height: int, best: dict,
                  width_scale: float = 1., subpixel: bool = False, *, resize=None) -> None:
    """One scale of the tiled strip search; keeps the strongest pixel evidence."""
    # Two vertical repeats must fully contain the query. A shorter tile would make
    # cv2.matchTemplate assert instead of degrading to "no evidence at this scale",
    # and the coarse pass can legitimately nominate such a height for very flat art.
    if height * 2 < query.shape[0]:
        return
    tile = resize(body, height) if resize is not None else _resize_height(body, height)
    if width_scale != 1.:
        width = max(6, int(round(tile.shape[1] * width_scale)))
        tile = cv2.resize(tile, (width, tile.shape[0]), interpolation=cv2.INTER_AREA)
    if tile.shape[1] < 6:
        return
    count = max(2, math.ceil(query.shape[1] / tile.shape[1]) + 1)
    tiled = np.tile(tile, (2, count, 1))
    differences = cv2.matchTemplate(tiled, query, cv2.TM_SQDIFF)
    _, _, location, _ = cv2.minMaxLoc(differences)
    x, y = location
    patch = tiled[y:y + query.shape[0], x:x + query.shape[1]]
    if patch.shape != query.shape:
        return
    location = [float(x), float(y)]
    if subpixel:
        best_rms = pixel_rms(query, patch)
        for dy in (0., -.5, -.25, .25, .5):
            for dx in (0., -.5, -.25, .25, .5):
                if not (0 <= x + dx <= tiled.shape[1] - query.shape[1]
                        and 0 <= y + dy <= tiled.shape[0] - query.shape[0]):
                    continue
                candidate_patch = cv2.getRectSubPix(tiled, (query.shape[1], query.shape[0]),
                    (x + dx + (query.shape[1] - 1) / 2, y + dy + (query.shape[0] - 1) / 2))
                measured_rms = pixel_rms(query, candidate_patch)
                if measured_rms < best_rms:
                    best_rms = measured_rms
                    patch = candidate_patch
                    location = [x + dx, y + dy]
    error = _pixel_error(query, patch)
    rms = float(np.sqrt(np.mean(error ** 2)))
    score = 1 - rms
    if score <= best.get('score', 0.):
        return
    pixel = _channel_max(error)
    coherent = coherent_difference(query, patch)
    proof = phase_coverage(tiled, query, differences, tile.shape[:2])
    changed = float((pixel > .2).mean())
    major_changed = float((pixel > .45).mean())
    worst = float(np.percentile(pixel, 99.5))
    # The subpixel placement is a measured comparison too. Its full query window
    # covers the complete source only when it spans both source dimensions.
    if (subpixel and rms <= .045 and changed <= .015
            and major_changed <= .003 and worst <= .55
            and coherent == 0
            and query.shape[0] >= tile.shape[0] and query.shape[1] >= tile.shape[1]):
        proof = dict(proof, source_coverage=1., source_ink_coverage=1., residual=0., phases=[location])
    periodic = None
    if proof['source_coverage'] < .95 and proof['source_ink_coverage'] < .98 and rms <= .065:
        periodic = periodic_extension(query, tile, tuple(location))
        if periodic and periodic['source_coverage'] >= .95:
            proof = dict(proof, source_coverage=periodic['source_coverage'],
                         source_ink_coverage=periodic['source_ink_coverage'], residual=periodic['residual'])
    best.update(score=score, height=height, rms=rms, width_scale=width_scale,
                changed=changed, major_changed=major_changed, worst=worst,
                residual=proof['residual'], source_coverage=proof['source_coverage'],
                source_ink_coverage=proof['source_ink_coverage'], phases=proof['phases'],
                location=location, tile_shape=list(tile.shape[:2]), coherent_difference=coherent)
    if periodic:
        best['periodic_proof'] = periodic


def _texture_search(query: np.ndarray, body: np.ndarray, trimmed: bool, *,
                    resize=None, probe=None) -> dict:
    """Locate the best scale for one candidate body, then refine it."""
    outcome = {'score': 0., 'strong': False, 'method': 'texture', 'trimmed': trimmed}
    if probe is None:
        probe = _resize_height(query, 32)
    coarse = {'score': 0.}
    for height in range(18, 92, 4):
        _texture_scan(probe, body, height, coarse, resize=resize)
    # The coarse pass only locates the neighbourhood; its own score is not reused
    # because low-detail motifs are unreliable at that resolution.
    if 'height' in coarse:
        centre = coarse['height'] * 2
        # Refinement works on the 64 px query copy, so a tile below 32 px cannot
        # contain it even with the two-row repeat: start the window there.
        span = range(max(32, centre - 5), min(184, centre + 6))
    else:
        span = range(44, 124, 4)
    for height in span:
        _texture_scan(query, body, height, outcome, resize=resize)
    if 'height' in outcome:
        # Whole-pixel heights leave a residual aspect error that shifts the motif
        # by about a pixel. A short sub-percent width sweep removes it without
        # masking real content differences.
        for scale in (.991, .994, .997, 1.003, 1.006, 1.009):
            _texture_scan(query, body, outcome['height'], outcome, scale, resize=resize)
    return outcome


def _texture(query: _Appearance, candidate: _Appearance, *, precision: bool = False,
             cache: _TextureCache | None = None) -> dict:
    """Whole-strip comparison, with scale/translation and horizontal repetition.

    Useful for lines, dots and repeated motifs that have too few unique
    keypoints for geometric verification. Every pixel-level signal is returned
    so callers can require several independent evidences (pixel error, changed
    area, worst case, colour distribution) before this fallback auto-accepts.

    The artboard itself is searched first. A workbook thumbnail may be a crop of
    it rather than a downscaled copy, and a declared artboard padding shifts the
    matching scale as well, so the search range is wide. Only when the artboard
    cannot be aligned at all is the trimmed content box tried as a fallback -
    trimming changes the motif scale, which must not be applied blindly.
    """
    cache = cache if cache is not None else _TextureCache()
    query_token = (query.digest, query.image.shape)
    candidate_token = (candidate.digest, candidate.image.shape)
    q = cache.resized(query.image, query_token, 64)
    crop = cache.get(('bounds', candidate_token), lambda: _content_bounds(candidate.image))
    content = None
    if crop is not None:
        content = candidate.image[crop[1]:crop[3], crop[0]:crop[2]]
    def resize_body(image, height):
        # Cropped and whole-canvas coordinates cannot share a scale entry.
        bounds = crop if content is not None and image is content else None
        return cache.resized(image, (candidate_token, bounds), height)

    def coarse_search():
        probe = cache.resized(q, (query_token, 'height64'), 32)
        result = _texture_search(q, candidate.image, False, resize=resize_body, probe=probe)
        if result.get('rms', 1.) > .05 and content is not None:
            alternative = _texture_search(q, content, True, resize=resize_body, probe=probe)
            if alternative.get('score', 0.) > result.get('score', 0.):
                result = alternative
        return result

    # Precision starts from the exact raw coarse result. Never undo the public
    # .94 score factor with division or reuse a previously finalized verdict.
    best = copy.deepcopy(cache.get(('coarse', query_token, candidate_token), coarse_search))
    # Colour spread is compared on the content only: a declared artboard margin
    # legitimately adds white that the workbook thumbnail never shows.
    colour_body = content if content is not None else candidate.image
    def content_histogram():
        lab = cv2.cvtColor(resize_body(colour_body, 96), cv2.COLOR_BGR2LAB)
        result = cv2.calcHist([lab], [0, 1, 2], None, [12, 16, 16], [0, 256] * 3)
        cv2.normalize(result, result, norm_type=cv2.NORM_L1)
        return result
    histogram = cache.get(('content_histogram', candidate_token, crop), content_histogram)
    best['color_distance'] = float(cv2.compareHist(query.histogram, histogram,
                                                   cv2.HISTCMP_BHATTACHARYYA))
    palette = _palette_difference(query, candidate)
    comparison_height = 64
    body = content if best.get('trimmed') and content is not None else candidate.image
    if (precision and best.get('score', 0.) >= .80 and best['color_distance'] <= .25
            and query.image.shape[0] >= 96 and 'height' in best):
        # Use original detail for the final proof. At 64 pixels, moving an edge
        # by one sampling pixel can count as a large changed area in a stripe or
        # dot pattern. A denser scale/phase measurement reduces that quantisation
        # error without changing the acceptance limits or the source artwork.
        comparison_height = min(256, query.image.shape[0])
        detailed_query = cache.resized(query.image, query_token, comparison_height)
        centre = best['height'] * comparison_height / 64
        detailed = {'score': 0., 'method': 'texture', 'strong': False,
                    'trimmed': best.get('trimmed', False)}
        base_width = best.get('width_scale', 1.)
        for height in range(max(math.ceil(comparison_height / 2), round(centre) - 2),
                            round(centre) + 3):
            nominal_width = _resized_width(body, height)
            centre_width = round(nominal_width * base_width)
            radius = max(1, math.ceil(nominal_width * .005))
            for width in range(centre_width - radius, centre_width + radius + 1):
                width_scale = width / nominal_width
                if not .991 <= width_scale <= 1.009:
                    continue
                _texture_scan(detailed_query, body, height, detailed, width_scale, resize=resize_body)
        if 'height' in detailed:
            _texture_scan(detailed_query, body, detailed['height'], detailed,
                          detailed.get('width_scale', 1.), subpixel=True, resize=resize_body)
        # A low-resolution score is never substituted for a failed detailed
        # verification. Retain it for diagnostics only.
        if 'rms' in detailed:
            detailed['coarse_metrics'] = {key: best.get(key) for key in
                ('rms', 'changed', 'major_changed', 'worst', 'residual', 'height')}
            detailed['color_distance'] = best['color_distance']
            best = detailed
        else:
            comparison_height = 64
    if 'rms' in best:
        # Auto acceptance needs every signal at once: near-exact pixels, no
        # localized difference, no bad region, a matching colour spread, and no
        # inked artboard content left unexplained outside the matched window.
        # Bounds sit inside the measured gap between aligned repeats (rms <~ .033,
        # changed <~ .012, no gross difference) and genuinely altered artwork
        # (rms >~ .15, changed >~ .07), so no single relaxed number can carry a
        # false match on its own.
        best['strong'] = bool(best['rms'] <= .045 and best['changed'] <= .015
                              and best['major_changed'] <= .003 and best['worst'] <= .55
                              and best['color_distance'] <= .25
                              and best.get('residual', 1.) <= .08
                              and palette['palette_mismatch'] <= .005
                              and best.get('coherent_difference', 1.) == 0
                              and (best.get('source_coverage', 0.) >= .95
                                   or best.get('source_ink_coverage', 0.) >= .98))
    thresholds = {'rms': .045, 'changed': .015, 'major_changed': .003,
                  'worst': .55, 'color_distance': .25, 'residual': .08}
    best['failed_checks'] = [key for key, limit in thresholds.items()
                             if best.get(key, 1.) > limit]
    best.update(palette)
    if palette['palette_mismatch'] > .005:
        best['failed_checks'].append('foreground_colours')
    if best.get('coherent_difference', 1.) > 0:
        best['failed_checks'].append('coherent_difference')
    if best.get('source_coverage', 0.) < .95 and best.get('source_ink_coverage', 0.) < .98:
        best['failed_checks'].append('candidate_coverage')
    if 'location' in best:
        bounds = crop if best.get('trimmed') and crop else (0, 0, candidate.image.shape[1], candidate.image.shape[0])
        left, top, right, bottom = bounds
        th, tw = best['tile_shape']
        sx, sy = tw / (right - left), th / (bottom - top)
        factor = query.image.shape[0] / comparison_height
        qh, qw = comparison_height, _resized_width(query.image, comparison_height)
        matrices = []
        for x, y in (best.get('phases') or [best['location']]):
            for row_offset in range(math.floor(y / th), math.ceil((y + qh) / th)):
                for col_offset in range(math.floor(x / tw), math.ceil((x + qw) / tw)):
                    matrices.append([[sx * factor, 0., (col_offset * tw - x - left * sx) * factor],
                                     [0., sy * factor, (row_offset * th - y - top * sy) * factor]])
                    if len(matrices) >= 32:
                        break
                if len(matrices) >= 32:
                    break
            if len(matrices) >= 32:
                break
        source_coverage = best.get('source_coverage', 0.)
        local_pixels_ok = (best.get('rms', 1.) <= .045 and best.get('changed', 1.) <= .015
                           and best.get('major_changed', 1.) <= .003
                           and best.get('worst', 1.) <= .55)
        best['alignment'] = {
            'kind': 'periodic', 'direction': 'candidate_to_query',
            'matrix': matrices[0], 'matrices': matrices,
            'body_bounds': list(bounds),
            'query_size': [query.image.shape[1], query.image.shape[0]],
            'candidate_size': [candidate.image.shape[1], candidate.image.shape[0]],
            'query_coverage': 1. if local_pixels_ok else 0.,
            'candidate_coverage': source_coverage,
            'candidate_ink_coverage': best.get('source_ink_coverage', 0.),
            'unverified_query': 0. if local_pixels_ok else 1.,
            'unverified_candidate': 1 - source_coverage, 'edge_verified_coverage': 0.,
            'geometry_verified': bool(local_pixels_ok), 'verified': best['strong'],
            'comparison_height': comparison_height}
    # Keep the textured fallback below a geometrically verified near-exact match.
    best['score'] *= .94
    return best


def _auto_reason(result: dict) -> str:
    """Short, employee-facing reason for an automatic decision."""
    if result.get('accepted_by') == '纹理像素验证':
        return '图案逐像素一致、颜色分布相同，且本批次没有接近的其他候选。'
    return '图像细节、排列和颜色一致，且本批次没有接近的其他候选。'


def _review_reason(result: dict, histogram_distance: float) -> str:
    """Name the specific evidence that is missing instead of a generic hint."""
    colour = float(result.get('color_distance', histogram_distance))
    if colour > .25:
        return '图案排列接近，但两侧颜色分布不一致，请确认是否为同款不同色。'
    failed = result.get('failed_checks', [])
    if 'candidate_coverage' in failed:
        return '原稿还有未核实的图案区域，请确认是否存在额外内容。'
    if 'query_coverage' in failed:
        return '部分图案尚未完整对齐，请放大确认。'
    if result.get('method') == 'texture':
        if result.get('major_changed', 0.) > .02:
            return '图案接近，但有局部区域明显不同，请并排确认。'
        if result.get('changed', 0.) > .06 or result.get('rms', 1.) > .06:
            return '图案大致一致，但仍有较多区域对不上，请放大确认。'
        return '图案重复度高，自动核对无法完全确认，请对照后选择。'
    if not result.get('inliers'):
        return '图中可辨认的独特细节不足，暂时无法自动核对图案。'
    if result.get('major_changed', 0.) > .015 or result.get('mae', 1.) > .06:
        return '两张图的局部内容存在差异，请确认是否为同一张图。'
    if result.get('coverage', 1.) < .18:
        return '只核对上图片的一小部分区域，其余内容无法比对。'
    return '图像细节接近，但还不足以自动确认，请对照后选择。'


def _combine_evidence(feature: dict, texture: dict) -> dict:
    """Merge both methods without letting one silently overwrite the other."""
    if feature.get('channels'):
        feature = feature['channels']['features']
    primary = (texture if texture.get('strong') else feature if feature.get('auto_ok')
               else texture if texture.get('score', 0.) > feature.get('score', 0.) else feature)
    merged = dict(primary)
    merged['score'] = max(float(texture.get('score', 0.)), float(feature.get('score', 0.)))
    merged['strong'] = bool(texture.get('strong') or feature.get('strong'))
    merged['feature_score'] = round(float(feature.get('score', 0.)), 4)
    merged['feature_strong'] = bool(feature.get('strong'))
    merged['channels'] = {'features': dict(feature), 'texture': dict(texture)}
    merged['selected_channel'] = primary.get('method', 'features')
    if texture.get('strong'):
        merged['auto_ok'], merged['accepted_by'] = True, '纹理像素验证'
    elif feature.get('auto_ok'):
        merged['auto_ok'], merged['accepted_by'] = True, '几何特征验证'
    else:
        merged['auto_ok'], merged['accepted_by'] = False, None
    return merged


def _evidence(result: dict, histogram_distance: float, gap: float) -> dict:
    """Every signal behind one decision, for diagnosis rather than for the UI.

    Kept complete on purpose: when a row stays in review, the reason text names
    the missing evidence, and this record shows the measured value that produced
    it, so a borderline case can be inspected without re-running the batch.
    """
    def rounded(key):
        value = result.get(key)
        return None if value is None else round(float(value), 4)

    channels = result.get('channels') or {result.get('method', 'features'): result}
    def channel(value):
        return {'score': float(value.get('score', 0.)), 'strong': bool(value.get('strong')),
                'auto_ok': bool(value.get('auto_ok') or value.get('method') == 'texture' and value.get('strong')),
                'metrics': {key: value[key] for key in
                    ('inliers', 'coverage', 'mae', 'rms', 'changed', 'major_changed', 'worst',
                     'color_distance', 'global_mae', 'global_changed', 'overlap', 'verified_coverage',
                     'source_coverage', 'source_ink_coverage', 'residual', 'plausible', 'edge_proof',
                     'coarse_metrics', 'periodic_proof', 'palette_applicable',
                     'palette_mismatch', 'palette_query_flat_coverage',
                     'palette_candidate_flat_coverage', 'coherent_difference') if key in value},
                'failed_checks': list(value.get('failed_checks', [])),
                'alignment': value.get('alignment')}
    return {'evidence_version': 2, 'method': result.get('method', 'features'),
            'selected_channel': result.get('selected_channel', result.get('method', 'features')),
            'channels': {key: channel(value) for key, value in channels.items()},
            'failed_checks': list(result.get('failed_checks', [])),
            'checked': result.get('accepted_by'),
            'colour': rounded('color_distance') if 'color_distance' in result
                      else round(float(histogram_distance), 4),
            'gap': round(gap, 4),
            'thresholds': ({'rms': .045, 'changed': .015, 'major_changed': .003,
                            'worst': .55, 'colour': .25, 'residual': .08,
                            'source_coverage_min': .95, 'source_ink_coverage_min': .98}
                           if result.get('method') == 'texture' else
                           {'mae': .045, 'changed': .08, 'major_changed': .015,
                            'inliers_min': 14, 'coverage_min': .18, 'query_coverage_min': .95,
                            'source_coverage_min': .95, 'source_ink_coverage_min': .98}),
            'pixel_rms': rounded('rms'),
            'changed': rounded('changed'),
            'major_changed': rounded('major_changed'),
            'worst': rounded('worst'),
            'residual': rounded('residual'),
            'trimmed': result.get('trimmed'),
            'inliers': result.get('inliers'),
            'coverage': rounded('coverage'),
            'mae': rounded('mae')}


def _pattern_supported(result: dict) -> bool:
    channels = result.get('channels') or {result.get('method', 'features'): result}
    feature = channels.get('features', {})
    texture = channels.get('texture', {})
    return bool((feature.get('inliers', 0) >= 6 and feature.get('coverage', 0.) >= .05
                 and feature.get('mae', 1.) <= .08 and feature.get('major_changed', 1.) <= .04)
                or (texture.get('rms', 1.) <= .16 and texture.get('changed', 1.) <= .2
                    and texture.get('major_changed', 1.) <= .08
                    and texture.get('color_distance', 1.) <= .35))


def _ownership_supported(result: dict) -> bool:
    """A shared logo/local crop cannot claim a file from a complete match."""
    if result.get('auto_ok'):
        return True
    channels = result.get('channels') or {result.get('method', 'features'): result}
    feature = channels.get('features', {})
    texture = channels.get('texture', {})
    geometry = (feature.get('verified_coverage', 0.) >= .9
                and feature.get('global_mae', 1.) <= .06
                and feature.get('global_changed', 1.) <= .12
                and feature.get('source_coverage', 0.) >= .9
                and feature.get('palette_mismatch', 0.) <= .005)
    repeat = (texture.get('rms', 1.) <= .065 and texture.get('changed', 1.) <= .04
              and texture.get('major_changed', 1.) <= .015
              and texture.get('source_coverage', 0.) >= .9
              and texture.get('color_distance', 1.) <= .25
              and texture.get('palette_mismatch', 0.) <= .005)
    return bool(geometry or repeat)


def _texture_results(query, identities, file_images, precision, cache, executor=None):
    parent_check = current_check()
    def evaluate(identity):
        with cancellation_scope(parent_check):
            cancellation_check()
            try:
                result = _texture(query, file_images[identity], precision=precision, cache=cache)
                cancellation_check()
                return identity, result
            except TaskCancelled:
                raise
            except Exception:
                return identity, None
    # Both map variants preserve original candidate order, including failures.
    # No worker touches geometry RNG, row ownership or another worker's best.
    return (executor.map(evaluate, identities) if executor is not None
            else map(evaluate, identities))


def _match_appearances(rows: list[dict], files: list[dict], row_images: dict,
                       file_images: dict, progress=None, *, texture_workers=2,
                       proposals=None) -> list[dict]:
    if type(texture_workers) is not int or texture_workers not in (1, 2):
        raise ValueError('纹样验证工作线程数只能是 1 或 2。')
    if texture_workers == 1:
        return _match_appearances_serial(rows, files, row_images, file_images, progress,
                                         proposals=proposals)
    # PyMuPDF rendering and SIFT/RANSAC remain on the calling thread. OpenCV's
    # process-global thread setting is never changed inside a running job.
    with ThreadPoolExecutor(max_workers=texture_workers, thread_name_prefix='hsd-texture') as executor:
        return _match_appearances_serial(rows, files, row_images, file_images, progress, executor,
                                         proposals=proposals)


def _match_appearances_serial(rows, files, row_images, file_images, progress=None, executor=None,
                              *, proposals=None):
    results = []
    texture_cache = _TextureCache()
    readable = [f for f in files if f['id'] in file_images]
    duplicate_previews = Counter(a.digest for a in file_images.values())
    for i, row in enumerate(rows, 1):
        cancellation_check()
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
        scores, histograms, failures = {}, {}, []
        proposal = (proposals or {}).get(row['id'])
        proposed_id = (proposal.get('file_id') if isinstance(proposal, dict)
                       and proposal.get('verdict') == 'same' else None)
        proposed_file = next((file for file in readable if file['id'] == proposed_id), None)
        proposed_result, score_cutoff = None, None
        if (proposed_file is not None and not proposed_file.get('issue')
                and duplicate_previews[file_images[proposed_id].digest] == 1):
            try:
                proposed_result = _features(query, file_images[proposed_id])
                if proposed_result.get('strong') and proposed_result['score'] >= .91:
                    # This is the unchanged existing feature-only acceptance
                    # path. AI selects the order of work but supplies no proof.
                    # Every other file still gets the full descriptor ratio
                    # test, and only a rigorous upper bound can avoid its warp.
                    # Preserve the wider credible-competition window too, not
                    # only the .045 runner-up gap. A candidate within .12 still
                    # needs its real pattern evidence for qualification/audit.
                    score_cutoff = min(.91, max(.55, proposed_result['score'] - .12))
            except Exception:
                # Failed speculative work never removes a candidate or turns
                # a partial inspection into a complete competition proof.
                proposed_result = None
        for file in readable:
            cancellation_check()
            identity = file['id']
            candidate = file_images[identity]
            histograms[identity] = float(cv2.compareHist(query.histogram, candidate.histogram,
                                                        cv2.HISTCMP_BHATTACHARYYA))
            try:
                if identity == proposed_id and proposed_result is not None:
                    result = proposed_result
                elif score_cutoff is not None:
                    result = _features(query, candidate, score_cutoff=score_cutoff)
                else:
                    result = _features(query, candidate)
            except Exception:
                # One unruly pair must never abort the whole batch; it simply
                # carries no geometric evidence and falls back to the texture pass.
                result = {'score': 0., 'strong': False, 'method': 'features'}
                failures.append({'file_id': identity, 'check': 'geometry_evaluation_failed'})
            result['score'] = max(result['score'], .4 * (1 - histograms[identity]))
            result['auto_ok'] = bool(result['strong'] and result['score'] >= .91)
            result['accepted_by'] = '几何特征验证' if result['auto_ok'] else None
            scores[identity] = result
        best_feature = max(scores, key=lambda identity: scores[identity]['score'])
        if score_cutoff is not None and not scores[best_feature]['strong']:
            # A higher-scoring but unverified competitor activates the legacy
            # texture shortlist. Bounds must never reorder that shortlist (or
            # its dynamically chosen fine pass), so recover exact geometry for
            # every candidate before entering the original path.
            scores, failures = {}, []
            for file in readable:
                identity = file['id']
                try:
                    result = _features(query, file_images[identity])
                except Exception:
                    result = {'score': 0., 'strong': False, 'method': 'features'}
                    failures.append({'file_id': identity, 'check': 'geometry_evaluation_failed'})
                result['score'] = max(result['score'], .4 * (1 - histograms[identity]))
                result['auto_ok'] = bool(result['strong'] and result['score'] >= .91)
                result['accepted_by'] = '几何特征验证' if result['auto_ok'] else None
                scores[identity] = result
            score_cutoff = None
            best_feature = max(scores, key=lambda identity: scores[identity]['score'])
        if not scores[best_feature]['strong']:
            shortlist = sorted(histograms, key=histograms.get)[:6]
            shortlist += sorted(scores, key=lambda identity: scores[identity]['score'], reverse=True)[:2]
            for identity, texture in _texture_results(query, list(dict.fromkeys(shortlist)),
                    file_images, False, texture_cache, executor):
                if texture is None:
                    # Texture evidence is optional; a failure here only means this
                    # candidate keeps its geometric/histogram evidence.
                    failures.append({'file_id': identity, 'check': 'texture_evaluation_failed'})
                    continue
                if texture['score'] > scores[identity]['score'] or texture.get('strong'):
                    scores[identity] = _combine_evidence(scores[identity], texture)
        # Detailed verification is reserved for credible leading candidates;
        # the full candidate set has already been measured independently.
        coarse_ranking = sorted(scores, key=lambda identity: -scores[identity]['score'])
        leading = coarse_ranking[:3]
        if (not scores[coarse_ranking[0]].get('auto_ok')
                or scores[coarse_ranking[0]].get('selected_channel') == 'texture'):
            prefetched = None
            if executor is not None:
                # Fine verification may raise OR lower the leading score. Keep
                # the original sequential eligibility check when applying each
                # result; speculative work must not add/remove evidence.
                detailed = [identity for identity in leading if scores[identity]['score'] >= .75]
                prefetched = dict(_texture_results(query, detailed, file_images,
                                                   True, texture_cache, executor))
            for identity in leading:
                if scores[identity]['score'] < max(.75, scores[coarse_ranking[0]]['score'] - .18):
                    continue
                texture = (prefetched[identity] if prefetched is not None else
                           next(_texture_results(query, [identity], file_images,
                                                 True, texture_cache))[1])
                if texture is None:
                    failures.append({'file_id': identity, 'check': 'detailed_texture_evaluation_failed'})
                    continue
                scores[identity] = _combine_evidence(scores[identity], texture)
        ranking = sorted(scores, key=lambda identity: (-scores[identity]['score'], identity))
        base['candidates'] = [{'file_id': identity, 'score': round(scores[identity]['score'], 4)}
                              for identity in ranking[:5]]
        for candidate in base['candidates']:
            if 'score_upper_bound' in scores[candidate['file_id']]:
                candidate['score_kind'] = 'geometric_upper_bound'
        top = ranking[0]
        top_result = scores[top]
        top_score = top_result['score']
        runner_up = scores[ranking[1]]['score'] if len(ranking) > 1 else 0
        gap = top_score - runner_up
        top_file = next(file for file in readable if file['id'] == top)
        base['evidence'] = _evidence(top_result, histograms[top], gap)
        credible = [identity for identity in ranking if identity == top or
                    (scores[identity].get('strong') or
                     (scores[identity]['score'] >= max(.55, top_score - .12)
                      and _pattern_supported(scores[identity])))]
        supported = _pattern_supported(top_result)
        base['evidence']['competition'] = {
            'version': 'local-competition-1',
            'evaluated_file_ids': [file['id'] for file in readable],
            'credible_candidate_ids': credible,
            'scores': [{'file_id': identity, 'score': round(scores[identity]['score'], 4),
                        'pattern_supported': _pattern_supported(scores[identity])} for identity in ranking],
            'complete': not failures, 'unique': len(credible) == 1 and supported,
            'failures': failures}
        if score_cutoff is not None:
            excluded = [{'file_id': identity, 'geometric_score_upper_bound':
                         scores[identity]['score_upper_bound']}
                        for identity in ranking if 'score_upper_bound' in scores[identity]]
            base['evidence']['competition']['bounded_geometry'] = {
                'version': 'all-correspondence-hull-1',
                'proposal_file_id': proposed_id, 'cutoff': score_cutoff,
                'excluded_from_expensive_geometry': excluded,
                'all_files_ratio_tested': True,
                'ai_supplies_acceptance_evidence': False}
            for candidate in base['evidence']['competition']['scores']:
                if 'score_upper_bound' in scores[candidate['file_id']]:
                    candidate['score_kind'] = 'geometric_upper_bound'
        base['evidence']['claim_strength'] = ('verified' if top_result.get('auto_ok')
                                               else 'credible' if _ownership_supported(top_result) else 'weak')
        decision_failures = []
        if top_score < .55:
            decision_failures.append('no_credible_candidate')
        if top_file.get('issue'):
            decision_failures.append('source_issue')
        if duplicate_previews[file_images[top].digest] > 1:
            decision_failures.append('duplicate_preview')
        if gap < .045:
            decision_failures.append('candidate_gap')
        if failures:
            decision_failures.append('incomplete_candidate_validation')
        base['evidence']['failed_checks'] = list(dict.fromkeys(
            base['evidence']['failed_checks'] + decision_failures))
        if top_score < .55:
            base['reason'] = '相似度不足，未自动选择文件；候选仅供人工查看。'
        else:
            base['status'] = 'review'
            base['reason'] = _review_reason(top_result, histograms[top])
            if top_file.get('issue'):
                base['reason'] = top_file['issue']
            elif duplicate_previews[file_images[top].digest] > 1:
                base['reason'] = '多个 AI 文件有相同预览，无法自动确定唯一原文件。'
            elif gap < .045:
                base['reason'] = '存在十分接近的候选，请确认具体颜色、图案及文件。'
            elif failures:
                base['reason'] = '部分候选无法完成验证，请人工确认。'
            elif top_result.get('auto_ok'):
                base.update(status='auto', file_id=top, reason=_auto_reason(top_result))
        results.append(base)
    # A weak competing row is still evidence of conflicting ownership; never
    # silently allocate a shared best file to whichever row happened to run first.
    contenders = defaultdict(list)
    for result in results:
        if (result['candidates'] and result['candidates'][0]['score'] >= .55
                and result.get('evidence', {}).get('claim_strength') != 'weak'):
            contenders[result['candidates'][0]['file_id']].append(result)
    for group in contenders.values():
        if len(group) > 1:
            for result in group:
                result.update(status='review', file_id=None,
                              reason='多行图片指向同一个 AI 文件，请人工确认一一对应关系。')
                result['evidence']['failed_checks'] = list(dict.fromkeys(
                    result['evidence']['failed_checks'] + ['ownership_conflict']))
    return results


@dataclass(frozen=True)
class PreparedMatching:
    """Task-local decoded inputs; never serialize this object or share jobs.

    Splitting preparation from verification lets an optional candidate-routing
    provider inspect the existing previews without a second extraction/render.
    Files, row IDs and arrays remain bound to this particular preparation.
    """
    rows: list[dict]
    files: list[dict]
    warnings: list[str]
    row_images: dict
    file_images: dict
    file_bindings: dict[str, str]


def _bound_appearance(path: str, detector, bindings: dict[str, str]) -> _Appearance:
    """Bind the actual encoded image bytes to the pixels decoded from them."""
    source = Path(path)
    with _source_reader(source) as (stream, write_locked):
        signature = _file_signature(os.fstat(stream.fileno()))
        digest = _source_digest(stream)[0]
        appearance = _appearance(_read_image(path), detector)
        checked = digest if write_locked else _source_digest(stream)[0]
        if (checked != digest or _file_signature(os.fstat(stream.fileno())) != signature
                or _file_signature(source.stat()) != signature):
            raise ValueError('准备期间图片发生变化，请重新导入。')
    bindings[str(source.resolve())] = digest
    return appearance


def _verify_prepared_bindings(prepared: PreparedMatching) -> None:
    for source, expected in prepared.file_bindings.items():
        cancellation_check()
        path = Path(source)
        try:
            with _source_reader(path) as (stream, _):
                signature = _file_signature(os.fstat(stream.fileno()))
                digest = _source_digest(stream)[0]
                changed = (digest != expected
                           or _file_signature(os.fstat(stream.fileno())) != signature
                           or _file_signature(path.stat()) != signature)
        except OSError as exc:
            raise ValueError('AI 检索期间原稿或图片无法读取，请重新导入。') from exc
        if changed:
            raise ValueError('AI 检索期间源文件发生变化，请重新导入。')


def prepare_matching(source_path: str, rows: list[dict], work_dir: str,
                     progress=None) -> PreparedMatching:
    """Safely read/extract/render inputs once, without comparing file pairs."""
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
    from .appearance_cache import DiskAppearances, AppearanceStorageError
    file_bindings = {}
    file_images = DiskAppearances(session / 'file_appearances', file_bindings)
    row_images = DiskAppearances(session / 'row_appearances', file_bindings)
    for i, record in enumerate(files, 1):
        cancellation_check()
        if progress:
            progress(f'正在生成 AI 预览 {i} / {len(files)}', i, len(files))
        try:
            _render(record, previews)
            file_images[record['id']] = _bound_appearance(record['preview_path'], detector,
                                                        file_bindings)
        except (TaskCancelled, AppearanceStorageError):
            raise
        except Exception as exc:
            record['issue'] = str(exc) if isinstance(exc, ValueError) else 'AI 文件损坏或预览无法读取，请单独检查。'
    for row in rows:
        cancellation_check()
        if not row.get('image_path') or row.get('issue'):
            continue
        try:
            row_images[row['id']] = _bound_appearance(row['image_path'], detector, file_bindings)
        except (OSError, ValueError, cv2.error):
            warnings.append(f"第 {row.get('row_number', row['id'])} 行图片无法读取，已留待处理。")
    bad_count = sum(bool(file['issue']) for file in files)
    if bad_count:
        warnings.append(f'{bad_count} 个 AI 文件预览有问题或含多个画板，请查看原文件列表。')
    file_bindings.update({str(Path(record['source_path']).resolve()): record['source_sha256']
                          for record in files if record.get('source_sha256')})
    return PreparedMatching(copy.deepcopy(rows), files, warnings, row_images, file_images,
                            file_bindings)


def match_prepared(prepared: PreparedMatching, progress=None, *, proposals=None,
                   texture_workers=2, verify_sources=True) -> dict:
    """Verify local evidence; AI proposals only choose evaluation order.

    A provider round trip can be long, so the split API rechecks every readable
    source before using its earlier pixels. The immediate legacy wrapper skips
    this extra pass because _render already checks under its read lease.
    """
    if not isinstance(prepared, PreparedMatching):
        raise TypeError('请传入当前任务准备好的匹配输入。')
    if verify_sources:
        _verify_prepared_bindings(prepared)
    cv2.setRNGSeed(42)
    matches = _match_appearances(prepared.rows, prepared.files, prepared.row_images,
                                prepared.file_images, progress,
                                texture_workers=texture_workers, proposals=proposals)
    if verify_sources:
        _verify_prepared_bindings(prepared)
    return {'files': prepared.files, 'matches': matches, 'warnings': list(prepared.warnings),
            'comparison_bindings': dict(prepared.file_bindings)}


def scan_and_match(source_path: str, rows: list[dict], work_dir: str, progress=None, *,
                   texture_workers=2) -> dict:
    """Inspect originals read-only and return conservative per-row candidates."""
    prepared = prepare_matching(source_path, rows, work_dir, progress)
    return match_prepared(prepared, progress, texture_workers=texture_workers,
                          verify_sources=False)
