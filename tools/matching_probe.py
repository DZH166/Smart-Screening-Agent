from pathlib import Path
import zipfile, re, xml.etree.ElementTree as ET
import cv2, numpy as np, pymupdf

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'tmp/matching_probe'
OUT.mkdir(parents=True, exist_ok=True)
ns = {'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main','xdr':'http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing','a':'http://schemas.openxmlformats.org/drawingml/2006/main','r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
with zipfile.ZipFile(ROOT / '测试样本/10月表格.xlsx') as z:
    rels = {r.attrib['Id']:r.attrib['Target'] for r in ET.fromstring(z.read('xl/_rels/cellimages.xml.rels'))}
    imgs = {}
    for pic in ET.fromstring(z.read('xl/cellimages.xml')).findall('.//xdr:pic',ns):
        name = pic.find('.//xdr:cNvPr',ns).attrib['name']
        rid = pic.find('.//a:blip',ns).attrib['{'+ns['r']+'}embed']
        imgs[name] = 'xl/'+rels[rid].lstrip('/')
    for row in ET.fromstring(z.read('xl/worksheets/sheet1.xml')).findall('.//s:row',ns):
        for cell in row.findall('s:c',ns):
            f = cell.find('s:f',ns)
            if f is not None and 'DISPIMG' in (f.text or ''):
                key = re.search(r'"(ID_[^"]+)"', f.text).group(1)
                p = OUT / f"row_{row.attrib['r']}.png"
                arr = cv2.imdecode(np.frombuffer(z.read(imgs[key]),np.uint8),cv2.IMREAD_COLOR)
                cv2.imencode('.png',arr)[1].tofile(str(p))
with zipfile.ZipFile(ROOT / '测试样本/10.10.zip') as z:
    for i,info in enumerate(x for x in z.infolist() if x.filename.lower().endswith('.ai')):
        p = OUT / f'ai_{i+1}.png'
        if p.exists(): continue
        with pymupdf.open(stream=z.read(info), filetype='pdf') as doc:
            page = doc[0]
            mat = pymupdf.Matrix(1000/max(page.rect.width,page.rect.height),1000/max(page.rect.width,page.rect.height))
            page.get_pixmap(matrix=mat,alpha=False).save(p)
        print(i+1, info.filename, flush=True)
for kind in ('row','ai'):
    paths = sorted(OUT.glob(f'{kind}_*.png'),key=lambda p:int(p.stem.split('_')[1]))
    canvas = np.full((180*((len(paths)+5)//6),1200,3),255,np.uint8)
    for i,p in enumerate(paths):
        arr = cv2.imdecode(np.fromfile(p,np.uint8),1)
        h,w=arr.shape[:2]; scale=min(190/w,150/h)
        arr=cv2.resize(arr,(round(w*scale),round(h*scale)))
        y=(i//6)*180; x=(i%6)*200
        canvas[y:y+arr.shape[0],x:x+arr.shape[1]]=arr
        cv2.putText(canvas,p.stem,(x+5,y+170),cv2.FONT_HERSHEY_SIMPLEX,.5,(0,0,0),1)
    cv2.imencode('.jpg',canvas)[1].tofile(str(OUT/f'{kind}_montage.jpg'))
