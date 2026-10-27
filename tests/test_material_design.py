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
        self.refine_calls = 0
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

    def refine_design(self, *args, **kwargs):
        self.refine_calls += 1
        raise AssertionError("Default extraction must never dispatch a refinement")

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


class NativeArk(FakeArk):
    """Return a known native canvas; any automatic second call is a trap."""

    def __init__(self, *, transparent=True, **kwargs):
        super().__init__(**kwargs)
        self.native = transparent_card() if transparent else card()

    def extract_design(self, png, **kwargs):
        result = super().extract_design(png, **kwargs)
        layer = ArkLayer(self.native, "完整设计", "", result.layers[0].bounds, 1)
        # The adapter must keep the provider's actual image accounting, which
        # may count both the base and foreground even though it is one call.
        usage = {**result.usage, "generated_images": 2}
        return ArkResult((layer,), usage, (), result.base_png, result.base_size, result.request_id)


@pytest.mark.parametrize("transparent", [False, True])
@pytest.mark.parametrize("boxes", [
    [(10, 10, 110, 110)],
    [(10, 10, 60, 60), (200, 200, 250, 250)],
    [(10, 10, 110, 110), (160, 20, 390, 390)],
    [(0, 0, 240, 100), (240, 0, 400, 200)],
])
def test_every_design_is_extracted_once_regardless_of_size_count_or_transparency(transparent, boxes):
    ark = NativeArk(transparent=transparent)
    result = provider(ark, [design(box) for box in boxes], workers=1).extract(source_image())
    assert [row["operation"] for row in ark.calls] == ["clean"] + ["extract_design"] * len(boxes)
    assert ark.refine_calls == 0
    assert len(result.layers) == len(boxes)
    assert result.provider_usage["seedream"]["input_images"] == 1 + len(boxes)
    assert result.provider_usage["seedream"]["generated_images"] == 1 + 2 * len(boxes)
    assert result.provider_usage["deepseek"]["requests"] == 1
    assert all("不要白色贴纸边" in row["instructions"] for row in ark.calls[1:])
    assert not any("精修" in note for layer in result.layers for note in layer.warnings)
    for layer in result.layers:
        assert_canvas_preserved(Image.open(io.BytesIO(ark.native)), layer.png)
    final = {row["id"]: row for row in result.attempts}
    assert [row["operation"] for row in final.values()].count("extract_design") == len(boxes)
    assert not any(row["operation"] == "refine_design" for row in final.values())
    if not transparent:
        assert all(any("未返回透明区域" in note for note in layer.warnings) for layer in result.layers)


@pytest.mark.parametrize("settled,code", [(True, "provider_failed"), (False, "submission_unknown")])
def test_native_failure_is_not_retried_and_the_other_design_keeps_its_original_canvas(settled, code):
    class FailFirstNative(NativeArk):
        def extract_design(self, png, **kwargs):
            result = super().extract_design(png, **kwargs)
            if len(self.calls) == 2:
                raise ArkProviderError(code, "static message", settled=settled,
                                       usage={"input_images": 1}, request_id="native-failed")
            return result

    ark = FailFirstNative()
    result = provider(ark, [design((10, 10, 110, 110), "较小设计"),
                            design((160, 20, 390, 390), "较大设计")], workers=1).extract(source_image())
    assert [layer.label for layer in result.layers] == ["较大设计"]
    assert [row["operation"] for row in ark.calls] == ["clean", "extract_design", "extract_design"]
    assert ark.refine_calls == 0
    assert any("较小设计" in note and "未能生成" in note for note in result.warnings)
    final = {row["id"]: row for row in result.attempts}
    failed = [row for row in final.values() if row["request_id"] == "native-failed"]
    assert len(failed) == 1 and failed[0]["state"] == ("failed" if settled else "unknown")
    assert failed[0]["operation"] == "extract_design"
    assert result.provider_usage["seedream"]["input_images"] == 3
    assert_canvas_preserved(Image.open(io.BytesIO(ark.native)), result.layers[0].png)



def test_all_native_submissions_unknown_raise_with_complete_paid_history_and_no_new_requests():
    class UnknownNative(NativeArk):
        def extract_design(self, png, **kwargs):
            super().extract_design(png, **kwargs)
            raise ArkProviderError("submission_unknown", "static", settled=False,
                                   usage={"input_images": 1})

    ark = UnknownNative()
    with pytest.raises(ArkProviderError) as raised:
        provider(ark, [design((10, 10, 110, 110)), design((200, 200, 300, 300))], workers=1).extract(source_image())
    final = {row["id"]: row for row in raised.value.attempts}
    assert [row["operation"] for row in ark.calls] == ["clean", "extract_design", "extract_design"]
    assert ark.refine_calls == 0
    assert sum(row["state"] == "unknown" for row in final.values()) == 2
    assert raised.value.provider_usage["seedream"]["input_images"] == 3
    assert not raised.value.safe_retry and not raised.value.settled


def test_cancel_after_successful_native_extraction_prevents_the_next_design_request():
    cancelled = threading.Event()

    class CancelAfterExtract(NativeArk):
        def extract_design(self, png, **kwargs):
            result = super().extract_design(png, **kwargs)
            cancelled.set()
            return result

    ark = CancelAfterExtract()
    with pytest.raises(ArkCancelled) as raised:
        provider(ark, [design((10, 10, 110, 110)), design((200, 200, 300, 300))], workers=1).extract(
            source_image(), check_cancel=cancelled.is_set)
    assert [row["operation"] for row in ark.calls] == ["clean", "extract_design"]
    assert ark.refine_calls == 0
    assert raised.value.provider_usage["seedream"]["input_images"] == 2


def test_cancelled_native_with_lost_reply_stays_unknown_after_parallel_drain():
    cancelled = threading.Event()

    class LostNative(NativeArk):
        def extract_design(self, png, **kwargs):
            super().extract_design(png, **kwargs)
            cancelled.set()
            raise ArkCancelled(settled=False, usage={"input_images": 1}, request_id="native-unknown")

    ark = LostNative()
    with pytest.raises(ArkCancelled) as raised:
        provider(ark, [design((10, 10, 110, 110)), design((200, 200, 300, 300))], workers=1).extract(
            source_image(), check_cancel=cancelled.is_set)
    assert [row["operation"] for row in ark.calls] == ["clean", "extract_design"]
    assert ark.refine_calls == 0
    final = {row["id"]: row for row in raised.value.attempts}
    unknown = [row for row in final.values() if row["state"] == "unknown"]
    assert len(unknown) == 1 and unknown[0]["operation"] == "extract_design"
    assert unknown[0]["request_id"] == "native-unknown" and not unknown[0]["settled"]
    assert not raised.value.settled and raised.value.code == "submission_unknown"
    assert raised.value.provider_usage["seedream"]["input_images"] == 2
    assert raised.value.provider_usage["seedream"]["generated_images"] == 1


def test_explicit_employee_edit_adds_only_one_edit_request_after_extraction():
    ark = NativeArk()
    pipeline = provider(ark, [design((10, 10, 110, 110)), design((200, 200, 300, 300))], workers=1)
    result = pipeline.extract(source_image())
    assert [row["operation"] for row in ark.calls] == ["clean", "extract_design", "extract_design"]
    edited = pipeline.edit(result.layers[0].png, instructions="不要白色贴纸边")
    assert [row["operation"] for row in ark.calls] == ["clean", "extract_design", "extract_design", "edit"]
    assert ark.refine_calls == 0 and len(edited.layers) == 1
    assert edited.provider_usage["deepseek"]["requests"] == 0
    assert edited.provider_usage["seedream"]["input_images"] == 1


def test_transparent_edit_uses_existing_one_call_protocol_and_keeps_returned_canvas():
    ark = FakeArk(payloads=[transparent_card()])
    result = provider(ark, []).edit(transparent_card(), instructions="不要白色贴纸边",
                                    bounds={"x": 10, "y": 10, "width": 50, "height": 50})
    assert len(ark.calls) == 1 and ark.calls[0]["operation"] == "edit" and ark.refine_calls == 0
    assert_canvas_preserved(Image.open(io.BytesIO(transparent_card())), result.layers[0].png)


def test_extraction_concurrency_uses_shared_reference_pixel_budget(monkeypatch):
    monkeypatch.setattr(design_module, "CONCURRENT_REFERENCE_PIXELS", 320_000)

    class CountActive(NativeArk):
        def __init__(self):
            super().__init__()
            self.active = self.peak = 0

        def extract_design(self, png, **kwargs):
            with self.lock:
                self.active += 1
                self.peak = max(self.peak, self.active)
            try:
                time.sleep(.01)
                return super().extract_design(png, **kwargs)
            finally:
                with self.lock:
                    self.active -= 1

    ark = CountActive()
    result = provider(ark, eight_designs()).extract(source_image())
    assert len(result.layers) == 8 and ark.peak == 2
    assert [row["operation"] for row in ark.calls] == ["clean"] + ["extract_design"] * 8
    assert ark.refine_calls == 0


def busy_sheet(size=(400, 400)):
    """Every region differs, so a private crop is provably a different payload."""
    image = Image.new("RGB", size)
    draw = ImageDraw.Draw(image)
    for y in range(0, size[1], 8):
        for x in range(0, size[0], 8):
            draw.rectangle((x, y, x + 7, y + 7),
                           fill=((x * 7) % 256, (y * 11) % 256, ((x + y) * 3) % 256))
    return _encode(image)

DENSE_HINT = "\u653e\u5927\u5c40\u90e8\u53c2\u8003\u56fe"


def test_dense_sheet_draws_each_design_from_its_own_enlarged_view():
    """Sixty-odd tiny designs have too few sheet pixels to stay sharp."""
    boxes = [(x, y, x + 40, y + 40) for y in (10, 90, 170, 250) for x in (10, 90, 170, 250)]
    ark = FakeArk()
    result = provider(ark, [design(box) for box in boxes], workers=1).extract(busy_sheet())
    assert len(result.layers) == len(boxes)
    views = [row["png"] for row in ark.calls[1:]]
    assert all(view != ark.calls[0]["png"] for view in views)
    assert len(set(views)) == len(boxes)
    crop = Image.open(io.BytesIO(views[0]))
    assert max(crop.size) >= 900
    assert any(DENSE_HINT in note for layer in result.layers for note in layer.warnings)
    assert all(row["bounds"]["width"] <= crop.width for row in ark.calls[1:])


def test_sparse_sheet_still_shares_one_whole_sheet_reference():
    boxes = [(0, 0, 180, 180), (200, 200, 380, 380)]
    ark = FakeArk()
    result = provider(ark, [design(box) for box in boxes], workers=1).extract(busy_sheet())
    views = [row["png"] for row in ark.calls[1:]]
    assert views[0] == views[1]
    assert ark.calls[1]["bounds"] != ark.calls[2]["bounds"]
    assert not any(DENSE_HINT in note for layer in result.layers for note in layer.warnings)


def test_magnified_reference_keeps_the_box_inside_its_own_view():
    source = Image.open(io.BytesIO(busy_sheet())).convert("RGB")
    box = (180, 180, 230, 230)
    png, region, encoded_size = design_module.magnified_reference(source, box)
    assert region[0] <= box[0] < box[2] <= region[2]
    assert region[1] <= box[1] < box[3] <= region[3]
    hint = design_module.design_hint_in_region(box, region, encoded_size)
    crop = Image.open(io.BytesIO(png))
    assert encoded_size == crop.size
    assert 0 <= hint["x"] and hint["x"] + hint["width"] <= crop.width
    assert 0 <= hint["y"] and hint["y"] + hint["height"] <= crop.height
    assert max(crop.size) > 50 * 4


@pytest.mark.parametrize("limits", ["upscale", "downscale", "byte_shrink"])
@pytest.mark.parametrize("box", [(400, 400, 500, 500), (0, 50, 100, 150)])
def test_dense_request_hint_points_at_the_design_in_the_final_encoded_image(monkeypatch, limits, box):
    # Pixel projection, not just containment: the hint must still surround the
    # visible subject after up/down-scaling and PNG byte-budget resizing.
    source = Image.new("RGBA", (1000, 1000), (0, 0, 0, 0))
    pixels = np.random.default_rng(57).integers(0, 256, (100, 100, 3), dtype=np.uint8)
    subject = Image.fromarray(pixels).convert("RGBA")
    source.paste(subject, box[:2])
    if limits == "downscale":
        monkeypatch.setattr(design_module, "MAGNIFIED_PIXELS", 10_000)
        monkeypatch.setattr(design_module, "MAGNIFIED_MAX_PIXELS", 12_000)
    elif limits == "byte_shrink":
        monkeypatch.setattr(design_module, "MAX_INPUT_BYTES", 20_000)
    ark = FakeArk()
    locator_box = tuple(value * 2 // 5 for value in box)
    result = provider(ark, [design(locator_box)], workers=1).extract(_encode(source))
    assert len(result.layers) == 1 and len(ark.calls) == 2
    request = ark.calls[1]
    with Image.open(io.BytesIO(request["png"])) as reference:
        visible = reference.getchannel("A").point(lambda value: 255 if value >= 128 else 0).getbbox()
        hint = request["bounds"]
        actual = (hint["x"], hint["y"], hint["x"] + hint["width"], hint["y"] + hint["height"])
        assert all(abs(sent - seen) <= 2 for sent, seen in zip(actual, visible))
        assert 0 <= actual[0] < actual[2] <= reference.width
        assert 0 <= actual[1] < actual[3] <= reference.height
    if limits == "byte_shrink":
        assert len(request["png"]) <= 20_000


@pytest.mark.parametrize("box", [(40, 160, 360, 168), (160, 40, 168, 360),
                                  (0, 0, 1, 380), (0, 0, 380, 1)])
def test_thin_design_uses_accepted_whole_reference_without_an_extra_call(box):
    from hsd_tool.material_ark import _input, _prompt_bounds

    class ValidatingArk(FakeArk):
        def extract_design(self, png, **kwargs):
            _, size, _, _ = _input(png, decomposition=False)
            _prompt_bounds(kwargs["bounds"], size)
            return super().extract_design(png, **kwargs)

    ark = ValidatingArk()
    result = provider(ark, [design(box)], workers=1).extract(source_image((1000, 1000)))
    assert len(result.layers) == 1 and len(ark.calls) == 2
    with Image.open(io.BytesIO(ark.calls[1]["png"])) as reference:
        assert reference.size == (1000, 1000)
    assert not any(DENSE_HINT in note for layer in result.layers for note in layer.warnings)


@pytest.mark.parametrize("source_size,budget,expected", [
    ((400, 400), 32_000_000, 8), ((6000, 6000), 32_000_000, 8),
    ((6000, 6000), 4_800_000, 2)], ids=["small-eight", "large-eight", "large-budget-two"])
def test_dense_parallelism_uses_sent_reference_pixels(monkeypatch, source_size, budget, expected):
    monkeypatch.setattr(design_module, "CONCURRENT_REFERENCE_PIXELS", budget)
    entered, release = threading.Event(), threading.Event()

    class HeldArk(FakeArk):
        def __init__(self):
            super().__init__()
            self.active = self.peak = 0
            self.sizes = []

        def extract_design(self, png, **kwargs):
            with Image.open(io.BytesIO(png)) as reference:
                size = reference.size
            with self.lock:
                self.sizes.append(size)
                self.active += 1
                self.peak = max(self.peak, self.active)
                if self.active == expected:
                    entered.set()
            try:
                assert release.wait(20)
                return super().extract_design(png, **kwargs)
            finally:
                with self.lock:
                    self.active -= 1

    designs = [design((10 + 90 * (i % 4), 10 + 180 * (i // 4),
                       40 + 90 * (i % 4), 40 + 180 * (i // 4))) for i in range(8)]
    ark = HeldArk()
    with ThreadPoolExecutor(max_workers=1) as driver:
        task = driver.submit(provider(ark, designs, workers=8).extract, source_image(source_size))
        try:
            reached = entered.wait(12)
        finally:
            release.set()
        result = task.result(20)
    assert reached and ark.peak == expected
    assert len(result.layers) == 8 and len(ark.calls) == 9
    assert max(width * height for width, height in ark.sizes) * ark.peak <= budget


def test_mixed_references_bound_parallelism_by_largest_planned_view(monkeypatch):
    limits = []

    class ObservedPool(ThreadPoolExecutor):
        def __init__(self, max_workers):
            limits.append(max_workers)
            super().__init__(max_workers=max_workers)

    monkeypatch.setattr(design_module, "ThreadPoolExecutor", ObservedPool)
    ark = FakeArk()
    result = provider(ark, [design((0, 0, 200, 200)), design((250, 250, 280, 280))]).extract(
        source_image((6000, 6000)))
    assert len(result.layers) == 2 and len(ark.calls) == 3
    assert limits == [2]
    pixels = []
    for request in ark.calls[1:]:
        with Image.open(io.BytesIO(request["png"])) as image:
            pixels.append(image.width * image.height)
    assert max(pixels) * limits[0] <= design_module.CONCURRENT_REFERENCE_PIXELS
