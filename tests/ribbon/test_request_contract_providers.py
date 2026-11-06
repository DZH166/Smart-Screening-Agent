"""Real adapter request contracts with synthetic HTTP only; zero model calls."""
import base64
from copy import deepcopy
from io import BytesIO
import json
from types import SimpleNamespace

from PIL import Image
import pytest

from hsd_tool.ai_key_pool import ApiKeyPool
from hsd_tool import material_providers as transport
from ribbon_backend.config import Settings
from ribbon_backend.providers import ClarificationNeeded, PLAN_SCHEMA, get_provider
from ribbon_backend.request_contract import PROTOCOL
from test_request_contract import content, parameter, view, wire


def real_adapter(tmp_path, provider):
    if provider == 'openai':
        return get_provider(Settings(data_dir=tmp_path, provider='openai', openai_api_key='synthetic-not-a-real-key',
                                     language_model='synthetic-text-model', image_model='synthetic-image-model'))
    pool = ApiKeyPool(SimpleNamespace(runtime=lambda: {'enabled': True, 'api_key': 'synthetic-not-a-real-key'}))
    return get_provider(Settings(data_dir=tmp_path, provider='deepseek_seedream', auth_mode='hsd', deepseek_pool=pool,
                                 ark_key='synthetic-not-a-real-ark-key', language_model='deepseek-flash',
                                 image_model='doubao-seedream-5-0-flash-test'))


def install_plan(adapter, monkeypatch, plan, observed):
    if adapter.name == 'openai':
        def post(endpoint, **kwargs):
            observed.append((endpoint, kwargs['payload']))
            return dict(status='completed', output=[dict(type='message', content=[dict(type='output_text', text=json.dumps(plan))])],
                        usage={'input_tokens': 20, 'output_tokens': 30}), 'synthetic-request-v2'
        monkeypatch.setattr(adapter, '_post', post)
    else:
        def post(request, **kwargs):
            observed.append(('chat', json.loads(request.data)))
            reply = dict(choices=[dict(finish_reason='stop', message={'content': json.dumps(plan)})],
                         usage={'prompt_tokens': 20, 'completion_tokens': 30})
            return transport.HttpReply(200, json.dumps(reply).encode(), {'x-request-id': 'synthetic-request-v2'}, transport.DEEPSEEK_ENDPOINT)
        monkeypatch.setattr(transport, '_default_transport', post)


@pytest.mark.parametrize('name', ['openai', 'deepseek_seedream'])
def test_real_planning_adapters_send_original_units_and_require_v2(tmp_path, monkeypatch, name):
    prompt = '图案缩小20%，底纹添加几何装饰'
    plan = wire(prompt, ['parameters', 'content'], [
        parameter('scale', .8, '图案缩小20%', mode='percent', amount=20, direction='decrease'),
        content(sources=['s2'])], ['layout', 'background'])
    adapter, observed = real_adapter(tmp_path, name), []
    install_plan(adapter, monkeypatch, plan, observed)
    result = adapter.plan(prompt, view(), [])
    assert len(observed) == 1
    payload = observed[0][1]
    supplied = json.loads(payload['input'] if name == 'openai' else payload['messages'][1]['content'])
    assert ''.join(unit['text'] for unit in supplied['source_units']) == prompt
    assert supplied['request_targets']['p1']['asset_id'] == 'a'
    assert result['request_contract']['protocol'] == PROTOCOL
    assert result['operations'][1]['prompt'] == '底纹添加几何装饰'
    assert result['request_id'] == 'synthetic-request-v2'
    assert result['usage']
    assert 'synthetic-not-a-real-key' not in str(result)


@pytest.mark.parametrize('name', ['openai', 'deepseek_seedream'])
def test_real_adapters_do_not_silently_accept_legacy_planner_reply(tmp_path, monkeypatch, name):
    adapter, observed = real_adapter(tmp_path, name), []
    legacy = dict(summary='旧返回', clarification=None, operations=[dict(type='parameters', values={'scale': .8})])
    install_plan(adapter, monkeypatch, legacy, observed)
    with pytest.raises(ClarificationNeeded) as error:
        adapter.plan('图案缩小20%', view(), [])
    assert len(observed) == 1
    assert error.value.request_id == 'synthetic-request-v2'
    assert error.value.usage
    assert not error.value.uncertain_result


def test_schema_requires_source_bindings_and_per_parameter_intent():
    assert set(PLAN_SCHEMA['required']) == {'summary', 'clarification', 'requirements', 'operations'}
    variants = PLAN_SCHEMA['properties']['operations']['items']['anyOf']
    assert all('source_ids' in variant['required'] for variant in variants)
    assert 'intents' in variants[0]['required']
    modes = variants[0]['properties']['intents']['items']['properties']['mode']['enum']
    assert 'absolute_percent' in modes and 'direction' in modes


@pytest.mark.parametrize('name', ['openai', 'deepseek_seedream'])
def test_image_prefix_does_not_forbid_explicit_text_or_outline_request(tmp_path, monkeypatch, name):
    adapter, observed = real_adapter(tmp_path, name), []
    source = tmp_path / 'source.png'
    with Image.new('RGBA', (128, 128), (0, 0, 0, 0)) as image:
        image.putpixel((64, 64), (255, 0, 0, 255))
        image.save(source)
    if name == 'openai':
        with Image.new('RGBA', (1024, 1024), (0, 0, 0, 0)) as image:
            image.putpixel((512, 512), (255, 0, 0, 255))
            raw = BytesIO()
            image.save(raw, format='PNG')
        def post(endpoint, **kwargs):
            observed.append(kwargs['data'])
            return {'data': [{'b64_json': base64.b64encode(raw.getvalue()).decode()}]}, 'synthetic-image-request'
        monkeypatch.setattr(adapter, '_post', post)
    else:
        def image(payload, *args, **kwargs):
            observed.append(payload)
            return {'model': 'synthetic-image-result'}
        monkeypatch.setattr(adapter, '_image', image)
    requested = '添加“HELLO”文字，并添加深色描边'
    adapter.edit_image(requested, source, tmp_path / 'out.png', 'asset')
    instruction = observed[0]['prompt']
    assert requested in instruction
    assert 'Do not add text or watermarks' not in instruction
    assert '不要新增水印、描边或阴影' not in instruction
    assert 'unrequested' in instruction or '未要求' in instruction
