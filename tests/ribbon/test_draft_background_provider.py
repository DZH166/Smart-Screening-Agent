"""Reference-driven draft backgrounds; synthetic transport only, no paid calls."""
import base64
from contextlib import closing
import io
import json
import re
from types import SimpleNamespace

from PIL import Image, ImageDraw, PngImagePlugin
import pytest

from hsd_tool.ai_key_pool import ApiKeyPool
from hsd_tool import material_ark
from ribbon_backend.config import Settings
from ribbon_backend.providers import ProviderError, TestProvider, get_provider

TestProvider.__test__ = False


def client(tmp_path):
    pool = ApiKeyPool(SimpleNamespace(runtime=lambda: {
        'enabled': True, 'api_key': 'synthetic-language-key'}))
    settings = Settings(data_dir=tmp_path, provider='deepseek_seedream', auth_mode='hsd',
                        language_model='deepseek-flash', image_model='doubao-seedream-5-0-flash-test',
                        deepseek_pool=pool, ark_key='synthetic-image-key')
    return get_provider(settings)


def image_bytes(size, color, *, private_metadata=False):
    buffer = io.BytesIO()
    info = PngImagePlugin.PngInfo()
    if private_metadata:
        info.add_text('Comment', r'D:\company-private\case-secret.png')
    with closing(Image.new('RGBA', size, color)) as image:
        image.save(buffer, format='PNG', pnginfo=info)
    return buffer.getvalue()


@pytest.fixture
def sources(tmp_path):
    first = tmp_path / 'employee-private-portrait.png'
    first.write_bytes(image_bytes((40, 120), '#DC2814', private_metadata=True))
    second = tmp_path / 'employee-private-landscape.png'
    second.write_bytes(image_bytes((160, 40), '#1446D0', private_metadata=True))
    background = tmp_path / 'employee-private-background.png'
    background.write_bytes(image_bytes((96, 96), '#E7DCA1', private_metadata=True))
    case = image_bytes((1000, 44), '#208F65', private_metadata=True)
    return [first, second], background, case


def install_submit(provider, monkeypatch, calls, *, result_size=(2048, 2048)):
    def transport(request, **kwargs):
        payload = json.loads(request.data)
        calls.append(payload)
        output = image_bytes(result_size, '#E7DCA1')
        reply = {'data': [{'b64_json': base64.b64encode(output).decode('ascii'),
                           'size': f'{result_size[0]}x{result_size[1]}'}],
                 'usage': {'generated_images': 1, 'input_images': len(payload.get('image', []))}}
        return material_ark.HttpReply(200, json.dumps(reply).encode(),
                                     {'x-request-id': 'synthetic-draft'}, material_ark.ENDPOINT)
    monkeypatch.setattr(provider.ark, '_transport', transport)


def decode_reference(value):
    assert value.startswith('data:image/png;base64,')
    return Image.open(io.BytesIO(base64.b64decode(value.split(',', 1)[1])))


def test_wire_payload_contains_only_the_explicit_case_and_colour_summaries(tmp_path, sources, monkeypatch):
    provider = client(tmp_path)
    patterns, background, case = sources
    originals = {p: p.read_bytes() for p in patterns + [background]}
    calls = []
    install_submit(provider, monkeypatch, calls)
    metadata = provider.generate_draft_background(patterns, background, case, tmp_path / 'result.png',
                                                   mode='ends', density='rich', prompt='浅绿色细小花点')
    assert len(calls) == 1
    payload = calls[0]
    assert payload['size'] == '2048x2048' and payload['watermark'] is False
    assert payload['background'] == 'opaque' and payload['output_format'] == 'png'
    assert payload['response_format'] == 'b64_json' and len(payload['image']) == 1
    assert '左右两端各放完整大主体，中间单排小主体重复' in payload['prompt']
    assert '饱满' in payload['prompt'] and '浅绿色细小花点' in payload['prompt']
    assert '后续主体区域留出安静空间' in payload['prompt']
    assert '不复制其中人物、文字、水印或标志' in payload['prompt']
    assert '原样' in payload['prompt'] and '简单几何或浅织纹' in payload['prompt']
    assert all(colour in payload['prompt'] for colour in ('#DC2814', '#1446D0', '#E7DCA1'))
    assert 'private' not in json.dumps(payload) and 'case-secret' not in json.dumps(payload)
    with closing(decode_reference(payload['image'][0])) as reference:
        assert reference.size == (2048, 2048) and not reference.info
        with closing(reference.getchannel('R').point(lambda v: 255 if v < 100 else 0)) as mask:
            left, top, right, bottom = mask.getbbox()
            assert (right - left) / (bottom - top) == pytest.approx(1000 / 44, rel=.02)
    assert originals == {p: p.read_bytes() for p in originals}
    assert metadata['is_demo'] is False and metadata['usage']['input_images'] == 1
    assert metadata['request_id'] == 'synthetic-draft'
    with Image.open(tmp_path / 'result.png') as output:
        assert output.size == (2048, 2048)


@pytest.mark.parametrize('include_background,include_case', [(False, False), (True, False), (False, True)])
def test_no_case_omits_the_image_field_on_the_wire(tmp_path, sources, monkeypatch,
                                               include_background, include_case):
    provider = client(tmp_path)
    patterns, background, case = sources
    calls = []
    install_submit(provider, monkeypatch, calls)
    provider.generate_draft_background(patterns, background if include_background else None,
                                       case if include_case else None, tmp_path / 'out.png',
                                       mode='stagger', density='airy')
    assert len(calls) == 1
    assert ('#E7DCA1' in calls[0]['prompt']) is include_background
    if include_case:
        assert len(calls[0]['image']) == 1
        assert '参考图1是员工明确选择的公司案例' in calls[0]['prompt']
    else:
        assert 'image' not in calls[0] and 'data:image' not in json.dumps(calls[0])


def test_twelve_inputs_only_send_a_bounded_palette(tmp_path, monkeypatch):
    provider = client(tmp_path)
    patterns = []
    for index in range(12):
        path = tmp_path / f'private-{index}.png'
        path.write_bytes(image_bytes((24, 24), (20 + index * 12, 30, 80, 255)))
        patterns.append(path)
    calls = []
    install_submit(provider, monkeypatch, calls)
    provider.generate_draft_background(patterns, None, None, tmp_path / 'out.png', mode='grid', density='balanced')
    assert len(calls) == 1 and 'image' not in calls[0]
    assert len(re.findall(r'#[0-9A-F]{6}', calls[0]['prompt'])) == 4


def test_palette_excludes_hidden_rgb_and_prioritises_visible_alpha(tmp_path, monkeypatch):
    provider = client(tmp_path)
    path = tmp_path / 'transparent-pattern.png'
    with Image.new('RGBA', (128, 64), (0, 255, 0, 0)) as source:
        draw = ImageDraw.Draw(source)
        draw.rectangle((0, 0, 31, 63), fill=(255, 0, 0, 255))
        draw.rectangle((96, 0, 127, 63), fill=(0, 0, 255, 32))
        source.save(path)
    calls = []
    install_submit(provider, monkeypatch, calls)
    provider.generate_draft_background([path], None, None, tmp_path / 'out.png', mode='grid', density='balanced')
    assert re.findall(r'#[0-9A-F]{6}', calls[0]['prompt']) == ['#FF0000', '#0000FF']
    assert 'image' not in calls[0] and 'transparent-pattern' not in json.dumps(calls[0])


@pytest.mark.parametrize('layer', ['pattern', 'background', 'case'])
@pytest.mark.parametrize('failure', ['corrupt', 'too_many_pixels', 'too_many_bytes', 'empty'])
def test_all_inputs_are_preflighted_before_the_single_paid_call(tmp_path, sources, monkeypatch, layer, failure):
    provider = client(tmp_path)
    patterns, background, case = sources
    monkeypatch.setattr(provider.ark, '_submit', lambda *args: pytest.fail('ineligible input reached network'))
    if failure == 'corrupt':
        invalid = b'not a PNG'
    elif failure == 'too_many_pixels':
        monkeypatch.setattr(material_ark, 'MAX_INPUT_PIXELS', 16)
        invalid = image_bytes((5, 5), 'red')
        # Ensure earlier, unrelated references remain eligible under this
        # deliberately small limit, so the selected late input causes failure.
        for path in patterns + [background]:
            path.write_bytes(image_bytes((2, 2), 'blue'))
        case = image_bytes((2, 2), 'green')
    elif failure == 'too_many_bytes':
        invalid = b'x' * (material_ark.MAX_INPUT_BYTES + 1)
    else:
        invalid = image_bytes((32, 32), (0, 0, 0, 0))
    if layer == 'pattern':
        patterns[-1].write_bytes(invalid)
    elif layer == 'background':
        background.write_bytes(invalid)
    else:
        case = invalid
    originals = {p: p.read_bytes() for p in patterns + [background]}
    with pytest.raises(ProviderError):
        provider.generate_draft_background(patterns, background, case, tmp_path / 'out.png',
                                           mode='ends', density='rich')
    assert not (tmp_path / 'out.png').exists()
    assert originals == {p: p.read_bytes() for p in originals}


@pytest.mark.parametrize('kwargs', [dict(pattern_paths=[]), dict(pattern_paths=['unused'] * 13),
                                  dict(mode='invented'), dict(density='invented'), dict(prompt='x' * 4001),
                                  dict(reference_bytes='https://not-allowed.invalid/case.png')])
def test_invalid_context_never_reads_files_or_calls_model(tmp_path, monkeypatch, kwargs):
    import ribbon_backend.providers as adapters
    provider = client(tmp_path)
    monkeypatch.setattr(adapters, '_bounded_edit_bytes', lambda *args: pytest.fail('invalid context read a file'))
    monkeypatch.setattr(provider.ark, '_submit', lambda *args: pytest.fail('invalid context reached model'))
    values = dict(pattern_paths=['unused'], background_path=None, reference_bytes=None,
                  output_path=tmp_path / 'out.png', mode='grid', density='balanced', prompt='')
    values.update(kwargs)
    with pytest.raises(ProviderError):
        provider.generate_draft_background(**values)


def test_unknown_result_is_not_retried_and_preserves_usage(tmp_path, sources, monkeypatch):
    provider = client(tmp_path)
    patterns, background, case = sources
    calls = []
    def submit(*args):
        calls.append(1)
        raise material_ark.ArkProviderError('submission_unknown', '请求结果未知', settled=False,
                                           request_id='synthetic-unknown', usage={'generated_images': 1})
    monkeypatch.setattr(provider.ark, '_submit', submit)
    with pytest.raises(ProviderError) as caught:
        provider.generate_draft_background(patterns, background, case, tmp_path / 'out.png',
                                           mode='ends', density='rich')
    assert calls == [1] and caught.value.uncertain_result
    assert caught.value.request_id == 'synthetic-unknown' and caught.value.usage['generated_images'] == 1
    assert not (tmp_path / 'out.png').exists()


@pytest.mark.parametrize('size', [(512, 512), (2048, 1024)])
def test_wrong_native_result_fails_without_upscaling_or_retry(tmp_path, sources, monkeypatch, size):
    provider = client(tmp_path)
    patterns, _, _ = sources
    calls = []
    install_submit(provider, monkeypatch, calls, result_size=size)
    with pytest.raises(ProviderError) as caught:
        provider.generate_draft_background(patterns, None, None, tmp_path / 'out.png', mode='single', density='airy')
    assert len(calls) == 1 and not caught.value.uncertain_result
    assert caught.value.usage['generated_images'] == 1 and caught.value.request_id == 'synthetic-draft'
    assert not (tmp_path / 'out.png').exists()


def test_fixture_uses_same_preflight_and_is_explicitly_demo(tmp_path, sources):
    patterns, background, case = sources
    metadata = TestProvider().generate_draft_background(patterns, background, case, tmp_path / 'test.png',
                                                        mode='ends', density='rich')
    assert metadata['is_demo'] is True and metadata['model'] == 'test-draft-background-v1'
    assert '测试替身' in metadata['description'] and '不是真实AI' in metadata['description']
    with Image.open(tmp_path / 'test.png') as output:
        assert output.size == (2048, 2048)
    with pytest.raises(ProviderError):
        TestProvider().generate_draft_background(patterns, background, b'invalid', tmp_path / 'bad.png',
                                                 mode='ends', density='rich')
    assert not (tmp_path / 'bad.png').exists()


def test_openai_has_no_draft_background_capability():
    from ribbon_backend.providers import OpenAIProvider
    assert not hasattr(OpenAIProvider, 'generate_draft_background')
