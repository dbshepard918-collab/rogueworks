## 2026-09-14 — P5.6 Modding-lite (Forge) — DONE

- **P5.6 implemented and documented** — Modding-lite: expose `game/data/` overrides from a user folder.
  - `game/main.py`: `--data-dir` and `--mod-dir` CLI flags added. `data_dir` overrides `game/data/`; `mod_dir` is layered on top (mod entries override base by id, warn-on-duplicate).
  - `game/systems/data.py`: `Content.__init__` gains `mod_dir` param. `_load_table_with_mod()` loads mod JSON for each table (monsters/items/affixes/rooms/biomes/statuses/flavor) and merges overrides via `_merge_table()`. Mod entries missing `id` are skipped; duplicate ids warn but the mod entry wins.
  - `game/systems/world.py`: `World.__init__` gains `mod_dir` param, threads it to `Content`.
  - `game/engine/scenes.py`: `RunScene.__init__` gains `data_dir`/`mod_dir` params, threads to `World`. `Game.__init__` reads `data_dir`/`mod_dir` from `args`.
  - `tools/validate_data.py`: `validate_dir()` gains `mod_dir` parameter. Validates mod files against the same schema as base data, checks for duplicate ids within mod files, warns on unrecognised filenames (must be in CONTRACTS §4), errors on wrong `version` field or non-list `entries`.
- **Gates:** `python -m game.main --headless --turns 300 --seed 0..2` → exit 0, violations=[]; `python -m tools.studio.verify_gate --seeds 0 1 2 --turns 300` → PASS all 7 green; `python -m tools.validate_data` → PASS (9 files, 625 entries, 0 errors).
- **Contract change:** `docs/CONTRACTS.md` updated to document `mod_dir` support and the mod file schema (top-level `version: 1` + `entries` array).
- **Files changed:** `game/main.py`, `game/systems/data.py`, `game/systems/world.py`, `game/engine/scenes.py`, `tools/validate_data.py`, `docs/ROADMAP.md`, `docs/TICKETS.md`, `docs/CONTRACTS.md`, `docs/PROGRESS.md`.

## 2026-09-17 — P0.6 Orphan Art Fix (Forge) — DONE
