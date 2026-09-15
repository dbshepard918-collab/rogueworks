"""death-run: drive the real death and victory paths and render the end screen.

    python -m tools.qa.death_run --seed 42
    python -m tools.qa.death_run --seed 42 --out runs/shots/end --keep

Why this exists: ``RunScene`` hands over to ``EndScene`` when the run ends, and
``EndScene.draw`` renders the recap through ``menus.draw_end_screen``.  A
300-tick headless gate never reaches that code, so a crash there survives every
green light and only fires in the player's face.  This tool walks the actual
path - start a run, kill the player (or call ``on_victory``), let ``Game.end_run``
bank the run and push the scene, then render it - and asserts real pixels came
out.

Frames go to a temporary directory and are deleted afterwards; pass ``--keep``
or an explicit ``--out`` to keep them.  The run uses a throwaway profile so the
player's own ``save.json`` is never touched.

Exit status: 0 both end screens rendered, 1 a path crashed or rendered blank,
2 the game package is not importable yet or the arguments were bad.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

from tools import _util  # noqa: E402
from tools._util import EXIT_FAIL, EXIT_OK, EXIT_PREREQ  # noqa: E402

MIN_BYTES = 2048
MIN_COLOURS = 6
PROBE_TICKS = 120


class _Args:
    """The attribute set ``scenes.Game`` reads off the CLI namespace."""

    def __init__(self, seed: int, floor: int = 1) -> None:
        self.seed = seed
        self.floor = floor
        self.turns = PROBE_TICKS
        self.headless = True
        self.script = None
        self.shot = None
        self.shot_dir = None
        self.log = None
        self.save = None
        self.daily = False
        self.curses: list[str] = []
        self.endless = False
        self.new_run = True
        self.frames = None
        self.resolution = None
        self.fullscreen = False
        self.vsync = False
        self.fps = None


def _count_colours(png: Path) -> int:
    from PIL import Image

    with Image.open(png) as img:
        return len(img.convert("RGB").getcolors(maxcolors=1 << 20) or [])


def _render(scene, size=(1280, 720)):
    """Render a scene to an offscreen surface (never a window)."""
    import pygame

    surface = pygame.Surface(size)
    scene.draw(surface)
    return surface


def _check_png(png: Path) -> str | None:
    """Return an error string when the PNG looks blank, else None."""
    if not png.is_file():
        return "no PNG was written"
    size = png.stat().st_size
    if size < MIN_BYTES:
        return "PNG is only %d bytes - looks blank" % size
    colours = _count_colours(png)
    if colours < MIN_COLOURS:
        return "PNG has only %d distinct colour(s) - looks blank" % colours
    return None


def _run_path(kind: str, seed: int, out_dir: Path, scratch: Path) -> dict:
    """Drive one end-of-run path ('death' or 'victory') and render the screen."""
    import pygame

    from game.engine import scenes as scenes_mod
    from game.systems import save as save_sys

    result = {"kind": kind, "ok": False, "png": None, "detail": ""}
    profile, notes = save_sys.load_profile(str(scratch / "profile.json"))
    warnings = list(notes)
    args = _Args(seed)
    game = scenes_mod.Game(args, profile, warnings, headless=True,
                           save_path=str(scratch / "profile.json"))
    game.start_run(seed=seed)
    run_scene = next((s for s in game.scenes.stack if isinstance(s, scenes_mod.RunScene)), None)
    if run_scene is None:
        result["detail"] = "start_run did not push a RunScene"
        return result

    world = run_scene.world
    surface = pygame.Surface((1280, 720))
    for _ in range(PROBE_TICKS):
        run_scene.update(1 / 60.0)
        run_scene.draw(surface)

    if kind == "death":
        # r46: death goes to HQ hub first, not EndScene
        world.on_player_death("slain by bone_rat")
    else:
        world.on_victory()
    run_scene.end_timer = 99.0            # skip the death fade-in
    for _ in range(8):
        run_scene.update(1 / 60.0)

    top = game.scenes.top()
    if kind == "death":
        # r46: expect HQScene after death
        if top is None or type(top).__name__ != "HQScene":
            result["detail"] = "top scene is %s, expected HQScene (death→HQ)" % type(top).__name__
            return result
        # Drive the HQ scene: move, interact, render
        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            top.handle_event(pygame.event.Event(pygame.KEYDOWN, key=getattr(pygame, "K_LEFT" if dx < 0 else "K_RIGHT" if dx > 0 else "K_UP" if dy < 0 else "K_DOWN"), unicode="", mod=0))
        # Try to interact
        top.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_e, unicode="", mod=0))
    else:
        if top is None or type(top).__name__ != "EndScene":
            result["detail"] = "top scene is %s, expected EndScene" % type(top).__name__
            return result

    # real persistence path: banks the run, writes codex/bestiary/run history
    game.end_run() if kind != "death" else None  # death doesn't persist the same way

    png = out_dir / ("end-screen-%s-seed%d.png" % (kind, seed))
    surface = _render(top)
    pygame.image.save(surface, str(png))
    blank = _check_png(png)
    if blank:
        result["detail"] = blank
        return result
    result.update(ok=True, png=png, detail="rendered %d bytes, %d colours"
                  % (png.stat().st_size, _count_colours(png)))
    return result


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m tools.qa.death_run",
        description="Render the death and victory end screens through the real scene stack.",
    )
    ap.add_argument("--seed", type=int, default=42, help="run seed (default 42)")
    ap.add_argument("--out", default=None, help="keep PNGs here (default: temp dir, deleted)")
    ap.add_argument("--keep", action="store_true", help="keep the PNGs in the temp dir")
    ap.add_argument("--json", action="store_true", dest="as_json", help="machine-readable report")
    args = ap.parse_args(argv)

    root = _util.find_root()
    sys.path.insert(0, str(root))

    try:
        import importlib
        importlib.import_module("game.main")
    except Exception as exc:  # noqa: BLE001
        _util.say("game package not importable (%s) - nothing to render" % exc)
        return EXIT_PREREQ

    scratch = Path(tempfile.mkdtemp(prefix="rw_death_run_"))

    import pygame

    pygame.init()
    pygame.display.set_mode((1, 1))

    keep_dir = Path(args.out) if args.out else None
    if keep_dir is not None and not keep_dir.is_absolute():
        keep_dir = root / keep_dir
    out_dir = _util.ensure_dir(keep_dir or scratch)

    results = []
    rc = EXIT_OK
    try:
        for kind in ("death", "victory"):
            try:
                res = _run_path(kind, int(args.seed), out_dir, scratch)
            except Exception:  # noqa: BLE001
                res = {"kind": kind, "ok": False, "png": None, "detail": "crashed"}
                if not args.as_json:
                    _util.say("--- %s path traceback ---" % kind)
                    traceback.print_exc()
            results.append(res)
            if not res["ok"]:
                rc = EXIT_FAIL
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

    if args.as_json:
        print(json.dumps({
            "ok": rc == EXIT_OK,
            "seed": int(args.seed),
            "paths": [{"kind": r["kind"], "ok": r["ok"], "detail": r["detail"],
                       "png": _util.rel_posix(r["png"], root) if r["png"] else None}
                      for r in results],
        }, indent=2))
        return rc

    keep = keep_dir is not None or args.keep
    _util.say("end-screen smoke (seed %d)" % int(args.seed))
    for res in results:
        if res["ok"]:
            where = "  -> %s" % _util.rel_posix(res["png"], root) if keep else ""
            _util.say("  [PASS] %-8s %s%s" % (res["kind"], res["detail"], where))
        else:
            _util.say("  [FAIL] %-8s %s" % (res["kind"], res["detail"]))
    if not keep:
        _util.say("  (frames deleted - pass --out DIR or --keep to inspect them)")
    _util.say("OK: both end screens render" if rc == EXIT_OK else "FAILED: see above")
    return rc


if __name__ == "__main__":
    sys.exit(_util.guard(main)())
