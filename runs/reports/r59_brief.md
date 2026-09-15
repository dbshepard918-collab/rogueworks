# r59 — Autopilot consistency: prioritize reaching stairs over fighting

**Forge → Chip** (autopilot pathfinding + combat)

## Problem

| Seeds | Result |
|---|---|
| 0, 5 | Reach floor 9-15 (VICTORY) |
| 1, 2, 3, 4, 6, 7 | Die/stuck floors 2-5 |

The bot dies early on 6/8 seeds. Root cause: the bot **fights everything** on the way to stairs. It engages every monster within 230px, burns HP and cooldowns, then dies when it reaches the stairs with no resources left.

Looking at seed 3: 1 kill, level 1, 0 items — the bot got overwhelmed on floor 3 without scaling.

## Fix: Stair-First Navigation

### 1. New mode: PATH_TO_STAIRS
When no monsters are actively attacking us (no recent damage), prioritize reaching the stairs over fighting. Only engage monsters that are:
- Between us and the stairs (blocking our path)
- Very close (< 100px)
- Damaged (low HP, easy kill)

### 2. Avoid monsters when navigating
Use A* to find a path to stairs that avoids monster engagement zones (don't walk within 100px of a monster unless it's on the direct path).

### 3. Retreat threshold
Currently: retreat only when HP < 40% AND threat_dist < 120px
New: retreat when HP < 50% OR more than 2 monsters are nearby (< 150px)

### 4. Consumables
Use healing items when HP < 60% (was < 40%)

## What NOT to do
- Don't change monster stats or spawn rates
- Don't change floor generation
- Don't change combat mechanics — only bot behavior

## Acceptance
1. `autopilot --seeds 0..7 --turns 60000` — at least 6/8 seeds reach floor 6+
2. `game.main --headless --turns 300 --seed 0..2` exits 0, violations=[]
3. `tools.selftest` 22/22

## Files to touch
- `game/engine/input.py` — `AutoPilotInput.sample()` stair-first navigation
