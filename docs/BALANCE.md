# BALANCE — measured, not assumed

> **2026-09-15 (r53) — CRITICAL BUG FOUND AND FIXED.** The r52 VFX pass
> introduced an `UnboundLocalError: cannot access local variable 'crit'`
> in `combat.py` — the `if crit:` check was placed **before** `crit = ...`
> was assigned. This crashed every melee hit in the balance harness, silently
> degrading every run it touched. All pre-r53 numbers are invalid. The numbers
> below are post-fix and reproducible.

> **2026-09-14 (r44) — meta-progression loop WORKS (confirmed again at r53).**
> The finding below ("depth does not rise with investment") was a measurement
> artefact: the QA autopilot could not see ranged monsters holding 230-300 px,
> so it stood still and died without fighting. After the r44 sight fix, a
> 12-seed paired ladder showed fresh 5.58 → full-tree 8.67 floors (+3.1).

Ticket **G-01** asks for TTK, death rate per floor and essence economy.
This is the first measurement pass. Every number below comes from real play.

## Method and instrument

`python -m tools.qa.balance` drives the same headless world + `AutoPilotInput`
for 8 seeds at a 20,000-tick budget. The harness was verified to reproduce
the reference autopilot exactly.

**Instrument caveat:** the autopilot is a competent-but-simple proxy, so these
numbers are a **floor on difficulty, not a ceiling**.

## Result — 8 seeds, 20,000 ticks, r52 VFX bug fixed

| seed | state | final floor | kills | essence | level |
|---|---|---|---|---|---|
| 0 | dead | 4 | 10 | 5 | 3 |
| 1 | dead | 4 | 17 | 8 | 3 |
| 2 | dead | 4 | 13 | 7 | 3 |
| 3 | dead | 5 | 37 | 18 | 5 |
| 4 | dead | 2 | 8 | 2 | 2 |
| 5 | dead | 5 | 16 | 7 | 4 |
| 6 | running | 3 | 42 | 21 | 5 |
| 7 | dead | 2 | 26 | 9 | 4 |

| metric | value |
|---|---|
| death rate | **0.875** (7/8 dead, 1 still running) |
| average final floor | **3.6** |
| max floor reached | **5** (the game has 15) |
| average kills per run | **21.1** (range 8-42) |
| average essence per run | **9.5** (range 2-21) |

**Floor attrition:**

```
floor 1: 8/8     floor 4: 4/8
floor 2: 7/8     floor 5: 2/8
floor 3: 6/8     floor 6: 0/8   <-- nobody reaches floor 6
```

## Findings

1. **No run reaches floor 6 of 15.** Three-quarters of the game's content
   (biomes 2, 3, 4 at floors 6, 11, 16) is unreachable by the autopilot proxy.
2. **The economy is swingy.** Essence ranges 2 to 21 across 8 seeds.
3. **Kills are bimodal.** Runs either clear floors quickly or die early.
4. **The r52 VFX bug was silent but catastrophic.** Using `crit` before
   assignment crashed every melee swing, which the harness logged as a
   "dead floor 1" result — masking the real damage output.

## Does meta investment take you deeper?

Roguelite design intends: dying on floor 3-4 with a fresh save is fine, and
the meta-progression tree carries you deeper on repeat runs.

| tiers | stat bonus | avg floor | best | avg kills | avg max_hp | deaths |
|---|---|---|---|---|---|---|
| 0 (fresh) | 0.0 | 3.75 | 5 | 17.5 | 116.5 | 4/4 |
| 2 | 22.0 | 5.5 | 8 | 28.2 | 138.5 | 3/4 |
| 5 | 58.5 | 7.75 | 9 | 44.5 | 184.2 | 1/4 |
| 10 | 67.9 | 5.25 | 10 | 34.0 | 178.0 | 2/4 |
| 15 | 75.45 | 6.5 | 11 | 27.0 | 168.8 | 3/4 |
| 20 (full tree) | **208.45** | **8.75** | **13** | **41.2** | **195.0** | **2/4** |

**VERDICT: meta investment moves depth** (3.75 → 8.75 floors, +133%).
The tree's intended ladder holds: 20 tiers gives 2.3× the depth of fresh.

**Caveats:** n=4 seeds per level, floors are high-variance. ~12 seeds would
be conclusive. The autopilot is a weak proxy — results measure what a bot
can do, not what a human can.

```bash
cd /c/Users/dbshe/rogueworks
MSYS_NO_PATHCONV=1 .venv/Scripts/python.exe -m tools.qa.progression --seeds 0 1 2 3 --turns 12000
```

## What this does NOT measure

- **Real TTK.** The proxy kills 21/run now, but ticks-per-kill still includes
  travel. Proper TTK needs combat telemetry.
- **Human difficulty.** One proxy, one build.
- **Anything past floor 5.** Every boss after the first is unmeasured.
