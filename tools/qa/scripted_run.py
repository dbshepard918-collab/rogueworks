"""scripted_run: replay a scripted-input JSON and audit the run summary.

    python -m tools.qa.scripted_run --seed 1 --turns 300
    python -m tools.qa.scripted_run --seed 3 --script runs/scripts/boss.json

Drives ``python -m game.main --headless --seed S --script F --log L`` (section 3
of docs/CONTRACTS.md) and then audits ``L`` against the exact section-3.1 schema:
every top-level key present, ``ok == true``, ``errors`` empty and
``invariants.violations`` empty.  Without ``--script`` it writes a deterministic
smoke script into ``runs/scripts/`` first, so an auto-run always exists to point
a QA report at.

Exit status: 0 clean run, 1 a real problem (bad exit code, missing/malformed
summary, invariant violation), 2 the game package is not importable yet or the
arguments were bad.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

from tools import _util
from tools._util import EXIT_FAIL, EXIT_OK, EXIT_PREREQ, ToolError

# docs/CONTRACTS.md section 3.1 - exact top-level keys
TOP_KEYS = ("ok", "seed", "ticks", "biome", "floor", "player", "world", "metrics", "errors", "invariants")
PLAYER_KEYS = ("hp", "max_hp", "level", "xp", "gold", "essence", "kills", "items", "statuses", "pos")
WORLD_KEYS = ("entities", "monsters", "projectiles", "pickups", "rooms", "level_w", "level_h")
METRIC_KEYS = ("frames", "ms_per_tick", "fps_equiv")

ACTIONS = ("attack", "dash", "use", "interact", "tab", "confirm")


def default_script(name: str = "smoke") -> dict:
    """A deterministic sweep: forward, strafe, dash, back, attack, idle."""
    return {
        "name": name,
        "steps": [
            {"tick": 0, "move": [1, 0], "actions": ["attack"]},
            {"tick": 15, "move": [0, 1], "actions": []},
            {"tick": 30, "move": [0, -1], "actions": ["dash"]},
            {"tick": 45, "move": [-1, 0], "actions": ["attack"]},
            {"tick": 60, "move": [-1, -1], "actions": []},
            {"tick": 80, "move": [0, 0], "actions": ["attack", "dash"]},
        ],
    }


def validate_script(data, where: str) -> list[str]:
    """Check the section-3.2 scripted-input shape; returns error strings."""
    errs: list[str] = []
    if not isinstance(data, dict):
        return [f"{where}: script must be a JSON object with 'steps'"]
    steps = data.get("steps")
    if not isinstance(steps, list) or not steps:
        return [f"{where}: 'steps' must be a non-empty array"]
    last = -1
    for i, step in enumerate(steps):
        at = f"{where}: step {i}"
        if not isinstance(step, dict):
            errs.append(f"{at} must be an object")
            continue
        tick = step.get("tick")
        if not isinstance(tick, int) or isinstance(tick, bool) or tick < 0:
            errs.append(f"{at} 'tick' must be a non-negative integer, got {tick!r}")
        elif tick < last:
            errs.append(f"{at} 'tick' {tick} goes backwards (previous {last})")
        else:
            last = tick
        move = step.get("move", [0, 0])
        if (not isinstance(move, list) or len(move) != 2
                or not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in move)):
            errs.append(f"{at} 'move' must be [x, y] numbers, got {move!r}")
        elif any(abs(float(v)) > 1.0 + 1e-9 for v in move):
            errs.append(f"{at} 'move' {move!r} is outside [-1,1]^2")
        actions = step.get("actions", [])
        if not isinstance(actions, list) or any(not isinstance(a, str) for a in actions):
            errs.append(f"{at} 'actions' must be a list of strings, got {actions!r}")
    return errs


def audit_summary(data, seed: int) -> tuple[list[str], list[str], dict]:
    """Audit a run summary -> (errors, warnings, headline dict)."""
    errs: list[str] = []
    warns: list[str] = []
    for key in TOP_KEYS:
        if key not in data:
            errs.append(f"run summary is missing top-level key '{key}'")
    for key, keys in (("player", PLAYER_KEYS), ("world", WORLD_KEYS), ("metrics", METRIC_KEYS)):
        block = data.get(key)
        if not isinstance(block, dict):
            errs.append(f"run summary '{key}' must be an object")
            continue
        for sub in keys:
            if sub not in block:
                errs.append(f"run summary '{key}.{sub}' is missing")

    if data.get("ok") is not True:
        errs.append(f"run summary ok is {data.get('ok')!r} (must be true)")
    if data.get("errors"):
        errs.append(f"run reported {len(data['errors'])} error(s): {str(data['errors'][0])[:90]}")
    hist_seed = data.get("seed")
    if isinstance(hist_seed, int) and hist_seed != seed:
        warns.append(f"run summary seed {hist_seed} != requested {seed} (the game may ignore --seed)")

    inv = data.get("invariants")
    if not isinstance(inv, dict) or not isinstance(inv.get("violations"), list):
        errs.append("run summary has no 'invariants.violations' list")
    else:
        violations = inv["violations"]
        if violations:
            errs.append(f"{len(violations)} invariant violation(s), first: {str(violations[0])[:110]}")
            for extra in violations[1:4]:
                errs.append(f"  violation: {str(extra)[:110]}")

    player = data.get("player") or {}
    world = data.get("world") or {}
    metrics = data.get("metrics") or {}
    hp, max_hp = player.get("hp"), player.get("max_hp")
    if isinstance(hp, (int, float)) and isinstance(max_hp, (int, float)):
        if not (0 <= hp <= max_hp):
            errs.append(f"player hp {hp} is outside [0, max_hp={max_hp}]")
    headline = {
        "seed": data.get("seed"),
        "ticks": data.get("ticks"),
        "floor": data.get("floor"),
        "biome": data.get("biome"),
        "hp": f"{hp}/{max_hp}" if hp is not None else "?",
        "kills": player.get("kills"),
        "gold": player.get("gold"),
        "entities": world.get("entities"),
        "monsters": world.get("monsters"),
        "rooms": world.get("rooms"),
        "ms_per_tick": metrics.get("ms_per_tick"),
        "fps_equiv": metrics.get("fps_equiv"),
    }
    return errs, warns, headline


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m tools.qa.scripted_run",
        description="Replay a scripted input against the game CLI and audit the run summary.",
    )
    ap.add_argument("--seed", type=int, default=0, help="run seed (default 0)")
    ap.add_argument("--script", default=None, help="scripted-input JSON; default: a generated smoke script")
    ap.add_argument("--name", default="smoke", help="name for the generated script (default smoke)")
    ap.add_argument("--turns", type=int, default=300, help="simulation steps (default 300)")
    ap.add_argument("--log", default=None, help="run summary path (default runs/playtest-<seed>.json)")
    ap.add_argument("--timeout", type=float, default=300.0, help="subprocess timeout seconds")
    ap.add_argument("--python", default=sys.executable, help="interpreter for the game")
    ap.add_argument("--game-module", default="game.main", help="entry module (default game.main)")
    ap.add_argument("--floor", type=int, default=None, help="start on floor N (debug)")
    ap.add_argument("--keep-save", action="store_true",
                    help="do not pass --new-run (exercise the save/load path)")
    ap.add_argument("--json", action="store_true", dest="as_json", help="machine-readable report")
    args = ap.parse_args(argv)

    root = _util.find_root()

    # -- script: load or generate ------------------------------------------- #
    if args.script:
        script_path = Path(args.script) if Path(args.script).is_absolute() else root / args.script
        if not script_path.is_file():
            script_path = Path.cwd() / args.script
        script = _util.load_json(script_path)
    else:
        script = default_script(args.name)
        script_path = _util.ensure_dir(root / "runs" / "scripts") / f"{args.name}-seed{int(args.seed)}.json"
        _util.write_json(script_path, script)

    script_errors = validate_script(script, _util.rel_posix(script_path, root))
    if script_errors:
        for e in script_errors:
            _util.err(e)
        _util.say(f"FAIL: scripted input is malformed ({len(script_errors)} problem(s))")
        return EXIT_FAIL

    available, detail = _util.module_available(args.python, args.game_module, root)
    if not available:
        _util.say(
            f"game package not built yet - '{args.game_module}' is not importable ({detail}); "
            "generated the script and stopped"
        )
        _util.say(f"script written: {_util.rel_posix(script_path, root)}")
        _util.say("hint: rerun this once game/main.py exists; the driver is CLI-only on purpose")
        return EXIT_PREREQ

    log_path = Path(args.log) if args.log else (root / "runs" / f"playtest-{int(args.seed)}.json")
    if not log_path.is_absolute():
        log_path = root / log_path
    _util.ensure_dir(log_path.parent)

    cmd = [args.python, "-m", args.game_module, "--headless", "--seed", str(int(args.seed)),
           "--script", str(script_path), "--log", str(log_path)]
    if args.turns is not None:
        cmd += ["--turns", str(int(args.turns))]
    if args.floor is not None:
        cmd += ["--floor", str(int(args.floor))]
    if not args.keep_save:
        cmd += ["--new-run"]

    if not args.as_json:
        _util.say(f"$ {' '.join(cmd)}")
        _util.say("--- game output ---")

    started = time.time()
    try:
        proc = subprocess.run(cmd, cwd=str(root), capture_output=True, text=True,
                              timeout=float(args.timeout), env=_child_env())
        rc, stdout, stderr = proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        _util.say(f"game run timed out after {args.timeout}s")
        return EXIT_FAIL
    except OSError as exc:
        _util.say(f"cannot launch the game ({args.python}): {exc}")
        return EXIT_PREREQ
    elapsed = time.time() - started

    if not args.as_json:
        for line in (stdout or "").splitlines():
            _util.say(f"  {line}")
        if stderr:
            for line in stderr.splitlines():
                _util.say(f"  ! {line}")
        _util.say("--- end game output ---")

    problems: list[str] = []
    if rc != 0:
        problems.append(f"game exited with code {rc}")

    summary = None
    if not log_path.is_file():
        problems.append(f"no run summary at {_util.rel_posix(log_path, root)}")
    else:
        try:
            summary = json.loads(log_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            problems.append(f"run summary is not valid JSON: {exc}")

    warnings: list[str] = []
    headline: dict = {}
    if isinstance(summary, dict):
        errs, warnings, headline = audit_summary(summary, int(args.seed))
        problems += errs

    ok = not problems
    if args.as_json:
        print(json.dumps({
            "ok": ok,
            "cmd": cmd,
            "exit_code": rc,
            "seed": int(args.seed),
            "script": _util.rel_posix(script_path, root),
            "log": _util.rel_posix(log_path, root),
            "elapsed_s": round(elapsed, 3),
            "summary": headline,
            "problems": problems,
            "warnings": warnings,
        }, indent=2))
        return EXIT_OK if ok else EXIT_FAIL

    _util.say(f"game exit code: {rc}   wall {elapsed:.2f}s")
    _util.say(f"script: {_util.rel_posix(script_path, root)}")
    _util.say(f"summary: {_util.rel_posix(log_path, root)}")
    if headline:
        _util.say(
            "  seed {seed}  floor {floor}  biome {biome}  hp {hp}  kills {kills}  gold {gold}\n"
            "  entities {entities}  monsters {monsters}  rooms {rooms}  "
            "ms/tick {ms_per_tick}  fps-equiv {fps_equiv}".format(**headline)
        )
    for w in warnings:
        _util.warn(w)
    for p in problems:
        if p.startswith("  "):
            _util.say(f"ERROR{p}")
        else:
            _util.err(p)
    if ok:
        _util.say("PASS: run completed, summary schema exact, invariants clean")
        return EXIT_OK
    _util.say(f"FAIL: {len(problems)} problem(s)")
    return EXIT_FAIL


def _child_env() -> dict:
    import os

    env = dict(os.environ)
    env["SDL_VIDEODRIVER"] = "dummy"
    env["SDL_AUDIODRIVER"] = "dummy"
    env.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
    return env


if __name__ == "__main__":
    sys.exit(_util.guard(main)())
