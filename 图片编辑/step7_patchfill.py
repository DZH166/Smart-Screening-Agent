import os
import numpy as np
from PIL import Image, ImageFilter
from numpy.lib.stride_tricks import sliding_window_view

SRC = r"E:\DSH-Data\home\attachments\v1\objects\2a\2a692731a31d1e582ab8dc7dfe9774080f249a23bbca6fd9ae22471a3b63e2bd"
WORK = r"E:\图号助手\图片编辑"
S = 2

base = Image.open(SRC).convert("RGB")
W, H = base.size
img = np.asarray(base.resize((W * S, H * S), Image.LANCZOS)).astype(np.float32)
mask_small = np.load(os.path.join(WORK, "mask3.npy"))
mask = np.asarray(Image.fromarray((mask_small * 255).astype(np.uint8)).resize(
    (W * S, H * S), Image.NEAREST)) > 0
mask = np.asarray(Image.fromarray((mask * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(3))) > 0
HH, WW = mask.shape
print("size", WW, HH, "unknown", int(mask.sum()))

PAD = 4  # patch radius -> 9x9

gy = np.zeros_like(mask, float)
gx = np.zeros_like(mask, float)


def compute_grad(im):
    g = im.mean(axis=2)
    gy = np.zeros_like(g)
    gx = np.zeros_like(g)
    gy[1:-1, :] = (g[2:, :] - g[:-2, :]) * 0.5
    gx[:, 1:-1] = (g[:, 2:] - g[:, :-2]) * 0.5
    return gx, gy


gx, gy = compute_grad(img)
conf = (~mask).astype(np.float32)

filled = img.copy()
unknown = mask.copy().astype(bool)


def patch_view(im):
    return sliding_window_view(im, (2 * PAD + 1, 2 * PAD + 1), axis=(0, 1))


def fill_front(unknown):
    u = unknown
    nb = np.zeros_like(u)
    nb[1:, :] |= u[:-1, :]
    nb[:-1, :] |= u[1:, :]
    nb[:, 1:] |= u[:, :-1]
    nb[:, :-1] |= u[:, 1:]
    return u & ~nb & False  # placeholder


def front_pixels(unknown):
    # unknown pixels adjacent to known
    known = ~unknown
    nb = np.zeros_like(known)
    nb[1:, :] |= known[:-1, :]
    nb[:-1, :] |= known[1:, :]
    nb[:, 1:] |= known[:, :-1]
    nb[:, :-1] |= known[:, 1:]
    return unknown & nb


rng = np.random.default_rng(3)
iters = 0
while unknown.any() and iters < 60000:
    iters += 1
    if iters % 400 == 0:
        gx, gy = compute_grad(filled)
    front = front_pixels(unknown)
    ys, xs = np.nonzero(front)
    if len(ys) == 0:
        break
    # priority: confidence in patch + data term
    best = -1e9
    bestp = None
    idx = rng.permutation(len(ys))[:min(len(ys), 120)]
    for i in idx:
        y, x = ys[i], xs[i]
        y0, y1 = max(0, y - PAD), min(HH, y + PAD + 1)
        x0, x1 = max(0, x - PAD), min(WW, x + PAD + 1)
        c = conf[y0:y1, x0:x1].sum() / ((2 * PAD + 1) ** 2)
        d = np.hypot(gx[y, x], gy[y, x]) / 255.0 + 0.001
        pr = c * c * d
        if pr > best:
            best = pr
            bestp = (y, x, c)
    y, x, c = bestp
    y0, y1 = max(0, y - PAD), min(HH, y + PAD + 1)
    x0, x1 = max(0, x - PAD), min(WW, x + PAD + 1)
    tp = filled[y0:y1, x0:x1]
    tm = (~unknown[y0:y1, x0:x1])
    # candidate centres within search window whose patch is fully known
    R = 42
    cy0, cy1 = max(PAD, y - R), min(HH - PAD - 1, y + R)
    cx0, cx1 = max(PAD, x - R), min(WW - PAD - 1, x + R)
    if cy1 <= cy0 or cx1 <= cx0:
        break
    sub_known = ~unknown[cy0 - PAD:cy1 + PAD + 1, cx0 - PAD:cx1 + PAD + 1]
    full = np.asarray(Image.fromarray((sub_known * 255).astype(np.uint8)).filter(
        ImageFilter.MinFilter(2 * PAD + 1))) > 0
    full = full[PAD:-PAD, PAD:-PAD]  # align to candidate centres
    sub_img = filled[cy0 - PAD:cy1 + PAD + 1, cx0 - PAD:cx1 + PAD + 1]
    cand = sliding_window_view(sub_img, (2 * PAD + 1, 2 * PAD + 1), axis=(0, 1))
    cand = np.ascontiguousarray(np.transpose(cand, (0, 1, 3, 4, 2)))  # h,w,ph,pw,3
    valid = full
    if not valid.any():
        # fall back: widen using nearest known value
        filled[y, x] = img[~unknown].mean(axis=0) if (~unknown).any() else filled[y, x]
        unknown[y, x] = False
        conf[y, x] = c
        continue
    hh, ww = valid.shape
    diff = cand - tp[None, None]
    wgt = tm[None, None, :, :, None].astype(np.float32)
    ssd = (diff * diff * wgt).sum(axis=(2, 3, 4)) / max(tm.sum(), 1)
    dy = np.arange(hh)[:, None] + (cy0 - y)
    dx = np.arange(ww)[None, :] + (cx0 - x)
    dist = (dy * dy + dx * dx) * 0.01
    ssd = ssd + dist
    ssd[~valid] = np.inf
    k = np.argmin(ssd)
    sy, sx = divmod(int(k), ww)
    oy, ox = cy0 + sy, cx0 + sx
    src = filled[oy - PAD:oy + PAD + 1, ox - PAD:ox + PAD + 1]
    tgt_slice = (slice(y0, y1), slice(x0, x1))
    m = unknown[tgt_slice]
    filled[tgt_slice][m] = src[m]
    conf[tgt_slice][m] = c * (1 - 0.05)
    unknown[tgt_slice] = False

print("iters", iters, "left", int(unknown.sum()))

# feather blend + grain
alpha = np.asarray(Image.fromarray((mask * 255).astype(np.uint8)).filter(
    ImageFilter.GaussianBlur(1.5))).astype(np.float32)[..., None] / 255.0
out = img * (1 - alpha) + filled * alpha
gray = out.mean(axis=2)
hp = gray - np.asarray(Image.fromarray(np.clip(gray, 0, 255).astype(np.uint8)).filter(
    ImageFilter.GaussianBlur(2))).astype(np.float32)
sig = float(np.std(hp[~mask]))
noise = rng.normal(0, max(sig * 0.5, 1.0), (HH, WW, 1)).astype(np.float32)
out = out + np.repeat(noise, 3, axis=2) * alpha

res = Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))
res.save(os.path.join(WORK, "clean2_340.png"))
res.resize((W, H), Image.LANCZOS).save(os.path.join(WORK, "clean2_170.png"))
print("saved")
