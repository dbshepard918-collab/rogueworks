# r56 — Autopilot deep-floor fix: engage ranged enemies instead of fleeing them

**Forge → Chip** (autopilot targeting logic)

## Problem
The autopilot dies on floors 3-5 across all seeds (verified 4/4 seeds). The r44 sight fix made it detect ranged enemies within `RANGED_MAX` (300px) and dash AWAY from them — but it never shoots back. It just burns dash cooldown and HP fleeing until it dies.

Looking at `AutoPilotInput.sample()`:
- Line 238: `if ranged_at is not None and threat_dist > player.ATTACK_REACH and player.dash_ready(): dash away` — returns early
- The ranged attack at line 260 (`if player.ranged_ready() and RANGED_MIN < threat_dist < RANGED_MAX: shoot`) is NEVER REACHED when a ranged enemy is detected because line 238 returns first

## Fix

### 1. Shoot ranged enemies instead of fleeing them
In `sample()`, when a ranged threat is detected:
- If `player.ranged_ready()` and `RANGED_MIN < threat_dist < RANGED_MAX`: add `"ranged"` action, face the enemy
- Only dash away if `low_hp` AND `threat_dist < 120` (emergency retreat)
- Otherwise pathfind toward the enemy to close distance for melee

### 2. Remove the early-return dash-away for ranged
The line 238 early return is the bug. Replace it with shoot-first logic.

### 3. Ranged targeting priority
When a ranged enemy is detected, it should be the PRIMARY threat — it's the one actively damaging us. The current code treats it as a "thing to flee from" rather than "thing to kill."

## What NOT to do
- Don't change `ENGAGE_RANGE`, `RANGED_MIN`, `RANGED_MAX` — they're tuned correctly
- Don't add new RNG calls — all timing via cooldown counters
- Don't break the headless gate — every new branch must be safe in headless mode
- Don't change the tile atlas or art — this is pure logic

## Acceptance
1. `python -m tools.qa.autopilot --seed 0 --turns 60000` reaches floor 6+ (was dying floor 3-5)
2. `python -m game.main --headless --turns 300 --seed 0..2` exits 0, violations=[]
3. `python -m tools.selftest` 22/22

## Files to touch
- `game/engine/input.py` — `AutoPilotInput.sample()` ranged threat handling
