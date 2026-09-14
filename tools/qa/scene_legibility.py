"""scene-legibility: a rendered floor must be readable, not just non-blank.

    python -m tools.qa.scene_legibility
    python -m tools.qa.scene_legibility --json

Why this exists: P4.1's lighting shipped with an acceptance metric of
"centre/brightness ratio > 4.0". That is a *contrast* measurement, and it passed
happily while the dungeon was unplayable — the frame was 74% near-black, the
map was invisible, and the light was drawn as solid 64 px discs stamped per tile
("large pixelated circles"). Contrast was excellent. Nobody could see anything.

Blank-frame checks cannot catch that either: `> 2 KB and > 8 colours` passes on a
frame that is 25% pure black with giant orange blobs on it.

So this gate measures **legibility** on a real frame from the real render path:

* visible-tile coverage - 32 px cells whose mean luminance is above black
  (a dungeon that is invisible fails here),
* the share of pixels in a readable mid-tone band (dark art or blown-out white
  both fail),
* overall mean luminance inside a sane band,
* colour variety, so a flat single-tone frame fails.

Exit status: 0 the frame is legible, 1 it is not, 2 the game package is missing.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

from tools import _util  # noqa: E402
from tools._util import EXIT_FAIL, EXIT_OK, EXIT_PREREQ  # noqa: E402

TILE = 32
SIZE = (1280, 720)

#: Thresholds. Each one was set from a measurement of a frame that was actually
#: broken, so a regression to that state fails the gate.
MIN_VISIBLE_TILE_COVERAGE = 0.85   # broken frame measured 0.33
MIN_MIDTONE_SHARE = 0.25           # broken frame measured 0.045
MAX_DARK_SHARE = 0.45              # broken frame measured 0.74
MEAN_LUMINANCE_BAND = (30.0, 170.0)
MIN_DISTINCT_COLOURS = 500         # broken frame: 806, but a flat fill would be <50


def measure(surface) -> dict:
    import numpy as np
    import pygame

    frame = pygame.surfarray.array3d(surface).astype(int)     # [x][y][rgb]
    lum = frame.sum(2) / 3.0
    h, w = lum.shape
    cells = lum[: h // TILE * TILE, : w // TILE * TILE].reshape(h // TILE, TILE,
                                                                 w // TILE, TILE)
    cell_mean = cells.mean(axis=(1, 3))
    return {
        "mean_luminance": round(float(lum.mean()), 2),
        "visible_tile_coverage": round(float((cell_mean > 16).mean()), 4),
        "mid_tone_share": round(float(((lum >= 16) & (lum < 80)).mean()), 4),
        "dark_share": round(float((lum < 16).mean()), 4),
        "bright_share": round(float((lum > 80).mean()), 4),
        "distinct_colours": len({tuple(c) for c in frame.reshape(-1, 3)}),
    }


def render_frame(seed: int, ticks: int):
    """Render one real gameplay frame through the game's own scene stack."""
    import pygame

    from game.engine import scenes as scenes_mod
    from game.systems import save as save_sys

    class _Args:
        def __init__(self):
            self.seed = seed
            self.turns = ticks
            self.floor = 1
            self.headless = True
            self.script = None
            self.shot = None
            self.shot_dir = None
            self.log = None
            self.save = None
            self.daily = False
            self.curses: list = []
            self.endless = False
            self.new_run = True
            self.frames = None
            self.resolution = None
            self.fullscreen = False
            self.vsync = False
            self.fps = None

    import tempfile
    scratch = Path(tempfile.mkdtemp(prefix="rw_legibility_"))
    try:
        profile, notes = save_sys.load_profile(str(scratch / "profile.json"))
        game = scenes_mod.Game(_Args(), profile, list(notes), headless=True,
                               save_path=str(scratch / "profile.json"))
        scene = game.start_run(seed=seed)
        for _ in range(ticks):
            scene.update(1 / 60.0)
        surface = pygame.Surface(SIZE)
        scene.draw(surface)
        return surface
    finally:
        import shutil
        shutil.rmtree(scratch, ignore_errors=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m tools.qa.scene_legibility",
        description="Assert a rendered floor is legible, not merely non-blank.",
    )
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--ticks", type=int, default=120)
    ap.add_argument("--frame", default=None,
                    help="measure a saved PNG instead of rendering (audit any frame)")
    ap.add_argument("--json", action="store_true", dest="as_json")
    args = ap.parse_args(argv)

    root = _util.find_root()
    sys.path.insert(0, str(root))

    import pygame

    pygame.init()
    pygame.display.set_mode((1, 1))

    if args.frame:
        path = Path(args.frame)
        if not path.is_absolute():
            path = root / path
        if not path.is_file():
            _util.say("no such frame: %s" % path)
            return EXIT_PREREQ
        m = measure(pygame.image.load(str(path)))
        label = "frame %s" % path.name
    else:
        if not (root / "game" / "main.py").is_file():
            _util.say("game package not built yet - nothing to measure")
            return EXIT_PREREQ
        m = measure(render_frame(int(args.seed), int(args.ticks)))
        label = "scene legibility (seed %d, %d ticks)" % (args.seed, args.ticks)

    problems = []
    if m["visible_tile_coverage"] < MIN_VISIBLE_TILE_COVERAGE:
        problems.append("only %.0f%% of tiles are visible (need >= %.0f%%) - the map is dark"
                        % (100 * m["visible_tile_coverage"], 100 * MIN_VISIBLE_TILE_COVERAGE))
    if m["mid_tone_share"] < MIN_MIDTONE_SHARE:
        problems.append("only %.1f%% of pixels are mid-tone (need >= %.0f%%) - no readable detail"
                        % (100 * m["mid_tone_share"], 100 * MIN_MIDTONE_SHARE))
    if m["dark_share"] > MAX_DARK_SHARE:
        problems.append("%.1f%% of pixels are near-black (limit %.0f%%)"
                        % (100 * m["dark_share"], 100 * MAX_DARK_SHARE))
    lo, hi = MEAN_LUMINANCE_BAND
    if not (lo <= m["mean_luminance"] <= hi):
        problems.append("mean luminance %.1f outside %.0f-%.0f" % (m["mean_luminance"], lo, hi))
    if m["distinct_colours"] < MIN_DISTINCT_COLOURS:
        problems.append("only %d distinct colours (need >= %d)"
                        % (m["distinct_colours"], MIN_DISTINCT_COLOURS))

    rc = EXIT_FAIL if problems else EXIT_OK
    if args.as_json:
        print(json.dumps({"ok": rc == EXIT_OK, "seed": args.seed, **m,
                          "problems": problems}, indent=2))
        return rc

    _util.say("scene legibility  %s" % label)
    _util.say("  mean luminance       %6.1f   (want %.0f-%.0f)" % (m["mean_luminance"], lo, hi))
    _util.say("  visible tiles        %6.1f%%  (want >= %.0f%%)"
              % (100 * m["visible_tile_coverage"], 100 * MIN_VISIBLE_TILE_COVERAGE))
    _util.say("  mid-tone share       %6.1f%%  (want >= %.0f%%)"
              % (100 * m["mid_tone_share"], 100 * MIN_MIDTONE_SHARE))
    _util.say("  near-black share     %6.1f%%  (want <= %.0f%%)"
              % (100 * m["dark_share"], 100 * MAX_DARK_SHARE))
    _util.say("  distinct colours     %6d   (want >= %d)"
              % (m["distinct_colours"], MIN_DISTINCT_COLOURS))
    for p in problems:
        _util.say("  [FAIL] %s" % p)
    _util.say("OK: the floor is legible" if rc == EXIT_OK
              else "FAILED: the floor is not readable")
    return rc


if __name__ == "__main__":
    sys.exit(_util.guard(main)())
