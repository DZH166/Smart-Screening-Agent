import os
import numpy as np
from PIL import Image, ImageFilter

SRC = r"E:\DSH-Data\home\attachments\v1\objects\2a\2a692731a31d1e582ab8dc7dfe9774080f249a23bbca6fd9ae22471a3b63e2bd"
WORK = r"E:\图号助手\图片编辑"
S = 2

base = Image.open(SRC).convert("RGB")
W, H = base.size
small = np.asarray(base).astype(np.float32)
g = small @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
mx = small.max(axis=2); mn = small.min(axis=2)
sat = (mx - mn) / np.maximum(mx, 1)

band = np.zeros((H, W), bool)
band[94:158, 16:152] = True
core = (((g > 185) & (sat < 0.20)) | (g < 105)) & band
mask_small = (np.asarray(Image.fromarray((core * 255).astype(np.uint8)).filter(
    ImageFilter.MaxFilter(5))) > 0) & band
print("mask@170", int(mask_small.sum()))

img = np.asarray(base.resize((W * S, H * S), Image.LANCZOS)).astype(np.float32)
mask = np.asarray(Image.fromarray((mask_small * 255).astype(np.uint8)).resize(
    (W * S, H * S), Image.NEAREST)) > 0
mask = np.asarray(Image.fromarray((mask * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(3))) > 0
HH, WW = mask.shape

PAD = 4
WIN = 2 * PAD + 1
wy = np.cos(np.linspace(-np.pi / 2, np.pi / 2, WIN)) ** 2
wpatch = (wy[:, None] * wy[None, :]).astype(np.float32)
offs_y, offs_x = np.mgrid[-PAD:PAD + 1, -PAD:PAD + 1]


def compute_grad(im):
    gg = im.mean(axis=2)
    gy = np.zeros_like(gg); gx = np.zeros_like(gg)
    gy[1:-1, :] = (gg[2:, :] - gg[:-2, :]) * 0.5
    gx[:, 1:-1] = (gg[:, 2:] - gg[:, :-2]) * 0.5
    return gx, gy


def front_pixels(unknown):
    known = ~unknown
    nb = np.zeros_like(known)
    nb[1:, :] |= known[:-1, :]; nb[:-1, :] |= known[1:, :]
    nb[:, 1:] |= known[:, :-1]; nb[:, :-1] |= known[:, 1:]
    return unknown & nb


unknown = mask.copy()
known_mask = ~unknown
conf = known_mask.astype(np.float32)
filled = img.copy()
accum = np.zeros_like(img)
wsum = np.zeros((HH, WW), np.float32)
rng = np.random.default_rng(5)

step = 2
grid_y, grid_x = np.mgrid[PAD:HH - PAD:step, PAD:WW - PAD:step]
grid_y = grid_y.ravel(); grid_x = grid_x.ravel()

iters = 0
while unknown.any() and iters < 40000:
    iters += 1
    gx, gy = compute_grad(filled)
    front = front_pixels(unknown)
    ys, xs = np.nonzero(front)
    if len(ys) == 0:
        break
    best, bestp = -1e9, None
    for i in rng.permutation(len(ys))[:min(len(ys), 150)]:
        y, x = ys[i], xs[i]
        y0, y1 = max(0, y - PAD), min(HH, y + PAD + 1)
        x0, x1 = max(0, x - PAD), min(WW, x + PAD + 1)
        c = conf[y0:y1, x0:x1].sum() / (WIN * WIN)
        d = np.hypot(gx[y, x], gy[y, x]) / 255.0 + 1e-3
        pr = c * c * d
        if pr > best:
            best, bestp = pr, (y, x, c)
    y, x, c = bestp
    y0, y1 = max(0, y - PAD), min(HH, y + PAD + 1)
    x0, x1 = max(0, x - PAD), min(WW, x + PAD + 1)
    tp = filled[y0:y1, x0:x1]
    tm = (~unknown[y0:y1, x0:x1])

    km = np.asarray(Image.fromarray((known_mask * 255).astype(np.uint8)).filter(
        ImageFilter.MinFilter(WIN))) > 0
    full = km[grid_y, grid_x]
    cand_y = grid_y[full]; cand_x = grid_x[full]
    if len(cand_y) > 3000:
        sel = rng.choice(len(cand_y), 3000, replace=False)
        cand_y, cand_x = cand_y[sel], cand_x[sel]
    if len(cand_y) == 0:
        unknown[y, x] = False
        continue
    patches = filled[cand_y[:, None, None] + offs_y.ravel()[None, :, None],
                     cand_x[:, None, None] + offs_x.ravel()[None, :, None], :]
    patches = patches.reshape(len(cand_y), WIN, WIN, 3)
    tgt_patch = np.zeros((WIN, WIN, 3), np.float32)
    tgt_patch[:tm.shape[0], :tm.shape[1]] = tp
    wmask = np.zeros((WIN, WIN), np.float32)
    wmask[:tm.shape[0], :tm.shape[1]] = tm
    diff = patches - tgt_patch[None]
    ssd = (diff * diff * wmask[None, :, :, None]).sum(axis=(1, 2, 3)) / max(tm.sum(), 1)
    dyv = (cand_y - y) / 60.0; dxv = (cand_x - x) / 60.0
    ssd = ssd + (dyv * dyv + dxv * dxv) * 12.0
    k = int(np.argmin(ssd))
    sy, sx = int(cand_y[k]), int(cand_x[k])
    src = filled[sy - PAD:sy + PAD + 1, sx - PAD:sx + PAD + 1]

    tgt = (slice(y0, y1), slice(x0, x1))
    wsub = wpatch[(y0 - y + PAD):(y1 - y + PAD), (x0 - x + PAD):(x1 - x + PAD)]
    msub = unknown[tgt].copy()
    accum[tgt] += src * (wsub * msub)[..., None]
    wsum[tgt] += wsub * msub
    conf[tgt] = np.where(msub, c * 0.97, conf[tgt])
    unknown[tgt] = False
    known_mask[tgt] = True
    upd = msub & (wsum[tgt] > 0)
    filled[tgt] = np.where(upd[..., None], accum[tgt] / np.maximum(wsum[tgt], 1e-6)[..., None], filled[tgt])

print("iters", iters, "unknown left", int(unknown.sum()))

alpha = np.asarray(Image.fromarray((mask * 255).astype(np.uint8)).filter(
    ImageFilter.GaussianBlur(1.5))).astype(np.float32)[..., None] / 255.0
out = img * (1 - alpha) + filled * alpha
gg = out.mean(axis=2)
hp = gg - np.asarray(Image.fromarray(np.clip(gg, 0, 255).astype(np.uint8)).filter(
    ImageFilter.GaussianBlur(2))).astype(np.float32)
sig = float(np.std(hp[~mask]))
noise = rng.normal(0, max(sig * 0.45, 1.0), (HH, WW, 1)).astype(np.float32)
out = out + np.repeat(noise, 3, axis=2) * alpha

res = Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))
res.save(os.path.join(WORK, "clean4_340.png"))
res.resize((W, H), Image.LANCZOS).save(os.path.join(WORK, "clean4_170.png"))
print("saved")
