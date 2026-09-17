"""Regenerate the 3 class-select portraits with the local FLUX pipeline.

The class-select screen is text-only; this adds a distinct bust portrait for
each starting loadout (Lantern Keeper / Grave Warden / Ash Dancer) so the
screen reads at a glance.  Portraits are generated at 256x256 on a clean
magenta key, palette-locked and centred into a 128x128 cell, then packed into
``assets/atlas/classes.png``.

Usage
-----
    python -m tools.art.gen_classes_sd
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from PIL import Image

from tools.art.gen_monsters_sd import (
    CACHE,
    generate,
    _snap_rgb,
    _pal,
)

ROOT = Path(__file__).resolve().parents[2]
OUT_PNG = ROOT / "assets" / "atlas" / "classes.png"
OUT_JSON = ROOT / "assets" / "atlas" / "classes.json"

CELL = 128

NEGATIVE = ("drop shadow, ground shadow, glow, gradient background, white background, "
            "grey background, floor, vignette, blur, smooth shading, anti-aliased, "
            "photorealistic, 3d render, text, caption, label, letters, numbers, watermark, "
            "signature, grid lines, duplicate sprites, identical clones, extra limbs, "
            "missing limbs, deformed hands")

CLASS_SPECS = [
    ("class_lantern_keeper",
     "a hooded lantern-keeper, pale face hidden in shadow beneath the hood, holding "
     "a glowing amber lantern, bust portrait, front view"),
    ("class_grave_warden",
     "an armored grave warden in heavy dark plate armor, holding a mace and a "
     "battered shield, bust portrait, front view"),
    ("class_ash_dancer",
     "an agile ash dancer in light flowing garb, twin curved daggers, embers "
     "trailing from her, bust portrait, front view"),
]


def _prompt(desc):
    return (
        "pixel art of a single %s, dark fantasy roguelite, bust portrait, "
        "on a flat solid pure magenta #ff00ff background, hard aliased pixels, "
        "no anti-aliasing, flat 3-tone shading, high contrast, chunky readable "
        "silhouette, distinct shape, no text, no watermark" % desc
    )


def process(path, size=CELL):
    """Key magenta, palette-lock, trim and centre into a size x size cell."""
    import numpy as np

    img = Image.open(path).convert("RGBA")
    arr = np.asarray(img).astype("int16")
    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
    key = (r > 140) & (b > 100) & (g < 0.75 * np.minimum(r, b))
    keep = ~key

    rgb = _snap_rgb(arr[..., :3])
    alpha = np.where(keep, 255, 0).astype("uint8")
    out = np.dstack([rgb, alpha])

    ys, xs = np.nonzero(alpha > 0)
    if len(xs) == 0:
        return None
    x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
    crop = Image.fromarray(out[y0:y1, x0:x1], "RGBA")
    margin = max(2, int(size * 0.10))
    crop.thumbnail((size - 2 * margin, size - 2 * margin), Image.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.paste(crop, ((size - crop.width) // 2, (size - crop.height) // 2), crop)
    final = np.asarray(canvas).astype("int16")
    final[..., :3] = _snap_rgb(final[..., :3])
    final[..., 3] = np.where(final[..., 3] > 90, 255, 0).astype("uint8")
    return Image.fromarray(final.astype("uint8"), "RGBA")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m tools.art.gen_classes_sd")
    ap.add_argument("--limit", type=int, default=0, help="only generate this many (smoke test, no pack)")
    ap.add_argument("--seed", type=int, default=31, help="base SD seed")
    args = ap.parse_args(argv)

    specs = list(CLASS_SPECS)
    smoke = bool(args.limit)
    if args.limit:
        specs = specs[:args.limit]

    CACHE.mkdir(parents=True, exist_ok=True)

    images = []
    t0 = time.time()
    for idx, (sprite, desc) in enumerate(specs):
        raw = CACHE / ("%s.png" % sprite)
        if not raw.exists():
            ok = generate(_prompt(desc), raw, args.seed + idx)
            if not ok:
                print("  FAILED %s" % sprite)
                continue
        cell = process(raw)
        if cell is None:
            print("  EMPTY  %s" % sprite)
            continue
        images.append((sprite, cell))
        print("  [%d/%d] %s" % (idx + 1, len(specs), sprite), flush=True)

    if not images:
        print("no sprites generated")
        return 1

    if smoke:
        print("smoke test: %d portrait(s) generated to cache (atlas untouched)" % len(images))
        return 0

    cols = len(images)
    sheet = Image.new("RGBA", (cols * CELL, CELL), (0, 0, 0, 0))
    frames = {}
    for idx, (sprite, cell) in enumerate(images):
        x = idx * CELL
        sheet.paste(cell, (x, 0))
        frames[sprite] = [x, 0, CELL, CELL]

    OUT_PNG.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(OUT_PNG)
    doc = {
        "version": 1,
        "image": "assets/atlas/classes.png",
        "meta": {"tile": 64, "palette_version": _pal.get("version", 1),
                 "generated_by": "sd"},
        "frames": frames,
    }
    OUT_JSON.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    print("packed %d portraits -> %s (%.1fs total)" % (len(images), OUT_PNG, time.time() - t0))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
