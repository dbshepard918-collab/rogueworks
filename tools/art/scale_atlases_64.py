"""Scale all atlas PNGs + JSONs from 32x32 tiles to 64x64 tiles (NEAREST upscale 2x)."""
from __future__ import annotations

import json
from pathlib import Path
from PIL import Image

ATLAS_DIR = Path(r"C:\Users\dbshe\rogueworks\assets\atlas")

OLD = 32
NEW = 64
SCALE = NEW // OLD

json_files = sorted(ATLAS_DIR.glob("*.json"))
for jf in json_files:
    data = json.loads(jf.read_text(encoding="utf-8"))
    old_tile = data.get("meta", {}).get("tile", OLD)
    if old_tile == NEW:
        print(f"skip (already 64): {jf.name}")
        continue

    # Scale frame rects
    frames = data.get("frames", {})
    for name, rect in frames.items():
        x, y, w, h = rect
        frames[name] = [x * SCALE, y * SCALE, w * SCALE, h * SCALE]
    data["meta"]["tile"] = NEW

    jf.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    # Scale the PNG
    png_path = ATLAS_DIR / data["image"].split("/")[-1]
    if png_path.exists():
        img = Image.open(png_path)
        new_w = img.width * SCALE
        new_h = img.height * SCALE
        scaled = img.resize((new_w, new_h), Image.NEAREST)
        scaled.save(png_path)
        print(f"scaled {png_path.name}: {img.width}x{img.height} -> {new_w}x{new_h}")

print("done")
