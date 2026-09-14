"""Tests for the learning layer: escalation must hold, verification must not lie, SOUL must stay sane.

The failures these pin down, all observed in docs/SLAPS.md:
  * forge took 8 debris slaps across 4 different rule sentences and was escalated to level 3 twice -
    each wording reset the counter (escalation was keyed on a slug of the rule's free text).
  * WARDEN passed prose as `--fix`, bash choked, and ~40 "STILL OPEN" close passes were logged for
    defects that may well have been fixed - noise that both escalates innocents and hides real ones.
  * level 2 appended the rule sentence to SOUL.md, so ten near-duplicate sentences accumulated and the
    one number that mattered (you have done this N times) was nowhere.

    python -m tools.studio.test_learning
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from tools.studio import learn, preflight, rules

PASS, FAIL = [], []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name)
    print("  %-46s %s%s" % (name, "PASS" if ok else "FAIL", ("  " + detail) if detail else ""))


def fake_ledger(bot: str, texts: list[str]) -> dict:
    """A ledger where the SAME class was reported in N different wordings, as WARDEN writes them."""
    return {"version": 1, "slaps": [
        {"n": i + 1, "bot": bot, "at": "2026-09-13 0%d:00" % (i + 1), "rule": t,
         "violation": t, "evidence": "e", "level": 1, "status": "CLEAN - fix verified"}
        for i, t in enumerate(texts)]}


def main() -> int:
    print("learning layer selftest")

    # ------------------------------------------------------------------ classification by class
    print("\nruled classes (wording must not matter)")
    wordings = [
        "left pipeline test debris in the shipped asset tree",
        "Test debris left in runs/ and project root - 89 playtest-findshrine-*.json",
        "Never leave test fixtures in runs/ or assets/ - write them under $LOCALAPPDATA/Temp",
        "left test fixture tools/studio/rmdir.py in the project",
    ]
    ids = [rules.classify(w) for w in wordings]
    check("4 debris wordings -> one class", len(set(ids)) == 1 and ids[0] == "R-DEBRIS", " / ".join(set(ids)))
    check("round-protocol wording -> R-ROUNDDOC",
          rules.classify("Round 9 is undocumented. No runs/reports/BUILD-2026-09-13-r9.md") == "R-ROUNDDOC")
    check("crash wording -> R-BREAKMAIN",
          rules.classify("shipped broken code: spawn.py:162 NameError: name 'difficulty' is not defined")
          == "R-BREAKMAIN")
    check("numeric-evidence wording -> R-EVIDENCE",
          rules.classify("Visual claim of shrine activation unsupported by numeric evidence")
          == "R-EVIDENCE")
    check("unknown wording -> R-OTHER", rules.classify("the moon was in the wrong phase") == "R-OTHER")

    # ------------------------------------------------------------------ monotonic escalation
    print("\nescalation is monotonic (the actual bug)")
    led = fake_ledger("forge", wordings)
    lv = rules.escalation_level(led, "forge", "R-DEBRIS")
    check("4 reworded debris slaps -> level 3, not 1", lv == 3, "level=%d" % lv)
    led2 = fake_ledger("forge", wordings + ["left a stray diag_ script in runs/scripts/"])
    led2["slaps"][-1]["n"] = 5
    check("5th reworded debris slap stays >= 3", rules.escalation_level(led2, "forge", "R-DEBRIS") >= 3)
    check("a different bot starts at level 1", rules.escalation_level(led, "chip", "R-DEBRIS") == 1)
    check("an open defect does not double-escalate",
          rules.escalation_level(led, "forge", "R-DEBRIS", already_open=True) == 3)

    # ------------------------------------------------------------------ acceptance-command hygiene
    print("\nacceptance commands must be runnable")
    good = ["MSYS_NO_PATHCONV=1 .venv/Scripts/python.exe -m tools.studio.verify_gate",
            "test ! -f runs/scripts/verify_r3.py",
            "python -m game.main --headless --turns 300 --seed 0"]
    bad = ["Capture a fresh shrine-activation frame AFTER the statuses.py fix: run a scripted path that "
           "reaches a shrine, then count the pixels yourself",
           "Write docs/PROGRESS.md prepended entry for Round 9, write runs/reports/BUILD-2026-09-13-r9.md",
           "rm 'C:\\Users\\dbshe\\AppData\\Local\\Temp/gen_missing_items.py' (the Temp copy",
           "grep -q unique docs/CONTRACTS.md && grep -A1 'items.json"]
    check("3 real commands accepted", all(rules.is_runnable_command(c) for c in good))
    check("4 prose/broken ones rejected", not any(rules.is_runnable_command(c) for c in bad),
          "%d/4 leaked" % sum(rules.is_runnable_command(c) for c in bad))

    # ------------------------------------------------------------------ SOUL is bounded + deduped
    print("\nSOUL.md block: deduped by class and capped")
    with tempfile.TemporaryDirectory() as td:
        soul = Path(td) / "SOUL.md"
        soul.write_text("# BOT\n\nsomething the human wrote\n\n"
                        + learn.HEADER + "\n\n" + "\n".join("- **%s**" % w for w in wordings) + "\n")
        learn.SOUL_FOR["forge"] = soul
        note = learn.sync_soul("forge", led)
        text = soul.read_text(encoding="utf-8")
        check("4 wordings collapse to 1 block entry", text.count("R-DEBRIS") == 1)
        check("the count is visible in SOUL.md", "R-DEBRIS ×4" in text, text.splitlines()[-1][:60])
        check("hand-written content preserved", "something the human wrote" in text)
        check("block stays under the cap", len(text) < learn.MAX_CHARS + 400, note)
        big = fake_ledger("forge", ["test debris in " + str(i) for i in range(40)])
        for i, s in enumerate(big["slaps"]):
            s["rule_id"] = "R-DEBRIS"
        learn.sync_soul("forge", big)
        check("40 offences still one bounded entry", len(soul.read_text(encoding='utf-8')) < 1500)

    # ------------------------------------------------------------------ history line for the brief
    line = learn.history_line("forge", led)
    check("brief history names the class and its count", "R-DEBRIS x4" in line)
    check("brief history names the check", "check" in line.lower() and "before you finish" in line)

    # ------------------------------------------------------------------ preflight catches, then clears
    print("\npre-flight: catches a planted repeat offence, clears when fixed")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        for d in ("runs/reports", "runs/scripts", "docs", "game/data", "game/systems", "assets",
                  "tools/studio", ".venv/Scripts"):
            (root / d).mkdir(parents=True, exist_ok=True)
        (root / "docs/PROGRESS.md").write_text("# Progress\n\n## Round 14: P2.3\n\nchanged things\n")
        (root / "docs/ROADMAP.md").write_text("- [x] **P2.3 Enemy behaviour breadth.**\n")
        (root / "docs/TICKETS.md").write_text("| T-14 | P2.3 | done |\n")
        (root / "docs/CONTRACTS.md").write_text("contract v1\n")
        (root / "game/data/items.json").write_text("[]\n")
        (root / "tools/validate_data.py").write_text("# validator\n")
        (root / "runs/reports/BUILD-2026-09-13-r14.md").write_text("# Round 14: P2.3\n\nwork\n")

        clean = preflight.run(root, 14, "P2.3", "2026-09-13", update=True)
        check("clean tree passes", clean == [], "%d violation(s)" % len(clean))

        stray = root / "_verify_tree.py"
        stray.write_text("# one-off\n")
        (root / "runs/scripts/verify_r14.py").write_text("# debris\n")
        found = preflight.run(root, 14, "P2.3", "2026-09-13", update=False)
        classes = {f["rule_id"] for f in found}
        check("planted root script caught", any(f["path"] == "_verify_tree.py" for f in found))
        check("planted runs/scripts debris caught",
              any(f["path"].endswith("verify_r14.py") for f in found))
        check("both are R-DEBRIS", classes == {"R-DEBRIS"}, str(classes))
        stray.unlink()
        (root / "runs/scripts/verify_r14.py").unlink()
        check("removing them clears the finding",
              preflight.run(root, 14, "P2.3", "2026-09-13", update=False) == [])

        # undocumented round
        (root / "runs/reports/BUILD-2026-09-13-r14.md").unlink()
        found = preflight.run(root, 14, "P2.3", "2026-09-13", update=False)
        check("missing BUILD report caught", any(f["rule_id"] == "R-ROUNDDOC" for f in found))
        check("missing report names the path",
              any("BUILD-2026-09-13-r14.md" in f["evidence"] for f in found))
        (root / "runs/reports/BUILD-2026-09-13-r14.md").write_text("# Round 14: P2.3\n\nwork\n")

        # report collision / mislabel
        (root / "runs/reports/BUILD-2026-09-13-r13.md").write_text("# Round 14: P2.3\n\nwrong title\n")
        found = preflight.run(root, 14, "P2.3", "2026-09-13", update=False)
        check("report titled for another round caught",
              any("title says round 14" in f["violation"] for f in found))
        (root / "runs/reports/BUILD-2026-09-13-r13.md").unlink()

        # an overwritten past report is history, not a scratchpad
        old = root / "runs/reports/BUILD-2026-09-13-r9.md"
        old.write_text("# Round 9\n\noriginal\n")
        preflight.run(root, 0, "", "2026-09-13", update=True)
        old.write_text("# Round 9\n\nrewritten later\n")
        found = preflight.run(root, 0, "", "2026-09-13", update=False)
        check("overwriting a closed round's report caught",
              any("modified after the round closed" in f["violation"] for f in found))

        # contract drift
        preflight.run(root, 0, "", "2026-09-13", update=True)
        (root / "game/data/items.json").write_text('[{"id": "new_field"}]\n')
        found = preflight.run(root, 0, "", "2026-09-13", update=False)
        check("data change with no CONTRACTS.md change caught",
              any(f["rule_id"] == "R-CONTRACT" for f in found))
        (root / "docs/CONTRACTS.md").write_text("contract v2 with new_field\n")
        found = preflight.run(root, 0, "", "2026-09-13", update=False)
        check("contract updated in the same round clears it",
              not any(f["rule_id"] == "R-CONTRACT" for f in found))

        # evidence vs disk
        (root / "runs/shots/qa-x").mkdir(parents=True, exist_ok=True)
        (root / "runs/shots/qa-x/frame-000100.png").write_bytes(b"x")
        (root / "docs/PROGRESS.md").write_text(
            "# Progress\n\n## Round 14: P2.3\n\n5 frames at ticks 50/51/52/53/54 in runs/shots/qa-x\n")
        found = preflight.run(root, 0, "", "2026-09-13", update=False)
        check("claimed ticks missing on disk caught",
              any(f["rule_id"] == "R-EVIDENCE" for f in found))
        (root / "docs/PROGRESS.md").write_text(
            "# Progress\n\n## Round 14: P2.3\n\nframe at tick 100 in runs/shots/qa-x\n")
        found = preflight.run(root, 0, "", "2026-09-13", update=False)
        check("a tick that does exist clears it", not any(f["rule_id"] == "R-EVIDENCE" for f in found))

    # ------------------------------------------------------------------ the real ledger
    print("\nreal ledger (docs/slaps.json)")
    led = json.loads((learn.ROOT / "docs" / "slaps.json").read_text(encoding="utf-8"))
    rows = learn.class_rows(led, "forge")
    check("forge's 33 slaps collapse to a handful of classes", 0 < len(rows) <= 10, "%d classes" % len(rows))
    check("forge's worst class is level 3", rows and rows[0]["level"] == 3,
          "worst=%s x%d" % (rows[0]["rule_id"], rows[0]["count"]) if rows else "no rows")
    check("every real entry classifies to a known class",
          all((s.get("rule_id") or rules.classify(s.get("violation", ""), s.get("evidence", "")))
              in rules.BY_ID for s in led["slaps"]))
    lessons = learn.render_lessons(led)
    check("LESSONS.md renders with a per-class table", "| class | times |" in lessons)

    print("\n%d passed, %d failed" % (len(PASS), len(FAIL)))
    if FAIL:
        print("FAIL: %s" % ", ".join(FAIL))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
