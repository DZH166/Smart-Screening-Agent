"""A failing local write or a task-level error must always leave the batch in a
state the page can act on: terminal, with a reason and a retry path.

Synthetic providers and images only; no paid calls.
"""
from __future__ import annotations

import errno

import pytest
from werkzeug.exceptions import Conflict

from hsd_tool.material_service import MaterialManager, _setup_error
from test_material_service import Provider, Settings, complete, upload


def manager_for(tmp_path, provider):
    return MaterialManager(tmp_path, Settings(), cloud=True, provider_factory=lambda config: provider)


def test_a_failed_first_save_ends_the_batch_instead_of_leaving_it_processing(tmp_path):
    provider = Provider()
    manager = manager_for(tmp_path, provider)
    original = manager._save

    def failing(job, **kwargs):
        if job["status"] == "processing" and not kwargs.get("touch"):
            raise OSError(errno.ENOSPC, "synthetic save failure")
        return original(job, **kwargs)

    manager._save = failing
    try:
        identifier = upload(manager)
        final = complete(manager, identifier)
    finally:
        manager.close()
    assert final["status"] == "error"
    assert "任务状态写入失败" in final["error"]
    assert final["sources"][0]["status"] == "error" and final["sources"][0]["error"]
    assert final["stats"]["failed"] == 1
    # Nothing was sent to the provider, so nothing was billed.
    assert provider.calls == 0


def test_a_failed_redo_write_keeps_the_saved_state_and_asks_to_retry(tmp_path):
    provider = Provider()
    manager = manager_for(tmp_path, provider)
    try:
        state = complete(manager, upload(manager))
        original = manager._save

        def failing(job, **kwargs):
            if job["status"] == "queued" and job["items"]:
                raise OSError(errno.ENOSPC, "synthetic save failure")
            return original(job, **kwargs)

        manager._save = failing
        with pytest.raises(Conflict, match="写入失败"):
            manager.redo(state["id"], "employee-a",
                         {"expected_revision": state["revision"], "source_id": state["sources"][0]["id"],
                          "box": {"x": 8, "y": 8, "width": 8, "height": 8}})
        # The in-memory job still matches the last saved state, so the page can
        # simply retry instead of sitting on a "queued" batch nobody will run.
        live = manager.snapshot(state["id"], "employee-a")
        assert live["status"] == "ready" and live["revision"] == state["revision"]
        assert manager.futures[state["id"]].done()
    finally:
        manager.close()
    assert provider.calls == 1


def test_a_task_level_setup_error_names_the_fix_and_closes_the_originals(tmp_path):
    provider = Provider()
    manager = manager_for(tmp_path, provider)
    message = "素材范围识别需要可用的 DeepSeek 服务，请联系管理员配置并开启。"
    calls = {"count": 0}
    real = manager._runtime

    def runtime(**kwargs):
        calls["count"] += 1
        if calls["count"] > 1:  # The upload-time check passes; the run-time one fails.
            raise _setup_error(message)
        return real(**kwargs)

    manager._runtime = runtime
    try:
        identifier = upload(manager)
        final = complete(manager, identifier)
    finally:
        manager.close()
    assert final["status"] == "error" and final["error"] == message
    assert final["sources"][0]["status"] == "error"
    assert final["sources"][0]["error"] == message
    assert final["stats"]["failed"] == 1
    assert provider.calls == 0
