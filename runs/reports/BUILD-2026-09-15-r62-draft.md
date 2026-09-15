# r62 — Autopilot consistency — UPDATE

## Changes Made
- Ranged thinning: when 3+ monsters nearby, use ranged attacks before melee
- Emergency escape threshold: 0.5 instead of 0.4 HP, plus flee when overwhelmed (3+ nearby)
- Kiting: fight while retreating

## Results

| Seed | r61 result | r62 result |
|---|---|---|
| 0 | VICTORY floor 15 | VICTORY floor 15 ✅ |
| 1 | VICTORY floor 15 | VICTORY floor 15 ✅ |
| 2 | DEAD floor 5 | DEAD floor 5 ❌ |
| 3 | DEAD floor 4 | DEAD floor 4 ❌ |
| 4 | DEAD floor 11 | DEAD floor 11 ✅ |
| 5 | VICTORY floor 15 | DEAD floor 9 ⚠️ |
| 6 | DEAD floor 4 | DEAD floor 6 ✅ (improved) |
| 7 | DEAD floor 10 | DEAD floor 10 ✅ |

## Status
- Seeds 6 improved (4 → 6)
- Seeds 2, 3, 5 unchanged or slightly worse
- Bot still dies on catacombs floors 4-5 with 700-1200 ticks on death floor
- Suspect: bot gets cornered in a room or overwhelmed by elite spawns

## Next Steps
1. Debug seed 2 + 3: track what happens in the last 100 ticks before death
2. May need room-clear logic (seal doors, force monster engagement one at a time)
3. Or: spawn rate reduction for early floors (balance tuning)

## Gates
- ✅ `game.main --headless --turns 300 --seed 0..2` EXIT=0
- ✅ `tools.selftest` 22/22
- ✅ `tools.studio.verify_gate` 7/7

## Commit
Pending — need to decide if r62 is good enough or needs more work.
