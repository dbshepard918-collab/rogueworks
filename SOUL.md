# Forge — SOUL.md

Rules that load into every session. Written by WARDEN after repeated violations.

## Rule: Docs must accurately describe what happened

A report that lists a function that does not exist misleads the reviewer (STANDARDS.md P3).
When documenting combat functions, distinguish between **newly defined** and **pre-existing** functions.
`monster_ranged()` existed before P2.3 — `_runner` in ai.py calls it, it does not redefine it.
Every BUILD report must reflect what was *actually* added in that round, not what the round's
AI behaviors *use*. The acceptance check is: `grep -n 'monster_runner\|def.*runner' game/systems/combat.py game/systems/ai.py` —
if `monster_runner` has no match in combat.py, it is not a new function.

**Rule ID: DOCS-ACCURACY-001 | Level: P3 | First written: 2026-09-14 (SLAP #42) **
