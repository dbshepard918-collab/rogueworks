"""Meta-progression save file (docs/CONTRACTS.md section 7).

``save.json`` lives in the project root.  Loading tolerates a missing file
(fresh profile) and an older/invalid ``version`` (migrate or reset) and never
raises.

P5.1 — save robustness: version 3 adds ``save_slots`` and ``autosave`` fields,
atomic writes with .bak backup, corrupted-save recovery, and named save slots.
"""

import json
import os
import shutil
from pathlib import Path

SAVE_VERSION = 3

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SAVE_PATH = PROJECT_ROOT / "save.json"

RUNS_DIR = PROJECT_ROOT / "runs"

# ----- tree data (loaded once, cached) -----
_TREE = None


def meta_tree_data():
    global _TREE
    if _TREE is not None:
        return _TREE
    try:
        raw = json.loads((PROJECT_ROOT / "game" / "data" / "meta_tree.json").read_text(encoding="utf-8"))
        if isinstance(raw, dict) and isinstance(raw.get("branches"), list):
            _TREE = raw
            return _TREE
    except (OSError, ValueError):
        pass
    _TREE = {"version": 1, "branches": [], "respec_cost": 0}
    return _TREE


def _branch(branch_id):
    for b in meta_tree_data().get("branches", []):
        if b.get("id") == branch_id:
            return b
    return None


def _tier_def(branch_id, level):
    b = _branch(branch_id)
    if not b:
        return None
    for t in b.get("tiers", []):
        if int(t.get("level", 0)) == int(level):
            return t
    return None


def tier_exists(branch_id, level):
    if level < 1:
        return False
    t = _tier_def(branch_id, level)
    return t is not None


def tier_prereqs(branch_id, level):
    t = _tier_def(branch_id, level)
    if not t:
        return []
    prereq = t.get("prereq")
    if not prereq:
        return []
    return [prereq]


def tier_cost(branch_id, level):
    t = _tier_def(branch_id, level)
    if not t:
        return None
    return int(t.get("cost", 0))


def tier_bonus(branch_id, level):
    t = _tier_def(branch_id, level)
    if not t:
        return 0.0
    bonus = t.get("bonus")
    if bonus is None:
        return 0.0
    return float(bonus)


def stat_for_tier(branch_id, level):
    t = _tier_def(branch_id, level)
    if not t:
        return None
    return t.get("stat")


def tier_label(branch_id, level):
    t = _tier_def(branch_id, level)
    return t.get("label") if t else ""


def tier_desc(branch_id, level):
    t = _tier_def(branch_id, level)
    return t.get("desc") if t else ""


def respec_cost():
    return int(meta_tree_data().get("respec_cost", 0) or 0)


def branch_ids():
    return [b["id"] for b in meta_tree_data().get("branches", [])]


def branch_for_stat(stat):
    mapping = {
        "max_hp": "vitality", "damage": "might", "speed": "agility",
        "luck": "fortune", "armor": "vitality", "crit": "might", "lantern": "lantern",
    }
    return mapping.get(stat)


# ----- profile shape -----

CLASS_DEFS = {
    "lantern_keeper": {
        "name": "Lantern Keeper", "desc": "Balanced — the default descent.",
        "stats": {"max_hp": 90.0, "damage": 7.0, "speed": 4.2, "armor": 0.0, "luck": 0.0, "crit": 0.05},
        "unlock": None, "unlock_desc": "Available from the start",
    },
    "grave_warden": {
        "name": "Grave Warden", "desc": "Tanky — more HP and armor, slower and less deadly.",
        "stats": {"max_hp": 120.0, "damage": 6.0, "speed": 3.6, "armor": 0.03, "luck": 0.0, "crit": 0.03},
        "unlock": "floor:10", "unlock_desc": "Unlocked by reaching floor 10",
    },
    "ash_dancer": {
        "name": "Ash Dancer", "desc": "Fast & fragile — high damage and speed, low HP.",
        "stats": {"max_hp": 65.0, "damage": 9.0, "speed": 5.2, "armor": 0.0, "luck": 2.0, "crit": 0.08},
        "unlock": "floor:6", "unlock_desc": "Unlocked by reaching floor 6",
    },
}
CLASS_IDS = list(CLASS_DEFS.keys())


def class_stats(class_id, meta_totals):
    defn = CLASS_DEFS.get(class_id) or CLASS_DEFS["lantern_keeper"]
    base = dict(defn["stats"])
    mt = meta_totals or {}
    base["max_hp"] = float(base["max_hp"]) + float(mt.get("max_hp", 0.0))
    base["damage"] = float(base["damage"]) + float(mt.get("damage", 0.0))
    base["armor"] = float(base["armor"]) + float(mt.get("armor", 0.0)) * 0.01
    base["speed"] = float(base["speed"]) + float(mt.get("speed", 0.0))
    base["luck"] = float(base["luck"]) + float(mt.get("luck", 0.0))
    base["crit"] = float(base["crit"]) + float(mt.get("crit", 0.0))
    return base


# ----- P1.4: ascension tiers -----

ASCENSION_MODIFIERS = {
    1: {"enemy_hp_mult": 1.10}, 2: {"enemy_damage_mult": 1.10},
    3: {"elite_chance_mult": 1.15}, 4: {"healing_mult": 0.85},
    5: {"boss_random_affix": True},
}
_ASCENSION_DEFAULTS = {
    "enemy_hp_mult": 1.0, "enemy_damage_mult": 1.0,
    "elite_chance_mult": 1.0, "healing_mult": 1.0, "boss_random_affix": False,
}


def ascension_modifiers(ascension_level):
    out = dict(_ASCENSION_DEFAULTS)
    level = max(0, min(5, int(ascension_level)))
    for lvl, mods in ASCENSION_MODIFIERS.items():
        if lvl <= level:
            for key, value in mods.items():
                out[key] = value
    return out


def unlock_item(profile, item_id):
    if profile is None:
        return False
    unlocks = profile.setdefault("unlocks", {})
    if unlocks.get(item_id):
        return False
    unlocks[item_id] = True
    return True


# ----- profile shape -----

def default_profile():
    return {
        "version": SAVE_VERSION,
        "meta": {"hp": 0, "damage": 0, "speed": 0.0, "luck": 0, "armor": 0, "crit": 0.0},
        "levels": {}, "essence": 0,
        "stats": {"runs": 0, "best_floor": 1, "kills": 0},
        "run": None, "class_id": "lantern_keeper", "unlocks": {},
        "ascension": 0, "unlocked_classes": ["lantern_keeper"], "unlocked_ascension": 0,
        "settings": {}, "run_history": [], "codex": {}, "bestiary": {},
        "quests": {"active": [], "completed": [], "progress": {}},
        "save_slots": {"default": str(DEFAULT_SAVE_PATH), "autosave": str(PROJECT_ROOT / "save_autosave.json")},
        "autosave": {"last_floor": 0, "last_biome": "", "last_seed": 0, "timestamp": 0},
    }


def _sanitize_slot_name(slot_name):
    if slot_name in (None, "default"):
        return "default"
    if slot_name == "autosave":
        return "autosave"
    text = str(slot_name).strip()
    if not text:
        return "default"
    clean = []
    for ch in text:
        if ch.isalnum() or ch in ("_", "-"):
            clean.append(ch)
    cleaned = "".join(clean).strip("_-")
    return cleaned or "default"


def _slot_path(slot_name):
    name = _sanitize_slot_name(slot_name)
    if name == "default":
        return DEFAULT_SAVE_PATH
    if name == "autosave":
        return PROJECT_ROOT / "save_autosave.json"
    return PROJECT_ROOT / ("save_%s.json" % name)


# ----- normalization helpers -----

def _norm_levels(levels):
    if not isinstance(levels, dict):
        return {}
    out = {}
    for key, value in levels.items():
        if not isinstance(key, str) or ":" not in key:
            continue
        branch_id, sep, lvl = key.partition(":")
        if not branch_id or not lvl or not tier_exists(branch_id, int(lvl)):
            continue
        try:
            out[key] = 1 if int(value or 0) >= 1 else 0
        except (TypeError, ValueError):
            out[key] = 0
    return out


def _norm_meta(meta):
    if not isinstance(meta, dict):
        meta = {}
    out = {"hp": 0.0, "damage": 0.0, "speed": 0.0, "luck": 0.0, "armor": 0.0, "crit": 0.0}
    for key in out:
        try:
            out[key] = float(meta.get(key, 0.0) or 0.0)
        except (TypeError, ValueError):
            out[key] = 0.0
    return out


def _norm_unlocks(unlocks):
    if not isinstance(unlocks, dict):
        return {}
    out = {}
    for key, value in unlocks.items():
        if not isinstance(key, str):
            continue
        out[key] = True if value else False
    return {k: v for k, v in out.items() if v}


def _settings_norm(raw):
    from ..ui.settings import normalize as _norm
    return _norm(raw)


def _norm_unlocked_classes(classes):
    if not isinstance(classes, list):
        return ["lantern_keeper"]
    out = []
    for cid in classes:
        if isinstance(cid, str) and cid in CLASS_DEFS:
            out.append(cid)
    if "lantern_keeper" not in out:
        out.insert(0, "lantern_keeper")
    return out


def _norm_quests(raw):
    """Normalise the persistent quest state (active/completed/progress)."""
    if not isinstance(raw, dict):
        return {"active": [], "completed": [], "progress": {}}
    active = [str(x) for x in raw.get("active", []) if isinstance(x, str)]
    completed = [str(x) for x in raw.get("completed", []) if isinstance(x, str)]
    progress = raw.get("progress") if isinstance(raw.get("progress"), dict) else {}
    clean_progress = {}
    for qid, obj in progress.items():
        if isinstance(qid, str) and isinstance(obj, dict):
            clean_obj = {}
            for k, v in obj.items():
                if not isinstance(k, str):
                    continue
                try:
                    clean_obj[k] = int(v or 0)
                except (TypeError, ValueError):
                    clean_obj[k] = 0
            clean_progress[qid] = clean_obj
    return {"active": active, "completed": completed, "progress": clean_progress}


# ----- pricing -----

def upgrade_price(profile, upgrade_id):
    if ":" in upgrade_id:
        branch_id, sep, lvl = upgrade_id.partition(":")
        level = int(lvl)
        if not tier_exists(branch_id, level):
            return None
        lvlkey = "%s:%d" % (branch_id, level)
        if (profile or {}).get("levels", {}).get(lvlkey):
            return None
        return tier_cost(branch_id, level)
    branch_id = upgrade_id
    b = _branch(branch_id)
    if not b:
        return None
    purchased = 0
    levels = profile.get("levels") if profile else {}
    for t in b.get("tiers", []):
        lvl = int(t.get("level", 0))
        if levels.get("%s:%d" % (branch_id, lvl)):
            purchased = max(purchased, lvl)
    next_lvl = purchased + 1
    if next_lvl > len(b.get("tiers", [])):
        return None
    if not tier_exists(branch_id, next_lvl):
        return None
    return tier_cost(branch_id, next_lvl)


def meta_stat_totals(profile):
    totals = {"max_hp": 0.0, "damage": 0.0, "speed": 0.0, "luck": 0.0, "armor": 0.0, "crit": 0.0, "lantern": 0.0}
    levels = (profile or {}).get("levels") or {}
    for key, purchased in levels.items():
        if not purchased:
            continue
        branch_id, sep, lvl = key.partition(":")
        stat = stat_for_tier(branch_id, int(lvl))
        if stat:
            bonus = tier_bonus(branch_id, int(lvl))
            totals[stat] = totals.get(stat, 0.0) + bonus
    return totals


def meta_special_effects(profile):
    levels = (profile or {}).get("levels") or {}
    effects = {
        "heal_on_floor_pct": 0.0, "melee_knockback_add": 0.0,
        "dash_cooldown_sub": 0.0, "dash_iframes_add": 0.0,
        "essence_drop_mult": 1.0, "shop_price_mult": 1.0,
        "lantern_radius_add": 0.0, "dot_weakness": 0.0, "burning_dot_weakness": 0.0,
    }
    for key, purchased in levels.items():
        if not purchased:
            continue
        branch_id, sep, lvl = key.partition(":")
        t = _tier_def(branch_id, int(lvl))
        if not t:
            continue
        if branch_id == "vitality" and int(lvl) == 3:
            effects["heal_on_floor_pct"] += 8.0
        if branch_id == "vitality" and int(lvl) == 4:
            effects["heal_on_floor_pct"] += 10.0
        if branch_id == "might" and int(lvl) == 2:
            effects["crit_add"] = effects.get("crit_add", 0.0) + 0.01
        if branch_id == "might" and int(lvl) == 3:
            effects["melee_knockback_add"] += 30.0
        if branch_id == "might" and int(lvl) == 4:
            effects["melee_knockback_add"] += 30.0
        if branch_id == "agility" and int(lvl) == 2:
            effects["dash_cooldown_sub"] += 0.08
        if branch_id == "agility" and int(lvl) == 3:
            effects["dash_cooldown_sub"] += 0.12
            effects["dash_iframes_add"] += 0.03
        if branch_id == "agility" and int(lvl) == 4:
            effects["dash_cooldown_sub"] += 0.04
            effects["dash_iframes_add"] += 0.02
        if branch_id == "fortune" and int(lvl) == 2:
            effects["essence_drop_mult"] *= 1.25
        if branch_id == "fortune" and int(lvl) == 3:
            effects["essence_drop_mult"] *= 1.20
            effects["shop_price_mult"] *= 0.88
        if branch_id == "fortune" and int(lvl) == 4:
            effects["essence_drop_mult"] *= 1.12
            effects["shop_price_mult"] *= 0.82
        if branch_id == "lantern" and int(lvl) == 2:
            effects["lantern_fog_reveal_add"] = effects.get("lantern_fog_reveal_add", 0) + 1
        if branch_id == "lantern" and int(lvl) == 3:
            effects["burning_dot_weakness"] += 0.20
        if branch_id == "lantern" and int(lvl) == 4:
            effects["dot_weakness"] += 0.15
    return effects


def purchase(profile, upgrade_id):
    if ":" not in upgrade_id:
        return False
    branch_id, sep, lvl = upgrade_id.partition(":")
    level = int(lvl)
    if not tier_exists(branch_id, level):
        return False
    lvlkey = "%s:%d" % (branch_id, level)
    if (profile or {}).get("levels", {}).get(lvlkey):
        return False
    for prereq in tier_prereqs(branch_id, level):
        if not (profile or {}).get("levels", {}).get(prereq):
            return False
    price = tier_cost(branch_id, level)
    if price is None:
        return False
    essence = int(profile.get("essence", 0))
    if essence < price:
        return False
    profile["essence"] = essence - price
    profile.setdefault("levels", {})[lvlkey] = 1
    return True


def respec(profile):
    cost = respec_cost()
    essence = int(profile.get("essence", 0))
    if essence < cost:
        return False
    refund = essence_spent_on_tree(profile) // 2
    profile["essence"] = essence - cost + refund
    profile["levels"] = {}
    return True


def essence_spent_on_tree(profile):
    levels = (profile or {}).get("levels") or {}
    total = 0
    for key, purchased in levels.items():
        if not purchased:
            continue
        branch_id, sep, lvl = key.partition(":")
        cost = tier_cost(branch_id, int(lvl))
        if cost:
            total += cost
    return total


def tree_state(profile):
    rows = []
    for branch in meta_tree_data().get("branches", []):
        bid = branch["id"]
        for tier in branch.get("tiers", []):
            lvl = int(tier.get("level", 0))
            lvlkey = "%s:%d" % (bid, lvl)
            levels = (profile or {}).get("levels", {})
            owned = bool(levels.get(lvlkey))
            prerequisites = tier_prereqs(bid, lvl)
            prereq_missing = any(not levels.get(p) for p in prerequisites)
            cost = tier_cost(bid, lvl)
            essence = int((profile or {}).get("essence", 0))
            affordable = (not owned) and cost is not None and essence >= cost and not prereq_missing
            rows.append({
                "branch_id": bid, "branch_name": branch.get("name", bid),
                "branch_color": branch.get("color", [246, 242, 232]),
                "level": lvl, "max_level": len(branch.get("tiers", [])),
                "label": tier.get("label", ""), "desc": tier.get("desc", ""),
                "stat": tier.get("stat"), "bonus": tier.get("bonus"),
                "cost": cost, "owned": owned,
                "prerequisites": prerequisites, "prereq_missing": prereq_missing,
                "affordable": affordable, "essence": essence,
            })
    return rows


# ----- persistence -----

def save_profile(profile, path=None, slot_name=None):
    """Write the profile. Returns the path written (or None on failure).

    *slot_name* (default None) selects a named save slot:
    'default' writes to save.json, 'autosave' to save_autosave.json,
    or a custom name to save_<name>.json. When slot_name is given,
    path is ignored. For backward compatibility, path can still be
    passed positionally.
    """
    if slot_name:
        target = _slot_path(slot_name)
    else:
        target = Path(path) if path else DEFAULT_SAVE_PATH
    payload = {
        "version": SAVE_VERSION,
        "meta": _norm_meta(profile.get("meta", {})),
        "levels": _norm_levels(profile.get("levels", {})),
        "essence": int(profile.get("essence", 0)),
        "stats": profile.get("stats", {}),
        "run": profile.get("run"),
        "class_id": str(profile.get("class_id", "lantern_keeper") or "lantern_keeper"),
        "unlocks": _norm_unlocks(profile.get("unlocks", {})),
        "ascension": max(0, int(profile.get("ascension", 0) or 0)),
        "unlocked_classes": _norm_unlocked_classes(profile.get("unlocked_classes", ["lantern_keeper"])),
        "unlocked_ascension": max(0, int(profile.get("unlocked_ascension", 0) or 0)),
        "settings": _settings_norm(profile.get("settings", {})),
        "save_slots": profile.get("save_slots", {}),
        "autosave": profile.get("autosave", {}),
        "run_history": profile.get("run_history", []),
        "codex": profile.get("codex", {}),
        "bestiary": profile.get("bestiary", {}),
        "quests": _norm_quests(profile.get("quests", {})),
    }
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = Path(str(target) + ".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp, target)
        bak = Path(str(target) + ".bak")
        try:
            shutil.copy2(target, bak)
        except OSError:
            pass
        return target
    except OSError:
        return None


def _recover_from_bak(target):
    """Try to restore target from its .bak file. Returns True on success."""
    bak = Path(str(target) + ".bak")
    if not bak.is_file():
        return False
    try:
        shutil.copy2(bak, target)
        return True
    except OSError:
        return False


def load_profile(path=None):
    """Load a profile, migrating or resetting anything unusable.  Never raises."""
    target = Path(path) if path else DEFAULT_SAVE_PATH
    profile = default_profile()
    notes = []
    try:
        with open(target, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except FileNotFoundError:
        notes.append("fresh profile (no save.json)")
        return profile, notes
    except (OSError, json.JSONDecodeError) as exc:
        # --- corrupted-save recovery: try .bak ---
        bak = Path(str(target) + ".bak")
        if bak.exists():
            try:
                with open(bak, "r", encoding="utf-8") as fh:
                    raw = json.load(fh)
                notes.append("recovered from backup")
            except (OSError, json.JSONDecodeError):
                notes.append("save corrupted, .bak also invalid - starting fresh")
                return profile, notes
        else:
            notes.append("save corrupted, recovered fresh")
            return profile, notes

    if not isinstance(raw, dict):
        notes.append("save.json is not an object - starting fresh")
        return profile, notes

    version = raw.get("version")
    if version != SAVE_VERSION:
        notes.append("save version %r != %d - migrated" % (version, SAVE_VERSION))
        if version == 2:
            # v2->v3 migration: copy v2 fields, add save_slots + autosave defaults
            profile = default_profile()
            old_levels = raw.get("levels") or {}
            new_levels = {}
            migration_map = {
                "vitality": [("vitality", 1), ("vitality", 2), ("vitality", 3), ("vitality", 4)],
                "might": [("might", 1), ("might", 2), ("might", 3), ("might", 4)],
                "swiftness": [("agility", 1), ("agility", 2)],
                "fortune": [("fortune", 1), ("fortune", 2), ("fortune", 3), ("fortune", 4)],
                "armor": [("vitality", 1), ("vitality", 2)],
                "crit": [("might", 1), ("might", 2)],
            }
            essence = int(raw.get("essence", 0) or 0)
            migrated_essence = essence
            for old_id, dests in migration_map.items():
                old_lvl = int(old_levels.get(old_id, 0) or 0)
                for dest_bid, dest_lvl in dests:
                    if old_lvl >= dest_lvl:
                        new_levels["%s:%d" % (dest_bid, dest_lvl)] = 1
                        migrated_essence -= tier_cost(dest_bid, dest_lvl) or 0
            if migrated_essence < 0:
                migrated_essence = 0
            profile["essence"] = migrated_essence
            profile["levels"] = new_levels
            if isinstance(raw.get("stats"), dict):
                for key in ("runs", "best_floor", "kills"):
                    try:
                        profile["stats"][key] = int(raw["stats"].get(key, 0) or 0)
                    except (TypeError, ValueError):
                        profile["stats"][key] = 0
            run = raw.get("run")
            if isinstance(run, dict):
                try:
                    profile["run"] = {"seed": int(run.get("seed", 0)), "floor": int(run.get("floor", 1)), "biome": str(run.get("biome", ""))}
                except (TypeError, ValueError):
                    profile["run"] = None
            # fall through to v2/v3 common load

        # --- v2/v3 common load ---
        if isinstance(raw.get("meta"), dict):
            profile["meta"] = _norm_meta(raw["meta"])
        if isinstance(raw.get("levels"), dict):
            profile["levels"] = _norm_levels(raw["levels"])
        try:
            profile["essence"] = int(raw.get("essence", 0) or 0)
        except (TypeError, ValueError):
            profile["essence"] = 0
        if isinstance(raw.get("stats"), dict):
            for key in ("runs", "best_floor", "kills"):
                try:
                    profile["stats"][key] = int(raw["stats"].get(key, 0) or 0)
                except (TypeError, ValueError):
                    profile["stats"][key] = 0
        run = raw.get("run")
        if isinstance(run, dict):
            try:
                profile["run"] = {"seed": int(run.get("seed", 0)), "floor": int(run.get("floor", 1)), "biome": str(run.get("biome", ""))}
            except (TypeError, ValueError):
                profile["run"] = None
        try:
            profile["class_id"] = str(raw.get("class_id", "lantern_keeper") or "lantern_keeper")
        except (TypeError, ValueError):
            profile["class_id"] = "lantern_keeper"
        if profile["class_id"] not in CLASS_DEFS:
            profile["class_id"] = "lantern_keeper"
        if isinstance(raw.get("unlocks"), dict):
            profile["unlocks"] = _norm_unlocks(raw["unlocks"])
        if isinstance(raw.get("unlocked_classes"), list):
            profile["unlocked_classes"] = _norm_unlocked_classes(raw["unlocked_classes"])
        try:
            profile["ascension"] = max(0, int(raw.get("ascension", 0) or 0))
        except (TypeError, ValueError):
            profile["ascension"] = 0
        try:
            profile["unlocked_ascension"] = max(0, int(raw.get("unlocked_ascension", 0) or 0))
        except (TypeError, ValueError):
            profile["unlocked_ascension"] = 0
        from ..ui.settings import normalize as _settings_normalize
        if "settings" in raw and isinstance(raw["settings"], dict):
            profile["settings"] = _settings_normalize(raw["settings"])
        else:
            profile["settings"] = _settings_normalize({})
        if isinstance(raw.get("save_slots"), dict):
            profile["save_slots"] = raw["save_slots"]
        else:
            profile["save_slots"] = default_profile()["save_slots"]
        if isinstance(raw.get("autosave"), dict):
            profile["autosave"] = raw["autosave"]
        else:
            profile["autosave"] = default_profile()["autosave"]
        if isinstance(raw.get("run_history"), list):
            profile["run_history"] = raw["run_history"]
        else:
            profile["run_history"] = []
        if isinstance(raw.get("codex"), dict):
            profile["codex"] = raw["codex"]
        else:
            profile["codex"] = {}
        if isinstance(raw.get("bestiary"), dict):
            profile["bestiary"] = raw["bestiary"]
        else:
            profile["bestiary"] = {}
        profile["quests"] = _norm_quests(raw.get("quests"))
        return profile, notes

    # --- v3 native load ---
    if isinstance(raw.get("meta"), dict):
        profile["meta"] = _norm_meta(raw["meta"])
    if isinstance(raw.get("levels"), dict):
        profile["levels"] = _norm_levels(raw["levels"])
    try:
        profile["essence"] = int(raw.get("essence", 0) or 0)
    except (TypeError, ValueError):
        profile["essence"] = 0
    if isinstance(raw.get("stats"), dict):
        for key in ("runs", "best_floor", "kills"):
            try:
                profile["stats"][key] = int(raw["stats"].get(key, 0) or 0)
            except (TypeError, ValueError):
                profile["stats"][key] = 0
    run = raw.get("run")
    if isinstance(run, dict):
        try:
            profile["run"] = {"seed": int(run.get("seed", 0)), "floor": int(run.get("floor", 1)), "biome": str(run.get("biome", ""))}
        except (TypeError, ValueError):
            profile["run"] = None
    try:
        profile["class_id"] = str(raw.get("class_id", "lantern_keeper") or "lantern_keeper")
    except (TypeError, ValueError):
        profile["class_id"] = "lantern_keeper"
    if profile["class_id"] not in CLASS_DEFS:
        profile["class_id"] = "lantern_keeper"
    if isinstance(raw.get("unlocks"), dict):
        profile["unlocks"] = _norm_unlocks(raw["unlocks"])
    if isinstance(raw.get("unlocked_classes"), list):
        profile["unlocked_classes"] = _norm_unlocked_classes(raw["unlocked_classes"])
    try:
        profile["ascension"] = max(0, int(raw.get("ascension", 0) or 0))
    except (TypeError, ValueError):
        profile["ascension"] = 0
    try:
        profile["unlocked_ascension"] = max(0, int(raw.get("unlocked_ascension", 0) or 0))
    except (TypeError, ValueError):
        profile["unlocked_ascension"] = 0
    from ..ui.settings import normalize as _settings_normalize
    if "settings" in raw and isinstance(raw["settings"], dict):
        profile["settings"] = _settings_normalize(raw["settings"])
    else:
        profile["settings"] = _settings_normalize({})
    if isinstance(raw.get("save_slots"), dict):
        profile["save_slots"] = raw["save_slots"]
    else:
        profile["save_slots"] = default_profile()["save_slots"]
    if isinstance(raw.get("autosave"), dict):
        profile["autosave"] = raw["autosave"]
    else:
        profile["autosave"] = default_profile()["autosave"]
    if isinstance(raw.get("run_history"), list):
        profile["run_history"] = raw["run_history"]
    else:
        profile["run_history"] = []
    if isinstance(raw.get("codex"), dict):
        profile["codex"] = raw["codex"]
    else:
        profile["codex"] = {}
    if isinstance(raw.get("bestiary"), dict):
        profile["bestiary"] = raw["bestiary"]
    else:
        profile["bestiary"] = {}
    profile["quests"] = _norm_quests(raw.get("quests"))
    return profile, notes


def profile_bonuses(profile):
    return meta_stat_totals(profile)


# ----- P5.1 save slots -----

def save_slot(slot_name, profile):
    """Save profile to a named slot. Returns the path written."""
    safe_slot_name = _sanitize_slot_name(slot_name)
    path = _slot_path(safe_slot_name)
    profile.setdefault("save_slots", {})[safe_slot_name] = str(path)
    return save_profile(profile, path)


def load_slot(slot_name):
    """Load a named save slot. Returns (profile, notes) like load_profile().
    Falls back to the default slot if the named slot file is missing."""
    safe_slot_name = _sanitize_slot_name(slot_name)
    path = _slot_path(safe_slot_name)
    if not path.is_file():
        profile = default_profile()
        profile["save_slots"] = {"default": str(DEFAULT_SAVE_PATH), "autosave": str(PROJECT_ROOT / "save_autosave.json")}
        return profile, ["slot %r not found - fresh profile" % safe_slot_name]
    return load_profile(path)


def save_slot_autosave(profile):
    """Autosave the profile to the 'autosave' slot. Called on floor entry."""
    return save_slot("autosave", profile)


def list_saves():
    """Return a dict of slot_name -> metadata for all existing save slots."""
    import json as _json
    saves = {}

    def _record(path, slot_name):
        if not path.is_file():
            return
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = _json.load(fh)
        except (OSError, ValueError):
            return
        saves[slot_name] = {
            "version": data.get("version"),
            "essence": data.get("essence", 0),
            "stats": data.get("stats", {}),
        }

    _record(DEFAULT_SAVE_PATH, "default")
    _record(PROJECT_ROOT / "save_autosave.json", "autosave")

    for p in sorted(PROJECT_ROOT.glob("save_*.json")):
        name = p.stem
        if name == "save":
            slot_name = "default"
        elif name == "save_autosave":
            slot_name = "autosave"
        else:
            slot_name = name[len("save_") :]
        _record(p, slot_name)

    saves_dir = PROJECT_ROOT / "saves"
    if saves_dir.is_dir():
        for p in sorted(saves_dir.glob("save_*.json")):
            name = p.stem
            if name == "save":
                slot_name = "default"
            elif name == "save_autosave":
                slot_name = "autosave"
            else:
                slot_name = name[len("save_") :]
            _record(p, slot_name)

    return saves
