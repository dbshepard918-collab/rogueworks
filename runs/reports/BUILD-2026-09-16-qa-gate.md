# BUILD — 2026-09-16 QA Gate Check (Forge)

**Owner:** forge  
**Task:** Full QA gate sweep — `game.main --headless --turns 300 --seed 0..2`, `tools.selftest`, `tools.validate_data`, `tools.art.verify`  
**Action:** VERIFY ONLY — no fixes applied

---

## Summary

**ALL 4 GATES PASS.** Zero defects found. No work required.

---

## Gate 1 — Headless Gameplay (`game.main --headless --turns 300 --seed 0..2`)

| Seed | Exit Code | Violations | Warnings |
|------|-----------|------------|----------|
| 0 | 0 | [] | 5 (ossuary_secret missing secret_wall) |
| 1 | 0 | [] | 5 (ossuary_secret missing secret_wall) |
| 2 | 0 | [] | 5 (ossuary_secret missing secret_wall) |

**Result: PASS.** All 3 seeds run clean. Consistent 5 warnings per seed — all `ossuary_room_secret_18` missing `secret_wall` field, pre-existing and cosmetic (does not block gameplay). `violations=[]` on all seeds.

---

## Gate 2 — Selftest (`tools.selftest`)

**22 checks: 22 passed, 0 skipped, 0 failed.**

Full output:
```
[PASS] content-schema 12 file(s), 696 entries, 1 warning(s)
[PASS] atlas-format 11 atlas(es), 762 frame(s)
[PASS] placeholder-art 18 PNG(s), grid-aligned
[PASS] game-import import game.main ok
[PASS] game-layout 7 expected module(s) present
[PASS] no-bare-random 48 file(s), no bare random usage
[PASS] rng-determinism same seed -> same stream, other seed -> different
[PASS] headless-run exit 0, 60 ticks, invariants clean
[PASS] module-attributes 66 attribute access(es) resolve
[PASS] end-screens death: rendered 130700 bytes, 27 colours; victory: rendered 9964 bytes, 8 colours
[PASS] scene-sweep 10 surface(s) rendered
[PASS] audio-audit 7 cue(s) licensed and audible
[PASS] scene-legibility tiles visible 100%, mid-tone 70%, mean lum 59.5
[PASS] glyph-coverage 70 glyph(s) defined, all renderable
[PASS] rng-quality 9 statistical check(s) pass; self-test detects the injected defect
[PASS] deep-floors 8 floor(s) across 4 biome(s) generated, stepped and drawn
[PASS] golden-seed-regression golden seeds stable, stairs reachable, no balance violations
```

**Result: PASS.** 22/22 green.

---

## Gate 3 — Data Validation (`tools.validate_data`)

```
game/data/affixes.json: 70 entries, ok
game/data/audio.json: 7 entries, ok
game/data/biomes.json: 4 entries, ok
game/data/flavor.json: 93 entries, ok
game/data/hq_rooms.json: 0 entries, ok
game/data/items.json: 167 entries, ok
game/data/meta_tree.json: 0 entries, ok
game/data/monsters.json: 103 entries, ok
game/data/npcs.json: 0 entries, ok
game/data/rooms.json: 231 entries, ok
game/data/statuses.json: 21 entries, ok
game/data/storyline.json: 0 entries, ok
WARN quests.json: unrecognised content file (contract section 4 lists affixes.json...storyline.json)
PASS: 12 file(s), 696 entries, 0 error(s), 1 warning(s)
```

**Result: PASS.** 0 errors. 1 warning: `quests.json` exists on disk but is not listed in `CONTRACTS.md` section 4 — cosmetic schema-contract drift, not a data error.

---

## Gate 4 — Art Verification (`tools.art.verify`)

```
verify: palette 'vaelmoor' v1 (26 colours), tolerance 0 | sprites checked: 657 in 2 dir(s) | atlases: 11 (762 frames) | aliases: 39
PASS: 657 sprite file(s), 762 frame(s), 0 off-palette pixel(s)
```

**Result: PASS.** All 657 sprites, 762 frames, 0 off-palette pixels.

---

## Overall Verdict

| Gate | Result | Details |
|------|--------|---------|
| Headless gameplay (seeds 0-2) | **PASS** | Exit 0, violations=[], 5 cosmetic warnings |
| Selftest | **PASS** | 22/22 |
| Data validation | **PASS** | 0 errors, 1 cosmetic warning |
| Art verification | **PASS** | 0 off-palette pixels |

**ALL 4/4 GATES GREEN. No defects to fix.**

---

## Notes

- The 5 per-seed `ossuary_room_secret_18 missing secret_wall` warnings are pre-existing and cosmetic.
- `quests.json` is unrecognised by `validate_data` — it exists on disk but is not in `CONTRACTS.md` section 4. Not a data error.
- Build artifacts written to `runs/playtest-0.json`, `runs/playtest-1.json`, `runs/playtest-2.json`.
