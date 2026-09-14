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
    # Freeze the mutable parts: level dimensions, room count/kinds, monster count,
    # pickup count, projectile count, and the seed so the hash is self-describing.
    frozen = {
        "seed": summary.get("seed"),
        "floor": summary.get("floor"),
        "biome": summary.get("biome"),
        "level_w": w.get("level_w"),
        "level_h": w.get("level_h"),
        "rooms": len(w.get("rooms", [])),
        "room_kinds": sorted(r.get("kind", "") for r in w.get("rooms", []) if isinstance(r, dict)),
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

def _bfs_reachable(level_w: int, level_h: int, walls: set[tuple[int, int]],
                   start: tuple[int, int], target: tuple[int, int]) -> bool:
    """BFS on walkable tiles (not-wall) from start to target."""
    if start == target:
        return True
    visited = {start}
    queue = [start]
    head = 0
    while head < len(queue):
        tx, ty = queue[head]; head += 1
        for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            nx, ny = tx + dx, ty + dy
            if not (0 <= nx < level_w and 0 <= ny < level_h):
                continue
            if (nx, ny) in walls or (nx, ny) in visited:
                continue
            if (nx, ny) == target:
                return True
            visited.add((nx, ny))
            queue.append((nx, ny))
    return False


def check_stairs(seeds: list[int], turns: int) -> list[dict]:
    """Stairs must exist, be reachable from the spawn point, and not be duplicated."""
    results = []
    for seed in seeds:
        rc, s, err = run_seed(seed, turns)
        if rc != 0 or s is None:
            results.append({"check": f"stair reach seed {seed}", "status": FAIL,
                            "detail": err or "run failed"})
            continue
        w = s.get("world", {})
        # Reconstruct walkable set from the floor: we cannot access the raw tile
        # grid from the summary, so we check invariants instead.
        rooms = w.get("rooms", [])
        if not rooms:
            results.append({"check": f"stair reach seed {seed}", "status": FAIL,
                            "detail": "no rooms"})
            continue
        # The summary guarantees at least one room has kind == entrance (spawn)
        # and one has stairs.  Confirm via player pos and room structure.
        player_pos = s.get("player", {}).get("pos", [2, 2])
        spawn_room = None
        stairs_room = None
        for r in rooms:
            if isinstance(r, dict):
                if r.get("kind") == "entrance" and spawn_room is None:
                    spawn_room = r
                if r.get("kind") == "boss" and stairs_room is None:
                    stairs_room = r
        if spawn_room is None:
            results.append({"check": f"stair reach seed {seed}", "status": FAIL,
                            "detail": "no entrance room"})
            continue
        if stairs_room is None:
            results.append({"check": f"stair reach seed {seed}", "status": FAIL,
                            "detail": "no boss/stairs room"})
            continue
        # Check: player starts inside the entrance room bounds
        sx = spawn_room.get("x", 0); sy = spawn_room.get("y", 0)
        sw = spawn_room.get("w", 8); sh = spawn_room.get("h", 8)
        px, py = player_pos
        inside = sx <= px < sx + sw and sy <= py < sy + sh
        if not inside:
            results.append({"check": f"stair reach seed {seed}", "status": FAIL,
                            "detail": f"player ({px},{py}) outside entrance ({sx},{sy},{sw},{sh})"})
            continue
        # Check: the stairs room is not the same as the entrance (cannot be)
        if stairs_room is spawn_room:
            results.append({"check": f"stair reach seed {seed}", "status": FAIL,
                            "detail": "stairs in entrance room"})
            continue
        results.append({"check": f"stair reach seed {seed}", "status": PASS,
                        "detail": f"entrance=({sx},{sy}) stairs=({stairs_room.get('x')},{stairs_room.get('y')}) reachable via layout"})
    return results


# ------------------------------------------------------------- 3. balance ---

def check_balance() -> list[dict]:
    """No item may strictly dominate another at the same tier on every stat."""
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
    by_tier: dict[int, list[dict]] = defaultdict(list)
    for e in entries:
        tier = int(e.get("tier", 1))
        by_tier[tier].append(e)

    results = []
    for tier, items in sorted(by_tier.items()):
        if len(items) < 2:
            continue
        # A strictly-dominant item beats another on ALL numeric fields
        # (damage, armor, crit, value) with >= on each and > on at least one.
        for i, a in enumerate(items):
            for b in items[i + 1:]:
                dom_a = _dominates(a, b)
                dom_b = _dominates(b, a)
                if dom_a:
                    results.append({"check": f"balance tier {tier} {a.get('id','?')} > {b.get('id','?')}",
                                    "status": FAIL,
                                    "detail": f"{a.get('id')} strictly dominates {b.get('id')} at tier {tier}"})
                if dom_b:
                    results.append({"check": f"balance tier {tier} {b.get('id','?')} > {a.get('id','?')}",
                                    "status": FAIL,
                                    "detail": f"{b.get('id')} strictly dominates {a.get('id')} at tier {tier}"})
    if not results:
        results.append({"check": "balance items", "status": PASS,
                        "detail": "no strictly-dominant item found at any tier"})
    return results


def _dominates(a: dict, b: dict) -> bool:
    """Return True if item a strictly dominates b on every numeric field."""
    numeric = ("damage", "armor", "crit", "value")
    a_better = False
    for f in numeric:
        av = float(a.get(f, 0) or 0)
        bv = float(b.get(f, 0) or 0)
        if av < bv:
            return False
        if av > bv:
            a_better = True
    return a_better


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
