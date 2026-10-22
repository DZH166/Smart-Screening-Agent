"""Synthetic HTTP/pixel controls only; no credentials, network or business labels."""
import base64
import copy
import io
import json
from unittest.mock import patch

from PIL import Image, PngImagePlugin
import pytest

from hsd_tool.cancellation import TaskCancelled
from hsd_tool.material_providers import (
    DEEPSEEK_ENDPOINT, DEEPSEEK_MODEL, MAX_IMAGE_PIXELS, MAX_JSON_BYTES,
    QUEUE_ORIGIN, REPAIR_MODEL, SAM_MODEL, DeepSeekInventoryClient,
    FalMaterialClient, HttpReply, MaterialCancelled, MaterialProviderError,
    _NoRedirect, _default_transport,
)


KEY = "synthetic-provider-credential-not-real"
MEDIA = "https://v3.fal.media/files/test/synthetic.png"
BOUNDS = {"x": 10, "y": 10, "width": 30, "height": 25}
INVENTORY = {"designs": [{"label": "完整设计", "kind": "cutout", "bounds": BOUNDS,
                           "prompt": "A complete design including attached lettering"}],
             "watermarks": [], "warnings": []}


def png(size=(100, 80), color="white", mode="RGBA", *, metadata=False):
    image = Image.new(mode, size, color)
    stream = io.BytesIO()
    params = {}
    if metadata:
        info = PngImagePlugin.PngInfo()
        info.add_text("private_path", "C:/private/business-secret.png")
        params["pnginfo"] = info
    image.save(stream, "PNG", **params)
    return stream.getvalue()


def as_json(value):
    return json.dumps(value, ensure_ascii=False).encode("utf-8")


def inventory_reply(value=None, **updates):
    payload = {"id": "chat-synthetic", "model": DEEPSEEK_MODEL,
               "choices": [{"finish_reason": "stop", "message": {
                   "content": json.dumps(copy.deepcopy(INVENTORY if value is None else value))}}],
               "usage": {"prompt_tokens": 100, "completion_tokens": 50}}
    payload.update(updates)
    return payload


def submitted(model=SAM_MODEL, identity="synthetic-request-1"):
    prefix = QUEUE_ORIGIN + "/" + "/".join(model.split("/")[:2]) + "/requests/" + identity
    return {"request_id": identity, "status_url": prefix + "/status", "response_url": prefix,
            "cancel_url": prefix + "/cancel"}


class Clock:
    def __init__(self):
        self.value = 0
        self.sleeps = []

    def __call__(self):
        return self.value

    def sleep(self, amount):
        self.sleeps.append(amount)
        self.value += max(.001, amount)


class Http:
    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def __call__(self, request, *, timeout, max_bytes):
        self.calls.append((request, timeout, max_bytes))
        assert self.outcomes, "Unexpected extra HTTP call"
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        if callable(outcome):
            return outcome(request)
        if isinstance(outcome, HttpReply):
            return outcome
        return HttpReply(200, outcome if isinstance(outcome, bytes) else as_json(outcome), {}, request.full_url)


def mask_pipeline(mask=None, result=None, model=SAM_MODEL):
    return [submitted(model), {"status": "COMPLETED"}, result or {"masks": [{"url": MEDIA}], "scores": [.9]},
            mask or png((50, 40), "white")]


def fal(http, **updates):
    clock = updates.pop("clock", None) or Clock()
    return FalMaterialClient(KEY, transport=http, clock=clock, sleeper=clock.sleep,
                             queue_timeout=updates.pop("queue_timeout", .5), drain_timeout=updates.pop("drain_timeout", .5),
                             poll_interval=.05, **updates)


def test_inventory_fixed_protocol_no_metadata_and_no_acceptance_claim():
    http = Http(inventory_reply())
    client = DeepSeekInventoryClient(KEY, transport=http, review_tiles=False)
    result = client.inventory(png(metadata=True), 100, 80)
    request, timeout, max_bytes = http.calls[0]
    payload = json.loads(request.data)
    assert request.full_url == DEEPSEEK_ENDPOINT and request.method == "POST"
    assert request.get_header("Authorization") == "Bearer " + KEY
    assert timeout == 90 and max_bytes == MAX_JSON_BYTES
    assert payload["model"] == DEEPSEEK_MODEL and not payload["stream"]
    assert payload["thinking"] == {"type": "disabled"}
    assert payload["response_format"] == {"type": "json_object"}
    content = payload["messages"][0]["content"]
    assert "JSON" in content[0]["text"] and "内部底板" in content[0]["text"]
    assert content[1]["image_url"]["detail"] == "original"
    image_bytes = base64.b64decode(content[1]["image_url"]["url"].split(",", 1)[1])
    with Image.open(io.BytesIO(image_bytes)) as image:
        assert image.size == (100, 80) and not image.info
    assert result["designs"] == INVENTORY["designs"]
    assert result["variant"] == "full_only" and "自动通过" not in json.dumps(result, ensure_ascii=False)
    assert result["usage"] == {"requests": 1, "successes": 1, "failures": 0, "prompt_tokens": 100,
                                "completion_tokens": 50, "unknown_usage_requests": 0}
    assert KEY not in repr(result) and "data:image" not in repr(result)


def test_full_and_four_overlapping_views_map_local_pixels_and_retain_seam_warning():
    empty = {"designs": [], "watermarks": [], "warnings": []}
    local = {"designs": [{"label": "右下完整设计", "kind": "rectangle",
                           "bounds": {"x": 5, "y": 5, "width": 30, "height": 20}, "prompt": "whole badge"}],
             "watermarks": [], "warnings": []}
    seam = copy.deepcopy(local)
    seam["designs"][0]["bounds"]["x"] = 0
    http = Http(inventory_reply(empty), inventory_reply(empty), inventory_reply(seam), inventory_reply(empty),
                inventory_reply(local))
    result = DeepSeekInventoryClient(KEY, transport=http).inventory(png(), 100, 80)
    assert len(http.calls) == 5
    assert result["designs"][0]["bounds"] == {"x": 45, "y": 37, "width": 30, "height": 20}
    assert len(result["designs"]) == 1 and any("分块边缘" in v for v in result["warnings"])
    assert result["usage"]["requests"] == result["usage"]["successes"] == 5
    sizes = []
    for request, _, _ in http.calls:
        uri = json.loads(request.data)["messages"][0]["content"][1]["image_url"]["url"]
        with Image.open(io.BytesIO(base64.b64decode(uri.split(",")[1]))) as view:
            sizes.append(view.size)
    assert sizes == [(100, 80)] + [(60, 48)] * 4


def test_inventory_dedupes_spatial_views_but_does_not_merge_nonoverlapping_designs():
    # The same full-image box is deliberately supplied as an interior tile box.
    source = {"designs": [{"label": "完整设计", "kind": "cutout", "bounds": {"x": 20, "y": 20, "width": 20, "height": 20},
                            "prompt": "design"}], "watermarks": [], "warnings": []}
    empty = {"designs": [], "watermarks": [], "warnings": []}
    last = copy.deepcopy(source)
    last["designs"][0]["bounds"] = {"x": 5, "y": 5, "width": 20, "height": 20}
    http = Http(inventory_reply(source), inventory_reply(source), inventory_reply(empty), inventory_reply(empty),
                inventory_reply(last))
    result = DeepSeekInventoryClient(KEY, transport=http).inventory(png(), 100, 80)
    assert [v["bounds"] for v in result["designs"]] == [source["designs"][0]["bounds"],
                                                           {"x": 45, "y": 37, "width": 20, "height": 20}]


@pytest.mark.parametrize("mutate", [
    lambda v: v.update(extra="unknown"),
    lambda v: v["designs"][0].update(kind=[]),
    lambda v: v["designs"][0]["bounds"].update(x=True),
    lambda v: v["designs"][0]["bounds"].update(width=float("nan")),
    lambda v: v["designs"][0]["bounds"].update(width=200),
    lambda v: v["designs"][0].update(label=""),
    lambda v: v.update(watermarks=[{"bounds": BOUNDS, "description": "水印", "confidence": []}]),
    lambda v: v.update(warnings=[""] * 31),
])
def test_invalid_inventory_is_never_applied_or_retried(mutate):
    value = copy.deepcopy(INVENTORY)
    mutate(value)
    http = Http(inventory_reply(value))
    client = DeepSeekInventoryClient(KEY, transport=http, review_tiles=False)
    with pytest.raises(MaterialProviderError) as caught:
        client.inventory(png(), 100, 80)
    assert caught.value.code in {"invalid_inventory", "invalid_bounds"}
    assert caught.value.usage["requests"] == 1 and caught.value.usage["failures"] == 1
    assert len(http.calls) == 1 and KEY not in str(caught.value)


@pytest.mark.parametrize("body", [b'{"choices":[],"choices":[]}', b'{"choices":NaN}', b'not-json'])
def test_duplicate_or_invalid_json_rejected_without_repeating_post(body):
    http = Http(body)
    with pytest.raises(MaterialProviderError, match="无法解析") as caught:
        DeepSeekInventoryClient(KEY, transport=http, review_tiles=False).inventory(png(), 100, 80)
    assert caught.value.code == "invalid_json" and not caught.value.settled
    assert len(http.calls) == 1


def test_missing_token_usage_is_unknown_and_truncated_answer_is_failure():
    http = Http(inventory_reply(usage=None))
    result = DeepSeekInventoryClient(KEY, transport=http, review_tiles=False).inventory(png(), 100, 80)
    assert result["usage"]["unknown_usage_requests"] == 1
    assert "estimated_usd" not in result["usage"]
    partial = inventory_reply()
    partial["choices"][0]["finish_reason"] = "length"
    with pytest.raises(MaterialProviderError) as caught:
        DeepSeekInventoryClient(KEY, transport=Http(partial)).inventory(png(), 100, 80)
    assert caught.value.usage["prompt_tokens"] == 100 and caught.value.usage["failures"] == 1


def test_inventory_later_failure_preserves_prior_attempts_and_usage_without_secrets():
    response = inventory_reply()
    response["choices"][0]["message"]["content"] = "not-json " + KEY
    http = Http(inventory_reply(), response)
    client = DeepSeekInventoryClient(KEY, transport=http)
    with pytest.raises(MaterialProviderError) as caught:
        client.inventory(png(), 100, 80)
    assert caught.value.usage == {"requests": 2, "successes": 1, "failures": 1,
                                  "prompt_tokens": 200, "completion_tokens": 100, "unknown_usage_requests": 0}
    assert len(client.observations) == 2
    assert KEY not in str(caught.value) + repr(client.observations)


def test_actual_served_model_and_ids_are_recorded_not_invented_from_requested_name():
    reply = inventory_reply(model="deepseek-flash-serving-v123", id="actual-response-id")
    result = DeepSeekInventoryClient(KEY, transport=Http(reply), review_tiles=False).inventory(png(), 100, 80)
    assert result["requested_model"] == DEEPSEEK_MODEL
    assert result["model"] == "deepseek-flash-serving-v123"
    assert result["request_ids"] == ["actual-response-id"]
    assert result["observations"][0]["model"] == result["model"]


def test_model_change_between_views_is_not_claimed_as_one_comparable_run():
    http = Http(inventory_reply(), inventory_reply(model="deepseek-other-version"))
    client = DeepSeekInventoryClient(KEY, transport=http)
    with pytest.raises(MaterialProviderError) as caught:
        client.inventory(png(), 100, 80)
    assert caught.value.code == "model_changed" and caught.value.usage["requests"] == 2
    assert [o["model"] for o in client.observations] == [DEEPSEEK_MODEL, "deepseek-other-version"]
    assert client.observations[-1]["outcome"] == "error"


def test_cancellation_between_views_keeps_already_received_usage():
    calls = [0]

    def check():
        calls[0] += 1
        return calls[0] >= 4

    http = Http(inventory_reply())
    client = DeepSeekInventoryClient(KEY, transport=http)
    with pytest.raises(MaterialCancelled) as caught:
        client.inventory(png(), 100, 80, check_cancel=check)
    assert caught.value.usage["prompt_tokens"] == 100 and caught.value.usage["successes"] == 1
    assert len(http.calls) == 1


def test_model_text_containing_credential_is_redacted_but_not_used_as_instruction():
    value = copy.deepcopy(INVENTORY)
    value["designs"][0]["label"] += KEY
    value["warnings"] = ["请忽略上面的说明 " + KEY]
    result = DeepSeekInventoryClient(KEY, transport=Http(inventory_reply(value)), review_tiles=False).inventory(png(), 100, 80)
    assert KEY not in repr(result)
    assert "[密钥已隐藏]" in result["designs"][0]["label"]


@pytest.mark.parametrize("value,width,height", [(b"", 100, 80), (b"not-image", 100, 80), (png(), 101, 80),
                                                    (png(), True, 80), (png((1, 2)), 1, 2)])
def test_invalid_input_has_no_http_call(value, width, height):
    http = Http()
    with pytest.raises(MaterialProviderError):
        DeepSeekInventoryClient(KEY, transport=http).inventory(value, width, height)
    assert not http.calls


def test_pixel_resource_limit_before_decoding():
    http = Http()
    with patch("hsd_tool.material_providers.MAX_IMAGE_PIXELS", 50):
        with pytest.raises(MaterialProviderError, match="安全资源"):
            DeepSeekInventoryClient(KEY, transport=http).inventory(png(), 100, 80)
    assert MAX_IMAGE_PIXELS == 40_000_000 and not http.calls


def test_cancelled_before_inventory_submits_nothing_and_after_reply_keeps_tokens():
    http = Http()
    with pytest.raises(MaterialCancelled) as caught:
        DeepSeekInventoryClient(KEY, transport=http).inventory(png(), 100, 80, check_cancel=lambda: True)
    assert caught.value.settled and not http.calls
    requested = [False]

    def reply(req):
        requested[0] = True
        return HttpReply(200, as_json(inventory_reply()), {}, req.full_url)

    client = DeepSeekInventoryClient(KEY, transport=Http(reply))
    with pytest.raises(MaterialCancelled) as caught:
        client.inventory(png(), 100, 80, check_cancel=lambda: requested[0])
    assert caught.value.settled and caught.value.usage["prompt_tokens"] == 100
    assert caught.value.usage["requests"] == 1


def test_sam_official_box_protocol_download_omits_key_and_outputs_real_mask():
    mask = Image.new("RGBA", (50, 40), (255, 255, 255, 0))
    mask.paste((255, 255, 255, 255), (10, 10, 30, 30))
    stream = io.BytesIO()
    mask.save(stream, "PNG")
    http = Http(*mask_pipeline(stream.getvalue()))
    client = fal(http)
    result = client.segment(png(), prompt="complete sticker", box=BOUNDS, max_masks=1)
    req = http.calls[0][0]
    body = json.loads(req.data)
    assert req.full_url == QUEUE_ORIGIN + "/" + SAM_MODEL and req.method == "POST"
    assert req.get_header("Authorization") == "Key " + KEY
    assert req.get_header("X-fal-no-retry") == "1" and req.get_header("X-fal-store-io") == "0"
    assert req.get_header("X-app-fal-disable-fallback") == "true"
    assert body["apply_mask"] is False and body["sync_mode"] is False
    assert body["box_prompts"] == [{"x_min": 10, "y_min": 10, "x_max": 40, "y_max": 35, "object_id": 1}]
    assert body["max_masks"] == 1 and body["include_scores"]
    assert [r.full_url for r, _, _ in http.calls][1:3] == [submitted()["status_url"], submitted()["response_url"]]
    media_req = http.calls[-1][0]
    assert media_req.full_url == MEDIA and media_req.get_header("Authorization") is None
    assert result[0]["score"] == .9
    with Image.open(io.BytesIO(result[0]["mask"])) as actual:
        assert actual.size == (100, 80) and actual.mode == "L"
        assert actual.getpixel((0, 0)) == 0 and actual.getpixel((30, 30)) == 255
        assert set(actual.tobytes()) == {0, 255}
    assert KEY not in repr(client.observations) and MEDIA not in repr(client.observations)


def test_sam_empty_result_is_not_synthetic_rectangle_mask():
    http = Http(submitted(), {"status": "COMPLETED"}, {"masks": []})
    assert fal(http).segment(png(), prompt="design", box=BOUNDS) == []
    assert len(http.calls) == 3


def test_colour_preview_cannot_be_used_as_pixel_segmentation_mask():
    http = Http(*mask_pipeline(png((50, 40), "red")))
    with pytest.raises(MaterialProviderError) as caught:
        fal(http).segment(png(), prompt="design")
    assert caught.value.code == "invalid_mask" and caught.value.settled
    assert len(http.calls) == 4


def test_hidden_transparent_colour_does_not_create_mask_foreground():
    http = Http(*mask_pipeline(png((50, 40), (255, 0, 0, 0))))
    result = fal(http).segment(png(), prompt="design")
    with Image.open(io.BytesIO(result[0]["mask"])) as mask:
        assert mask.getextrema() == (0, 0)


@pytest.mark.parametrize("scores", [[-1], [float("nan")], [True], [.9, .8], "high"])
def test_invalid_sam_scores_prevent_media_download(scores):
    http = Http(submitted(), {"status": "COMPLETED"}, {"masks": [{"url": MEDIA}], "scores": scores})
    with pytest.raises(MaterialProviderError):
        fal(http).segment(png(), prompt="design")
    assert len(http.calls) == 3


@pytest.mark.parametrize("url", ["http://v3.fal.media/a.png", "https://evil.test/a.png",
                                  "https://v3.fal.media.evil.test/a.png", "https://u:p@v3.fal.media/a.png",
                                  "https://127.0.0.1/a.png", "https://v3.fal.media:444/a.png",
                                  "https://v3.fal.media/a.png#fragment", "https://v3.fal.media\\@evil.test/a.png",
                                  "file:///etc/passwd", "data:image/png;base64,xxx"])
def test_untrusted_media_is_never_contacted(url):
    http = Http(submitted(), {"status": "COMPLETED"}, {"masks": [{"url": url}]})
    with pytest.raises(MaterialProviderError) as caught:
        fal(http).segment(png(), prompt="design")
    assert caught.value.code == "untrusted_media_url" and len(http.calls) == 3


def test_download_redirect_and_resource_limits_are_errors_no_extra_calls():
    reply = HttpReply(200, png(), {}, "https://evil.test/redirect.png")
    http = Http(*mask_pipeline()[:-1], reply)
    with pytest.raises(MaterialProviderError) as caught:
        fal(http).segment(png(), prompt="design")
    assert caught.value.code == "redirect_blocked" and len(http.calls) == 4
    assert caught.value.settled
    with patch("hsd_tool.material_providers.MAX_IMAGE_BYTES", 1000):
        oversized = Http(*mask_pipeline()[:-1], b"x" * 1001)
        with pytest.raises(MaterialProviderError) as caught:
            fal(oversized).segment(png(), prompt="design")
        assert caught.value.code == "invalid_response"


def test_mask_wrong_aspect_is_refused_instead_of_silent_stretch():
    http = Http(*mask_pipeline(png((100, 100))))
    with pytest.raises(MaterialProviderError, match="宽高比例"):
        fal(http).segment(png(), prompt="design")


@pytest.mark.parametrize("box,prompt,count", [({**BOUNDS, "x": True}, "design", 3),
                                            ({**BOUNDS, "width": 1000}, "design", 3),
                                            (BOUNDS, "", 3), (BOUNDS, KEY, 3), (None, "design", True),
                                            (None, "design", 33)])
def test_invalid_segmentation_input_does_not_bill(box, prompt, count):
    http = Http()
    with pytest.raises(MaterialProviderError):
        fal(http).segment(png(), prompt=prompt, box=box, max_masks=count)
    assert not http.calls


def test_repair_uses_actual_pixel_mask_no_expansion_and_returns_provider_pixels():
    source, selected = png(), png(color="black")
    selected_image = Image.open(io.BytesIO(selected))
    selected_image.paste("white", (5, 5, 10, 10))
    stream = io.BytesIO()
    selected_image.save(stream, "PNG")
    processed = png(color="red")
    http = Http(*mask_pipeline(processed, {"images": [{"url": MEDIA}]}, REPAIR_MODEL))
    result = fal(http).repair(source, stream.getvalue())
    body = json.loads(http.calls[0][0].data)
    assert http.calls[0][0].full_url.endswith(REPAIR_MODEL)
    assert body["model"] == "best_quality" and body["mask_expansion"] == 0
    assert "mask_url" in body and body["mask_url"].startswith("data:image/png;base64,")
    with Image.open(io.BytesIO(result)) as actual:
        assert actual.size == (100, 80) and actual.getpixel((50, 50)) == (255, 0, 0, 255)


@pytest.mark.parametrize("mask,code", [(png(color="black"), "empty_mask"),
                                       (png(color=(255, 255, 255, 0)), "empty_mask"),
                                       (png(color="red"), "invalid_mask"),
                                       (png((50, 40)), "invalid_mask")])
def test_empty_or_wrong_size_repair_mask_never_submits(mask, code):
    http = Http()
    with pytest.raises(MaterialProviderError) as caught:
        fal(http).repair(png(), mask)
    assert caught.value.code == code and not http.calls


def test_forged_queue_urls_never_receive_key_and_cleanup_uses_known_canonical_id():
    submit = submitted()
    submit["status_url"] = "https://evil.test/steal"
    http = Http(submit, {"status": "OK"})
    with pytest.raises(MaterialProviderError) as caught:
        fal(http).segment(png(), prompt="design")
    assert caught.value.code == "untrusted_queue_url" and caught.value.settled
    assert len(http.calls) == 2 and http.calls[1][0].full_url == submitted()["cancel_url"]
    assert http.calls[1][0].method == "PUT"


def test_full_model_path_queue_urls_are_not_mistaken_for_owner_app_paths():
    submit = submitted()
    submit["response_url"] = submit["response_url"].replace("sam-3/requests", "sam-3/image/requests")
    http = Http(submit, {"status": "OK"})
    with pytest.raises(MaterialProviderError) as caught:
        fal(http).segment(png(), prompt="design")
    assert caught.value.code == "untrusted_queue_url"


@pytest.mark.parametrize("failure,code", [(TimeoutError(KEY), "network_error"),
                                         (lambda req: HttpReply(503, KEY.encode(), {}, req.full_url), "provider_error"),
                                         (lambda req: HttpReply(401, KEY.encode(), {}, req.full_url), "authentication"),
                                         (lambda req: HttpReply(429, KEY.encode(), {}, req.full_url), "rate_limit"),
                                         (lambda req: HttpReply(200, as_json(submitted()), {}, "https://evil.test/a"), "redirect_blocked")])
def test_billable_submission_failure_never_retries_or_echoes_upstream(failure, code):
    http = Http(failure)
    client = fal(http)
    with pytest.raises(MaterialProviderError) as caught:
        client.segment(png(), prompt="design")
    assert caught.value.code == code and len(http.calls) == 1
    assert KEY not in str(caught.value) + repr(client.observations)
    if code in {"network_error", "provider_error", "redirect_blocked"}:
        assert not caught.value.settled


def test_cancel_before_submission_has_no_calls():
    http = Http()

    def check():
        raise TaskCancelled()

    with pytest.raises(MaterialCancelled) as caught:
        fal(http).segment(png(), prompt="design", check_cancel=check)
    assert caught.value.settled and not http.calls


def cancelling_submit(flag):
    def result(req):
        flag[0] = True
        return HttpReply(200, as_json(submitted()), {}, req.full_url)
    return result


def test_queued_cancel_ok_is_confirmed_and_no_poll_or_media():
    flag = [False]
    http = Http(cancelling_submit(flag), {"status": "OK"})
    client = fal(http)
    with pytest.raises(MaterialCancelled) as caught:
        client.segment(png(), prompt="design", check_cancel=lambda: flag[0])
    assert caught.value.settled and len(http.calls) == 2
    assert client.observations[1]["outcome"] == "cancelled_before_execution"


def test_running_cancel_202_drains_actual_completion_and_captures_units_not_result():
    flag = [False]

    def cancelling(req):
        return HttpReply(202, as_json({"status": "CANCELLATION_REQUESTED"}), {}, req.full_url)

    def final(req):
        return HttpReply(200, as_json({"masks": [{"url": MEDIA}]}), {"X-Fal-Billable-Units": "1.25"}, req.full_url)

    http = Http(cancelling_submit(flag), cancelling, {"status": "IN_PROGRESS"},
                {"status": "COMPLETED", "request_id": "synthetic-request-1"}, final)
    client = fal(http)
    with pytest.raises(MaterialCancelled) as caught:
        client.segment(png(), prompt="design", check_cancel=lambda: flag[0])
    assert caught.value.settled and len(http.calls) == 5
    assert client.observations[1]["outcome"] == "completed_after_stop"
    assert client.observations[-1]["billable_units"] == 1.25
    assert not any(req.full_url == MEDIA for req, _, _ in http.calls)


def test_running_cancellation_without_terminal_proof_is_bounded_and_unsettled():
    flag, clock = [False], Clock()
    cancel = lambda req: HttpReply(202, as_json({"status": "CANCELLATION_REQUESTED"}), {}, req.full_url)
    http = Http(cancelling_submit(flag), cancel, *[{"status": "IN_PROGRESS"}] * 20)
    client = fal(http, clock=clock, drain_timeout=.2)
    with pytest.raises(MaterialCancelled) as caught:
        client.segment(png(), prompt="design", check_cancel=lambda: flag[0])
    assert not caught.value.settled and caught.value.code == "unsettled"
    assert clock.value <= .21 and client.observations[1]["outcome"] == "unsettled"
    assert sum(req.method == "POST" for req, _, _ in http.calls) == 1


def test_status_failure_attempts_cancel_without_retrying_inference():
    http = Http(submitted(), TimeoutError(KEY), {"status": "OK"})
    client = fal(http)
    with pytest.raises(MaterialProviderError) as caught:
        client.segment(png(), prompt="design")
    assert caught.value.code == "network_error" and caught.value.settled
    assert [r.method for r, _, _ in http.calls] == ["POST", "GET", "PUT"]


def test_queue_timeout_attempts_cancel_and_is_not_reported_as_success():
    http = Http(submitted(), {"status": "IN_PROGRESS"}, {"status": "IN_PROGRESS"}, {"status": "OK"})
    client = fal(http, queue_timeout=.1)
    with pytest.raises(MaterialProviderError) as caught:
        client.segment(png(), prompt="design")
    assert caught.value.code == "queue_timeout" and caught.value.settled
    assert len(http.calls) == 4 and http.calls[-1][0].method == "PUT"


def test_already_completed_cancel_fetches_terminal_result_once():
    flag = [False]
    cancel = lambda req: HttpReply(400, as_json({"status": "ALREADY_COMPLETED"}), {}, req.full_url)
    http = Http(cancelling_submit(flag), cancel, {"status": "COMPLETED"}, {"masks": []})
    with pytest.raises(MaterialCancelled) as caught:
        fal(http).segment(png(), prompt="design", check_cancel=lambda: flag[0])
    assert caught.value.settled and len(http.calls) == 4


def test_wrong_request_identity_cannot_prove_completion_during_drain():
    flag, clock = [False], Clock()
    cancel = lambda req: HttpReply(202, as_json({"status": "CANCELLATION_REQUESTED"}), {}, req.full_url)
    http = Http(cancelling_submit(flag), cancel,
                *[{"status": "COMPLETED", "request_id": "some-other-request"}] * 10)
    with pytest.raises(MaterialCancelled) as caught:
        fal(http, clock=clock, drain_timeout=.1).segment(png(), prompt="design", check_cancel=lambda: flag[0])
    assert not caught.value.settled


def test_default_transport_blocks_redirects_and_streams_bounded_reads():
    assert _NoRedirect().redirect_request(None, None, 302, None, None, "https://evil.test/") is None

    class Reply(io.BytesIO):
        status = 200
        headers = {}
        reads = []

        def geturl(self):
            return DEEPSEEK_ENDPOINT

        def read(self, count=-1):
            self.reads.append(count)
            return super().read(count)

        read1 = read

    class Opener:
        def open(self, req, timeout):
            return Reply(b"x" * 150_001)

    request = __import__("urllib.request", fromlist=["Request"]).Request(DEEPSEEK_ENDPOINT)
    with patch("hsd_tool.material_providers.urllib.request.build_opener", return_value=Opener()):
        with pytest.raises(MaterialProviderError, match="安全大小"):
            _default_transport(request, timeout=1, max_bytes=150_000)
    assert all(0 < n <= 64 * 1024 for n in Reply.reads)


def test_default_transport_total_deadline_limits_slow_streams():
    class Reply(io.BytesIO):
        status = 200
        headers = {}

        def geturl(self):
            return DEEPSEEK_ENDPOINT

        def read1(self, count):
            return super().read(1)

    class Opener:
        def open(self, req, timeout):
            return Reply(b"x" * 1000)

    request = __import__("urllib.request", fromlist=["Request"]).Request(DEEPSEEK_ENDPOINT)
    with patch("hsd_tool.material_providers.urllib.request.build_opener", return_value=Opener()), \
            patch("hsd_tool.material_providers.time.monotonic", side_effect=[0, .1, .2, 2]):
        with pytest.raises(MaterialProviderError) as caught:
            _default_transport(request, timeout=1, max_bytes=1000)
    assert caught.value.code == "network_timeout" and not caught.value.settled


@pytest.mark.parametrize("key", ["", "a\nb", " key with spaces ", "秘密", None])
def test_bad_credentials_fail_before_any_request(key):
    with pytest.raises(MaterialProviderError, match="管理员配置"):
        DeepSeekInventoryClient(key)
