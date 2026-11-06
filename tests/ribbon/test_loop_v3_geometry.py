"""Free-field composition contracts, including actual raster and legacy pixels."""
from copy import deepcopy
import math
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw
import pytest

from ribbon_backend import loop_layout_v2 as v2, loop_layout_v3 as v3


def snapshot(mode='scatter', density='balanced', n=6, seed=32, **updates):
    return dict(layout_engine=v3.ENGINE, template_mode=mode,
                asset_refs=[str(i) for i in range(n)], background_ref='bg',
                template_rules={}, seed=seed, design_density=density, params={},
                output_profile=dict(width=11811, height=520, dpi=300, format='PNG'), **updates)


def shapes(n=6):
    return [dict(width=w,height=h) for w,h in
            ([(100,180),(300,90),(130,140),(80,120),(200,100),(120,200)]*n)[:n]]


def resolve(n=6, **kwargs):
    return v3.resolve(snapshot(n=n, **kwargs), specs=shapes(n))


def assert_separation(placements, width):
    for i,a in enumerate(placements):
        assert a['y'] - a['planned_height']/2 >= a['region'][1] - 1e-7
        assert a['y'] + a['planned_height']/2 <= a['region'][3] + 1e-7
        for b in placements[:i]:
            dx=abs(a['x']-b['x']); dx=min(dx,width-dx)
            dy=abs(a['y']-b['y'])
            assert (dx >= (a['planned_width']+b['planned_width'])/2+1-1e-7 or
                    dy >= (a['planned_height']+b['planned_height'])/2+1-1e-7)


@pytest.mark.parametrize('n',[1,2,3,6,12])
@pytest.mark.parametrize('seed',[1,32,77])
def test_density_seed_coverage_and_full_field_circular_clearance(n,seed):
    results=[resolve(n=n,seed=seed,density=d) for d in ('airy','balanced','rich')]
    cover=[r['loop_layout']['metrics']['footprint_ratio'] for r in results]
    assert cover[0] < cover[1] < cover[2]
    for r in results:
        p=v3.plan(r)
        assert p == v3.plan(r)
        assert {q['asset_index'] for q in p}==set(range(n))
        assert {q['rotation'] for q in p}=={-18.,-9.,9.,18.}
        assert r['loop_layout']['metrics']['arrangement']=='free_2d'
        assert r['loop_layout']['metrics']['row_count']==0
        assert len({round(q['y'],2) for q in p}) >= len(p)-1
        assert_separation(p,r['output_profile']['width'])
        # Default unit contains every complete rotated figure, not clipped ends.
        assert all(q['x']-q['planned_width']/2 >= 0 for q in p)
        assert all(q['x']+q['planned_width']/2 <= r['output_profile']['width'] for q in p)


def test_free_scatter_can_place_in_middle_of_former_lane_boundary():
    r=resolve(seed=32)
    p=v3.plan(r)
    # A row-based algorithm keeps complete figures on one side of y=260.
    assert any(q['y']-q['planned_height']/2 <260<q['y']+q['planned_height']/2 for q in p)
    assert v3.plan(resolve(seed=33)) != p


@pytest.mark.parametrize('n',[1,3,12])
def test_spacing_expands_actual_distances_without_rearranging_axes(n):
    states=[]
    for spacing in (.25,.8,1.,1.25,2.5):
        s=snapshot(n=n);s['params']={'spacing':spacing}
        states.append(v3.resolve(s,specs=shapes(n)))
    widths=[s['output_profile']['width'] for s in states]
    assert widths==sorted(set(widths))
    gaps=[s['loop_layout']['metrics']['mean_gap_px'] for s in states]
    assert all(a<b for a,b in zip(gaps,gaps[1:]))
    previous=v3.plan(states[0])
    for state in states[1:]:
        p=v3.plan(state)
        for before,after in zip(previous,p):
            assert before['y']==after['y']
            assert before['rotation']==after['rotation']
            assert before['target_width']==after['target_width']
            assert after['x'] > before['x']
        previous=p


def test_targeted_resize_or_translation_preserves_other_slots():
    base=resolve();p=v3.plan(base)
    for change in ({'scale':.8},{'offset_x':2.},{'offset_x':-2.}):
        changed=deepcopy(base);changed['slot_params']={'pattern-2':change}
        after=v3.resolve(changed,specs=shapes())
        q=v3.plan(after)
        assert base['output_profile']==after['output_profile']
        for a,b in zip(p,q):
            if a['slot_id']!='pattern-2':
                assert {k:v for k,v in a.items() if k!='repetition'}=={k:v for k,v in b.items() if k!='repetition'}
            elif 'scale' in change:
                assert b['target_width']<a['target_width']
                assert b['x']==a['x'] and b['y']==a['y']
            else:
                assert b['x']-a['x']==pytest.approx(change['offset_x'])


def test_targeted_overlap_or_vertical_clipping_is_rejected():
    base=resolve();p=v3.plan(base)
    selected=p[0];other=next(q for q in p if q['slot_id']!=selected['slot_id'])
    collision=deepcopy(base)
    collision['slot_params']={selected['slot_id']:{'offset_x':other['x']-selected['x'],
                                                  'offset_y':other['y']-selected['y']}}
    with pytest.raises(ValueError,match='重叠|边界'):
        v3.resolve(collision,specs=shapes())
    outside=deepcopy(base);outside['slot_params']={selected['slot_id']:{'offset_y':520}}
    with pytest.raises(ValueError,match='边界'):
        v3.resolve(outside,specs=shapes())


@pytest.mark.parametrize('tamper', ['asset_refs','background_ref','seed','params','geometry'])
def test_saved_v3_signature_detects_changed_source_and_geometry(tamper):
    saved=resolve();changed=deepcopy(saved)
    if tamper=='asset_refs':changed['asset_refs'][0]='other'
    elif tamper=='background_ref':changed['background_ref']='other'
    elif tamper=='seed':changed['seed']+=1
    elif tamper=='params':changed['params']['spacing']=1.4
    else:changed['loop_layout']['metrics']['placements']+=1
    with pytest.raises(ValueError,match='保存的排法'):
        v3.plan(changed)


@pytest.fixture
def artwork(tmp_path):
    refs={}
    for i,(w,h) in enumerate([(80,140),(240,90),(130,150)]):
        path=tmp_path/(str(i)+'.png')
        with Image.new('RGBA',(w,h)) as im:
            d=ImageDraw.Draw(im)
            d.polygon([(4,h-4),(w-4,h-4),(w-4,h//2),(w//2,4)],fill=('red','green','blue')[i])
            d.rectangle((w//3,h//3,w//3+5,h//3+5),fill='yellow')
            im.save(path)
        refs[str(i)]=path
    return refs


def draw(engine,state,refs,destination):
    destination=Path(destination);destination.parent.mkdir(parents=True,exist_ok=True)
    with Image.new('RGBA',(state['output_profile']['width'],state['output_profile']['height'])) as canvas:
        transforms=engine.compose(canvas,state,refs.__getitem__,destination)
        canvas.save(destination)
    return transforms


def test_real_alpha_pixels_are_complete_and_wrap_by_exact_integer_shift(artwork,tmp_path):
    base=v3.resolve(snapshot(n=3),artwork.__getitem__)
    draw(v3,base,artwork,tmp_path/'base.png')
    changed=deepcopy(base);changed['params']['offset_x']=133
    changed=v3.resolve(changed,artwork.__getitem__)
    draw(v3,changed,artwork,tmp_path/'shifted.png')
    with Image.open(tmp_path/'base.png') as a,Image.open(tmp_path/'shifted.png') as b:
        with ImageChops.offset(a,133,0) as shifted:
            assert shifted.tobytes()==b.tobytes()
        # No alpha is lost at the seam or top/bottom when offsets wrap.
        assert sum(a.getchannel('A').getdata())==sum(b.getchannel('A').getdata())
    p=v3.plan(base)
    expected=0
    for q in p:
        spec=base['loop_layout']['specs'][q['asset_index']]
        with Image.open(artwork[str(q['asset_index'])]) as source:
            cropped=source.crop(spec['bbox'])
            fitted=cropped.resize((q['target_width'],q['target_height']),Image.Resampling.LANCZOS)
            turned=fitted.rotate(-q['rotation'],resample=Image.Resampling.BICUBIC,expand=True)
            expected+=sum(turned.getchannel('A').getdata())
            cropped.close();fitted.close();turned.close()
    with Image.open(tmp_path/'base.png') as result:
        assert sum(result.getchannel('A').getdata())==expected


@pytest.mark.parametrize('mode',[m for m in v2.MODES if m not in ('scatter','scene','bordered','split','panels','stacked')])
def test_unmodified_modes_delegate_without_changing_existing_v2_pixels(mode,artwork,tmp_path):
    n=1 if mode=='fullwidth' else 2 if mode=='ends_open' else 3
    old=snapshot(mode=mode,n=n);old['layout_engine']=v2.ENGINE
    old=v2.resolve(old,artwork.__getitem__)
    new={**old,'layout_engine':v3.ENGINE};new=v3.resolve(new,artwork.__getitem__)
    a=tmp_path/(mode+'-v2.png');b=tmp_path/(mode+'-v3.png')
    draw(v2,old,artwork,a);draw(v3,new,artwork,b)
    assert a.read_bytes()==b.read_bytes()
    assert old['loop_layout']['engine']==v2.ENGINE
    assert new['loop_layout']['engine']==v3.ENGINE
    assert old['loop_layout']['input_signature']!=new['loop_layout']['input_signature']


def test_rejects_old_engine_and_excessive_output_dimensions():
    s=snapshot();s['layout_engine']=v2.ENGINE
    with pytest.raises(ValueError,match='新作品'):v3.resolve(s,specs=shapes())
    s=snapshot();s['params']['spacing']=100000
    with pytest.raises(ValueError):v3.resolve(s,specs=shapes())


@pytest.mark.parametrize('mode',['scene','scatter','bordered'])
def test_explicit_roles_reject_unknown_slots_invalid_roles_and_no_main(mode):
    base=snapshot(mode=mode,n=3)
    invalid=[{'missing':'main'}, {'pattern-1':'invented'},
             {f'pattern-{i+1}':('border' if mode=='bordered' else 'accent') for i in range(3)}]
    for roles in invalid:
        with pytest.raises(ValueError,match='角色|主体'):
            v3.resolve({**base,'pattern_roles':roles},specs=shapes(3))
    with pytest.raises(ValueError,match='角色'):
        v3.resolve({**snapshot(mode='single',n=3),'pattern_roles':{'pattern-1':'main'}},specs=shapes(3))


def test_scene_roles_create_complete_grounded_group_with_free_accents():
    roles={'pattern-1':'main','pattern-2':'main','pattern-3':'support',
           'pattern-4':'support','pattern-5':'accent','pattern-6':'accent'}
    s=snapshot(mode='scene',n=6)
    r=v3.resolve({**s,'pattern_roles':roles},specs=[dict(width=120,height=180)]*6)
    p=v3.plan(r);assert {q['asset_index'] for q in p}==set(range(6))
    main=[q for q in p if q['role']=='main'];support=[q for q in p if q['role']=='support']
    accents=[q for q in p if q['role']=='accent']
    assert all(q['target_height']<min(a['target_height'] for a in main)*.67 for q in support)
    assert all(q['target_height']<min(a['target_height'] for a in main)*.27 for q in accents)
    assert len({round(q['y']+q['planned_height']/2,5) for q in main+support})==1
    assert any(q['y'] < min(a['y'] for a in main+support) for q in accents)
    assert_separation(p,r['output_profile']['width'])
    tampered=deepcopy(r);tampered['pattern_roles']['pattern-6']='support'
    with pytest.raises(ValueError,match='保存的排法'):v3.plan(tampered)


def test_scatter_accents_really_are_small_and_fill_the_same_field():
    roles={f'pattern-{i+1}':('main' if i<2 else 'accent') for i in range(6)}
    r=v3.resolve({**snapshot(n=6),'pattern_roles':roles},specs=[dict(width=120,height=160)]*6)
    p=v3.plan(r);main=[q for q in p if q['role']=='main'];accent=[q for q in p if q['role']=='accent']
    assert max(q['planned_height'] for q in accent)<min(q['planned_height'] for q in main)*.48
    assert {q['asset_index'] for q in p}==set(range(6))
    assert_separation(p,r['output_profile']['width'])


def test_bordered_never_turns_unassigned_characters_into_tiny_edge_decoration():
    base=v3.resolve(snapshot(mode='bordered',n=6),specs=[dict(width=120,height=180)]*6)
    p=v3.plan(base)
    assert {q['role'] for q in p}=={'main'}
    assert len({q['target_height'] for q in p})==1
    explicit={**snapshot(mode='bordered',n=6), 'pattern_roles':
              {f'pattern-{i+1}':('main' if i<4 else 'border') for i in range(6)}}
    r=v3.resolve(explicit,specs=[dict(width=120,height=180)]*6);p=v3.plan(r)
    assert {q['asset_index'] for q in p if q['role']=='main'}=={0,1,2,3}
    for side in ('top-border','bottom-border'):
        assert {q['asset_index'] for q in p if q['role']==side}=={4,5}
    assert max(q['target_height'] for q in p if q['role']!='main') < min(
        q['target_height'] for q in p if q['role']=='main')*.3
    assert_separation(p,r['output_profile']['width'])


@pytest.mark.parametrize('mode',['split','panels','stacked'])
@pytest.mark.parametrize('n',[2,3,6,7,12])
def test_partition_regions_have_equal_rows_and_motif_height(mode,n):
    r=v3.resolve(snapshot(mode=mode,n=n),specs=[dict(width=120,height=180)]*n)
    p=v3.plan(r)
    assert len({q['target_height'] for q in p})<=2 # integer half-height rounding
    assert max(q['target_height'] for q in p)-min(q['target_height'] for q in p)<=1
    assert {q['asset_index'] for q in p}==set(range(n))
    assert len(r['loop_layout']['groups'])==(3 if mode=='panels' else 2)
    assert_separation(p,r['output_profile']['width'])
    for q in p:
        if mode!='stacked':
            assert q['x']-q['planned_width']/2>=q['region'][0]-1e-7
            assert q['x']+q['planned_width']/2<=q['region'][2]+1e-7


@pytest.mark.parametrize('mode',['scene','bordered','split','panels','stacked'])
def test_new_structures_density_and_spacing_have_real_direction(mode):
    s=snapshot(mode=mode,n=6)
    if mode=='scene':s['pattern_roles']={'pattern-5':'accent','pattern-6':'accent'}
    covered=[v3.resolve({**s,'design_density':d},specs=shapes())['loop_layout']['metrics']['footprint_ratio']
             for d in ('airy','balanced','rich')]
    assert covered[0]<covered[1]<covered[2]
    sizes=[v3.resolve({**s,'params':{'spacing':x}},specs=shapes())['output_profile']['width'] for x in (.5,1.,1.5)]
    assert sizes[0]<sizes[1]<sizes[2]


@pytest.mark.parametrize('mode',['scene','bordered','split','panels','stacked'])
def test_complete_actual_alpha_preserved_in_new_structures(mode,artwork,tmp_path):
    s=snapshot(mode=mode,n=3)
    if mode=='scene':s['pattern_roles']={'pattern-3':'accent'}
    elif mode=='bordered':s['pattern_roles']={'pattern-3':'border'}
    state=v3.resolve(s,artwork.__getitem__)
    path=tmp_path/(mode+'-actual.png');draw(v3,state,artwork,path)
    expected=0
    for q in v3.plan(state):
        spec=state['loop_layout']['specs'][q['asset_index']]
        with Image.open(artwork[str(q['asset_index'])]) as source:
            cropped=source.crop(spec['bbox']);fitted=cropped.resize((q['target_width'],q['target_height']),Image.Resampling.LANCZOS)
            expected+=sum(fitted.getchannel('A').getdata());cropped.close();fitted.close()
    with Image.open(path) as result:assert sum(result.getchannel('A').getdata())==expected


@pytest.mark.parametrize('mode,dimensions,roles', [
 ('scene', [(200,100),(1600,100),(40,200)], {'pattern-2':'accent','pattern-3':'accent'}),
 ('bordered', [(100,200),(200,100),(40,100),(40,40),(1600,800),(40,1600),(1600,100)],
  {'pattern-6':'border','pattern-7':'border'}),
 ('bordered', [(100,1600),(1600,800),(200,200),(800,100),(200,800)],
  {'pattern-4':'border','pattern-5':'border'}),
])
def test_wide_mixed_shapes_spacing_never_reverses_or_changes_repeat_budget(mode,dimensions,roles):
    # Independent review found a wider gap could trigger fewer scene retries,
    # or add an edge-repeat group, making the result narrower/more crowded.
    specs=[dict(width=w,height=h) for w,h in dimensions]
    states=[]
    for spacing in (.25,.5,1.,1.5,2.5):
        s=snapshot(mode=mode,n=len(specs));s['pattern_roles']=roles;s['params']['spacing']=spacing
        states.append(v3.resolve(s,specs=specs))
    widths=[s['output_profile']['width'] for s in states]
    gaps=[s['loop_layout']['metrics']['mean_gap_px'] for s in states]
    assert all(a<b for a,b in zip(widths,widths[1:]))
    assert all(a<b for a,b in zip(gaps,gaps[1:]))
    assert len({tuple(g['groups'] for g in s['loop_layout']['groups']) for s in states})==1
    first=v3.plan(states[0])
    for state in states[1:]:
        for a,b in zip(first,v3.plan(state)):
            assert a['target_width']==b['target_width'] and a['target_height']==b['target_height']
            assert a['y']==b['y']


def test_scene_initial_pack_allows_a_complete_very_wide_accent():
    s=snapshot(mode='scene',n=3)
    s['pattern_roles']={'pattern-2':'accent','pattern-3':'accent'}
    result=v3.resolve(s,specs=[dict(width=w,height=h) for w,h in [(100,100),(1600,1600),(1600,40)]])
    p=v3.plan(result)
    assert {q['asset_index'] for q in p}=={0,1,2}
    assert max(q['planned_width'] for q in p)<result['output_profile']['width']<=16000
    assert_separation(p,result['output_profile']['width'])
