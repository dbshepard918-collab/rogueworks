# r61 — Content Volume: more room templates, items, and monster variety

**Forge → Lore** (content generation via local LLM)

## Problem
GDD targets (80 monsters, 150 items, 60 affixes, 40 room templates per biome) are met at minimum. Replayability suffers because:
- **Sunken Ossuary** only has 40 room templates (vs 55/55/55 for others) — biome repeats 35% faster
- Many items share the same `effect` dict (different names, same numbers) — "duplicate" loot
- Per-biome monster pools are shallow — same spawns every run after a few floors

## Current counts
Run `python -m tools.validate_data` and `python -m tools.studio.audit_sprites` to get exact numbers. Known:
- Monsters: 85 total (20/19/18/28 per biome)
- Items: 150 total
- Affixes: 60 total
- Room templates: 55/55/55/40 per biome (catacombs/ember/drowned/ossuary)

## What to build

### 1. Room templates for Sunken Ossuary
Generate 15 new `rooms.json` entries for `biome: "sunken_ossuary"` — reaches the 55/biome standard.
- Use the existing naming convention: `ossuary_room_<kind>_<N>`
- Kinds to add: more `secret`, `shrine`, `gambling` rooms (biome flavor: caustic pools, toxic vents, bone pits)
- Mirror the structure of existing entries: `id`, `biome`, `kind`, `w`, `h`, `monsters` pool, `loot` weight

### 2. Unique items
Add 20 new items to `items.json` — targeting the GDD "build-defining loot" niche:
- **Dash leaves fire trail** (unique_id: `ember_dash`)
- **Killing spawns a soul minion** (unique_id: `soul_reaper`)
- **Dodge grants brief invulnerability** (unique_id: `phase_cloak`)
- **Ranged shots pierce** (unique_id: `pierce_bolt`)
- **Melee kills heal** (unique_id: `vampiric_blade`)
- Each must have a distinct `unique` tag and a `sprite` that resolves

### 3. Monster variety
Add 10 new monster entries across all biomes — `splitter` and `charger` variants for ossuary + drowned (biomes that currently have fewest):
- `ossuary_splitter` — splits into 2 mini-versions on death
- `ossuary_charger` — lunges across the room
- `drowned_ink` — blinds player (new status)
- Each needs: `name`, `sprite`, `hp`, `damage`, `speed`, `behavior`, `element`, `status_on_hit`, `xp`

## What NOT to do
- Don't modify `game/` code — this is pure data
- Don't regenerate existing content — ADD only
- Don't change the tile atlas — no new sprites needed (reuse existing)
- Keep all numeric values within existing ranges (check `tools/validate_data.py` schema)

## Acceptance
1. `python -m tools.validate_data` exits 0 with new counts:
   - Room templates: 55/55/55/55 per biome (was 55/55/55/40)
   - Items: 170+ total (was 150)
   - Monsters: 95+ total (was 85)
2. `python -m tools.studio.audit_sprites` 0 MISSING
3. `python -m game.main --headless --turns 300 --seed 0..2` exits 0
4. `python -m tools.selftest` 22/22

## Files to touch
- `game/data/rooms.json` — add 15 ossuary templates
- `game/data/items.json` — add 20 unique items
- `game/data/monsters.json` — add 10 monsters

## Skill to use
`roguelite-narrative` — bulk game data generation workflow. Load it first and follow the prompt format.
