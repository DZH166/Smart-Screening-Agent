"""Function-level synthetic texture-cache experiment; never a business benchmark.

Example: python tools/benchmark_texture_cache.py --out tmp/v180/texture-cache.json
Runs each scenario at least three times, retaining every measurement. Scratch
data is reused only inside each trial, never across jobs or employees. No input
files, AI API, source-file integrity checks or export timings are involved.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import platform
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import cv2
import numpy as np

from hsd_tool import matching
from hsd_tool import matching_verification as verification


class ObservedCache(matching._TextureCache):
    def __init__(self):
        super().__init__()
        self.lookups = Counter()
        self.factories = Counter()

    def get(self, token, factory):
        category = token[0]
        self.lookups[category] += 1
        def measured():
            self.factories[category] += 1
            return factory()
        return super().get(token, measured)

    def snapshot(self):
        return {'entries':len(self._items), 'accounted_bytes':self.bytes,
                'max_accounted_bytes':self.max_bytes, 'max_entries':self.max_entries,
                'lookups':dict(self.lookups), 'factories':dict(self.factories)}


def synthetic_pattern():
    motif = np.full((96, 96, 3), 245, np.uint8)
    cv2.rectangle(motif, (3, 8), (14, 86), (25, 95, 190), -1)
    cv2.circle(motif, (44, 29), 14, (160, 55, 20), -1)
    cv2.circle(motif, (71, 67), 18, (40, 150, 65), -1)
    cv2.line(motif, (24, 92), (88, 6), (75, 30, 100), 3)
    return np.tile(motif, (1, 6, 1))


def counters_delta(after, before):
    return {category:{key:int(after[category].get(key, 0) - before[category].get(key, 0))
                      for key in sorted(set(after[category]) | set(before[category]))}
            for category in ('lookups','factories')}


def evaluate_pair(query, candidate, cache):
    before = cache.snapshot()
    periods_before = verification._periods_cached.cache_info()._asdict()
    started = time.perf_counter()
    coarse = matching._texture(query, candidate, precision=False, cache=cache)
    coarse_seconds = time.perf_counter() - started
    started = time.perf_counter()
    precise = matching._texture(query, candidate, precision=True, cache=cache)
    precise_seconds = time.perf_counter() - started
    after = cache.snapshot()
    return {'coarse_seconds':coarse_seconds, 'precision_seconds':precise_seconds,
            'elapsed_seconds':coarse_seconds + precise_seconds,
            'coarse_result':coarse, 'precision_result':precise,
            'cache_before':before, 'cache_after':after,
            'counter_delta':counters_delta(after,before),
            'query_period_cache_before':periods_before,
            'query_period_cache_after':verification._periods_cached.cache_info()._asdict()}


def run_trial(index):
    verification._periods_cached.cache_clear()
    detector = cv2.SIFT_create(nfeatures=1600, contrastThreshold=.025)
    pixels = synthetic_pattern()
    query = matching._appearance(pixels.copy(), detector)
    candidate = matching._appearance(pixels.copy(), detector)
    cache = ObservedCache()
    fresh = evaluate_pair(query,candidate,cache)
    repeated = evaluate_pair(query,candidate,cache)

    # Alter real RGB pixels, then rebuild appearance and its content digest.
    # Neither the old digest nor a filename can nominate the cached old result.
    altered = candidate.image.copy()
    altered[15:80, 210:285] = (15, 15, 200)
    prepared_at = time.perf_counter()
    changed_candidate = matching._appearance(altered,detector)
    rebuild_seconds = time.perf_counter() - prepared_at
    changed = evaluate_pair(query,changed_candidate,cache)
    changed['appearance_rebuild_seconds'] = rebuild_seconds
    changed['elapsed_including_rebuild_seconds'] = changed['elapsed_seconds'] + rebuild_seconds

    same = fresh['coarse_result'] == repeated['coarse_result'] and fresh['precision_result'] == repeated['precision_result']
    new_digest = candidate.digest != changed_candidate.digest
    new_search = changed['counter_delta']['factories'].get('coarse',0) > 0
    rejected = not changed['precision_result'].get('strong',False)
    return {'trial':index, 'synthetic':True, 'scope':'one matching-call scratch cache',
            'pixel_shape':list(pixels.shape), 'original_digest':candidate.digest,
            'changed_digest':changed_candidate.digest,
            'fresh_coarse_and_precision':fresh, 'same_pair_repeated':repeated,
            'changed_pixels_reprepared':changed,
            'checks':{'repeat_results_identical':same,'actual_pixel_digest_changed':new_digest,
                      'changed_pair_rebuilt_coarse_search':new_search,
                      'known_synthetic_change_not_strong':rejected}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',required=True,help='New local JSON result file; never commit it')
    parser.add_argument('--repeats',type=int,default=3)
    parser.add_argument('--opencv-threads',type=int,default=16,
                        help='Stable process-start setting, never changed during a job')
    args = parser.parse_args()
    if args.repeats < 3: parser.error('At least three trials are required.')
    if not 1 <= args.opencv_threads <= 32: parser.error('OpenCV thread count must be between 1 and 32.')
    destination = Path(args.out).resolve()
    if destination.exists(): parser.error('Output exists; choose a new file so every result is preserved.')
    destination.parent.mkdir(parents=True,exist_ok=True)
    cv2.setNumThreads(args.opencv_threads)
    runs = [run_trial(index) for index in range(1,args.repeats + 1)]
    stages = ('fresh_coarse_and_precision','same_pair_repeated','changed_pixels_reprepared')
    report = {'experiment':'synthetic-function-level-texture-cache',
              'python':platform.python_version(),'numpy':np.__version__,'opencv':cv2.__version__,
              'opencv_threads':cv2.getNumThreads(),'cache_version':matching._TextureCache.VERSION,
              'source_sha256':{name:hashlib.sha256((ROOT/'hsd_tool'/name).read_bytes()).hexdigest()
                               for name in ('matching.py','matching_verification.py')},
              'runs':runs, 'medians':{stage:{'elapsed_seconds':statistics.median(run[stage]['elapsed_seconds'] for run in runs),
                                           'cache_entries_after':statistics.median(run[stage]['cache_after']['entries'] for run in runs),
                                           'cache_accounted_bytes_after':statistics.median(run[stage]['cache_after']['accounted_bytes'] for run in runs)}
                                        for stage in stages},
              'limitations':['Synthetic function-level controls; not a full batch, employee throughput, or business accuracy estimate.',
                             'No persistent cross-batch cache. Each trial starts new scratch and clears the existing query-period LRU.',
                             'Same-pair repetition intentionally retains scratch and query-period data within that trial.',
                             'Scratch byte accounting includes ndarray payload plus bounded metadata estimates, not total Python process memory.',
                             'No workbook, source files, PyMuPDF, upload, AI request, export, packaging or download is timed.']}
    report['all_checks_passed'] = all(all(run['checks'].values()) for run in runs)
    with destination.open('x',encoding='utf-8') as stream:
        json.dump(report,stream,ensure_ascii=False,indent=2,allow_nan=False)
    print(json.dumps({'result':str(destination),'medians':report['medians'],
                      'all_checks_passed':report['all_checks_passed']},ensure_ascii=False))
    return 0 if report['all_checks_passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
