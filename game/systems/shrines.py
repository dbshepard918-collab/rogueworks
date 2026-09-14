"""Shrine system: risk/reward boons and curses (P1.5).

When a player touches a shrine pickup they gain a boon and take a curse.
Boons and curses are drawn from data tables; some route through the existing
status pipeline and some are temporary stat modifiers tracked on the world.
"""

from . import statuses as status_sys
from .statuses import ARMOR_PER_POINT

# ---------------------------------------------------------------------------
# Boons
# ---------------------------------------------------------------------------

BOONS = [
    {"id": "boon_fortify", "name": "Fortified",
     "flavor": "Your skin hardens like cured stone.",
     "type": "status", "status_id": "fortify", "duration": 600},
    {"id": "boon_rage", "name": "Rage",
     "flavor": "Something angry wakes in your blood.",
     "type": "status", "status_id": "rage", "duration": 600},
    {"id": "boon_haste", "name": "Haste",
     "flavor": "Your feet find the spaces between.",
     "type": "status", "status_id": "haste", "duration": 480},
    {"id": "boon_regen", "name": "Regeneration",
     "flavor": "The wound closes itself, slowly.",
     "type": "status", "status_id": "regeneration", "duration": 480},
    {"id": "boon_luck", "name": "Luck Ward",
     "flavor": "Chance leans your way for a while.",
     "type": "status", "status_id": "luck_ward", "duration": 480},
    {"id": "boon_lantern", "name": "Lantern Glow",
     "flavor": "Your light swells, just for a time.",
     "type": "status", "status_id": "lantern_glow", "duration": 600},
    {"id": "boon_damage_3", "name": "Sharp Edge",
     "flavor": "Every swing bites harder.",
     "type": "stat_boost", "stat": "damage", "value": 3, "duration": 600},
    {"id": "boon_damage_5", "name": "Rending Edge",
     "flavor": "The air splits around your weapon.",
     "type": "stat_boost", "stat": "damage", "value": 5, "duration": 600},
    {"id": "boon_armor_3", "name": "Hardened",
     "flavor": "Your skin takes the hit for you.",
     "type": "stat_boost", "stat": "armor", "value": 3, "duration": 600},
    {"id": "boon_speed_04", "name": "Light Foot",
     "flavor": "The floor stops fighting you.",
     "type": "stat_boost", "stat": "speed", "value": 0.4, "duration": 600},
    {"id": "boon_crit_05", "name": "Focused",
     "flavor": "One target, one will.",
     "type": "stat_boost", "stat": "crit", "value": 0.05, "duration": 600},
    {"id": "boon_max_hp_20", "name": "Drawn Tight",
     "flavor": "Your pulse finds a little more room.",
     "type": "stat_boost", "stat": "max_hp", "value": 20, "duration": 600},
]

# ---------------------------------------------------------------------------
# Curses
# ---------------------------------------------------------------------------

CURSES = [
    {"id": "curse_slow", "name": "Weighed Down",
     "flavor": "The floor drinks your footing.",
     "type": "status", "status_id": "slow", "duration": 600},
    {"id": "curse_weaken", "name": "Weakened",
     "flavor": "Your strikes land a beat late.",
     "type": "status", "status_id": "weaken", "duration": 600},
    {"id": "curse_poison", "name": "Self-Poisoned",
     "flavor": "You swallow something foul.",
     "type": "status", "status_id": "poison", "duration": 180},
    {"id": "curse_damage_2", "name": "Dull Edge",
     "flavor": "Your blade meets only air.",
     "type": "stat_penalty", "stat": "damage", "value": 2, "duration": 600},
    {"id": "curse_damage_4", "name": "Broken",
     "flavor": "Your weapon is a joke now.",
     "type": "stat_penalty", "stat": "damage", "value": 4, "duration": 600},
    {"id": "curse_speed_03", "name": "Heavy Boots",
     "flavor": "The dark clings to your heels.",
     "type": "stat_penalty", "stat": "speed", "value": 0.3, "duration": 600},
    {"id": "curse_elites", "name": "Elite Tide",
     "flavor": "Vaelmoor sends its hounds.",
     "type": "elite_bonus", "magnitude": 0.15},
    {"id": "curse_no_minimap", "name": "Veiled",
     "flavor": "The lantern's light forgets the way.",
     "type": "no_minimap"},
    {"id": "curse_max_hp", "name": "Diminished",
     "flavor": "Your breath runs shorter than it should.",
     "type": "stat_penalty", "stat": "max_hp", "value": 15, "duration": 600},
    {"id": "curse_armor", "name": "Exposed",
     "flavor": "Your skin remembers every cut.",
     "type": "stat_penalty", "stat": "armor", "value": 3, "duration": 600},
    {"id": "curse_gold_tax", "name": "Gold Tax",
     "flavor": "Vaelmoor takes its cut from every coin.",
     "type": "gold_tax", "magnitude": 0.25},
    {"id": "diminished", "name": "Diminished",
     "flavor": "Your blade meets only air.",
     "type": "stat_penalty", "stat": "damage", "value": 2, "duration": 600},
    {"id": "armor", "name": "Exposed",
     "flavor": "Your skin remembers every cut.",
     "type": "stat_penalty", "stat": "armor", "value": 3, "duration": 600},
    {"id": "gold_tax", "name": "Gold Tax",
     "flavor": "Vaelmoor takes its cut from every coin.",
     "type": "gold_tax", "magnitude": 0.25},
    {"id": "heavy_boots", "name": "Heavy Boots",
     "flavor": "The dark clings to your heels.",
     "type": "stat_penalty", "stat": "speed", "value": 0.3, "duration": 600},
    {"id": "fragile", "name": "Fragile",
     "flavor": "Your breath runs shorter than it should.",
     "type": "stat_penalty", "stat": "max_hp", "value": 15, "duration": 600},
]

BOON_COLOR = (121, 176, 74)
CURSE_COLOR = (196, 99, 95)


def activate_shrine(world):
    """Apply a random boon and a random curse from the shrine."""
    if world.player is None or not getattr(world.player, "alive", False):
        return None, None
    boon = world.rng.choice(BOONS)
    curse = world.rng.choice(CURSES)
    _apply_boon(world, boon)
    _apply_curse(world, curse)
    return boon, curse


def _apply_boon(world, boon):
    player = world.player
    if boon["type"] == "status":
        status_sys.apply_status(world, player, boon["status_id"],
                                duration_ticks=boon["duration"])
    elif boon["type"] == "stat_boost":
        value = float(boon["value"])
        if boon["stat"] == "armor":
            value = value * ARMOR_PER_POINT
        _add_shrine_temp_effect(world, boon["stat"], value, boon["duration"])
        if boon["stat"] == "max_hp" and value > 0:
            new_max = player.stats.max_hp()
            if new_max > player.hp:
                player.hp = new_max
                player.clamp_hp()

    _register_effect(world, "BOON: " + boon["name"], BOON_COLOR, boon.get("duration", 600))
    world.floating.add("BLESSING: " + boon["name"], color=BOON_COLOR, life=2.0)
    if boon.get("flavor"):
        world.floating.add(boon["flavor"], color=BOON_COLOR, life=2.6)


def _apply_curse(world, curse):
    player = world.player
    if curse["type"] == "status":
        status_sys.apply_status(world, player, curse["status_id"],
                                duration_ticks=curse["duration"])
    elif curse["type"] == "stat_penalty":
        value = float(curse["value"])
        if curse["stat"] == "armor":
            value = value * ARMOR_PER_POINT
        _add_shrine_temp_effect(world, curse["stat"], -value, curse["duration"])
        if curse["stat"] == "max_hp":
            player.clamp_hp()
    elif curse["type"] == "elite_bonus":
        world.elite_bonus += curse["magnitude"]
    elif curse["type"] == "no_minimap":
        world.no_minimap = True
    elif curse["type"] == "gold_tax":
        world.gold_tax = max(getattr(world, "gold_tax", 0.0), float(curse["magnitude"]))

    _register_effect(world, "CURSE: " + curse["name"], CURSE_COLOR, curse.get("duration", 0))
    world.floating.add("CURSE: " + curse["name"], color=CURSE_COLOR, life=2.0)
    if curse.get("flavor"):
        world.floating.add(curse["flavor"], color=CURSE_COLOR, life=2.6)

    if curse["type"] == "elite_bonus":
        world.notice = "ELITE TIDE — more elites spawn now"
        world.notice_timer = 3.0
    elif curse["type"] == "no_minimap":
        world.notice = "VEILED — the minimap is blind"
        world.notice_timer = 3.0
    elif curse["type"] == "gold_tax":
        world.notice = "GOLD TAX — 25%% of drops lost"
        world.notice_timer = 3.0


def _add_shrine_temp_effect(world, stat, value, duration):
    world.shrine_temp_effects.append({
        "stat": stat,
        "value": float(value),
        "remaining": float(duration),
    })
    _refresh_shrine_temp_mods(world)


def _register_effect(world, name, color, duration):
    """Register a persistent shrine effect for the HUD panel."""
    if not hasattr(world, "shrine_active_effects"):
        world.shrine_active_effects = []
    world.shrine_active_effects.append({
        "name": name,
        "color": color,
        "remaining": float(duration),
    })


def _refresh_shrine_temp_mods(world):
    merged = {}
    for eff in world.shrine_temp_effects:
        merged[eff["stat"]] = merged.get(eff["stat"], 0.0) + eff["value"]
    if merged:
        world.player.stats.set_mod("shrine:temp", merged)
    else:
        world.player.stats.remove_mod("shrine:temp")


def tick_shrine_effects(world, dt):
    """Tick down shrine temp effects and the HUD active-effects panel. Called from World.step()."""
    ticks = dt * 60.0
    survivors = []
    for eff in world.shrine_temp_effects:
        eff["remaining"] -= ticks
        if eff["remaining"] > 0:
            survivors.append(eff)
    world.shrine_temp_effects = survivors
    _refresh_shrine_temp_mods(world)

    # tick the active-effects panel (effects with duration > 0)
    panel = getattr(world, "shrine_active_effects", None)
    if panel:
        psurv = []
        for peff in panel:
            peff["remaining"] -= ticks
            if peff["remaining"] > 0:
                psurv.append(peff)
        world.shrine_active_effects = psurv


def apply_curse_list(world, curse_ids):
    """Apply multiple curses to the player at run start (P1.8).

    Looks up each curse id in the CURSES table and applies its effect
    just like a shrine activation would.
    """
    if world.player is None or not getattr(world.player, "alive", False):
        return
    for cid in curse_ids:
        cdef = None
        for c in CURSES:
            if c["id"] == cid:
                cdef = c
                break
        if cdef is None:
            continue
        _apply_curse(world, cdef)
