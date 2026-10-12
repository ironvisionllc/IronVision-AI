#!/usr/bin/env python3
"""Builds every brand asset from the customer-supplied original logo (single source of truth):
    frontend/src/assets/brand/original/Logo-01.webp   (official IronVision vertical lockup, transparent background)
Outputs (frontend/src/assets/brand/): logo-mark{,-dark,-mono}.png (512) + -40/-80 (1x/2x), logo-lockup{,-dark}.png (900) + -288/-576 (1x/2x)
and favicons in frontend/public/ (favicon.svg wrapper, favicon-16/32.png, apple-touch-icon.png, logo-512.png).
To swap in a new official file, replace original/Logo-01.webp (same layout) and re-run:  python3 scripts/build_brand_assets.py
Requires Pillow + numpy (dev-only)."""
import base64
import io
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
BRAND = ROOT / "frontend/src/assets/brand"
PUB = ROOT / "frontend/public"
SRC = BRAND / "original/Logo-01.webp"

LIGHT_TEXT = np.array([226, 232, 240])   # #e2e8f0 – IRON + keyhole on dark surfaces
DARK_VISION = np.array([69, 174, 199])    # brand-400 #45aec7 – VISION on dark surfaces


def split(arr: np.ndarray) -> int:
    """Row index of the transparent gap between the mark and the wordmark."""
    rows = (arr[:, :, 3] > 20).sum(axis=1)
    h = arr.shape[0]
    empty = [y for y in range(int(h * 0.4), int(h * 0.75)) if rows[y] == 0]
    return empty[len(empty) // 2]


def trim(img: Image.Image, pad: int = 0, square: bool = False) -> Image.Image:
    img = img.crop(img.getchannel("A").point(lambda a: 255 if a > 20 else 0).getbbox())
    w, h = img.size
    W, H = (max(w, h),) * 2 if square else (w, h)
    out = Image.new("RGBA", (W + 2 * pad, H + 2 * pad), (0, 0, 0, 0))
    out.paste(img, (pad + (W - w) // 2, pad + (H - h) // 2), img)
    return out


def masks(a: np.ndarray):
    rgb = a[:, :, :3].astype(int)
    vis = a[:, :, 3] > 0
    gray = vis & ((rgb.max(axis=2) - rgb.min(axis=2)) < 40)  # charcoal #414143 (IRON + keyhole)
    return vis, gray, vis & ~gray


def recolor(img: Image.Image, gray_to=None, teal_to=None, all_to=None) -> Image.Image:
    a = np.array(img).copy()
    vis, gray, teal = masks(a)
    if all_to is not None:
        a[vis, :3] = all_to
    if gray_to is not None:
        a[gray, :3] = gray_to
    if teal_to is not None:
        a[teal, :3] = teal_to
    return Image.fromarray(a)


def save(img: Image.Image, path: Path, width: int | None = None):
    if width:
        img = img.resize((width, round(img.size[1] * width / img.size[0])), Image.LANCZOS)
    img.save(path, optimize=True)
    print(f"wrote {path.relative_to(ROOT)} {img.size}")


src = Image.open(SRC).convert("RGBA")
arr = np.array(src)
cut = split(arr)
mark = trim(src.crop((0, 0, src.width, cut)), pad=8, square=True)
lockup = trim(src, pad=8)
word = src.crop((0, cut, src.width, src.height))
word_dark = recolor(word, gray_to=LIGHT_TEXT, teal_to=DARK_VISION)
lockup_dark_src = src.copy()
lockup_dark_src.paste(recolor(src.crop((0, 0, src.width, cut)), gray_to=LIGHT_TEXT), (0, 0))
lockup_dark_src.paste(word_dark, (0, cut))

variants = {"logo-mark": mark, "logo-mark-dark": recolor(mark, gray_to=LIGHT_TEXT), "logo-mark-mono": recolor(mark, all_to=np.array([255, 255, 255]))}
for name, img in variants.items():  # 512 master + 1x/2x for the 40 px header (srcset)
    save(img, BRAND / f"{name}.png", 512)
    save(img, BRAND / f"{name}-40.png", 40)
    save(img, BRAND / f"{name}-80.png", 80)
for name, img in {"logo-lockup": lockup, "logo-lockup-dark": trim(lockup_dark_src, pad=8)}.items():  # login: 288 px wide
    save(img, BRAND / f"{name}.png", 900)
    save(img, BRAND / f"{name}-288.png", 288)
    save(img, BRAND / f"{name}-576.png", 576)

for size, name in ((16, "favicon-16.png"), (32, "favicon-32.png"), (512, "logo-512.png")):
    save(mark, PUB / name, size)
touch = Image.new("RGBA", (180, 180), (255, 255, 255, 255))
m = mark.resize((150, 150), Image.LANCZOS)
touch.paste(m, (15, 15), m)
save(touch, PUB / "apple-touch-icon.png")
buf = io.BytesIO()
mark.resize((96, 96), Image.LANCZOS).save(buf, "PNG", optimize=True)
(PUB / "favicon.svg").write_text(
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96"><title>IronVision AI</title>'
    f'<image width="96" height="96" href="data:image/png;base64,{base64.b64encode(buf.getvalue()).decode()}"/></svg>\n')
print("wrote frontend/public/favicon.svg")
