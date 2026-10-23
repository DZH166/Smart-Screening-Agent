"""Linux production lifecycle contracts, with no network/model credentials."""
import os
import signal
from types import SimpleNamespace

import pytest

if os.name == "nt":
    pytest.skip("Gunicorn生产生命周期在Linux验收，Windows不加载POSIX服务器。", allow_module_level=True)
pytest.importorskip("gunicorn")

from hsd_tool import cloud_gunicorn as production


def test_production_options_ignore_worker_environment_and_disable_shared_control_socket(monkeypatch):
    monkeypatch.setenv("GUNICORN_CMD_ARGS", "--workers 8 --preload")
    monkeypatch.setenv("WEB_CONCURRENCY", "8")
    app = production.CloudApplication()
    assert app.cfg.workers == 1 and app.cfg.threads == 4
    assert not app.cfg.preload_app and not app.cfg.reload
    assert app.cfg.max_requests == 0 and app.cfg.timeout == 0
    assert app.cfg.control_socket_disable
    assert app.cfg.forwarded_allow_ips == [] and app.cfg.secure_scheme_headers == {}
    assert app.cfg.address == [("127.0.0.1", 8830)]


def test_term_marks_stopping_without_acquiring_manager_lock():
    deferred = []
    worker = object.__new__(production.CloudWorker)
    worker.wsgi = SimpleNamespace(config={})
    worker.alive = True
    worker.method_queue = SimpleNamespace(defer=deferred.append)
    worker.handle_exit(signal.SIGTERM, None)
    assert not worker.alive and worker.wsgi.config["HSD_STOPPING"]
    assert len(deferred) == 1


def test_worker_drains_http_before_stopping_retention_and_background_jobs(monkeypatch):
    order = []
    worker = object.__new__(production.CloudWorker)
    worker.wsgi = SimpleNamespace(config={
        "HSD_RETENTION": SimpleNamespace(stop=lambda: order.append("retention_stopped"),
            sweep=lambda *, delete: order.append(("final_settled", delete))),
        "HSD_MANAGER": SimpleNamespace(close=lambda *, on_drained: (order.append("manager_drained"), on_drained())),
    })
    worker.tpool = SimpleNamespace(shutdown=lambda *, wait: order.append(("http_drained", wait)))
    monkeypatch.setattr(production.ThreadWorker, "run", lambda self: order.append("http_loop_ended"))
    worker.run()
    assert order == ["http_loop_ended", ("http_drained", True), "retention_stopped", "manager_drained", ("final_settled", False)]
    assert worker.wsgi.config["HSD_STOPPING"]


def test_master_waits_for_worker_exit_instead_of_default_grace_force_kill(monkeypatch):
    master = object.__new__(production.CloudArbiter)
    master.reexec_pid = master.master_pid = 0
    master.systemd = False
    master.cfg = SimpleNamespace(reuse_port=False)
    master.LISTENERS = ["synthetic-listener"]
    master.WORKERS = {1: "synthetic-worker"}
    actions = []
    master.kill_workers = lambda sig: actions.append(sig)
    master.reap_workers = lambda: master.WORKERS.clear()
    monkeypatch.setattr(production.sock, "close_sockets", lambda listeners, unlink: actions.append((listeners, unlink)))
    monkeypatch.setattr(production.time, "sleep", lambda delay: None)
    master.stop()
    assert actions == [(["synthetic-listener"], True), signal.SIGTERM]
    assert master.LISTENERS == []


def test_shutdown_drains_material_requests_before_numbering_and_final_retention():
    order = []
    app = SimpleNamespace(config={
        "HSD_MATERIAL_MANAGER": SimpleNamespace(close=lambda: order.append("materials_settled")),
        "HSD_MANAGER": SimpleNamespace(close=lambda: order.append("numbering_settled")),
    })
    production.shutdown_application(app)
    assert app.config["HSD_STOPPING"]
    assert order == ["materials_settled", "numbering_settled"]


def test_reload_and_worker_count_signals_cannot_create_parallel_owner_maps():
    master = object.__new__(production.CloudArbiter)
    warnings = []
    master.log = SimpleNamespace(warning=warnings.append)
    for name in ("handle_hup", "handle_usr2", "handle_ttin", "handle_ttou", "handle_winch"):
        getattr(master, name)()
    assert len(warnings) == 5
