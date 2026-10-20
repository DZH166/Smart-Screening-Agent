import os
import numpy as np
from PIL import Image, ImageFilter, ImageFont, ImageDraw

SRC = r"E:\DSH-Data\home\attachments\v1\objects\2a\2a692731a31d1e582ab8dc7dfe9774080f249a23bbca6fd9ae22471a3b63e2bd"
WORK = r"E:\图号助手\图片编辑"
S = 4  # working scale

raw = Image.open(SRC)
print("mode", raw.mode)
has_alpha = raw.mode in ("RGBA", "LA")
base = raw.convert("RGBA")
W, H = base.size
big = base.resize((W * S, H * S), Image.LANCZOS)
arr = np.asarray(big).astype(np.float32)

mask_small = np.load(os.path.join(WORK, "mask3.npy"))
mask = np.asarray(Image.fromarray((mask_small * 255).astype(np.uint8)).resize((W * S, H * S), Image.NEAREST)) > 0
mask = np.asarray(Image.fromarray((mask * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(5))) > 0
print("mask 4x px", int(mask.sum()))


def harmonic_fill(img, m, levels=4, iters=120):
    """Multiscale Jacobi (Laplace) inpainting. img: HxWxC float, m: bool unknown."""
    pyr_img, pyr_mask = [img], [m]
    for _ in range(levels):
        i2 = pyr_img[-1]
        h, w = i2.shape[:2]
        h2, w2 = h // 2, w // 2
        down = i2[:h2 * 2, :w2 * 2].reshape(h2, 2, w2, 2, -1).mean(axis=(1, 3))
        md = m[:h2 * 2, :w2 * 2].reshape(h2, 2, w2, 2).any(axis=(1, 3))
        pyr_img.append(down)
        pyr_mask.append(md)
    cur = pyr_img[-1].copy()
    mk = pyr_mask[-1]
    if mk.any():
        cur[mk] = cur[~mk].mean(axis=0)
    for lvl in range(levels, -1, -1):
        target = pyr_img[lvl]
        mm = pyr_mask[lvl]
        if lvl < levels:
            up = np.asarray(Image.fromarray(np.clip(cur, 0, 255).astype(np.uint8)).resize(
                (target.shape[1], target.shape[0]), Image.BICUBIC)).astype(np.float32)
            cur = up
        else:
            cur = cur
        cur[~mm] = target[~mm]
        w = cur.copy()
        for _ in range(iters):
            nb = (np.roll(w, 1, 0) + np.roll(w, -1, 0) + np.roll(w, 1, 1) + np.roll(w, -1, 1)) * 0.25
            w[mm] = nb[mm]
            w[~mm] = target[~mm]
        cur = w
    return cur


filled = harmonic_fill(arr[..., :3].copy(), mask)
print("fill done")

# texture: local high-frequency noise from untouched surroundings
gray = filled.mean(axis=2)
hp = gray - np.asarray(Image.fromarray(np.clip(gray, 0, 255).astype(np.uint8)).filter(
    ImageFilter.GaussianBlur(2))).astype(np.float32)
ring = mask & ~np.asarray(Image.fromarray((mask * 255).astype(np.uint8)).filter(
    ImageFilter.MinFilter(9))) > 0
sig = float(np.std(hp[~mask])) if (~mask).any() else 2.0
print("noise sigma", round(sig, 2))
rng = np.random.default_rng(7)
noise = rng.normal(0, max(sig, 1.5), (arr.shape[0], arr.shape[1], 1)).astype(np.float32)
noise3 = np.repeat(noise, 3, axis=2)
filled = filled + noise3 * 0.55

# feather blend
alpha = np.asarray(Image.fromarray((mask * 255).astype(np.uint8)).filter(
    ImageFilter.GaussianBlur(2))).astype(np.float32)[..., None] / 255.0
out_rgb = arr[..., :3] * (1 - alpha) + filled * alpha
out = np.dstack([np.clip(out_rgb, 0, 255), arr[..., 3]]).astype(np.uint8)
clean = Image.fromarray(out, "RGBA")
clean.save(os.path.join(WORK, "clean_bg_680.png"))
clean.resize((W, H), Image.LANCZOS).save(os.path.join(WORK, "clean_bg_170.png"))
print("saved clean background")
