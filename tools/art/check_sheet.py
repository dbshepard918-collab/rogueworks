"""Deterministic acceptance gate for a generated sprite sheet.

The vision model is a useful second opinion but it is slow, it costs a call, and on pixel art it
has produced confident false positives. This tool answers the questions that decide whether a sheet
is usable AT ALL, with numbers, in under a second:

  * is the background actually key-able (pure magenta family) all round each cell,
  * is there a sprite in every cell (ink coverage neither empty nor filling the cell),
  * are the cells actually DIFFERENT from each other (near-duplicate detection),
  * is the art flat enough to survive palette-locking to 32x32 (colour count).

    python -m tools.art.check_sheet assets/raw/x.png [--cols 4] [--rows 4] [--json]

Exit 0 = usable, 1 = reject (with the per-cell reasons printed).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# Thresholds calibrated against real sheets, not intuition: the hosted sheet that SHIPPED to the
# atlas measures ring-magenta 0.73-0.79 (sprites slightly overhang their cell) and ~650 distinct
# colours at 32x32 (raw anti-aliased AI art - palette locking is what reduces it to <=26 later).
# So: measure the ring loosely, treat colour count as a relative painterliness signal only, and
# lean on duplicate detection, which separated the good sheet (16/16 distinct) from the bad one
# (1/16 distinct) cleanly.
KEY_MIN_RING = 0.70       # fraction of the cell's outer ring that must be magenta
INK_MIN = 0.03            # a cell with less ink than this is empty
INK_MAX = 0.90            # more than this and the sprite has no key-able margin
MAX_COLOURS = 1600        # raw-art painterliness ceiling (post-lock limit is enforced by art.verify)
DUP_DIST = 0.04           # L1 distance between 16x16 ink fingerprints below which = duplicate


def magenta_mask(arr):
    import numpy as np
    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
    return (r > 200) & (b > 200) & (g < 90)


def analyse(path: Path, cols: int, rows: int) -> dict:
    import numpy as np
    from PIL import Image

    img = Image.open(path).convert("RGB")
    w, h = img.size
    cw, ch = w // cols, h // rows
    arr = np.asarray(img).astype("int16")
    cells = []
    for row in range(rows):
        for col in range(cols):
            x0, y0 = col * cw, row * ch
            cell = arr[y0:y0 + ch, x0:x0 + cw]
            key = magenta_mask(cell)
            ring = np.zeros_like(key, dtype=bool)
            b = max(1, min(cw, ch) // 32)
            ring[:b, :] = ring[-b:, :] = True
            ring[:, :b] = ring[:, -b:] = True
            ring_key = float(key[ring].mean()) if ring.any() else 0.0
            ink = float(1.0 - key.mean())
            small = np.asarray(Image.fromarray(cell.astype("uint8")).resize((32, 32), Image.BOX))
            colours = len(np.unique(small.reshape(-1, 3), axis=0))
            fp = np.asarray(Image.fromarray(cell.astype("uint8")).resize((16, 16), Image.BOX))
            fp = (~magenta_mask(fp)).astype("float32")
            reasons = []
            if ring_key < KEY_MIN_RING:
                reasons.append("background not key-able (ring magenta %.2f < %.2f)"
                               % (ring_key, KEY_MIN_RING))
            if ink < INK_MIN:
                reasons.append("empty cell (ink %.2f)" % ink)
            if ink > INK_MAX:
                reasons.append("no margin (ink %.2f) - sprite touches the cell edge" % ink)
            if colours > MAX_COLOURS:
                reasons.append("too painterly (%d colours at 32x32)" % colours)
            cells.append({"index": row * cols + col, "row": row, "col": col,
                          "ring_key": round(ring_key, 3), "ink": round(ink, 3),
                          "colours": colours, "fp": fp, "reasons": reasons})

    pairs = []
    for i in range(len(cells)):
        for j in range(i + 1, len(cells)):
            d = float(np.abs(cells[i]["fp"] - cells[j]["fp"]).mean())
            if d < DUP_DIST:
                pairs.append((cells[i]["index"], cells[j]["index"], round(d, 4)))
                cells[j]["dup_of"] = cells[i]["index"]

    bad = [c for c in cells if c["reasons"]]
    distinct = len([c for c in cells if "dup_of" not in c])
    verdict = "PASS" if not bad and distinct >= max(1, int(0.85 * len(cells))) else "REJECT"
    return {
        "sheet": str(path), "size": [w, h], "grid": [cols, rows], "verdict": verdict,
        "cells": len(cells), "distinct": distinct, "duplicate_pairs": pairs[:24],
        "rejected_cells": [{"index": c["index"], "reasons": c["reasons"]} for c in bad],
        "median_ring_key": round(float(np.median([c["ring_key"] for c in cells])), 3),
        "median_colours": int(np.median([c["colours"] for c in cells])),
        "detail": [{"i": c["index"], "ring": c["ring_key"], "ink": c["ink"],
                    "colours": c["colours"], "dup_of": c.get("dup_of")} for c in cells],
    }


def suggest(rep: dict) -> list[str]:
    """Turn the failure modes into prompt fixes - this is what makes re-rolls get better."""
    tips = []
    if rep["median_ring_key"] < KEY_MIN_RING:
        tips.append("background is not key-able: add 'flat solid #ff00ff magenta background, "
                    "no drop shadow, no gradient behind the subject' and raise the magenta weight")
    if rep["distinct"] < 0.85 * rep["cells"]:
        tips.append("%d/%d cells are near-duplicates: name DISTINCT subjects per cell and vary "
                    "size, pose and species - 'skeleton, rat, bat, spider' not 'undead x4'"
                    % (rep["cells"] - rep["distinct"], rep["cells"]))
    if rep["median_colours"] > MAX_COLOURS:
        tips.append("art is painterly (%d colours at 32x32): add 'flat 3-tone pixel art shading, "
                    "no gradients, no highlights, no rendering'" % rep["median_colours"])
    if rep["rejected_cells"]:
        tips.append("check individual cells: %s" % rep["rejected_cells"][:4])
    return tips


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m tools.art.check_sheet")
    ap.add_argument("sheet")
    ap.add_argument("--cols", type=int, default=4)
    ap.add_argument("--rows", type=int, default=4)
    ap.add_argument("--json", action="store_true", dest="as_json")
    args = ap.parse_args(argv)
    path = Path(args.sheet)
    if not path.is_absolute():
        path = ROOT / path
    if not path.is_file():
        print("no such sheet: %s" % path)
        return 2
    rep = analyse(path, args.cols, args.rows)
    if args.as_json:
        print(json.dumps(rep, indent=2))
        return 0 if rep["verdict"] == "PASS" else 1
    print("check_sheet: %s  %dx%d  grid %dx%d" % (path.name, rep["size"][0], rep["size"][1],
                                                  rep["cols"] if "cols" in rep else args.cols,
                                                  args.rows))
    print("  verdict      : %s" % rep["verdict"])
    print("  key-able ring: median %.2f (need >= %.2f)" % (rep["median_ring_key"], KEY_MIN_RING))
    print("  distinct     : %d/%d cells (%d duplicate pair(s))"
          % (rep["distinct"], rep["cells"], len(rep["duplicate_pairs"])))
    print("  colours@32px : median %d (limit %d)" % (rep["median_colours"], MAX_COLOURS))
    for c in rep["rejected_cells"]:
        print("  cell %2d       : %s" % (c["index"], "; ".join(c["reasons"])))
    if rep["verdict"] != "PASS":
        print("  fix the prompt:")
        for tip in suggest(rep):
            print("    - %s" % tip)
    return 0 if rep["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
