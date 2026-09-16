"""Monster actor: data-driven, four behaviors, elite/guardian/boss variants."""

from .actor import Actor, Stats

TILE = 64
ARMOR_PER_POINT = 0.03      # content 'armor' -> damage-reduction fraction
ARMOR_FRACTION_CAP = 0.6

_frame_checks = {}


def _has_frame(name):
    """Cached art availability probe (asset presence is not simulation state)."""
    hit = _frame_checks.get(name)
    if hit is None:
        from ..engine import assets
        hit = assets.has_frame(name)
        _frame_checks[name] = hit
    return hit


class Monster(Actor):
    kind = "monster"

    def __init__(self, eid, x, y, defn, elite=False, guardian=False, boss=False,
                 difficulty=1.0, damage_mult=1.0):
        self.defn = dict(defn)
        tier = int(defn.get("tier", 1))
        elite_tier = tier + 1 if elite else tier
        hp = float(defn.get("hp", 10)) * difficulty * (1.6 if elite else 1.0)
        damage = float(defn.get("damage", 3)) * damage_mult * (1.25 if elite else 1.0)
        armor_flat = float(defn.get("armor", 0)) + (1.0 if elite else 0.0)
        base = {
            "max_hp": hp,
            "damage": damage,
            "armor": min(ARMOR_FRACTION_CAP, armor_flat * ARMOR_PER_POINT),
            "speed": max(0.2, min(3.0, float(defn.get("speed", 1.0)))),
            "luck": 0.0,
            "crit": 0.05,
        }
        sprite = str(defn.get("sprite") or ("monster_%s" % defn.get("id", "unknown")))
        super().__init__(eid, x, y, radius=24.0 if not boss else 60.0, sprite=sprite, stats=Stats(base))
        self.hp = self.stats.max_hp()
        self.monster_id = defn.get("id", "unknown")
        self.name = defn.get("name", self.monster_id)
        self.tier = elite_tier
        self.base_tier = tier
        self.xp = int(defn.get("xp", 5)) * (2 if elite else 1)
        self.weight = float(defn.get("weight", 10) or 0.0)
        self.behavior = defn.get("behavior", "chaser")
        self.status_on_hit = defn.get("status_on_hit")
        self.elite = bool(elite)
        self.guardian = bool(guardian)
        self.boss = bool(boss)
        self.difficulty = difficulty

        self.attack_timer = 0.8
        self.state = "idle" if self.behavior == "ambusher" else "hunt"
        self.alert = False
        self.telegraph = 0.0        # brute wind-up
        self.telegraph_indicator = None  # P2.2: VFX sprite for windup visual
        self.burst_timer = 0.0      # ambusher burst
        self.goal = None            # (tile_x, tile_y) wander target
        self.repath_timer = 0.0
        self.path = []
        self.wander_timer = 0.0
        self.slam_radius = 124.0
        self.ranged_range = 260.0
        self.knock_resist = 1.6 if boss else (1.0 if self.behavior == "brute" else 0.0)
        self.affix_name = None
        self.elite_sprite = None
        # Boss phase system
        self.phase = {}
        self.current_phase_index = 0
        self.enraged = False
        self.enrage_timer = 0
        self.phase_transition_timer = 0
        if boss and self.defn.get("phases"):
            self.current_phase_index = 0
            self.phase = self.defn["phases"][0]
        if elite:
            from ..engine import assets
            candidate = "%s_elite" % sprite
            if assets.has_frame(candidate):
                self.elite_sprite = candidate

    # -- helpers ---------------------------------------------------------
    def is_heavy(self):
        return self.boss or self.behavior == "brute"

    def touch_damage(self):
        return self.stats.damage()

    def attack_cooldown(self):
        if self.behavior == "ranged":
            return 1.5
        if self.behavior == "brute" or self.boss:
            return 1.9
        return 1.05

    def melee_range(self):
        return 30.0 if not self.boss else 46.0

    def check_phase_transition(self):
        """Advance to next phase if hp/total_hp <= current phase hp_threshold."""
        if not self.boss or not self.defn.get("phases"):
            return False
        phases = self.defn["phases"]
        total_hp = self.stats.max_hp()
        ratio = self.hp / total_hp if total_hp > 0 else 1.0
        if self.current_phase_index < len(phases) - 1:
            next_phase = phases[self.current_phase_index + 1]
            if ratio <= next_phase["hp_threshold"]:
                self.current_phase_index += 1
                self.phase = next_phase
                self.phase_transition_timer = 60  # 1 second of transition invincibility
                return True
        return False

    def apply_enrage(self):
        """Apply enrage multipliers from boss defn."""
        enrage = self.defn.get("enrage")
        if not enrage:
            return
        self.enraged = True
        self.enrage_timer = enrage.get("duration", 600)
        dmg_mult = enrage.get("damage_multiplier", 1.0)
        spd_mult = enrage.get("speed_multiplier", 1.0)
        self.stats.set_pct("enrage", {"damage": (dmg_mult - 1.0), "speed": (spd_mult - 1.0)})

    def tick(self, dt):
        self.tick_age(dt)
        # P2.1: freeze during hit-stop — no movement, no attacks
        if self.hit_stop > 0.0:
            self.hit_stop = max(0.0, self.hit_stop - dt)
            if self.hit_stop <= 0.0:
                self._frozen = False
            return
        self.attack_timer = max(0.0, self.attack_timer - dt)
        self.telegraph = max(0.0, self.telegraph - dt)
        if self.telegraph <= 0.0 and self.telegraph_indicator:
            self.telegraph_indicator = None
        self.burst_timer = max(0.0, self.burst_timer - dt)
        self.repath_timer = max(0.0, self.repath_timer - dt)
        self.wander_timer = max(0.0, self.wander_timer - dt)

    def current_frame(self):
        """Frame name for the shipped 32x32 monster set.

        Elites use the ``_elite`` art when it exists.  ``_hurt``/``_attack``
        variants are only requested when the atlas actually ships them (the white
        hit flash carries the hit read otherwise), so a real-art run never falls
        back to a placeholder.
        """
        base = self.sprite
        if self.elite and self.elite_sprite:
            base = self.elite_sprite
        if not self.alive:
            return base
        if self.hit_flash > 0.0 and _has_frame(base + "_hurt"):
            return base + "_hurt"
        if self.telegraph > 0.0 and _has_frame(base + "_attack"):
            return base + "_attack"
        if self.telegraph > 0.0 and self.telegraph_indicator and _has_frame(self.telegraph_indicator):
            return self.telegraph_indicator
        return base

    def sprite_size(self):
        """All shipped frames are 32x32 (bosses included)."""
        return 32
