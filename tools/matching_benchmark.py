"""Read-only, reproducible end-to-end matching report for an explicit batch.

Example: python tools/matching_benchmark.py --workbook table.xlsx --source art.zip
 --out tmp/run_name --baseline tmp/v11_baseline/baseline.json
Reports and optional human-reference comparisons never influence the matcher.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from hsd_tool.matching import scan_and_match
from hsd_tool.workbook import inspect_workbook
from PIL import Image, ImageDraw


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workbook', required=True)
    parser.add_argument('--source', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--baseline')
    parser.add_argument('--reference', help='Optional manually labelled JSON, only used after matching')
    args = parser.parse_args()
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    if (out / 'results.json').exists():
        parser.error('This output already contains a result; choose a new output directory.')
    start = time.perf_counter()
    table = inspect_workbook(str(Path(args.workbook).resolve()), str(out / 'workbook'))
    result = scan_and_match(str(Path(args.source).resolve()), table['rows'], str(out),
        progress=lambda message, current, total: print(f'{current}/{total}', flush=True) if current % 10 == 0 else None)
    result['elapsed_seconds'] = round(time.perf_counter() - start, 3)
    result['counts'] = {s: sum(m['status'] == s for m in result['matches']) for s in ('auto', 'review', 'unmatched')}
    result['source_code_sha256'] = {name: hashlib.sha256((ROOT / 'hsd_tool' / name).read_bytes()).hexdigest()
                                     for name in ('matching.py', 'verification.py')}
    if args.reference:
        reference = json.loads(Path(args.reference).read_text(encoding='utf-8'))
        if 'row_to_ai_index' in reference:
            reference = {f'r{key}': f'f{value:04d}' for key, value in reference['row_to_ai_index'].items()}
        result['reference_deviations'] = [{'row_id': m['row_id'], 'expected': reference.get(m['row_id']),
            'candidate': m['candidates'][0]['file_id'] if m['candidates'] else None}
            for m in result['matches'] if reference.get(m['row_id']) and
            (not m['candidates'] or m['candidates'][0]['file_id'] != reference[m['row_id']])]
    if args.baseline:
        baseline = json.loads(Path(args.baseline).read_text(encoding='utf-8'))
        old_rows = {m['row_id']: m for m in baseline['matches']}
        changes = [{'row_id': m['row_id'], 'baseline_status': old_rows[m['row_id']]['status'],
                    'current_status': m['status'], 'reason_code': m.get('reason_code'),
                    'reason': m['reason'], 'diagnostics': m.get('diagnostics'),
                    'baseline_candidates': old_rows[m['row_id']]['candidates'], 'current_candidates': m['candidates']}
                   for m in result['matches'] if m['row_id'] in old_rows and old_rows[m['row_id']]['status'] != 'auto']
        (out / 'baseline_review_comparison.json').write_text(json.dumps(changes, ensure_ascii=False,
            indent=2, allow_nan=False), encoding='utf-8')
        result['baseline_counts'] = baseline.get('counts')
    (out / 'results.json').write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    rows = {r['id']: r for r in table['rows']}
    files = {f['id']: f for f in result['files']}
    for status in ('auto', 'review', 'unmatched'):
        selected = [m for m in result['matches'] if m['status'] == status and m['candidates']]
        for page in range(0, len(selected), 10):
            group = selected[page:page + 10]
            canvas = Image.new('RGB', (1500, len(group) * 180), '#edf2f7')
            draw = ImageDraw.Draw(canvas)
            for index, match in enumerate(group):
                identity = match['file_id'] or match['candidates'][0]['file_id']
                for x, path in [(10, rows[match['row_id']]['image_path']), (760, files[identity]['preview_path'])]:
                    image = Image.open(path).convert('RGB')
                    image.thumbnail((730, 140))
                    canvas.paste(image, (x, index * 180 + (140 - image.height) // 2))
                draw.text((12, index * 180 + 147), f"{match['row_id']} | {status} | workbook", fill='black')
                draw.text((760, index * 180 + 147), f"{identity} | {match.get('reason_code', '')}", fill='black')
            canvas.save(out / f'{status}_{page // 10 + 1}.jpg', quality=94)
    print(json.dumps({key: result[key] for key in ('counts', 'elapsed_seconds', 'reference_deviations') if key in result}, ensure_ascii=False))


if __name__ == '__main__':
    main()
