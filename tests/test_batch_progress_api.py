"""Streaming progress and grouped decisions retain session/revision boundaries."""
import json

from test_material_api import application, call, login, upload, ORIGIN
from test_bulk_confirmation import reviewing, selection


def finished(application):
    app, manager, provider = application
    client = app.test_client(); login(client)
    identifier = upload(client).json["id"]
    manager.futures[identifier].result(20)
    state = call(client, f"/api/material/jobs/{identifier}").json
    return client, identifier, state


def test_material_stream_only_own_task_and_terminal_closes(application):
    client, identifier, state = finished(application)
    app, manager, _ = application
    response = call(client, f"/api/material/jobs/{identifier}/events")
    assert response.status_code == 200
    assert response.mimetype == "text/event-stream"
    assert response.headers["X-Accel-Buffering"] == "no"
    assert "no-store" in response.headers["Cache-Control"]
    content = response.data.decode()
    assert "event: snapshot" in content and "event: end" in content
    assert identifier in content and "synthetic-private-key" not in content
    response.close()
    other = app.test_client(); login(other)
    assert call(other, f"/api/material/jobs/{identifier}/events").status_code == 404
    assert call(app.test_client(), f"/api/material/jobs/{identifier}/events").status_code == 401
    assert not manager.has_active_operations()


def test_stream_slot_is_released_on_disconnect(application):
    app, manager, provider = application
    client = app.test_client(); login(client)
    provider.block = True
    identifier = upload(client).json["id"]
    assert provider.entered.wait(5)
    first = call(client, f"/api/material/jobs/{identifier}/events", buffered=False)
    second = call(client, f"/api/material/jobs/{identifier}/events", buffered=False)
    assert first.status_code == second.status_code == 200
    assert call(client, f"/api/material/jobs/{identifier}/events").status_code == 429
    # Ordinary GET remains available while two streams wait on upstream.
    assert call(client, f"/api/material/jobs/{identifier}").status_code == 200
    first.close()
    replacement = call(client, f"/api/material/jobs/{identifier}/events", buffered=False)
    assert replacement.status_code == 200
    replacement.close(); second.close(); provider.release.set()


def test_material_batch_requires_owner_token_revision_and_can_undo(application):
    client, identifier, state = finished(application)
    app, _, _ = application
    path = f"/api/material/jobs/{identifier}"
    payload = {"expected_revision": state["revision"], "item_ids": [row["id"] for row in state["items"]]}
    assert call(client, path + "/resolve-batch", method="POST", payload=payload, token=None).status_code == 403
    other = app.test_client(); login(other)
    assert call(other, path + "/resolve-batch", method="POST", payload=payload).status_code == 404
    response = call(client, path + "/resolve-batch", method="POST", payload=payload)
    assert response.status_code == 200 and response.json["stats"]["ready"] == 2
    assert call(client, path + "/resolve-batch", method="POST", payload=payload).status_code == 409
    undo = call(client, path + "/undo-batch", method="POST", payload={"expected_revision": response.json["revision"]})
    assert undo.status_code == 200 and undo.json["stats"]["needs_review"] == 2


def test_numbering_batch_revision_owner_csrf_and_group_undo(application, tmp_path):
    app, _, _ = application
    fixture_manager, job = reviewing(tmp_path / "inputs")
    job["_output_root"] = str(tmp_path / "outputs")
    fixture_manager.jobs.pop("sample"); fixture_manager.close()
    client = app.test_client(); login(client)
    with client.session_transaction(base_url=ORIGIN) as sess:
        job["_owner_id"] = sess["employee_id"]
    app.config["HSD_MANAGER"].jobs["sample"] = job
    payload = {"expected_revision": 0, "items": selection(2, 3)}
    other = app.test_client(); login(other)
    assert call(other, "/api/jobs/sample/resolve-batch", method="POST", payload=payload).status_code == 404
    assert call(client, "/api/jobs/sample/resolve-batch", method="POST", payload=payload, token=None).status_code == 403
    response = call(client, "/api/jobs/sample/resolve-batch", method="POST", payload=payload)
    assert response.status_code == 200, response.json
    assert response.json["stats"]["confirmed"] == 2
    assert call(client, "/api/jobs/sample/resolve-batch", method="POST", payload=payload).status_code == 409
    undo = call(client, "/api/jobs/sample/undo", method="POST", payload={"expected_revision": 1})
    assert undo.status_code == 200 and undo.json["last_undone_count"] == 2
    assert undo.json["stats"]["review"] == 3
