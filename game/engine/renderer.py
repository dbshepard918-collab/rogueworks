"""Renderer: pure drawing of the world.  Never mutates gameplay state.

Builds a per-frame draw list (stored on ``world.render_list``) so the invariant
checker can assert there are no ``None`` entries in it.
"""

import math

import pygame

from .assets import colour
from ..engine.assets import has_frame as _has_frame
from ..ui.settings import rarity_colour

from ..systems import biome_mods as _bm
from ..systems.statuses import COMBO_IDS
from game.systems.procgen import FLOOR

TILE = 64


def _hash2(x, y, salt=0):
    h = (x * 73856093) ^ (y * 19349663) ^ (salt * 83492791)
    return abs(h)


def _draw_biome_texture(surface, biome_id, sx, sy, tx, ty, tile_px):
    """Add sparse, deterministic surface detail to otherwise flat biome tiles."""
    tile_px = int(tile_px)
    detail = pygame.Surface((tile_px, tile_px), pygame.SRCALPHA)
    h = _hash2(tx, ty, 101)
    if biome_id == "drowned_vaults":
        colour = (79, 151, 171, 22 + (h % 30))
        if h % 4 in (0, 1):
            pygame.draw.arc(
                detail,
                colour,
                pygame.Rect((h % 17) - tile_px // 8, tile_px // 4,
                            max(4, tile_px * 3 // 4), max(3, tile_px // 4)),
                0.25 if h % 2 else 3.25,
                2.35 if h % 2 else 5.35,
                max(1, tile_px // 32),
            )
        if h % 5 in (0, 2):
            pygame.draw.line(
                detail,
                (164, 213, 204, 24 + (h % 16)),
                ((h % 19), tile_px * (2 + h % 4) // 8),
                (tile_px * 3 // 4, tile_px * (2 + h % 4) // 8),
                max(1, tile_px // 32),
            )
        if h % 7 == 0:
            pygame.draw.line(
                detail,
                (31, 95, 128, 34 + (h % 24)),
                (tile_px // 6, tile_px * 7 // 8),
                (tile_px * 5 // 6, tile_px * 7 // 8),
                max(1, tile_px // 24),
            )
    elif biome_id == "sunken_ossuary":
        if h % 2 == 0:
            pygame.draw.line(
                detail,
                (217, 210, 197, 32 + (h % 20)),
                (tile_px // 4, tile_px * 2 // 5),
                (tile_px * 3 // 4, tile_px * 3 // 5),
                max(1, tile_px // 32),
            )
        if h % 3 == 0:
            pygame.draw.line(
                detail,
                (138, 132, 150, 30 + (h % 20)),
                (tile_px // 5, tile_px * 3 // 4),
                (tile_px * 4 // 5, tile_px * 3 // 4),
                max(1, tile_px // 32),
            )
        if h % 5 == 1:
            pygame.draw.line(
                detail,
                (36, 52, 45, 90 + (h % 20)),
                (tile_px // 8, tile_px // 2),
                (tile_px * 7 // 8, tile_px // 2),
                max(1, tile_px // 32),
            )
        if h % 5 == 0:
            pygame.draw.circle(
                detail,
                (121, 176, 74, 38 + (h % 16)),
                (tile_px * 3 // 4, tile_px // 4),
                max(1, tile_px // 24),
            )
    if detail.get_bounding_rect().width:
        surface.blit(detail, (sx, sy))


def _draw_contact_shadow(surface, wx, wy, ox, oy, radius, scale=1.0):
    """Ground actors and pickups without changing their palette-locked art."""
    width = max(12, min(42, int(radius * 2.2 * scale)))
    height = max(4, int(width * 0.32))
    cx = int((wx - ox) * scale)
    cy = int((wy - oy) * scale + radius * 0.58 * scale)
    shadow = pygame.Surface((width, height), pygame.SRCALPHA)
    pygame.draw.ellipse(shadow, (11, 10, 16, 112), shadow.get_rect())
    surface.blit(shadow, (cx - width // 2, cy - height // 2))


def _draw_combat_ring(surface, wx, wy, ox, oy, radius, color, width=2, scale=1.0):
    """Draw a crisp ground-space cue without changing the simulation."""
    cx = int((wx - ox) * scale)
    cy = int((wy - oy) * scale)
    pygame.draw.circle(surface, color, (cx, cy), max(2, int(radius * scale)),
                       max(1, int(width * scale)))


def _draw_combat_silhouette(surface, wx, wy, ox, oy, radius, color, scale=1.0):
    """Give tiny atlas sprites a readable dark keyline against busy floors."""
    cx = int((wx - ox) * scale)
    cy = int((wy - oy) * scale)
    r = max(5, int(radius * 0.78 * scale))
    pygame.draw.circle(surface, color, (cx, cy), r + max(2, int(3 * scale)))


# Element colors for combo aura rendering
COMBO_ELEMENT_COLORS = {
    "steam_burst": (200, 180, 120, 80),    # warm amber steam
    "shatter": (100, 180, 230, 60),         # icy blue shatter
    "frost_burn": (100, 200, 80, 70),       # ice-fire blend
}

# r54: Animated tile sequences — each key maps to a list of frame names to
# cycle through. Period controls how long each frame displays (seconds).
# Deterministic: no RNG, animation is purely time-based.
ANIMATED_TILES = {
    "floor_burning":     (["floor_burning", "floor_burning_alt"], 0.25),
    "floor_water":       (["floor_water", "floor_water_alt"], 0.35),
    "wall_torch":        (["wall_torch", "wall_torch_bright"], 0.18),
}

# r54: Ground glow colours for light-emitting props (matches lighting.py spec)
PROP_GLOW = {
    "prop_brazier":    ((255, 120, 40), 18, 60),
    "prop_candles":    ((255, 200, 80), 12, 40),
    "prop_lava_vent":  ((255, 80, 20), 22, 70),
    "prop_forge":      ((215, 100, 30), 16, 50),
    "prop_fountain":   ((110, 190, 255), 10, 35),
    "prop_crystal":    ((150, 205, 255), 10, 35),
    "prop_altar":      ((190, 130, 255), 12, 35),
    "prop_anvil":      ((190, 170, 150), 8, 25),
}

def _combo_status_id(actor):
    """Return the combo status ID if actor has one, else None."""
    for inst in getattr(actor, "statuses", []):
        if inst.status_id in COMBO_IDS:
            return inst.status_id
    return None


def _draw_combo_aura(renderer, world, actor, surface, ox, oy):
    """P2.5: Draw colored aura around entities with active combo statuses."""
    combo_id = _combo_status_id(actor)
    if combo_id is None:
        return
    color = COMBO_ELEMENT_COLORS.get(combo_id, (255, 255, 255, 40))
    radius = max(actor.radius * 1.5, 20)
    cx = int(actor.x - ox)
    cy = int(actor.y - oy)
    # Draw colored circle overlay
    s = pygame.Surface((int(radius * 2), int(radius * 2)), pygame.SRCALPHA)
    pygame.draw.circle(s, color, (int(radius), int(radius)), int(radius))
    surface.blit(s, (cx - int(radius), cy - int(radius)))


class Renderer:
    """Draws a World into a 1280x720 surface."""

    def __init__(self, size=(1280, 720)):
        self.size = size
        self._frames = {}
        self._fog = {}
        self._vignette = None
        self._halo = None
        self._locked_tint = {}
        # r54: global animation phase counter for deterministic tile cycling
        self._tile_anim_tick = 0.0

    # -- frame cache -----------------------------------------------------
    @staticmethod
    def _resolve_tile_frame(name, anim_tick, tileset=""):
        """r54: pick the correct frame from an animated tile sequence.
        Accepts a full frame name (e.g. 'tile_catacombs_wall_torch') and
        returns the full animated frame name (e.g. 'tile_catacombs_wall_torch_bright')."""
        # Extract short name by stripping tileset prefix
        short = name
        if tileset and name.startswith(tileset + "_"):
            short = name[len(tileset) + 1:]
        entry = ANIMATED_TILES.get(short)
        if entry is None:
            return name
        frames, period = entry
        idx = int(anim_tick / period) % len(frames)
        animated_short = frames[idx]
        # Reconstruct full frame name
        if tileset:
            return tileset + "_" + animated_short
        return animated_short

    def frame(self, world, name, flip=False, scale=1.0):
        key = (name, flip, scale)
        img = self._frames.get(key)
        if img is None:
            img = world.frame(name)
            if scale != 1.0:
                img = pygame.transform.scale(
                    img, (max(1, int(img.get_width() * scale)),
                          max(1, int(img.get_height() * scale))))
            if flip:
                img = pygame.transform.flip(img, True, False)
            self._frames[key] = img
        return img

    def white(self, img, key=None):
        cache_key = ("white", key if key is not None else id(img))
        out = self._frames.get(cache_key)
        if out is None:
            out = img.copy()
            out.fill((255, 255, 255, 0), special_flags=pygame.BLEND_RGB_MAX)
            self._frames[cache_key] = out
        return out

    # -- cached full-screen overlays -------------------------------------
    def fog(self, world):
        biome = world.content.biome(world.biome_id) or {}
        ambient = tuple(biome.get("ambient") or (11, 10, 16))
        key = (world.biome_id, ambient)
        surf = self._fog.get(key)
        if surf is None:
            fog_strength = float(biome.get("fog", 0.3) or 0.3)
            surf = pygame.Surface(self.size, pygame.SRCALPHA)
            surf.fill(tuple(ambient) + (int(max(0.0, min(1.0, fog_strength)) * 120),))
            self._fog[key] = surf
        return surf

    def vignette(self):
        if self._vignette is None:
            import numpy as np
            w, h = self.size
            surf = pygame.Surface(self.size, pygame.SRCALPHA)
            cx, cy = w / 2.0, h / 2.0
            max_d = (cx * cx + cy * cy) ** 0.5
            axis_x = np.arange(w, dtype=np.float32) - cx
            axis_y = np.arange(h, dtype=np.float32) - cy
            xx, yy = np.meshgrid(axis_x, axis_y, indexing="xy")
            distance = np.sqrt(xx * xx + yy * yy) / max_d
            alpha = np.clip((distance - 0.45) / 0.55, 0.0, 1.0) ** 2
            rgb = np.zeros((w, h, 3), dtype=np.uint8)
            rgb[:, :, 0] = 11
            rgb[:, :, 1] = 10
            rgb[:, :, 2] = 16
            pygame.surfarray.blit_array(surf, rgb)
            pygame.surfarray.pixels_alpha(surf)[:, :] = np.transpose(
                (70.0 * alpha).astype(np.uint8)
            )
            self._vignette = surf
        return self._vignette

    def halo(self, radius=220):
        """Warm lantern glow added around the player.

        Drawn with BLEND_RGB_ADD, which ignores alpha - so the ramp is in RGB,
        from black at the rim to a dim warm tone at the centre (one blit, no
        accumulation).

        The halo surface is cached per radius; rebuilding a 280-440px alpha blend
        every frame is what we are avoiding here.
        """
        if self._halo is not None and self._halo[0] == radius:
            return self._halo
        size = radius * 2
        surf = pygame.Surface((size, size))
        surf.fill((0, 0, 0))
        steps = 24
        cx = radius
        cy = radius
        for i in range(steps):
            t = i / float(steps - 1)          # 0 = rim, 1 = centre
            r = int(radius * (1.0 - t * 0.94))
            level = t * t
            col = (int(30 * level), int(23 * level), int(13 * level))
            pygame.draw.circle(surf, col, (cx, cy), max(1, r))
        self._halo = (radius, surf)
        return self._halo

    def dark_wall(self, world, img):
        """Wall fill for tiles far from any floor (keeps the map solid, not black)."""
        key = ("darkwall", world.tileset())
        out = self._frames.get(key)
        if out is None:
            out = img.copy()
            out.fill((70, 70, 70, 0), special_flags=pygame.BLEND_RGB_SUB)
            self._frames[key] = out
        return out

    # -- main draw -------------------------------------------------------
    def draw(self, world, surface, dt=0.0):
        """Render one frame.  Returns the draw list (never contains None)."""
        level = world.level
        camera = world.camera
        self._tile_scale = camera.tile_scale  # r45: sync zoom
        # r54: advance animation phase for deterministic tile cycling
        self._tile_anim_tick += dt
        draw_list = []
        surface.fill(colour("void", (11, 10, 16)))
        if level is None:
            world.render_list = draw_list
            return draw_list

        ox, oy = camera.world_offset()
        st = camera.tile_scale  # r45 camera zoom
        # tile size and visible-bounds in scaled pixels
        tile_px = TILE * st
        t0x = max(0, int(ox // tile_px))
        t0y = max(0, int(oy // tile_px))
        t1x = min(level.w - 1, int((ox + camera.view_w) // tile_px))
        t1y = min(level.h - 1, int((oy + camera.view_h) // tile_px))

        from game.systems import procgen as procgen_mod
        tiles = world.tile_frames()
        tileset = world.tileset()

        # -- tiles -------------------------------------------------------
        burning = _bm.burning_tiles(level)
        water = _bm.water_tiles(level)
        for ty in range(t0y, t1y + 1):
            for tx in range(t0x, t1x + 1):
                sx = int(tx * tile_px - ox * st)
                sy = int(ty * tile_px - oy * st)
                value = level.tiles[tx][ty]
                if value == procgen_mod.STAIRS:
                    img = self.frame(world, tiles["stairs_down"])
                    if not world.stairs_unlocked_flag:
                        img = self.locked(img)
                    surface.blit(img, (sx, sy))
                    draw_list.append(("stairs", tx, ty))
                    continue
                if value == procgen_mod.DOOR:
                    door_locked = self._is_door_locked(world, tx, ty)
                    if door_locked:
                        img = self.frame(world, tiles["door"])
                        img = self.locked(img)
                    else:
                        img = self.frame(world, tiles["door_open"])
                    surface.blit(img, (sx, sy))
                    draw_list.append(("door", tx, ty, "locked" if door_locked else "open"))
                    continue
                if value == procgen_mod.DOOR_OPEN:
                    img = self.frame(world, tiles["door_open"])
                    surface.blit(img, (sx, sy))
                    draw_list.append(("door", tx, ty, "open"))
                    continue
                if value == procgen_mod.CRACKED_WALL:
                    # Draw cracked wall with crack overlay
                    img = self.frame(world, tiles.get("wall_cracked", tiles["wall"]))
                    surface.blit(img, (sx, sy))
                    # Draw subtle crack indicator
                    h = _hash2(tx, ty, 13)
                    crack_x = sx + 4 + (h % 24)
                    crack_y = sy + 4 + ((h >> 8) % 24)
                    pygame.draw.line(surface, (100, 90, 70),
                                     (crack_x, crack_y),
                                     (crack_x + 4 + (h % 8), crack_y + 2), 1)
                    pygame.draw.line(surface, (100, 90, 70),
                                     (crack_x + 2, crack_y + 4),
                                     (crack_x + 6 + (h % 6), crack_y + 6), 1)
                    draw_list.append(("cracked_wall", tx, ty))
                    continue
                if value == procgen_mod.HIDDEN_DOOR:
                    # Draw hidden door sprite
                    img = self.frame(world, "prop_hidden_door")
                    surface.blit(img, (sx, sy))
                    # Highlight when adjacent to player
                    player = world.player
                    if player:
                        ptx = int(player.x // TILE)
                        pty = int(player.y // TILE)
                        if abs(ptx - tx) <= 1 and abs(pty - ty) <= 1:
                            # Draw a subtle highlight ring
                            pygame.draw.rect(surface, (120, 80, 180),
                                             pygame.Rect(sx, sy, TILE, TILE), 1)
                    draw_list.append(("hidden_door", tx, ty))
                    continue
                if value == procgen_mod.WALL:
                    neighbour = False
                    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1)):
                        if level.walkable(tx + dx, ty + dy):
                            neighbour = True
                            break
                    h = _hash2(tx, ty, 7)
                    if h % 29 == 0:
                        name = self._resolve_tile_frame(tiles["wall_torch"], self._tile_anim_tick, tileset)
                    elif h % 41 == 0:
                        name = tiles["wall_skull"]
                    elif h % 5 == 0:
                        name = tiles["wall_cracked"]
                    elif h % 3 == 0:
                        name = tiles["wall_alt"]
                    else:
                        name = tiles["wall"]
                    img = self.frame(world, name)
                    if not neighbour:
                        img = self.dark_wall(world, self.frame(world, tiles["wall"]))
                    surface.blit(img, (sx, sy))
                    draw_list.append(("wall", tx, ty, name))
                    continue
                if (tx, ty) in burning:
                    base_name = tiles.get("floor_burning") or tiles["floor_rubble"]
                    name = self._resolve_tile_frame(base_name, self._tile_anim_tick, tileset)
                    img = self.frame(world, name)
                    img.fill((226, 113, 29, 60), special_flags=pygame.BLEND_RGB_ADD)
                    surface.blit(img, (sx, sy))
                    draw_list.append(("floor_burning", tx, ty))
                    continue
                if (tx, ty) in water:
                    base_name = tiles.get("floor_water") or tiles["pool"]
                    name = self._resolve_tile_frame(base_name, self._tile_anim_tick, tileset)
                    img = self.frame(world, name)
                    surface.blit(img, (sx, sy))
                    _draw_biome_texture(surface, world.biome_id, sx, sy, tx, ty, tile_px)
                    draw_list.append(("floor_water", tx, ty))
                    continue
                # r45: sparse, structured decoration — never per-tile random.
                # Dead Cells-style clarity: plain floors dominate, decoration
                # is rare and biome-appropriate. No hash-based scatter.
                room_kind = level.room_at(tx, ty)
                rk = room_kind.get("kind", "") if room_kind else ""
                # Use a deterministic but sparse pattern: only decorate tiles
                # where (tx + ty) % N == 0, and only in themed rooms
                is_decoration_tile = ((tx + ty) % 5 == 0) or ((tx * 7 + ty * 3) % 11 == 0)
                if rk == "treasure" and is_decoration_tile:
                    name = tiles["floor_coins"]
                elif rk in ("combat", "boss", "secret") and is_decoration_tile:
                    name = tiles["floor_bones"] if (tx % 3 == 0) else tiles["floor_rubble"]
                elif rk in ("shrine", "omen", "gambling") and is_decoration_tile:
                    name = tiles["floor_cracked"]
                elif is_decoration_tile:
                    # corridors/entrance/shop: very sparse wear
                    name = tiles["floor_rubble"]
                else:
                    name = tiles["floor"]
                surface.blit(self.frame(world, name), (sx, sy))
                _draw_biome_texture(surface, world.biome_id, sx, sy, tx, ty, tile_px)
                draw_list.append(("floor", tx, ty, name))

        st = camera.tile_scale
        tile_px = TILE * st
        # -- secret room floors (revealed) --------------------------------
        for room in level.rooms:
            if room.get("kind") != "secret":
                continue
            if not room.revealed:
                continue
            rx = int(room.get("x", 0))
            ry = int(room.get("y", 0))
            rw = int(room.get("w", 8))
            rh = int(room.get("h", 8))
            for tx in range(rx, min(level.w, rx + rw)):
                for ty in range(ry, min(level.h, ry + rh)):
                    if level.tiles[tx][ty] == FLOOR:
                        sx = int(tx * tile_px - ox * st)
                        sy = int(ty * tile_px - oy * st)
                        # r45: sparse decoration in secret rooms too
                        is_dec = ((tx + ty) % 5 == 0) or ((tx * 7 + ty * 3) % 11 == 0)
                        if is_dec and (tx % 3 == 0):
                            name = tiles["floor_bones"]
                        elif is_dec and (tx % 3 == 1):
                            name = tiles["floor_coins"]
                        elif is_dec:
                            name = tiles["floor_blood"]
                        else:
                            name = tiles["floor"]
                        img = self.frame(world, name)
                        if st != 1.0:
                            img = pygame.transform.scale(img, (int(TILE*st), int(TILE*st)))
                        surface.blit(img, (sx, sy))
                        draw_list.append(("secret_floor", tx, ty, name))

        # -- props -------------------------------------------------------
        for prop in level.props:
            sx = int(prop["tx"] * tile_px - ox * st)
            sy = int(prop["ty"] * tile_px - oy * st)
            if sx < -tile_px or sy < -tile_px or sx > camera.view_w or sy > camera.view_h:
                continue
            sprite_name = prop.get("sprite", "")
            # r54: ground glow for light-emitting props
            glow_spec = PROP_GLOW.get(sprite_name)
            if glow_spec is not None:
                glow_color, glow_radius, glow_alpha = glow_spec
                # A restrained, deterministic pulse gives lights and crystals
                # a living presence without moving their authored sprites.
                phase = self._tile_anim_tick * 2.2 + (int(prop["tx"]) * 0.71) + (int(prop["ty"]) * 1.13)
                pulse = 0.88 + 0.12 * math.sin(phase)
                glow_radius = max(2, int(glow_radius * (0.96 + 0.04 * math.sin(phase))))
                glow_alpha = int(glow_alpha * pulse)
                gx = sx + int(tile_px // 2)
                gy = sy + int(tile_px // 2)
                glow_surf = pygame.Surface((glow_radius * 2, glow_radius * 2), pygame.SRCALPHA)
                pygame.draw.circle(glow_surf, (*glow_color, glow_alpha), (glow_radius, glow_radius), glow_radius)
                surface.blit(glow_surf, (gx - glow_radius, gy - glow_radius),
                             special_flags=pygame.BLEND_RGB_ADD)
            img = self.frame(world, sprite_name)
            if st != 1.0:
                img = pygame.transform.scale(img, (int(TILE*st), int(TILE*st)))
            surface.blit(img, (sx, sy))
            draw_list.append(("prop", sprite_name, prop["tx"], prop["ty"]))

        # -- event-room overlays ---------------------------------------
        st = camera.tile_scale  # ensure st is in scope
        tile_px = TILE * st
        for room in level.rooms:
            kind = room.get("kind", "")
            if kind not in ("gambling", "blacksmith", "fountain", "omen"):
                continue
            rx = int(room.get("x", 0))
            ry = int(room.get("y", 0))
            rw = int(room.get("w", 8))
            rh = int(room.get("h", 8))
            for tx in range(rx, min(level.w, rx + rw)):
                for ty in range(ry, min(level.h, ry + rh)):
                    if level.tiles[tx][ty] != FLOOR:
                        continue
                    sx = int(tx * tile_px - ox * st)
                    sy = int(ty * tile_px - oy * st)
                    cx = sx + int(tile_px // 2)
                    cy = sy + int(tile_px // 2)
                    # Draw event-room floor overlay
                    if kind == "gambling":
                        h = _hash2(tx, ty, 7)
                        if h % 3 == 0:
                            icon = self.frame(world, "prop_gold_pile")
                            self._blit_centered(surface, icon, cx, cy, ox, oy)
                    elif kind == "blacksmith":
                        h = _hash2(tx, ty, 11)
                        if h % 3 == 0:
                            icon = self.frame(world, "prop_anvil")
                            self._blit_centered(surface, icon, cx, cy, ox, oy)
                    elif kind == "fountain":
                        h = _hash2(tx, ty, 13)
                        if h % 3 == 0:
                            icon = self.frame(world, "prop_fountain")
                            self._blit_centered(surface, icon, cx, cy, ox, oy)
                    elif kind == "omen":
                        h = _hash2(tx, ty, 17)
                        if h % 3 == 0:
                            icon = self.frame(world, "prop_eye")
                            self._blit_centered(surface, icon, cx, cy, ox, oy)

        # -- pickups -----------------------------------------------------
        for pk in world.pickups:
            if not pk.alive or pk.collected:
                continue
            bob = math.sin((pk.age + pk.bob) * 4.0) * 2.0 if pk.magnet else 0.0
            _draw_contact_shadow(surface, pk.x, pk.y, ox, oy, pk.radius, st)
            img = self.frame(world, pk.sprite)
            self._blit_centered(surface, img, pk.x, pk.y + bob, ox, oy)
            draw_list.append(("pickup", pk.sprite, pk.id))

        # -- monsters ----------------------------------------------------
        for mon in world.monsters:
            if not mon.alive:
                continue
            _draw_contact_shadow(surface, mon.x, mon.y, ox, oy, mon.radius, st)
            # A compact silhouette keyline keeps enemies legible when several
            # palette-locked sprites overlap in a horde.
            _draw_combat_silhouette(surface, mon.x, mon.y, ox, oy, mon.radius,
                                    (8, 7, 13), st)
            if mon.boss:
                # Boss presence is communicated on the ground, not by changing
                # stats or authored sprite art.
                pulse = 0.5 + 0.5 * math.sin(mon.age * 5.0)
                _draw_combat_ring(surface, mon.x, mon.y, ox, oy,
                                  72.0 + pulse * 5.0, (112, 35, 55), 2, st)
                _draw_combat_ring(surface, mon.x, mon.y, ox, oy,
                                  62.0 + pulse * 3.0, (232, 178, 60), 1, st)
            if mon.telegraph > 0.0:
                # Telegraphs sit beneath the actor so the danger zone remains
                # readable even when the attack frame is missing.
                duration = max(0.01, getattr(mon, "telegraph_duration", 0.55))
                progress = 1.0 - mon.telegraph / duration
                pulse = 0.5 + 0.5 * math.sin((mon.age + progress) * 18.0)
                tele_color = (226, 113, 29) if pulse < 0.75 else (255, 210, 92)
                _draw_combat_ring(surface, mon.x, mon.y, ox, oy,
                                  max(30.0, mon.radius + 8.0 + progress * 18.0),
                                  tele_color, 2, st)
                fx, fy = getattr(mon, "facing", (1.0, 0.0))
                tip_x = mon.x + fx * (mon.radius + 22.0 + progress * 18.0)
                tip_y = mon.y + fy * (mon.radius + 22.0 + progress * 18.0)
                pygame.draw.line(surface, tele_color,
                                 (int((mon.x - ox) * st), int((mon.y - oy) * st)),
                                 (int((tip_x - ox) * st), int((tip_y - oy) * st)),
                                 max(1, int(2 * st)))
            img = self.frame(world, mon.current_frame())
            if not mon.boss:
                img = pygame.transform.scale(img, (int(img.get_width() * 1.28),
                                                    int(img.get_height() * 1.28)))
            if mon.boss:
                # Boss sprites are 2x normal size — scale by zoom too so they
                # stay proportionally larger when the camera is zoomed.
                bscale = 2.0 * st
                img = pygame.transform.scale(img, (int(img.get_width() * bscale), int(img.get_height() * bscale)))
            # P2.2: telegraph indicator sprite rendered during windup
            if mon.telegraph > 0.0 and getattr(mon, 'telegraph_indicator', None):
                indicator_name = mon.telegraph_indicator
                if _has_frame(indicator_name):
                    ind_img = self.frame(world, indicator_name)
                    # animate indicator: scale up and fade during windup
                    ind_scale = 1.0 + 0.3 * (1.0 - mon.telegraph / max(0.01, getattr(mon, 'telegraph_duration', 0.55)))
                    ind_img = pygame.transform.scale(ind_img, (int(ind_img.get_width() * ind_scale), int(ind_img.get_height() * ind_scale)))
                    self._blit_centered(surface, ind_img, mon.x, mon.y - 10 - ind_img.get_height() // 2 - 4, ox, oy)
            if mon.telegraph > 0.0 or (mon.elite and mon.hit_flash <= 0.0):
                # telegraphed hits glow; elites get a warm rim
                glow = img.copy()
                glow.fill((90, 30, 12, 0) if mon.telegraph > 0.0 else (40, 20, 60, 0),
                          special_flags=pygame.BLEND_RGB_ADD)
                self._blit_centered(surface, glow, mon.x, mon.y, ox, oy)
            if mon.hit_flash > 0.0:
                img = self.white(img, key=("monster", mon.monster_id))
            self._blit_centered(surface, img, mon.x, mon.y, ox, oy)
            if (mon.boss or mon.elite) and mon.hp < mon.stats.max_hp():
                cb_mode = getattr(world, "settings", {}).get("colourblind_mode", "off")
                self._health_bar(surface, mon.x - ox, mon.y - oy - (34 if mon.boss else 18),
                                 mon.hp_fraction(), 40 if mon.boss else 26,
                                 colourblind_mode=cb_mode)
            # P2.5: combo aura visual feedback
            _draw_combo_aura(self, world, mon, surface, ox, oy)
            draw_list.append(("monster", mon.monster_id, mon.id))

        # -- projectiles -------------------------------------------------
        for proj in world.projectiles:
            if not proj.alive:
                continue
            # Directional streaks make fast bolts readable without allocating
            # particles or consuming the deterministic gameplay RNG.
            speed = proj.speed()
            if speed > 1.0:
                nx, ny = proj.vx / speed, proj.vy / speed
                trail_len = min(34.0, 10.0 + speed * 0.045)
                trail_color = (226, 113, 29) if proj.owner == "monster" else (180, 220, 255)
                start = ((proj.x - nx * trail_len - ox) * st,
                         (proj.y - ny * trail_len - oy) * st)
                end = ((proj.x - ox) * st, (proj.y - oy) * st)
                pygame.draw.line(surface, trail_color,
                                 (int(start[0]), int(start[1])),
                                 (int(end[0]), int(end[1])), max(1, int(2 * st)))
                pygame.draw.circle(surface, (246, 242, 232),
                                   (int(end[0]), int(end[1])), max(1, int(2 * st)))
            img = self.frame(world, proj.sprite)
            if proj.owner == "monster":
                img = pygame.transform.flip(img, True, False)
            self._blit_centered(surface, img, proj.x, proj.y, ox, oy)
            draw_list.append(("projectile", proj.sprite, proj.id))

        # -- player ------------------------------------------------------
        player = world.player
        settings = getattr(world, "settings", {}) or {}
        if player.alive:
            _draw_contact_shadow(surface, player.x, player.y, ox, oy, player.radius, st)
            name, flip = player.current_frame()
            img = self.frame(world, name, flip=flip)
            img = pygame.transform.scale(img, (int(img.get_width() * 1.22),
                                               int(img.get_height() * 1.22)))
            if player.hit_flash > 0.0:
                # P2.6: reduced_flashing - reduce hit_flash intensity
                if settings.get("reduced_flashing", False):
                    img = self.white(img)
                    img.fill((255, 255, 255, int(img.get_alpha() or 255) // 2),
                             special_flags=pygame.BLEND_RGBA_MULT)
                else:
                    img = self.white(img)
            self._blit_centered(surface, img, player.x, player.y, ox, oy)
            draw_list.append(("player", name, player.id))
            # P2.5: combo aura visual feedback for player
            _draw_combo_aura(self, world, player, surface, ox, oy)
            if player.swing_timer > 0.0:
                fx, fy = player.facing
                length = max(0.001, (fx * fx + fy * fy) ** 0.5)
                arc_img = self.frame(world, "vfx_slash")
                self._blit_centered(surface, arc_img, player.x + fx / length * 20,
                                    player.y + fy / length * 20, ox, oy)
                draw_list.append(("vfx_slash", player.id))
        else:
            name, flip = player.current_frame()
            img = self.frame(world, name, flip=flip)
            self._blit_centered(surface, img, player.x, player.y, ox, oy)
            draw_list.append(("player", name, player.id))

        # -- particles + vfx --------------------------------------------
        world.particles.draw(surface, camera)
        for sprite in world.particles.sprites:
            sx = sprite["x"] - ox
            sy = sprite["y"] - oy
            if sx < -64 or sy < -64 or sx > camera.view_w + 64 or sy > camera.view_h + 64:
                continue
            img = self.frame(world, sprite["name"], scale=float(sprite.get("scale", 1.0)))
            fade = max(0.25, min(1.0, sprite["life"] / max(0.001, sprite["max_life"])))
            if fade < 0.99:
                img = img.copy()
                shade = int(255 * (1.0 - fade))
                img.fill((shade, shade, shade, 0), special_flags=pygame.BLEND_RGB_SUB)
            self._blit_centered(surface, img, sprite["x"], sprite["y"], ox, oy)
            draw_list.append(("vfx", sprite["name"]))

        # P4.4: scorch decals
        self.draw_scorch_decals(surface, world, ox, oy)

        # P2.6: respect damage_numbers setting
        settings = getattr(world, "settings", {}) or {}
        if settings.get("damage_numbers", True) or world.headless:
            cb_mode = settings.get("colourblind_mode", "off")
            world.damage_numbers.draw(surface, camera, colourblind_mode=cb_mode)
        world.floating.draw(surface, camera.view_w // 2, 96, scale=2)

        # -- lighting (P4.1) ----------------------------------------------
        from game.engine import lighting as _light
        _light.render_lighting(surface, world, ox, oy, dt)

        # P2.6: reduced_flashing - dampen screen_flash and vignette
        reduced_flashing = getattr(world, "settings", {}).get("reduced_flashing", False)
        if world.screen_flash > 0.0:
            flash_alpha = int(min(0.55, world.screen_flash) * 110)
            if reduced_flashing:
                flash_alpha = flash_alpha // 2
            flash = pygame.Surface(self.size, pygame.SRCALPHA)
            flash.fill((140, 20, 30, flash_alpha))
            surface.blit(flash, (0, 0))
        # P2.6: reduced_flashing - reduce vignette intensity
        vig = self.vignette()
        if reduced_flashing:
            # Preserve the accessibility setting while reusing the smooth
            # cached gradient. Only the overlay alpha is reduced.
            vig_scaled = vig.copy()
            alpha = pygame.surfarray.pixels_alpha(vig_scaled)
            alpha[:] = (alpha.astype("uint16") // 2).astype("uint8")
            del alpha
            surface.blit(vig_scaled, (0, 0))
        else:
            surface.blit(vig, (0, 0))

        # P4.4: floor transition fade overlay
        fade_surf = self.floor_transition_fade(world)
        if fade_surf is not None:
            surface.blit(fade_surf, (0, 0))

        world.render_list = draw_list
        return draw_list

    # -- helpers ---------------------------------------------------------
    def _blit_centered(self, surface, img, wx, wy, ox, oy):
        st = getattr(self, "_tile_scale", 1.0)
        # World pixel to screen pixel after zoom
        sx = int((wx - ox) * st - img.get_width() / 2.0)
        sy = int((wy - oy) * st - img.get_height() / 2.0)
        if st != 1.0:
            # Scale the image to match zoom
            new_w = int(img.get_width() * st)
            new_h = int(img.get_height() * st)
            if new_w > 0 and new_h > 0:
                img = pygame.transform.scale(img, (new_w, new_h))
        surface.blit(img, (sx, sy))

    def _health_bar(self, surface, cx, cy, fraction, width, colourblind_mode="off"):
        height = 4
        x = int(cx - width / 2)
        bg_col = rarity_colour(1, colourblind_mode)
        bar_col = rarity_colour(2, colourblind_mode)
        danger_col = rarity_colour(4, colourblind_mode)
        pygame.draw.rect(surface, (11, 10, 16), pygame.Rect(x - 1, int(cy) - 1, width + 2, height + 2))
        pygame.draw.rect(surface, bg_col, pygame.Rect(x, int(cy), width, height))
        filled = int(width * max(0.0, min(1.0, fraction)))
        if filled > 0:
            # Blend from danger to bar colour based on hp fraction
            if fraction < 0.3:
                draw_col = danger_col
            else:
                draw_col = bar_col
            pygame.draw.rect(surface, draw_col, pygame.Rect(x, int(cy), filled, height))

    def _is_door_locked(self, world, tx, ty):
        """Check if a door tile at (tx, ty) is locked.

        A DOOR tile is locked if the room it belongs to has not
        had its reward chosen yet.
        """
        if not hasattr(world, "room_doors"):
            return True
        for room_id, info in world.room_doors.items():
            if (tx, ty) in info.get("doors", []):
                return info.get("locked", True)
        return True

    def draw_scorch_decals(self, surface, world, ox, oy):
        """P4.4: render scorch/decal marks on the floor."""
        camera = world.camera
        for decal in world.scorch_decals:
            if decal["life"] <= 0:
                continue
            sx = decal["x"] - ox
            sy = decal["y"] - oy
            if sx < -64 or sy < -64 or sx > camera.view_w + 64 or sy > camera.view_h + 64:
                continue
            fade = max(0.0, min(1.0, decal["life"] / max(0.001, decal["max_life"])))
            alpha = int(120 * fade)
            size = 32
            s = pygame.Surface((size, size), pygame.SRCALPHA)
            pygame.draw.circle(s, (60, 20, 8, alpha), (size // 2, size // 2), size // 2)
            surface.blit(s, (sx - size // 2, sy - size // 2))

    def floor_transition_fade(self, world):
        """P4.4: render a full-screen fade overlay during floor transitions.
        0.5s fade to black, then fade in (new floor).
        """
        fade = world.floor_transition_fade
        if fade <= 0.0 or not world.transition_fade_active:
            return None
        half = 0.25
        if fade >= half:
            alpha = int(min(1.0, (fade - half) / half) * 180)
        else:
            alpha = int((fade / half) * 180)
        if alpha <= 0:
            return None
        surf = pygame.Surface(self.size, pygame.SRCALPHA)
        surf.fill((0, 0, 0, alpha))
        return surf

    def locked(self, img):
        key = id(img)
        out = self._locked_tint.get(key)
        if out is None:
            out = img.copy()
            out.fill((60, 30, 90, 0), special_flags=pygame.BLEND_RGB_ADD)
            self._locked_tint[key] = out
        return out
