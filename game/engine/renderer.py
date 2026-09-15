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

TILE = 32


def _hash2(x, y, salt=0):
    h = (x * 73856093) ^ (y * 19349663) ^ (salt * 83492791)
    return abs(h)


# Element colors for combo aura rendering
COMBO_ELEMENT_COLORS = {
    "steam_burst": (200, 180, 120, 80),    # warm amber steam
    "shatter": (100, 180, 230, 60),         # icy blue shatter
    "frost_burn": (100, 200, 80, 70),       # ice-fire blend
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

    # -- frame cache -----------------------------------------------------
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
            w, h = self.size
            surf = pygame.Surface(self.size, pygame.SRCALPHA)
            cx, cy = w / 2.0, h / 2.0
            max_d = (cx * cx + cy * cy) ** 0.5
            step = 12
            for i in range(0, step):
                t = i / float(step)
                radius = max_d * (0.45 + 0.55 * t)
                alpha = int(70 * (t ** 2))
                if alpha <= 0:
                    continue
                pygame.draw.circle(surf, (11, 10, 16, alpha), (int(cx), int(cy)), int(radius), step)
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
                        name = tiles["wall_torch"]
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
                    name = tiles.get("floor_burning") or tiles["floor_rubble"]
                    img = self.frame(world, name)
                    img.fill((226, 113, 29, 60), special_flags=pygame.BLEND_RGB_ADD)
                    surface.blit(img, (sx, sy))
                    draw_list.append(("floor_burning", tx, ty))
                    continue
                if (tx, ty) in water:
                    name = tiles.get("floor_water") or tiles["pool"]
                    img = self.frame(world, name)
                    surface.blit(img, (sx, sy))
                    draw_list.append(("floor_water", tx, ty))
                    continue
                h = _hash2(tx, ty, 3)
                bucket = h % 37
                # r44 cohesion fix: decoration is clustered per-ROOM by room kind
                # (uniform per-tile scatter looked like jumbled salad - bones next
                # to coins next to blood with no logic). The room's theme picks ONE
                # dressing family; within the room, tiles vary naturally around it.
                room_kind = level.room_at(tx, ty)
                rk = room_kind.get("kind", "") if room_kind else ""
                if rk == "treasure":
                    # coin pockets: ~1/3 of the floor glitters, nothing gory
                    name = (tiles["floor_coins"] if bucket % 3 == 0
                            else tiles["floor_alt2"] if bucket % 5 == 0
                            else tiles["floor"])
                elif rk in ("combat", "boss", "secret"):
                    # battle-scarred: bones/rubble/blood, never coins
                    if bucket < 6:
                        name = tiles["floor_bones"]
                    elif bucket < 12:
                        name = tiles["floor_rubble"]
                    elif bucket < 15:
                        name = tiles["floor_blood"]
                    elif bucket < 25:
                        name = tiles["floor_cracked"]
                    else:
                        name = tiles["floor"]
                elif rk in ("shrine", "omen", "gambling"):
                    # solemn/clean: cracked + alt wear only, no gore or glitter
                    if bucket < 10:
                        name = tiles["floor_cracked"]
                    elif bucket < 22:
                        name = tiles["floor_alt"]
                    else:
                        name = tiles["floor"]
                else:
                    # corridors/entrance/shop/fountain/blacksmith: mostly clean
                    # plain floors with sparse, mild wear
                    if bucket < 8:
                        name = tiles["floor_rubble"]
                    elif bucket < 16:
                        name = tiles["floor_alt"]
                    elif bucket < 24:
                        name = tiles["floor_alt2"]
                    else:
                        name = tiles["floor"]
                surface.blit(self.frame(world, name), (sx, sy))
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
                        h = _hash2(tx, ty, 3)
                        bucket = h % 37
                        if bucket == 0:
                            name = tiles["floor_bones"]
                        elif bucket == 1:
                            name = tiles["floor_coins"]
                        elif bucket < 4:
                            name = tiles["floor_blood"]
                        elif bucket < 9:
                            name = tiles["floor_rubble"]
                        elif bucket < 15:
                            name = tiles["floor_alt"]
                        elif bucket < 20:
                            name = tiles["floor_alt2"]
                        elif bucket < 25:
                            name = tiles["floor_cracked"]
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
            img = self.frame(world, prop["sprite"])
            if st != 1.0:
                img = pygame.transform.scale(img, (int(TILE*st), int(TILE*st)))
            surface.blit(img, (sx, sy))
            draw_list.append(("prop", prop["sprite"], prop["tx"], prop["ty"]))

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
            img = self.frame(world, pk.sprite)
            self._blit_centered(surface, img, pk.x, pk.y + bob, ox, oy)
            draw_list.append(("pickup", pk.sprite, pk.id))

        # -- monsters ----------------------------------------------------
        for mon in world.monsters:
            if not mon.alive:
                continue
            img = self.frame(world, mon.current_frame())
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
            img = self.frame(world, proj.sprite)
            if proj.owner == "monster":
                img = pygame.transform.flip(img, True, False)
            self._blit_centered(surface, img, proj.x, proj.y, ox, oy)
            draw_list.append(("projectile", proj.sprite, proj.id))

        # -- player ------------------------------------------------------
        player = world.player
        settings = getattr(world, "settings", {}) or {}
        if player.alive:
            name, flip = player.current_frame()
            img = self.frame(world, name, flip=flip)
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
            # Create a dimmer vignette by scaling alpha
            vig_scaled = vig.copy()
            # Scale down alpha channel by half
            vig_scaled.fill((0, 0, 0, 0), special_flags=pygame.BLEND_RGB_ADD)
            # Use a simpler approach: create half-alpha version
            w, h = self.size
            half_vig = pygame.Surface(self.size, pygame.SRCALPHA)
            half_vig.fill((0, 0, 0, 0))
            # Draw a dimmer vignette
            cx, cy = w / 2.0, h / 2.0
            max_d = (cx * cx + cy * cy) ** 0.5
            step = 12
            for i in range(0, step):
                t = i / float(step)
                radius = max_d * (0.45 + 0.55 * t)
                alpha = int(35 * (t ** 2))  # Half of 70
                if alpha <= 0:
                    continue
                pygame.draw.circle(half_vig, (11, 10, 16, alpha),
                                   (int(cx), int(cy)), int(radius), step)
            surface.blit(half_vig, (0, 0))
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
            if sx < -32 or sy < -32 or sx > camera.view_w + 32 or sy > camera.view_h + 32:
                continue
            fade = max(0.0, min(1.0, decal["life"] / max(0.001, decal["max_life"])))
            alpha = int(120 * fade)
            size = 16
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
