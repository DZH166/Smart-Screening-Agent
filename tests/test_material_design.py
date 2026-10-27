"""Native design extraction, full canvas preservation and bounded concurrency. No real API."""
from concurrent.futures import ThreadPoolExecutor
import io
import threading
import time

from PIL import Image, ImageDraw
import numpy as np
import pytest

from hsd_tool.material_ark import ArkCancelled, ArkLayer, ArkProviderError, ArkResult, _encode
from hsd_tool.ai_usage import empty_usage
from hsd_tool import material_design as design_module
from hsd_tool.material_design import (MaterialDesignProvider, design_target_bounds,
                                      pad_box, prepare_design_reference, preserve_design, reference_workers)
from hsd_tool.material_locate import LocatedDesign

KEY = "unit-only-material-key"
MODEL = "doubao-seedream-5-0-flash-260915"
CONFIG = {"ark_key": KEY, "model_id": MODEL}


def source_image(size=(400, 400)):
    image = Image.new("RGB", size, (205, 205, 205))
    draw = ImageDraw.Draw(image)
    draw.rectangle((40, 40, 180, 180), fill=(180, 60, 40))
    draw.rectangle((220, 220, 360, 360), fill=(40, 90, 160))
    return _encode(image)


def card(size=(400, 400), *, background=(255, 255, 255), box=(120, 90, 280, 310)):
    """What the model tends to return: one design on a plain white card."""
    image = Image.new("RGB", size, background)
    draw = ImageDraw.Draw(image)
    draw.rectangle(box, fill=(200, 40, 40))
    return _encode(image)


def design(box, label="完整设计", uncertain=False, warnings=()):
    return LocatedDesign(label, box, uncertain, tuple(warnings))


class FakeLocator:
    def __init__(self, designs, warnings=()):
        self.designs = tuple(designs)
        self.warnings = tuple(warnings)
        self.calls = []

    def available(self):
        return None

    def locate(self, png, *, check_cancel=None):
        self.calls.append(png)
        usage = empty_usage()
        usage.update(requests=1, successes=1, prompt_tokens=100, completion_tokens=50)
        return type("Located", (), {
            "designs": self.designs, "warnings": self.warnings,
            "usage": usage, "request_id": "locate-1"})()


class FakeArk:
    """Answers like the image endpoint, optionally failing selected designs.

    Call 1 is the whole-sheet pass, so design calls start at index 2.
    """

    def __init__(self, payloads=None, *, fail=(), barrier=None, delay=None, barrier_from=2):
        self.payloads = list(payloads or ())
        self.fail = set(fail)
        self.barrier = barrier
        self.barrier_from = barrier_from
        self.delay = delay
        self.calls = []
        self.lock = threading.Lock()

    def clean(self, png, *, instructions="", bounds=None, check_cancel=None, _operation="clean"):
        with self.lock:
            self.calls.append({"png": png, "instructions": instructions, "bounds": bounds, "operation": _operation})
            index = len(self.calls)
        if self.barrier is not None and index >= self.barrier_from:
            self.barrier.wait(timeout=10)
        if self.delay is not None:
            self.delay.wait(timeout=10)
        if index in self.fail:
            raise ArkProviderError("provider_busy", "图片服务当前繁忙，稍后可重试。",
                                   settled=True, safe_retry=True,
                                   usage={"input_images": 1, "generated_images": 0})
        png = self.payloads[(index - 1) % len(self.payloads)] if self.payloads else card()
        return ArkResult((ArkLayer(png, "设计 %d" % index, "", {"x": 0, "y": 0, "width": 10, "height": 10}, 1),),
                         {"input_images": 1, "generated_images": 1, "output_tokens": 10, "total_tokens": 10},
                         (), png, (400, 400), "req-%d" % index)

    def extract_design(self, png, *, instructions="", bounds=None, check_cancel=None):
        return self.clean(png, instructions=instructions, bounds=bounds,
                          check_cancel=check_cancel, _operation="extract_design")

    def refine_design(self, png, *, instructions="", check_cancel=None):
        return self.clean(png, instructions=instructions, check_cancel=check_cancel,
                          _operation="refine_design")

    def edit(self, png, *, instructions="", bounds=None, check_cancel=None):
        return self.clean(png, instructions=instructions, bounds=bounds,
                          check_cancel=check_cancel, _operation="edit")



def provider(ark, designs, *, workers=8):
    return MaterialDesignProvider(CONFIG, None, ark=ark, locator=FakeLocator(designs), workers=workers)


# -- framing ---------------------------------------------------------------

def test_pad_box_grows_the_range_and_stays_inside_the_image():
    assert pad_box((50, 50, 150, 150), (400, 400)) == (38, 38, 162, 162)
    assert pad_box((0, 0, 50, 50), (400, 400)) == (0, 0, 56, 56)
    assert pad_box((390, 390, 400, 400), (400, 400)) == (384, 384, 400, 400)


@pytest.mark.parametrize("box", [(10, 10, 10, 20), (10, 10, 20, 20, 30), (0, 0, 401, 20),
                                 ("a", 0, 10, 10), (10.0, 0, 10, 10)])
def test_pad_box_rejects_impossible_ranges(box):
    with pytest.raises(ArkProviderError):
        pad_box(box, (400, 400))


def assert_canvas_preserved(source, output):
    with Image.open(io.BytesIO(output)) as actual:
        assert actual.size == source.size
        assert actual.convert("RGBA").tobytes() == source.convert("RGBA").tobytes()


def test_preserve_keeps_soft_alpha_white_details_and_original_canvas():
    image = Image.new("RGBA", (400, 400), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle((100, 80, 300, 330), fill=(200, 40, 40, 255))
    draw.rectangle((100, 120, 150, 170), fill=(255, 255, 255, 255))
    image.putpixel((99, 120), (200, 40, 40, 37))
    image.putpixel((301, 120), (200, 40, 40, 188))
    png, notes = preserve_design(image)
    assert_canvas_preserved(image, png)
    assert any("完整画布" in note for note in notes)
    assert not any("未返回透明区域" in note for note in notes)


def test_preserve_does_not_delete_disconnected_edge_ornaments_letters_or_feet():
    image = Image.new("RGBA", (400, 400), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle((140, 100, 260, 300), fill=(30, 30, 30, 255))
    draw.ellipse((0, 0, 24, 24), fill=(10, 90, 220, 255))
    draw.rectangle((130, 380, 145, 399), fill=(20, 100, 80, 255))
    png, notes = preserve_design(image)
    assert_canvas_preserved(image, png)
    assert any("触及画布边缘" in note for note in notes)
    assert not any("已去掉" in note for note in notes)


def test_preserve_opaque_background_is_warned_and_never_silently_removed():
    image = Image.open(io.BytesIO(card()))
    png, notes = preserve_design(image)
    assert_canvas_preserved(image, png)
    assert any("未返回透明区域" in note for note in notes)
    with Image.open(io.BytesIO(png)) as actual:
        assert actual.getchannel("A").getextrema() == (255, 255)


def test_preserve_warns_on_small_content_without_cropping_or_scaling():
    image = Image.new("RGBA", (400, 400), (0, 0, 0, 0))
    ImageDraw.Draw(image).rectangle((150, 150, 180, 180), fill=(40, 60, 80, 255))
    png, notes = preserve_design(image)
    assert_canvas_preserved(image, png)
    assert any("占比偏小" in note for note in notes)


def test_preserve_rejects_empty_transparent_output():
    with pytest.raises(ArkProviderError):
        preserve_design(Image.new("RGBA", (200, 200), (255, 0, 0, 0)))


# -- provider --------------------------------------------------------------

def test_extract_regenerates_each_design_and_reports_progress():
    ark = FakeArk()
    progress, attempts = [], []
    designs = [design((40, 40, 180, 180), "人物"), design((220, 220, 360, 360), "文字")]
    result = provider(ark, designs).extract(
        source_image(), instructions="保持平面风格",
        on_progress=lambda code, message="", **extra: progress.append((code, message, extra)),
        on_attempt=attempts.append)

    assert result.rectangular_crops is True and result.no_upscale is True
    assert [layer.z_index for layer in result.layers] == [1, 2]
    assert [layer.label for layer in result.layers] == ["人物", "文字"]
    assert len(ark.calls) == 3, "one whole-sheet pass plus one call per design"
    assert all("保持平面风格" in call["instructions"] for call in ark.calls)
    assert result.usage == {"input_images": 3, "generated_images": 3, "output_tokens": 30, "total_tokens": 30}
    assert result.provider_usage["deepseek"]["requests"] == 1
    rows = {}
    for update in attempts:
        rows[update["id"]] = update
    assert [row["provider"] for row in rows.values()].count("seedream") == 3
    assert [row["provider"] for row in rows.values()].count("deepseek") == 1
    assert all(row["state"] == "returned" for row in rows.values())
    assert ("designs", "", {"current": 2, "total": 2}) in progress
    assert any("模型提取可能改变" in note for layer in result.layers for note in layer.warnings)
    assert [c["operation"] for c in ark.calls] == ["clean", "extract_design", "extract_design"]


def test_extract_shares_whole_source_context_and_only_hints_the_padded_range():
    ark = FakeArk()
    original = source_image()
    provider(ark, [design((40, 40, 180, 180)), design((220, 220, 360, 360))]).extract(original)
    assert ark.calls[1]["png"] is ark.calls[2]["png"], "encode the whole reference once per source"
    with Image.open(io.BytesIO(ark.calls[1]["png"])) as reference:
        assert reference.size == (400, 400)
        assert_canvas_preserved(Image.open(io.BytesIO(original)), ark.calls[1]["png"])
    assert ark.calls[1]["bounds"] == {"x": 23, "y": 23, "width": 174, "height": 174}


def test_reference_limits_pixels_without_cutting_the_full_image_or_changing_ratio():
    source = Image.new("RGBA", (6000, 3000), (80, 20, 10, 127))
    source.putpixel((0, 0), (200, 0, 0, 255))
    png, size = prepare_design_reference(source)
    assert size[0] * size[1] <= 16_000_000
    assert abs(size[0] / size[1] / 2 - 1) < .002
    with Image.open(io.BytesIO(png)) as reference:
        assert reference.size == size
        assert reference.getpixel((size[0] - 1, size[1] - 1)) == (80, 20, 10, 127)
    target = design_target_bounds((0, 0, 6000, 3000), source.size, size)
    assert target == {"x": 0, "y": 0, "width": size[0], "height": size[1]}


def test_high_resolution_reference_retains_more_than_four_megapixels_and_reduces_parallelism():
    source = Image.new("RGBA", (3000, 2000), (80, 20, 10, 127))
    png, size = prepare_design_reference(source)
    assert size == source.size and size[0] * size[1] > 4_000_000
    assert reference_workers(size) == 5
    assert reference_workers((4000, 4000)) == 2
    assert reference_workers((2000, 2000)) == 8
    assert reference_workers(size, 3) == 3
    with Image.open(io.BytesIO(png)) as actual:
        assert actual.tobytes() == source.tobytes()


def test_noisy_reference_shrinks_whole_canvas_to_byte_limit_without_dropping_alpha(monkeypatch):
    monkeypatch.setattr(design_module, "MAX_INPUT_BYTES", 64_000)
    source = Image.fromarray(np.random.default_rng(42).integers(0, 256, (256, 512, 4), dtype=np.uint8), "RGBA")
    png, size = prepare_design_reference(source)
    assert len(png) <= 64_000 and size[0] < 512
    assert abs(size[0] / size[1] / 2 - 1) < .02
    with Image.open(io.BytesIO(png)) as actual:
        assert actual.mode == "RGBA" and actual.size == size
        assert actual.getchannel("A").getextrema()[0] < 255


def test_provider_keeps_native_layer_pixels_and_canvas_including_separate_edge_details():
    native = Image.new("RGBA", (320, 640), (0, 0, 0, 0))
    drawing = ImageDraw.Draw(native)
    drawing.rectangle((120, 180, 190, 430), fill=(255, 255, 255, 255))
    drawing.ellipse((0, 0, 12, 12), fill=(10, 90, 220, 255))
    drawing.rectangle((130, 615, 145, 639), fill=(20, 100, 80, 255))
    native.putpixel((120, 179), (200, 40, 40, 37))
    ark = FakeArk(payloads=[card(), _encode(native)])
    result = provider(ark, [design((40, 40, 180, 180))]).extract(source_image())
    assert_canvas_preserved(native, result.layers[0].png)
    assert any("触及画布边缘" in note for note in result.layers[0].warnings)


def test_extract_runs_designs_at_the_same_time():
    barrier = threading.Barrier(3)
    designs = [design((10 + 120 * i, 10, 110 + 120 * i, 110)) for i in range(3)]
    result = provider(FakeArk(barrier=barrier), designs, workers=8).extract(source_image())
    assert len(result.layers) == 3


def test_extract_keeps_the_good_designs_when_one_fails():
    ark = FakeArk(fail={3})
    result = provider(ark, [design((40, 40, 180, 180), "甲"), design((220, 220, 360, 360), "乙")]).extract(source_image())
    assert len(result.layers) == 1
    assert any("未能生成" in note and "乙" in note for note in result.warnings)


def test_extract_fails_only_when_every_design_fails():
    ark = FakeArk(fail={2, 3})
    with pytest.raises(ArkProviderError) as error:
        provider(ark, [design((40, 40, 180, 180)), design((220, 220, 360, 360))]).extract(source_image())
    assert error.value.code == "provider_failed"
    assert error.value.safe_retry is False
    assert error.value.usage["input_images"] == 3


def test_extract_stops_before_spending_when_cancel_is_set():
    ark = FakeArk()
    with pytest.raises(ArkCancelled):
        provider(ark, [design((40, 40, 180, 180))]).extract(source_image(), check_cancel=lambda: True)
    assert ark.calls == []


def test_extract_refuses_an_empty_location():
    with pytest.raises(ArkProviderError) as error:
        provider(FakeArk(), []).extract(source_image())
    assert error.value.code == "invalid_decision"


def test_edit_keeps_one_clean_request_and_preserves_full_returned_canvas():
    ark = FakeArk()
    result = provider(ark, []).edit(source_image(), instructions="把红色改成蓝色",
                                    bounds={"x": 10, "y": 10, "width": 50, "height": 50})
    assert len(result.layers) == 1
    assert ark.calls[0]["bounds"] == {"x": 10, "y": 10, "width": 50, "height": 50}
    assert "把红色改成蓝色" in ark.calls[0]["instructions"]
    with Image.open(io.BytesIO(result.layers[0].png)) as framed:
        assert framed.getchannel("A").getextrema() == (255, 255)
        assert framed.size == (400, 400)
    assert any("未返回透明区域" in note for note in result.layers[0].warnings)


def test_provider_caps_the_worker_pool():
    assert provider(FakeArk(), []).workers == 8
    assert MaterialDesignProvider(CONFIG, None, ark=FakeArk(), locator=FakeLocator([]), workers=64).workers == 8


def eight_designs():
    return [design((10 + 90 * (i % 4), 10 + 180 * (i // 4),
                    80 + 90 * (i % 4), 150 + 180 * (i // 4))) for i in range(8)]


def test_eight_concurrent_successes_and_failures_retain_exact_usage_without_retry():
    ark = FakeArk(fail={4, 8}, barrier=threading.Barrier(8))
    attempts = []
    result = provider(ark, eight_designs()).extract(source_image(), on_attempt=attempts.append)
    assert len(ark.calls) == 9 and len(result.layers) == 6
    assert result.provider_usage["seedream"] == {
        "input_images": 9, "generated_images": 7, "output_tokens": 70, "total_tokens": 70}
    final = {row["id"]: row for row in attempts}
    assert len(final) == 10  # Whole-sheet + locator + 8 native design requests.
    assert sum(row["state"] == "failed" for row in final.values()) == 2
    assert sum(row["usage"].get("input_images", 0) for row in final.values()) == 9


def test_cancelled_parallel_request_drains_and_retains_all_paid_results():
    cancelled = threading.Event()

    class CancelOne(FakeArk):
        def extract_design(self, png, **kwargs):
            result = super().extract_design(png, **kwargs)
            with self.lock:
                first = not cancelled.is_set()
                cancelled.set()
            if first:
                raise ArkCancelled(usage=result.usage, request_id=result.request_id)
            return result

    ark = CancelOne(barrier=threading.Barrier(8))
    with pytest.raises(ArkCancelled) as error:
        provider(ark, eight_designs()).extract(source_image(), check_cancel=cancelled.is_set)
    assert len(ark.calls) == 9
    assert error.value.provider_usage["seedream"] == {
        "input_images": 9, "generated_images": 9, "output_tokens": 90, "total_tokens": 90}
    final = {row["id"]: row for row in error.value.attempts}
    assert sum(row["usage"].get("input_images", 0) for row in final.values()) == 9
    assert sum(row["state"] == "cancelled" for row in final.values()) == 1


def transparent_card(size=(400, 400)):
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    drawing = ImageDraw.Draw(image)
    drawing.rectangle((size[0] // 4, size[1] // 4, 3 * size[0] // 4, 3 * size[1] // 4), fill=(250, 250, 250, 255))
    image.putpixel((0, 0), (10, 20, 30, 37))
    image.putpixel((size[0] - 1, size[1] - 1), (50, 60, 70, 255))
    return _encode(image)


class RefineArk(FakeArk):
    def __init__(self, *, refine_error=None, native_size=(400, 400), **kwargs):
        super().__init__(**kwargs)
        self.refine_error = refine_error
        self.native = transparent_card(native_size)
        self.refined = transparent_card((320, 640))

    def extract_design(self, png, **kwargs):
        result = super().extract_design(png, **kwargs)
        layer = ArkLayer(self.native, "完整设计", "", result.layers[0].bounds, 1)
        return ArkResult((layer,), result.usage, (), result.base_png, result.base_size, result.request_id)

    def refine_design(self, png, **kwargs):
        result = super().refine_design(png, **kwargs)
        if self.refine_error:
            raise self.refine_error
        layer = ArkLayer(self.refined, "精修设计", "", result.layers[0].bounds, 1)
        return ArkResult((layer,), result.usage, (), result.base_png, result.base_size, result.request_id)


def test_only_small_targets_in_multiple_designs_get_one_planned_refinement():
    ark = RefineArk()
    result = provider(ark, [design((10, 10, 110, 110)), design((160, 20, 390, 390))], workers=1).extract(source_image())
    assert [row["operation"] for row in ark.calls] == ["clean", "extract_design", "refine_design", "extract_design"]
    assert result.provider_usage["seedream"]["input_images"] == 4
    assert_canvas_preserved(Image.open(io.BytesIO(ark.refined)), result.layers[0].png)
    assert_canvas_preserved(Image.open(io.BytesIO(ark.native)), result.layers[1].png)
    assert any("已单独请求高清精修" in note for note in result.layers[0].warnings)
    assert not any("已单独请求高清精修" in note for note in result.layers[1].warnings)


def test_single_design_and_exact_ratio_boundary_do_not_add_refinement():
    ark = RefineArk()
    provider(ark, [design((10, 10, 110, 110))]).extract(source_image())
    assert [row["operation"] for row in ark.calls] == ["clean", "extract_design"]
    ark = RefineArk()
    provider(ark, [design((0, 0, 240, 100)), design((240, 0, 400, 200))]).extract(source_image())
    assert [row["operation"] for row in ark.calls].count("refine_design") == 0


def test_small_opaque_native_result_keeps_its_pixels_with_warning_without_extra_spending():
    ark = FakeArk()
    result = provider(ark, [design((10, 10, 110, 110)), design((200, 200, 300, 300))]).extract(source_image())
    assert len(ark.calls) == 3
    assert all(any("未继续精修" in note for note in layer.warnings) for layer in result.layers)
    assert_canvas_preserved(Image.open(io.BytesIO(card())), result.layers[0].png)


@pytest.mark.parametrize("settled,code", [(True, "provider_failed"), (False, "submission_unknown")])
def test_refinement_failure_never_falls_back_or_retries_and_other_design_remains(settled, code):
    ark = RefineArk(refine_error=ArkProviderError(code, "static message", settled=settled,
                                               usage={"input_images": 1}, request_id="refine-failed"))
    result = provider(ark, [design((10, 10, 110, 110), "较小设计"),
                            design((160, 20, 390, 390), "较大设计")], workers=1).extract(source_image())
    assert [layer.label for layer in result.layers] == ["较大设计"]
    assert [row["operation"] for row in ark.calls] == ["clean", "extract_design", "refine_design", "extract_design"]
    assert any("较小设计" in note and "未能生成" in note for note in result.warnings)
    final = {row["id"]: row for row in result.attempts}
    refine = [row for row in final.values() if row["operation"] == "refine_design"]
    assert len(refine) == 1 and refine[0]["state"] == ("failed" if settled else "unknown")
    assert refine[0]["request_id"] == "refine-failed"
    assert result.provider_usage["seedream"]["input_images"] == 4


def test_all_refinements_unknown_raise_with_complete_paid_history_without_native_fallback():
    ark = RefineArk(refine_error=ArkProviderError("submission_unknown", "static", settled=False,
                                               usage={"input_images": 1}))
    with pytest.raises(ArkProviderError) as raised:
        provider(ark, [design((10, 10, 110, 110)), design((200, 200, 300, 300))], workers=1).extract(source_image())
    final = {row["id"]: row for row in raised.value.attempts}
    assert len(ark.calls) == 5
    assert sum(row["state"] == "unknown" for row in final.values()) == 2
    assert raised.value.provider_usage["seedream"]["input_images"] == 5
    assert not raised.value.safe_retry


def test_cancel_between_successful_extraction_and_planned_refinement_does_not_dispatch_refinement():
    cancelled = threading.Event()

    class CancelAfterExtract(RefineArk):
        def extract_design(self, png, **kwargs):
            result = super().extract_design(png, **kwargs)
            cancelled.set()
            return result

    ark = CancelAfterExtract()
    with pytest.raises(ArkCancelled) as raised:
        provider(ark, [design((10, 10, 110, 110)), design((200, 200, 300, 300))], workers=1).extract(
            source_image(), check_cancel=cancelled.is_set)
    assert [row["operation"] for row in ark.calls] == ["clean", "extract_design"]
    assert raised.value.provider_usage["seedream"]["input_images"] == 2


def test_cancelled_refinement_with_lost_reply_stays_unknown_after_parallel_drain():
    cancelled = threading.Event()

    class LostRefinement(RefineArk):
        def refine_design(self, png, **kwargs):
            result = super().refine_design(png, **kwargs)
            cancelled.set()
            raise ArkCancelled(settled=False, usage={"input_images": 1}, request_id="refine-unknown")

    ark = LostRefinement()
    with pytest.raises(ArkCancelled) as raised:
        provider(ark, [design((10, 10, 110, 110)), design((200, 200, 300, 300))], workers=1).extract(
            source_image(), check_cancel=cancelled.is_set)
    # Cleanup, native extraction, and the planned refinement only. The lost
    # reply does not dispatch any retry or start the second queued design.
    assert [row["operation"] for row in ark.calls] == ["clean", "extract_design", "refine_design"]
    final = {row["id"]: row for row in raised.value.attempts}
    unknown = [row for row in final.values() if row["state"] == "unknown"]
    assert len(unknown) == 1 and unknown[0]["operation"] == "refine_design"
    assert unknown[0]["request_id"] == "refine-unknown" and not unknown[0]["settled"]
    assert not raised.value.settled and raised.value.code == "submission_unknown"
    assert raised.value.provider_usage["seedream"]["input_images"] == 3
    assert raised.value.provider_usage["seedream"]["generated_images"] == 2


def test_transparent_edit_uses_existing_one_call_protocol_and_keeps_returned_canvas():
    ark = FakeArk(payloads=[transparent_card()])
    result = provider(ark, []).edit(transparent_card(), instructions="不要白色贴纸边",
                                    bounds={"x": 10, "y": 10, "width": 50, "height": 50})
    assert len(ark.calls) == 1 and ark.calls[0]["operation"] == "edit"
    assert_canvas_preserved(Image.open(io.BytesIO(transparent_card())), result.layers[0].png)


def test_refinement_concurrency_uses_pixel_budget_even_when_original_is_small(monkeypatch):
    monkeypatch.setattr(design_module, "CONCURRENT_REFERENCE_PIXELS", 640_000)

    class CountActive(RefineArk):
        def __init__(self):
            super().__init__(native_size=(800, 800))
            self.active = self.peak = 0

        def refine_design(self, png, **kwargs):
            with self.lock:
                self.active += 1
                self.peak = max(self.peak, self.active)
            try:
                time.sleep(.01)
                return super().refine_design(png, **kwargs)
            finally:
                with self.lock:
                    self.active -= 1

    ark = CountActive()
    result = provider(ark, eight_designs()).extract(source_image())
    assert len(result.layers) == 8 and ark.peak == 1
    assert [row["operation"] for row in ark.calls].count("refine_design") == 8
