"""Regenerate monster sprites with the local FLUX pipeline.

The shipped monsters are 32x32 Copilot art upscaled to 64x64, which reads as
"black and white blobs".  This regenerates each monster at 256x256 on a clean
magenta key, then keys the background, palette-locks to the vaelmoor palette and
centres the result in a 64x64 cell.

Resumable: generated raw PNGs are cached under ``assets/raw/sd_cache`` so a
re-run only regenerates missing sprites.

Usage
-----
    python -m tools.art.gen_monsters_sd --limit 3     # smoke test
    python -m tools.art.gen_monsters_sd               # full batch
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
SD_BIN = ROOT / "tools" / "art" / "sd" / "bin" / "sd-cli.exe"
MODELS = Path(r"C:\Users\dbshe\models\flux")
DIFFUSION = MODELS / "flux1-schnell-Q4_K_S.gguf"
CLIP_L = MODELS / "clip_l.safetensors"
T5XXL = MODELS / "t5xxl-Q5_K_M.gguf"
VAE = MODELS / "ae.safetensors"

CACHE = ROOT / "assets" / "raw" / "sd_cache"
OUT_PNG = ROOT / "assets" / "atlas" / "monsters.png"
OUT_JSON = ROOT / "assets" / "atlas" / "monsters.json"

TILE = 64

_pal = json.loads((ROOT / "assets" / "palette.json").read_text(encoding="utf-8"))
_PAL_RGB = np.array([tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))
                     for h in _pal["colors"].values()], dtype="int32")

BIOME_HINT = {
    "catacombs": "undead crypt creature",
    "ember_warrens": "molten fire creature",
    "drowned_vaults": "drowned aquatic creature",
    "sunken_ossuary": "bony ossuary creature",
}

NEGATIVE = ("drop shadow, ground shadow, glow, gradient background, white background, "
            "grey background, floor, vignette, blur, smooth shading, anti-aliased, "
            "photorealistic, 3d render, text, caption, label, letters, numbers, watermark, "
            "signature, grid lines, duplicate sprites, identical clones")


def _prompt_for(name, biome, extra=""):
    hint = BIOME_HINT.get(biome, "dark fantasy creature")
    desc = name.lower()
    if extra:
        desc = "%s %s" % (extra, desc)
    return (
        "pixel art of a single %s, a %s, dark fantasy roguelite, top-down "
        "three-quarter view, on a flat solid pure magenta #ff00ff background, "
        "hard aliased pixels, no anti-aliasing, flat 3-tone shading, high contrast, "
        "chunky readable silhouette, distinct shape, no text, no watermark"
        % (desc, hint)
    )


def load_specs():
    """Return a list of (frame_name, prompt) covering every atlas frame.

    Base sprites come from monsters.json; elite variants and boss/minion
    sprites (referenced by spawn code but absent from monsters.json) are
    derived from their frame name.
    """
    data = json.loads((ROOT / "game" / "data" / "monsters.json").read_text(encoding="utf-8"))
    name_by_sprite = {}
    biome_by_sprite = {}
    for e in data.get("entries", []):
        sprite = e.get("sprite", "")
        if not sprite:
            continue
        name_by_sprite.setdefault(sprite, e.get("name", sprite))
        biome_by_sprite.setdefault(sprite, e.get("biome", "catacombs"))

    atlas = json.loads((OUT_JSON).read_text(encoding="utf-8"))["frames"]
    specs = []
    for sprite in sorted(atlas.keys()):
        if sprite in name_by_sprite:
            specs.append((sprite, _prompt_for(name_by_sprite[sprite], biome_by_sprite[sprite])))
        elif sprite.endswith("_elite"):
            base = sprite[:-len("_elite")]
            base_name = name_by_sprite.get(base, base.replace("monster_", "").replace("_", " "))
            specs.append((sprite, _prompt_for(base_name, biome_by_sprite.get(base, "catacombs"),
                                              extra="elite armored glowing")))
        else:
            name = sprite.replace("monster_", "").replace("_", " ")
            specs.append((sprite, _prompt_for(name, "catacombs")))
    return specs


def generate(prompt, out_path, seed):
    cmd = [str(SD_BIN), "-M", "img_gen",
           "--diffusion-model", str(DIFFUSION),
           "--clip_l", str(CLIP_L), "--t5xxl", str(T5XXL), "--vae", str(VAE),
           "-p", prompt, "-n", NEGATIVE,
           "-o", str(out_path), "-W", "256", "-H", "256",
           "--steps", "4", "--cfg-scale", "1.0", "-s", str(seed),
           "--sampling-method", "euler", "--offload-to-cpu"]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace")
    return proc.returncode == 0 and out_path.exists()


def _snap_rgb(arr):
    """Snap an HxWx3 int array to the nearest locked palette colour."""
    h, w = arr.shape[:2]
    flat = arr.reshape(-1, 3).astype("int32")
    best_d = np.full((h * w,), 1 << 30, dtype="int64")
    best_i = np.zeros((h * w,), dtype="int32")
    for i in range(_PAL_RGB.shape[0]):
        d = ((flat - _PAL_RGB[i]) ** 2).sum(axis=1)
        closer = d < best_d
        best_d[closer] = d[closer]
        best_i[closer] = i
    return _PAL_RGB[best_i].reshape(h, w, 3).astype("uint8")


def process(path, size=TILE):
    """Key magenta, palette-lock, trim and centre into a size x size cell."""
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
    margin = max(2, int(size * 0.12))
    crop.thumbnail((size - 2 * margin, size - 2 * margin), Image.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.paste(crop, ((size - crop.width) // 2, (size - crop.height) // 2), crop)
    # re-snap after the resize: LANCZOS blends edge pixels with the transparent
    # background, producing off-palette colours. Snap again and re-threshold alpha.
    final = np.asarray(canvas).astype("int16")
    final[..., :3] = _snap_rgb(final[..., :3])
    final[..., 3] = np.where(final[..., 3] > 90, 255, 0).astype("uint8")
    return Image.fromarray(final.astype("uint8"), "RGBA")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m tools.art.gen_monsters_sd")
    ap.add_argument("--limit", type=int, default=0, help="only generate this many (smoke test, no pack)")
    ap.add_argument("--seed", type=int, default=42, help="base SD seed")
    args = ap.parse_args(argv)

    specs = load_specs()
    smoke = bool(args.limit)
    if args.limit:
        specs = specs[:args.limit]

    CACHE.mkdir(parents=True, exist_ok=True)

    images = []
    t0 = time.time()
    for idx, (sprite, prompt) in enumerate(specs):
        raw = CACHE / ("%s.png" % sprite)
        if not raw.exists():
            ok = generate(prompt, raw, args.seed + idx)
            if not ok:
                print("  FAILED %s" % sprite)
                continue
        cell = process(raw)
        if cell is None:
            print("  EMPTY  %s" % sprite)
            continue
        images.append((sprite, cell))
        print("  [%3d/%d] %s" % (idx + 1, len(specs), sprite), flush=True)

    if not images:
        print("no sprites generated")
        return 1

    if smoke:
        print("smoke test: %d sprite(s) generated to cache (atlas untouched)" % len(images))
        return 0

    # pack into a grid
    n = len(images)
    cols = 16
    rows = (n + cols - 1) // cols
    sheet = Image.new("RGBA", (cols * TILE, rows * TILE), (0, 0, 0, 0))
    frames = {}
    for idx, (sprite, cell) in enumerate(images):
        r, c = divmod(idx, cols)
        x, y = c * TILE, r * TILE
        sheet.paste(cell, (x, y))
        frames[sprite] = [x, y, TILE, TILE]

    OUT_PNG.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(OUT_PNG)
    doc = {
        "version": 1,
        "image": "assets/atlas/monsters.png",
        "meta": {"tile": TILE, "palette_version": _pal.get("version", 1),
                 "generated_by": "sd"},
        "frames": frames,
    }
    OUT_JSON.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    print("packed %d monsters -> %s (%.1fs total)" % (n, OUT_PNG, time.time() - t0))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
