"""Keep the continuous loop alive. Run by cron every 15 minutes with no_agent=True.

Deliberately tiny and LLM-free: if the loop's lock pid is dead (or the lock is missing), start a new
detached loop. This is what makes "continuous" survive a crash, a reboot, or an OOM-killed turn.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PY = str(ROOT / ".venv" / "Scripts" / "python.exe")
LOCK = ROOT / "runs" / "studio" / "loop.lock"
OUT = ROOT / "runs" / "studio" / "loop.out"
STOP = ROOT / "runs" / "STOP"


def alive(pid: int) -> bool:
    try:
        out = subprocess.run(["tasklist", "/FI", "PID eq %d" % pid, "/FO", "CSV", "/NH"],
                             capture_output=True, text=True, timeout=30).stdout
        return str(pid) in out
    except Exception:  # noqa: BLE001
        return False


def main() -> int:
    if STOP.exists():
        print("watchdog: runs/STOP present - loop intentionally stopped, doing nothing")
        return 0
    if LOCK.is_file():
        try:
            pid = int(json.loads(LOCK.read_text(encoding="utf-8")).get("pid", 0))
        except Exception:  # noqa: BLE001
            pid = 0
        if pid and alive(pid):
            print("watchdog: loop alive (pid %d)" % pid)
            return 0
        print("watchdog: stale lock (pid %d is gone) - restarting" % pid)
    else:
        print("watchdog: no lock - starting the continuous loop")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, MSYS_NO_PATHCONV="1")
    env.pop("HERMES_DELEGATED_CHILD_CONTEXT", None)
    with OUT.open("ab") as fh:
        subprocess.Popen([PY, "-m", "tools.studio.loop"], cwd=str(ROOT), env=env,
                         stdout=fh, stderr=subprocess.STDOUT,
                         creationflags=0)  # DETACHED_PROCESS|NEW_PROCESS_GROUP
    print("watchdog: loop started detached (log: runs/studio/loop.out)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
