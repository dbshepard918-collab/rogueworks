"""Biome-specific rule modifiers (P1.2).

Each biome can carry one ``modifier`` id from ``game/data/biomes.json``.
The modifiers change simulation rules, not just art:

* ``ember_heat``    — standing on a burning tile ticks burn DOT; magnitude ramps
                       with floor depth (GDD "heat damage ramp").
* ``drowned_water`` — standing in water slows the player; standing still in
                       water applies slow ("slip"); ranged hits can chain once
                       through the water ("electric-conductive pools").
* ``catacombs_darkness`` — reduced lantern halo radius ("lantern radius matters");
                       catacombs undead respawn once per floor ("undead respawn
                       once").

The active modifier is shown on the HUD as a short badge (GDD "Display the
active modifier on the HUD").

All new effects funnel through the existing Stats / statuses pipeline
(CONTRACTS.md §6) — no ad-hoc stat arithmetic outside this module.
"""

from __future__ import annotations

from . import statuses as status_sys


# --------------------------------------------------------------------------- tile types
# These must stay in sync with procgen.TILE_* (same module family).
TILE_BURNING = 4
TILE_WATER = 5
TILE_CRACKED = 8

# --------------------------------------------------------------------------- config
# One config dict per modifier id.  Numbers are tuned to feel different but
# not punishing on the default difficulty curve (P1.1).
_MODULES = {
    "ember_heat": {
        "hud_label": "EMBER",
        "hud_color": (226, 113, 29),
        # heat ticks the burn status every HEAT_TICK_EVERY ticks while on a
        # burning tile; magnitude ramps +1 every 5 floors (GDD "heat damage ramp").
        "heat_tick_every": 120,        # ticks (~2 s at 60 Hz)
        "heat_base_magnitude": 2,
        "heat_ramp_per_5": 1,
    },
    "drowned_water": {
        "hud_label": "DROWNED",
        "hud_color": (31, 95, 128),
        # persistent speed penalty while standing in water tiles
        "water_slow_pct": 0.18,
        # standing still in water applies slow after SLIP_DELAY ticks
        "slip_delay_ticks": 150,       # ~2.5 s
        "slip_status": "slow",
        "slip_magnitude": 0.45,
        "slip_duration": 120,
        # after a ranged hit lands, a tiny chance to chain to one nearby monster
        "chain_chance": 0.20,
        "chain_radius": 260.0,
        "chain_damage": 1.0,
    },
    "ossuary_toxic": {
        "hud_label": "TOXIC",
        "hud_color": (126, 168, 72),
        # Sunken Ossuary pools are caustic: standing in one ticks poison every
        # TOXIC_TICK_EVERY ticks, magnitude ramping +1 per 5 floors like ember heat.
        "toxic_tick_every": 150,       # ticks (~2.5 s at 60 Hz)
        "toxic_base_magnitude": 2,
        "toxic_ramp_per_5": 1,
        # the miasma corrodes anywhere on the floor: a slow stacking weaken
        "miasma_tick_every": 900,      # ~15 s
        "miasma_duration": 900,
        "miasma_magnitude": 0.08,
    },
    "catacombs_darkness": {
        "hud_label": "DARK",
        "hud_color": (138, 132, 150),
        # lantern halo radius scales down from the renderer default
        "halo_radius": 280,            # renderer default is 440
        # undead corpses have a chance to respawn once per floor after a delay
        "respawn_chance": 0.18,
        "respawn_delay": 300,          # ticks (~5 s)
        "respawn_hp_frac": 0.5,
        "respawn_tier_cap": 3,
    },
}

# undead heuristic — kept cheap and stable; only catacombs rooms use this path.
_UNDEAD_PREFIXES = (
    "bone_", "ash_", "skull_", "crypt_", "grave_",
    "shroud_", "wraith", "ghoul", "skeleton", "ossuary",
)


# --------------------------------------------------------------------------- state

class _BiomeState:
    """Mutable state attached to a World for the current run/floor."""
    __slots__ = ("modifier", "heat_timer", "slip_timer",
                 "was_in_water", "respawn_queue", "respawned_ids",
                 "last_moved", "toxic_timer", "miasma_timer")

    def __init__(self):
        self.modifier = None
        self.heat_timer = 0.0
        self.slip_timer = 0.0
        self.was_in_water = False
        self.respawn_queue = []          # list[dict] for catacombs
        self.respawned_ids = set()       # one revive per id per floor
        self.last_moved = False
        self.toxic_timer = 0.0
        self.miasma_timer = 0.0


def attach_biome_state(world):
    if getattr(world, "_biome_mod_state", None) is None:
        world._biome_mod_state = _BiomeState()
    return world._biome_mod_state


def config(world):
    st = attach_biome_state(world)
    return _MODULES.get(st.modifier)


def mod_id(world):
    st = attach_biome_state(world)
    return st.modifier


def set_modifier(world, mid):
    st = attach_biome_state(world)
    st.modifier = mid
    # entering a new biome: clear transient state that does not carry over
    st.heat_timer = 0.0
    st.slip_timer = 0.0
    st.toxic_timer = 0.0
    st.miasma_timer = 0.0
    st.was_in_water = False
    st.last_moved = False
    # respawn queue is floor-scoped; cleared in new_floor


# ---------------------------------------------------------------------- step

def step(world, dt):
    """Called from World.step once per tick, after status ticks."""
    cfg = config(world)
    if cfg is None:
        _clear_water_penalties(world)
        return

    st = attach_biome_state(world)
    mid = st.modifier

    if mid == "ember_heat":
        _step_ember(world, cfg, st)
    elif mid == "drowned_water":
        _step_drowned(world, cfg, st)
    elif mid == "catacombs_darkness":
        _step_catacombs(world, cfg, st)
    elif mid == "ossuary_toxic":
        _step_ossuary(world, cfg, st)


def _step_ossuary(world, cfg, st):
    """Sunken Ossuary: the pools are caustic and the air corrodes.

    Pools reuse the WATER tile (the renderer already draws it) but the *modifier*
    gives them their meaning, exactly as drowned_water does - so the two biomes read
    the same tile and behave differently. The drowned slow penalty is explicitly
    cleared here: toxic water must not inherit it.
    """
    _clear_water_penalties(world)
    player = world.player
    if player is None or not player.alive:
        st.toxic_timer = 0.0
        return

    if _tile_at(world, player) == TILE_WATER:
        st.toxic_timer += 1.0       # step() runs once per tick (dt == TICK)
        if st.toxic_timer >= cfg["toxic_tick_every"]:
            st.toxic_timer = 0.0
            ramp = max(0, (world.floor - 1) // 5) * cfg["toxic_ramp_per_5"]
            status_sys.apply_status(world, player, "poison",
                                    duration_ticks=cfg["toxic_tick_every"],
                                    magnitude=cfg["toxic_base_magnitude"] + ramp)
    else:
        st.toxic_timer = 0.0

    st.miasma_timer += 1.0
    if st.miasma_timer >= cfg["miasma_tick_every"]:
        st.miasma_timer = 0.0
        status_sys.apply_status(world, player, "weaken",
                                duration_ticks=cfg["miasma_duration"],
                                magnitude=cfg["miasma_magnitude"])


def _step_ember(world, cfg, st):
    player = world.player
    if player is None or not player.alive:
        return
    on_burn = _tile_at(world, player) == TILE_BURNING
    if on_burn:
        st.heat_timer += 1.0   # step() is called once per tick (dt == TICK)
        if st.heat_timer >= cfg["heat_tick_every"]:
            st.heat_timer = 0.0
            ramp = max(0, (world.floor - 1) // 5) * cfg["heat_ramp_per_5"]
            mag = cfg["heat_base_magnitude"] + ramp
            dot_weakness = 0.0
            try:
                from . import save as save_sys
                se = save_sys.meta_special_effects(world.profile)
                dot_weakness = float(se.get("burning_dot_weakness", 0.0))
            except Exception:
                pass
            mag = mag * (1.0 - dot_weakness)
            status_sys.apply_status(world, player, "burn",
                                    duration_ticks=cfg["heat_tick_every"],
                                    magnitude=mag)
    else:
        st.heat_timer = 0.0


def _step_drowned(world, cfg, st):
    player = world.player
    if player is None or not player.alive:
        return
    in_water = _tile_at(world, player) == TILE_WATER
    if in_water and not st.was_in_water:
        _apply_water_penalty(world, True, cfg)
    elif not in_water and st.was_in_water:
        _apply_water_penalty(world, False, cfg)

    if in_water and not st.last_moved:
        st.slip_timer += 1.0
        if st.slip_timer >= cfg["slip_delay_ticks"]:
            st.slip_timer = 0.0
            status_sys.apply_status(world, player, cfg["slip_status"],
                                    duration_ticks=cfg["slip_duration"],
                                    magnitude=cfg["slip_magnitude"])
    else:
        st.slip_timer = 0.0

    st.was_in_water = in_water


def _apply_water_penalty(world, on, cfg):
    player = world.player
    if player is None:
        return
    src = "biome_drowned_water"
    if on:
        player.stats.set_pct(src, {"speed": -cfg["water_slow_pct"]})
    else:
        player.stats.remove_mod(src)


def _clear_water_penalties(world):
    player = world.player
    if player is None:
        return
    player.stats.remove_mod("biome_drowned_water")


def _step_catacombs(world, cfg, st):
    now = world.tick
    queue = st.respawn_queue
    if not queue:
        return
    remaining = []
    for entry in queue:
        if now >= entry["at"]:
            if entry["monster_id"] not in st.respawned_ids:
                _try_respawn(world, entry, cfg)
                st.respawned_ids.add(entry["monster_id"])
        else:
            remaining.append(entry)
    st.respawn_queue = remaining


def _try_respawn(world, entry, cfg):
    level = world.level
    if level is None:
        return
    tx, ty = entry["tile_x"], entry["tile_y"]
    if not (0 <= tx < level.w and 0 <= ty < level.h):
        return
    if level.tiles[tx][ty] == 1:      # WALL
        return
    defn = world.content.monster(entry["monster_id"])
    if defn is None:
        return
    if int(defn.get("tier", 1)) > cfg["respawn_tier_cap"]:
        return
    from ..entities.monster import Monster
    x = tx * 64 + 32
    y = ty * 64 + 32
    mon = Monster(world.next_id(), x, y, defn, difficulty=1.0, damage_mult=1.0)
    mon.hp = mon.stats.max_hp() * cfg["respawn_hp_frac"]
    world.add_entity(mon)
    world.floating.add("the dead stir", color=(170, 160, 140), life=2.0)


# -------------------------------------------------------------------- combat

def maybe_chain_lightning(world, hit_x, hit_y, source_id):
    """After a ranged projectile lands, try one chain hop in drowned vaults."""
    cfg = config(world)
    if cfg is None or config(world).get("hud_label") != "DROWNED":
        return None
    if not world.rng.chance(cfg["chain_chance"]):
        return None
    best = None
    best_d2 = cfg["chain_radius"] ** 2
    for mon in world.monsters:
        if not mon.alive or mon.id == source_id:
            continue
        d2 = (mon.x - hit_x) ** 2 + (mon.y - hit_y) ** 2
        if d2 < best_d2:
            best_d2 = d2
            best = mon
    if best is None:
        return None
    from . import combat
    combat.damage_target(world, best, cfg["chain_damage"], source=None,
                         damage_type="physical")
    world.damage_numbers.add(best.x, best.y - 14, cfg["chain_damage"],
                             color=(180, 240, 255), scale=2)
    world.particles.burst(best.x, best.y, world.rng, count=8,
                          color=(180, 240, 255), speed=110.0, life=0.35, size=3)
    world.floating.add("chain lightning", color=(180, 240, 255), life=0.7)
    return best.id


def on_monster_death_add_respawn(world, mon):
    """Called from combat.kill when a monster dies — catacombs undead may
    be scheduled for one revive."""
    cfg = config(world)
    if cfg is None or cfg.get("hud_label") != "DARK":
        return
    if mon.monster_id in attach_biome_state(world).respawned_ids:
        return
    if not _is_undead(mon.defn):
        return
    if not world.rng.chance(cfg["respawn_chance"]):
        return
    attach_biome_state(world).respawn_queue.append({
        "monster_id": mon.monster_id,
        "tile_x": int(mon.tile_x),
        "tile_y": int(mon.tile_y),
        "at": world.tick + cfg["respawn_delay"],
    })


def _is_undead(defn):
    if defn is None:
        return False
    prefix = str(defn.get("id", "")).lower()
    return any(prefix.startswith(p) for p in _UNDEAD_PREFIXES) or bool(defn.get("undead"))


# -------------------------------------------------------------------- tiles

def _level_tile_set(level, *names):
    """First attribute of `level` that exists and is not None, else an empty set.

    `Level` stores these as `_burning` / `_water`; these helpers used to look for
    `_biome_burning_tiles` / `_biome_water_tiles`, which nothing ever set - so both
    returned empty for every floor. The only consumers are the renderer's tile overlays,
    which meant burning tiles, water pools and the Sunken Ossuary's toxic pools were
    **drawn nowhere**: the player could not see the hazard standing on them.
    """
    for name in names:
        value = getattr(level, name, None)
        if value is not None:
            return value
    return frozenset()


def burning_tiles(level):
    """Set of (tx, ty) burning tiles placed by procgen for the active ember floor."""
    return _level_tile_set(level, "_biome_burning_tiles", "_burning")


def water_tiles(level):
    """Set of (tx, ty) water/hazard-pool tiles placed by procgen for the active biome."""
    return _level_tile_set(level, "_biome_water_tiles", "_water")


def _tile_at(world, player):
    level = world.level
    if level is None or player is None:
        return None
    tx = player.tile_x
    ty = player.tile_y
    if not (0 <= tx < level.w and 0 <= ty < level.h):
        return None
    return level.tiles[tx][ty]


# -------------------------------------------------------------------- HUD

def hud_badge(world):
    """(label, color) for the active modifier badge, or None."""
    cfg = config(world)
    if cfg is None:
        return None
    return (cfg["hud_label"], cfg["hud_color"])


def lantern_radius(world, profile=None):
    """Lantern halo radius for the active biome modifier (renderer use).

    P1.3: the lantern branch stat bonuses (meta_stat_totals["lantern"]) add
    flat px on top of the biome baseline.  This is the canonical path: every
    lantern tier sets ``stat: "lantern"`` with its px bonus, and
    ``meta_stat_totals`` sums them — so the radius grows linearly with what
    the player bought, and the renderer + minimap see the same number.
    """
    cfg = config(world)
    base = cfg.get("halo_radius", 220) if cfg is not None else 220
    add = 0.0
    if profile is not None:
        try:
            from . import save as save_sys
            totals = save_sys.meta_stat_totals(profile)
            add = float(totals.get("lantern", 0.0))
        except Exception:
            pass
    return base + add


def mark_moved(world):
    """Call after a player move resolves so the drowned slip timer can reset."""
    st = getattr(world, "_biome_mod_state", None)
    if st is not None:
        st.last_moved = True


def clear_moved_flag(world):
    st = getattr(world, "_biome_mod_state", None)
    if st is not None:
        st.last_moved = False
