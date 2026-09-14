"""Spawning: per-biome tables, floor budgets, elites, guardians, bosses, loot."""

import math

from ..entities.monster import Monster
from ..entities.pickup import Pickup
from . import loot

TILE = 32

MAX_FLOOR = 15
FLOOR_PER_BIOME = 5

# --------------------------------------------------------------------------- scaling
# P1.1 — per-floor difficulty curve, tuned so a competent run reaches boss 1
# (floor 5) in roughly 8-12 minutes and dies between floor 6-12.
#
# Each row is [floor, hp_mult, damage_mult, count_add, elite_chance, guardian_chance].
# count_add is added to every room's spawn_budget on that floor (before the 8 cap).
# Interpolate between rows; clamp; floor 0 == floor 1.
#
SCALING = [
    # floor, hp, damage, count_add, elite_chance, guardian_chance
    [1,     1.00, 1.00, 0, 0.040, 0.55],
    [2,     1.08, 1.06, 0, 0.070, 0.62],
    [3,     1.18, 1.13, 1, 0.105, 0.68],
    [4,     1.30, 1.21, 1, 0.150, 0.74],
    [5,     1.44, 1.30, 1, 0.195, 0.75],   # boss floor — sharpness before the fight
    [6,     1.55, 1.38, 1, 0.215, 0.75],
    [7,     1.68, 1.47, 1, 0.230, 0.75],
    [8,     1.82, 1.57, 2, 0.245, 0.75],
    [9,     1.96, 1.67, 2, 0.260, 0.75],   # boss floor
    [10,    2.12, 1.78, 2, 0.270, 0.75],
    [11,    2.28, 1.89, 2, 0.278, 0.75],
    [12,    2.45, 2.01, 2, 0.285, 0.75],
    [13,    2.62, 2.13, 3, 0.290, 0.75],
    [14,    2.80, 2.26, 3, 0.295, 0.75],
    [15,    3.00, 2.40, 3, 0.300, 1.00],   # final boss floor — guaranteed guardian
]

SCALING_FLOORS = [r[0] for r in SCALING]


def _lerp(a, b, t):
    return a + (b - a) * t


def _scale_for(floor):
    """Return (hp_mult, damage_mult, count_add, elite_chance, guardian_chance) for a floor.

    Extrapolates past floor 15 for endless mode: +0.15 hp and +0.1 damage per
    floor beyond MAX_FLOOR (15).
    """
    f = max(1, int(floor))
    if f <= SCALING_FLOORS[0]:
        return tuple(SCALING[0][1:])
    if f >= SCALING_FLOORS[-1]:
        # Extrapolate past floor 15 for endless mode
        extra = f - SCALING_FLOORS[-1]
        hp = SCALING[-1][1] + 0.15 * extra
        dmg = SCALING[-1][2] + 0.1 * extra
        cnt = SCALING[-1][3]
        elite = SCALING[-1][4]
        guard = SCALING[-1][5]
        return (hp, dmg, cnt, elite, guard)
    # find bracketing rows
    for i in range(len(SCALING_FLOORS) - 1):
        lo = SCALING_FLOORS[i]
        hi = SCALING_FLOORS[i + 1]
        if lo <= f < hi:
            t = (f - lo) / (hi - lo)
            row_lo = SCALING[i]
            row_hi = SCALING[i + 1]
            hp = _lerp(row_lo[1], row_hi[1], t)
            dmg = _lerp(row_lo[2], row_hi[2], t)
            cnt = int(_lerp(row_lo[3], row_hi[3], t))
            elite = _lerp(row_lo[4], row_hi[4], t)
            guard = _lerp(row_lo[5], row_hi[5], t)
            return (hp, dmg, cnt, elite, guard)
    return tuple(SCALING[-1][1:])


def _scale_for_ascended(floor, ascension_mods=None):
    """Return (hp_mult, damage_mult, count_add, elite_chance, guardian_chance) for a floor,
    with ascension modifiers applied (P1.4)."""
    hp, dmg, cnt, elite, guard = _scale_for(floor)
    am = ascension_mods or {}
    hp *= float(am.get("enemy_hp_mult", 1.0))
    dmg *= float(am.get("enemy_damage_mult", 1.0))
    elite *= float(am.get("elite_chance_mult", 1.0))
    # clamp elite to [0, 1]
    elite = max(0.0, min(1.0, elite))
    return (hp, dmg, cnt, elite, guard)


def difficulty_for(floor):
    """Monster hp/damage scaling for *floor* (P1.1 table-driven, was 12%/floor)."""
    hp, dmg, *_ = _scale_for(floor)
    return hp  # legacy callers expect a single multiplier; use hp as the canonical one


def elite_chance(floor):
    """Elite spawn chance on *floor* (P1.1 table)."""
    return _scale_for(floor)[3]


def guardian_chance(floor):
    """Chance a non-boss floor spawns a guardian on the stairs (P1.1 table)."""
    return _scale_for(floor)[4]


def make_monster(world, defn, x, y, elite=False, guardian=False, boss=False,
                  difficulty=1.0, damage_mult=1.0):
    mon = Monster(world.next_id(), x, y, defn, elite=elite, guardian=guardian, boss=boss,
                  difficulty=difficulty, damage_mult=damage_mult)
    if elite:
        affix = world.rng.choice(world.content.affixes()) if world.content.affixes() else None
        mon.affix_name = affix.get("name") if affix else None
        if affix:
            effects = dict(affix.get("effect") or {})
            mon.stats.set_mod("affix", effects)
            mon.affix_effects = effects
        mon.hp = mon.stats.max_hp()
    world.add_entity(mon)
    return mon


def spawn_pool(content, world, biome_id, floor):
    tier_cap = max(1, min(4, 1 + int(floor / 3.0)))
    pool = []
    for defn in content.monster_pool(biome_id, max_tier=tier_cap):
        if int(defn.get("tier", 1)) >= 5:
            continue                       # bosses and guardians spawn explicitly
        weight = float(defn.get("weight", 1) or 1)
        distance = abs(int(defn.get("tier", 1)) - tier_cap)
        pool.append((defn, weight / (1.0 + 0.5 * distance)))
    if not pool:
        for defn in content.monster_pool(biome_id, max_tier=5):
            if int(defn.get("tier", 1)) < 5:
                pool.append((defn, 1.0))
    return pool


def populate_floor(world, floor, biome_id):
    """Fill every room of the freshly generated level with monsters and loot."""
    level = world.level
    content = world.content
    pool = spawn_pool(content, world, biome_id, floor)
    asc_mods = getattr(world, "ascension_modifiers", None) or {}
    hp_mult, dmg_mult, count_add, elite_rate, _guardian_rate = _scale_for_ascended(floor, asc_mods)
    elite_rate = min(1.0, elite_rate + world.elite_bonus)
    # P1.8: endless mode scaling past floor 15
    if getattr(world, "endless", False) and floor > MAX_FLOOR:
        extra = floor - MAX_FLOOR
        hp_mult *= (1.0 + 0.15 * extra)
        dmg_mult *= (1.0 + 0.1 * extra)
    spawned = 0
    for room in level.rooms:
        if room["kind"] == "entrance":
            continue
        # .get, not []: rooms arrive from content AND from procgen, and a template missing
        # an optional field must not end the run. This is the second time a room source has
        # disagreed about this key, so the consumer refuses to be the thing that crashes.
        budget = int(room.get("spawn_budget", 0) or 0) + count_add
        if room["kind"] == "boss":
            continue
        budget = max(0, min(8, budget))
        for _ in range(budget):
            if not pool:
                break
            defn = world.rng.weighted(pool)
            if defn is None:
                break
            tx, ty = level.spawn_tile_in(room, world.rng, avoid=level.spawn_tile, margin=2)
            if (tx, ty) == level.spawn_tile:
                continue
            elite = world.rng.chance(elite_rate)
            make_monster(world, defn, tx * TILE + 16, ty * TILE + 16, elite=elite,
                         difficulty=hp_mult, damage_mult=dmg_mult)
            spawned += 1
        # room flavour: treasure rooms hold a chest, shops a stall, shrines a shrine
        if room["kind"] == "treasure":
            cx, cy = room["center"]
            world.add_entity(Pickup(world.next_id(), cx * TILE + 16, cy * TILE + 16, "chest",
                                    sprite="prop_chest", magnet=False))
        elif room["kind"] == "shop":
            cx, cy = room["center"]
            world.add_entity(Pickup(world.next_id(), cx * TILE + 16, cy * TILE + 16, "shop",
                                    sprite="prop_table", magnet=False))
        elif room["kind"] == "shrine":
            cx, cy = room["center"]
            world.add_entity(Pickup(world.next_id(), cx * TILE + 16, cy * TILE + 16, "shrine",
                                    sprite="prop_shrine", magnet=False))

    world.floor_spawned = spawned
    _spawn_guardian_or_boss(world, floor, biome_id, hp_mult)


def _spawn_guardian_or_boss(world, floor, biome_id, difficulty):
    level = world.level
    content = world.content
    asc_mods = getattr(world, "ascension_modifiers", None) or {}
    hp_mult, dmg_mult, *_ = _scale_for_ascended(floor, asc_mods)
    stairs_room = level.stairs_room or (level.rooms[-1] if level.rooms else None)
    is_boss_floor = (floor % FLOOR_PER_BIOME == 0)
    if stairs_room is None:
        return None
    tx, ty = level.spawn_tile_in(stairs_room, world.rng, avoid=level.spawn_tile, margin=3)
    if is_boss_floor:
        boss_defn = content.boss_for(biome_id)
        if boss_defn is None:
            return None
        mon = make_monster(world, boss_defn, tx * TILE + 16, ty * TILE + 16,
                           boss=True, guardian=True, difficulty=hp_mult, damage_mult=dmg_mult)
        # P1.4: ascension 5 — boss gets a random affix
        if asc_mods.get("boss_random_affix", False) and content.affixes():
            affix = world.rng.choice(content.affixes())
            if affix:
                mon.affix_name = affix.get("name")
                effects = dict(affix.get("effect") or {})
                mon.stats.set_mod("affix", effects)
                mon.affix_effects = effects
                mon.hp = mon.stats.max_hp()
        world.guardian_id = mon.id
        world.boss_alive = True
        world.boss_phase = 0
        world.boss_phase_name = mon.phase.get("name", "") if mon.defn.get("phases") else ""
        world.boss_hazard_timer = 0
        world.boss_add_timer = 0
        world.floating.add(world.content.flavor_for("boss", world.rng) or "The guardian wakes.",
                           color=(232, 178, 60), life=3.0)
        return mon
    # non-boss floors: a unique guardian holds the stairs (P1.1 table rate)
    if world.rng.chance(guardian_chance(floor)):
        pool = [p for p in spawn_pool(content, world, biome_id, floor)]
        if not pool:
            return None
        stronger = [(d, w) for d, w in pool if int(d.get("tier", 1)) >= 2]
        pool = stronger or pool
        defn = world.rng.weighted([(d, w * (1.0 + int(d.get("tier", 1)))) for d, w in pool])
        if defn is None:
            return None
        mon = make_monster(world, defn, tx * TILE + 16, ty * TILE + 16, elite=True,
                           guardian=True, difficulty=hp_mult * 1.15, damage_mult=dmg_mult)
        mon.hp = mon.stats.max_hp()
        mon.guardian = True
        world.guardian_id = mon.id
        return mon
    return None


def spawn_boss_for_floor(world, floor, biome_id):
    """Explicit boss spawn (used by tests and QA autopilot)."""
    return _spawn_guardian_or_boss(world, floor - (floor % FLOOR_PER_BIOME) + FLOOR_PER_BIOME,
                                   biome_id, difficulty_for(floor))


def drop_loot_for(world, mon):
    """Death drops: gold, sometimes essence, health orbs, items, keys."""
    rng = world.rng
    floor = world.floor
    gold = int(rng.randint(2, 5) + mon.tier * rng.randint(1, 3))
    if mon.boss:
        gold *= 6
    elif mon.guardian:
        gold *= 3
    world.add_entity(Pickup(world.next_id(), mon.x, mon.y, "gold", amount=gold,
                            sprite="prop_gold_pile"))
    if rng.chance(0.28 if not mon.boss else 1.0):
        amount = int(rng.randint(1, 2) + mon.tier * 0.8)
        if mon.boss:
            amount *= 8
        world.add_entity(Pickup(world.next_id(), mon.x + 8, mon.y + 4, "essence", amount=amount,
                                sprite="prop_essence"))
    if rng.chance(0.18) or (mon.boss and rng.chance(0.9)):
        world.add_entity(Pickup(world.next_id(), mon.x - 8, mon.y + 4, "health", amount=18,
                                sprite="prop_potion_health"))
    drop_chance = 0.10 + 0.03 * mon.tier
    if mon.elite:
        drop_chance += 0.18
    if mon.boss:
        drop_chance = 1.0
    if rng.chance(min(0.95, drop_chance)):
        tier = loot.tier_for_floor(floor, world.player.stats.luck())
        unlocks = (world.profile or {}).get("unlocks") if world.profile else None
        item = loot.make_item(world.content, rng, tier=tier, luck=world.player.stats.luck(), unlocks=unlocks)
        if item is not None:
            world.add_entity(Pickup(world.next_id(), mon.x, mon.y - 6, "item", item=item,
                                    sprite=item.get("sprite")))
    if mon.guardian or mon.boss:
        world.add_entity(Pickup(world.next_id(), mon.x + 4, mon.y - 10, "key",
                                amount=1, sprite="prop_key"))


def chest_loot(world, x, y):
    """Chests spawn 1-3 item pickups (GDD section 5)."""
    rng = world.rng
    count = rng.randint(1, 3)
    tier = loot.tier_for_floor(world.floor, world.player.stats.luck())
    unlocks = (world.profile or {}).get("unlocks") if world.profile else None
    out = []
    for i in range(count):
        item = loot.make_item(world.content, rng, tier=tier, luck=world.player.stats.luck(), unlocks=unlocks)
        if item is None:
            continue
        angle = i * (math.tau / max(1, count))
        px = x + math.cos(angle) * 22.0
        py = y + math.sin(angle) * 22.0
        pickup = Pickup(world.next_id(), px, py, "item", item=item, sprite=item.get("sprite"))
        world.add_entity(pickup)
        out.append(pickup)
    return out


def _scale_for_endless(world, floor):
    """No-op placeholder. Endless floor scaling is handled in populate_floor()
    via the hp_mult/dmg_mult multipliers applied when world.endless is True."""
    pass
