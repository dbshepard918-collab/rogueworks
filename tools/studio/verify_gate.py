"""Run EVERY gate in one command and print a table. The studio's pre-flight and its acceptance test.

    python -m tools.studio.verify_gate [--seeds 0 1 2] [--turns 300] [--raw] [--json]

Exit 0 only if every gate passes. `forge` runs it before and after a round; `warden` runs it to check
the claim; `lens` uses its per-seed detail. One command, one verdict, real output - this is what makes
"the gates are green" a fact instead of an assertion.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PY = ROOT / ".venv" / "Scripts" / "python.exe"


def run(args: list[str], timeout: int = 900) -> tuple[int, str, float]:
    t0 = time.time()
    try:
        p = subprocess.run([str(PY), "-m"] + args, cwd=str(ROOT), capture_output=True, text=True,
                           timeout=timeout, encoding="utf-8", errors="replace")
        out = ((p.stdout or "") + (p.stderr or "")).strip()
        return p.returncode, out, time.time() - t0
    except subprocess.TimeoutExpired:
        return 124, "TIMEOUT after %ds" % timeout, time.time() - t0


def last_meaningful(out: str, n: int = 2) -> str:
    lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
    lines = [ln for ln in lines if not ln.startswith("pygame-ce")]
    return " | ".join(lines[-n:])[:220]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m tools.studio.verify_gate")
    ap.add_argument("--seeds", nargs="*", type=int, default=[0, 1, 2])
    ap.add_argument("--turns", type=int, default=300)
    ap.add_argument("--raw", action="store_true",
                    help="also check every sheet in assets/raw/ with check_sheet (slower)")
    ap.add_argument("--json", action="store_true", dest="as_json")
    args = ap.parse_args(argv)

    results = []

    for seed in args.seeds:
        rc, out, secs = run(["game.main", "--headless", "--turns", str(args.turns),
                             "--seed", str(seed)])
        detail = ""
        summary = ROOT / "runs" / ("playtest-%d.json" % seed)
        if rc == 0 and summary.is_file():
            try:
                data = json.loads(summary.read_text(encoding="utf-8"))
                v = data.get("invariants", {}).get("violations", [])
                detail = "ok=%s violations=%s" % (data.get("ok"), v)
                if not data.get("ok") or v:
                    rc = 1
            except Exception as exc:  # noqa: BLE001
                rc, detail = 1, "summary unreadable: %s" % exc
        results.append(("headless seed %d" % seed, rc, detail or last_meaningful(out), secs))

    for module in ("tools.validate_data", "tools.art.verify", "tools.selftest",
                   "tools.studio.audit_sprites"):
        rc, out, secs = run([module])
        results.append((module, rc, last_meaningful(out, 3), secs))

    if args.raw:
        raw_dir = ROOT / "assets" / "raw"
        for sheet in sorted(raw_dir.glob("*.png")):
            rc, out, secs = run(["tools.art.check_sheet", str(sheet)])
            verdict = "PASS" if "verdict      : PASS" in out else "REJECT"
            results.append(("check_sheet %s" % sheet.name, rc,
                            verdict + " " + last_meaningful(out, 1), secs))

    failed = [(n, rc, d) for n, rc, d, _ in results if rc != 0]
    if args.as_json:
        print(json.dumps({"ok": not failed,
                          "gates": [{"name": n, "exit": rc, "detail": d, "seconds": round(s, 1)}
                                    for n, rc, d, s in results]}, indent=2))
        return 0 if not failed else 1

    print("=" * 78)
    print("VERIFY GATE  %s" % time.strftime("%Y-%m-%d %H:%M"))
    print("=" * 78)
    for name, rc, detail, secs in results:
        print("  %-34s %-5s %6.1fs  %s" % (name, "PASS" if rc == 0 else "FAIL", secs, detail))
    print("-" * 78)
    if failed:
        print("VERDICT: FAIL - %d gate(s) red: %s" % (len(failed), ", ".join(n for n, _, _ in failed)))
        return 1
    print("VERDICT: PASS - all %d gate(s) green" % len(results))
    return 0


if __name__ == "__main__":
    sys.exit(main())
