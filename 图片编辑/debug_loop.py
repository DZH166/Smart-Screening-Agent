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
HH, WW = mask.shape

PAD = 4; WIN = 9
wy = np.cos(np.linspace(-np.pi / 2, np.pi / 2, WIN)) ** 2
wpatch = (wy[:, None] * wy[None, :]).astype(np.float32)
offs_y, offs_x = np.mgrid[-PAD:PAD + 1, -PAD:PAD + 1]

unknown = mask.copy(); known_mask = ~unknown
conf = known_mask.astype(np.float32)
filled = img.copy()
accum = np.zeros_like(img); wsum = np.zeros((HH, WW), np.float32)
rng = np.random.default_rng(5)

def front_pixels(u):
    k = ~u
    nb = np.zeros_like(k)
    nb[1:, :] |= k[:-1, :]; nb[:-1, :] |= k[1:, :]
    nb[:, 1:] |= k[:, :-1]; nb[:, :-1] |= k[:, 1:]
    return u & nb

stepped = 0
while unknown.any() and stepped < 60:
    stepped += 1
    front = front_pixels(unknown)
    ys, xs = np.nonzero(front)
    y, x = int(ys[0]), int(xs[0])
    y0, y1 = max(0, y - PAD), min(HH, y + PAD + 1)
    x0, x1 = max(0, x - PAD), min(WW, x + PAD + 1)
    tp = filled[y0:y1, x0:x1]
    tm = (~unknown[y0:y1, x0:x1])
    km = np.asarray(Image.fromarray((known_mask * 255).astype(np.uint8)).filter(
        ImageFilter.MinFilter(WIN))) > 0
    gy, gx = np.mgrid[PAD:HH - PAD:2, PAD:WW - PAD:2]
    gy = gy.ravel(); gx = gx.ravel()
    full = km[gy, gx]
    cy, cx = gy[full], gx[full]
    if len(cy) == 0:
        print("no candidates at step", stepped); unknown[y, x] = False; continue
    patches = filled[cy[:, None, None] + offs_y.ravel()[None, :, None],
                     cx[:, None, None] + offs_x.ravel()[None, :, None], :].reshape(len(cy), WIN, WIN, 3)
    tgt_patch = np.zeros((WIN, WIN, 3), np.float32)
    tgt_patch[:tm.shape[0], :tm.shape[1]] = tp
    wmask = np.zeros((WIN, WIN), np.float32)
    wmask[:tm.shape[0], :tm.shape[1]] = tm
    diff = patches - tgt_patch[None]
    ssd = (diff * diff * wmask[None, :, :, None]).sum(axis=(1, 2, 3))
    k = int(np.argmin(ssd))
    sy, sx = int(cy[k]), int(cx[k])
    src = filled[sy - PAD:sy + PAD + 1, sx - PAD:sx + PAD + 1]
    tgt = (slice(y0, y1), slice(x0, x1))
    wsub = wpatch[(y0 - y + PAD):(y1 - y + PAD), (x0 - x + PAD):(x1 - x + PAD)]
    msub = unknown[tgt].copy()
    accum[tgt] += src * (wsub * msub)[..., None]
    wsum[tgt] += wsub * msub
    unknown[tgt] = False
    known_mask[tgt] = True
    upd = msub & (wsum[tgt] > 0)
    filled[tgt] = np.where(upd[..., None], accum[tgt] / np.maximum(wsum[tgt], 1e-6)[..., None], filled[tgt])

print("steps", stepped)
print("nan in filled", int(np.isnan(filled).sum()))
print("filled min/max in mask", float(filled[mask].min()), float(filled[mask].max()))
print("accum min/max", float(accum.min()), float(accum.max()))
print("wsum min/max", float(wsum.min()), float(wsum.max()))
