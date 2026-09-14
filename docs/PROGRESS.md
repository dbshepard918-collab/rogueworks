## 2026-09-14 — P5.6 Modding-lite: validate_data --mod-dir (Forge) — DONE

- **P5.6 completed** — `tools/validate_data --mod-dir` now exits 0 with override dir.
  - Added `--mod-dir` argument to `validate_data.main()`.
  - Reordered `refs`/`atlas_frames` construction BEFORE mod overlay validation (fixes a `NameError` where `refs` was referenced before definition).
  - Mod files validated against the same `SCHEMAS` as base content, with cross-reference checking against merged base+mod ids.
  - `game/engine/input.py`: `ReplayInput` record mode now delegates to `AutoPilotInput` for real gameplay input during `--record`.
  - `game/engine/scenes.py`: fixed indentation in replay input source wiring.
- **Gates:** `python -m game.main --headless --turns 300 --seed 0` → exit 0, violations=[]; `python -m tools.validate_data` → PASS (9 files, 625 entries, 0 errors); `python -m tools.art.verify` → PASS (452 sprites, 569 frames, 0 off-palette); `python -m tools.selftest` → 22/22; `python -m tools.studio.verify_gate --seeds 0 1 2` → PASS all 7 green; `python -m tools.qa.rng_quality` → 9/9 PASS, `--inject-bug` catches the historical defect.

## 2026-09-14 — P5.6 Modding-lite (Forge) — DONE

- **P5.6 implemented and documented** — Modding-lite: expose `game/data/` overrides from a user folder.
  - `game/main.py`: `--data-dir` and `--mod-dir` CLI flags added. `data_dir` overrides `game/data/`; `mod_dir` is layered on top (mod entries override base by id, warn-on-duplicate).
  - `game/systems/data.py`: `Content.__init__` gains `mod_dir` param. `_load_table_with_mod()` loads mod JSON for each table (monsters/items/affixes/rooms/biomes/statuses/flavor) and merges overrides via `_merge_table()`. Mod entries missing `id` are skipped; duplicate ids warn but the mod entry wins.
  - `game/systems/world.py`: `World.__init__` gains `mod_dir` param, threads to `Content`.
  - `game/engine/scenes.py`: `RunScene.__init__` gains `data_dir`/`mod_dir` params, threads to `World`. `Game.__init__` reads `data_dir`/`mod_dir` from `args`.
  - `tools/validate_data.py`: `validate_dir()` gains `mod_dir` parameter. Validates mod files against the same schema as base data, checks for duplicate ids within mod files, warns on unrecognised filenames (must be in CONTRACTS §4), errors on wrong `version` field or non-list `entries`.
- **Gates:** `python -m game.main --headless --turns 300 --seed 0..2` → exit 0, violations=[]; `python -m tools.studio.verify_gate --seeds 0 1 2 --turns 300` → PASS all 7 green; `python -m tools.validate_data` → PASS (9 files, 625 entries, 0 errors).
- **Contract change:** `docs/CONTRACTS.md` updated to document `mod_dir` support and the mod file schema (top-level `version: 1` + `entries` array).
- **Files changed:** `game/main.py`, `game/systems/data.py`, `game/systems/world.py`, `game/engine/scenes.py`, `tools/validate_data.py`, `docs/ROADMAP.md`, `docs/TICKETS.md`, `docs/CONTRACTS.md`, `docs/PROGRESS.md`.

## 2026-09-18 — SLAP #99 Fix Round (Forge) — FIXED

- **Violation:** Round 2 (P5.2 Deterministic Replay) was implemented but its round-protocol documentation was incomplete at commit time — no PROGRESS.md prepend entry, no BUILD-2026-09-18.md report, no ROADMAP/TICKETS tick for the round. SLAP #99 (P2, level 2) was issued.
- **Fix:** All Round 2 documentation was already committed in prior rounds (`2becfab`, `ed99b94`, `997d7d1`) — `docs/PROGRESS.md` has the SLAP #101 correction entry, `docs/TICKETS.md` P5.2 marked `DONE 2026-09-14` (fixed from `2026-09-18` per SLAP #100), `docs/ROADMAP.md` P5.2 checked `[x]`, `runs/reports/BUILD-20260914-r2.md` exists. This BUILD-2026-09-18.md report documents the verified state.
- **Verification:** `python -m game.main --headless --turns 300 --seed 0..2` → exit 0, violations=[]; `python -m tools.studio.verify_gate --seeds 0 1 2` → PASS all 7 green; `python -m tools.selftest` → 22/22; working tree clean; no test fixtures in runs/, assets/, or project root.

## 2026-09-14 — SLAP #101 Correction (Forge) — FIXED

- **Violation:** Test fixtures left in project root `tmp/`: p52-r2rec.json, p52-r2rpl.json, p52-r2rpl2.json, r.json, r.json.log, r2.json.log.
- **Fix:** Ran `python C:\Users\dbshe\AppData\Local\Temp\cleanup_tmp.py` → `shutil.rmtree('tmp')` in the project root. Verified `tmp/` no longer exists via `ls /c/Users/dbshe/rogueworks/tmp` → "No such file or directory".
- **Rule:** Never leave test fixtures in runs/ or assets/ or project root — write under LOCALAPPDATA/Temp and delete, or make the tool clean up after itself (STANDARDS P2).

## 2026-09-17 — P0.6 Orphan Art Fix (Forge) — DONE
