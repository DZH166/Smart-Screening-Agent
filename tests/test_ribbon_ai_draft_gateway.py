"""Real HSD gateway wiring with a self-made reference and explicit provider substitute."""
from dataclasses import replace
from io import BytesIO
import hashlib

from PIL import Image

from hsd_tool import ribbon_examples
from test_cloud_server import employee_app, login
from test_ribbon_gateway import call, read, selection, wait_job


def test_hsd_ai_draft_uses_only_explicit_installed_matching_reference(employee_app, monkeypatch):
    first, second = employee_app.test_client(), employee_app.test_client()
    login(first); login(second)
    read(call(first, '/auth/me'))
    service = employee_app.config['HSD_RIBBON'].service
    runtime = replace(service.settings, provider='deepseek_seedream', enabled=True,
                      language_model='synthetic-language', image_model='synthetic-image',
                      deepseek_pool=object(), ark_key='synthetic-only-not-a-credential')
    service.runtime_settings_supplier = lambda: runtime
    service.save_profile(dict(name='Synthetic gateway AI draft', width=1080, height=240, dpi=96, format='PNG', is_demo=True))
    reference = BytesIO()
    with Image.new('RGB', (48, 24), '#9cba89') as image:
        image.save(reference, format='JPEG')
    value = reference.getvalue(); code = 'HSD68145'
    monkeypatch.setitem(ribbon_examples.IMAGE_SPECS, code, (48, 24, len(value), hashlib.sha256(value).hexdigest()))
    directory = employee_app.config['HSD_MANAGER'].ai_settings.path.parent / 'ribbon_layout_examples'
    directory.mkdir(parents=True)
    (directory / f'{code}.jpg').write_bytes(value)
    calls = []

    class SyntheticGatewayProvider:
        name = 'deepseek_seedream'

        def generate_draft_background(self, patterns, background, reference_bytes, output, **options):
            calls.append((reference_bytes, options))
            with Image.new('RGBA', (2048, 2048), '#e2e9dc') as image:
                image.save(output, format='PNG', dpi=(144, 144))
            return dict(model='synthetic-only', request_id='synthetic-gateway-ai-draft')

    service.provider_factory = lambda *args: SyntheticGatewayProvider()
    assert read(call(first, '/config'))['ai_draft_available'] is True
    catalog = read(call(first, '/layout-examples'))
    assert next(row for row in catalog['examples'] if row['code'] == code)['available']
    assert calls == []
    work = read(call(first, '/designs', {'name': 'Synthetic gateway first draft'}))
    selected = {**selection(first), 'template_id': 'grid'}
    body = dict(selected, idempotency_key='synthetic-installed-case-ai-draft', ai_assisted=True, reference_code=code)
    job = read(call(first, f'/designs/{work["id"]}/generate', body))
    assert read(call(first, f'/designs/{work["id"]}/generate', body))['id'] == job['id']
    settled = wait_job(first, job)
    assert settled['status'] == 'SUCCEEDED', settled
    assert calls == [(value, dict(mode='grid', density='balanced', prompt=''))]
    saved = read(call(first, '/designs/' + work['id']))
    snapshot = saved['versions'][0]['snapshot']
    assert saved['successful_refinement_count'] == 0 and snapshot['asset_refs'] == selected['asset_ids']
    assert snapshot['ai_draft']['reference_sha256'] == hashlib.sha256(value).hexdigest()
    denied = call(second, '/designs/' + work['id'])
    assert denied.status_code == 404
    denied.close()
    version = saved['versions'][0]
    download = call(first, version['download_url'].removeprefix('/api/ribbon'))
    try:
        assert download.status_code == 200
        assert download.data == service.version_file(read(call(first, '/auth/me'))['id'], version['id']).read_bytes()
    finally:
        download.close()
