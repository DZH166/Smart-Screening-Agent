import json
from types import SimpleNamespace

import pytest

from hsd_tool.ribbon_settings import RibbonSettings, RibbonSettingsConflict
from ribbon_backend.config import Settings
from ribbon_backend.providers import ProviderError

KEY = 'synthetic-ribbon-openai-key-not-real'


class Protector:
    def encrypt(self, value):
        return b'protected:' + bytes(c ^ 159 for c in value)

    def decrypt(self, value):
        if not value.startswith(b'protected:'):
            raise ValueError('bad ciphertext')
        return bytes(c ^ 159 for c in value[10:])


def store(tmp_path, **kwargs):
    return RibbonSettings(tmp_path, protector=Protector(), environ={}, **kwargs)


def activate(settings):
    return settings.save(dict(expected_revision=0, provider='openai', api_key=KEY,
        language_model='model-language', image_model='model-image', enabled=True))


def test_roundtrip_no_secret_snapshot_and_separate_storage(tmp_path):
    settings = store(tmp_path)
    saved = activate(settings)
    assert saved['provider'] == 'openai' and saved['configured']
    assert KEY not in json.dumps(saved) and KEY not in settings.path.read_text()
    restored = store(tmp_path)
    assert restored.snapshot() == saved
    runtime = restored.runtime_settings(Settings(auth_mode='hsd'))
    assert runtime.openai_api_key == KEY and runtime.ai_ready
    assert not (tmp_path / 'material_volcengine_settings.json').exists()


def test_stale_save_and_blank_preserve_then_delete(tmp_path):
    settings = store(tmp_path)
    activate(settings)
    with pytest.raises(RibbonSettingsConflict):
        settings.save(dict(expected_revision=0, enabled=False))
    assert settings.save(dict(expected_revision=1, api_key=''))['revision'] == 1
    result = settings.save(dict(expected_revision=1, clear_key=True))
    assert not result['enabled'] and not result['openai_configured']


@pytest.mark.parametrize('change', [{'provider':'test'}, {'enabled':1}, {'api_key':'short'},
    {'api_key':KEY, 'clear_key':True}, {'clear_key':'yes'}, {'language_model':KEY},
    {'language_model':'sk-secret-goes-in-wrong-field'}, {'image_model':'https://example.invalid'},
    {'endpoint':'https://example.invalid'}, {'image_quality':'ultra'}])
def test_invalid_fields_do_not_mutate(tmp_path, change):
    settings = store(tmp_path)
    activate(settings)
    before = settings.path.read_bytes()
    with pytest.raises(ValueError):
        settings.save(dict(expected_revision=1, **change))
    assert settings.path.read_bytes() == before


def test_storage_failure_does_not_publish(tmp_path, monkeypatch):
    settings = store(tmp_path)
    activate(settings)
    before = settings.snapshot()
    def fail(_):
        raise OSError('secret path must not leak')
    monkeypatch.setattr(settings._store, '_write', fail)
    with pytest.raises(ValueError) as error:
        settings.save(dict(expected_revision=1, enabled=False))
    assert 'secret path' not in str(error.value) and settings.snapshot() == before


def test_changed_settings_fail_queued_provider_closed(tmp_path):
    settings = store(tmp_path)
    activate(settings)
    runtime = settings.runtime_settings(Settings(auth_mode='hsd'))
    binding = {name:getattr(runtime,name) for name in ('language_model','image_model','image_quality','config_revision')}
    assert settings.provider_for_job('openai', binding).name == 'openai'
    settings.save(dict(expected_revision=1,image_model='model-image-second'))
    with pytest.raises(ProviderError,match='设置已变化'):
        settings.provider_for_job('openai', binding)
    with pytest.raises(ProviderError,match='设置已变化'):
        runtime.runtime_validator()


def test_inherited_selection_preserves_host_settings_and_detects_rotation(tmp_path):
    ai = {'enabled':True,'api_key':'synthetic-deepseek-key','key_revision':7}
    ark = {'enabled':True,'ark_key':'synthetic-ark-key','model_id':'doubao-seedream-5-0-flash-test','revision':4}
    settings = store(tmp_path, ai_settings=SimpleNamespace(runtime=lambda:dict(ai)),
        material_settings=SimpleNamespace(runtime=lambda:dict(ark)), key_pool=object())
    result = settings.save(dict(expected_revision=0,provider='deepseek_seedream',enabled=True))
    assert result['inherited_ready'] and 'synthetic' not in json.dumps(result)
    runtime = settings.runtime_settings(Settings(auth_mode='hsd'))
    assert runtime.ai_ready and runtime.openai_api_key == ''
    ark['revision'] += 1
    with pytest.raises(ProviderError):
        runtime.runtime_validator()
    assert ai['enabled'] and ark['enabled']


def test_corrupt_ciphertext_never_enables_demo_or_leaks(tmp_path):
    settings = store(tmp_path)
    activate(settings)
    record = json.loads(settings.path.read_text())
    record['encrypted_openai_key'] = 'invalid'
    settings.path.write_text(json.dumps(record))
    restored = store(tmp_path)
    assert restored.snapshot()['warning']
    assert not restored.snapshot()['enabled'] and restored.snapshot()['provider'] != 'test'


def test_ribbon_can_override_the_ark_key_and_model(tmp_path):
    """The ribbon page keeps its own copy of the Seedream configuration.

    Empty fields fall back to the material settings, so existing deployments keep
    working; once a value is saved it wins until it is cleared again.
    """
    ai = {'enabled': True, 'api_key': 'synthetic-deepseek-key', 'key_revision': 1}
    ark = {'enabled': True, 'ark_key': 'material-ark-key', 'model_id': 'doubao-material', 'revision': 1}
    settings = store(tmp_path, ai_settings=SimpleNamespace(runtime=lambda: dict(ai)),
                     material_settings=SimpleNamespace(runtime=lambda: dict(ark)), key_pool=object())
    saved = settings.save(dict(expected_revision=0, provider='deepseek_seedream', enabled=True,
                               ark_api_key='ribbon-ark-key', ark_model='doubao-ribbon'))
    assert saved['ark_configured'] and saved['ark_model'] == 'doubao-ribbon'
    assert 'ribbon-ark-key' not in json.dumps(saved) and 'ribbon-ark-key' not in settings.path.read_text()

    runtime = settings.runtime_settings(Settings(auth_mode='hsd'))
    assert runtime.ark_key == 'ribbon-ark-key' and runtime.image_model == 'doubao-ribbon'
    assert runtime.ai_ready

    # Clearing returns to the shared material configuration.
    cleared = settings.save(dict(expected_revision=1, clear_ark_key=True))
    assert not cleared['ark_configured'] and cleared['ark_model'] == ''
    restored = settings.runtime_settings(Settings(auth_mode='hsd'))
    assert restored.ark_key == 'material-ark-key' and restored.image_model == 'doubao-material'

    # The override changes the binding, so an in-flight job must not continue.
    bound = {name: getattr(restored, name) for name in ('language_model', 'image_model', 'image_quality', 'config_revision')}
    settings.save(dict(expected_revision=2, ark_model='doubao-third'))
    with pytest.raises(ProviderError, match='设置已变化'):
        settings.provider_for_job('deepseek_seedream', bound)


def test_ribbon_override_requires_a_key_and_model(tmp_path):
    ai = {'enabled': True, 'api_key': 'synthetic-deepseek-key', 'key_revision': 1}
    ark = {'enabled': False, 'ark_key': '', 'model_id': '', 'revision': 1}
    settings = store(tmp_path, ai_settings=SimpleNamespace(runtime=lambda: dict(ai)),
                     material_settings=SimpleNamespace(runtime=lambda: dict(ark)), key_pool=object())
    saved = settings.save(dict(expected_revision=0, provider='deepseek_seedream', enabled=True))
    assert not saved['configured']
    runtime = settings.runtime_settings(Settings(auth_mode='hsd'))
    assert runtime.ai_ready is False


def test_no_protector_has_no_plaintext_fallback(tmp_path):
    settings = RibbonSettings(tmp_path,protector=None,environ={})
    with pytest.raises(ValueError):
        activate(settings)
    assert not settings.path.exists()
