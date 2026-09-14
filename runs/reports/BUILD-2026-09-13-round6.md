# BUILD 2026-09-13 — Round 6: P1.5 Shrines, curses and blessings

## What changed

1. **procgen.py** — Fixed `kind_want` order so shrine rooms appear on every floor.
   Was: `["entrance", "boss"] + ["combat"]*3 + ["treasure", "shrine", "shop", "combat"]`
   → shrine was always 7th, cut off by the 6-slot 3×2 grid.
   Now: `["entrance", "boss", "combat", "treasure", "shrine", "shop", "combat", "combat"]`
   → shrine is 5th, always gets a slot. Shop also now appears (was also cut off).

2. **shrines.py** — Added 3 new curses:
   - `curse_max_hp` ("Diminished"): -15 max_hp for 600 ticks, clamps player HP.
   - `curse_armor` ("Exposed"): -3 armor (as fraction) for 600 ticks.
   - `curse_gold_tax` ("Gold Tax"): 25% of gold drops lost for the floor.
   
   Added `_register_effect()` to track active effects on `world.shrine_active_effects`
   for the HUD panel. Updated `tick_shrine_effects()` to also tick down the panel entries.

3. **world.py** — Added `shrine_active_effects` (list) and `gold_tax` (float) to `__init__`
   and `new_floor()` reset. Gold pickup collection now subtracts `gold_tax` fraction.

4. **hud.py** — Removed duplicate biome-modifier badge (was drawn at both top-right and
   center — kept center only). Added `_shrine_panel()` method: persistent right-side panel
   showing active boons (green) and curses (red) with countdown timers.

## Gates (real output)

```
$ python -m game.main --headless --turns 300 --seed 0
  ok=True  errors=[]  violations=[]  exit 0
$ python -m game.main --headless --turns 300 --seed 1
  ok=True  errors=[]  violations=[]  exit 0
$ python -m game.main --headless --turns 300 --seed 2
  ok=True  errors=[]  violations=[]  exit 0

$ python -m tools.validate_data
  PASS: 8 file(s), 239 entries, 0 error(s), 0 warning(s)

$ python -m tools.art.verify
  PASS: 329 sprite file(s), 311 frame(s), 0 off-palette pixel(s)

$ python -m tools.selftest
  13 checks: 13 passed, 0 skipped, 0 failed

$ python -m tools.studio.audit_sprites
  238 sprite name(s) referenced by content
  resolved: 238  MISSING: 0
```

## Shrine integration test

```
Shrine at (784, 208)
shrine_temp_effects: [{'stat': 'damage', 'value': 5.0, 'remaining': 600.0},
                       {'stat': 'speed', 'value': -0.3, 'remaining': 600.0}]
shrine_active_effects: [{'name': 'BOON: Rending Edge', 'color': (121,176,74), 'remaining': 600.0},
                        {'name': 'CURSE: Heavy Boots', 'color': (196,99,95), 'remaining': 600.0}]
After 120 ticks: shrine_active_effects still alive, temp_effects count=2
```

## Screenshot QA (numeric)

3 frames (seed 0, ticks 20/100/199), all 1280×720:
- frame-000020: 2623 distinct colours, 0 white, 0 magenta, HUD 702 colours, minimap 160
- frame-000100: 2623 distinct colours, 0 white, 0 magenta
- frame-000199: 2622 distinct colours, 0 white, 0 magenta, player warm-glow 3779px

## Contract

No contract changes. Shrine pickup kind and shrine room kind already in CONTRACTS.md §4.

## Next

P1.6 (Build-defining loot) or P2.1 (Hit feel).
