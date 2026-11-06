"""Durable single-host job service. Files precede a fenced, atomic version commit."""
from __future__ import annotations

import base64
import copy
import hashlib
import hmac
import io
import json
import logging
import math
import os
import re
import secrets
import shutil
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from functools import wraps
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageOps

from hsd_tool.provider_diagnostics import call_view, diagnostic

from .config import Settings
from .db import Database
from .imaging import memory_bounded_operation, disk_space_guard, png_space, estimate_render_space, STANDALONE_FREE_MARGIN, MAX_PIXELS, PARAM_DEFAULTS, _save_png

log = logging.getLogger(__name__)
MODES = {'grid': '整齐平铺', 'stagger': '错位平铺', 'scatter': '随机散点', 'single': '单排重复', 'ends': '两端主图', 'panels': '分区拼接',
         'bordered': '上下边饰', 'scene': '组合循环', 'fullwidth': '整幅定位',
         'alternating': '大小交替', 'ends_open': '两端留白', 'split': '左右分区',
         'stacked': '上下分区', 'opposed': '正倒交替'}
EXTENDED_MODES = frozenset({'bordered', 'scene', 'fullwidth', 'alternating', 'ends_open', 'split', 'stacked', 'opposed'})
NON_REPEATING_MODES = frozenset({'fullwidth', 'ends_open'})
ASSET_PREVIEW_VERSION = 'asset-preview-v1'
ASSET_PREVIEW_SIZE = (640, 640)
from .ribbon_targets import loop_inputs

LAYOUT_ENGINE = 'seamless-unit-v3'
MODERN_LOOP_ENGINES = ('seamless-unit-v2', LAYOUT_ENGINE)
LOOP_ENGINES = ('seamless-unit-v1', *MODERN_LOOP_ENGINES)
QUALITY_LAYOUT_ENGINES = frozenset({'design-rhythm-v1', 'design-rhythm-v2', *LOOP_ENGINES})
BACKGROUND_TONES = frozenset({'soft', 'quiet', 'original'})
DESIGN_DENSITIES = frozenset({'airy', 'balanced', 'rich'})
TERMINAL = ('SUCCEEDED', 'FAILED')


def now():
    return datetime.now(timezone.utc).isoformat()


def uid():
    return uuid.uuid4().hex


def dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def digest(data: bytes):
    return hashlib.sha256(data).hexdigest()


def file_digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


@memory_bounded_operation
def same_rgba_pixels(first, second):
    """Compare the saved result, rather than just parameters or PNG encoding.

    Keep the comparison under the renderer's allocation guard and convert only
    narrow bands. Metadata/compression changes alone are not a new refinement.
    """
    with Image.open(first) as before, Image.open(second) as after:
        if before.size != after.size:
            return False
        before.load()
        after.load()
        for top in range(0, before.height, 64):
            box = (0, top, before.width, min(before.height, top + 64))
            with before.crop(box) as before_band, after.crop(box) as after_band:
                with before_band.convert('RGBA') as a, after_band.convert('RGBA') as b:
                    if a.tobytes() != b.tobytes():
                        return False
    return True


def leased_operation(method):
    @wraps(method)
    def wrapped(self, identity, *args, **kwargs):
        owner = identity.get('owner_id', identity.get('id')) if isinstance(identity, dict) else identity
        with self.resource_lease(owner):
            return method(self, identity, *args, **kwargs)
    return wrapped


def guarded_file_operations(method):
    @wraps(method)
    def wrapped(self, *args, **kwargs):
        with disk_space_guard(self.check_space):
            try:
                return method(self, *args, **kwargs)
            except OSError as error:
                if disk_full(error):
                    raise ServiceError(507, '存储空间不足，请清理后重试；原版本已保留') from None
                raise
    return wrapped


def disk_full(error):
    return getattr(error, 'errno', None) in (28, 122) or getattr(error, 'winerror', None) in (39, 112)


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    return salt + ':' + hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 200_000).hex()


class ServiceError(Exception):
    def __init__(self, status: int, message: str):
        self.status, self.message = status, message
        super().__init__(message)


class Service:
    def __init__(self, settings: Settings, runtime_settings_supplier=None, provider_factory=None, example_resolver=None):
        self.settings = settings
        self.runtime_settings_supplier = runtime_settings_supplier
        self.provider_factory = provider_factory
        self.example_resolver = example_resolver
        self.root = settings.data_dir
        if self.root.resolve() == Path(self.root.anchor):
            raise ServiceError(507, '请为丝带功能设置专用数据目录，不能使用磁盘根目录')
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = Database(self.root / 'ribbon.sqlite3')
        from .retention import registry_for
        self._leases = registry_for(self.root)
        # Style previews are pure functions of the selection; cache a few so
        # re-opening the trial is instant. Bounded and in-memory only.
        self._candidate_cache = {}
        self._candidate_lock = threading.Lock()
        self.stop_event = threading.Event()
        self._asset_preview_lock = threading.RLock()
        self.thread = None
        self.initialize()

    def check_space(self, directory, required_bytes):
        """Inject host disk budgeting without allowing writes outside our root."""
        root = self.root.resolve()
        directory = Path(directory).absolute()
        if root == Path(root.anchor) or not directory.is_relative_to(root):
            raise ServiceError(507, '保存目录不在本功能的数据目录内')
        relative = directory.relative_to(root)
        if any(part in ('.', '..') for part in relative.parts):
            raise ServiceError(507, '保存目录无效')
        node = root
        for part in ('', *relative.parts):
            node = node / part
            if node.is_symlink() or (hasattr(node, 'is_junction') and node.is_junction()):
                raise ServiceError(507, '保存目录不支持链接或目录联接')
        existing = directory
        while not existing.exists() and existing != root:
            existing = existing.parent
        checker = getattr(self.settings, 'space_reserver', None)
        try:
            if checker is not None:
                if checker(existing, int(required_bytes)) is False:
                    raise OSError(28, 'space denied')
            elif shutil.disk_usage(existing).free < int(required_bytes) + STANDALONE_FREE_MARGIN:
                raise OSError(28, 'space denied')
        except Exception:
            raise ServiceError(507, '存储空间不足或无法确认，请联系管理员清理后重试；原版本已保留') from None

    def current_settings(self):
        return self.runtime_settings_supplier() if self.runtime_settings_supplier else self.settings

    def ensure_external_user(self, owner, role='customer'):
        """Bind only an identity already authenticated by the HSD host."""
        if self.settings.auth_mode != 'hsd':
            raise ServiceError(403, '当前服务未启用主站身份')
        if not isinstance(owner, str) or not re.fullmatch(r'[A-Za-z0-9:_-]{1,160}', owner) or role not in ('customer', 'employee', 'admin'):
            raise ServiceError(422, '主站身份无效')
        role = 'customer' if role == 'employee' else role
        username = 'hsd-' + digest(owner.encode())[:48]
        # A normal image/list read must not acquire SQLite's write lock merely
        # to repeat an unchanged host identity. The host supplies the role on
        # every request; role changes still go through a transaction below.
        with self.db.connect() as db:
            previous = db.execute('SELECT * FROM users WHERE id=?', (owner,)).fetchone()
        if previous and previous['username'] != username:
            raise ServiceError(409, '主站身份与已有账号冲突')
        if previous and previous['role'] == role:
            return dict(id=owner, username=username, role=role)
        with self.db.transaction() as db:
            previous = db.execute('SELECT * FROM users WHERE id=?', (owner,)).fetchone()
            if previous and previous['username'] != username:
                raise ServiceError(409, '主站身份与已有账号冲突')
            db.execute('INSERT INTO users(id,username,password_hash,role) VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET role=excluded.role',
                       (owner, username, '!external-auth-only', role))
        return dict(id=owner, username=username, role=role)

    @contextmanager
    def resource_lease(self, owner, *, design_id=None, version_id=None, asset_id=None, job_id=None):
        """Keep private resources alive until an operation/response closes."""
        with self._leases.lock:
            with self.db.connect() as db:
                if not db.execute('SELECT 1 FROM users WHERE id=?', (owner,)).fetchone():
                    raise ServiceError(401, '请先登录')
                if design_id:
                    self.owned_design(db, owner, design_id)
                if asset_id:
                    self.accessible_asset(db, asset_id, owner)
                if version_id and not db.execute('SELECT 1 FROM versions v JOIN designs d ON d.id=v.design_id WHERE v.id=? AND d.owner_id=?', (version_id, owner)).fetchone():
                    raise ServiceError(404, '版本不存在或无权访问')
                if job_id and not db.execute('SELECT 1 FROM jobs WHERE id=? AND owner_id=?', (job_id, owner)).fetchone():
                    raise ServiceError(404, '任务不存在或无权访问')
            self._leases.owners[owner] += 1
        try:
            yield
        finally:
            with self._leases.lock:
                self._leases.owners[owner] -= 1
                if not self._leases.owners[owner]:
                    del self._leases.owners[owner]

    def cleanup_expired(self, now=None):
        from .retention import cleanup
        return cleanup(self, now=now)

    @guarded_file_operations
    @memory_bounded_operation
    def initialize(self):
        from .imaging import seed_assets, template_thumbnail
        with self.db.transaction() as db:
            if self.settings.auth_mode == 'demo':
                for username, role in [('demo', 'customer'), ('client', 'customer'), ('admin', 'admin')]:
                    if not db.execute('SELECT 1 FROM users WHERE username=?', (username,)).fetchone():
                        db.execute('INSERT INTO users VALUES(?,?,?,?)', (uid(), username, password_hash(username + '12345'), role))
            if not db.execute('SELECT 1 FROM assets LIMIT 1').fetchone():
                for asset in seed_assets(self.root / 'seed'):
                    self.insert_asset(db, dict(asset, owner_id=None, sha256=digest(Path(asset['path']).read_bytes()), created_at=now()))
            for mode, name in MODES.items():
                template_id = self.default_template_id(db, mode)
                if template_id is not None:
                    path = self.root / 'templates' / f'{template_id}-1.png'
                    path.parent.mkdir(parents=True, exist_ok=True)
                    template_thumbnail(mode, path)
                    db.execute('INSERT INTO templates(id,version,name,mode,rules_json,enabled,thumbnail_path,thumbnail_sha256) VALUES(?,?,?,?,?,?,?,?)', (template_id, 1, name, mode, dump({'is_demo': True}), 1, str(path), file_digest(path)))
            if not db.execute('SELECT 1 FROM output_profiles').fetchone():
                profile = dict(id='demo-v1', version=1, name='演示输出配置', width=2400, height=600, dpi=150, format='PNG', is_demo=True)
                db.execute('INSERT INTO output_profiles VALUES(?,?,?,?,1)', (profile['id'], 1, profile['name'], dump(profile)))

    def default_template_id(self, db, mode):
        """Append new built-ins without rewriting an administrator's template.

        Old six defaults retain their existing initialization semantics. A new
        mode may need a different ID if its short name was already used by a
        custom template. Any historical row for that built-in mode means it
        was initialized before, including a subsequently disabled/changed row.
        """
        if mode not in EXTENDED_MODES:
            return None if db.execute('SELECT 1 FROM templates WHERE id=?', (mode,)).fetchone() else mode
        for candidate in [mode, 'builtin-' + mode, *('builtin-' + mode + '-' + str(i) for i in range(2, 100))]:
            rows = db.execute('SELECT mode FROM templates WHERE id=?', (candidate,)).fetchall()
            if any(row['mode'] == mode for row in rows):
                return None
            if rows:
                continue
            path = self.root / 'templates' / f'{candidate}-1.png'
            if path.exists() or path.is_symlink():
                continue
            return candidate
        raise ServiceError(409, '新增排版的默认标识已被占用，请联系管理员处理；已有模板没有改动')

    @staticmethod
    def validate_layout_selection(mode, asset_ids, engine=None):
        if mode == 'bordered' and len(asset_ids) < 2 and engine not in MODERN_LOOP_ENGINES:
            raise ServiceError(422, '上下边饰至少选择2个图案：第1个作主体，其余作上下边饰')
        if mode == 'fullwidth' and len(asset_ids) != 1:
            raise ServiceError(422, '整幅定位请选择1张完整设计；不会忽略其他所选图案')
        if mode == 'ends_open' and len(asset_ids) not in (1, 2):
            raise ServiceError(422, '两端留白请选择1或2个图案：1个放两端，2个分别放左右')
        if mode == 'split' and len(asset_ids) < 2:
            raise ServiceError(422, '左右分区至少选择2个图案：前半组放左区，后半组放右区')
        if mode == 'stacked' and len(asset_ids) < 2:
            raise ServiceError(422, '上下分区至少选择2个图案：前半组放上区，后半组放下区')

    def insert_asset(self, db, asset):
        db.execute('INSERT INTO assets(id,owner_id,name,kind,path,sha256,source,is_demo,shared,derived_from,created_at,retained_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                   (asset['id'], asset.get('owner_id'), asset['name'], asset['kind'], str(asset['path']), asset['sha256'], asset.get('source', 'upload'), int(asset.get('is_demo', False)), int(asset.get('shared', False)), asset.get('derived_from'), asset.get('created_at', now()), time.time()))

    def add_user(self, username, password, role='customer'):
        if not re.fullmatch(r'[a-zA-Z0-9_-]{3,40}', username) or len(password) < 10 or role not in ('customer', 'admin'):
            raise ServiceError(422, '账号需 3–40 个字母、数字或下划线，密码至少 10 位')
        with self.db.transaction() as db:
            db.execute('INSERT INTO users VALUES(?,?,?,?)', (uid(), username, password_hash(password), role))

    def login(self, username, password):
        if self.settings.auth_mode == 'hsd':
            raise ServiceError(403, '请从主站登录')
        with self.db.transaction() as db:
            row = db.execute('SELECT * FROM users WHERE username=?', (username,)).fetchone()
            if not row or not hmac.compare_digest(row['password_hash'], password_hash(password, row['password_hash'].split(':')[0])):
                raise ServiceError(401, '账号或密码不正确')
            token = secrets.token_urlsafe(32)
            db.execute('DELETE FROM sessions WHERE expires_at<?', (time.time(),))
            db.execute('INSERT INTO sessions VALUES(?,?,?)', (digest(token.encode()), row['id'], time.time() + self.settings.session_hours * 3600))
            return token, {k: row[k] for k in ('id', 'username', 'role')}

    def authenticate(self, token):
        if not token:
            raise ServiceError(401, '请先登录')
        with self.db.connect() as db:
            row = db.execute('SELECT u.id,u.username,u.role FROM users u JOIN sessions s ON s.user_id=u.id WHERE s.token_hash=? AND s.expires_at>?', (digest(token.encode()), time.time())).fetchone()
        if not row:
            raise ServiceError(401, '会话已过期，请重新登录')
        return dict(row)

    def logout(self, token):
        with self.db.transaction() as db:
            db.execute('DELETE FROM sessions WHERE token_hash=?', (digest((token or '').encode()),))

    def config(self):
        from .providers import workflow_editing
        with self.db.connect() as db:
            profile = json.loads(db.execute('SELECT profile_json FROM output_profiles WHERE active=1').fetchone()[0])
        settings = self.current_settings()
        return dict(provider=settings.provider, ai_ready=settings.ai_ready, auth_mode=self.settings.auth_mode, output_profile={k: profile[k] for k in ('id', 'version', 'name', 'is_demo')}, max_refinements=2,
                    ai_draft_available=settings.provider == 'deepseek_seedream' and settings.ai_ready,
                    retention_hours=self.settings.retention_seconds // 3600,
                    editing=workflow_editing(settings.provider, dict(output_profile=profile, template_mode='stagger')))

    def asset_public(self, row):
        prefix = f"{getattr(self.settings, 'api_prefix', '/api')}/assets/{row['id']}"
        return {**{k: row[k] for k in ('id', 'name', 'kind', 'source', 'derived_from')}, 'is_demo': bool(row['is_demo']), 'shared': bool(row['shared']), 'url': prefix + '/file',
                'thumbnail_url': prefix + '/thumbnail?v=' + self.asset_preview_version(row['sha256'])}

    @staticmethod
    def asset_preview_version(source_sha256):
        return ASSET_PREVIEW_VERSION + '-' + source_sha256[:16]

    def asset_preview_path(self, source_path, source_sha256):
        identity = str(Path(source_path).relative_to(self.root)) + ':' + source_sha256 + ':' + ASSET_PREVIEW_VERSION
        return self.root / 'assets' / ('preview-' + digest(identity.encode()) + '.png')

    @memory_bounded_operation
    def write_asset_preview(self, image, path, fingerprints=None):
        # Keep the complete canvas and alpha; this is a screen derivative only.
        preview = image.copy()
        try:
            preview.thumbnail(ASSET_PREVIEW_SIZE, Image.Resampling.LANCZOS)
            if fingerprints is not None:
                fingerprints['thumbnail_pixel_sha256'] = self.image_pixel_digest(preview)
            self.check_space(path.parent, png_space(*preview.size))
            if path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction()):
                raise ServiceError(409, '素材缩略图不支持链接')
            encoded = io.BytesIO()
            preview.save(encoded, format='PNG', optimize=False, compress_level=3)
            expected = digest(encoded.getvalue())
            if path.exists():
                self.verified_file(path, expected, '素材缩略图')
            else:
                _save_png(preview, path, dpi=None, compress_level=3)
                self.verified_file(path, expected, '素材缩略图')
            return expected
        finally:
            preview.close()

    def cleanup_uncommitted_asset_files(self, paths):
        # A commit exception can be uncertain. Recheck all asset references in
        # a fresh write transaction before deleting a file or queuing cleanup.
        try:
            from .retention import _safe_path
            with self.db.transaction() as db:
                for raw in paths:
                    path = Path(raw).absolute()
                    if path.parent != self.root / 'assets' or not _safe_path(self.root, path):
                        continue
                    referenced = db.execute('SELECT 1 FROM assets WHERE path=? OR thumbnail_path=? LIMIT 1',
                                            (str(path), str(path))).fetchone()
                    if referenced:
                        continue
                    db.execute('INSERT OR IGNORE INTO cleanup_paths VALUES(?,0)', (str(path),))
                    try:
                        path.unlink(missing_ok=True)
                    except OSError:
                        pass  # The normal safe cleanup retries the registered file.
                    else:
                        db.execute('DELETE FROM cleanup_paths WHERE path=?', (str(path),))
        except (OSError, sqlite3.Error, ServiceError):
            # No successful read/transaction means no proof of non-reference.
            log.warning('Uncommitted asset cleanup postponed; files retained')

    @leased_operation
    @guarded_file_operations
    def verified_asset_preview(self, owner, asset_id, version=None):
        with self.db.connect() as db:
            asset = self.accessible_asset(db, asset_id, owner)
        source = self.verified_file(asset['path'], asset['sha256'], '素材文件')
        if version is not None and version != self.asset_preview_version(asset['sha256']):
            raise ServiceError(404, '素材缩略图版本不存在')
        expected_path = self.asset_preview_path(source, asset['sha256'])
        if asset['thumbnail_path'] or asset['thumbnail_sha256']:
            if asset['thumbnail_path'] != str(expected_path) or not asset['thumbnail_sha256']:
                raise ServiceError(409, '素材缩略图记录校验失败')
            return self.verified_file(expected_path, asset['thumbnail_sha256'], '素材缩略图'), asset['thumbnail_sha256']
        # Old/source-generated assets get a derivative once. Do not hold the
        # allocation lock while acquiring a database write transaction.
        with self._asset_preview_lock:
            with self.db.connect() as db:
                current = self.accessible_asset(db, asset_id, owner)
            if current['path'] != str(source) or current['sha256'] != asset['sha256']:
                raise ServiceError(409, '素材文件已变化，请刷新')
            self.verified_file(source, current['sha256'], '素材文件')
            if current['thumbnail_path'] or current['thumbnail_sha256']:
                if current['thumbnail_path'] != str(expected_path) or not current['thumbnail_sha256']:
                    raise ServiceError(409, '素材缩略图记录校验失败')
                return self.verified_file(expected_path, current['thumbnail_sha256'], '素材缩略图'), current['thumbnail_sha256']
            try:
                fingerprints = {}
                preview_sha = self.create_asset_preview(source, asset['sha256'], expected_path, fingerprints)
                self.verified_file(source, asset['sha256'], '素材文件')
                with self.db.transaction() as db:
                    current = self.accessible_asset(db, asset_id, owner)
                    if current['sha256'] != asset['sha256'] or current['path'] != str(source):
                        raise ServiceError(409, '素材文件已变化，请刷新')
                    db.execute("UPDATE assets SET thumbnail_path=?,thumbnail_sha256=?,thumbnail_pixel_sha256=?,pixel_sha256=CASE WHEN source='upload' THEN COALESCE(pixel_sha256,?) ELSE pixel_sha256 END WHERE id=?",
                               (str(expected_path), preview_sha, fingerprints['thumbnail_pixel_sha256'], fingerprints['pixel_sha256'], asset_id))
                    db.execute('DELETE FROM cleanup_paths WHERE path=?', (str(expected_path),))
            except BaseException:
                self.cleanup_uncommitted_asset_files([expected_path])
                raise
        return self.verified_file(expected_path, preview_sha, '素材缩略图'), preview_sha

    @memory_bounded_operation
    def create_asset_preview(self, source, expected_source_sha, target, fingerprints=None):
        from .imaging import read_image
        self.verified_file(source, expected_source_sha, '素材文件')
        with Image.open(source) as original:
            # Saved sources are normalized single-frame PNGs. read_image also
            # checks legacy/derived inputs before any large allocation.
            if getattr(original, 'n_frames', 1) != 1:
                raise ServiceError(409, '素材文件不是单帧图片')
        image = read_image(source)
        try:
            if fingerprints is not None:
                fingerprints['pixel_sha256'] = self.image_pixel_digest(image)
            return self.write_asset_preview(image, target, fingerprints)
        finally:
            image.close()

    @leased_operation
    def assets(self, owner, kind=None):
        with self.db.connect() as db:
            rows = db.execute('SELECT * FROM assets WHERE enabled=1 AND (owner_id=? OR shared=1) AND (? IS NULL OR kind=?) ORDER BY created_at,id', (owner, kind, kind)).fetchall()
        return [self.asset_public(r) for r in rows]

    def accessible_asset(self, db, asset_id, owner, kind=None, require_enabled=False):
        row = db.execute('SELECT * FROM assets WHERE id=? AND (owner_id=? OR shared=1)', (asset_id, owner)).fetchone()
        if not row or (kind and row['kind'] != kind) or (require_enabled and not row['enabled']):
            raise ServiceError(404, '素材不存在、类型不符或无权使用')
        return dict(row)

    def verified_file(self, path, expected, description='保存文件'):
        path = self.safe_path(path)
        if not expected or file_digest(path) != expected:
            raise ServiceError(409, f'{description}校验失败，原文件可能已改变，请联系管理员')
        return path

    @leased_operation
    def verified_asset_path(self, owner, asset_id):
        with self.db.connect() as db:
            asset = self.accessible_asset(db, asset_id, owner)
        return self.verified_file(asset['path'], asset['sha256'], '素材文件')

    def verified_template_path(self, template_id, version):
        with self.db.connect() as db:
            row = db.execute('SELECT thumbnail_path,thumbnail_sha256 FROM templates WHERE id=? AND version=?', (template_id, version)).fetchone()
        if not row:
            raise ServiceError(404, '模板不存在')
        return self.verified_file(row['thumbnail_path'], row['thumbnail_sha256'], '模板缩略图')

    @staticmethod
    def snapshot_asset_ids(snapshot):
        return set(snapshot.get('asset_refs', [])) | set(snapshot.get('zone_background_refs', {}).values()) | {
            snapshot[key] for key in ('background_ref', 'composite_ref', 'border_ref') if snapshot.get(key)
        }

    @staticmethod
    def image_pixel_digest(image):
        """Exact normalized RGBA identity, including canvas and invisible pixels."""
        value = hashlib.sha256(f'rgba-v1:{image.width}:{image.height}:'.encode())
        for top in range(0, image.height, 64):
            with image.crop((0, top, image.width, min(image.height, top + 64))) as band:
                value.update(band.tobytes())
        return value.hexdigest()

    @memory_bounded_operation
    def legacy_upload_pixel_digest(self, asset):
        source = self.verified_file(asset['path'], asset['sha256'], '素材文件')
        with Image.open(source) as original:
            if original.width * original.height > MAX_PIXELS or getattr(original, 'n_frames', 1) != 1:
                raise ServiceError(409, '已有上传素材无法确认完整像素')
            with original.convert('RGBA') as image:
                value = self.image_pixel_digest(image)
        self.verified_file(source, asset['sha256'], '素材文件')
        return value

    @memory_bounded_operation
    def legacy_preview_pixel_digest(self, asset):
        # Only derivatives produced by the current immutable preview contract
        # qualify as a shortlist. Encoding metadata (e.g. ICC) is not identity.
        if not asset['thumbnail_path'] or not asset['thumbnail_sha256']:
            return None
        if asset['thumbnail_path'] != str(self.asset_preview_path(Path(asset['path']), asset['sha256'])):
            return None
        path = self.verified_file(asset['thumbnail_path'], asset['thumbnail_sha256'], '素材缩略图')
        with Image.open(path) as original:
            if original.format != 'PNG' or max(original.size) > ASSET_PREVIEW_SIZE[0] or getattr(original, 'n_frames', 1) != 1:
                return None
            with original.convert('RGBA') as image:
                return self.image_pixel_digest(image)

    def index_legacy_uploads(self, owner, kind, shared, stored):
        # Never decode the whole original gallery on an upload. Cached 640px
        # pixel fingerprints shortlist originals; a match still needs exact
        # full RGBA identity. Unknown no-preview rows are indexed when their
        # preview is first derived, or immediately if PNG bytes match exactly.
        with self.db.connect() as db:
            pending = db.execute("SELECT * FROM assets WHERE owner_id=? AND kind=? AND shared=? AND source='upload' AND pixel_sha256 IS NULL AND (sha256=? OR thumbnail_pixel_sha256=? OR thumbnail_pixel_sha256 IS NULL) ORDER BY created_at,id",
                                 (owner, kind, int(shared), stored['sha256'], stored['thumbnail_pixel_sha256'])).fetchall()
        for row in pending:
            asset = dict(row)
            try:
                if asset['sha256'] == stored['sha256']:
                    # Equal verified normalized file bytes imply equal pixels;
                    # the incoming image has already been fully decoded.
                    self.verified_file(asset['path'], asset['sha256'], '素材文件')
                    pixel_sha = stored['pixel_sha256']
                else:
                    preview_sha = asset['thumbnail_pixel_sha256']
                    if preview_sha is None:
                        preview_sha = self.legacy_preview_pixel_digest(asset)
                        if preview_sha is not None:
                            with self.db.transaction() as db:
                                db.execute('UPDATE assets SET thumbnail_pixel_sha256=? WHERE id=? AND thumbnail_path=? AND thumbnail_sha256=? AND thumbnail_pixel_sha256 IS NULL',
                                           (preview_sha, asset['id'], asset['thumbnail_path'], asset['thumbnail_sha256']))
                    if preview_sha != stored['thumbnail_pixel_sha256']:
                        continue
                    pixel_sha = self.legacy_upload_pixel_digest(asset)
            except (ServiceError, OSError, ValueError):
                continue  # An unverifiable legacy file is never reused.
            # Keep the write transaction outside the image allocation lock.
            with self.db.transaction() as db:
                db.execute('UPDATE assets SET pixel_sha256=? WHERE id=? AND path=? AND sha256=? AND pixel_sha256 IS NULL',
                           (pixel_sha, asset['id'], asset['path'], asset['sha256']))
            if pixel_sha == stored['pixel_sha256']:
                with self.db.connect() as db:
                    if self.matching_upload(db, owner, kind, shared, pixel_sha):
                        break

    def matching_upload(self, db, owner, kind, shared, pixel_sha):
        candidates = db.execute("SELECT * FROM assets WHERE owner_id=? AND kind=? AND shared=? AND source='upload' AND pixel_sha256=? ORDER BY created_at,id",
                                (owner, kind, int(shared), pixel_sha))
        for row in candidates:
            try:
                source = self.verified_file(row['path'], row['sha256'], '素材文件')
                if row['thumbnail_path'] or row['thumbnail_sha256']:
                    if row['thumbnail_path'] != str(self.asset_preview_path(source, row['sha256'])) or not row['thumbnail_sha256']:
                        continue
                    self.verified_file(row['thumbnail_path'], row['thumbnail_sha256'], '素材缩略图')
            except (ServiceError, OSError, ValueError):
                # A damaged historical candidate remains immutable and keeps
                # its old references. It cannot block a valid fresh upload.
                continue
            return row
        return None

    @leased_operation
    @guarded_file_operations
    def upload(self, user, data, name, kind, shared=False):
        if kind not in ('pattern', 'background'):
            raise ServiceError(422, '请选择图案或底图')
        if shared and user['role'] != 'admin':
            raise ServiceError(403, '只有内部账号可上传共享素材')
        if len(data) > 20 * 1024 * 1024 or not data:
            raise ServiceError(413, '图片须为 20MB 以内的 PNG、JPEG 或 WebP')
        asset_id = uid()
        path = self.root / 'assets' / f'{asset_id}.png'
        created = [path]
        try:
            stored = self.store_uploaded_image(data, path, created, scope=(user['id'], kind, shared))
            while True:
                if 'thumbnail_path' in stored:
                    self.index_legacy_uploads(user['id'], kind, shared, stored)
                with self.db.transaction() as db:
                    existing = self.matching_upload(db, user['id'], kind, shared, stored['pixel_sha256'])
                    if existing:
                        asset = dict(existing)
                        db.execute('UPDATE assets SET enabled=1,retained_at=? WHERE id=?', (time.time(), asset['id']))
                        if 'thumbnail_path' in stored:
                            # A racing upload may already have encoded its pair.
                            # Persist cleanup before commit for restart recovery.
                            db.executemany('INSERT OR IGNORE INTO cleanup_paths VALUES(?,0)', [(str(p),) for p in created])
                        break
                    if 'thumbnail_path' in stored:
                        asset = dict(id=asset_id, owner_id=user['id'], name=(name or '上传素材')[:80], kind=kind, path=str(path), sha256=stored['sha256'], source='upload', is_demo=False, shared=shared, derived_from=None)
                        self.insert_asset(db, asset)
                        db.execute('UPDATE assets SET thumbnail_path=?,thumbnail_sha256=?,pixel_sha256=?,thumbnail_pixel_sha256=? WHERE id=?',
                                   (str(stored['thumbnail_path']), stored['thumbnail_sha256'], stored['pixel_sha256'], stored['thumbnail_pixel_sha256'], asset_id))
                        db.execute('DELETE FROM cleanup_paths WHERE path IN (?,?)', (str(path), str(stored['thumbnail_path'])))
                        break
                # A fast-path candidate became unusable before the transaction.
                # Encode outside the database write lock, then recheck the scope.
                stored = self.store_uploaded_image(data, path, created)
        except BaseException:
            self.cleanup_uncommitted_asset_files(created)
            raise
        reused = asset['id'] != asset_id
        if reused and 'thumbnail_path' in stored:
            self.cleanup_uncommitted_asset_files(created)
        return {**self.asset_public(asset), 'deduplicated': reused}

    @memory_bounded_operation
    def store_uploaded_image(self, data, path, created=None, scope=None):
        # Never take the database write lock while holding this allocation lock:
        # template generation and retention have their own transaction ordering.
        try:
            with Image.open(io.BytesIO(data)) as original:
                if original.format not in ('PNG', 'JPEG', 'WEBP') or original.width * original.height > 40_000_000:
                    raise ValueError('Unsupported image')
                if getattr(original, 'n_frames', 1) != 1:
                    raise ServiceError(422, '暂不支持动态图像，请上传单帧 PNG、JPEG 或 WebP')
                original.load()
                if original.getexif().get(274, 1) == 1:
                    img = original.convert('RGBA')
                else:
                    oriented = ImageOps.exif_transpose(original)
                    try:
                        img = oriented.convert('RGBA')
                    finally:
                        oriented.close()
        except ServiceError:
            raise
        except Exception:
            raise ServiceError(422, '图片无法解码，或像素数量超过 4000 万') from None
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            pixel_sha = self.image_pixel_digest(img)
            if scope is not None:
                with self.db.connect() as db:
                    existing = self.matching_upload(db, *scope, pixel_sha)
                if existing:
                    return dict(sha256=existing['sha256'], pixel_sha256=pixel_sha)
            self.check_space(path.parent, png_space(*img.size))
            _save_png(img, path, dpi=None, compress_level=3)
            source_sha = file_digest(path)
            preview = self.asset_preview_path(path, source_sha)
            if created is not None:
                created.append(preview)
            fingerprints = {}
            preview_sha = self.write_asset_preview(img, preview, fingerprints)
            return dict(sha256=source_sha, thumbnail_path=preview, thumbnail_sha256=preview_sha, pixel_sha256=pixel_sha,
                        thumbnail_pixel_sha256=fingerprints['thumbnail_pixel_sha256'])
        finally:
            img.close()

    @leased_operation
    def hide_asset(self, user, asset_id):
        with self.db.transaction() as db:
            row = db.execute('SELECT * FROM assets WHERE id=?', (asset_id,)).fetchone()
            if not row or not (row['owner_id'] == user['id'] or (user['role'] == 'admin' and row['shared'])):
                raise ServiceError(404, '素材不存在或无权维护')
            db.execute('UPDATE assets SET enabled=0 WHERE id=?', (asset_id,))

    def templates(self):
        with self.db.connect() as db:
            rows = db.execute('SELECT t.* FROM templates t JOIN (SELECT id,MAX(version) v FROM templates GROUP BY id) m ON m.id=t.id AND m.v=t.version').fetchall()
        order = list(MODES)
        rows = sorted(rows, key=lambda r: (order.index(r['id']) if r['id'] in order else len(order), r['name']))
        return [dict(id=r['id'], name=r['name'], version=r['version'], mode=r['mode'], enabled=bool(r['enabled']), rules=json.loads(r['rules_json']), thumbnail_url=f"{getattr(self.settings, 'api_prefix', '/api')}/templates/{r['id']}/{r['version']}/thumbnail") for r in rows]

    @leased_operation
    def create_design(self, owner, name):
        design_id = uid()
        with self.db.transaction() as db:
            db.execute('INSERT INTO designs(id,owner_id,name,created_at,retained_at) VALUES(?,?,?,?,?)', (design_id, owner, (name or '未命名设计')[:80], now(), time.time()))
        return self.design(owner, design_id)

    def owned_design(self, db, owner, design_id, *, include_deleted=False):
        row = db.execute('SELECT * FROM designs WHERE id=? AND owner_id=?', (design_id, owner)).fetchone()
        if not row or (row['deleted_at'] is not None and not include_deleted):
            raise ServiceError(404, '作品不存在或无权访问')
        return dict(row)

    @staticmethod
    def require_idle_design(db, design):
        if design['active_job_id'] or db.execute("SELECT 1 FROM jobs WHERE design_id=? AND status NOT IN ('SUCCEEDED','FAILED') LIMIT 1", (design['id'],)).fetchone():
            raise ServiceError(409, '作品正在处理，请等待当前任务结束')

    @leased_operation
    def delete_design(self, owner, design_id):
        with self.db.transaction() as db:
            design = self.owned_design(db, owner, design_id, include_deleted=True)
            self.require_idle_design(db, design)
            deleted_at = design['deleted_at']
            if deleted_at is None:
                deleted_at = time.time()
                # Soft deletion starts a normal retention window; it does not
                # erase any version, quota event, request or underlying file.
                db.execute('UPDATE designs SET deleted_at=?,retained_at=?,revision=revision+1 WHERE id=?',
                           (deleted_at, deleted_at, design_id))
        return dict(ok=True, id=design_id, deleted_at=deleted_at)

    @leased_operation
    def restore_design(self, owner, design_id):
        with self.db.transaction() as db:
            design = self.owned_design(db, owner, design_id, include_deleted=True)
            self.require_idle_design(db, design)
            if design['deleted_at'] is not None:
                db.execute('UPDATE designs SET deleted_at=NULL,retained_at=?,revision=revision+1 WHERE id=?',
                           (time.time(), design_id))
        return self.design(owner, design_id)

    def version_public(self, row):
        from .providers import workflow_editing
        prefix = getattr(self.settings, 'api_prefix', '/api')
        snapshot = json.loads(row['snapshot_json'])
        return {**{k: row[k] for k in ('id', 'design_id', 'parent_version_id', 'sequence', 'prompt', 'render_kind', 'provider', 'created_at')}, 'snapshot': snapshot,
                'editing': workflow_editing(self.current_settings().provider, snapshot),
                'preview_url': f"{prefix}/versions/{row['id']}/preview", 'view_url': f"{prefix}/versions/{row['id']}/view", 'download_url': f"{prefix}/versions/{row['id']}/download"}

    @staticmethod
    def job_public(row):
        return {**{k: row[k] for k in ('id', 'design_id', 'kind', 'status', 'phase', 'attempt', 'provider', 'error', 'result_version_id', 'result_asset_id', 'created_at', 'updated_at')}, 'needs_clarification': bool(row['needs_clarification'])}

    @leased_operation
    def design(self, owner, design_id, *, include_deleted=False):
        with self.db.connect() as db:
            result = self.owned_design(db, owner, design_id, include_deleted=include_deleted)
            versions = db.execute('SELECT * FROM versions WHERE design_id=? ORDER BY sequence', (design_id,)).fetchall()
            active = db.execute('SELECT * FROM jobs WHERE id=?', (result['active_job_id'],)).fetchone()
        result.pop('owner_id')
        result['versions'] = [self.version_public(v) for v in versions]
        result['active_job'] = self.job_public(active) if active else None
        return result

    @leased_operation
    def designs(self, owner, deleted=False, summary=False):
        with self.db.connect() as db:
            # Resolve the list and versions in one read snapshot, so a delete
            # or restore racing this request cannot turn the whole list into 404.
            db.execute('BEGIN')
            rows = db.execute('SELECT * FROM designs WHERE owner_id=? AND (deleted_at IS NOT NULL)=? ORDER BY created_at DESC', (owner, int(deleted))).fetchall()
            result = []
            for row in rows:
                item = dict(row)
                item.pop('owner_id')
                if summary:
                    item.update(versions=[], active_job=None)
                    result.append(item)
                    continue
                item['versions'] = [self.version_public(v) for v in db.execute('SELECT * FROM versions WHERE design_id=? ORDER BY sequence', (row['id'],))]
                active = db.execute('SELECT * FROM jobs WHERE id=?', (row['active_job_id'],)).fetchone()
                item['active_job'] = self.job_public(active) if active else None
                result.append(item)
        return result

    @leased_operation
    def job(self, owner, job_id):
        with self.db.connect() as db:
            row = db.execute('SELECT * FROM jobs WHERE id=? AND owner_id=?', (job_id, owner)).fetchone()
        if not row:
            raise ServiceError(404, '任务不存在或无权访问')
        return self.job_public(row)

    def selection_snapshot(self, db, owner, selection, profile=None, base=None):
        ids = selection.get('asset_ids')
        if not isinstance(ids, list) or not 1 <= len(ids) <= 12 or len(set(ids)) != len(ids):
            raise ServiceError(422, '请选择 1–12 个不重复的图案')
        for asset_id in ids:
            self.accessible_asset(db, asset_id, owner, 'pattern', True)
        self.accessible_asset(db, selection.get('background_id'), owner, 'background', True)
        template = db.execute('SELECT * FROM templates WHERE id=? ORDER BY version DESC LIMIT 1', (selection.get('template_id'),)).fetchone()
        if not template or not template['enabled']:
            raise ServiceError(422, '请选择可用的排版模式')
        self.validate_layout_selection(template['mode'], ids, base.get('layout_engine') if base else LAYOUT_ENGINE)
        profile = profile or json.loads(db.execute('SELECT profile_json FROM output_profiles WHERE active=1').fetchone()[0])
        result = copy.deepcopy(base) if base else dict(schema_version=1, layout_engine=LAYOUT_ENGINE,
                    seed=secrets.randbelow(2**31), params=dict(scale=1.0, spacing=1.0, rotation=0.0, offset_x=0.0, offset_y=0.0, background_color=None))
        default_tone = 'soft' if result.get('layout_engine') in QUALITY_LAYOUT_ENGINES else 'original'
        tone = selection.get('background_tone', result.get('background_tone', default_tone))
        if not isinstance(tone, str) or tone not in BACKGROUND_TONES:
            raise ServiceError(422, '底纹显示方式请选择柔和或原色')
        result['background_tone'] = tone
        density = selection.get('design_density', result.get('design_density', 'balanced'))
        if not isinstance(density, str) or density not in DESIGN_DENSITIES:
            raise ServiceError(422, '排列疏密请选择疏朗、均衡或丰富')
        if result.get('layout_engine') in QUALITY_LAYOUT_ENGINES:
            result['design_density'] = density
        elif density != 'balanced':
            raise ServiceError(422, '旧版作品保留原排版方式；如需选择疏密，请新建作品')
        if result.get('layout_engine') not in MODERN_LOOP_ENGINES and (selection.get('zone_background_refs') or selection.get('border_ref')):
            raise ServiceError(422, '此作品保留旧版排法；独立底纹和边饰可用于新作品')
        if selection.get('pattern_roles') and result.get('layout_engine') != LAYOUT_ENGINE:
            raise ServiceError(422, '此作品保留原排法；图案用途分工可用于新作品')
        if result.get('layout_engine') in MODERN_LOOP_ENGINES:
            from .ribbon_targets import configure_layers
            configure_layers(self, db, owner, selection, template['mode'], result, ids)
        result.update(asset_refs=ids, background_ref=selection['background_id'], template_id=template['id'], template_version=template['version'], template_mode=template['mode'], template_rules=json.loads(template['rules_json']), output_profile=profile)
        if result.get('layout_engine') in LOOP_ENGINES:
            result.setdefault('output_profile_source', copy.deepcopy(profile))
        result.pop('composite_ref', None)
        if base is None:
            # A named preset fills only what the client left at its defaults.
            # It writes existing fields, so old snapshots and the layout
            # engine stay untouched.
            from .design_style import STYLES, expand
            wanted = selection.get('design_style', 'classic')
            if not isinstance(wanted, str) or wanted not in STYLES:
                raise ServiceError(422, '请选择有效的设计风格')
            style, params, density, tone, slot_params = expand(
                wanted, result.get('pattern_slots') or [], result['params'],
                result.get('design_density', 'balanced'), result.get('background_tone', default_tone),
                density_given='design_density' in selection,
                tone_given='background_tone' in selection,
            )
            result['design_style'] = style
            result['params'] = params
            result['design_density'] = density
            result['background_tone'] = tone
            if slot_params:
                merged = dict(result.get('slot_params') or {})
                for slot, values in slot_params.items():
                    merged.setdefault(slot, {})
                    for key, value in values.items():
                        merged[slot].setdefault(key, value)
                result['slot_params'] = merged
        elif 'design_style' in selection:
            from .design_style import STYLES, restyle
            wanted = selection['design_style']
            if not isinstance(wanted, str) or wanted not in STYLES:
                raise ServiceError(422, '请选择有效的设计风格')
            previous = base.get('design_style', 'classic')
            if wanted != previous:
                if result.get('layout_engine') not in MODERN_LOOP_ENGINES:
                    raise ServiceError(422, '此旧版作品不支持更换风格，请新建作品试排')
                params, local, density, tone = restyle(previous, wanted, result.get('pattern_slots', []),
                    result['params'], result.get('slot_params', {}), result['design_density'], result['background_tone'],
                    density_given='design_density' in selection and selection['design_density'] != base.get('design_density', 'balanced'),
                    tone_given='background_tone' in selection and selection['background_tone'] != base.get('background_tone', 'original'))
                result.update(design_style=wanted, params=params, slot_params=local,
                              design_density=density, background_tone=tone)
        return result

    @leased_operation
    def candidates(self, owner, design_id, selection, styles=None):
        """Render one or more style proposals without creating a version or job.

        Each call renders the requested styles one at a time and returns them in
        order. The UI asks for a single style per request so the workspace can
        paint a progress bar and stay responsive while the strip is composed.
        Nothing here writes a version, quota event, snapshot or provider call.
        """
        wanted = styles or ['classic', 'hierarchy', 'airy']
        if not isinstance(wanted, list) or not 1 <= len(wanted) <= 4:
            raise ServiceError(422, '试排一次最多四种风格')
        from .design_style import STYLES

        for style in wanted:
            if not isinstance(style, str) or style not in STYLES:
                raise ServiceError(422, '请选择有效的设计风格')
        return [self.candidate(owner, design_id, selection, style) for style in wanted]

    def candidate(self, owner, design_id, selection, style):
        """Compose one style preview in memory (plus a temporary preview PNG)."""
        import tempfile

        from .design_style import STYLES
        from .imaging import render

        if not isinstance(style, str) or style not in STYLES:
            raise ServiceError(422, '请选择有效的设计风格')
        with self.db.connect() as db:
            base = None
            if design_id:
                design = self.owned_design(db, owner, design_id)
                if design['active_job_id']:
                    raise ServiceError(409, '作品正在处理，请等待当前任务结束')
                if design['current_version_id']:
                    row = db.execute('SELECT snapshot_json FROM versions WHERE id=? AND design_id=?',
                                     (design['current_version_id'], design_id)).fetchone()
                    if not row:
                        raise ServiceError(409, '当前版本不可用，请刷新作品')
                    base = json.loads(row['snapshot_json'])
            profile = copy.deepcopy(base.get('output_profile_source', base['output_profile'])) if base else json.loads(
                db.execute('SELECT profile_json FROM output_profiles WHERE active=1').fetchone()[0])
            snapshot = self.selection_snapshot(db, owner, {**selection, 'design_style': style}, profile, base)
            if snapshot.get('layout_engine') not in MODERN_LOOP_ENGINES:
                raise ServiceError(422, '试排只支持新版循环排版')
            cache_snapshot = {k: v for k, v in snapshot.items() if k not in ('seed', 'loop_layout')}
            aliases = {slot: 'asset:' + asset for slot, asset in zip(snapshot.get('pattern_slots', []), snapshot['asset_refs'])}
            cache_snapshot['pattern_slots'] = [aliases[slot] for slot in snapshot.get('pattern_slots', [])]
            for field in ('slot_params', 'pattern_roles'):
                cache_snapshot[field] = {aliases.get(slot, slot): value for slot, value in snapshot.get(field, {}).items()}
            key = hashlib.sha256(dump({'owner': owner, 'design': design_id,
                                      'version': design['current_version_id'] if design_id else None,
                                      'snapshot': cache_snapshot}).encode()).hexdigest()
            cached = self._candidate_cache.get(key)
            if cached is not None:
                for asset_id in self.snapshot_asset_ids(snapshot):
                    self.verified_asset_path(owner, asset_id)
                return {**cached, 'cached': True}

        if snapshot['layout_engine'] == 'seamless-unit-v3':
            from .loop_pipeline_v3 import resolve as resolve_loop
        else:
            from .loop_pipeline_v2 import resolve as resolve_loop
        resolve = lambda asset_id: self.verified_asset_path(owner, asset_id)
        snapshot = resolve_loop(snapshot, resolve)
        workspace = self.root / 'tmp'
        workspace.mkdir(parents=True, exist_ok=True)
        directory = Path(tempfile.mkdtemp(prefix='candidates-', dir=workspace))
        try:
            master = directory / 'master.png'
            preview = directory / 'preview.png'
            metadata = render(snapshot, resolve, master, preview, preview_only=True)
            with Image.open(preview) as image:
                image.thumbnail((640, 640), Image.Resampling.LANCZOS)
                buffer = io.BytesIO()
                image.convert('RGB').save(buffer, format='PNG', compress_level=6)
            loop = metadata['loop']
            row = dict(
                style=style,
                engine=snapshot['layout_engine'],
                label=STYLES[style]['label'],
                hint=STYLES[style]['hint'],
                image='data:image/png;base64,' + base64.b64encode(buffer.getvalue()).decode('ascii'),
                width=loop['width'],
                height=loop['height'],
                rhythm=loop['rhythm'],
            )
        finally:
            shutil.rmtree(directory, ignore_errors=True)
        self._remember_candidate(key, row)
        return row

    def _remember_candidate(self, key, row):
        with self._candidate_lock:
            self._candidate_cache[key] = row
            while len(self._candidate_cache) > 24:
                self._candidate_cache.pop(next(iter(self._candidate_cache)))

    def verified_draft_reference(self, code, mode, expected_sha=None):
        """Only an explicitly chosen, matching installed example may leave the host."""
        from hsd_tool.ribbon_examples import IMAGE_SPECS, MODE_GUIDES, eligible_ai_reference
        if not isinstance(code, str) or code not in IMAGE_SPECS or not eligible_ai_reference(code, mode) or not any(
                guide['mode'] == mode and code in guide['example_ids'] for guide in MODE_GUIDES):
            raise ServiceError(422, '参考案例与当前排版不匹配，请重新选择')
        fixed_sha = IMAGE_SPECS[code][3]
        if expected_sha is not None and expected_sha != fixed_sha:
            raise ServiceError(409, '参考案例版本已变化，请重新选择后提交')
        try:
            value = self.example_resolver(code) if self.example_resolver else None
        except Exception:
            value = None
        if not isinstance(value, bytes) or len(value) != IMAGE_SPECS[code][2] or digest(value) != fixed_sha:
            raise ServiceError(422, '参考案例暂不可用或校验失败，请重新选择')
        return value

    def prepare_ai_draft(self, db, owner, payload, settings):
        assisted = payload.get('ai_assisted', False)
        code = payload.get('reference_code')
        if type(assisted) is not bool or (code is not None and not isinstance(code, str)):
            raise ServiceError(422, 'AI 搭配及参考案例选项格式无效')
        if code is not None and not assisted:
            raise ServiceError(422, '选择参考案例前请启用 AI 搭配')
        if not assisted:
            return
        available = settings.provider == 'deepseek_seedream' and settings.ai_ready
        fixture = settings.provider == 'test' and self.settings.auth_mode == 'demo' and settings.enabled
        if not (available or fixture):
            raise ServiceError(503, 'AI 搭配尚未启用或真实服务未就绪，请联系管理员')
        snapshot = payload['snapshot']
        from .ribbon_targets import ZONES
        zones = ZONES.get(snapshot['template_mode'], ())
        if zones and all(z in snapshot.get('zone_background_refs', {}) for z in zones):
            raise ServiceError(422, '所有分区均已选独立底纹，请关闭 AI 搭配后生成，避免无效调用')
        if code is not None:
            payload['reference_sha256'] = digest(self.verified_draft_reference(code, snapshot['template_mode']))
        def identity(asset_id):
            row = self.accessible_asset(db, asset_id, owner)
            return dict(id=asset_id, sha256=row['sha256'])
        payload['ai_draft_inputs'] = dict(patterns=[identity(a) for a in snapshot['asset_refs']],
                                        background=identity(snapshot['background_ref']))

    def verified_ai_draft_sources(self, owner, snapshot, inputs):
        patterns, background = inputs.get('patterns'), inputs.get('background')
        if not isinstance(patterns, list) or [item.get('id') for item in patterns if isinstance(item, dict)] != snapshot['asset_refs'] or not isinstance(background, dict) or background.get('id') != snapshot['background_ref']:
            raise ServiceError(409, 'AI 首稿的素材绑定无效，未调用模型')
        paths = {}
        with self.db.connect() as db:
            for expected in [*patterns, background]:
                actual = self.accessible_asset(db, expected['id'], owner)
                if not expected.get('sha256') or actual['sha256'] != expected['sha256']:
                    raise ServiceError(409, 'AI 首稿的原素材已变化，未保存新版本')
                paths[expected['id']] = self.verified_file(actual['path'], expected['sha256'], 'AI 首稿原素材')
        return [paths[item['id']] for item in patterns], paths[background['id']]

    @leased_operation
    def submit(self, owner, kind, payload, design_id=None):
        key = payload.get('idempotency_key', '')
        if not isinstance(key, str) or not 8 <= len(key) <= 160:
            raise ServiceError(422, '需要有效的幂等键')
        request_hash = digest(dump(dict(kind=kind, design_id=design_id, payload=payload)).encode())
        with self.db.transaction() as db:
            expired = db.execute('SELECT request_hash FROM expired_requests WHERE owner_id=? AND idempotency_key=?', (owner, key)).fetchone()
            if expired:
                if expired['request_hash'] != request_hash:
                    raise ServiceError(409, '相同提交标识对应了不同内容，请重新提交')
                raise ServiceError(410, '这次提交已过保存期限，未再次调用模型；请新建任务')
            previous = db.execute('SELECT * FROM jobs WHERE owner_id=? AND idempotency_key=?', (owner, key)).fetchone()
            if previous:
                if previous['request_hash'] != request_hash:
                    raise ServiceError(409, '相同提交标识对应了不同内容，请重新提交')
                return self.job_public(previous)
            payload = copy.deepcopy(payload)
            settings = self.current_settings()
            payload['model_config'] = dict(language_model=settings.language_model, image_model=settings.image_model, image_quality=settings.image_quality, config_revision=getattr(settings, 'config_revision', ''))
            base_id = None
            if kind != 'background':
                design = self.owned_design(db, owner, design_id)
                if design['active_job_id']:
                    raise ServiceError(409, '作品正在处理，请等待当前任务结束')
                if kind == 'generate':
                    if design['current_version_id']:
                        raise ServiceError(409, '已有首稿，更改配置请使用精修')
                    payload['snapshot'] = self.selection_snapshot(db, owner, payload)
                    self.prepare_ai_draft(db, owner, payload, settings)
                else:
                    base_id = payload.get('base_version_id')
                    if not base_id or base_id != design['current_version_id']:
                        raise ServiceError(409, '当前版本已变化，请刷新后再精修')
                    if design['successful_refinement_count'] >= 2:
                        raise ServiceError(409, '两次精修已用完，仍可回退、查看和下载')
                    prompt = payload.get('prompt', '')
                    if not isinstance(prompt, str) or not 1 <= len(prompt.strip()) <= 2000:
                        raise ServiceError(422, '请输入 1–2000 字的修改要求')
                    version = db.execute('SELECT * FROM versions WHERE id=?', (base_id,)).fetchone()
                    snapshot = json.loads(version['snapshot_json'])
                    if payload.get('selection'):
                        snapshot = self.selection_snapshot(db, owner, payload['selection'], snapshot['output_profile'], snapshot)
                    payload['snapshot'] = snapshot
            else:
                if len(payload.get('prompt', '')) > 2000:
                    raise ServiceError(422, '底图要求最多 2000 字')
                if db.execute("SELECT COUNT(*) FROM jobs WHERE owner_id=? AND kind='background' AND status NOT IN ('SUCCEEDED','FAILED')", (owner,)).fetchone()[0] >= 1:
                    raise ServiceError(409, '底图正在生成，请稍后再试')
            job_id, stamp = uid(), now()
            db.execute('INSERT INTO jobs(id,owner_id,design_id,kind,idempotency_key,request_hash,payload_json,base_version_id,status,phase,provider,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)', (job_id, owner, design_id, kind, key, request_hash, dump(payload), base_id, 'QUEUED', '等待处理', settings.provider, stamp, stamp))
            db.execute('INSERT INTO outbox_events VALUES(?,?,NULL)', (job_id, stamp))
            if design_id:
                db.execute('UPDATE designs SET active_job_id=?,revision=revision+1 WHERE id=?', (job_id, design_id))
            return self.job_public(db.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone())

    @leased_operation
    def rollback(self, owner, design_id, expected):
        with self.db.transaction() as db:
            design = self.owned_design(db, owner, design_id)
            if design['active_job_id']:
                raise ServiceError(409, '处理中不能回退')
            if not expected or expected != design['current_version_id']:
                raise ServiceError(409, '当前版本已变化，请刷新')
            row = db.execute('SELECT parent_version_id FROM versions WHERE id=?', (expected,)).fetchone()
            if not row or not row[0]:
                raise ServiceError(409, '首稿没有上一版本')
            db.execute('UPDATE designs SET current_version_id=?,revision=revision+1,retained_at=? WHERE id=?', (row[0], time.time(), design_id))
        return self.design(owner, design_id)

    @leased_operation
    def version_file(self, owner, version_id, preview=False):
        with self.db.connect() as db:
            row = db.execute('SELECT v.* FROM versions v JOIN designs d ON d.id=v.design_id WHERE v.id=? AND d.owner_id=?', (version_id, owner)).fetchone()
        if not row:
            raise ServiceError(404, '版本不存在或无权访问')
        path = self.safe_path(row['preview_path' if preview else 'master_path'])
        expected = row['preview_sha256' if preview else 'master_sha256']
        if not expected or file_digest(path) != expected:
            raise ServiceError(409, '此版本的保存文件校验失败，请联系管理员')
        return path

    def safe_path(self, path):
        result = Path(path).resolve()
        if not result.is_relative_to(self.root) or not result.is_file():
            raise ServiceError(404, '保存文件不可用，请联系内部人员')
        return result

    def claim_job(self):
        with self.db.transaction() as db:
            row = db.execute("SELECT * FROM jobs WHERE status='QUEUED' OR (status IN ('RUNNING','RECONCILING') AND lease_until<?) ORDER BY created_at LIMIT 1", (time.time(),)).fetchone()
            if not row:
                return None
            job = dict(row)
            job['attempt'] += 1
            job['recovered'] = row['status'] != 'QUEUED'
            if job['recovered']:
                db.execute("UPDATE provider_calls SET status='UNKNOWN',error=? WHERE job_id=? AND status='STARTED' AND attempt<?",
                           (dump(diagnostic('interrupted', 'recovery')),job['id'],job['attempt']))
            job['lease_until'] = time.time() + self.settings.lease_seconds
            phase = '正在恢复任务' if job['recovered'] else '正在准备处理'
            db.execute("UPDATE jobs SET status='RUNNING',phase=?,attempt=?,lease_until=?,updated_at=? WHERE id=?", (phase, job['attempt'], job['lease_until'], now(), job['id']))
            db.execute('UPDATE outbox_events SET delivered_at=? WHERE job_id=?', (now(), job['id']))
            return job

    def phase(self, job, message):
        with self.db.transaction() as db:
            db.execute("UPDATE jobs SET phase=?,updated_at=? WHERE id=? AND attempt=? AND status='RUNNING'", (message, now(), job['id'], job['attempt']))

    def call_provider(self, job, operation, fn, *, render_snapshot=None, retry_provider=None):
        payload = json.loads(job['payload_json'])
        bound_render = render_snapshot if render_snapshot is not None else payload.get('snapshot')
        expected = estimate_render_space(bound_render) if bound_render else 0
        # Native model result plus an atomic/adapted copy. Recheck for every
        # operation; other HSD tasks may consume space while a model is waiting.
        self.check_space(self.root / 'jobs' / job['id'] / str(job['attempt']),
                         expected + 2 * png_space(MAX_PIXELS, 1))
        from hsd_tool.provider_diagnostics import normalize_details, safe_request_id
        from .providers import _safe_usage
        call_id = uid()
        start = time.monotonic()
        models = payload.get('model_config', {})
        model = models.get('language_model' if operation == 'plan' else 'image_model')
        # Commit first so a crash after the network write cannot erase the call.
        with self.db.transaction() as db:
            row = db.execute('SELECT attempt,status FROM jobs WHERE id=?', (job['id'],)).fetchone()
            if not row or row['attempt'] != job['attempt'] or row['status'] != 'RUNNING':
                raise ServiceError(409, '任务已变化，请刷新工作台。')
            db.execute('INSERT INTO provider_calls(id,job_id,attempt,operation,provider,model,elapsed_ms,status,created_at) '
                       'VALUES(?,?,?,?,?,?,0,?,?)', (call_id, job['id'], job['attempt'], operation, job['provider'], model, 'STARTED', now()))
        def record_retry(error):
            nonlocal call_id, start
            details = normalize_details(getattr(error, 'diagnostic', None))
            if getattr(error, 'uncertain_result', False) or details.get('category') != 'output_policy':
                raise error
            next_call = uid()
            with self.db.transaction() as db:
                row = db.execute('SELECT attempt,status FROM jobs WHERE id=?', (job['id'],)).fetchone()
                if not row or row['attempt'] != job['attempt'] or row['status'] != 'RUNNING':
                    raise ServiceError(409, '任务已变化，未再次调用图片服务。')
                db.execute("UPDATE provider_calls SET status='FAILED',error=?,request_id=?,usage_json=?,elapsed_ms=? WHERE id=?",
                    (dump(details), safe_request_id(getattr(error, 'request_id', None)), dump(_safe_usage(getattr(error, 'usage', {}))),
                     int((time.monotonic() - start) * 1000), call_id))
                db.execute('INSERT INTO provider_calls(id,job_id,attempt,operation,provider,model,elapsed_ms,status,created_at) '
                           'VALUES(?,?,?,?,?,?,0,?,?)', (next_call, job['id'], job['attempt'], operation, job['provider'], model, 'STARTED', now()))
            call_id, start = next_call, time.monotonic()
        previous_hook = getattr(retry_provider, '_image_retry_hook', None) if retry_provider is not None else None
        try:
            if retry_provider is not None:
                retry_provider._image_retry_hook = record_retry
            result = fn()
        except Exception as error:
            uncertain = getattr(error, 'uncertain_result', False)
            details = normalize_details(getattr(error, 'diagnostic', None)) if getattr(error, 'diagnostic', None) else diagnostic(
                'unknown_result' if uncertain else 'unclassified', 'transport' if uncertain else 'unknown')
            with self.db.transaction() as db:
                db.execute('UPDATE provider_calls SET status=?,error=?,request_id=?,usage_json=?,elapsed_ms=? WHERE id=?',
                           ('UNKNOWN' if uncertain else 'FAILED',dump(details), safe_request_id(getattr(error, 'request_id', None)),
                            dump(_safe_usage(getattr(error, 'usage', {}))), int((time.monotonic() - start) * 1000), call_id))
            raise
        finally:
            if retry_provider is not None:
                retry_provider._image_retry_hook = previous_hook
        meta = result if isinstance(result, dict) else {}
        with self.db.transaction() as db:
            db.execute("UPDATE provider_calls SET status='SUCCEEDED',model=?,request_id=?,usage_json=?,elapsed_ms=? WHERE id=?",
                       (meta.get('model') or model, safe_request_id(meta.get('request_id')), dump(_safe_usage(meta.get('usage', {}))),
                        int((time.monotonic() - start) * 1000), call_id))
        return result

    @staticmethod
    def validate_parameters(values, profile):
        ranges = {'scale': (0.2, 2.5), 'spacing': (0.4, 3), 'rotation': (-360, 360), 'offset_x': (-profile['width'], profile['width']), 'offset_y': (-profile['height'], profile['height'])}
        if not isinstance(values, dict) or not values or set(values) - (set(ranges) | {'background_color'}):
            raise ServiceError(422, '编辑计划包含不支持的参数')
        for key, value in values.items():
            if key == 'background_color':
                if value is not None and not re.fullmatch(r'#[0-9a-fA-F]{6}', str(value)):
                    raise ServiceError(422, '背景颜色必须是六位颜色值')
            elif not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or not ranges[key][0] <= value <= ranges[key][1]:
                raise ServiceError(422, '编辑参数超出可用范围')

    def effective_edit_operations(self, provider, snapshot, plan, selection_changed):
        """Validate the whole plan before executing any paid image edit.

        A planner's output is a proposal, not permission. Filter echoed defaults
        and reject impossible later operations before an earlier valid image
        edit could spend money or leave a partially applied modification.
        """
        from .providers import ClarificationNeeded, workflow_editing
        operations = plan.get('operations') if isinstance(plan, dict) else None
        if not isinstance(operations, list) or len(operations) > 8:
            raise ClarificationNeeded('请具体说明要调整的图案、参数或内容')
        editing = workflow_editing(provider, snapshot)
        initial = {**PARAM_DEFAULTS, **snapshot.get('params', {})}
        proposed = dict(initial)
        effective = []
        targets = set()
        background_edited = False
        for original in operations:
            if not isinstance(original, dict):
                raise ServiceError(422, '无法执行该编辑计划')
            operation = copy.deepcopy(original)
            kind = operation.get('type')
            if kind not in {'parameters', 'edit_asset', 'edit_background', 'edit_composite'}:
                raise ServiceError(422, '编辑计划包含不支持的操作')
            if kind not in editing['allowed_operations']:
                raise ClarificationNeeded(editing['composite_edit_reason'] or '当前版本不支持这项修改，请补充具体要求')
            if kind == 'parameters':
                values = operation.get('values')
                self.validate_parameters(values, snapshot['output_profile'])
                changed = {}
                for key, value in values.items():
                    current = proposed.get(key)
                    if key == 'background_color':
                        value = value.upper() if isinstance(value, str) else value
                        current = current.upper() if isinstance(current, str) else current
                    if value == current:
                        continue
                    if key not in editing['allowed_parameters']:
                        if key == 'spacing' and snapshot.get('template_mode') in NON_REPEATING_MODES:
                            raise ClarificationNeeded('该排版不使用重复间距；可调整大小、位置或旋转，无需调整间距')
                        raise ClarificationNeeded('当前排版不支持这项参数，请选择其它修改要求')
                    changed[key] = value
                    proposed[key] = value
                if not changed:
                    continue
                operation['values'] = changed
            else:
                prompt = operation.get('prompt', '')
                if not isinstance(prompt, str) or not prompt.strip() or not 1 <= len(prompt) <= 4000:
                    raise ServiceError(422, '内容编辑要求无效')
                if kind == 'edit_asset':
                    asset_id = operation.get('asset_id')
                    if asset_id not in snapshot['asset_refs']:
                        raise ServiceError(422, '编辑目标必须属于当前作品')
                    if asset_id in targets:
                        raise ClarificationNeeded('同一个图案的修改请合并成一条要求，避免重复生成')
                    targets.add(asset_id)
                elif kind == 'edit_background':
                    if background_edited:
                        raise ClarificationNeeded('同一底图的修改请合并成一条要求，避免重复生成')
                    background_edited = True
            effective.append(operation)
        if any(op['type'] == 'edit_composite' for op in effective) and len(effective) != 1:
            raise ClarificationNeeded('整幅修改不能与独立图案或参数修改混在同一次，请明确选择一种方式')
        if effective and all(op['type'] == 'parameters' for op in effective):
            # Two proposed changes that cancel each other are no net edit.
            original = dict(initial)
            if isinstance(original.get('background_color'), str):
                original['background_color'] = original['background_color'].upper()
            if proposed == original:
                effective = []
        if not effective and not selection_changed:
            message = '本次没有可执行的修改，请说明需要改变的大小、位置、底图或图案内容'
            if snapshot.get('template_mode') in NON_REPEATING_MODES and snapshot.get('layout_engine') not in LOOP_ENGINES:
                message += '；该排版不使用重复间距'
            raise ClarificationNeeded(message)
        return effective

    def refinement_selection_changed(self, job, payload, snapshot):
        if not payload.get('selection'):
            return False
        with self.db.connect() as db:
            row = db.execute('SELECT snapshot_json FROM versions WHERE id=? AND design_id=?',
                             (job['base_version_id'], job['design_id'])).fetchone()
        if row is None:
            raise ServiceError(409, '原版本已变化，请刷新后再精修')
        before = json.loads(row['snapshot_json'])
        fields = ('asset_refs', 'background_ref', 'zone_background_refs', 'border_ref', 'pattern_roles', 'design_style', 'template_id', 'template_version',
                  'template_mode', 'template_rules', 'composite_ref', 'pattern_roles')
        tone_changed = before.get('background_tone', 'original') != snapshot.get('background_tone', 'original')
        density_changed = before.get('design_density', 'balanced') != snapshot.get('design_density', 'balanced')
        return tone_changed or density_changed or any(before.get(key) != snapshot.get(key) for key in fields)

    def build_artifact(self, job, directory):
        from .imaging import render, validate_image
        from .providers import get_provider, ClarificationNeeded, workflow_editing
        payload = json.loads(job['payload_json'])
        needs_provider = job['kind'] == 'background' or (job['kind'] == 'generate' and payload.get('ai_assisted') is True) or (job['kind'] == 'refine' and not (payload.get('selection') and payload.get('prompt', '').strip() in ('应用所选配置', '应用新的素材与排版')))
        if needs_provider and self.settings.auth_mode == 'hsd' and job['provider'] == 'test':
            raise ServiceError(503, '尚未配置真实 AI 服务，请联系管理员')
        provider = None
        if needs_provider:
            provider = self.provider_factory(job['provider'], payload.get('model_config', {})) if self.provider_factory else get_provider(replace(self.settings, provider=job['provider'], **payload.get('model_config', {})))
        new_assets = []

        def derived(path, kind, name, original=None):
            with Image.open(path) as image:
                image.load()
                if image.width * image.height > 40_000_000:
                    raise ServiceError(422, '模型输出像素过大')
            result = dict(id=uid(), owner_id=job['owner_id'], name=name, kind=kind, path=str(path), sha256=digest(path.read_bytes()), source=provider.name, is_demo=provider.name == 'test', shared=False, derived_from=original, created_at=now())
            new_assets.append(result)
            return result['id']

        def resolve(asset_id):
            for asset in new_assets:
                if asset['id'] == asset_id:
                    return self.verified_file(asset['path'], asset['sha256'], '本次派生素材')
            return self.verified_asset_path(job['owner_id'], asset_id)

        def prepared_loop(value):
            if value.get('layout_engine') == LAYOUT_ENGINE:
                from .loop_pipeline_v3 import resolve as resolve_loop
            elif value.get('layout_engine') == 'seamless-unit-v2':
                from .loop_pipeline_v2 import resolve as resolve_loop
            else:
                from .loop_pipeline import resolve as resolve_loop
            try:
                return resolve_loop(value, resolve)
            except ValueError as error:
                # These are local bounded geometry checks, not provider bodies.
                raise ServiceError(422, str(error)) from None

        def call_model(operation, fn):
            bound = prepared_loop(snapshot) if snapshot.get('layout_engine') in LOOP_ENGINES else snapshot
            kwargs = {'retry_provider': provider} if operation != 'plan' and getattr(provider, 'output_retry_observable', False) else {}
            return self.call_provider(job, operation, fn, render_snapshot=bound, **kwargs)

        if job['kind'] == 'background':
            self.phase(job, '正在生成底图')
            path = directory / 'background.png'
            kwargs = {'retry_provider': provider} if getattr(provider, 'output_retry_observable', False) else {}
            metadata = self.call_provider(job, 'generate_background', lambda: provider.generate_background(payload.get('prompt', ''), path), **kwargs)
            asset_id = derived(path, 'background', 'AI 随机底图' if provider.name != 'test' else '演示随机底图')
            return dict(assets=new_assets, result_asset_id=asset_id, provider_metadata=metadata)

        snapshot = copy.deepcopy(payload['snapshot'])
        self.validate_layout_selection(snapshot['template_mode'], snapshot['asset_refs'], snapshot.get('layout_engine'))
        # Check immutable inputs before a paid planner/editor sees them. Recheck
        # when each input is opened and at commit; an old ID cannot silently
        # acquire different pixels while retaining its version provenance.
        for asset_id in self.snapshot_asset_ids(snapshot):
            resolve(asset_id)
        if snapshot.get('layout_engine') in LOOP_ENGINES:
            # Geometry/resource errors should precede any paid generation.
            snapshot = prepared_loop(snapshot)
        prompt, render_kind = '', 'layered'
        if job['kind'] == 'generate' and payload.get('ai_assisted') is True:
            inputs = payload.get('ai_draft_inputs') or {}
            # Every source and its immutable digest must pass before the first
            # image request; a bad later input cannot waste an earlier call.
            pattern_paths, background_path = self.verified_ai_draft_sources(job['owner_id'], snapshot, inputs)
            patterns, background = inputs['patterns'], inputs['background']
            original_bg = background['id']
            code = payload.get('reference_code')
            reference_bytes = None
            if code is not None:
                if not isinstance(payload.get('reference_sha256'), str):
                    raise ServiceError(409, 'AI 首稿的参考案例绑定无效，未调用模型')
                reference_bytes = self.verified_draft_reference(code, snapshot['template_mode'], payload['reference_sha256'])
            self.phase(job, '正在生成搭配底纹与辅助装饰，原图案保持不变')
            output = directory / 'draft-background.png'
            call_model('design_background', lambda: provider.generate_draft_background(
                pattern_paths, background_path, reference_bytes, output,
                mode=snapshot['template_mode'], density=snapshot.get('design_density', 'balanced'), prompt=''))
            with Image.open(output) as native:
                if native.size != (2048, 2048) or native.format != 'PNG' or native.mode not in ('RGB', 'RGBA'):
                    raise ServiceError(422, '首稿搭配底纹未达到原生 2048×2048 要求，未保存新版本')
                native.load()
                if native.mode == 'RGBA':
                    with native.getchannel('A') as alpha:
                        if alpha.getbbox() is None:
                            raise ServiceError(422, '首稿搭配底纹没有可见内容，未保存新版本')
            snapshot['background_ref'] = derived(output, 'background',
                'AI 首稿搭配底纹' if provider.name != 'test' else '测试替身首稿搭配底纹', original_bg)
            snapshot['ai_draft'] = dict(operation='design_background', provider=provider.name,
                original_background_ref=original_bg, reference_code=code,
                reference_sha256=payload.get('reference_sha256'), input_assets=[*patterns, background],
                full_canvas_redraw=False, redraws_original_patterns=False, is_demo=provider.name == 'test')
        if job['kind'] == 'refine':
            from .ribbon_targets import target_view, apply_values, check_parameter_effect
            prompt = payload['prompt']
            target = payload.get('edit_target', 'layout')
            view = target_view(snapshot, target)
            request_base = copy.deepcopy(snapshot)
            self.phase(job, '正在理解修改要求')
            with self.db.connect() as db:
                assets = [self.asset_public(self.accessible_asset(db, a, job['owner_id'])) for a in view['asset_refs']]
            if not needs_provider:
                plan = {'operations': [], 'summary': '应用所选配置', 'local_selection_only': True}
            else:
                plan = call_model('plan', lambda: provider.plan(prompt, view, assets))
            selection_changed = self.refinement_selection_changed(job, payload, snapshot)
            has_contract = isinstance(plan, dict) and ('requirements' in plan or 'request_contract' in plan)
            if needs_provider and (job['provider'] != 'test' or has_contract):
                from .request_contract import validate_request_plan
                plan = validate_request_plan(prompt, view, plan, job['provider'])
                plan['request_contract']['planned_operations'] = copy.deepcopy(plan['operations'])
            operations = self.effective_edit_operations(job['provider'], view, plan, selection_changed)
            if needs_provider and not has_contract and job['provider'] == 'test':
                # Explicit historical test fixtures are not production NLU or
                # evidence of request coverage. Real providers cannot use it.
                from .background_edit import background_edit_request
                operations, request_protection = background_edit_request(prompt, view, operations)
                plan = {**plan, 'request_protection': request_protection}
            plan = {**plan, 'operations': operations}
            # Validate every independent image source before the first paid
            # image request. A later oversized/unsupported input must not waste
            # an earlier otherwise valid generation and then discard it.
            prepared_backgrounds = {}
            trial = copy.deepcopy(snapshot)
            visible_params = dict(view['params'])
            background_generated = False
            for index, operation in enumerate(operations):
                kind = operation['type']
                if kind == 'parameters':
                    if background_generated and operation['values'].get('background_color') is not None:
                        raise ClarificationNeeded('后面的纯色设置会盖住本次生成的底纹，请合并底纹要求后再提交；未调用图片模型、未扣精修次数。')
                    if trial.get('layout_engine') in MODERN_LOOP_ENGINES:
                        if trial.get('layout_engine') == LAYOUT_ENGINE:
                            from .loop_layout_v3 import resolve as geometry_only
                        else:
                            from .loop_layout_v2 import resolve as geometry_only
                        specs = trial['loop_layout']['specs']
                        before = copy.deepcopy(trial)
                        apply_values(trial, target, operation['values'])
                        after = geometry_only(trial, specs=specs)
                        for key, value in operation['values'].items():
                            other = copy.deepcopy(before)
                            remaining = {k: v for k, v in operation['values'].items() if k != key}
                            if remaining:
                                apply_values(other, target, remaining)
                            check_parameter_effect(geometry_only(other, specs=specs), after, target, {key:value})
                        if has_contract or job['provider'] != 'test':
                            from .request_geometry import validate_request_geometry
                            validate_request_geometry(before, after, operation, target)
                        trial = after
                    visible_params.update(operation['values'])
                elif kind == 'edit_asset':
                    prepared = provider.validate_edit_input(resolve(operation['asset_id']), 'asset')
                    if has_contract or job['provider'] != 'test':
                        from .request_geometry import validate_request_image_policy
                        validate_request_image_policy(operation['prompt'], prepared)
                elif kind == 'edit_background':
                    background_generated = True
                    if target == 'layout' and snapshot.get('layout_engine') in MODERN_LOOP_ENGINES:
                        target_view(snapshot, 'background')
                    source = resolve(view['background_ref'])
                    if visible_params.get('background_color'):
                        # Validate the image that is actually visible, including
                        # an opaque override of an otherwise transparent asset.
                        with Image.open(source) as background_image:
                            visible = Image.new('RGBA', background_image.size, visible_params['background_color'])
                        source = directory / f'before-background-{index}.png'
                        try:
                            _save_png(visible, source)
                        finally:
                            visible.close()
                        prepared_backgrounds[index] = (source, file_digest(source))
                    prepared = provider.validate_edit_input(source, 'background')
                    if has_contract or job['provider'] != 'test':
                        from .request_geometry import validate_request_image_policy
                        validate_request_image_policy(operation['prompt'], prepared)
                    visible_params['background_color'] = None
            for index, operation in enumerate(operations):
                kind = operation.get('type')
                if kind == 'parameters':
                    apply_values(snapshot, target, operation['values'])
                elif kind in ('edit_asset', 'edit_background', 'edit_composite'):
                    self.phase(job, {'edit_asset': '正在修改图案', 'edit_background': '正在修改底图',
                                     'edit_composite': '正在修改整幅画面'}[kind])
                    edit_prompt = operation.get('prompt', '')
                    if not isinstance(edit_prompt, str) or not 1 <= len(edit_prompt) <= 4000:
                        raise ServiceError(422, '内容编辑要求无效')
                    if kind == 'edit_asset':
                        original = operation.get('asset_id')
                        if original not in view['asset_refs']:
                            raise ServiceError(422, '编辑目标必须属于当前作品')
                        source = resolve(original)
                        asset_kind = 'pattern'
                    elif kind == 'edit_background':
                        original = view['background_ref']
                        source = resolve(original)
                        asset_kind = 'background'
                        if index in prepared_backgrounds:
                            # Reuse the exact visible image checked before any
                            # image request, rather than its older hidden texture.
                            prepared, expected = prepared_backgrounds[index]
                            source = self.verified_file(prepared, expected, '当前可见底图')
                        if target.startswith('zone:'):
                            snapshot.setdefault('zone_colors', {}).pop(target[5:], None)
                        else:
                            snapshot['params']['background_color'] = None
                    else:
                        # Flatten the actual full-resolution current composition, never the preview.
                        source = directory / f'before-composite-{index}.png'
                        render(snapshot, resolve, source, directory / f'before-preview-{index}.png')
                        original, asset_kind = snapshot.get('composite_ref'), 'composite'
                    output = directory / f'edited-{index}.png'
                    def checked_edit():
                        meta = provider.edit_image(edit_prompt, source, output, kind.removeprefix('edit_'))
                        if snapshot.get('layout_engine') in MODERN_LOOP_ENGINES:
                            from .edit_quality import validate_edit_result
                            from .providers import ProviderError
                            try:
                                validate_edit_result(source, output, target=kind.removeprefix('edit_'))
                            except ProviderError as error:
                                # Retain confirmed model usage and request identity even
                                # when a local result check rejects the returned image.
                                error.request_id = meta.get('request_id')
                                error.usage = meta.get('usage', {})
                                raise
                        return meta
                    call_model(kind, checked_edit)
                    replacement = derived(output, asset_kind, '精修派生素材', original)
                    if kind == 'edit_asset':
                        if target == 'border':
                            snapshot['border_ref'] = replacement
                        else:
                            snapshot['asset_refs'] = [replacement if a == original else a for a in snapshot['asset_refs']]
                    elif kind == 'edit_background':
                        if target.startswith('zone:'):
                            snapshot['zone_background_refs'][target[5:]] = replacement
                        else:
                            snapshot['background_ref'] = replacement
                    else:
                        snapshot['composite_ref'] = replacement
                        snapshot['params'] = dict(scale=1.0, spacing=1.0, rotation=0.0, offset_x=0.0, offset_y=0.0, background_color=None)
                        render_kind = 'composite'
                else:
                    raise ServiceError(422, '编辑计划包含不支持的操作')
            snapshot['edit_plan'] = {**plan, 'target': target}
        render_kind = 'composite' if snapshot.get('composite_ref') else 'layered'
        self.phase(job, '正在合成并检查循环单元' if snapshot.get('layout_engine') in LOOP_ENGINES else '正在合成并检查保存文件')
        if snapshot.get('layout_engine') in LOOP_ENGINES:
            # New backgrounds, content proportions and numeric edits can all
            # change the complete period. Never reuse a parent's old width.
            snapshot = prepared_loop(snapshot)
        if job['kind'] == 'refine' and snapshot.get('edit_plan', {}).get('request_contract'):
            from .request_contract import public_request_receipt
            from .request_geometry import validate_request_geometry
            for operation in snapshot['edit_plan']['operations']:
                if operation['type'] == 'parameters':
                    validate_request_geometry(request_base, snapshot, operation, target)
            snapshot['edit_plan']['request_receipt'] = public_request_receipt(
                snapshot['edit_plan'], geometry_verified=snapshot.get('layout_engine') == 'seamless-unit-v2')
        master, preview = directory / 'master.png', directory / 'preview.png'
        try:
            metadata = render(snapshot, resolve, master, preview)
        except ValueError as error:
            if snapshot.get('layout_engine') in LOOP_ENGINES:
                raise ServiceError(422, str(error)) from None
            raise
        if snapshot.get('layout_engine') in LOOP_ENGINES:
            snapshot['loop'] = metadata['loop']
            snapshot['loop']['output_sha256'] = file_digest(master)
            snapshot['loop']['inputs'] = [dict(id=a, sha256=file_digest(resolve(a))) for a in loop_inputs(snapshot)]
        snapshot['object_transforms'] = metadata.get('object_transforms', [])
        snapshot['local_patches'] = []
        capabilities = {'parameters': 'parameters', 'edit_asset': 'asset_edit',
                        'edit_background': 'background_edit', 'edit_composite': 'composite_edit'}
        snapshot['capabilities'] = [capabilities[operation] for operation in
                                  workflow_editing(job['provider'], snapshot)['allowed_operations']]
        validate_image(master, snapshot['output_profile'])
        with Image.open(preview) as image:
            image.load()
        return dict(assets=new_assets, version_id=uid(), snapshot=snapshot, master_path=str(master), preview_path=str(preview), master_sha256=file_digest(master), preview_sha256=file_digest(preview), prompt=prompt, render_kind=render_kind)

    def checkpoint(self, job, artifact, directory):
        self.check_space(directory, len(dump(artifact).encode('utf-8')) + 1024 * 1024)
        manifest = directory / 'artifact.json'
        temp = directory / 'artifact.tmp'
        with temp.open('w', encoding='utf-8') as stream:
            stream.write(dump(artifact))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, manifest)
        with self.db.transaction() as db:
            db.execute("UPDATE jobs SET artifact_json=?,phase='文件已保存，正在提交版本',updated_at=? WHERE id=? AND attempt=? AND status='RUNNING'", (dump(artifact), now(), job['id'], job['attempt']))

    def verify_refinement_request(self, job, artifact):
        """Recheck immutable request bindings on ordinary commit and recovery."""
        from .request_contract import validate_request_plan, public_request_receipt
        from .request_geometry import validate_request_geometry
        from .ribbon_targets import target_view, apply_values
        from .providers import ClarificationNeeded

        payload = json.loads(job['payload_json'])
        local_selection = payload.get('selection') and payload.get('prompt', '').strip() in ('应用所选配置', '应用新的素材与排版')
        plan = artifact['snapshot'].get('edit_plan', {})
        contract = plan.get('request_contract')
        if not contract:
            if job['provider'] != 'test' and not local_selection:
                raise ClarificationNeeded('缺少本次原文执行记录，未保存、未扣精修次数。')
            return
        if local_selection or plan.get('target') != payload.get('edit_target', 'layout'):
            raise ServiceError(422, '精修要求与保存目标不一致')
        base = copy.deepcopy(payload['snapshot'])
        if base.get('layout_engine') in LOOP_ENGINES:
            if base['layout_engine'] == 'seamless-unit-v3':
                from .loop_pipeline_v3 import resolve
            elif base['layout_engine'] == 'seamless-unit-v2':
                from .loop_pipeline_v2 import resolve
            else:
                from .loop_pipeline import resolve
            base = resolve(base, lambda a: self.verified_asset_path(job['owner_id'], a))
        target = payload.get('edit_target', 'layout')
        view = target_view(base, target)
        wire = {key: plan.get(key) for key in ('summary', 'clarification', 'requirements')}
        wire['operations'] = contract.get('planned_operations')
        verified = validate_request_plan(payload['prompt'], view, wire, job['provider'])
        verified['request_contract']['planned_operations'] = copy.deepcopy(verified['operations'])
        if dump(contract) != dump(verified['request_contract']):
            raise ServiceError(422, '精修原文执行记录校验失败')
        operations = self.effective_edit_operations(job['provider'], view, verified,
            self.refinement_selection_changed(job, payload, base))
        if dump(operations) != dump(plan.get('operations')):
            raise ServiceError(422, '保存的精修操作与原文执行记录不一致')
        expected_state = copy.deepcopy(base)
        remaining = list(artifact.get('assets', []))
        for operation in operations:
            kind = operation['type']
            if kind == 'parameters':
                apply_values(expected_state, target, operation['values'])
                continue
            original = (operation.get('asset_id') if kind == 'edit_asset' else
                        view['background_ref'] if kind == 'edit_background' else base.get('composite_ref'))
            asset_kind = {'edit_asset': 'pattern', 'edit_background': 'background', 'edit_composite': 'composite'}[kind]
            candidates = [a for a in remaining if a.get('derived_from') == original and a.get('kind') == asset_kind
                          and a.get('owner_id') == job['owner_id']]
            if len(candidates) != 1:
                raise ServiceError(422, '图片结果与本次精修目标不一致')
            replacement = candidates[0]['id']
            remaining.remove(candidates[0])
            if kind == 'edit_asset':
                if target == 'border':
                    expected_state['border_ref'] = replacement
                else:
                    expected_state['asset_refs'] = [replacement if a == original else a for a in expected_state['asset_refs']]
            elif kind == 'edit_background':
                if target.startswith('zone:'):
                    expected_state['zone_background_refs'][target[5:]] = replacement
                    expected_state.setdefault('zone_colors', {}).pop(target[5:], None)
                else:
                    expected_state['background_ref'] = replacement
                    expected_state['params']['background_color'] = None
            else:
                expected_state['composite_ref'] = replacement
                expected_state['params'] = dict(PARAM_DEFAULTS)
        protected = ('params', 'slot_params', 'zone_colors', 'asset_refs', 'background_ref',
                     'zone_background_refs', 'border_ref', 'composite_ref', 'pattern_slots',
                     'layout_engine', 'template_id', 'template_mode', 'template_version', 'template_rules',
                     'seed', 'design_density', 'background_tone', 'pattern_roles', 'design_style', 'output_profile_source')
        if remaining or any(expected_state.get(key) != artifact['snapshot'].get(key) for key in protected):
            raise ServiceError(422, '实际参数或图层结果与本次原文执行计划不一致')
        for operation in operations:
            if operation['type'] == 'parameters':
                validate_request_geometry(base, artifact['snapshot'], operation, target)
        expected = public_request_receipt(verified, geometry_verified=base.get('layout_engine') == 'seamless-unit-v2')
        if plan.get('request_receipt') != expected:
            raise ServiceError(422, '精修结果说明与原文执行记录不一致')

    def complete_job(self, job, artifact):
        from .imaging import validate_image
        payload = json.loads(job['payload_json'])
        if job['kind'] == 'generate' and payload.get('ai_assisted') is True:
            # The original background was replaced in the rendered snapshot,
            # so retain and recheck its provenance explicitly at commit too.
            self.verified_ai_draft_sources(job['owner_id'], payload['snapshot'], payload['ai_draft_inputs'])
        if job['kind'] != 'background':
            master = self.safe_path(artifact['master_path'])
            if digest(master.read_bytes()) != artifact['master_sha256']:
                raise ServiceError(422, '保存结果校验失败')
            validate_image(master, artifact['snapshot']['output_profile'])
            if artifact['snapshot'].get('layout_engine') in LOOP_ENGINES:
                if artifact['snapshot'].get('layout_engine') == LAYOUT_ENGINE:
                    from .loop_pipeline_v3 import validate_binding
                elif artifact['snapshot'].get('layout_engine') == 'seamless-unit-v2':
                    from .loop_pipeline_v2 import validate_binding
                else:
                    from .loop_pipeline import validate_binding
                validate_binding(artifact['snapshot'], artifact['master_sha256'])
            preview = self.safe_path(artifact['preview_path'])
            if not artifact.get('preview_sha256') or file_digest(preview) != artifact['preview_sha256']:
                raise ServiceError(422, '保存预览校验失败')
        for asset in artifact['assets']:
            if digest(self.safe_path(asset['path']).read_bytes()) != asset['sha256']:
                raise ServiceError(422, '保存素材校验失败')
        if artifact.get('snapshot'):
            new_ids = {asset['id'] for asset in artifact['assets']}
            for asset_id in self.snapshot_asset_ids(artifact['snapshot']) - new_ids:
                self.verified_asset_path(job['owner_id'], asset_id)
            saved = artifact['snapshot']
            if saved.get('layout_engine') in LOOP_ENGINES:
                identities = {a['id']: a['sha256'] for a in artifact['assets']}
                with self.db.connect() as db:
                    bound = []
                    for a in loop_inputs(saved):
                        sha = identities.get(a)
                        if sha is None:
                            sha = self.accessible_asset(db, a, job['owner_id'])['sha256']
                        bound.append(dict(id=a, sha256=sha))
                if saved['loop'].get('inputs') != bound:
                    raise ServiceError(422, '循环素材来源与保存版本不一致')
        if job['kind'] == 'refine':
            self.verify_refinement_request(job, artifact)
            # Also applies to a recovered immutable artifact. A numeric edit
            # may quantise to the same raster, or a model may return a copy.
            # Neither may create a version or consume the successful quota.
            from .providers import ClarificationNeeded
            original = self.version_file(job['owner_id'], job['base_version_id'])
            if same_rgba_pixels(original, master):
                raise ClarificationNeeded('本次结果与原图像素相同，未保存新版本，也未扣精修次数；请调整幅度或说明具体修改要求')
        with self.db.transaction() as db:
            actual = db.execute('SELECT * FROM jobs WHERE id=?', (job['id'],)).fetchone()
            if actual['attempt'] != job['attempt'] or actual['status'] not in ('RUNNING', 'RECONCILING'):
                return False
            if actual['lease_until'] < time.time():
                return False
            if job['design_id']:
                design = self.owned_design(db, job['owner_id'], job['design_id'])
                if design['active_job_id'] != job['id'] or design['current_version_id'] != job['base_version_id']:
                    raise ServiceError(409, '任务基准版本失效，原版本已保留')
                if job['kind'] == 'refine' and design['successful_refinement_count'] >= 2:
                    raise ServiceError(409, '精修次数已用完')
            for asset in artifact['assets']:
                self.insert_asset(db, asset)
            version_id = artifact.get('version_id')
            if version_id:
                sequence = db.execute('SELECT COALESCE(MAX(sequence),-1)+1 FROM versions WHERE design_id=?', (job['design_id'],)).fetchone()[0]
                db.execute('INSERT INTO versions(id,design_id,parent_version_id,sequence,snapshot_json,preview_path,master_path,master_sha256,prompt,render_kind,provider,job_id,created_at,preview_sha256) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)', (version_id, job['design_id'], job['base_version_id'], sequence, dump(artifact['snapshot']), artifact['preview_path'], artifact['master_path'], artifact['master_sha256'], artifact['prompt'], artifact['render_kind'], job['provider'], job['id'], now(), artifact['preview_sha256']))
                charge = int(job['kind'] == 'refine')
                if charge:
                    db.execute('INSERT INTO quota_events VALUES(?,?,?)', (job['id'], job['design_id'], now()))
                db.execute('UPDATE designs SET current_version_id=?,successful_refinement_count=successful_refinement_count+?,active_job_id=NULL,revision=revision+1,retained_at=? WHERE id=?', (version_id, charge, time.time(), job['design_id']))
            db.execute("UPDATE jobs SET status='SUCCEEDED',phase='已保存',result_version_id=?,result_asset_id=?,artifact_json=?,lease_until=NULL,error=NULL,updated_at=?,settled_at=? WHERE id=?", (version_id, artifact.get('result_asset_id'), dump(artifact), now(), time.time(), job['id']))
            return True

    def fail_job(self, job, error, clarification=False):
        with self.db.transaction() as db:
            changed = db.execute("UPDATE jobs SET status='FAILED',phase=?,error=?,needs_clarification=?,lease_until=NULL,updated_at=?,settled_at=? WHERE id=? AND attempt=? AND status IN ('RUNNING','RECONCILING')", ('需要补充说明' if clarification else '处理失败，未扣次数', error[:500], int(clarification), now(), time.time(), job['id'], job['attempt'])).rowcount
            if changed and job['design_id']:
                db.execute('UPDATE designs SET active_job_id=NULL,revision=revision+1 WHERE id=? AND active_job_id=?', (job['design_id'], job['id']))

    @leased_operation
    @guarded_file_operations
    def process_job(self, job):
        from .providers import ClarificationNeeded, ProviderError
        directory = self.root / 'jobs' / job['id'] / str(job['attempt'])
        try:
            self.check_space(directory, 1024 * 1024)
            directory.mkdir(parents=True, exist_ok=True)
            artifact = json.loads(job['artifact_json']) if job.get('artifact_json') else None
            if artifact is None and job.get('recovered'):
                manifests = list(directory.parent.glob('*/artifact.json'))
                manifests.sort(key=lambda p: int(p.parent.name), reverse=True)
                if manifests:
                    artifact = json.loads(manifests[0].read_text(encoding='utf-8'))
                elif (job['provider'] != 'test' and job['kind'] != 'generate') or (job['kind'] == 'generate' and json.loads(job['payload_json']).get('ai_assisted') is True):
                    raise ProviderError('上次模型调用因进程中断结果未知，未自动重复调用；原版本与额度保留，请核对后重新提交')
            if artifact is None:
                artifact = self.build_artifact(job, directory)
            self.checkpoint(job, artifact, directory)
            self.complete_job(job, artifact)
        except sqlite3.Error:
            # Artifacts are immutable. Recovery retries only the commit when the manifest exists.
            log.warning('Job database commit deferred: %s', job['id'])
            try:
                with self.db.transaction() as db:
                    db.execute("UPDATE jobs SET status='RECONCILING',phase='保存确认中，正在恢复',lease_until=?,updated_at=? WHERE id=? AND attempt=? AND status='RUNNING'", (time.time()-1, now(), job['id'], job['attempt']))
            except sqlite3.Error:
                log.error('Database temporarily unavailable; lease recovery will retry')
        except ClarificationNeeded as error:
            self.fail_job(job, str(error), True)
        except (ProviderError, ServiceError) as error:
            self.fail_job(job, str(error))
        except OSError as error:
            self.fail_job(job, '存储空间不足，请清理后重试；原版本已保留，本次未扣次数' if disk_full(error) else '文件无法保存，原结果已保留，本次未扣次数')
        except Exception as error:
            # Do not expose provider response bodies or credentials in logs or client messages.
            log.error('Job failed: %s (%s)', job['id'], type(error).__name__)
            self.fail_job(job, '图像处理或保存失败，原结果已保留，本次未扣次数')

    def run_once(self):
        job = self.claim_job()
        if not job:
            return False
        heartbeat_stop = threading.Event()

        def heartbeat():
            while not heartbeat_stop.wait(max(1, self.settings.lease_seconds / 3)):
                try:
                    with self.db.transaction() as db:
                        db.execute("UPDATE jobs SET lease_until=? WHERE id=? AND attempt=? AND status='RUNNING'", (time.time()+self.settings.lease_seconds, job['id'], job['attempt']))
                except sqlite3.Error:
                    pass

        thread = threading.Thread(target=heartbeat, daemon=True)
        thread.start()
        try:
            self.process_job(job)
        finally:
            heartbeat_stop.set()
            thread.join(timeout=2)
        return True

    def worker_loop(self):
        last_cleanup = 0
        while not self.stop_event.is_set():
            try:
                if time.monotonic() - last_cleanup >= 600:
                    try:
                        self.cleanup_expired()
                    except (OSError, ValueError):
                        log.warning('Private-data cleanup postponed; files retained')
                    last_cleanup = time.monotonic()
                if not self.run_once():
                    self.stop_event.wait(0.5)
            except sqlite3.Error:
                self.stop_event.wait(2)

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.stop_event.clear()
        self.thread = threading.Thread(target=self.worker_loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:
            # Drain an accepted paid operation; never close the database underneath
            # it or launch a second worker while the previous call is unresolved.
            self.thread.join()

    def admin_overview(self):
        with self.db.connect() as db:
            jobs = [self.job_public(row) for row in db.execute('SELECT * FROM jobs ORDER BY created_at DESC LIMIT 100')]
            profiles = [json.loads(row[0]) for row in db.execute('SELECT profile_json FROM output_profiles ORDER BY version DESC')]
            users = [dict(row) for row in db.execute('SELECT id,username,role FROM users')]
            calls = [call_view(row) for row in db.execute('SELECT * FROM provider_calls ORDER BY created_at DESC LIMIT 100')]
        return dict(jobs=jobs, templates=self.templates(), output_profiles=profiles, users=users, provider_calls=calls)

    @guarded_file_operations
    @memory_bounded_operation
    def save_template(self, body):
        from .imaging import template_thumbnail
        mode = body.get('mode')
        if mode not in MODES or not body.get('name') or len(body['name']) > 80:
            raise ServiceError(422, '模板名称或模式无效')
        rules = body.get('rules', {})
        if not isinstance(rules, dict) or set(rules) - {'rows', 'step_ratio', 'motif_ratio', 'is_demo'}:
            raise ServiceError(422, '模板规则支持 rows、step_ratio 与 motif_ratio')
        if mode in EXTENDED_MODES and ('rows' in rules or (mode in NON_REPEATING_MODES and 'step_ratio' in rules)):
            raise ServiceError(422, '该排版行数固定，整幅定位和两端留白不使用重复间距；请移除不适用的规则')
        for key, value in rules.items():
            if key == 'is_demo':
                if type(value) is not bool:
                    raise ServiceError(422, '模板示例标记无效')
                continue
            low, high = {'rows': (1, 4), 'step_ratio': (0.2, 2), 'motif_ratio': (0.05, 0.8)}[key]
            if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high or (key == 'rows' and type(value) is not int):
                raise ServiceError(422, '模板规则超出允许范围')
        template_id = body.get('id') or uid()
        if not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', template_id):
            raise ServiceError(422, '模板标识无效')
        with self.db.transaction() as db:
            version = db.execute('SELECT COALESCE(MAX(version),0)+1 FROM templates WHERE id=?', (template_id,)).fetchone()[0]
            path = self.root / 'templates' / f'{template_id}-{version}.png'
            template_thumbnail(mode, path, rules)
            db.execute('INSERT INTO templates(id,version,name,mode,rules_json,enabled,thumbnail_path,thumbnail_sha256) VALUES(?,?,?,?,?,?,?,?)', (template_id, version, body['name'], mode, dump(rules), int(body.get('enabled', True)), str(path), file_digest(path)))
        return next(t for t in self.templates() if t['id'] == template_id)

    def save_profile(self, body):
        if body.get('format', 'PNG') != 'PNG' or not body.get('name') or len(body['name']) > 80:
            raise ServiceError(422, '当前导出支持 PNG；请填写配置名称')
        width, height, dpi = body.get('width'), body.get('height'), body.get('dpi')
        if any(type(v) is not int for v in (width, height, dpi)) or not (64 <= width <= 16000 and 64 <= height <= 5000 and width*height <= 40_000_000 and 72 <= dpi <= 1200):
            raise ServiceError(422, '输出参数超出支持范围')
        with self.db.transaction() as db:
            version = db.execute('SELECT COALESCE(MAX(version),0)+1 FROM output_profiles').fetchone()[0]
            profile = dict(id=uid(), version=version, name=body['name'], width=width, height=height, dpi=dpi, format='PNG', is_demo=bool(body.get('is_demo', True)))
            db.execute('UPDATE output_profiles SET active=0')
            db.execute('INSERT INTO output_profiles VALUES(?,?,?,?,1)', (profile['id'], version, profile['name'], dump(profile)))
        return profile
