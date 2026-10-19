"""Sequential, repeatable stage timings against an explicit source checkout.

Only explicit XLSX/ZIP inputs are read. Results, previews and diagnostics belong
in an ignored local directory. No reference answers or credentials are loaded.
Each session is a new Python process, followed by a second pass in that process;
this distinguishes fresh application caches from repeat use, not OS cold disks.
"""
from __future__ import annotations

import argparse
from collections import Counter
from functools import wraps
import hashlib
import json
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import threading
import time


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def child(args):
    sys.path.insert(0, str(Path(args.source_root).resolve()))
    import cv2
    import hsd_tool.matching as matching
    import hsd_tool.matching_verification as verification
    from hsd_tool.workbook import inspect_workbook
    import hsd_tool.workbook as workbook_module
    root = Path(args.source_root).resolve()
    module_files = {module.__name__: Path(module.__file__).resolve()
                    for module in (matching, verification, workbook_module)}
    assert all(path.is_relative_to(root) for path in module_files.values()), 'Source isolation failed'
    implementation_before = {name: digest(path) for name, path in module_files.items()}
    if args.opencv_threads is not None:
        cv2.setNumThreads(args.opencv_threads)

    lock = threading.Lock()
    counters = {}

    def instrument(module, name, label):
        original = getattr(module, name)
        @wraps(original)
        def measured(*values, **options):
            started = time.perf_counter()
            try:
                return original(*values, **options)
            finally:
                elapsed = time.perf_counter() - started
                with lock:
                    item = counters.setdefault(label, {'calls': 0, 'seconds': 0.0})
                    item['calls'] += 1
                    item['seconds'] += elapsed
        setattr(module, name, measured)
        # matching imports verification functions directly; instrument both aliases.
        if module is verification and getattr(matching, name, None) is original:
            setattr(matching, name, measured)

    for name, label in [('_collect', 'unpack'), ('_render', 'render'),
            ('_appearance', 'appearance'), ('_match_appearances', 'compare'),
            ('_features', 'features'), ('_texture', 'texture_total'),
            ('_texture_search', 'texture_coarse'), ('_texture_scan', 'texture_scan')]:
        instrument(matching, name, label)
    for name in ('pixel_metrics', 'phase_coverage', 'periodic_extension', 'affine_coverage'):
        instrument(verification, name, name)

    directory = Path(args.out).resolve()
    directory.mkdir(parents=True, exist_ok=False)
    (directory / 'environment.json').write_text(json.dumps({
        'source_root': str(root), 'module_sha256': implementation_before,
        'harness_sha256': digest(Path(__file__)), 'opencv': cv2.__version__,
        'opencv_threads': cv2.getNumThreads(), 'passes': args.passes}, indent=2), 'utf-8')
    results = []
    for pass_index in range(args.passes):
        counters.clear()
        work = directory / ('pass-' + str(pass_index))
        work.mkdir()
        started = time.perf_counter()
        table = inspect_workbook(str(Path(args.workbook).resolve()), str(work / 'workbook'))
        read_seconds = time.perf_counter() - started
        def progress(message, current, total):
            if current in {0, 1, total} or current % 15 == 0:
                print(f'session={args.session} pass={pass_index} {current}/{total} {message}', flush=True)
        options = {} if args.texture_workers is None else {'texture_workers': args.texture_workers}
        value = matching.scan_and_match(str(Path(args.source).resolve()), table['rows'], str(work), progress, **options)
        elapsed = time.perf_counter() - started
        value.update(counts=dict(Counter(row['status'] for row in value['matches'])),
                     elapsed_seconds=elapsed, read_seconds=read_seconds,
                     stage_cumulative_seconds={key: dict(item) for key, item in counters.items()},
                     session=args.session, pass_index=pass_index,
                     application_cache='fresh_process' if pass_index == 0 else 'same_process_repeat',
                     opencv_threads=cv2.getNumThreads(), texture_workers=args.texture_workers)
        (work / 'results.json').write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2), 'utf-8')
        summary = {key: value[key] for key in ('counts', 'elapsed_seconds', 'read_seconds',
                    'stage_cumulative_seconds', 'session', 'pass_index', 'application_cache', 'opencv_threads', 'texture_workers')}
        results.append(summary)
        print(json.dumps(summary, ensure_ascii=False), flush=True)
    (directory / 'session.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), 'utf-8')
    assert implementation_before == {name: digest(path) for name, path in module_files.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', required=True)
    parser.add_argument('--workbook', required=True)
    parser.add_argument('--source', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--sessions', type=int, default=3)
    parser.add_argument('--passes', type=int, default=2)
    parser.add_argument('--child', action='store_true')
    parser.add_argument('--session', type=int, default=0)
    parser.add_argument('--texture-workers', type=int, choices=(1, 2))
    parser.add_argument('--opencv-threads', type=int, choices=(1, 2, 4, 8, 16))
    args = parser.parse_args()
    if args.child:
        child(args)
        return
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    initial = {'workbook_sha256': digest(args.workbook), 'source_sha256': digest(args.source),
               'sessions': args.sessions, 'passes': args.passes,
               'python': sys.version, 'platform': platform.platform(),
               'source_code_sha256': {name: digest(Path(args.source_root) / 'hsd_tool' / name)
                   for name in ('matching.py', 'matching_verification.py')},
               'measurement': 'same harness, no cProfile; sequential new processes with repeated pass; OS cache not flushed',
               'ai': 'disabled (matcher only)', 'nested_stage_warning':
                   'hotspot cumulative times overlap parent phases; parallel cumulative times are not wall time'}
    (out / 'input_manifest.json').write_text(json.dumps(initial, ensure_ascii=False, indent=2), 'utf-8')
    all_results = []
    for session in range(args.sessions):
        target = out / ('session-' + str(session))
        command = [sys.executable, str(Path(__file__).resolve()), '--child', '--source-root', args.source_root,
                   '--workbook', args.workbook, '--source', args.source, '--out', str(target),
                   '--passes', str(args.passes), '--session', str(session)]
        if args.texture_workers is not None:
            command += ['--texture-workers', str(args.texture_workers)]
        if args.opencv_threads is not None:
            command += ['--opencv-threads', str(args.opencv_threads)]
        subprocess.run(command, check=True)
        all_results.extend(json.loads((target / 'session.json').read_text('utf-8')))
    assert initial['workbook_sha256'] == digest(args.workbook)
    assert initial['source_sha256'] == digest(args.source)
    report = {**initial, 'runs': all_results, 'medians_seconds': {
        kind: statistics.median(item['elapsed_seconds'] for item in all_results if item['application_cache'] == kind)
        for kind in {item['application_cache'] for item in all_results}}}
    (out / 'summary.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), 'utf-8')
    print(json.dumps({'medians_seconds': report['medians_seconds']}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
