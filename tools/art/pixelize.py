"""palette-lock and slice raw art into engine-ready sprites.

``assets/raw/<sheet>.png`` -> ``assets/sprites/<name>/<frame>.png`` (+ ``manifest.json``)

Three slicing modes, because raw AI sheets are not tidy:

``--split grid`` (default)
    fixed ``--grid`` cells (32px), right for sheets already laid out on the tile grid.

``--split panels``
    auto-detect the sprite panels on an AI sheet: mask the background, project the
    mask onto coarse 8px bands, split into contiguous bands of ink and take their
    cross-product, then snap every box **outward** to a multiple of 32 so the
    result is still grid-aligned.  This is what makes a 1024x1024 "16 sprites on
    magenta" sheet usable without hand-written coordinates.

``--split manifest``
    honour ``assets/raw/manifest.json`` (or ``--manifest PATH``) which names frames
    explicitly - the only way to get semantic frame names such as
    ``monster_bone_rat`` that match the ``sprite`` fields in ``game/data/*.json``::

        {"version": 1,
         "sheets": [
           {"raw": "assets/raw/monsters_catacombs.png", "name": "monsters_catacombs",
            "cell": 128,
            "frames": {"monster_bone_rat": [0, 0, 128, 128],   # [x, y, w, h] px
                       "bone_rat_walk_1": [1, 0]}}]}           # [col, row] with sheet "cell"

Background removal: the chroma key (#ff00ff - deliberately *not* a palette
colour, so it can never ship as art) plus, by default, the whole **magenta
family** - AI sheets come back with an off-key
backdrop (measured on this project's sheets: ``#c60ea5``, ``#c311a4``, ``#f511f2``)
that an exact-match key would leave in place.  A pixel is magenta-family when
``r > 140 and b > 100 and g < 0.75 * min(r, b)``; the red floor of 140 keeps
``arcane`` ``#7b4fd1`` (r=123) out of the key.  pixelize refuses to run if the
rule would ever key out a locked palette colour (``--key-min``/``--key-ratio``).
``--key exact`` restores strict behaviour, ``--key none`` keeps the backdrop.

Every surviving pixel is snapped to the nearest locked palette colour, so the
output passes ``tools.art.verify`` at tolerance 0.

Usage
-----
    python -m tools.art.pixelize --raw assets/raw/hero.png --name hero
    python -m tools.art.pixelize --split panels          # every sheet in assets/raw
    python -m tools.art.pixelize --split manifest --dry-run
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

from tools import _util
from tools._util import EXIT_OK, ToolError

GENERATED_BY = "pixel"
KEY_MODES = ("family", "exact", "tolerance", "none")
SPLIT_MODES = ("grid", "panels", "manifest")
COARSE = 8          # panel detection band size in px
MIN_PANEL = 16      # px; boxes smaller than this are noise
FAMILY_RATIO = 0.75 # g < ratio * min(r, b) => magenta-ish
FAMILY_MIN_R = 140  # r must exceed this too: keeps 'arcane' #7b4fd1 (r=123) out of the key


# --------------------------------------------------------------------------- #
# background / palette maths
# --------------------------------------------------------------------------- #
def key_mask(pixels, pal: _util.Palette, key_mode: str, tolerance: float, ratio: float,
             min_r: int = FAMILY_MIN_R):
    """Boolean mask of "this pixel is chroma-key background" for an int16 HxWx3 array."""
    import numpy as np

    r, g, b = pixels[..., 0], pixels[..., 1], pixels[..., 2]
    key = pal.chroma_key
    if key_mode == "none":
        return np.zeros(pixels.shape[:2], dtype=bool)
    if key_mode == "exact":
        return (r == key[0]) & (g == key[1]) & (b == key[2])
    if key_mode == "tolerance":
        d2 = float(tolerance) ** 2
        return ((r - key[0]) ** 2 + (g - key[1]) ** 2 + (b - key[2]) ** 2) <= d2
    return (r > min_r) & (b > 100) & (g < ratio * np.minimum(r, b))


def family_keyed_palette_colours(pal: _util.Palette, ratio: float = FAMILY_RATIO,
                                 min_r: int = FAMILY_MIN_R) -> list[str]:
    """Palette colours the magenta-family rule would eat - must always be empty."""
    return [
        name for name, (r, g, b) in pal.colors.items()
        if r > min_r and b > 100 and g < ratio * min(r, b)
    ]


def lock_sheet(img, pal: _util.Palette, alpha_min: int, keep_key: bool,
               key_mode: str, tolerance: float, ratio: float, min_r: int = FAMILY_MIN_R):
    """Palette-lock a whole image -> (RGBA uint8 HxWx4 array, key_removed count)."""
    import numpy as np
    from PIL import Image

    rgba = np.asarray(img.convert("RGBA")).astype("int16")
    alpha = rgba[..., 3]
    visible = alpha >= alpha_min
    keys = (np.zeros(rgba.shape[:2], dtype=bool) if keep_key
            else key_mask(rgba, pal, key_mode, tolerance, ratio, min_r))
    keep = visible & ~keys

    palette = np.array(list(pal.colors.values()), dtype="int16")
    h, w = keep.shape
    best_d = np.full((h, w), 1 << 30, dtype="int64")
    best_i = np.zeros((h, w), dtype="int32")
    for i in range(palette.shape[0]):
        cr, cg, cb = palette[i]
        d = (rgba[..., 0] - cr) ** 2 + (rgba[..., 1] - cg) ** 2 + (rgba[..., 2] - cb) ** 2
        closer = d < best_d
        best_d[closer] = d[closer]
        best_i[closer] = i
    rgb = palette[best_i]

    out = np.zeros((h, w, 4), dtype="uint8")
    sel = keep[..., None]
    out[..., :3] = np.where(sel, rgb, 0).astype("uint8")
    out[..., 3] = np.where(keep, 255, 0).astype("uint8")
    del Image
    return out, int(keys.sum())


def ink_mask(locked) -> "object":
    """Boolean mask of non-transparent pixels of a locked RGBA array."""
    import numpy as np

    return locked[..., 3] > 0


def snap_out(lo: int, hi: int, size: int, limit: int, grid: int) -> tuple[int, int]:
    """Expand [lo, hi) outward to a multiple of grid, clipped to [0, limit)."""
    lo = max(0, (lo // grid) * grid)
    hi = min(limit, int(math.ceil(hi / grid)) * grid)
    if hi <= lo:
        hi = min(limit, lo + grid)
    return lo, hi


def detect_panels(locked, grid: int, min_px: int = MIN_PANEL, pad_tiles: int = 0) -> list[tuple[int, int, int, int]]:
    """Split a locked sheet into panel boxes, snapped outward to the tile grid."""
    import numpy as np

    ink = ink_mask(locked)
    h, w = ink.shape
    ch, cw = math.ceil(h / COARSE), math.ceil(w / COARSE)
    padded = np.zeros((ch * COARSE, cw * COARSE), dtype=bool)
    padded[:h, :w] = ink
    coarse = padded.reshape(ch, COARSE, cw, COARSE).any(axis=(1, 3))

    def bands(active):
        out, start = [], None
        for i, on in enumerate(active):
            if on and start is None:
                start = i
            elif not on and start is not None:
                out.append((start, i))
                start = None
        if start is not None:
            out.append((start, len(active)))
        return out

    row_bands = bands(coarse.any(axis=1))
    col_bands = bands(coarse.any(axis=0))
    boxes: list[tuple[int, int, int, int]] = []
    for r0, r1 in row_bands:
        for c0, c1 in col_bands:
            if not coarse[r0:r1, c0:c1].any():
                continue  # empty corner of the cross-product
            y0, y1 = r0 * COARSE, r1 * COARSE
            x0, x1 = c0 * COARSE, c1 * COARSE
            if (y1 - y0) < min_px or (x1 - x0) < min_px:
                continue
            sy0, sy1 = snap_out(y0 - pad_tiles * grid, y1 + pad_tiles * grid, COARSE, h, grid)
            sx0, sx1 = snap_out(x0 - pad_tiles * grid, x1 + pad_tiles * grid, COARSE, w, grid)
            boxes.append((sx0, sy0, sx1 - sx0, sy1 - sy0))
    boxes.sort(key=lambda b: (b[1], b[0]))
    return _merge_overlaps(boxes)


def _merge_overlaps(boxes: list[tuple[int, int, int, int]]) -> list[tuple[int, int, int, int]]:
    merged = True
    while merged:
        merged = False
        out: list[tuple[int, int, int, int]] = []
        for box in boxes:
            x, y, w, h = box
            for i, (ox, oy, ow, oh) in enumerate(out):
                if x < ox + ow and ox < x + w and y < oy + oh and oy < y + h:
                    nx, ny = min(x, ox), min(y, oy)
                    out[i] = (nx, ny, max(x + w, ox + ow) - nx, max(y + h, oy + oh) - ny)
                    merged = True
                    break
            else:
                out.append(box)
        boxes = out
    boxes.sort(key=lambda b: (b[1], b[0]))
    return boxes


# --------------------------------------------------------------------------- #
# frame production
# --------------------------------------------------------------------------- #
def frames_from_grid(locked, name: str, grid: int, names: list[str] | None, prefix: str):
    """Fixed-cell slicing of an already-locked sheet."""
    h, w = locked.shape[:2]
    rows, cols = h // grid, w // grid
    frames = []
    kept = 0
    for row in range(rows):
        for col in range(cols):
            cell = locked[row * grid:(row + 1) * grid, col * grid:(col + 1) * grid]
            if not ink_mask(cell).any():
                continue
            fname = names[kept] if names and kept < len(names) else f"{prefix}{name}_r{row}c{col}"
            frames.append((fname, cell))
            kept += 1
    return frames


def frames_from_panels(locked, name: str, grid: int, names: list[str] | None, prefix: str,
                       min_px: int, pad_tiles: int):
    boxes = detect_panels(locked, grid, min_px, pad_tiles)
    frames = []
    for i, (x, y, w, h) in enumerate(boxes):
        crop = locked[y:y + h, x:x + w]
        fname = names[i] if names and i < len(names) else f"{prefix}{name}_p{i:03d}"
        frames.append((fname, crop))
    return frames


def frames_from_manifest(locked, sheet: dict, set_name: str, grid: int, raw_path: Path):
    cell = sheet.get("cell")
    frames = []
    for fname, spec in (sheet.get("frames") or {}).items():
        if isinstance(spec, (list, tuple)) and len(spec) == 4:
            x, y, w, h = (int(v) for v in spec)
        elif isinstance(spec, (list, tuple)) and len(spec) == 2 and isinstance(cell, int):
            col, row = (int(v) for v in spec)
            x, y, w, h = col * cell, row * cell, cell, cell
        elif isinstance(spec, dict) and "cell" in spec and isinstance(cell, int):
            col, row = spec["cell"]
            x, y, w, h = int(col) * cell, int(row) * cell, cell, cell
        elif isinstance(spec, dict) and "rect" in spec:
            x, y, w, h = (int(v) for v in spec["rect"])
        else:
            _util.warn(f"manifest frame '{fname}' has an unusable rect {spec!r} (want [x,y,w,h] or [col,row])")
            continue
        hgt, wid = locked.shape[:2]
        if x < 0 or y < 0 or x >= wid or y >= hgt or w <= 0 or h <= 0:
            _util.warn(f"manifest frame '{fname}' rect [{x}, {y}, {w}, {h}] is outside {wid}x{hgt}; skipped")
            continue
        w = min(w, wid - x)
        h = min(h, hgt - y)
        if w % grid or h % grid:
            _util.warn(f"manifest frame '{fname}' is {w}x{h}, not a tile multiple; snapped outward")
            w = min(wid - x, int(math.ceil(w / grid)) * grid)
            h = min(hgt - y, int(math.ceil(h / grid)) * grid)
        crop = locked[y:y + h, x:x + w]
        if not ink_mask(crop).any():
            _util.warn(f"manifest frame '{fname}' is empty after keying; skipped")
            continue
        frames.append((fname, crop))
    return frames


def _save_frames(out_root: Path, set_name: str, frames, pal: _util.Palette, raw_path: Path,
                 root: Path, grid: int, key_mode: str, dry_run: bool):
    from PIL import Image

    set_dir = out_root / set_name
    if not dry_run:
        _util.ensure_dir(set_dir)
    manifest = {
        "version": 1,
        "name": set_name,
        "grid": grid,
        "palette_version": pal.version,
        "palette": _util.rel_posix(pal.source, root),
        "colour_key": "#%02x%02x%02x" % pal.chroma_key,
        "key_mode": key_mode,
        "source": _util.rel_posix(raw_path, root),
        "generated_by": GENERATED_BY,
        "frames": {},
    }
    for fname, arr in frames:
        if not dry_run:
            Image.fromarray(arr, mode="RGBA").save(set_dir / f"{fname}.png")
        manifest["frames"][fname] = {"size": [int(arr.shape[1]), int(arr.shape[0])]}
    if not dry_run:
        _util.write_json(set_dir / "manifest.json", manifest)
    return set_dir, manifest


def load_raw_manifest(path: Path) -> dict:
    data = _util.load_json(path)
    if not isinstance(data, dict) or not isinstance(data.get("sheets"), list):
        raise ToolError(f"{path}: expected an object with a 'sheets' array")
    return data


# --------------------------------------------------------------------------- #
# entry point
# --------------------------------------------------------------------------- #
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m tools.art.pixelize",
        description="Palette-lock and slice raw art into assets/sprites/<name>/.",
    )
    ap.add_argument("--raw", nargs="*", default=None, metavar="PNG",
                    help="raw image(s); default: every *.png under assets/raw")
    ap.add_argument("--name", default=None, help="output sprite set name; default: the raw file stem")
    ap.add_argument("--out", default="assets/sprites", help="output root (default assets/sprites)")
    ap.add_argument("--palette", default=None, help="palette JSON (default assets/palette.json)")
    ap.add_argument("--split", choices=SPLIT_MODES, default="grid",
                    help="grid = fixed --grid cells; panels = auto-detect; manifest = named rects")
    ap.add_argument("--manifest", default=None, help="manifest JSON (default assets/raw/manifest.json)")
    ap.add_argument("--grid", type=int, default=_util.TILE, help="tile/cell size in px (default 64)")
    ap.add_argument("--alpha-min", type=int, default=128, help="alpha below this is cut (default 128)")
    ap.add_argument("--key", dest="key_mode", choices=KEY_MODES, default="family",
                    help="background removal: family (default), exact, tolerance, none")
    ap.add_argument("--key-tolerance", type=float, default=0.0,
                    help="RGB distance for --key tolerance (default 0)")
    ap.add_argument("--key-ratio", type=float, default=FAMILY_RATIO,
                    help=f"g < ratio * min(r,b) marks magenta family (default {FAMILY_RATIO})")
    ap.add_argument("--key-min", type=int, default=FAMILY_MIN_R,
                    help=f"red channel floor for --key family (default {FAMILY_MIN_R})")
    ap.add_argument("--keep-key", action="store_true", help="keep chroma-key pixels (overrides --key)")
    ap.add_argument("--min-panel", type=int, default=MIN_PANEL, help="panels smaller than this px are noise")
    ap.add_argument("--pad-tiles", type=int, default=0, help="extra tiles of margin around auto panels")
    ap.add_argument("--names", default=None, help="comma-separated frame names, in sheet order")
    ap.add_argument("--dry-run", action="store_true", help="report what would be cut, write nothing")
    ap.add_argument("--json", action="store_true", dest="as_json", help="print a JSON report")
    args = ap.parse_args(argv)

    root = _util.find_root()
    pal = _util.load_palette(args.palette, root)
    grid = int(args.grid)
    if grid <= 0:
        raise ToolError(f"--grid must be positive, got {grid}")
    if not args.keep_key and args.key_mode == "family":
        eaten = family_keyed_palette_colours(pal, float(args.key_ratio), int(args.key_min))
        if eaten:
            raise ToolError(
                f"--key family with ratio {args.key_ratio} / min {args.key_min} would key out the "
                f"palette colour(s) {', '.join(eaten)}; lower --key-ratio or raise --key-min"
            )

    manifest_data = None
    if args.split == "manifest":
        mpath = Path(args.manifest) if args.manifest else root / "assets" / "raw" / "manifest.json"
        if not mpath.is_file():
            raise ToolError(
                f"manifest not found: {mpath} - write one (see tools/art/pixelize.py docstring) "
                "or use --split grid / --split panels"
            )
        manifest_data = load_raw_manifest(mpath)

    # -- which sheets to process -------------------------------------------- #
    jobs: list[tuple[Path, str, dict | None]] = []
    if manifest_data is not None:
        for sheet in manifest_data["sheets"]:
            raw = sheet.get("raw")
            if not isinstance(raw, str):
                raise ToolError("manifest sheet is missing a 'raw' path")
            p = Path(raw) if Path(raw).is_absolute() else root / raw
            if not p.is_file():
                raise ToolError(f"manifest sheet not found: {p}")
            jobs.append((p, str(sheet.get("name") or p.stem), sheet))
    else:
        if args.raw:
            raws = []
            for item in args.raw:
                p = Path(item)
                p = p if p.is_absolute() else (root / item if (root / item).is_file() else Path.cwd() / item)
                if not p.is_file():
                    raise ToolError(f"raw image not found: {p}")
                raws.append(p)
        else:
            raw_dir = root / "assets" / "raw"
            raws = _util.iter_pngs(raw_dir)
            if not raws:
                _util.say(f"0 raw images found in {_util.rel_posix(raw_dir, root)} - nothing to pixelize")
                _util.say("hint: python -m tools.art.pixelize --raw path/to/art.png --name <set>")
                return EXIT_OK
        jobs = [(p, args.name or p.stem, None) for p in raws]

    names = [n.strip() for n in args.names.split(",") if n.strip()] if args.names else None
    out_root = Path(args.out) if Path(args.out).is_absolute() else root / args.out
    if not args.dry_run:
        _util.ensure_dir(out_root)

    report: list[dict] = []
    total = 0
    for raw_path, set_name, sheet in jobs:
        prefix = f"{raw_path.stem}_" if (args.name is None and manifest_data is None and args.raw and len(jobs) > 1) else ""
        img = _open(raw_path)
        locked, keyed = lock_sheet(img, pal, int(args.alpha_min), bool(args.keep_key),
                                   args.key_mode, float(args.key_tolerance), float(args.key_ratio),
                                   int(args.key_min))
        if args.split == "manifest" and sheet is not None:
            frames = frames_from_manifest(locked, sheet, set_name, grid, raw_path)
        elif args.split == "panels":
            frames = frames_from_panels(locked, set_name, grid, names, prefix,
                                        int(args.min_panel), int(args.pad_tiles))
        else:
            frames = frames_from_grid(locked, set_name, grid, names, prefix)
        set_dir, _ = _save_frames(out_root, set_name, frames, pal, raw_path, root, grid,
                                  "none" if args.keep_key else args.key_mode, bool(args.dry_run))
        total += len(frames)
        report.append({
            "raw": _util.rel_posix(raw_path, root),
            "set": set_name,
            "dir": _util.rel_posix(set_dir, root),
            "frames": len(frames),
            "keyed_px": keyed,
            "size": [img.width, img.height],
        })

    if args.as_json:
        print(json.dumps({"ok": True, "split": args.split, "key": args.key_mode,
                          "dry_run": bool(args.dry_run), "sheets": report}, indent=2))
        return EXIT_OK

    verb = "would write" if args.dry_run else "wrote"
    _util.say(f"pixelize: {args.split} split, key={args.key_mode if not args.keep_key else 'none'}, grid {grid}, "
              f"palette '{pal.name or pal.source.name}' v{pal.version} ({len(pal)} colours)")
    _util.say(f"{verb} {total} frame(s) from {len(jobs)} sheet(s):")
    for item in report:
        _util.say(f"  {item['frames']:>4} frame(s)  {item['size'][0]}x{item['size'][1]} "
                  f"{item['raw']} -> {item['dir']}/")
    if total == 0:
        _util.say("0 frames produced - every panel was empty or chroma-keyed "
                  "(try --key exact, --alpha-min 1 or --min-panel 8)")
        return EXIT_OK
    if not args.dry_run:
        _util.say(f"next: python -m tools.art.pack_atlas --name {report[0]['set']}")
    return EXIT_OK


def _open(path: Path):
    from PIL import Image

    try:
        return Image.open(path).convert("RGBA")
    except Exception as exc:  # noqa: BLE001
        raise ToolError(f"{path}: cannot read image ({type(exc).__name__}: {exc})") from None


if __name__ == "__main__":
    sys.exit(_util.guard(main)())
