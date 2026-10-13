from pathlib import Path
import sys,json,cv2
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from hsd_tool.matching import _appearance,_read_image,_features
from hsd_tool.workbook import inspect_workbook
OUT=ROOT/'tmp/matching_validation'
result=json.loads((OUT/'results.json').read_text(encoding='utf8'))
table=inspect_workbook(str(ROOT/'测试样本/10月表格.xlsx'),str(OUT/'workbook_diagnostics'))
detector=cv2.SIFT_create(nfeatures=1600,contrastThreshold=.025)
rows={r['id']:_appearance(_read_image(r['image_path']),detector) for r in table['rows']}
files={f['id']:_appearance(_read_image(f['preview_path']),detector) for f in result['files']}
metrics=[]
for m in result['matches']:
    file_id=m['candidates'][0]['file_id']
    d=_features(rows[m['row_id']],files[file_id]); metrics.append([m['row_id'],file_id,d])
    print(m['row_id'],m['status'],file_id,{k:round(v,3) if isinstance(v,float) else v for k,v in d.items()},flush=True)
(OUT/'diagnostics.json').write_text(json.dumps(metrics,indent=2),encoding='utf8')
