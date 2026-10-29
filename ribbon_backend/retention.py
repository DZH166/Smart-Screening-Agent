"""Conservative, single-process private-data retention and response leases.

Registry entries are shared by Service instances using the same database. A lease
protects the owner's work until the response is closed, even across threads. No
lock is held across a lease's yield. Unknown legacy ages are never guessed.

Expired-request tombstones deliberately have no time-based deletion: owner ID,
idempotency key and request hash remain to prevent a delayed POST from charging
again after its images and result were removed. They contain no image, prompt or
credential, but their row count grows with lifetime requests. Future archival must
preserve this uniqueness check rather than silently expiring retry protection.
"""
from __future__ import annotations

import json
import re
import shutil
import threading
import time
from collections import Counter
from pathlib import Path

from hsd_tool.retention_window import RETENTION_SECONDS


class LeaseRegistry:
    def __init__(self):
        self.lock = threading.RLock()
        self.owners = Counter()


_registries = {}
_registry_lock = threading.Lock()


def registry_for(root):
    key = str(Path(root).resolve())
    with _registry_lock:
        return _registries.setdefault(key, LeaseRegistry())


def _references(snapshot):
    return {str(x) for x in snapshot.get('asset_refs', [])} | {
        str(snapshot[k]) for k in ('background_ref', 'composite_ref') if snapshot.get(k)
    }


def _safe_path(root, path):
    """Refuse symlinks and outside-root paths, including ancestor links."""
    raw = Path(path).absolute()
    try:
        relative = raw.relative_to(root)
    except ValueError:
        return False
    if not relative.parts:
        return False
    if relative.parts[0] not in ('assets', 'jobs') or any(part in ('.', '..') for part in relative.parts):
        return False
    if len(relative.parts) < 2 or (relative.parts[0] == 'jobs' and not re.fullmatch(r'[0-9a-f]{32}', relative.parts[1])):
        return False
    node = root
    for component in relative.parts:
        node /= component
        if node.is_symlink():
            return False
    return raw.resolve() != root and raw.resolve().is_relative_to(root)


def _drain_removals(service):
    """A committed deletion remains retryable after a crash or an OS file lock."""
    failures = 0
    root = service.root.resolve()
    with service.db.connect() as db:
        pending = db.execute('SELECT * FROM cleanup_paths ORDER BY is_directory').fetchall()
    for row in pending:
        path = Path(row['path'])
        if not _safe_path(root, path) or (row['is_directory'] and path.exists() and any(p.is_symlink() for p in path.rglob('*'))):
            failures += 1
            continue
        try:
            if row['is_directory']:
                if path.exists():
                    shutil.rmtree(path)
            else:
                path.unlink(missing_ok=True)
        except OSError:
            failures += 1
            continue
        with service.db.transaction() as db:
            db.execute('DELETE FROM cleanup_paths WHERE path=?', (row['path'],))
    return failures


def cleanup(service, *, now=None):
    """Remove expired terminal private work; never shared/config/auth resources.

    A busy owner is retained wholesale. This also protects uploads selected by a
    queued job before they have become part of a version snapshot. Files are
    removed only from the service's own root and from positively identified job
    directories. Filesystem failures may retain extra bytes, never another task.
    """
    current = time.time() if now is None else float(now)
    # Ages are kept as timestamps, so the current shared policy also tightens
    # work created under the earlier 72-hour retention window.
    cutoff = current - getattr(service.settings, 'retention_seconds', RETENTION_SECONDS)
    counts = dict(designs=0, versions=0, assets=0, jobs=0, files_failed=0)
    root = service.root.resolve()
    leases = service._leases
    with leases.lock:
        with service.db.connect() as db:
            owners = [r[0] for r in db.execute('SELECT DISTINCT owner_id FROM designs UNION SELECT DISTINCT owner_id FROM assets WHERE owner_id IS NOT NULL UNION SELECT DISTINCT owner_id FROM jobs')]
        for owner in owners:
            if leases.owners[owner]:
                continue
            removal_paths = set()
            job_dirs = set()
            with service.db.transaction() as db:
                jobs = [dict(r) for r in db.execute('SELECT * FROM jobs WHERE owner_id=?', (owner,))]
                if any(j['status'] not in ('SUCCEEDED', 'FAILED') for j in jobs):
                    continue
                designs = [dict(r) for r in db.execute('SELECT * FROM designs WHERE owner_id=?', (owner,))]
                assets = {r['id']: dict(r) for r in db.execute('SELECT * FROM assets WHERE owner_id=? AND shared=0', (owner,))}
                versions = [dict(r) for r in db.execute('SELECT v.* FROM versions v JOIN designs d ON d.id=v.design_id WHERE d.owner_id=?', (owner,))]
                try:
                    references = {v['id']: _references(json.loads(v['snapshot_json'])) for v in versions}
                except (ValueError, TypeError, AttributeError):
                    continue  # Cannot establish safe ownership of referenced files.
                expired = set()
                for design in designs:
                    related = [j for j in jobs if j['design_id'] == design['id']]
                    if design['active_job_id'] or design['retained_at'] is None or any(j['settled_at'] is None for j in related):
                        continue
                    last = max([design['retained_at']] + [j['settled_at'] for j in related])
                    if last <= cutoff:
                        expired.add(design['id'])
                # A newer work may reuse a generated asset from an older work.
                # Keep that source work and all its immutable provenance together.
                while True:
                    live_refs = set().union(*(references[v['id']] for v in versions if v['design_id'] not in expired)) if versions else set()
                    pending = list(live_refs)
                    while pending:
                        asset = assets.get(pending.pop())
                        parent = asset.get('derived_from') if asset else None
                        if parent and parent not in live_refs:
                            live_refs.add(parent)
                            pending.append(parent)
                    keep = set()
                    for job in jobs:
                        if job['design_id'] in expired:
                            directory = root / 'jobs' / job['id']
                            if any(Path(assets[a]['path']).is_relative_to(directory) for a in live_refs if a in assets):
                                keep.add(job['design_id'])
                    if not keep:
                        break
                    expired -= keep
                delete_assets = {a for a, row in assets.items() if a not in live_refs and row['retained_at'] is not None and row['retained_at'] <= cutoff}
                delete_jobs = {j['id'] for j in jobs if j['design_id'] in expired or (
                    j['design_id'] is None and j['settled_at'] is not None and j['settled_at'] <= cutoff
                    and not any(Path(a['path']).is_relative_to(root / 'jobs' / j['id']) for aid, a in assets.items() if aid not in delete_assets)
                )}
                # Never remove a job directory while any retained asset points in it.
                delete_jobs = {jid for jid in delete_jobs if not any(Path(a['path']).is_relative_to(root / 'jobs' / jid) for aid, a in assets.items() if aid not in delete_assets)}
                blocked_designs = {j['design_id'] for j in jobs if j['design_id'] in expired and j['id'] not in delete_jobs}
                if blocked_designs:
                    continue  # Conservative; a later pass can reclaim this owner.
                deleted_versions = [v for v in versions if v['design_id'] in expired]
                for v in deleted_versions:
                    removal_paths.update((Path(v['master_path']), Path(v['preview_path'])))
                removal_paths.update(Path(assets[a]['path']) for a in delete_assets)
                job_dirs = {root / 'jobs' / jid for jid in delete_jobs}
                # Any unexpected path or symlink makes the whole owner ineligible.
                all_paths = removal_paths | job_dirs
                if any(not _safe_path(root, p) for p in all_paths):
                    continue
                if any(p.is_symlink() for directory in job_dirs if directory.exists() for p in directory.rglob('*')):
                    continue
                for path in removal_paths:
                    db.execute('INSERT OR IGNORE INTO cleanup_paths VALUES(?,0)', (str(path),))
                for path in job_dirs:
                    db.execute('INSERT OR IGNORE INTO cleanup_paths VALUES(?,1)', (str(path),))
                for asset_id in delete_assets:
                    db.execute('DELETE FROM assets WHERE id=? AND shared=0', (asset_id,))
                for did in expired:
                    db.execute('DELETE FROM quota_events WHERE design_id=?', (did,))
                    db.execute('DELETE FROM versions WHERE design_id=?', (did,))
                for jid in delete_jobs:
                    db.execute('INSERT OR IGNORE INTO expired_requests SELECT owner_id,idempotency_key,request_hash FROM jobs WHERE id=?', (jid,))
                    db.execute('DELETE FROM provider_calls WHERE job_id=?', (jid,))
                    db.execute('DELETE FROM outbox_events WHERE job_id=?', (jid,))
                    db.execute('DELETE FROM jobs WHERE id=?', (jid,))
                for did in expired:
                    db.execute('DELETE FROM designs WHERE id=?', (did,))
                counts['designs'] += len(expired)
                counts['versions'] += len(deleted_versions)
                counts['assets'] += len(delete_assets)
                counts['jobs'] += len(delete_jobs)
        counts['files_failed'] = _drain_removals(service)
    return counts
