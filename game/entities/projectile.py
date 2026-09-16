"""Projectiles for the aimed attack and ranged monsters."""

from .actor import Entity

TILE = 64


class Projectile(Entity):
    kind = "projectile"

    def __init__(self, eid, x, y, vx, vy, damage, owner="player", sprite="vfx_magic_bolt",
                 lifetime=1.5, radius=10.0, status_on_hit=None, pierce=0):
        super().__init__(eid, x, y, radius=radius, sprite=sprite)
        self.vx = float(vx)
        self.vy = float(vy)
        self.damage = float(damage)
        self.owner = owner          # "player" | "monster"
        self.lifetime = float(lifetime)
        self.max_lifetime = float(lifetime)
        self.status_on_hit = status_on_hit
        self.pierce = int(pierce)
        self.hit_ids = set()

    def tick(self, dt):
        self.tick_age(dt)
        self.lifetime -= dt
        if self.lifetime <= 0.0:
            self.alive = False
        self.x += self.vx * dt
        self.y += self.vy * dt

    def speed(self):
        return (self.vx * self.vx + self.vy * self.vy) ** 0.5

    def facing_angle(self):
        import math
        return math.degrees(math.atan2(self.vy, self.vx))
