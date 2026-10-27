"""Display derivatives retain ownership/integrity; downloads remain full size."""
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

from PIL import Image
import pytest
from werkzeug.datastructures import FileStorage, MultiDict
from werkzeug.exceptions import Conflict

from hsd_tool.material_ark import ArkLayer, ArkResult
from test_material_service import service, complete, upload, png
from test_material_api import application, call, login, upload as api_upload


def test_native_output_thumbnail_is_small_without_changing_the_original(service):
    manager, provider = service
    raw = png(size=(1600, 1200))
    provider.extract = lambda *args, **kwargs: ArkResult(
        (ArkLayer(raw, "合成设计", "", {"x": 0, "y": 0, "width": 32, "height": 24}, 1),),
        {}, (), b"", (1600, 1200), rectangular_crops=True, no_upscale=True)
    result = complete(manager, upload(manager))
    item, source = result["items"][0], result["sources"][0]
    original, _ = manager.asset(result["id"], "employee-a", "item", item["id"])
    original_bytes = original.read_bytes()
    preview, digest = manager.asset(result["id"], "employee-a", "item", item["id"], thumbnail=True)
    with Image.open(preview) as image:
        assert image.size == (640, 480)
        assert image.mode == "RGBA" and image.getchannel("A").getextrema()[0] == 0
    with Image.open(original) as image:
        assert image.size == (1600, 1200)
        with Image.open(BytesIO(raw)) as expected:
            assert image.tobytes() == expected.tobytes()
    assert len(preview.read_bytes()) < len(original_bytes)
    assert item["thumbnail_url"].endswith("?variant=thumb&v=" + digest[:16])
    assert source["thumbnail_url"].startswith(source["image_url"] + "?variant=thumb&v=")
    assert "thumbnail_sha256" not in item and "thumbnail_sha256" not in source
    updated = manager.resolve(result["id"], "employee-a", {
        "expected_revision": result["revision"], "item_id": item["id"], "action": "confirm"})
    assert updated["items"][0]["thumbnail_url"] == item["thumbnail_url"]
    downloaded, _ = manager.asset(result["id"], "employee-a", "item", item["id"], download=True)
    assert downloaded == original and downloaded.read_bytes() == original_bytes


@pytest.mark.parametrize("changed", ["source", "item", "thumbnail"])
def test_original_and_derivative_tampering_cannot_reuse_a_cached_thumbnail(service, changed):
    manager, _ = service
    result = complete(manager, upload(manager))
    item, source = result["items"][0], result["sources"][0]
    preview, _ = manager.asset(result["id"], "employee-a", "item", item["id"], thumbnail=True)
    changed_path = (preview if changed == "thumbnail" else
                    manager._directory(result["id"]) / ((source if changed == "source" else item)["id"] + ".png"))
    changed_path.write_bytes(b"synthetic changed bytes")
    with pytest.raises(ValueError):
        manager.asset(result["id"], "employee-a", "item", item["id"], thumbnail=True)


def test_preview_endpoints_revalidate_ownership_content_etag_and_lease(application):
    app, manager, _ = application
    client = app.test_client(); login(client)
    identifier = api_upload(client).json["id"]
    manager.futures[identifier].result(20)
    state = call(client, f"/api/material/jobs/{identifier}").json
    row = state["items"][0]
    first = call(client, row["thumbnail_url"])
    assert first.status_code == 200 and first.mimetype == "image/png"
    assert "private" in first.headers["Cache-Control"]
    assert "must-revalidate" in first.headers["Cache-Control"]
    with Image.open(BytesIO(first.data)) as image:
        assert max(image.size) == 640
    etag = first.headers["ETag"]
    first.close()
    assert not manager.leases
    cached = call(client, row["thumbnail_url"], headers={"If-None-Match": etag})
    assert cached.status_code == 304
    cached.close()
    other = app.test_client(); login(other)
    assert call(other, row["thumbnail_url"]).status_code == 404
    assert call(client, row["image_url"] + "?variant=invalid").status_code == 400
    assert call(client, row["image_url"] + "?variant=thumb&v=old").status_code == 404
    assert call(client, row["image_url"] + "?variant=thumb&variant=full").status_code == 400
    source = manager._directory(identifier) / (row["source_id"] + ".png")
    source.write_bytes(b"synthetic source modification")
    changed = call(client, row["thumbnail_url"], headers={"If-None-Match": etag})
    assert changed.status_code == 400  # Must not return 304 for stale pixels.
    changed.close()


def test_source_thumbnail_keeps_source_integrity_and_is_not_a_download(service):
    manager, _ = service
    result = complete(manager, upload(manager, data=png(size=(1200, 800))))
    source = result["sources"][0]
    path, _ = manager.asset(result["id"], "employee-a", "source", source["id"], thumbnail=True)
    with Image.open(path) as image:
        assert image.size == (640, 427)
    with pytest.raises(KeyError):
        manager.asset(result["id"], "employee-b", "source", source["id"], thumbnail=True)
    with pytest.raises(ValueError):
        manager.asset(result["id"], "employee-a", "source", source["id"], thumbnail=True, download=True)


def staged_partial_provider(provider, *, unknown_first=True):
    """Return usable pixels while a billed refinement has an unknown reply."""
    extract = provider.extract
    provider.supports_progress = True
    def staged(raw, **kwargs):
        result = extract(raw, **kwargs)
        index = provider.calls
        record = kwargs["on_attempt"]
        record({"id": f"clean-{index}", "provider": "seedream", "operation": "cleanup",
                "state": "returned", "usage": {"generated_images": 1}, "settled": True})
        record({"id": f"refine-{index}", "provider": "seedream", "operation": "refine",
                "state": "submitted", "usage": {}, "settled": False})
        record({"id": f"refine-{index}", "provider": "seedream", "operation": "refine",
                "state": "unknown", "usage": {"generated_images": 1}, "settled": False})
        if not unknown_first or index != 1:
            # A later callback settles the SAME call ID. Its earlier unknown
            # state must not survive as an independent, permanently blocking row.
            record({"id": f"refine-{index}", "provider": "seedream", "operation": "refine",
                    "state": "returned", "usage": {"generated_images": 1}, "settled": True})
        result.provider_usage = {"seedream": {"generated_images": 2}}
        result.no_upscale = result.rectangular_crops = True
        return result
    provider.extract = staged


def test_partial_refinement_unknown_preserves_usage_successes_and_redo_ack(service):
    manager, provider = service
    staged_partial_provider(provider)
    result = complete(manager, upload(manager))
    source, item = result["sources"][0], result["items"][0]
    assert result["status"] == "ready" and source["status"] == "done"
    assert source["submission_unknown"] is True
    assert "部分调用结果尚未确认" in source["error"]
    assert item["status"] == "generated" and item["downloadable"]
    attempt = manager._read(manager._directory(result["id"]))["attempts"][0]
    assert attempt["state"] == "returned"
    assert attempt["provider_usage"] == {"seedream": {"generated_images": 2}}
    assert len(attempt["pipeline_attempts"]) == 2
    assert attempt["pipeline_attempts"][1]["state"] == "unknown"
    assert attempt["pipeline_attempts"][1]["usage"] == {"generated_images": 1}
    confirmed = manager.resolve(result["id"], "employee-a", {
        "expected_revision": result["revision"], "item_id": item["id"], "action": "confirm"})
    assert confirmed["items"][0]["status"] == "confirmed"
    manager.asset(result["id"], "employee-a", "item", item["id"], download=True)
    redo = {"expected_revision": confirmed["revision"], "source_id": source["id"],
            "box": {"x": 0, "y": 0, "width": 32, "height": 24}}
    with pytest.raises(Conflict, match="可能重复计费"):
        manager.redo(result["id"], "employee-a", redo)
    assert provider.calls == 1
    manager.redo(result["id"], "employee-a", {**redo, "acknowledge_unknown": True})
    assert complete(manager, result["id"])["status"] == "ready"
    assert provider.calls == 2


def test_unknown_is_source_scoped_and_settled_call_updates_remove_stale_unknown(service):
    manager, provider = service
    staged_partial_provider(provider)
    files = MultiDict([("files", FileStorage(BytesIO(png()), filename=f"{i}.png")) for i in range(2)])
    result = complete(manager, manager.receive(files, MultiDict(), owner="employee-a"))
    first, second = result["sources"]
    assert first["submission_unknown"] is True
    assert second["submission_unknown"] is False and second["error"] == ""
    attempt = manager._read(manager._directory(result["id"]))["attempts"][1]
    assert len(attempt["pipeline_attempts"]) == 2
    assert all(row["state"] == "returned" for row in attempt["pipeline_attempts"])
    # Another source's unresolved call cannot require an acknowledgement here.
    manager.redo(result["id"], "employee-a", {
        "expected_revision": result["revision"], "source_id": second["id"],
        "box": {"x": 0, "y": 0, "width": 32, "height": 24}})
    final = complete(manager, result["id"])
    assert final["sources"][1]["submission_unknown"] is False
    assert provider.calls == 3


def test_detail_view_shows_the_cached_thumbnail_before_the_full_file():
    """Opening another item must not keep the previous picture on screen."""
    script = (Path(__file__).resolve().parents[1] / "hsd_tool" / "static" / "material.js").read_text("utf-8")
    assert "function swapImage(el,value)" in script
    body = script.split("function swapImage(el,value)", 1)[1][:1200]
    assert "thumbnail_url" in body and "image_url" in body
    assert "new Image()" in body
    assert "preload.onload=settle" in body and "image-loading" in body
    assert 'swapImage($("material-detail-source"),before||source)' in script
    assert 'swapImage($("material-detail-output"),item)' in script
    assert 'getAttribute("src")!==sourceUrl' not in script
