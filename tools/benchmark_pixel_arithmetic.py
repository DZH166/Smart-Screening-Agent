"""Pure arithmetic microbenchmark of guarded uint8/RGB fast paths.

Uses one fixed synthetic frame pair. No images/files, artwork labels, matching
decisions, workbook, API or complete-batch timings are involved. The reference
is the previous float32 subtraction/absolute/division and channel reduction.
Every result is retained; three old/new runs and their medians are required.
"""
from __future__ import annotations

import argparse
import hashlib
import inspect
import json
from pathlib import Path
import platform
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

import cv2
import numpy as np

from hsd_tool import matching_verification as current


def original_error(first, second, mask=None):
    if mask is not None:
        first, second = first[mask],second[mask]
    error = np.subtract(first,second,dtype=np.float32)
    np.abs(error,out=error)
    error /= 255
    return error


def original_channel_max(error):
    return error.max(axis=-1)


def original_metrics_and_pixels(first, second):
    error = original_error(first,second)
    pixels = error.max(axis=-1)
    return {'mae':float(error.mean()),'rms':float(np.sqrt(np.mean(error ** 2))),
            'changed':float((pixels > .2).mean()),'major_changed':float((pixels > .45).mean())},pixels


def measure(function, arguments, iterations):
    started = time.perf_counter()
    for _ in range(iterations):
        result = function(*arguments)
    elapsed = time.perf_counter() - started
    # Keep the result live until the timer ends. NumPy/OpenCV are eager, and no
    # sum or extra correctness comparison is included in measured arithmetic.
    shape = list(result[-1].shape if isinstance(result,tuple) else result.shape)
    return {'seconds':elapsed,'seconds_per_call':elapsed/iterations,
            'iterations':iterations,'result_shape':shape}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',required=True,type=Path)
    parser.add_argument('--repeats',type=int,default=3)
    parser.add_argument('--iterations',type=int,default=30)
    parser.add_argument('--opencv-threads',type=int,default=16)
    args = parser.parse_args()
    if args.repeats < 3: parser.error('At least three repeats are required.')
    if args.iterations < 1: parser.error('At least one iteration is required.')
    if not 1 <= args.opencv_threads <= 32: parser.error('OpenCV threads must be between 1 and 32.')
    destination = args.out.resolve()
    if destination.exists(): parser.error('Choose a new output file to preserve every measurement.')
    destination.parent.mkdir(parents=True,exist_ok=True)
    cv2.setNumThreads(args.opencv_threads)
    source_file = Path(current.__file__).resolve()
    source_before = hashlib.sha256(source_file.read_bytes()).hexdigest()
    rng = np.random.default_rng(258931)
    first = rng.integers(0,256,(256,1536,3),dtype=np.uint8)
    second = rng.integers(0,256,first.shape,dtype=np.uint8)
    error = original_error(first,second)
    stages = {'pixel_error':((original_error,current._pixel_error),(first,second)),
              'rgb_max':((original_channel_max,current._channel_max),(error,)),
              'metrics_and_pixels':((original_metrics_and_pixels,current._metrics_and_pixels),(first,second))}
    checks = {}
    for name, ((reference,optimized), arguments) in stages.items():
        expected,actual = reference(*arguments),optimized(*arguments)
        if isinstance(expected,tuple):
            checks[name] = expected[0] == actual[0] and np.array_equal(expected[1],actual[1])
        else:
            checks[name] = expected.dtype == actual.dtype and expected.shape == actual.shape and np.array_equal(
                expected.view(np.uint32),actual.view(np.uint32))
    runs = []
    for repeat in range(1,args.repeats+1):
        for name, ((reference,optimized), arguments) in stages.items():
            order = [('reference',reference),('current',optimized)]
            if repeat % 2 == 0: order.reverse()
            for label,function in order:
                runs.append({'repeat':repeat,'stage':name,'implementation':label,
                             **measure(function,arguments,args.iterations)})
    source_after = hashlib.sha256(source_file.read_bytes()).hexdigest()
    report = {'scope':'pure arithmetic synthetic microbenchmark; no batch speed or accuracy claim',
              'python':platform.python_version(),'numpy':np.__version__,'opencv':cv2.__version__,
              'opencv_threads':cv2.getNumThreads(),'shape':list(first.shape),
              'input_sha256':{'first':hashlib.sha256(first.tobytes()).hexdigest(),
                              'second':hashlib.sha256(second.tobytes()).hexdigest()},
              'source_before_sha256':source_before,'source_after_sha256':source_after,
              'reference_source_sha256':hashlib.sha256((inspect.getsource(original_error)+
                   inspect.getsource(original_channel_max)+inspect.getsource(original_metrics_and_pixels)).encode()).hexdigest(),
              'checks':checks,'source_unchanged':source_before == source_after,'runs':runs,
              'medians_seconds_per_call':{name:{label:statistics.median(run['seconds_per_call'] for run in runs
                   if run['stage']==name and run['implementation']==label) for label in ('reference','current')}
                   for name in stages},
              'limitations':['One fixed in-memory uint8 frame pair; no source reading, cache or matching benchmark.',
                             'One untimed correctness/warmup call per implementation; OS cache is irrelevant to these in-memory arrays.',
                             'Alternating old/new measurement order; same process and stable OpenCV setting.',
                             'NaN, broadcasting, mixed dtypes, masks and empty-channel fallback correctness belongs to the separate unit controls.']}
    report['all_checks_passed'] = all(checks.values()) and report['source_unchanged']
    with destination.open('x',encoding='utf-8') as stream:
        json.dump(report,stream,ensure_ascii=False,indent=2,allow_nan=False)
    print(json.dumps({'all_checks_passed':report['all_checks_passed'],
                      'medians_seconds_per_call':report['medians_seconds_per_call']},ensure_ascii=False))
    return 0 if report['all_checks_passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
