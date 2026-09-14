"""QA autopilot: proves floors generate, connect and are completable.

Drives a headless world with the AutoPilotInput source (BFS path to the floor
objective + automatic combat) until the run ends or a tick budget is spent, and
prints a per-floor report.  This is a QA tool: it does not touch game logic.

    .venv/Scripts/python.exe tools/qa/autopilot.py --seed 0 --turns 60000
"""

import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402

from game.engine.input import AutoPilotInput  # noqa: E402
from game.systems.world import TICK, World  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(prog="tools.qa.autopilot")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--turns", type=int, default=60000)
    parser.add_argument("--floor", type=int, default=1)
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--max-floor-seconds", type=float, default=180.0,
                        help="give up on a floor after this many simulated seconds")
    args = parser.parse_args(argv)

    pygame.init()
    try:
        pygame.display.set_mode((1, 1))
    except pygame.error:
        pass

    warnings = []
    world = World(seed=args.seed, profile=None, headless=True, start_floor=args.floor,
                  warnings=warnings)
    world.input_source = AutoPilotInput(world)

    floors = []
    current = {"floor": world.floor, "ticks": 0,
               "level": (world.level.w, world.level.h)}
    floors.append(current)
    steps = 0
    while steps < args.turns and world.run_state == "running":
        world.step(TICK)
        steps += 1
        current["ticks"] += 1
        if current["ticks"] > args.max_floor_seconds * 60:
            current["stuck"] = True
            break
        if world.floor != current["floor"]:
            current = {"floor": world.floor, "ticks": 0,
                       "entered_tick": world.tick, "level": (world.level.w, world.level.h),
                       "hp": int(world.player.hp)}
            floors.append(current)

    previous = None
    print("autopilot seed=%d steps=%d state=%s floor=%d biome=%s"
          % (args.seed, steps, world.run_state, world.floor, world.biome_id))
    for i, entry in enumerate(floors):
        dims = entry.get("level") or (world.level.w, world.level.h)
        print("  floor %-2d ticks=%-6d level=%dx%d%s"
              % (entry["floor"], entry["ticks"], dims[0], dims[1],
                 "  STUCK" if entry.get("stuck") else ""))
    violations = world.check_invariants()
    print("  kills=%d essence=%d level=%d items=%d"
          % (world.player.kills, world.essence_run, world.player.level,
             len(world.player.owned_item_ids())))
    print("  violations=%s" % violations)
    print("  warnings=%d" % len(warnings))
    pygame.quit()
    return 0 if not violations else 1


if __name__ == "__main__":
    sys.exit(main())
