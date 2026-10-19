"""Check complete match decisions/evidence from local sequential timing runs.

This is a regression comparison, not independent visual business validation.
Never used by the production matcher. Paths, images and results stay local.
"""
import argparse
import json
import math
from pathlib import Path


def differences(first, second, path='', *, tolerance=1e-7):
    if type(first) is float and type(second) in (float, int):
        if not math.isclose(first, second, abs_tol=tolerance, rel_tol=tolerance):
            return [{'path': path, 'before': first, 'after': second}]
        return []
    if type(first) is not type(second):
        return [{'path': path, 'kind': 'type'}]
    if isinstance(first, dict):
        result = []
        if set(first) != set(second):
            result.append({'path': path, 'kind': 'keys', 'before': sorted(first), 'after': sorted(second)})
        for key in sorted(set(first) & set(second)):
            result.extend(differences(first[key], second[key], path+'/'+str(key), tolerance=tolerance))
        return result
    if isinstance(first, list):
        if len(first) != len(second):
            return [{'path': path, 'kind': 'length'}]
        return [item for index, (a, b) in enumerate(zip(first, second))
                for item in differences(a, b, path+'/'+str(index), tolerance=tolerance)]
    return [] if first == second else [{'path': path, 'before': first, 'after': second}]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--current', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--sessions', type=int, default=3)
    parser.add_argument('--baseline-passes', type=int, default=2)
    parser.add_argument('--current-passes', type=int, default=2)
    args = parser.parse_args()
    baseline_files = sorted(args.baseline.glob('session-*/pass-*/results.json'))
    current_files = sorted(args.current.glob('session-*/pass-*/results.json'))
    for root, paths, passes in ((args.baseline, baseline_files, args.baseline_passes),
                               (args.current, current_files, args.current_passes)):
        expected = {(session, iteration) for session in range(args.sessions) for iteration in range(passes)}
        actual = {(int(path.parent.parent.name.split('-')[1]), int(path.parent.name.split('-')[1])) for path in paths}
        assert actual == expected and len(paths) == len(expected), 'Missing/extra benchmark repetitions'
    manifests = [json.loads((root/'input_manifest.json').read_text('utf-8')) for root in (args.baseline, args.current)]
    assert all(manifests[0][name] == manifests[1][name] for name in ('workbook_sha256', 'source_sha256')), 'Different business inputs'
    first_value = json.loads(baseline_files[0].read_text('utf-8'))
    baseline = first_value['matches']
    fields = ('id', 'name', 'relative_path', 'source_sha256', 'page_count', 'issue')
    file_binding = [{key: item.get(key) for key in fields} for item in first_value['files']]
    checks = []
    for path in baseline_files + current_files:
        value = json.loads(path.read_text('utf-8'))
        changes = differences(baseline, value['matches'])
        changes += differences(file_binding, [{key: item.get(key) for key in fields} for item in value['files']], '/files')
        checks.append({'result': str(path), 'counts': value['counts'], 'differences': changes})
    report = {'scope': 'Full candidate/order/ownership/status/reason/evidence regression; floats 1e-7 abs/rel tolerance; no accuracy claim',
              'ok': all(not item['differences'] for item in checks), 'checks': checks}
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), 'utf-8')
    print(json.dumps({'ok': report['ok'], 'runs': len(checks),
                      'changed_runs': sum(bool(item['differences']) for item in checks)}))
    if not report['ok']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
