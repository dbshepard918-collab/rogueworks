"""The Lantern-Keeper: movement, auto-melee, ranged attack, dash, inventory, XP."""

from ..engine.audio import play
from ..systems import statuses as status_sys
from .actor import Actor, Stats, move_with_collision

TILE = 64

PLAYER_DIRECTIONS = ("down", "up", "left", "right")

# Canonical frame names from assets/art_manifest.json (all 64x64).
PLAYER_FRAMES = {
    "idle": {d: "player_idle_%s" % d for d in PLAYER_DIRECTIONS},
    "idle_breath": {d: ["player_idle_breath_%s_0" % d, "player_idle_breath_%s_1" % d] for d in PLAYER_DIRECTIONS},
    "attack": {d: ["player_attack_%s_0" % d, "player_attack_%s_1" % d, "player_attack_%s_2" % d] for d in PLAYER_DIRECTIONS},
    "walk": {d: ["player_walk_%s_0" % d, "player_walk_%s_1" % d, "player_walk_%s_2" % d, "player_walk_%s_3" % d] for d in PLAYER_DIRECTIONS},
    "hurt": {"left": ["player_hurt_left_0", "player_hurt_left_1"]},
    "death": ["player_death_0", "player_death_1", "player_death_2", "player_death_3"],
    "dash": {"right": "player_dash_right"},
}


def facing_direction(vec):
    """Map a facing vector onto one of the four shipped sprite directions."""
    fx, fy = vec
    if abs(fx) >= abs(fy):
        return "right" if fx >= 0 else "left"
    return "down" if fy >= 0 else "up"

EQUIP_SLOTS = ("weapon", "armor", "trinket")
CONSUMABLE_SLOTS = 4
BACKPACK_SLOTS = 8


class Player(Actor):
    kind = "player"

    ATTACK_COOLDOWN = 0.38
    ATTACK_REACH = 88.0          # pixels from the player centre
    ATTACK_ARC = 2.2             # radians, total width of the swing
    RANGED_COOLDOWN = 0.72
    DASH_TIME = 0.15
    DASH_COOLDOWN = 0.80
    DASH_SPEED = 15.5            # tiles / second during the burst
    PICKUP_RADIUS = 22.0
    MAGNET_RADIUS = 66.0

    def __init__(self, eid, x, y, stats=None, meta_totals=None, meta_effects=None, base_stats=None):
        if base_stats is not None:
            base = {
                "max_hp": float(base_stats.get("max_hp", 90.0)),
                "damage": float(base_stats.get("damage", 7.0)),
                "armor": float(base_stats.get("armor", 0.0)),
                "speed": float(base_stats.get("speed", 4.2)),
                "luck": float(base_stats.get("luck", 0.0)),
                "crit": float(base_stats.get("crit", 0.05)),
            }
        else:
            base = {
                "max_hp": 90.0 + float((meta_totals or {}).get("max_hp", 0.0)),
                "damage": 7.0 + float((meta_totals or {}).get("damage", 0.0)),
                "armor": 0.0 + float((meta_totals or {}).get("armor", 0.0)) * 0.01,
                "speed": 4.2 + float((meta_totals or {}).get("speed", 0.0)),
                "luck": 0.0 + float((meta_totals or {}).get("luck", 0.0)),
                "crit": 0.05 + float((meta_totals or {}).get("crit", 0.0)),
            }
        super().__init__(eid, x, y, radius=22.0, sprite="player_idle_0", stats=Stats(base))
        self.hp = self.stats.max_hp()

        self.level = 1
        self.xp = 0
        self.gold = 0
        self.essence = 0
        self.kills = 0
        self.items_owned = []          # ordered ids of everything picked up
        self.equipment = {"weapon": None, "armor": None, "trinket": None}
        self.consumables = []
        self.backpack = []

        self.attack_timer = 0.0
        self.ranged_timer = 0.0
        self.dash_timer = 0.0
        self.dash_cooldown = 0.0
        self.dash_dir = (0.0, 0.0)
        self.swing_timer = 0.0
        self.swing_dir = (1.0, 0.0)
        self.last_damage_taken = 0.0
        self.floor_transitions = 0
        self.hurt_timer = 0.0
        self.attack_phase = 0  # 0=anticipation, 1=main, 2=settle
        self.death_timer = 0.0

        # Animation state machine
        self._anim_state = None      # current animation state
        self._anim_timer = 0.0       # time in current state
        self._anim_frame = 0         # frame index for walk/idle cycling

        # P1.3 meta-derived runtime tuning (read once, updated by the world when profile changes)
        self._meta_effects = meta_effects or {}

    # -- cooldowns -------------------------------------------------------
    def attack_ready(self):
        return self.attack_timer <= 0.0 and self.dash_timer <= 0.0

    def ranged_ready(self):
        return self.ranged_timer <= 0.0 and self.dash_timer <= 0.0

    def dash_ready(self):
        return self.dash_cooldown <= 0.0 and self.dash_timer <= 0.0

    def dash_cooldown_amount(self):
        base = self.DASH_COOLDOWN
        sub = float((self._meta_effects or {}).get("dash_cooldown_sub", 0.0))
        return max(0.12, base - sub)

    def dash_time_amount(self):
        base = self.DASH_TIME
        add = float((self._meta_effects or {}).get("dash_iframes_add", 0.0))
        return base + add

    def is_dashing(self):
        return self.dash_timer > 0.0

    def invulnerable(self):
        return self.invuln > 0.0 or self.dash_timer > 0.0

    # -- xp --------------------------------------------------------------
    def xp_needed(self):
        return 24 + (self.level - 1) * 16

    def equip(self, item):
        """Equip an item, returning the displaced item (or None)."""
        slot = item.get("slot")
        if slot not in self.equipment:
            return None
        old = self.equipment[slot]
        self.equipment[slot] = item
        self.refresh_item_mods()
        return old

    def refresh_item_mods(self):
        from .monster import ARMOR_PER_POINT, ARMOR_FRACTION_CAP
        for slot in EQUIP_SLOTS:
            item = self.equipment.get(slot)
            if item is None:
                self.stats.remove_mod("item:%s" % slot)
            else:
                effects = dict(item.get("effect") or {})
                for affix in item.get("affixes", []):
                    for key, value in (affix.get("effect") or {}).items():
                        effects[key] = effects.get(key, 0.0) + value
                if "armor" in effects:
                    effects["armor"] = min(ARMOR_FRACTION_CAP, effects["armor"] * ARMOR_PER_POINT)
                self.stats.set_mod("item:%s" % slot, effects)
        self.clamp_hp()

    def equipped_items(self):
        return [i for i in (self.equipment.get(s) for s in EQUIP_SLOTS) if i is not None]

    def owned_item_ids(self):
        return list(self.items_owned)

    def add_consumable(self, item):
        if len(self.consumables) < CONSUMABLE_SLOTS:
            self.consumables.append(item)
            return True
        if len(self.backpack) < BACKPACK_SLOTS:
            self.backpack.append(item)
            return True
        return False

    def use_consumable(self):
        if not self.backpack and not self.consumables:
            return None
        item = self.consumables.pop(0) if self.consumables else self.backpack.pop(0)
        if self.consumables and self.backpack:
            pass
        return item

    # -- movement --------------------------------------------------------
    def move(self, direction, dt, level):
        # P2.1: freeze during hit-stop
        if self.hit_stop > 0.0:
            return False
        mx, my = direction
        length = (mx * mx + my * my) ** 0.5
        if length > 1.0:
            mx /= length
            my /= length
        if mx or my:
            self.facing = (mx, my) if length > 0.0001 else self.facing

        stun = status_sys.is_stunned(self)
        if self.dash_timer > 0.0:
            speed = self.DASH_SPEED
            mx, my = self.dash_dir
        elif stun:
            return False
        else:
            speed = self.stats.speed()

        if not (mx or my):
            self.anim_time = 0.0
            return False
        moved = move_with_collision(self, mx * speed * TILE * dt, my * speed * TILE * dt, level)
        return moved[0] or moved[1]

    def start_dash(self, direction, world=None):
        mx, my = direction
        if not (mx or my):
            mx, my = self.facing
        length = (mx * mx + my * my) ** 0.5
        if length > 0.0001:
            mx /= length
            my /= length
        self.dash_dir = (mx, my)
        self.dash_timer = self.dash_time_amount()
        self.dash_cooldown = self.dash_cooldown_amount()
        self.facing = (mx, my)
        if world is not None:
            world.particles.trail(self.x, self.y, world.rng, count=8,
                                  color=(138, 132, 150), life=0.32, size=3)
            world.particles.sprite_burst(self.x, self.y, "vfx_dust", life=0.28)
            play(world, "dash")

    # -- per-tick --------------------------------------------------------
    def tick(self, dt, hold_to_attack=False):
        self.tick_age(dt)
        # P2.1: freeze during hit-stop — no movement, no attacks
        if self.hit_stop > 0.0:
            self.hit_stop = max(0.0, self.hit_stop - dt)
            if self.hit_stop <= 0.0:
                self._frozen = False
            return
        self.attack_timer = max(0.0, self.attack_timer - dt)
        self.ranged_timer = max(0.0, self.ranged_timer - dt)
        self.dash_cooldown = max(0.0, self.dash_cooldown - dt)
        self.dash_timer = max(0.0, self.dash_timer - dt)
        self.swing_timer = max(0.0, self.swing_timer - dt)
        self.invuln = max(0.0, self.invuln - dt)
        self.last_damage_taken = max(0.0, self.last_damage_taken - dt)
        self.death_timer = max(0.0, self.death_timer - dt)
        self.hurt_timer = max(0.0, self.hurt_timer - dt)
        # P2.6: hold-to-attack — keep auto-melee going while the button is held
        if hold_to_attack and self.attack_ready() and self.swing_timer <= 0.0:
            pass  # Attack is triggered by world.step based on continuous input

    # -- animation state machine ----------------------------------------
    ANIM_IDLE = "idle"
    ANIM_WALK = "walk"
    ANIM_ATTACK = "attack"
    ANIM_HURT = "hurt"
    ANIM_DEATH = "death"
    ANIM_DASH = "dash"

    def set_anim_state(self, state):
        """Transition to a new animation state, resetting per-state timers."""
        if getattr(self, "_anim_state", None) != state:
            self._anim_state = state
            self._anim_timer = 0.0
            self._anim_frame = 0

    def tick_anim(self, dt):
        """Advance the animation state machine one tick."""
        self._anim_timer += dt
        direction = facing_direction(self.facing)

        # State transitions (priority order)
        if not self.alive:
            self.set_anim_state(self.ANIM_DEATH)
        elif self.dash_timer > 0.0:
            self.set_anim_state(self.ANIM_DASH)
        elif self.hurt_timer > 0.0 or self.hit_flash > 0.0:
            self.set_anim_state(self.ANIM_HURT)
        elif self.swing_timer > 0.0:
            self.set_anim_state(self.ANIM_ATTACK)
        elif self._moving:
            self.set_anim_state(self.ANIM_WALK)
        else:
            self.set_anim_state(self.ANIM_IDLE)

        # Advance frame counters per state
        if self._anim_state == self.ANIM_WALK:
            if self._anim_timer > 0.12:
                self._anim_timer = 0.0
                self._anim_frame = (self._anim_frame + 1) % 4
        elif self._anim_state == self.ANIM_IDLE:
            if self._anim_timer > 0.12:
                self._anim_timer = 0.0
        elif self._anim_state == self.ANIM_ATTACK:
            ratio = 1.0 - (self.swing_timer / 0.18)
            if ratio < 0.33:
                self.attack_phase = 0
            elif ratio < 0.66:
                self.attack_phase = 1
            else:
                self.attack_phase = 2
        elif self._anim_state == self.ANIM_HURT:
            if self._anim_timer > 0.15:
                self._anim_timer = 0.0

    def current_frame(self):
        """Return (frame_name, flip_horizontal) for the shipped 32x32 art set.

        Uses the animation state machine for clean state transitions
        between idle/walk/attack/hurt/death/dash states.
        """
        direction = facing_direction(self.facing)

        # Ensure state machine has been ticked
        if not hasattr(self, "_anim_state"):
            self.set_anim_state(self.ANIM_IDLE)

        state = self._anim_state

        if state == self.ANIM_DEATH or not self.alive:
            if self.death_timer <= 0:
                frame_idx = 3
            else:
                frame_idx = min(int((self.death_timer / 0.6) * 4), 3)
            return (PLAYER_FRAMES["death"][frame_idx], False)

        if state == self.ANIM_DASH:
            return (PLAYER_FRAMES["dash"]["right"], self.dash_dir[0] < 0)

        if state == self.ANIM_HURT:
            frame_idx = int((self._anim_timer / 0.15) * 2) % 2
            if self.hurt_timer <= 0.0:
                self.hurt_timer = 0.15
            return (PLAYER_FRAMES["hurt"]["left"][frame_idx], direction == "right")

        if state == self.ANIM_ATTACK:
            frames = PLAYER_FRAMES["attack"].get(direction, PLAYER_FRAMES["attack"]["down"])
            return (frames[self.attack_phase], False)

        if state == self.ANIM_WALK:
            names = PLAYER_FRAMES["walk"].get(direction) or [PLAYER_FRAMES["idle"][direction]]
            return (names[self._anim_frame % len(names)], False)

        # ANIM_IDLE: alternate breathing frames
        breath_idx = int(self._anim_timer / 0.06) % 2
        return (PLAYER_FRAMES["idle_breath"][direction][breath_idx], False)

    swinging = False
    _moving = False

    def set_moving(self, moving):
        self._moving = bool(moving)
