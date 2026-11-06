"""Cross-branch backend compatibility with local synthetic data only."""
from copy import deepcopy
import json

import pytest

from hsd_tool.provider_diagnostics import diagnostic
from ribbon_backend import loop_pipeline_v3
from ribbon_backend.providers import ProviderError
from test_call_diagnostics import work
from test_loop_workflow import current, ok, workflow
from test_request_contract_workflow import parameter, submit_plan, wire


def test_v3_trial_retains_main_progressive_preview_and_cache_without_versions(workflow):
    body = {**workflow.selection, 'style': 'airy'}
    first = ok(workflow.client.post('/api/candidates/one', json=body))
    second = ok(workflow.client.post('/api/candidates/one', json=body))
    assert first['style'] == 'airy' and first['rhythm']['unit_width'] > 0
    assert first['image'] == second['image'] and second['cached'] is True
    with workflow.service.db.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM versions').fetchone()[0] == 0
        assert db.execute('SELECT COUNT(*) FROM provider_calls').fetchone()[0] == 0


def test_v3_quiet_background_and_rhythm_survive_merge(workflow):
    initial = workflow.generate({**workflow.selection, 'background_tone': 'quiet', 'design_style': 'airy'})
    snapshot = current(initial)['snapshot']
    assert snapshot['layout_engine'] == 'seamless-unit-v3'
    assert snapshot['design_style'] == 'airy'
    assert snapshot['loop']['rhythm']['unit_width'] > 0
    resolve = lambda asset: workflow.service.verified_asset_path(workflow.owner, asset)
    quiet, _ = loop_pipeline_v3._make_background(snapshot, resolve)
    original = deepcopy(snapshot)
    original['background_tone'] = 'original'
    base, _ = loop_pipeline_v3._make_background(original, resolve)
    try:
        assert all(quiet.getpixel((0, 0))[i] > base.getpixel((0, 0))[i] for i in range(3))
    finally:
        quiet.close()
        base.close()


def test_v3_valid_refinement_keeps_original_binding_but_not_v2_physical_claim(workflow):
    before = workflow.generate()
    prompt = '图案缩小20%'
    plan = wire(prompt, ['parameters'], [parameter(prompt, 'scale', .8, mode='percent', amount=20, direction='decrease')])
    done, after, _ = submit_plan(workflow, before, prompt, plan)
    assert done['status'] == 'SUCCEEDED', done
    snapshot = current(after)['snapshot']
    assert snapshot['params']['scale'] == .8 and snapshot['layout_engine'] == 'seamless-unit-v3'
    assert snapshot['edit_plan']['request_receipt']['requirements'][0]['execution'] == 'parameters_applied_unverified'
    assert after['successful_refinement_count'] == 1


@pytest.mark.parametrize('final', ['success', 'unknown'])
def test_output_retry_has_two_durable_request_records_before_second_dispatch(work, tmp_path, monkeypatch, final):
    service, _, job, provider = work
    attempts = []
    def once(*args, **kwargs):
        attempts.append(1)
        if len(attempts) == 1:
            raise ProviderError('settled output block', request_id='first-request', usage={'generated_images': 1},
                                details=diagnostic('output_policy', 'provider'))
        with service.db.connect() as db:
            rows = list(db.execute('SELECT status,request_id FROM provider_calls ORDER BY rowid'))
        assert [(row['status'], row['request_id']) for row in rows] == [('FAILED', 'first-request'), ('STARTED', None)]
        if final == 'unknown':
            raise ProviderError('second unknown', request_id='second-request', usage={'generated_images': 2}, uncertain_result=True)
        return {'request_id': 'second-request', 'usage': {'generated_images': 2}}
    monkeypatch.setattr(provider, '_image_once', once)
    call = lambda: service.call_provider(job, 'generate_background', lambda: provider._image({}, tmp_path/'out.png'), retry_provider=provider)
    if final == 'unknown':
        with pytest.raises(ProviderError):
            call()
    else:
        call()
    with service.db.connect() as db:
        rows = [dict(row) for row in db.execute('SELECT * FROM provider_calls ORDER BY rowid')]
    assert len(attempts) == len(rows) == 2
    assert [row['request_id'] for row in rows] == ['first-request', 'second-request']
    assert [json.loads(row['usage_json'])['generated_images'] for row in rows] == [1, 2]
    assert [row['status'] for row in rows] == ['FAILED', 'UNKNOWN' if final == 'unknown' else 'SUCCEEDED']
    assert provider._image_retry_hook is None


def test_unknown_output_category_is_not_retried(work, tmp_path, monkeypatch):
    service, _, job, provider = work
    attempts = []
    def once(*args, **kwargs):
        attempts.append(1)
        raise ProviderError('unknown', uncertain_result=True, details=diagnostic('output_policy', 'provider'))
    monkeypatch.setattr(provider, '_image_once', once)
    with pytest.raises(ProviderError):
        service.call_provider(job, 'generate_background', lambda: provider._image({}, tmp_path/'out.png'), retry_provider=provider)
    with service.db.connect() as db:
        rows = list(db.execute('SELECT status FROM provider_calls'))
    assert len(attempts) == len(rows) == 1 and rows[0]['status'] == 'UNKNOWN'


def test_existing_style_only_change_has_real_output_and_repeat_is_free_noop(workflow):
    before = workflow.generate()
    old = current(before)
    original = workflow.download(old)
    selection = {**workflow.selection, 'design_style': 'hierarchy'}
    done, after = workflow.refine(before, selection=selection, prompt='应用所选配置')
    assert done['status'] == 'SUCCEEDED', done
    snapshot = current(after)['snapshot']
    assert snapshot['design_style'] == 'hierarchy'
    assert snapshot['params']['spacing'] == pytest.approx(1.08)
    scales = [snapshot['slot_params'][slot]['scale'] for slot in snapshot['pattern_slots']]
    assert scales == pytest.approx([1.24, .78, .78])
    assert workflow.download(old) == original
    assert workflow.download(current(after)) != original
    assert after['successful_refinement_count'] == 1
    same = {**selection, 'background_tone': snapshot['background_tone'], 'design_density': snapshot['design_density']}
    failed, unchanged = workflow.refine(after, selection=same, prompt='应用所选配置')
    assert failed['status'] == 'FAILED'
    assert unchanged['successful_refinement_count'] == 1
    assert unchanged['current_version_id'] == after['current_version_id']
    assert not workflow.provider.plan_calls and not workflow.provider.edit_calls


def test_style_label_without_pixel_change_cannot_consume_a_refinement(workflow):
    selection = {**workflow.selection, 'asset_ids': workflow.selection['asset_ids'][:1], 'background_tone': 'quiet'}
    before = workflow.generate(selection)
    original = workflow.download(current(before))
    done, after = workflow.refine(before, selection={**selection, 'design_style': 'rhythm'}, prompt='应用所选配置')
    assert done['status'] == 'FAILED' and '像素相同' in done['error']
    assert after['successful_refinement_count'] == 0
    assert after['current_version_id'] == before['current_version_id']
    assert workflow.download(current(after)) == original


def test_existing_v2_trial_keeps_parent_engine_profile_and_scope(workflow, monkeypatch):
    import ribbon_backend.loop_pipeline_v3 as v3
    create = workflow.service.selection_snapshot
    def historical(db, owner, selection, profile=None, base=None):
        result = create(db, owner, selection, profile, base)
        if base is None:
            result['layout_engine'] = 'seamless-unit-v2'
            result.pop('pattern_roles', None)
        return result
    with monkeypatch.context() as patch:
        patch.setattr(workflow.service, 'selection_snapshot', historical)
        before = workflow.generate()
    parent = current(before)
    original = workflow.download(parent)
    workflow.service.save_profile(dict(name='New unrelated active profile', width=1800, height=360,
                                      dpi=144, format='PNG', is_demo=True))
    monkeypatch.setattr(v3, 'resolve', lambda *args, **kwargs: pytest.fail('An existing v2 work must not preview v3'))
    trial = ok(workflow.client.post(f'/api/designs/{before["id"]}/candidates/one',
                                   json={**workflow.selection, 'style': 'airy'}))
    assert trial['engine'] == 'seamless-unit-v2'
    assert trial['height'] == parent['snapshot']['output_profile']['height'] == 240
    after = workflow.get(before)
    assert len(after['versions']) == 1 and after['successful_refinement_count'] == 0
    assert workflow.download(parent) == original
    assert not workflow.provider.plan_calls and not workflow.provider.edit_calls
