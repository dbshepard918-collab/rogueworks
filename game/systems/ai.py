"""Monster AI: chaser, ranged, ambusher, brute - plus elites, guardians and bosses.

P2.2 TELEGRAPHS: Every enemy attack gets a windup animation/indicator before it lands.
Each behavior has a data-driven telegraph_duration (seconds of visible windup) and
telegraph_sprite (VFX frame name to render as the windup indicator).
The telegraph must be visible and dodgeable — no unavoidable damage.
"""

import math

from ..entities.actor import move_with_collision
from . import combat, statuses as status_sys

TILE = 32
AGGRO_RADIUS = 380.0      # monsters notice the lantern at this range (or when hit)

# Default telegraph durations per behavior (seconds) — overridden by monster data
DEFAULT_TELEGRAPH = {
    'chaser': 0.25,       # quick lunge windup
    'ranged': 0.35,       # charge windup before projectile
    'ambusher': 0.40,     # burst windup before leap
    'brute': 0.55,        # heavy slam windup
}


def update_monster(world, mon, dt):
    player = world.player
    if not mon.alive or player is None or not player.alive:
        return
    if status_sys.is_stunned(mon):
        return

    dist = mon.dist_to(player)

    # aggro gate: unalerted monsters far away hold their post (no whole-floor conga line)
    if not mon.alert:
        if dist <= AGGRO_RADIUS or mon.boss or mon.guardian:
            mon.alert = True
        else:
            _hold_post(world, mon, dt)
            return

    behavior = mon.behavior

    if behavior == 'ambusher':
        _ambusher(world, mon, player, dist, dt)
    elif behavior == 'ranged':
        _ranged(world, mon, player, dist, dt)
    elif behavior == 'brute' or mon.boss:
        _brute(world, mon, player, dist, dt)
    elif behavior == 'summoner':
        _summoner(world, mon, player, dist, dt)
    elif behavior == 'shielded':
        _shielded(world, mon, player, dist, dt)
    elif behavior == 'teleporter':
        _teleporter(world, mon, player, dist, dt)
    elif behavior == 'charger':
        _charger(world, mon, player, dist, dt)
    elif behavior == 'splitter':
        _splitter(world, mon, player, dist, dt)
    elif behavior == 'runner':
        _runner(world, mon, player, dist, dt)
    else:
        _chaser(world, mon, player, dist, dt)


def _hold_post(world, mon, dt):
    """Idle drift around the spawn area so the floor looks alive but stays calm."""
    mon.wander_timer -= dt
    if mon.wander_timer <= 0.0:
        mon.wander_timer = 1.2 + world.rng.random() * 1.6
        mon.state_side = world.rng.choice((-1, 0, 1))
        mon.state_fwd = world.rng.choice((-1, 0, 1))
    side = getattr(mon, 'state_side', 0)
    fwd = getattr(mon, 'state_fwd', 0)
    if not (side or fwd):
        return
    speed = mon.stats.speed() * 0.25 * TILE
    move_with_collision(mon, side * speed * dt, fwd * speed * dt, world.level)


def _telegraph_duration(mon):
    """Return the telegraph windup duration for this monster."""
    return getattr(mon, 'telegraph_duration',
                   DEFAULT_TELEGRAPH.get(mon.behavior, 0.25))


def _telegraph_sprite(mon):
    """Return the VFX atlas frame name for this monster's telegraph indicator."""
    return getattr(mon, 'telegraph_sprite',
                   {'chaser': 'vfx_sparkle', 'ranged': 'vfx_soul_wisp',
                    'ambusher': 'vfx_smoke', 'brute': 'vfx_shockwave'
                    }.get(mon.behavior, 'vfx_sparkle'))


# ------------------------------------------------------------------ chaser --
def _chaser(world, mon, player, dist, dt):
    telegraph_dur = _telegraph_duration(mon)
    # P2.2: telegraph windup before lunge — stop moving, show indicator
    if mon.telegraph > 0.0:
        return
    # telegraph just expired — fire the strike
    if getattr(mon, 'pending_strike', False):
        mon.pending_strike = False
        combat.monster_contact_attack(world, mon)
        return
    if dist <= mon.melee_range() and mon.attack_timer <= 0.0:
        mon.telegraph = telegraph_dur
        mon.telegraph_indicator = _telegraph_sprite(mon)
        mon.state = 'wind'
        mon.pending_strike = True
        world.particles.burst(mon.x, mon.y, world.rng, count=6,
                              color=(200, 200, 180), speed=40.0, life=0.3, size=2)
        return
    _approach(world, mon, player, dt, speed_scale=1.0)


# ------------------------------------------------------------------ ambusher --
def _ambusher(world, mon, player, dist, dt):
    if mon.state == 'idle':
        if dist < 180.0 and world.level.line_walkable(mon.x, mon.y, player.x, player.y):
            mon.state = 'hunt'
            mon.burst_timer = 2.2
            mon.alert = True
        else:
            return
    telegraph_dur = _telegraph_duration(mon)
    # P2.2: telegraph windup before burst
    if mon.telegraph > 0.0:
        return
    # telegraph just expired — fire the strike
    if getattr(mon, 'pending_strike', False):
        mon.pending_strike = False
        combat.monster_contact_attack(world, mon)
        return
    if dist <= mon.melee_range() and mon.attack_timer <= 0.0:
        mon.telegraph = telegraph_dur
        mon.telegraph_indicator = _telegraph_sprite(mon)
        mon.state = 'wind'
        mon.pending_strike = True
        world.particles.burst(mon.x, mon.y, world.rng, count=8,
                              color=(138, 132, 150), speed=50.0, life=0.35, size=2)
        return
    scale = 2.0 if mon.burst_timer > 0.0 else 1.15
    _approach(world, mon, player, dt, speed_scale=scale)


# ------------------------------------------------------------------- ranged --
def _ranged(world, mon, player, dist, dt):
    ideal_far = 250.0
    ideal_near = 150.0
    if dist < ideal_near:
        _retreat(world, mon, player, dt)
    elif dist > ideal_far:
        _approach(world, mon, player, dt, speed_scale=1.0)
    else:
        _strafe(world, mon, player, dt)
    telegraph_dur = _telegraph_duration(mon)
    # P2.2: telegraph windup before ranged attack
    if mon.telegraph > 0.0:
        return
    # telegraph just expired — fire the projectile
    if getattr(mon, 'pending_shot', False):
        mon.pending_shot = False
        combat.monster_ranged(world, mon)
        return
    if (mon.attack_timer <= 0.0 and 90.0 < dist < 340.0
            and world.level.line_walkable(mon.x, mon.y, player.x, player.y)):
        mon.telegraph = telegraph_dur
        mon.telegraph_indicator = _telegraph_sprite(mon)
        mon.state = 'wind'
        mon.pending_shot = True
        return
    # attack_timer reset handled by monster_contact_attack/monster_ranged calls


# ------------------------------------------------------------------- brute --
def _brute(world, mon, player, dist, dt):
    if mon.telegraph > 0.0:
        return                       # winding up, do not move
    telegraph_dur = _telegraph_duration(mon)
    # telegraph just expired — fire the slam
    if getattr(mon, 'pending_slam', False):
        mon.pending_slam = False
        combat.monster_slam(world, mon)
        return
    if dist <= mon.slam_radius and mon.attack_timer <= 0.0:
        mon.telegraph = telegraph_dur
        mon.telegraph_indicator = _telegraph_sprite(mon)
        mon.state = 'wind'
        world.particles.burst(mon.x, mon.y, world.rng, count=10,
                              color=(168, 60, 28), speed=60.0, life=0.35, size=3)
        mon.pending_slam = True
        return
    if dist <= mon.melee_range() and mon.attack_timer <= 0.0:
        combat.monster_contact_attack(world, mon)
        return
    _approach(world, mon, player, dt, speed_scale=1.0)


def _runner(world, mon, player, dist, dt):
    """Runs away and shoots: retreats while firing ranged projectiles."""
    # Retreat
    _retreat(world, mon, player, dt)
    telegraph_dur = _telegraph_duration(mon)
    if mon.telegraph > 0.0:
        return
    if getattr(mon, 'pending_shot', False):
        mon.pending_shot = False
        combat.monster_ranged(world, mon)
        return
    if (mon.attack_timer <= 0.0 and 120.0 < dist < 400.0
            and world.level.line_walkable(mon.x, mon.y, player.x, player.y)):
        mon.telegraph = telegraph_dur
        mon.telegraph_indicator = _telegraph_sprite(mon)
        mon.state = 'wind'
        mon.pending_shot = True
        return


# ------------------------------------------------------------- summoner --

def _summoner(world, mon, player, dist, dt):
    """Spawns 2-3 minion copies of itself when telegraph expires."""
    telegraph_dur = _telegraph_duration(mon)
    if mon.telegraph > 0.0:
        return
    if getattr(mon, 'pending_summon', False):
        mon.pending_summon = False
        combat.monster_summon(world, mon)
        return
    if dist <= mon.melee_range() and mon.attack_timer <= 0.0:
        mon.telegraph = telegraph_dur
        mon.telegraph_indicator = _telegraph_sprite(mon)
        mon.state = 'wind'
        mon.pending_summon = True
        world.particles.burst(mon.x, mon.y, world.rng, count=10,
                              color=(200, 60, 60), speed=50.0, life=0.4, size=3)
        return
    _approach(world, mon, player, dt, speed_scale=1.0)


# -------------------------------------------------------------- shielded --

def _shielded(world, mon, player, dist, dt):
    """Directional damage block: absorbs frontal attacks and reflects a fraction."""
    telegraph_dur = _telegraph_duration(mon)
    # During telegraph, face player and show shield indicator
    if mon.telegraph > 0.0:
        dx = player.x - mon.x
        dy = player.y - mon.y
        length = max(0.001, (dx * dx + dy * dy) ** 0.5)
        mon.facing = (dx / length, dy / length)
        return
    if getattr(mon, 'pending_block', False):
        mon.pending_block = False
        combat.monster_shield(world, mon)
        return
    if dist <= mon.melee_range() and mon.attack_timer <= 0.0:
        mon.telegraph = telegraph_dur
        mon.telegraph_indicator = _telegraph_sprite(mon)
        mon.state = 'wind'
        mon.pending_block = True
        world.particles.burst(mon.x, mon.y, world.rng, count=8,
                              color=(60, 120, 200), speed=40.0, life=0.3, size=2)
        return
    if dist <= mon.melee_range() + 10:
        _approach(world, mon, player, dt, speed_scale=0.5)
    else:
        _approach(world, mon, player, dt, speed_scale=1.0)


# ------------------------------------------------------------ teleporter ---

def _teleporter(world, mon, player, dist, dt):
    """Repositions to a random position near the player when telegraph expires."""
    telegraph_dur = _telegraph_duration(mon)
    if mon.telegraph > 0.0:
        return
    if getattr(mon, 'pending_teleport', False):
        mon.pending_teleport = False
        combat.monster_teleport(world, mon)
        return
    if dist <= mon.melee_range() and mon.attack_timer <= 0.0:
        mon.telegraph = telegraph_dur
        mon.telegraph_indicator = _telegraph_sprite(mon)
        mon.state = 'wind'
        mon.pending_teleport = True
        world.particles.burst(mon.x, mon.y, world.rng, count=12,
                              color=(120, 80, 180), speed=60.0, life=0.35, size=2)
        return
    _approach(world, mon, player, dt, speed_scale=1.2)


# ------------------------------------------------------------- charger -----

def _charger(world, mon, player, dist, dt):
    """Leap attack: dashes toward the player dealing AoE damage on landing."""
    telegraph_dur = _telegraph_duration(mon)
    if mon.telegraph > 0.0:
        return
    if getattr(mon, 'pending_charge', False):
        mon.pending_charge = False
        combat.monster_charge(world, mon)
        return
    if dist <= mon.slam_radius and mon.attack_timer <= 0.0:
        mon.telegraph = telegraph_dur
        mon.telegraph_indicator = _telegraph_sprite(mon)
        mon.state = 'wind'
        mon.pending_charge = True
        world.particles.burst(mon.x, mon.y, world.rng, count=10,
                              color=(180, 80, 30), speed=70.0, life=0.35, size=3)
        return
    _approach(world, mon, player, dt, speed_scale=1.4)


# ------------------------------------------------------------- splitter --

def _splitter(world, mon, player, dist, dt):
    """Standard chaser that splits into weaker copies on death."""
    telegraph_dur = _telegraph_duration(mon)
    if mon.telegraph > 0.0:
        return
    if getattr(mon, 'pending_strike', False):
        mon.pending_strike = False
        combat.monster_contact_attack(world, mon)
        return
    if dist <= mon.melee_range() and mon.attack_timer <= 0.0:
        mon.telegraph = telegraph_dur
        mon.telegraph_indicator = _telegraph_sprite(mon)
        mon.state = 'wind'
        mon.pending_strike = True
        world.particles.burst(mon.x, mon.y, world.rng, count=6,
                              color=(100, 160, 60), speed=45.0, life=0.3, size=2)
        return
    _approach(world, mon, player, dt, speed_scale=1.0)
def _step_toward(world, mon, tx, ty, dt, speed_scale):
    dx = tx - mon.x
    dy = ty - mon.y
    length = (dx * dx + dy * dy) ** 0.5
    if length < 1.0:
        return False
    speed = mon.stats.speed() * speed_scale * TILE
    before = (mon.x, mon.y)
    move_with_collision(mon, dx / length * speed * dt, dy / length * speed * dt, world.level)
    moved = abs(mon.x - before[0]) > 0.01 or abs(mon.y - before[1]) > 0.01
    if not moved:
        # blocked by geometry: fall back to a short BFS path
        if mon.repath_timer <= 0.0:
            mon.path = world.path_to(mon.tile_x, mon.tile_y,
                                     int(tx // TILE), int(ty // TILE), cap=900) or []
            mon.repath_timer = 0.45
        if mon.path:
            nxt = mon.path[0]
            gx = nxt[0] * TILE + 16
            gy = nxt[1] * TILE + 16
            adx = gx - mon.x
            ady = gy - mon.y
            alen = (adx * adx + ady * ady) ** 0.5
            if alen > 1.0:
                move_with_collision(mon, adx / alen * speed * dt, ady / alen * speed * dt,
                                    world.level)
            if alen < 10.0:
                mon.path.pop(0)
    else:
        mon.path = []
    if dx or dy:
        mon.facing = (dx / max(0.001, length), dy / max(0.001, length))
    return moved


def _approach(world, mon, player, dt, speed_scale=1.0):
    _step_toward(world, mon, player.x, player.y, dt, speed_scale)


def _retreat(world, mon, player, dt):
    dx = mon.x - player.x
    dy = mon.y - player.y
    length = (dx * dx + dy * dy) ** 0.5
    if length < 1.0:
        dx, dy, length = 1.0, 0.0, 1.0
    speed = mon.stats.speed() * 0.8 * TILE
    move_with_collision(mon, dx / length * speed * dt, dy / length * speed * dt, world.level)
    mon.facing = (player.x - mon.x, player.y - mon.y)


def _strafe(world, mon, player, dt):
    mon.wander_timer -= dt
    if mon.wander_timer <= 0.0:
        mon.wander_timer = 0.8
        mon.state_side = world.rng.choice((-1, 1))
    side = getattr(mon, 'state_side', 1)
    dx = player.x - mon.x
    dy = player.y - mon.y
    length = max(0.001, (dx * dx + dy * dy) ** 0.5)
    px, py = -dy / length * side, dx / length * side
    speed = mon.stats.speed() * 0.55 * TILE
    move_with_collision(mon, px * speed * dt, py * speed * dt, world.level)
    mon.facing = (dx / length, dy / length)
