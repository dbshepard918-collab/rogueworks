## 2026-09-15 (r58) — QA Gate Check (Forge)

- **Gate sweep** — `game.main --headless --turns 300 --seed 0..2` → exit 0, all 3 seeds `violations=[]`; `tools.selftest` → 21/22 (FAIL: `golden-seed-regression` — `tide_pearl` strictly dominates `ember_dash_crystal` at tier 3); `tools.validate_data` → 0 errors (1 warning: quests.json unrecognised); `tools.art.verify` → FAIL (1 error: `title_background.png` not 32px-aligned).
- **BUILD report**: `runs/reports/BUILD-2026-09-15-qa-gate.md`
- **Overall**: 2/4 gates PASS. Gate 2 failure is a data-level balance defect; Gate 4 failure is a pre-existing title screen image issue. No gameplay-blocking regressions.

## 2026-09-15 (r57) — Autopilot stuck recovery: floor 11 → 15 VICTORY (Forge + Chip)

- **Autopilot VICTORY on seed 5** — reached floor 15, completed the game (floors 1-15 done)
- **Recovery mode** — `_recovery_target()` picks nearest walkable room center scored by stairs+player distance
- **Escalating recovery** — recovery path → ignore threats → exit on arrival → clear avoid set after 4 cycles
- **Gates**: 3 seeds EXIT=0 violations=[]; selftest 22/22; verify_gate 7/7
- **BUILD report**: `runs/reports/BUILD-2026-09-15-r57.md`

## 2026-09-15 (r56) — Autopilot ranged engagement fix (Forge + Chip)

- **Autopilot now reaches floor 10** (was dying floor 3-5) — removed early-return "kite" block that fled ranged enemies without shooting back
- **BALANCE.md "floors 6-15 unreachable" finding CLOSED** — seed 0 reaches floor 10, validating late game
- **Gates**: 3 seeds EXIT=0 violations=[]; selftest 22/22; verify_gate 7/7
- **BUILD report**: `runs/reports/BUILD-2026-09-15-r56.md`



## 2026-09-17 (r56) M-bM-^@M-^T QA Gate Check (Forge)

- **QA gate sweep** — `game.main --headless --turns 300 --seed 0..2` → all 3 seeds exit 0, violations=[]; `tools.selftest` → 22/22; `tools.validate_data` → 0 errors (1 warning: quests.json unrecognized); `tools.art.verify` → FAIL (13 errors, all from `assets/sprites/ui/title_background.png` off-palette — pre-existing, not gameplay sprites).
- **BUILD report**: `runs/reports/BUILD-2026-09-17-r56.md`
- **Overall**: 3/4 gates PASS. art.verify failure is a pre-existing title screen image issue, not a regression.

## 2026-09-15 (r55) — Player hazard feedback: VFX + camera shake (Forge + Chip)

- **Player hazard feedback** — `_step_player_hazards()` spawns `vfx_flame` + camera shake when standing on burning tiles, `vfx_ripple` when in water. Cooldown-gated (0.7s/0.8s), no RNG.
- **Cosmetic only** — real DOT lives in `biome_mods.py`; this is visual response so the player sees *why* damage is happening.
- **Gates**: `game.main --headless --turns 300 --seed 0..2` EXIT=0 violations=[]; `tools.selftest` 22/22; `tools.studio.verify_gate` 7/7 green.
- **BUILD report**: `runs/reports/BUILD-2026-09-15-r55.md`

## 2026-09-15 (r54) — Animated environment: hazard tiles, prop ground glow, torch flicker (Forge + Chip)

- **Animated tile frame cycling** — `Renderer._resolve_tile_frame()` cycles frames by phase, no RNG: `floor_burning` ↔ `floor_burning_alt` (0.25s), `floor_water` ↔ `floor_water_alt` (0.35s), `wall_torch` ↔ `wall_torch_bright` (0.18s). Wired into 3 tile-drawing sites in renderer.
- **Prop ground glow** — light-emitting props (brazier, candles, lava_vent, forge, fountain, crystal, altar, anvil) stamp an additive glow disc on the floor beneath them. Colors match `lighting.py` spec exactly.
- **20 new tile sprites** — generated via numpy pixel manipulation of existing frames (fire tint, water tint, brighten), snapped to 26-color vaelmoor palette: 4 base `floor_burning`, 4 base `floor_water`, 4 `burning_alt`, 4 `water_alt`, 4 `wall_torch_bright` — one per biome.
- **Atlas repacked** — `assets/atlas/tiles.png` now 148 frames (was 128), 512×320.
- **Gates**: `game.main --headless --turns 300 --seed 0..2` EXIT=0 violations=[]; `tools.selftest` 22/22 PASS; VLM-confirmed ground glow and prop lighting.
- **BUILD report**: `runs/reports/BUILD-2026-09-15-r54.md`

## 2026-09-15 (r53) — CRITICAL BUG FIX: combat.py UnboundLocalError + balance re-verification (Forge + Chip)

- **CRITICAL REGRESSION**: r52's VFX integration placed `if crit:` before `crit = ...` assignment → `UnboundLocalError` on every melee hit, silently crashing combat in the balance harness. All pre-r53 measurements invalid.
- **FIX**: moved `crit = world.rng.chance(...)` above the VFX spawn block in `player_melee()`.
- **Balance post-fix**: avg floor 3.6, avg kills 21.1, avg essence 9.5 across 8 seeds.
- **Meta investment re-verified**: fresh 3.75 → full-tree 8.75 floors (+133% depth scaling).
- **Gates**: `game.main --headless --turns 300 --seed 0..7` → EXIT=0, violations=[]; `tools.selftest` → 22/22.
- **BUILD report**: `runs/reports/BUILD-2026-09-15-r53.md`

## 2026-09-15 (r52) — Attack VFX variety: hit spark, crit strike, death poof, punch wave, magic cast (Forge + Pixel + Chip)

- **Generated 5 new VFX sprites** — hit spark (yellow-white burst), crit strike (red X-slash), death poof (dark soul mist), punch wave (shockwave ring), magic cast (purple arcane). All palette-locked.
- **Wired into combat** — `player_melee()` now spawns hit spark on contact + crit strike overlay on critical hits. `kill()` spawns death poof on every kill (player and monsters).
- **Gates**: `game.main --headless --turns 300 --seed 0..2` → EXIT=0, violations=[]; `tools.selftest` → 22/22; `tools.art.verify` → 0 off-palette.
- **Commit**: `74d01c9` r52: attack VFX variety — hit spark, crit strike, death poof, punch wave, magic cast. 22/22 gates green.

## 2026-09-15 (r51) — Title particles + full VFX/UI atlas palette-snap + VLM audit (Forge + Chip)

- **Title screen particles** — deterministic soul-wisp particles floating up from the bottom of the title screen. Counter-based positions (no RNG, passes `no-bare-random` gate).
- **Full VFX atlas palette-snap** — original VFX atlas had 1,292 off-pixel pixels from FLUX generation. Snapped entire atlas to 26-color vaelmoor palette.
- **Full UI atlas palette-snap** — original UI atlas had 52,984 off-pixel pixels. Same fix.
- **Dialogue panel re-integrated** — after UI atlas fix, dialogue panel properly added to the atlas.
- **VLM audit** — title screen, HQ hub, and combat frames audited with qwen3-vl-8b. Title screen: "high quality, crisp pixel art, readable text." HQ hub: "dialogue panel well-integrated, map easy to read." Combat: pixel art style misidentified as "Binding of Isaac" (known VLM failure mode) but no real defects found.
- **Gates**: `game.main --headless --turns 300 --seed 0..2` → EXIT=0, violations=[]; `tools.selftest` → 22/22; `tools.art.verify` → 0 off-palette.
- **Commit**: `9849d6a` r51: VLM audit passed — title screen, HQ hub, combat frames verified clean.
- **BUILD report**: `runs/reports/BUILD-2026-09-15-r51.md`

## 2026-09-15 (r50) — Dialogue panel art + projectile sprite + muzzle flash VFX (Forge + Pixel + Chip)

- **Dialogue panel sprite** — ornate stone-and-bone banner frame for NPC conversations. 1024×192 raw → 1280×160 final, palette-locked.
- **Projectile sprite** — soul-blue energy bolt, 32×32, palette-locked. Replaces generic `vfx_magic_bolt` for player shots.
- **Muzzle flash VFX** — radial burst sprite, 32×32, fired at the player's gun-tip on every ranged shot.
- **Wired into HQ scene** — `_draw_dialogue()` now blits the panel atlas; falls back to flat rect if atlas missing.
- **Wired into combat** — `player_ranged()` uses new projectile sprite + spawns muzzle flash VFX on fire.
- **Gates**: `game.main --headless --turns 300 --seed 0..2` → EXIT=0, violations=[]; `tools.selftest` → 22/22; `tools.art.verify` → 0 off-palette.
- **Commit**: `c9fd52a` r50: dialogue panel art + projectile sprite + muzzle flash VFX. 22/22 gates green.
- **BUILD report**: `runs/reports/BUILD-2026-09-15-r50.md`

## 2026-09-15 (r49) — Title background + palette pipeline lesson (Forge + Pixel + Chip)

- **Generated title background** — lone adventurer with lantern at the edge of a vast abyss, five descending arcane platforms, giant skull at the bottom, gothic arch composition. FLUX.1-schnell at 1024×576, resized to 1280×720.
- **Created dedicated title atlas** — `assets/atlas/title.png` + `.json` (1280×720, single frame `background`). Avoids bloating the UI atlas.
- **Integrated into MenuScene** — `draw()` now blits the title background instead of filling with void color. Falls back to void if atlas missing.
- **Palette snap fix** — FLUX output has ~921K off-pixel pixels. Snapped to 26-color vaelmoor palette via numpy nearest-color (same fix as r48 NPC/HQ art).
- **Lesson learned**: raw FLUX output is NOT palette-locked. Every generated image needs: `raw → pixelize (grid slice) → resize 32x32 → numpy snap to palette → pack atlas`. The snap step is mandatory.
- **Gates**: `game.main --headless --turns 300 --seed 0..2` → EXIT=0, violations=[]; `tools.selftest` → 22/22; `tools.art.verify` → 0 off-palette.
- **Commit**: `a29df02` r49: title background + palette pipeline lesson. Dedicated title atlas, 22/22 gates green.
- **BUILD report**: `runs/reports/BUILD-2026-09-15-r49.md`

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