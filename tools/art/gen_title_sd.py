"""Regenerate the title background with the local FLUX pipeline.

The shipped title background is a FLUX image that (a) has the game title and a
garbled "© Rogle Linte" watermark baked into the pixels, and (b) was packed at
2x resolution (2560x1472) with a matching frame rect, so the menu blits a
zoomed-in top-left quadrant.  This regenerates a clean 16:9 scene with an
explicit "no text" negative, palette-locks it to the vaelmoor palette and packs
it at the correct 1280x736 (32px-aligned) size.

Usage
-----
    python -m tools.art.gen_title_sd
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

import numpy as np
from PIL import Image

from tools.art.gen_monsters_sd import (
    SD_BIN,
    DIFFUSION,
    CLIP_L,
    T5XXL,
    VAE,
    _snap_rgb,
    _pal,
)

ROOT = Path(__file__).resolve().parents[2]
OUT_PNG = ROOT / "assets" / "atlas" / "title.png"
OUT_JSON = ROOT / "assets" / "atlas" / "title.json"
RAW_OUT = ROOT / "assets" / "raw" / "title_background.png"

# 1280x720 render, padded to 1280x768 so the height is a 64px-grid multiple.
W, H = 1280, 768
GEN_W, GEN_H = 1024, 576  # 16:9, 64px-aligned for the SD sampler

PROMPT = (
    "pixel art of a lone hooded adventurer holding a glowing amber lantern, "
    "standing at the base of a glowing arcane staircase descending into a vast "
    "dark abyss, framed by a gothic stone archway, a giant skull in the "
    "foreground, scattered skulls and swords, dark fantasy roguelite, "
    "atmospheric, moody, high contrast, hard aliased pixels, no anti-aliasing, "
    "no text, no watermark, no letters, no caption, no signature"
)

NEGATIVE = ("text, caption, label, letters, numbers, watermark, signature, logo, "
            "title, word, alphabet, glyph, blur, smooth shading, anti-aliased, "
            "photorealistic, 3d render, gradient background")


def generate(out_path, seed):
    cmd = [str(SD_BIN), "-M", "img_gen",
           "--diffusion-model", str(DIFFUSION),
           "--clip_l", str(CLIP_L), "--t5xxl", str(T5XXL), "--vae", str(VAE),
           "-p", PROMPT, "-n", NEGATIVE,
           "-o", str(out_path), "-W", str(GEN_W), "-H", str(GEN_H),
           "--steps", "4", "--cfg-scale", "1.0", "-s", str(seed),
           "--sampling-method", "euler", "--offload-to-cpu"]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace")
    return proc.returncode == 0 and out_path.exists()


def main(argv=None) -> int:
    seed = 11
    t0 = time.time()
    raw = RAW_OUT
    if not raw.exists():
        ok = generate(raw, seed)
        if not ok:
            print("generation failed")
            return 1
    print("generated (%.1fs)" % (time.time() - t0))

    img = Image.open(raw).convert("RGB")
    img = img.resize((W, H - 48), Image.LANCZOS)  # 1280x720
    # pad to 1280x768 with the ink colour so the height is 64px-aligned
    canvas = Image.new("RGB", (W, H), tuple(int(_pal["colors"]["ink"][i:i + 2], 16)
                                            for i in (1, 3, 5)))
    canvas.paste(img, (0, 0))

    arr = np.asarray(canvas).astype("int16")
    arr = _snap_rgb(arr)
    out = Image.fromarray(arr.astype("uint8"), "RGB").convert("RGBA")

    OUT_PNG.parent.mkdir(parents=True, exist_ok=True)
    out.save(OUT_PNG)
    doc = {
        "version": 1,
        "image": "assets/atlas/title.png",
        "meta": {"tile": 64, "palette_version": _pal.get("version", 1),
                 "generated_by": "sd"},
        "frames": {"background": [0, 0, W, H]},
    }
    OUT_JSON.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    print("packed title background -> %s (%dx%d)" % (OUT_PNG, W, H))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
