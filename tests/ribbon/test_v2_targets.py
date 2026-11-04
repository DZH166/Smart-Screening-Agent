"""Exercise employee-selected edit targets through HTTP, the worker and saved native PNGs."""

from io import BytesIO
from uuid import uuid4

from PIL import Image
import pytest

from test_loop_workflow import workflow, current, ok, png


def edit(workflow, design, target, operation):
    workflow.provider.operations = [operation]
    job = ok(
        workflow.client.post(
            f'/api/designs/{design["id"]}/refinements',
            json={
                'idempotency_key': str(uuid4()),
                'base_version_id': design['current_version_id'],
                'prompt': 'Explicit test request',
                'edit_target': target,
            },
        )
    )
    return workflow.work(job), workflow.get(design)


def sample(workflow, design):
    return current(design)['snapshot']


def test_target_signed_translation_and_wrong_asset_cannot_change_neighbor(workflow):
    original = workflow.generate({**workflow.selection, 'template_id': 'grid'})
    first = sample(workflow, original)
    target = first['pattern_slots'][0]
    failed, unchanged = edit(
        workflow,
        original,
        target,
        {'type': 'edit_asset', 'asset_id': first['asset_refs'][1], 'prompt': 'Change another slot'},
    )
    assert failed['status'] == 'FAILED'
    assert (
        unchanged['current_version_id'] == original['current_version_id'] and not workflow.provider.edit_calls
    )
    done, after = edit(workflow, original, target, {'type': 'parameters', 'values': {'offset_x': -4}})
    assert done['status'] == 'SUCCEEDED', done
    newer = sample(workflow, after)
    assert len(set(p['row'] for p in newer['object_transforms'] if p['slot_id'] == target)) > 1
    for old, new in zip(first['object_transforms'], newer['object_transforms']):
        assert old['y'] == new['y']
        assert new['x'] - old['x'] == pytest.approx(-4 if old['slot_id'] == target else 0)
    assert after['successful_refinement_count'] == 1
    fail, latest = edit(workflow, after, target, {'type': 'parameters', 'values': {'offset_x': -4}})
    assert fail['status'] == 'FAILED' and latest['successful_refinement_count'] == 1
    assert latest['current_version_id'] == after['current_version_id']


def test_one_asset_edit_replaces_all_selected_copies_and_preserves_source(workflow):
    initial = workflow.generate({**workflow.selection, 'template_id': 'stagger'})
    base = sample(workflow, initial)
    target, source = base['pattern_slots'][1], base['asset_refs'][1]
    before = workflow.download(current(initial))
    workflow.provider.edit_size = (200, 140)
    done, after = edit(
        workflow, initial, target, {'type': 'edit_asset', 'asset_id': source, 'prompt': 'Selected only'}
    )
    assert done['status'] == 'SUCCEEDED', done
    changed = sample(workflow, after)
    assert changed['pattern_slots'] == base['pattern_slots']
    assert changed['asset_refs'][1] != source
    assert changed['asset_refs'][::2] == base['asset_refs'][::2]
    copies = [p for p in changed['object_transforms'] if p['slot_id'] == target]
    assert len(copies) >= 2 and {p['asset_ref'] for p in copies} == {changed['asset_refs'][1]}
    assert len(workflow.provider.edit_calls) == 1 and workflow.download(current(initial)) == before


def test_chosen_zone_solid_colour_then_content_edit_preserves_other_zone(workflow):
    second = workflow.upload(png((140, 110), '#24558a', pattern=False), 'Right blue', 'background')
    left = workflow.background['id']
    initial = workflow.generate(
        {
            **workflow.selection,
            'template_id': 'split',
            'zone_background_refs': {'left': left, 'right': second['id']},
        }
    )
    done, colored = edit(
        workflow, initial, 'zone:left', {'type': 'parameters', 'values': {'background_color': '#7043B2'}}
    )
    assert done['status'] == 'SUCCEEDED', done

    def edges(design):
        with Image.open(BytesIO(workflow.download(current(design)))) as im:
            return im.getpixel((1, 1))[:3], im.getpixel((im.width - 1, 1))[:3]

    assert edges(colored) == ((112, 67, 178), (36, 85, 138))
    workflow.provider.edit_size = (320, 200)
    done, changed = edit(
        workflow, colored, 'zone:left', {'type': 'edit_background', 'prompt': 'Change the zone texture'}
    )
    assert done['status'] == 'SUCCEEDED', done
    s = sample(workflow, changed)
    assert 'left' not in s['zone_colors']
    assert s['zone_background_refs']['left'] != left and s['zone_background_refs']['right'] == second['id']
    assert edges(changed)[1] == edges(colored)[1]
    with Image.open(BytesIO(workflow.provider.edit_calls[0]['source'])) as visible:
        assert visible.getpixel((0, 0))[:3] == (112, 67, 178)
    assert changed['successful_refinement_count'] == 2


def test_edit_shared_asset_when_it_is_selected_as_strip_only(workflow):
    source = workflow.patterns[0]['id']
    initial = workflow.generate({**workflow.selection, 'template_id': 'bordered', 'border_ref': source})
    base = sample(workflow, initial)
    workflow.provider.edit_size = (310, 96)
    done, changed = edit(
        workflow, initial, 'border', {'type': 'edit_asset', 'asset_id': source, 'prompt': 'Strip only'}
    )
    assert done['status'] == 'SUCCEEDED', done
    s = sample(workflow, changed)
    assert s['asset_refs'] == base['asset_refs'] and s['border_ref'] != source
    assert s['loop']['background']['border']['source'] == s['border_ref']
    assert s['pattern_slots'] == base['pattern_slots'] and len(workflow.provider.edit_calls) == 1


def test_expired_target_fails_before_planner_and_does_not_charge(workflow):
    initial = workflow.generate()
    fail, same = edit(
        workflow, initial, 'pattern-wrong-slot', {'type': 'parameters', 'values': {'scale': 0.7}}
    )
    assert fail['status'] == 'FAILED' and same['successful_refinement_count'] == 0
    assert same['current_version_id'] == initial['current_version_id']
    assert not workflow.provider.plan_calls and not workflow.provider.edit_calls


@pytest.mark.parametrize('new_mode', ['split', 'single'])
def test_zone_colour_is_cleared_when_source_or_layout_changes(workflow, new_mode):
    second = workflow.upload(png((100, 110), '#24558a', pattern=False), 'Blue', 'background')
    selection = {
        **workflow.selection,
        'template_id': 'split',
        'zone_background_refs': {'left': workflow.background['id'], 'right': second['id']},
    }
    initial = workflow.generate(selection)
    done, colored = edit(
        workflow, initial, 'zone:left', {'type': 'parameters', 'values': {'background_color': '#7043B2'}}
    )
    assert done['status'] == 'SUCCEEDED', done
    replacement = {
        **selection,
        'template_id': new_mode,
        'zone_background_refs': {'left': second['id'], 'right': second['id']} if new_mode == 'split' else {},
    }
    done, changed = workflow.refine(colored, selection=replacement, prompt='应用所选配置')
    assert done['status'] == 'SUCCEEDED', done
    assert 'left' not in sample(workflow, changed)['zone_colors']
    assert changed['successful_refinement_count'] == 2
    if new_mode == 'split':
        with Image.open(BytesIO(workflow.download(current(changed)))) as im:
            assert im.getpixel((1, 1))[:3] == (36, 85, 138)
