"""Per-design regeneration, local framing and bounded concurrency. No real API."""
from concurrent.futures import ThreadPoolExecutor
import io
import threading

from PIL import Image, ImageDraw
import numpy as np
import pytest

from hsd_tool.material_ark import ArkCancelled, ArkLayer, ArkProviderError, ArkResult, _encode
from hsd_tool.ai_usage import empty_usage
from hsd_tool.material_design import (MaterialDesignProvider, pad_box, remove_plain_background,
                                      trim_design)
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

    def clean(self, png, *, instructions="", bounds=None, check_cancel=None):
        with self.lock:
            self.calls.append({"png": png, "instructions": instructions, "bounds": bounds})
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


def test_white_card_becomes_real_transparency():
    result, plain = remove_plain_background(Image.open(io.BytesIO(card())))
    assert plain is True
    assert result.getchannel("A").getextrema() == (0, 255)
    assert result.getchannel("A").getpixel((2, 2)) == 0
    assert result.getchannel("A").getpixel((200, 200)) == 255


def test_white_area_inside_the_design_survives():
    image = Image.new("RGB", (200, 200), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    draw.rectangle((20, 20, 180, 180), fill=(20, 20, 20))
    draw.rectangle((80, 80, 120, 120), fill=(255, 255, 255))
    framed, plain = remove_plain_background(image)
    assert plain is True
    assert framed.getchannel("A").getpixel((100, 100)) == 255
    assert framed.getchannel("A").getpixel((5, 5)) == 0


def test_trim_keeps_the_design_and_adds_one_uniform_margin():
    png, notes = trim_design(Image.open(io.BytesIO(card())))
    with Image.open(io.BytesIO(png)) as framed:
        alpha = framed.getchannel("A")
        assert framed.mode == "RGBA"
        assert alpha.getextrema() == (0, 255)
        left, top, right, bottom = alpha.getbbox()
        assert (right - left, bottom - top) == (161, 221)
        assert left == top and framed.width - right == left and framed.height - bottom == top
    assert any("模型重新绘制了这张设计" in note for note in notes)
    assert not any("可能被裁切" in note for note in notes)


def test_trim_drops_neighbour_fragments_in_the_outer_band():
    image = Image.new("RGB", (400, 400), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    draw.rectangle((140, 120, 260, 280), fill=(30, 30, 30))
    draw.rectangle((0, 0, 24, 24), fill=(10, 90, 220))          # leftover neighbour
    png, notes = trim_design(image)
    with Image.open(io.BytesIO(png)) as framed:
        assert framed.width < 160 and framed.height < 200
        pixels = np.asarray(framed.convert("RGB")).reshape(-1, 3)
    assert not np.any((pixels[:, 2] > 200) & (pixels[:, 0] < 40))
    assert any("边缘杂块" in note for note in notes)


def test_trim_warns_when_the_design_touches_the_frame():
    image = Image.new("RGB", (400, 400), (255, 255, 255))
    ImageDraw.Draw(image).rectangle((0, 0, 399, 200), fill=(30, 30, 30))
    _, notes = trim_design(image)
    assert any("可能被裁切" in note for note in notes)


def test_trim_warns_when_the_background_was_not_cleared():
    _, notes = trim_design(Image.open(io.BytesIO(card(background=(238, 226, 214)))))
    assert any("背景没有清理干净" in note for note in notes)


def test_trim_refuses_an_empty_result():
    with pytest.raises(ArkProviderError):
        trim_design(Image.new("RGB", (200, 200), (255, 255, 255)))


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
    assert any("模型重新绘制" in note for layer in result.layers for note in layer.warnings)


def test_extract_uses_the_padded_range_not_the_bare_box():
    ark = FakeArk()
    provider(ark, [design((40, 40, 180, 180))]).extract(source_image())
    with Image.open(io.BytesIO(ark.calls[1]["png"])) as crop:
        assert crop.size == (180 - 40 + 2 * 17, 180 - 40 + 2 * 17)


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


def test_edit_regenerates_and_frames_a_single_design():
    ark = FakeArk()
    result = provider(ark, []).edit(source_image(), instructions="把红色改成蓝色",
                                    bounds={"x": 10, "y": 10, "width": 50, "height": 50})
    assert len(result.layers) == 1
    assert ark.calls[0]["bounds"] == {"x": 10, "y": 10, "width": 50, "height": 50}
    assert "把红色改成蓝色" in ark.calls[0]["instructions"]
    with Image.open(io.BytesIO(result.layers[0].png)) as framed:
        assert framed.getchannel("A").getextrema() == (0, 255)


def test_provider_caps_the_worker_pool():
    assert provider(FakeArk(), []).workers == 8
    assert MaterialDesignProvider(CONFIG, None, ark=FakeArk(), locator=FakeLocator([]), workers=64).workers == 8
