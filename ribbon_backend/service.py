"""Durable single-host job service. Files precede a fenced, atomic version commit."""
from __future__ import annotations

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

from .config import Settings
from .db import Database
from .imaging import memory_bounded_operation, disk_space_guard, png_space, estimate_render_space, STANDALONE_FREE_MARGIN, MAX_PIXELS, _save_png

log = logging.getLogger(__name__)
MODES = {'grid': '整齐平铺', 'stagger': '错位平铺', 'scatter': '随机散点', 'single': '单排重复', 'ends': '两端主图', 'panels': '分区拼接',
         'bordered': '上下边饰', 'scene': '组合循环', 'fullwidth': '整幅定位',
         'alternating': '大小交替', 'ends_open': '两端留白', 'split': '左右分区',
         'stacked': '上下分区', 'opposed': '正倒交替'}
EXTENDED_MODES = frozenset({'bordered', 'scene', 'fullwidth', 'alternating', 'ends_open', 'split', 'stacked', 'opposed'})
NON_REPEATING_MODES = frozenset({'fullwidth', 'ends_open'})
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
    def __init__(self, settings: Settings, runtime_settings_supplier=None, provider_factory=None):
        self.settings = settings
        self.runtime_settings_supplier = runtime_settings_supplier
        self.provider_factory = provider_factory
        self.root = settings.data_dir
        if self.root.resolve() == Path(self.root.anchor):
            raise ServiceError(507, '请为丝带功能设置专用数据目录，不能使用磁盘根目录')
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = Database(self.root / 'ribbon.sqlite3')
        from .retention import registry_for
        self._leases = registry_for(self.root)
        self.stop_event = threading.Event()
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
    def validate_layout_selection(mode, asset_ids):
        if mode == 'bordered' and len(asset_ids) < 2:
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
        with self.db.connect() as db:
            profile = json.loads(db.execute('SELECT profile_json FROM output_profiles WHERE active=1').fetchone()[0])
        settings = self.current_settings()
        return dict(provider=settings.provider, ai_ready=settings.ai_ready, auth_mode=self.settings.auth_mode, output_profile={k: profile[k] for k in ('id', 'version', 'name', 'is_demo')}, max_refinements=2,
                    retention_hours=self.settings.retention_seconds // 3600)

    def asset_public(self, row):
        return {**{k: row[k] for k in ('id', 'name', 'kind', 'source', 'derived_from')}, 'is_demo': bool(row['is_demo']), 'shared': bool(row['shared']), 'url': f"{getattr(self.settings, 'api_prefix', '/api')}/assets/{row['id']}/file"}

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
        return set(snapshot.get('asset_refs', [])) | {
            snapshot[key] for key in ('background_ref', 'composite_ref') if snapshot.get(key)
        }

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
        self.store_uploaded_image(data, path)
        asset = dict(id=asset_id, owner_id=user['id'], name=(name or '上传素材')[:80], kind=kind, path=str(path), sha256=file_digest(path), source='upload', is_demo=False, shared=shared, derived_from=None)
        with self.db.transaction() as db:
            self.insert_asset(db, asset)
        return self.asset_public(asset)

    @memory_bounded_operation
    def store_uploaded_image(self, data, path):
        # Never take the database write lock while holding this allocation lock:
        # template generation and retention have their own transaction ordering.
        try:
            with Image.open(io.BytesIO(data)) as original:
                if original.format not in ('PNG', 'JPEG', 'WEBP') or original.width * original.height > 40_000_000:
                    raise ValueError('Unsupported image')
                self.check_space(path.parent, png_space(*original.size))
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
            _save_png(img, path, dpi=None)
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

    def owned_design(self, db, owner, design_id):
        row = db.execute('SELECT * FROM designs WHERE id=? AND owner_id=?', (design_id, owner)).fetchone()
        if not row:
            raise ServiceError(404, '作品不存在或无权访问')
        return dict(row)

    def version_public(self, row):
        prefix = getattr(self.settings, 'api_prefix', '/api')
        return {**{k: row[k] for k in ('id', 'design_id', 'parent_version_id', 'sequence', 'prompt', 'render_kind', 'provider', 'created_at')}, 'snapshot': json.loads(row['snapshot_json']), 'preview_url': f"{prefix}/versions/{row['id']}/preview", 'view_url': f"{prefix}/versions/{row['id']}/view", 'download_url': f"{prefix}/versions/{row['id']}/download"}

    @staticmethod
    def job_public(row):
        return {**{k: row[k] for k in ('id', 'design_id', 'kind', 'status', 'phase', 'attempt', 'provider', 'error', 'result_version_id', 'result_asset_id', 'created_at', 'updated_at')}, 'needs_clarification': bool(row['needs_clarification'])}

    @leased_operation
    def design(self, owner, design_id):
        with self.db.connect() as db:
            result = self.owned_design(db, owner, design_id)
            versions = db.execute('SELECT * FROM versions WHERE design_id=? ORDER BY sequence', (design_id,)).fetchall()
            active = db.execute('SELECT * FROM jobs WHERE id=?', (result['active_job_id'],)).fetchone()
        result.pop('owner_id')
        result['versions'] = [self.version_public(v) for v in versions]
        result['active_job'] = self.job_public(active) if active else None
        return result

    @leased_operation
    def designs(self, owner):
        with self.db.connect() as db:
            ids = [r[0] for r in db.execute('SELECT id FROM designs WHERE owner_id=? ORDER BY created_at DESC', (owner,))]
        return [self.design(owner, i) for i in ids]

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
        self.validate_layout_selection(template['mode'], ids)
        profile = profile or json.loads(db.execute('SELECT profile_json FROM output_profiles WHERE active=1').fetchone()[0])
        result = copy.deepcopy(base) if base else dict(schema_version=1, seed=secrets.randbelow(2**31), params=dict(scale=1.0, spacing=1.0, rotation=0.0, offset_x=0.0, offset_y=0.0, background_color=None))
        result.update(asset_refs=ids, background_ref=selection['background_id'], template_id=template['id'], template_version=template['version'], template_mode=template['mode'], template_rules=json.loads(template['rules_json']), output_profile=profile)
        result.pop('composite_ref', None)
        return result

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
            job['lease_until'] = time.time() + self.settings.lease_seconds
            db.execute("UPDATE jobs SET status='RUNNING',phase='正在恢复任务',attempt=?,lease_until=?,updated_at=? WHERE id=?", (job['attempt'], job['lease_until'], now(), job['id']))
            db.execute('UPDATE outbox_events SET delivered_at=? WHERE job_id=?', (now(), job['id']))
            return job

    def phase(self, job, message):
        with self.db.transaction() as db:
            db.execute("UPDATE jobs SET phase=?,updated_at=? WHERE id=? AND attempt=? AND status='RUNNING'", (message, now(), job['id'], job['attempt']))

    def call_provider(self, job, operation, fn):
        payload = json.loads(job['payload_json'])
        expected = estimate_render_space(payload['snapshot']) if payload.get('snapshot') else 0
        # Native model result plus an atomic/adapted copy. Recheck for every
        # operation; other HSD tasks may consume space while a model is waiting.
        self.check_space(self.root / 'jobs' / job['id'] / str(job['attempt']),
                         expected + 2 * png_space(MAX_PIXELS, 1))
        start = time.monotonic()
        status, result, failure = 'SUCCEEDED', {}, None
        try:
            result = fn()
            return result
        except Exception as error:
            status = 'UNKNOWN' if getattr(error, 'uncertain_result', False) else 'FAILED'
            failure = error
            raise
        finally:
            meta = result if isinstance(result, dict) else {}
            models = json.loads(job['payload_json']).get('model_config', {})
            model = meta.get('model') or models.get('language_model' if operation == 'plan' else 'image_model')
            with self.db.transaction() as db:
                db.execute('INSERT INTO provider_calls VALUES(?,?,?,?,?,?,?,?,?,?,?,?)', (uid(), job['id'], job['attempt'], operation, job['provider'], model, meta.get('request_id') or getattr(failure, 'request_id', None), dump(meta.get('usage') or getattr(failure, 'usage', {})), int((time.monotonic()-start)*1000), status, ('外部调用结果未知，未自动重试' if getattr(failure, 'uncertain_result', False) else '提供商调用失败') if failure else None, now()))

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

    def build_artifact(self, job, directory):
        from .imaging import render, validate_image
        from .providers import get_provider, ClarificationNeeded
        payload = json.loads(job['payload_json'])
        needs_provider = job['kind'] == 'background' or (job['kind'] == 'refine' and not (payload.get('selection') and payload.get('prompt', '').strip() in ('应用所选配置', '应用新的素材与排版')))
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

        if job['kind'] == 'background':
            self.phase(job, '正在生成底图')
            path = directory / 'background.png'
            metadata = self.call_provider(job, 'generate_background', lambda: provider.generate_background(payload.get('prompt', ''), path))
            asset_id = derived(path, 'background', 'AI 随机底图' if provider.name != 'test' else '演示随机底图')
            return dict(assets=new_assets, result_asset_id=asset_id, provider_metadata=metadata)

        snapshot = copy.deepcopy(payload['snapshot'])
        self.validate_layout_selection(snapshot['template_mode'], snapshot['asset_refs'])
        # Check immutable inputs before a paid planner/editor sees them. Recheck
        # when each input is opened and at commit; an old ID cannot silently
        # acquire different pixels while retaining its version provenance.
        for asset_id in self.snapshot_asset_ids(snapshot):
            resolve(asset_id)
        prompt, render_kind = '', 'layered'
        if job['kind'] == 'refine':
            prompt = payload['prompt']
            self.phase(job, '正在理解修改要求')
            with self.db.connect() as db:
                assets = [self.asset_public(self.accessible_asset(db, a, job['owner_id'])) for a in snapshot['asset_refs']]
            if payload.get('selection') and prompt.strip() in ('应用所选配置', '应用新的素材与排版'):
                plan = {'operations': [], 'summary': '应用所选配置'}
            else:
                plan = self.call_provider(job, 'plan', lambda: provider.plan(prompt, snapshot, assets))
            operations = plan.get('operations')
            if not isinstance(operations, list) or len(operations) > 8 or (not operations and not payload.get('selection')):
                raise ClarificationNeeded('请具体说明要调整的图案、参数或内容')
            removed_unused_spacing = False
            applied_operations = []
            for index, operation in enumerate(operations):
                if not isinstance(operation, dict):
                    raise ServiceError(422, '无法执行该编辑计划')
                kind = operation.get('type')
                if snapshot.get('composite_ref') and kind != 'edit_composite':
                    raise ClarificationNeeded('当前版本为整幅编辑结果；请描述整体画面修改，或重新选择图案、底图和排版')
                if kind == 'parameters':
                    self.validate_parameters(operation.get('values'), snapshot['output_profile'])
                    if snapshot['template_mode'] in NON_REPEATING_MODES and 'spacing' in operation['values']:
                        if operation['values']['spacing'] != snapshot['params'].get('spacing', 1.0):
                            raise ClarificationNeeded('该排版不使用重复间距；可调整大小、位置或旋转，无需调整间距')
                        # Some planners echo an unchanged default alongside a
                        # real size/position edit. Do not claim it was applied,
                        # and do not charge a refinement for that default alone.
                        removed_unused_spacing = True
                        operation = {**operation, 'values': {key: value for key, value in operation['values'].items() if key != 'spacing'}}
                        if not operation['values']:
                            continue
                    snapshot['params'].update(operation['values'])
                elif kind in ('edit_asset', 'edit_background', 'edit_composite'):
                    self.phase(job, '正在编辑图像内容')
                    edit_prompt = operation.get('prompt', '')
                    if not isinstance(edit_prompt, str) or not 1 <= len(edit_prompt) <= 4000:
                        raise ServiceError(422, '内容编辑要求无效')
                    if kind == 'edit_asset':
                        original = operation.get('asset_id')
                        if original not in snapshot['asset_refs']:
                            raise ServiceError(422, '编辑目标必须属于当前作品')
                        source = resolve(original)
                        asset_kind = 'pattern'
                    elif kind == 'edit_background':
                        original = snapshot['background_ref']
                        source = resolve(original)
                        asset_kind = 'background'
                        if snapshot['params'].get('background_color'):
                            # Edit the visible solid color, rather than the older hidden texture.
                            with Image.open(source) as background_image:
                                visible_background = Image.new('RGBA', background_image.size, snapshot['params']['background_color'])
                            source = directory / f'before-background-{index}.png'
                            try:
                                _save_png(visible_background, source)
                            finally:
                                visible_background.close()
                        snapshot['params']['background_color'] = None
                    else:
                        # Flatten the actual full-resolution current composition, never the preview.
                        source = directory / f'before-composite-{index}.png'
                        render(snapshot, resolve, source, directory / f'before-preview-{index}.png')
                        original, asset_kind = snapshot.get('composite_ref'), 'composite'
                    output = directory / f'edited-{index}.png'
                    self.call_provider(job, kind, lambda: provider.edit_image(edit_prompt, source, output, kind.removeprefix('edit_')))
                    replacement = derived(output, asset_kind, '精修派生素材', original)
                    if kind == 'edit_asset':
                        snapshot['asset_refs'] = [replacement if a == original else a for a in snapshot['asset_refs']]
                    elif kind == 'edit_background':
                        snapshot['background_ref'] = replacement
                    else:
                        snapshot['composite_ref'] = replacement
                        snapshot['params'] = dict(scale=1.0, spacing=1.0, rotation=0.0, offset_x=0.0, offset_y=0.0, background_color=None)
                        render_kind = 'composite'
                else:
                    raise ServiceError(422, '编辑计划包含不支持的操作')
                applied_operations.append(operation)
            if removed_unused_spacing:
                if not applied_operations:
                    selection_changed = False
                    if payload.get('selection'):
                        with self.db.connect() as db:
                            base = db.execute('SELECT snapshot_json FROM versions WHERE id=? AND design_id=?',
                                              (job['base_version_id'], job['design_id'])).fetchone()
                        if base is None:
                            raise ServiceError(409, '原版本已变化，请刷新后再精修')
                        before = json.loads(base['snapshot_json'])
                        selection_fields = ('asset_refs', 'background_ref', 'template_id', 'template_version',
                                            'template_mode', 'template_rules', 'composite_ref')
                        selection_changed = any(before.get(key) != snapshot.get(key) for key in selection_fields)
                    if not selection_changed:
                        raise ClarificationNeeded('本次没有可执行的修改：该排版不使用重复间距；可要求调整大小、位置或旋转')
                plan = {**plan, 'operations': applied_operations}
            snapshot['edit_plan'] = plan
        render_kind = 'composite' if snapshot.get('composite_ref') else 'layered'
        self.phase(job, '正在合成并检查保存文件')
        master, preview = directory / 'master.png', directory / 'preview.png'
        metadata = render(snapshot, resolve, master, preview)
        snapshot['object_transforms'] = metadata.get('object_transforms', [])
        snapshot['local_patches'] = []
        snapshot['capabilities'] = ['composite_edit'] if render_kind == 'composite' else ['parameters', 'asset_edit', 'background_edit', 'composite_edit']
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

    def complete_job(self, job, artifact):
        from .imaging import validate_image
        if job['kind'] != 'background':
            master = self.safe_path(artifact['master_path'])
            if digest(master.read_bytes()) != artifact['master_sha256']:
                raise ServiceError(422, '保存结果校验失败')
            validate_image(master, artifact['snapshot']['output_profile'])
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
                elif job['provider'] != 'test' and job['kind'] != 'generate':
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
            calls = [dict(row) for row in db.execute('SELECT * FROM provider_calls ORDER BY created_at DESC LIMIT 100')]
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
