"""Pre-flight: the recurring offence classes, checked by a machine instead of remembered by a model.

Every class in this file is one this studio has been slapped for repeatedly, and every one of them is
mechanically decidable - debris either is or is not in the tree, a BUILD report either exists for the
round or it does not. Leaving that to WARDEN's judgement meant the same defect was re-derived from
scratch every round and re-shipped; a bot cannot *learn* a check it has to remember, so the check is
taken away from it and run by the driver. What is left for the bots is the actual work.

    python -m tools.studio.preflight                     # check the whole tree
    python -m tools.studio.preflight --round 14 --item P2.3
    python -m tools.studio.preflight --json              # machine-readable, used by the loop
    python -m tools.studio.preflight --accept '<command>'  # is this a runnable acceptance command?

Exit 0 = clean. Exit 1 = violations, each naming the canonical rule class it belongs to, so the loop
can slap the right class and escalate the right counter.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

from tools.studio import rules

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / "runs" / "studio" / "preflight-state.json"

# shipped tooling - anything else in tools/ costs a reference or an allowlist entry to be legitimate
SHIPPED_TOOLS = {"__init__", "slap", "loop", "verify_gate", "watchdog", "audit_sprites", "bench_local",
                 "learn", "rules", "preflight", "test_learning"}
LEGACY_TOOLS = {"fix_purifier", "gen_missing_items"}   # predate this check; not this round's debris
DEBRIS_NAME = re.compile(r"^(?:_|tmp|scratch|test_|diag_|verify_)|(_test|_tmp|_diag)\.", re.I)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def load_state() -> dict:
    if STATE.is_file():
        try:
            return json.loads(STATE.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            pass
    return {}


def save_state(state: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def v(rule_id: str, violation: str, evidence: str, path: str = "") -> dict:
    meta = rules.rule_of(rule_id)
    return {"rule_id": rule_id, "severity": meta["severity"], "violation": violation,
            "evidence": evidence, "rule": meta["rule"], "path": path}


# --------------------------------------------------------------------------------------- detectors
def check_debris(root: Path) -> list[dict]:
    """R-DEBRIS: fixtures, one-off scripts and scratch files anywhere they are not shipped from."""
    out = []
    for p in sorted(root.glob("*.py")):
        out.append(v("R-DEBRIS", "one-off script left in the project root",
                     "ls %s (%d bytes)" % (p.name, p.stat().st_size), p.name))
    for pat in ("runs/scripts/*", "runs/*.py", "assets/**/_*", "assets/raw/_*",
                "game/**/_*.py", "game/**/*_test.py", "assets/**/*_test.*"):
        for p in sorted(root.glob(pat)):
            # __init__.py matches game/**/_*.py but is shipped, not debris
            if p.is_file() and p.name != "__init__.py":
                out.append(v("R-DEBRIS", "test debris left in the shipped tree",
                             "ls %s" % p.relative_to(root).as_posix(), p.relative_to(root).as_posix()))
    for p in sorted((root / "tools" / "studio").glob("*.py")):
        stem = p.stem
        if stem in SHIPPED_TOOLS or stem in LEGACY_TOOLS:
            continue
        if DEBRIS_NAME.search(stem):
            out.append(v("R-DEBRIS", "transient helper script left in tools/studio/",
                         "ls %s (not a shipped tool)" % p.relative_to(root).as_posix(),
                         p.relative_to(root).as_posix()))
        else:
            out.append(v("R-DEBRIS", "unreferenced script in tools/studio/ - shipped tooling or debris?",
                         "ls %s; not in the shipped set %s" % (p.relative_to(root).as_posix(),
                                                               sorted(SHIPPED_TOOLS)[:4] + ["..."]),
                         p.relative_to(root).as_posix()))
    return out


def check_rounddoc(root: Path, round_n: int, item_id: str, day: str) -> list[dict]:
    """R-ROUNDDOC / R-ROUNDNOP: did this round leave the four artefacts the protocol requires?"""
    out = []
    report = root / "runs" / "reports" / ("BUILD-%s-r%d.md" % (day, round_n))
    if not report.is_file():
        out.append(v("R-ROUNDDOC", "round %d wrote no runs/reports/BUILD-%s-r%d.md"
                     % (round_n, day, round_n),
                     "ls runs/reports/BUILD-%s-r%d.md -> no such file" % (day, round_n),
                     "runs/reports/BUILD-%s-r%d.md" % (day, round_n)))
    progress = root / "docs" / "PROGRESS.md"
    if progress.is_file():
        top = progress.read_text(encoding="utf-8", errors="replace")
        if ("Round %d" % round_n) not in top:
            out.append(v("R-ROUNDDOC", "no dated docs/PROGRESS.md entry for round %d" % round_n,
                         "grep -n 'Round %d' docs/PROGRESS.md -> no matches" % round_n,
                         "docs/PROGRESS.md"))
        elif item_id and item_id not in top.split("\n## ")[-1]:
            out.append(v("R-ROUNDNOP", "the newest PROGRESS entry never names the assigned item %s"
                         % item_id,
                         "grep -n '%s' <newest PROGRESS entry> -> no matches" % item_id,
                         "docs/PROGRESS.md"))
    roadmap = root / "docs" / "ROADMAP.md"
    if roadmap.is_file() and item_id:
        line = next((ln for ln in roadmap.read_text(encoding="utf-8", errors="replace").splitlines()
                     if item_id in ln), "")
        if not line:
            out.append(v("R-ROUNDDOC", "assigned item %s is not in docs/ROADMAP.md" % item_id,
                         "grep -n '%s' docs/ROADMAP.md -> no matches" % item_id, "docs/ROADMAP.md"))
        elif "[ ]" in line:
            out.append(v("R-ROUNDDOC", "%s is implemented but still unchecked in docs/ROADMAP.md" % item_id,
                         "docs/ROADMAP.md: %s" % line.strip()[:120], "docs/ROADMAP.md"))
    tickets = root / "docs" / "TICKETS.md"
    if tickets.is_file() and item_id and item_id not in tickets.read_text(encoding="utf-8", errors="replace"):
        out.append(v("R-ROUNDDOC", "no docs/TICKETS.md ticket for %s" % item_id,
                     "grep -n '%s' docs/TICKETS.md -> no matches" % item_id, "docs/TICKETS.md"))
    return out


def check_reports(root: Path, state: dict) -> list[dict]:
    """R-REPORT: a report that describes a different round, two reports for one round, or a past
    round's report edited/overwritten."""
    out, seen = [], {}
    reports = sorted((root / "runs" / "reports").glob("BUILD-*.md"))
    for p in reports:
        text = p.read_text(encoding="utf-8", errors="replace")[:2000]
        head = "\n".join(text.splitlines()[:8])
        named = re.search(r"-r(\d+)\.md$", p.name)
        titled = re.search(r"Round\s+(\d+)", head, re.I)
        if named and titled and named.group(1) != titled.group(1):
            out.append(v("R-REPORT", "report filename says round %s, its title says round %s"
                         % (named.group(1), titled.group(1)),
                         "%s: %s" % (p.relative_to(root).as_posix(), head.replace("\n", " ")[:110]),
                         p.relative_to(root).as_posix()))
        tag = named.group(1) if named else (titled.group(1) if titled else None)
        if tag:
            if tag in seen:
                out.append(v("R-REPORT", "two BUILD reports both claim round %s" % tag,
                             "%s and %s" % (seen[tag], p.relative_to(root).as_posix()),
                             p.relative_to(root).as_posix()))
            else:
                seen[tag] = p.relative_to(root).as_posix()
        rel = p.relative_to(root).as_posix()
        old = state.get("reports", {}).get(rel)
        if old and old != _sha(p):
            out.append(v("R-REPORT", "a previous round's report was modified after the round closed",
                         "%s changed since the last pre-flight (it is history, not a scratchpad)" % rel, rel))
    return out


def check_contract(root: Path, state: dict) -> list[dict]:
    """R-CONTRACT: data/schema/flags moved but docs/CONTRACTS.md did not move with them."""
    data_files = sorted((root / "game" / "data").glob("*.json")) if (root / "game" / "data").is_dir() else []
    watched = data_files + [root / "tools" / "validate_data.py", root / "docs" / "CONTRACTS.md"]
    now = {p.relative_to(root).as_posix(): _sha(p) for p in watched if p.is_file()}
    was = state.get("contract_hashes", {})
    changed = [k for k, h in now.items() if k in was and was[k] != h]
    if not changed:
        return []
    data_changed = [k for k in changed if not k.endswith("CONTRACTS.md")]
    contract_changed = "docs/CONTRACTS.md" in changed
    if data_changed and not contract_changed:
        return [v("R-CONTRACT", "content/interface changed without touching docs/CONTRACTS.md",
                  "changed since last round: %s - docs/CONTRACTS.md unchanged" % ", ".join(data_changed),
                  "docs/CONTRACTS.md")]
    return []


def check_evidence(root: Path) -> list[dict]:
    """R-EVIDENCE: frame/tick claims in the newest PROGRESS entry that do not survive on disk."""
    progress = root / "docs" / "PROGRESS.md"
    if not progress.is_file():
        return []
    text = progress.read_text(encoding="utf-8", errors="replace")
    entry = ("\n## " + text.split("\n## ", 1)[1]) if "\n## " in text else text
    out = []
    for line in entry.splitlines():
        m = re.search(r"runs/shots/([\w.\-]+)", line)
        if not m:
            continue
        shotdir = root / "runs" / "shots" / m.group(1)
        ticks = re.findall(r"\b(\d{2,3})\b", line)
        if not shotdir.is_dir():
            out.append(v("R-EVIDENCE", "a cited shots directory does not exist",
                         "ls runs/shots/%s -> no such directory (cited line: %s)"
                         % (m.group(1), line.strip()[:90]), "runs/shots/" + m.group(1)))
            continue
        on_disk = {p.name for p in shotdir.glob("frame-*.png")}
        missing = [t for t in ticks
                   if ("frame-%06d.png" % int(t)) not in on_disk and int(t) < 1000]
        if missing and on_disk:
            out.append(v("R-EVIDENCE", "the entry claims frames at ticks %s that are not on disk"
                         % ", ".join(missing[:6]),
                         "runs/shots/%s holds: %s" % (m.group(1),
                                                      ", ".join(sorted(on_disk)[:6]) or "nothing"),
                         "runs/shots/" + m.group(1)))
    return out


def check_gates(root: Path) -> list[dict]:
    py = root / ".venv" / "Scripts" / "python.exe"
    if not py.is_file():
        return []
    p = subprocess.run([str(py), "-m", "tools.studio.verify_gate", "--seeds", "0", "--turns", "300"],
                       cwd=str(root), capture_output=True, text=True, timeout=1800,
                       encoding="utf-8", errors="replace")
    if p.returncode == 0:
        return []
    tail = "\n".join((p.stdout or "").strip().splitlines()[-4:])
    return [v("R-BREAKMAIN", "the pre-flight gates are red", tail[:400], "tools.studio.verify_gate")]


def check_sprites(root: Path) -> list[dict]:
    py = root / ".venv" / "Scripts" / "python.exe"
    if not py.is_file():
        return []
    p = subprocess.run([str(py), "-m", "tools.studio.audit_sprites", "--fallback"],
                       cwd=str(root), capture_output=True, text=True, timeout=600,
                       encoding="utf-8", errors="replace")
    out = (p.stdout or "") + (p.stderr or "")
    if p.returncode == 0 and "unresolved: 0" in out:
        return []
    return [v("R-FALLBACK", "embedded fallback content does not resolve to shipped sprite names",
              "\n".join(out.strip().splitlines()[-3:])[:300], "game/systems/data.py")]


# ---------------------------------------------------------------------------------------------- main
def run(root: Path, round_n: int = 0, item_id: str = "", day: str = "", gates: bool = False,
        sprites: bool = False, update: bool = True) -> list[dict]:
    state = load_state()
    found: list[dict] = []
    found += check_debris(root)
    if round_n:
        found += check_rounddoc(root, round_n, item_id, day or date.today().isoformat())
    found += check_reports(root, state)
    found += check_contract(root, state)
    found += check_evidence(root)
    if gates:
        found += check_gates(root)
    if sprites:
        found += check_sprites(root)

    if update:
        st = load_state()
        st["reports"] = {p.relative_to(root).as_posix(): _sha(p)
                         for p in sorted((root / "runs" / "reports").glob("BUILD-*.md"))}
        st["contract_hashes"] = {p.relative_to(root).as_posix(): _sha(p)
                                 for p in sorted((root / "game" / "data").glob("*.json"))
                                 + [root / "tools" / "validate_data.py", root / "docs" / "CONTRACTS.md"]
                                 if p.is_file()}
        save_state(st)          # snapshot AFTER grading, so the diff is always "since last check"
    return found


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m tools.studio.preflight")
    ap.add_argument("--root", default=str(ROOT))
    ap.add_argument("--round", type=int, default=0)
    ap.add_argument("--item", default="", help="roadmap item id, e.g. P2.3")
    ap.add_argument("--date", default="")
    ap.add_argument("--gates", action="store_true", help="also run tools.studio.verify_gate (slow)")
    ap.add_argument("--sprites", action="store_true", help="also run the fallback sprite audit")
    ap.add_argument("--accept", metavar="CMD", help="check whether a string is a runnable acceptance command")
    ap.add_argument("--json", action="store_true", dest="as_json")
    ap.add_argument("--no-update", action="store_true", help="grade without moving the snapshot forward")
    args = ap.parse_args(argv)

    # Evidence strings may contain non-ASCII glyphs (e.g. the arrow in a BUILD
    # report's title). The Windows console default (cp1252) cannot encode those
    # and would raise UnicodeEncodeError before every violation is printed, so
    # force UTF-8 output for the whole process.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001 - encoding may be fixed on some platforms
        pass

    if args.accept is not None:
        ok = rules.is_runnable_command(args.accept)
        print("ACCEPTANCE COMMAND: %s" % ("run OK" if ok else "NOT RUNNABLE - supply a real command"))
        if not ok:
            print("  given: %s" % args.accept[:200])
            print("  %s" % rules.rule_of("R-AUTOCLOSE")["rule"])
        return 0 if ok else 1

    root = Path(args.root)
    found = run(root, args.round, args.item, args.date, args.gates, args.sprites,
                update=not args.no_update)
    if args.as_json:
        print(json.dumps({"ok": not found, "violations": found}, indent=2))
        return 0 if not found else 1

    print("PRE-FLIGHT  %s" % date.today().isoformat())
    if not found:
        print("  clean - no known repeat-offence class is present")
        print("VERDICT: PASS")
        return 0
    for f in found:
        print("  [%s / %s] %s" % (f["rule_id"], f["severity"], f["violation"]))
        print("      evidence: %s" % f["evidence"])
        print("      rule    : %s" % f["rule"])
    print("VERDICT: FAIL - %d violation(s) in %d class(es): %s"
          % (len(found), len({f["rule_id"] for f in found}),
             ", ".join(sorted({f["rule_id"] for f in found}))))
    return 1


if __name__ == "__main__":
    sys.exit(main())
