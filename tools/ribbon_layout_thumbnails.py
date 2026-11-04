"""Rebuild public mode previews from bounded, private-data-free demo assets."""

from pathlib import Path
from tempfile import TemporaryDirectory
import sys

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ribbon_backend import imaging, loop_layout_v2, loop_pipeline_v2


def main():
    destination = ROOT / 'ribbon_frontend/public/layout-v2'
    destination.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix='ribbon-thumbnails-') as tmp:
        work = Path(tmp)
        assets = {x['id']: x['path'] for x in imaging.seed_assets(work)}
        # A single complete emblem illustrates the full-panel mode more clearly
        # than one isolated motif. Only generated demo shapes are used.
        with Image.new('RGBA', (640, 180)) as emblem:
            ImageDraw.Draw(emblem).rounded_rectangle(
                (3, 3, 636, 177), radius=70, fill='#F7E3C1', outline='#CEAE73', width=5
            )
            for i, key in enumerate(('leaf', 'star', 'flower', 'star', 'leaf')):
                with Image.open(assets['demo-' + key]) as source:
                    size = 145 if i == 2 else 95
                    with source.resize((size, size), Image.Resampling.LANCZOS) as fitted:
                        emblem.alpha_composite(fitted, (24 + 115 * i, (180 - size) // 2))
            assets['demo-emblem'] = work / 'emblem.png'
            emblem.save(assets['demo-emblem'])
        with Image.new('RGB', (640, 240), '#E8F1E2') as scene:
            drawing = ImageDraw.Draw(scene)
            drawing.polygon(
                [(0, 196), (150, 134), (331, 194), (465, 149), (640, 196), (640, 240), (0, 240)],
                fill='#CADCBF',
            )
            drawing.rectangle((0, 207, 640, 240), fill='#B6CFB4')
            assets['demo-scene'] = work / 'scene.png'
            scene.save(assets['demo-scene'])
        for mode in loop_layout_v2.MODES:
            motifs = ['demo-leaf', 'demo-star', 'demo-flower']
            if mode in ('ends_open', 'stacked', 'bordered'):
                motifs = motifs[:2]
            if mode == 'fullwidth':
                motifs = ['demo-emblem']
            if mode == 'split':
                motifs = ['demo-leaf', 'demo-ring', 'demo-star', 'demo-flower']
            zones = loop_layout_v2.ZONE_IDS.get(mode, ())
            s = dict(
                layout_engine=loop_layout_v2.ENGINE,
                template_mode=mode,
                asset_refs=motifs,
                background_ref='demo-scene' if mode == 'scene' else 'demo-bg-sage',
                zone_background_refs=dict(zip(zones, ['demo-bg-rose', 'demo-bg-blue', 'demo-bg-cream'])),
                template_rules={},
                seed=32,
                design_density='balanced',
                params={},
                output_profile=dict(width=256, height=256, dpi=300, format='PNG'),
            )
            resolved = loop_pipeline_v2.resolve(s, assets.__getitem__)
            output = work / 'unit.png'
            imaging.render(resolved, assets.__getitem__, output, work / 'preview.png')
            with Image.open(output) as unit, Image.new('RGB', (420, 132), '#F4F6EF') as tile:
                if resolved['loop_layout']['kind'] == 'panel':
                    unit.thumbnail(tile.size, Image.Resampling.LANCZOS)
                    tile.paste(unit, ((tile.width - unit.width) // 2, (tile.height - unit.height) // 2))
                else:
                    with unit.resize(
                        (round(unit.width * tile.height / unit.height), tile.height), Image.Resampling.LANCZOS
                    ) as repeat:
                        for x in range(0, tile.width, repeat.width):
                            tile.paste(repeat, (x, 0))
                tile.save(destination / (mode + '.webp'), quality=90, method=6)


if __name__ == '__main__':
    main()
