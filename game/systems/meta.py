"""Meta-progression: run results folded into the persistent profile (P1.3 tree-aware)."""

from . import save as save_sys


def apply_run_results(profile, world):
    """Death is progress: bank essence, bump counters, remember the best floor."""
    if profile is None:
        return profile
    if getattr(world, "results_banked", False):
        return profile
    world.results_banked = True
    profile["essence"] = int(profile.get("essence", 0)) + int(world.essence_run)
    stats = profile.setdefault("stats", {"runs": 0, "best_floor": 1, "kills": 0})
    stats["runs"] = int(stats.get("runs", 0)) + 1
    stats["kills"] = int(stats.get("kills", 0)) + int(world.kills_run)
    stats["best_floor"] = max(int(stats.get("best_floor", 1) or 1), int(world.floor))
    # P3.5: persist run history, codex, and bestiary
    _persist_run_storytelling(profile, world)
    return profile


def _persist_run_storytelling(profile, world):
    """Save run history, codex, and bestiary data to the profile."""
    if profile is None:
        return
    # Run history entry
    run_entry = {
        "seed": int(world.seed),
        "floor": int(world.floor),
        "biome": str(world.biome_name or world.biome_id),
        "kills": int(world.kills_run),
        "rooms": int(world.rooms_visited),
        "death_cause": str(world.death_cause),
        "essence": int(world.essence_run),
    }
    run_history = profile.setdefault("run_history", [])
    run_history.append(run_entry)
    # Keep last 50 runs
    if len(run_history) > 50:
        profile["run_history"] = run_history[-50:]
    # Update codex with seen monsters from this run
    codex = profile.setdefault("codex", {})
    for mon_id in world.seen_monsters:
        if mon_id not in codex:
            codex[mon_id] = {"seen": False, "kills": 0}
        codex[mon_id]["seen"] = True
    # Update bestiary with killed monsters from this run
    bestiary = profile.setdefault("bestiary", {})
    for mon_id, count in world.killed_monsters.items():
        bestiary[mon_id] = int(bestiary.get(mon_id, 0)) + count
    # Update codex kill counts for killed monsters
    for mon_id, count in world.killed_monsters.items():
        if mon_id not in codex:
            codex[mon_id] = {"seen": False, "kills": 0}
        codex[mon_id]["kills"] = int(codex[mon_id].get("kills", 0)) + count
    # Mark seen items in codex
    for item_id in world.seen_items:
        if item_id not in codex:
            codex[item_id] = {"seen": False, "kills": 0}
        codex[item_id]["seen"] = True


def clear_run(profile):
    if profile is not None:
        profile["run"] = None
    return profile


def start_run(profile, seed, floor=1, biome=""):
    if profile is not None:
        profile["run"] = {"seed": int(seed), "floor": int(floor), "biome": str(biome)}
    return profile


def upgrade_rows(profile):
    """(id, label, level, max_level, price, affordable) rows for the meta shop.

    P1.3: one row per tree tier, with branch grouping.  Consumers that only read
    ``id / label / level / max_level / per_level / price / affordable`` keep
    working; the row dict now also carries ``branch_id``, ``branch_name``,
    ``branch_color``, ``stat``, ``bonus``, ``desc``, ``owned``,
    ``prerequisites``, ``prereq_missing`` and ``essence`` so the shop UI can
    render the tree.
    """
    rows = []
    for row in save_sys.tree_state(profile):
        rows.append({
            "id": "%s:%d" % (row["branch_id"], row["level"]),
            "label": row["label"],
            "level": row["level"],
            "max_level": row["max_level"],
            "per_level": row["bonus"] or 0,
            "price": row["cost"],
            "affordable": row["affordable"],
            # extras for the tree UI
            "branch_id": row["branch_id"],
            "branch_name": row["branch_name"],
            "branch_color": row["branch_color"],
            "stat": row["stat"],
            "bonus": row["bonus"],
            "desc": row["desc"],
            "owned": row["owned"],
            "prerequisites": row["prerequisites"],
            "prereq_missing": row["prereq_missing"],
            "essence": row["essence"],
        })
    return rows


def bonus_totals(profile):
    return save_sys.meta_stat_totals(profile)


def tree_state(profile):
    return save_sys.tree_state(profile) if profile else []


def respec(profile):
    if profile is None:
        return False
    return save_sys.respec(profile)


def respec_cost():
    return save_sys.respec_cost()


def special_effects(profile):
    """Non-stat meta effects available to the systems that consume them."""
    return save_sys.meta_special_effects(profile) if profile else {}
