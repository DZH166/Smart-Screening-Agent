"""Real-adapter contracts with synthetic transport/images; no model calls."""
import base64
from copy import deepcopy
import io
import json
from types import SimpleNamespace

from PIL import Image
import pytest

from hsd_tool.ai_key_pool import ApiKeyPool
from ribbon_backend.config import Settings
from ribbon_backend.imaging import MODES, PARAM_DEFAULTS
from ribbon_backend.providers import (
    ClarificationNeeded, PLAN_SCHEMA, ProviderError, _normalise_plan,
    _safe_plan_input, _seedream_edit_size, get_provider, workflow_editing,
)


def snapshot(mode='grid', size=(11811, 520), *, flattened=False):
    result = dict(template_mode=mode, template_rules={'rows': 2, 'is_demo': False},
                  output_profile={'width': size[0], 'height': size[1]},
                  asset_refs=['pattern-b', 'pattern-a'], params=dict(PARAM_DEFAULTS))
    if flattened:
        result['composite_ref'] = 'flattened-synthetic-artwork'
    return result


def provider(tmp_path):
    ai = SimpleNamespace(runtime=lambda: {'enabled': True, 'api_key': 'synthetic-ribbon-model-credential'})
    pool = ApiKeyPool(ai)
    settings = Settings(data_dir=tmp_path, provider='deepseek_seedream', auth_mode='hsd',
                        language_model='deepseek-flash', image_model='doubao-seedream-5-0-flash-test',
                        deepseek_pool=pool, ark_key='synthetic-image-model-credential')
    return get_provider(settings), pool


@pytest.mark.parametrize('mode', MODES)
def test_formal_master_exposes_real_layer_capabilities_without_fake_composite_support(mode):
    contract = workflow_editing('deepseek_seedream', snapshot(mode))
    assert contract['allowed_operations'] == ['parameters', 'edit_asset', 'edit_background']
    assert contract['composite_edit'] is False and contract['composite_edit_reason']
    assert contract['planner_sees_images'] is False
    assert ('spacing' in contract['allowed_parameters']) == (mode not in ('fullwidth', 'ends_open'))


@pytest.mark.parametrize('service,size,supported', [
    ('deepseek_seedream', (2400, 600), True), ('deepseek_seedream', (11811, 520), False),
    ('deepseek_seedream', (1800, 400), False), ('deepseek_seedream', (8192, 512), True),
    ('openai', (1024, 1024), True), ('openai', (3072, 1024), True),
    ('openai', (11811, 520), False), ('openai', (2400, 600), False),
])
def test_flattened_work_has_only_supported_whole_picture_path(service, size, supported):
    contract = workflow_editing(service, snapshot(size=size, flattened=True))
    assert contract['allowed_operations'] == (['edit_composite'] if supported else [])
    assert contract['allowed_parameters'] == []
    assert contract['composite_edit'] is supported
    if not supported:
        assert '图' in contract['composite_edit_reason']


def test_safe_text_plan_context_keeps_mode_and_selection_order_but_not_private_state():
    state = snapshot('bordered')
    state['private_path'] = 'DO-NOT-SEND-SNAPSHOT'
    state['template_rules']['private_path'] = 'DO-NOT-SEND-RULES'
    assets = [dict(id='pattern-a', name='第二个图案', kind='pattern', path='DO-NOT-SEND-ASSET'),
              dict(id='pattern-b', name='第一个图案', kind='pattern'),
              dict(id='not-selected', name='DO-NOT-SEND-OTHER', kind='pattern')]
    result = _safe_plan_input('修改第一个图案', state, assets, provider='deepseek_seedream')
    encoded = json.dumps(result, ensure_ascii=False)
    assert 'DO-NOT-SEND' not in encoded
    assert result['snapshot']['template_mode'] == 'bordered'
    assert result['snapshot']['editing']['planner_sees_images'] is False
    assert [(item['id'], item['position']) for item in result['assets']] == [('pattern-b', 1), ('pattern-a', 2)]
    assert all('image_url' not in item and 'path' not in item for item in result['assets'])


def model_plan(operations):
    return {'summary': '明确标记的合成规划结果', 'clarification': None, 'operations': operations}


def test_schema_and_parser_enforce_the_same_eight_operation_limit():
    assert PLAN_SCHEMA['properties']['operations']['maxItems'] == 8
    operation = {'type': 'parameters', 'values': {'scale': .8}}
    assert len(_normalise_plan(model_plan([operation] * 8), 'deepseek_seedream', snapshot())['operations']) == 8
    with pytest.raises(ProviderError) as caught:
        _normalise_plan(model_plan([operation] * 9), 'deepseek_seedream', snapshot(),
                        request_id='synthetic-too-many', usage={'prompt_tokens': 12})
    assert caught.value.request_id == 'synthetic-too-many'
    assert caught.value.usage['prompt_tokens'] == 12


@pytest.mark.parametrize('operation', [
    {'type': 'edit_composite', 'prompt': '给整个画面添加星光'},
    {'type': 'edit_asset', 'asset_id': 'unselected', 'prompt': '改成红色'},
    {'type': 'parameters', 'values': {'execute_command': 'not-a-command'}},
])
def test_unsupported_plan_cannot_dispatch_a_picture_edit(operation):
    with pytest.raises(ClarificationNeeded) as caught:
        _normalise_plan(model_plan([operation]), 'deepseek_seedream', snapshot(),
                        request_id='synthetic-invalid-scope', usage={'completion_tokens': 9})
    assert caught.value.usage['completion_tokens'] == 9


@pytest.mark.parametrize('mode', ('fullwidth', 'ends_open'))
def test_non_repeated_unchanged_spacing_is_not_an_edit_but_does_not_block_real_scale(mode):
    empty = _normalise_plan(model_plan([{'type': 'parameters', 'values': {'spacing': 1.0}}]),
                            'deepseek_seedream', snapshot(mode))
    assert empty['operations'] == []  # Service decides whether selection actually changed.
    plan = _normalise_plan(model_plan([{'type': 'parameters', 'values': {'spacing': 1.0, 'scale': .8}}]),
                           'deepseek_seedream', snapshot(mode))
    assert plan['operations'] == [{'type': 'parameters', 'values': {'scale': .8}}]


def test_uneditable_flattened_work_is_rejected_without_a_language_call(tmp_path, monkeypatch):
    client, pool = provider(tmp_path)
    from hsd_tool import material_providers
    monkeypatch.setattr(material_providers, '_default_transport', lambda *args, **kwargs: pytest.fail('no request allowed'))
    with pytest.raises(ClarificationNeeded):
        client.plan('修改整幅图片', snapshot(flattened=True), [])
    assert pool.snapshot()['usage']['requests'] == 0


def test_real_deepseek_payload_disables_thinking_and_identifies_text_only_roles(tmp_path, monkeypatch):
    from hsd_tool import material_providers
    client, pool = provider(tmp_path)
    seen = []
    def send(request, **kwargs):
        payload = json.loads(request.data)
        seen.append(payload)
        assert payload['thinking'] == {'type': 'disabled'}
        assert payload['stream'] is False and payload['response_format'] == {'type': 'json_object'}
        context = json.loads(payload['messages'][1]['content'])
        assert context['snapshot']['template_mode'] == 'stacked'
        assert context['snapshot']['editing']['composite_edit'] is False
        assert context['snapshot']['editing']['planner_sees_images'] is False
        result = {**model_plan([{'type': 'parameters', 'values': {'scale': .8}, 'source_ids': ['s1'],
            'intents': [{'key': 'scale', 'mode': 'direction', 'amount': None,
                         'direction': 'decrease', 'evidence': context['request']}]}]),
            'requirements': [{'source_id': 's1', 'target_id': 'layout', 'effect': 'parameters'}]}
        raw = json.dumps({'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(result)}}],
                          'usage': {'prompt_tokens': 10, 'completion_tokens': 20}}).encode()
        return material_providers.HttpReply(200, raw, {'x-request-id': 'synthetic-live-protocol'}, material_providers.DEEPSEEK_ENDPOINT)
    monkeypatch.setattr(material_providers, '_default_transport', send)
    result = client.plan('整体图案缩小', snapshot('stacked'), [])
    assert len(seen) == 1 and result['request_id'] == 'synthetic-live-protocol'
    assert result['usage']['prompt_tokens'] == 10 and pool.snapshot()['usage']['requests'] == 1


@pytest.mark.parametrize('size', [(512, 512), (800, 1600), (3000, 1000), (240, 15), (15, 240), (1200, 750)])
def test_native_edit_canvas_is_deterministic_near_four_mp_and_preserves_ratio(size):
    width, height = _seedream_edit_size(size)
    assert (width, height) == _seedream_edit_size(size)
    assert not width % 16 and not height % 16
    assert 3_900_000 <= width * height <= 4_624_220
    assert max(width / height, height / width) <= 16
    assert abs(width / height / (size[0] / size[1]) - 1) < .015


def inline_image(size, *, transparent=False):
    image = Image.new('RGBA', size, '#788d63')
    if transparent:
        image.putpixel((0, 0), (0, 0, 0, 0))
    stream = io.BytesIO(); image.save(stream, format='PNG'); image.close()
    return {'b64_json': base64.b64encode(stream.getvalue()).decode(), 'size': f'{size[0]}x{size[1]}'}


@pytest.mark.parametrize('result_size', [(512, 512), (2048, 1024)])
def test_background_rejects_low_resolution_or_wrong_ratio_without_upscaling(tmp_path, monkeypatch, result_size):
    client, _ = provider(tmp_path)
    calls = []
    def submit(payload, cancel):
        calls.append(payload)
        assert payload['size'] == '2048x2048' and 'image' not in payload
        return {'data': [inline_image(result_size)]}, {'generated_images': 1, 'total_tokens': 20}, 'synthetic-wrong-native'
    monkeypatch.setattr(client.ark, '_submit', submit)
    with pytest.raises(ProviderError) as caught:
        client.generate_background('浅色底纹', tmp_path / 'background.png')
    assert len(calls) == 1 and not (tmp_path / 'background.png').exists()
    assert caught.value.usage == {'generated_images': 1, 'total_tokens': 20}
    assert caught.value.request_id == 'synthetic-wrong-native' and not caught.value.uncertain_result


def test_individual_edit_requests_one_native_canvas_and_never_resizes_the_source(tmp_path, monkeypatch):
    client, _ = provider(tmp_path)
    source = tmp_path / 'source.png'
    image = Image.new('RGBA', (600, 1200), '#ab6677'); image.putpixel((0, 0), (0, 0, 0, 0)); image.save(source); image.close()
    original = source.read_bytes(); expected = _seedream_edit_size((600, 1200)); calls = []
    def submit(payload, cancel):
        calls.append(payload)
        assert payload['size'] == f'{expected[0]}x{expected[1]}' and payload['background'] == 'transparent'
        raw = base64.b64decode(payload['image'].split(',', 1)[1])
        assert raw == original
        return {'data': [inline_image(expected, transparent=True)]}, {'generated_images': 1, 'input_images': 1}, 'synthetic-native-edit'
    monkeypatch.setattr(client.ark, '_submit', submit)
    metadata = client.edit_image('保持主体，增加一点细节', source, tmp_path / 'edited.png', 'asset')
    assert len(calls) == 1 and source.read_bytes() == original
    with Image.open(tmp_path / 'edited.png') as result:
        assert result.size == expected and result.getextrema()[3][0] < 255
    assert metadata['is_demo'] is False and metadata['usage'] == {'generated_images': 1, 'input_images': 1}


@pytest.mark.parametrize('employee_prompt', [
    '帮我把背景铺满星星',
    '删除旧花纹，换成分布均匀的树叶，保留底色',
    '只在左上角加一片叶子，其余不动',
])
def test_background_transport_preserves_original_request_and_does_not_use_motif_preservation_prompt(
        tmp_path, monkeypatch, employee_prompt):
    client, _ = provider(tmp_path)
    source = tmp_path / 'background.png'
    Image.new('RGBA', (512, 512), '#d8e2cc').save(source)
    original = source.read_bytes()
    calls = []
    def submit(payload, cancel):
        calls.append(payload)
        assert base64.b64decode(payload['image'].split(',', 1)[1]) == original
        assert payload['prompt'].endswith(employee_prompt)
        assert '独立的丝带底纹' in payload['prompt']
        assert '保持原有背景。' not in payload['prompt']
        assert '若要求铺满' in payload['prompt']  # conditional, never an unconditional extra request
        assert payload['background'] == 'opaque'
        return {'data': [inline_image((2048, 2048))]}, {'generated_images': 1}, 'synthetic-background-edit'
    monkeypatch.setattr(client.ark, '_submit', submit)
    result = client.edit_image(employee_prompt, source, tmp_path / 'out.png', 'background')
    assert len(calls) == 1 and result['request_id'] == 'synthetic-background-edit'
    assert source.read_bytes() == original


def test_background_scope_also_reaches_openai_without_changing_pattern_edits(tmp_path, monkeypatch):
    from ribbon_backend.providers import OpenAIProvider
    client = OpenAIProvider(SimpleNamespace(openai_api_key='synthetic-openai-input-key',
        language_model='synthetic-language', image_model='synthetic-image', model_timeout=60, image_quality='high'))
    source = tmp_path / 'source.png'
    Image.new('RGB', (128, 128), '#aabbcc').save(source)
    prompts = []
    def post(endpoint, **kwargs):
        prompts.append(kwargs['data']['prompt'])
        return {'data': [inline_image((1024, 1024))]}, 'synthetic-background-contract'
    monkeypatch.setattr(client, '_post', post)
    client.edit_image('只在角落添加一片叶子', source, tmp_path / 'background.png', 'background')
    client.edit_image('保留人物，衣服改为蓝色', source, tmp_path / 'pattern.png', 'asset')
    assert prompts[0].endswith('只在角落添加一片叶子')
    assert '独立的丝带底纹' in prompts[0]
    assert '独立的丝带底纹' not in prompts[1]
    assert prompts[1].endswith('保留人物，衣服改为蓝色')


def test_native_edit_mismatch_preserves_source_usage_and_has_no_retry(tmp_path, monkeypatch):
    client, _ = provider(tmp_path)
    source = tmp_path / 'source.png'
    Image.new('RGB', (700, 1400), '#bbbbaa').save(source)
    original = source.read_bytes(); calls = []
    def submit(*args):
        calls.append(1)
        return {'data': [inline_image((512, 1024))]}, {'generated_images': 1}, 'synthetic-low-native'
    monkeypatch.setattr(client.ark, '_submit', submit)
    with pytest.raises(ProviderError) as caught:
        client.edit_image('增加波点', source, tmp_path / 'edited.png', 'background')
    assert calls == [1] and source.read_bytes() == original and not (tmp_path / 'edited.png').exists()
    assert caught.value.request_id == 'synthetic-low-native' and caught.value.usage['generated_images'] == 1


@pytest.mark.parametrize('layer', ('response', 'plan'))
def test_deeply_nested_json_has_truthful_settlement_and_no_retry(tmp_path, monkeypatch, layer):
    from hsd_tool import material_providers
    client, pool = provider(tmp_path); calls = []
    nested = '[' * 2000 + '0' + ']' * 2000
    def send(request, **kwargs):
        calls.append(1)
        body = nested.encode() if layer == 'response' else json.dumps({
            'choices': [{'finish_reason': 'stop', 'message': {'content': nested}}],
            'usage': {'prompt_tokens': 10, 'completion_tokens': 5}}).encode()
        return material_providers.HttpReply(200, body, {'x-request-id': 'synthetic-nested-json'}, material_providers.DEEPSEEK_ENDPOINT)
    monkeypatch.setattr(material_providers, '_default_transport', send)
    with pytest.raises(ProviderError) as caught:
        client.plan('缩小图案', snapshot(), [])
    assert calls == [1] and caught.value.request_id == 'synthetic-nested-json'
    assert caught.value.uncertain_result is (layer == 'response')
    assert pool.snapshot()['usage']['requests'] == 1
    if layer == 'plan':
        assert caught.value.usage['prompt_tokens'] == 10


def test_seedream_input_preflight_is_local_and_does_not_modify_the_source(tmp_path, monkeypatch):
    client, _ = provider(tmp_path)
    source = tmp_path / 'preflight.png'
    image = Image.new('RGBA', (400, 800), '#aabbcc'); image.putpixel((0, 0), (0, 0, 0, 0)); image.save(source); image.close()
    original = source.read_bytes()
    monkeypatch.setattr(client.ark, '_submit', lambda *args: pytest.fail('preflight contacted provider'))
    prepared = client.validate_edit_input(source, 'asset')
    assert prepared['source_size'] == (400, 800) and prepared['transparent'] is True
    assert prepared['output_size'] == _seedream_edit_size((400, 800))
    assert isinstance(prepared['_input_bytes'], bytes) and prepared['_input_bytes'] == original
    assert source.read_bytes() == original


@pytest.mark.parametrize('size,visible', [((400, 20), True), ((14, 100), True), ((128, 128), False)])
def test_seedream_preflight_rejects_ineligible_inputs_without_network(tmp_path, monkeypatch, size, visible):
    client, _ = provider(tmp_path)
    source = tmp_path / 'ineligible.png'
    Image.new('RGBA', size, '#aabbcc' if visible else (0, 0, 0, 0)).save(source)
    original = source.read_bytes()
    monkeypatch.setattr(client.ark, '_submit', lambda *args: pytest.fail('ineligible input contacted provider'))
    with pytest.raises(ProviderError):
        client.validate_edit_input(source, 'asset')
    assert source.read_bytes() == original


def test_seedream_preflight_reads_a_bounded_source_before_decode(tmp_path, monkeypatch):
    import ribbon_backend.providers as adapters
    client, _ = provider(tmp_path)
    source = tmp_path / 'oversized.png'
    with source.open('wb') as stream:
        stream.truncate(30 * 1024 * 1024 + 1)
    monkeypatch.setattr(adapters, '_edit_image_from_bytes', lambda *args: pytest.fail('oversize image decoded'))
    with pytest.raises(ProviderError, match='大小'):
        client.validate_edit_input(source, 'asset')
    assert source.stat().st_size == 30 * 1024 * 1024 + 1


def test_seedream_revalidates_when_execution_follows_an_earlier_preflight(tmp_path, monkeypatch):
    client, _ = provider(tmp_path)
    source = tmp_path / 'drifting.png'
    Image.new('RGB', (128, 128), '#aabbcc').save(source)
    assert client.validate_edit_input(source, 'asset')['source_size'] == (128, 128)
    Image.new('RGB', (640, 20), '#aabbcc').save(source)
    monkeypatch.setattr(client.ark, '_submit', lambda *args: pytest.fail('drifted input contacted provider'))
    with pytest.raises(ClarificationNeeded):
        client.edit_image('添加波点', source, tmp_path / 'out.png', 'asset')
    assert not (tmp_path / 'out.png').exists()


def test_openai_preflight_preserves_existing_alpha_contract_and_has_no_network(tmp_path, monkeypatch):
    from ribbon_backend.providers import OpenAIProvider
    client = OpenAIProvider(SimpleNamespace(openai_api_key='synthetic-openai-input-key',
        language_model='synthetic-language', image_model='synthetic-image', model_timeout=60, image_quality='high'))
    source = tmp_path / 'transparent.png'
    Image.new('RGBA', (128, 128), (0, 0, 0, 0)).save(source)
    original = source.read_bytes()
    monkeypatch.setattr(client, '_post', lambda *args, **kwargs: pytest.fail('preflight contacted OpenAI'))
    metadata = client.validate_edit_input(source, 'asset')
    assert metadata['transparent'] is True and metadata['request_size'] == '1024x1024'
    assert metadata['_input_bytes'] == original and source.read_bytes() == original


def test_openai_upload_uses_validated_snapshot_not_a_reopened_file(tmp_path, monkeypatch):
    from ribbon_backend.providers import OpenAIProvider
    client = OpenAIProvider(SimpleNamespace(openai_api_key='synthetic-openai-input-key',
        language_model='synthetic-language', image_model='synthetic-image', model_timeout=60, image_quality='high'))
    source = tmp_path / 'source.png'
    Image.new('RGB', (128, 128), '#aabbcc').save(source)
    original = source.read_bytes(); calls = []
    def post(endpoint, **kwargs):
        calls.append(endpoint)
        source.write_bytes(b'simulated-file-change-after-validation')
        assert kwargs['files']['image'][1].read() == original
        return {'data': [inline_image((1024, 1024))]}, 'synthetic-captured-input'
    monkeypatch.setattr(client, '_post', post)
    result = client.edit_image('添加波点', source, tmp_path / 'out.png', 'asset')
    assert calls == ['images/edits'] and result['request_id'] == 'synthetic-captured-input'


def test_fixture_input_validation_is_visible_local_and_never_a_real_service(tmp_path, monkeypatch):
    from ribbon_backend.providers import TestProvider
    client = TestProvider(); source = tmp_path / 'fixture.png'
    Image.new('RGBA', (128, 128), (0, 0, 0, 0)).save(source)
    with pytest.raises(ProviderError, match='测试图片'):
        client.validate_edit_input(source, 'asset')
    Image.new('RGB', (128, 128), '#aabbcc').save(source)
    original = source.read_bytes()
    prepared = client.validate_edit_input(source, 'background')
    assert prepared['source_size'] == (128, 128) and source.read_bytes() == original
