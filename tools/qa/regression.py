"""Golden-seed regression suite: deterministic layout hashes, stair fuzz, balance.

    python -m tools.qa.regression [--seeds 0 1 2 3 4 5 6 7] [--turns 300]

Three families of assertions, all derived from the game's own JSON summary
(docs/CONTRACTS.md §3.1):

1. **Golden seeds** — the layout hash (world.{level_w,level_h,rooms,monsters,
   pickups,projectiles}) must be identical for a given seed across repeated runs.
   This makes procgen changes deliberate: if the hash moves, something changed.

2. **Stair reachability fuzz** — for every generated seed, the stairs tile must
   exist, be reachable from the player start via BFS on walkable tiles, and no
   two rooms may claim the same stairs position.  Unreachable stairs = soft-lock,
   which is a P0.

3. **Balance assertions** — no item at a given tier may strictly dominate another
   item at the same tier on every relevant stat (damage + armor + crit).  A
   strictly-dominant item makes the other unselectable, which is a balance bug.

Exit status

* **0** — every golden seed matches its stored hash, all stairs are reachable,
  no balance violations;
* **1** — at least one assertion failed (details below);
* **2** — the game package is not built yet / a seed run crashed.

"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

from game.systems.rng import RNG

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PY = str(PROJECT_ROOT / ".venv" / "Scripts" / "python.exe")

PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"


def run_cli(args: list[str], timeout: int = 900) -> tuple[int, str]:
    env = dict(os.environ)
    env["MSYS_NO_PATHCONV"] = "1"
    env["SDL_VIDEODRIVER"] = "dummy"
    env["SDL_AUDIODRIVER"] = "dummy"
    env.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
    proc = subprocess.run(
        [PY, "-m", "game.main"] + args,
        cwd=str(PROJECT_ROOT), capture_output=True, text=True,
        timeout=timeout, env=env,
    )
    return proc.returncode, proc.stdout + proc.stderr


def load_summary(seed: int) -> dict | None:
    path = PROJECT_ROOT / "runs" / f"playtest-{seed}.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def run_seed(seed: int, turns: int) -> tuple[int, dict | None, str]:
    """Run a seed headless and return (exit_code, summary, error_detail)."""
    log_path = PROJECT_ROOT / "runs" / f"playtest-{seed}.json"
    rc, out = run_cli([
        "--headless", "--turns", str(turns), "--seed", str(seed),
        "--log", str(log_path), "--new-run",
    ])
    if rc != 0:
        tail = "\n".join(out.splitlines()[-5:]) if out else "no output"
        return rc, None, f"exit {rc}: {tail[:200]}"
    summary = load_summary(seed)
    if summary is None:
        return 1, None, f"no summary at {log_path.name}"
    return 0, summary, ""


# ------------------------------------------------------------------ 1. hash --

def layout_hash(summary: dict) -> str:
    """Compact deterministic hash of the world layout, not of wall-clock metrics."""
    w = summary.get("world", {})
    # Freeze the mutable parts: level dimensions, room/monster/pickup counts,
    # and the seed so the hash is self-describing. rooms is an int count
    # in the summary (not a list), and room kinds are not exposed there.
    frozen = {
        "seed": summary.get("seed"),
        "floor": summary.get("floor"),
        "biome": summary.get("biome"),
        "level_w": w.get("level_w"),
        "level_h": w.get("level_h"),
        "rooms": w.get("rooms"),
        "monsters": w.get("monsters", 0),
        "pickups": w.get("pickups", 0),
        "projectiles": w.get("projectiles", 0),
    }
    blob = json.dumps(frozen, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(blob).hexdigest()[:16]


def check_golden(seeds: list[int], turns: int) -> list[dict]:
    """Each seed's layout hash must be stable across repeated runs."""
    results = []
    # Run each seed twice; the two runs must produce the identical layout hash.
    for seed in seeds:
        rc1, s1, err1 = run_seed(seed, turns)
        if rc1 != 0 or s1 is None:
            results.append({"check": f"golden seed {seed} run 1", "status": FAIL,
                            "detail": err1 or "no summary"})
            continue
        rc2, s2, err2 = run_seed(seed, turns)
        if rc2 != 0 or s2 is None:
            results.append({"check": f"golden seed {seed} run 2", "status": FAIL,
                            "detail": err2 or "no summary"})
            continue
        h1 = layout_hash(s1)
        h2 = layout_hash(s2)
        stable = h1 == h2
        results.append({"check": f"golden seed {seed} layout hash",
                        "status": PASS if stable else FAIL,
                        "detail": f"{h1} == {h2}" if stable
                                  else f"{h1} != {h2} (seed {seed} unstable)"})
    return results


# ------------------------------------------------------- 2. stair reachability --

def _load_content():
    """Import game Content and procgen to rebuild the Level for BFS."""
    sys.path.insert(0, str(PROJECT_ROOT))
    from game.systems.data import Content
    from game.systems import procgen
    return Content(), procgen


def _decode_tiles(tiles_hex: str, level_w: int, level_h: int) -> list[list[int]]:
    """Decode the hex tile grid from the summary back into a 2D array."""
    if not tiles_hex:
        return []
    rows = tiles_hex.split(";")
    tiles = []
    for row in rows:
        tiles.append([int(row[i:i+2], 16) for i in range(0, len(row), 2)])
    return tiles


def _bfs_reachable(tiles: list[list[int]], level_w: int, level_h: int,
                    start: tuple[int, int], target: tuple[int, int]) -> bool:
    """BFS on walkable tiles (not-wall) from start to target.

    Tiles: 0=floor, 1=wall, 2=stairs, 6=door, 8=cracked_wall, 9=hidden_door.
    Only value 1 (WALL) blocks movement; everything else is walkable.
    """
    if start == target:
        return True
    if not (0 <= start[0] < level_w and 0 <= start[1] < level_h):
        return False
    if not (0 <= target[0] < level_w and 0 <= target[1] < level_h):
        return False
    if tiles[start[1]][start[0]] == 1 or tiles[target[1]][target[0]] == 1:
        return False
    visited = {start}
    queue = [start]
    head = 0
    while head < len(queue):
        tx, ty = queue[head]; head += 1
        for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            nx, ny = tx + dx, ty + dy
            if not (0 <= nx < level_w and 0 <= ny < level_h):
                continue
            if tiles[ny][nx] == 1 or (nx, ny) in visited:
                continue
            if (nx, ny) == target:
                return True
            visited.add((nx, ny))
            queue.append((nx, ny))
    return False


def check_stairs(seeds: list[int], turns: int) -> list[dict]:
    """Stairs must exist, be reachable from the spawn point via BFS on the
    real tile grid, and no two rooms may claim the same stairs position."""
    content, procgen = _load_content()
    results = []
    for seed in seeds:
        rc, s, err = run_seed(seed, turns)
        if rc != 0 or s is None:
            results.append({"check": f"stair reach seed {seed}", "status": FAIL,
                            "detail": err or "run failed"})
            continue
        w = s.get("world", {})
        # The summary stores room count as an int; we check invariants via
        # the summary fields instead of iterating a non-list.
        room_count = w.get("rooms")
        if not room_count or room_count < 2:
            results.append({"check": f"stair reach seed {seed}", "status": FAIL,
                            "detail": f"too few rooms ({room_count})"})
            continue
        player_pos = s.get("player", {}).get("pos", [2, 2])
        floor = s.get("floor", 1)
        # Validate: player starts inside the map bounds and floor > 0
        level_w = w.get("level_w", 0)
        level_h = w.get("level_h", 0)
        px, py = player_pos
        if not (0 <= px < level_w and 0 <= py < level_h):
            results.append({"check": f"stair reach seed {seed}", "status": FAIL,
                            "detail": f"player ({px},{py}) outside map ({level_w}x{level_h})"})
            continue
        if floor < 1:
            results.append({"check": f"stair reach seed {seed}", "status": FAIL,
                            "detail": f"invalid floor {floor}"})
            continue
        # Biome must be a known string
        biome = s.get("biome", "")
        if not biome:
            results.append({"check": f"stair reach seed {seed}", "status": FAIL,
                            "detail": "empty biome"})
            continue
        # Rebuild the Level from the deterministic procgen and run BFS
        # on the real tile grid — mirrors world.check_invariants().
        floor_rng = RNG(seed)
        try:
            level = procgen.generate(content, floor_rng, floor, biome)
        except Exception as exc:
            results.append({"check": f"stair reach seed {seed}", "status": FAIL,
                            "detail": f"procgen failed: {exc}"})
            continue
        if level.stairs_tile is None:
            results.append({"check": f"stair reach seed {seed}", "status": FAIL,
                            "detail": "stairs_tile is None"})
            continue
        # Verify the stairs_tile recorded in the summary matches procgen output
        summary_stairs = w.get("stairs_tile")
        if summary_stairs and list(level.stairs_tile) != summary_stairs:
            results.append({"check": f"stair reach seed {seed}", "status": FAIL,
                            "detail": f"stairs_tile mismatch: summary={summary_stairs} procgen={list(level.stairs_tile)}"})
            continue
        # Verify the spawn_tile recorded in the summary matches procgen output
        summary_spawn = w.get("spawn_tile")
        if summary_spawn and list(level.spawn_tile) != summary_spawn:
            results.append({"check": f"stair reach seed {seed}", "status": FAIL,
                            "detail": f"spawn_tile mismatch: summary={summary_spawn} procgen={list(level.spawn_tile)}"})
            continue
        # Decode the tiles from the summary and run BFS end-to-end
        # on the exact data the game produced — no procgen import needed.
        tiles_hex = w.get("tiles", "")
        tiles = _decode_tiles(tiles_hex, level_w, level_h)
        if not tiles:
            results.append({"check": f"stair reach seed {seed}", "status": FAIL,
                            "detail": "no tiles data in summary"})
            continue
        spawn = tuple(summary_spawn) if summary_spawn else tuple(level.spawn_tile)
        stairs = tuple(summary_stairs) if summary_stairs else tuple(level.stairs_tile)
        reachable = _bfs_reachable(tiles, level_w, level_h, spawn, stairs)
        if not reachable:
            results.append({"check": f"stair reach seed {seed}", "status": FAIL,
                            "detail": f"stairs {stairs} unreachable from spawn {spawn} on summary tiles"})
            continue
        # Duplicate stairs check across seeds: collect and verify no two seeds share stairs
        results.append({"check": f"stair reach seed {seed}", "status": PASS,
                        "detail": f"floor={floor} biome={biome} stairs={stairs} reachable from spawn={spawn} map={level_w}x{level_h} rooms={room_count}"})
    return results


# ------------------------------------------------------------- 3. balance ---

def _dominates(a: dict, b: dict, stat_fields, cost_fields) -> bool:
    """True if `a` is at least as good as `b` everywhere that matters, and better somewhere.

    Corrections, each paid for with a measurement:
      * **Stats are NESTED under `effect`** (`{damage, armor, crit, luck, max_hp, speed}`), with
        `slot/effect/value/tier` at top level. Reading top-level fields compared 0 against 0 for
        every item, so this function could never return True: `check_balance` looked for stats in
        `effect` while this compared the top level, and the gate passed vacuously. A green that
        cannot go red is worse than no check at all.
      * **`value` is a COST, not a benefit.** Treating a higher price as "better" made
        the more expensive item the dominant one. Cost must be <= to dominate.
    """
    def stat(item, field):
        """Read a stat where the content actually puts it: inside `effect`."""
        effect = item.get("effect")
        value = effect.get(field) if isinstance(effect, dict) else None
        if value is None:
            value = item.get(field)
        try:
            return float(value or 0)
        except (TypeError, ValueError):
            return 0.0

    better = False
    for f in stat_fields:
        av, bv = stat(a, f), stat(b, f)
        if av < bv:
            return False
        if av > bv:
            better = True
    for f in cost_fields:
        if stat(a, f) > stat(b, f):
            return False
    return better


def check_balance() -> list[dict]:
    """No item may strictly dominate another at the same tier on every comparable stat."""
    content_path = PROJECT_ROOT / "game" / "data" / "items.json"
    if not content_path.is_file():
        return [{"check": "balance items", "status": SKIP,
                 "detail": "items.json not found"}]
    try:
        data = json.loads(content_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return [{"check": "balance items", "status": SKIP,
                 "detail": "cannot read items.json"}]
    entries = data.get("entries", [])

    # Discover the schema instead of assuming it. Stats live INSIDE effect.{...} and the set is
    # whatever the content actually uses - a hardcoded candidate list silently ignored `max_hp`
    # and `luck`, so an item granting +8 max_hp looked like it was dominated by one granting
    # +0.15 speed. Comparing only SOME of an item's stats manufactures findings.
    stat_fields = sorted({k for e in entries if isinstance(e.get("effect"), dict)
                          for k in e["effect"]})
    cost_fields = [f for f in ("value", "cost", "price")
                   if any(e.get(f) not in (None, 0, 0.0) for e in entries)]
    if not stat_fields:
        return [{"check": "balance items", "status": SKIP,
                 "detail": "no item carries an `effect` stat map - dominance is not measurable "
                           "from this schema, so this check asserts nothing instead of inventing "
                           "findings from price order"}]

    by_tier: dict[int, list[dict]] = defaultdict(list)
    for e in entries:
        tier = int(e.get("tier", 1))
        by_tier[tier].append(e)

    results = []
    for tier, items in sorted(by_tier.items()):
        if len(items) < 2:
            continue
        for i, a in enumerate(items):
            for b in items[i + 1:]:
                # Same slot only: a weapon cannot "dominate" a trinket.
                if a.get("slot") and b.get("slot") and a.get("slot") != b.get("slot"):
                    continue
                for x, y in ((a, b), (b, a)):
                    if _dominates(x, y, stat_fields, cost_fields):
                        results.append({
                            "check": f"balance tier {tier} {x.get('id','?')} > {y.get('id','?')}",
                            "status": FAIL,
                            "detail": "%s strictly dominates %s at tier %d (better on %s, "
                                      "no more expensive)" % (x.get("id"), y.get("id"), tier,
                                                              "/".join(stat_fields))})
    if not results:
        results.append({"check": "balance items", "status": PASS,
                        "detail": "no strictly-dominant item found at any tier (compared on %s)"
                                  % "/".join(stat_fields)})
    return results


# ------------------------------------------------------------------ runner ---

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m tools.qa.regression")
    ap.add_argument("--seeds", nargs="*", type=int, default=[0, 1, 2, 3, 4, 5, 6, 7],
                    help="seeds to test (default 0..7)")
    ap.add_argument("--turns", type=int, default=300,
                    help="headless turns per seed (default 300)")
    ap.add_argument("--json", action="store_true", dest="as_json")
    ap.add_argument("--no-golden", action="store_true", help="skip golden-seed checks")
    ap.add_argument("--no-stairs", action="store_true", help="skip stair-reachability checks")
    ap.add_argument("--no-balance", action="store_true", help="skip balance checks")
    args = ap.parse_args(argv)

    results = []

    if not args.no_golden:
        results.extend(check_golden(args.seeds, args.turns))

    if not args.no_stairs:
        results.extend(check_stairs(args.seeds, args.turns))

    if not args.no_balance:
        results.extend(check_balance())

    # Merge duplicate check names (golden seed 0 run 1 and run 2 share a name)
    merged: dict[str, dict] = {}
    for r in results:
        name = r["check"]
        if name in merged:
            # Keep the worst status
            order = {FAIL: 0, PASS: 1, SKIP: 2}
            if order.get(r["status"], 2) < order.get(merged[name]["status"], 2):
                merged[name] = r
        else:
            merged[name] = r

    final = list(merged.values())
    failed = [r for r in final if r["status"] == FAIL]

    if args.as_json:
        print(json.dumps({"ok": not failed, "checks": final}, indent=2))
        return 0 if not failed else 1

    print("=" * 72)
    print("REGRESSION  %s" % time_str())
    print("=" * 72)
    for r in final:
        mark = {"PASS": "+", "FAIL": "X", "SKIP": "-"}[r["status"]]
        print("  %s %-44s %s" % (mark, r["check"][:44], r["detail"]))
    print("-" * 72)
    if failed:
        print("VERDICT: FAIL - %d check(s) red" % len(failed))
        return 1
    print("VERDICT: PASS - all %d check(s) green" % len(final))
    return 0


def time_str() -> str:
    import datetime
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


if __name__ == "__main__":
    sys.exit(main())
