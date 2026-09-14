"""Pre-commit gate: no broken `main`, and no silently deleted tooling.

    python -m tools.studio.pre_commit              # run the checks by hand
    python -m tools.studio.pre_commit --install    # write .git/hooks/pre-commit
    SKIP_GATE=1 git commit ...                     # bypass (emergencies; justify it in the message)

Two rules, both learned from real incidents on 2026-09-14:

1. **Law 2 - never break `main`.** A round edited `game/ui/settings.py` to `pygame.K_J` (not a real
   pygame constant), which made the whole game unimportable, and it sat in the tree until a human
   looked. Law 2 was enforced by *review*, which cannot see a break that lands between reviews. Now
   it is enforced at the commit boundary: if the game does not import, or a 300-tick headless run
   does not exit 0 with empty `invariants.violations`, the commit is refused with the real output.

2. **Never delete tracked source.** A round committed
   `18453ee "tools/qa/progression.py removed"` - deleting a tracked, working QA tool minutes after it
   landed, apparently treating an unfamiliar file as debris. The studio's no-debris rule is aimed at
   scratch artifacts in `runs/` and `assets/`; it must never be read as licence to remove tracked
   source under `game/` or `tools/`. Deleting a tracked `.py` there is refused and has to be
   justified deliberately (delete the file in its own commit with SKIP_GATE and a reason).

Install once per clone (hooks are not versioned):
    python -m tools.studio.pre_commit --install

Exit: 0 safe to commit, 1 refused, 2 could not run the checks.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HOOK = ROOT / ".git" / "hooks" / "pre-commit"
TURNS = 300
SEED = 0
PROTECTED_PREFIXES = ("game/", "tools/")

HOOK_BODY = """#!/bin/sh
# Rogueworks commit gate - installed by `python -m tools.studio.pre_commit --install`.
# Bypass deliberately (and say why in the message): SKIP_GATE=1 git commit ...
exec "{python}" -m tools.studio.pre_commit
"""


def python_bin() -> str:
    """Prefer the game venv, so the gate tests the interpreter the game actually runs on."""
    for cand in (ROOT / ".venv/Scripts/python.exe", ROOT / ".venv/bin/python"):
        if cand.exists():
            return str(cand)
    return sys.executable


def run(cmd: list[str], timeout: int = 900) -> tuple[int, str]:
    env = {**os.environ, "MSYS_NO_PATHCONV": "1", "SDL_VIDEODRIVER": "dummy",
           "SDL_AUDIODRIVER": "dummy", "PYGAME_HIDE_SUPPORT_PROMPT": "1"}
    p = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=timeout, env=env)
    return p.returncode, ((p.stdout or "") + (p.stderr or "")).strip()


def staged_deletions() -> list[str]:
    """Tracked files deleted in this commit (staged)."""
    p = subprocess.run(["git", "diff", "--cached", "--diff-filter=D", "--name-only"],
                       cwd=str(ROOT), capture_output=True, text=True)
    return [l.strip() for l in (p.stdout or "").splitlines() if l.strip()]


def check_deletions() -> int:
    gone = [f for f in staged_deletions()
            if f.startswith(PROTECTED_PREFIXES) and f.endswith(".py")]
    if not gone:
        return 0
    print("\n*** COMMIT REFUSED - tracked source deleted ***\n")
    for f in gone:
        print("  D %s" % f)
    print("\n`game/` and `tools/` hold the game and the studio's own tooling. The no-debris rule")
    print("covers scratch artifacts in runs/ and assets/ - it is NOT licence to remove tracked")
    print("source you did not recognise. If the deletion is genuinely intended, make it its own")
    print("commit and say why:  SKIP_GATE=1 git commit -m \"remove <file>: <reason>\"")
    return 1


def check_law2() -> int:
    py = python_bin()
    rc, out = run([py, "-c", "import game.main"])
    if rc != 0:
        print("\n*** COMMIT REFUSED - LAW 2: the game package does not import ***\n")
        print("\n".join(out.splitlines()[-8:]))
        print("\nFix the import error, then commit again. (Bypass: SKIP_GATE=1)")
        return 1

    rc, out = run([py, "-c",
                   "from game.main import main; import sys; "
                   "sys.exit(main(['--headless','--turns','%d','--seed','%d']))" % (TURNS, SEED)])
    ok_line = [l for l in out.splitlines() if "ok=" in l]
    if rc != 0 or not any("violations=[]" in l for l in ok_line):
        print("\n*** COMMIT REFUSED - LAW 2: main is broken ***\n")
        print("  game.main --headless --turns %d --seed %d  ->  exit %d" % (TURNS, SEED, rc))
        for l in (ok_line[:2] or out.splitlines()[-8:]):
            print("  %s" % l.strip())
        print("\nA round may hold a broken tree while it works; it may not record it as done.")
        print("(Bypass: SKIP_GATE=1)")
        return 1
    return 0


def check() -> int:
    if check_deletions() != 0:
        return 1
    if check_law2() != 0:
        return 1
    print("commit gate: no protected deletions, import OK, headless %d ticks seed %d "
          "violations=[]" % (TURNS, SEED))
    return 0


def install() -> int:
    HOOK.parent.mkdir(parents=True, exist_ok=True)
    HOOK.write_text(HOOK_BODY.format(python=python_bin()), encoding="utf-8", newline="\n")
    try:
        os.chmod(HOOK, 0o755)
    except OSError:
        pass
    print("installed %s" % HOOK)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m tools.studio.pre_commit")
    ap.add_argument("--install", action="store_true", help="write .git/hooks/pre-commit")
    args = ap.parse_args(argv)
    if args.install:
        return install()
    if os.environ.get("SKIP_GATE") or os.environ.get("SKIP_LAW2"):
        print("commit gate: BYPASSED by env - this must be justified in the commit message")
        return 0
    return check()


if __name__ == "__main__":
    sys.exit(main())
