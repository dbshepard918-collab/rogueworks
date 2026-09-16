"""Camera: dead-zone follow, smoothing, clamp to level bounds, integer snap."""

import pygame


class Camera:
    def __init__(self, view_w=1280, view_h=720, tile=64):
        self.view_w = view_w
        self.view_h = view_h
        self.tile = tile
        self.tile_scale = 1.0  # 1.0 shows 20 world tiles across at the 64px tile contract.
        self.x = 0.0
        self.y = 0.0
        self.dead_zone = 144
        self.smooth = 7.0
        self.look_ahead = 56.0
        self.shake = 0.0
        self.shake_mag = 0.0
        self.offset_x = 0
        self.offset_y = 0
        self.kick = 0.0           # P4.4: dead-zone camera kick
        self.kick_x = 0           # P4.4: kick offset X
        self.kick_y = 0           # P4.4: kick offset Y
        self.shake_enabled = True       # P2.1: toggle for screen shake

    def scaled_tile(self):
        """Tile size in screen pixels after zoom."""
        return int(self.tile * self.tile_scale)

    def scaled_view(self):
        """Visible world area in world pixels after zoom."""
        return (self.view_w / self.tile_scale, self.view_h / self.tile_scale)

    def center_on(self, px, py, level_w=0, level_h=0):
        vw, vh = self.scaled_view()
        self.x = px - vw / 2.0
        self.y = py - vh / 2.0
        self._clamp(level_w, level_h)

    def _clamp(self, level_w, level_h):
        vw, vh = self.scaled_view()
        world_w = level_w * self.tile
        world_h = level_h * self.tile
        if world_w <= vw:
            self.x = (world_w - vw) / 2.0
        else:
            self.x = max(0.0, min(self.x, world_w - vw))
        if world_h <= vh:
            self.y = (world_h - vh) / 2.0
        else:
            self.y = max(0.0, min(self.y, world_h - vh))

    def follow(self, px, py, level_w, level_h, dt, facing=(0.0, 0.0)):
        vw, vh = self.scaled_view()
        fx, fy = facing
        length = (fx * fx + fy * fy) ** 0.5
        if length > 0.001:
            fx, fy = fx / length, fy / length
        look_x = fx * self.look_ahead
        look_y = fy * self.look_ahead
        target_x = px + look_x - vw / 2.0
        target_y = py + look_y - vh / 2.0
        dz = self.dead_zone
        cx = self.x + vw / 2.0
        cy = self.y + vh / 2.0
        if px + look_x - cx > dz / 2.0:
            target_x = self.x + (px + look_x - cx - dz / 2.0)
        elif cx - (px + look_x) > dz / 2.0:
            target_x = self.x - (cx - (px + look_x) - dz / 2.0)
        else:
            target_x = self.x
        if py + look_y - cy > dz / 2.0:
            target_y = self.y + (py + look_y - cy - dz / 2.0)
        elif cy - (py + look_y) > dz / 2.0:
            target_y = self.y - (cy - (py + look_y) - dz / 2.0)
        else:
            target_y = self.y

        k = min(1.0, self.smooth * dt)
        self.x += (target_x - self.x) * k
        self.y += (target_y - self.y) * k
        self._clamp(level_w, level_h)

    def add_shake(self, magnitude):
        if not self.shake_enabled:
            return
        self.shake = max(self.shake, min(14.0, magnitude))
        self.shake_mag = self.shake

    def add_kick(self, magnitude):
        """P4.4: quick camera kick burst — shorter, punchier than shake."""
        self.kick = max(self.kick, min(20.0, magnitude))

    def update_shake(self, dt, rng=None):
        if self.shake > 0.0:
            self.shake = max(0.0, self.shake - dt * 26.0)
            if rng is not None and self.shake > 0.2:
                self.offset_x = rng.randint(-int(self.shake), int(self.shake))
                self.offset_y = rng.randint(-int(self.shake), int(self.shake))
            else:
                self.offset_x = 0
                self.offset_y = 0
        else:
            self.offset_x = 0
            self.offset_y = 0
        # P4.4: kick decay — fast punchy decay per spec (decay = pow(0.001, dt))
        if self.kick > 0.0:
            self.kick *= pow(0.001, dt)
            if self.kick < 0.5:
                self.kick = 0.0
            self.kick_x = int(self.kick)
            self.kick_y = int(self.kick)

    def world_offset(self):
        """Integer-snapped top-left of the view in world pixels."""
        return (int(self.x) - self.offset_x - self.kick_x, int(self.y) - self.offset_y - self.kick_y)

    def world_to_screen(self, wx, wy, ox, oy):
        """Convert a world pixel coordinate to a screen pixel coordinate
        after zoom."""
        st = self.tile_scale
        return ((wx - ox) * st, (wy - oy) * st)

    def to_screen(self, wx, wy):
        ox, oy = self.world_offset()
        return (int(wx - ox), int(wy - oy))

    def to_world(self, sx, sy):
        ox, oy = self.world_offset()
        return (sx + ox, sy + oy)

    def visible_rect(self):
        ox, oy = self.world_offset()
        return pygame.Rect(ox, oy, self.view_w, self.view_h)
