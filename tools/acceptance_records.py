"""Read private export evidence during explicit local acceptance only.

Never expose this helper through the employee HTTP API. The caller supplies the
isolated data directory of the test instance; user settings are not searched.
"""
import json
from pathlib import Path
import re


def read_export_record(data_dir, identifier):
    assert re.fullmatch(r'[0-9a-f]{32}', identifier), 'Invalid test job ID'
    root = (Path(data_dir) / 'task_records' / identifier / 'export_records').resolve(strict=True)
    candidates = sorted(root.glob('*/处理记录.json'))
    assert len(candidates) == 1, 'Expected exactly one export attempt in this acceptance'
    record = candidates[0]
    assert record.resolve().is_relative_to(root) and not record.is_symlink()
    assert {p.name for p in record.parent.iterdir()} == {'处理记录.json', '对应关系.csv', '待处理清单.csv'}
    for name in ('对应关系.csv', '待处理清单.csv'):
        assert (record.parent / name).read_text('utf-8-sig'), 'Private CSV evidence was not retained'
    return json.loads(record.read_text('utf-8'))
