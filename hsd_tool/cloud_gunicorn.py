"""Linux-only single-worker streaming WSGI lifecycle.

No request-body byte limit or whole-body spool is added by this server. The
existing authenticated EmployeeUploadRequest remains responsible for streaming
multipart files and checking available disk space.
"""
from __future__ import annotations

import os
import signal
import time

from gunicorn.app.base import BaseApplication
from gunicorn.arbiter import Arbiter
from gunicorn import sock
from gunicorn.workers.gthread import ThreadWorker


def shutdown_application(app):
    app.config["HSD_STOPPING"] = True
    retention = app.config.get("HSD_RETENTION")
    if retention is not None:
        retention.stop()
        app.config["HSD_MANAGER"].close(on_drained=lambda: retention.sweep(delete=False))
    else:
        app.config["HSD_MANAGER"].close()


class CloudWorker(ThreadWorker):
    def handle_exit(self, sig, frame):
        # Do not acquire locks from a signal handler. This atomic flag rejects
        # new mutations; already accepted request/job work is drained below.
        if getattr(self, "wsgi", None) is not None:
            self.wsgi.config["HSD_STOPPING"] = True
        super().handle_exit(sig, frame)

    def run(self):
        try:
            super().run()
        finally:
            # Gunicorn's ordinary gthread grace stops waiting for HTTP futures
            # after a fixed delay. Do not abandon active uploads/downloads or
            # accepted background work when the service receives normal TERM.
            self.tpool.shutdown(wait=True)
            if getattr(self, "wsgi", None) is not None:
                shutdown_application(self.wsgi)


class CloudArbiter(Arbiter):
    def stop(self, graceful=True):
        if not graceful:
            return super().stop(graceful=False)
        unlink = self.reexec_pid == self.master_pid == 0 and not self.systemd and not self.cfg.reuse_port
        sock.close_sockets(self.LISTENERS, unlink)
        self.LISTENERS = []
        self.kill_workers(signal.SIGTERM)
        while self.WORKERS:
            self.reap_workers()
            time.sleep(0.1)

    def _no_parallel_reload(self):
        self.log.warning("Single-worker service: use a drained service restart for updates.")

    # Sessions/jobs are intentionally process-local. Neither a reload signal
    # nor worker-count signal may silently create a second live owner map.
    handle_hup = handle_usr2 = handle_ttin = handle_ttou = handle_winch = _no_parallel_reload


def server_options(environ=None):
    env = os.environ if environ is None else environ
    try:
        port = int(env.get("HSD_BIND_PORT", "8830"))
    except ValueError:
        raise ValueError("服务器内部端口无效。") from None
    if not 1024 <= port <= 65535:
        raise ValueError("服务器内部端口必须为1024–65535。")
    return {"bind": f"127.0.0.1:{port}", "workers": 1,
            "worker_class": "hsd_tool.cloud_gunicorn.CloudWorker", "threads": 4,
            "worker_connections": 64, "timeout": 0, "graceful_timeout": 30,
            "preload_app": False, "max_requests": 0, "reload": False,
            "accesslog": None, "errorlog": "-", "capture_output": False,
            "control_socket_disable": True,
            "forwarded_allow_ips": "", "secure_scheme_headers": {},
            "umask": 0o077}


class CloudApplication(BaseApplication):
    def load_config(self):
        for key, value in server_options().items():
            self.cfg.set(key, value)

    def load(self):
        from .cloud_server import create_cloud_app
        return create_cloud_app()

    def run(self):
        CloudArbiter(self).run()


def run():
    CloudApplication().run()
