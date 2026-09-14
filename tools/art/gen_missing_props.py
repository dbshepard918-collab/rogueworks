"""Generate the 12 missing room-prop sprites as 32x32 pixel art using the locked palette.

Props needed (not present as sprite files at all):
  prop_kelp, prop_lava_vent, prop_pillar, prop_pillar_drowned, prop_pipes,
  prop_roots, prop_sarcophagus, prop_shop_stall, prop_shrine_drowned, prop_urn,
  prop_water_pool

Each sprite is 32x32, palette-locked, 1-bit alpha, drawn in the same style as the
existing props (small, centered, readable silhouette).
"""
from __future__ import annotations

import json
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]

PALETTE = json.loads((ROOT / "assets" / "palette.json").read_text())
C = {name: tuple(int(h[i:i+2], 16) for i in (1, 3, 5))
     for name, h in PALETTE["colors"].items()}

TRANSPARENT = (0, 0, 0, 0)

def _new():
    return Image.new("RGBA", (32, 32), TRANSPARENT)

def _put(img, x, y, color):
    if 0 <= x < 32 and 0 <= y < 32:
        img.putpixel((x, y), color)

def _rect(img, x0, y0, w, h, color):
    for y in range(y0, y0 + h):
        for x in range(x0, x0 + w):
            _put(img, x, y, color)

def _hline(img, x0, y, w, color):
    _rect(img, x0, y, w, 1, color)

def _vline(img, x, y0, h, color):
    _rect(img, x, y0, 1, h, color)

def _outline(img, x0, y0, w, h, color):
    _hline(img, x0, y0, w, color)
    _hline(img, x0, y0 + h - 1, w, color)
    _vline(img, x0, y0, h, color)
    _vline(img, x0 + w - 1, y0, h, color)


# ── prop_pillar: a stone column from floor to ceiling ───────────────────────
def make_pillar():
    img = _new()
    _outline(img, 10, 2, 12, 28, C["stone_light"])
    _rect(img, 11, 3, 10, 26, C["stone"])
    # base
    _rect(img, 8, 26, 16, 4, C["stone_dark"])
    _rect(img, 9, 27, 14, 2, C["stone"])
    # capital
    _rect(img, 8, 2, 16, 3, C["stone_dark"])
    _rect(img, 9, 3, 14, 1, C["stone"])
    # cracks
    _put(img, 14, 10, C["ink"])
    _put(img, 14, 11, C["ink"])
    _put(img, 18, 14, C["ink"])
    _put(img, 18, 15, C["ink"])
    return img

# ── prop_pillar_drowned: a pillar with kelp/water at base ───────────────────
def make_pillar_drowned():
    img = _new()
    _outline(img, 10, 2, 12, 24, C["stone_light"])
    _rect(img, 11, 3, 10, 22, C["stone"])
    _rect(img, 8, 2, 16, 3, C["stone_dark"])
    _rect(img, 9, 3, 14, 1, C["stone"])
    # water at base
    _rect(img, 6, 26, 20, 4, C["water"])
    _hline(img, 6, 26, 20, C["water_dark"])
    # kelp strands
    _vline(img, 8, 20, 6, C["moss"])
    _vline(img, 23, 22, 4, C["venom"])
    _vline(img, 7, 18, 8, C["venom_dark"])
    return img

# ── prop_rubble: scattered stone chunks ────────────────────────────────────
def make_rubble():
    img = _new()
    # a few chunky stones on the ground
    _rect(img, 6, 22, 6, 4, C["stone"])
    _outline(img, 6, 22, 6, 4, C["stone_dark"])
    _rect(img, 14, 20, 5, 6, C["stone_light"])
    _outline(img, 14, 20, 5, 6, C["stone"])
    _rect(img, 20, 24, 4, 3, C["stone_dark"])
    _rect(img, 9, 26, 4, 2, C["stone_dark"])
    _put(img, 7, 24, C["stone_light"])
    _put(img, 8, 25, C["stone_light"])
    _put(img, 19, 26, C["stone_light"])
    return img

# ── prop_urn: a funeral urn ────────────────────────────────────────────────
def make_urn():
    img = _new()
    # body
    _rect(img, 10, 12, 12, 16, C["stone"])
    _outline(img, 10, 12, 12, 16, C["stone_dark"])
    # neck
    _rect(img, 12, 8, 8, 5, C["stone"])
    _outline(img, 12, 8, 8, 5, C["stone_dark"])
    # lid
    _rect(img, 11, 6, 10, 3, C["stone_light"])
    _outline(img, 11, 6, 10, 3, C["stone_dark"])
    _put(img, 15, 4, C["stone_light"])
    _put(img, 16, 4, C["stone_light"])
    _put(img, 15, 5, C["stone_light"])
    _put(img, 16, 5, C["stone_light"])
    # base
    _rect(img, 9, 27, 14, 3, C["stone_dark"])
    # decorative band
    _hline(img, 11, 18, 10, C["bone"])
    _hline(img, 11, 19, 10, C["stone_dark"])
    return img

# ── prop_sarcophagus: a stone coffin ──────────────────────────────────────
def make_sarcophagus():
    img = _new()
    # body
    _rect(img, 6, 14, 20, 14, C["stone"])
    _outline(img, 6, 14, 20, 14, C["stone_dark"])
    # lid (raised)
    _rect(img, 8, 10, 16, 5, C["stone_light"])
    _outline(img, 8, 10, 16, 5, C["stone_dark"])
    # decorative top
    _rect(img, 10, 7, 12, 4, C["stone"])
    _outline(img, 10, 7, 12, 4, C["stone_dark"])
    _put(img, 15, 5, C["gold"])
    _put(img, 16, 5, C["gold"])
    _put(img, 15, 6, C["gold_dark"])
    _put(img, 16, 6, C["gold_dark"])
    # body decorations
    _hline(img, 8, 18, 16, C["stone_dark"])
    _hline(img, 8, 22, 16, C["stone_dark"])
    _put(img, 15, 19, C["bone"])
    _put(img, 16, 19, C["bone"])
    _put(img, 15, 23, C["bone"])
    _put(img, 16, 23, C["bone"])
    return img

# ── prop_kelp: tall strands of underwater plant ───────────────────────────
def make_kelp():
    img = _new()
    # several wavy strands from bottom
    for y in range(31, 8, -1):
        offset = int((y * 0.3) % 3) - 1
        _put(img, 10 + offset, y, C["venom"])
        _put(img, 10 + offset + 1, y, C["venom_dark"])
    for y in range(31, 10, -1):
        offset = int((y * 0.25) % 2)
        _put(img, 18 + offset, y, C["moss"])
        _put(img, 18 + offset + 1, y, C["venom"])
    for y in range(31, 14, -1):
        offset = int((y * 0.2) % 2)
        _put(img, 24 + offset, y, C["venom"])
    # some floating bits
    _put(img, 12, 12, C["moss"])
    _put(img, 20, 9, C["moss"])
    _put(img, 25, 14, C["venom_dark"])
    return img

# ── prop_lava_vent: a crack in the floor glowing with lava ─────────────────
def make_lava_vent():
    img = _new()
    # dark stone surround
    _rect(img, 4, 10, 24, 16, C["ember_dark"])
    _outline(img, 4, 10, 24, 16, C["ink"])
    # glowing crack
    _hline(img, 8, 14, 16, C["flame"])
    _hline(img, 8, 15, 16, C["ember"])
    _hline(img, 10, 16, 12, C["flame"])
    _hline(img, 10, 17, 12, C["ember"])
    _hline(img, 8, 18, 16, C["flame"])
    _hline(img, 8, 19, 16, C["ember"])
    _hline(img, 10, 20, 12, C["flame"])
    _hline(img, 10, 21, 12, C["ember"])
    _hline(img, 8, 22, 16, C["flame"])
    # bright core
    _put(img, 12, 16, C["flame"])
    _put(img, 20, 19, C["flame"])
    _put(img, 16, 18, C["flame"])
    _put(img, 14, 20, C["flame"])
    _put(img, 18, 22, C["flame"])
    return img

# ── prop_pipes: industrial metal pipes on a wall ──────────────────────────
def make_pipes():
    img = _new()
    # horizontal pipe
    _rect(img, 2, 12, 28, 4, C["steel"])
    _outline(img, 2, 12, 28, 4, C["slate"])
    # joints
    _rect(img, 8, 11, 3, 6, C["steel"])
    _rect(img, 20, 11, 3, 6, C["steel"])
    # vertical pipe
    _rect(img, 14, 2, 4, 14, C["steel"])
    _outline(img, 14, 2, 4, 14, C["slate"])
    # elbow
    _rect(img, 13, 14, 6, 4, C["steel"])
    _outline(img, 13, 14, 6, 4, C["slate"])
    # rivets
    _put(img, 6, 14, C["slate"])
    _put(img, 16, 5, C["slate"])
    _put(img, 16, 9, C["slate"])
    _put(img, 24, 14, C["slate"])
    # valve
    _rect(img, 24, 8, 4, 4, C["stone_dark"])
    _put(img, 25, 9, C["ember"])
    _put(img, 26, 10, C["ember"])
    return img

# ── prop_roots: tangled tree roots breaking through ────────────────────────
def make_roots():
    img = _new()
    # main root from top
    _vline(img, 12, 2, 18, C["venom_dark"])
    _vline(img, 13, 2, 18, C["venom_dark"])
    _vline(img, 14, 4, 14, C["venom"])
    # branching roots
    for y in range(6, 20):
        if y % 4 < 2:
            _put(img, 12 - (y // 6), y, C["venom_dark"])
            _put(img, 12 - (y // 6) + 1, y, C["venom"])
        if y % 5 < 2:
            _put(img, 15 + (y // 8), y, C["venom_dark"])
            _put(img, 15 + (y // 8) + 1, y, C["venom"])
    # ground spread
    _hline(img, 6, 26, 20, C["venom_dark"])
    _hline(img, 8, 27, 16, C["venom"])
    _hline(img, 10, 28, 12, C["venom_dark"])
    # tendrils
    _put(img, 18, 8, C["venom"])
    _put(img, 19, 9, C["venom"])
    _put(img, 20, 10, C["venom"])
    _put(img, 8, 14, C["venom"])
    _put(img, 22, 14, C["venom"])
    _put(img, 23, 15, C["venom_dark"])
    return img

# ── prop_shop_stall: a merchant's stall with a canopy ─────────────────────
def make_shop_stall():
    img = _new()
    # counter
    _rect(img, 4, 18, 24, 10, C["stone"])
    _outline(img, 4, 18, 24, 10, C["stone_dark"])
    _hline(img, 4, 22, 24, C["stone_dark"])
    # goods on counter
    _rect(img, 8, 16, 4, 3, C["gold"])
    _rect(img, 14, 15, 4, 4, C["blood"])
    _rect(img, 20, 16, 3, 3, C["arcane"])
    _put(img, 9, 15, C["gold_dark"])
    _put(img, 15, 14, C["blood_dark"])
    _put(img, 21, 15, C["arcane_light"])
    # canopy/awning
    _rect(img, 2, 6, 28, 3, C["ember"])
    _outline(img, 2, 6, 28, 3, C["ember_dark"])
    # canopy stripes
    for x in range(2, 30, 4):
        _vline(img, x, 6, 3, C["gold"])
    # posts
    _vline(img, 3, 6, 12, C["stone_dark"])
    _vline(img, 28, 6, 12, C["stone_dark"])
    # sign
    _rect(img, 12, 10, 8, 3, C["gold_dark"])
    _outline(img, 12, 10, 8, 3, C["ink"])
    return img

# ── prop_shrine_drowned: a submerged shrine with arcane glow ──────────────
def make_shrine_drowned():
    img = _new()
    # base
    _rect(img, 8, 22, 16, 8, C["stone"])
    _outline(img, 8, 22, 16, 8, C["stone_dark"])
    # pillar
    _rect(img, 12, 10, 8, 14, C["stone_light"])
    _outline(img, 12, 10, 8, 14, C["stone_dark"])
    # top altar
    _rect(img, 10, 6, 12, 5, C["stone"])
    _outline(img, 10, 6, 12, 5, C["stone_dark"])
    # arcane orb on top
    _rect(img, 14, 2, 4, 4, C["arcane"])
    _outline(img, 14, 2, 4, 4, C["arcane_light"])
    _put(img, 15, 3, C["soul"])
    _put(img, 16, 3, C["soul"])
    _put(img, 15, 4, C["arcane_light"])
    _put(img, 16, 4, C["arcane_light"])
    # water at base
    _rect(img, 6, 28, 20, 4, C["water"])
    _hline(img, 6, 28, 20, C["water_dark"])
    # glowing runes
    _put(img, 13, 16, C["soul"])
    _put(img, 18, 16, C["soul"])
    _put(img, 13, 20, C["soul"])
    _put(img, 18, 20, C["soul"])
    return img

# ── prop_water_pool: a pool of water on the floor ─────────────────────────
def make_water_pool():
    img = _new()
    # stone rim
    _rect(img, 4, 12, 24, 16, C["stone_dark"])
    _outline(img, 4, 12, 24, 16, C["stone"])
    # water
    _rect(img, 6, 14, 20, 12, C["water"])
    _outline(img, 6, 14, 20, 12, C["water_dark"])
    # ripples
    _hline(img, 9, 18, 6, C["water_dark"])
    _hline(img, 18, 21, 5, C["water_dark"])
    _hline(img, 10, 23, 4, C["water_dark"])
    _hline(img, 20, 17, 3, C["water_dark"])
    # highlights
    _put(img, 11, 16, C["steel"])
    _put(img, 22, 19, C["steel"])
    _put(img, 14, 22, C["steel"])
    return img


MAKERS = {
    "prop_pillar": make_pillar,
    "prop_pillar_drowned": make_pillar_drowned,
    "prop_rubble": make_rubble,
    "prop_urn": make_urn,
    "prop_sarcophagus": make_sarcophagus,
    "prop_kelp": make_kelp,
    "prop_lava_vent": make_lava_vent,
    "prop_pipes": make_pipes,
    "prop_roots": make_roots,
    "prop_shop_stall": make_shop_stall,
    "prop_shrine_drowned": make_shrine_drowned,
    "prop_water_pool": make_water_pool,
}


def main():
    out_dir = ROOT / "assets" / "sprites" / "props"
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, maker in MAKERS.items():
        img = maker()
        # flatten alpha to 1-bit
        pixels = list(img.getdata())
        flat = [(r, g, b, 255 if a > 0 else 0) for r, g, b, a in pixels]
        img.putdata(flat)
        img.save(out_dir / f"{name}.png")
        print(f"  wrote {name}.png")
    print(f"Generated {len(MAKERS)} prop sprites to {out_dir}")


if __name__ == "__main__":
    main()
