"""Synthetic upload/recycle integration through authenticated HSD WSGI routes."""
from io import BytesIO

from PIL import Image

from test_cloud_server import employee_app, login
from test_ribbon_gateway import call, read


def upload(client):
    image = BytesIO()
    with Image.new('RGBA', (48, 24), '#61a58f') as source:
        source.save(image, format='PNG')
    image.seek(0)
    return read(call(client, '/assets', method='POST', data={'kind': 'pattern', 'file': (image, 'synthetic.png')},
                     content_type='multipart/form-data'))


def test_gateway_dedupe_recycle_and_csrf_preserve_browser_ownership(employee_app):
    first, second = employee_app.test_client(), employee_app.test_client()
    login(first); login(second)
    asset = upload(first)
    assert upload(first)['id'] == asset['id']
    assert upload(second)['id'] != asset['id']
    work = read(call(first, '/designs', {'name': 'synthetic recoverable work'}))
    path = '/designs/' + work['id']
    for kwargs in ({'token': None}, {'origin': 'https://untrusted.example.test'}):
        denied = call(first, path, method='DELETE', **kwargs)
        assert denied.status_code == 403
        denied.close()
    assert read(call(first, path, method='DELETE'))['ok']
    assert read(call(first, '/designs')) == []
    assert read(call(first, '/designs?deleted=true'))[0]['id'] == work['id']
    assert read(call(second, '/designs?deleted=true')) == []
    for method, suffix in (('DELETE', ''), ('POST', '/restore')):
        denied = call(second, path + suffix, {}) if method == 'POST' else call(second, path + suffix, method=method)
        assert denied.status_code == 404
        denied.close()
    denied = call(first, path + '/restore', {}, token=None)
    assert denied.status_code == 403
    denied.close()
    restored = read(call(first, path + '/restore', {}))
    assert restored['deleted_at'] is None and restored['id'] == work['id']
    assert read(call(first, '/designs'))[0]['id'] == work['id']
