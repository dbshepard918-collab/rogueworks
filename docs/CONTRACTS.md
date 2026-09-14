# Roguelite — Interface Contracts v1

**Frozen interfaces between bots.** Change a contract deliberately: update this file in the same
commit as the code, and say so in your report. Silent renames are the one unforgivable act here.

Project root: `C:\Users\dbshe\rogueworks` — Python 3.11, pygame-ce 2.5.8, venv `.venv`.

## 1. Layout

```
game/
  main.py           # CLI entry: python -m game.main [...]
  engine/           # loop, input, camera, renderer, scene stack, particles
  entities/         # player, monster, projectile, pickup, player as data-driven actors
  systems/          # rng, procgen, combat, statuses, loot, ai, spawn, meta, save
  data/             # content JSON written by `lore`
  ui/               # HUD, minimap, inventory, menus, tooltips
tools/
  art/              # pixelize.py, pack_atlas.py, verify.py
  qa/               # shot.py, scripted_run.py
  validate_data.py  # content schema validator
  selftest.py       # imports + invariant smoke test
assets/
  raw/              # untouched AI output (never shipped)
  sprites/          # palette-locked, grid-aligned PNGs
  atlas/            # <name>.png + <name>.json
  placeholder/      # flat-colour fallbacks so the game always runs
  palette.json      # THE locked palette
runs/               # playtest-N.json, shots/*.png, reports/QA-*.md
docs/               # GDD.md, CONTRACTS.md, TICKETS.md, ASSETS.md, CONTENT.md
```

## 2. Base units

- Tile grid **32x32 px**. Window **1280x720** (40x22.5 tiles visible). Tile coordinates are integers
  `(tx, ty)`; world pixels = tile * 32. Sprites are exact multiples of 32.
- Simulation is **fixed timestep 60 Hz** (`1/60` s), decoupled from rendering. All gameplay logic
  advances only in `world.step(dt)`; the renderer is pure.
- **All randomness** comes from `game.systems.rng.RNG` — `RNG(seed)` exposing
  `.randint/.random/.choice/.shuffle/.weighted(pairs)`. `--seed N` fully reproduces a run:
  same floor layout, same spawns, same loot. No bare `random` anywhere in `game/`.

## 3. Game CLI (stable — QA and chip both depend on it)

```
python -m game.main [options]
  --seed SPEC           run seed(s): INT, range 0..7, stepped 0..7..2, list 0,3,7 (default 0)
  --daily               daily seeded run (seed = YYYYMMDD from today's date)
  --curses IDS          comma-separated curse ids to apply at run start
  --endless             endless mode: continue past floor 15 with escalating difficulty
  --headless            no window, SDL dummy driver (QA + CI path)
  --turns INT           headless: max simulation steps (default 300)
  --script PATH         scripted-input JSON (see 3.2)
  --shot PATH[,PATH...] render frames at those tick numbers to PNGs
  --shot-dir DIR        directory for --shot output (default runs/shots)
  --floor INT           start on floor N (debug)
  --new-run             ignore save, start a fresh run
  --log PATH            write the run summary JSON (default runs/playtest-<seed>.json)
  --save PATH           profile path (default save.json)
  --frames INT          windowed mode: stop after N frames (debug)
```
Exit code **0** iff the run completed without an unhandled exception. Any traceback = non-zero.
`--headless` never opens a window and never depends on a GPU.

**`--seed` accepts a range** (added 2026-09-13). `--seed 0..2` runs seeds 0, 1, 2 in sequence and
exits 0 only if every seed did; `0..8..2` steps by two and `0,3,7` is an explicit list. The
shorthand exists because the gate commands are *written* that way — a documented command that
cannot run is a bug with no way to notice it. Each seed re-reads the profile from disk, so a range
reproduces sequential single-seed invocations exactly (all summary keys identical except the
wall-clock `metrics` block). With a range, one `--log` path becomes one file per seed
(`NAME-seed0.json`, `NAME-seed1.json`, ...); without `--log` the default per-seed
`runs/playtest-<seed>.json` already separates them. Ranges apply to `--headless` runs only.

### 3.1 Run summary JSON (exact top-level keys)

```json
{
  "ok": true, "seed": 1234, "ticks": 300, "biome": "catacombs", "floor": 3,
  "player": {"hp": 62, "max_hp": 80, "level": 4, "xp": 120, "gold": 340, "essence": 12,
             "kills": 27, "items": ["rusty_blade", "leather_cap"], "statuses": ["poison"],
             "pos": [21, 14]},
  "world": {"entities": 41, "monsters": 18, "projectiles": 3, "pickups": 7,
              "rooms": 9, "level_w": 64, "level_h": 48,
              "spawn_tile": [21, 14], "stairs_tile": [30, 40],
              "tiles": "hex-encoded tile grid, one row per semicolon segment; 0=floor, 1=wall, 2=stairs, 6=door, 8=cracked_wall, 9=hidden_door"},
  "metrics": {"frames": 300, "ms_per_tick": 0.41, "fps_equiv": 2439},
  "endless": false, "curses": [],
  "errors": [], "invariants": {"violations": []}
}
```
`invariants.violations` is a list of strings; it MUST be empty for a passing run. Assert at minimum:
no entity outside level bounds; player hp within `[0, max_hp]`; no duplicate entity ids; every floor's
stairs reachable from spawn (BFS over walkable tiles, cap 20 000 visited); item ids exist in
`game/data/items.json`; no `None` in a render list.
`stairs_tile` and `spawn_tile` are `[tx, ty]` tile coordinates; `tiles` encodes the full
tile grid so regression checks can verify reachability via BFS.

### 3.2 Scripted input JSON

```json
{"name": "smoke", "steps": [{"tick": 0, "move": [1,0], "actions": ["attack"]},
                            {"tick": 45, "move": [0,-1], "actions": ["dash"]}]}
```
Unspecified ticks repeat the last action vector. `move` is a unit-ish vector in `[-1,1]^2`.

## 4. Content JSON (owned by `lore`, validated by `tools.validate_data`)

All files are a JSON **object** with `{"version": 1, "entries": [ ... ]}`; arrays of objects; ids
`snake_case`, unique per file, stable across regenerations.

| File | Required fields per entry |
|---|---|
|| `game/data/monsters.json` | `id`, `name`, `biome`, `tier`(1-5), `hp`, `damage`, `armor`, `speed`(0.2-3.0), `xp`, `weight`, `behavior`(`chaser`\|`ranged`\|`ambusher`\|`brute`\|`summoner`\|`shielded`\|`teleporter`\|`charger`\|`splitter`\|`runner`), `sprite`(atlas frame name), `status_on_hit`(id or null), `telegraph_duration`(float, seconds of windup before attack, 0.25-0.55), `telegraph_sprite`(vfx atlas frame name for the windup indicator), optional `element`(`physical`\|`fire`\|`water`\|`ice`\|`lightning`\|`poison`\|`shadow`\|`holy`\|`wind`\|`earth`), optional `shield_angle`(float), optional `summon_count`(int), optional `leap_range`(float), optional `split_count`(int), optional `phases`(array of phase objects — boss multi-phase fights), optional `enrage`(object — enrage mechanic), optional `minibosses`(array of string monster ids — adds that spawn with this boss), optional `hazards`(array of strings — hazard type names) |
|| `game/data/items.json` | `id`, `name`, `slot`(`weapon`\|`armor`\|`trinket`\|`consumable`), `tier`(1-5), `effect`(`{stat: value}` from `damage,armor,max_hp,speed,luck,crit`), `value`(gold), `sprite`, `flavor`, `unique`(optional, string — one of `pierce`/`chain`/`reflect`/`lifesteal`/`death_spark`/`purifier`/`dash_fire`/`poison_on_hit`/`frost_bite`/`storm_call`/`bone_crusader`/`void_step`/`soul_harvest`/`molten_core`/`thorn_vine`/`gravity_weight`/`shadow_veil`/`star_forge`; marks a build-defining legendary), optional `element`(`physical`\|`fire`\|`water`\|`ice`\|`lightning`\|`poison`\|`shadow`\|`holy`\|`wind`\|`earth`) |
| `game/data/affixes.json` | `id`, `name`, `effect`(same stat map), `tier_min`, `tier_max`, `weight` |
| `game/data/rooms.json` | `id`, `biome`, `kind`(`combat`\|`treasure`\|`shrine`\|`shop`\|`boss`\|`entrance`\|`secret`\|`gambling`\|`blacksmith`\|`fountain`\|`omen`), `w`, `h`(5-24), `spawn_budget`, `props`(list of strings) |
||| `game/data/biomes.json` | `id`, `name`, `tileset`(atlas prefix), `monsters`(list of monster ids), `ambient`(`[r,g,b]`), `fog`(0.0-1.0), `music`(string or null), `modifier`(biome modifier id or null — one of `catacombs_darkness`\|`ember_heat`\|`drowned_water`\|`ossuary_toxic`), `secret_rooms`(list, optional), `ambient_sound`(dict, optional — `{frequency, pattern, volume}`), `attenuation`(dict, optional — `{min_distance, max_distance, rolloff}`), `sfx_events`(dict, optional — `{footstep, door, hit, death}` event-to-sound mappings) |
| `game/data/statuses.json` | `id`, `name`, `kind`(`dot`\|`debuff`\|`buff`), `magnitude`, `duration`(ticks), `tick_every`, `icon` |
|| `game/data/flavor.json` | `{"version":1,"entries":[{"id":..., "context":(`death`|`levelup`|`item`|`shrine`|`boss`), "text": "..."}]}` |
|| `game/data/meta_tree.json` | `{"version":1, "respec_cost": int(>=0), "branches":[{"id":str,"name":str,"color":[3 ints 0-255],"tiers":[{"level":int,"label":str,"stat":str,"bonus":num,"cost":int(>0),"desc":str,"prereq":str|null}]}]}` |
|| `game/data/audio.json` | `{"version":1,"manifest":[{"id":str,"file":str,"model":str,"license":str,"seed":int,"loop":bool,"gain":float,"prompt":str,"cmd":str}]}` — audio manifest entries with `id` (e.g. `death_sting`, `victory_sting`), `file` path, `model`, `license`, `seed`, `loop`, `gain`, `prompt`, `cmd` |

Numbers are numbers and booleans are booleans, never strings. `sprite` values must exist as frames in
an atlas (validator cross-checks `assets/atlas/*.json`).

## 5. Atlas format (owned by `pixel`)

`assets/atlas/<name>.json`:
```json
{"version": 1, "image": "assets/atlas/<name>.png",
 "meta": {"tile": 32, "palette_version": 1, "generated_by": "pixel"},
 "frames": {"player_idle_0": [0, 0, 32, 32], "wall_catacombs": [32, 0, 32, 32]}}
```
Rects are `[x, y, w, h]` in atlas pixels, top-left origin, no scaling, no padding > 1px.
Loader: `game/engine/assets.py::Atlas.load(name)` -> `.frame(name) -> pygame.Surface` (alpha intact).
Missing frame => return the placeholder surface and append to `world.warnings`, never crash.
No two frames in one atlas may share a rect (the verifier enforces this).

Every atlas frame is exactly **32x32** (including bosses, for v1) and lives in one of the logical
sets `monsters · player · tiles · props · vfx · ui · bosses · items`. Frame lookup by name must work
without the caller knowing which file a frame came from.

### 5.1 Loader aliases (`assets/aliases.json`)

Extra frame names that resolve to a real frame, kept out of the atlases so the verifier stays strict:

```json
{"version": 1, "note": "alias -> real atlas frame name", "aliases": {"ui_status_chill": "ui_status_slow"}}
```
`Atlas.frame(name)`: if `name` is not a frame, consult the alias map and load the target; if the
target is missing too, fall back to the placeholder.

## 6. Palette

`assets/palette.json`: `{"version": 1, "colors": {"<name>": "#rrggbb", ...}}`.
Ship art uses only these colours. `tools.art.verify` fails on an off-palette pixel (tolerance 0).

## 7. Save format

`save.json` in the project root:
```json
{"version": 3, "meta": {"hp": 10, "damage": 2, "speed": 0.05, "luck": 3, "armor": 0, "crit": 0},
 "essence": 240, "stats": {"runs": 7, "best_floor": 11, "kills": 310},
 "run": {"seed": 1234, "floor": 3, "biome": "catacombs"} | null,
 "class_id": "lantern_keeper",
 "unlocks": {"iron_mace": true, "iron_helm": true},
 "ascension": 0,
 "unlocked_classes": ["lantern_keeper"],
 "unlocked_ascension": 0,
 "levels": {"vitality:1": 1, "vitality:2": 0, "might:1": 1},
 "settings": {},
 "run_history": [], "codex": {}, "bestiary": {},
 "save_slots": {"default": "save.json", "autosave": "save_autosave.json"},
 "autosave": {"last_floor": 3, "last_biome": "catacombs", "last_seed": 1234, "timestamp": 420}}
```

Named slot files:
- `save.json` — the default slot (also written by `save_profile(profile)` without a slot name)
- `save_autosave.json` — the autosave slot (written by `save_slot_autosave(profile)`)
- `save_<slot_name>.json` — custom named slots (e.g. `save_quick_1.json`)
- `save.json.bak` — backup of the last successful write for corrupted-save recovery

Load must tolerate a missing file (fresh profile), an older `version` (migrate or reset, never crash), and a corrupted/invalid JSON file (recover from `.bak` if available, otherwise start fresh).

### P5.2 Deterministic replay (version 3)

- **`--record <path>`**: records all player inputs during a headless run to a
  JSON replay file at *path*. The `ReplayInput` captures every `InputState`
  (move vector + action set) at each tick and serializes it on run end.
- **`--replay <path>`**: replays a previously recorded input JSON deterministically,
  feeding the exact same inputs back into `World.step()` on every tick.
  Frame-exact reproduction: same seed + same replay → identical run.
- **`ReplayInput`** (`game/engine/input.py`):
  - `start_recording()` / `stop_recording()` — capture states live
  - `save(path)` / `load(path)` — serialize/deserialize the state list
  - States are `{"move": [mx, my], "actions": ["attack", ...]}` dicts
- **`Game.replay`** (`game/engine/scenes.py`): set by `--replay` or `--record`;
  `RunScene.__init__` wires `self.world.input_source` to it automatically.

### P5.1 Save robustness (version 3)

- **`version`** is `3`. The v2→v3 migration copies all existing v2 fields forward
  (additive) and fills `save_slots` and `autosave` with defaults when missing.
  `version=2` saves are migrated automatically.
- **`save_slots`** (dict, default `{"default": "save.json", "autosave": "save_autosave.json"}`) —
  named slots mapping slot names to file paths. `_slot_path(slot_name)` resolves the
  path: `default` → `save.json`, `autosave` → `save_autosave.json`, custom → `save_<name>.json`.
  `list_saves()` enumerates slots, `load_slot(slot_name)` loads, `save_slot(slot_name, profile)` writes.
- **`autosave`** (dict, default `{"last_floor": 0, "last_biome": "", "last_seed": 0, "timestamp": 0}`) —
  autosave metadata updated on every floor entry. `world.new_floor()` calls
  `save_sys.save_slot_autosave(profile)` whenever the floor changes, writing to `save_autosave.json`.
- **Atomic writes with `.bak` backup**: `save_profile()` writes to `{path}.tmp` then `os.replace()`,
  then copies the written file to `{path}.bak`. `load_profile()` recovers from `.bak` on corrupted JSON.
- **Autosave on floor entry**: `world.new_floor()` calls `save_sys.save_slot_autosave(profile)`
  when `self.profile is not None` and `floor != previous_floor`. Saves are silently ignored
  on failure — autosave must never break gameplay.
- **Corrupted-save recovery**: if `save.json` contains invalid JSON, `load_profile()` attempts to
  restore from `save.json.bak`. If the backup is also unusable, the profile is reset to
  `default_profile()` and the failure is recorded in `notes` (e.g. `"save corrupted, recovered fresh"`).

P1.4 fields (additive, default for older saves):
- `class_id` (str, default `"lantern_keeper"`) — selected starting loadout. See `save.CLASS_DEFS`.
- `unlocks` (dict `{item_id: true}`, default `{}`) — tier-2+ items seen during any run; unlocked items get a small drop-weight bonus.
- `ascension` (int 0-5, default `0`) — selected ascension tier. Applied to monster scaling and healing.
- `unlocked_classes` (list of class ids, default `["lantern_keeper"]`) — classes available in the class-select menu. Extended by reaching floors 6 (`ash_dancer`) and 10 (`grave_warden`).
- `unlocked_ascension` (int 0-5, default `0`) — highest ascension tier unlocked. Extended by beating the boss at the current ascension level.

P2.6 fields (additive, default for older saves):
- `settings` (dict, default `{}`) — accessibility and controls settings. Normalized by `game.ui.settings.normalize()`. Fields:
  - `shake_enabled` (bool, default True) — screen shake on hit
  - `damage_numbers` (bool, default True) — floating damage numbers
  - `reduced_flashing` (bool, default False) — dampens flicker/strobe effects
  - `font_scale` (int 1 or 2, default 1) — 1 = normal, 2 = large HUD text
  - `hold_to_attack` (bool, default False) — hold direction to auto-attack
  - `colourblind_mode` (str "off"|"protan"|"deutan"|"tritan", default "off") — colourblind-safe rarity colours
  - `gamepad_enabled` (bool, default False) — use joystick if present
  - `key_map` (dict `{action: pygame_key_int}`, default `{}`) — remappable key bindings; missing keys fall back to defaults in `game.ui.settings.DEFAULT_KEY_MAP`

The `settings` dict is normalized by `game.ui.settings.normalize()`. Every field has a default and loading is tolerant of missing or partial settings. Settings are passed through `world.settings` and applied to rendering, input, and gameplay:

- `shake_enabled`: synced to `camera.shake_enabled` in RunScene; toggles screen shake on hit
- `damage_numbers`: toggles `world.damage_numbers.draw()` in the renderer
- `reduced_flashing`: halves screen_flash alpha and reduces vignette intensity in the renderer
- `font_scale`: scales all HUD text, panel size, and damage number font sizes
- `hold_to_attack`: when True, KeyboardInput and GamepadInput register "attack" continuously while holding attack+direction; Player.tick() accepts `hold_to_attack` param; world.step() calls player_melee while attack is held
- `colourblind_mode`: maps tier colours through `rarity_colour()` palette in renderer (health bars, damage numbers) and HUD (essence, gold, status colours)
- `gamepad_enabled`: when True, GamepadInput is used instead of KeyboardInput; falls back gracefully when no joystick is present
- `key_map`: remappable key bindings read by KeyboardInput

### P3.5 Run storytelling

Fields added to `save.json` profile (additive, default for older saves):

- `run_history` (list) — list of run entries, each `{seed, floor, biome, kills, rooms, death_cause, essence}`. Keeps last 50 runs.
- `codex` (dict) — `{monster_id: {seen: bool, kills: int}, item_id: {seen: bool, kills: 0}}`. Tracks all monsters and items seen across runs.
- `bestiary` (dict) — `{monster_id: kill_count}`. Tracks total kill counts per monster across all runs.

### P5.1 Save robustness

Fields added to `save.json` profile (additive, default for older saves):

- `save_slots` (dict) — named save slots. Keys are slot names (e.g. `"default"`), values are slot metadata.
- `autosave` (dict) — `{last_floor, last_biome, last_seed, timestamp}`. Updated automatically on floor entry via `world.new_floor()`. Written to `save_autosave.json`.

P5.1 mechanisms:
- **Version migration**: `SAVE_VERSION = 3`. Older saves (v1/v2) are migrated to v3 on load with full field mapping.
- **Atomic writes**: `save_profile()` writes to a `.tmp` file then `os.replace()` to the target path, ensuring no partial writes on crash.
- **Corrupted-save recovery**: On invalid JSON, `load_profile()` attempts to restore from `<path>.bak`. If the backup is also invalid, the profile resets to `default_profile()`.
- **Autosave on floor entry**: `world.new_floor()` calls `save_sys.save_profile(self.profile, slot_name="autosave")` when `self.floor != self.previous_floor`. Failure is silently caught to never break gameplay.
- **Named slots**: `save_slot(slot_name, profile)` / `load_slot(slot_name)` / `list_saves()` allow multiple named save files.

Version history:
- v1 → v2: meta-progression tree fields (`meta`, `levels`, `essence`).
- v2 → v3: `save_slots`, `autosave`, `run_history`, `codex`, `bestiary`, `class_id`, `unlocks`, `ascension`, `unlocked_classes`, `unlocked_ascension`. Migration path defined in `load_profile()`.
