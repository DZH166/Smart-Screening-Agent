import base64
import io
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
from PIL import Image
import pytest

from ribbon_backend.imaging import PARAM_DEFAULTS, seed_assets
from ribbon_backend.providers import ClarificationNeeded, OpenAIProvider, ProviderError, TestProvider, get_provider

# Prevent pytest treating a production class imported for testing as a test case.
TestProvider.__test__ = False


@pytest.fixture
def inputs(tmp_path):
    assets = seed_assets(tmp_path/"assets")
    snapshot = {"asset_refs": ["demo-flower", "demo-star", "demo-ring"], "background_ref": "demo-bg-sage",
                "params": dict(PARAM_DEFAULTS), "output_profile": {"width": 1800, "height": 400}}
    return assets, snapshot


def configured_openai():
    return OpenAIProvider(SimpleNamespace(openai_api_key="test-credential-never-sent", language_model="configured-language-model",
                                         image_model="configured-image-model", model_timeout=60, image_quality="high"))


def test_multiple_parameter_requirements_return_one_plan(inputs):
    assets, snapshot = inputs
    plan = TestProvider().plan("图案缩小一些，间距拉大一点", snapshot, assets)
    assert plan["operations"] == [{"type": "parameters", "values": {"scale": .8, "spacing": 1.25}}]
    assert "测试替身" in plan["summary"]
    plan2 = TestProvider().plan("图案放大一些，旋转15度，背景改为浅蓝色", snapshot, assets)
    assert plan2["operations"][0]["values"] == {"scale": 1.2, "rotation": 15, "background_color": "#DFEAF0"}
    preserving = TestProvider().plan("图案缩小一些，保留当前浅绿底色", snapshot, assets)
    assert preserving["operations"][0]["values"] == {"scale": .8}


@pytest.mark.parametrize("prompt", ["请让它变得更好看", "图案缩小一些，换成一只小猫", "把花朵缩小一点", "保留背景", "图案缩小一点并放大一点"])
def test_unknown_or_partial_or_conflicting_requests_never_fake_success(inputs, prompt):
    assets, snapshot = inputs
    with pytest.raises(ClarificationNeeded):
        TestProvider().plan(prompt, snapshot, assets)


def test_background_and_individual_content_edit_change_bytes_without_mutating_source(inputs, tmp_path):
    assets, snapshot = inputs
    by_id = {a["id"]: a for a in assets}
    provider = TestProvider()
    for prompt, expected, target in (("背景添加波点", "edit_background", "background"), ("给花朵添加笑脸", "edit_asset", "pattern")):
        op = provider.plan(prompt, snapshot, assets)["operations"][0]
        assert op["type"] == expected
        source = Path(by_id[op.get("asset_id", snapshot["background_ref"])]["path"])
        before = source.read_bytes()
        result = tmp_path/f"{expected}.png"
        meta = provider.edit_image(op["prompt"], source, result, target)
        assert result.read_bytes() != before
        assert source.read_bytes() == before
        assert meta["is_demo"] is True
        with Image.open(source) as first, Image.open(result) as second:
            assert first.size == second.size


def test_test_background_marked_and_missing_real_key_fails_closed(tmp_path):
    provider = get_provider(SimpleNamespace(provider="test"))
    meta = provider.generate_background("浅绿色柔和底图", tmp_path/"bg.png")
    assert meta["is_demo"] is True
    with pytest.raises(ProviderError, match="OPENAI_API_KEY"):
        get_provider(SimpleNamespace(provider="openai", openai_api_key="", language_model="x", image_model="y", model_timeout=60, image_quality="high"))


def test_real_response_validation_and_metadata_no_key(monkeypatch, inputs):
    assets, snapshot = inputs
    provider = configured_openai()
    observed = {}
    def fake_post(endpoint, **kwargs):
        observed.update(endpoint=endpoint, **kwargs)
        return {"status": "completed", "output": [{"type": "message", "content": [{"type": "output_text", "text":
                '{"summary":"缩小图案","clarification":null,"operations":[{"type":"parameters","values":{"scale":0.8,"spacing":null,"rotation":null,"offset_x":null,"offset_y":null,"background_color":null}}]}'}]}],
                "usage": {"input_tokens": 15, "output_tokens": 40}}, "req-test"
    monkeypatch.setattr(provider, "_post", fake_post)
    plan = provider.plan("图案缩小一点", snapshot, assets)
    assert observed["endpoint"] == "responses"
    assert observed["payload"]["text"]["format"]["strict"] is True
    assert plan["operations"][0]["values"] == {"scale": .8}
    assert plan["request_id"] == "req-test"
    assert plan["usage"]["input_tokens"] == 15
    assert "test-credential" not in str(plan)


def test_real_image_invalid_bytes_and_resolution_do_not_pass(tmp_path, monkeypatch):
    provider = configured_openai()
    with pytest.raises(ProviderError, match="文件检查"):
        provider._decode_image({"data": [{"b64_json": base64.b64encode(b"bad").decode()}]}, tmp_path/"bad.png", "req-bad")
    assert not (tmp_path/"bad.png").exists()
    source = tmp_path/"long.png"
    Image.new("RGBA", (1800, 400), "white").save(source)
    with pytest.raises(ClarificationNeeded, match="长条母版"):
        provider.edit_image("添加星光", source, tmp_path/"edited.png", "composite")


def test_real_image_request_and_inline_decode(tmp_path, monkeypatch):
    provider = configured_openai()
    buffer = io.BytesIO()
    Image.new("RGBA", (1024, 1024), "#AACCAA").save(buffer, format="PNG")
    def fake_post(endpoint, **kwargs):
        assert endpoint == "images/generations"
        assert kwargs["payload"]["model"] == "configured-image-model"
        assert kwargs["payload"]["size"] == "1024x1024"
        return {"data": [{"b64_json": base64.b64encode(buffer.getvalue()).decode()}], "usage": {"total_tokens": 73}}, "req-img"
    monkeypatch.setattr(provider, "_post", fake_post)
    meta = provider.generate_background("浅绿纹理", tmp_path/"real.png")
    assert meta["is_demo"] is False
    assert meta["request_id"] == "req-img"
    assert meta["usage"]["total_tokens"] == 73


def test_real_edit_multipart_preserves_transparency_and_no_external_urls(tmp_path, monkeypatch):
    provider = configured_openai()
    source = tmp_path/"source.png"
    Image.new("RGBA", (512, 512), (240, 180, 100, 0)).save(source)
    encoded = base64.b64encode(source.read_bytes()).decode()
    def fake_post(endpoint, **kwargs):
        assert endpoint == "images/edits"
        assert kwargs["data"]["background"] == "transparent"
        assert kwargs["data"]["output_format"] == "png"
        assert kwargs["files"]["image"][2] == "image/png"
        assert kwargs["files"]["image"][1].read(8) == b"\x89PNG\r\n\x1a\n"
        return {"data": [{"b64_json": encoded}], "usage": {"input_tokens": 50}}, "req-edit"
    monkeypatch.setattr(provider, "_post", fake_post)
    meta = provider.edit_image("给图案添加笑脸", source, tmp_path/"edit.png", "asset")
    assert meta["request_id"] == "req-edit"
    assert meta["is_demo"] is False
    with pytest.raises(ProviderError, match="文件检查"):
        provider._decode_image({"data": [{"url": "https://untrusted.invalid/image.png"}]}, tmp_path/"bad-url.png", "req-url")


def test_real_plan_refusal_and_bad_json_fail_closed(monkeypatch, inputs):
    assets, snapshot = inputs
    provider = configured_openai()
    for response in ({"status": "incomplete"}, {"status": "completed", "output": []},
                     {"status": "completed", "output": [{"type": "message", "content": [{"type": "refusal", "refusal": "No"}]}]}):
        monkeypatch.setattr(provider, "_post", lambda *args, **kwargs: (response, "req-refusal"))
        with pytest.raises(ProviderError):
            provider.plan("修改图案", snapshot, assets)


def test_timeout_is_unknown_result_without_retry(monkeypatch):
    provider = configured_openai()
    calls = []
    def fail(*args, **kwargs):
        calls.append(1)
        raise httpx.ReadTimeout("sensitive text must not appear")
    monkeypatch.setattr(httpx.Client, "stream", fail)
    with pytest.raises(ProviderError) as captured:
        provider._post("responses", payload={})
    assert captured.value.uncertain_result is True
    assert "sensitive" not in str(captured.value)
    assert calls == [1]


def combined_provider(tmp_path):
    from ribbon_backend.config import Settings
    from hsd_tool.ai_key_pool import ApiKeyPool
    ai = SimpleNamespace(runtime=lambda:{'enabled':True,'api_key':'synthetic-deepseek-credential-not-real'})
    pool = ApiKeyPool(ai)
    settings = Settings(data_dir=tmp_path,provider='deepseek_seedream',auth_mode='hsd',
        language_model='deepseek-flash',image_model='doubao-seedream-5-0-flash-test',
        deepseek_pool=pool,ark_key='synthetic-ark-credential-not-real')
    return get_provider(settings),pool


def test_hsd_never_uses_test_provider():
    with pytest.raises(ProviderError,match='测试替身'):
        get_provider(SimpleNamespace(provider='test',auth_mode='hsd'))


def test_combined_plan_shares_pool_and_records_known_usage(tmp_path,inputs,monkeypatch):
    from hsd_tool import material_providers as transport
    provider,pool=combined_provider(tmp_path)
    assets,snapshot=inputs
    snapshot['local_private_path']='DO-NOT-SEND'
    observed=[]
    plan={'summary':'缩小图案','clarification':None,'operations':[{'type':'parameters','values':{'scale':.8,'spacing':None}}]}
    def send(request,**kwargs):
        payload=json.loads(request.data)
        observed.append(payload)
        assert 'DO-NOT-SEND' not in request.data.decode()
        return transport.HttpReply(200,json.dumps({'choices':[{'finish_reason':'stop','message':{'content':json.dumps(plan)}}],
            'usage':{'prompt_tokens':100,'completion_tokens':20}}).encode(),{'x-request-id':'synthetic-plan'},transport.DEEPSEEK_ENDPOINT)
    monkeypatch.setattr(transport,'_default_transport',send)
    result=provider.plan('图案缩小',snapshot,assets)
    assert result['operations'][0]['values']=={'scale':.8}
    assert result['usage']['prompt_tokens']==100 and len(observed)==1
    assert pool.snapshot()['usage']['requests']==1


def test_combined_429_cools_shared_pool_without_rotating_or_retry(tmp_path,inputs,monkeypatch):
    from hsd_tool import material_providers as transport
    provider,pool=combined_provider(tmp_path)
    calls=[]
    def send(request,**kwargs):
        calls.append(1)
        return transport.HttpReply(429,b'{"error":{"message":"sensitive"}}',{},transport.DEEPSEEK_ENDPOINT)
    monkeypatch.setattr(transport,'_default_transport',send)
    assets,snapshot=inputs
    with pytest.raises(ProviderError) as captured:
        provider.plan('缩小',snapshot,assets)
    assert 'sensitive' not in str(captured.value)
    with pytest.raises(ValueError):
        pool.acquire()
    assert calls==[1]


@pytest.mark.parametrize('status,body',[(500,b'{"error":{}}'),(200,b'not json')])
def test_combined_unknown_reply_never_retried(tmp_path,inputs,monkeypatch,status,body):
    from hsd_tool import material_providers as transport
    provider,pool=combined_provider(tmp_path)
    calls=[]
    def send(request,**kwargs):
        calls.append(1)
        return transport.HttpReply(status,body,{},transport.DEEPSEEK_ENDPOINT)
    monkeypatch.setattr(transport,'_default_transport',send)
    assets,snapshot=inputs
    with pytest.raises(ProviderError) as captured:
        provider.plan('缩小',snapshot,assets)
    assert captured.value.uncertain_result and calls==[1]


def test_seedream_background_and_edit_use_distinct_ribbon_prompt(tmp_path,monkeypatch):
    provider,pool=combined_provider(tmp_path)
    image=Image.new('RGBA',(512,512),(255,0,0,255))
    image.putpixel((0,0),(0,0,0,0))
    source=tmp_path/'motif.png'
    image.save(source)
    encoded=base64.b64encode(source.read_bytes()).decode()
    requests=[]
    def submit(payload,cancel):
        requests.append(payload)
        return {'data':[{'b64_json':encoded,'size':'512x512','output_format':'png'}]}, {'generated_images':1},'synthetic-image'
    monkeypatch.setattr(provider.ark,'_submit',submit)
    meta=provider.generate_background('浅蓝底纹',tmp_path/'background.png')
    assert meta['is_demo'] is False and requests[-1]['size']=='2048x2048'
    assert 'image' not in requests[-1]
    before=source.read_bytes()
    provider.edit_image('加星光',source,tmp_path/'edited.png','asset')
    assert requests[-1]['background']=='transparent'
    assert '清理整张图片' not in requests[-1]['prompt']
    assert source.read_bytes()==before


def test_seedream_opaque_edit_output_rejected_if_input_alpha(tmp_path,monkeypatch):
    provider,pool=combined_provider(tmp_path)
    source=tmp_path/'motif.png'
    image=Image.new('RGBA',(512,512),'red');image.putpixel((0,0),(0,0,0,0));image.save(source)
    b=io.BytesIO();Image.new('RGB',(512,512),'red').save(b,format='PNG')
    monkeypatch.setattr(provider.ark,'_submit',lambda *args:({'data':[{'b64_json':base64.b64encode(b.getvalue()).decode(),'size':'512x512'}]}, {'generated_images':1},'req'))
    with pytest.raises(ProviderError,match='透明背景') as error:
        provider.edit_image('加星光',source,tmp_path/'out.png','asset')
    assert error.value.usage['generated_images']==1 and not (tmp_path/'out.png').exists()


def test_seedream_unknown_error_preserves_settlement_and_no_retry(tmp_path,monkeypatch):
    from hsd_tool.material_ark import ArkProviderError
    provider,pool=combined_provider(tmp_path)
    calls=[]
    def submit(*args):
        calls.append(1)
        raise ArkProviderError('submission_unknown','返回超时',settled=False,request_id='req')
    monkeypatch.setattr(provider.ark,'_submit',submit)
    with pytest.raises(ProviderError) as error:
        provider.generate_background('蓝色',tmp_path/'out.png')
    assert error.value.uncertain_result and calls==[1]


def test_runtime_change_checked_before_each_image_call(tmp_path,monkeypatch):
    provider,pool=combined_provider(tmp_path)
    calls=[]
    def changed():
        raise ProviderError('配置已变化')
    provider.settings.runtime_validator=changed
    monkeypatch.setattr(provider.ark,'_submit',lambda *args:calls.append(1))
    with pytest.raises(ProviderError,match='配置已变化'):
        provider.generate_background('蓝色',tmp_path/'out.png')
    assert not calls


@pytest.mark.parametrize('status,body,headers',[(302,b'',{'Location':'http://untrusted.invalid'}),
    (200,b'{}',{'content-length':str(3*1024*1024)}),(200,b'not-json',{})])
def test_openai_redirect_oversize_and_bad_json_are_unknown_not_retried(monkeypatch,status,body,headers):
    provider=configured_openai()
    calls=[]
    class FakeClient:
        def __init__(self,**kwargs):
            assert kwargs['follow_redirects'] is False
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def stream(self,*args,**kwargs):
            calls.append(1)
            class Reply:
                status_code=status
                def __init__(self):self.headers=headers
                def __enter__(self):return self
                def __exit__(self,*args):pass
                def iter_bytes(self,size):yield body
            return Reply()
    monkeypatch.setattr(httpx,'Client',FakeClient)
    with pytest.raises(ProviderError) as error:
        provider._post('responses',payload={})
    assert error.value.uncertain_result and calls==[1]


def test_model_metadata_never_persists_unknown_string_usage():
    from ribbon_backend.providers import _meta
    result=_meta('model',usage={'input_tokens':12,'secret':'private-key',
        'input_tokens_details':{'text_tokens':8,'arbitrary':'private-key'}})
    assert result['usage']=={'input_tokens':12,'input_tokens_details':{'text_tokens':8}}
    assert 'private-key' not in str(result)


def test_seedream_supported_long_composite_is_edited_at_exact_dimensions(tmp_path,monkeypatch):
    provider,pool=combined_provider(tmp_path)
    source=tmp_path/'ribbon.png'
    Image.new('RGB',(2400,600),'blue').save(source)
    encoded=base64.b64encode(source.read_bytes()).decode()
    calls=[]
    def submit(payload,cancel):
        calls.append(payload)
        assert payload['size']=='2400x600' and payload['background']=='opaque'
        return {'data':[{'b64_json':encoded,'size':'2400x600'}]}, {'generated_images':1},'req-long'
    monkeypatch.setattr(provider.ark,'_submit',submit)
    metadata=provider.edit_image('加星光',source,tmp_path/'result.png','composite')
    assert (metadata['width'],metadata['height'])==(2400,600) and len(calls)==1


@pytest.mark.parametrize('size,target', [((1800,400),'composite'),((3000,2000),'composite'),
    ((1700,100),'composite'),((14,800),'asset'),((6400,6000),'asset')])
def test_seedream_invalid_dimensions_rejected_before_billable_request(tmp_path,monkeypatch,size,target):
    provider,pool=combined_provider(tmp_path)
    source=tmp_path/'ribbon.png';Image.new('RGB',size,'blue').save(source)
    calls=[]
    monkeypatch.setattr(provider.ark,'_submit',lambda *args:calls.append(1))
    with pytest.raises(ClarificationNeeded):
        provider.edit_image('加星光',source,tmp_path/'result.png',target)
    assert not calls


def test_seedream_changed_composite_output_dimensions_fail_instead_of_resizing(tmp_path,monkeypatch):
    provider,pool=combined_provider(tmp_path)
    source=tmp_path/'ribbon.png';Image.new('RGB',(2400,600),'blue').save(source)
    b=io.BytesIO();Image.new('RGB',(2048,512),'blue').save(b,format='PNG')
    monkeypatch.setattr(provider.ark,'_submit',lambda *args:({'data':[{'b64_json':base64.b64encode(b.getvalue()).decode(),'size':'2048x512'}]}, {'generated_images':1},'req'))
    with pytest.raises(ProviderError):
        provider.edit_image('加星光',source,tmp_path/'result.png','composite')
    assert not (tmp_path/'result.png').exists()


def test_deepseek_setting_change_during_acquisition_does_not_dispatch(tmp_path,inputs,monkeypatch):
    from hsd_tool import material_providers as transport
    provider,pool=combined_provider(tmp_path)
    checks=[];calls=[]
    def validator():
        checks.append(1)
        if len(checks)>1:
            raise ProviderError('设置已变化')
    provider.settings.runtime_validator=validator
    monkeypatch.setattr(transport,'_default_transport',lambda *args,**kwargs:calls.append(1))
    assets,snapshot=inputs
    with pytest.raises(ProviderError,match='设置已变化'):
        provider.plan('缩小',snapshot,assets)
    assert not calls and pool.snapshot()['usage']['requests']==0
