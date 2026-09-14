"""Acceptance helpers: seed reproducibility + save/load round-trip.

Run with the project venv:
    .venv/Scripts/python.exe tools/qa/acceptance.py
"""

import json
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PY = str(PROJECT_ROOT / ".venv" / "Scripts" / "python.exe")


def run_cli(args):
    env = dict(os.environ)
    env["MSYS_NO_PATHCONV"] = "1"
    proc = subprocess.run([PY, "-m", "game.main"] + args, cwd=str(PROJECT_ROOT),
                          env=env, capture_output=True, text=True)
    return proc.returncode, proc.stdout + proc.stderr


def comparable(summary):
    """Summary minus wall-clock metrics, for byte-for-byte comparison."""
    out = json.loads(json.dumps(summary))
    out.pop("metrics", None)
    return out


def main():
    print("=== seed reproducibility (two fresh seed-5 runs must match exactly) ===")
    save_path = PROJECT_ROOT / "save.json"
    if save_path.exists():
        save_path.unlink()
    code_a, out_a = run_cli(["--headless", "--turns", "400", "--seed", "5",
                             "--log", "runs/repro-a.json"])
    if save_path.exists():
        save_path.unlink()
    code_b, out_b = run_cli(["--headless", "--turns", "400", "--seed", "5",
                             "--log", "runs/repro-b.json"])
    a = json.load(open(PROJECT_ROOT / "runs" / "repro-a.json"))
    b = json.load(open(PROJECT_ROOT / "runs" / "repro-b.json"))
    same = comparable(a) == comparable(b)
    print("  exit codes: %d / %d" % (code_a, code_b))
    print("  world   A=%s B=%s" % (a["world"], b["world"]))
    print("  player  A=%s B=%s" % (a["player"], b["player"]))
    print("  identical (ignoring metrics): %s" % same)
    different = [k for k in comparable(a) if comparable(a)[k] != comparable(b)[k]]
    print("  differing keys: %s" % (different or "none"))

    print()
    print("=== save/load round-trip ===")
    code, out = run_cli(["--headless", "--turns", "250", "--seed", "2"])
    for line in out.splitlines():
        if "essence" in line or "summary written" in line:
            print("  writer: %s" % line.strip())
    sys.path.insert(0, str(PROJECT_ROOT))
    from game.systems import save as save_sys
    profile, notes = save_sys.load_profile()
    print("  reader notes: %s" % notes)
    print("  reader: essence=%d meta=%s levels=%s stats=%s run=%s"
          % (profile["essence"], profile["meta"], profile["levels"], profile["stats"],
             profile["run"]))
    print("  round-trip meta totals: %s" % save_sys.meta_stat_totals(profile))

    # a missing file must be a fresh profile
    missing, missing_notes = save_sys.load_profile(str(PROJECT_ROOT / "runs" / "nope.json"))
    print("  missing file -> essence=%d notes=%s" % (missing["essence"], missing_notes))

    # an older version must migrate or reset, never crash
    old_path = PROJECT_ROOT / "runs" / "old-save.json"
    old_path.write_text(json.dumps({"version": 0, "essence": 123,
                                    "levels": {"vitality": 2}, "stats": {"runs": 4}}))
    migrated, migrated_notes = save_sys.load_profile(str(old_path))
    print("  v0 file -> essence=%d levels=%s notes=%s"
          % (migrated["essence"], migrated["levels"], migrated_notes))

    # corrupt file must reset
    bad_path = PROJECT_ROOT / "runs" / "bad-save.json"
    bad_path.write_text("{not json at all")
    bad, bad_notes = save_sys.load_profile(str(bad_path))
    print("  corrupt file -> essence=%d notes=%s" % (bad["essence"], bad_notes))

    print()
    print("=== meta progression across processes ===")
    if save_path.exists():
        save_path.unlink()
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    import pygame

    pygame.init()
    try:
        pygame.display.set_mode((1, 1))
    except pygame.error:
        pass
    from game.engine.input import AutoPilotInput
    from game.systems import meta as meta_sys
    from game.systems.save import default_profile
    from game.systems.world import TICK, World

    writer_profile = default_profile()
    world = World(seed=1, profile=writer_profile, headless=True)
    world.input_source = AutoPilotInput(world)
    for _ in range(9000):
        if world.run_state != "running":
            break
        world.step(TICK)
    meta_sys.apply_run_results(writer_profile, world)
    meta_sys.clear_run(writer_profile)
    saved = save_sys.save_profile(writer_profile, None)
    print("  writer(process 1): run seed=%d floor=%d kills=%d essence_earned=%d"
          % (world.seed, world.floor, world.player.kills, world.essence_run))
    print("  writer(process 1): save.json -> %s  essence=%d stats=%s"
          % (saved.name, writer_profile["essence"], writer_profile["stats"]))

    proc = subprocess.run([PY, str(PROJECT_ROOT / "tools" / "qa" / "reader.py"), "--buy"],
                          cwd=str(PROJECT_ROOT), capture_output=True, text=True)
    print("  reader(process 2) exit=%d" % proc.returncode)
    for line in proc.stdout.splitlines():
        print("   ", line.strip())
    if proc.stderr.strip():
        print("  reader stderr: %s" % proc.stderr.strip().splitlines()[-1])

    upgraded, _notes = save_sys.load_profile()
    code, out = run_cli(["--headless", "--turns", "20", "--seed", "9", "--log",
                         "runs/meta-check.json"])
    summary = json.load(open(PROJECT_ROOT / "runs" / "meta-check.json"))
    expect_hp = 90 + 10 * int(upgraded["levels"].get("vitality", 0))
    print("  run with meta applied: player max_hp=%d expected>=%d (vitality lv %d) exit=%d"
          % (summary["player"]["max_hp"], expect_hp,
             int(upgraded["levels"].get("vitality", 0)), code))
    meta_ok = summary["player"]["max_hp"] >= expect_hp

    print()
    ok = same and code_a == 0 and code_b == 0 and meta_ok
    print("ACCEPTANCE: %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())