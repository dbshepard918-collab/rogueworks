"""sprite-critique: the art feedback loop, with the VLM on a leash.

    python -m tools.qa.sprite_critique                 # metrics only (fast, offline)
    python -m tools.qa.sprite_critique --vlm           # + a local-VLM critique
    python -m tools.qa.sprite_critique --vlm --json

Two halves, deliberately separated:

**Objective half (authoritative).** Pixel art has mechanical properties and they
are measurable, so a model never gets to assert them: alpha is 0 or 255 (no
anti-aliasing), every colour is in the locked palette, the sprite fills enough of
its cell to read, and silhouettes are distinct from one another.

**Vision half (judgement only).** A local VLM answers the question no metric can:
*do these read as the things they are supposed to be?* It runs against a strict
rubric, because unguided it gives wrong medium advice — asked openly, qwen3-vl-8b
recommended "add consistent, clean anti-aliasing" for pixel art, which is the
opposite of correct. Domain rules are stated in the prompt and mechanical claims
are marked as already measured, so the model argues about subjects, not pixels.

Why this exists: the pipeline generated, post-processed and palette-verified ~200
sprites without ever once asking whether a single one looked like its subject.
Palette compliance is not quality.

Exit status: 0 no defects, 1 defects found, 2 prerequisites missing.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.request
from itertools import combinations

from tools import _util  # noqa: E402
from tools._util import EXIT_FAIL, EXIT_OK, EXIT_PREREQ  # noqa: E402

ATLAS_DIR = "assets/atlas"
DEFAULT_ATLASES = ("monsters", "props", "items", "bosses")

#: pixel-art acceptance thresholds (see the module docstring)
MIN_FILL = 0.06          # a sprite under 6% of its cell is a speck, not a sprite
FLAT_FILL = 0.98         # a sprite filling its whole cell in <= FLAT_COLOURS colours
FLAT_COLOURS = 8         # is a coloured rectangle, not art (found: 6 shipped props)
MAX_DUPLICATE_IOU = 0.92 # silhouettes this similar are the same sprite twice

#: Duplicate silhouettes are a DEFECT where the player must tell entities apart,
#: and normal for a family of consumables (potions share a bottle shape on purpose
#: and are distinguished by colour). Only the first set fails the gate.
DISTINCTNESS_REQUIRED = ("monsters", "props")

#: Fragmenting a sprite into detached specks is a defect where a single readable body
#: is expected. Particles legitimately have several components, so vfx is exempt.
FRAGMENTATION_REQUIRED = ("monsters", "props", "items", "bosses")
MAX_SPEC_PX = 3          # a component this small (and not the body) is a speck
VLM_ENDPOINT = "http://localhost:1234/v1/chat/completions"
VLM_MODEL = "qwen/qwen3-vl-8b"

RUBRIC = (
    "You are the art director for a top-down action roguelite. The image is a contact sheet of the "
    "sprites that ship in the game, each shown at 4x on a grey tile, ordered left-to-right, top-to-bottom.\n"
    "HOUSE RULES, already enforced by measurement - do NOT contradict them or suggest breaking them:\n"
    "  * this is HARD-EDGED pixel art: every pixel is fully opaque or fully transparent, so "
    "'anti-aliasing', 'softer edges' and 'gradients' are DEFECTS here, never improvements;\n"
    "  * the palette is limited to 26 colours on purpose;\n"
    "  * sprite sizes and grid alignment are already verified correct.\n"
    "Answer ONLY these questions, terse and specific:\n"
    "1. Does each sprite read as a distinct OBJECT at 32x32, or are some an unreadable blob? Name the "
    "   worst offenders by position (row/column).\n"
    "2. Which sprites are near-duplicates of each other that a player could not tell apart?\n"
    "3. Does anything look like a resized photograph or a smooth gradient rather than pixel art?\n"
    "4. One concrete, in-medium improvement (hard edges, silhouette, silhouette contrast against the "
    "   floor - NOT anti-aliasing).\n"
    "5. Score 1-10 for 'would a player read this as deliberate game art'."
)


def _alpha_metrics(cell) -> dict:
    import numpy as np
    a = cell[..., 3]
    return {
        "opaque": int((a == 255).sum()),
        "partial": int(((a > 0) & (a < 255)).sum()),
        "fill": float((a > 0).mean()),
    }


def _components(mask) -> list:
    """4-connected component sizes of a boolean mask, largest first (flood fill)."""
    from collections import deque
    h, w = mask.shape
    seen = [[False] * w for _ in range(h)]
    sizes = []
    for y0 in range(h):
        for x0 in range(w):
            if not mask[y0][x0] or seen[y0][x0]:
                continue
            q = deque([(y0, x0)])
            seen[y0][x0] = True
            n = 0
            while q:
                cy, cx = q.popleft()
                n += 1
                for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    ny, nx = cy + dy, cx + dx
                    if 0 <= ny < h and 0 <= nx < w and mask[ny][nx] and not seen[ny][nx]:
                        seen[ny][nx] = True
                        q.append((ny, nx))
            sizes.append(n)
    return sorted(sizes, reverse=True)


def measure(root) -> dict:
    """Objective audit over the atlases. No model involved."""
    import numpy as np
    from PIL import Image

    report = {"atlases": {}, "problems": []}
    for name in DEFAULT_ATLASES:
        png = root / ATLAS_DIR / (name + ".png")
        meta = root / ATLAS_DIR / (name + ".json")
        if not (png.is_file() and meta.is_file()):
            continue
        frames = json.loads(meta.read_text(encoding="utf-8")).get("frames", {})
        arr = np.asarray(Image.open(png).convert("RGBA"))
        opaque = partial = 0
        fills, colours = [], []
        flats = []
        fragmented = []
        # silhouettes are only comparable WITHIN an atlas: a coffer and a monster
        # sharing a bounding box is not a duplicate
        masks_by_size = {}
        for fname in sorted(frames):
            x, y, w, h = frames[fname][:4]
            cell = arr[y:y + h, x:x + w]
            m = _alpha_metrics(cell)
            opaque += m["opaque"]
            partial += m["partial"]
            vis = cell[cell[..., 3] > 0]
            n_colours = len({tuple(p) for p in vis[:, :3]}) if vis.size else 0
            if vis.size:
                fills.append(m["fill"])
                colours.append(n_colours)
                if m["fill"] > FLAT_FILL and n_colours <= FLAT_COLOURS:
                    flats.append((fname, n_colours))
                comps = _components(cell[..., 3] > 0)
                specks = [c for c in comps[1:] if c <= MAX_SPEC_PX]
                if specks:
                    fragmented.append((fname, len(comps), len(specks), sum(specks)))
                masks_by_size.setdefault((w, h), []).append((fname, (cell[..., 3] > 0).astype(np.uint8)))

        dupes = []
        for size, group in masks_by_size.items():
            masks = [m for _, m in group]
            names = [n for n, _ in group]
            for (na, a), (nb, b) in combinations(list(zip(names, masks)), 2):
                union = int((a | b).sum())
                if union and int((a & b).sum()) / union > MAX_DUPLICATE_IOU:
                    dupes.append([na, nb])

        entry = {
            "frames": len(frames),
            "opaque_px": opaque,
            "partial_alpha_px": partial,
            "partial_alpha_pct": round(100.0 * partial / max(1, opaque + partial), 4),
            "fill_mean": round(float(np.mean(fills)), 4) if fills else 0.0,
            "fill_min": round(float(np.min(fills)), 4) if fills else 0.0,
            "colours_mean": round(float(np.mean(colours)), 1) if colours else 0.0,
            "colours_max": int(max(colours)) if colours else 0,
            "flat_sprites": [f for f, _ in flats],
            "fragmented_sprites": [{"frame": f, "components": c, "specks": s, "speck_px": px}
                                   for f, c, s, px in fragmented[:12]],
            "fragmented_count": len(fragmented),
            "near_duplicates": dupes[:12],
            "near_duplicates_advisory": name not in DISTINCTNESS_REQUIRED and bool(dupes),
        }
        report["atlases"][name] = entry
        if entry["partial_alpha_px"]:
            report["problems"].append("%s: %d anti-aliased pixel(s) - pixel art must be hard-edged"
                                      % (name, entry["partial_alpha_px"]))
        for fname, n_colours in flats:
            report["problems"].append(
                "%s: %s is a FLAT RECTANGLE (%d colours filling its whole cell) - not art"
                % (name, fname, n_colours))
        if name in FRAGMENTATION_REQUIRED and fragmented:
            worst = max(fragmented, key=lambda r: r[2])
            report["problems"].append(
                "%s: %d sprite(s) fragment into detached specks, worst %s (%d components, "
                "%d specks) - the sprite is falling apart" % (name, len(fragmented), worst[0],
                                                              worst[1], worst[2]))
        elif fragmented:
            report.setdefault("advisory", []).append(
                "%s: %d particle frame(s) have detached motes - expected for a particle effect"
                % (name, len(fragmented)))
        if entry["fill_min"] and entry["fill_min"] < MIN_FILL:
            report["problems"].append("%s: a sprite fills only %.1f%% of its cell (min %.0f%%)"
                                      % (name, 100 * entry["fill_min"], 100 * MIN_FILL))
        if name in DISTINCTNESS_REQUIRED:
            for pair in dupes:
                report["problems"].append("%s: near-identical silhouettes %s / %s - the player "
                                          "cannot tell them apart" % (name, pair[0], pair[1]))
        elif dupes:
            report.setdefault("advisory", []).append(
                "%s: %d near-identical silhouette pair(s) - expected for a consumable family "
                "distinguished by colour" % (name, len(dupes)))
    return report


def vlm_critique(sheet_path, timeout=600) -> str:
    with open(sheet_path, "rb") as fh:
        b64 = base64.b64encode(fh.read()).decode()
    body = {
        "model": VLM_MODEL,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": RUBRIC},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64," + b64}},
        ]}],
        "max_tokens": 700, "temperature": 0.2,
    }
    req = urllib.request.Request(VLM_ENDPOINT, data=json.dumps(body).encode(),
                                headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())["choices"][0]["message"]["content"]


def build_contact_sheet(root, out_path, max_w=1600, max_h=1200):
    """Contact sheet at the largest WHOLE scale that fits the pixel budget.

    An unnecessarily large sheet is not free: the local VLM processes it as
    visual tokens (77 s for 2116x1896), and downscaling a finished sheet would
    blur the very pixels under review. Choosing an integer scale up front keeps
    NEAREST crispness and bounds the cost.
    """
    from PIL import Image, ImageDraw
    cols, pad = 16, 4
    items = []
    for name in DEFAULT_ATLASES:
        png = root / ATLAS_DIR / (name + ".png")
        meta = root / ATLAS_DIR / (name + ".json")
        if not (png.is_file() and meta.is_file()):
            continue
        frames = json.loads(meta.read_text(encoding="utf-8")).get("frames", {})
        src = Image.open(png).convert("RGBA")
        for frame_name in sorted(frames):
            items.append((src, frames[frame_name]))
    if not items:
        return None

    rows = (len(items) + cols - 1) // cols
    scale = 1
    for candidate in (4, 3, 2, 1):
        cell = 32 * candidate
        if cols * (cell + pad) + pad <= max_w and rows * (cell + pad) + pad <= max_h:
            scale = candidate
            break
    cell = 32 * scale
    canvas = Image.new("RGB", (cols * (cell + pad) + pad, rows * (cell + pad) + pad),
                       (26, 24, 34))
    draw = ImageDraw.Draw(canvas)
    for i, (src, box) in enumerate(items):
        r, c = divmod(i, cols)
        x, y = pad + c * (cell + pad), pad + r * (cell + pad)
        draw.rectangle([x - 1, y - 1, x + cell, y + cell], fill=(70, 64, 86))
        sprite = src.crop((box[0], box[1], box[0] + box[2], box[1] + box[3]))
        sprite = sprite.resize((cell, cell), Image.NEAREST)
        canvas.paste(sprite, (x, y), sprite)
    canvas.save(out_path)
    return out_path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m tools.qa.sprite_critique",
        description="Art feedback loop: objective sprite metrics + an optional local-VLM critique.",
    )
    ap.add_argument("--vlm", action="store_true", help="also run the local-VLM critique")
    ap.add_argument("--json", action="store_true", dest="as_json")
    ap.add_argument("--sheet", default=None, help="contact-sheet output path")
    args = ap.parse_args(argv)

    root = _util.find_root()
    sys.path.insert(0, str(root))
    if not (root / ATLAS_DIR).is_dir():
        _util.say("no %s yet - nothing to critique" % ATLAS_DIR)
        return EXIT_PREREQ

    report = measure(root)
    vlm_text = None
    if args.vlm:
        sheet = args.sheet or os.path.join(os.environ.get("TEMP", "."), "rw_sprite_contact.png")
        build_contact_sheet(root, sheet)
        try:
            vlm_text = vlm_critique(sheet)
        except Exception as exc:                                  # noqa: BLE001
            vlm_text = "VLM critique unavailable: %s: %s" % (type(exc).__name__, exc)
        report["contact_sheet"] = sheet
        report["vlm"] = vlm_text

    rc = EXIT_FAIL if report["problems"] else EXIT_OK
    if args.as_json:
        print(json.dumps({"ok": rc == EXIT_OK, **report}, indent=2))
        return rc

    _util.say("sprite critique (objective)")
    for name, e in sorted(report["atlases"].items()):
        _util.say("  %-9s %3d frames  partial-alpha=%.2f%%  fill %.0f-%.0f%%  colours avg %.1f max %d  "
                  "flat=%d  dupes=%d%s"
                  % (name, e["frames"], e["partial_alpha_pct"], 100 * e["fill_min"],
                     100 * e["fill_mean"], e["colours_mean"], e["colours_max"],
                     len(e["flat_sprites"]), len(e["near_duplicates"]),
                     " (advisory)" if e.get("near_duplicates_advisory") else ""))
    for p in report["problems"]:
        _util.say("  [FAIL] %s" % p)
    for a in report.get("advisory", []):
        _util.say("  [note] %s" % a)
    if vlm_text:
        _util.say("")
        _util.say("  --- local VLM critique (%s) ---" % VLM_MODEL)
        for line in vlm_text.splitlines():
            _util.say("  " + line)
    _util.say("OK: no objective art defects" if rc == EXIT_OK
              else "FAILED: %d art defect(s)" % len(report["problems"]))
    return rc


if __name__ == "__main__":
    sys.exit(_util.guard(main)())
