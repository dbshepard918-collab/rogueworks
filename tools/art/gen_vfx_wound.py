"""Procedurally generate dedicated flesh-boss VFX frames for The Wound.

The final boss's hazards (blood_pool / vein_lash / heart_pulse) currently point
at generic `vfx_blood` / `vfx_shockwave` frames. This adds three distinct,
palette-locked VFX sprites (64x64, RGBA) and appends them to the vfx atlas so the
Heart of the Depths fight reads as flesh, not a borrowed fire/shockwave.

Output: ``assets/atlas/vfx.png`` + ``assets/atlas/vfx.json`` (appended).

Usage
-----
    python -m tools.art.gen_vfx_wound
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
PALETTE_PATH = ROOT / "assets" / "palette.json"
OUT_PNG = ROOT / "assets" / "atlas" / "vfx.png"
OUT_JSON = ROOT / "assets" / "atlas" / "vfx.json"

TILE = 64

_pal = json.loads(PALETTE_PATH.read_text(encoding="utf-8"))
_HEX = {k: tuple(int(v[i:i + 2], 16) for i in (1, 3, 5)) for k, v in _pal["colors"].items()}
_PAL_NAMES = list(_HEX.keys())
_PAL_RGB = np.array([_HEX[n] for n in _PAL_NAMES], dtype="int32")


def C(name):
    return _HEX[name]


def _snap_rgba(arr):
    h, w = arr.shape[:2]
    rgb = arr[:, :, :3].reshape(-1, 3).astype("int32")
    pal = _PAL_RGB.astype("int32")
    best_d = np.full((h * w,), 1 << 30, dtype="int64")
    best_i = np.zeros((h * w,), dtype="int32")
    for i in range(pal.shape[0]):
        d = ((rgb - pal[i]) ** 2).sum(axis=1)
        closer = d < best_d
        best_d[closer] = d[closer]
        best_i[closer] = i
    out = arr.copy()
    out[:, :, :3] = _PAL_RGB[best_i].reshape(h, w, 3).astype("uint8")
    return out


def _canvas():
    return Image.new("RGBA", (TILE, TILE), (0, 0, 0, 0))


def _disc(d, cx, cy, r, color, alpha=255):
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color + (alpha,))


def _ring(d, cx, cy, r, color, alpha=255, width=2):
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=color + (alpha,), width=width)


def _line(d, x0, y0, x1, y1, color, width=1, alpha=255):
    d.line([x0, y0, x1, y1], fill=color + (alpha,), width=width)


# --------------------------------------------------------------------------- #
# the three flesh-boss VFX
# --------------------------------------------------------------------------- #
def _blood_pool(d):
    # spreading pool of blood: red disc, darker centre, splatter drops
    blood = C("blood")
    dark = C("blood_dark")
    _disc(d, 32, 32, 24, blood, 180)
    _disc(d, 26, 28, 18, blood, 255)
    _disc(d, 32, 32, 12, dark, 220)
    _disc(d, 32, 32, 6, dark, 255)
    for dx, dy in ((18, -14), (-16, 12), (14, 16), (-12, -16), (0, -22)):
        _disc(d, 32 + dx, 32 + dy, 4, blood, 180)


def _vein_lash(d):
    # lashing vein: a curved red tendril with a pointed tip
    blood = C("blood")
    dark = C("blood_dark")
    pts = [(12, 48), (26, 36), (38, 30), (50, 22)]
    for i in range(len(pts) - 1):
        _line(d, pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1], blood, width=6)
    for i in range(len(pts) - 1):
        _line(d, pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1], dark, width=2)
    # pointed tip
    _disc(d, 50, 22, 3, blood, 255)
    _disc(d, 52, 20, 2, C("flesh"), 255)


def _heart_pulse(d):
    # pulsing heart: expanding ring + a small heart core
    glow = C("arcane_light")
    blood = C("blood")
    _ring(d, 32, 32, 26, glow, 200, width=3)
    _ring(d, 32, 32, 20, blood, 170, width=2)
    # small heart core
    _disc(d, 29, 28, 5, blood, 255)
    _disc(d, 35, 28, 5, blood, 255)
    _disc(d, 32, 34, 3, blood, 255)
    _disc(d, 32, 30, 4, C("white"), 255)


_VFX = [
    ("vfx_blood_pool", _blood_pool),
    ("vfx_vein_lash", _vein_lash),
    ("vfx_heart_pulse", _heart_pulse),
]


def _render(name, fn):
    img = _canvas()
    d = ImageDraw.Draw(img)
    fn(d)
    arr = np.array(img, dtype="uint8")
    arr = _snap_rgba(arr)
    return Image.fromarray(arr, mode="RGBA")


def main() -> int:
    new_sprites = [(name, _render(name, fn)) for name, fn in _VFX]

    atlas = Image.open(OUT_PNG).convert("RGBA")
    doc = json.loads(OUT_JSON.read_text(encoding="utf-8"))
    frames = doc["frames"]

    cols = 5
    old_w, old_h = atlas.size

    to_place = []
    for name, sprite in new_sprites:
        if name in frames:
            to_place.append((name, sprite, tuple(frames[name])))
        else:
            to_place.append((name, sprite, None))

    # Track which cells are already occupied so we never overwrite an
    # existing frame, and never shrink the sheet (the atlas may have gaps).
    occupied = set()
    for name, rect in frames.items():
        x, y, w, h = rect
        for r in range(y // TILE, (y + h + TILE - 1) // TILE):
            for c in range(x // TILE, (x + w + TILE - 1) // TILE):
                occupied.add((r, c))

    new_names = [n for n, _, pos in to_place if pos is None]
    free_cells = []
    r = 0
    while len(free_cells) < len(new_names):
        for c in range(cols):
            if (r, c) not in occupied:
                free_cells.append((r, c))
                if len(free_cells) >= len(new_names):
                    break
        r += 1

    new_w = cols * TILE
    new_h = max(old_h, (free_cells[-1][0] + 1) * TILE)

    sheet = Image.new("RGBA", (new_w, new_h), (0, 0, 0, 0))
    sheet.paste(atlas, (0, 0))

    for (name, sprite, pos), (r, c) in zip(
        [t for t in to_place if t[2] is None], free_cells
    ):
        x, y = c * TILE, r * TILE
        sheet.paste(sprite, (x, y))
        frames[name] = [x, y, TILE, TILE]

    sheet.save(OUT_PNG)
    doc["meta"]["generated_by"] = "procedural+wound"
    OUT_JSON.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    print("wrote %d flesh-boss VFX -> %s (%dx%d), %d frames total"
          % (len(to_place), OUT_PNG, new_w, new_h, len(frames)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
