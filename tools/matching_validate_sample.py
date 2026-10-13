"""Read-only validation fixture; never use known names as matcher evidence."""
from pathlib import Path
import sys,json,time
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from hsd_tool.workbook import inspect_workbook
from hsd_tool.matching import scan_and_match
from PIL import Image,ImageOps,ImageDraw
OUT=ROOT/'tmp/matching_validation'
OUT.mkdir(parents=True,exist_ok=True)
start=time.time()
table=inspect_workbook(str(ROOT/'测试样本/10月表格.xlsx'),str(OUT/'workbook'))
result=scan_and_match(str(ROOT/'测试样本/10.10.zip'),table['rows'],str(OUT),
                      progress=lambda message,current,total:print(message,flush=True))
result['elapsed_seconds']=round(time.time()-start,2)
(OUT/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
files={f['id']:f for f in result['files']}
rows={r['id']:r for r in table['rows']}
for label, selected in [('auto',[m for m in result['matches'] if m['status']=='auto']),
                         ('review',[m for m in result['matches'] if m['status']!='auto'])]:
    for page in range(0,len(selected),10):
        group=selected[page:page+10]
        canvas=Image.new('RGB',(1500,len(group)*180),'#edf2f7')
        draw=ImageDraw.Draw(canvas)
        for index,match in enumerate(group):
            y=index*180
            identity=match['file_id'] or match['candidates'][0]['file_id']
            for x,path in [(10,rows[match['row_id']]['image_path']),(760,files[identity]['preview_path'])]:
                image=Image.open(path).convert('RGB');image.thumbnail((730,140))
                canvas.paste(image,(x,y+(140-image.height)//2))
            draw.text((12,y+147),f"{match['row_id']} | {label} | workbook",fill='black')
            draw.text((760,y+147),f"{identity} | similarity {match['candidates'][0]['score']:.4f}",fill='black')
        canvas.save(OUT/f'{label}_{page//10+1}.jpg',quality=94)
print('Counts', {s:sum(m['status']==s for m in result['matches']) for s in ['auto','review','unmatched']})
print('Seconds',result['elapsed_seconds'])
