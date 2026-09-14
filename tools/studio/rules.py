"""Canonical rule classes - the studio's memory of *what kind* of mistake was made.

The bug this fixes: `slap.py` derived its escalation key from a slug of the rule's free text
(`slug(args.rule)`). WARDEN never writes the same sentence twice, so `Never leave test fixtures in
assets/, runs/ or game/` and `Never leave test fixtures in runs/ or assets/` were two different keys,
each starting at level 1. The escalation ladder - warning, SOUL.md, freeze - therefore never held:
forge collected 8 debris slaps across 4 keys, reached level 3 twice, and was back at level 1 the next
time it left a script in the project root.

A rule is a *class of defect*, not a sentence. This module is the single registry of those classes,
a text classifier that maps any free-text violation onto one of them, and the ledger statistics that
turn `docs/slaps.json` into "how many times has THIS bot been caught doing THIS kind of thing".

Escalation is computed from the class history, so it is monotonic: rewording cannot reset it.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LEDGER_JSON = ROOT / "docs" / "slaps.json"

# --------------------------------------------------------------------------------------------------
# The registry. One entry per class of defect this studio has actually been bitten by.
#   signals   - regexes that identify the class from violation + evidence text (scored, best wins)
#   rule      - the canonical statement written into SOUL.md / STANDARDS.md / the brief
#   enforced  - the mechanical check that now catches it before a human (or WARDEN) has to.
#               'preflight:<detector>' means tools.studio.preflight fails the round on its own.
#               'review' means it still needs judgement and stays a WARDEN call.
# --------------------------------------------------------------------------------------------------
RULES: list[dict] = [
    {
        "id": "R-DEBRIS",
        "title": "test debris left in the shipped tree",
        "severity": "P2",
        "rule": ("Never leave test fixtures, one-off scripts or scratch files in game/, runs/, assets/, "
                 "tools/ or the project root - write them under $LOCALAPPDATA/Temp and delete them, or "
                 "make the tool clean up after itself."),
        "check": ("before you end the turn: no new .py in the project root, nothing new in runs/scripts/, "
                  "no _*.py / *test* / *verify*_ / *diag* file anywhere in game/ or assets/"),
        "enforced": "preflight:debris",
        "signals": [
            (r"test\s+(fixture|debris|artifact)", 3), (r"\bdebris\b", 3),
            (r"never leave test fixtures", 4),
            (r"left in (assets|runs|game|project root|tools)", 3),
            (r"stray \.py|_pipeline_test|_local_test|verify_r\d|diag_procgen|verify_biomes", 3),
            (r"temp cop(y|ies)|AppData\\Local[/\\]Temp", 2),
            (r"transient cleanup utility|scratch file", 2),
            (r"leav(e|ing|es) .*(artifact|artefact|fixture|script|debris)", 2),
        ],
    },
    {
        "id": "R-ROUNDDOC",
        "title": "round shipped without its paper trail",
        "severity": "P2",
        "rule": ("Round protocol (docs/ROADMAP.md item 4): every round writes runs/reports/BUILD-<date>-rN.md, "
                 "PREPENDS a dated entry to docs/PROGRESS.md, and ticks the item in docs/ROADMAP.md and "
                 "docs/TICKETS.md. An undocumented round did not happen."),
        "check": ("run `python -m tools.studio.preflight --round N --item <ID>` and paste its output - the "
                  "report, the PROGRESS entry, the tick and the ticket all have to exist"),
        "enforced": "preflight:rounddoc",
        "signals": [
            (r"undocumented", 4), (r"no runs/reports/BUILD", 4),
            (r"no .*PROGRESS\.md entry|no Round \d+ entry", 4),
            (r"round protocol", 3), (r"still unchecked|unchecked \[ \]", 3),
            (r"no .*\bticket\b", 2), (r"prepend a dated entry", 2),
            (r"did not happen", 2), (r"paper trail", 3),
        ],
    },
    {
        "id": "R-REPORT",
        "title": "build/QA report wrong, misnamed, overwritten or deleted",
        "severity": "P2",
        "rule": ("One report per round, named BUILD-<date>-rN.md for the round that produced it, describing "
                 "that round's work only. Never overwrite or delete a prior round's report, and never write "
                 "then delete an artefact inside the same round."),
        "check": ("report filename round matches its title, no two reports claim the same round, and any "
                  "QA report you mention still exists on disk when the round ends"),
        "enforced": "preflight:report",
        "signals": [
            (r"describes (a different|round \d)", 4), (r"overwrote|overwrit", 4),
            (r"mislabel", 4), (r"wrote then deleted|written then deleted", 4),
            (r"delete(d)? mid-turn", 3), (r"report .*(gone|absent|not in runs/reports)", 3),
            (r"QA report .*was", 2), (r"named '?r\d", 2),
        ],
    },
    {
        "id": "R-BREAKMAIN",
        "title": "main left broken (Law 2)",
        "severity": "P0",
        "rule": ("Law 2 - never break main. `python -m game.main --headless --turns 300 --seed N` must exit 0 "
                 "with invariants.violations == [] before AND after your change. After any edit, re-run it; "
                 "if you inserted a block check the indentation below it, and check that RNG methods and "
                 "container types (rooms are dicts, not objects) actually exist before you call them."),
        "check": "python -m tools.studio.verify_gate --seeds 0 --turns 300 (paste the real verdict)",
        "enforced": "preflight:gates",
        "signals": [
            (r"never break main|law 2", 4), (r"\bNameError\b|\bAttributeError\b|\bIndentationError\b", 4),
            (r"crashes? (with|on)|exit 1 .*Traceback|all (three|four) seeds crash", 4),
            (r"shipped broken code", 4), (r"broken .*(main|code)", 2),
            (r"import.*(crashes|fails)|crashes on import", 3),
        ],
    },
    {
        "id": "R-EVIDENCE",
        "title": "claim not backed by evidence that survives on disk",
        "severity": "P2",
        "rule": ("No claim without a command, and no visual claim without a numeric one. The evidence you "
                 "cite must be what a reviewer finds on disk, at the path and tick you named - pixel counts, "
                 "alpha coverage, distinct colours, frame files. A VLM reading a stale frame is not evidence."),
        "check": ("every frame/tick/pixel number you state resolves to a real file at that path; measure "
                  "the number yourself, never quote a screenshot's appearance"),
        "enforced": "preflight:evidence",
        "signals": [
            (r"unsupported by numeric|numeric evidence|numeric audit|numeric check", 4),
            (r"claimed .*(frames|N frames)|evidence must match", 4),
            (r"stale frame|pixel audit|green-text|pixel count", 3),
            (r"states? .*tick|tick numbers must be", 3),
            (r"visual claim|VLM (analysis|reading)", 3),
            (r"claims? .*but", 1),
        ],
    },
    {
        "id": "R-CONTRACT",
        "title": "interface changed without the contract (Law 3)",
        "severity": "P1",
        "rule": ("Law 3 - the contracts are frozen. Any change to a data field, path, CLI flag, save format or "
                 "content file updates docs/CONTRACTS.md in the same change, and the report says so."),
        "check": ("if game/data/*.json, a save format, a CLI flag or a schema changed this round, "
                  "docs/CONTRACTS.md changed in the same round"),
        "enforced": "preflight:contract",
        "signals": [
            (r"law 3|contracts are frozen", 4), (r"CONTRACTS\.md", 4),
            (r"contract .*(change|violation|drift|updated)", 3),
            (r"save format", 3), (r"schema", 2), (r"not in CONTRACTS|absenta|missing .*field", 3),
        ],
    },
    {
        "id": "R-ROUNDNOP",
        "title": "assigned item not actually done (a no-round)",
        "severity": "P2",
        "rule": ("Each round implements the item it was assigned, or says BLOCKED with a concrete reason in "
                 "the report. Clearing earlier technical debt instead, and calling that the round, is a "
                 "no-round - the gates being green does not mean the item was done."),
        "check": "the report names the assigned item and the files that implement it",
        "enforced": "preflight:rounddoc",
        "signals": [
            (r"not implemented", 4), (r"no-round|n(o)? meaningful,? playable improvement", 4),
            (r"assigned item", 3), (r"zero game logic files", 3),
            (r"technical debt from a prior round", 2),
        ],
    },
    {
        "id": "R-AUTOMATION",
        "title": "shipped or left running automation that was never executed",
        "severity": "P1",
        "rule": ("Any new driver, loop or automation is executed end-to-end - or its code paths are exercised "
                 "via --selftest - BEFORE it is left running. Leaving something running is a claim that it "
                 "works; make that claim true first."),
        "check": "python -m tools.studio.<driver> --selftest, then one real --once cycle, with output pasted",
        "enforced": "review",
        "signals": [
            (r"never executed|never ran|no code path", 4), (r"left it running", 4),
            (r"selftest", 3), (r"driver|automation", 2), (r"loop crashed|crashed on round", 3),
        ],
    },
    {
        "id": "R-CONFIG",
        "title": "unauthorized model or unpinned provider in automation",
        "severity": "P2",
        "rule": ("Cron jobs and drivers inherit the profile's authorized model (model=null) or pin an "
                 "explicitly authorized free/local one. Never snapshot a model that is not on the authorized "
                 "list - a studio must not be stoppable by a model falling outside it."),
        "check": "every scheduled job and profile pin resolves to a model on the free/local list in docs/MODELS.md",
        "enforced": "review",
        "signals": [
            (r"model_snapshot|cron job", 4), (r"not in the authorized|unauthorized|free-tier list", 4),
            (r"invalid tool call|runtimeerror.*model", 2),
        ],
    },
    {
        "id": "R-DOCS",
        "title": "docs that misdescribe what happened",
        "severity": "P3",
        "rule": ("Docs record what happened, not what was planned. A progress entry must not contradict "
                 "itself or a sibling entry; if two rounds share a number, say which one you mean."),
        "check": "re-read your PROGRESS entry against the diff before you submit it",
        "enforced": "review",
        "signals": [
            (r"contradict", 4), (r"self-contradicting", 4), (r"docs? .*describe a plan", 3),
            (r"misleads the reviewer", 2), (r"ambiguous", 2),
        ],
    },
    {
        "id": "R-FALLBACK",
        "title": "second dialect of content ids",
        "severity": "P3",
        "rule": ("Embedded fallback content uses the SAME sprite/item ids as shipped content "
                 "(docs/CONTENT.md conventions). Never a second dialect - a checkout with no game/data/ "
                 "must still resolve every name."),
        "check": "python -m tools.studio.audit_sprites --fallback (unresolved must be 0)",
        "enforced": "preflight:sprites",
        "signals": [
            (r"fallback content|_FALLBACK", 4), (r"second dialect", 4),
            (r"sprite naming", 3), (r"unresolved names?", 2),
        ],
    },
    {
        "id": "R-AUTOCLOSE",
        "title": "reviewer closed a defect it never verified",
        "severity": "P2",
        "rule": ("An acceptance command must be a command: one line, runnable, no prose and no unbalanced "
                 "quotes. A slap whose acceptance command cannot run is a reviewer defect - it is recorded "
                 "as UNVERIFIABLE and re-issued with a real command, never counted against the offender."),
        "check": "python -m tools.studio.preflight --accept '<command>' before you pass --fix",
        "enforced": "preflight:accept",
        "signals": [
            (r"acceptance command .*(not|no (acceptance|runnable))", 4),
            (r"no acceptance command", 3), (r"unable to verify|verification (was )?broken", 3),
            (r"unexpected EOF|syntax error near unexpected token", 3),
        ],
    },
]

BY_ID = {r["id"]: r for r in RULES}
FALLBACK_ID = "R-OTHER"

_OTHER = {
    "id": FALLBACK_ID, "title": "unclassified", "severity": "P2",
    "rule": "Fix the defect and reply with the real output of the acceptance command.",
    "check": "", "enforced": "review", "signals": [],
}


def rule_of(rule_id: str) -> dict:
    return BY_ID.get(rule_id, _OTHER)


def classify(violation: str, evidence: str = "") -> str:
    """Map a free-text violation onto a canonical rule id. Highest score wins; ties go to the first
    rule in the registry, which is ordered by how often this studio has actually been bitten."""
    text = ("%s %s" % (violation or "", evidence or "")).lower()
    best, best_score = FALLBACK_ID, 0
    for entry in RULES:
        score = sum(w for pat, w in entry["signals"] if re.search(pat, text))
        if score > best_score:
            best, best_score = entry["id"], score
    return best


def escalation_level(ledger: dict, bot: str, rule_id: str, already_open: bool = False) -> int:
    """Level = 1 + prior offences of this CLASS by this bot - monotonic across rewordings.

    `already_open` keeps an unfixed defect from double-escalating while its fix is still pending.
    """
    prior = [s for s in ledger.get("slaps", [])
             if s.get("bot") == bot and s.get("rule_id", classify(s.get("violation", ""),
                                                                  s.get("evidence", ""))) == rule_id]
    n = len(prior)
    if already_open:
        n = max(0, n - 1)
    return min(3, 1 + n)


def is_runnable_command(cmd: str | None) -> bool:
    """Is this string actually a shell command, or is it WARDEN's prose description of one?

    The ledger is full of `--fix "Capture a fresh shrine-activation frame AFTER the statuses.py fix:
    run a scripted path that reaches a shri..."`, which bash rejects with a syntax error. That reads as
    a failed fix, escalates an innocent bot, and buries the signal under dozens of identical
    "STILL OPEN" lines. Prose is not a command.
    """
    if not cmd or not cmd.strip():
        return False
    cmd = cmd.strip()
    if "\n" in cmd or "\r" in cmd:
        return False
    if cmd.count("'") % 2 or cmd.count('"') % 2:
        return False
    if len(cmd) > 500:
        return False
    # a description, not a command: prose verbs and sentence punctuation at the start
    if re.match(r"^(capture|write|implement|remove|add|check|ensure|verify|run a|make sure|then )\b",
                cmd, re.I) and not re.match(r"^(rm|cp|mv|test|grep|git|python|msys_no_pathconv|cd)\b",
                                            cmd, re.I):
        return False
    if cmd.endswith((".", ":")) and " " in cmd.split()[-1]:
        return False
    return True


def stats(ledger: dict) -> dict:
    """Per bot, per class: how many times, current level, last offence, is it still open.

    This is the number that was missing - `status: CLEAN` on 29 of 33 entries says the artefact got
    fixed, while `count` per class says whether the *bot* actually stopped.
    """
    out: dict[str, dict[str, dict]] = {}
    for s in ledger.get("slaps", []):
        bot = s.get("bot", "?")
        rid = s.get("rule_id") or classify(s.get("violation", ""), s.get("evidence", ""))
        row = out.setdefault(bot, {}).setdefault(rid, {
            "rule_id": rid, "count": 0, "level": 1, "spans": [], "open": 0, "last": "",
        })
        row["count"] += 1
        row["spans"].append(s.get("n"))
        row["last"] = s.get("at", row["last"])
        row["level"] = min(3, row["count"])
        if str(s.get("status", "")).upper().startswith(("PENDING", "STILL OPEN", "UNVERIFIABLE")):
            row["open"] += 1
    return out


def summarise(ledger: dict) -> str:
    st = stats(ledger)
    lines = []
    for bot in sorted(st):
        rows = sorted(st[bot].values(), key=lambda r: (-r["count"], r["rule_id"]))
        lines.append("%s: %d slap(s) over %d class(es)" % (bot, sum(r["count"] for r in rows), len(rows)))
        for r in rows:
            lines.append("  %-12s x%-2d level %d  %s  last %s%s"
                         % (r["rule_id"], r["count"], r["level"], rule_of(r["rule_id"])["title"],
                            r["last"], "  [%d open]" % r["open"] if r["open"] else ""))
    return "\n".join(lines) or "(ledger empty)"


def annotate(ledger: dict) -> int:
    """Write `rule_id` back onto every ledger entry. Idempotent; never changes a past verdict."""
    changed = 0
    for s in ledger.get("slaps", []):
        rid = classify(s.get("violation", ""), s.get("evidence", ""))
        if s.get("rule_id") != rid:
            s["rule_id"] = rid
            changed += 1
        s["class_count"] = sum(1 for o in ledger["slaps"]
                               if o.get("bot") == s.get("bot")
                               and (o.get("rule_id") or classify(o.get("violation", ""), "")) == rid
                               and o.get("n", 0) <= s.get("n", 0))
    return changed


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="python -m tools.studio.rules")
    ap.add_argument("--audit", action="store_true", help="print per-bot class counts from the ledger")
    ap.add_argument("--annotate", action="store_true",
                    help="write rule_id + class_count onto every ledger entry (does not change verdicts)")
    ap.add_argument("--classify", metavar="TEXT", help="show which class a violation maps to (debug)")
    args = ap.parse_args(argv)

    ledger = json.loads(LEDGER_JSON.read_text(encoding="utf-8")) if LEDGER_JSON.is_file() else {"slaps": []}
    if args.classify:
        rid = classify(args.classify)
        print("%s -> %s (%s)" % (args.classify[:60], rid, rule_of(rid)["title"]))
        return 0
    if args.annotate:
        n = annotate(ledger)
        LEDGER_JSON.write_text(json.dumps(ledger, indent=2), encoding="utf-8")
        print("annotated %d ledger entr(ies) with their rule class" % n)
    print(summarise(ledger))
    return 0


if __name__ == "__main__":
    sys.exit(main())
