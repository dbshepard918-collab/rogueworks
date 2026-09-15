# r62 — Autopilot consistency for seeds 2, 3, 6

**Forge → Bot AI** (autopilot targeting + escape logic)

## Diagnosis

Seeds 2, 3, 6 die quickly on floors 4-5 (catacombs), spending only 700-1200 ticks (10-20s) on the death floor. The bot is engaging too many monsters at once and burning HP.

## Fix

### 1. Ranged thinning
When 3+ monsters are nearby (< 150px), use ranged attacks to reduce their numbers before committing to melee. Prioritize the closest ranged/teleporter monsters first (they're the ones that chunk HP).

### 2. Escape threshold
Currently: only escape when HP < 40% AND threat_dist < 120px.
New: escape when HP < 50% AND (threat_dist < 120px OR 3+ monsters nearby).

### 3. Kiting
When retreating, use ranged attacks on the pursuer if available. Don't just run — fight while retreating.

### What NOT to do
- Don't change combat mechanics — only bot behavior
- Don't change monster stats — that's balance tuning (already done)
- Don't change floor generation
- Keep headless-safe

## Acceptance
1. `autopilot --seeds 2 3 6` — all reach floor 7+ (was dying on 4-5)
2. `game.main --headless --turns 300 --seed 0..2` exits 0
3. `selftest` 22/22

## Files to touch
- `game/engine/input.py` — `AutoPilotInput.sample()`
