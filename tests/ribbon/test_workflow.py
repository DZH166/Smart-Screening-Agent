"""V1 acceptance tests against real HTTP routes, SQLite transactions and PNG files.

All image providers in this suite are explicitly test providers. These tests are
engineering evidence, not evidence for real AI quality or production output.
"""
from __future__ import annotations

import hashlib
import io
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from ribbon_backend.app import create_app
from ribbon_backend.config import Settings


def key() -> str:
    return str(uuid4())


def png_bytes(color: str = "#c86c86") -> bytes:
    image = Image.new("RGBA", (120, 120), (0, 0, 0, 0))
    ImageDraw.Draw(image).ellipse((10, 10, 110, 110), fill=color)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def ok(response):
    assert response.is_success, f"{response.status_code}: {response.text}"
    return response.json()


class Harness:
    def __init__(self, app, client):
        self.app = app
        self.client = client
        self.service = app.state.service

    def login(self, username="demo", client=None):
        client = client or self.client
        return ok(client.post("/api/auth/login", json={
            "username": username, "password": f"{username}12345",
        }))

    def selection(self):
        patterns = ok(self.client.get("/api/assets", params={"kind": "pattern"}))
        backgrounds = ok(self.client.get("/api/assets", params={"kind": "background"}))
        templates = ok(self.client.get("/api/templates"))
        assert len(patterns) >= 2 and backgrounds and len(templates) >= 6
        return {"asset_ids": [a["id"] for a in patterns[:2]],
                "background_id": backgrounds[0]["id"], "template_id": templates[0]["id"]}

    def create(self):
        return ok(self.client.post("/api/designs", json={"name": "验收作品"}))

    def get(self, design):
        return ok(self.client.get(f"/api/designs/{design['id']}"))

    def work(self, job):
        for _ in range(10):
            latest = ok(self.client.get(f"/api/jobs/{job['id']}"))
            if latest["status"] in {"SUCCEEDED", "FAILED"}:
                return latest
            self.service.run_once()
        pytest.fail(f"Job did not terminate: {latest}")

    def generate(self, design=None, selection=None):
        design = design or self.create()
        job = ok(self.client.post(f"/api/designs/{design['id']}/generate", json={
            "idempotency_key": key(), **(selection or self.selection()),
        }))
        finished = self.work(job)
        assert finished["status"] == "SUCCEEDED", finished
        return self.get(design)

    def refine(self, design, prompt="图案缩小一些，间距拉大一点", **extra):
        return self.client.post(f"/api/designs/{design['id']}/refinements", json={
            "idempotency_key": key(), "base_version_id": design["current_version_id"],
            "prompt": prompt, **extra,
        })

    def refined(self, design, prompt="图案缩小一些，间距拉大一点", **extra):
        job = ok(self.refine(design, prompt, **extra))
        finished = self.work(job)
        assert finished["status"] == "SUCCEEDED", finished
        return self.get(design)

    def rollback(self, design):
        return ok(self.client.post(f"/api/designs/{design['id']}/rollback", json={
            "expected_version_id": design["current_version_id"],
        }))

    def download(self, version_id):
        response = self.client.get(f"/api/versions/{version_id}/download")
        assert response.status_code == 200, response.text
        assert "image/png" in response.headers["content-type"]
        return response.content


@pytest.fixture
def env(tmp_path):
    settings = Settings(data_dir=tmp_path / "data", provider="test", start_worker=False)
    app = create_app(settings)
    with TestClient(app, base_url="http://localhost") as client:
        harness = Harness(app, client)
        harness.login()
        yield harness


def test_a01_a02_a03_multiple_assets_templates_and_decodable_first_draft(env):
    """Actual uploaded PNG is included in the saved recipe and immutable output."""
    uploaded = ok(env.client.post("/api/assets", files={
        "file": ("private-pattern.png", png_bytes(), "image/png"),
    }, data={"kind": "pattern", "name": "验收圆点"}))
    selection = env.selection()
    selection["asset_ids"] = [uploaded["id"], selection["asset_ids"][0]]
    for template in ok(env.client.get("/api/templates")):
        assert template["name"] and template["mode"]
        image = env.client.get(template["thumbnail_url"])
        assert image.status_code == 200
        Image.open(io.BytesIO(image.content)).verify()
    design = env.generate(selection=selection)
    assert design["successful_refinement_count"] == 0
    assert len(design["versions"]) == 1
    version = design["versions"][0]
    assert version["sequence"] == 0 and version["parent_version_id"] is None
    assert version["snapshot"]["asset_refs"] == selection["asset_ids"]
    assert version["snapshot"]["background_ref"] == selection["background_id"]
    assert version["snapshot"]["template_id"] == selection["template_id"]
    image = Image.open(io.BytesIO(env.download(version["id"])))
    profile = version["snapshot"]["output_profile"]
    assert image.size == (profile["width"], profile["height"])
    assert profile["is_demo"] is True
    preview = env.client.get(version["preview_url"])
    assert preview.status_code == 200
    Image.open(io.BytesIO(preview.content)).verify()
    # The detail view needs the full-resolution master inline: a preview shrunk
    # to fit a 3600 px box would be upscaled by the browser and look soft.
    view = env.client.get(version["view_url"])
    assert view.status_code == 200 and view.headers["content-type"] == "image/png"
    assert "attachment" not in view.headers.get("content-disposition", "")
    assert "max-age" in view.headers.get("cache-control", "")
    with Image.open(io.BytesIO(view.content)) as shown:
        assert shown.size == (profile["width"], profile["height"])
    assert ok(env.client.get("/api/config"))["provider"] == "test"


def test_a04_a05_a07_a11_branch_rollback_monotonic_quota_and_pinned_downloads(env):
    original = env.generate()
    v0 = original["current_version_id"]
    bytes0 = env.download(v0)
    one = env.refined(original)
    v1 = one["current_version_id"]
    bytes1 = env.download(v1)
    assert one["successful_refinement_count"] == 1
    assert bytes1 != bytes0
    back = env.rollback(one)
    assert back["current_version_id"] == v0
    assert back["successful_refinement_count"] == 1
    two = env.refined(back, "图案放大一些")
    v2 = two["current_version_id"]
    assert v2 not in {v0, v1} and two["successful_refinement_count"] == 2
    by_id = {v["id"]: v for v in two["versions"]}
    assert by_id[v1]["parent_version_id"] == by_id[v2]["parent_version_id"] == v0
    assert sorted(v["sequence"] for v in two["versions"]) == [0, 1, 2]
    back_again = env.rollback(two)
    assert back_again["current_version_id"] == v0
    assert back_again["successful_refinement_count"] == 2
    third = env.refine(back_again)
    assert third.status_code == 409, third.text
    assert env.get(original)["successful_refinement_count"] == 2
    assert env.download(v0) == bytes0
    assert env.download(v1) == bytes1
    assert hashlib.sha256(env.download(v2)).digest() not in {
        hashlib.sha256(bytes0).digest(), hashlib.sha256(bytes1).digest(),
    }


def test_a08_a13_a14_idempotency_and_busy_slot(env):
    design = env.generate()
    payload = {"idempotency_key": key(), "base_version_id": design["current_version_id"],
               "prompt": "图案缩小一些"}
    url = f"/api/designs/{design['id']}/refinements"
    first = ok(env.client.post(url, json=payload))
    again = ok(env.client.post(url, json=payload))
    assert first["id"] == again["id"]
    mismatch = env.client.post(url, json={**payload, "prompt": "图案放大一些"})
    assert mismatch.status_code == 409
    competing = env.client.post(url, json={**payload, "idempotency_key": key()})
    assert competing.status_code == 409
    rollback = env.client.post(f"/api/designs/{design['id']}/rollback", json={
        "expected_version_id": design["current_version_id"],
    })
    assert rollback.status_code == 409
    assert env.work(first)["status"] == "SUCCEEDED"
    final_repeat = ok(env.client.post(url, json=payload))
    assert final_repeat["id"] == first["id"] and final_repeat["status"] == "SUCCEEDED"
    for _ in range(3):
        env.service.run_once()
    saved = env.get(design)
    assert len(saved["versions"]) == 2 and saved["successful_refinement_count"] == 1


def test_a13_actual_concurrent_distinct_requests_admit_one_job(env):
    # Race for the final remaining refinement, not just an empty quota.
    design = env.refined(env.generate())
    url = f"/api/designs/{design['id']}/refinements"

    def submit(_):
        return env.client.post(url, json={
            "idempotency_key": key(), "base_version_id": design["current_version_id"],
            "prompt": "图案缩小一些",
        })

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(submit, range(2)))
    successes = [r for r in responses if r.is_success]
    assert len(successes) == 1, [(r.status_code, r.text) for r in responses]
    assert [r.status_code for r in responses if not r.is_success] == [409]
    assert env.work(successes[0].json())["status"] == "SUCCEEDED"
    saved = env.get(design)
    assert len(saved["versions"]) == 3 and saved["successful_refinement_count"] == 2
    assert env.refine(saved).status_code == 409


def test_a06_clarification_keeps_original_and_does_not_charge(env):
    design = env.generate()
    old = env.download(design["current_version_id"])
    failed = env.work(ok(env.refine(design, "请让它变得更好看")))
    assert failed["status"] == "FAILED"
    assert failed["needs_clarification"] is True
    saved = env.get(design)
    assert saved["current_version_id"] == design["current_version_id"]
    assert saved["successful_refinement_count"] == 0 and saved["active_job_id"] is None
    assert env.download(saved["current_version_id"]) == old
    assert len(env.refined(saved)["versions"]) == 2


def test_a09_a15_reconnect_uses_persisted_result_and_quota(env):
    design = env.generate()
    payload = {"idempotency_key": key(), "base_version_id": design["current_version_id"],
               "prompt": "图案缩小一些"}
    job = ok(env.client.post(f"/api/designs/{design['id']}/refinements", json=payload))
    assert env.get(design)["active_job_id"] == job["id"]
    # Worker finishes independently of any browser polling or response receipt.
    env.service.run_once()
    with TestClient(env.app, base_url="http://localhost") as reconnected:
        env.login(client=reconnected)
        state = ok(reconnected.get(f"/api/designs/{design['id']}"))
        result = ok(reconnected.get(f"/api/jobs/{job['id']}"))
        replay = ok(reconnected.post(f"/api/designs/{design['id']}/refinements", json=payload))
        assert result["status"] == replay["status"] == "SUCCEEDED"
        assert result["id"] == replay["id"] == job["id"]
        assert state["current_version_id"] == result["result_version_id"]
        assert state["successful_refinement_count"] == 1 and len(state["versions"]) == 2


def test_a12_private_assets_designs_jobs_and_files_are_isolated(env):
    uploaded = ok(env.client.post("/api/assets", files={
        "file": ("private.png", png_bytes(), "image/png"),
    }, data={"kind": "pattern", "name": "客户私有"}))
    design = env.generate()
    version = design["versions"][0]
    running = ok(env.refine(design))
    with TestClient(env.app, base_url="http://localhost") as other:
        env.login("client", client=other)
        assert uploaded["id"] not in {a["id"] for a in ok(other.get("/api/assets"))}
        assert design["id"] not in {d["id"] for d in ok(other.get("/api/designs"))}
        for url in [uploaded["url"], f"/api/designs/{design['id']}",
                    f"/api/jobs/{running['id']}", version["download_url"], version["preview_url"]]:
            response = other.get(url)
            assert response.status_code in {403, 404}, (url, response.status_code)
        assert other.post(f"/api/designs/{design['id']}/rollback", json={
            "expected_version_id": version["id"],
        }).status_code in {403, 404}
        assert other.get("/api/admin/overview").status_code == 403
        assert any(a["shared"] for a in ok(other.get("/api/assets")))
        forbidden_share = other.post("/api/assets", files={
            "file": ("share.png", png_bytes(), "image/png"),
        }, data={"kind": "pattern", "name": "非法共享", "shared": "true"})
        assert forbidden_share.status_code == 403


def test_selection_changes_after_first_draft_are_refinements(env):
    design = env.generate()
    selection = env.selection()
    selection["asset_ids"] = selection["asset_ids"][:1]
    repeat_generation = env.client.post(f"/api/designs/{design['id']}/generate", json={
        "idempotency_key": key(), **selection,
    })
    assert repeat_generation.status_code == 409
    revised = env.refined(design, "应用所选配置", selection=selection)
    assert revised["successful_refinement_count"] == 1
    version = next(v for v in revised["versions"] if v["id"] == revised["current_version_id"])
    assert version["snapshot"]["asset_refs"] == selection["asset_ids"]


def test_content_edit_is_a_new_derived_asset_and_counts_once(env):
    design = env.generate()
    initial = design["versions"][0]
    revised = env.refined(design, "背景添加波点")
    latest = next(v for v in revised["versions"] if v["id"] == revised["current_version_id"])
    assert revised["successful_refinement_count"] == 1
    assert latest["snapshot"]["background_ref"] != initial["snapshot"]["background_ref"]
    assert env.download(initial["id"]) != env.download(latest["id"])


def test_background_texture_edit_preserves_previously_selected_visible_color(env):
    blue = env.refined(env.generate(), "背景改为浅蓝色")
    blue_version = next(v for v in blue["versions"] if v["id"] == blue["current_version_id"])
    assert blue_version["snapshot"]["params"]["background_color"] == "#DFEAF0"
    dotted = env.refined(blue, "背景添加波点")
    latest = next(v for v in dotted["versions"] if v["id"] == dotted["current_version_id"])
    assert dotted["successful_refinement_count"] == 2
    assert latest["snapshot"]["params"]["background_color"] is None
    new_background = next(a for a in ok(env.client.get("/api/assets"))
                          if a["id"] == latest["snapshot"]["background_ref"])
    image = Image.open(io.BytesIO(env.client.get(new_background["url"]).content)).convert("RGB")
    # The new texture is based on the visible blue fill, not the older hidden library texture.
    assert image.getpixel((0, 0)) == (223, 234, 240)
    colors = image.getcolors(image.width * image.height)
    blue_count = next(count for count, color in colors if color == (223, 234, 240))
    assert blue_count > image.width * image.height * 0.9
    assert len(colors) > 1


def test_pattern_content_edit_preserves_original_and_unrequested_asset(env):
    selection = env.selection()
    patterns = ok(env.client.get("/api/assets", params={"kind": "pattern"}))
    flower = next(a for a in patterns if "花" in a["name"])
    ring = next(a for a in patterns if "圆环" in a["name"])
    selection["asset_ids"] = [flower["id"], ring["id"]]
    original_asset_bytes = env.client.get(flower["url"]).content
    design = env.generate(selection=selection)
    first = design["versions"][0]
    revised = env.refined(design, "给花朵添加笑脸")
    latest = next(v for v in revised["versions"] if v["id"] == revised["current_version_id"])
    refs = latest["snapshot"]["asset_refs"]
    assert refs[0] != flower["id"] and refs[1] == ring["id"]
    assets = ok(env.client.get("/api/assets"))
    derived = next(a for a in assets if a["id"] == refs[0])
    assert derived["derived_from"] == flower["id"] and derived["source"] == "test"
    assert env.client.get(derived["url"]).content != original_asset_bytes
    assert env.client.get(flower["url"]).content == original_asset_bytes
    assert latest["snapshot"]["background_ref"] == first["snapshot"]["background_ref"]
    assert env.download(latest["id"]) != env.download(first["id"])


def test_whole_image_after_parameter_edit_flattens_actual_current_master(env):
    design = env.refined(env.generate(), "图案缩小一些")
    before = env.download(design["current_version_id"])
    modified = env.refined(design, "整体添加星光")
    latest = next(v for v in modified["versions"] if v["id"] == modified["current_version_id"])
    assert modified["successful_refinement_count"] == 2
    assert latest["render_kind"] == "composite" and latest["snapshot"]["composite_ref"]
    assert latest["snapshot"]["params"]["scale"] == 1
    assert latest["snapshot"].get("object_transforms", []) == []
    assert env.download(latest["id"]) != before


def test_flattened_version_rejects_fake_layer_adjustment_without_charging(env):
    design = env.refined(env.generate(), "整体添加星光")
    failed = env.work(ok(env.refine(design, "图案缩小一些")))
    assert failed["status"] == "FAILED" and failed["needs_clarification"]
    saved = env.get(design)
    assert saved["successful_refinement_count"] == 1
    assert saved["current_version_id"] == design["current_version_id"]
    layered = env.refined(saved, "应用所选配置", selection=env.selection())
    latest = next(v for v in layered["versions"] if v["id"] == layered["current_version_id"])
    assert layered["successful_refinement_count"] == 2
    assert latest["render_kind"] == "layered" and not latest["snapshot"].get("composite_ref")


def test_background_generation_is_separate_from_design_quota(env):
    design = env.generate()
    payload = {"idempotency_key": key(), "prompt": "浅绿色柔和底图"}
    job = ok(env.client.post("/api/background-jobs", json=payload))
    assert ok(env.client.post("/api/background-jobs", json=payload))["id"] == job["id"]
    completed = env.work(job)
    assert completed["status"] == "SUCCEEDED" and completed["result_asset_id"]
    asset = next(a for a in ok(env.client.get("/api/assets")) if a["id"] == completed["result_asset_id"])
    assert asset["kind"] == "background" and asset["is_demo"] is True
    assert env.get(design)["successful_refinement_count"] == 0


def test_invalid_upload_and_unauthenticated_reads_are_rejected(env):
    malformed = env.client.post("/api/assets", files={
        "file": ("bad.png", b"this is not a PNG", "image/png"),
    }, data={"kind": "pattern", "name": "坏图"})
    assert malformed.status_code in {400, 422}
    with TestClient(env.app, base_url="http://localhost") as anonymous:
        assert anonymous.get("/api/designs").status_code == 401
        assert anonymous.get("/api/assets").status_code == 401


def test_hiding_asset_removes_library_entry_but_preserves_saved_recipe(env):
    uploaded = ok(env.client.post("/api/assets", files={
        "file": ("archived.png", png_bytes(), "image/png"),
    }, data={"kind": "pattern", "name": "待下架素材"}))
    selection = env.selection()
    selection["asset_ids"] = [uploaded["id"]]
    design = env.generate(selection=selection)
    original = env.download(design["current_version_id"])
    ok(env.client.delete(f"/api/assets/{uploaded['id']}"))
    assert uploaded["id"] not in {a["id"] for a in ok(env.client.get("/api/assets"))}
    assert env.download(design["current_version_id"]) == original
    # Existing snapshots still resolve the immutable file during refinement.
    assert env.refined(design)["successful_refinement_count"] == 1
    new_design = env.create()
    response = env.client.post(f"/api/designs/{new_design['id']}/generate", json={
        "idempotency_key": key(), **selection,
    })
    assert response.status_code == 404


def test_stale_base_and_stale_rollback_are_rejected(env):
    old = env.generate()
    new = env.refined(old)
    assert env.refine(old).status_code == 409
    stale = env.client.post(f"/api/designs/{old['id']}/rollback", json={
        "expected_version_id": old["current_version_id"],
    })
    assert stale.status_code == 409
    assert env.get(new)["current_version_id"] == new["current_version_id"]


def test_a15_new_application_instance_recovers_queued_job_and_saved_versions(env):
    design = env.generate()
    original_bytes = env.download(design["current_version_id"])
    queued = ok(env.refine(design))
    restored_app = create_app(Settings(
        data_dir=env.service.db.path.parent, provider="test", start_worker=False,
    ))
    with TestClient(restored_app, base_url="http://localhost") as client:
        recovered = Harness(restored_app, client)
        recovered.login()
        before = recovered.get(design)
        assert before["active_job_id"] == queued["id"]
        assert recovered.download(design["current_version_id"]) == original_bytes
        assert recovered.work(queued)["status"] == "SUCCEEDED"
        after = recovered.get(design)
        assert after["successful_refinement_count"] == 1 and len(after["versions"]) == 2


def test_a08_duplicate_worker_completion_is_atomic_and_charges_once(env):
    design = env.generate()
    job = ok(env.refine(design))
    claimed = env.service.claim_job()
    assert claimed and claimed["id"] == job["id"]
    env.service.process_job(claimed)
    assert ok(env.client.get(f"/api/jobs/{job['id']}"))["status"] == "SUCCEEDED"
    with env.service.db.connect() as conn:
        artifact = json.loads(conn.execute("SELECT artifact_json FROM jobs WHERE id=?", (job["id"],)).fetchone()[0])
    # Simulate duplicate delivery of an already completed callback, including files.
    env.service.complete_job(claimed, artifact)
    env.service.complete_job(claimed, artifact)
    with env.service.db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM quota_events WHERE job_id=?", (job["id"],)).fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM versions WHERE job_id=?", (job["id"],)).fetchone()[0] == 1
    saved = env.get(design)
    assert saved["successful_refinement_count"] == 1 and len(saved["versions"]) == 2


def test_a10_saved_artifact_reconciles_after_database_commit_failure(env):
    design = env.generate()
    job = ok(env.refine(design))
    # Fail the LAST write of the real completion transaction, after the version,
    # quota event and current pointer writes. SQLite must roll all of them back.
    with env.service.db.transaction() as conn:
        conn.execute("""
            CREATE TRIGGER injected_commit_failure BEFORE UPDATE ON jobs
            WHEN NEW.status = 'SUCCEEDED'
            BEGIN SELECT RAISE(ABORT, 'injected completion transaction failure'); END
        """)
    env.service.run_once()
    interim = env.get(design)
    assert interim["current_version_id"] == design["current_version_id"]
    assert interim["successful_refinement_count"] == 0
    with env.service.db.transaction() as conn:
        row = conn.execute("SELECT status,artifact_json FROM jobs WHERE id=?", (job["id"],)).fetchone()
        assert row["artifact_json"] is not None
        assert row["status"] in {"RUNNING", "RECONCILING", "QUEUED"}
        artifact = json.loads(row["artifact_json"])
        assert Path(artifact["master_path"]).is_file()
        assert conn.execute("SELECT COUNT(*) FROM versions WHERE job_id=?", (job["id"],)).fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM quota_events WHERE job_id=?", (job["id"],)).fetchone()[0] == 0
        calls_before = conn.execute("SELECT COUNT(*) FROM provider_calls WHERE job_id=?", (job["id"],)).fetchone()[0]
        conn.execute("DROP TRIGGER injected_commit_failure")
        conn.execute("UPDATE jobs SET lease_until=0 WHERE id=?", (job["id"],))
    finished = env.work(job)
    assert finished["status"] == "SUCCEEDED", finished
    saved = env.get(design)
    assert saved["successful_refinement_count"] == 1 and len(saved["versions"]) == 2
    Image.open(io.BytesIO(env.download(saved["current_version_id"]))).verify()
    with env.service.db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM quota_events WHERE job_id=?", (job["id"],)).fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM provider_calls WHERE job_id=?", (job["id"],)).fetchone()[0] == calls_before


def test_admin_configuration_creates_new_versions_without_rewriting_history(env):
    original = env.generate()
    version = original["versions"][0]
    original_bytes = env.download(version["id"])
    original_profile = version["snapshot"]["output_profile"]
    with TestClient(env.app, base_url="http://localhost") as admin:
        env.login("admin", client=admin)
        profile = ok(admin.post("/api/admin/output-profiles", json={
            "name": "验收演示配置", "width": 1200, "height": 300,
            "dpi": 144, "format": "PNG", "is_demo": True,
        }))
        assert profile["version"] > original_profile["version"]
        template = ok(admin.post("/api/admin/templates", json={
            "name": "内部验收单排", "mode": "single", "enabled": True,
            "rules": {"motif_ratio": 0.25, "step_ratio": 0.8},
        }))
        overview = ok(admin.get("/api/admin/overview"))
        assert overview["jobs"] and overview["output_profiles"] and overview["users"]
    current = env.get(original)
    assert current["versions"][0]["snapshot"]["output_profile"] == original_profile
    assert env.download(version["id"]) == original_bytes
    selection = env.selection()
    selection["template_id"] = template["id"]
    new = env.generate(selection=selection)
    new_version = new["versions"][0]
    assert new_version["snapshot"]["output_profile"]["version"] == profile["version"]
    assert Image.open(io.BytesIO(env.download(new_version["id"]))).size == (1200, 300)


@pytest.mark.parametrize("failure_at", ["provider", "render", "file_save"])
def test_a06_system_failures_preserve_version_and_release_quota_slot(env, monkeypatch, failure_at):
    from ribbon_backend import imaging, providers

    design = env.generate()
    original = env.download(design["current_version_id"])
    with monkeypatch.context() as patch:
        if failure_at == "provider":
            provider = providers.get_provider(env.service.settings)

            def fail_plan(*_args, **_kwargs):
                raise providers.ProviderError("simulated provider failure")

            patch.setattr(provider, "plan", fail_plan)
            patch.setattr(providers, "get_provider", lambda _settings: provider)
        else:
            def fail_render(*_args, **_kwargs):
                raise OSError("simulated image or filesystem failure")

            patch.setattr(imaging, "render" if failure_at == "render" else "_save_png", fail_render)
        failed = env.work(ok(env.refine(design)))
    assert failed["status"] == "FAILED"
    state = env.get(design)
    assert state["current_version_id"] == design["current_version_id"]
    assert state["successful_refinement_count"] == 0 and state["active_job_id"] is None
    assert len(state["versions"]) == 1
    assert env.download(state["current_version_id"]) == original
    recovered = env.refined(state)
    assert recovered["successful_refinement_count"] == 1


def test_expired_worker_cannot_commit_after_new_attempt_claims_job(env):
    design = env.generate()
    job = ok(env.refine(design))
    old = env.service.claim_job()
    assert old["id"] == job["id"]
    directory = env.service.root / "jobs" / old["id"] / str(old["attempt"])
    directory.mkdir(parents=True, exist_ok=True)
    artifact = env.service.build_artifact(old, directory)
    env.service.checkpoint(old, artifact, directory)
    with env.service.db.transaction() as conn:
        conn.execute("UPDATE jobs SET lease_until=0 WHERE id=?", (job["id"],))
    newer = env.service.claim_job()
    assert newer["id"] == old["id"] and newer["attempt"] == old["attempt"] + 1
    assert env.service.complete_job(old, artifact) is False
    assert env.get(design)["successful_refinement_count"] == 0
    env.service.process_job(newer)
    saved = env.get(design)
    assert saved["successful_refinement_count"] == 1 and len(saved["versions"]) == 2
    assert env.service.complete_job(old, artifact) is False
    assert env.get(design)["current_version_id"] == saved["current_version_id"]


@pytest.mark.parametrize("operation", [
    {"type": "parameters", "values": {"scale": 999}},
    {"type": "parameters", "values": {"scale": float("nan")}},
    {"type": "edit_asset", "asset_id": "another-customers-asset", "prompt": "添加星光"},
    {"type": "delete_all_assets", "values": {}},
])
def test_untrusted_edit_plan_is_semantically_validated(env, monkeypatch, operation):
    from ribbon_backend import providers

    design = env.generate()
    provider = providers.get_provider(env.service.settings)
    monkeypatch.setattr(provider, "plan", lambda *_args: {"operations": [operation], "summary": "invalid"})
    monkeypatch.setattr(providers, "get_provider", lambda _settings: provider)
    failed = env.work(ok(env.refine(design)))
    assert failed["status"] == "FAILED"
    saved = env.get(design)
    assert saved["successful_refinement_count"] == 0
    assert saved["current_version_id"] == design["current_version_id"]


def test_openai_without_credentials_keeps_deterministic_work_and_fails_ai_closed(tmp_path):
    settings = Settings(data_dir=tmp_path / "no-credentials", provider="openai",
                        openai_api_key="", language_model="", image_model="", start_worker=False)
    app = create_app(settings)
    with TestClient(app, base_url="http://localhost") as client:
        harness = Harness(app, client)
        harness.login()
        config = ok(client.get("/api/config"))
        assert config["provider"] == "openai" and config["ai_ready"] is False
        uploaded = ok(client.post("/api/assets", files={
            "file": ("no-model-needed.png", png_bytes(), "image/png"),
        }, data={"kind": "pattern", "name": "无需模型的上传图案"}))
        selection = harness.selection()
        selection["asset_ids"] = [uploaded["id"], selection["asset_ids"][0]]
        draft = harness.generate(selection=selection)
        assert draft["successful_refinement_count"] == 0
        selection["asset_ids"] = [uploaded["id"]]
        changed = harness.refined(draft, "应用所选配置", selection=selection)
        assert changed["successful_refinement_count"] == 1
        saved_bytes = harness.download(changed["current_version_id"])
        Image.open(io.BytesIO(saved_bytes)).verify()
        asset_ids_before = {a["id"] for a in ok(client.get("/api/assets"))}

        background = ok(client.post("/api/background-jobs", json={
            "idempotency_key": key(), "prompt": "浅绿柔和底图",
        }))
        background_failure = harness.work(background)
        content_failure = harness.work(ok(harness.refine(changed, "给第一个图案添加笑脸")))
        for failure in (background_failure, content_failure):
            assert failure["status"] == "FAILED" and failure["provider"] == "openai"
            assert "OPENAI_API_KEY" in failure["error"]
            assert failure["result_asset_id"] is None and failure["result_version_id"] is None
        unchanged = harness.get(changed)
        assert unchanged["current_version_id"] == changed["current_version_id"]
        assert unchanged["successful_refinement_count"] == 1 and len(unchanged["versions"]) == 2
        assert harness.download(unchanged["current_version_id"]) == saved_bytes
        assert {a["id"] for a in ok(client.get("/api/assets"))} == asset_ids_before
        with harness.service.db.connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM provider_calls").fetchone()[0] == 0


def test_queued_jobs_pin_provider_and_model_config_across_worker_restart(env, monkeypatch):
    from ribbon_backend import providers

    design = env.generate()
    env.service.settings.language_model = "saved-test-language"
    env.service.settings.image_model = "saved-test-image"
    env.service.settings.image_quality = "low"
    env.service.settings.config_revision = 7
    refinement = ok(env.refine(design, "背景添加波点"))
    background = ok(env.client.post("/api/background-jobs", json={
        "idempotency_key": key(), "prompt": "浅蓝色柔和底图",
    }))
    observed_configs = []
    actual_get_provider = providers.get_provider

    def observe(settings):
        observed_configs.append((settings.provider, settings.language_model,
                                 settings.image_model, settings.image_quality, settings.config_revision))
        return actual_get_provider(settings)

    monkeypatch.setattr(providers, "get_provider", observe)
    # A restarted worker has a changed global provider and model selection, with
    # no real credential. Previously accepted jobs must use their saved config.
    restarted = create_app(Settings(
        data_dir=env.service.root, provider="openai", openai_api_key="",
        language_model="new-language", image_model="new-image", image_quality="high",
        start_worker=False,
    ))
    with TestClient(restarted, base_url="http://localhost") as client:
        restored = Harness(restarted, client)
        restored.login()
        assert ok(client.get("/api/config"))["provider"] == "openai"
        for queued in (refinement, background):
            completed = restored.work(queued)
            assert completed["status"] == "SUCCEEDED" and completed["provider"] == "test"
        assert observed_configs == [("test", "saved-test-language", "saved-test-image", "low", 7)] * 2
        saved = restored.get(design)
        assert saved["successful_refinement_count"] == 1
        assert next(v for v in saved["versions"] if v["id"] == saved["current_version_id"])["provider"] == "test"
        with restored.service.db.connect() as conn:
            for job in (refinement, background):
                payload = json.loads(conn.execute("SELECT payload_json FROM jobs WHERE id=?", (job["id"],)).fetchone()[0])
                assert payload["model_config"] == {"language_model": "saved-test-language",
                                                   "image_model": "saved-test-image", "image_quality": "low", "config_revision": 7}
                calls = conn.execute("SELECT provider FROM provider_calls WHERE job_id=?", (job["id"],)).fetchall()
                assert calls and all(row["provider"] == "test" for row in calls)


def test_failed_provider_call_preserves_reported_usage_without_charging_refinement(env, monkeypatch):
    from ribbon_backend import providers

    design = env.generate()

    def failed_plan(*args, **kwargs):
        error = providers.ProviderError('模拟已计费但无法完成的调用')
        error.usage = {'prompt_tokens': 12, 'completion_tokens': 3}
        raise error

    monkeypatch.setattr(providers.TestProvider, 'plan', failed_plan)
    job = ok(env.refine(design))
    assert env.work(job)['status'] == 'FAILED'
    assert env.get(design)['successful_refinement_count'] == 0
    with env.service.db.connect() as db:
        call = db.execute('SELECT * FROM provider_calls WHERE job_id=?', (job['id'],)).fetchone()
        assert json.loads(call['usage_json']) == {'prompt_tokens': 12, 'completion_tokens': 3}
        assert call['status'] == 'FAILED'


@pytest.mark.parametrize('source_kind', ['pattern', 'background', 'composite'])
def test_changed_source_is_rejected_before_paid_planning_or_quota_charge(env, source_kind):
    design = env.generate()
    if source_kind == 'composite':
        design = env.refined(design, '整体添加星光')
    before = env.download(design['current_version_id'])
    version = next(v for v in design['versions'] if v['id'] == design['current_version_id'])
    snapshot = version['snapshot']
    asset_id = snapshot['asset_refs'][0] if source_kind == 'pattern' else snapshot[source_kind + '_ref']
    with env.service.db.connect() as db:
        path = Path(db.execute('SELECT path FROM assets WHERE id=?', (asset_id,)).fetchone()[0])
    Image.new('RGBA', (32, 32), 'purple').save(path, 'PNG')
    preview = env.client.get(f'/api/assets/{asset_id}/file')
    assert preview.status_code == 409 and '校验失败' in preview.text
    job = ok(env.refine(design, '整体添加星光' if source_kind == 'composite' else '图案缩小一些'))
    result = env.work(job)
    assert result['status'] == 'FAILED' and '校验失败' in result['error']
    unchanged = env.get(design)
    assert unchanged['current_version_id'] == design['current_version_id']
    assert unchanged['successful_refinement_count'] == design['successful_refinement_count']
    assert env.download(design['current_version_id']) == before
    with env.service.db.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM provider_calls WHERE job_id=?', (job['id'],)).fetchone()[0] == 0


@pytest.mark.parametrize('changed', ['pixels', 'legacy_hash'])
def test_template_preview_rejects_changed_or_unverifiable_image(env, changed):
    template = env.service.templates()[0]
    assert env.client.get(template['thumbnail_url']).status_code == 200
    with env.service.db.transaction() as db:
        if changed == 'legacy_hash':
            db.execute('UPDATE templates SET thumbnail_sha256=NULL WHERE id=? AND version=?', (template['id'], template['version']))
        else:
            path = db.execute('SELECT thumbnail_path FROM templates WHERE id=? AND version=?', (template['id'], template['version'])).fetchone()[0]
            Image.new('RGB', (32, 32), 'red').save(path, 'PNG')
    response = env.client.get(template['thumbnail_url'])
    assert response.status_code == 409 and '校验失败' in response.text


def test_editing_demo_template_preserves_marker_and_old_thumbnail(env):
    old = env.service.templates()[0]
    first = env.client.get(old['thumbnail_url']).content
    new = env.service.save_template(dict(id=old['id'], name=old['name'], mode=old['mode'], rules=dict(old['rules'], rows=3)))
    assert new['version'] == old['version'] + 1
    assert new['rules']['is_demo']
    assert env.client.get(old['thumbnail_url']).content == first
    response = env.client.get(new['thumbnail_url'])
    assert response.status_code == 200 and response.content != first
