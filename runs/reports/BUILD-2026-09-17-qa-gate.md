# BUILD — 2026-09-17 QA Gate Check (Forge)

**Date:** 2026-09-17 (Wednesday)  
**Owner:** forge  
**Task:** Full QA gate sweep — `game.main --headless --turns 300 --seed 0..2`, `tools.selftest`, `tools.validate_data`, `tools.art.verify`  
**Action:** REPORT ONLY — no fixes applied

---

## Gate 1 — `game.main --headless --turns 300 --seed 0..2`

**Result: PASS (all 3 seeds exit 0, violations=[])**

| Seed | Exit | Ticks | Floor | Biome | Rooms | Entities | Monsters | Violations | ms/tick | fps_equiv |
|------|------|-------|-------|-------|-------|----------|----------|------------|--------|-----------|
| 0 | 0 | 300 | 1 | catacombs | 6 | 17 | 13 | [] | 3.712 | 269 |
| 1 | 0 | 300 | 1 | catacombs | 6 | 17 | 13 | [] | 3.781 | 264 |
| 2 | 0 | 300 | 1 | catacombs | 6 | 17 | 13 | [] | 3.846 | 260 |

All 3 seeds report `ok=True`, `errors=[]`, `violations=[]`.  
Warnings: 5 per seed — `room 'ossuary_room_secret_18' is kind=secret but missing secret_wall` (pre-existing, non-blocking).

Playtest artifacts written to `runs/playtest-0.json`, `runs/playtest-1.json`, `runs/playtest-2.json`.

---

## Gate 2 — `tools.selftest`

**Result: FAIL — 20/22 passed, 2 failed**

**PASS (20):** python-version, dep-pygame-ce, dep-pillow, dep-numpy, palette-lock, content-schema, placeholder-art, game-import, game-layout, no-bare-random, rng-determinism, headless-run, module-attributes, end-screens, scene-sweep, audio-audit, glyph-coverage, rng-quality, deep-floors, golden-seed-regression

**FAIL (2):**

1. **atlas-format** — `assets/atlas/tiles.json: sheet assets/atlas/tiles.png has 147456 off-palette pixel(s)` (5 errors total)
2. **scene-legibility** — `only 79% of tiles are visible (need >= 85%) — the map is dark`

---

## Gate 3 — `tools.validate_data`

**Result: PASS — 12 files, 696 entries, 0 errors, 1 warning**

All 12 data files validate cleanly:
- affixes.json (70), audio.json (7), biomes.json (4), flavor.json (93), items.json (167), monsters.json (103), rooms.json (231), statuses.json (21)
- hq_rooms.json (0), meta_tree.json (0), npcs.json (0), storyline.json (0)

Warning: `quests.json: unrecognised content file` (contract section 4 does not list quests.json — pre-existing, not an error)

---

## Gate 4 — `tools.art.verify`

**Result: FAIL — 3 errors, 1 warning**

**Errors (3):**
1. `assets/sprites/ui/title_background.png: 1280x720 is not a multiple of the 32px tile grid`
2. `assets/atlas/tiles.json: sheet assets/atlas/tiles.png has 8200 off-palette pixel(s)` — off-palette #000000 ×8200 (nearest 'void' #0b0a10, distance 21.8)
3. (counted in atlas-format within selftest; art.verify reports the same tiles.png issue)

**Warning (1):**
- `assets/atlas/title.json: frame 'background' is 1280x720, not a tile-grid multiple`

Sprites checked: 657 in 2 dirs | Atlases: 11 (762 frames) | Aliases: 39

---

## Summary

| Gate | Result | Notes |
|------|--------|-------|
| Gate 1: game.main seeds 0-2 | **PASS** | All 3 seeds exit 0, violations=[] |
| Gate 2: selftest | **FAIL** | 20/22 — atlas-format (off-palette) and scene-legibility (dark map) |
| Gate 3: validate_data | **PASS** | 0 errors, 1 pre-existing warning |
| Gate 4: art.verify | **FAIL** | 3 errors — title_background.png grid size, tiles.png off-palette |

**Overall: 2/4 gates PASS**

Gate 1 (headless gameplay) is clean. Gate 3 (data) is clean. The two failures are art-related:
- `title_background.png` (1280×720) is a pre-existing title screen image issue, not a gameplay regression
- `tiles.png` off-palette pixels and scene-legibility (dark map) may indicate a regression in the tileset or lighting

---

## Round Protocol Compliance

- [x] `docs/PROGRESS.md` prepended with dated entry (2026-09-17)
- [x] `runs/reports/BUILD-2026-09-17-qa-gate.md` written
- [x] `docs/TICKETS.md` T-01 status updated
- [x] `docs/ROADMAP.md` ticked
