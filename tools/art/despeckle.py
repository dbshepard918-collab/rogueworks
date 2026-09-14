"""despeckle: remove detached debris pixels from sprites (a quality fix, not art).

43 shipped sprites fragment into detached specks: a 3-pixel island floating beside
a monster is keying/downscale debris, not intent. It makes the sprite read as
"falling apart" at 32x32 and it is invisible to every existing check.

This clears any connected component of the alpha mask that is not the sprite body
and is at most `--max-speck` pixels. It only ever REMOVES pixels:

* the palette cannot change (no colour is introduced),
* the grid cannot shift (the image keeps its exact dimensions and the atlas keeps
  its exact frame rects),
* so `tools.art.verify` and every layout invariant are unaffected by construction.

Both the source sprite and the packed atlas are fixed, in place, so the fix
survives a future repack. `vfx` is skipped by default: particles are legitimately
multi-component, and the art gate exempts them for the same reason.

    python -m tools.art.despeckle                 # report only
    python -m tools.art.despeckle --apply         # fix sources + atlases in place
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image

from tools import _util
from tools._util import EXIT_FAIL, EXIT_OK, EXIT_PREREQ

ROOT = Path(__file__).resolve().parents[2]
ATLAS_DIR = ROOT / "assets" / "atlas"
SPRITES_DIR = ROOT / "assets" / "sprites"
DEFAULT_FAMILIES = ("monsters", "props", "items", "bosses")


def components(mask):
    """4-connected component pixel coordinates, largest first."""
    h, w = mask.shape
    seen = np.zeros_like(mask, dtype=bool)
    out = []
    for y0 in range(h):
        for x0 in range(w):
            if not mask[y0, x0] or seen[y0, x0]:
                continue
            q = deque([(y0, x0)])
            seen[y0, x0] = True
            pixels = []
            while q:
                cy, cx = q.popleft()
                pixels.append((cy, cx))
                for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    ny, nx = cy + dy, cx + dx
                    if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        q.append((ny, nx))
            out.append(pixels)
    out.sort(key=len, reverse=True)
    return out


def despeckle_cell(cell: np.ndarray, max_speck: int) -> tuple[np.ndarray, int]:
    """Return (cell with specks cleared, specks_removed)."""
    mask = cell[..., 3] > 0
    if not mask.any():
        return cell, 0
    comps = components(mask)
    removed = 0
    out = cell.copy()
    for comp in comps[1:]:                      # comps[0] is the body by definition
        if len(comp) <= max_speck:
            for y, x in comp:
                out[y, x] = (0, 0, 0, 0)
            removed += len(comp)
    return out, removed


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m tools.art.despeckle",
        description="Clear detached debris pixels from sprites and atlases in place.",
    )
    ap.add_argument("--families", nargs="*", default=list(DEFAULT_FAMILIES))
    ap.add_argument("--max-speck", type=int, default=3,
                    help="largest detached island to treat as debris (default 3)")
    ap.add_argument("--apply", action="store_true", help="write the fix (default: report only)")
    ap.add_argument("--json", action="store_true", dest="as_json")
    args = ap.parse_args(argv)

    if not ATLAS_DIR.is_dir():
        _util.say("no assets/atlas - nothing to do")
        return EXIT_PREREQ

    report = {"families": {}, "total_specks": 0, "files_changed": 0, "apply": bool(args.apply)}
    for family in args.families:
        atlas_png = ATLAS_DIR / (family + ".png")
        atlas_meta = ATLAS_DIR / (family + ".json")
        if not (atlas_png.is_file() and atlas_meta.is_file()):
            continue
        frames = json.loads(atlas_meta.read_text(encoding="utf-8")).get("frames", {})
        atlas = np.asarray(Image.open(atlas_png).convert("RGBA"))
        atlas_out = atlas.copy()
        family_specks = 0
        touched = []
        for name, box in sorted(frames.items()):
            x, y, w, h = box[:4]
            cell = atlas[y:y + h, x:x + w]
            cleaned, removed = despeckle_cell(cell, args.max_speck)
            if removed:
                family_specks += removed
                touched.append({"frame": name, "specks": removed})
                atlas_out[y:y + h, x:x + w] = cleaned
                # keep the SOURCE in step so a future repack cannot reintroduce them
                src = SPRITES_DIR / family / (name + ".png")
                if src.is_file():
                    s_img = np.asarray(Image.open(src).convert("RGBA"))
                    if s_img.shape[:2] == (h, w):
                        s_clean, _ = despeckle_cell(s_img, args.max_speck)
                        if args.apply:
                            Image.fromarray(s_clean, "RGBA").save(src)
        report["families"][family] = {"speck_px": family_specks, "frames": touched}
        report["total_specks"] += family_specks
        if args.apply and family_specks:
            Image.fromarray(atlas_out, "RGBA").save(atlas_png)
            report["files_changed"] += 1

    rc = EXIT_OK
    if args.as_json:
        print(json.dumps(report, indent=2))
    else:
        _util.say("despeckle %s (max speck %d px)"
                  % ("APPLIED" if args.apply else "REPORT ONLY", args.max_speck))
        for family, e in sorted(report["families"].items()):
            _util.say("  %-9s %3d speck px across %d frame(s)"
                      % (family, e["speck_px"], len(e["frames"])))
            for t in e["frames"][:4]:
                _util.say("      %-34s %d px" % (t["frame"], t["specks"]))
        _util.say("  total: %d speck pixel(s)" % report["total_specks"])
        if not args.apply:
            _util.say("  pass --apply to write (sources + atlases, in place)")
    return rc


if __name__ == "__main__":
    sys.exit(_util.guard(main)())
