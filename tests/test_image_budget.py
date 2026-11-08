"""Tiny synthetic pixels/weights; never allocates production-sized images."""
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
import threading
from types import SimpleNamespace

from PIL import Image
import pytest
from werkzeug.datastructures import FileStorage, MultiDict

from hsd_tool.cancellation import TaskCancelled
from hsd_tool.image_budget import PixelBudget


def test_small_workspaces_can_overlap():
    budget = PixelBudget(100)
    barrier = threading.Barrier(2)

    def small():
        with budget.reserve(40):
            barrier.wait(3)
            return True

    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = pool.submit(small), pool.submit(small)
        assert first.result(4) and second.result(4)
    assert budget._used == 0


def test_large_work_waits_and_exceptions_release_the_reservation():
    budget = PixelBudget(100)
    started, entered = threading.Event(), threading.Event()

    def later():
        started.set()
        with budget.reserve(40):
            entered.set()
            raise ValueError("synthetic failure")

    with ThreadPoolExecutor(max_workers=1) as pool:
        with budget.reserve(80):
            future = pool.submit(later)
            assert started.wait(2)
            assert not entered.wait(.05)
        with pytest.raises(ValueError, match="synthetic failure"):
            future.result(3)
    assert entered.is_set() and budget._used == 0
    with budget.reserve():
        assert budget._used == 100


def test_waiting_cancellation_drops_its_ticket_without_losing_capacity():
    budget = PixelBudget(100)
    cancelled, waiting = threading.Event(), threading.Event()

    def check():
        waiting.set()
        if cancelled.is_set():
            raise TaskCancelled()

    def later():
        with budget.reserve(80, check_cancel=check):
            pytest.fail("Cancelled workspace was admitted")

    with ThreadPoolExecutor(max_workers=1) as pool:
        with budget.reserve(80):
            future = pool.submit(later)
            assert waiting.wait(2)
            cancelled.set()
            with pytest.raises(TaskCancelled):
                future.result(3)
            assert budget._used == 80 and not budget._waiting
    assert budget._used == 0


def test_nested_operations_are_reentrant_and_cannot_deadlock_by_upgrading():
    budget = PixelBudget(100)
    with budget.reserve(60):
        with budget.reserve(40):
            assert budget._used == 60
        with pytest.raises(RuntimeError, match="complete workspace"):
            with budget.reserve():
                pytest.fail("An in-flight allocation cannot upgrade")
        assert budget._used == 60
    with budget.reserve():
        with budget.reserve():
            assert budget._used == 100
    assert budget._used == 0


def png():
    with Image.new("RGBA", (16, 16), (180, 40, 90, 128)) as image:
        target = BytesIO()
        image.save(target, "PNG")
        return target.getvalue()


def test_material_upload_retains_budget_through_thumbnail_and_releases_before_provider(tmp_path, monkeypatch):
    from hsd_tool import material_service as material

    budget = PixelBudget(100)
    monkeypatch.setattr(material, "IMAGE_BUDGET", budget)
    monkeypatch.setattr(material, "image_workspace_bytes", lambda _: 70)
    entered, release, second_started, second_decoded = (threading.Event() for _ in range(4))
    real_thumbnail, real_decode = material._thumbnail, material._decode
    decoded = []

    def thumbnail(image):
        assert getattr(budget._local, "held", 0) == 70
        if threading.current_thread().name == "first-upload":
            entered.set()
            assert release.wait(4)
        return real_thumbnail(image)

    def decode(raw):
        image = real_decode(raw)
        if threading.current_thread().name == "second-upload":
            second_decoded.set()
        decoded.append(image)
        return image

    monkeypatch.setattr(material, "_thumbnail", thumbnail)
    monkeypatch.setattr(material, "_decode", decode)

    class Settings:
        def runtime(self):
            return dict(enabled=True, ark_key="synthetic", model_id="synthetic")

    class Provider:
        def extract(self, raw, **kwargs):
            assert not getattr(budget._local, "held", 0), "Network work held a pixel reservation"
            return SimpleNamespace(layers=[SimpleNamespace(png=png(), label="test", warnings=(), bounds={})],
                                   no_upscale=True, rectangular_crops=True, warnings=(), usage={})

    manager = material.MaterialManager(tmp_path, Settings(), provider_factory=lambda _: Provider())
    outcomes, errors = [], []

    def upload(name):
        try:
            if name == "second-upload":
                second_started.set()
            files = MultiDict([("files", FileStorage(BytesIO(png()), filename="synthetic.png"))])
            outcomes.append(manager.receive(files, MultiDict(), owner=name))
        except BaseException as error:
            errors.append(error)

    first = threading.Thread(target=upload, args=("first-upload",), name="first-upload")
    second = threading.Thread(target=upload, args=("second-upload",), name="second-upload")
    try:
        first.start()
        assert entered.wait(3)
        second.start()
        assert second_started.wait(2)
        assert not second_decoded.wait(.05), "Large decode overlapped prior PNG/thumbnail work"
        # Status/cancellation locks remain available while waiting for pixels.
        assert manager.lock.acquire(timeout=.2)
        manager.lock.release()
    finally:
        release.set()
        first.join(5)
        if second.ident:
            second.join(5)
        manager.close()
    assert not first.is_alive() and not second.is_alive() and not errors
    assert len(outcomes) == 2 and second_decoded.is_set() and budget._used == 0
    assert decoded
    for image in decoded:
        with pytest.raises(ValueError, match="closed image"):
            image.getpixel((0, 0))


def test_ribbon_allocation_and_material_workspace_share_admission(monkeypatch):
    from hsd_tool import material_service as material
    from ribbon_backend import imaging

    budget = PixelBudget(100)
    monkeypatch.setattr(material, "IMAGE_BUDGET", budget)
    monkeypatch.setattr(imaging, "IMAGE_BUDGET", budget)
    monkeypatch.setattr(material, "image_workspace_bytes", lambda _: 40)
    entered = threading.Event()

    @imaging.memory_bounded_operation
    def render():
        with material._image_workspace(png()):
            entered.set()
            assert budget._used == 100

    render()
    assert entered.is_set() and budget._used == 0


def test_large_optional_quality_check_stops_before_decoding_without_claiming_fidelity(monkeypatch):
    from hsd_tool import material_quality as quality

    data = png()
    monkeypatch.setattr(quality, "MAX_DIAGNOSTIC_PIXELS", 100)
    original_load = Image.Image.load

    def unexpected_load(self, *args, **kwargs):
        pytest.fail("Optional component check decoded an over-budget image")

    monkeypatch.setattr(Image.Image, "load", unexpected_load)
    result = quality.quality_hook(data, data, dict(x=0, y=0, width=16, height=16))
    assert result["auto_ready"] is False
    assert result["evidence"]["pixel_fidelity_verified"] is False
    assert result["evidence"]["diagnostic_complete"] is False
    assert "未执行完整像素核对" in result["warnings"][0]
    monkeypatch.setattr(Image.Image, "load", original_load)


def test_native_edge_decode_uses_shared_budget_and_releases_before_return(monkeypatch):
    from hsd_tool import material_quality as quality

    data = png()
    budget = PixelBudget(100)
    monkeypatch.setattr(quality, "IMAGE_BUDGET", budget)
    monkeypatch.setattr(quality, "image_workspace_bytes", lambda _: 70)
    real_convert = Image.Image.convert
    calls = []

    # The second RGB conversion belongs to the small <=512 derivative after
    # native pixels were freed, so give the synthetic source larger dimensions.
    with Image.new("RGBA", (600, 600), (0, 0, 0, 0)) as large:
        large.paste((180, 40, 90, 255), (100, 100, 500, 500))
        target = BytesIO()
        large.save(target, "PNG")
    def checked_native_convert(image, *args, **kwargs):
        if image.size == (600, 600):
            assert getattr(budget._local, "held", 0) == 70
            calls.append(True)
        return real_convert(image, *args, **kwargs)
    monkeypatch.setattr(Image.Image, "convert", checked_native_convert)
    result = quality.native_edge_diagnostics(target.getvalue())
    assert calls and result["white_edge_ratio"] is not None and budget._used == 0
