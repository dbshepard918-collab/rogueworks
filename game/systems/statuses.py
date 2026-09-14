"""Status effects: DOTs, debuffs and buffs driven by game/data/statuses.json.

Statuses tick on their own cadence and resolve into the target's single Stats
object (never ad-hoc arithmetic in the combat code).

P1.3: DOT magnitudes are weakened by the lantern tree's global DOT-weakness
effect (statuses.tick_statuses reads meta_special_effects on the world's
profile).

P2.5: Elemental status interplay - when conflicting elements meet, combo
statuses are triggered via check_combos().
"""

from __future__ import annotations

TICKS_PER_SECOND = 60.0
ARMOR_PER_POINT = 0.03
ARMOR_FRACTION_CAP = 0.6

DOT_IDS = ("poison", "burn", "bleed")
BUFF_IDS = ("fortify", "rage")
STUN_IDS = ("stun", "doom_mark")
SLOW_IDS = ("slow", "weaken", "corrode", "chill")
ARMOR_BUFF_IDS = ("fortify", "iron_skin", "lantern_glow", "luck_ward", "haste")

# P2.5: Elemental combination detection
# Maps (element1, element2) -> combo_status_id
# Order-insensitive: both (a,b) and (b,a) will match
ELEMENT_COMBOS: dict[tuple[str, str], str] = {
    ("wet", "ember"): "steam_burst",
    ("ember", "wet"): "steam_burst",
    ("chilled", "fire"): "shatter",
    ("fire", "chilled"): "shatter",
    ("ice", "water"): "frost_burn",
    ("water", "ice"): "frost_burn",
}

COMBO_IDS: tuple[str, ...] = ("steam_burst", "shatter", "frost_burn")

# Element to status mapping: what status an element corresponds to
ELEMENT_TO_STATUS: dict[str, str] = {
    "fire": "burn",
    "ice": "chilled",
    "water": "wet",
    "poison": "poison",
    "shadow": "doom_mark",
    "lightning": "stun",
    "holy": "regeneration",
    "wind": "haste",
    "earth": "fortify",
    "physical": None,
}


def is_combo(status_id: str) -> bool:
    """Return True if a status_id is a combo status."""
    return status_id in COMBO_IDS


class StatusInstance:
    __slots__ = ("status_id", "name", "kind", "magnitude", "remaining", "tick_every",
                 "timer", "icon", "stacks", "ticks_done")

    def __init__(self, defn, magnitude=None, duration_ticks=None, stacks=1):
        self.status_id = defn.get("id", "unknown")
        self.name = defn.get("name", self.status_id)
        self.kind = defn.get("kind", "debuff")
        self.magnitude = float(defn.get("magnitude", 1) if magnitude is None else magnitude)
        self.remaining = float(defn.get("duration", 60) if duration_ticks is None else duration_ticks)
        self.tick_every = max(1, int(defn.get("tick_every", 60) or 60))
        self.timer = float(self.tick_every)
        self.icon = defn.get("icon", "status_%s" % self.status_id)
        self.stacks = int(stacks)
        self.ticks_done = 0

    def seconds_left(self):
        return max(0.0, self.remaining / TICKS_PER_SECOND)


def _meta_dot_weakness(world):
    """Fraction by which all DOT magnitudes are reduced (lantern:4, P1.3).

    Burning-tile DOT also gets the burning_dot_weakness bonus (biome_mods reads
    the same key when applying ember heat).  Both stack additively.
    """
    try:
        from . import save as save_sys
        se = save_sys.meta_special_effects(world.profile) if world.profile else {}
        return float(se.get("dot_weakness", 0.0)) + float(se.get("burning_dot_weakness", 0.0))
    except Exception:
        return 0.0


def apply_status(world, actor, status_id, duration_ticks=None, magnitude=None):
    """Apply or refresh a status.  Unknown ids are ignored (and warned once)."""
    if actor is None or not getattr(actor, "alive", False):
        return None
    defn = world.content.status(status_id)
    if defn is None:
        if status_id not in world.unknown_statuses:
            world.unknown_statuses.add(status_id)
            world.warnings.append("status %r not in content - ignored" % status_id)
        return None
    existing = None
    for inst in actor.statuses:
        if inst.status_id == status_id:
            existing = inst
            break
    if existing is not None:
        existing.remaining = max(existing.remaining, float(
            defn.get("duration", 60) if duration_ticks is None else duration_ticks))
        if magnitude is not None:
            existing.magnitude = max(existing.magnitude, float(magnitude))
        existing.timer = min(existing.timer, float(existing.tick_every))
        if existing.kind in ("dot",):
            existing.stacks += 1
    else:
        actor.statuses.append(StatusInstance(defn, magnitude=magnitude, duration_ticks=duration_ticks))
        if actor is getattr(world, "player", None):
            pass
    refresh_status_mods(actor)
    # P2.5: check for elemental combos after applying new status
    check_combos(world, actor)
    return actor


def check_combos(world, actor):
    """Scan actor.statuses for conflicting elements, apply combo status if found.

    P2.5: When an actor has two statuses whose elements form a known combo,
    the combo status is applied (overriding the component statuses). Combos
    override their component statuses and last 30-90 ticks dealing extra damage.
    """
    if world is None or actor is None:
        return None
    # Collect elements from current statuses
    active_elements = set()
    for inst in actor.statuses:
        sid = inst.status_id
        element = _status_to_element(sid)
        if element:
            active_elements.add(element)

    # Check for combos
    elements = list(active_elements)
    for i in range(len(elements)):
        for j in range(i + 1, len(elements)):
            key = (elements[i], elements[j])
            combo_id = ELEMENT_COMBOS.get(key)
            if combo_id:
                _apply_combo(world, actor, combo_id)
                return combo_id
    return None


def _status_to_element(status_id: str) -> str | None:
    """Map a status ID back to its element. Returns None if not an elemental status."""
    for element, sid in ELEMENT_TO_STATUS.items():
        if sid == status_id:
            return element
    return None


def _apply_combo(world, actor, combo_id: str):
    """Apply a combo status, removing its component statuses."""
    defn = world.content.status(combo_id)
    if defn is None:
        return

    # Remove other combo statuses (components get replaced)
    actor.statuses = [inst for inst in actor.statuses if inst.status_id not in COMBO_IDS]

    # Apply the combo status fresh
    actor.statuses.append(StatusInstance(defn, duration_ticks=defn.get("duration", 60)))
    refresh_status_mods(actor)


def refresh_status_mods(actor):
    """Recompute the status-derived portion of the stats object.

    Data-driven by ``kind``; ids modulate which stat moves (so new statuses in
    game/data/statuses.json work without code changes).
    """
    actor.stats.clear_sources("status:")
    pct = {}
    flat = {}
    for inst in actor.statuses:
        sid = inst.status_id
        if sid in SLOW_IDS:
            pct["speed"] = pct.get("speed", 0.0) - min(0.85, inst.magnitude)
        elif sid == "rage":
            flat["damage"] = flat.get("damage", 0.0) + inst.magnitude
        elif sid == "haste":
            flat["speed"] = flat.get("speed", 0.0) + inst.magnitude
        elif sid == "luck_ward":
            flat["luck"] = flat.get("luck", 0.0) + inst.magnitude
        elif sid == "lantern_glow":
            flat["max_hp"] = flat.get("max_hp", 0.0) + inst.magnitude
        elif sid in ARMOR_BUFF_IDS:
            flat["armor"] = min(ARMOR_FRACTION_CAP,
                                flat.get("armor", 0.0) + inst.magnitude * ARMOR_PER_POINT)
        elif sid == "regeneration":
            pass                       # handled as a heal-over-time in tick_statuses
        elif inst.kind == "buff":
            flat["damage"] = flat.get("damage", 0.0) + inst.magnitude * 0.5
        elif inst.kind == "debuff":
            pct["speed"] = pct.get("speed", 0.0) - min(0.5, inst.magnitude * 0.4)
        # P2.5 combo statuses
        elif sid == "steam_burst":
            flat["damage"] = flat.get("damage", 0.0) + inst.magnitude * 0.2
        elif sid == "shatter":
            pct["speed"] = pct.get("speed", 0.0) - min(0.5, inst.magnitude)
        elif sid == "frost_burn":
            flat["armor"] = min(ARMOR_FRACTION_CAP,
                                flat.get("armor", 0.0) - inst.magnitude * 0.1)
    if flat:
        actor.stats.set_mod("status:flat", flat)
    if pct:
        actor.stats.set_pct("status:pct", pct)


def tick_statuses(world, actor, dt):
    """Advance all statuses on an actor; returns net heal (positive) or damage (negative).

    P1.3: DOT magnitudes are weakened by the lantern tree's global
    dot-weakness effect before being applied.
    """
    if not actor.statuses:
        return 0.0
    net = 0.0
    survivors = []
    weakness = _meta_dot_weakness(world)
    for inst in actor.statuses:
        inst.remaining -= dt * TICKS_PER_SECOND
        if inst.kind == "dot":
            inst.timer -= dt * TICKS_PER_SECOND
            if inst.timer <= 0.0:
                inst.timer += inst.tick_every
                inst.ticks_done += 1
                dot_weakness = 0.0
                try:
                    from . import save as save_sys
                    se = save_sys.meta_special_effects(getattr(world, "profile", None))
                    dot_weakness = float(se.get("dot_weakness", 0.0))
                except Exception:
                    pass
                dmg = inst.magnitude * (1.0 - dot_weakness) * (1.0 + 0.25 * (inst.stacks - 1))
                net -= dmg
        elif inst.status_id == "regeneration":
            inst.timer -= dt * TICKS_PER_SECOND
            if inst.timer <= 0.0:
                inst.timer += inst.tick_every
                inst.ticks_done += 1
                net += inst.magnitude
        if inst.remaining > 0.0:
            survivors.append(inst)
    removed = len(survivors) != len(actor.statuses)
    actor.statuses = survivors
    if net != 0.0:
        from . import combat
        if net < 0.0:
            combat.damage_target(world, actor, -net, source=None, damage_type="dot",
                                 status_id=actor.statuses[0].status_id if actor.statuses else "dot")
        else:
            actor.hp += net
            actor.clamp_hp()
    if removed:
        refresh_status_mods(actor)
    return net


def clear_statuses(actor):
    if getattr(actor, "statuses", None):
        actor.statuses = []
        actor.stats.clear_sources("status:")


def status_ids(actor):
    return [inst.status_id for inst in getattr(actor, "statuses", [])]


def is_stunned(actor):
    return any(inst.status_id in STUN_IDS for inst in getattr(actor, "statuses", []))
