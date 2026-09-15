# r54 — Animated environment: hazard tiles, prop ground overlays, torch flicker

**Forge → Chip** (renderer, tile drawing, VFX integration)

## Problem
VLM audit of real gameplay frames: "repeating dark stone tiles, no animated or hazard tiles; all environmental elements are static." The tile atlas has 128 biome frames (4 biomes × 32 frame types) but the renderer never animates any of them — `floor_burning`, `floor_water`, `wall_torch`, `brazier` props are all static sprites. A roguelite world needs life: flowing lava, rippling water, flickering torchlight.

## Current state
- `game/engine/renderer.py draw()`: draws tiles with static `self.frame(world, name)` — no frame cycling
- `game/engine/lighting.py`: lights tick and flicker, but the sprites beneath them don't animate
- `assets/atlas/tiles.json`: has `floor_burning`, `floor_water`, `wall_torch`, `prop_brazier` — all single static frames
- `assets/atlas/vfx.json`: has flame, ember, spark, ripple VFX sprites that could overlay on tiles
- `world.tile_frames()` returns `{key: "tileset_key"}` — one frame per key, no animation sequences

## What to build

### 1. Animated tile frame cycling in renderer
- Add `self._tile_anim_phase = 0.0` to `__init__`, advance by `dt` each frame (wrapping at loop period)
- Define animated tile sequences as constants at module level:
  ```python
  ANIMATED_TILES = {
      "floor_burning": ["floor_burning", "floor_burning_alt"],  # 2-frame flicker
      "floor_water": ["floor_water", "floor_water_alt"],       # 2-frame ripple
      "wall_torch": ["wall_torch", "wall_torch_bright"],        # 2-frame flicker
  }
  ```
- In `draw()`, when the chosen tile name is in `ANIMATED_TILES`, pick the frame index from `self._tile_anim_phase`
- Period: 0.4s for burning, 0.6s for water, 0.3s for torch (deterministic, no RNG — use `sin(phase)`-based index)

### 2. Hazard ground VFX overlay
- When drawing a burning tile: after blitting the tile, spawn a flame VFX overlay (use existing `vfx_flame` or `vfx_ember` from vfx atlas) at the tile center, scaled 0.5
- When drawing a water tile: after blitting, spawn a subtle `vfx_ripple` overlay at random offsets (counter-based, not RNG) every ~3rd tile
- These overlays render in the entity/effect pass (after tiles, before entities), not as particles — they're static sprite stamps tied to tile position

### 3. Brazier/candle prop ground glow
- After drawing prop sprites (brazier, candles, lava_vent, forge), stamp a colored glow disc on the floor beneath them — use `pygame.draw.circle` with additive blend, color matching the light:
  - brazier: (255, 120, 40) radius 18 alpha 60
  - candles: (255, 200, 80) radius 12 alpha 40
  - lava_vent: (255, 80, 20) radius 22 alpha 70
  - forge: (215, 100, 30) radius 16 alpha 50

### 4. New tile frames needed
Generate 4 new tile atlas frames (single 32×32 sprites, palette-locked) and add to `assets/atlas/tiles.json`:
- `tile_{biome}_floor_burning_alt` for all 4 biomes — brighter orange/red variant of floor_burning
- `tile_{biome}_floor_water_alt` for all 4 biomes — lighter blue/white highlight variant of floor_water
- `tile_{biome}_wall_torch_bright` for all 4 biomes — brighter yellow torch head variant of wall_torch
Total: 12 new sprite files. Generate via numpy pixel manipulation of existing tile frames (brighten/redden/bluen channels) — no need to regenerate from FLUX.

## What NOT to do
- Don't add `random` calls for animation timing — use counter/phase-based selection (deterministic)
- Don't spawn particles — particle budget is for combat; these are static overlays
- Don't change the tile atlas packing format — add frames to existing atlas, rebuild JSON
- Don't break the headless gate — every new draw call must be safe in headless mode

## Acceptance
1. `python -m game.main --headless --turns 300 --seed 0..2` exits 0, violations=[]
2. `python -m tools.selftest` 22/22
3. `python -m tools.art.verify` 0 off-palette, frame count = 128 + 12 = 140 in tiles atlas
4. Render 3 frames at ticks 50/100/150 in a burning floor area (biome=ember_warrens) and water area (biome=drowned_vaults) — visual audit by VLM should confirm animation frames cycle and overlays present
5. No new imports at module scope; all existing imports in renderer.py and lighting.py stay

## Files to touch
- `game/engine/renderer.py` — add animated tile cycling, hazard overlays, prop glow
- `game/engine/assets.py` — add `tiles.json` frame rebuild helper if needed
- `assets/atlas/tiles.json` — add 12 new frame entries (manual JSON edit after generating sprites)
- `assets/sprites/tiles/` — add 12 new sprite PNGs (generated via numpy manipulation)
