"""Procedurally generate dedicated flesh/viscera monster sprites for The Wound.

The 5th biome's minions and boss currently reuse generic sprites from other
biomes (putrid_ghoul, mire_hulk, coral_leviathan). This generates distinct,
palette-locked flesh silhouettes (64x64, RGBA with alpha transparency) and
appends them to the monsters atlas so the biome reads as *flesh*, not borrowed
art.

Everything is deterministic (no RNG) and every opaque pixel is snapped to the
locked vaelmoor palette, so ``tools.art.verify`` stays green.

Output: ``assets/atlas/monsters.png`` + ``assets/atlas/monsters.json`` (appended).

Usage
-----
    python -m tools.art.gen_monsters_flesh
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
PALETTE_PATH = ROOT / "assets" / "palette.json"
OUT_PNG = ROOT / "assets" / "atlas" / "monsters.png"
OUT_JSON = ROOT / "assets" / "atlas" / "monsters.json"

TILE = 64

_pal = json.loads(PALETTE_PATH.read_text(encoding="utf-8"))
_HEX = {k: tuple(int(v[i:i + 2], 16) for i in (1, 3, 5)) for k, v in _pal["colors"].items()}
_PAL_NAMES = list(_HEX.keys())
_PAL_RGB = np.array([_HEX[n] for n in _PAL_NAMES], dtype="int32")


def C(name):
    return _HEX[name]


def _snap_rgba(arr):
    """Snap RGB channels to the nearest palette colour, preserving alpha."""
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


# --------------------------------------------------------------------------- #
# drawing helpers (PIL ImageDraw on a transparent RGBA canvas)
# --------------------------------------------------------------------------- #
def _canvas():
    return Image.new("RGBA", (TILE, TILE), (0, 0, 0, 0))


def _disc(d, cx, cy, r, color, alpha=255):
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color + (alpha,))


def _ellipse(d, x0, y0, x1, y1, color, alpha=255):
    d.ellipse([x0, y0, x1, y1], fill=color + (alpha,))


def _line(d, x0, y0, x1, y1, color, width=1, alpha=255):
    d.line([x0, y0, x1, y1], fill=color + (alpha,), width=width)


def _poly(d, pts, color, alpha=255):
    d.polygon(pts, fill=color + (alpha,))


def _eye(d, cx, cy, r, glow=None):
    """A simple eye: white sclera + dark pupil (or a glowing core)."""
    _disc(d, cx, cy, r, C("white"))
    if glow is not None:
        _disc(d, cx, cy, max(1, r - 1), glow)
    else:
        _disc(d, cx, cy, max(1, r - 2), C("void"))


# --------------------------------------------------------------------------- #
# the nine flesh monsters
# --------------------------------------------------------------------------- #
def _flesh_spawn(d):
    # small amorphous blob with a single large eye
    body = C("flesh")
    dark = C("blood_dark")
    _disc(d, 32, 34, 20, body)
    _disc(d, 24, 26, 12, body)
    _disc(d, 42, 26, 11, body)
    _disc(d, 32, 44, 14, body)
    # mottling
    _disc(d, 20, 36, 5, dark)
    _disc(d, 44, 40, 5, dark)
    _disc(d, 32, 20, 4, dark)
    # single large eye
    _eye(d, 32, 32, 7, glow=C("soul"))


def _wound_maggot(d):
    # horizontal segmented worm with a round mouth
    body = C("flesh")
    dark = C("blood_dark")
    seg = C("blood")
    _ellipse(d, 8, 24, 56, 42, body)
    # segments
    for x in range(16, 52, 8):
        _line(d, x, 24, x, 42, seg, width=2)
    # mouth (round, dark, teeth)
    _disc(d, 10, 33, 6, dark)
    _poly(d, [(10, 28), (12, 30), (10, 32), (12, 34), (10, 36)], C("bone"))
    # tiny eyes
    _disc(d, 46, 28, 2, C("white"))
    _disc(d, 50, 36, 2, C("white"))


def _vein_lurker(d):
    # spindly elongated body with long trailing tendrils (ambusher)
    body = C("flesh")
    dark = C("blood_dark")
    blood = C("blood")
    # thin vertical body
    _ellipse(d, 26, 12, 38, 50, body)
    # long spindly tendrils trailing down and out
    _line(d, 28, 38, 14, 56, blood, width=2)
    _line(d, 36, 38, 50, 56, blood, width=2)
    _line(d, 28, 40, 20, 60, blood, width=2)
    _line(d, 36, 40, 44, 60, blood, width=2)
    # short tendrils up top
    _line(d, 30, 16, 22, 6, blood, width=2)
    _line(d, 34, 16, 42, 6, blood, width=2)
    # dark core
    _disc(d, 32, 30, 5, dark)
    # eyes
    _disc(d, 28, 24, 3, C("white"))
    _disc(d, 36, 24, 3, C("white"))
    _disc(d, 28, 24, 1, C("void"))
    _disc(d, 36, 24, 1, C("void"))


def _heart_thrall(d):
    # fleshy mass with a visible beating heart core
    body = C("flesh")
    dark = C("blood_dark")
    blood = C("blood")
    # torso
    _ellipse(d, 16, 12, 48, 54, body)
    # stubby arms
    _ellipse(d, 8, 22, 20, 40, body)
    _ellipse(d, 44, 22, 56, 40, body)
    # darker under-shadow
    _ellipse(d, 20, 40, 44, 54, dark)
    # beating heart (glowing core)
    _disc(d, 32, 30, 9, blood)
    _disc(d, 28, 26, 5, C("arcane_light"))
    _disc(d, 36, 26, 5, C("arcane_light"))
    _poly(d, [(28, 32), (36, 32), (32, 40)], C("arcane_light"))
    # eyes
    _disc(d, 24, 20, 3, C("white"))
    _disc(d, 40, 20, 3, C("white"))


def _pulse_caller(d):
    # floating orb with radiating veins and a central eye
    body = C("flesh")
    vein = C("blood")
    dark = C("blood_dark")
    # radiating veins
    import math
    for ang in range(0, 360, 30):
        a = math.radians(ang)
        x1 = 32 + math.cos(a) * 24
        y1 = 32 + math.sin(a) * 24
        _line(d, 32, 32, x1, y1, vein, width=2)
    # orb
    _disc(d, 32, 32, 15, body)
    _disc(d, 32, 32, 11, dark)
    # central eye
    _eye(d, 32, 32, 6, glow=C("soul"))


def _viscera_brute(d):
    # wide hulking mass with arms and a gaping mouth
    body = C("blood_dark")
    hi = C("blood")
    flesh = C("flesh")
    # wide body
    _ellipse(d, 10, 16, 54, 56, body)
    _ellipse(d, 14, 20, 50, 52, hi)
    # arms
    _ellipse(d, 4, 22, 18, 48, body)
    _ellipse(d, 46, 22, 60, 48, body)
    # gaping mouth with teeth
    _ellipse(d, 20, 30, 44, 48, C("void"))
    for x in range(22, 44, 4):
        _poly(d, [(x, 30), (x + 2, 30), (x + 1, 34)], C("bone"))
    # small eyes
    _disc(d, 24, 22, 3, C("white"))
    _disc(d, 40, 22, 3, C("white"))
    # flesh highlight
    _ellipse(d, 22, 16, 42, 22, flesh)


def _wound_horror(d):
    # vertical gaping maw with teeth and tentacles
    body = C("flesh")
    dark = C("blood_dark")
    blood = C("blood")
    # tentacles around the maw
    import math
    for ang in (20, 160, 200, 340):
        a = math.radians(ang)
        x1 = 32 + math.cos(a) * 28
        y1 = 32 + math.sin(a) * 28
        _line(d, 32, 32, x1, y1, blood, width=4)
    # body
    _disc(d, 32, 32, 20, body)
    # vertical maw
    _ellipse(d, 24, 14, 40, 50, C("void"))
    # teeth top and bottom
    for y in (14, 44):
        for x in range(26, 40, 4):
            _poly(d, [(x, y), (x + 2, y), (x + 1, y + 5)], C("bone"))
    # eyes on the sides
    _disc(d, 16, 26, 3, C("white"))
    _disc(d, 48, 26, 3, C("white"))
    _disc(d, 16, 38, 3, C("white"))
    _disc(d, 48, 38, 3, C("white"))


def _flesh_weaver(d):
    # central mass with many thin tendrils and multiple eyes
    body = C("flesh")
    tendril = C("blood")
    dark = C("blood_dark")
    # many thin tendrils
    import math
    for ang in range(0, 360, 24):
        a = math.radians(ang)
        x1 = 32 + math.cos(a) * 28
        y1 = 32 + math.sin(a) * 28
        _line(d, 32, 32, x1, y1, tendril, width=2)
    # central mass
    _disc(d, 32, 32, 13, body)
    _disc(d, 32, 32, 9, dark)
    # multiple eyes
    _disc(d, 26, 28, 3, C("white"))
    _disc(d, 38, 28, 3, C("white"))
    _disc(d, 32, 36, 3, C("white"))
    for ex, ey in ((26, 28), (38, 28), (32, 36)):
        _disc(d, ex, ey, 1, C("void"))


def _the_wound(d):
    # the Heart of the Depths: a clear heart with an aorta and a glowing core
    body = C("blood")
    dark = C("blood_dark")
    flesh = C("flesh")
    glow = C("arcane_light")
    # heart: two lobes + a point at the bottom
    _disc(d, 24, 22, 14, body)
    _disc(d, 40, 22, 14, body)
    _poly(d, [(14, 26), (50, 26), (32, 54)], body)
    # aorta: a single major artery rising from the top
    _line(d, 32, 8, 32, 22, dark, width=6)
    _line(d, 26, 14, 38, 14, dark, width=4)
    _line(d, 30, 18, 34, 18, dark, width=3)
    # a couple of veins on the heart
    _line(d, 24, 22, 30, 30, dark, width=2)
    _line(d, 40, 22, 34, 30, dark, width=2)
    # inner flesh highlight
    _disc(d, 24, 22, 9, flesh)
    _disc(d, 40, 22, 9, flesh)
    _poly(d, [(20, 28), (44, 28), (32, 46)], flesh)
    # glowing core
    _disc(d, 32, 28, 7, glow)
    _disc(d, 32, 28, 4, C("white"))


_MONSTERS = [
    ("monster_flesh_spawn", _flesh_spawn),
    ("monster_wound_maggot", _wound_maggot),
    ("monster_vein_lurker", _vein_lurker),
    ("monster_heart_thrall", _heart_thrall),
    ("monster_pulse_caller", _pulse_caller),
    ("monster_viscera_brute", _viscera_brute),
    ("monster_wound_horror", _wound_horror),
    ("monster_flesh_weaver", _flesh_weaver),
    ("monster_the_wound", _the_wound),
]


def _render(name, fn):
    img = _canvas()
    d = ImageDraw.Draw(img)
    fn(d)
    arr = np.array(img, dtype="uint8")
    arr = _snap_rgba(arr)
    return Image.fromarray(arr, mode="RGBA")


def main() -> int:
    # render the nine new sprites
    new_sprites = [(name, _render(name, fn)) for name, fn in _MONSTERS]

    # load the existing atlas
    atlas = Image.open(OUT_PNG).convert("RGBA")
    doc = json.loads(OUT_JSON.read_text(encoding="utf-8"))
    frames = doc["frames"]

    cols = 16
    old_w, old_h = atlas.size
    old_count = len(frames)

    # flesh frames overwrite any existing slot; new ones are appended.
    to_place = []
    for name, sprite in new_sprites:
        if name in frames:
            to_place.append((name, sprite, tuple(frames[name])))
        else:
            to_place.append((name, sprite, None))

    # figure out the final sheet size (append new frames after existing ones)
    new_names = [n for n, _, pos in to_place if pos is None]
    total = old_count + len(new_names)
    rows = (total + cols - 1) // cols
    new_w = cols * TILE
    new_h = rows * TILE

    sheet = Image.new("RGBA", (new_w, new_h), (0, 0, 0, 0))
    sheet.paste(atlas, (0, 0))

    idx = old_count
    for name, sprite, pos in to_place:
        if pos is None:
            r, c = divmod(idx, cols)
            pos = (c * TILE, r * TILE)
            idx += 1
        x, y = pos[0], pos[1]
        sheet.paste(sprite, (x, y))
        frames[name] = [x, y, TILE, TILE]
        sprite.save(ROOT / "assets" / "sprites" / "monsters" / (name + ".png"))

    sheet.save(OUT_PNG)
    doc["meta"]["generated_by"] = "procedural+flesh"
    OUT_JSON.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    print("wrote %d flesh monster(s) -> %s (%dx%d), %d frames total"
          % (len(to_place), OUT_PNG, new_w, new_h, len(frames)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
