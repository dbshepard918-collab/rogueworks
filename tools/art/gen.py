"""Local, free image generation for Rogueworks — no API, no cost.

Wraps stable-diffusion.cpp (CUDA) + FLUX.1-schnell GGUF, which run on the local GPU.

    python -m tools.art.gen --sheet monsters_drowned --theme "flooded catacomb" \
        --subjects "drowned knight,drowned priest,jellyfish horror,..." [--seed 7]

    python -m tools.art.gen -p "any free prompt" -o assets/raw/thing.png

Single-subject mode (T-07): one 512x512 image per subject, auto-keyed, trimmed,
centred and palette-locked to 32x32, ready for the atlas:

    python -m tools.art.gen --single --subjects "brazier,pillar,rubble,..." \
        --prefix prop_ --out assets/sprites/props [--seed 7]

Verified on an RTX 5070 (12 GB): 512x512, 4 steps, ~11 s per image, no cloud call.
Notes that cost real time to learn:
  * use --diffusion-model, NOT -m: the FLUX GGUF is diffusion-only, and -m fails with
    "get sd version from file failed".
  * --offload-to-cpu keeps the t5 encoder in RAM; without it the 12 GB card is tight.
  * the local LLMs must be unloaded first (a chat model + diffusion model do not co-reside);
    this script does that for you.
  * FLUX needs the negative prompt to be non-empty in practice (empty cfg-scale 1 runs are fine,
    but the model drifts off the "flat magenta background" instruction without it).
  * Local FLUX ignores background instructions: --single auto-detects the border colour
    (the most common colour in the outer 8px ring) instead of assuming magenta, so a
    salmon or grey-background image still keys cleanly.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SD_BIN = ROOT / "tools" / "art" / "sd" / "bin" / "sd-cli.exe"
MODELS = Path(r"C:\Users\dbshe\models\flux")
DIFFUSION = MODELS / "flux1-schnell-Q4_K_S.gguf"
CLIP_L = MODELS / "clip_l.safetensors"
T5XXL = MODELS / "t5xxl-Q5_K_M.gguf"
VAE = MODELS / "ae.safetensors"

CELL = ("Pixel art sprite sheet, EXACTLY a {cols}x{rows} grid of {n} separate {what}, "
        "each drawn on a 32x32 pixel grid with hard aliased pixels (no anti-aliasing, no blur, "
        "no gradients), evenly spaced with clear gaps. The ENTIRE background is one flat solid "
        "pure magenta #ff00ff colour, edge to edge, with NO drop shadow under any sprite, NO glow, "
        "NO floor, NO gradient, NO vignette and NO label or caption under any sprite. "
        "{style}: {subjects}. Every sprite is a DIFFERENT species with a DIFFERENT silhouette - "
        "they must not share a body shape or pose. Each one: flat 3-tone shading only, 1-pixel "
        "solid black outline, high contrast, chunky readable shapes, distinct silhouette, top-down "
        "three-quarter view, NO text, NO letters, NO numbers, NO grid lines, NO watermark.")
NEGATIVE = ("drop shadow, ground shadow, glow, gradient background, white background, grey "
            "background, pink background, floor, vignette, blur, smooth shading, anti-aliased, "
            "photorealistic, 3d render, text, caption, label, letters, numbers, watermark, "
            "signature, grid lines, duplicate sprites, identical clones, same pose, frame border")

SINGLE_PROMPT = ("Pixel art of a single {subject}, drawn on a 32x32 pixel grid with hard aliased "
                 "pixels (no anti-aliasing, no blur, no gradients). The ENTIRE background is one "
                 "flat solid pure magenta #ff00ff colour, edge to edge, with NO drop shadow, NO glow, "
                 "NO floor, NO gradient, NO vignette. Dark fantasy roguelite, limited palette. "
                 "Flat 3-tone shading only, 1-pixel solid black outline, high contrast, chunky "
                 "readable shapes, distinct silhouette, top-down three-quarter view, NO text, "
                 "NO letters, NO numbers, NO grid lines, NO watermark.")

# Subject-specific prompt overrides: FLUX produces sparse noise for abstract subjects like
# "chain" or "water_pool" without a concrete visual description. These give it something solid
# to draw, while the frame name stays the data-bot's id.
SUBJECT_OVERRIDES = {
    "altar": "stone altar, a dark stone sacrificial table with carved runes and a glowing rune on top",
    "anvil": "blacksmith anvil, heavy dark iron anvil with a flat top and horn, a few sparks",
    "bones": "pile of bones, a skull and ribs scattered in a small pile on the ground",
    "brazier": "lit brazier, a metal fire basket with glowing orange flames and embers rising",
    "candles": "three lit candles, white wax candles with small orange flames on a stone holder",
    "chain": "iron chain, a coiled length of rusty iron chain with thick links lying on the ground",
    "crystal": "glowing crystal, a large faceted teal crystal cluster growing out of dark rock",
    "forge": "stone forge, a blacksmith forge with glowing orange coals and a stone chimney",
    "kelp": "kelp fronds, tall green underwater plant strands waving in dark water",
    "lava_vent": "lava vent, a crack in dark rock with glowing orange lava bubbling out",
    "pillar": "stone pillar, a broken ancient stone column with cracks and moss at the base",
    "pillar_drowned": "drowned pillar, a waterlogged stone pillar covered in green algae and kelp",
    "pipes": "metal pipes, rusty iron pipes and valves bolted to a stone wall",
    "roots": "dark roots, thick twisted dark tree roots spreading across the ground",
    "rubble": "stone rubble, a pile of broken grey stone blocks and debris on the ground",
    "sarcophagus": "stone sarcophagus, an ancient dark stone coffin lid with carved decorations",
    "shop_stall": "merchant shop stall, a wooden market stall with a canvas awning and goods on a counter",
    "shrine_drowned": "drowned shrine, a flooded stone altar with teal glowing runes in dark water",
    "urn": "funerary urn, an ornate dark ceramic urn with a lid and carved patterns",
    "water_pool": "dark water pool, a pool of dark blue-green water with ripples on a stone floor",
}


def unload_llms() -> None:
    lms = Path.home() / ".lmstudio" / "bin" / "lms.exe"
    if not lms.is_file():
        return
    try:
        subprocess.run([str(lms), "unload", "--all"], capture_output=True, timeout=120)
        print("  unloaded LM Studio models (freeing VRAM for the diffusion model)")
    except Exception as exc:  # noqa: BLE001
        print("  (could not unload LM Studio: %s)" % exc)


def generate(prompt: str, out: Path, w: int, h: int, steps: int, seed: int, cfg: float) -> int:
    for path, what in ((SD_BIN, "sd-cli.exe"), (DIFFUSION, "flux gguf"), (CLIP_L, "clip_l"),
                       (T5XXL, "t5xxl"), (VAE, "vae")):
        if not path.exists():
            print("MISSING %s: %s (re-run the local image stack installer)" % (what, path))
            return 2
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [str(SD_BIN), "-M", "img_gen",
           "--diffusion-model", str(DIFFUSION),
           "--clip_l", str(CLIP_L), "--t5xxl", str(T5XXL), "--vae", str(VAE),
           "-p", prompt, "-n", NEGATIVE,
           "-o", str(out), "-W", str(w), "-H", str(h),
           "--steps", str(steps), "--cfg-scale", str(cfg), "-s", str(seed),
           "--sampling-method", "euler", "--offload-to-cpu"]
    print("  $ sd-cli -M img_gen --diffusion-model flux1-schnell-Q4_K_S.gguf ... -o %s" % out.name)
    t0 = time.time()
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    took = time.time() - t0
    if proc.returncode != 0 or not out.exists():
        tail = "\n".join((proc.stdout or proc.stderr or "").strip().splitlines()[-8:])
        print("  FAILED rc=%d after %.1fs\n%s" % (proc.returncode, took, tail))
        return proc.returncode or 1
    print("  ok %s  %.0f KB in %.1fs (%.1f MB free VRAM accounting handled by --offload-to-cpu)"
          % (out.name, out.stat().st_size / 1024, took, 0))
    return 0


# --------------------------------------------------------------------------- #
# single-subject post-processing: raw 512x512 -> palette-locked 32x32
# --------------------------------------------------------------------------- #
def detect_border_colour(arr):
    """Return (r, g, b) of the most common colour in the outer 8px ring.

    Local FLUX ignores background instructions, so the border might be salmon,
    grey, or anything. We detect the dominant border colour and key that instead
    of assuming magenta.
    """
    import numpy as np
    h, w = arr.shape[:2]
    ring = 8
    top = arr[:ring, :, :3].reshape(-1, 3)
    bot = arr[-ring:, :, :3].reshape(-1, 3)
    left = arr[ring:-ring, :ring, :3].reshape(-1, 3)
    right = arr[ring:-ring, -ring:, :3].reshape(-1, 3)
    border = np.concatenate([top, bot, left, right])
    # quantise to reduce noise (round to nearest 8)
    quantised = (border // 8 * 8)
    colours, counts = np.unique(quantised, axis=0, return_counts=True)
    idx = counts.argmax()
    return tuple(int(x) for x in colours[idx])


def key_out_border(arr, border_rgb, tolerance=48):
    """Set pixels within `tolerance` of border_rgb to transparent.

    Tolerance is wider than the sheet pipeline (24) because single-subject 512x512
    FLUX images have more gradient background noise than a pre-gridded sheet.
    """
    import numpy as np
    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
    br, bg, bb = border_rgb
    dist2 = (r.astype("int16") - br) ** 2 + (g.astype("int16") - bg) ** 2 + (b.astype("int16") - bb) ** 2
    mask = dist2 <= tolerance ** 2
    out = arr.copy()
    out[..., 3] = np.where(mask, 0, arr[..., 3])
    return out


def trim_and_centre(rgba, target=32):
    """Trim to the bounding box of opaque pixels, then centre on a target x target canvas."""
    import numpy as np
    from PIL import Image
    alpha = rgba[..., 3]
    rows = np.any(alpha > 0, axis=1)
    cols = np.any(alpha > 0, axis=0)
    if not rows.any() or not cols.any():
        # nothing opaque; return a blank transparent target
        return np.zeros((target, target, 4), dtype="uint8")
    r0, r1 = np.where(rows)[0][[0, -1]]
    c0, c1 = np.where(cols)[0][[0, -1]]
    trimmed = rgba[r0:r1 + 1, c0:c1 + 1]
    th, tw = trimmed.shape[:2]
    # scale to fit target (preserving aspect, box filter)
    scale = min(target / tw, target / th)
    new_w = max(1, int(round(tw * scale)))
    new_h = max(1, int(round(th * scale)))
    img = Image.fromarray(trimmed, mode="RGBA")
    img = img.resize((new_w, new_h), Image.BOX)
    # centre on target x target
    canvas = Image.new("RGBA", (target, target), (0, 0, 0, 0))
    ox = (target - new_w) // 2
    oy = (target - new_h) // 2
    canvas.paste(img, (ox, oy), img)
    return np.asarray(canvas)


def palette_lock(rgba, palette_path=None):
    """Snap every opaque pixel to the nearest locked palette colour."""
    import json
    import numpy as np
    if palette_path is None:
        palette_path = ROOT / "assets" / "palette.json"
    pal = json.load(open(palette_path, encoding="utf-8"))
    colours = list(pal["colors"].values())
    pal_arr = np.array([[int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)] for c in colours],
                       dtype="int16")
    h, w = rgba.shape[:2]
    flat = rgba[..., :3].reshape(-1, 3).astype("int16")
    # nearest palette colour for every pixel
    best_d = np.full((h * w,), 1 << 30, dtype="int64")
    best_i = np.zeros((h * w,), dtype="int32")
    for i in range(pal_arr.shape[0]):
        d = ((flat - pal_arr[i]) ** 2).sum(axis=1)
        closer = d < best_d
        best_d[closer] = d[closer]
        best_i[closer] = i
    locked_rgb = pal_arr[best_i].reshape(h, w, 3).astype("uint8")
    out = rgba.copy()
    out[..., :3] = locked_rgb
    return out


def process_single(raw_path, out_path, target=32):
    """Full single-subject pipeline: auto-key border -> trim -> centre -> palette-lock -> save."""
    import numpy as np
    from PIL import Image
    img = Image.open(raw_path).convert("RGBA")
    arr = np.asarray(img).astype("uint8")
    # step 1: detect border colour
    border = detect_border_colour(arr)
    # step 2: key out the border colour
    keyed = key_out_border(arr.astype("int16"), border)
    keyed = keyed.astype("uint8")
    # step 3: trim + centre
    centred = trim_and_centre(keyed, target).copy()
    # step 3b: snap alpha to 1-bit (art.verify requires no partial alpha)
    alpha = centred[..., 3]
    centred[..., 3] = np.where(alpha > 64, 255, 0).astype("uint8")
    # step 4: palette-lock
    locked = palette_lock(centred)
    # step 5: save
    Image.fromarray(locked, mode="RGBA").save(out_path)
    return border


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m tools.art.gen",
                                 description="Local free image generation (FLUX via sd.cpp).")
    ap.add_argument("-p", "--prompt", default=None, help="free prompt (skip the sheet recipe)")
    ap.add_argument("--sheet", default=None, help="sheet id, e.g. monsters_drowned")
    ap.add_argument("--subjects", default=None,
                    help="comma-separated subject list, one per cell (vary them: local FLUX "
                         "produces near-identical clones if you don't)")
    ap.add_argument("--what", default="monster sprites", help="what each cell is")
    ap.add_argument("--style", default="Dark fantasy roguelite, limited palette",
                    help="theme sentence for the sheet recipe")
    ap.add_argument("--cols", type=int, default=4)
    ap.add_argument("--rows", type=int, default=4)
    ap.add_argument("-W", type=int, default=512)
    ap.add_argument("-H", type=int, default=512)
    ap.add_argument("--steps", type=int, default=4, help="schnell is a 4-step model")
    ap.add_argument("--cfg-scale", type=float, default=1.0)
    ap.add_argument("-s", "--seed", type=int, default=0)
    ap.add_argument("-o", "--out", default=None)
    ap.add_argument("--no-unload", action="store_true", help="skip unloading local LLMs first")
    ap.add_argument("--tries", type=int, default=1, help="re-roll this many seeds until a file lands")
    # single-subject mode (T-07)
    ap.add_argument("--single", action="store_true",
                    help="single-subject mode: one 512x512 per subject, auto-key + trim + centre + "
                         "palette-lock to 32x32, saved directly to assets/sprites/<name>/")
    ap.add_argument("--prefix", default="prop_",
                    help="frame name prefix for --single (default 'prop_')")
    ap.add_argument("--raw-dir", default=None,
                    help="directory for raw 512x512 outputs in --single mode (default $TEMP/rogueworks_raw)")
    args = ap.parse_args(argv)

    if args.single:
        return main_single(args)

    if args.prompt:
        prompt = args.prompt
    else:
        if not args.sheet:
            ap.error("give either -p/--prompt or --sheet")
        subjects = (args.subjects or "").strip()
        if not subjects:
            ap.error("--sheet needs --subjects (the per-cell subject list)")
        n = args.cols * args.rows
        listed = [s.strip() for s in subjects.split(",") if s.strip()]
        if len(listed) != n:
            print("  warning: %d subjects for %d cells - FLUX will improvise the gaps"
                  % (len(listed), n))
        prompt = CELL.format(cols=args.cols, rows=args.rows, n=n, what=args.what,
                             style=args.style, subjects=", ".join(listed))

    out = Path(args.out) if args.out else (ROOT / "assets" / "raw" / ("%s.png" % args.sheet))
    if not out.is_absolute():
        out = ROOT / out

    if not args.no_unload:
        unload_llms()
    for attempt in range(max(1, args.tries)):
        seed = args.seed + attempt
        if attempt:
            print("  re-roll %d (seed %d)" % (attempt, seed))
        rc = generate(prompt, out, args.W, args.H, args.steps, seed, args.cfg_scale)
        if rc == 0:
            print("next: python -m tools.art.build_from_manifest --only %s"
                  % (args.sheet or "monsters"))
            return 0
    return 1


def main_single(args) -> int:
    """Generate one 512x512 image per subject, then auto-key + trim + centre + palette-lock."""
    import os
    import tempfile
    subjects = [s.strip() for s in (args.subjects or "").split(",") if s.strip()]
    if not subjects:
        print("--single requires --subjects (comma-separated list)")
        return 2
    prefix = args.prefix
    out_root = Path(args.out) if args.out else (ROOT / "assets" / "sprites" / "props")
    if not out_root.is_absolute():
        out_root = ROOT / out_root
    out_root.mkdir(parents=True, exist_ok=True)
    raw_dir = Path(args.raw_dir) if args.raw_dir else Path(tempfile.gettempdir()) / "rogueworks_raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    if not args.no_unload:
        unload_llms()

    n_ok = 0
    for i, subject in enumerate(subjects):
        frame_name = prefix + subject
        out_path = out_root / ("%s.png" % frame_name)
        raw_path = raw_dir / ("%s_%d.png" % (frame_name, args.seed + i))
        # Use the override prompt if available, else the generic one
        subject_desc = SUBJECT_OVERRIDES.get(subject, subject)
        prompt = SINGLE_PROMPT.format(subject=subject_desc)
        print("  [%d/%d] %s" % (i + 1, len(subjects), frame_name))
        rc = generate(prompt, raw_path, args.W, args.H, args.steps, args.seed + i, args.cfg_scale)
        if rc != 0:
            print("  FAILED to generate %s (rc=%d)" % (frame_name, rc))
            continue
        border = process_single(raw_path, out_path)
        print("  -> %s  (border key=%s)" % (out_path.name, border))
        n_ok += 1
        # clean up raw
        try:
            raw_path.unlink()
        except OSError:
            pass
    print("done: %d/%d sprites" % (n_ok, len(subjects)))
    print("next: python -m tools.art.pack_atlas --name props")
    return 0 if n_ok == len(subjects) else 1


if __name__ == "__main__":
    sys.exit(main())
