import os
import numpy as np
from PIL import Image

SRC = r"E:\DSH-Data\home\attachments\v1\objects\2a\2a692731a31d1e582ab8dc7dfe9774080f249a23bbca6fd9ae22471a3b63e2bd"
WORK = r"E:\图号助手\图片编辑"
os.makedirs(WORK, exist_ok=True)

im = Image.open(SRC).convert("RGB")
W, H = im.size
print("size", im.size)
im.save(os.path.join(WORK, "原图.png"))

crop = im.crop((0, 90, W, 156))
crop.resize((crop.width * 8, crop.height * 8), Image.NEAREST).save(os.path.join(WORK, "text_zoom.png"))

a = np.asarray(im).astype(np.float32)
gray = a @ np.array([0.299, 0.587, 0.114], dtype=np.float32)

# icon box: find large white rounded square (very bright, low sat) in top area
mx = a.max(axis=2); mn = a.min(axis=2)
sat = (mx - mn) / np.maximum(mx, 1)
whiteish = (gray > 200) & (sat < 0.12)
rows = whiteish[:105].sum(axis=1)
print("top rows white counts:", [(y, int(rows[y])) for y in range(20, 105, 4)])
cols = whiteish[30:95].sum(axis=0)
print("icon cols>15:", [x for x in range(W) if cols[x] > 15][:3], [x for x in range(W) if cols[x] > 15][-3:])

# text rows: bright pixels below icon
tmask = (gray > 140)
for y0, y1 in ((96, 126), (126, 152)):
    m = tmask[y0:y1, :]
    cs = np.nonzero(m.sum(axis=0) > 0)[0]
    rs = np.nonzero(m.sum(axis=1) > 0)[0] + y0
    print(f"band {y0}-{y1}: x {cs.min()}..{cs.max()}  y {rs.min()}..{rs.max()}  px {int(m.sum())}")

# sample text color (brightest pixels in band) and shadow color (darkest ring)
band = a[96:152, :, :]
g = gray[96:152, :]
print("brightest", band.reshape(-1, 3)[np.argsort(g.ravel())[-8:]].astype(int))
print("darkest", band.reshape(-1, 3)[np.argsort(g.ravel())[:8]].astype(int))
