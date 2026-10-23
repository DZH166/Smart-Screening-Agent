"""Cleanup, strict location, exact crop and settlement regressions. No real API."""
import base64
import io
import json
from types import SimpleNamespace

from PIL import Image
import pytest

from hsd_tool.material_ark import ArkMaterialProvider, ArkProviderError, ArkCancelled, ArkResult, HttpReply, _encode, ENDPOINT
from hsd_tool.material_locate import DeepSeekMaterialLocator, parse_designs
from hsd_tool.material_pipeline import MaterialPipelineProvider
from hsd_tool.ai_key_pool import ApiKeyPool
from hsd_tool.ai_settings import OFFICIAL_ENDPOINT

KEY = "unit-only-material-key"
MODEL = "doubao-seedream-5-0-flash-260915"
CONFIG = {"ark_key": KEY, "model_id": MODEL}


def image(size=(1000, 500), *, transparent=False):
    im = Image.new("RGBA", size, (70, 20, 90, 255))
    for x in range(size[0] // 2):
        im.paste((180, 50, 25, 255), (x, 0, x + 1, size[1]))
    if transparent:
        im.putpixel((0, 0), (0, 0, 0, 0))
    return _encode(im)


def api_image(png):
    with Image.open(io.BytesIO(png)) as im:
        size = f"{im.width}x{im.height}"
    return {"data": [{"size": size, "output_format": "png", "b64_json": base64.b64encode(png).decode()}],
            "usage": {"input_images": 1, "generated_images": 1}}


def design(box, label="完整设计", uncertain=False, reason=""):
    return {"label": label, "box": box, "uncertain": uncertain, "reason": reason}


def answer(designs=None):
    return {"complete": True, "designs": designs if designs is not None else [design([0, 0, 480, 1000]), design([520, 0, 1000, 1000])]}


def completion(value=None):
    return {"id": "unit-request-1", "model": "deepseek-flash",
            "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(value if value is not None else answer())}}],
            "usage": {"prompt_tokens": 200, "completion_tokens": 100, "prompt_cache_hit_tokens": 0, "prompt_cache_miss_tokens": 200}}


class Transport:
    def __init__(self, payload, status=200, url="", before=None):
        self.payload, self.status, self.url, self.before = payload, status, url, before
        self.calls = []

    def __call__(self, request, **options):
        self.calls.append((request, options))
        if self.before:
            self.before()
        if isinstance(self.payload, Exception):
            raise self.payload
        raw = self.payload if isinstance(self.payload, bytes) else json.dumps(self.payload).encode()
        return HttpReply(self.status, raw, {}, self.url)


class Settings:
    enabled = True

    def runtime(self):
        return {"enabled": self.enabled, "api_key": KEY, "endpoint": OFFICIAL_ENDPOINT}


def locator(transport, settings=None, pool=None):
    return DeepSeekMaterialLocator(settings or Settings(), key_pool=pool, transport=transport)


def test_cleanup_requests_single_whole_canvas_preserves_composition_and_opaque_output():
    t = Transport(api_image(image()))
    result = ArkMaterialProvider(KEY, MODEL, transport=t).clean(image(), instructions="保留文字")
    body = json.loads(t.calls[0][0].data)
    assert body["layer_decomposition"] is False
    assert "stream" not in body and "background" not in body
    assert "不拆分" in body["prompt"] and "数量、位置" in body["prompt"]
    assert "PNG Alpha 通道" in body["prompt"] and "保留设计内部底板" in body["prompt"]
    assert "不要用白底或棋盘格图案假装透明" in body["prompt"]
    w, h = map(int, body["size"].split("x"))
    assert 921600 <= w * h <= 4624220 and abs(w / h - 2) < .01
    assert result.rectangular_crops and len(result.layers) == 1
    with Image.open(io.BytesIO(result.base_png)) as im:
        assert im.getchannel("A").getextrema() == (255, 255)
    assert result.usage["generated_images"] == 1


@pytest.mark.parametrize("payload,code", [
    ({"data": []}, "invalid_response"),
    ({"data": [{"url": "http://127.0.0.1/private"}]}, "invalid_response"),
    (api_image(image((500, 500))), "invalid_bounds"),
])
def test_cleanup_rejects_missing_or_wrong_canvas_without_retry(payload, code):
    t = Transport(payload)
    with pytest.raises(ArkProviderError) as caught:
        ArkMaterialProvider(KEY, MODEL, transport=t).clean(image())
    assert caught.value.code == code and not caught.value.safe_retry
    assert len(t.calls) == 1


def test_clean_accepts_opaque_edit_with_valid_local_bounds():
    t = Transport(api_image(image()))
    result = ArkMaterialProvider(KEY, MODEL, transport=t).clean(image(), instructions="去掉水印",
                       bounds={"x": 10, "y": 10, "width": 100, "height": 100})
    assert result.rectangular_crops
    assert "<bbox>10 10 110 110</bbox>" in json.loads(t.calls[0][0].data)["prompt"]


@pytest.mark.parametrize("box", [[-1, 0, 400, 1000], [0, 0, 1001, 1000], [0, 0, 0, 1000],
                                [0, 0, 1000, False], [0, 0, 1.5, 1000], [0, 0, 1000]])
def test_location_rejects_invalid_coordinates(box):
    with pytest.raises(ValueError):
        parse_designs(answer([design(box)]), (1000, 500))


@pytest.mark.parametrize("value", [
    {"complete": True, "designs": []},
    {"complete": "true", "designs": [design([0, 0, 1000, 1000])]},
    {"complete": True, "designs": [design([0, 0, 1000, 1000])] * 129},
    {"complete": True, "designs": [dict(design([0, 0, 1000, 1000]), extra="bad")]},
    answer([design([0, 0, 1000, 1000]), design([0, 0, 1000, 1000])]),
    answer([design([0, 0, 1000, 1000]), design([100, 100, 800, 800])]),
    answer([design([0, 0, 500, 1000]), design([1, 0, 501, 1000])]),
])
def test_location_rejects_missing_duplicate_nested_or_near_duplicate_designs(value):
    with pytest.raises(ValueError):
        parse_designs(value, (1000, 500))


def test_meaningful_overlap_flagged_and_partial_coverage_not_hidden():
    value = answer([design([0, 0, 600, 1000]), design([400, 0, 1000, 1000])])
    value["complete"] = False
    designs, notes = parse_designs(value, (1000, 500))
    assert notes and all(d.uncertain and d.warnings for d in designs)


def test_many_more_than_sixteen_designs_allowed_with_resource_limit():
    rows = [design([x * 100, y * 100, x * 100 + 90, y * 100 + 90]) for y in range(6) for x in range(10)]
    designs, _ = parse_designs(answer(rows), (2000, 2000))
    assert len(designs) == 60


def test_location_private_image_protocol_usage_and_redaction():
    t = Transport(completion(answer([design([0, 0, 1000, 1000], KEY, reason=KEY)])))
    settings = Settings()
    pool = ApiKeyPool(settings)
    result = locator(t, settings, pool).locate(image())
    body = json.loads(t.calls[0][0].data)
    assert body["model"] == "deepseek-flash" and body["thinking"] == {"type": "disabled"}
    assert body["response_format"] == {"type": "json_object"}
    assert t.calls[0][0].full_url == OFFICIAL_ENDPOINT
    assert body["messages"][1]["content"][1]["image_url"]["url"].startswith("data:image/png;base64,")
    assert KEY not in repr(result)
    assert result.usage["requests"] == 1 and result.usage["successes"] == 1
    assert pool.snapshot()["usage"]["requests"] == 1


@pytest.mark.parametrize("payload,status,code,settled", [
    (TimeoutError(KEY), 200, "network_error", False),
    (b"garbage", 200, "invalid_response", False),
    ({"error": {"code": "upstream"}}, 503, "provider_error", False),
    ({"error": {"code": "invalid_key"}}, 401, "authentication", True),
    (completion(answer([design([0, 0, 1100, 1000])])), 200, "invalid_decision", True),
])
def test_location_failure_once_recorded_and_unknown_not_zero(payload, status, code, settled):
    t = Transport(payload, status)
    settings = Settings()
    pool = ApiKeyPool(settings)
    with pytest.raises(ArkProviderError) as caught:
        locator(t, settings, pool).locate(image())
    error = caught.value
    assert error.code == code and error.settled is settled
    assert KEY not in str(error) and len(t.calls) == 1
    assert pool.snapshot()["usage"]["requests"] == 1
    assert error.usage["cost_incomplete"] is (not settled)


def test_location_missing_usage_is_honestly_unknown_even_successful():
    payload = completion()
    del payload["usage"]
    result = locator(Transport(payload)).locate(image())
    assert result.usage["unknown_usage_requests"] == 1
    assert result.usage["estimated_usd_upper_bound"] is None


def test_cancel_after_location_response_retains_usage_once():
    cancelled = [False]
    t = Transport(completion(), before=lambda: cancelled.__setitem__(0, True))
    settings = Settings()
    pool = ApiKeyPool(settings)
    with pytest.raises(ArkCancelled) as caught:
        locator(t, settings, pool).locate(image(), check_cancel=lambda: cancelled[0])
    assert caught.value.usage["requests"] == 1
    assert pool.snapshot()["usage"]["requests"] == 1


def make_pipeline(ark_transport=None, deepseek_transport=None, settings=None):
    ark_transport = ark_transport or Transport(api_image(image()))
    deepseek_transport = deepseek_transport or Transport(completion())
    pipeline = MaterialPipelineProvider(CONFIG, settings or Settings(),
                ark=ArkMaterialProvider(KEY, MODEL, transport=ark_transport),
                locator=locator(deepseek_transport, settings))
    return pipeline, ark_transport, deepseek_transport


def test_pipeline_crops_exact_clean_pixels_maps_bounds_and_reports_real_events():
    p, ark, ds = make_pipeline()
    events, attempts = [], []
    result = p.extract(image((500, 250)), on_progress=lambda *v: events.append(v), on_attempt=attempts.append)
    assert [e[0] for e in events] == ["preparing", "cleanup", "locating", "cropping", "cropping", "saving"]
    assert [a["state"] for a in attempts] == ["submitted", "returned", "submitted", "returned"]
    assert attempts[0]["id"] == attempts[1]["id"] and attempts[2]["id"] == attempts[3]["id"]
    assert result.rectangular_crops and len(result.layers) == 2
    assert result.layers[0].bounds == {"x": 0, "y": 0, "width": 240, "height": 250}
    with Image.open(io.BytesIO(result.base_png)) as whole, Image.open(io.BytesIO(result.layers[0].png)) as cropped:
        assert cropped.size == (480, 500)
        assert cropped.tobytes() == whole.crop((0, 0, 480, 500)).tobytes()
    assert any("未做透明抠图" in w for w in result.layers[0].warnings)
    assert result.provider_usage["seedream"]["generated_images"] == 1
    assert result.provider_usage["deepseek"]["requests"] == 1
    assert len(ark.calls) == len(ds.calls) == 1


def test_disabled_locator_fails_before_charged_cleanup():
    settings = Settings()
    settings.enabled = False
    p, ark, ds = make_pipeline(settings=settings)
    with pytest.raises(ArkProviderError, match="DeepSeek"):
        p.extract(image())
    assert not ark.calls and not ds.calls


def test_pipeline_preserves_real_transparency_without_claiming_opaque_crop_is_transparent():
    p, _, _ = make_pipeline(ark_transport=Transport(api_image(image(transparent=True))))
    result = p.extract(image())
    with Image.open(io.BytesIO(result.layers[0].png)) as first:
        assert first.getchannel("A").getextrema()[0] == 0
    assert not any("未做透明抠图" in warning for warning in result.layers[0].warnings)
    assert any("未做透明抠图" in warning for warning in result.layers[1].warnings)


def test_late_locator_unknown_preserves_cleanup_charge_and_never_replays():
    p, ark, ds = make_pipeline(deepseek_transport=Transport(TimeoutError()))
    with pytest.raises(ArkProviderError) as caught:
        p.extract(image())
    assert len(ark.calls) == len(ds.calls) == 1
    error = caught.value
    assert not error.safe_retry and not error.settled
    assert [a["state"] for a in error.attempts] == ["returned", "unknown"]
    assert error.provider_usage["seedream"]["generated_images"] == 1
    assert error.provider_usage["deepseek"]["cost_incomplete"]


def test_cleanup_safe_rejection_retries_only_that_stage_once():
    t = Transport({"error": {"code": "RateLimitExceeded"}}, 429)
    calls = []
    def twice(req, **opts):
        calls.append(req)
        if len(calls) == 1:
            return t(req, **opts)
        return Transport(api_image(image()))(req, **opts)
    p = MaterialPipelineProvider(CONFIG, Settings(), ark=ArkMaterialProvider(KEY, MODEL, transport=twice),
                locator=locator(Transport(completion())), sleeper=lambda _: None)
    result = p.extract(image())
    assert [a["state"] for a in result.attempts] == ["failed", "returned", "returned"]
    assert len(calls) == 2


def test_edit_uses_one_cleanup_without_another_location_or_alpha_requirement():
    p, ark, ds = make_pipeline()
    result = p.edit(image(), instructions="去掉水印")
    assert result.rectangular_crops and len(result.layers) == 1
    assert len(ark.calls) == 1 and not ds.calls


def test_stop_after_cleanup_prevents_location_retains_paid_attempt():
    stopped = [False]
    t = Transport(api_image(image()), before=lambda: stopped.__setitem__(0, True))
    p, ark, ds = make_pipeline(ark_transport=t)
    with pytest.raises(ArkCancelled) as caught:
        p.extract(image(), check_cancel=lambda: stopped[0])
    assert not ds.calls
    assert caught.value.provider_usage["seedream"]["generated_images"] == 1
    assert caught.value.attempts[0]["state"] == "cancelled"

def test_locator_rate_limit_retry_waits_shared_pool_without_repeating_cleanup():
    now = [0.0]
    settings = Settings()
    pool = ApiKeyPool(settings, clock=lambda: now[0])
    calls = []
    def ds_transport(req, **opts):
        calls.append(req)
        payload, status = ({"error": {"code": "rate_limit_exceeded"}}, 429) if len(calls) == 1 else (completion(), 200)
        return Transport(payload, status)(req, **opts)
    ark = Transport(api_image(image()))
    p = MaterialPipelineProvider(CONFIG, settings, ark=ArkMaterialProvider(KEY, MODEL, transport=ark),
            locator=DeepSeekMaterialLocator(settings, key_pool=pool, transport=ds_transport),
            sleeper=lambda seconds: now.__setitem__(0, now[0] + seconds))
    result = p.extract(image())
    assert len(ark.calls) == 1 and len(calls) == 2 and now[0] == 60
    assert result.provider_usage["deepseek"]["requests"] == 2
    assert result.provider_usage["deepseek"]["failures"] == 1
    assert [a["state"] for a in result.attempts] == ["returned", "failed", "returned"]


def test_arbitrary_429_not_safe_to_retry_or_replay_cleanup():
    p, ark, ds = make_pipeline(deepseek_transport=Transport({"error": {"code": "quota_exceeded"}}, 429))
    with pytest.raises(ArkProviderError) as caught:
        p.extract(image())
    assert not caught.value.safe_retry
    assert len(ark.calls) == len(ds.calls) == 1


def test_locator_does_not_accept_duplicate_json_fields_or_truncated_completion():
    payload = completion()
    payload["choices"][0]["message"]["content"] = '{"complete":true,"complete":false,"designs":[]}'
    with pytest.raises(ArkProviderError, match="定位范围"):
        locator(Transport(payload)).locate(image())
    payload = completion()
    payload["choices"][0]["finish_reason"] = "length"
    with pytest.raises(ArkProviderError, match="定位范围"):
        locator(Transport(payload)).locate(image())


def test_locator_rejects_redirect_and_oversized_response_without_retry():
    for transport in (Transport(completion(), url="http://127.0.0.1/secret"), Transport(b"x" * (2 * 1024 * 1024 + 1))):
        with pytest.raises(ArkProviderError) as caught:
            locator(transport).locate(image())
        assert not caught.value.settled and not caught.value.safe_retry
        assert len(transport.calls) == 1


def test_location_rechecks_disabled_credential_before_dispatch():
    settings = Settings()
    class DisablingPool(ApiKeyPool):
        def acquire(self, exclude_ids=()):
            result = super().acquire(exclude_ids)
            settings.enabled = False
            return result
    t = Transport(completion())
    with pytest.raises(ArkProviderError, match="设置已改变"):
        locator(t, settings, DisablingPool(settings)).locate(image())
    assert not t.calls


def test_stop_during_limiter_wait_never_sends_second_request_or_cleanup():
    stopped = [False]
    p, ark, ds = make_pipeline(deepseek_transport=Transport({"error": {"code": "rate_limit_exceeded"}}, 429))
    p._sleep = lambda _: stopped.__setitem__(0, True)
    with pytest.raises(ArkCancelled) as caught:
        p.extract(image(), check_cancel=lambda: stopped[0])
    assert len(ark.calls) == len(ds.calls) == 1
    assert caught.value.provider_usage["seedream"]["generated_images"] == 1
    assert caught.value.provider_usage["deepseek"]["requests"] == 1

def test_incomplete_http_body_is_unknown_not_safe_retry():
    import http.client
    t = Transport(http.client.IncompleteRead(b"private partial body"))
    with pytest.raises(ArkProviderError) as caught:
        ArkMaterialProvider(KEY, MODEL, transport=t).clean(image())
    assert caught.value.code == "submission_unknown" and not caught.value.settled
    assert not caught.value.safe_retry and "private" not in str(caught.value)


def test_unexpected_adapter_failure_retains_unknown_record_without_error_details():
    p, ark, ds = make_pipeline(deepseek_transport=Transport(RuntimeError(KEY)))
    with pytest.raises(ArkProviderError) as caught:
        p.extract(image())
    assert caught.value.code == "submission_unknown" and not caught.value.settled
    assert caught.value.provider_usage["seedream"]["generated_images"] == 1
    assert caught.value.attempts[-1]["state"] == "unknown"
    assert caught.value.provider_usage["deepseek"]["unknown_usage_requests"] == 1
    assert KEY not in str(caught.value)

def test_coordinate_guide_is_secondary_only_and_preserves_exact_crop_source():
    from hsd_tool.material_locate import coordinate_guide
    source = Image.open(io.BytesIO(image())).convert('RGBA')
    before = source.tobytes()
    guide = coordinate_guide(source)
    assert source.tobytes() == before
    assert guide.size == source.size and guide.tobytes() != before
    t = Transport(completion())
    locator(t).locate(image())
    parts = json.loads(t.calls[0][0].data)['messages'][1]['content']
    assert len(parts) == 3
    first = Image.open(io.BytesIO(base64.b64decode(parts[1]['image_url']['url'].split(',', 1)[1]))).convert('RGBA')
    second = Image.open(io.BytesIO(base64.b64decode(parts[2]['image_url']['url'].split(',', 1)[1]))).convert('RGBA')
    assert first.size == (1000, 1000) and second.size == (1000, 1000)
    assert first.crop((0, 250, 1000, 750)).tobytes() == before
    assert second.tobytes() != first.tobytes()

def test_square_canvas_mapping_preserves_aspect_and_removes_only_known_padding():
    from hsd_tool.material_locate import coordinate_canvas, map_canvas_designs, LocatedDesign
    original = Image.open(io.BytesIO(image())).convert('RGBA')
    canvas, content = coordinate_canvas(original)
    assert canvas.size == (1000, 1000) and content == (0, 250, 1000, 750)
    assert canvas.crop(content).tobytes() == original.tobytes()
    mapped = map_canvas_designs((LocatedDesign('whole', (0, 0, 1000, 1000), False),), content, original.size)
    assert mapped[0].box == (0, 0, 1000, 500)
    with pytest.raises(ValueError, match='padding'):
        map_canvas_designs((LocatedDesign('pad', (0, 0, 100, 200), False),), content, original.size)
    with pytest.raises(ValueError, match='duplicate'):
        map_canvas_designs((LocatedDesign('same1', (0, 0, 1000, 1000), False),
                            LocatedDesign('same2', (0, 250, 1000, 750), False)), content, original.size)


def test_padding_removal_rechecks_nested_real_crop_rectangles():
    from hsd_tool.material_locate import map_canvas_designs
    # These overlap without containment on the square reference, but once only
    # the known synthetic padding is removed A is entirely inside B.
    proposed = answer([design([100, 0, 400, 300], 'A'), design([100, 250, 400, 400], 'B')])
    designs, _ = parse_designs(proposed, (1000, 1000))
    with pytest.raises(ValueError, match='contained mapped'):
        map_canvas_designs(designs, (0, 250, 1000, 750), (1000, 500))


def test_padding_removal_preserves_and_adds_actual_crop_overlap_warnings():
    from hsd_tool.material_locate import map_canvas_designs
    proposed = answer([design([100, 0, 400, 260], 'A', reason='保留文字'),
                       design([100, 259, 400, 500], 'B')])
    designs, _ = parse_designs(proposed, (1000, 1000))
    assert all(not item.uncertain for item in designs)
    actual = map_canvas_designs(designs, (0, 250, 1000, 750), (1000, 500))
    assert actual[0].box == (100, 0, 400, 10)
    assert actual[1].box == (100, 9, 400, 250)
    assert all(item.uncertain and any('范围重叠' in note for note in item.warnings) for item in actual)
    assert '保留文字' in actual[0].warnings
