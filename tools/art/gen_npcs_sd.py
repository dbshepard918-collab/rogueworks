"""Regenerate the 5 HQ NPC sprites with the local FLUX pipeline.

The shipped NPCs are 32x32 Copilot art upscaled to 64x64 — five identical
"basic humanoid" figures that differ only by torso colour.  This regenerates
each NPC as a distinct character (from ``game/data/npcs.json``) at 256x256 on a
clean magenta key, then keys the background, palette-locks to the vaelmoor
palette and centres the result in a 64x64 cell.

Usage
-----
    python -m tools.art.gen_npcs_sd --limit 1   # smoke test
    python -m tools.art.gen_npcs_sd             # full batch
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
    process,
    _pal,
)

ROOT = Path(__file__).resolve().parents[2]
OUT_PNG = ROOT / "assets" / "atlas" / "npcs.png"
OUT_JSON = ROOT / "assets" / "atlas" / "npcs.json"

TILE = 64

NEGATIVE = ("drop shadow, ground shadow, glow, gradient background, white background, "
            "grey background, floor, vignette, blur, smooth shading, anti-aliased, "
            "photorealistic, 3d render, text, caption, label, letters, numbers, watermark, "
            "signature, grid lines, duplicate sprites, identical clones, extra limbs, "
            "missing limbs, deformed hands")

# (sprite, character prompt) — one per NPC in game/data/npcs.json.
NPC_SPECS = [
    ("npc_keeper_eira",
     "a blind archivist keeper in a hooded robe, pale sightless eyes, holding a "
     "leather-bound tome, quiet and wise"),
    ("npc_forge_brokk",
     "a seven-foot forge-giant blacksmith, massive muscular build, soot-stained "
     "leather apron, holding a heavy forge hammer, gruff"),
    ("npc_tide_mira",
     "a half-drowned cartographer, sea-soaked tattered clothes, water dripping "
     "from her, holding a rolled sea chart, ethereal"),
    ("npc_skull_raven",
     "a human skull hanging on a rusted chain, faintly glowing eye sockets, "
     "speaking in riddles"),
    ("npc_sorrow_lena",
     "a sorrowful keeper in a hooded mourning robe, holding a single candle, "
     "melancholy and gentle"),
]


def _prompt(desc):
    return (
        "pixel art of a single %s, dark fantasy roguelite, top-down "
        "three-quarter view, on a flat solid pure magenta #ff00ff background, "
        "hard aliased pixels, no anti-aliasing, flat 3-tone shading, high contrast, "
        "chunky readable silhouette, distinct shape, no text, no watermark"
        % desc
    )


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m tools.art.gen_npcs_sd")
    ap.add_argument("--limit", type=int, default=0, help="only generate this many (smoke test, no pack)")
    ap.add_argument("--seed", type=int, default=23, help="base SD seed")
    args = ap.parse_args(argv)

    specs = list(NPC_SPECS)
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
        print("smoke test: %d NPC(s) generated to cache (atlas untouched)" % len(images))
        return 0

    cols = len(images)
    sheet = Image.new("RGBA", (cols * TILE, TILE), (0, 0, 0, 0))
    frames = {}
    for idx, (sprite, cell) in enumerate(images):
        x = idx * TILE
        sheet.paste(cell, (x, 0))
        frames[sprite] = [x, 0, TILE, TILE]

    OUT_PNG.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(OUT_PNG)
    doc = {
        "version": 1,
        "image": "assets/atlas/npcs.png",
        "meta": {"tile": TILE, "palette_version": _pal.get("version", 1),
                 "generated_by": "sd"},
        "frames": frames,
    }
    OUT_JSON.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    print("packed %d NPCs -> %s (%.1fs total)" % (len(images), OUT_PNG, time.time() - t0))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
