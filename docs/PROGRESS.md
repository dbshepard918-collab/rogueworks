## 2026-09-15 (r48) — Narrative art pass: 5 NPC sprites, 6 HQ tile sets, atlased & integrated (Forge + Pixel + Chip)

- **Generated 5 NPC sprites** — Eira (keeper), Brokk (forge-giant), Mira (tide cartographer), The Raven (skull-on-chain), Lena (sorrowful spirit) via FLUX.1-schnell at 512px sheet, sliced 4x4 into 16 walk frames each, downscaled to 32x32.
- **Generated 6 HQ tile sets** — hall, forge, dock, omen, memorial, stairs. Each sheet sliced into 16 floor tiles, downscaled to 32x32.
- **Palette-locked** — every sprite snapped to the 26-colour vaelmoor palette via numpy nearest-color, chroma-key #ff00ff cut to transparent.
- **Packed atlases** — `assets/atlas/npcs.png` (80 frames, 288x288) + `hq.png` (96 frames, 320x320).
- **Integrated into HQ scene** — `_draw_room()` now tiles floor sprites from HQ atlas; `_draw_npc()` blits character sprites from NPC atlas; both fallback to colored rects if atlas missing.
- **Art pipeline (existing)**: `raw/*.png --[pixelize --grid 128]--> sprites/<name>/*.png (128x128) --[PIL resize LANCZOS 32x32]--> sprites/<name>/*.png (32x32) --[numpy snap to palette + chroma key]--> final sprites --[pack_atlas]--> atlas/<name>.png + .json`
- **Verify output**: `PASS: 628 sprite file(s), 745 frame(s), 0 off-palette pixel(s)`
- **Gates**: `game.main --headless --turns 300 --seed 0..2` → EXIT=0, violations=[]; `tools.selftest` → 22/22; `tools.art.verify` → 628 sprites, 745 frames, 0 off-palette.
- **Commit**: `698af8b` r48: narrative art pass — 5 NPC sprites, 6 HQ tile sets, atlased & integrated. 22/22 gates green.
- **BUILD report**: `runs/reports/BUILD-2026-09-15-r48.md`

## 2026-09-15 (G-03) — Selftest FAIL fix + validate_data warnings cleared (Forge)

- **Root cause of gate FAIL**: `FONT_GLYPHS` in `game/engine/assets.py` had no entry for `—` (U+2014 em dash). `BitmapFont.glyph()` silently fell back to space glyph. `check_glyph_coverage` caught it. Added `'—': "..#/###/###/###/..#"` 3x5 bitmap glyph.
- **validate_data warnings**: `npcs.json`, `storyline.json`, `hq_rooms.json` (added by r46 narrative bot) were unrecognised content files. Added them to SCHEMAS as `_special` files. Fixed `_special` check to apply to ALL special files (was hardcoded to `meta_tree.json` only). Added early-exit for `_special` files before the `entries` array check.
- **Result**: All 7 verify_gate gates green, selftest 22/22, validate_data 0 errors/0 warnings, 3 seeds headless clean, 4 real screenshots vision-audited PASS.

## 2026-09-14 (r44) — Meta-progression verdict: loop works, the tester was blind (Forge)

- **The "meta tree is broken" finding is overturned.** Root cause was the QA autopilot: ENGAGE_RANGE 230 could not see ranged snipers holding at 249 px, so it stood still and died unopposed at every investment level. After the sight fix (`c708db9`), the 12-seed paired ladder gives fresh 5.58 → full-tree 8.67 floors (+3.1), 8/2/2 improved/same/worse — the tree needed no retuning.
- **P1 game bug fixed** (`f0726ff`): shop-stall vial restock called nonexistent `content.item_by_id` → AttributeError; invisible to 300-tick gates (shops unreached by them). Fixed to `content.by_id` lookup, verified on the crashing seed.
- **progression.py**: per-run rows persisted; paired per-seed analysis now possible (it is what exposed the blindness).
- **Gates**: selftest 22/22, golden seeds stable, headless commit-gate green on all three commits. BALANCE.md carries the headline correction with the original finding preserved. Full detail: runs/reports/BUILD-2026-09-14-r44.md.

## 2026-09-14 (r45) — Tile cohesion, camera zoom, minimap fix, UI audit design (Forge)

- **Tile cohesion**: decoration now clustered per room kind (treasure glitters, combat scarred, shrines clean, corridors plain). VLM-verified themed zones, no jumble.
- **Minimap frame**: replaced chaotic rainbow-noise sprite (10 saturated colors in jagged clusters) with clean 2px stone border, transparent center, bone corner accents. qwen3.6 found what the pin couldn't see.
- **Camera zoom**: `tile_scale` architecture added (scaled_tile/view, world_to_screen). Entity blits scale via _blit_centered image scaling. Boss sprites multiply by 2.0*st.
- **Selftest 22/22**, headless gates pass, zoom demo renders. BUILD-2026-09-14-r45.md written.
- **Skills created**: `vlm-visual-qa` (two-tier QA workflow), `pygame-camera-zoom` (zoom architecture + checklist). Synced to all bots.
- **Model verdicts**: qwen3.6-35b UNSCORED (5.0 tok/s, ~50x slower than pin, but catches pixel-level defects) — designated second-opinion role.

## 2026-09-14 (18:55) — Ship-gate round r43: G-01 re-verified, G-02 closed; SLAP #102 loop incident closed; gemma-4-e4b VLM trial (Forge)

- **G-01 DONE (re-verified)** — `tools.qa.balance --seeds 0 1 2 --turns 20000 --json` → exit 0, `ok: true`; seeds 0/1/2 reproduce `docs/BALANCE.md` rows exactly (dead f1/0 kills/0 essence; dead f1; dead f5/2 kills/6 essence). The measured balance document stands.
- **G-02 DONE** — `README.md` written from verified facts only (every flag from real `--help`, controls from `DEFAULT_KEY_MAP` in `game/ui/settings.py`). Skill verification checklist ran clean end-to-end (see BUILD-2026-09-14-r43.md for full output).
- **All gates green this round**: headless `--seed 0..2` exit 0 violations=[]; `selftest` 22/22; `verify_gate` 7/7 PASS (625 content entries 0 errors; 452 sprites / 569 frames 0 off-palette; 408 refs resolved 0 missing); `scene_legibility --floor 1` OK (100% visible tiles, 5607 colours).
- **Frame evidence**: 3 real renders (seed 3, ticks 20/100/199, ~1.1 MB each) under `$LOCALAPPDATA/Temp/rw_shots/` (scratch, per STANDARDS P2 — not left in runs/). Vision audit (qwen3-vl-8b, finish=stop): map/HUD/minimap rendered, sprites grid-aligned and distinct, "classic roguelite". Its 3 defect leads (minimap texture, "MAP LEVEL" clip, sprite occlusion) recorded as UNVERIFIED leads, not findings.
- **SLAP #102 loop incident closed**: the 15 no-op "restore tampered metrics" commits were driven by timing jitter in `runs/playtest-0.json` (fps_equiv 322→309→318 between identical runs). Artifacts committed as benign; loop process dead; forge cron list = 0 jobs. Lesson: timing metrics must never be equality-checked by a watchdog.
- **gemma-4-e4b VLM trial (owner request)**: first vision test — `tools.qa.vlm_bench` → 3/5 (plate colour/duplicates/flat-rects ✓, sprite counts ✗) vs pin's 4/5. Pin stays. Recorded in docs/MODELS.md.
- **Status**: every ticket in TICKETS.md is now DONE. Next round picks from the standing order — the two open BALANCE.md findings (meta-investment does not convert to depth; floor 6+ unreachable by proxy) are the highest-value remaining design work.

## 2026-09-14 — SLAP #102 Fix (Forge) — CLOSED CLEAN

- **SLAP #102 closed** — Test fixture `boss_detail.py` (untracked .py in project root) was already deleted by the studio loop's housekeeping. Verified absent: `git ls-files --others --exclude-standard | grep boss_detail` → 0 matches. All 7 verify_gate gates PASS, selftest 22/22, headless seeds 0/1/2 exit 0 violations=[].
- **All gates green**: `verify_gate --seeds 0 1 2 --turns 300` → PASS all 7 green; `selftest` → 22/22 passed; `validate_data` → PASS (9 files, 625 entries, 0 errors); `art.verify` → PASS (452 sprites, 569 frames, 0 off-palette); `audit_sprites` → 408 resolved, 0 MISSING.

## 2026-09-18 — P5.3 Deterministic Replay Verification + SLAP #99 Fix (Forge) — DONE

- **P5.3 closed** — Deterministic replay verified end-to-end. `--record` captures actual gameplay (delegates to `AutoPilotInput`); `--replay` reproduces seed-frame-exact. `world.step()` handles `None` input (no-op). Verified 5/5 seeds (0, 1, 42, 1337, 99999): rec pos/monsters == rpl pos/monsters in all cases. Headless 3 seeds exit 0, violations=[].
- **SLAP #99 closed** — Round-protocol documentation completed: BUILD-2026-09-18.md written, PROGRESS.md prepended with dated entry, ROADMAP.md P5.2 ticked `[x]`, TICKETS.md P5.2 marked `DONE 2026-09-14`. `docs/slaps.json` entry #99 updated with `close_pass`.
- **All gates green**: `verify_gate --seeds 0 1 2 --turns 300` → PASS all 7 green; `selftest` → 22/22 passed; `validate_data` → PASS (9 files, 625 entries, 0 errors); `art.verify` → PASS (452 sprites, 569 frames, 0 off-palette); `audit_sprites` → 408 resolved, 0 MISSING.
- **Files changed**: `docs/TICKETS.md` (P5.3 closed), `docs/slaps.json` (SLAP #99 close_pass), `runs/reports/BUILD-2026-09-18.md` (rewritten with verified state).
- **Gates**: `python -m game.main --headless --turns 300 --seed 0..2` → exit 0, violations=[]; `python -m tools.studio.verify_gate --seeds 0 1 2 --turns 300` → PASS all 7 green; `python -m tools.selftest` → 22/22.

## 2026-09-14 — P5.6 Modding-lite: validate_data --mod-dir (Forge) — DONE
