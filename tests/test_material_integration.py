"""Real provider/service boundaries with synthetic external replies, no API calls."""
from io import BytesIO
from dataclasses import replace
import json
import zipfile

from PIL import Image
import pytest
from werkzeug.exceptions import Conflict

from hsd_tool.material_design import MaterialDesignProvider
from hsd_tool.material_service import MaterialManager
from test_material_design import CONFIG, FakeArk, FakeLocator, card, design, source_image
from test_material_service import Settings, complete, png, upload


@pytest.fixture(params=[(10, 20, 50, 60), (100, 100, 300, 300)], ids=["dense", "sparse"])
def real_pipeline(tmp_path, request):
    # Cleanup changes dimensions; saved bounds must still refer to the source,
    # not to cleanup pixels, the zoomed reference or the generated PNG canvas.
    output = png(size=(128, 96))
    class PipelineArk(FakeArk):
        def clean(self, *args, **kwargs):
            result = super().clean(*args, **kwargs)
            # The external cleanup reference size is stable across extraction,
            # editing and re-selection, independently of the foreground canvas.
            return replace(result, base_png=card(), base_size=(400, 400))

        def refine_design(self, png, *, check_cancel=None):
            return self.clean(png, check_cancel=check_cancel, _operation="refine_design")

    ark = PipelineArk(payloads=[output])
    box = request.param
    locator = FakeLocator([design(box)])
    provider = MaterialDesignProvider(CONFIG, None, ark=ark, locator=locator, workers=1)
    manager = MaterialManager(tmp_path, Settings(), cloud=True,
                              provider_factory=lambda config: provider)
    expected = {"x": box[0] * 2, "y": box[1] * 3 // 2,
                "width": (box[2] - box[0]) * 2, "height": (box[3] - box[1]) * 3 // 2}
    yield manager, ark, locator, output, expected
    manager.close()


def extracted(pipeline):
    manager = pipeline[0]
    result = complete(manager, upload(manager, data=source_image((800, 600))))
    assert result["status"] == "ready"
    assert result["sources"][0]["status"] == "done"
    assert result["stats"]["total"] == result["stats"]["downloadable"] == 1
    return result


def test_real_extraction_saves_confirms_and_downloads_source_bound_canvas(real_pipeline):
    manager, ark, locator, output, expected = real_pipeline
    result = extracted(real_pipeline)
    assert result["has_generation_failures"] is False
    item = result["items"][0]
    assert item["bounds"] == expected
    assert (item["width"], item["height"]) == (128, 96)
    assert result["download_url"] and item["status"] == "generated" and "review" not in item
    path, _ = manager.asset(result["id"], "employee-a", "item", item["id"])
    with Image.open(path) as saved, Image.open(BytesIO(output)) as original:
        assert saved.tobytes() == original.tobytes()
    manager.asset(result["id"], "employee-a", "item", item["id"], download=True)
    attempt = manager.jobs[result["id"]]["attempts"][0]
    assert attempt["state"] == "returned"
    assert [row["operation"] for row in attempt["pipeline_attempts"]] == ["cleanup", "locate", "extract_design"]
    assert attempt["provider_usage"]["seedream"]["generated_images"] == 2
    assert attempt["provider_usage"]["deepseek"]["requests"] == 1
    assert len(ark.calls) == 2 and len(locator.calls) == 1
    confirmed = manager.resolve(result["id"], "employee-a", {
        "expected_revision": result["revision"], "item_id": item["id"], "action": "confirm"})
    assert confirmed["stats"]["ready"] == 1
    archive_path, _ = manager.download(result["id"], "employee-a")
    with zipfile.ZipFile(archive_path) as archive:
        assert archive.testzip() is None
        record = json.loads(archive.read("素材说明.json"))["items"][0]
        assert record["bounds"] == expected and record["status"] == "confirmed"
        with Image.open(BytesIO(archive.read(record["file"]))) as saved:
            assert saved.size == (128, 96)
    assert len(ark.calls) == 2  # Reviewing/exporting never generates again.


def test_real_pipeline_redo_preserves_item_bounds_and_offsets_new_selection_once(real_pipeline):
    manager, ark, locator, _, expected = real_pipeline
    result = extracted(real_pipeline)
    old = result["items"][0]
    manager.redo(result["id"], "employee-a", {"expected_revision": result["revision"],
        "source_id": old["source_id"], "item_id": old["id"],
        "instruction": "清理边缘", "box": expected})
    edited = complete(manager, result["id"])
    assert edited["status"] == "ready"
    assert len(edited["items"]) == 1 and edited["items"][0]["bounds"] == expected
    assert edited["items"][0]["status"] == "generated"
    assert len(ark.calls) == 3 and ark.calls[-1]["operation"] == "edit"
    assert len(locator.calls) == 1
    selection = {"x": 90, "y": 60, "width": 400, "height": 400}
    manager.redo(result["id"], "employee-a", {"expected_revision": edited["revision"],
        "source_id": old["source_id"], "box": selection})
    final = complete(manager, result["id"])
    assert final["status"] == "ready" and len(final["items"]) == 2
    box = locator.designs[0].box
    added = final["items"][-1]
    assert added["bounds"] == {"x": box[0] + 90, "y": box[1] + 60,
                                "width": box[2] - box[0], "height": box[3] - box[1]}
    assert added["status"] == "generated"
    assert len(ark.calls) == 5 and len(locator.calls) == 2


def test_real_refine_calls_only_one_image_request_and_preserves_before(real_pipeline):
    manager, ark, locator, output, expected = real_pipeline
    result = extracted(real_pipeline)
    old = result["items"][0]
    def no_location():
        raise AssertionError("Refinement must not require the locator")
    locator.available = no_location
    manager.refine(result["id"], "employee-a", {"expected_revision": result["revision"], "item_id": old["id"]})
    current = complete(manager, result["id"])
    item = current["items"][0]
    assert len(current["items"]) == 1 and item["bounds"] == expected
    assert item["refined"] and item["status"] == "generated" and item["downloadable"]
    assert len(ark.calls) == 3 and ark.calls[-1]["operation"] == "refine_design"
    assert len(locator.calls) == 1
    before, _ = manager.asset(result["id"], "employee-a", "before", item["id"])
    with Image.open(before) as saved, Image.open(BytesIO(output)) as original:
        assert saved.tobytes() == original.tobytes()
    attempt = manager.jobs[result["id"]]["attempts"][-1]
    assert attempt["operation"] == "refine" and attempt["state"] == "returned"
    assert [row["operation"] for row in attempt["pipeline_attempts"]] == ["refine"]
    assert attempt["provider_usage"]["seedream"]["generated_images"] == 1
    assert attempt["provider_usage"]["deepseek"]["requests"] == 0


def test_partial_generation_failure_is_reported_without_blocking_successful_download(real_pipeline):
    manager, ark, locator, _, _ = real_pipeline
    locator.designs += (design((310, 20, 350, 60), "失败的设计"),)
    ark.fail = {3}  # Whole-sheet cleanup, one successful design, one failed design.
    result = extracted(real_pipeline)
    assert result["has_generation_failures"] is True
    assert len(result["items"]) == 1
    assert result["items"][0]["status"] == "generated" and result["items"][0]["downloadable"]
    assert result["sources"][0]["warnings"]
    calls = manager.jobs[result["id"]]["attempts"][0]["pipeline_attempts"]
    assert [(row["operation"], row["state"]) for row in calls][-2:] == [
        ("extract_design", "returned"), ("extract_design", "failed")]
    manager.download(result["id"], "employee-a")
