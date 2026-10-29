"""Private ribbon provider selection. Keys never leave the runtime boundary.

The existing material credential storage supplies descriptor-pinned I/O only;
this uses a separate file and encryption domain, never the material settings.
"""
from __future__ import annotations

import base64
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import re
import threading

from .ai_settings import _DPAPI, _valid_key, MODEL
from .material_settings import MaterialSettings

_DEFAULT = object()
_PREFIX = b'HSD-RIBBON-OPENAI-1\0'
_ARK_PREFIX = b'HSD-RIBBON-ARK-1\0'
_MODEL = re.compile(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z')
_ERROR = '无法安全保存丝带模型设置，本次更改未生效。'


class RibbonSettingsConflict(ValueError):
    code = 'revision_conflict'


class _Storage(MaterialSettings):
    def __init__(self, directory, protector, environ, key_file):
        self.path = Path(directory).absolute() / 'ribbon_model_settings.json'
        source = os.environ if environ is None else environ
        key_file = source.get('HSD_CREDENTIAL_KEY_FILE', '') if key_file is None else key_file
        self._server_store = None
        if key_file:
            if protector is not _DEFAULT:
                raise ValueError(_ERROR)
            from .credential_store import LinuxCredentialStore
            self._server_store = LinuxCredentialStore(key_file, self.path)
            self._protector = self._server_store
        else:
            self._protector = (_DPAPI() if os.name == 'nt' else None) if protector is _DEFAULT else protector


class RibbonSettings:
    def __init__(self, data_dir, *, ai_settings=None, material_settings=None,
                 key_pool=None, usage_ledger=None, protector=_DEFAULT, environ=None,
                 credential_key_file=None):
        self._store = _Storage(data_dir, protector, environ, credential_key_file)
        self.path = self._store.path
        self.ai_settings, self.material_settings = ai_settings, material_settings
        self.key_pool, self.usage_ledger = key_pool, usage_ledger
        self._lock = threading.RLock()
        self._key = ''
        self._ark_key = ''
        self._record = dict(version=1, provider='deepseek_seedream', enabled=False,
                            language_model='', image_model='', image_quality='high',
                            revision=0, encrypted_openai_key='',
                            encrypted_ark_key='', ark_model='')
        self._warning = ''
        try:
            raw = self._store._read()
            if raw is not None:
                record = json.loads(raw)
                if isinstance(record, dict):
                    # Records written before the ribbon-specific Ark override existed.
                    record.setdefault('encrypted_ark_key', '')
                    record.setdefault('ark_model', '')
                self._validate_record(record)
                key = ''
                if record['encrypted_openai_key']:
                    if self._store._protector is None:
                        raise ValueError(_ERROR)
                    decrypted = self._store._protector.decrypt(base64.b64decode(record['encrypted_openai_key'], validate=True))
                    if not decrypted.startswith(_PREFIX):
                        raise ValueError(_ERROR)
                    key = decrypted[len(_PREFIX):].decode('ascii')
                    if not _valid_key(key):
                        raise ValueError(_ERROR)
                ark_key = ''
                if record['encrypted_ark_key']:
                    if self._store._protector is None:
                        raise ValueError(_ERROR)
                    decrypted = self._store._protector.decrypt(base64.b64decode(record['encrypted_ark_key'], validate=True))
                    if not decrypted.startswith(_ARK_PREFIX):
                        raise ValueError(_ERROR)
                    ark_key = decrypted[len(_ARK_PREFIX):].decode('ascii')
                    if not _valid_key(ark_key):
                        raise ValueError(_ERROR)
                self._check_secret_fields(record, key)
                if record['enabled'] and record['provider'] == 'openai' and not (key and record['language_model'] and record['image_model']):
                    raise ValueError(_ERROR)
                self._record, self._key, self._ark_key = record, key, ark_key
        except Exception:
            self._warning = '丝带模型设置无法读取，请重新保存；没有改用测试结果。'

    @staticmethod
    def _validate_record(record):
        names = {'version', 'provider', 'enabled', 'language_model', 'image_model',
                 'image_quality', 'revision', 'encrypted_openai_key',
                 'encrypted_ark_key', 'ark_model'}
        if (not isinstance(record, dict) or set(record) != names
                or type(record['version']) is not int or record['version'] != 1
                or record['provider'] not in ('openai', 'deepseek_seedream')
                or type(record['enabled']) is not bool
                or type(record['revision']) is not int or record['revision'] < 0
                or record['image_quality'] not in ('low', 'medium', 'high', 'auto')
                or not isinstance(record['encrypted_openai_key'], str)
                or not isinstance(record['encrypted_ark_key'], str)):
            raise ValueError(_ERROR)
        for field in ('language_model', 'image_model'):
            value = record[field]
            if not isinstance(value, str) or value and not _MODEL.fullmatch(value):
                raise ValueError('模型 ID 格式不正确，请填写模型名称，不要填写网址。')
        ark_model = record['ark_model']
        if not isinstance(ark_model, str) or ark_model and not _MODEL.fullmatch(ark_model):
            raise ValueError('图片模型 ID 格式不正确，请填写模型名称，不要填写网址。')

    @staticmethod
    def _check_secret_fields(record, key):
        for name in ('language_model', 'image_model'):
            if record[name].startswith('sk-') or key and key in record[name]:
                raise ValueError('请将 API Key 填入密钥框，不要填进模型 ID。')

    def _inherited(self):
        ai = self.ai_settings.runtime() if self.ai_settings else {}
        ark = self.material_settings.runtime() if self.material_settings else {}
        ready = bool(ai.get('enabled') and (ai.get('api_key') or any(k.get('enabled') for k in ai.get('keys', [])))
                     and ark.get('enabled') and ark.get('ark_key') and ark.get('model_id') and self.key_pool)
        return ai, ark, ready

    def snapshot(self):
        with self._lock:
            ai, ark, inherited_ready = self._inherited()
            record = self._record
            ark_key, ark_model, ark_ready = self._override(record, ark)
            host_ready = bool(ai.get('enabled') and (ai.get('api_key') or any(k.get('enabled') for k in ai.get('keys', [])))
                              and self.key_pool and ark_ready)
            configured = bool(self._key and record['language_model'] and record['image_model']) if record['provider'] == 'openai' else host_ready
            return {k: record[k] for k in ('provider', 'enabled', 'language_model', 'image_model', 'image_quality', 'revision')} | {
                'configured': configured, 'openai_configured': bool(self._key),
                'ark_configured': bool(self._ark_key), 'ark_model': record.get('ark_model', ''),
                'inherited_ready': inherited_ready, 'inherited_language_model': MODEL,
                'inherited_image_model': ark.get('model_id', ''),
                'key_persistence': 'linux_aesgcm' if self._store._server_store else 'windows_dpapi' if self._store._protector else 'unavailable',
                'warning': self._warning,
            }

    def save(self, payload):
        if (not isinstance(payload, dict) or set(payload) - {'expected_revision', 'provider', 'enabled', 'language_model', 'image_model', 'image_quality', 'api_key', 'clear_key', 'ark_api_key', 'clear_ark_key', 'ark_model'}
                or type(payload.get('expected_revision')) is not int or payload['expected_revision'] < 0):
            raise ValueError('设置格式不正确，请刷新页面后重试。')
        with self._lock:
            if payload['expected_revision'] != self._record['revision']:
                raise RibbonSettingsConflict('设置已被更新，请重新读取后再保存。')
            record = dict(self._record)
            for name in ('provider', 'enabled', 'language_model', 'image_model', 'image_quality'):
                if name in payload:
                    record[name] = payload[name]
            self._validate_record(record)
            key, encrypted = self._key, record['encrypted_openai_key']
            if 'clear_key' in payload and type(payload['clear_key']) is not bool:
                raise ValueError('删除密钥选项不正确。')
            if 'api_key' in payload and (not isinstance(payload['api_key'], str) or payload['api_key'] and not _valid_key(payload['api_key'])):
                raise ValueError('API Key 格式不正确，请完整粘贴且不要带空格。')
            if payload.get('clear_key'):
                if payload.get('api_key'):
                    raise ValueError('不能同时删除和添加密钥。')
                key = encrypted = ''
                if record['provider'] == 'openai':
                    record['enabled'] = False
            elif payload.get('api_key') and payload['api_key'] != key:
                if self._store._protector is None:
                    raise ValueError(_ERROR)
                key = payload['api_key']
                try:
                    encrypted = base64.b64encode(self._store._protector.encrypt(_PREFIX + key.encode('ascii'))).decode('ascii')
                except Exception:
                    raise ValueError(_ERROR) from None
            ark_key, encrypted_ark = self._ark_key, record['encrypted_ark_key']
            if 'clear_ark_key' in payload and type(payload['clear_ark_key']) is not bool:
                raise ValueError('删除密钥选项不正确。')
            if 'ark_api_key' in payload and (not isinstance(payload['ark_api_key'], str) or payload['ark_api_key'] and not _valid_key(payload['ark_api_key'])):
                raise ValueError('API Key 格式不正确，请完整粘贴且不要带空格。')
            if 'ark_model' in payload:
                if not isinstance(payload['ark_model'], str):
                    raise ValueError('图片模型 ID 格式不正确。')
                record['ark_model'] = payload['ark_model'].strip()
            if payload.get('clear_ark_key'):
                if payload.get('ark_api_key'):
                    raise ValueError('不能同时删除和添加密钥。')
                ark_key = encrypted_ark = ''
                record['ark_model'] = ''
            elif payload.get('ark_api_key') and payload['ark_api_key'] != ark_key:
                if self._store._protector is None:
                    raise ValueError(_ERROR)
                ark_key = payload['ark_api_key']
                try:
                    encrypted_ark = base64.b64encode(self._store._protector.encrypt(_ARK_PREFIX + ark_key.encode('ascii'))).decode('ascii')
                except Exception:
                    raise ValueError(_ERROR) from None
            for field in ('language_model', 'image_model', 'ark_model'):
                if ark_key and ark_key in record[field]:
                    raise ValueError('请将 API Key 填入密钥框，不要填进模型 ID。')
            self._check_secret_fields(record, key)
            if record['enabled'] and record['provider'] == 'openai' and not (key and record['language_model'] and record['image_model']):
                raise ValueError('启用 OpenAI 前，请保存 Key 和两个模型 ID。')
            record['encrypted_openai_key'] = encrypted
            record['encrypted_ark_key'] = encrypted_ark
            if record == self._record and not self._warning:
                return self.snapshot()
            record['revision'] += 1
            try:
                self._store._write(record)
            except Exception:
                raise ValueError(_ERROR) from None
            self._record, self._key, self._ark_key, self._warning = record, key, ark_key, ''
            return self.snapshot()

    def _override(self, record, ark):
        """Ribbon-specific Ark key/model, falling back to the material settings."""
        key = self._ark_key or ark.get('ark_key', '')
        model = record.get('ark_model') or ark.get('model_id', '')
        ready = bool(key and model and (self._ark_key or ark.get('enabled')))
        return key, model, ready

    def runtime_settings(self, base):
        with self._lock:
            ai, ark, inherited_ready = self._inherited()
            record = self._record
            inherited = record['provider'] == 'deepseek_seedream'
            ark_key, ark_model, ark_ready = self._override(record, ark)
            revision = hashlib.sha256(json.dumps([record['revision'],
                ai.get('key_revision', 0) if inherited else None,
                ark.get('revision', 0) if inherited else None,
                record.get('ark_model', ''),
                bool(self._ark_key)], separators=(',', ':')).encode()).hexdigest()
            ready = inherited_ready if not self._ark_key and not record.get('ark_model') else bool(
                ai.get('enabled') and (ai.get('api_key') or any(k.get('enabled') for k in ai.get('keys', [])))
                and self.key_pool and ark_ready)
            current = replace(base, provider=record['provider'], config_revision=revision,
                enabled=record['enabled'] and (ready if inherited else True),
                openai_api_key='' if inherited else self._key,
                language_model=MODEL if inherited else record['language_model'],
                image_model=ark_model if inherited else record['image_model'],
                image_quality=record['image_quality'], deepseek_pool=self.key_pool,
                ark_key=ark_key if inherited else '', usage_ledger=self.usage_ledger)
            current.runtime_validator = lambda: self._assert_current(base, current)
            return current

    def _assert_current(self, base, saved):
        from ribbon_backend.providers import ProviderError
        current = self.runtime_settings(base)
        if current.config_revision != saved.config_revision or not current.ai_ready:
            raise ProviderError('管理员模型设置已变化或服务已停用；未继续调用，请确认设置后重新提交。')

    def provider_for_job(self, provider, model_config, *, base=None):
        from ribbon_backend.config import Settings
        from ribbon_backend.providers import ProviderError, get_provider
        current = self.runtime_settings(base or Settings(auth_mode='hsd'))
        expected = {name: getattr(current, name) for name in ('language_model', 'image_model', 'image_quality', 'config_revision')}
        if provider != current.provider or model_config != expected:
            raise ProviderError('任务提交后模型设置已变化；原版本保留，请确认设置后重新提交。')
        return get_provider(current)
