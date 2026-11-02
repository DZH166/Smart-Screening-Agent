"""Actual HSD WSGI gateway: private thumbnails and current host privileges."""
from io import BytesIO
from PIL import Image

from hsd_tool import admin_auth
from test_cloud_server import employee_app, cloud_request, login, ORIGIN
from test_ribbon_gateway import call, read


def upload(client, shared=False):
    value=BytesIO();Image.new('RGBA',(800,400),'#9755AA').save(value,format='PNG');value.seek(0)
    return call(client,'/assets',method='POST',data={'kind':'pattern','shared':'true' if shared else 'false',
        'file':(value,'own.png')},content_type='multipart/form-data')


def test_gateway_preserves_only_authenticated_thumbnail_conditional_cache(employee_app):
    first=employee_app.test_client();second=employee_app.test_client();login(first);login(second)
    asset=read(upload(first));path=asset['thumbnail_url'].removeprefix('/api/ribbon')
    image=call(first,path);assert image.status_code==200
    etag=image.headers['ETag'];assert image.headers['Cache-Control']=='private, no-cache, must-revalidate';image.close()
    cached=call(first,path,proxy_headers={'If-None-Match':etag});assert cached.status_code==304
    assert cached.headers['Cache-Control']=='private, no-cache, must-revalidate';cached.close()
    assert call(second,path,proxy_headers={'If-None-Match':etag}).status_code==404
    assert call(employee_app.test_client(),path,proxy_headers={'If-None-Match':etag}).status_code==401
    original=call(first,asset['url'].removeprefix('/api/ribbon'))
    assert original.status_code==200 and original.headers['Cache-Control']=='no-store';original.close()
    for suffix in ('&other=1','&v=duplicate'):
        denied=call(first,path+suffix,proxy_headers={'If-None-Match':etag})
        assert denied.status_code==400 and denied.headers['Cache-Control']=='no-store';denied.close()


def test_host_admin_logout_immediately_revokes_shared_upload_and_admin_routes(employee_app, monkeypatch):
    monkeypatch.setattr(admin_auth,'verify_credentials',lambda username,password:(username,password)==('synthetic-admin','synthetic-password'))
    client=employee_app.test_client();login(client)
    response=cloud_request(client,'/admin/login',method='POST',payload={'username':'synthetic-admin','password':'synthetic-password'})
    assert response.status_code==200;response.close()
    assert read(call(client,'/auth/me'))['role']=='admin'
    read(upload(client,shared=True))
    response=cloud_request(client,'/admin/logout',method='POST',payload={})
    assert response.status_code==200;response.close()
    assert read(call(client,'/auth/me'))['role']=='customer'
    assert call(client,'/admin/overview').status_code in (401,403)
    denied=upload(client,shared=True);assert denied.status_code==403;denied.close()
