"""Actor base class and the single Stats object all modifiers resolve through.

GDD section 3: "all modifiers resolve through one Stats object - never ad-hoc
arithmetic in the combat code".

P2.2 TELEGRAPHS: telegraph_indicator is the VFX sprite name rendered during
the windup before a monster attack lands. Set by the AI system from
monsters.json data.
"""

TILE = 64

STAT_KEYS = ("damage", "armor", "max_hp", "speed", "luck", "crit")

BASE_STATS = {
    "max_hp": 90.0,
    "damage": 7.0,
    "armor": 0.0,
    "speed": 4.2,          # tiles / second
    "luck": 0.0,
    "crit": 0.05,
}

STAT_LIMITS = {
    "max_hp": (1.0, 100000.0),
    "damage": (0.0, 100000.0),
    "armor": (0.0, 0.75),      # armor is a fraction: 0.75 = 75% reduction cap
    "speed": (0.6, 14.0),
    "luck": (0.0, 1000.0),
    "crit": (0.0, 0.85),
}


class Stats:
    """Base stats plus layered additive modifiers from named sources."""

    def __init__(self, base=None):
        self.base = dict(BASE_STATS)
        if base:
            for key, value in base.items():
                if key in STAT_KEYS:
                    self.base[key] = float(value)
        self.mods = {}          # source -> {stat: value}
        self.pct_mods = {}      # source -> {stat: multiplier delta}
        self._cache = None

    # -- sources ---------------------------------------------------------
    def set_mod(self, source, effects):
        clean = {}
        for key, value in (effects or {}).items():
            if key in STAT_KEYS and isinstance(value, (int, float)):
                clean[key] = float(value)
        if clean:
            self.mods[source] = clean
        else:
            self.mods.pop(source, None)
        self._cache = None

    def remove_mod(self, source):
        if source in self.mods:
            del self.mods[source]
            self._cache = None

    def set_pct(self, source, effects):
        clean = {}
        for key, value in (effects or {}).items():
            if key in STAT_KEYS and isinstance(value, (int, float)):
                clean[key] = float(value)
        if clean:
            self.pct_mods[source] = clean
        else:
            self.pct_mods.pop(source, None)
        self._cache = None

    def clear_sources(self, prefix):
        for source in list(self.mods):
            if str(source).startswith(prefix):
                del self.mods[source]
        for source in list(self.pct_mods):
            if str(source).startswith(prefix):
                del self.pct_mods[source]
        self._cache = None

    # -- resolution ------------------------------------------------------
    def _resolve(self):
        if self._cache is None:
            out = dict(self.base)
            for effects in self.mods.values():
                for key, value in effects.items():
                    out[key] = out.get(key, 0.0) + value
            for effects in self.pct_mods.values():
                for key, value in effects.items():
                    out[key] = out.get(key, 0.0) * (1.0 + value)
            for key, (low, high) in STAT_LIMITS.items():
                out[key] = max(low, min(high, out.get(key, 0.0)))
            self._cache = out
        return self._cache

    def get(self, stat, default=0.0):
        return self._resolve().get(stat, default)

    def max_hp(self):
        return self.get("max_hp")

    def damage(self):
        return self.get("damage")

    def armor(self):
        return self.get("armor")

    def speed(self):
        return self.get("speed")

    def luck(self):
        return self.get("luck")

    def crit(self):
        return self.get("crit")

    def snapshot(self):
        return dict(self._resolve())


class Entity:
    """Anything with a position that the renderer can draw."""

    kind = "entity"

    def __init__(self, eid, x, y, radius=12.0, sprite="entity"):
        self.id = int(eid)
        self.x = float(x)
        self.y = float(y)
        self.radius = float(radius)
        self.sprite = sprite
        self.alive = True
        self.vx = 0.0
        self.vy = 0.0
        self.facing = (1.0, 0.0)
        self.age = 0.0
        self.hit_flash = 0.0
        self.last_damage_source = None  # P3.5: last entity that dealt damage

    # -- geometry --------------------------------------------------------
    @property
    def tile_x(self):
        return int(self.x // TILE)

    @property
    def tile_y(self):
        return int(self.y // TILE)

    def center(self):
        return (self.x, self.y)

    def dist_to(self, other):
        dx = other.x - self.x
        dy = other.y - self.y
        return (dx * dx + dy * dy) ** 0.5

    def dist_sq_to_xy(self, x, y):
        dx = x - self.x
        dy = y - self.y
        return dx * dx + dy * dy

    def facing_tile(self, distance=TILE):
        fx, fy = self.facing
        return (self.x + fx * distance, self.y + fy * distance)

    def tick_age(self, dt):
        self.age += dt
        if self.hit_flash > 0.0:
            self.hit_flash = max(0.0, self.hit_flash - dt)


class Actor(Entity):
    """Living entity: hp, stats, statuses, knockback."""

    kind = "actor"

    def __init__(self, eid, x, y, radius=12.0, sprite="actor", stats=None):
        super().__init__(eid, x, y, radius, sprite)
        self.stats = stats if stats is not None else Stats()
        self.hp = float(self.stats.max_hp())
        self.statuses = []          # list[StatusInstance] from systems.statuses
        self.knock_x = 0.0
        self.knock_y = 0.0
        self.death_timer = 0.0
        self.invuln = 0.0
        self.hit_stop = 0.0        # P2.1: hit-stop freeze on hit (seconds)
        self._frozen = False         # P2.1: entity is frozen during hit-stop
        self.telegraph_indicator = None  # P2.2: VFX sprite name for windup indicator
        self.last_damage_source = None  # P3.5: last entity that dealt damage to this actor

    # -- health ----------------------------------------------------------
    def heal(self, amount):
        if amount <= 0:
            return 0.0
        before = self.hp
        self.hp = min(self.stats.max_hp(), self.hp + float(amount))
        return self.hp - before

    def clamp_hp(self):
        if self.hp > self.stats.max_hp():
            self.hp = self.stats.max_hp()
        if self.hp < 0.0:
            self.hp = 0.0

    def hp_fraction(self):
        top = self.stats.max_hp()
        return 0.0 if top <= 0 else max(0.0, min(1.0, self.hp / top))

    def has_status(self, status_id):
        return any(s.status_id == status_id for s in self.statuses)

    def add_knockback(self, dx, dy, force):
        length = (dx * dx + dy * dy) ** 0.5
        if length <= 0.0001:
            return
        self.knock_x += (dx / length) * force
        self.knock_y += (dy / length) * force

    def apply_knockback(self, level, dt):
        if abs(self.knock_x) < 0.5 and abs(self.knock_y) < 0.5:
            self.knock_x = 0.0
            self.knock_y = 0.0
            return
        # P2.1: no knockback movement during hit-stop
        if self.hit_stop > 0.0:
            self.knock_x = 0.0
            self.knock_y = 0.0
            return
        nx = self.x + self.knock_x * dt
        ny = self.y + self.knock_y * dt
        if level is None or not level.blocked_px(nx, ny, self.radius):
            self.x = nx
            self.y = ny
        # P2.1: exponential knockback decay curve (was linear multiply)
        decay = pow(0.0015, dt)
        self.knock_x *= decay
        self.knock_y *= decay

    def trigger_hit_stop(self, duration=0.09):
        """P2.1: freeze the entity for `duration` seconds on hit."""
        self.hit_stop = max(self.hit_stop, duration)
        self._frozen = True

    def tick_hit_stop(self, dt):
        """Decrement hit-stop timer; returns True while frozen."""
        if self.hit_stop > 0.0:
            self.hit_stop = max(0.0, self.hit_stop - dt)
            if self.hit_stop <= 0.0:
                self._frozen = False
            return True
        return False

    def is_frozen(self):
        """P2.1: return True if the entity is currently hit-stop frozen."""
        return self._frozen or self.hit_stop > 0.0


def move_with_collision(actor, dx, dy, level):
    """Axis-separated movement so sliding along walls feels right."""
    moved = [False, False]
    if dx:
        nx = actor.x + dx
        if not level.blocked_px(nx, actor.y, actor.radius):
            actor.x = nx
            moved[0] = True
    if dy:
        ny = actor.y + dy
        if not level.blocked_px(actor.x, ny, actor.radius):
            actor.y = ny
            moved[1] = True
    return moved
