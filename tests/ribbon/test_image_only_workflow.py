"""Image-only ribbon configuration after edit retirement; synthetic transports."""
import base64
from io import BytesIO
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient
from PIL import Image
import pytest

from hsd_tool import material_ark, material_providers
from hsd_tool.ribbon_settings import RibbonSettings
from ribbon_backend.app import create_app
from ribbon_backend.config import Settings
from ribbon_backend.providers import ProviderError, get_provider
from ribbon_backend.service import Service


class Protector:
    def encrypt(self, value):
        return b'synthetic:' + bytes(item ^ 159 for item in value)

    def decrypt(self, value):
        assert value.startswith(b'synthetic:')
        return bytes(item ^ 159 for item in value[10:])


def encoded_png(size):
    stream = BytesIO()
    with Image.new('RGB', size, '#dae8f4') as image:
        image.save(stream, 'PNG')
    return base64.b64encode(stream.getvalue()).decode('ascii')


@pytest.mark.parametrize('override', [False, True])
def test_ark_only_runtime_and_http_background_and_first_draft(tmp_path, monkeypatch, override):
    ai = {'enabled': False, 'api_key': '', 'keys': [], 'key_revision': 3}
    ark = {'enabled': True, 'ark_key': 'synthetic-ark-only-key',
           'model_id': 'doubao-seedream-5-0-flash-test', 'revision': 4}
    store = RibbonSettings(tmp_path / 'settings', protector=Protector(), environ={},
        ai_settings=SimpleNamespace(runtime=lambda: dict(ai)),
        material_settings=SimpleNamespace(runtime=lambda: dict(ark)))
    options = dict(expected_revision=0, enabled=True)
    if override:
        options.update(ark_api_key='synthetic-ribbon-only-key', ark_model='doubao-seedream-5-0-flash-ribbon-test')
        ark.update(enabled=False, ark_key='', model_id='')
    saved = store.save(options)
    assert saved['configured'] is True
    base = Settings(data_dir=tmp_path / 'data', auth_mode='demo', provider='deepseek_seedream')
    runtime = store.runtime_settings(base)
    assert runtime.image_ready and runtime.ai_ready and not runtime.plan_ready
    assert runtime.deepseek_pool is None
    calls = []
    def no_text(*args, **kwargs):
        pytest.fail('Image-only operations must not call DeepSeek text transport')
    monkeypatch.setattr(material_providers, '_default_transport', no_text)
    def submit(self, payload, cancel):
        calls.append(payload)
        return {'data': [{'b64_json': encoded_png((2048, 2048)), 'size': '2048x2048'}]}, {
            'generated_images': 1}, 'synthetic-image-only-request'
    monkeypatch.setattr(material_ark.ArkMaterialProvider, '_submit', submit)
    service = Service(base, runtime_settings_supplier=lambda: store.runtime_settings(base),
        provider_factory=lambda provider, config: store.provider_for_job(provider, config, base=base))
    service.save_profile(dict(name='Synthetic image-only', width=1080, height=240, dpi=96, format='PNG', is_demo=True))
    with TestClient(create_app(base, service=service)) as client:
        owner = client.post('/api/auth/login', json={'username': 'demo', 'password': 'demo12345'}).json()['id']
        config = client.get('/api/config').json()
        assert config['ai_ready'] and config['ai_draft_available']
        response = client.post('/api/background-jobs', json={'idempotency_key': str(uuid4()), 'prompt': '浅蓝底纹'})
        assert response.status_code == 202, response.text
        assert service.run_once()
        completed = service.job(owner, response.json()['id'])
        assert completed['status'] == 'SUCCEEDED' and completed['result_asset_id'], completed
        design = client.post('/api/designs', json={'name': 'Synthetic image-only draft'}).json()
        selected = dict(asset_ids=[service.assets(owner, 'pattern')[0]['id']],
            background_id=service.assets(owner, 'background')[0]['id'], template_id='grid')
        response = client.post(f'/api/designs/{design["id"]}/generate', json=dict(selected,
            idempotency_key=str(uuid4()), ai_assisted=True))
        assert response.status_code == 202, response.text
        assert service.run_once()
        completed = service.job(owner, response.json()['id'])
        assert completed['status'] == 'SUCCEEDED', completed
        result = service.design(owner, design['id'])
        assert result['successful_refinement_count'] == 0 and len(result['versions']) == 1
        assert client.get(result['versions'][0]['download_url']).status_code == 200
        with service.db.connect() as db:
            assert {row[0] for row in db.execute('SELECT operation FROM provider_calls')} == {'generate_background', 'design_background'}
    assert len(calls) == 2
    assert "image" not in calls[1] and "本地图案主色" in calls[1]["prompt"]
    assert ai == {'enabled': False, 'api_key': '', 'keys': [], 'key_revision': 3}
    # Older accepted planning cannot borrow image readiness as text readiness.
    provider = store.provider_for_job(runtime.provider, {field: getattr(runtime, field)
        for field in ('language_model', 'image_model', 'image_quality', 'config_revision')}, base=base)
    with pytest.raises(ProviderError, match='DeepSeek'):
        provider.plan('修改背景', {}, [])
    assert len(calls) == 2


@pytest.mark.parametrize('provider_name', ['openai', 'deepseek_seedream'])
def test_standalone_image_adapter_needs_no_language_model(tmp_path, monkeypatch, provider_name):
    settings = Settings(data_dir=tmp_path, provider=provider_name, language_model='',
        image_model='doubao-seedream-5-0-flash-test' if provider_name == 'deepseek_seedream' else 'synthetic-image-model',
        openai_api_key='synthetic-openai-key', ark_key='synthetic-ark-key')
    assert settings.image_ready and settings.ai_ready and not settings.plan_ready
    provider = get_provider(settings)
    calls = []
    if provider_name == 'openai':
        def post(endpoint, **kwargs):
            calls.append(endpoint)
            return {'data': [{'b64_json': encoded_png((1024, 1024))}]}, 'synthetic-openai-image'
        monkeypatch.setattr(provider, '_post', post)
    else:
        def submit(payload, cancel):
            calls.append(payload['model'])
            return {'data': [{'b64_json': encoded_png((2048, 2048)), 'size': '2048x2048'}]}, {}, 'synthetic-ark-image'
        monkeypatch.setattr(provider.ark, '_submit', submit)
    output = tmp_path / 'background.png'
    provider.generate_background('浅蓝底纹', output)
    assert output.is_file() and len(calls) == 1
    with pytest.raises(ProviderError):
        provider.plan('修改背景', {}, [])
    assert len(calls) == 1
