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
box[93:156, 16:152] = True

bright = (gray > 168) & (sat < 0.22) & box
# distance from bright pixels, computed by repeated max-filter via PIL
bimg = Image.fromarray((bright * 255).astype(np.uint8))
near3 = np.asarray(bimg.filter(ImageFilter.MaxFilter(7))) > 0
near2 = np.asarray(bimg.filter(ImageFilter.MaxFilter(5))) > 0

shadow = (gray < 70) & near3 & box
fringe = (sat > 0.12) & (gray > 60) & (gray < 235) & near2 & box
mask = (bright | shadow | fringe) & box
mimg = Image.fromarray((mask * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(3))
mask = np.asarray(mimg) > 0

ys, xs = np.nonzero(mask)
print("mask px", int(mask.sum()), "bbox x", xs.min(), xs.max(), "y", ys.min(), ys.max())

vis = np.asarray(im).copy()
vis[mask] = [255, 0, 255]
Image.fromarray(vis).resize((W * 4, H * 4), Image.NEAREST).save(os.path.join(WORK, "mask_vis.png"))
np.save(os.path.join(WORK, "mask.npy"), mask)

# how much background is left inside box after masking
print("box px", int(box.sum()), "kept background px", int(box.sum() - mask.sum()))
