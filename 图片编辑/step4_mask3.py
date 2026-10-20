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
box[94:156, 18:148] = True

core = (gray > 208) & (sat < 0.12) & box
print("core px", int(core.sum()))
core_img = Image.fromarray((core * 255).astype(np.uint8))
core_dil = np.asarray(core_img.filter(ImageFilter.MaxFilter(11))) > 0
dark = (gray < 75) & core_dil & box
mask = (core_dil | dark) & box
ys, xs = np.nonzero(mask)
print("mask px", int(mask.sum()), "bbox x", xs.min(), xs.max(), "y", ys.min(), ys.max())

vis = np.asarray(im).copy()
vis[mask] = [255, 0, 255]
Image.fromarray(vis).resize((W * 4, H * 4), Image.NEAREST).save(os.path.join(WORK, "mask_vis3.png"))
np.save(os.path.join(WORK, "mask3.npy"), mask)
