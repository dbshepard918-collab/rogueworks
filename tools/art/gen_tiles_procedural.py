"""Procedurally generate a clean, readable dark-fantasy dungeon tileset.

Replaces the flat AI-downscaled tiles with hand-built pixel art that actually
reads as a dungeon: stone floors with grout, brick walls with a lit top edge,
descending staircases, framed doors, pools, pillars and props.

Everything is deterministic (seeded hashes, no RNG) and every pixel is snapped
to the locked vaelmoor palette, so ``tools.art.verify`` stays green.

Output: ``assets/atlas/tiles.png`` + ``assets/atlas/tiles.json`` (64x64 cells).

Usage
-----
    python -m tools.art.gen_tiles_procedural
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
PALETTE_PATH = ROOT / "assets" / "palette.json"
OUT_PNG = ROOT / "assets" / "atlas" / "tiles.png"
OUT_JSON = ROOT / "assets" / "atlas" / "tiles.json"

TILE = 64

# --------------------------------------------------------------------------- #
# palette
# --------------------------------------------------------------------------- #
_pal = json.loads(PALETTE_PATH.read_text(encoding="utf-8"))
_HEX = {k: tuple(int(v[i:i + 2], 16) for i in (1, 3, 5)) for k, v in _pal["colors"].items()}
_PAL_NAMES = list(_HEX.keys())
_PAL_RGB = np.array([_HEX[n] for n in _PAL_NAMES], dtype="int16")


def C(name):
    return _HEX[name]


def _snap(arr):
    """Snap an HxWx3 int array to the nearest locked palette colour."""
    h, w = arr.shape[:2]
    flat = arr.reshape(-1, 3).astype("int32")
    pal = _PAL_RGB.astype("int32")
    best_d = np.full((h * w,), 1 << 30, dtype="int64")
    best_i = np.zeros((h * w,), dtype="int32")
    for i in range(pal.shape[0]):
        d = ((flat - pal[i]) ** 2).sum(axis=1)
        closer = d < best_d
        best_d[closer] = d[closer]
        best_i[closer] = i
    return _PAL_RGB[best_i].reshape(h, w, 3).astype("uint8")


def _blank():
    return np.zeros((TILE, TILE, 3), dtype="uint8")


def _fill(arr, color, rect=None):
    if rect is None:
        rect = (0, 0, TILE, TILE)
    x0, y0, x1, y1 = rect
    arr[y0:y1, x0:x1] = color
    return arr


def _hash(x, y, salt=0):
    h = (x * 73856093) ^ (y * 19349663) ^ (salt * 83492791)
    return abs(h)


def _vary(color, amount, salt):
    """Deterministically nudge a colour by a small amount, then snap later."""
    r, g, b = color
    n = (_hash(salt, 7, 3) % (amount * 2 + 1)) - amount
    return (max(0, min(255, r + n)), max(0, min(255, g + n)), max(0, min(255, b + n)))


# --------------------------------------------------------------------------- #
# biome themes
# --------------------------------------------------------------------------- #
THEMES = {
    "catacombs": {
        "floor": C("stone_dark"), "floor_hi": C("stone"), "floor_lo": C("ink"),
        "grout": C("ink"), "wall": C("stone"), "wall_hi": C("stone_light"),
        "wall_lo": C("stone_dark"), "accent": C("bone"), "hazard": C("blood"),
        "glow": C("flame"), "water": C("water"), "metal": C("steel"),
        "wood": C("gold_dark"), "dark": C("void"),
    },
    "ember": {
        "floor": C("ember_dark"), "floor_hi": C("ember"), "floor_lo": C("blood_dark"),
        "grout": C("ink"), "wall": C("stone_dark"), "wall_hi": C("stone"),
        "wall_lo": C("ink"), "accent": C("flame"), "hazard": C("ember"),
        "glow": C("flame"), "water": C("water"), "metal": C("steel"),
        "wood": C("gold_dark"), "dark": C("void"),
    },
    "drowned": {
        "floor": C("water_dark"), "floor_hi": C("water"), "floor_lo": C("ink"),
        "grout": C("ink"), "wall": C("stone_dark"), "wall_hi": C("stone"),
        "wall_lo": C("ink"), "accent": C("soul"), "hazard": C("water"),
        "glow": C("soul"), "water": C("water"), "metal": C("steel"),
        "wood": C("gold_dark"), "dark": C("void"),
    },
    "ossuary": {
        "floor": C("stone_dark"), "floor_hi": C("ash"), "floor_lo": C("ink"),
        "grout": C("ink"), "wall": C("stone"), "wall_hi": C("bone"),
        "wall_lo": C("stone_dark"), "accent": C("bone"), "hazard": C("blood"),
        "glow": C("arcane_light"), "water": C("water"), "metal": C("steel"),
        "wood": C("gold_dark"), "dark": C("void"),
    },
    "wound": {
        "floor": C("flesh"), "floor_hi": C("bone"), "floor_lo": C("blood_dark"),
        "grout": C("blood_dark"), "wall": C("blood_dark"), "wall_hi": C("blood"),
        "wall_lo": C("void"), "accent": C("blood"), "hazard": C("blood"),
        "glow": C("arcane_light"), "water": C("blood"), "metal": C("bone"),
        "wood": C("gold_dark"), "dark": C("void"),
        "flesh": True,
    },
}

TILESETS = ["catacombs", "ember", "drowned", "ossuary", "wound"]

# tile type -> generator function (theme, salt) -> HxWx3 array
_TYPES = (
    "floor", "floor_alt", "floor_alt2", "floor_rubble", "floor_cracked",
    "floor_blood", "floor_bones", "floor_coins", "wall", "wall_alt",
    "wall_torch", "wall_corner", "wall_decor", "wall_cracked", "wall_skull",
    "doorway", "door", "door_open", "stairs_down", "stairs_up", "pillar",
    "pool", "pool_alt", "grate", "brazier", "slab", "gate", "rune_floor",
    "shrine_floor", "treasure_floor", "pit", "barricade", "floor_burning",
    "floor_water",
)


# --------------------------------------------------------------------------- #
# drawing primitives
# --------------------------------------------------------------------------- #
def _stone_floor(t, salt, alt=0):
    """Brick-pattern stone floor with grout lines and speckle."""
    arr = _blank()
    base = t["floor"]
    hi = t["floor_hi"]
    lo = t["floor_lo"]
    grout = t["grout"]
    _fill(arr, grout)
    brick_h = 16
    for row in range(4):
        offset = (row % 2) * 16
        for col in range(-1, 5):
            x0 = col * 32 + offset
            y0 = row * brick_h
            # stone body
            shade = _vary(base, 6, _hash(col, row, salt + alt * 97))
            _fill(arr, shade, (x0 + 1, y0 + 1, x0 + 31, y0 + brick_h - 1))
            # top highlight
            _fill(arr, _vary(hi, 4, _hash(col, row, salt + 5)), (x0 + 1, y0 + 1, x0 + 31, y0 + 3))
            # bottom shadow
            _fill(arr, lo, (x0 + 1, y0 + brick_h - 2, x0 + 31, y0 + brick_h - 1))
    # speckle
    for i in range(40):
        x = _hash(i, salt, 11) % TILE
        y = _hash(i, salt, 13) % TILE
        arr[y, x] = _vary(lo, 4, _hash(x, y, salt + 21))
    return arr


def _wall(t, salt, alt=0):
    """Brick wall with a lit top edge and darker base."""
    arr = _blank()
    wall = t["wall"]
    hi = t["wall_hi"]
    lo = t["wall_lo"]
    grout = t["grout"]
    _fill(arr, grout)
    brick_h = 8
    for row in range(8):
        offset = (row % 2) * 16
        for col in range(-1, 5):
            x0 = col * 32 + offset
            y0 = row * brick_h
            shade = _vary(wall, 6, _hash(col, row, salt + alt * 53))
            _fill(arr, shade, (x0 + 1, y0 + 1, x0 + 31, y0 + brick_h - 1))
            # top edge highlight (lit from above) — brighter and thicker
            _fill(arr, _vary(hi, 4, _hash(col, row, salt + 7)), (x0 + 1, y0 + 1, x0 + 31, y0 + 3))
            # bottom shade
            _fill(arr, lo, (x0 + 1, y0 + brick_h - 2, x0 + 31, y0 + brick_h - 1))
    # darker base band
    _fill(arr, lo, (0, 58, TILE, TILE))
    return arr


def _flesh_floor(t, salt, alt=0):
    """Organic flesh floor: mottled tissue with darker veins (not brick)."""
    arr = _blank()
    base = t["floor"]
    lo = t["floor_lo"]
    grout = t["grout"]
    hi = t["floor_hi"]
    _fill(arr, base)
    # mottled tissue: scattered darker blotches of varying size
    for i in range(70):
        x = _hash(i, salt + alt * 97, 11) % TILE
        y = _hash(i, salt + alt * 97, 13) % TILE
        r = 1 + _hash(i, salt, 17) % 3
        shade = _vary(lo, 5, _hash(x, y, salt + alt * 31))
        _fill(arr, shade, (x - r, y - r, x + r + 1, y + r + 1))
    # veins: wavy darker threads running down the tile
    for v in range(5):
        x = 6 + _hash(v, salt, 41) % 52
        y = 0
        while y < TILE:
            x += (_hash(v, y, salt + 53) % 5) - 2
            x = max(2, min(TILE - 3, x))
            arr[y, x] = _vary(grout, 2, _hash(x, y, salt + 61))
            arr[y, x + 1] = _vary(grout, 2, _hash(x, y, salt + 67))
            y += 1
    # sparse wet-sheen highlights
    for i in range(20):
        x = _hash(i, salt, 71) % TILE
        y = _hash(i, salt, 73) % TILE
        arr[y, x] = _vary(hi, 3, _hash(x, y, salt + 79))
    return arr


def _flesh_wall(t, salt, alt=0):
    """Organic flesh wall: vertical muscle striations with a lit top edge."""
    arr = _blank()
    wall = t["wall"]
    hi = t["wall_hi"]
    lo = t["wall_lo"]
    grout = t["grout"]
    _fill(arr, wall)
    # vertical muscle striations
    for x in range(TILE):
        if _hash(x, salt + alt * 53, 3) % 3 == 0:
            _fill(arr, _vary(lo, 4, _hash(x, salt, 7)), (x, 0, x + 1, TILE))
    # lit top edge (flesh catches light from above)
    _fill(arr, _vary(hi, 4, _hash(0, salt, 7)), (0, 0, TILE, 4))
    # darker base band
    _fill(arr, lo, (0, 56, TILE, TILE))
    # veins
    for v in range(3):
        x = 8 + _hash(v, salt, 41) % 48
        y = 0
        while y < TILE:
            x += (_hash(v, y, salt + 53) % 5) - 2
            x = max(2, min(TILE - 3, x))
            arr[y, x] = _vary(grout, 2, _hash(x, y, salt + 61))
            y += 1
    return arr


def _base_floor(t, salt, alt=0):
    """Flesh theme gets an organic floor; every other theme gets stone brick."""
    if t.get("flesh"):
        return _flesh_floor(t, salt, alt)
    return _stone_floor(t, salt, alt)


def _base_wall(t, salt, alt=0):
    """Flesh theme gets an organic wall; every other theme gets stone brick."""
    if t.get("flesh"):
        return _flesh_wall(t, salt, alt)
    return _wall(t, salt, alt)


def _stairs(t, salt, up=False):
    """A staircase: high-contrast treads + risers narrowing toward the bottom."""
    arr = _blank()
    hi = t["floor_hi"]
    dark = t["dark"]
    accent = t["accent"]
    # dark stairwell opening
    _fill(arr, dark, (0, 0, TILE, TILE))
    # side walls framing the well (angled inward for depth)
    for i in range(TILE):
        inset = int(10 + (i / TILE) * 6)
        _fill(arr, t["wall"], (0, i, inset, i + 1))
        _fill(arr, t["wall"], (TILE - inset, i, TILE, i + 1))
    # steps: 8 treads, top (near viewer) wide+light -> bottom narrow+dark
    n = 8
    for i in range(n):
        tval = i / (n - 1)
        if up:
            tval = 1.0 - tval
        half_w = int(24 - tval * 10)
        x0 = 32 - half_w
        x1 = 32 + half_w
        y0 = 4 + i * 7
        # tread: light, fading to dark toward the bottom
        c0 = np.array(hi, dtype="float32")
        c1 = np.array(dark, dtype="float32")
        tread = tuple(int(v) for v in (c0 * (1 - tval) + c1 * tval))
        _fill(arr, tread, (x0, y0, x1, y0 + 4))
        # riser: dark shadow band (strong contrast against the tread)
        _fill(arr, dark, (x0, y0 + 4, x1, y0 + 6))
    # accent glow at the bottom of the descent
    _fill(arr, accent, (28, 60, 36, 62))
    return arr


def _doorway(t, salt):
    arr = _blank()
    _fill(arr, t["wall"])
    # archway opening (dark)
    _fill(arr, t["dark"], (16, 8, 48, 60))
    # arch top
    _fill(arr, t["wall_hi"], (12, 6, 52, 10))
    _fill(arr, t["wall_hi"], (12, 6, 52, 8))
    return arr


def _door(t, salt):
    arr = _blank()
    _fill(arr, t["wall"])
    # door frame
    _fill(arr, t["wall_hi"], (14, 6, 50, 60))
    _fill(arr, t["wall_lo"], (14, 6, 50, 8))
    # wooden/iron door body
    _fill(arr, t["wood"], (18, 10, 46, 58))
    # planks
    for x in (22, 30, 38):
        _fill(arr, t["wall_lo"], (x, 10, x + 2, 58))
    # iron bands
    _fill(arr, t["metal"], (18, 20, 46, 24))
    _fill(arr, t["metal"], (18, 42, 46, 46))
    # handle
    _fill(arr, t["accent"], (40, 32, 44, 36))
    return arr


def _door_open(t, salt):
    arr = _blank()
    _fill(arr, t["wall"])
    _fill(arr, t["dark"], (14, 6, 50, 60))
    _fill(arr, t["wall_hi"], (10, 4, 54, 10))
    return arr


def _pillar(t, salt):
    arr = _blank()
    _fill(arr, t["floor"])
    # column
    _fill(arr, t["wall"], (20, 8, 44, 60))
    _fill(arr, t["wall_hi"], (20, 8, 44, 12))
    _fill(arr, t["wall_lo"], (20, 52, 44, 60))
    # fluting
    _fill(arr, t["wall_lo"], (28, 12, 30, 52))
    _fill(arr, t["wall_lo"], (36, 12, 38, 52))
    # base
    _fill(arr, t["wall_hi"], (16, 56, 48, 60))
    return arr


def _pool(t, salt, alt=0):
    arr = _blank()
    _fill(arr, t["floor"])
    liquid = t["water"] if alt == 0 else t["hazard"]
    # pool border
    _fill(arr, t["wall"], (8, 8, 56, 56))
    _fill(arr, liquid, (12, 12, 52, 52))
    # ripples
    for i in range(6):
        y = 16 + i * 6
        _fill(arr, t["accent"], (14 + (i % 3) * 6, y, 50 - (i % 3) * 6, y + 1))
    return arr


def _grate(t, salt):
    arr = _blank()
    _fill(arr, t["floor"])
    _fill(arr, t["metal"], (10, 10, 54, 54))
    _fill(arr, t["dark"], (14, 14, 50, 50))
    for i in range(4):
        x = 16 + i * 10
        _fill(arr, t["metal"], (x, 14, x + 3, 50))
    for j in range(4):
        y = 16 + j * 10
        _fill(arr, t["metal"], (14, y, 50, y + 3))
    return arr


def _brazier(t, salt):
    arr = _blank()
    _fill(arr, t["floor"])
    # bowl
    _fill(arr, t["metal"], (22, 34, 42, 44))
    _fill(arr, t["metal"], (20, 30, 44, 34))
    # legs
    _fill(arr, t["metal"], (24, 44, 28, 54))
    _fill(arr, t["metal"], (36, 44, 40, 54))
    # flame
    _fill(arr, t["glow"], (28, 16, 36, 30))
    _fill(arr, C("gold"), (30, 20, 34, 28))
    _fill(arr, C("white"), (31, 24, 33, 28))
    return arr


def _slab(t, salt):
    arr = _blank()
    _fill(arr, t["floor"])
    _fill(arr, t["wall"], (10, 10, 54, 54))
    _fill(arr, t["wall_hi"], (10, 10, 54, 14))
    _fill(arr, t["wall_lo"], (10, 48, 54, 54))
    # chipped edges
    _fill(arr, t["floor"], (10, 10, 16, 16))
    _fill(arr, t["floor"], (48, 44, 54, 54))
    return arr


def _gate(t, salt):
    arr = _blank()
    _fill(arr, t["wall"])
    _fill(arr, t["dark"], (16, 8, 48, 60))
    for i in range(4):
        x = 18 + i * 8
        _fill(arr, t["metal"], (x, 8, x + 2, 60))
    _fill(arr, t["metal"], (16, 8, 48, 12))
    _fill(arr, t["metal"], (16, 40, 48, 44))
    return arr


def _floor_decor(t, salt, kind):
    arr = _base_floor(t, salt)
    accent = t["accent"]
    hazard = t["hazard"]
    if kind == "rubble":
        for i in range(8):
            x = _hash(i, salt, 31) % 56 + 4
            y = _hash(i, salt, 33) % 56 + 4
            _fill(arr, t["wall_hi"], (x, y, x + 4, y + 4))
            _fill(arr, t["wall_lo"], (x + 1, y + 1, x + 4, y + 4))
    elif kind == "cracked":
        x = 12
        y = 8
        for i in range(6):
            x += _hash(i, salt, 41) % 9 - 3
            y += 8
            _fill(arr, t["dark"], (x, y, x + 2, y + 6))
            _fill(arr, t["dark"], (x + 2, y + 2, x + 4, y + 3))
    elif kind == "blood":
        for i in range(10):
            x = _hash(i, salt, 51) % 48 + 6
            y = _hash(i, salt, 53) % 48 + 6
            _fill(arr, hazard, (x, y, x + 3, y + 3))
        _fill(arr, hazard, (24, 26, 40, 34))
    elif kind == "bones":
        for i in range(4):
            x = _hash(i, salt, 61) % 40 + 10
            y = _hash(i, salt, 63) % 40 + 10
            _fill(arr, accent, (x, y, x + 8, y + 3))
            _fill(arr, accent, (x + 2, y + 2, x + 6, y + 3))
    elif kind == "coins":
        for i in range(7):
            x = _hash(i, salt, 71) % 48 + 8
            y = _hash(i, salt, 73) % 48 + 8
            _fill(arr, C("gold"), (x, y, x + 4, y + 4))
            _fill(arr, C("gold_dark"), (x, y + 3, x + 4, y + 4))
    return arr


def _rune_floor(t, salt):
    arr = _base_floor(t, salt)
    glow = t["glow"]
    # circle rune
    cx, cy = 32, 32
    for y in range(TILE):
        for x in range(TILE):
            d = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5
            if 18 <= d <= 20:
                arr[y, x] = glow
            if 10 <= d <= 11:
                arr[y, x] = glow
    _fill(arr, glow, (31, 14, 33, 50))
    _fill(arr, glow, (14, 31, 50, 33))
    return arr


def _shrine_floor(t, salt):
    arr = _base_floor(t, salt)
    glow = t["glow"]
    accent = t["accent"]
    _fill(arr, glow, (28, 28, 36, 36))
    _fill(arr, accent, (30, 30, 34, 34))
    _fill(arr, glow, (20, 20, 24, 24))
    _fill(arr, glow, (40, 20, 44, 24))
    _fill(arr, glow, (20, 40, 24, 44))
    _fill(arr, glow, (40, 40, 44, 44))
    return arr


def _treasure_floor(t, salt):
    arr = _base_floor(t, salt)
    gold = C("gold")
    gd = C("gold_dark")
    _fill(arr, gd, (24, 26, 40, 40))
    _fill(arr, gold, (26, 28, 38, 38))
    _fill(arr, C("white"), (30, 30, 34, 32))
    return arr


def _pit(t, salt):
    arr = _blank()
    _fill(arr, t["floor"])
    _fill(arr, t["wall"], (8, 8, 56, 56))
    _fill(arr, t["dark"], (12, 12, 52, 52))
    _fill(arr, t["wall_hi"], (8, 8, 56, 10))
    return arr


def _barricade(t, salt):
    arr = _blank()
    _fill(arr, t["floor"])
    wood = t["wood"]
    _fill(arr, wood, (8, 22, 56, 28))
    _fill(arr, wood, (8, 38, 56, 44))
    _fill(arr, t["metal"], (8, 22, 56, 26))
    _fill(arr, t["metal"], (8, 38, 56, 42))
    for x in (12, 20, 28, 36, 44):
        _fill(arr, t["metal"], (x, 22, x + 2, 44))
    return arr


def _floor_burning(t, salt):
    arr = _base_floor(t, salt)
    flame = t["glow"]
    gold = C("gold")
    for i in range(8):
        x = _hash(i, salt, 81) % 44 + 8
        y = _hash(i, salt, 83) % 44 + 8
        _fill(arr, flame, (x, y, x + 5, y + 5))
        _fill(arr, gold, (x + 1, y + 1, x + 4, y + 4))
    return arr


def _floor_water(t, salt):
    arr = _base_floor(t, salt)
    water = t["water"]
    _fill(arr, water, (8, 8, 56, 56))
    for i in range(5):
        y = 14 + i * 8
        _fill(arr, t["accent"], (12 + (i % 2) * 8, y, 48, y + 1))
    return arr


def _wall_torch(t, salt):
    arr = _base_wall(t, salt)
    metal = t["metal"]
    glow = t["glow"]
    # bracket
    _fill(arr, metal, (28, 12, 36, 18))
    _fill(arr, metal, (30, 18, 34, 26))
    # torch head
    _fill(arr, t["wood"], (29, 26, 35, 34))
    # flame
    _fill(arr, glow, (30, 8, 34, 14))
    _fill(arr, C("gold"), (31, 10, 33, 14))
    return arr


def _wall_skull(t, salt):
    arr = _base_wall(t, salt)
    bone = t["accent"]
    _fill(arr, bone, (26, 22, 38, 34))
    _fill(arr, bone, (28, 20, 36, 22))
    _fill(arr, t["dark"], (29, 26, 31, 28))
    _fill(arr, t["dark"], (33, 26, 35, 28))
    _fill(arr, t["dark"], (31, 30, 33, 32))
    return arr


def _wall_cracked(t, salt):
    arr = _base_wall(t, salt)
    x, y = 18, 6
    for i in range(7):
        x += _hash(i, salt, 91) % 7 - 3
        y += 7
        _fill(arr, t["dark"], (x, y, x + 2, y + 5))
    return arr


def _wall_decor(t, salt):
    arr = _base_wall(t, salt)
    _fill(arr, t["wall_hi"], (24, 16, 40, 20))
    _fill(arr, t["wall_lo"], (26, 18, 38, 20))
    _fill(arr, t["accent"], (30, 18, 34, 20))
    return arr


def _wall_corner(t, salt):
    arr = _base_wall(t, salt)
    _fill(arr, t["wall_lo"], (0, 0, 8, TILE))
    _fill(arr, t["wall_hi"], (0, 0, 8, 3))
    return arr


# --------------------------------------------------------------------------- #
# dispatch
# --------------------------------------------------------------------------- #
def _generate_type(kind, t, salt):
    if kind == "floor":
        return _base_floor(t, salt)
    if kind == "floor_alt":
        return _base_floor(t, salt, alt=1)
    if kind == "floor_alt2":
        return _base_floor(t, salt, alt=2)
    if kind == "floor_rubble":
        return _floor_decor(t, salt, "rubble")
    if kind == "floor_cracked":
        return _floor_decor(t, salt, "cracked")
    if kind == "floor_blood":
        return _floor_decor(t, salt, "blood")
    if kind == "floor_bones":
        return _floor_decor(t, salt, "bones")
    if kind == "floor_coins":
        return _floor_decor(t, salt, "coins")
    if kind == "wall":
        return _base_wall(t, salt)
    if kind == "wall_alt":
        return _base_wall(t, salt, alt=1)
    if kind == "wall_torch":
        return _wall_torch(t, salt)
    if kind == "wall_corner":
        return _wall_corner(t, salt)
    if kind == "wall_decor":
        return _wall_decor(t, salt)
    if kind == "wall_cracked":
        return _wall_cracked(t, salt)
    if kind == "wall_skull":
        return _wall_skull(t, salt)
    if kind == "doorway":
        return _doorway(t, salt)
    if kind == "door":
        return _door(t, salt)
    if kind == "door_open":
        return _door_open(t, salt)
    if kind == "stairs_down":
        return _stairs(t, salt, up=False)
    if kind == "stairs_up":
        return _stairs(t, salt, up=True)
    if kind == "pillar":
        return _pillar(t, salt)
    if kind == "pool":
        return _pool(t, salt, alt=0)
    if kind == "pool_alt":
        return _pool(t, salt, alt=1)
    if kind == "grate":
        return _grate(t, salt)
    if kind == "brazier":
        return _brazier(t, salt)
    if kind == "slab":
        return _slab(t, salt)
    if kind == "gate":
        return _gate(t, salt)
    if kind == "rune_floor":
        return _rune_floor(t, salt)
    if kind == "shrine_floor":
        return _shrine_floor(t, salt)
    if kind == "treasure_floor":
        return _treasure_floor(t, salt)
    if kind == "pit":
        return _pit(t, salt)
    if kind == "barricade":
        return _barricade(t, salt)
    if kind == "floor_burning":
        return _floor_burning(t, salt)
    if kind == "floor_water":
        return _floor_water(t, salt)
    return _base_floor(t, salt)


def main() -> int:
    frames = []
    images = []
    salt = 0
    for tileset in TILESETS:
        t = THEMES[tileset]
        for kind in _TYPES:
            name = "tile_%s_%s" % (tileset, kind)
            arr = _generate_type(kind, t, salt)
            arr = _snap(arr)
            images.append((name, arr))
            salt += 1

    # pack into a grid (square-ish)
    n = len(images)
    cols = 16
    rows = (n + cols - 1) // cols
    sheet = np.zeros((rows * TILE, cols * TILE, 4), dtype="uint8")
    frames = {}
    for idx, (name, arr) in enumerate(images):
        r, c = divmod(idx, cols)
        x, y = c * TILE, r * TILE
        sheet[y:y + TILE, x:x + TILE, :3] = arr
        sheet[y:y + TILE, x:x + TILE, 3] = 255
        frames[name] = [x, y, TILE, TILE]

    OUT_PNG.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(sheet, mode="RGBA").save(OUT_PNG)
    doc = {
        "version": 1,
        "image": "assets/atlas/tiles.png",
        "meta": {"tile": TILE, "palette_version": _pal.get("version", 1),
                 "generated_by": "procedural"},
        "frames": frames,
    }
    OUT_JSON.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    print("generated %d tiles -> %s (%dx%d)" % (n, OUT_PNG, cols * TILE, rows * TILE))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
