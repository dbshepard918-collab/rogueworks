"""generate the flat-colour placeholder set so the game always has art to load.

``Atlas.load(name)`` must never crash on a missing frame (docs/CONTRACTS.md
section 5): it returns a placeholder surface and appends to ``world.warnings``.
This tool writes that fallback family into ``assets/placeholder/`` - flat,
palette-locked, grid-aligned, deliberately ugly so nobody ships them by accident.

    python -m tools.art.placeholders            # (re)write every placeholder
    python -m tools.art.placeholders --pack-atlas   # also build assets/atlas/placeholder.*

Names are stable and documented in the generated ``placeholder.json``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from tools import _util
from tools._util import EXIT_OK

# name -> (w, h, base colour, accent colour, style)
# style: fill | border | blob | cross | frame | bar
PLACEHOLDERS: dict[str, tuple[int, int, str, str, str]] = {
    "missing":        (32, 32, "void",        "flesh",        "blob"),
    "player":         (32, 32, "steel",       "white",        "blob"),
    "monster":        (32, 32, "blood",       "bone",         "blob"),
    "boss":           (64, 64, "blood_dark",  "flame",        "blob"),
    "projectile":     (32, 32, "arcane",      "arcane_light", "blob"),
    "pickup":         (32, 32, "gold",        "gold_dark",    "blob"),
    "prop":           (32, 32, "stone",       "stone_light",  "border"),
    "tile":           (32, 32, "stone_dark",  "stone",        "border"),
    "tile_light":     (32, 32, "stone",       "stone_light",  "border"),
    "stairs":         (32, 32, "slate",       "bone",         "cross"),
    "chest":          (32, 32, "gold_dark",   "gold",         "border"),
    "key":            (32, 32, "gold",        "white",        "cross"),
    "orb_health":     (32, 32, "flesh",       "white",        "cross"),
    "cursor":         (32, 32, "white",       "ink",          "frame"),
    "ui_icon":        (32, 32, "ink",         "steel",        "border"),
    "ui_frame":       (96, 96, "ink",         "stone",        "frame"),
    "ui_panel":      (128, 64, "ink",         "stone",        "frame"),
    "ui_bar":        (128, 32, "blood_dark",  "blood",        "bar"),
}


def _draw(w: int, h: int, base, accent, style: str):
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if style == "bar":
        d.rectangle([0, 0, w - 1, h - 1], fill=base)
        d.rectangle([2, 2, w - 3, h - 3], fill=accent)
    elif style == "frame":
        d.rectangle([0, 0, w - 1, h - 1], outline=accent, width=2)
        d.rectangle([2, 2, w - 3, h - 3], fill=base)
    elif style == "border":
        d.rectangle([0, 0, w - 1, h - 1], fill=base)
        d.rectangle([0, 0, w - 1, h - 1], outline=accent)
    elif style == "cross":
        d.rectangle([0, 0, w - 1, h - 1], fill=base)
        c = w // 2
        d.rectangle([c - 2, 4, c + 1, h - 5], fill=accent)
        d.rectangle([4, c - 2, w - 5, c + 1], fill=accent)
    else:  # blob: a filled rounded square, unmistakably a placeholder
        m = max(2, w // 8)
        d.rectangle([m, m, w - 1 - m, h - 1 - m], fill=base)
        d.rectangle([w // 2 - 2, h // 2 - 2, w // 2 + 1, h // 2 + 1], fill=accent)
        d.rectangle([m, m, w - 1 - m, h - 1 - m], outline=accent)
    return img


def generate(out_dir: Path, pal: _util.Palette) -> list[tuple[str, Path]]:
    written: list[tuple[str, Path]] = []
    for name, (w, h, base_name, accent_name, style) in PLACEHOLDERS.items():
        for colour in (base_name, accent_name):
            if colour not in pal.colors:
                raise _util.ToolError(
                    f"palette has no colour '{colour}' needed by placeholder '{name}' "
                    f"(available: {', '.join(sorted(pal.colors))})"
                )
        img = _draw(w, h, pal.colors[base_name], pal.colors[accent_name], style)
        path = out_dir / f"{name}.png"
        img.save(path)
        written.append((name, path))
    return written


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m tools.art.placeholders",
        description="Write the flat palette-coloured placeholder art the game falls back to.",
    )
    ap.add_argument("--out", default="assets/placeholder", help="output dir (default assets/placeholder)")
    ap.add_argument("--palette", default=None, help="palette JSON (default assets/palette.json)")
    ap.add_argument("--pack-atlas", action="store_true",
                    help="also pack them into assets/atlas/placeholder.png + .json")
    args = ap.parse_args(argv)

    root = _util.find_root()
    pal = _util.load_palette(args.palette, root)
    out_dir = _util.ensure_dir(Path(args.out) if Path(args.out).is_absolute() else root / args.out)

    written = generate(out_dir, pal)
    manifest = {
        "version": 1,
        "generated_by": "pixel",
        "palette_version": pal.version,
        "note": "flat fallbacks; Atlas.load must return these instead of crashing on a missing frame",
        "frames": {name: {"file": _util.rel_posix(path, root), "size": list(path_sizes(name))}
                   for name, path in written},
    }
    _util.write_json(out_dir / "placeholder.json", manifest)

    _util.say(f"placeholders: {len(written)} PNG(s) -> {_util.rel_posix(out_dir, root)}/")
    for name, _ in written:
        w, h, base, accent, style = PLACEHOLDERS[name]
        _util.say(f"  {name:12} {w:>3}x{h:<3} {style:5} {base}/{accent}")
    _util.say(f"manifest -> {_util.rel_posix(out_dir / 'placeholder.json', root)}")

    if args.pack_atlas:
        from tools.art import pack_atlas

        rc = pack_atlas.main([
            "--name", "placeholder",
            "--sprites", str(out_dir),
            "--palette", str(pal.source),
        ])
        if rc != EXIT_OK:
            return rc
    return EXIT_OK


def path_sizes(name: str) -> tuple[int, int]:
    w, h, *_ = PLACEHOLDERS[name]
    return w, h


if __name__ == "__main__":
    sys.exit(_util.guard(main)())
