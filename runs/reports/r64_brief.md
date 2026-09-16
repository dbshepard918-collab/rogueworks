# r64 — Seeds 2/3 consistency: diagnose death on catacombs floors 4-5

**Forge → Bot AI**

## Diagnosis

Seeds 2 and 3 both die on catacombs floors 4-5 with only 700-1200 ticks on the death floor. The bot is getting overwhelmed or cornered. I need to understand:
1. Is the bot dying to elite spawns?
2. Is the bot getting stuck in combat with too many monsters?
3. Is the bot running out of HP/consumables at a critical moment?

## What to build

### 1. Diagnostic logging
Run seeds 2 and 3 with detailed logging:
- Track HP over time
- Track monster count and positions
- Track bot actions (attack, dash, use consumable)
- Track path length and avoid set size

### 2. Targeted fix based on findings
Possible fixes depending on diagnosis:
- **If elites are the problem**: reduce elite spawn rate on floors 4-5, or make bot prioritize fleeing elites
- **If corner deaths**: improve escape logic — bot should never get stuck in a dead-end
- **If HP drain**: earlier consumable use, or reduce floor 4-5 damage slightly

## What NOT to do
- Don't change combat mechanics
- Don't change floor generation
- Keep headless-safe

## Acceptance
1. `autopilot --seeds 2 3 --turns 60000` — both reach floor 7+
2. `game.main --headless --turns 300 --seed 0..2` exits 0
3. `selftest` 22/22

## Files to touch
- `game/engine/input.py` — diagnostic logging + targeted fix
