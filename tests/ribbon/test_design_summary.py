"""The lightweight library must not materialize historical version snapshots."""
from test_workflow import env, ok

def test_summary_is_owner_scoped_without_reading_versions(env, monkeypatch):
    design = env.generate()
    full = ok(env.client.get('/api/designs'))
    assert full[0]['versions']
    def forbidden(*args):
        raise AssertionError('summary serialized a full historical snapshot')
    monkeypatch.setattr(env.service, 'version_public', forbidden)
    summary = ok(env.client.get('/api/designs?summary=true'))
    assert len(summary) == 1 and summary[0]['id'] == design['id']
    assert summary[0]['versions'] == [] and summary[0]['active_job'] is None
    assert summary[0]['current_version_id'] == design['current_version_id']
    env.login('client')
    assert ok(env.client.get('/api/designs?summary=true')) == []

def test_summary_deleted_partition_and_default_backward_compatibility(env):
    design = env.generate()
    assert ok(env.client.get('/api/designs'))[0]['versions']
    ok(env.client.delete('/api/designs/' + design['id']))
    assert ok(env.client.get('/api/designs?summary=true')) == []
    archived = ok(env.client.get('/api/designs?summary=true&deleted=true'))
    assert [d['id'] for d in archived] == [design['id']]
    assert archived[0]['versions'] == []
