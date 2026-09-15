# r57 — Autobot stuck fix: pathfinding recovery + stuck detection

**Forge → Chip** (autopilot pathfinding)

## Problem
Mixed results after r56 fix:
- Seeds 5: reaches floor 11 but **STUCK** at floor transition
- Seed 4: **STUCK** at floor 3
- Seeds 6, 7: die on floors 5, 2

The autopilot is reaching deep floors (validated), but getting stuck on certain floors. The `stuck` flag triggers after 10801 ticks (~180s) without movement. This is a pathfinding recovery issue — the bot grinds against geometry, drops its target, but never recovers a path to the objective.

## Root cause
`AutoPilotInput` has stuck detection that drops the target but the repath logic is tied to the **target**. If the target is dropped, the bot has no goal and stands still. Need: a recovery mode that tries alternate targets when the primary objective is unreachable.

## Fix

### 1. Recovery mode on stuck
When stuck is detected for >60 ticks:
- Drop current target and pick the nearest reachable room center
- If still stuck, scan for any unexplored tile on the floor
- If still stuck, use A* to the stairs directly (ignore rooms)

### 2. Target priority fallback
Current: always pathfind to objective_tile()
New: objective_tile() → nearest room center → stairs fallback

### 3. Anti-stuck: random walk when all else fails
When stuck >120 ticks, pick a random reachable tile and walk toward it — this breaks geometry deadlocks.

## Acceptance
1. `autopilot --seeds 4..7 --turns 60000` — no STUCK states, all reach floor 6+
2. `game.main --headless --turns 300 --seed 0..2` exits 0, violations=[]
3. `tools.selftest` 22/22

## Files to touch
- `game/engine/input.py` — `AutoPilotInput.sample()` stuck recovery logic
