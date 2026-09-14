# Content Inventory — Depths of Vaelmoor

Seed content shipped in `game/data/` (owner: **lore**). Every file is strict JSON in the
`{"version": 1, "entries": [...]}` envelope from `docs/CONTRACTS.md` §4.

## Counts

| File | Entries | Contract minimum | Coverage notes |
|---|---|---|---|
| `monsters.json` | **37** | >= 36 / >= 12 per biome | 13 catacombs, 12 ember_warrens, 12 drowned_vaults. Tiers 1-5 present (t1:4, t2:8, t3:10, t4:10, t5:5). Behaviors: chaser 12, brute 10, ranged 9, ambusher 6 — all four in every biome. 37 distinct (hp, damage, armor, speed, xp) profiles, no repeats. 15 monsters carry a `status_on_hit`, 22 are null. |
| `items.json` | **64** | >= 60 | weapon 15, armor 15, trinket 17, consumable 17. **All 20 slot x tier combinations present.** Gold bands scale with tier: t1 9-18, t2 36-52, t3 95-122, t4 200-250, t5 380-480 (no overlap between bands). Every item has a flavour line. |
| `affixes.json` | **28** | >= 25 | 15 prefix-shaped (`sharp`, `vital`, ...) + 13 suffix-shaped (`of_embers`, `of_the_void`, ...). Weights 10-100: common affixes weigh 75-100, chase affixes 10-30. `tier_min <= tier_max` everywhere. 2 affixes carry two-key effects. |
| `rooms.json` | **24** | >= 21 / >= 7 per biome | 8 per biome. All six kinds: combat 9, boss 3, entrance 3, shop 3, shrine 3, treasure 3. Dims 7x6 to 24x20 (contract 5-24). `spawn_budget` scales with area and kind: entrance/shop 0, shrine 1, treasure 2-3, boss 1, combat 4-11. |
||| `biomes.json` | **4** | >= 4 | catacombs / ember_warrens / drowned_vaults / sunken_ossuary. Ambient values are locked-palette colours. Fog values distinct per biome. Each biome carries a P1.2 `modifier`: catacombs_darkness / ember_heat / drowned_water / ossuary_toxic. |
| `statuses.json` | **18** | >= 12 | dot 6, debuff 6, buff 6. Durations 60-600 ticks at 60 Hz (1 s to 10 s); `tick_every` 30/40/60 and never exceeds `duration`. |
| `flavor.json` | **65** | >= 60 | death 14, item 16, levelup 12, shrine 12, boss 11 — all five contexts covered. |

## Bosses / guardians

`catacomb_guardian` (t5 brute), `warren_overseer` (t5 brute) and `drowned_leviathan` (t5 brute)
are the three per-biome floor-5 guardians, all spawned by that biome's `*_boss_*` room.

## Id and sprite naming conventions (frozen — the art agent is generating to these names)

**Ids** — unique per file, `snake_case`, never renamed once shipped (saves and cross-file refs
depend on them):

- monsters: bare creature name — `bone_rat`, `drowned_soldier`
- items: `item` id equals the sprite suffix — `rusty_blade` / `item_rusty_blade`
- affixes: prefix = adjective (`sharp`), suffix = `of_<noun>` (`of_the_grave`)
- rooms: `<biome>_<kind>_<shape>` — `catacombs_combat_hall`, `drowned_vaults_boss_sanctum`
- statuses: bare effect name — `poison`, `doom_mark`
- flavor: `<context>_NN` — `death_01`, `item_16`

**Sprites** — `<kind>_<thing>[_variant]`, lowercase snake_case:

- `monster_<id>` — `monster_bone_rat`, `monster_drowned_leviathan` (37 frames)
- `item_<id>` — `item_rusty_blade`, `item_of...` n/a (64 frames)
- `tile_<biome>` tileset prefixes — `tile_catacombs`, `tile_ember`, `tile_drowned`
- `prop_<thing>` — `prop_brazier`, `prop_chest`, `prop_lava_vent`, `prop_water_pool`,
  `prop_shrine_drowned`, `prop_pillar_drowned` (23 distinct props used by rooms)
- `ui_status_<id>` — `ui_status_poison`, `ui_status_lantern_glow` (18 icon frames)
- music keys (`biomes.music`): `music_catacombs_drip`, `music_ember_warrens`, null

Atlas frames are not yet packed (`assets/atlas/` is empty); `sprite`/`props`/`icon` values are the
authoritative frame names `tools.art.pack_atlas` must emit.

## Validation

Content was emitted by a table-driven generator (kept in temp, not in the repo) and then re-checked
by an independent validator that re-reads the files from disk and asserts: strict JSON with no
comments/trailing commas/NaN, exact `version`/`entries` envelope, required fields per file, enum
membership, numeric ranges, int-vs-float types, snake_case and uniqueness of ids, cross-file
references (biome -> monster ids, monster -> status ids, monster -> biome ids), palette membership
of ambient colours, tier coverage, gold scaling and sprite naming. Latest run: **PASS**, 0 errors.
`tools/validate_data.py` (owned by `link`) remains the shipped validator; this count table is the
human-readable summary.

## Integration notes for `link` / `pixel` (divergences to reconcile)

`game/systems/data.py` loads these files correctly as-is (required fields match, biomes resolve,
`boss_for()` picks `drowned_leviathan` / `warren_overseer` / `catacomb_guardian` for their biomes,
`monster_pool(max_tier=4)` correctly keeps the t5 guardians out of normal spawns). Two naming
divergences between that module's **embedded fallback** content and the shipped data file exist and
should be settled in favour of the data file:

1. **Status icons.** Shipped: `ui_status_poison`. Fallback: `status_poison`. The HUD icon lookup
   must agree with the data file or every status icon will fall back to a placeholder. `ui_*` is
   the contract's convention for UI frames; whichever wins, `pixel` needs one list.
2. **Room props.** Shipped: `prop_brazier`, `prop_chest`, `prop_water_pool`. Fallback: `brazier`,
   `chest`, `pool`. The contract's frame-name examples use the `prop_` prefix.

