"""Synthetic teaching-preview checks; no company images or paid calls."""
from io import BytesIO
import hashlib
from pathlib import Path

from PIL import Image
import pytest

from hsd_tool import ribbon_examples
from test_cloud_server import employee_app, cloud_request, login


CODE = 'HSD31620'


@pytest.fixture
def example_bytes(monkeypatch):
    stream = BytesIO()
    Image.new('RGB', (48, 16), '#8ab6c3').save(stream, 'JPEG')
    data = stream.getvalue()
    monkeypatch.setitem(ribbon_examples.IMAGE_SPECS, CODE,
                        (48, 16, len(data), hashlib.sha256(data).hexdigest()))
    return data


@pytest.fixture
def installed_example(employee_app, example_bytes):
    repository = employee_app.config['HSD_RIBBON_EXAMPLES']
    repository.directory.mkdir()
    path = repository.directory / (CODE + '.jpg')
    path.write_bytes(example_bytes)
    return repository, path


def test_catalog_covers_every_implemented_mode_without_reference_only_shortcuts(tmp_path):
    from ribbon_backend.imaging import MODES
    catalog = ribbon_examples.RibbonExamples(tmp_path / 'not-installed').catalog()
    assert {m['mode'] for m in catalog['modes']} == set(MODES)
    cases = {item['id']: item for item in catalog['examples']}
    assert len(cases) == 13
    for guide in catalog['modes']:
        assert guide['example_ids']
        assert all(guide['mode'] in cases[code]['mode_tags'] for code in guide['example_ids'])
    assert not any(item['reference_only'] for item in cases.values())
    assert all(not item['available'] and item['image_url'] is None for item in cases.values())
    assert not (tmp_path / 'not-installed').exists()


def test_only_reviewed_bytes_are_read_and_catalog_paths_stay_private(installed_example, example_bytes):
    repository, path = installed_example
    assert repository.image(CODE) == example_bytes
    catalog = repository.catalog()
    case = next(item for item in catalog['examples'] if item['id'] == CODE)
    assert case['available'] and case['width'] == 48 and case['height'] == 16
    assert case['image_url'].startswith('/api/ribbon/layout-examples/' + CODE + '/image?v=')
    assert str(repository.directory) not in repr(catalog)
    assert repository.image('../' + CODE) is None
    path.write_bytes(b'x' * len(example_bytes))
    assert repository.image(CODE) is None
    assert not next(item for item in repository.catalog()['examples'] if item['id'] == CODE)['available']


def test_missing_oversized_directory_and_unreadable_inputs_are_unavailable(installed_example, example_bytes, monkeypatch):
    repository, path = installed_example
    path.write_bytes(example_bytes + b'not an authorized extension')
    assert repository.image(CODE) is None
    path.unlink()
    path.mkdir()
    assert repository.image(CODE) is None
    path.rmdir()
    path.write_bytes(example_bytes)
    original = Path.open

    def denied(self, *args, **kwargs):
        if self == path:
            raise PermissionError('synthetic permission failure')
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, 'open', denied)
    assert repository.image(CODE) is None


def test_linked_image_or_directory_is_rejected(installed_example, monkeypatch):
    repository, path = installed_example
    original = Path.is_symlink
    monkeypatch.setattr(Path, 'is_symlink', lambda value: value == repository.directory or original(value))
    assert repository.image(CODE) is None


def test_host_auth_precedes_any_example_read(employee_app, monkeypatch):
    repository = employee_app.config['HSD_RIBBON_EXAMPLES']
    monkeypatch.setattr(repository, 'image', lambda code: pytest.fail('anonymous preview read'))
    client = employee_app.test_client()
    for path in ('/api/ribbon/layout-examples', f'/api/ribbon/layout-examples/{CODE}/image'):
        response = cloud_request(client, path, proxy_headers={'If-None-Match': '"old-preview"'})
        assert response.status_code == 401
        assert response.headers['Cache-Control'] == 'no-store'
    assert employee_app.config['HSD_RIBBON'].service is None


def test_viewing_does_not_start_worker_or_write_business_state(employee_app, installed_example, example_bytes):
    client = employee_app.test_client()
    login(client)
    manager = employee_app.config['HSD_MANAGER']
    before = set(manager.jobs)
    catalog = cloud_request(client, '/api/ribbon/layout-examples')
    assert catalog.status_code == 200
    case = next(item for item in catalog.json['examples'] if item['id'] == CODE)
    response = cloud_request(client, case['image_url'])
    assert response.status_code == 200 and response.data == example_bytes
    assert response.mimetype == 'image/jpeg'
    assert response.headers['Cache-Control'] == 'private, no-cache, must-revalidate'
    assert response.headers['Cross-Origin-Resource-Policy'] == 'same-origin'
    assert response.headers['X-Content-Type-Options'] == 'nosniff'
    assert 'Cookie' in response.headers['Vary']
    assert employee_app.config['HSD_RIBBON'].service is None
    assert set(manager.jobs) == before
    assert not (Path(manager.data_dir) / 'ribbon' / 'ribbon.sqlite3').exists()


def test_conditional_and_head_recheck_auth_and_current_bytes(employee_app, installed_example, example_bytes):
    client = employee_app.test_client()
    login(client)
    url = f'/api/ribbon/layout-examples/{CODE}/image'
    response = cloud_request(client, url)
    etag = response.headers['ETag']
    assert cloud_request(client, url, proxy_headers={'If-None-Match': etag}).status_code == 304
    head = cloud_request(client, url, method='HEAD')
    assert head.status_code == 200 and not head.data and int(head.headers['Content-Length']) == len(example_bytes)
    other = employee_app.test_client()
    assert cloud_request(other, url, proxy_headers={'If-None-Match': etag}).status_code == 401
    _, path = installed_example
    path.write_bytes(b'x' * len(example_bytes))
    denied = cloud_request(client, url, proxy_headers={'If-None-Match': etag})
    assert denied.status_code == 404 and denied.headers['Cache-Control'] == 'no-store'


@pytest.mark.parametrize('suffix,status', [
    ('/unknown/image', 404),
    ('/' + CODE + '/image?v=wrong', 404),
    ('/' + CODE + '/image?v=first&v=second', 400),
    ('/' + CODE + '/image?path=private.key', 400),
])
def test_unknown_or_modified_example_addresses_fail_closed(employee_app, installed_example, suffix, status):
    client = employee_app.test_client()
    login(client)
    response = cloud_request(client, '/api/ribbon/layout-examples' + suffix)
    assert response.status_code == status
    assert response.headers['Cache-Control'] == 'no-store'


def test_case_endpoint_has_no_upload_or_mutation_api(employee_app, installed_example):
    client = employee_app.test_client()
    login(client)
    assert cloud_request(client, '/api/ribbon/layout-examples', method='POST', payload={}, buffered=True).status_code in {404, 405}
    assert cloud_request(client, f'/api/ribbon/layout-examples/{CODE}/image',
                         method='POST', payload={}, buffered=True).status_code in {404, 405}
