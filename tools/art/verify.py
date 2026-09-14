"""verify: the palette / geometry gate for shipped art.

Checks, in order:

**sprites** (``assets/sprites`` + ``assets/placeholder`` + ``--dir`` extras)

* every pixel is **exactly** a locked palette colour - tolerance **0**, per
  docs/CONTRACTS.md section 6 ("tools.art.verify fails on an off-palette pixel
  (tolerance 0)").  Offenders are reported with their hex, the nearest palette
  colour and the distance, so a failed run is actionable.
* image dimensions are multiples of the 32px tile grid (section 2).
* the chroma key (#ff00ff, which is deliberately *not* a palette colour) never
  survives into shipped art - an error by default, downgraded by ``--allow-key``.

**atlases** (``assets/atlas/*.json``)

* the frozen schema of section 5: ``version``, ``image`` (resolvable path),
  ``meta.tile == 32``, ``meta.palette_version`` matching the palette,
  ``generated_by``, and ``frames`` mapping name -> ``[x, y, w, h]`` ints;
* every rect is inside the sheet and no two rects overlap (padding is fine;
  overlap means two frames fight over the same pixels);
* the sheet's own pixels are palette-locked too.

**aliases** (``assets/aliases.json``, optional)

* shape is ``{"version": 1, "aliases": {alias: real_frame_name}}`` and every
  target resolves to a frame that exists - alias names are resolved by the game's
  Atlas loader and must **never** be duplicated into an atlas JSON (two frames
  sharing a rect is an error, so verify rejects it; it does not inject rects).

Exit 0 when everything passes (including "no art to check yet"), 1 on any error.

    python -m tools.art.verify
    python -m tools.art.verify --dir assets/ui --json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from tools import _util
from tools._util import EXIT_FAIL, EXIT_OK

FRAME_RE = re.compile(r"^[a-z0-9]+(_[a-z0-9]+)*$")
DEFAULT_SPRITE_DIRS = ("assets/sprites", "assets/placeholder")


# --------------------------------------------------------------------------- #
# pixel auditing
# --------------------------------------------------------------------------- #
def _pack(r: int, g: int, b: int) -> int:
    return (int(r) << 16) | (int(g) << 8) | int(b)


def pixel_audit(img, pal: _util.Palette) -> dict:
    """Audit one RGBA image -> counts of off-palette / key / partial-alpha pixels."""
    rgba = img.convert("RGBA")
    allowed = {_pack(*rgb) for rgb in pal.colors.values()}
    key = _pack(*pal.chroma_key)
    off: dict[int, int] = {}
    key_hits = 0
    partial = 0
    opaque = 0
    total = 0

    try:
        import numpy as np

        arr = np.asarray(rgba, dtype=np.uint8)
        packed = (
            arr[..., 0].astype("uint32") << 16
            | arr[..., 1].astype("uint32") << 8
            | arr[..., 2].astype("uint32")
        )
        alpha = arr[..., 3]
        total = int(arr.shape[0] * arr.shape[1])
        opaque = int((alpha > 0).sum())
        partial = int(((alpha > 0) & (alpha < 255)).sum())
        vis = packed[alpha > 0]
        if vis.size:
            vals, counts = np.unique(vis, return_counts=True)
            for value, count in zip(vals.tolist(), counts.tolist()):
                if value in allowed:
                    continue
                if key is not None and value == key:
                    key_hits += int(count)
                    continue
                off[int(value)] = int(count)
    except ImportError:  # pragma: no cover - numpy always present in this venv
        for r, g, b, a in rgba.getdata():
            total += 1
            if a == 0:
                continue
            opaque += 1
            if a < 255:
                partial += 1
            value = _pack(r, g, b)
            if value in allowed:
                continue
            if key is not None and value == key:
                key_hits += 1
                continue
            off[value] = off.get(value, 0) + 1

    return {"total": total, "opaque": opaque, "off": off, "key": key_hits, "partial": partial}


def check_aliases(root: Path, alias_path: Path, atlas_frames: set[str], atlas_count: int):
    """Validate ``assets/aliases.json`` WITHOUT touching atlas rects.

    Aliases are alternative frame names resolved by the game's Atlas loader, so
    they must never be duplicated into an atlas JSON (two frames sharing a rect
    is an error).  This check only makes sure the alias file is well formed and
    every alias points at a frame that actually exists.
    """
    errors: list[str] = []
    warnings: list[str] = []
    if not alias_path.is_file():
        return None, errors, warnings
    rel = _util.rel_posix(alias_path, root)
    try:
        data = _util.load_json(alias_path)
    except _util.ToolError as exc:
        return None, [str(exc)], []
    if not isinstance(data, dict):
        return None, [f"{rel}: top level must be a JSON object"], []
    if data.get("version") != 1:
        errors.append(f"{rel}: version must be 1, got {data.get('version')!r}")
    aliases = data.get("aliases")
    if not isinstance(aliases, dict):
        return None, errors + [f"{rel}: missing 'aliases' object"], []

    for alias, target in aliases.items():
        if not isinstance(alias, str) or not isinstance(target, str):
            errors.append(f"{rel}: alias {alias!r} -> {target!r} must map a string to a string")
            continue
        if not FRAME_RE.match(alias):
            warnings.append(f"{rel}: alias '{alias}' is not snake_case")
        if alias in atlas_frames:
            warnings.append(f"{rel}: alias '{alias}' shadows a real atlas frame of the same name")
        if atlas_count == 0:
            continue  # nothing packed yet; cannot resolve
        if target not in atlas_frames:
            errors.append(f"{rel}: alias '{alias}' points at '{target}', which is not a frame in any "
                          f"assets/atlas/*.json ({len(atlas_frames)} frame(s) known)")
    return len(aliases), errors, warnings


def _hex(value: int) -> str:
    return "#%02x%02x%02x" % ((value >> 16) & 0xFF, (value >> 8) & 0xFF, value & 0xFF)


def _offender_lines(off: dict[int, int], pal: _util.Palette, limit: int) -> list[str]:
    lines: list[str] = []
    for value, count in sorted(off.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]:
        rgb = ((value >> 16) & 0xFF, (value >> 8) & 0xFF, value & 0xFF)
        name, prgb, dist2 = pal.nearest(rgb)
        lines.append(
            f"off-palette {_hex(value)} x{count} (nearest '{name}' #{prgb[0]:02x}{prgb[1]:02x}{prgb[2]:02x}, "
            f"distance {dist2 ** 0.5:.1f})"
        )
    if len(off) > limit:
        lines.append(f"... and {len(off) - limit} more distinct off-palette colour(s)")
    return lines


# --------------------------------------------------------------------------- #
# sprite / atlas checks
# --------------------------------------------------------------------------- #
def check_sprite_dirs(root: Path, dirs: list[Path], pal: _util.Palette, limit: int, allow_key: bool):
    errors: list[str] = []
    warnings: list[str] = []
    checked = 0
    for d in dirs:
        pngs = _util.iter_pngs(d)
        if not pngs:
            continue
        for png in pngs:
            rel = _util.rel_posix(png, root)
            checked += 1
            try:
                from PIL import Image

                with Image.open(png) as img:
                    w, h = img.size
                    if w % _util.TILE or h % _util.TILE:
                        errors.append(f"{rel}: {w}x{h} is not a multiple of the {_util.TILE}px tile grid")
                    audit = pixel_audit(img, pal)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{rel}: cannot read image ({type(exc).__name__}: {exc})")
                continue
            if audit["off"]:
                n = sum(audit["off"].values())
                errors.append(f"{rel}: {n} off-palette pixel(s) across {len(audit['off'])} colour(s)")
                errors.extend("  " + line for line in _offender_lines(audit["off"], pal, limit))
            if audit["key"]:
                # the chroma key is deliberately NOT a palette colour (see
                # assets/palette.json 'notes'), so a surviving key pixel is an
                # off-palette pixel: it fails unless the caller explicitly allows it.
                msg = (f"{rel}: {audit['key']} chroma-key (#ff00ff) pixel(s) survived into shipped art - "
                       "the key was not cut")
                (warnings if allow_key else errors).append(msg)
            if audit["partial"]:
                warnings.append(f"{rel}: {audit['partial']} partial-alpha pixel(s) (art should be 1-bit alpha)")
    return checked, errors, warnings


def check_atlas_json(root: Path, json_path: Path, pal: _util.Palette, limit: int, allow_key: bool):
    errors: list[str] = []
    warnings: list[str] = []
    rel = _util.rel_posix(json_path, root)
    try:
        data = _util.load_json(json_path)
    except _util.ToolError as exc:
        return 0, [str(exc)], []

    if not isinstance(data, dict):
        return 0, [f"{rel}: top level must be a JSON object"], []
    if data.get("version") != 1:
        errors.append(f"{rel}: version must be 1, got {data.get('version')!r}")

    image_ref = data.get("image")
    sheet = None
    if not isinstance(image_ref, str) or not image_ref:
        errors.append(f"{rel}: missing string 'image'")
    else:
        sheet = Path(image_ref) if Path(image_ref).is_absolute() else root / image_ref
        if not sheet.is_file():
            errors.append(f"{rel}: image not found: {image_ref}")
            sheet = None

    meta = data.get("meta")
    if not isinstance(meta, dict):
        errors.append(f"{rel}: missing 'meta' object")
    else:
        if meta.get("tile") != _util.TILE:
            errors.append(f"{rel}: meta.tile must be {_util.TILE}, got {meta.get('tile')!r}")
        if meta.get("palette_version") != pal.version:
            errors.append(
                f"{rel}: meta.palette_version is {meta.get('palette_version')!r} but the palette is v{pal.version} "
                "(art was generated against a different palette)"
            )
        if not isinstance(meta.get("generated_by"), str):
            errors.append(f"{rel}: meta.generated_by must be a string")

    frames = data.get("frames")
    if not isinstance(frames, dict) or not frames:
        errors.append(f"{rel}: missing non-empty 'frames' object")
        frames = {}

    rects: list[tuple[str, tuple[int, int, int, int]]] = []
    for name, rect in frames.items():
        if not FRAME_RE.match(str(name)):
            warnings.append(f"{rel}: frame '{name}' is not snake_case")
        if not isinstance(rect, (list, tuple)) or len(rect) != 4:
            errors.append(f"{rel}: frame '{name}' rect must be [x, y, w, h], got {rect!r}")
            continue
        if not all(isinstance(v, int) and not isinstance(v, bool) for v in rect):
            errors.append(f"{rel}: frame '{name}' rect must be 4 integers, got {rect!r}")
            continue
        x, y, w, h = (int(v) for v in rect)
        if w <= 0 or h <= 0:
            errors.append(f"{rel}: frame '{name}' has non-positive size {w}x{h}")
            continue
        if x < 0 or y < 0:
            errors.append(f"{rel}: frame '{name}' has negative origin ({x}, {y})")
            continue
        rects.append((str(name), (x, y, w, h)))

    if sheet is not None:
        try:
            from PIL import Image

            with Image.open(sheet) as img:
                sw, sh = img.size
                for name, (x, y, w, h) in rects:
                    if x + w > sw or y + h > sh:
                        errors.append(
                            f"{rel}: frame '{name}' rect [{x}, {y}, {w}, {h}] leaves the {sw}x{sh} sheet"
                        )
                    if w % _util.TILE or h % _util.TILE:
                        warnings.append(f"{rel}: frame '{name}' is {w}x{h}, not a tile-grid multiple")
                seen: list[tuple[str, tuple[int, int, int, int]]] = []
                for name, rect in sorted(rects, key=lambda r: (r[1][1], r[1][0])):
                    x, y, w, h = rect
                    for oname, (ox, oy, ow, oh) in seen:
                        if x < ox + ow and ox < x + w and y < oy + oh and oy < y + h:
                            errors.append(f"{rel}: frames '{oname}' and '{name}' overlap")
                            break
                    seen.append((name, rect))
                audit = pixel_audit(img, pal)
                if audit["off"]:
                    n = sum(audit["off"].values())
                    errors.append(f"{rel}: sheet {image_ref} has {n} off-palette pixel(s)")
                    errors.extend("  " + line for line in _offender_lines(audit["off"], pal, limit))
                if audit["key"]:
                    msg = (f"{rel}: sheet {image_ref} contains {audit['key']} chroma-key (#ff00ff) "
                           "pixel(s) - the key was not cut")
                    (warnings if allow_key else errors).append(msg)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{rel}: cannot read sheet {image_ref} ({type(exc).__name__}: {exc})")

    return len(frames), errors, warnings


# --------------------------------------------------------------------------- #
# entry point
# --------------------------------------------------------------------------- #
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m tools.art.verify",
        description="Palette-lock (tolerance 0) and atlas geometry gate for shipped art.",
    )
    ap.add_argument("--atlas", default="assets/atlas", help="atlas dir (default assets/atlas)")
    ap.add_argument("--dir", dest="extra_dirs", action="append", default=None, metavar="DIR",
                    help="extra sprite dir to palette-check (repeatable)")
    ap.add_argument("--no-default-dirs", action="store_true",
                    help="do not check assets/sprites and assets/placeholder automatically")
    ap.add_argument("--palette", default=None, help="palette JSON (default assets/palette.json)")
    ap.add_argument("--limit", type=int, default=10, help="distinct off-palette colours to list (default 10)")
    ap.add_argument("--aliases", default=None, help="alias map JSON (default assets/aliases.json)")
    ap.add_argument("--no-aliases", action="store_true", help="skip alias validation")
    ap.add_argument("--allow-key", action="store_true",
                    help="downgrade surviving chroma-key (#ff00ff) pixels from error to warning")
    ap.add_argument("--json", action="store_true", dest="as_json", help="machine-readable report on stdout")
    args = ap.parse_args(argv)

    root = _util.find_root()
    pal = _util.load_palette(args.palette, root)

    atlas_dir = Path(args.atlas) if Path(args.atlas).is_absolute() else root / args.atlas
    dirs: list[Path] = []
    if not args.no_default_dirs:
        dirs += [root / d for d in DEFAULT_SPRITE_DIRS]
    if args.extra_dirs:
        dirs += [Path(d) if Path(d).is_absolute() else root / d for d in args.extra_dirs]
    dirs = [d for d in dirs if d.is_dir()]

    errors: list[str] = []
    warnings: list[str] = []

    sprites_checked, serr, swarn = check_sprite_dirs(root, dirs, pal, int(args.limit), bool(args.allow_key))
    errors += serr
    warnings += swarn

    atlas_jsons = _util.iter_files(atlas_dir, (".json",))
    frames_seen = 0
    all_frames: set[str] = set()
    for jp in atlas_jsons:
        n, aerr, awarn = check_atlas_json(root, jp, pal, int(args.limit), bool(args.allow_key))
        frames_seen += n
        errors += aerr
        warnings += awarn
        try:
            data = _util.load_json(jp)
            if isinstance(data, dict) and isinstance(data.get("frames"), dict):
                all_frames |= {str(k) for k in data["frames"]}
        except _util.ToolError:
            pass

    n_aliases = None
    if not args.no_aliases:
        alias_path = Path(args.aliases) if args.aliases else root / "assets" / "aliases.json"
        n_aliases, aerr, awarn = check_aliases(root, alias_path, all_frames, len(atlas_jsons))
        errors += aerr
        warnings += awarn

    ok = not errors
    if args.as_json:
        print(json.dumps({
            "ok": ok,
            "palette": pal.name,
            "palette_version": pal.version,
            "palette_colours": len(pal),
            "sprites_checked": sprites_checked,
            "atlases_checked": len(atlas_jsons),
            "frames": frames_seen,
            "aliases": n_aliases,
            "errors": errors,
            "warnings": warnings,
        }, indent=2))
        return EXIT_OK if ok else EXIT_FAIL

    _util.say(
        f"verify: palette '{pal.name}' v{pal.version} ({len(pal)} colours), tolerance 0 | "
        f"sprites checked: {sprites_checked} in {len(dirs)} dir(s) | "
        f"atlases: {len(atlas_jsons)} ({frames_seen} frames)"
        + (f" | aliases: {n_aliases}" if n_aliases is not None else "")
    )
    if not sprites_checked and not atlas_jsons:
        _util.say("0 art files found under assets/sprites, assets/placeholder or assets/atlas - nothing to verify")
        return EXIT_OK
    for w in warnings:
        _util.warn(w)
    for e in errors:
        print(e if e.startswith("  ") else f"ERROR {e}", file=sys.stderr)
    if ok:
        _util.say(f"PASS: {sprites_checked} sprite file(s), {frames_seen} frame(s), 0 off-palette pixel(s)")
        return EXIT_OK
    _util.say(f"FAIL: {len(errors)} error(s), {len(warnings)} warning(s)")
    return EXIT_FAIL


if __name__ == "__main__":
    sys.exit(_util.guard(main)())
