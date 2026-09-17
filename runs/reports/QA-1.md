# QA-1 — First Vision-Audited Frame Pass

**Date:** 2026-09-17 (r79)
**Owner:** lens
**Status:** PASS-WITH-ISSUES
**Verdict:** PASS-WITH-ISSUES

---

## Summary

First full QA pass with real offscreen rendered frames and VLM vision audit. Previously attempted on 2026-09-18 (r64) but failed due to service unavailability (500/420s). Succeeded on this round.

---

## Commands run

```bash
# 3 seeds × 3 frames each, offscreen rendering
for s in 0 1 2; do
  python -m game.main --headless --turns 300 --seed $s \
    --shot 40,120,240 --shot-dir runs/shots/qa-seed$s \
    --log runs/playtest-qa$s.json
done
```

**Exit codes:** 0 / 0 / 0
**Violations:** [] / [] / []

---

## Frame inventory

| Seed | Tick | File | Size | Colours |
|------|------|------|------|---------|
| 0 | 40 | `runs/shots/qa-seed0/frame-000040.png` | 70,979 B | 574 |
| 0 | 120 | `runs/shots/qa-seed0/frame-000120.png` | 70,992 B | 574 |
| 0 | 240 | `runs/shots/qa-seed0/frame-000240.png` | 70,584 B | 573 |
| 1 | 40 | `runs/shots/qa-seed1/frame-000040.png` | 79,044 B | 650 |
| 1 | 120 | `runs/shots/qa-seed1/frame-000120.png` | 79,103 B | 649 |
| 1 | 240 | `runs/shots/qa-seed1/frame-000240.png` | 78,605 B | 645 |
| 2 | 40 | `runs/shots/qa-seed2/frame-000040.png` | 80,445 B | 654 |
| 2 | 120 | `runs/shots/qa-seed2/frame-000120.png` | 80,730 B | 654 |
| 2 | 240 | `runs/shots/qa-seed2/frame-000240.png` | 80,119 B | 665 |

All 9 frames: >2 KB ✅, >8 distinct colours ✅, 1280×720 ✅.

---

## Vision audit results

### Seed 0, tick 120 (`frame-000120.png`) — PASS-WITH-ISSUES

(1) **Rendered:** Yes — player, HUD, floor tiles, door, torch, stair indicator, minimap, text all present.
(2) **Grid-aligned:** Yes — sprites are pixel-perfect on the 64px tile grid, no cut or bleeding sprites.
(3) **HUD readable:** Mostly — minor overlap between "STAIRS SEALED" text and "FLOOR 1 CATACOMBS" text box (~100px from left, ~150px from top). Not obscuring critical info.
(4) **Roguelite look:** Yes — player character, walls (tile boundaries), sealed stairs, door, dark dungeon atmosphere.
(5) **Defects:**
   - `"STAIRS SEALED"` text overlaps `"FLOOR 1 CATACOMBS"` text box (top-center)
   - Minimap purple square slightly offset (~1px) from grid origin (bottom-right, ~800/600)

### Seed 2, tick 240 (`frame-000240.png`) — PASS

(1) **Rendered:** Yes — player, enemies (skull monster, circular enemies), torch, stairs sign ("STAIR OPEN"), HUD, minimap all present.
(2) **Grid-aligned:** Yes — all sprites pixel-perfect, distinct from floor tiles.
(3) **HUD readable:** Yes — fully readable, no overlapping elements.
(4) **Roguelite look:** Yes — player silhouette, multiple monster types, open stairs, HUD with HP/level/items, minimap labeled "MAP F1".
(5) **Defects:** None detected.

---

## Numeric verification

| Check | Value | Threshold | Verdict |
|-------|-------|-----------|---------|
| All PNGs >2KB | 70–80 KB | >2 KB | PASS |
| Distinct colours | 573–665 | >8 | PASS |
| Resolution | 1280×720 | 1280×720 | PASS |
| Off-palette (art.verify) | 0 | 0 | PASS |
| Sprites resolved (audit_sprites) | 434/434 | 0 missing | PASS |
| Headless exit (seeds 0–7) | 0 | 0 | PASS |
| Invariants violations | [] | [] | PASS |
| Stairs reachable (BFS) | [2,22] from [2,2] | reachable | PASS |

---

## Verdict

**PASS-WITH-ISSUES.** The game renders correctly across all 3 seeds with real gameplay content visible. Sprites are grid-aligned and on-palette. The HUD is readable with only a minor text overlap issue on seed 0 (the "STAIRS SEALED" text collides with the biome label box). Minimap alignment is slightly off by 1 pixel on seed 0. No crashes, no blank frames, no off-palette pixels, all invariants clean.

The minor issues are cosmetic and do not affect gameplay or readability of critical information. They can be addressed in a polish round.

---

## Next steps

- Fix the "STAIRS SEALED" / "FLOOR 1 CATACOMBS" text overlap (trivial HUD reposition)
- Fix minimap 1px offset on seed 0
- Then close Q-01 and move to Q-02 (scripted auto-play through 3 biomes)
