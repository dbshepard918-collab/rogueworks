"""Combat: damage resolution, player auto-melee, aimed shots, monster attacks."""

import math

from ..engine.audio import play
from ..entities.projectile import Projectile
from . import statuses as status_sys
from . import unique as unique_sys

ELEMENT_TO_STATUS = {
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

TILE = 32

# Element -> impact particle colour/sprite mapping (P2.1)
ELEMENT_PARTICLES = {
    "physical": ("vfx_impact", (246, 242, 232), (140, 31, 52)),
    "fire": ("vfx_impact", (226, 113, 29), (232, 178, 60)),
    "poison": ("vfx_impact", (3, 120, 46), (61, 176, 74)),
    "ice": ("vfx_impact", (100, 180, 230), (121, 176, 74)),
    "lightning": ("vfx_impact", (200, 200, 80), (140, 31, 52)),
    "holy": ("vfx_impact", (232, 220, 180), (232, 178, 60)),
    "shadow": ("vfx_impact", (60, 50, 80), (140, 31, 52)),
}

# --------------------------------------------------------------- damage ----
def damage_target(world, target, amount, source=None, damage_type="physical",
                  crit=False, knockback=0.0, attacker_pos=None, status_id=None,
                  element="physical"):
    """Single funnel for all damage. Returns the damage actually dealt."""
    if target is None or not getattr(target, "alive", False):
        return 0.0
    if getattr(target, "invulnerable", None) and target.invulnerable():
        if target is world.player:
            world.damage_numbers.add(target.x, target.y - 14, 0, label="dodge",
                                     color=(180, 240, 255))
        return 0.0

    raw = max(0.0, float(amount))
    if crit:
        raw *= 2.0
    armor = target.stats.armor()
    if damage_type == "dot":
        dealt = raw                                  # DOTs bypass armor
    else:
        dealt = raw * (1.0 - armor)
        if dealt < 1.0 and raw > 0.0:
            dealt = 1.0
    dealt = round(dealt, 2)
    target.hp -= dealt
    target.clamp_hp()

    # P2.1: trigger hit-stop on both attacker and target
    target.trigger_hit_stop(0.09)
    if source is not None and hasattr(source, "trigger_hit_stop"):
        source.trigger_hit_stop(0.06)

    # P3.5: track seen monsters
    is_player_target = target is world.player
    if not is_player_target and getattr(target, 'monster_id', None):
        world.seen_monsters.add(target.monster_id)

    # P2.5: propagate element as status on hit
    if element and element != "physical":
        _apply_element_on_hit(world, target, element)

    # P3.5: track last damage source for death cause attribution
    if source is not None:
        target.last_damage_source = source
    elif target is world.player and getattr(target, 'last_damage_source', None) is None:
        # For projectiles fired by monsters (source=None in damage_target call)
        # the projectile knows its owner
        pass

    if is_player_target:
        target.hit_flash = 0.12
        target.last_damage_taken = dealt
        world.screen_flash = max(world.screen_flash, min(0.5, dealt / max(1.0, target.stats.max_hp())))
        # P2.1: screen shake scaled by damage, capped at 14, respects toggle
        shake = min(14.0, 2.0 + dealt * 0.35)
        world.camera.add_shake(shake)
        # P4.4: dead-zone kick on heavy hits
        if dealt >= 15:
            world.camera.add_kick(int(dealt * 0.8))
        world.damage_numbers.add(target.x, target.y - 18, dealt, color=(255, 120, 120),
                                 scale=3)
        world.particles.sprite_burst(target.x, target.y, "vfx_blood", life=0.22)
        play(world, "hurt")
        world.metrics_damage_taken = getattr(world, "metrics_damage_taken", 0.0) + dealt
        # P1.6: armor unique reflect — return a fraction of damage taken
        unique_sys.apply_unique(world, world.player.equipment.get("armor"), "damage_taken",
                                 attacker=source, amount=dealt)
        # P1.6: trinket purifier — a DOT applied to the player returns a pulse
        if status_id:
            unique_sys.apply_unique(world, world.player.equipment.get("trinket"),
                                    "damage_taken", actor=target, status_id=status_id)
    else:
        target.hit_flash = 0.08
        target.alert = True            # being hit pulls a monster in
        # P2.1: damage numbers with crit styling — scale 2 cream non-crit, scale 3 gold crit, DOT green
        if damage_type == "dot":
            dn_scale = 2
            dn_color = (121, 176, 74)  # green for DOT
        elif crit:
            dn_scale = 3
            dn_color = (232, 178, 60)  # gold for crit
        else:
            dn_scale = 2
            dn_color = (246, 242, 232)  # cream for non-crit
        world.damage_numbers.add(target.x, target.y - 14, dealt, color=dn_color,
                                 scale=dn_scale)
        # P2.1: element-matched impact particles
        _spawn_elemental_particles(world, target.x, target.y, element, crit)
        if dealt > 0:
            world.particles.sprite_burst(target.x, target.y, "vfx_impact", life=0.16)
        # P4.4: scorch decal on fire/ember damage
        if element in ("fire", "ember"):
            world.scorch_decals.append({
                "x": target.x, "y": target.y,
                "life": 3.0, "max_life": 3.0,
            })
            # Cap scorch decals
            if len(world.scorch_decals) > 200:
                world.scorch_decals.pop(0)
        world.particles.burst(target.x, target.y, world.rng, count=5 if not crit else 9,
                              color=(140, 31, 52) if not crit else (232, 178, 60),
                              speed=70.0, life=0.32, size=3)
        play(world, "hit")
        world.metrics_damage_dealt = getattr(world, "metrics_damage_dealt", 0.0) + dealt

    if knockback > 0.0:
        base = attacker_pos if attacker_pos else (target.x + 1.0, target.y)
        kx = target.x - base[0]
        ky = target.y - base[1]
        resist = float(getattr(target, "knock_resist", 1.0) or 1.0)
        force = knockback / max(0.05, resist)
        target.add_knockback(kx, ky, force)

    if target.hp <= 0.0:
        kill(world, target, source)
    return dealt


def _get_weapon_element(player):
    """P2.5: Get the element from the player's equipped weapon."""
    weapon = player.equipment.get("weapon") if hasattr(player, "equipment") else None
    if weapon and isinstance(weapon, dict):
        return weapon.get("element", "physical")
    return "physical"


def _apply_element_on_hit(world, target, element):
    """P2.5: Apply element-based status on hit."""
    from . import statuses as status_sys
    status_id = ELEMENT_TO_STATUS.get(element)
    if status_id and hasattr(world, "content"):
        status_sys.apply_status(world, target, status_id)


def _spawn_elemental_particles(world, x, y, element, crit=False):
    """P2.1: spawn impact particles matched to the damage element."""
    particle_name, burst_color, _ = ELEMENT_PARTICLES.get(element, ELEMENT_PARTICLES["physical"])
    count = 9 if crit else 5
    world.particles.sprite_burst(x, y, particle_name, life=0.2, scale=1.5 if crit else 1.0)
    world.particles.burst(x, y, world.rng, count=count, color=burst_color,
                          speed=80.0 if crit else 60.0, life=0.35, size=3 if crit else 2)


def kill(world, target, source=None):
    target.hp = 0.0
    if not target.alive:
        return
    target.alive = False
    target.death_timer = 0.6
    # r52: death poof on every kill
    world.particles.sprite_burst(target.x, target.y, "vfx_death_poof", life=0.3, scale=1.5)
    if target is world.player:
        # P3.5: determine death cause
        death_cause = ""
        if source is not None:
            if hasattr(source, 'monster_id'):
                death_cause = "slain by %s" % source.monster_id
            elif hasattr(source, 'name'):
                death_cause = "slain by %s" % source.name
            elif hasattr(source, 'kind'):
                death_cause = "killed by %s" % source.kind
        # P3.5: if source is a projectile, get the owner monster
        if not death_cause and source is not None:
            src = source
            if hasattr(src, 'owner') and src.owner != "player":
                if hasattr(src, 'monster_id'):
                    death_cause = "slain by %s" % src.monster_id
                elif hasattr(src, 'owner_id'):
                    death_cause = "killed by projectile"
        elif not death_cause:
            # Try last_damage_source fallback
            last_src = getattr(target, 'last_damage_source', None)
            if last_src is not None:
                if hasattr(last_src, 'monster_id'):
                    death_cause = "slain by %s" % last_src.monster_id
        if not death_cause:
            death_cause = "killed"
        world.on_player_death(death_cause)
        return
    world.on_monster_death(target, source)
    # P1.2 biome: catacombs undead may respawn once per floor
    from . import biome_mods as _bm
    _bm.on_monster_death_add_respawn(world, target)


# --------------------------------------------------------------- player -----
def player_melee(world, player):
    """The auto-swing.  Fires when a monster is inside the weapon's reach/arc."""
    reach = player.ATTACK_REACH
    best = None
    best_dist = 1e18
    for mon in world.monsters:
        if not mon.alive:
            continue
        dist = mon.dist_to(player) - mon.radius
        if dist > reach:
            continue
        dx = mon.x - player.x
        dy = mon.y - player.y
        length = max(0.001, (dx * dx + dy * dy) ** 0.5)
        fx, fy = player.facing
        flen = max(0.001, (fx * fx + fy * fy) ** 0.5)
        dot = (dx / length) * (fx / flen) + (dy / length) * (fy / flen)
        angle = math.acos(max(-1.0, min(1.0, dot)))
        # point blank swings hit in a full circle; the arc matters at reach
        if angle > player.ATTACK_ARC / 2.0 and dist > 22.0:
            continue
        if dist < best_dist:
            best_dist = dist
            best = mon
    if best is None:
        return None
    # always swing at what we are actually hitting
    dx = best.x - player.x
    dy = best.y - player.y
    length = max(0.001, (dx * dx + dy * dy) ** 0.5)
    player.facing = (dx / length, dy / length)
    player.attack_timer = player.ATTACK_COOLDOWN
    player.swing_timer = 0.18
    player.swing_dir = player.facing
    world.particles.sprite_burst(player.x + player.facing[0] * 20, player.y + player.facing[1] * 20,
                                 "vfx_slash", life=0.16)
    world.particles.burst(player.x + player.facing[0] * 18, player.y + player.facing[1] * 18,
                          world.rng, count=4, color=(147, 160, 180), speed=60.0, life=0.22, size=3)
    play(world, "swing")
    crit = world.rng.chance(player.stats.crit())
    # r52: hit spark on contact + crit strike overlay
    world.particles.sprite_burst(best.x, best.y, "vfx_hit_spark", life=0.18, scale=1.5)
    if crit:
        world.particles.sprite_burst(best.x, best.y, "vfx_crit_strike", life=0.25, scale=2.0)
    # P1.3: might tree tiers add extra melee knockback
    knockback = 120.0
    try:
        from . import save as save_sys
        se = save_sys.meta_special_effects(world.profile)
        knockback += float(se.get("melee_knockback_add", 0.0))
    except Exception:
        pass
    # P2.5: get weapon element
    weapon_element = _get_weapon_element(player)
    dealt = damage_target(world, best, player.stats.damage(), source=player, crit=crit,
                          knockback=knockback, attacker_pos=(player.x, player.y),
                          element=weapon_element)
    # P1.6: weapon unique effects fire on a melee hit
    unique_sys.apply_unique(world, player.equipment.get("weapon"), "melee_hit",
                             target=best, damage_dealt=dealt)
    return dealt


def _meta_melee_knockback_add(world):
    """Extra knockback force from the might tree (P1.3)."""
    try:
        from . import save as save_sys
        se = save_sys.meta_special_effects(world.profile)
        return float(se.get("melee_knockback_add", 0.0))
    except Exception:
        return 0.0


def player_ranged(world, player):
    """SPACE: aimed projectile in the facing direction."""
    player.ranged_timer = player.RANGED_COOLDOWN
    fx, fy = player.facing
    length = max(0.001, (fx * fx + fy * fy) ** 0.5)
    fx /= length
    fy /= length
    speed = 620.0
    weapon_element = _get_weapon_element(player)
    proj = Projectile(world.next_id(), player.x + fx * 14, player.y + fy * 14,
                      fx * speed, fy * speed, player.stats.damage() * 0.85,
                      owner="player", sprite="projectile_soul", lifetime=1.4, radius=5.0)
    proj.crit_chance = player.stats.crit()
    proj.element = weapon_element
    # P1.6: weapon unique pierce — extra monsters the bolt passes through
    unique_sys.apply_unique(world, player.equipment.get("weapon"), "ranged_fire", proj=proj)
    world.add_entity(proj)
    # r50: muzzle flash VFX
    world.particles.sprite_burst(player.x + fx * 16, player.y + fy * 16,
                                 "vfx_muzzle_flash", life=0.12, scale=1.5)
    play(world, "shoot")
    return proj


def monster_ranged(world, mon):
    mon.attack_timer = mon.attack_cooldown()
    tx, ty = world.player.x, world.player.y
    dx = tx - mon.x
    dy = ty - mon.y
    length = max(0.001, (dx * dx + dy * dy) ** 0.5)
    speed = 260.0
    element = getattr(mon, "element", "physical")
    proj = Projectile(world.next_id(), mon.x, mon.y, dx / length * speed, dy / length * speed,
                      mon.stats.damage(), owner="monster",
                      sprite="vfx_soul_wisp", lifetime=2.0, radius=6.0,
                      status_on_hit=mon.status_on_hit)
    proj.element = element
    world.add_entity(proj)
    play(world, "shoot")
    return proj


def monster_charge(world, mon):
    """Charger leap attack — dash toward player, AoE damage + shockwave on landing."""
    mon.attack_timer = mon.attack_cooldown()
    dx = world.player.x - mon.x
    dy = world.player.y - mon.y
    length = max(0.001, (dx * dx + dy * dy) ** 0.5)
    # Leap toward player
    leap_x = mon.x + (dx / length) * 20
    leap_y = mon.y + (dy / length) * 20
    mon.x = leap_x
    mon.y = leap_y
    world.particles.sprite_burst(mon.x, mon.y, "vfx_shockwave", life=0.3, scale=2.0)
    world.particles.burst(mon.x, mon.y, world.rng, count=12,
                          color=(180, 80, 30), speed=100.0, life=0.4, size=3)
    world.camera.add_shake(6.0)
    # AoE damage to all monsters and player in radius
    radius = 40.0
    for target in [world.player] + world.monsters:
        if not target.alive or target is mon:
            continue
        if mon.dist_to(target) <= radius + target.radius:
            dealt = damage_target(world, target, mon.stats.damage() * 0.7, source=mon,
                                  knockback=200.0, attacker_pos=(mon.x, mon.y))
            if mon.status_on_hit and dealt > 0:
                status_sys.apply_status(world, target, mon.status_on_hit)


def monster_summon(world, mon):
    """Summoner — spawns 2-3 minion copies of the monster."""
    summon_count = getattr(mon, 'summon_count', 3)
    minion_defn = getattr(mon, 'minion_defn', None) or mon.defn
    for i in range(summon_count):
        angle = (2 * math.pi / summon_count) * i
        offset = 50.0
        tx = mon.x + offset * math.cos(angle)
        ty = mon.y + offset * math.sin(angle)
        if world.level.in_bounds(int(tx // TILE), int(ty // TILE)):
            from .spawn import make_monster
            minion = make_monster(world, minion_defn, tx, ty, elite=False, difficulty=world.rng.uniform(0.8, 1.0))
            minion.hp = minion.stats.max_hp() * 0.4
            minion.stats.set_mod("summon", {"max_hp": -0.6, "damage": -0.3, "speed": 0.2})
            world.add_entity(minion)
    world.particles.sprite_burst(mon.x, mon.y, "vfx_soul_wisp", life=0.4, scale=1.5)
    world.particles.burst(mon.x, mon.y, world.rng, count=15,
                          color=(200, 60, 60), speed=60.0, life=0.4, size=3)


def monster_shield(world, mon):
    """Shielded — applies a directional block and reflects damage."""
    shield_angle = getattr(mon, 'shield_angle', 130.0)
    block_radius = 35.0
    reflect_frac = 0.3
    # Find if player is in the shield cone
    player = world.player
    if player is not None and mon.dist_to(player) <= block_radius + player.radius:
        dx = player.x - mon.x
        dy = player.y - mon.y
        length = max(0.001, (dx * dx + dy * dy) ** 0.5)
        dot = (dx / length) * mon.facing[0] + (dy / length) * mon.facing[1]
        angle_deg = math.acos(max(-1.0, min(1.0, dot))) * 180 / math.pi
        if angle_deg < shield_angle / 2:
            # Player is in front — reflect a fraction of damage back
            if player.hit_flash <= 0.0:
                reflect_dmg = player.stats.damage() * reflect_frac
                if reflect_dmg > 0:
                    from .combat import damage_target
                    damage_target(world, player, reflect_dmg, source=mon,
                                  knockback=50.0, attacker_pos=(mon.x, mon.y))
                    world.damage_numbers.add(mon.x, mon.y - 14, reflect_dmg,
                                              color=(60, 120, 200), scale=2)
    world.particles.sprite_burst(mon.x, mon.y, "vfx_shield", life=0.25, scale=1.5)


def monster_teleport(world, mon):
    """Teleporter — repositions to a random walkable tile near the player."""
    player = world.player
    if player is None:
        return
    # Pick a random position within 100px of player
    angle = world.rng.random() * math.tau
    dist = world.rng.uniform(60, 150)
    tx = int((player.x + dist * math.cos(angle)) // TILE)
    ty = int((player.y + dist * math.sin(angle)) // TILE)
    if world.level.in_bounds(tx, ty) and world.level.walkable(tx, ty):
        mon.x = tx * 32 + 16
        mon.y = ty * 32 + 16
    world.particles.sprite_burst(mon.x, mon.y, "vfx_smoke", life=0.5, scale=2.0)
    world.particles.burst(mon.x, mon.y, world.rng, count=10,
                          color=(120, 80, 180), speed=50.0, life=0.5, size=3)


def monster_split(world, mon):
    """Splitter — on death, splits into 2 weaker copies."""
    split_count = getattr(mon, 'split_count', 2)
    from .spawn import make_monster
    for i in range(split_count):
        angle = (2 * math.pi / split_count) * i + world.rng.uniform(-0.3, 0.3)
        offset = 20.0
        tx = mon.x + offset * math.cos(angle)
        ty = mon.y + offset * math.sin(angle)
        if world.level.in_bounds(int(tx // TILE), int(ty // TILE)) and world.level.walkable(int(tx // TILE), int(ty // TILE)):
            split_defn = getattr(mon, 'split_defn', None)
            if split_defn is None:
                split_defn = dict(mon.defn)
                split_defn["hp"] = str(int(float(mon.defn.get("hp", "10")) * 0.4))
                split_defn["damage"] = str(int(float(mon.defn.get("damage", "3")) * 0.5))
            split_mon = make_monster(world, split_defn, tx, ty, elite=False, difficulty=0.6)
            split_mon.hp = split_mon.stats.max_hp() * 0.4
            world.add_entity(split_mon)
    world.particles.sprite_burst(mon.x, mon.y, "vfx_splash", life=0.3, scale=1.5)
    world.particles.burst(mon.x, mon.y, world.rng, count=12,
                          color=(100, 160, 60), speed=55.0, life=0.3, size=3)


def monster_contact_attack(world, mon):
    mon.attack_timer = mon.attack_cooldown()
    crit = world.rng.chance(0.05)
    element = getattr(mon, "element", "physical")
    dealt = damage_target(world, world.player, mon.stats.damage(), source=mon, crit=crit,
                          knockback=150.0, attacker_pos=(mon.x, mon.y), element=element)
    if mon.status_on_hit and dealt > 0:
        status_sys.apply_status(world, world.player, mon.status_on_hit)
    return dealt


def monster_slam(world, mon):
    """Brute/boss telegraphed heavy hit - a radial shockwave."""
    mon.attack_timer = mon.attack_cooldown()
    radius = mon.slam_radius
    world.particles.burst(mon.x, mon.y, world.rng, count=26, color=(168, 60, 28),
                          speed=190.0, life=0.5, size=4)
    world.particles.sprite_burst(mon.x, mon.y, "vfx_shockwave", life=0.35, scale=2.5)
    world.camera.add_shake(9.0 if mon.boss else 6.0)
    # P4.4: dead-zone kick on boss slam
    if mon.boss:
        world.camera.add_kick(12)
    player = world.player
    dist = player.dist_to(mon)
    if dist <= radius:
        element = getattr(mon, "element", "physical")
        dealt = damage_target(world, player, mon.stats.damage() * 1.5, source=mon,
                              knockback=260.0, attacker_pos=(mon.x, mon.y), element=element)
        if dealt > 0 and mon.status_on_hit:
            status_sys.apply_status(world, player, mon.status_on_hit)
        return dealt
    return 0.0


# ------------------------------------------------------------ projectiles ---
def update_projectiles(world, dt):
    for proj in world.projectiles:
        if not proj.alive:
            continue
        proj.tick(dt)
        if not proj.alive:
            continue
        level = world.level
        if not level.in_bounds(int(proj.x // TILE), int(proj.y // TILE)):
            proj.alive = False
            continue
        if not level.walkable_px(proj.x, proj.y):
            proj.alive = False
            world.particles.burst(proj.x, proj.y, world.rng, count=3,
                                  color=(138, 132, 150), speed=45.0, life=0.2, size=2)
            continue

        if proj.owner == "player":
            for mon in world.monsters:
                if not mon.alive or mon.id in proj.hit_ids:
                    continue
                reach = mon.radius + proj.radius
                if proj.dist_sq_to_xy(mon.x, mon.y) <= reach * reach:
                    crit = world.rng.chance(getattr(proj, "crit_chance", 0.05))
                    element = getattr(proj, "element", "physical")
                    damage_target(world, mon, proj.damage, source=world.player, crit=crit,
                                  knockback=90.0, attacker_pos=(proj.x, proj.y),
                                  element=element)
                    proj.hit_ids.add(mon.id)
                    if proj.pierce > 0:
                        proj.pierce -= 1
                    else:
                        proj.alive = False
                    break
        else:
            player = world.player
            reach = player.radius + proj.radius
            if player.alive and proj.dist_sq_to_xy(player.x, player.y) <= reach * reach:
                element = getattr(proj, "element", "physical")
                # P3.5: for monster projectiles, pass the projectile as source
                # so the kill() can attribute death to the monster owner
                if proj.owner == "monster":
                    dealt = damage_target(world, player, proj.damage, source=proj,
                                          attacker_pos=(proj.x, proj.y), element=element)
                else:
                    dealt = damage_target(world, player, proj.damage, source=None,
                                          attacker_pos=(proj.x, proj.y), element=element)
                if dealt > 0 and proj.status_on_hit:
                    status_sys.apply_status(world, player, proj.status_on_hit)
                proj.alive = False
                # P1.2 drowned chain lightning — after a ranged hit, try one chain hop
                from . import biome_mods as _bm
                _bm.maybe_chain_lightning(world, proj.x, proj.y, getattr(proj, "owner_id", -1))

    world.projectiles = [p for p in world.projectiles if p.alive]
