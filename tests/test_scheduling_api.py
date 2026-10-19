"""Shutdown and admin busy guards during narrow per-task operations."""
import pytest

from test_admin_api import admin_app, call


@pytest.mark.parametrize('path,payload', [
    ('/api/admin/keys', {'expected_revision': 0, 'add': []}),
    ('/api/ai/settings', {'enabled': False}),
    ('/api/jobs', {}),
])
def test_shutdown_stops_new_mutations_before_grace_timer_exits(admin_app, path, payload):
    admin_app.config['HSD_STOPPING'] = True
    response = call(admin_app.test_client(), path, method='POST', payload=payload)
    assert response.status_code == 409
    assert '退出' in response.get_json()['error']


@pytest.mark.parametrize('path,payload', [
    ('/api/admin/keys', {'expected_revision': 0, 'add': []}),
    ('/api/ai/settings', {'enabled': False}),
])
def test_ready_task_plan_operation_prevents_admin_setting_changes(admin_app, path, payload):
    manager = admin_app.config['HSD_MANAGER']
    manager.jobs['test-plan'] = {'status': 'ready'}
    before = manager.ai_settings.snapshot()
    with manager.job_operation('test-plan'):
        response = call(admin_app.test_client(), path, method='POST', payload=payload)
        assert response.status_code == 400
        assert '处理' in response.get_json()['error']
    assert manager.ai_settings.snapshot() == before
