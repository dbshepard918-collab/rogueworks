# BALANCE — measured, not assumed

> **2026-09-14 (r44) — HEADLINE CORRECTION: the meta-progression loop WORKS.**
> The finding below ("depth does not rise with investment") was mostly a **measurement
> artefact**: the QA autopilot could not see ranged monsters holding 230-300 px (its
> ENGAGE_RANGE was 230 while their hold distance is 249), so it stood still and died
> without fighting — at any investment level. After fixing the pilot's sight
> (`game/engine/input.py`, commit `c708db9`), the same 12-seed paired ladder gives:
>
> | tiers | 0 | 2 | 5 | 10 | 15 | 20 |
> |---|---|---|---|---|---|---|
> | avg final floor | 5.58 | 6.92 | 7.75 | 8.83 | **10.17** | 8.67 |
>
> Fresh mean 5.58 → full-tree mean 8.67 (**+3.1 floors**); per-seed paired deltas:
> 8 improved / 2 same / 2 worse. Investment now shows the intended monotonic ladder
> (with a noise-level dip at 20 tiers vs 15). **The tree needed no retuning — the
> instrument did.** Two harness defects were also fixed en route: `world.py` shop-stall
> `item_by_id` AttributeError (P1, committed `f0726ff`) and progression.py's missing
> per-run rows (paired analysis was impossible without them).
>
> Lesson added to the studio's method: **the QA proxy is part of the instrument.** A
> blind proxy reports game defects that a human player would never experience — and it
> reported this one as a balance problem for two rounds before the per-seed pairing
> exposed it.

Ticket **G-01** asks for TTK, death rate per floor and essence economy with before/after numbers.
This is the first measurement pass. Every number below comes from real play, and every one is
reproducible with the command at the bottom.

## Method and instrument

`python -m tools.qa.balance` drives the same headless world + `AutoPilotInput` that
`tools.qa.autopilot` uses — BFS to the floor objective, engage the nearest monster, dash, drink
consumables, retreat when low — for 8 seeds at a 20,000-tick budget. The harness was verified to
reproduce the reference autopilot exactly (seed 0, 5999 ticks: `steps=1877 state=dead floor=1
kills=0`, identical in both tools).

**Instrument caveat, stated up front:** the autopilot is a competent-but-simple proxy, so these
numbers are a **floor on difficulty, not a ceiling**. They say what a decent bot can do, not what a
human will do.

## Result — 8 seeds, 20,000 ticks, corrected RNG

| seed | state | final floor | kills | essence | level |
|---|---|---|---|---|---|
| 0 | dead | 1 | 0 | 0 | 1 |
| 1 | dead | 1 | 0 | 0 | 1 |
| 2 | dead | 5 | 2 | 6 | 2 |
| 3 | dead | 5 | 13 | 4 | 4 |
| 4 | running | 3 | 2 | 1 | 1 |
| 5 | running | 3 | 1 | 0 | 1 |
| 6 | dead | 4 | 4 | 0 | 2 |
| 7 | dead | 5 | 37 | 18 | 5 |

| metric | value |
|---|---|
| death rate | **0.75** (6/8 dead, 2 still running when the budget expired) |
| average final floor | **3.38** |
| max floor reached | **5** (the game has 15) |
| average kills per run | 7.38 (range 0-37) |
| average essence per run | 3.62 (range 0-18) |

**Floor attrition** — how many of the 8 runs reached each floor:

```
floor 1: 8/8     floor 4: 4/8
floor 2: 6/8     floor 5: 3/8
floor 3: 6/8     floor 6: 0/8   <-- nobody reaches floor 6
```

## Findings

1. **No run reaches floor 6 of 15.** Biomes 2, 3 and 4 begin at floors 6, 11 and 16, so **three
   quarters of the game's content is unreachable by this proxy** — and anything only reachable
   past floor 5 is effectively untested by play. This is consistent with the studio's own history
   of deep-floor defects that "no gate before this could see".
2. **The economy is extremely swingy.** Essence per run ranges 0 to 18 across 8 seeds; two runs
   finished with literally zero. Essence drives the meta-progression tree, so a run that earns
   nothing is a run that advanced nothing.
3. **Two runs stalled on floor 3** (seeds 4 and 5: 11,559 and 12,047 ticks to still be on floor 3
   when the budget expired, with 1-2 kills). Either the floor is unusually hard to clear or the
   proxy gets stuck; it needs eyes on a real frame before it is called a difficulty problem.
4. **Kills are bimodal.** Six of eight runs killed 0-4 monsters; one killed 37. A floor either
   goes fine or the run dies early, which is what a too-steep early curve looks like.

## Before/after: the RNG fix, and a hypothesis that failed

The shipped RNG was repaired on 2026-09-14 (it had collapsed to an 8-value cycle — see
`docs/MODELS.md` and ticket RNG-01). That changes every loot roll, spawn and level-up, so the
economy measured before it is not the economy that ships. `--rng buggy` reinstalls the historical
generator so the same seeds can be measured both ways.

Measured on seed 0, 6,000 ticks: under the **old** generator the floor counter advanced through
floors 1-5 at 279 ticks each with **0 kills** — implausibly fast progression, as if the floors were
being skipped rather than played. Under the corrected generator the same seed dies on floor 1 after
1,877 ticks.

**The obvious hypothesis — "the degenerate RNG was placing the stairs next to the player" — is
DISPROVEN by measurement:** spawn-to-objective Manhattan distance is **20 on every seed under both
generators** (`[20, 20, 20, 20, 20, 20]`), while monster counts *do* differ per seed and per
generator (fixed: 13/13/13/11/14/12; buggy: 14/10/13/12/13/13). So the RNG does affect spawns, but
not the objective distance.

**The 279-tick floor advance under the old generator is therefore an open question, not a
finding.** Do not write a cause into a doc until it has one.

## What this does NOT measure

- **Real TTK.** The proxy barely kills anything (7.4 kills/run), so a ticks-per-kill figure from it
  is dominated by travel, not combat. Proper TTK needs combat telemetry — time from first damage to
  monster death — not a proxy average.
- **Human difficulty.** One proxy, one build, 8 seeds.
- **Anything past floor 5.** Including every boss after the first.

## Reproduce

```bash
cd /c/Users/dbshe/rogueworks
P="MSYS_NO_PATHCONV=1 .venv/Scripts/python.exe"
$P -m tools.qa.balance --seeds 0 1 2 3 4 5 6 7 --turns 20000        # the table above
$P -m tools.qa.balance --seeds 0 --turns 6000 --rng buggy           # the historical generator
$P -m tools.qa.balance --seeds 0 --json                             # machine-readable
```

## Next (opened as tickets, not fixed here)

- **A fighting autopilot**: real TTK needs an agent that reliably engages, or combat telemetry.
- **Find out why floor 3 stalls** for two of eight seeds (needs a rendered frame, not a number).
- **Decide the intended depth curve**: if a competent proxy is supposed to reach floor 10-15, the
  current curve is far too steep; if it is supposed to die at floor 4, then floors 6-15 are content
  no one can see and the game is effectively 4 floors long.



## Does meta investment take you deeper? (the design's own prediction, tested)



Roguelite design intends this: dying on floor 3-4 with a **fresh** save is fine, and the

meta-progression tree is what carries you deeper on repeat runs. That intent makes a falsifiable

prediction, so `tools/qa/progression.py` tests it: build profiles holding 0 / 2 / 5 / 10 / 15 / 20

purchased tree tiers, run the **same 4 seeds** at each level, and compare depth.



| tiers bought | stat bonus | avg floor | best floor | avg kills | avg max_hp | deaths |

|---|---|---|---|---|---|---|

| 0 (fresh) | 0.0 | 3.00 | 5 | 3.8 | 96.0 | 4/4 |

| 2 | 22.0 | 3.00 | 5 | 3.8 | 118.0 | 4/4 |

| 5 | 58.5 | 3.00 | 5 | 1.2 | 149.0 | 4/4 |

| 10 | 67.9 | 6.00 | **14** | 23.2 | 174.2 | 3/4 |

| 15 | 75.45 | 3.25 | 7 | 6.5 | 166.8 | 2/4 |

| 20 (full tree) | **208.45** | 3.00 | 6 | 4.5 | 153.0 | 4/4 |



**The instrument is valid — the upgrades really are applied.** A fresh profile carries 96 max HP;

the same profile with 20 tiers carries 153-174, and `meta_stat_totals` climbs 0 -> 208.45. The tool

refuses to report at all if a powered profile does not differ from a fresh one, so this is not a

harness artefact.



**The finding: depth does not rise with investment.** Average floor is flat across the ladder

(3.0, 3.0, 3.0, 6.0, 3.25, 3.0), and a **fully-invested save dies as often as a fresh one**

(4/4 deaths at both 0 and 20 tiers, avg floor 3.00 both). The single deep run in the whole matrix

(floor 14) happened at **10** tiers, not at maximum investment — the opposite of the design intent.



**Caveats, stated rather than glossed:**

- n = 4 seeds per level and floors are high-variance, so this is a strong *signal* of flatness, not

  a proof. A conclusive pass needs ~12 seeds per level.

- The autopilot is a weak proxy. The tree also grants crit, luck, speed and dash i-frames, which a

  clumsy bot may simply not exploit — so this measures whether investment helps *this* player, not

  whether it helps a skilled one. The HP half of the tree *is* demonstrably applied and still does

  not convert into depth for it.

- Deeper investment carrying **lower** average max HP than mid investment (153 at 20 tiers vs 174 at

  10) is expected, not a bug: vitality has only 4 tiers, so later purchases go to other branches.



**Why this matters:** if a maxed tree performs like a fresh save, the repeat-run loop does not pay

off and "choose your destiny" becomes "nothing you do persists" — the one failure mode that would

make the roguelite structure pointless. Worth a dedicated balance pass before more content.



```bash

cd /c/Users/dbshe/rogueworks

MSYS_NO_PATHCONV=1 .venv/Scripts/python.exe -m tools.qa.progression --seeds 0 1 2 3 --turns 12000

```

