"""Do the deep floors actually run? No gate ever checked.

`tools.studio.verify_gate` plays `game.main --headless --turns 300` - 300 ticks at 60 Hz is
five seconds of gameplay, and a run never leaves the first floor. So every biome past the
first, and every room template the content round generates for them, was **unreachable by
any gate**: a crash on floor 16 would ship, be announced as "gates green", and only the
owner would ever see it.

This walks one floor per biome entry and asserts each one generates, populates, steps and
satisfies the world's own invariants:

    python -m tools.qa.deep_floors                       # seeds 0-1, one floor per biome
    python -m tools.qa.deep_floors --seeds 0 --ticks 300
    python -m tools.qa.deep_floors --json

Exit 0 = every biome generated, stepped and held its invariants.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def _build(seed: int, floor: int, ticks: int):
    """Build a world at `floor`, step it, and return (summary, biome, extra)."""
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    import pygame
    from game.engine import scenes as scenes_mod
    from game.systems import save as save_sys
    from game.systems.biome_mods import water_tiles as bm_water_tiles

    class _Args:
        def __init__(self):
            self.seed = seed
            self.turns = ticks
            self.floor = floor          # scenes.start_run takes the floor before World()
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

    pygame.init()
    pygame.display.set_mode((1, 1))
    profile, notes = save_sys.load_profile(None)
    game = scenes_mod.Game(_Args(), profile, list(notes), headless=True, save_path=None)
    scene = game.start_run(seed=seed)
    world = scene.world
    if world.floor != floor:
        world.new_floor(floor)
    for _ in range(ticks):
        world.step(1 / 60.0)
    # Draw too. Stepping alone missed a NameError in the HUD's secret-count indicator:
    # the draw path is where the HUD and renderer run, so a floor that crashed only when
    # rendered looked perfectly healthy to a step-only gate.
    import pygame as _pg
    surface = _pg.Surface((1280, 720))
    scene.draw(surface)
    extra = {
        "rooms": len(getattr(world.level, "rooms", []) or []),
        "monsters": len(getattr(world, "monsters", []) or []),
        "pools": len(bm_water_tiles(world.level)),
    }
    return world.summary(), world.biome_id, extra


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m tools.qa.deep_floors")
    ap.add_argument("--seeds", nargs="*", type=int, default=[0, 1])
    ap.add_argument("--ticks", type=int, default=180)
    ap.add_argument("--json", action="store_true", dest="as_json")
    args = ap.parse_args(argv)

    # one floor per biome entry, derived from the content's own ordering
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from game.systems.data import Content
    order = Content().biome_order() or ["catacombs"]
    floors = [1 + i * 5 for i in range(len(order))]

    rows, problems = [], []
    for seed in args.seeds:
        for floor in floors:
            try:
                summary, biome, extra = _build(seed, floor, args.ticks)
                violations = summary["invariants"]["violations"]
                errors = summary["errors"]
                rows.append({"seed": seed, "floor": floor, "biome": biome,
                             "violations": violations, "errors": errors, **extra})
                if violations or errors:
                    problems.append("seed %d floor %d (%s): %d violation(s), %d error(s) - %s"
                                    % (seed, floor, biome, len(violations), len(errors),
                                       (violations + errors)[:2]))
            except Exception as exc:                                   # noqa: BLE001
                rows.append({"seed": seed, "floor": floor, "biome": "?",
                             "crashed": "%s: %s" % (type(exc).__name__, exc)})
                problems.append("seed %d floor %d CRASHED: %s: %s"
                                % (seed, floor, type(exc).__name__, exc))

    if args.as_json:
        print(json.dumps({"rows": rows, "problems": problems}, indent=2))
        return 1 if problems else 0

    print("deep floors — every biome must generate, populate, step and hold its invariants")
    print("  biome order: %s" % ", ".join(order))
    for r in rows:
        if r.get("crashed"):
            print("  seed %-2d floor %-3d %-16s CRASHED: %s"
                  % (r["seed"], r["floor"], "?", r["crashed"][:70]))
        else:
            print("  seed %-2d floor %-3d %-16s rooms %-4d monsters %-3d pools %-3d "
                  "violations %-2d errors %-2d"
                  % (r["seed"], r["floor"], r["biome"], r["rooms"], r["monsters"],
                     r["pools"], len(r["violations"]), len(r["errors"])))
    if problems:
        print("FAILED (%d):" % len(problems))
        for p in problems:
            print("  - %s" % p)
        return 1
    print("OK: %d floor(s) across %d biome(s) generated, stepped and held invariants"
          % (len(rows), len(order)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
