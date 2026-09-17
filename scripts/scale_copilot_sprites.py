#!/usr/bin/env python3
"""Scale Copilot's 32x32 monster sprites to 64x64 and repack atlases."""
import json, os, sys
from PIL import Image
import numpy as np

TILE = 64
SPRITES_DIR = "assets/sprites/monsters"
ATLAS_DIR = "assets/atlas"

# Load manifest
manifest_path = os.path.join(SPRITES_DIR, "manifest.json")
if os.path.exists(manifest_path):
    with open(manifest_path) as f:
        manifest = json.load(f)
    print(f"Manifest: {len(manifest.get('sprites', []))} sprites")
else:
    manifest = None

# Find all monster sprite PNGs
sprite_files = [f for f in os.listdir(SPRITES_DIR) 
                if f.startswith("monster_") and f.endswith('.png')]
print(f"Found {len(sprite_files)} monster sprites")

# Scale each sprite to 64x64
scaled_count = 0
for fname in sprite_files:
    path = os.path.join(SPRITES_DIR, fname)
    img = Image.open(path)
    if img.size == (32, 32):
        # Scale up 2x with NEAREST (pixel art)
        img = img.resize((64, 64), Image.NEAREST)
        img.save(path)
        scaled_count += 1
    elif img.size == (64, 64):
        pass  # Already correct size
    else:
        print(f"  WARNING: {fname} is {img.size}, expected 32x32 or 64x64")

print(f"Scaled {scaled_count} sprites from 32x32 to 64x64")

# Now repack the monsters atlas
# Load existing atlas
atlas_path = os.path.join(ATLAS_DIR, "monsters.png")
atlas_json_path = os.path.join(ATLAS_DIR, "monsters.json")

with open(atlas_json_path) as f:
    atlas_data = json.load(f)

# Get all frame names from the sprites directory
frame_names = [f.replace('.png', '') for f in sprite_files]
frame_names.sort()

# Calculate atlas layout (16 columns)
COLS = 16
ROWS = (len(frame_names) + COLS - 1) // COLS
ATLAS_W = COLS * TILE
ATLAS_H = ROWS * TILE

print(f"Atlas layout: {COLS}x{ROWS} = {ATLAS_W}x{ATLAS_H}")

# Create new atlas
new_atlas = Image.new("RGBA", (ATLAS_W, ATLAS_H), (0, 0, 0, 0))
new_frames = {}

for idx, name in enumerate(frame_names):
    col = idx % COLS
    row = idx // COLS
    x, y = col * TILE, row * TILE
    
    sprite_path = os.path.join(SPRITES_DIR, f"{name}.png")
    try:
        sprite = Image.open(sprite_path)
        if sprite.size != (TILE, TILE):
            sprite = sprite.resize((TILE, TILE), Image.NEAREST)
        new_atlas.paste(sprite, (x, y))
        new_frames[name] = [x, y, TILE, TILE]
    except Exception as e:
        print(f"  Error packing {name}: {e}")

# Save atlas
new_atlas.save(atlas_path)
atlas_data["frames"] = new_frames
atlas_data["meta"]["tile"] = TILE
with open(atlas_json_path, "w") as f:
    json.dump(atlas_data, f, indent=1)

print(f"Repacked monsters atlas: {len(new_frames)} frames, {ATLAS_W}x{ATLAS_H}")
print("Done!")
