"""Protocol, resource, privacy and submission-uncertainty controls, no real API."""
import base64
import io
import json
import socket

from PIL import Image, PngImagePlugin
import pytest

from hsd_tool import material_ark as ark
from hsd_tool.cancellation import TaskCancelled


KEY = "unit-only-ark-credential"
MODEL = "doubao-seedream-5-0-flash-260915"


def picture(size=(512, 512), *, alpha=False, empty=False, metadata=False, format="PNG"):
    im = Image.new("RGBA" if alpha else "RGB", size, (110, 25, 190, 255) if alpha else (110, 25, 190))
    if alpha:
        im.putpixel((0, 0), (0, 0, 0, 0))
    if empty:
        im = Image.new("RGBA", size, (255, 0, 0, 0))
    target = io.BytesIO()
    extra = {}
    if metadata:
        text = PngImagePlugin.PngInfo()
        text.add_text("Author", "private_original_filename.png")
        extra["pnginfo"] = text
    im.save(target, format, **extra)
    return target.getvalue()


def item(index, *, size=(512, 512), alpha=None, bounds=None):
    result = {"z_index": index, "size": f"{size[0]}x{size[1]}", "output_format": "png",
              "b64_json": base64.b64encode(picture(size, alpha=bool(index) if alpha is None else alpha)).decode()}
    if index:
        result.update(name="完整设计", description="保留人物、文字和内部底板", bounding_box=bounds or {
            "absolute": [0, 0, 512, 512], "normalized": [0, 0, 1000, 1000]})
    return result


def result_data():
    return {"data": [item(0), item(1)], "model": MODEL,
            "usage": {"generated_images": 2, "input_images": 1, "output_tokens": 2048}}


class Recorder:
    def __init__(self, data=None, status=200, *, raw=None, headers=None, url=ark.ENDPOINT, callback=None):
        self.data = result_data() if data is None else data
        self.status = status
        self.raw = raw
        self.headers = headers or {"x-request-id": "test-request-01"}
        self.url = url
        self.calls = []
        self.callback = callback

    def __call__(self, request, **options):
        self.calls.append((request, options))
        if self.callback:
            self.callback()
        return ark.HttpReply(self.status, self.raw if self.raw is not None else json.dumps(self.data).encode(), self.headers, self.url)


def provider(transport):
    return ark.ArkMaterialProvider(KEY, MODEL, transport=transport)


def test_extract_uses_fixed_authenticated_base64_protocol_and_removes_metadata():
    transport = Recorder()
    output = provider(transport).extract(picture(metadata=True), instructions="保留底板")
    request, options = transport.calls[0]
    body = json.loads(request.data)
    assert request.full_url == ark.ENDPOINT
    assert request.method == "POST"
    assert request.get_header("Authorization") == "Bearer " + KEY
    assert body["layer_decomposition"] is True
    assert body["response_format"] == "b64_json"
    assert body["size"] == "2K"
    assert body["output_format"] == "png"
    assert body["watermark"] is False
    assert "背景" in body["prompt"] and "完整设计" in body["prompt"] and "保留底板" in body["prompt"]
    assert "private_original_filename" not in base64.b64decode(body["image"].split(",", 1)[1]).decode("latin1")
    assert "background" not in body and "sequential_image_generation" not in body
    assert options == {"timeout": 240, "max_bytes": ark.MAX_RESPONSE_BYTES}
    assert len(output.layers) == 1
    assert output.layers[0].bounds == {"x": 0, "y": 0, "width": 512, "height": 512}
    assert output.usage["generated_images"] == 2
    assert output.request_id == "test-request-01"
    assert output.base_png.startswith(b"\x89PNG")
    assert KEY not in repr(output)
    assert "b64_json" not in repr(output)


def test_upscale_only_satisfies_upstream_minimum_and_keeps_source_box():
    transport = Recorder()
    output = provider(transport).extract(picture((256, 256)))
    body = json.loads(transport.calls[0][0].data)
    with Image.open(io.BytesIO(base64.b64decode(body["image"].split(",", 1)[1]))) as im:
        assert im.size == (512, 512)
    assert output.layers[0].bounds["width"] == 256
    assert any("不代表恢复细节" in note for note in output.warnings)


def test_embedded_icc_is_converted_before_private_metadata_is_stripped():
    from PIL import ImageCms
    source = Image.new("RGBA", (512, 512), (110, 25, 190, 255))
    source.putpixel((0, 0), (0, 0, 0, 0))
    source.info['icc_profile'] = ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
    exif = source.getexif()
    exif[315] = 'private metadata must not leave server'
    source.info['exif'] = exif.tobytes()
    normal = ark.normalise_rgba(source)
    assert normal.getpixel((100, 100)) == (110, 25, 190, 255)
    assert normal.getpixel((0, 0))[3] == 0
    assert normal.info == {}
    encoded = ark._encode(normal)
    assert b'private metadata' not in encoded
    with Image.open(io.BytesIO(encoded)) as actual:
        assert 'icc_profile' not in actual.info and 'exif' not in actual.info


def test_bad_icc_is_not_silently_dropped_while_claiming_colours_were_preserved():
    source = Image.new("RGB", (512, 512), (20, 30, 40))
    source.info['icc_profile'] = b'not a valid profile'
    with pytest.raises(ValueError, match='sRGB'):
        ark.normalise_rgba(source)


def test_exif_orientation_is_applied_before_metadata_removal():
    source = Image.new("RGB", (4, 6), (20, 30, 40))
    exif = source.getexif()
    exif[274] = 6
    source.info['exif'] = exif.tobytes()
    normal = ark.normalise_rgba(source)
    assert normal.size == (6, 4)
    assert normal.info == {}


def test_bounds_map_output_canvas_to_source_not_output_layer_size():
    data = result_data()
    data["data"][1] = item(1, size=(256, 256), bounds={"absolute": [128, 128, 384, 384], "normalized": [250, 250, 750, 750]})
    output = provider(Recorder(data)).extract(picture((1024, 1024)))
    assert output.layers[0].bounds == {"x": 256, "y": 256, "width": 512, "height": 512}


def test_layers_are_sorted_and_base_is_not_a_design():
    data = result_data()
    data["data"] = [item(2), item(0), item(1)]
    output = provider(Recorder(data)).extract(picture())
    assert [value.z_index for value in output.layers] == [1, 2]


def test_native_design_is_one_submission_and_keeps_complete_layer_canvas_and_soft_alpha():
    image = Image.new("RGBA", (320, 640), (0, 0, 0, 0))
    image.putpixel((0, 0), (255, 255, 255, 255))  # Legitimate isolated ornament.
    image.putpixel((319, 639), (30, 40, 50, 255))  # Detached foot/letter at edge.
    image.putpixel((160, 300), (200, 100, 50, 37))
    png = ark._encode(image)
    data = result_data()
    data["data"][1] = item(1, size=image.size)
    data["data"][1]["b64_json"] = base64.b64encode(png).decode()
    transport = Recorder(data)
    result = provider(transport).extract_design(picture(), instructions="保留完整裙摆和鞋子")
    assert len(transport.calls) == 1 and len(result.layers) == 1
    payload = json.loads(transport.calls[0][0].data)
    assert payload["layer_decomposition"] is True and payload["size"] == "2K"
    assert "一个前景图层" in payload["prompt"] and "不画白底或棋盘格" in payload["prompt"]
    assert "不新增白色贴纸边、黑色外描边、光晕或投影" in payload["prompt"]
    assert "保留原设计内部线条和白色内容" in payload["prompt"]
    assert "保留完整裙摆和鞋子" in payload["prompt"]
    with Image.open(io.BytesIO(result.layers[0].png)) as actual:
        assert actual.size == image.size and actual.tobytes() == image.tobytes()
    assert result.usage == data["usage"]


def test_native_design_rejects_multiple_layers_without_selecting_or_resubmitting():
    data = result_data()
    data["data"].append(item(2))
    data["usage"]["generated_images"] = 3
    transport = Recorder(data)
    with pytest.raises(ark.ArkProviderError) as error:
        provider(transport).extract_design(picture())
    assert error.value.code == "ambiguous_design"
    assert error.value.settled and not error.value.safe_retry and len(transport.calls) == 1
    assert error.value.usage["generated_images"] == 3


@pytest.mark.parametrize("png,code", [(picture(alpha=True, empty=True), "empty_layer"),
                                     (picture(alpha=False), "missing_alpha")])
def test_native_design_rejects_invalid_alpha_without_paid_fallback(png, code):
    data = result_data();data["data"][1]["b64_json"] = base64.b64encode(png).decode()
    transport = Recorder(data)
    with pytest.raises(ark.ArkProviderError) as error:
        provider(transport).extract_design(picture())
    assert error.value.code == code and len(transport.calls) == 1
    assert error.value.usage == data["usage"] and not error.value.safe_retry


def test_native_design_warns_on_fully_opaque_alpha_instead_of_deleting_pixels():
    data = result_data()
    rgba = Image.new("RGBA", (512, 512), (250, 250, 250, 255))
    data["data"][1]["b64_json"] = base64.b64encode(ark._encode(rgba)).decode()
    result = provider(Recorder(data)).extract_design(picture())
    with Image.open(io.BytesIO(result.layers[0].png)) as actual:
        assert actual.tobytes() == rgba.tobytes()
    assert any("没有透明区域" in warning for warning in result.layers[0].warnings)


def test_native_target_is_a_prompt_hint_and_maps_the_whole_image_upscale():
    transport = Recorder()
    result = provider(transport).extract_design(
        picture((256, 256)), bounds={"x": 10, "y": 20, "width": 100, "height": 150})
    payload = json.loads(transport.calls[0][0].data)
    assert "<bbox>39 78 430 665</bbox>" in payload["prompt"]
    assert "延伸到框外时仍整体保留" in payload["prompt"]
    with Image.open(io.BytesIO(base64.b64decode(payload["image"].split(",", 1)[1]))) as reference:
        assert reference.size == (512, 512), "the hint must not crop the reference"
    with Image.open(io.BytesIO(result.layers[0].png)) as actual:
        assert actual.size == (512, 512), "the hint must not crop the returned layer"


@pytest.mark.parametrize("bounds", [
    {}, {"x": 0}, {"x": -1, "y": 0, "width": 10, "height": 10},
    {"x": 0, "y": True, "width": 10, "height": 10},
    {"x": 0, "y": 0, "width": 0, "height": 10},
    {"x": 500, "y": 0, "width": 20, "height": 10},
    {"x": 0, "y": 0, "width": 20.0, "height": 10},
    {"x": 0, "y": 0, "width": 20, "height": 10, "extra": 1},
])
def test_native_target_rejects_invalid_pixels_before_any_paid_submission(bounds):
    transport = Recorder()
    with pytest.raises(ark.ArkProviderError) as error:
        provider(transport).extract_design(picture(), bounds=bounds)
    assert error.value.code == "invalid_bounds" and not transport.calls


@pytest.mark.parametrize("change,code", [
    (lambda d: d["data"].pop(), "no_designs"),
    (lambda d: d["data"][1].update(z_index=0), "invalid_response"),
    (lambda d: d["data"][1].update(z_index=True), "invalid_response"),
    (lambda d: d["data"][1].update(z_index=3), "invalid_response"),
    (lambda d: d["data"][1].update(error={"message": KEY}), "invalid_response"),
    (lambda d: d["data"][1].update(size="4096x4096"), "invalid_response"),
    (lambda d: d["data"][1].update(output_format="jpeg"), "invalid_response"),
    (lambda d: d["data"][1].update(b64_json="not base64 *"), "invalid_response"),
    (lambda d: d["data"][1].update(b64_json=base64.b64encode(b"not a png").decode()), "invalid_image"),
    (lambda d: d["data"][1].update(bounding_box={"absolute": [-1, 0, 10, 10]}), "invalid_bounds"),
    (lambda d: d["data"][1].update(bounding_box={"absolute": [0, 0, 513, 512]}), "invalid_bounds"),
    (lambda d: d["data"][1].update(bounding_box={"absolute": [0, 0, 0, 512]}), "invalid_bounds"),
    (lambda d: d["data"][1].update(bounding_box={"absolute": [False, 0, 512, 512]}), "invalid_bounds"),
    (lambda d: d["data"][1].update(bounding_box={"normalized": [0, 0, 1000, 1000]}), "invalid_bounds"),
    (lambda d: d["data"][1].update(bounding_box={"absolute": [0, 0, 512, 512], "normalized": [0, 0, 500, 500]}), "invalid_bounds"),
])
def test_invalid_layer_data_never_retried_and_keeps_real_known_usage(change, code):
    data = result_data()
    change(data)
    transport = Recorder(data)
    with pytest.raises(ark.ArkProviderError) as raised:
        provider(transport).extract(picture())
    assert raised.value.code == code
    assert raised.value.settled is True
    assert raised.value.safe_retry is False
    assert raised.value.usage["generated_images"] == 2
    assert len(transport.calls) == 1
    assert KEY not in str(raised.value)


def test_external_url_is_never_fetched_even_when_provider_returns_one():
    data = result_data()
    del data["data"][1]["b64_json"]
    data["data"][1]["url"] = "http://127.0.0.1/private"
    transport = Recorder(data)
    with pytest.raises(ark.ArkProviderError, match="未按约定"):
        provider(transport).extract(picture())
    assert len(transport.calls) == 1


@pytest.mark.parametrize("url", ["http://127.0.0.1/", "https://169.254.169.254/", "https://untrusted.example/", ark.ENDPOINT + "?key=bad"])
def test_transport_redirect_contract_is_enforced(url):
    transport = Recorder(url=url)
    with pytest.raises(ark.ArkProviderError) as error:
        provider(transport).extract(picture())
    assert not error.value.settled
    assert not error.value.safe_retry
    assert len(transport.calls) == 1


def test_non_alpha_png_is_not_misrepresented_as_transparent():
    data = result_data()
    data["data"][1] = item(1, alpha=False)
    with pytest.raises(ark.ArkProviderError) as error:
        provider(Recorder(data)).extract(picture())
    assert error.value.code == "missing_alpha"


def test_empty_transparent_layer_is_rejected():
    data = result_data()
    data["data"][1]["b64_json"] = base64.b64encode(picture(empty=True)).decode()
    with pytest.raises(ark.ArkProviderError) as error:
        provider(Recorder(data)).extract(picture())
    assert error.value.code == "empty_layer"


def test_full_opaque_alpha_layer_keeps_internal_design_board_but_warns():
    data = result_data()
    image = Image.new("RGBA", (512, 512), (255, 255, 255, 255))
    target = io.BytesIO()
    image.save(target, "PNG")
    data["data"][1]["b64_json"] = base64.b64encode(target.getvalue()).decode()
    output = provider(Recorder(data)).extract(picture())
    assert any("内部底板" in note for note in output.layers[0].warnings)


def test_model_label_is_untrusted_text_and_never_contains_key():
    data = result_data()
    data["data"][1].update(name="<script>" + KEY + "\x00", description=KEY)
    output = provider(Recorder(data)).extract(picture())
    assert KEY not in output.layers[0].label + output.layers[0].description
    assert "\x00" not in output.layers[0].label
    assert "<script>" in output.layers[0].label  # UI must use textContent, not HTML.


def test_layer_limit_explicitly_warns_about_unverified_complete_coverage():
    data = result_data()
    data["data"] = [item(i) for i in range(17)]
    output = provider(Recorder(data)).extract(picture())
    assert len(output.layers) == 16
    assert any("未提取设计" in note for note in output.warnings)
    data["data"].append(item(17))
    with pytest.raises(ark.ArkProviderError):
        provider(Recorder(data)).extract(picture())


def test_no_usage_does_not_become_zero_usage():
    data = result_data()
    del data["usage"]
    assert provider(Recorder(data)).extract(picture()).usage == {}


@pytest.mark.parametrize("raw", [b"not-json", b"[]", b'{"data":[],"data":[]}', b'{"usage":NaN}', b'\xff'])
def test_invalid_json_is_unknown_and_never_retried(raw):
    transport = Recorder(raw=raw)
    with pytest.raises(ark.ArkProviderError) as error:
        provider(transport).extract(picture())
    assert not error.value.settled
    assert not error.value.safe_retry
    assert len(transport.calls) == 1


@pytest.mark.parametrize("status", [500, 502, 503, 504])
def test_gateway_or_server_failures_never_prove_no_paid_work(status):
    data = {"error": {"code": "InternalError", "message": KEY}, "usage": {"generated_images": 0}}
    transport = Recorder(data, status=status)
    with pytest.raises(ark.ArkProviderError) as error:
        provider(transport).extract(picture())
    assert not error.value.safe_retry
    assert not error.value.settled
    assert KEY not in str(error.value)
    assert len(transport.calls) == 1


def test_explicit_rate_rejection_can_be_retried_by_task_service_once():
    transport = Recorder({"error": {"code": "RateLimitExceeded", "message": KEY}}, status=429)
    with pytest.raises(ark.ArkProviderError) as error:
        provider(transport).extract(picture())
    assert error.value.settled
    assert error.value.safe_retry
    assert error.value.usage == {}
    assert len(transport.calls) == 1  # Provider never retries itself.
    assert KEY not in str(error.value)


@pytest.mark.parametrize("code", ["RateLimitExceeded.EndpointRPMExceeded", "ModelAccountIpmRateLimitExceeded", "ServerOverloaded", "RequestBurstTooFast"])
def test_documented_pre_generation_throttle_has_one_retry_eligibility(code):
    transport = Recorder({"error": {"code": code}}, status=429)
    with pytest.raises(ark.ArkProviderError) as error:
        provider(transport).extract(picture())
    assert error.value.safe_retry and error.value.settled
    assert len(transport.calls) == 1


@pytest.mark.parametrize("code", ["QuotaExceeded", "SetLimitExceeded", "AccountQuotaExceeded", "UnknownError"])
def test_non_transient_or_unrecognized_429_does_not_waste_another_paid_attempt(code):
    transport = Recorder({"error": {"code": code}}, status=429)
    with pytest.raises(ark.ArkProviderError) as error:
        provider(transport).extract(picture())
    assert not error.value.safe_retry


@pytest.mark.parametrize("usage", [{"generated_images": 1}, {"generated_images": -1}, {"generated_images": "0"}, {"generated_images": False}])
def test_inconsistent_rate_reply_cannot_trigger_duplicate_submission(usage):
    transport = Recorder({"error": {"code": "RateLimitExceeded"}, "usage": usage}, status=429)
    with pytest.raises(ark.ArkProviderError) as error:
        provider(transport).extract(picture())
    assert not error.value.safe_retry
    assert not error.value.settled


def test_timeout_after_submission_never_automatically_resends():
    calls = []
    def fail(request, **options):
        calls.append(request)
        raise socket.timeout(KEY)
    with pytest.raises(ark.ArkProviderError) as error:
        provider(fail).extract(picture())
    assert error.value.code == "submission_unknown"
    assert not error.value.settled and not error.value.safe_retry
    assert len(calls) == 1
    assert KEY not in str(error.value)


def test_cancel_before_submission_makes_no_request():
    transport = Recorder()
    with pytest.raises(ark.ArkCancelled) as error:
        provider(transport).extract(picture(), check_cancel=lambda: True)
    assert error.value.settled
    assert not transport.calls


def test_cancel_callback_raising_existing_task_exception_is_supported():
    def check():
        raise TaskCancelled()
    with pytest.raises(ark.ArkCancelled):
        provider(Recorder()).extract(picture(), check_cancel=check)


def test_cancel_during_request_receives_response_and_preserves_known_usage():
    stopped = False
    def request_finishes():
        nonlocal stopped
        stopped = True
    transport = Recorder(callback=request_finishes)
    with pytest.raises(ark.ArkCancelled) as error:
        provider(transport).extract(picture(), check_cancel=lambda: stopped)
    assert error.value.settled
    assert error.value.usage["generated_images"] == 2
    assert error.value.request_id == "test-request-01"
    assert len(transport.calls) == 1


def test_cancel_during_timeout_remains_unknown_instead_of_claiming_upstream_stopped():
    stopped = False
    def fail(request, **options):
        nonlocal stopped
        stopped = True
        raise TimeoutError(KEY)
    with pytest.raises(ark.ArkCancelled) as error:
        provider(fail).extract(picture(), check_cancel=lambda: stopped)
    assert not error.value.settled
    assert error.value.code == "submission_unknown"


@pytest.mark.parametrize("key,model", [("", MODEL), ("a\nb", MODEL), (KEY, "fal-ai/model"), (KEY, "doubao-seedream-4-5-251128"), (KEY, "doubao-seededit-3-0-i2i")])
def test_unsupported_config_is_rejected_before_network(key, model):
    with pytest.raises(ark.ArkProviderError):
        ark.ArkMaterialProvider(key, model)


def test_private_endpoint_id_is_supported_without_guessing_its_mapping():
    assert ark.ArkMaterialProvider(KEY, "ep-20261022010101-abcdef").model_id.startswith("ep-")


@pytest.mark.parametrize("source", [b"broken image", picture((1024, 16)), picture(format="GIF")])
def test_invalid_source_never_leaves_server(source):
    transport = Recorder()
    with pytest.raises(ark.ArkProviderError):
        provider(transport).extract(source)
    assert not transport.calls


def test_response_byte_resource_limit_is_enforced_for_injected_transport(monkeypatch):
    monkeypatch.setattr(ark, "MAX_RESPONSE_BYTES", 10)
    with pytest.raises(ark.ArkProviderError) as error:
        provider(Recorder()).extract(picture())
    assert not error.value.settled


def test_aggregate_pixel_limit_stops_layer_decode_without_resubmitting(monkeypatch):
    monkeypatch.setattr(ark, "MAX_TOTAL_OUTPUT_PIXELS", 512 * 512)
    with pytest.raises(ark.ArkProviderError) as error:
        provider(Recorder()).extract(picture())
    assert error.value.code == "response_resource_limit"
    assert error.value.settled
    assert not error.value.safe_retry


def test_edit_uses_transparent_image_protocol_and_marks_generated_changes():
    data = {"data": [{key: value for key, value in item(1).items() if key in {"size", "b64_json", "output_format"}}], "usage": {"generated_images": 1}}
    transport = Recorder(data)
    output = provider(transport).edit(picture(alpha=True), instructions="清理边缘", bounds={"x": 10, "y": 20, "width": 100, "height": 80})
    request = json.loads(transport.calls[0][0].data)
    assert request["background"] == "transparent"
    assert "layer_decomposition" not in request
    assert "<bbox>19 39 215 196</bbox>" in request["prompt"]
    assert len(output.layers) == 1
    assert output.base_png == b""
    assert any("其他区域" in note for note in output.warnings)
    assert any("模型生成" in note for note in output.warnings)


@pytest.mark.parametrize("bounds", [{"x": -1, "y": 0, "width": 1, "height": 1}, {"x": 0, "y": 0, "width": 513, "height": 1}, {"x": 0, "y": 0, "width": True, "height": 1}, {"x": 0}])
def test_edit_bounds_are_validated_before_submission(bounds):
    transport = Recorder()
    with pytest.raises(ark.ArkProviderError):
        provider(transport).edit(picture(alpha=True), instructions="修补", bounds=bounds)
    assert not transport.calls


def test_edit_requires_actual_alpha_input_instead_of_claiming_transparency():
    transport = Recorder()
    with pytest.raises(ark.ArkProviderError) as error:
        provider(transport).edit(picture(), instructions="去背景")
    assert error.value.code == "missing_alpha"
    assert not transport.calls


def test_edit_bad_result_preserves_usage_and_does_not_retry():
    transport = Recorder({"data": [], "usage": {"generated_images": 1}})
    with pytest.raises(ark.ArkProviderError) as error:
        provider(transport).edit(picture(alpha=True), instructions="修补")
    assert error.value.settled
    assert not error.value.safe_retry
    assert error.value.usage["generated_images"] == 1


@pytest.mark.parametrize("operation", ["clean", "edit", "extract_design"])
def test_every_interaction_prompt_uses_normalized_0_999_not_pixel_coordinates(operation):
    data = result_data()
    if operation != "extract_design":
        data["data"] = [item(1)]
    transport = Recorder(data)
    getattr(provider(transport), operation)(
        picture(alpha=True), instructions="保留原图",
        bounds={"x": 128, "y": 64, "width": 256, "height": 384})
    prompt = json.loads(transport.calls[0][0].data)["prompt"]
    assert "<bbox>250 125 750 875</bbox>" in prompt
    assert "<bbox>128 64 384 448</bbox>" not in prompt
    assert "描边" in prompt and "白色内容" in prompt


def test_input_bounds_clamp_at_999_while_response_normalized_bounds_still_accept_1000():
    assert ark._prompt_bounds({"x": 0, "y": 0, "width": 512, "height": 512}, (512, 512)) == (0, 0, 999, 999)
    assert ark._prompt_bounds({"x": 5999, "y": 5999, "width": 1, "height": 1}, (6000, 6000)) == (998, 998, 999, 999)
    assert provider(Recorder()).extract(picture()).layers[0].bounds["width"] == 512


def single_image_data(png=None):
    png = picture(alpha=True) if png is None else png
    with Image.open(io.BytesIO(png)) as image:
        size = image.size
    return {"data": [{"size": f"{size[0]}x{size[1]}", "output_format": "png",
                      "b64_json": base64.b64encode(png).decode()}],
            "usage": {"generated_images": 1, "input_images": 1}}


def test_refine_is_one_transparent_native_2k_request_and_preserves_every_output_pixel():
    image = Image.new("RGBA", (320, 640), (0, 0, 0, 0))
    image.putpixel((0, 0), (255, 255, 255, 255))
    image.putpixel((160, 300), (10, 20, 30, 37))
    image.putpixel((319, 639), (10, 20, 30, 255))
    transport = Recorder(single_image_data(ark._encode(image)))
    output = provider(transport).refine_design(picture(alpha=True), instructions="保留鞋子")
    assert len(transport.calls) == 1
    body = json.loads(transport.calls[0][0].data)
    assert body["size"] == "2K" and body["background"] == "transparent"
    assert "layer_decomposition" not in body
    assert "约80%" not in body["prompt"] and "保留鞋子" in body["prompt"]
    assert "保持原有构图、位置、比例" in body["prompt"] and "不移动或重新排版" in body["prompt"]
    assert "不新增白色贴纸边、黑色外描边、光晕或投影" in body["prompt"]
    assert "保留原设计内部线条及白色内容" in body["prompt"]
    with Image.open(io.BytesIO(output.layers[0].png)) as actual:
        assert actual.size == image.size and actual.tobytes() == image.tobytes()
    assert output.no_upscale and output.rectangular_crops
    assert output.usage == {"generated_images": 1, "input_images": 1}


@pytest.mark.parametrize("format", ["PNG", "JPEG", "WEBP", "RGBA"])
def test_refine_opaque_input_uses_one_official_opaque_request_without_cutting_or_fake_alpha(format):
    native = Image.new("RGB", (320, 640), (253, 242, 231))
    native.putpixel((0, 0), (80, 20, 90))
    native.putpixel((319, 639), (50, 120, 30))
    transport = Recorder(single_image_data(ark._encode(native)))
    source = ark._encode(Image.new("RGBA", (512, 512), (110, 25, 190, 255))) if format == "RGBA" else picture(format=format)
    result = provider(transport).refine_design(source)
    assert len(transport.calls) == 1
    body = json.loads(transport.calls[0][0].data)
    assert body["background"] == "opaque" and body["size"] == "2K"
    assert body["output_format"] == "png" and body["response_format"] == "b64_json"
    assert body["watermark"] is False and "layer_decomposition" not in body
    assert "保持原有背景和内部底板" in body["prompt"] and "不擅自抠图" in body["prompt"]
    raw = base64.b64decode(body["image"].split(",", 1)[1])
    with Image.open(io.BytesIO(raw)) as sent:
        assert sent.size == (512, 512) and sent.getchannel("A").getextrema() == (255, 255)
    with Image.open(io.BytesIO(result.layers[0].png)) as actual:
        assert actual.size == native.size and actual.tobytes() == native.convert("RGBA").tobytes()
    assert result.no_upscale and result.rectangular_crops
    assert any("原素材无透明背景" in warning for warning in result.warnings)
    assert result.usage == {"generated_images": 1, "input_images": 1}


def test_refine_empty_image_and_cancel_before_dispatch_never_spend():
    transport = Recorder(single_image_data())
    with pytest.raises(ark.ArkProviderError) as error:
        provider(transport).refine_design(picture(alpha=True, empty=True))
    assert error.value.code == "empty_layer" and not transport.calls
    with pytest.raises(ark.ArkCancelled):
        provider(transport).refine_design(picture(alpha=True), check_cancel=lambda: True)
    assert not transport.calls


def test_refine_opaque_return_is_preserved_with_visible_warning_instead_of_mask_deletion():
    rgba = ark._encode(Image.new("RGBA", (512, 512), (255, 255, 255, 255)))
    output = provider(Recorder(single_image_data(rgba))).refine_design(picture(alpha=True))
    assert any("未返回透明区域" in warning for warning in output.warnings)
    with Image.open(io.BytesIO(output.layers[0].png)) as actual:
        assert actual.getchannel("A").getextrema() == (255, 255)


@pytest.mark.parametrize("data", [{"data": []}, {"data": [item(1), item(2)]}])
def test_refine_invalid_or_multiple_results_keep_paid_usage_without_fallback(data):
    data["usage"] = {"generated_images": 2}
    transport = Recorder(data)
    with pytest.raises(ark.ArkProviderError) as error:
        provider(transport).refine_design(picture(alpha=True))
    assert error.value.code == "invalid_response" and error.value.settled
    assert error.value.usage == {"generated_images": 2}
    assert not error.value.safe_retry and len(transport.calls) == 1


def test_refine_lost_reply_stays_unknown_and_never_posts_again():
    transport = Recorder(raw=b"not-json")
    with pytest.raises(ark.ArkProviderError) as error:
        provider(transport).refine_design(picture(alpha=True))
    assert not error.value.settled and not error.value.safe_retry
    assert len(transport.calls) == 1


def test_default_transport_builds_no_redirect_opener_and_uses_fixed_destination(monkeypatch):
    class Response:
        status = 200
        headers = {"Content-Length": "2"}
        def geturl(self):
            return ark.ENDPOINT
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def read(self, count):
            if not hasattr(self, "read_once"):
                self.read_once = True
                return b"{}"
            return b""
    class Opener:
        def open(self, request, timeout):
            assert request.full_url == ark.ENDPOINT
            assert timeout == 10
            return Response()
    def build(handler):
        assert isinstance(handler, ark._NoRedirect)
        assert handler.redirect_request(None, None, None, None, None, "http://127.0.0.1") is None
        return Opener()
    monkeypatch.setattr(ark.urllib.request, "build_opener", build)
    response = ark._default_transport(ark.urllib.request.Request(ark.ENDPOINT), timeout=10, max_bytes=10)
    assert response.body == b"{}"
