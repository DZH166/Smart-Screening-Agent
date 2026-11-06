"""Render public v3 examples using only original, code-drawn demonstration art.

Each picture derives from the production renderer. Complete native PNG units,
source art, snapshot metrics and the contact sheets remain in an ignored proof
directory. Public WebP previews fit one or three COMPLETE units: never crop an
edge motif to fill a thumbnail. Case suffixes 1/3/6 are stable example IDs, not
an assertion of how many inputs are appropriate for every layout mode.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import sys

from PIL import Image, ImageDraw, ImageFont, __version__ as PILLOW_VERSION

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ribbon_backend import imaging, loop_layout_v3 as layout, loop_pipeline_v3 as pipeline

# The labels explicitly state the actual input structure, including the modes
# restricted to one complete design or one/two endpoint motifs.
TITLES = {
 'grid': ['单图规律平铺','三图按序平铺','六图完整组平铺'],
 'stagger': ['单图隔行错位','三图错位循环','六图错位循环'],
 'scatter': ['同一主体自由散布','三种主体错落旋转','主体与小装饰穿插'],
 'single': ['单图单排循环','三图按序单排','六图完整序列'],
 'ends': ['同一主图与小图','两端主图与两种配图','两端主图与五种配图'],
 'panels': ['三区各一图','三区各两图','三区各三图'],
 'bordered': ['单主体与独立花边','三个主体与独立花边','主体与明确选定的边饰'],
 'scene': ['主体与两个小装饰','主体、配角与小装饰','多个主体与主辅组合'],
 'fullwidth': ['完整横向徽章','完整人物主题面板','完整竖向徽章循环'],
 'alternating': ['同一图案一大一小','奇数三图闭合大小相位','六图大小交替'],
 'ends_open': ['同图两端中间留白','两种端图中间留白','花朵与蝴蝶两端留白'],
 'split': ['左右各一图与独立底纹','左右各两图','左右各三图'],
 'stacked': ['上下各一图与独立底纹','上下各两图','上下各三图'],
 'opposed': ['单图正倒交替','奇数三图正倒闭合','六图正倒交替'],
}
CASE_IDS = (1,3,6)
PALETTE = {'ink':'#274D47','rose':'#E99593','coral':'#DC6E68','mint':'#8EC3A4',
           'gold':'#E5B34E','cream':'#FFF2CD','blue':'#85B4C9','paper':'#FBF8EF'}


def _save_art(directory, key, size, draw):
    # 2x source art keeps native rendered figures clear without an upscale pass.
    path=directory/(key+'.png')
    with Image.new('RGBA',(size[0]*2,size[1]*2)) as image:
        draw(image,ImageDraw.Draw(image),image.width,image.height)
        image.save(path)
    return path


def make_assets(directory):
    directory.mkdir(parents=True,exist_ok=True)
    assets={}
    ink=PALETTE['ink'];rose=PALETTE['rose'];mint=PALETTE['mint'];gold=PALETTE['gold']
    def bunny(im,d,w,h):
        line=max(2,round(w*.018))
        d.ellipse((w*.21,h*.03,w*.43,h*.43),fill='#F4DEC8',outline=ink,width=line)
        d.ellipse((w*.56,h*.01,w*.77,h*.42),fill='#F4DEC8',outline=ink,width=line)
        d.ellipse((w*.28,h*.08,w*.37,h*.36),fill=rose)
        d.ellipse((w*.62,h*.06,w*.71,h*.35),fill=rose)
        d.ellipse((w*.18,h*.48,w*.83,h*.94),fill=mint,outline=ink,width=line)
        d.ellipse((w*.07,h*.76,w*.38,h*.99),fill='#F4DEC8',outline=ink,width=line)
        d.ellipse((w*.64,h*.76,w*.95,h*.99),fill='#F4DEC8',outline=ink,width=line)
        d.ellipse((w*.09,h*.27,w*.91,h*.69),fill='#F4DEC8',outline=ink,width=line)
        for x in (.34,.67):d.ellipse((w*(x-.035),h*.435,w*(x+.035),h*.49),fill=ink)
        for x in (.25,.76):d.ellipse((w*(x-.06),h*.51,w*(x+.06),h*.55),fill='#EDA9A0')
        d.polygon([(w*.45,h*.505),(w*.55,h*.505),(w*.5,h*.545)],fill=ink)
        d.arc((w*.4,h*.51,w*.6,h*.59),0,180,fill=ink,width=line)
        d.polygon([(w*.22,h*.64),(w*.79,h*.64),(w*.75,h*.71),(w*.5,h*.73),(w*.34,h*.85),(w*.25,h*.82),(w*.4,h*.7)],fill=rose,outline=ink,width=line)
    assets['bunny']=_save_art(directory,'bunny',(150,260),bunny)
    def sign(im,d,w,h):
        line=max(2,round(h*.025))
        d.rounded_rectangle((w*.02,h*.1,w*.98,h*.9),radius=h*.2,fill='#F8DD99',outline=ink,width=line)
        font=ImageFont.load_default(size=round(h*.48));text='HELLO';box=d.textbbox((0,0),text,font=font)
        d.text(((w-(box[2]-box[0]))/2,(h-(box[3]-box[1]))/2-box[1]),text,font=font,fill=ink)
        d.ellipse((w*.06,h*.4,w*.1,h*.55),fill=rose);d.ellipse((w*.9,h*.4,w*.94,h*.55),fill=rose)
    assets['sign']=_save_art(directory,'sign',(340,105),sign)
    def leaf(im,d,w,h):
        line=max(2,round(w*.04))
        d.line([(w*.5,h*.96),(w*.5,h*.12)],fill=ink,width=line)
        for y in (.2,.42,.64):
            d.ellipse((w*.07,h*(y-.12),w*.51,h*(y+.13)),fill=mint,outline=ink,width=max(1,line//2))
            d.ellipse((w*.49,h*(y-.2),w*.94,h*(y+.05)),fill='#A4C889',outline=ink,width=max(1,line//2))
    assets['leaf']=_save_art(directory,'leaf',(105,175),leaf)
    def star(im,d,w,h):
        pts=[]
        for i in range(10):
            angle=-math.pi/2+i*math.pi/5;r=.46 if not i%2 else .21
            pts.append((w*(.5+r*math.cos(angle)),h*(.5+r*math.sin(angle))))
        d.polygon(pts,fill=gold,outline=ink,width=max(2,round(w*.02)))
    assets['star']=_save_art(directory,'star',(120,120),star)
    def flower(im,d,w,h):
        for i in range(8):
            a=i*math.pi/4;x=w*(.5+.29*math.cos(a));y=h*(.5+.29*math.sin(a))
            d.ellipse((x-w*.19,y-h*.19,x+w*.19,y+h*.19),fill=rose,outline=ink,width=max(2,round(w*.014)))
        d.ellipse((w*.32,h*.32,w*.68,h*.68),fill=PALETTE['cream'],outline=ink,width=max(2,round(w*.02)))
        for x in (.44,.57):d.ellipse((w*(x-.02),h*.44,w*(x+.02),h*.48),fill=ink)
        d.arc((w*.42,h*.45,w*.59,h*.58),0,180,fill=ink,width=max(2,round(w*.01)))
    assets['flower']=_save_art(directory,'flower',(170,170),flower)
    def butterfly(im,d,w,h):
        line=max(2,round(w*.018))
        for box,col in [((.03,.04,.49,.7),mint),((.51,.02,.98,.7),mint),((.13,.44,.48,.96),rose),((.52,.44,.88,.96),rose)]:
            d.ellipse(tuple(v*(w if i%2==0 else h) for i,v in enumerate(box)),fill=col,outline=ink,width=line)
        d.ellipse((w*.44,h*.2,w*.56,h*.91),fill=gold,outline=ink,width=line)
        d.line([(w*.49,h*.28),(w*.36,h*.02)],fill=ink,width=line)
        d.line([(w*.51,h*.28),(w*.67,h*.02)],fill=ink,width=line)
        for x in (.23,.76):d.ellipse((w*(x-.07),h*.24,w*(x+.07),h*.43),fill=PALETTE['cream'])
    assets['butterfly']=_save_art(directory,'butterfly',(190,135),butterfly)
    def heart(im,d,w,h):
        d.ellipse((w*.03,h*.02,w*.56,h*.65),fill=rose)
        d.ellipse((w*.44,h*.02,w*.97,h*.65),fill=rose)
        d.polygon([(w*.04,h*.36),(w*.96,h*.36),(w*.5,h*.97)],fill=rose)
        d.arc((w*.12,h*.12,w*.4,h*.43),185,280,fill='#FCE9DA',width=max(2,round(w*.04)))
    assets['heart']=_save_art(directory,'heart',(125,115),heart)
    def bow(im,d,w,h):
        d.polygon([(w*.46,h*.45),(w*.19,h*.98),(w*.12,h*.7),(w*.02,h*.71),(w*.25,h*.4)],fill=rose,outline=ink,width=3)
        d.polygon([(w*.54,h*.45),(w*.81,h*.98),(w*.88,h*.7),(w*.98,h*.71),(w*.75,h*.4)],fill=rose,outline=ink,width=3)
        d.polygon([(w*.48,h*.42),(w*.05,h*.05),(w*.02,h*.65),(w*.48,h*.56)],fill='#ECA7A2',outline=ink,width=3)
        d.polygon([(w*.52,h*.42),(w*.95,h*.05),(w*.98,h*.65),(w*.52,h*.56)],fill='#ECA7A2',outline=ink,width=3)
        d.rounded_rectangle((w*.4,h*.3,w*.6,h*.64),radius=w*.05,fill=gold,outline=ink,width=3)
    assets['bow']=_save_art(directory,'bow',(175,110),bow)
    def cloud(im,d,w,h):
        d.ellipse((w*.22,h*.04,w*.63,h*.84),fill=PALETTE['blue'])
        d.ellipse((w*.48,h*.24,w*.9,h*.94),fill=PALETTE['blue'])
        d.rounded_rectangle((w*.03,h*.4,w*.97,h*.95),radius=h*.25,fill=PALETTE['blue'])
    assets['cloud']=_save_art(directory,'cloud',(190,95),cloud)

    def paste(canvas,key,box):
        with Image.open(assets[key]) as source:
            source.thumbnail((box[2],box[3]),Image.Resampling.LANCZOS)
            canvas.alpha_composite(source,(box[0]+(box[2]-source.width)//2,box[1]+(box[3]-source.height)//2))
    with Image.new('RGBA',(1120,360)) as im:
        d=ImageDraw.Draw(im);d.rounded_rectangle((10,30,1110,330),radius=130,fill='#F5E5BB',outline=ink,width=7)
        paste(im,'flower',(35,65,230,230));paste(im,'sign',(280,78,560,190));paste(im,'flower',(855,65,230,230))
        assets['emblem-wide']=directory/'emblem-wide.png';im.save(assets['emblem-wide'])
    with Image.new('RGBA',(1000,430)) as im:
        d=ImageDraw.Draw(im);d.rounded_rectangle((10,15,990,420),radius=55,fill='#E7F0E1',outline=ink,width=7)
        paste(im,'bunny',(75,30,235,380));paste(im,'sign',(345,130,570,205));paste(im,'butterfly',(520,27,190,120))
        assets['emblem-scene']=directory/'emblem-scene.png';im.save(assets['emblem-scene'])
    with Image.new('RGBA',(460,610)) as im:
        d=ImageDraw.Draw(im);d.ellipse((10,10,450,600),fill='#F8E5CF',outline=ink,width=7)
        paste(im,'bunny',(100,50,260,440));paste(im,'flower',(29,380,135,135));paste(im,'leaf',(320,367,110,180))
        font=ImageFont.load_default(size=50);d.text((180,513),'JOY',font=font,fill=ink)
        assets['emblem-tall']=directory/'emblem-tall.png';im.save(assets['emblem-tall'])
    with Image.new('RGBA',(640,100)) as im:
        d=ImageDraw.Draw(im);d.line((0,50,640,50),fill=ink,width=4)
        for x in range(0,640,80):
            d.ellipse((x+20,20,x+60,80),fill=mint)
            d.line((x+28,50,x+52,50),fill=ink,width=3)
        assets['border-strip']=directory/'border-strip.png';im.save(assets['border-strip'])
    for key,col,style in [('sage','#EDF2E4','dots'),('rose','#F7E3DD','stripes'),('blue','#DCECF0','dots'),('cream','#FFF2CF','stripes')]:
        with Image.new('RGBA',(320,320),col) as im:
            d=ImageDraw.Draw(im)
            if style=='dots':
                for x,y in ((80,80),(240,240)):d.ellipse((x-9,y-9,x+9,y+9),fill='#FFFFFF90')
            else:
                for x in (40,120,200,280):d.rectangle((x,0,x+5,319),fill='#FFFFFF70')
            assets[key]=directory/(key+'.png');im.save(assets[key])
    with Image.new('RGBA',(960,420),'#EAF2EA') as im:
        d=ImageDraw.Draw(im);d.ellipse((-180,220,650,650),fill='#C1D5AE');d.ellipse((490,255,1230,650),fill='#AEC99F')
        d.rectangle((0,340,959,419),fill='#9DB98E')
        assets['landscape']=directory/'landscape.png';im.save(assets['landscape'])
    return assets


def selection(mode,case_id):
    standard={1:['bunny'],3:['bunny','flower','leaf'],6:['bunny','sign','flower','star','leaf','butterfly']}
    motifs=list(standard[case_id]);roles={};border=None
    if mode=='scene':
        motifs={1:['bunny','star','butterfly'],3:['bunny','flower','star','leaf','butterfly'],
                6:['bunny','sign','flower','star','leaf','butterfly','heart']}[case_id]
        roles={key:('main' if i==0 or case_id==6 and key=='flower' else 'support' if key in ('sign','flower','leaf') else 'accent') for i,key in enumerate(motifs)}
    elif mode=='scatter':
        roles={key:('accent' if case_id==6 and key in ('star','leaf','butterfly') else 'main') for key in motifs}
    elif mode=='bordered':
        motifs={1:['bunny'],3:['bunny','sign','flower'],6:['bunny','sign','flower','star','leaf','heart']}[case_id]
        roles={key:('border' if case_id==6 and key in ('star','leaf','heart') else 'main') for key in motifs}
        border='border-strip' if case_id!=6 else None
    elif mode=='panels':
        motifs={1:['bunny','sign','flower'],3:['bunny','leaf','sign','butterfly','flower','star'],
                6:['bunny','leaf','star','sign','heart','bow','flower','butterfly','cloud']}[case_id]
    elif mode in ('split','stacked'):
        motifs={1:['bunny','sign'],3:['bunny','flower','sign','butterfly'],6:standard[6]}[case_id]
    elif mode=='fullwidth':
        motifs=[{1:'emblem-wide',3:'emblem-scene',6:'emblem-tall'}[case_id]]
    elif mode=='ends_open':
        motifs={1:['bunny'],3:['bunny','sign'],6:['flower','butterfly']}[case_id]
    snapshot=dict(layout_engine=layout.ENGINE,template_mode=mode,asset_refs=motifs,
                  pattern_slots=['demo-'+key for key in motifs],
                  pattern_roles={'demo-'+key:role for key,role in roles.items()},
                  background_ref='landscape' if mode=='scene' else 'sage',
                  zone_background_refs=dict(zip(layout.ZONE_IDS.get(mode,()),['rose','blue','cream'])),
                  border_ref=border,template_rules={},seed=32+case_id,
                  design_density='balanced' if case_id!=6 or mode not in ('grid','stagger','scatter') else 'rich',
                  params={},output_profile=dict(width=1200,height=420,dpi=300,format='PNG',is_demo=True))
    return snapshot


def fit_complete(unit,target,unit_count):
    """Only repeat complete units and fit the complete strip without cropping."""
    with Image.new('RGBA',(unit.width*unit_count,unit.height)) as strip:
        for i in range(unit_count):strip.alpha_composite(unit,(i*unit.width,0))
        strip.thumbnail(target,Image.Resampling.LANCZOS)
        canvas=Image.new('RGB',target,PALETTE['paper'])
        canvas.paste(strip,((target[0]-strip.width)//2,(target[1]-strip.height)//2),strip)
        return canvas


def build(evidence):
    evidence.mkdir(parents=True,exist_ok=True)
    assets=make_assets(evidence/'source-art');masters=evidence/'masters';masters.mkdir(exist_ok=True)
    destination=ROOT/'ribbon_frontend/public/layout-v3';mirror=ROOT/'hsd_tool/static/ribbon/layout-v3'
    destination.mkdir(parents=True,exist_ok=True);mirror.mkdir(parents=True,exist_ok=True)
    records=[]
    for mode in layout.MODES:
        for index,case_id in enumerate(CASE_IDS):
            snapshot=selection(mode,case_id);resolved=pipeline.resolve(snapshot,assets.__getitem__)
            key=f'{mode}-{case_id}';master=masters/(key+'.png')
            result=imaging.render(resolved,assets.__getitem__,master,masters/(key+'-preview.png'))
            with Image.open(master) as unit:
                unit_count=3 if unit.width/unit.height<1.5 else 1
                with fit_complete(unit,(1200,360),unit_count) as preview:
                    preview.save(destination/(key+'.webp'),quality=93,method=6)
                if case_id==3:
                    with fit_complete(unit,(540,180),unit_count) as small:
                        small.save(destination/(mode+'.webp'),quality=93,method=6)
            records.append(dict(mode=mode,id=case_id,title=TITLES[mode][index],source_count=len(snapshot['asset_refs']),
                                assets=snapshot['asset_refs'],roles=snapshot['pattern_roles'],unit_count=unit_count,
                                dimensions=[resolved['output_profile']['width'],resolved['output_profile']['height']],
                                master_sha256=hashlib.sha256(master.read_bytes()).hexdigest(),
                                snapshot=resolved,render=result))
    hashes={}
    for path in sorted(destination.glob('*.webp')):
        shutil.copyfile(path,mirror/path.name)
        hashes[path.name]=hashlib.sha256(path.read_bytes()).hexdigest()
    font=ImageFont.load_default(size=20)
    for page in range(3):
        modes=layout.MODES[page*5:(page+1)*5]
        with Image.new('RGB',(1500,len(modes)*190),'#E3E6E1') as sheet:
            d=ImageDraw.Draw(sheet)
            for row,mode in enumerate(modes):
                for col,case_id in enumerate(CASE_IDS):
                    record=next(r for r in records if r['mode']==mode and r['id']==case_id)
                    with Image.open(destination/f'{mode}-{case_id}.webp') as source:
                        source.thumbnail((490,150),Image.Resampling.LANCZOS);sheet.paste(source,(col*500+5,row*190+35))
                    d.text((col*500+5,row*190+5),f'{mode} / case {case_id} / {record["source_count"]} inputs',font=font,fill='#173D35')
            sheet.save(evidence/f'contact-{page+1}.jpg',quality=95)
    report=dict(engine=layout.ENGINE,pillow=PILLOW_VERSION,private_or_external_images_used=False,
                source='original code-drawn demonstration artwork',examples=records,sha256=hashes)
    (evidence/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(dict(count=len(records),public_files=len(hashes),evidence=str(evidence),sha256=hashes),indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence-dir',type=Path,default=ROOT/'tmp/layout-v3-demo-proof')
    build(parser.parse_args().evidence_dir)
