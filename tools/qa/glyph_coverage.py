"""glyph-coverage: every character the game draws must have a real glyph.

    python -m tools.qa.glyph_coverage
    python -m tools.qa.glyph_coverage --json

The UI font is a hand-built bitmap glyph table (`FONT_GLYPHS` in
``game/engine/assets.py``).  A missing glyph is not an error — ``BitmapFont.render``
silently falls back to a space — so a string like ``"floor 1 (Catacombs)"`` loses
its parentheses and nobody notices until a player reads the screen.  That is how
the end screen shipped with silent gaps.

This tool does two things:

1. **Scan** every string literal in ``game/`` for characters that have no glyph,
   so real UI text counts as evidence rather than a hand-written sample.
2. **Require** a core ASCII set (digits, both cases, and the punctuation a UI
   actually uses) regardless of whether the current strings happen to exercise it.

Exit status: 0 every character is renderable, 1 glyphs are missing,
2 the game package is not importable yet.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import string
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

from tools import _util  # noqa: E402
from tools._util import EXIT_FAIL, EXIT_OK, EXIT_PREREQ  # noqa: E402

#: Functions whose string arguments end up on screen.  Matched by attribute/name
#: so `assets.draw_text`, `menus_mod.draw_title`, `surface.blit`-adjacent helpers
#: and the FONT.render seam are all covered.
DRAW_CALLS = {
    "draw_text", "draw_title", "draw_title_animated", "draw_list", "status",
    "set_caption", "render", "say", "_branch_header", "_tier_line",
}


def required_chars() -> set[str]:
    """Printable ASCII is the contract: a UI font must render all of it."""
    return {chr(c) for c in range(0x20, 0x7F)}


def _literal_parts(node) -> str:
    """Characters guaranteed to reach the screen from one argument expression."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):                 # f-string
        return "".join(v.value for v in node.values
                       if isinstance(v, ast.Constant) and isinstance(v.value, str))
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Mod, ast.Add)):
        return _literal_parts(node.left) + _literal_parts(node.right)
    if isinstance(node, (ast.Tuple, ast.List)):
        return "".join(_literal_parts(e) for e in node.elts)
    return ""


def _call_name(node) -> str:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return ""


def scan_drawn_strings(root: Path) -> dict[str, list[str]]:
    """Map character -> where it is actually drawn (call sites + content JSON)."""
    used: dict[str, set[str]] = {}

    def note(text: str, where: str) -> None:
        for ch in text:
            if ch.isprintable() and ch != " ":
                used.setdefault(ch, set()).add(where)

    for path in sorted((root / "game").rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        rel = _util.rel_posix(path, root)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or _call_name(node) not in DRAW_CALLS:
                continue
            for arg in list(node.args) + [kw.value for kw in node.keywords]:
                note(_literal_parts(arg), "%s:%d" % (rel, node.lineno))

    # content values are drawn too (item names, flavour lines, monster names)
    for jpath in sorted((root / "game" / "data").glob("*.json")):
        try:
            data = json.loads(jpath.read_text(encoding="utf-8", errors="replace"))
        except (OSError, json.JSONDecodeError):
            continue
        rel = _util.rel_posix(jpath, root)
        stack = [data]
        while stack:
            item = stack.pop()
            if isinstance(item, dict):
                stack.extend(item.values())
            elif isinstance(item, list):
                stack.extend(item)
            elif isinstance(item, str):
                note(item, rel)
    return {ch: sorted(where) for ch, where in used.items()}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m tools.qa.glyph_coverage",
        description="Report characters the UI font cannot render.",
    )
    ap.add_argument("--json", action="store_true", dest="as_json", help="machine-readable report")
    args = ap.parse_args(argv)

    root = _util.find_root()
    sys.path.insert(0, str(root))
    if not (root / "game" / "engine" / "assets.py").is_file():
        _util.say("game package not built yet - nothing to check")
        return EXIT_PREREQ

    import pygame

    pygame.init()
    pygame.display.set_mode((1, 1))

    from game.engine import assets

    glyphs = set(assets.FONT_GLYPHS)
    used = scan_drawn_strings(root)

    # the renderer uppercases before lookup (FONT_GLYPHS.get(ch.upper())), so a
    # lowercase letter is covered by its uppercase glyph
    required = required_chars()
    missing_required = sorted(c for c in required if c.upper() not in glyphs)
    missing_in_use = sorted(ch for ch in used if ch.upper() not in glyphs)
    all_missing = sorted(set(missing_required) | set(missing_in_use))

    report = {
        "glyphs_defined": len(glyphs),
        "required_chars": len(required),
        "chars_used_by_game_strings": len(used),
        "missing_required": missing_required,
        "missing_in_use": missing_in_use,
        "missing_detail": {ch: used.get(ch, []) for ch in all_missing},
        "non_ascii_in_use": sorted(ch for ch in used if ord(ch) > 126),
    }
    rc = EXIT_FAIL if all_missing else EXIT_OK

    if args.as_json:
        print(json.dumps({"ok": rc == EXIT_OK, **report}, indent=2))
        return rc

    _util.say("glyph coverage: %d glyph(s) defined, %d required (printable ASCII), "
              "%d used by drawn strings" % (report["glyphs_defined"], report["required_chars"],
                                            report["chars_used_by_game_strings"]))
    if report["non_ascii_in_use"]:
        _util.say("  non-ASCII appearing in drawn text: %s"
                  % " ".join(repr(c) for c in report["non_ascii_in_use"]))
    for ch in all_missing:
        where = report["missing_detail"].get(ch) or []
        origin = ("drawn at " + ", ".join(where[:4])) if where else "required set only"
        _util.say("  [FAIL] missing glyph %r  (%s)" % (ch, origin))
    _util.say("OK: every required and in-use character is renderable" if rc == EXIT_OK
              else "FAILED: %d glyph(s) missing - UI text using them renders as blanks"
                   % len(all_missing))
    return rc


if __name__ == "__main__":
    sys.exit(_util.guard(main)())
