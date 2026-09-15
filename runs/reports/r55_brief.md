# r55 — Player hazard feedback: VFX + camera shake when standing on hazards

**Forge → Chip** (world hazard stepping, player VFX, camera shake)

## Problem
The renderer animates burning/water tiles (r54), but the player character gets no visual feedback when standing on them — the floor ripples/flickers but the hero looks frozen and unbothered. Hazard damage is silent; the player can't see *why* they're taking damage.

## Current state
- `world.py` `step()` calls `_bm.step_ember(world, dt)` / `_bm.step_drowned(world, dt)` for hazard damage
- `biome_mods.py` `_step_ember`: burn DOT applied every 120 ticks, magnitude ramps with floor
- `biome_mods.py` `_step_drowned`: water slow applied after stationary threshold
- No VFX spawn on player during hazard damage
- No camera shake on taking hazard damage
- `world.burning_tiles(level)` and `world.water_tiles(level)` return sets of (tx, ty)

## What to build

### 1. Player hazard check in `world.step()`
Add `_check_player_hazards(dt)` called from `step()` after biome mods:
- Query `(player.tile_x, player.tile_y)` against `burning_tiles()` and `water_tiles()`
- If on burning tile AND no water protection (no `status_water_shield`):
  - Every ~1.0s (counter, not RNG), spawn `vfx_flame` at player position with scale 1.2, life 0.5
  - Add small camera shake (`add_shake(3.0)`)
  - Apply 1.0 burn damage (separate from the biome DOT — this is the "visual feedback" hit)
- If on water tile AND not standing still for < 150 ticks:
  - Every ~0.8s, spawn `vfx_ripple` at player position with scale 1.0, life 0.6
  - No camera shake (water is not violent)

### 2. Player visual response
- Brief `player.hit_flash` trigger (0.08s white flash) when hazard VFX spawns
- Sync with the existing biome damage ticks so VFX don't fire every frame

### 3. Avoid double-damage
- Track `self._hazard_feedback_cooldown` (0.8s countdown) to prevent multiple VFX/sec
- The biome mod still handles the "real" DOT; this is cosmetic + a tiny visual-only tick that matches the rhythm

## Acceptance
1. `python -m game.main --headless --turns 300 --seed 0..2` exits 0, violations=[]
2. `python -m tools.selftest` 22/22
3. Render frames in ember_warrens biome with burning tiles — VLM audit should confirm flame VFX at player position when on burning tiles
4. No new RNG calls — all timing via cooldown counter

## Files to touch
- `game/systems/world.py` — `_check_player_hazards()`, cooldown timer, camera shake call
