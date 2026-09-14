"""Manifest-driven art build: raw AI sheets -> palette-locked sprites -> packed atlases.

    python -m tools.art.build_from_manifest [--only SET ...] [--skip-verify]

Pipeline (each step is a real subprocess call to the sibling tools, so the output is the same as
running them by hand):

  1. stage   assets/raw/<sheet>.png  ->  assets/raw/staged/<sheet>.png      (square-crop + BOX
             downscale each painted cell to 32px, magenta background preserved)
  2. emit    assets/raw/pixelize_manifest.json   (pixelize's `manifest` split schema:
             {name, raw, cell, frames:{frame:[x,y,w,h]}})
  3. pixelize --split manifest  ->  assets/sprites/<set>/<frame>.png  (chroma-key + palette lock)
  4. pack_atlas --name <set>    ->  assets/atlas/<set>.png + .json
  5. aliases -> extra frame names pointing at existing rects (assets/art_manifest.json "aliases")
  6. verify (unless --skip-verify)

Owned by forge (director); the sibling tools it drives are owned by pixel.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "assets" / "art_manifest.json"
STAGED = ROOT / "assets" / "raw" / "staged"
PIXELIZE_MANIFEST = ROOT / "assets" / "raw" / "pixelize_manifest.json"
STRIPES = ("magenta",)
OUT_GRID = 32


def say(msg: str) -> None:
    print(msg, flush=True)


def load_manifest() -> dict:
    if not MANIFEST.is_file():
        raise SystemExit(f"missing {MANIFEST} - run the manifest generator first")
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def load_palette_rgb():
    pal = json.loads((ROOT / "assets" / "palette.json").read_text(encoding="utf-8"))
    return [tuple(int(h[i:i + 2], 16) for i in (1, 3, 5)) for h in pal["colors"].values()]


def presnap(cell, palette_rgb):
    """Snap the painted cell to the locked palette at SOURCE resolution, protecting the magenta key.

    Downscaling anti-aliased AI art straight to 32px produces colour mush (the "digital static"
    floor tiles). Flattening each pixel onto the palette first makes whole regions one colour, so
    the BOX downscale yields clean pixel-art blocks instead of noise.
    """
    import numpy as np

    arr = np.asarray(cell.convert("RGB")).astype("int16")
    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
    # r>140 (not >100): the locked palette contains arcane #7b4fd1 (r=123) and arcane_light #b48cf0;
    # a r>100 floor treats those purples as magenta family, flattens them and then keys them out,
    # punching holes in every purple sprite. Keep this in step with tools/art/_util.py.
    key = (r > 140) & (b > 100) & (g < 0.75 * np.minimum(r, b))

    pal = np.array(palette_rgb, dtype="int16")
    best_d = np.full(arr.shape[:2], 1 << 30, dtype="int64")
    best_i = np.zeros(arr.shape[:2], dtype="int32")
    for i in range(pal.shape[0]):
        d = ((arr[..., 0] - pal[i, 0]) ** 2 + (arr[..., 1] - pal[i, 1]) ** 2
             + (arr[..., 2] - pal[i, 2]) ** 2)
        closer = d < best_d
        best_d[closer] = d[closer]
        best_i[closer] = i
    snapped = pal[best_i].astype("uint8")
    snapped[key] = arr[key].astype("uint8")          # the key colour stays exactly as painted
    from PIL import Image
    return Image.fromarray(snapped, mode="RGB")


def stage_sheet(sheet: dict, palette_rgb=None, do_presnap: bool = True, fill: bool = False):
    """Downscale every painted cell to OUT_GRID and lay them out as a 32px-cell sheet."""
    from PIL import Image

    raw = ROOT / sheet["raw"]
    if not raw.is_file():
        raise SystemExit(f"missing raw sheet {raw}")
    img = Image.open(raw).convert("RGB")
    cols, rows = int(sheet["cols"]), int(sheet["rows"])
    cw = int(sheet.get("cell_w") or img.width // cols)
    ch = int(sheet.get("cell") or img.height // rows)

    staged = Image.new("RGB", (cols * OUT_GRID, rows * OUT_GRID), (255, 0, 255))
    placed: list[tuple[str, int, int]] = []
    for row in range(rows):
        for col in range(cols):
            idx = row * cols + col
            names = sheet["frames"]
            if idx >= len(names) or not names[idx]:
                continue
            x0, y0 = col * cw, row * ch
            cell = img.crop((x0, y0, x0 + cw, y0 + ch))
            # square-crop from the centre so a wide cell never gets squashed
            if cw != ch:
                side = min(cw, ch)
                cx, cy = (cw - side) // 2, (ch - side) // 2
                cell = cell.crop((cx, cy, cx + side, cy + side))
            if do_presnap and palette_rgb:
                cell = presnap(cell, palette_rgb)
            if fill or sheet.get("fit") == "fill":
                # tiles must be edge-to-edge: trim to the painted ink, then scale to fill the cell
                import numpy as np
                arr = np.asarray(cell.convert("RGB")).astype("int16")
                r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
                ink = ~((r > 140) & (b > 100) & (g < 0.75 * np.minimum(r, b)))
                ys, xs = np.nonzero(ink)
                if len(xs) > 8:
                    m = max(2, int(0.01 * max(arr.shape[:2])))
                    x0, x1 = max(0, xs.min() - m), min(arr.shape[1], xs.max() + 1 + m)
                    y0, y1 = max(0, ys.min() - m), min(arr.shape[0], ys.max() + 1 + m)
                    cell = cell.crop((x0, y0, x1, y1))
            cell = cell.resize((OUT_GRID, OUT_GRID), Image.BOX)
            staged.paste(cell, (col * OUT_GRID, row * OUT_GRID))
            placed.append((names[idx], col, row))

    STAGED.mkdir(parents=True, exist_ok=True)
    out = STAGED / f"{sheet['id']}.png"
    staged.save(out)
    return out, placed


def build_pixelize_manifest(manifest: dict, only: set[str] | None) -> tuple[dict, dict]:
    sheets, sets = [], {}
    palette_rgb = load_palette_rgb()
    for sheet in manifest["sheets"]:
        set_name = sheet["atlas"]
        if only and set_name not in only:
            continue
        staged, placed = stage_sheet(sheet, palette_rgb, fill=(set_name == "tiles"))
        frames = {name: [col * OUT_GRID, row * OUT_GRID, OUT_GRID, OUT_GRID]
                  for name, col, row in placed}
        sheets.append({
            "id": sheet["id"],
            "name": set_name,
            "sheet": sheet["id"],
            "raw": staged.relative_to(ROOT).as_posix(),
            "cell": OUT_GRID,
            "frames": frames,
        })
        sets.setdefault(set_name, 0)
        sets[set_name] += len(frames)
    doc = {"version": 1, "generated_by": "forge", "grid": OUT_GRID, "sheets": sheets}
    PIXELIZE_MANIFEST.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return doc, sets


def run(args: list[str]) -> int:
    say("  $ " + " ".join(args))
    return subprocess.call([sys.executable, "-m"] + args, cwd=str(ROOT))


def write_aliases(manifest: dict) -> int:
    """Alias names live in their own file: the atlas verifier (correctly) forbids two frames
    sharing a rect, so aliases are resolved by the loader, not duplicated into the atlas."""
    atlases = {}
    for path in (ROOT / "assets" / "atlas").glob("*.json"):
        if path.name == "aliases.json":
            continue
        atlases[path.stem] = json.loads(path.read_text(encoding="utf-8"))

    resolved, dropped = {}, []
    for alias, target in (manifest.get("aliases") or {}).items():
        for name, data in atlases.items():
            if target in (data.get("frames") or {}):
                resolved[alias] = target
                break
        else:
            dropped.append(alias)

    doc = {"version": 1, "generated_by": "forge",
           "note": "loader-level aliases: alias -> real atlas frame name",
           "aliases": resolved}
    (ROOT / "assets" / "aliases.json").write_text(json.dumps(doc, indent=2), encoding="utf-8")
    if dropped:
        say("  %d alias(es) had no painted target and were skipped: %s"
            % (len(dropped), ", ".join(sorted(dropped)[:6])))
    return len(resolved)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m tools.art.build_from_manifest")
    ap.add_argument("--only", nargs="*", default=None,
                    help="limit to these atlas/set names (monsters player tiles props vfx ui bosses items)")
    ap.add_argument("--skip-verify", action="store_true")
    args = ap.parse_args(argv)

    manifest = load_manifest()
    say(f"manifest: {len(manifest['sheets'])} sheets -> {MANIFEST}")

    say("staging sheets (downscale to %dpx cells)..." % OUT_GRID)
    doc, sets = build_pixelize_manifest(manifest, set(args.only) if args.only else None)
    for s in doc["sheets"]:
        say("  %-20s -> set %-9s %2d frames" % (s["id"], s["name"], len(s["frames"])))
    say("pixelize manifest: %s" % PIXELIZE_MANIFEST)

    say("pixelize (chroma-key + palette lock)...")
    rc = run(["tools.art.pixelize", "--split", "manifest", "--manifest",
              str(PIXELIZE_MANIFEST), "--grid", str(OUT_GRID)])
    if rc != 0:
        say("pixelize failed (rc=%d)" % rc)
        return rc

    say("packing atlases...")
    for set_name in sorted(sets):
        rc = run(["tools.art.pack_atlas", "--name", set_name,
                  "--sprites", "assets/sprites/%s" % set_name])
        if rc != 0:
            say("pack_atlas failed for %s (rc=%d)" % (set_name, rc))
            return rc

    say("writing loader aliases...")
    n_aliases = write_aliases(manifest)
    say("  assets/aliases.json: %d alias(es)" % n_aliases)
    stray = ROOT / "assets" / "atlas" / "aliases.json"
    if stray.exists():
        stray.unlink()

    if not args.skip_verify:
        say("verify...")
        rc = run(["tools.art.verify"])
        if rc != 0:
            say("verify failed (rc=%d)" % rc)
            return rc
    say("art build complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
