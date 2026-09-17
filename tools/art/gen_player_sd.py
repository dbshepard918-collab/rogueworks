"""Regenerate the player (Lantern-Keeper) sprites with the local FLUX pipeline.

The shipped player is 32x32 Copilot art upscaled to 64x64, which reads as a
"basic humanoid" with no resemblance to the hooded lantern-keeper described in
the GDD.  This regenerates a small set of base poses (idle / walk / attack x 4
directions, plus hurt + dash) at 256x256 on a clean magenta key, then keys the
background, palette-locks to the vaelmoor palette and derives the full 47-frame
animation atlas (idle breath, 4-frame walk cycles, 3-phase attacks, hurt flash,
death collapse, dash) before packing it back into ``assets/atlas/player.png``.

Resumable: generated raw PNGs are cached under ``assets/raw/sd_cache/player_*``
so a re-run only regenerates missing sprites.

Usage
-----
    python -m tools.art.gen_player_sd --limit 2     # smoke test
    python -m tools.art.gen_player_sd               # full batch
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
from PIL import Image

from tools.art.gen_monsters_sd import (
    CACHE,
    generate,
    process,
    _snap_rgb,
    _pal,
)

ROOT = Path(__file__).resolve().parents[2]
OUT_PNG = ROOT / "assets" / "atlas" / "player.png"
OUT_JSON = ROOT / "assets" / "atlas" / "player.json"

TILE = 64

# The Lantern-Keeper: a lone adventurer in a tattered hooded cloak, face hidden
# in shadow, carrying a single glowing amber lantern.
CHARACTER = ("a hooded lantern-keeper in a tattered dark hooded cloak, pale face "
             "hidden in shadow beneath the hood, holding a glowing amber lantern")

NEGATIVE = ("drop shadow, ground shadow, glow, gradient background, white background, "
            "grey background, floor, vignette, blur, smooth shading, anti-aliased, "
            "photorealistic, 3d render, text, caption, label, letters, numbers, watermark, "
            "signature, grid lines, duplicate sprites, identical clones, extra limbs, "
            "missing limbs, deformed hands")


def _prompt(pose):
    return (
        "pixel art of a single %s, %s, dark fantasy roguelite, top-down "
        "three-quarter view, on a flat solid pure magenta #ff00ff background, "
        "hard aliased pixels, no anti-aliasing, flat 3-tone shading, high contrast, "
        "chunky readable silhouette, distinct shape, no text, no watermark"
        % (pose, CHARACTER)
    )


# Base poses to generate (18).  These are the raw source; the full 47-frame
# animation atlas is derived from them below.
BASE_SPECS = [
    ("idle_down", "standing facing the camera, front view, lantern held at chest height"),
    ("idle_up", "standing facing away, back view, hood and cloak seen from behind"),
    ("idle_left", "standing in profile facing left, lantern held at the side"),
    ("idle_right", "standing in profile facing right, lantern held at the side"),
    ("walk_down_0", "walking toward the camera, front three-quarter view, mid-stride, left leg forward"),
    ("walk_down_1", "walking toward the camera, front three-quarter view, mid-stride, right leg forward"),
    ("walk_up_0", "walking away, back three-quarter view, mid-stride"),
    ("walk_up_1", "walking away, back three-quarter view, opposite stride"),
    ("walk_left_0", "walking in profile to the left, mid-stride"),
    ("walk_left_1", "walking in profile to the left, opposite stride"),
    ("walk_right_0", "walking in profile to the right, mid-stride"),
    ("walk_right_1", "walking in profile to the right, opposite stride"),
    ("attack_down", "swinging a short blade toward the camera, front view, lantern raised"),
    ("attack_up", "swinging a short blade away, back view"),
    ("attack_left", "swinging a short blade to the left, profile"),
    ("attack_right", "swinging a short blade to the right, profile"),
    ("hurt_left", "reeling back in pain, profile facing left, staggered"),
    ("dash_right", "dashing forward to the right, leaning into the dash, profile"),
]

# Screen-space facing vectors, used to nudge attack anticipation/follow-through.
_FACING = {"down": (0, 1), "up": (0, -1), "left": (-1, 0), "right": (1, 0)}


# --------------------------------------------------------------------------- #
# derivation helpers (all palette-safe: shifts/rotations preserve colours,
# tints re-snap, fades only touch alpha)
# --------------------------------------------------------------------------- #
def _shift(cell, dx, dy):
    arr = np.asarray(cell)
    out = np.zeros_like(arr)
    src_y0, src_y1 = max(0, -dy), arr.shape[0] - max(0, dy)
    src_x0, src_x1 = max(0, -dx), arr.shape[1] - max(0, dx)
    dst_y0, dst_x0 = max(0, dy), max(0, dx)
    out[dst_y0:dst_y0 + (src_y1 - src_y0),
        dst_x0:dst_x0 + (src_x1 - src_x0)] = arr[src_y0:src_y1, src_x0:src_x1]
    return Image.fromarray(out, "RGBA")


def _bob(cell, dy):
    return _shift(cell, 0, dy)


def _tint(cell, color, amount):
    arr = np.asarray(cell).astype("int16")
    mask = arr[..., 3] > 0
    rgb = arr[..., :3].astype("int32")
    rgb[mask] = rgb[mask] * (1.0 - amount) + np.array(color, dtype="int32") * amount
    arr[..., :3] = _snap_rgb(rgb)
    return Image.fromarray(arr.astype("uint8"), "RGBA")


def _rotate(cell, angle):
    return cell.rotate(angle, resample=Image.NEAREST, expand=False)


def _fade(cell, factor):
    arr = np.asarray(cell).copy()
    arr[..., 3] = (arr[..., 3] * factor).astype("uint8")
    return Image.fromarray(arr, "RGBA")


def derive_frames(base):
    """Build the full 47-frame atlas from the 18 base poses.

    ``base`` is a dict {pose_name: 64x64 RGBA Image}.
    """
    frames = {}

    def put(name, img):
        frames[name] = img

    for d in ("down", "up", "left", "right"):
        idle = base["idle_%s" % d]
        put("player_idle_%s" % d, idle)
        put("player_idle_breath_%s_0" % d, idle)
        put("player_idle_breath_%s_1" % d, _bob(idle, 1))

        w0 = base["walk_%s_0" % d]
        w1 = base["walk_%s_1" % d]
        put("player_walk_%s_0" % d, w0)
        put("player_walk_%s_1" % d, w1)
        put("player_walk_%s_2" % d, _bob(w0, 1))
        put("player_walk_%s_3" % d, _bob(w1, 1))

        atk = base["attack_%s" % d]
        fx, fy = _FACING[d]
        put("player_attack_%s_0" % d, _shift(atk, -fx * 2, -fy * 2))
        put("player_attack_%s_1" % d, atk)
        put("player_attack_%s_2" % d, _shift(atk, fx * 2, fy * 2))

    hurt = base["hurt_left"]
    put("player_hurt_left_0", hurt)
    put("player_hurt_left_1", _tint(hurt, (140, 31, 52), 0.35))  # blood #8c1f34

    idle_down = base["idle_down"]
    fallen = _rotate(idle_down, 90)
    put("player_death_0", idle_down)
    put("player_death_1", fallen)
    put("player_death_2", _fade(fallen, 0.6))
    put("player_death_3", _fade(fallen, 0.3))

    put("player_dash_right", base["dash_right"])
    return frames


def pack(frames):
    """Pack frames into a grid and write player.png + player.json."""
    names = sorted(frames.keys())
    cols = 16
    rows = (len(names) + cols - 1) // cols
    sheet = Image.new("RGBA", (cols * TILE, rows * TILE), (0, 0, 0, 0))
    rects = {}
    for idx, name in enumerate(names):
        r, c = divmod(idx, cols)
        x, y = c * TILE, r * TILE
        sheet.paste(frames[name], (x, y))
        rects[name] = [x, y, TILE, TILE]

    OUT_PNG.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(OUT_PNG)
    doc = {
        "version": 1,
        "image": "assets/atlas/player.png",
        "meta": {"tile": TILE, "palette_version": _pal.get("version", 1),
                 "generated_by": "sd"},
        "frames": rects,
    }
    OUT_JSON.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    print("packed %d player frames -> %s" % (len(names), OUT_PNG))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m tools.art.gen_player_sd")
    ap.add_argument("--limit", type=int, default=0, help="only generate this many (smoke test, no pack)")
    ap.add_argument("--seed", type=int, default=7, help="base SD seed")
    args = ap.parse_args(argv)

    specs = list(BASE_SPECS)
    smoke = bool(args.limit)
    if args.limit:
        specs = specs[:args.limit]

    CACHE.mkdir(parents=True, exist_ok=True)

    base = {}
    t0 = time.time()
    for idx, (pose, desc) in enumerate(specs):
        raw = CACHE / ("player_%s.png" % pose)
        if not raw.exists():
            ok = generate(_prompt(desc), raw, args.seed + idx)
            if not ok:
                print("  FAILED %s" % pose)
                continue
        cell = process(raw)
        if cell is None:
            print("  EMPTY  %s" % pose)
            continue
        base[pose] = cell
        print("  [%3d/%d] %s" % (idx + 1, len(specs), pose), flush=True)

    if not base:
        print("no sprites generated")
        return 1

    if smoke:
        print("smoke test: %d base pose(s) generated to cache (atlas untouched)" % len(base))
        return 0

    frames = derive_frames(base)
    pack(frames)
    print("done in %.1fs" % (time.time() - t0))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
