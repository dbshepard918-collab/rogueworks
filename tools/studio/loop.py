"""The studio's continuous driver: build -> review -> correct -> build, back to back, forever.

Schedule-based rounds are not continuous: a 2-hour cron leaves the studio idle for most of the day and
can start a round on top of a round that is still running. This loop owns the cadence instead:

    round N:  pre-flight gates  ->  one roadmap item (forge)  ->  review (warden)
              ->  close every pending slap against its acceptance command  ->  immediately round N+1

Guardrails (all of them exist because an unattended loop must never wedge the project):
  * single instance            - a pid lock; a stale lock from a dead pid is taken over
  * runs/STOP                  - create this file and the loop exits after the current turn
  * per-turn timeout           - a hung turn is killed and recorded, the loop continues
  * cooldown between rounds    - default 20s, so the GPU/LM Studio can breathe
  * full logging              - runs/studio/loop.jsonl + one log per turn
  * only free/local models     - every bot it drives is pinned free or local; nothing here can bill

    python -m tools.studio.loop                 # run forever (start it detached)
    python -m tools.studio.loop --once          # one full cycle, for testing
    python -m tools.studio.loop --rounds 5      # stop after 5 cycles
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PY = r"C:\Users\dbshe\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe"
STUDIO = ROOT / "runs" / "studio"
LOCK = STUDIO / "loop.lock"
STOPFILE = ROOT / "runs" / "STOP"
HEARTBEAT = STUDIO / "loop.jsonl"
ROADMAP = ROOT / "docs" / "ROADMAP.md"
SLAPS = ROOT / "docs" / "slaps.json"
BUILDER = "forge"
REVIEWER = "warden"


def log(msg: str) -> None:
    print("[%s] %s" % (time.strftime("%H:%M:%S"), msg), flush=True)


def record(event: dict) -> None:
    STUDIO.mkdir(parents=True, exist_ok=True)
    event["at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    with HEARTBEAT.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event) + "\n")


def pid_alive(pid: int) -> bool:
    try:
        out = subprocess.run(["tasklist", "/FI", "PID eq %d" % pid, "/FO", "CSV", "/NH"],
                             capture_output=True, text=True, timeout=30).stdout
        return str(pid) in out
    except Exception:  # noqa: BLE001
        return False


def take_lock() -> bool:
    STUDIO.mkdir(parents=True, exist_ok=True)
    if LOCK.is_file():
        try:
            old = json.loads(LOCK.read_text(encoding="utf-8"))
            if pid_alive(int(old.get("pid", 0))) and int(old.get("pid", 0)) != os.getpid():
                log("another loop is alive (pid %s, started %s) - exiting"
                    % (old.get("pid"), old.get("started")))
                return False
            log("taking over a stale lock (pid %s is gone)" % old.get("pid"))
        except Exception:  # noqa: BLE001
            pass
    LOCK.write_text(json.dumps({"pid": os.getpid(), "started": time.strftime("%Y-%m-%dT%H:%M:%S")}),
                    encoding="utf-8")
    return True


def run_turn(bot: str, brief: str, tag: str, timeout: int) -> dict:
    STUDIO.mkdir(parents=True, exist_ok=True)
    logfile = STUDIO / ("round-%s-%s.log" % (tag, bot))
    env = dict(os.environ, MSYS_NO_PATHCONV="1")
    env.pop("HERMES_DELEGATED_CHILD_CONTEXT", None)   # never drive bots as a read-only child
    cmd = [PY, "-m", "hermes_cli.main", "-p", bot, "chat", "-q", brief]
    t0 = time.time()
    with logfile.open("wb") as fh:
        try:
            proc = subprocess.Popen(cmd, cwd=str(ROOT), env=env, stdout=fh,
                                    stderr=subprocess.STDOUT)
            rc = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            rc = 124
    out = logfile.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"(\d+) tool call", out)
    status = "OK" if rc == 0 and m else ("TIMEOUT" if rc == 124 else "FAILED(rc=%d)" % rc)
    return {"bot": bot, "tag": tag, "status": status, "rc": rc, "seconds": round(time.time() - t0, 1),
            "tool_calls": int(m.group(1)) if m else 0, "log": logfile.relative_to(ROOT).as_posix(),
            "tail": "\n".join(out.strip().splitlines()[-3:])[:400]}


def in_flight() -> list[str]:
    """Anything mid-turn: another chat turn, or a FLUX generation. The loop serialises behind it.

    Without this, continuous means "two rounds on the same repo at once" the moment a cron round or a
    manual turn overlaps the loop.
    """
    ps = ("Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
          "Where-Object { $_.CommandLine -match 'chat -q|art.gen|studio.loop' } | "
          "ForEach-Object { $_.ProcessId.ToString() + ' ' + "
          "($_.CommandLine -replace '.*(chat -q|art.gen|studio.loop).*','$1') }")
    try:
        p = subprocess.run(["powershell.exe", "-NoProfile", "-Command", ps],
                           capture_output=True, text=True, timeout=60, encoding="utf-8",
                           errors="replace")
        hits = [ln.strip() for ln in (p.stdout or "").splitlines() if ln.strip()]
        me = os.getpid()
        return [h for h in hits if not h.startswith(str(me) + " ")
                and "studio.loop" not in h]
    except Exception:  # noqa: BLE001
        return []


def wait_idle(max_wait: int, poll: int = 20) -> int:
    waited = 0
    while waited < max_wait:
        busy = in_flight()
        if not busy:
            return waited
        if waited == 0:
            log("  in-flight work detected (%s) - waiting for it to finish" % ", ".join(busy[:3]))
        if STOPFILE.exists():
            return waited
        time.sleep(poll)
        waited += poll
    log("  still busy after %ds - proceeding anyway" % max_wait)
    return waited


def gate_summary() -> str:
    try:
        p = subprocess.run([PY, "-m", "tools.studio.verify_gate", "--seeds", "0", "--turns", "200"],
                           cwd=str(ROOT), env=dict(os.environ, MSYS_NO_PATHCONV="1"),
                           capture_output=True, text=True, timeout=600, encoding="utf-8",
                           errors="replace")
        lines = [ln.rstrip() for ln in (p.stdout or "").splitlines() if ln.strip()]
        keep = [ln for ln in lines if ("PASS" in ln or "FAIL" in ln or "VERDICT" in ln)]
        return "\n".join(keep[-9:]) or "(no gate output)"
    except Exception as exc:  # noqa: BLE001
        return "(gate run failed: %s)" % exc


def next_item() -> str:
    """First unchecked roadmap item - so the round is targeted, not 'choose something'."""
    if not ROADMAP.is_file():
        return "the highest-priority open ticket in docs/TICKETS.md"
    for line in ROADMAP.read_text(encoding="utf-8").splitlines():
        if re.match(r"^\s*-\s*\[ \]\s*\*\*", line):
            return line.strip().lstrip("- [ ] ").replace("**", "")
    return "the highest-priority open ticket in docs/TICKETS.md"


def open_slaps() -> list[dict]:
    if not SLAPS.is_file():
        return []
    try:
        data = json.loads(SLAPS.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return []
    return [s for s in data.get("slaps", [])
            if str(s.get("status", "")).startswith(("PENDING", "STILL OPEN"))]


def close_pending() -> list[str]:
    """Every open slap gets graded against its own acceptance command, immediately after review."""
    out = []
    for s in open_slaps():
        try:
            p = subprocess.run([PY, "-m", "tools.studio.slap", "--close", str(s["n"])],
                               cwd=str(ROOT), env=dict(os.environ, MSYS_NO_PATHCONV="1"),
                               capture_output=True, text=True, timeout=1800, encoding="utf-8",
                               errors="replace")
            verdict = "CLEAN" if "CLEAN - fix verified" in (p.stdout or "") else "STILL OPEN"
            out.append("SLAP #%s (%s): %s" % (s["n"], s.get("bot"), verdict))
        except Exception as exc:  # noqa: BLE001
            out.append("SLAP #%s: close failed (%s)" % (s["n"], exc))
    return out


def slap_line(s: dict) -> str:
    return ("SLAP #%s on %s (level %s, %s): %s"
            % (s.get("n"), s.get("bot"), s.get("level"),
               str(s.get("status", "")).split(" -")[0], s.get("violation")))


def build_brief(n: int, item: str, gates: str, slaps: list) -> str:
    return (
        "ROUND %d of the continuous Rogueworks loop. Project root: C:\\Users\\dbshe\\rogueworks "
        "(bash/MSYS shell; python is: cd /c/Users/dbshe/rogueworks && MSYS_NO_PATHCONV=1 "
        ".venv/Scripts/python.exe -m <module>).\n\n"
        "PRE-FLIGHT GATES (just run by the driver):\n%s\n\n"
        "OPEN SLAPS: %s\n\n"
        "THIS ROUND'S ITEM: %s\n\n"
        "Do it, and be strict with yourself:\n"
        "1. Done means: the item implemented, the gates re-run AFTER your last edit, and their real "
        "output pasted in your reply. `python -m tools.studio.verify_gate` must be green (or the red "
        "must be a genuine art-content gap with a ticket).\n"
        "2. QA it with real evidence: 3+ seeds headless, `--shot` frames, and a numeric check behind "
        "any visual claim. Audit individual frames, never a contact sheet.\n"
        "3. Document it: tick the item in docs/ROADMAP.md, update docs/TICKETS.md, PREPEND a dated "
        "entry to docs/PROGRESS.md, write runs/reports/BUILD-<date>.md. An undocumented round did not "
        "happen - the reviewer will slap you for it.\n"
        "4. Delegate to chip (code), pixel (art), lore (data), lens (verification) when the work is "
        "broad; give each child paths, the frozen contracts in docs/CONTRACTS.md, and an acceptance "
        "command. If a worker's work is substandard, slap it yourself with "
        "`python -m tools.studio.slap --bot <bot> --severity <P0..P3> --violation ... --evidence ... "
        "--rule ... --fix <command> --async`.\n"
        "5. No paid model, no paid image API - ever.\n"
        "6. NEVER delete tracked files to 'clean up'. `runs/STOP` is the operator's stop switch and "
        "is a CONTROL FILE, not debris: if you see it, finish your turn and stop. The no-debris rule "
        "covers scratch artifacts YOU created in runs/ and assets/ - it is never licence to remove "
        "tracked source under game/ or tools/ (a round deleted a working QA tool this way), and never "
        "run a broad `git checkout HEAD --` or `git clean`. The pre-commit gate refuses any commit "
        "that deletes tracked .py under game/ or tools/, or that leaves `main` broken.\n\n"
        "Reply with: the item, the files changed, the exact commands and real output, the QA verdict, "
        "and the next item you would take."
        % (n, gates, "; ".join(slap_line(x) for x in slaps) if slaps else "none open", item)
    )


def review_brief(n: int, item: str, turn: dict) -> str:
    return (
        "Review ROUND %d of the Rogueworks continuous loop (project root "
        "C:\\Users\\dbshe\\rogueworks; bash/MSYS shell; python is: cd /c/Users/dbshe/rogueworks && "
        "MSYS_NO_PATHCONV=1 .venv/Scripts/python.exe -m <module>).\n\n"
        "The builder was given this item: %s\n"
        "Its turn ended: status=%s, %s tool calls, %.0fs, transcript runs/studio/%s\n\n"
        "Review artefacts, not intentions: the diff, docs/PROGRESS.md (a dated entry is REQUIRED), "
        "runs/reports/BUILD-*.md, runs/playtest-*.json, runs/shots/**, assets/atlas/*.json, "
        "docs/TICKETS.md and docs/ROADMAP.md consistency.\n\n"
        "1. Run every gate YOURSELF (python -m tools.studio.verify_gate) and compare with what the "
        "builder claims. Re-run any acceptance command a claim depends on.\n"
        "2. Check the STANDARDS traps: a contract change without docs/CONTRACTS.md; renamed content "
        "ids (breaks saves); placeholder art passed off as final; a report with no commands; test "
        "debris in assets/ or runs/; a visual claim with no numeric check; an undocumented round.\n"
        "3. Slap every violation with the tool, asynchronously: `python -m tools.studio.slap --bot "
        "<bot> --severity <P0..P3> --violation ... --evidence ... --rule ... --fix <command> --async`. "
        "One slap per distinct violation; the driver closes them next cycle against their acceptance "
        "command.\n"
        "4. If it is genuinely clean, say so with the commands you ran - a clean review with real "
        "evidence is the best outcome, but be hard to satisfy.\n"
        "5. Confirm nothing legitimate was destroyed: `git diff --stat HEAD` must show no deletions "
        "under game/ or tools/, `runs/STOP` must still be honoured as a control file (never deleted "
        "as debris), and `python -m tools.studio.pre_commit` must pass. A gate that was never run is "
        "not a pass.\n\n"
        "Reply with: verdict (APPROVE / SLAPPED), what you verified with real output, the slaps "
        "issued, and the single biggest risk to the project right now."
        % (n, item, turn.get("status"), turn.get("tool_calls"), turn.get("seconds"),
           Path(turn.get("log", "")).name)
    )


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m tools.studio.loop")
    ap.add_argument("--once", action="store_true", help="one cycle then exit")
    ap.add_argument("--rounds", type=int, default=0, help="stop after N cycles (0 = forever)")
    ap.add_argument("--cooldown", type=int, default=20, help="seconds between cycles")
    ap.add_argument("--turn-timeout", type=int, default=3600, help="per-turn timeout in seconds")
    ap.add_argument("--no-review", action="store_true", help="builder rounds only (debugging)")
    ap.add_argument("--initial-delay", type=int, default=0,
                    help="seconds to wait before round 1 (lets an in-flight round finish)")
    ap.add_argument("--selftest", action="store_true",
                    help="exercise the driver's own code paths and exit (run this before leaving it "
                         "running: the first version of this file crashed on round 1 because a code "
                         "path was never executed)")
    ap.add_argument("--wait-idle", type=int, default=7200,
                    help="before each round, wait up to this long for in-flight work to finish")
    args = ap.parse_args(argv)

    if args.selftest:
        print("loop selftest: exercising driver code paths")
        gates = gate_summary()
        slaps = open_slaps()
        checks = [
            ("gate_summary", bool(gates.strip())),
            ("open_slaps", isinstance(slaps, list)),
            ("build_brief", "ROUND 1" in build_brief(1, "selftest item", gates, slaps)),
            ("review_brief", "ROUND 1" in review_brief(1, "selftest item",
                                                       {"status": "OK", "tool_calls": 0,
                                                        "seconds": 0.0, "log": "x.log"})),
            ("next_item", bool(next_item().strip())),
            ("in_flight", isinstance(in_flight(), list)),
        ]
        for name, ok in checks:
            print("  %-14s %s" % (name, "PASS" if ok else "FAIL"))
        bad = [n for n, ok in checks if not ok]
        print("loop selftest: %s" % ("PASS" if not bad else "FAIL: %s" % ", ".join(bad)))
        return 0 if not bad else 1

    if not take_lock():
        return 2
    if STOPFILE.exists():
        STOPFILE.unlink()
    log("continuous loop starting (cooldown %ds, turn timeout %ds)" % (args.cooldown,
                                                                      args.turn_timeout))
    record({"event": "loop-start", "pid": os.getpid()})

    if args.initial_delay:
        log("waiting %ds before round 1 so an in-flight round can finish" % args.initial_delay)
        for _ in range(args.initial_delay):
            if STOPFILE.exists():
                log("runs/STOP present before round 1 - exiting")
                return 0
            time.sleep(1)

    n = 0
    try:
        while True:
            n += 1
            if STOPFILE.exists():
                log("runs/STOP present - stopping after %d round(s)" % (n - 1))
                record({"event": "loop-stop", "reason": "stop file", "rounds": n - 1})
                return 0
            if args.rounds and n > args.rounds:
                log("completed %d round(s) - exiting" % (n - 1))
                record({"event": "loop-stop", "reason": "round limit", "rounds": n - 1})
                return 0

            wait_idle(args.wait_idle)
            log("ROUND %d - running pre-flight gates" % n)
            gates = gate_summary()
            item = next_item()
            log("ROUND %d item: %s" % (n, item[:110]))
            record({"event": "round-start", "round": n, "item": item})

            turn = run_turn(BUILDER, build_brief(n, item, gates, open_slaps()),
                            "r%d" % n, args.turn_timeout)
            log("ROUND %d builder: %s (%s tool calls, %.0fs)" % (n, turn["status"],
                                                                 turn["tool_calls"], turn["seconds"]))
            record({"event": "builder-turn", "round": n, **turn})

            if not args.no_review and turn["status"] == "OK":
                rev = run_turn(REVIEWER, review_brief(n, item, turn), "r%d" % n, args.turn_timeout)
                log("ROUND %d review: %s (%s tool calls, %.0fs)" % (n, rev["status"],
                                                                    rev["tool_calls"], rev["seconds"]))
                record({"event": "review-turn", "round": n, **rev})

            closed = close_pending()
            if closed:
                for line in closed:
                    log("  %s" % line)
            record({"event": "round-end", "round": n, "closed_slaps": closed})

            if args.once:
                log("--once: cycle complete")
                return 0
            time.sleep(max(0, args.cooldown))
    except KeyboardInterrupt:
        log("interrupted")
        record({"event": "loop-stop", "reason": "keyboard interrupt", "rounds": n})
        return 0
    finally:
        try:
            if LOCK.is_file():
                LOCK.unlink()
        except Exception:  # noqa: BLE001
            pass


if __name__ == "__main__":
    sys.exit(main())
