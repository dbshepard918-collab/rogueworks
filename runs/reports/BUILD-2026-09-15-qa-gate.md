# QA Gate Check — 2026-09-15

## Commands run

| Gate | Command | Exit | Result |
|---|---|---|---|
| 1. Headless run | `.venv/Scripts/python.exe -m game.main --headless --turns 300 --seed 0..2` | 0 | **PASS** — all 3 seeds `ok=True, violations=[]` |
| 2. Selftest | `.venv/Scripts/python.exe -m tools.selftest` | 1 | **FAIL** — 21/22; `golden-seed-regression` balance issue |
| 3. Data validation | `.venv/Scripts/python.exe -m tools.validate_data` | 0 | **PASS** — 688 entries, 0 errors, 1 warning |
| 4. Art verify | `.venv/Scripts/python.exe -m tools.art.verify` | 1 | **FAIL** — `title_background.png` not tile-grid-aligned |

## Gate 1: Headless run — PASS

All three seeds (0, 1, 2) completed 300 ticks exiting cleanly:
- Seed 0: floor 1, catacombs, 48x33, 6 rooms, 17 entities, 13 monsters, `ok=True, violations=[]`
- Seed 1: floor 1, catacombs, 48x34, 6 rooms, 17 entities, 13 monsters, `ok=True, violations=[]`
- Seed 2: floor 1, catacombs, 48x32, 6 rooms, 17 entities, 13 monsters, `ok=True, violations=[]`
- Warnings (not violations): `room 'ossuary_room_secret_18' is kind=secret but missing secret_wall` (pre-existing)
- ms_per_tick: 4.211 / 4.115 / 4.391; fps_equiv: 237 / 243 / 228

## Gate 2: Selftest — FAIL (21/22)

21 checks pass. 1 failure:
- **`golden-seed-regression`**: balance tier 3 `tide_pearl` strictly dominates `ember_dash_crystal` (better on armor/crit/damage/luck/max_hp/speed, no more expensive)
- This is a data-level balance defect — `tide_pearl` is strictly better than `ember_dash_crystal` at the same tier with no downside. Needs a lore fix (adjust `tide_pearl` stats or `ember_dash_crystal` value).

## Gate 3: Data validation — PASS

All 12 content files validate:
- affixes.json: 70 entries ok
- audio.json: 7 entries ok
- biomes.json: 4 entries ok
- flavor.json: 93 entries ok
- hq_rooms.json: 0 entries ok
- items.json: 167 entries ok
- meta_tree.json: 0 entries ok
- monsters.json: 95 entries ok
- npcs.json: 0 entries ok
- rooms.json: 231 entries ok
- statuses.json: 21 entries ok
- storyline.json: 0 entries ok
- **0 errors**, 1 warning: `quests.json` unrecognised content file (not in CONTRACTS §4 list)

## Gate 4: Art verify — FAIL

1 error:
- `assets/sprites/ui/title_background.png: 1280x720 is not a multiple of the 32px tile grid`
- 657 sprites checked, 11 atlases (774 frames), 39 aliases
- This is a pre-existing issue with the title screen image only — all gameplay sprites pass palette and grid checks.

## Summary

- **PASS**: Gate 1 (headless), Gate 3 (data validation)
- **FAIL**: Gate 2 (selftest — balance regression: tide_pearl > ember_dash_crystal)
- **FAIL**: Gate 4 (art.verify — title_background.png not 32px-aligned)
- **Overall**: 2/4 gates PASS, 2/4 FAIL. No gameplay-blocking issues; both failures are pre-existing or data-level.
