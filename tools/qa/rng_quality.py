"""rng-quality: the randomness the whole game rests on must actually be random.

    python -m tools.qa.rng_quality                  # check game.systems.rng
    python -m tools.qa.rng_quality --json
    python -m tools.qa.rng_quality --source <path>  # check some other rng.py
    python -m tools.qa.rng_quality --inject-bug     # self-test: the checker MUST fail

Why this exists. ``docs/CONTRACTS.md`` §2 says every random draw in ``game/`` goes through
``RNG``. In September 2026 ``RNG._next()`` lost two of its three xorshift steps to operator
precedence - ``&`` binds tighter than ``^``, so ``x ^ (x << 25) & MASK64) ^ (x << 25) & MASK64``
cancels to ``x`` - and the generator collapsed to an **8-value cycle**. ``randint(0, 9)``
could never return 0, 3, 8 or 9, and 10,000 draws produced 8 distinct values.

Every gate in the repo stayed green while that was true, because the golden-seed regression
asserts *stability* (same seed -> same output), and a broken generator is perfectly stable.
Determinism is not randomness. This tool asserts the other half.

Exit status: 0 the generator behaves like a generator, 1 it does not,
2 the module could not be loaded, 3 (with --inject-bug) the checker failed to notice.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import types
from pathlib import Path

from tools import _util  # noqa: E402
from tools._util import EXIT_FAIL, EXIT_OK, EXIT_PREREQ  # noqa: E402

DRAWS = 10_000
UNIFORM_DRAWS = 100_000
BUCKETS = 10
#: chi-square upper bound for 9 degrees of freedom. The 0.001 critical value is ~27.88;
#: 40 leaves head-room against unlucky seeds while still catching any real collapse (the
#: bugged generator scores in the tens of thousands).
CHI2_LIMIT = 40.0
#: A working 64-bit generator gives ~10,000 distinct values in 10,000 draws (coupon
#: collector loses ~1). The broken one gave 8, so this bound is not a close call.
MIN_DISTINCT = int(DRAWS * 0.90)
CYCLE_WINDOW = 100_000
MASK64 = 0xFFFFFFFFFFFFFFFF


def buggy_next(self):
    """The exact pre-fix implementation: steps 2 and 3 cancel out (operator precedence).

    Kept verbatim so the self-test proves this checker catches the real defect rather
    than a conveniently-broken stand-in.
    """
    x = self.state
    x ^= (x >> 12) & MASK64
    x = (x ^ (x << 25) & MASK64) ^ (x << 25) & MASK64
    x = (x ^ (x >> 27) & MASK64) ^ (x >> 27) & MASK64
    self.state = x & MASK64
    self.calls += 1
    return self.state


def load_rng(source: str = "") -> type:
    """Import RNG from the project, or from an arbitrary rng.py by path."""
    if not source:
        from game.systems.rng import RNG  # noqa: PLC0415
        return RNG
    path = Path(source).resolve()
    spec = importlib.util.spec_from_file_location("_rng_under_test", path)
    if spec is None or spec.loader is None:
        raise ImportError("cannot load %s" % path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["_rng_under_test"] = module
    spec.loader.exec_module(module)
    return module.RNG


def run_checks(RNG: type) -> list[dict]:
    """Return one result dict per assertion. Every check is a real measurement."""
    out: list[dict] = []

    def record(name: str, ok: bool, detail: str) -> None:
        out.append({"check": name, "ok": bool(ok), "detail": detail})

    # 1. random() must return floats in [0, 1).
    r = RNG(1234)
    vals = [r.random() for _ in range(1000)]
    bad = [v for v in vals if not isinstance(v, float) or not (0.0 <= v < 1.0)]
    record("random-in-unit-interval", not bad,
           "1000 draws all within [0,1)" if not bad else "out of range: %r" % bad[:3])

    # 2. distinct values: the headline symptom of the 8-value cycle.
    r = RNG(42)
    distinct = len({r.random() for _ in range(DRAWS)})
    record("distinct-values", distinct >= MIN_DISTINCT,
           "%d distinct values in %d draws (need >= %d)" % (distinct, DRAWS, MIN_DISTINCT))

    # 3. randint must reach every value in its range.
    r = RNG(7)
    seen = {r.randint(0, 9) for _ in range(DRAWS)}
    record("randint-coverage", seen == set(range(BUCKETS)),
           "randint(0,9) reached %s%s" % (sorted(seen),
                                          "" if seen == set(range(BUCKETS))
                                          else " (missing %s)" % sorted(set(range(BUCKETS)) - seen)))

    # 4. chi-square uniformity across buckets.
    r = RNG(99)
    counts = [0] * BUCKETS
    for _ in range(UNIFORM_DRAWS):
        counts[int(r.random() * BUCKETS)] += 1
    expected = UNIFORM_DRAWS / BUCKETS
    chi2 = sum((c - expected) ** 2 / expected for c in counts)
    record("uniformity-chi2", chi2 <= CHI2_LIMIT,
           "chi2=%.1f over %d buckets (limit %.1f)" % (chi2, BUCKETS, CHI2_LIMIT))

    # 5. determinism: the property the game DOES depend on - keep it asserted.
    a, b = RNG(555), RNG(555)
    same = [a.random() for _ in range(50)] == [b.random() for _ in range(50)]
    record("deterministic-same-seed", same, "identical streams for seed 555" if same
           else "same seed produced different streams")

    # 6. different seeds must diverge.
    c, d = RNG(1), RNG(2)
    differ = [c.random() for _ in range(50)] != [d.random() for _ in range(50)]
    record("seeds-diverge", differ, "seed 1 and seed 2 differ" if differ
           else "seed 1 and seed 2 produced the same stream")

    # 7. no short cycle in the raw stream.
    r = RNG(5)
    seen_states: set[int] = set()
    cycle = None
    for i in range(CYCLE_WINDOW):
        st = r._next()
        if st in seen_states:
            cycle = i
            break
        seen_states.add(st)
    record("no-short-cycle", cycle is None,
           "no repeat in %d draws" % CYCLE_WINDOW if cycle is None
           else "cycle of length %d detected" % cycle)

    # 8. choice() must cover its whole sequence.
    r = RNG(3)
    picked = {r.choice(["a", "b", "c", "d", "e"]) for _ in range(DRAWS)}
    record("choice-coverage", len(picked) == 5,
           "choice reached %d of 5 elements" % len(picked))

    # 9. shuffle must actually permute.
    r = RNG(8)
    seq = list(range(20))
    r.shuffle(seq)
    record("shuffle-permutes", sorted(seq) == list(range(20)) and seq != list(range(20)),
           "shuffled to %s" % seq[:8])

    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m tools.qa.rng_quality",
                                 description="Assert the game's RNG behaves like an RNG.")
    ap.add_argument("--json", action="store_true", dest="as_json")
    ap.add_argument("--source", default="", help="test some other rng.py by path")
    ap.add_argument("--inject-bug", action="store_true",
                    help="self-test: install the pre-fix _next() and REQUIRE the checker to fail")
    args = ap.parse_args(argv)

    try:
        RNG = load_rng(args.source)
    except Exception as exc:  # noqa: BLE001
        _util.say("FAILED: cannot load RNG: %s: %s" % (type(exc).__name__, exc))
        return EXIT_PREREQ

    if args.inject_bug:
        RNG._next = buggy_next
        results = run_checks(RNG)
        failures = [r for r in results if not r["ok"]]
        caught = bool(failures)
        payload = {"ok": caught, "injected_bug_detected": caught, "checks": results}
        if args.as_json:
            print(json.dumps(payload, indent=2))
            return EXIT_OK if caught else EXIT_FAIL
        _util.say("rng-quality --inject-bug: installed the precedence-bugged _next()")
        for r in failures:
            _util.say("  caught [%s] %s" % (r["check"], r["detail"]))
        if caught:
            _util.say("OK: the checker detects the historical defect (%d check(s) failed as "
                      "they should)" % len(failures))
            return EXIT_OK
        _util.say("FAILED: the bugged generator passed every check - this tool is blind")
        return EXIT_FAIL

    results = run_checks(RNG)
    failures = [r for r in results if not r["ok"]]
    rc = EXIT_FAIL if failures else EXIT_OK
    payload = {"ok": rc == EXIT_OK, "source": args.source or "game.systems.rng",
               "checks": results}

    if args.as_json:
        print(json.dumps(payload, indent=2))
        return rc

    _util.say("rng quality: %d check(s) on %s" % (len(results), payload["source"]))
    for r in results:
        _util.say("  [%s] %-24s %s" % ("PASS" if r["ok"] else "FAIL", r["check"], r["detail"]))
    _util.say("OK: the generator behaves like a generator" if rc == EXIT_OK
              else "FAILED: %d check(s) - the RNG is not producing random output" % len(failures))
    return rc


if __name__ == "__main__":
    sys.exit(_util.guard(main)())
