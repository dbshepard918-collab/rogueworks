"""progression: does investing in the meta tree actually take you deeper?

    python -m tools.qa.progression
    python -m tools.qa.progression --seeds 0 1 2 --turns 12000 --json

The roguelite design is deliberate: dying on floor 3-4 with a FRESH save is intended, and the
meta-progression tree is what is supposed to carry you deeper on repeat runs ("choose your
destiny"). That design makes a falsifiable prediction:

    a run with more meta upgrades spent should reach a measurably deeper floor than a fresh run.

This tool tests that prediction. It builds profiles at increasing investment levels, runs the same
autopilot seeds at each level, and reports depth versus investment. If depth does not rise with
investment, the loop is broken - the player is choosing a destiny that does not exist.

Guard against a vacuous result: before running, each level's profile is asserted to actually carry
larger stat totals than a fresh one. If the harness failed to apply the upgrades, this tool says so
instead of reporting "meta does not help".

Exit: 0 measured, 1 the game raised / the guard tripped, 2 the game package is unavailable.
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

DEFAULT_SEEDS = [0, 1, 2]
DEFAULT_TURNS = 12000
#: investment levels = number of tree tiers purchased. 5 branches x 4 tiers = 20 is a full tree.
LEVELS = [0, 2, 5, 10, 15, 20]


def fresh_profile():
    from game.systems import save  # noqa: PLC0415
    scratch = str(Path(os.environ.get("TEMP", ".")) / "__no_such_save__.json")
    prof, _notes = save.load_profile(path=scratch)
    return prof


def tier_order():
    """Every (branch, tier) id in purchase order (tier 1..N within each branch)."""
    root = Path(__file__).resolve().parents[2]
    doc = json.loads((root / "game/data/meta_tree.json").read_text(encoding="utf-8"))
    order = []
    branches = doc.get("branches") or {}
    items = branches.items() if isinstance(branches, dict) else [(b.get("id"), b) for b in branches]
    for bid, b in items:
        tiers = (b or {}).get("tiers") or []
        for i in range(len(tiers)):
            order.append("%s:%d" % (bid, i + 1))
    return order


def build_profile(n_tiers: int):
    """A profile with the first *n_tiers* tree tiers purchased (essence is not the constraint here)."""
    from game.systems import save  # noqa: PLC0415
    prof = fresh_profile()
    prof["essence"] = 10 ** 7          # the question is the EFFECT of upgrades, not their price
    prof.setdefault("levels", {})
    bought = []
    for uid in tier_order():
        if len(bought) >= n_tiers:
            break
        if save.purchase(prof, uid):
            bought.append(uid)
    return prof, bought


def play(seed: int, profile, turns: int) -> dict:
    import pygame  # noqa: PLC0415,F401
    from game.engine.input import AutoPilotInput  # noqa: PLC0415
    from game.systems.world import TICK, World  # noqa: PLC0415

    warnings: list = []
    world = World(seed=seed, profile=profile, headless=True, start_floor=1, warnings=warnings)
    world.input_source = AutoPilotInput(world)
    steps = 0
    while steps < turns and world.run_state == "running":
        world.step(TICK)
        steps += 1
    return {"seed": seed, "state": world.run_state, "floor": world.floor, "steps": steps,
            "kills": world.player.kills, "essence": world.essence_run,
            "level": world.player.level, "hp": int(world.player.hp),
            "max_hp": int(world.player.stats.max_hp()),
            "violations": world.check_invariants()}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m tools.qa.progression",
                                 description="Does meta investment take you deeper?")
    ap.add_argument("--seeds", type=int, nargs="*", default=DEFAULT_SEEDS)
    ap.add_argument("--turns", type=int, default=DEFAULT_TURNS)
    ap.add_argument("--json", action="store_true", dest="as_json")
    args = ap.parse_args(argv)

    try:
        import game.main  # noqa: F401,PLC0415
        from game.systems import save  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        _util.say("SKIP: game package not importable (%s)" % exc)
        return EXIT_PREREQ

    import pygame  # noqa: PLC0415
    pygame.init()
    try:
        pygame.display.set_mode((1, 1))
    except pygame.error:
        pass

    fresh, _ = build_profile(0)
    base_stats = save.meta_stat_totals(fresh)

    rows = []
    for n in LEVELS:
        prof, bought = build_profile(n)
        stats = save.meta_stat_totals(prof)
        effects = save.meta_special_effects(prof)
        # GUARD: the powered profile must actually differ from a fresh one, or the test is vacuous.
        gained = sum(stats.values())
        if n > 0 and gained <= 0:
            _util.say("REFUSING: %d tier(s) purchased but meta_stat_totals is still zero - the "
                      "harness is not applying upgrades, so any result would be meaningless" % n)
            pygame.quit()
            return EXIT_FAIL
        runs = []
        for seed in args.seeds:
            try:
                runs.append(play(seed, prof, args.turns))
            except Exception as exc:  # noqa: BLE001
                _util.say("level %d seed %d RAISED: %s: %s" % (n, seed, type(exc).__name__, exc))
                pygame.quit()
                return EXIT_FAIL
        floors = [r["floor"] for r in runs]
        rows.append({
            "tiers": n,
            "bought": bought,
            "stat_bonus_total": round(gained, 2),
            "heal_on_floor_pct": effects.get("heal_on_floor_pct"),
            "essence_drop_mult": effects.get("essence_drop_mult"),
            "avg_floor": round(statistics.fmean(floors), 2) if floors else None,
            "best_floor": max(floors) if floors else None,
            "avg_kills": round(statistics.fmean([r["kills"] for r in runs]), 1),
            "avg_max_hp": round(statistics.fmean([r["max_hp"] for r in runs]), 1),
            "deaths": sum(1 for r in runs if r["state"] == "dead"),
            "runs": len(runs),
        })
    pygame.quit()

    base = rows[0]["avg_floor"]
    top = rows[-1]["avg_floor"]
    verdict = ("meta investment moves depth (%.2f -> %.2f floors)" % (base, top)
               if top is not None and base is not None and top > base
               else "meta investment does NOT increase depth - the progression loop is broken")
    report = {"seeds": args.seeds, "turns": args.turns, "levels": rows,
              "base_stats": base_stats, "verdict": verdict}

    if args.as_json:
        print(json.dumps({"ok": True, **report}, indent=2))
        return EXIT_OK

    _util.say("progression: %d seed(s) x %d ticks per investment level"
              % (len(args.seeds), args.turns))
    _util.say("  tiers  stat_bonus  avg_floor  best  avg_kills  avg_max_hp  deaths")
    for r in rows:
        _util.say("  %-6d %-11s %-10s %-5s %-10s %-11s %d/%d"
                  % (r["tiers"], r["stat_bonus_total"], r["avg_floor"], r["best_floor"],
                     r["avg_kills"], r["avg_max_hp"], r["deaths"], r["runs"]))
    _util.say("")
    _util.say("VERDICT: %s" % verdict)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(_util.guard(main)())
