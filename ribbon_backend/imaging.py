"""Deterministic raster composition. Demo artwork is explicitly marked in metadata."""
from __future__ import annotations

import hashlib
import math
import os
import shutil
from pathlib import Path
import random
import tempfile
import threading
import uuid
from contextlib import closing, contextmanager
from contextvars import ContextVar
from functools import wraps
from typing import Callable

from PIL import Image, ImageColor, ImageDraw, ImageOps

MODES = ("grid", "stagger", "scatter", "single", "ends", "panels")
MAX_PIXELS = 40_000_000
# Check our own dimensions below; do not mutate Pillow's process-wide limit in
# the host, which also serves the existing HSD and material workflows.
PARAM_DEFAULTS = {"scale": 1.0, "spacing": 1.0, "rotation": 0.0,
                  "offset_x": 0.0, "offset_y": 0.0, "background_color": None}
_IMAGE_MEMORY_LOCK = threading.RLock()
_SPACE_CHECKER = ContextVar('ribbon_space_checker', default=None)
STANDALONE_FREE_MARGIN = 64 * 1024 * 1024


@contextmanager
def disk_space_guard(checker):
    token = _SPACE_CHECKER.set(checker)
    try:
        yield
    finally:
        _SPACE_CHECKER.reset(token)


def png_space(width, height):
    # RGBA raw bytes plus PNG filters/deflate overhead and metadata; independent
    # of whether a particular photograph happens to compress well.
    return int(width) * int(height) * 5 + 1024 * 1024


def require_space(directory, needed):
    directory = Path(directory)
    checker = _SPACE_CHECKER.get()
    if checker is not None:
        checker(directory, int(needed))
        return
    while not directory.exists() and directory.parent != directory:
        directory = directory.parent
    if shutil.disk_usage(directory).free < int(needed) + STANDALONE_FREE_MARGIN:
        raise OSError(28, '存储空间不足，请清理空间后重试')


def memory_bounded_operation(function):
    """Serialize large pixel allocations in this single service process.

    The lock is intentionally outside model/network calls: another employee may
    upload while the model is thinking. Host upload routes must call synchronous
    image work in a thread pool so an allocation wait cannot block ASGI polling.
    """
    @wraps(function)
    def wrapped(*args, **kwargs):
        with _IMAGE_MEMORY_LOCK:
            return function(*args, **kwargs)
    return wrapped


def _save_png(image: Image.Image, path: Path, dpi: int | None = 144) -> None:
    path = Path(path)
    require_space(path.parent, png_space(*image.size))
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        options = {'dpi': (dpi, dpi)} if dpi is not None else {}
        image.save(temp, format="PNG", optimize=False, **options)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def read_image(path: Path) -> Image.Image:
    """Decode fully and reject animated/oversized inputs before processing."""
    with Image.open(path) as source:
        if source.width * source.height > MAX_PIXELS or source.width < 1 or source.height < 1:
            raise ValueError("图像像素数量超出允许范围")
        if getattr(source, "n_frames", 1) != 1:
            raise ValueError("暂不支持动态图像，请上传单帧 PNG/JPEG/WebP")
        source.load()
        if source.getexif().get(274, 1) == 1:
            return source.convert("RGBA")
        with ImageOps.exif_transpose(source) as oriented:
            return oriented.convert("RGBA")


def _star_points(cx: float, cy: float, radius: float, points: int = 5) -> list[tuple[float, float]]:
    return [(cx + radius * (1 if i % 2 == 0 else .43) * math.cos(-math.pi / 2 + i * math.pi / points),
             cy + radius * (1 if i % 2 == 0 else .43) * math.sin(-math.pi / 2 + i * math.pi / points))
            for i in range(points * 2)]


def _demo_pattern(kind: str, size: int = 512) -> Image.Image:
    im = Image.new("RGBA", (size, size))
    d = ImageDraw.Draw(im)
    c = size / 2
    if kind == "flower":
        for i in range(6):
            a = math.pi * i / 3
            x, y, r = c + .22 * size * math.cos(a), c + .22 * size * math.sin(a), .19 * size
            d.ellipse((x-r, y-r, x+r, y+r), fill="#E9A28A")
        d.ellipse((c-.155*size, c-.155*size, c+.155*size, c+.155*size), fill="#E7BB53")
        d.ellipse((c-.064*size, c-.064*size, c+.064*size, c+.064*size), fill="#FFF1C2")
    elif kind == "star":
        d.polygon(_star_points(c, c, size*.44), fill="#E7B849")
        d.ellipse((c-25, c-25, c+25, c+25), fill="#FFF0C3")
    elif kind == "ring":
        d.ellipse((size*.1, size*.1, size*.9, size*.9), outline="#619D8F", width=int(size*.12))
        d.ellipse((size*.42, size*.42, size*.58, size*.58), fill="#619D8F")
    elif kind == "leaf":
        d.ellipse((size*.18, size*.08, size*.82, size*.92), fill="#7B9C6E")
        d.line((c, size*.22, c, size*.88), fill="#F3F0DD", width=13)
        for i in range(4):
            y = size*(.32+i*.13)
            d.line((c, y+.08*size, c-.17*size, y-.05*size), fill="#F3F0DD", width=8)
            d.line((c, y+.08*size, c+.17*size, y-.05*size), fill="#F3F0DD", width=8)
    else:
        raise ValueError("未知演示图案")
    return im


def seed_assets(directory: Path) -> list[dict]:
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    rows = []
    for key, name in (("flower", "杏粉小花"), ("star", "暖金星形"), ("ring", "青绿圆环"), ("leaf", "鼠尾草叶片")):
        path = directory / f"demo-{key}.png"
        if not path.exists():
            _save_png(_demo_pattern(key), path)
        rows.append({"id": f"demo-{key}", "name": name, "kind": "pattern", "path": str(path),
                     "is_demo": True, "shared": True, "source": "demo"})
    for key, name, color in (("sage", "浅绿织感", "#E6EFE3"), ("cream", "暖白纸感", "#F7F2E8"),
                              ("rose", "淡粉柔雾", "#F4DFDB"), ("blue", "雾蓝底色", "#DFEAF0")):
        path = directory / f"demo-bg-{key}.png"
        if not path.exists():
            im = Image.new("RGB", (1024, 512), color)
            d = ImageDraw.Draw(im, "RGBA")
            # Low contrast lines are intentionally a demo texture, never a company asset.
            for x in range(0, im.width, 8):
                d.line((x, 0, x, im.height), fill=(255, 255, 255, 30), width=1)
            _save_png(im, path)
        rows.append({"id": f"demo-bg-{key}", "name": name, "kind": "background", "path": str(path),
                     "is_demo": True, "shared": True, "source": "demo"})
    return rows


def _profile(profile: dict) -> tuple[int, int, int]:
    w, h, dpi = int(profile["width"]), int(profile["height"]), int(profile["dpi"])
    if not (16 <= w <= 16000 and 16 <= h <= 16000 and w*h <= MAX_PIXELS and 36 <= dpi <= 1200):
        raise ValueError("输出配置超出本地渲染器允许范围")
    if str(profile.get("format", "PNG")).upper() != "PNG":
        raise ValueError("当前渲染器仅支持 PNG；正式格式请通过业务验收配置")
    return w, h, dpi


def validate_image(path: Path, profile: dict) -> dict:
    width, height, dpi = _profile(profile)
    with Image.open(path) as im:
        im.verify()
    with Image.open(path) as im:
        im.load()
        if im.size != (width, height) or im.format != "PNG" or im.mode not in ("RGB", "RGBA"):
            raise ValueError("母版文件不符合已保存的输出配置")
        saved_dpi = im.info.get("dpi")
        if not saved_dpi or any(abs(value - dpi) > 1 for value in saved_dpi):
            raise ValueError("母版 DPI 元数据与配置不一致")
        return {"width": width, "height": height, "dpi": dpi, "format": im.format,
                "mode": im.mode, "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest(),
                "bytes": Path(path).stat().st_size}


def _positions(mode: str, width: int, height: int, params: dict, seed: int,
               rules: dict) -> list[tuple[float, float, float, float, int]]:
    """x, y, size multiplier, extra rotation, asset ordinal; ordered layers."""
    spacing = float(params["spacing"])
    rows = max(1, min(4, int(rules.get("rows", 2))))
    step = height * float(rules.get("step_ratio", .64)) * spacing
    cols = max(1, min(120, math.ceil(width / step)))
    actual_step = width / cols
    positions = []
    if mode in ("grid", "stagger", "scatter"):
        rng = random.Random(seed)
        for row in range(rows):
            for col in range(cols):
                x = (col + .5) * actual_step
                y = height * (row + .5) / rows
                extra = 0.0
                if mode == "stagger" and row % 2:
                    x += actual_step * .5
                elif mode == "scatter":
                    x += rng.uniform(-.23, .23) * actual_step
                    y += rng.uniform(-.13, .13) * height / rows
                    extra = rng.uniform(-25, 25)
                positions.append((x, y, 1, extra, row + col))
    elif mode == "single":
        for col in range(cols):
            positions.append(((col+.5)*actual_step, height/2, 1.25, 0, col))
    elif mode == "ends":
        positions.extend([(height*.46, height/2, 2, 0, 0), (width-height*.46, height/2, 2, 0, 0)])
        inner_width = max(0, width-height*1.85)
        inner_cols = max(0, int(inner_width / step))
        for col in range(inner_cols):
            positions.append((height*.925+(col+.5)*inner_width/inner_cols, height/2, .8, 0, col+1))
    elif mode == "panels":
        panel_width = width/3
        count = max(1, int(panel_width/step))
        for col in range(count):
            for row in range(2):
                positions.append(((col+.5)*panel_width/count, height*(row+.5)/2, .9, 0, col+row))
        for col in range(count):
            positions.append((panel_width+(col+.5)*panel_width/count, height/2, 1.1, 0, col+1))
        positions.append((panel_width*2.5, height/2, 2.15, 0, 0))
    else:
        raise ValueError("不支持的排版模式")
    return positions


def estimate_render_space(snapshot):
    """Conservative disk estimate for final PNGs and unique staged motifs.

    Stage bounds assume square source motifs (the largest aspect for a given
    long edge) and the renderer's existing 40 MP intermediate guard. This is a
    free-space preflight, not a user quota or a change to production dimensions.
    """
    width, height, _ = _profile(snapshot['output_profile'])
    required = png_space(width, height) + png_space(min(width, 1800), min(height, 600))
    if snapshot.get('composite_ref'):
        return required
    params = {**PARAM_DEFAULTS, **snapshot.get('params', {})}
    rules = snapshot.get('template_rules', {})
    mode = snapshot.get('template_mode', 'stagger')
    refs = snapshot.get('asset_refs', [])
    if not refs:
        return required
    base_size = height * float(rules.get('motif_ratio', .27)) * float(params['scale'])
    unique = {(index % len(refs), max(1, min(int(base_size*factor), height*3)),
               float(params['rotation']) + rotation)
              for _, _, factor, rotation, index in _positions(mode, width, height, params, int(snapshot.get('seed', 0)), rules)}
    for _, size, angle in unique:
        radians = math.radians(angle)
        edge = math.ceil(size * (abs(math.cos(radians)) + abs(math.sin(radians)))) + 2
        required += min(edge * edge, MAX_PIXELS) * 5 + 1024 * 1024
    return required


@memory_bounded_operation
def render(snapshot: dict, resolve_asset: Callable[[str], Path], master_path: Path,
           preview_path: Path) -> dict:
    require_space(Path(master_path).parent, estimate_render_space(snapshot))
    width, height, dpi = _profile(snapshot["output_profile"])
    params = {**PARAM_DEFAULTS, **snapshot.get("params", {})}
    if snapshot.get("composite_ref"):
        canvas = read_image(resolve_asset(snapshot["composite_ref"]))
        if canvas.size != (width, height):
            raise ValueError("合成底层尺寸不符，不能把低分辨率编辑结果放大充当母版")
        if params != PARAM_DEFAULTS:
            raise ValueError("整幅编辑结果不再具有独立图层，请继续使用内容编辑或替换素材重新排版")
        object_transforms = []
    else:
        if not snapshot.get("asset_refs"):
            raise ValueError("至少选择一个图案")
        if len(snapshot["asset_refs"]) > 12:
            raise ValueError("一次最多使用十二个图案")
        background = read_image(resolve_asset(snapshot["background_ref"]))
        # Repeated doubling preserves native pixels without millions of calls for tiny uploaded tiles.
        tile = background.crop((0, 0, min(width, background.width), min(height, background.height)))
        background.close()
        while tile.width < width:
            expanded = Image.new("RGBA", (min(width, tile.width*2), tile.height))
            expanded.paste(tile, (0, 0))
            expanded.paste(tile, (tile.width, 0))
            tile.close()
            tile = expanded
        while tile.height < height:
            expanded = Image.new("RGBA", (tile.width, min(height, tile.height*2)))
            expanded.paste(tile, (0, 0))
            expanded.paste(tile, (0, tile.height))
            tile.close()
            tile = expanded
        canvas = Image.new("RGBA", (width, height), "white")
        canvas.alpha_composite(tile)
        tile.close()
        if params["background_color"]:
            canvas.close()
            canvas = Image.new("RGBA", (width, height), ImageColor.getrgb(params["background_color"]))
        refs = snapshot['asset_refs']
        rules = snapshot.get("template_rules", {})
        mode = snapshot.get("template_mode", "stagger")
        object_transforms = []
        base_size = height * float(rules.get("motif_ratio", .27)) * float(params["scale"])
        if mode == "panels":
            d = ImageDraw.Draw(canvas, "RGBA")
            for x in (width//3, width*2//3):
                d.line((x, 0, x, height), fill=(64, 97, 78, 24), width=max(1, height//250))
        placements = [(x, y, max(1, min(int(base_size*factor), height*3)),
                       float(params['rotation']) + rotation, index % len(refs))
                      for x, y, factor, rotation, index in
                      _positions(mode, width, height, params, int(snapshot.get('seed', 0)), rules)]
        Path(master_path).parent.mkdir(parents=True, exist_ok=True)
        # Decode one full-size pattern at a time, not up to twelve together.
        # Lossless task-local intermediates preserve exact resize/rotate pixels;
        # final compositing still follows the original layer order and wrapping.
        with tempfile.TemporaryDirectory(prefix='ribbon-motifs-', dir=Path(master_path).parent) as staged:
            prepared = {}
            for index, ref in enumerate(refs):
                with closing(read_image(resolve_asset(ref))) as source:
                    for size, angle in dict.fromkeys((p[2], p[3]) for p in placements if p[4] == index):
                        ratio = size / max(source.size)
                        tw, th = max(1, round(source.width*ratio)), max(1, round(source.height*ratio))
                        radians = math.radians(angle)
                        bw = abs(tw*math.cos(radians)) + abs(th*math.sin(radians))
                        bh = abs(tw*math.sin(radians)) + abs(th*math.cos(radians))
                        if math.ceil(bw)*math.ceil(bh) > MAX_PIXELS:
                            raise ValueError('当前图案大小与旋转生成的中间图像过大，请减小图案或调整内部模板规则')
                        motif = source.resize((tw, th), Image.Resampling.LANCZOS)
                        if angle:
                            rotated = motif.rotate(-angle, resample=Image.Resampling.BICUBIC, expand=True)
                            motif.close()
                            motif = rotated
                        path = Path(staged) / f'{len(prepared)}.png'
                        try:
                            _save_png(motif, path)
                        finally:
                            motif.close()
                        prepared[index, size, angle] = path
            for layer, (x, y, size, angle, index) in enumerate(placements):
                with closing(read_image(prepared[index, size, angle])) as motif:
                    x += float(params['offset_x'])
                    y += float(params['offset_y'])
                    position = (round(x-motif.width/2), round(y-motif.height/2))
                    canvas.alpha_composite(motif, position)
                    if mode in ('grid', 'stagger', 'scatter', 'single'):
                        if position[0]+motif.width > width:
                            canvas.alpha_composite(motif, (position[0]-width, position[1]))
                        if position[0] < 0:
                            canvas.alpha_composite(motif, (position[0]+width, position[1]))
                    object_transforms.append({'asset_ref': refs[index], 'x': x, 'y': y,
                                              'size': size, 'rotation': angle, 'layer': layer})
    _save_png(canvas, Path(master_path), dpi)
    preview = canvas.copy()
    preview.thumbnail((1800, 600), Image.Resampling.LANCZOS)
    _save_png(preview, Path(preview_path), dpi)
    preview.close()
    canvas.close()
    metadata = validate_image(Path(master_path), snapshot["output_profile"])
    return {**metadata, "object_transforms": object_transforms,
            "render_kind": "composite" if snapshot.get("composite_ref") else "layered"}


def template_thumbnail(mode: str, path: Path, rules: dict | None = None) -> None:
    path = Path(path)
    assets_dir = path.parent / "thumbnail-assets"
    assets = seed_assets(assets_dir)
    refs = {row["id"]: Path(row["path"]) for row in assets}
    snapshot = {"asset_refs": ["demo-flower", "demo-star", "demo-ring"],
                "background_ref": "demo-bg-sage", "template_mode": mode, "template_rules": rules or {}, "seed": 42,
                "output_profile": {"width": 640, "height": 200, "dpi": 96, "format": "PNG", "is_demo": True}}
    # Thumbnail and master are the same dimensions; avoid retaining a second throwaway file.
    render(snapshot, refs.__getitem__, path, path)
