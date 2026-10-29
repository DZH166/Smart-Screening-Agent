from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlparse
import time

from fastapi import Depends, FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

from .config import ROOT, Settings
from .service import Service, ServiceError


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Login(StrictModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=256)


class DesignCreate(StrictModel):
    name: str = Field(default='未命名设计', max_length=80)


class Selection(StrictModel):
    asset_ids: list[str] = Field(min_length=1, max_length=12)
    background_id: str
    template_id: str


class Generate(Selection):
    idempotency_key: str = Field(min_length=8, max_length=160)


class Refinement(StrictModel):
    idempotency_key: str = Field(min_length=8, max_length=160)
    base_version_id: str
    prompt: str = Field(min_length=1, max_length=2000)
    selection: Selection | None = None


class Background(StrictModel):
    idempotency_key: str = Field(min_length=8, max_length=160)
    prompt: str = Field(default='', max_length=2000)


class Rollback(StrictModel):
    expected_version_id: str


class TemplateInput(StrictModel):
    id: str | None = None
    name: str = Field(min_length=1, max_length=80)
    mode: Literal['grid', 'stagger', 'scatter', 'single', 'ends', 'panels']
    enabled: bool = True
    rules: dict = Field(default_factory=dict)


class ProfileInput(StrictModel):
    name: str = Field(min_length=1, max_length=80)
    width: int
    height: int
    dpi: int
    format: Literal['PNG'] = 'PNG'
    is_demo: bool = True


def create_app(settings: Settings | None = None, *, service: Service | None = None):
    settings = settings or Settings()
    service = service or Service(settings)

    @asynccontextmanager
    async def lifespan(app):
        if settings.start_worker:
            service.start()
        yield
        service.stop()

    app = FastAPI(title='丝带设计助手 V1', lifespan=lifespan,
                  docs_url=None if settings.auth_mode == 'hsd' else '/docs',
                  redoc_url=None, openapi_url=None if settings.auth_mode == 'hsd' else '/openapi.json')
    app.state.service = service
    login_attempts = {}

    @app.exception_handler(ServiceError)
    async def service_error(request, error):
        return JSONResponse(status_code=error.status, content={'detail': error.message})

    @app.middleware('http')
    async def boundaries(request, call_next):
        # Cross-origin state-changing requests are never accepted. Cookies are HttpOnly/SameSite Strict.
        if request.method in ('POST', 'DELETE', 'PUT', 'PATCH'):
            origin = request.headers.get('origin')
            if origin and urlparse(origin).netloc != request.headers.get('host'):
                return JSONResponse(status_code=403, content={'detail': '不允许跨站请求'})
            length = request.headers.get('content-length')
            if length and (not length.isdigit() or int(length) > 21 * 1024 * 1024):
                return JSONResponse(status_code=413, content={'detail': '请求超过 20MB 限制'})
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['X-Frame-Options'] = 'DENY'
        if request.url.path.startswith('/api/') and 'cache-control' not in response.headers:
            # Image routes may opt into a short private cache; everything else
            # stays uncached so a stale token cannot be replayed from disk.
            response.headers['Cache-Control'] = 'private, no-store'
        return response

    def user(request: Request):
        if settings.auth_mode == 'hsd':
            # This value is inserted by the authenticated Flask gateway, never
            # read from an HTTP header, cookie value or caller-provided JSON.
            current = request.scope.get('wsgi_environ', {}).get('hsd.ribbon_user')
            if not isinstance(current, dict) or current.get('role') not in ('customer', 'admin'):
                raise ServiceError(401, '请通过主站登录后打开丝带设计')
        else:
            current = service.authenticate(request.cookies.get('ribbon_session'))
        with service.resource_lease(current['id']):
            yield current

    def admin(current=Depends(user)):
        if current['role'] != 'admin':
            raise ServiceError(403, '此操作需要内部管理员账号')
        return current

    @app.get('/api/health')
    def health():
        return {'status': 'ok', 'provider': settings.provider, 'storage': 'sqlite-local'}

    @app.post('/api/auth/login')
    def login(body: Login, request: Request):
        if settings.auth_mode == 'hsd':
            raise ServiceError(403, '请使用主站员工或管理员入口登录')
        address = request.client.host if request.client else 'local'
        attempts = [t for t in login_attempts.get(address, []) if t > time.time()-60]
        if len(attempts) >= 20:
            raise ServiceError(429, '登录尝试过多，请一分钟后重试')
        attempts.append(time.time())
        login_attempts[address] = attempts
        token, current = service.login(body.username, body.password)
        response = JSONResponse(current)
        response.set_cookie('ribbon_session', token, httponly=True, secure=settings.secure_cookie, samesite='strict', max_age=settings.session_hours*3600)
        return response

    @app.get('/api/auth/me')
    def me(current=Depends(user)):
        return current

    @app.post('/api/auth/logout')
    def logout(request: Request):
        if settings.auth_mode == 'hsd':
            raise ServiceError(403, '请使用主站退出入口')
        service.logout(request.cookies.get('ribbon_session'))
        response = JSONResponse({'ok': True})
        response.delete_cookie('ribbon_session')
        return response

    @app.get('/api/config')
    def config(current=Depends(user)):
        return service.config()

    @app.get('/api/assets')
    def assets(kind: Literal['pattern', 'background'] | None = None, current=Depends(user)):
        return service.assets(current['id'], kind)

    @app.post('/api/assets', status_code=201)
    async def upload(file: Annotated[UploadFile, File()], kind: Annotated[str, Form()] = 'pattern', name: Annotated[str, Form()] = '', shared: Annotated[bool, Form()] = False, current=Depends(user)):
        data = await file.read(20*1024*1024+1)
        return await run_in_threadpool(service.upload, current, data, name or Path(file.filename or '上传素材').stem, kind, shared)

    @app.delete('/api/assets/{asset_id}')
    def delete_asset(asset_id: str, current=Depends(user)):
        service.hide_asset(current, asset_id)
        return {'ok': True}

    @app.get('/api/assets/{asset_id}/file')
    def asset_file(asset_id: str, current=Depends(user)):
        return FileResponse(service.verified_asset_path(current['id'], asset_id), media_type='image/png')

    @app.get('/api/templates')
    def templates(current=Depends(user)):
        return service.templates()

    @app.get('/api/templates/{template_id}/{version}/thumbnail')
    def thumbnail(template_id: str, version: int, current=Depends(user)):
        return FileResponse(service.verified_template_path(template_id, version), media_type='image/png')

    @app.get('/api/designs')
    def designs(current=Depends(user)):
        return service.designs(current['id'])

    @app.post('/api/designs', status_code=201)
    def create_design(body: DesignCreate, current=Depends(user)):
        return service.create_design(current['id'], body.name)

    @app.get('/api/designs/{design_id}')
    def design(design_id: str, current=Depends(user)):
        return service.design(current['id'], design_id)

    @app.post('/api/designs/{design_id}/generate', status_code=202)
    def generate(design_id: str, body: Generate, current=Depends(user)):
        return service.submit(current['id'], 'generate', body.model_dump(), design_id)

    @app.post('/api/designs/{design_id}/refinements', status_code=202)
    def refine(design_id: str, body: Refinement, current=Depends(user)):
        return service.submit(current['id'], 'refine', body.model_dump(exclude_none=True), design_id)

    @app.post('/api/designs/{design_id}/rollback')
    def rollback(design_id: str, body: Rollback, current=Depends(user)):
        return service.rollback(current['id'], design_id, body.expected_version_id)

    @app.post('/api/background-jobs', status_code=202)
    def background(body: Background, current=Depends(user)):
        return service.submit(current['id'], 'background', body.model_dump())

    @app.get('/api/jobs/{job_id}')
    def job(job_id: str, current=Depends(user)):
        return service.job(current['id'], job_id)

    @app.get('/api/versions/{version_id}/preview')
    def preview(version_id: str, current=Depends(user)):
        return FileResponse(service.version_file(current['id'], version_id, True), media_type='image/png')

    @app.get('/api/versions/{version_id}/view')
    def view(version_id: str, current=Depends(user)):
        # Full-resolution master, inline, for the detail preview: a 11811x520 strip
        # shrunk into a 159 px preview is unreadable, and raising the print DPI
        # does not change what the screen shows.
        response = FileResponse(service.version_file(current['id'], version_id), media_type='image/png')
        response.headers['Cache-Control'] = 'private, max-age=300'
        return response

    @app.get('/api/versions/{version_id}/download')
    def download(version_id: str, current=Depends(user)):
        # Bind the exact immutable path before streaming; never resolve current pointer again.
        return FileResponse(service.version_file(current['id'], version_id), media_type='image/png', filename=f'ribbon-{version_id}.png')

    @app.get('/api/admin/overview')
    def overview(current=Depends(admin)):
        return service.admin_overview()

    @app.post('/api/admin/templates', status_code=201)
    def save_template(body: TemplateInput, current=Depends(admin)):
        return service.save_template(body.model_dump(exclude_none=True))

    @app.post('/api/admin/output-profiles', status_code=201)
    def save_profile(body: ProfileInput, current=Depends(admin)):
        return service.save_profile(body.model_dump())

    frontend = ROOT / 'ribbon_frontend' / 'dist'
    if settings.auth_mode == 'hsd':
        # Mount only the API under the host; no second login or public port.
        for route in app.routes:
            if getattr(route, 'path', '').startswith('/api/'):
                route.path = settings.api_prefix + route.path[4:]
                from starlette.routing import compile_path
                route.path_regex, route.path_format, route.param_convertors = compile_path(route.path)
    elif frontend.is_dir():
        app.mount('/', StaticFiles(directory=frontend, html=True), name='frontend')
    else:
        @app.get('/')
        def no_build():
            return {'detail': '请先在 frontend 执行 pnpm install 和 pnpm build，或通过 Vite 开发服务打开界面'}
    return app
