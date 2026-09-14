"""balance: the economy and difficulty numbers the game is tuned on.

    python -m tools.qa.balance                          # defaults: seeds 0-3, corrected RNG
    python -m tools.qa.balance --seeds 0 1 2 --turns 60000
    python -m tools.qa.balance --rng buggy              # the historical broken generator
    python -m tools.qa.balance --json

Ticket G-01 asks for TTK, death rate per floor and essence economy with before/after numbers.
"Before" is not a guess here: the shipped RNG collapsed to an 8-value cycle (see RNG-01), so every
loot roll, spawn and level-up was near-deterministic. `--rng buggy` reinstalls that exact
historical `_next()` at runtime, so the same seeds can be measured both ways and the difference is
the RNG fix's actual effect on balance rather than an assumption about it.

Drives the same headless world + AutoPilotInput that tools.qa.autopilot uses, so the numbers come
from real play, not from a model of play.

Exit: 0 measured, 1 the game raised / violated invariants, 2 the game package is unavailable.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

from tools import _util  # noqa: E402
from tools._util import EXIT_FAIL, EXIT_OK, EXIT_PREREQ  # noqa: E402

DEFAULT_SEEDS = [0, 1, 2, 3]
DEFAULT_TURNS = 40000
MAX_FLOOR_TICKS = 180 * 60          # give up on a floor after 180 simulated seconds


def install_buggy_rng() -> None:
    """Reinstall the pre-fix `_next()` so the same seeds can be measured as they were."""
    from game.systems.rng import RNG  # noqa: PLC0415
    from tools.qa.rng_quality import buggy_next  # noqa: PLC0415
    RNG._next = buggy_next


def play_one_seed(seed: int, turns: int) -> dict:
    """Run one autopilot seed; return per-floor and run-level metrics."""
    import pygame  # noqa: PLC0415
    from game.engine.input import AutoPilotInput  # noqa: PLC0415
    from game.systems.world import TICK, World  # noqa: PLC0415

    warnings: list = []
    world = World(seed=seed, profile=None, headless=True, start_floor=1, warnings=warnings)
    world.input_source = AutoPilotInput(world)

    floors: list[dict] = []
    cur = {"floor": world.floor, "ticks": 0, "kills0": world.player.kills,
           "ess0": world.essence_run, "hp0": int(world.player.hp)}
    steps = 0
    while steps < turns and world.run_state == "running":
        world.step(TICK)
        steps += 1
        cur["ticks"] += 1
        if cur["ticks"] > MAX_FLOOR_TICKS:
            cur["stuck"] = True
            break
        if world.floor != cur["floor"]:
            floors.append(_close_floor(world, cur))
            cur = {"floor": world.floor, "ticks": 0, "kills0": world.player.kills,
                   "ess0": world.essence_run, "hp0": int(world.player.hp)}
    floors.append(_close_floor(world, cur))

    return {
        "seed": seed,
        "state": world.run_state,
        "final_floor": world.floor,
        "steps": steps,
        "kills": world.player.kills,
        "essence": world.essence_run,
        "player_level": world.player.level,
        "items": len(world.player.owned_item_ids()),
        "violations": world.check_invariants(),
        "warnings": len(warnings),
        "floors": floors,
    }


def _close_floor(world, cur: dict) -> dict:
    kills = world.player.kills - cur["kills0"]
    essence = world.essence_run - cur["ess0"]
    ticks = max(1, cur["ticks"])
    return {
        "floor": cur["floor"],
        "ticks": cur["ticks"],
        "kills": kills,
        "essence": essence,
        "hp0": cur["hp0"],
        "stuck": bool(cur.get("stuck")),
        # TTK proxy: ticks of play per kill on this floor (lower = faster killing).
        "ticks_per_kill": round(ticks / kills, 1) if kills else None,
        "essence_per_kill": round(essence / kills, 2) if kills else None,
    }


def summarise(runs: list[dict]) -> dict:
    def avg(xs):
        xs = [x for x in xs if x is not None]
        return round(statistics.fmean(xs), 1) if xs else None

    by_floor: dict[int, list[dict]] = {}
    for r in runs:
        for f in r["floors"]:
            by_floor.setdefault(f["floor"], []).append(f)

    floors = []
    for fl in sorted(by_floor):
        rows = by_floor[fl]
        floors.append({
            "floor": fl,
            "reached": len(rows),
            "avg_ticks": avg([r["ticks"] for r in rows]),
            "avg_kills": avg([r["kills"] for r in rows]),
            "avg_essence": avg([r["essence"] for r in rows]),
            "avg_ticks_per_kill": avg([r["ticks_per_kill"] for r in rows]),
            "stuck": sum(1 for r in rows if r["stuck"]),
        })

    finished = [r for r in runs if r["state"] != "running"]
    return {
        "runs": len(runs),
        "deaths": sum(1 for r in runs if r["state"] == "dead"),
        "victories": sum(1 for r in runs if r["state"] == "victory"),
        "unfinished": sum(1 for r in runs if r["state"] == "running"),
        "death_rate": round(sum(1 for r in runs if r["state"] == "dead") / len(runs), 3)
        if runs else None,
        "avg_final_floor": avg([r["final_floor"] for r in runs]),
        "avg_kills": avg([r["kills"] for r in runs]),
        "avg_essence": avg([r["essence"] for r in runs]),
        "avg_essence_per_kill": avg([
            (r["essence"] / r["kills"]) if r["kills"] else None for r in runs]),
        "avg_ticks_per_kill": avg([
            (r["steps"] / r["kills"]) if r["kills"] else None for r in runs]),
        "total_violations": sum(len(r["violations"]) for r in runs),
        "finished_runs": len(finished),
        "floors": floors,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m tools.qa.balance",
                                 description="Measure difficulty and economy from real play.")
    ap.add_argument("--seeds", type=int, nargs="*", default=DEFAULT_SEEDS)
    ap.add_argument("--turns", type=int, default=DEFAULT_TURNS)
    ap.add_argument("--rng", choices=["fixed", "buggy"], default="fixed",
                    help="'buggy' reinstalls the historical 8-value-cycle generator")
    ap.add_argument("--json", action="store_true", dest="as_json")
    args = ap.parse_args(argv)

    try:
        import game.main  # noqa: F401,PLC0415
    except Exception as exc:  # noqa: BLE001
        _util.say("SKIP: game package not importable (%s)" % exc)
        return EXIT_PREREQ

    import pygame  # noqa: PLC0415
    pygame.init()
    try:
        pygame.display.set_mode((1, 1))
    except pygame.error:
        pass

    if args.rng == "buggy":
        install_buggy_rng()
        if not args.as_json:
            _util.say("RNG: HISTORICAL BUGGY GENERATOR reinstalled (8-value cycle)")

    runs = []
    for seed in args.seeds:
        try:
            runs.append(play_one_seed(seed, args.turns))
        except Exception as exc:  # noqa: BLE001
            _util.say("seed %d RAISED: %s: %s" % (seed, type(exc).__name__, exc))
            pygame.quit()
            return EXIT_FAIL
    pygame.quit()

    report = {"rng": args.rng, "turns": args.turns, "seeds": args.seeds,
              "summary": summarise(runs), "per_seed": [
                  {k: v for k, v in r.items() if k != "floors"} for r in runs]}
    rc = EXIT_FAIL if report["summary"]["total_violations"] else EXIT_OK

    if args.as_json:
        print(json.dumps({"ok": rc == EXIT_OK, **report}, indent=2))
        return rc

    s = report["summary"]
    _util.say("balance: %s RNG, %d seed(s), %d-turn budget" % (args.rng, len(runs), args.turns))
    _util.say("  deaths %d/%d (rate %s) | victories %d | unfinished %d | avg final floor %s"
              % (s["deaths"], s["runs"], s["death_rate"], s["victories"], s["unfinished"],
                 s["avg_final_floor"]))
    _util.say("  avg kills %s | avg essence %s | essence/kill %s | ticks/kill %s"
              % (s["avg_kills"], s["avg_essence"], s["avg_essence_per_kill"],
                 s["avg_ticks_per_kill"]))
    _util.say("  floor  reached  avg_ticks  avg_kills  avg_essence  ticks/kill  stuck")
    for f in s["floors"]:
        _util.say("  %-6d %-8d %-10s %-10s %-12s %-11s %d"
                  % (f["floor"], f["reached"], f["avg_ticks"], f["avg_kills"],
                     f["avg_essence"], f["avg_ticks_per_kill"], f["stuck"]))
    _util.say("OK: measured, 0 invariant violations" if rc == EXIT_OK
              else "FAILED: %d invariant violation(s)" % s["total_violations"])
    return rc


if __name__ == "__main__":
    sys.exit(_util.guard(main)())
