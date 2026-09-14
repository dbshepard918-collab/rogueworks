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
