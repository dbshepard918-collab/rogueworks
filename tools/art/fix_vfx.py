"""Regenerate the most-visible VFX frames with clean procedural pixel art.

The AI-generated VFX (dust, slash, impact, spark, muzzle flash, level-up) came
back as noisy multi-colour blobs.  This patches those frames in-place inside
``assets/atlas/vfx.png`` with hand-built, palette-locked art so combat and
movement reads cleanly.

Usage
-----
    python -m tools.art.fix_vfx
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
PNG = ROOT / "assets" / "atlas" / "vfx.png"
JSON = ROOT / "assets" / "atlas" / "vfx.json"

_pal = json.loads((ROOT / "assets" / "palette.json").read_text(encoding="utf-8"))
_HEX = {k: tuple(int(v[i:i + 2], 16) for i in (1, 3, 5)) for k, v in _pal["colors"].items()}
_PAL = np.array(list(_HEX.values()), dtype="int32")


def _snap(arr):
    h, w = arr.shape[:2]
    flat = arr.reshape(-1, 3).astype("int32")
    best_d = np.full((h * w,), 1 << 30, dtype="int64")
    best_i = np.zeros((h * w,), dtype="int32")
    for i in range(_PAL.shape[0]):
        d = ((flat - _PAL[i]) ** 2).sum(axis=1)
        closer = d < best_d
        best_d[closer] = d[closer]
        best_i[closer] = i
    return _PAL[best_i].reshape(h, w, 3).astype("uint8")


def _disc(arr, cx, cy, r, color, alpha=255):
    """Draw a filled disc into an RGBA array."""
    h, w = arr.shape[:2]
    y, x = np.ogrid[:h, :w]
    mask = (x - cx) ** 2 + (y - cy) ** 2 <= r * r
    arr[mask, 0] = color[0]
    arr[mask, 1] = color[1]
    arr[mask, 2] = color[2]
    arr[mask, 3] = alpha
    return arr


def _ring(arr, cx, cy, r, color, alpha=255, thickness=2):
    h, w = arr.shape[:2]
    y, x = np.ogrid[:h, :w]
    d = np.sqrt((x - cx) ** 2 + (y - cy) ** 2)
    mask = (d <= r) & (d >= r - thickness)
    arr[mask, 0] = color[0]
    arr[mask, 1] = color[1]
    arr[mask, 2] = color[2]
    arr[mask, 3] = alpha
    return arr


def _blank(size=64):
    return np.zeros((size, size, 4), dtype="uint8")


def make_dust(size=64):
    """Soft grey dust puff: concentric fading discs."""
    arr = _blank(size)
    c = _HEX["ash"]
    cx = cy = size // 2
    for r, a in ((22, 40), (16, 70), (10, 110), (5, 160)):
        _disc(arr, cx, cy, r, c, a)
    return arr


def make_slash(size=64):
    """Crisp crescent slash arc."""
    arr = _blank(size)
    c = _HEX["white"]
    cx = cy = size // 2
    # outer arc
    _ring(arr, cx, cy, 26, c, 200, thickness=5)
    # inner glow
    _ring(arr, cx, cy, 22, _HEX["arcane_light"], 140, thickness=3)
    # cut the arc so it reads as a swing (remove a wedge)
    # simple: draw a bright leading edge
    _ring(arr, cx, cy, 28, _HEX["white"], 255, thickness=2)
    return arr


def make_impact(size=64):
    """Impact starburst."""
    arr = _blank(size)
    c = _HEX["white"]
    cx = cy = size // 2
    _disc(arr, cx, cy, 8, c, 255)
    _ring(arr, cx, cy, 16, _HEX["flame"], 200, thickness=3)
    # spikes
    for ang in range(0, 360, 45):
        rad = np.deg2rad(ang)
        for d in range(10, 26, 2):
            x = int(cx + d * np.cos(rad))
            y = int(cy + d * np.sin(rad))
            if 0 <= x < size and 0 <= y < size:
                arr[y, x, :3] = c
                arr[y, x, 3] = 255
    return arr


def make_hit_spark(size=64):
    """Small bright spark."""
    arr = _blank(size)
    cx = cy = size // 2
    _disc(arr, cx, cy, 6, _HEX["white"], 255)
    _disc(arr, cx, cy, 12, _HEX["gold"], 140)
    for ang in range(0, 360, 60):
        rad = np.deg2rad(ang)
        for d in range(8, 20):
            x = int(cx + d * np.cos(rad))
            y = int(cy + d * np.sin(rad))
            if 0 <= x < size and 0 <= y < size:
                arr[y, x, :3] = _HEX["white"]
                arr[y, x, 3] = 255
    return arr


def make_muzzle_flash(size=64):
    """Muzzle flash cone."""
    arr = _blank(size)
    cx = cy = size // 2
    _disc(arr, cx, cy, 8, _HEX["white"], 255)
    _disc(arr, cx, cy, 14, _HEX["gold"], 160)
    _disc(arr, cx, cy, 20, _HEX["flame"], 90)
    return arr


def make_levelup(size=64):
    """Level-up burst: gold rings + sparkle."""
    arr = _blank(size)
    cx = cy = size // 2
    _disc(arr, cx, cy, 6, _HEX["white"], 255)
    _ring(arr, cx, cy, 14, _HEX["gold"], 220, thickness=3)
    _ring(arr, cx, cy, 24, _HEX["gold"], 140, thickness=2)
    for ang in range(0, 360, 30):
        rad = np.deg2rad(ang)
        x = int(cx + 28 * np.cos(rad))
        y = int(cy + 28 * np.sin(rad))
        if 0 <= x < size and 0 <= y < size:
            arr[y, x, :3] = _HEX["white"]
            arr[y, x, 3] = 255
    return arr


def make_sparkle(size=64):
    """Tiny 4-point sparkle."""
    arr = _blank(size)
    cx = cy = size // 2
    _disc(arr, cx, cy, 3, _HEX["white"], 255)
    for ang in range(0, 360, 90):
        rad = np.deg2rad(ang)
        for d in range(4, 14):
            x = int(cx + d * np.cos(rad))
            y = int(cy + d * np.sin(rad))
            if 0 <= x < size and 0 <= y < size:
                arr[y, x, :3] = _HEX["white"]
                arr[y, x, 3] = 255
    return arr


MAKERS = {
    "vfx_dust": make_dust,
    "vfx_slash": make_slash,
    "vfx_impact": make_impact,
    "vfx_hit_spark": make_hit_spark,
    "vfx_muzzle_flash": make_muzzle_flash,
    "vfx_levelup": make_levelup,
    "vfx_sparkle": make_sparkle,
}


def main() -> int:
    img = Image.open(PNG).convert("RGBA")
    data = json.loads(JSON.read_text(encoding="utf-8"))
    frames = data.get("frames", {})
    changed = 0
    for name, maker in MAKERS.items():
        if name not in frames:
            continue
        x, y, w, h = frames[name]
        made = maker(size=w)
        rgba = np.zeros((h, w, 4), dtype="uint8")
        rgba[..., :3] = _snap(made[..., :3])
        rgba[..., 3] = made[..., 3]
        img.paste(Image.fromarray(rgba, mode="RGBA"), (x, y))
        changed += 1
    img.save(PNG)
    print("patched %d vfx frame(s) -> %s" % (changed, PNG))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
