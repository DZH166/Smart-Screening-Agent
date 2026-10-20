import os
import numpy as np
from PIL import Image, ImageFilter
from numpy.lib.stride_tricks import sliding_window_view

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
core = ((g > 185) & (sat < 0.20) | (g < 105)) & band
m = np.asarray(Image.fromarray((core * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(5))) > 0
mask_small = m & band
print("mask@170", int(mask_small.sum()))
np.save(os.path.join(WORK, "mask4.npy"), mask_small)

img = np.asarray(base.resize((W * S, H * S), Image.LANCZOS)).astype(np.float32)
mask = np.asarray(Image.fromarray((mask_small * 255).astype(np.uint8)).resize(
    (W * S, H * S), Image.NEAREST)) > 0
mask = np.asarray(Image.fromarray((mask * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(3))) > 0
HH, WW = mask.shape
print("size", WW, HH, "unknown", int(mask.sum()))

PAD = 4
WIN = 2 * PAD + 1
wy = np.cos(np.linspace(-np.pi / 2, np.pi / 2, WIN)) ** 2
wpatch = (wy[:, None] * wy[None, :]).astype(np.float32)


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


gx, gy = compute_grad(img)
conf = (~mask).astype(np.float32)
accum = np.zeros_like(img)
wsum = np.zeros((HH, WW), np.float32)
filled = img.copy()
unknown = mask.copy()
rng = np.random.default_rng(11)

R = 40
iters = 0
while unknown.any() and iters < 40000:
    iters += 1
    if iters % 400 == 0:
        gx, gy = compute_grad(filled)
    front = front_pixels(unknown)
    ys, xs = np.nonzero(front)
    if len(ys) == 0:
        break
    best, bestp = -1e9, None
    for i in rng.permutation(len(ys))[:min(len(ys), 120)]:
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

    cy0, cy1 = max(PAD, y - R), min(HH - PAD - 1, y + R)
    cx0, cx1 = max(PAD, x - R), min(WW - PAD - 1, x + R)
    sub_known = ~unknown[cy0 - PAD:cy1 + PAD + 1, cx0 - PAD:cx1 + PAD + 1]
    full = np.asarray(Image.fromarray((sub_known * 255).astype(np.uint8)).filter(
        ImageFilter.MinFilter(WIN))) > 0
    full = full[PAD:-PAD, PAD:-PAD]
    sub_img = filled[cy0 - PAD:cy1 + PAD + 1, cx0 - PAD:cx1 + PAD + 1]
    cand = sliding_window_view(sub_img, (WIN, WIN), axis=(0, 1))
    cand = np.ascontiguousarray(np.transpose(cand, (0, 1, 3, 4, 2)))

    if not full.any():
        unknown[y, x] = False
        conf[y, x] = c
        continue

    diff = cand - tp[None, None]
    wgt = tm[None, None, :, :, None].astype(np.float32)
    ssd = (diff * diff * wgt).sum(axis=(2, 3, 4)) / max(tm.sum(), 1)
    hh, ww = full.shape
    dy = np.arange(hh)[:, None] + (cy0 - y)
    dx = np.arange(ww)[None, :] + (cx0 - x)
    ssd = ssd + (dy * dy + dx * dx) * 0.02
    ssd[~full] = np.inf
    k = int(np.argmin(ssd))
    sy, sx = divmod(k, ww)
    src = filled[cy0 + sy - PAD:cy0 + sy + PAD + 1, cx0 + sx - PAD:cx0 + sx + PAD + 1]

    tgt = (slice(y0, y1), slice(x0, x1))
    wsub = wpatch[(y0 - y + PAD):(y1 - y + PAD), (x0 - x + PAD):(x1 - x + PAD)]
    msub = unknown[tgt]
    accum[tgt] += src * (wsub * msub)[..., None]
    wsum[tgt] += wsub * msub
    conf[tgt] = np.where(msub, c * 0.97, conf[tgt])
    unknown[tgt] = False
    upd = msub & (wsum[tgt] > 0)
    filled[tgt] = np.where(upd[..., None], accum[tgt] / np.maximum(wsum[tgt], 1e-6)[..., None], filled[tgt])

print("iters", iters, "left", int(unknown.sum()))

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
res.save(os.path.join(WORK, "clean3_340.png"))
res.resize((W, H), Image.LANCZOS).save(os.path.join(WORK, "clean3_170.png"))
print("saved")
