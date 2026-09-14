"""pack palette-locked sprites into an atlas sheet + rect manifest.

``assets/sprites/<name>/**/*.png`` -> ``assets/atlas/<name>.png`` + ``assets/atlas/<name>.json``

The JSON is exactly the frozen format of docs/CONTRACTS.md section 5::

    {"version": 1, "image": "assets/atlas/<name>.png",
     "meta": {"tile": 32, "palette_version": 1, "generated_by": "pixel"},
     "frames": {"player_idle_0": [0, 0, 32, 32], ...}}

Rects are ``[x, y, w, h]`` atlas pixels, top-left origin, no scaling and
(default) no padding, so ``Atlas.frame(name)`` can blit straight out of the sheet.
Frame names come from the file stem, prefixed with any sub-directory path
(``catacombs/wall.png`` -> ``catacombs_wall``), which is how tilesets get their
``<thing>_<biome>`` prefix.

Usage
-----
    python -m tools.art.pack_atlas --name player
    python -m tools.art.pack_atlas --name tiles --sprites assets/sprites/catacombs
    python -m tools.art.pack_atlas --name all --sprites assets/sprites/player assets/sprites/monsters
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from tools import _util
from tools._util import EXIT_OK, ToolError

GENERATED_BY = "pixel"
MAX_PAD = 1  # docs/CONTRACTS.md section 5: "no padding > 1px"


def frame_name(root_dir: Path, png: Path) -> str:
    """``catacombs/wall.png`` -> ``catacombs_wall``; ``wall.png`` -> ``wall``."""
    rel = png.relative_to(root_dir)
    parts = list(rel.parts)
    parts[-1] = Path(parts[-1]).stem
    return "_".join(parts)


def collect_frames(roots: list[Path]) -> tuple[list[tuple[str, Path]], list[str]]:
    """Sorted ``(frame_name, png_path)`` pairs; de-duplicates with a warning list."""
    used: dict[str, Path] = {}
    warnings: list[str] = []
    out: list[tuple[str, Path]] = []
    for root in roots:
        for png in _util.iter_pngs(root):
            name = frame_name(root, png)
            if name in used:
                alt = f"{root.name}_{name}"
                warnings.append(f"duplicate frame '{name}' from {png.name}; renamed to '{alt}'")
                name = alt
                n = 2
                while name in used:
                    name = f"{alt}_{n}"
                    n += 1
            used[name] = png
            out.append((name, png))
    out.sort(key=lambda pair: pair[0])
    return out, warnings


def resolve_sprite_dirs(root: Path, name: str | None, explicit: list[str] | None) -> list[Path]:
    if explicit:
        dirs = [Path(p) if Path(p).is_absolute() else root / p for p in explicit]
        for d in dirs:
            if not d.is_dir():
                raise ToolError(f"sprite directory not found: {d}")
        return dirs
    base = root / "assets" / "sprites"
    if name and (base / name).is_dir():
        return [base / name]
    if base.is_dir():
        subdirs = sorted([d for d in base.iterdir() if d.is_dir()])
        if name:
            avail = ", ".join(d.name for d in subdirs) or "none"
            raise ToolError(f"assets/sprites/{name} not found (available: {avail})")
        if len(subdirs) == 1:
            return [subdirs[0]]
        if len(subdirs) > 1:
            avail = ", ".join(d.name for d in subdirs)
            raise ToolError(f"several sprite sets exist ({avail}); pass --name or --sprites")
    return []


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m tools.art.pack_atlas",
        description="Pack assets/sprites into assets/atlas/<name>.png + <name>.json.",
    )
    ap.add_argument("--name", default=None, help="atlas name (also the sprites/<name> default)")
    ap.add_argument("--sprites", nargs="*", default=None, metavar="DIR",
                    help="sprite director(ies); default assets/sprites/<name>")
    ap.add_argument("--out", default="assets/atlas", help="atlas output dir (default assets/atlas)")
    ap.add_argument("--palette", default=None, help="palette JSON (default assets/palette.json)")
    ap.add_argument("--cols", type=int, default=0, help="columns; 0 -> square-ish sheet")
    ap.add_argument("--pad", type=int, default=0, help="padding px around each frame (0 or 1)")
    args = ap.parse_args(argv)

    root = _util.find_root()
    pal = _util.load_palette(args.palette, root)

    pad = int(args.pad)
    if pad < 0 or pad > MAX_PAD:
        raise ToolError(f"--pad must be 0 or 1 (contract: no padding > 1px), got {pad}")

    dirs = resolve_sprite_dirs(root, args.name, args.sprites)
    if not dirs:
        _util.say("0 sprite sets found under assets/sprites - nothing to pack")
        _util.say("hint: python -m tools.art.pixelize --raw assets/raw/art.png --name <set>")
        return EXIT_OK

    pairs, warnings = collect_frames(dirs)
    for w in warnings:
        _util.warn(w)
    if not pairs:
        _util.say(f"0 sprite PNGs found in {', '.join(_util.rel_posix(d, root) for d in dirs)} - nothing to pack")
        return EXIT_OK

    name = args.name or dirs[0].name
    out_dir = Path(args.out) if Path(args.out).is_absolute() else root / args.out

    return _pack(root, name, pairs, pal, int(args.cols), pad, out_dir)


def _pack(root: Path, name: str, pairs, pal: _util.Palette, cols: int, pad: int, out_dir: Path) -> int:
    from PIL import Image

    images: list[tuple[str, "Image.Image"]] = []
    for fname, png in pairs:
        img = Image.open(png).convert("RGBA")
        images.append((fname, img))

    cell_w = max(img.width for _, img in images)
    cell_h = max(img.height for _, img in images)
    n = len(images)
    if cols <= 0:
        cols = 1
        while cols * cols < n:
            cols += 1
    cols = min(cols, n)
    rows = (n + cols - 1) // cols

    step_x, step_y = cell_w + pad, cell_h + pad
    sheet_w, sheet_h = cols * step_x, rows * step_y
    sheet = Image.new("RGBA", (sheet_w, sheet_h), (0, 0, 0, 0))

    frames: dict[str, list[int]] = {}
    for idx, (fname, img) in enumerate(images):
        row, col = divmod(idx, cols)
        x, y = col * step_x + pad, row * step_y + pad
        sheet.paste(img, (x, y))  # alpha preserved
        frames[fname] = [x, y, img.width, img.height]

    out_dir = _util.ensure_dir(out_dir)
    png_path = out_dir / f"{name}.png"
    json_path = out_dir / f"{name}.json"
    sheet.save(png_path)
    _util.write_json(
        json_path,
        {
            "version": 1,
            "image": _util.rel_posix(png_path, root),
            "meta": {
                "tile": _util.TILE,
                "palette_version": pal.version,
                "generated_by": GENERATED_BY,
            },
            "frames": frames,
        },
    )

    _util.say(f"pack_atlas: {n} frame(s) -> {_util.rel_posix(png_path, root)} ({sheet_w}x{sheet_h})")
    _util.say(f"            manifest -> {_util.rel_posix(json_path, root)}  cell {cell_w}x{cell_h}, {cols}x{rows}, pad {pad}")
    _util.say(f"next: python -m tools.art.verify --atlas {_util.rel_posix(out_dir, root)}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(_util.guard(main)())
