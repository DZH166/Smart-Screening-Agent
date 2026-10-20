import os
import numpy as np
from PIL import Image, ImageFilter

SRC = r"E:\DSH-Data\home\attachments\v1\objects\2a\2a692731a31d1e582ab8dc7dfe9774080f249a23bbca6fd9ae22471a3b63e2bd"
WORK = r"E:\图号助手\图片编辑"
im = Image.open(SRC).convert("RGB")
W, H = im.size
a = np.asarray(im).astype(np.float32)
gray = a @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
mx = a.max(axis=2); mn = a.min(axis=2)
sat = (mx - mn) / np.maximum(mx, 1)

box = np.zeros((H, W), bool)
box[92:158, 14:156] = True

core = (gray > 150) & (sat < 0.18) & box
core_img = Image.fromarray((core * 255).astype(np.uint8))
dark = (gray < 62) & box
dark_img = Image.fromarray((dark * 255).astype(np.uint8))

# shadow must be close to a glyph core
core_near = np.asarray(core_img.filter(ImageFilter.MaxFilter(7))) > 0
mask = core | (dark & core_near)
mask_img = Image.fromarray((mask * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(7))
mask = (np.asarray(mask_img) > 0) & box

ys, xs = np.nonzero(mask)
print("mask px", int(mask.sum()), "bbox x", xs.min(), xs.max(), "y", ys.min(), ys.max())

vis = np.asarray(im).copy()
vis[mask] = [255, 0, 255]
Image.fromarray(vis).resize((W * 4, H * 4), Image.NEAREST).save(os.path.join(WORK, "mask_vis2.png"))
np.save(os.path.join(WORK, "mask2.npy"), mask)

print("bg samples inside box (unmasked):")
pts = [(x, y) for x in (20, 40, 60, 80, 100, 120, 140, 150) for y in (100, 118, 136, 150)]
for (x, y) in pts[:14]:
    print((x, y), a[y, x].astype(int), "masked" if mask[y, x] else "")
