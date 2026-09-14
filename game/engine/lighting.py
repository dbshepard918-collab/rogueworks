"""Lighting system for P4.1: real light radius, line-of-sight fog, flicker.

P4.1 replaces the old single-halo approach with per-light additive blits:

1. A dark fog overlay is composited over the scene (BLEND_RGB_MULT),
   making unlit areas dark.
2. Light circles are drawn on a separate surface with distance falloff
   (quadratic) and composited additively (BLEND_RGB_ADD).
3. Line-of-sight from the player: tiles not visible from the player
   receive dramatically reduced light.
4. Each light has a flicker offset driven by sin(time * speed), seeded
   deterministically from position so the pattern is reproducible per seed.
"""

from __future__ import annotations

import math

import pygame

TILE = 32

LIGHT_EMITTING_PROPS = frozenset({
    "prop_brazier", "prop_candles", "prop_lava_vent", "prop_forge",
    "prop_fountain", "prop_crystal", "prop_altar", "prop_anvil",
})

# Per-biome ambient fog colour
_AMBIENT_COLORS = {
    "catacombs": (11, 10, 16),
    "ember_warrens": (30, 12, 8),
    "drowned_vaults": (8, 22, 38),
}


def _hash2(x, y, salt=0):
    h = (x * 73856093) ^ (y * 19349663) ^ (salt * 83492791)
    return abs(h)


class LightSource:
    __slots__ = ("x", "y", "radius", "colour", "flicker_phase",
                 "flicker_speed", "intensity", "kind")

    def __init__(self, x, y, radius, colour=(255, 220, 160),
                 flicker_speed=0.0, intensity=1.0, kind="lantern"):
        self.x = float(x)
        self.y = float(y)
        self.radius = float(radius)
        self.colour = tuple(colour)
        self.flicker_phase = _hash2(int(x), int(y), 0x9f2a) / 2147483647.0 * 6.283185
        self.flicker_speed = flicker_speed
        self.intensity = intensity
        self.kind = kind

    @property
    def effective_radius(self):
        if self.flicker_speed <= 0:
            return self.radius
        return max(1.0, self.radius + math.sin(self.flicker_phase) * self.radius * 0.04)


def _build_light_sources(world, dt):
    lights = []
    level = world.level
    if level is None:
        return lights

    player = world.player
    if player and player.alive:
        from game.systems import biome_mods as _bm
        try:
            base_radius = _bm.lantern_radius(world, profile=world.profile)
        except Exception:
            base_radius = 220.0
        lights.append(LightSource(
            player.x, player.y, base_radius,
            colour=(255, 220, 160),
            flicker_speed=1.5,
            intensity=1.0,
            kind="lantern",
        ))

    for prop in level.props:
        sprite = prop.get("sprite", "")
        if sprite not in LIGHT_EMITTING_PROPS:
            continue
        tx = prop.get("tx", 0)
        ty = prop.get("ty", 0)
        px = tx * TILE + TILE // 2
        py = ty * TILE + TILE // 2

        if sprite == "prop_brazier":
            lights.append(LightSource(px, py, 120, (255, 140, 40),
                                       flicker_speed=2.0, intensity=0.9, kind="fire"))
        elif sprite == "prop_candles":
            lights.append(LightSource(px, py, 90, (255, 200, 80),
                                       flicker_speed=3.5, intensity=0.6, kind="candle"))
        elif sprite == "prop_lava_vent":
            lights.append(LightSource(px, py, 150, (255, 80, 20),
                                       flicker_speed=1.0, intensity=1.0, kind="lava"))
        elif sprite == "prop_forge":
            lights.append(LightSource(px, py, 130, (200, 100, 30),
                                       flicker_speed=1.8, intensity=0.85, kind="forge"))
        elif sprite == "prop_fountain":
            lights.append(LightSource(px, py, 70, (100, 180, 255),
                                       flicker_speed=0.5, intensity=0.5, kind="water"))
        elif sprite == "prop_crystal":
            lights.append(LightSource(px, py, 80, (140, 200, 255),
                                       flicker_speed=0.8, intensity=0.6, kind="crystal"))
        elif sprite == "prop_altar":
            lights.append(LightSource(px, py, 100, (180, 120, 255),
                                       flicker_speed=0.3, intensity=0.55, kind="altar"))
        elif sprite == "prop_anvil":
            lights.append(LightSource(px, py, 60, (180, 160, 140),
                                       flicker_speed=0.2, intensity=0.35, kind="metal"))

    return lights


def _line_of_sight(tiles, x0, y0, x1, y1):
    dx = abs(x1 - x0)
    dy = abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy
    x, y = x0, y0
    while x != x1 or y != y1:
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x += sx
        if e2 < dx:
            err += dx
            y += sy
        if 0 <= x < len(tiles) and 0 <= y < len(tiles[0]):
            if tiles[x][y] == 1:
                return False
    return True


def _build_visibility_mask(level, player_tx, player_ty, sight_radius_tiles):
    w = level.w
    h = level.h
    tiles = level.tiles
    visible = [[False] * h for _ in range(w)]
    r = sight_radius_tiles
    for tx in range(max(0, player_tx - r), min(w, player_tx + r + 1)):
        for ty in range(max(0, player_ty - r), min(h, player_ty + r + 1)):
            if _line_of_sight(tiles, player_tx, player_ty, tx, ty):
                visible[tx][ty] = True
    return visible


def render_lighting(surface, world, ox, oy, dt):
    """Render the lighting overlay onto *surface*.

    Called from Renderer.draw() after all scene elements are drawn.
    Composites a dark fog over the scene, then adds light circles
    with distance falloff and line-of-sight visibility.
    """
    level = world.level
    if level is None:
        _fill_dark(surface)
        return

    lights = _build_light_sources(world, dt)
    if not lights:
        _fill_dark(surface)
        return

    w = surface.get_width()
    h = surface.get_height()

    # Build visibility mask from player
    player = world.player
    if player and player.alive:
        pl_tx = int(player.x // TILE)
        pl_ty = int(player.y // TILE)
        vis = _build_visibility_mask(level, pl_tx, pl_ty, 15)
    else:
        vis = None

    # Step 1: Dark fog overlay using BLEND_RGB_MULT
    # This darkens everything — unlit areas become very dark
    biome_id = world.biome_id
    ambient = _AMBIENT_COLORS.get(biome_id, (11, 10, 16))
    fog_alpha = 200  # High alpha = very dark unlit areas
    fog_surf = pygame.Surface((w, h), pygame.SRCALPHA)
    fog_surf.fill((*ambient, fog_alpha))
    surface.blit(fog_surf, (0, 0), special_flags=pygame.BLEND_RGB_MULT)

    # Step 2: Draw light circles on a separate surface, then composite additively
    light_surf = pygame.Surface((w, h), pygame.SRCALPHA)
    light_surf.fill((0, 0, 0, 0))

    for light in lights:
        radius = int(light.effective_radius)
        if radius < 4:
            continue

        lx = int(light.x - ox)
        ly = int(light.y - oy)

        if lx + radius < 0 or lx - radius > w or ly + radius < 0 or ly - radius > h:
            continue

        tx0 = max(0, (lx - radius) // TILE)
        tx1 = min(w - 1, (lx + radius) // TILE)
        ty0 = max(0, (ly - radius) // TILE)
        ty1 = min(h - 1, (ly + radius) // TILE)

        for tx in range(tx0, tx1 + 1):
            for ty in range(ty0, ty1 + 1):
                cx = tx * TILE + TILE // 2 - ox
                cy = ty * TILE + TILE // 2 - oy

                dx = cx - lx
                dy = cy - ly
                dist_sq = dx * dx + dy * dy
                if dist_sq > radius * radius:
                    continue

                dist = math.sqrt(max(1, dist_sq))
                falloff = max(0.0, 1.0 - (dist / radius) ** 2)
                if falloff < 0.02:
                    continue

                # Visibility check from player
                if vis is not None:
                    vtx = min(tx, len(vis) - 1)
                    vty = min(ty, len(vis[0]) - 1)
                    if not vis[vtx][vty]:
                        falloff *= 0.05  # Deep shadow

                alpha = int(falloff * 220 * light.intensity)
                if alpha < 1:
                    continue

                # Draw a large soft circle for this tile's light contribution
                pixel_radius = max(1, TILE)
                pygame.draw.circle(light_surf, (*light.colour, alpha),
                                   (cx, cy), pixel_radius)

    # Composite light additively onto the fog-darkened scene
    surface.blit(light_surf, (0, 0), special_flags=pygame.BLEND_RGB_ADD)


def _fill_dark(surface):
    biome_id = getattr(surface, '_biome_id', 'catacombs')
    ambient = _AMBIENT_COLORS.get(biome_id, (11, 10, 16))
    w = surface.get_width()
    h = surface.get_height()
    fog_surf = pygame.Surface((w, h), pygame.SRCALPHA)
    fog_surf.fill((*ambient, 210))
    surface.blit(fog_surf, (0, 0), special_flags=pygame.BLEND_RGB_MULT)
