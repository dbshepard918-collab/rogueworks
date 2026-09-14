"""Build-defining legendary unique effects (P1.6).

Each legendary item may carry a ``unique`` id that activates a gameplay effect
whenever a specific event fires.  The effects are data-driven (the ``unique``
field on the item dict) and implemented here so the combat/world code stays
readable.

Events wired so far
-------------------
* ``"melee_hit"``   — called from combat.player_melee after the primary hit
* ``"ranged_fire"`` — called from combat.player_ranged when a bolt is fired
* ``"damage_taken"``— called from combat.damage_target just before damage is
                      applied to the player
* ``"monster_killed"`` — called from world.on_monster_death after a monster dies
* ``"dash_start"``  — called from player.start_dash

Unique ids implemented
----------------------
* ``pierce``              — player ranged bolts pass through extra monsters
* ``chain``               — melee hit chains to one nearby monster
* ``reflect``             — a fraction of player damage taken is returned
* ``lifesteal``           — a fraction of player damage dealt heals the player
* ``death_spark``         — killing a monster deals splash damage nearby
* ``purifier``            — DOTs applied to the player deal bonus damage back
* ``dash_fire``           — every dash leaves burning tiles behind
* ``poison_on_hit``       — melee hits apply poison DOT to the target
"""

from __future__ import annotations

import math

TILE = 32


# --------------------------------------------------------------------------- pierce
def unique_pierce(world, item, proj):
    """Player ranged bolts pierce through up to 2 extra monsters."""
    extra = int(item.get("unique_data", {}).get("pierce_count", 2))
    proj.pierce = max(proj.pierce, extra)


# --------------------------------------------------------------------------- chain
def unique_chain(world, item, target, damage_dealt):
    """Melee hit chains to one nearby monster for 60% of the damage dealt."""
    chance = float(item.get("unique_data", {}).get("chain_chance", 1.0))
    if not world.rng.chance(chance):
        return
    best = None
    best_d2 = 90.0 * 90.0
    for mon in world.monsters:
        if mon is target or not mon.alive:
            continue
        d2 = (mon.x - target.x) ** 2 + (mon.y - target.y) ** 2
        if d2 < best_d2:
            best_d2 = d2
            best = mon
    if best is None:
        return
    chain_dmg = damage_dealt * float(item.get("unique_data", {}).get("chain_ratio", 0.6))
    from . import combat as _combat
    _combat.damage_target(world, best, chain_dmg, source=target,
                          knockback=60.0, attacker_pos=(target.x, target.y))
    world.particles.sprite_burst(best.x, best.y, "vfx_slash_alt", life=0.18)
    world.damage_numbers.add(best.x, best.y - 14, chain_dmg,
                             color=(232, 178, 60), scale=2)


# --------------------------------------------------------------------------- reflect
def unique_reflect(world, item, attacker, amount):
    """Return a fraction of damage taken back to the attacker."""
    ratio = float(item.get("unique_data", {}).get("reflect_ratio", 0.25))
    if attacker is None or not getattr(attacker, "alive", False):
        return
    reflected = amount * ratio
    if reflected < 1.0:
        return
    from . import combat as _combat
    _combat.damage_target(world, attacker, reflected, source=None,
                          knockback=40.0, attacker_pos=(attacker.x, attacker.y))
    world.particles.sprite_burst(attacker.x, attacker.y, "vfx_shield", life=0.25)


# --------------------------------------------------------------------------- lifesteal
def unique_lifesteal(world, item, amount_dealt):
    """Heal the player for a fraction of damage dealt."""
    ratio = float(item.get("unique_data", {}).get("lifesteal_ratio", 0.30))
    heal = amount_dealt * ratio
    if heal < 1.0:
        return
    player = world.player
    if player is None or not player.alive:
        return
    player.heal(heal)
    world.damage_numbers.add(player.x, player.y - 26, heal,
                             color=(121, 176, 74), label="+%d" % int(heal))


# --------------------------------------------------------------------------- death_spark
def unique_death_spark(world, item, killed_mon):
    """Killing a monster deals splash damage to nearby enemies."""
    radius = float(item.get("unique_data", {}).get("spark_radius", 80.0))
    dmg = float(item.get("unique_data", {}).get("spark_damage", 10.0))
    cx, cy = killed_mon.x, killed_mon.y
    world.particles.burst(cx, cy, world.rng, count=18,
                          color=(232, 178, 60), speed=140.0, life=0.5, size=4)
    world.particles.sprite_burst(cx, cy, "vfx_shockwave", life=0.35, scale=2.0)
    hit_any = False
    from . import combat as _combat
    for mon in world.monsters:
        if mon is killed_mon or not mon.alive:
            continue
        if (mon.x - cx) ** 2 + (mon.y - cy) ** 2 <= radius * radius:
            _combat.damage_target(world, mon, dmg, source=None,
                                  knockback=80.0, attacker_pos=(cx, cy))
            hit_any = True
    if hit_any:
        world.floating.add("DEATH SPARK", color=(232, 178, 60), life=0.9)


# --------------------------------------------------------------------------- purifier
def unique_purifier(world, item, actor, status_id):
    """When a DOT is applied to the player, deal bonus damage back to the source."""
    if actor is not None and actor is not world.player:
        return
    # snap the DOT magnitude into a one-shot damage pulse
    defn = world.content.status(status_id)
    if defn is None:
        return
    mag = float(defn.get("magnitude", 1))
    ratio = float(item.get("unique_data", {}).get("purify_ratio", 1.5))
    pulse = mag * ratio
    if pulse < 1.0:
        return
    from . import combat as _combat
    _combat.damage_target(world, actor, pulse, source=None,
                          damage_type="physical", attacker_pos=(actor.x, actor.y))
    world.particles.sprite_burst(actor.x, actor.y, "vfx_poison_cloud", life=0.3)


# --------------------------------------------------------------------------- dash_fire
def unique_dash_fire(world, item, player, dx, dy):
    """Every dash leaves 2 burning tiles behind the player."""
    count = int(item.get("unique_data", {}).get("dash_fire_tiles", 2))
    if count < 1:
        return
    level = world.level
    if level is None:
        return
    bx, by = player.x - dx * 26.0, player.y - dy * 26.0
    placed = 0
    for i in range(count * 3):
        if placed >= count:
            break
        off_x = dx * (18.0 + i * 9.0)
        off_y = dy * (18.0 + i * 9.0)
        px = int((bx - off_x) // TILE)
        py = int((by - off_y) // TILE)
        if not (0 <= px < level.w and 0 <= py < level.h):
            continue
        if level.tiles[px][py] != 0:          # not floor
            continue
        level.tiles[px][py] = 4               # BURNING
        burning = getattr(level, "_burning", None)
        if burning is None:
            level._burning = {(px, py)}
        else:
            burning.add((px, py))
        world.particles.burst(px * TILE + 16, py * TILE + 16, world.rng,
                              count=6, color=(226, 113, 29), speed=60.0, life=0.6, size=3)
        world.particles.sprite_burst(px * TILE + 16, py * TILE + 16,
                                      "vfx_ember", life=0.5, scale=1.2)
        placed += 1


# --------------------------------------------------------------------------- poison_on_hit
def unique_poison_on_hit(world, item, target, damage_dealt):
    """Melee hits apply poison DOT to the target."""
    if damage_dealt < 1.0:
        return
    status_id = "poison"
    defn = world.content.status(status_id)
    if defn is None:
        return
    magnitude = float(defn.get("magnitude", 2)) + float(item.get("unique_data", {}).get("venom_bonus", 1))
    status_sys = world.content                           # placeholder, real import below
    from . import statuses as _status_sys
    _status_sys.apply_status(world, target, status_id,
                             duration_ticks=int(defn.get("duration", 300)),
                             magnitude=magnitude)
    if target is not world.player:
        world.particles.sprite_burst(target.x, target.y, "vfx_poison_cloud", life=0.35)


# --------------------------------------------------------------------------- dispatch
_EVENTS = {
    "melee_hit": unique_chain,       # also lifesteal, poison_on_hit below
    "ranged_fire": unique_pierce,
    "damage_taken": unique_reflect,
    "monster_killed": unique_death_spark,
    "dash_start": unique_dash_fire,
}

# secondary melee handlers that must all run on a melee_hit event
_MELEE_HANDLERS = (unique_chain, unique_lifesteal, unique_poison_on_hit)


def apply_unique(world, item, event, **kwargs):
    """Dispatch a unique effect event.

    *item* is the equipment dict (may be None).  Returns True if a unique
    effect fired.
    """
    if not item:
        return False
    uid = item.get("unique")
    if not uid:
        return False
    if event == "melee_hit":
        for handler in _MELEE_HANDLERS:
            try:
                handler(world, item, **kwargs)
            except Exception:
                pass
        return True
    handler = _EVENTS.get(event)
    if handler is None:
        return False
    try:
        handler(world, item, **kwargs)
    except Exception:
        return False
    return True


def equipped_unique(world):
    """Return the unique id of the currently equipped weapon/armor/trinket, or None."""
    player = getattr(world, "player", None)
    if player is None:
        return None
    for slot in ("weapon", "armor", "trinket"):
        item = player.equipment.get(slot)
        if item and item.get("unique"):
            return item.get("unique")
    return None
