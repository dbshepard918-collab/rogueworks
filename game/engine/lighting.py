"""Lighting: a real light map, not a flat dark multiply (P4.1, repaired).

The first implementation made the dungeon unreadable — three separate defects:

1. **A flat dark multiply.** The "fog" step blended the whole frame with
   `BLEND_RGB_MULT` against the near-black ambient colour (11, 10, 16), so *every*
   pixel — floor tiles included — was reduced to ~4% brightness. The scene was
   dark, not lit.
2. **A solid 32 px disc stamped per tile.** Each tile inside a light drew a
   *solid* circle of radius `TILE` at its centre, so a 140 px lantern stamped
   ~190 overlapping discs: that is where the "large pixelated circles" with
   scalloped edges came from. There was no gradient at all.
3. **Line-of-sight in the wrong coordinate space.** The visibility mask is
   indexed by *level* tile, but it was queried with *screen* tile indices, so
   shadows landed in arbitrary places.

The repaired model is the standard one: build a **light map** that starts at a
visible ambient level, add smooth radial gradients to it, darken tiles the player
cannot see, then multiply the scene by that map once. Ambient ~30% keeps the
layout readable everywhere; lights push it back to full brightness; only genuine
line-of-sight shadowing goes dark.
"""

from __future__ import annotations

import math

import pygame

TILE = 32

LIGHT_EMITTING_PROPS = frozenset({
    "prop_brazier", "prop_candles", "prop_lava_vent", "prop_forge",
    "prop_fountain", "prop_crystal", "prop_altar", "prop_anvil",
})

#: Per-biome ambient light level, used as the *multiplier* applied to the scene
#: where nothing is lit.  Multiplication can only darken, so this sits near white:
#: the catacombs tile art measures ~78 mean luminance, and the previous
#: near-black (11, 10, 16) multiplied it down to ~26 — indistinguishable from
#: black on screen.  At ~84% the floor reads at ~65 luminance (dim but legible),
#: lights add on top up to full brightness, and the only genuinely dark places
#: are tiles the player cannot see.
_AMBIENT = {
    "catacombs": (232, 226, 240),
    "ember_warrens": (245, 205, 186),
    "drowned_vaults": (208, 228, 248),
}

#: How hard unseen-but-lit tiles are pushed down (multiplier, 0-255). Light is an
#: *accent* in this game, not the only thing that makes anything visible: at ~59%
#: the dungeon stays legible everywhere and the lantern reads as warmth on top.
#: The old 36% (on a near-black ambient) is what made the map look like trash.
_SHADOW_LEVEL = 150
#: Tiles the player can currently see; beyond this the lantern is all there is.
_SIGHT_RADIUS_TILES = 15

_gradient_cache: dict = {}
_vis_cache: dict = {}


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


def _radial_gradient(radius, colour):
    """A smooth additive falloff disc, cached per (radius, colour).

    The falloff is baked into the **RGB values**, not the alpha: an
    additive blit (`BLEND_RGB_ADD`) adds raw RGB and ignores alpha, so a
    gradient carried in the alpha channel adds at full strength everywhere and
    produces a flat disc — which is exactly what it did before this was fixed
    (the lantern left the player's own tile unlit at 1 distinct colour).

    Rings are painted outer-to-inner; `pygame.draw.circle` writes pixels rather
    than blending, so the innermost, brightest ring wins at the core.
    """
    key = (radius, colour)
    cached = _gradient_cache.get(key)
    if cached is not None:
        return cached

    steps = max(10, min(48, radius // 3))
    diameter = radius * 2
    surf = pygame.Surface((diameter, diameter))          # opaque: RGB carries the falloff
    surf.fill((0, 0, 0))
    for i in range(steps, 0, -1):
        t = i / float(steps)                             # 1.0 rim -> 0 core
        r = int(radius * t)
        if r <= 0:
            continue
        falloff = (1.0 - t) ** 2
        scaled = (int(colour[0] * falloff), int(colour[1] * falloff), int(colour[2] * falloff))
        if max(scaled) <= 0:
            continue
        pygame.draw.circle(surf, scaled, (radius, radius), r)
    _gradient_cache[key] = surf
    return surf


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
    else:
        base_radius = 220.0

    for prop in level.props:
        sprite = prop.get("sprite", "")
        if sprite not in LIGHT_EMITTING_PROPS:
            continue
        tx = prop.get("tx", 0)
        ty = prop.get("ty", 0)
        px = tx * TILE + TILE // 2
        py = ty * TILE + TILE // 2

        spec = {
            "prop_brazier":    (150, (255, 150, 50), 2.0, 0.9),
            "prop_candles":    (105, (255, 205, 90), 3.5, 0.6),
            "prop_lava_vent":  (175, (255, 95, 25), 1.0, 1.0),
            "prop_forge":      (155, (215, 110, 40), 1.8, 0.85),
            "prop_fountain":   (95,  (110, 190, 255), 0.5, 0.5),
            "prop_crystal":    (110, (150, 205, 255), 0.8, 0.6),
            "prop_altar":      (125, (190, 130, 255), 0.3, 0.55),
            "prop_anvil":      (80,  (190, 170, 150), 0.2, 0.35),
        }.get(sprite)
        if spec is None:
            continue
        radius, colour, speed, intensity = spec
        lights.append(LightSource(px, py, radius, colour=colour,
                                  flicker_speed=speed, intensity=intensity,
                                  kind=sprite.replace("prop_", "")))
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
            if tiles[x][y] == 1:                      # procgen.WALL
                return False
    return True


def _visibility_mask(level, player_tx, player_ty):
    """Visible-tile mask, cached per (level identity, player tile).

    The Bresenham sweep is ~900 rays; recomputing it every frame for an
    unchanged player tile is pure waste, so it is memoised on the tile.
    """
    key = (id(level), player_tx, player_ty, len(level.tiles))
    cached = _vis_cache.get(key)
    if cached is not None:
        return cached

    w = level.w
    h = level.h
    tiles = level.tiles
    r = _SIGHT_RADIUS_TILES
    visible = [[False] * h for _ in range(w)]
    for tx in range(max(0, player_tx - r), min(w, player_tx + r + 1)):
        for ty in range(max(0, player_ty - r), min(h, player_ty + r + 1)):
            if _line_of_sight(tiles, player_tx, player_ty, tx, ty):
                visible[tx][ty] = True

    if len(_vis_cache) > 8:                           # tiny LRU; levels are big
        _vis_cache.clear()
    _vis_cache[key] = visible
    return visible


def render_lighting(surface, world, ox, oy, dt):
    """Multiply the drawn scene by a light map.

    Called from ``Renderer.draw()`` after the level, entities and effects are on
    the surface, so everything is lit consistently.  Never raises: lighting must
    not be able to take the game down.
    """
    w, h = surface.get_size()
    level = world.level
    biome = getattr(world, "biome_id", "catacombs")

    try:
        lightmap = _compose_lightmap(world, level, ox, oy, w, h, biome, dt)
    except Exception:
        return                                        # leave the scene unlit-but-drawn
    surface.blit(lightmap, (0, 0), special_flags=pygame.BLEND_RGB_MULT)


def _compose_lightmap(world, level, ox, oy, w, h, biome, dt):
    ambient = _AMBIENT.get(biome, _AMBIENT["catacombs"])
    lightmap = pygame.Surface((w, h))
    lightmap.fill(ambient)

    for light in _build_light_sources(world, dt):
        radius = int(light.effective_radius)
        if radius < 4:
            continue
        lx = int(light.x - ox)
        ly = int(light.y - oy)
        if lx + radius < 0 or lx - radius > w or ly + radius < 0 or ly - radius > h:
            continue
        colour = (tuple(int(c * light.intensity) for c in light.colour)
                  if light.intensity < 1.0 else light.colour)
        gradient = _radial_gradient(radius, colour)
        lightmap.blit(gradient, (lx - radius, ly - radius),
                      special_flags=pygame.BLEND_RGB_ADD)

    # Line of sight: darken tiles the player cannot see, in LEVEL tile space.
    player = getattr(world, "player", None)
    if level is not None and player is not None and player.alive:
        pl_tx = int(player.x // TILE)
        pl_ty = int(player.y // TILE)
        vis = _visibility_mask(level, pl_tx, pl_ty)
        shadow = pygame.Surface((TILE, TILE))
        shadow.fill((_SHADOW_LEVEL, _SHADOW_LEVEL, _SHADOW_LEVEL))
        level_w, level_h = level.w, level.h
        for sy in range(0, h + TILE, TILE):
            wy = int((sy + TILE // 2 + oy) // TILE)
            if wy < 0 or wy >= level_h:
                continue
            for sx in range(0, w + TILE, TILE):
                wx = int((sx + TILE // 2 + ox) // TILE)
                if wx < 0 or wx >= level_w:
                    continue
                if not vis[wx][wy]:
                    lightmap.blit(shadow, (sx, sy), special_flags=pygame.BLEND_RGB_MULT)
    return lightmap


def _fill_dark(surface):
    """Fallback for a frame with no level: dim, not black."""
    ambient = _AMBIENT["catacombs"]
    fog = pygame.Surface(surface.get_size())
    fog.fill(ambient)
    surface.blit(fog, (0, 0), special_flags=pygame.BLEND_RGB_MULT)
