"""Authenticated, same-process FastAPI mount for the ribbon workspace.

The host remains the only identity authority and public listener. The durable
SQLite worker shares the host's provider pool; no credentials enter WSGI headers.
"""
from __future__ import annotations

import asyncio
import io
from pathlib import Path
import secrets
import threading

from flask import Response, jsonify, request, session

from . import admin_auth


def reserve_space(directory, required_bytes):
    from .uploads import DiskBudget
    # Preserve room for SQLite/checkpoints even after the expected write.
    DiskBudget(directory).reserve(required_bytes + 64 * 1024 * 1024)


class RibbonGateway:
    def __init__(self, manager, material_settings):
        from .ribbon_settings import RibbonSettings
        self.manager = manager
        self.settings = RibbonSettings(manager.ai_settings.path.parent,
                                       ai_settings=manager.ai_settings,
                                       material_settings=material_settings,
                                       key_pool=manager.ai_key_pool,
                                       usage_ledger=manager.ai_usage)
        self.lock = threading.RLock()
        self.condition = threading.Condition(self.lock)
        self.active_requests = 0
        self.service = self.mount = self.loop = self.thread = None
        self.closing = False

    def get(self):
        with self.lock:
            if self.closing:
                raise ValueError('服务正在更新，请稍后重试。')
            if self.service is None:
                from a2wsgi import ASGIMiddleware
                from ribbon_backend.app import create_app
                from ribbon_backend.config import Settings
                from ribbon_backend.service import Service
                base = Settings(data_dir=Path(self.manager.data_dir) / 'ribbon',
                                auth_mode='hsd', provider='openai',
                                openai_api_key='', language_model='', image_model='',
                                enabled=False, api_prefix='/api/ribbon', start_worker=False,
                                space_reserver=reserve_space)
                service = Service(base,
                    runtime_settings_supplier=lambda: self.settings.runtime_settings(base),
                    provider_factory=lambda provider, config: self.settings.provider_for_job(provider, config, base=base))
                api = create_app(base, service=service)
                loop = asyncio.new_event_loop()
                thread = threading.Thread(target=loop.run_forever, name='hsd-ribbon-api', daemon=True)
                thread.start()
                self.service, self.loop, self.thread = service, loop, thread
                self.mount = ASGIMiddleware(api, loop=loop)
                service.start()
            return self.service, self.mount

    def acquire(self):
        with self.condition:
            service, mount = self.get()
            self.active_requests += 1
        released = False
        def release():
            nonlocal released
            with self.condition:
                if not released:
                    released = True
                    self.active_requests -= 1
                    self.condition.notify_all()
        return service, mount, release

    def close(self):
        with self.condition:
            self.closing = True
            while self.active_requests:
                self.condition.wait()
            service, loop, thread = self.service, self.loop, self.thread
        if service:
            service.stop()
        if loop and loop.is_running():
            loop.call_soon_threadsafe(loop.stop)
            thread.join()
            loop.close()


def register_ribbon(app, manager, material_settings, employee_id):
    from .ribbon_examples import IMAGE_SPECS, RibbonExamples
    gateway = RibbonGateway(manager, material_settings)
    app.config['HSD_RIBBON'] = gateway
    manager.ribbon_gateway = gateway
    examples = RibbonExamples(manager.ai_settings.path.parent / 'ribbon_layout_examples')
    app.config['HSD_RIBBON_EXAMPLES'] = examples

    @app.get('/api/ribbon/layout-examples')
    def ribbon_layout_examples():
        # The existing host guard authenticates the employee before any read.
        # No design, worker, quota, provider call or uploaded asset is created.
        return jsonify(examples.catalog())

    @app.get('/api/ribbon/layout-examples/<code>/image')
    def ribbon_layout_example_image(code):
        expected = IMAGE_SPECS.get(code)
        versions = request.args.getlist('v')
        if set(request.args) - {'v'} or len(versions) > 1:
            return jsonify(error='案例图片地址无效，请重新打开案例。'), 400
        if expected is None or (versions and versions[0] != expected[3][:16]):
            return jsonify(error='案例图片暂时无法查看，请重新打开案例。'), 404
        data = examples.image(code)
        if data is None:
            return jsonify(error='案例图片暂未准备好，请联系管理员。'), 404
        response = Response(data, mimetype='image/jpeg')
        response.headers['Cache-Control'] = 'private, no-cache, must-revalidate'
        response.headers['Vary'] = 'Cookie'
        response.headers['Cross-Origin-Resource-Policy'] = 'same-origin'
        response.set_etag(expected[3])
        # Authentication and current-byte verification precede even a 304/HEAD.
        response.make_conditional(request)
        return response

    @app.route('/api/admin/ribbon-settings', methods=['GET', 'POST'])
    def ribbon_settings():
        # Defense in depth; the host guard also checks administrator auth.
        if not admin_auth.authenticated(session):
            return jsonify(error='请先登录管理员分区。'), 401
        if request.method == 'POST':
            from .ribbon_settings import RibbonSettingsConflict
            try:
                return jsonify(gateway.settings.save(request.get_json()))
            except RibbonSettingsConflict as error:
                return jsonify(error=str(error), code='revision_conflict'), 409
        return jsonify(gateway.settings.snapshot())

    @app.route('/api/ribbon/<path:ribbon_path>', methods=['GET', 'POST', 'DELETE', 'PUT', 'PATCH'])
    def ribbon_api(ribbon_path):
        service, mount, release = gateway.acquire()
        lease = None
        lease_entered = False
        try:
            owner = employee_id()
            if not owner:
                # Local mode still keeps distinct browsers private. Never use a
                # shared access code or caller-supplied user ID as the owner.
                owner = session.setdefault('ribbon_local_owner', secrets.token_hex(16))
            role = 'admin' if admin_auth.authenticated(session) else 'customer'
            if ribbon_path.startswith('admin/') and role != 'admin':
                release()
                return jsonify(error='请先登录管理员分区。'), 403
            current = service.ensure_external_user('hsd:' + owner, role)
            environ = request.environ.copy()
            environ['hsd.ribbon_user'] = current
            # The host JSON guard has read/cached the body. Multipart input
            # stays streaming and is not parsed twice.
            if request.is_json:
                body = request.get_data()
                environ['wsgi.input'] = io.BytesIO(body)
                environ['CONTENT_LENGTH'] = str(len(body))
            lease = service.resource_lease(current['id'])
            lease.__enter__()
            lease_entered = True
            response = Response.from_app(mount, environ)
            response.call_on_close(lambda: lease.__exit__(None, None, None))
            response.call_on_close(release)
            return response
        except BaseException:
            try:
                if lease_entered:
                    lease.__exit__(None, None, None)
            finally:
                release()
            raise

    # An existing persistent queue must recover without waiting for an employee
    # to visit the workspace. Fresh installs allocate it lazily.
    if (Path(manager.data_dir) / 'ribbon' / 'ribbon.sqlite3').is_file():
        gateway.get()
    return gateway
