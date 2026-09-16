"""Generate a dark fantasy tileset: 38 individual 32x32 tiles -> single grid PNG."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(r"C:\Users\dbshe\rogueworks")
SD_BIN = ROOT / "tools" / "art" / "sd" / "bin" / "sd-cli.exe"
MODELS = Path(r"C:\Users\dbshe\models\flux")
DIFFUSION = MODELS / "flux1-schnell-Q4_K_S.gguf"
CLIP_L = MODELS / "clip_l.safetensors"
T5XXL = MODELS / "t5xxl-Q5_K_M.gguf"
VAE = MODELS / "ae.safetensors"
PALETTE_PATH = ROOT / "assets" / "palette.json"
OUT_PATH = ROOT / "assets" / "tiles" / "tileset_dark_fantasy.png"

# Load palette
pal = json.load(open(PALETTE_PATH, encoding="utf-8"))
colours = list(pal["colors"].values())
pal_arr = np.array([[int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)] for c in colours], dtype="int16")

TILE = 64
COLS = 8

# (frame_name, description) — descriptions crafted for FLUX to produce concrete subjects
TILES = [
    # Floors (8)
    ("floor_stone", "flat stone floor tile, grey stone blocks with dark mortar lines, dark grout, dungeon paving"),
    ("floor_cracked", "cracked stone floor tile, broken grey stone with jagged fissures and missing chunks"),
    ("floor_mossy", "mossy stone floor tile, grey stone with patches of green moss growing in cracks"),
    ("floor_blood", "blood-stained floor tile, dark stone with splatters of dried dark red blood"),
    ("floor_tile", "tile pattern floor, dark grey stone tiles in a checkerboard pattern alternating two shades"),
    ("floor_slab", "dungeon slab floor, large flat dark grey rectangular stone slab with chipped edges"),
    ("floor_worn", "worn stone floor tile, smooth grey stone worn down and polished by many footsteps"),
    ("floor_dark", "dark stone floor tile, very dark grey-black stone, almost black, rough texture"),

    # Walls (8)
    ("wall_brick", "brick wall tile, dark grey stone bricks in a running bond pattern with mortar"),
    ("wall_mossy", "mossy brick wall, dark stone bricks with patches of green moss between them"),
    ("wall_cracked", "cracked wall tile, dark stone wall with deep cracks and crumbling mortar"),
    ("wall_vines", "wall with vines, dark stone wall with thick green vines hanging down from above"),
    ("wall_skulls", "wall with skulls, dark stone wall embedded with white human skulls and bones"),
    ("wall_block", "stone block wall, large smooth rectangular dark grey stone blocks stacked neatly"),
    ("wall_dark", "dark brick wall, very dark grey-black bricks, almost black, rough and weathered"),
    ("wall_cobble", "cobblestone wall, rounded irregular dark grey stones fitted together"),

    # Doors (4)
    ("door_wooden", "wooden door tile, vertical plank wooden door with iron handle and hinges, brown wood"),
    ("door_iron", "iron door tile, heavy riveted iron door with circular wheel lock, dark grey metal"),
    ("door_cell", "cell door tile, vertical iron bars of a prison cell door with gaps between bars"),
    ("door_open", "open doorway tile, dark empty stone rectangular archway leading to black void"),

    # Hazards (4)
    ("hazard_spikes", "floor spikes tile, row of sharp metal spikes protruding upwards from stone floor"),
    ("hazard_lava", "lava pool tile, bubbling bright orange-red lava with dark crusty edges"),
    ("hazard_water", "water pool tile, dark blue-green water pool with concentric ripples"),
    ("hazard_poison", "poison pool tile, bubbling toxic green pool with sickly vapour rising"),

    # Props (6)
    ("prop_pillar", "stone pillar tile, round fluted grey stone column with decorative capital and base"),
    ("prop_torch", "wall torch tile, iron wall bracket holding an unlit wooden torch with cloth wrap"),
    ("prop_chest", "treasure chest tile, wooden chest with iron bands and a keyhole lock, closed"),
    ("prop_rubble", "rubble tile, pile of broken grey stone blocks and debris scattered on the ground"),
    ("prop_bones", "bone pile tile, scattered white bones and a human skull on dark ground"),
    ("prop_chains", "chains tile, coiled rusty iron chains with thick links lying on the ground"),

    # Stairs (2)
    ("stairs_up", "stairs up tile, stone steps ascending upward into darkness, steps leading up"),
    ("stairs_down", "stairs down tile, stone steps descending downward into darkness, steps leading down"),

    # Traps (2)
    ("trap_arrow", "arrow trap tile, stone wall with a small dark hole where a metal arrow protrudes"),
    ("trap_switch", "floor switch tile, stone floor with a square pressure plate or small lever"),

    # Decor (4)
    ("decor_torch_lit", "lit wall torch tile, iron bracket holding a bright flaming torch with orange fire"),
    ("decor_banner", "banner tile, hanging dark red cloth banner with a white skull emblem painted on it"),
    ("decor_blood", "blood stain tile, splatter of dark red blood on a dark stone floor"),
    ("decor_cracks", "cracks tile, dark stone floor with radiating crack lines spreading from center"),
]

NEGATIVE = ("drop shadow, ground shadow, glow, gradient background, white background, grey "
            "background, pink background, floor, vignette, blur, smooth shading, anti-aliased, "
            "photorealistic, 3d render, text, caption, label, letters, numbers, watermark, "
            "signature, grid lines, duplicate sprites, identical clones")


def detect_border_colour(arr):
    h, w = arr.shape[:2]
    ring = 8
    top = arr[:ring, :, :3].reshape(-1, 3)
    bot = arr[-ring:, :, :3].reshape(-1, 3)
    left = arr[ring:-ring, :ring, :3].reshape(-1, 3)
    right = arr[ring:-ring, -ring:, :3].reshape(-1, 3)
    border = np.concatenate([top, bot, left, right])
    quantised = (border // 8 * 8)
    colours_u, counts = np.unique(quantised, axis=0, return_counts=True)
    idx = counts.argmax()
    return tuple(int(x) for x in colours_u[idx])


def key_out_border(arr, border_rgb, tolerance=48):
    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
    br, bg, bb = border_rgb
    dist2 = (r.astype("int16") - br) ** 2 + (g.astype("int16") - bg) ** 2 + (b.astype("int16") - bb) ** 2
    mask = dist2 <= tolerance ** 2
    out = arr.copy()
    out[..., 3] = np.where(mask, 0, arr[..., 3])
    return out


def trim_and_centre(rgba, target=32):
    alpha = rgba[..., 3]
    rows = np.any(alpha > 0, axis=1)
    cols = np.any(alpha > 0, axis=0)
    if not rows.any() or not cols.any():
        return np.zeros((target, target, 4), dtype="uint8")
    r0, r1 = np.where(rows)[0][[0, -1]]
    c0, c1 = np.where(cols)[0][[0, -1]]
    trimmed = rgba[r0:r1 + 1, c0:c1 + 1]
    th, tw = trimmed.shape[:2]
    scale = min(target / tw, target / th)
    new_w = max(1, int(round(tw * scale)))
    new_h = max(1, int(round(th * scale)))
    img = Image.fromarray(trimmed, mode="RGBA")
    img = img.resize((new_w, new_h), Image.BOX)
    canvas = Image.new("RGBA", (target, target), (0, 0, 0, 0))
    ox = (target - new_w) // 2
    oy = (target - new_h) // 2
    canvas.paste(img, (ox, oy), img)
    return np.asarray(canvas)


def palette_lock(rgba):
    h, w = rgba.shape[:2]
    flat = rgba[..., :3].reshape(-1, 3).astype("int16")
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


def process_single(raw_path, target=32):
    img = Image.open(raw_path).convert("RGBA")
    arr = np.asarray(img).astype("uint8")
    border = detect_border_colour(arr)
    keyed = key_out_border(arr.astype("int16"), border).astype("uint8")
    centred = trim_and_centre(keyed, target).copy()
    alpha = centred[..., 3]
    centred[..., 3] = np.where(alpha > 64, 255, 0).astype("uint8")
    locked = palette_lock(centred)
    return locked


def generate_one(prompt, out, w=512, h=512, steps=4, seed=0, cfg=1.0):
    cmd = [str(SD_BIN), "-M", "img_gen",
           "--diffusion-model", str(DIFFUSION),
           "--clip_l", str(CLIP_L), "--t5xxl", str(T5XXL), "--vae", str(VAE),
           "-p", prompt, "-n", NEGATIVE,
           "-o", str(out), "-W", str(w), "-H", str(h),
           "--steps", str(steps), "--cfg-scale", str(cfg), "-s", str(seed),
           "--sampling-method", "euler", "--offload-to-cpu"]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return proc.returncode == 0 and out.exists()


def main():
    # Check all model files exist
    for path, what in ((SD_BIN, "sd-cli.exe"), (DIFFUSION, "flux gguf"), (CLIP_L, "clip_l"),
                       (T5XXL, "t5xxl"), (VAE, "vae")):
        if not path.exists():
            print(f"MISSING {what}: {path}")
            return 2

    n = len(TILES)
    rows = (n + COLS - 1) // COLS
    grid_w = COLS * TILE
    grid_h = rows * TILE

    print(f"Generating {n} dark fantasy tiles ({COLS}x{rows} grid = {grid_w}x{grid_h})")

    tmp_dir = Path(tempfile.gettempdir()) / "rogueworks_darkfantasy"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    tiles_rgba = []
    ok_count = 0

    for i, (frame_name, description) in enumerate(TILES):
        raw_path = tmp_dir / f"{frame_name}.png"
        print(f"  [{i+1:2d}/{n}] {frame_name:20s}  {description[:50]}")

        prompt = (f"Pixel art of a single {description}, drawn on a 32x32 pixel grid with hard "
                  f"aliased pixels (no anti-aliasing, no blur, no gradients). The ENTIRE background "
                  f"is one flat solid pure magenta #ff00ff colour, edge to edge, with NO drop shadow, "
                  f"NO glow, NO floor, NO gradient, NO vignette. Dark fantasy roguelite, limited "
                  f"palette. Flat 3-tone shading only, 1-pixel solid black outline, high contrast, "
                  f"chunky readable shapes, distinct silhouette, top-down three-quarter view, "
                  f"NO text, NO letters, NO numbers, NO grid lines, NO watermark.")

        t0 = time.time()
        ok = generate_one(prompt, raw_path, seed=42 + i)
        took = time.time() - t0

        if not ok:
            print(f"    FAILED after {t1:.1f}s — skipping tile (will be transparent)")
            tiles_rgba.append(np.zeros((TILE, TILE, 4), dtype="uint8"))
            continue

        try:
            rgba = process_single(raw_path)
            tiles_rgba.append(rgba)
            ok_count += 1
            print(f"    ok in {took:.1f}s")
        except Exception as exc:
            print(f"    process error: {exc}")
            tiles_rgba.append(np.zeros((TILE, TILE, 4), dtype="uint8"))

    # Assemble grid
    grid = Image.new("RGBA", (grid_w, grid_h), (0, 0, 0, 0))
    for idx, rgba in enumerate(tiles_rgba):
        row, col = divmod(idx, COLS)
        x, y = col * TILE, row * TILE
        tile_img = Image.fromarray(rgba, mode="RGBA")
        grid.paste(tile_img, (x, y))

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    grid.save(OUT_PATH)

    size_kb = OUT_PATH.stat().st_size / 1024
    print(f"\nDONE: {ok_count}/{n} tiles generated")
    print(f"Output: {OUT_PATH}")
    print(f"Size: {size_kb:.1f} KB, dimensions: {grid_w}x{grid_h}")
    print(f"Next: verify with game/engine/assets.py Atlas loader")
    return 0


if __name__ == "__main__":
    sys.exit(main())
