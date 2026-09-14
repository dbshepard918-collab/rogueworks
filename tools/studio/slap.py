"""SLAP — the studio's correction mechanism. WARDEN's hand.

A slap is not a complaint, it is a workflow:
  1. it records the violation with evidence in docs/SLAPS.md (public, permanent ledger),
  2. it dispatches a correction order INTO the offending bot's own chat, so that bot takes a turn
     and has to answer for the work,
  3. it escalates on repeat offences: level 1 = warning, level 2 = the rule is written into the
     offending bot's SOUL.md (so it loads in every future session of that bot), level 3 = the bot's
     lane is frozen and forge is told to reassign,
  4. it verifies the claimed fix by re-running the acceptance command and recording the real output.

    python -m tools.studio.slap --bot chip --severity P1 \
        --violation "reported the gates as green without running them" \
        --evidence "runs/reports/BUILD-x.md claims exit 0; runs/playtest-0.json has ok=false" \
        --rule "Never report a gate as passed unless this round's real output is pasted." \
        --fix "python -m game.main --headless --turns 300 --seed 0" [--no-dispatch] [--dry-run]

Exit 0 = slap delivered (and, when --fix was given, the fix verified).
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LEDGER_MD = ROOT / "docs" / "SLAPS.md"
LEDGER_JSON = ROOT / "docs" / "slaps.json"
STANDARDS = ROOT / "docs" / "STANDARDS.md"
PY = r"C:\Users\dbshe\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe"
BOTS = ("forge", "chip", "pixel", "lore", "lens", "warden")

SOUL_FOR = {
    "forge": Path(r"C:\Users\dbshe\AppData\Local\hermes\profiles\forge\SOUL.md"),
    "chip": Path(r"C:\Users\dbshe\AppData\Local\hermes\profiles\chip\SOUL.md"),
    "pixel": Path(r"C:\Users\dbshe\AppData\Local\hermes\profiles\pixel\SOUL.md"),
    "lore": Path(r"C:\Users\dbshe\AppData\Local\hermes\profiles\lore\SOUL.md"),
    "lens": Path(r"C:\Users\dbshe\AppData\Local\hermes\profiles\lens\SOUL.md"),
    "warden": Path(r"C:\Users\dbshe\AppData\Local\hermes\profiles\warden\SOUL.md"),
}


def load_ledger() -> dict:
    if LEDGER_JSON.is_file():
        try:
            return json.loads(LEDGER_JSON.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            pass
    return {"version": 1, "slaps": []}


def slug(rule: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", rule.lower()).strip("-")[:60]


def escalation(ledger: dict, bot: str, rule_key: str) -> int:
    """How severe this bot's *next* offence of the same rule should be (1-3).

    VOID entries are excluded on purpose: a voided slap is one that was established as NOT the
    bot's failure (a malformed acceptance command, a target artefact that no longer exists). If a
    void still counted, its level would push the next genuine first offence straight to level 2 -
    writing the rule into the bot's SOUL.md - for something the bot never did. The same defect
    class as the prose `--fix`: a record that was never evidence must not be used as evidence.
    """
    n = 1
    for s in ledger["slaps"]:
        if s["bot"] == bot and s["rule_key"] == rule_key:
            if str(s.get("status", "")).strip().upper().startswith("VOID"):
                continue
            n = max(n, int(s.get("level", 1)) + 1)
    return min(n, 3)


def append_rule_to_soul(bot: str, rule: str) -> str:
    path = SOUL_FOR.get(bot)
    if not path or not path.is_file():
        return "no SOUL.md found for %s" % bot
    text = path.read_text(encoding="utf-8")
    header = "## Correction rules (written by WARDEN — non-negotiable)"
    if header not in text:
        text += "\n\n%s\n\n" % header
    if rule in text:
        return "rule already in %s's SOUL.md" % bot
    text += "- **%s**\n" % rule
    path.write_text(text, encoding="utf-8")
    return "rule appended to %s's SOUL.md (%d bytes)" % (bot, len(text))


def dispatch(bot: str, order: str) -> tuple[int, str]:
    cmd = [PY, "-m", "hermes_cli.main", "-p", bot, "chat", "-q", order]
    env = dict(__import__("os").environ, MSYS_NO_PATHCONV="1")
    try:
        p = subprocess.run(cmd, cwd=str(ROOT), env=env, capture_output=True, text=True,
                           timeout=1800, encoding="utf-8", errors="replace")
        out = (p.stdout or "") + (p.stderr or "")
        m = re.search(r"Messages:\s+(\d+)\s+\((\d+) user, (\d+) tool calls\)", out)
        tail = "\n".join(out.strip().splitlines()[-6:])
        return p.returncode, ("%s | %s" % (m.group(0), tail) if m else tail)[:1200]
    except subprocess.TimeoutExpired:
        return 124, "TIMEOUT: the bot did not answer the correction order within 30 minutes"


def dispatch_async(bot: str, order: str) -> tuple[int, str]:
    """Fire the correction order and return immediately.

    A reviewer that sweeps every 2 hours must not sit blocked for 8 minutes per offender (the first
    real slap took chip 7m33s). Async leaves the entry PENDING with a receipt path; the next sweep
    closes it with --close, which is also where the fix gets verified.
    """
    env = dict(__import__("os").environ, MSYS_NO_PATHCONV="1")
    receipts = ROOT / "runs" / "slaps"
    receipts.mkdir(parents=True, exist_ok=True)
    log = receipts / ("slap-%s-%s.log" % (bot, time.strftime("%Y%m%d-%H%M%S")))
    cmd = [PY, "-m", "hermes_cli.main", "-p", bot, "chat", "-q", order]
    with log.open("wb") as fh:
        proc = subprocess.Popen(cmd, cwd=str(ROOT), env=env, stdout=fh, stderr=subprocess.STDOUT)
    return proc.pid, log.relative_to(ROOT).as_posix()


SHELL_TOKENS = {
    "cd", "echo", "python", "python3", "py", "git", "ls", "rm", "cat", "grep", "sed", "awk",
    "true", "false", "test", "set", "export", "for", "if", "while", "mkdir", "cp", "mv", "touch",
    "find", "xargs", "head", "tail", "wc", "sort", "uniq", "tr", "sleep", "bash", "sh", "pytest",
    "make", "npm", "node", "curl", "diff", "which", "env", "timeout",
}


def looks_like_command(text: str) -> bool:
    """True if *text* could actually be executed, False if it is prose describing a fix.

    Measured failure this guards against: two slaps were issued with a `--fix` value written as an
    instruction ("Patch docs/PROGRESS.md lines 155-158: change ... to ...").  `verify_fix` runs that
    string through bash, so it exited 1 ("No such file or directory") and 2 (unbalanced quote) and
    the entries could never close - while the escalation ladder went on treating an innocent bot as
    unfixed, on course to write a rule into its SOUL.md and then freeze its lane.  A malformed
    acceptance command must never be evidence against a bot.
    """
    s = (text or "").strip()
    if not s:
        return False
    toks = s.split()
    i = 0
    # step over leading env assignments (VAR=value), which are a normal command prefix
    while i < len(toks) and "=" in toks[i] and "/" not in toks[i].split("=", 1)[0]:
        i += 1
    if i >= len(toks):
        return False
    first = toks[i]
    if first in SHELL_TOKENS:           # case-sensitive: "Set ..." is prose, "set ..." is not
        return True
    if "/" in first or "\\" in first:
        return True
    if first.lower().endswith((".exe", ".py", ".bat", ".sh", ".cmd")):
        return True
    if first.startswith((".", '"', "'")):
        return True
    return False


def close_slap(ledger: dict, n: int) -> int:
    """Re-run a pending slap's acceptance command and close it, or keep it open."""
    entry = next((s for s in ledger["slaps"] if s.get("n") == n), None)
    if entry is None:
        print("no slap #%d in the ledger" % n)
        return 2
    print("closing SLAP #%d (%s, level %d)" % (n, entry["bot"], entry.get("level", 1)))
    if not entry.get("fix_command"):
        print("  no acceptance command on this entry - nothing to verify; closing as ACKNOWLEDGED")
        entry["status"] = "ACKNOWLEDGED (no acceptance command)"
        return 0
    # A prose "command" is not a failed fix - it is a broken instrument. Never escalate on it.
    if not looks_like_command(entry["fix_command"]):
        entry["status"] = ("MALFORMED ACCEPTANCE COMMAND - not a runnable command, so NOT verifiable "
                           "and NOT a bot failure; reissue with --close N --reissue-fix '<command>'")
        entry["fix_exit"] = None
        entry["fix_output"] = "acceptance command was prose: %r" % entry["fix_command"][:120]
        print("  NOT VERIFIABLE: the acceptance command is prose, not a command.")
        print("    %r" % entry["fix_command"][:140])
        print("  no escalation applied - fix the instrument, not the bot:")
        print("    python -m tools.studio.slap --close %d --reissue-fix '<real command>'" % n)
        return 1
    rc, out = verify_fix(entry["fix_command"])
    entry["fix_exit"] = rc
    entry["fix_output"] = out[:800]
    entry["status"] = "CLEAN - fix verified" if rc == 0 else "STILL OPEN - fix did not verify"
    print("  %s -> exit=%s :: %s" % (entry["fix_command"], rc, out[:200]))
    print("  %s" % entry["status"])
    if rc != 0:
        already_open = str(entry.get("status", "")).startswith("STILL OPEN")
        if not already_open:
            entry["level"] = min(3, int(entry.get("level", 1)) + 1)
            print("  escalated to level %d (the fix did not verify)" % entry["level"])
        else:
            print("  still open; level stays %d (no second escalation for the same open defect)"
                  % int(entry.get("level", 1)))
        # level 2 is where the rule becomes permanent: it goes into the offender's SOUL.md, which
        # loads in every session that bot will ever run. That is the part that stops repeats.
        if int(entry.get("level", 1)) >= 2 and not entry.get("soul_note"):
            entry["soul_note"] = append_rule_to_soul(entry["bot"], entry["rule"])
            print("  %s" % entry["soul_note"])
    return 0 if rc == 0 else 1


def verify_fix(command: str) -> tuple[int, str]:
    """Run the acceptance command the way the project documents it: through bash.

    Windows is the trap here: subprocess(shell=True) uses cmd.exe, where a POSIX-style prefix like
    `MSYS_NO_PATHCONV=1 .venv/Scripts/python.exe ...` fails with "not recognized as an internal or
    external command" - which reads as a failed fix and escalates a bot that actually fixed it.
    """
    env = dict(__import__("os").environ, MSYS_NO_PATHCONV="1")
    bash = shutil.which("bash") or r"C:\Users\dbshe\AppData\Local\hermes\git\bin\bash.exe"
    argv = ([bash, "-lc", command] if bash and Path(bash).exists()
            else [command])
    try:
        p = subprocess.run(argv, cwd=str(ROOT), env=env, capture_output=True, text=True,
                           timeout=1800, encoding="utf-8", errors="replace")
        out = ((p.stdout or "") + (p.stderr or "")).strip()
        return p.returncode, "\n".join(out.splitlines()[-6:])[:800]
    except subprocess.TimeoutExpired:
        return 124, "TIMEOUT while verifying the fix"
    except FileNotFoundError as exc:
        return 127, "could not run the acceptance command: %s" % exc


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m tools.studio.slap")
    ap.add_argument("--bot", choices=BOTS)
    ap.add_argument("--violation", help="what the bot did wrong, one sentence")
    ap.add_argument("--evidence", help="the artefact/output that proves it")
    ap.add_argument("--rule", help="the rule that prevents the whole class of mistake")
    ap.add_argument("--severity", default="P2", choices=["P0", "P1", "P2", "P3"])
    ap.add_argument("--fix", default=None, help="acceptance command that must now pass")
    ap.add_argument("--no-dispatch", action="store_true", help="record only, do not run the bot")
    ap.add_argument("--async", dest="async_mode", action="store_true",
                    help="fire the correction order and return immediately; the entry stays PENDING "
                         "until a later review closes it with --close N")
    ap.add_argument("--close", type=int, default=None, metavar="N",
                    help="close an existing slap: re-run its acceptance command, mark it CLEAN or "
                         "escalate it. Use with no other arguments.")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--reissue-fix", default=None, metavar="CMD",
                    help="with --close N: replace a malformed acceptance command with a real one, "
                         "then verify it")
    ap.add_argument("--void", type=int, default=None, metavar="N",
                    help="void a slap that cannot be verified (target artefact gone, malformed "
                         "command, or superseded). Records the reason and never escalates.")
    ap.add_argument("--reason", default=None, help="why a slap is being voided")
    args = ap.parse_args(argv)

    ledger = load_ledger()

    if args.void is not None:
        entry = next((s for s in ledger["slaps"] if s.get("n") == args.void), None)
        if entry is None:
            print("no slap #%d in the ledger" % args.void)
            return 2
        if not args.reason:
            ap.error("--void requires --reason (a void without a reason is just a deleted record)")
        entry["status"] = "VOID - %s" % args.reason
        entry["voided"] = time.strftime("%Y-%m-%d %H:%M")
        LEDGER_JSON.write_text(json.dumps(ledger, indent=2), encoding="utf-8")
        with LEDGER_MD.open("a", encoding="utf-8") as fh:
            fh.write("\n> **VOID %s on SLAP #%d:** %s - no escalation applied\n"
                     % (time.strftime("%Y-%m-%d %H:%M"), args.void, args.reason))
        print("SLAP #%d voided (no escalation): %s" % (args.void, args.reason))
        return 0

    if args.close is not None:
        if args.reissue_fix:
            entry = next((s for s in ledger["slaps"] if s.get("n") == args.close), None)
            if entry is None:
                print("no slap #%d in the ledger" % args.close)
                return 2
            if not looks_like_command(args.reissue_fix):
                ap.error("--reissue-fix must be a runnable command, not prose: %r"
                         % args.reissue_fix)
            entry["fix_command"] = args.reissue_fix
            entry["reissued"] = time.strftime("%Y-%m-%d %H:%M")
            print("reissued acceptance command for SLAP #%d: %s" % (args.close, args.reissue_fix))
        rc = close_slap(ledger, args.close)
        LEDGER_JSON.write_text(json.dumps(ledger, indent=2), encoding="utf-8")
        with LEDGER_MD.open("a", encoding="utf-8") as fh:
            e = next((s for s in ledger["slaps"] if s.get("n") == args.close), {})
            fh.write("\n> **Close pass %s on SLAP #%d:** %s (exit %s) — %s\n"
                     % (time.strftime("%Y-%m-%d %H:%M"), args.close, e.get("status"),
                        e.get("fix_exit"), (e.get("fix_output") or "")[:200]))
        return rc
    missing = [n for n, v in (("--bot", args.bot), ("--violation", args.violation),
                              ("--evidence", args.evidence), ("--rule", args.rule)) if not v]
    if missing:
        ap.error("missing required argument(s) for a new slap: %s (or use --close N)"
                 % ", ".join(missing))

    rule_key = slug(args.rule)
    level = escalation(ledger, args.bot, rule_key)
    stamp = time.strftime("%Y-%m-%d %H:%M")

    if level == 1:
        action = "WARNING - fix it and reply with evidence"
    elif level == 2:
        action = "ESCALATED - the rule is now written into %s's SOUL.md (loads every session)" % args.bot
    else:
        action = ("FROZEN - repeat offence; %s's lane is frozen until the fix verifies, "
                  "forge must reassign the work" % args.bot)

    order = (
        "*** SLAP #%d from WARDEN (severity %s, escalation level %d) ***\n"
        "You are %s. Your work was reviewed and rejected.\n\n"
        "VIOLATION: %s\nEVIDENCE: %s\nLEVEL: %s\n\n"
        "THE RULE YOU BROKE: %s\n\n"
        "Do all of this now, in this turn, and do not argue:\n"
        "1. Fix the defect for real.\n"
        "2. Run the acceptance command%s and paste the ACTUAL output (not a summary of what it "
        "would print).\n"
        "3. If you cannot fix it, say exactly what blocks you and what you tried.\n"
        "4. Never repeat this mistake: the rule above is now part of how this studio works.\n"
        "Reply with: FIXED / BLOCKED, the command you ran, and its real output."
        % (len(ledger["slaps"]) + 1, args.severity, level, args.bot, args.violation,
           args.evidence, action, args.rule, ("\n   " + args.fix) if args.fix else "")
    )

    print("SLAP -> %s  [%s / level %d]" % (args.bot, args.severity, level))
    if args.fix and not looks_like_command(args.fix):
        print("  [WARNING] --fix does not look like a runnable command:")
        print("            %r" % args.fix[:120])
        print("            The verifier runs it through bash, so this slap will be recorded as")
        print("            UNVERIFIABLE and can never close. Pass a real command instead, e.g.")
        print("            --fix \"python -m tools.selftest\"")
    print("  violation: %s" % args.violation)
    print("  evidence : %s" % args.evidence)
    print("  rule     : %s" % args.rule)
    print("  action   : %s" % action)
    if args.dry_run:
        print("  (dry run: nothing written, nothing dispatched)")
        return 0

    soul_note = ""
    if level >= 2:
        soul_note = append_rule_to_soul(args.bot, args.rule)
        print("  %s" % soul_note)

    if not STANDARDS.is_file():
        STANDARDS.write_text("# Standards\n", encoding="utf-8")
    with STANDARDS.open("a", encoding="utf-8") as fh:
        fh.write("\n- **%s** (%s, added %s after a %s) — %s\n"
                 % (args.rule, args.severity, stamp, args.bot, args.evidence))

    rc, reply = (0, "(not dispatched)")
    if not args.no_dispatch and args.async_mode:
        pid, log = dispatch_async(args.bot, order)
        rc, reply = 0, "PENDING - dispatched as pid %s, receipt %s" % (pid, log)
        print("  dispatched ASYNC to %s (pid %s) - receipt: %s" % (args.bot, pid, log))
        print("  this entry stays PENDING; close it with: python -m tools.studio.slap --close %d"
              % (len(ledger["slaps"]) + 1))
    elif not args.no_dispatch:
        print("  dispatching the correction order into %s's chat ..." % args.bot)
        rc, reply = dispatch(args.bot, order)
        print("  %s answered (rc=%d): %s" % (args.bot, rc, reply[:400]))

    fix_rc, fix_out = (None, "")
    if args.fix and args.async_mode and not args.no_dispatch:
        # verifying now would grade a fix the bot has not had its turn to make yet - the whole point
        # of async is that the NEXT review does the grading via --close N.
        print("  (async: verification deferred - close with --close %d after %s's turn lands)"
              % (len(ledger["slaps"]) + 1, args.bot))
    elif args.fix:
        print("  verifying the fix: %s" % args.fix)
        fix_rc, fix_out = verify_fix(args.fix)
        print("  fix exit=%s :: %s" % (fix_rc, fix_out[:300]))

    entry = {"n": len(ledger["slaps"]) + 1, "at": stamp, "bot": args.bot, "severity": args.severity,
             "violation": args.violation, "evidence": args.evidence, "rule": args.rule,
             "rule_key": rule_key, "level": level, "action": action, "soul_note": soul_note,
             "reply_rc": rc, "reply": reply, "fix_command": args.fix, "fix_exit": fix_rc,
             "fix_output": fix_out,
             "status": ("PENDING - awaiting the bot's turn" if args.async_mode and not args.no_dispatch
                        else ("CLEAN - fix verified" if (args.fix and fix_rc == 0)
                              else ("STILL OPEN" if args.fix else "RECORDED (no acceptance command)")))}
    ledger["slaps"].append(entry)
    LEDGER_JSON.write_text(json.dumps(ledger, indent=2), encoding="utf-8")

    if not LEDGER_MD.is_file():
        LEDGER_MD.write_text("# SLAPS — the correction ledger\n\n"
                             "Every entry is a review that failed and the fix that followed. "
                             "Kept forever: repeat offences escalate.\n", encoding="utf-8")
    with LEDGER_MD.open("a", encoding="utf-8") as fh:
        fh.write("\n## SLAP #%d — %s — %s (%s, level %d)\n\n"
                 "- **Violation:** %s\n- **Evidence:** %s\n- **Rule:** %s\n- **Action:** %s\n"
                 "- **Bot's reply (rc=%d):** %s\n- **Fix verification:** exit=%s :: %s\n"
                 % (entry["n"], args.bot, stamp, args.severity, level, args.violation, args.evidence,
                    args.rule, action, rc, reply[:600], fix_rc,
                    (fix_out[:400] or "(no acceptance command given)")))

    print("  logged to docs/SLAPS.md (%d total)" % len(ledger["slaps"]))
    if args.async_mode and not args.no_dispatch:
        print("VERDICT: slap delivered ASYNC - entry %d is PENDING until closed" % entry["n"])
        return 0
    if args.fix and fix_rc not in (0, None):
        print("VERDICT: fix NOT verified (exit %s) - the slap stands, escalate next review" % fix_rc)
        return 1
    print("VERDICT: slap delivered%s" % (", fix verified" if args.fix else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
