import os
import numpy as np
from PIL import Image, ImageFilter

WORK = r"E:\图号助手\图片编辑"
SRC = r"E:\DSH-Data\home\attachments\v1\objects\2a\2a692731a31d1e582ab8dc7dfe9774080f249a23bbca6fd9ae22471a3b63e2bd"
base = Image.open(SRC).convert("RGB")
W, H = base.size
S = 2
img = np.asarray(base.resize((W * S, H * S), Image.LANCZOS)).astype(np.float32)
small = np.asarray(base).astype(np.float32)
g = small @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
mx = small.max(axis=2); mn = small.min(axis=2)
sat = (mx - mn) / np.maximum(mx, 1)
band = np.zeros((H, W), bool); band[94:158, 16:152] = True
core = (((g > 185) & (sat < 0.20)) | (g < 105)) & band
mask_small = (np.asarray(Image.fromarray((core * 255).astype(np.uint8)).filter(
    ImageFilter.MaxFilter(5))) > 0) & band
mask = np.asarray(Image.fromarray((mask_small * 255).astype(np.uint8)).resize(
    (W * S, H * S), Image.NEAREST)) > 0
mask = np.asarray(Image.fromarray((mask * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(3))) > 0

PAD = 4
offs_y, offs_x = np.mgrid[-PAD:PAD + 1, -PAD:PAD + 1]
filled = img.copy()
cy = np.array([100, 200]); cx = np.array([100, 200])
p = filled[cy[:, None, None] + offs_y.ravel()[None, :, None], cx[:, None, None] + offs_x.ravel()[None, :, None], :]
print("patches shape", p.shape)
print("first", p[0, 0], "expected center-ish", filled[96, 96])
print("img stats", img.min(), img.max(), img.mean())
print("mask stats", mask.sum(), mask.shape)
