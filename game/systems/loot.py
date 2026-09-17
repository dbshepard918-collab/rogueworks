"""Loot: rarity rolls, affixes, item generation.  All draws from the world RNG."""

RARITIES = [
    {"id": "common", "name": "Common", "color": (217, 210, 197), "affixes": (0, 1), "power": 1.00},
    {"id": "uncommon", "name": "Uncommon", "color": (121, 176, 74), "affixes": (1, 1), "power": 1.10},
    {"id": "rare", "name": "Rare", "color": (31, 95, 128), "affixes": (1, 2), "power": 1.25},
    {"id": "epic", "name": "Epic", "color": (123, 79, 209), "affixes": (2, 2), "power": 1.40},
    {"id": "legendary", "name": "Legendary", "color": (232, 178, 60), "affixes": (2, 3), "power": 1.60},
]

RARITY_BY_ID = {r["id"]: r for r in RARITIES}


def rarity_weights(tier, luck):
    """Drop weights per rarity from item tier + player luck (GDD section 5)."""
    t = max(1, min(5, int(tier)))
    lk = max(0.0, float(luck))
    return [
        max(1.0, 62.0 - t * 7.0 - lk * 1.6),
        22.0 + t * 2.0 + lk * 1.2,
        9.0 + t * 3.0 + lk * 1.4,
        3.0 + t * 2.0 + lk * 0.9,
        0.6 + t * 1.3 + lk * 0.6,
    ]


def roll_rarity(rng, tier, luck):
    weights = rarity_weights(tier, luck)
    index = rng.weighted_index(weights)
    return RARITIES[max(0, min(len(RARITIES) - 1, index))]


def pick_base_item(content, rng, tier=None, slot=None, luck=0.0, unlocks=None):
    """Choose a base item, preferring the requested tier range.

    *unlocks* (optional) is a set/dict of item ids that have been seen before;
    unlocked items get a small weight bonus (P1.4).
    """
    unlock_set = unlocks if unlocks is not None else set()
    if isinstance(unlock_set, dict):
        unlock_set = set(k for k, v in unlock_set.items() if v)
    else:
        unlock_set = set(unlock_set)
    pool = []
    for item in content.items():
        if item.get("quest_only"):
            continue
        if slot is not None and item.get("slot") != slot:
            continue
        if tier is None:
            w = 1.0
        else:
            diff = abs(int(item.get("tier", 1)) - int(tier))
            if diff > 2:
                continue
            w = 1.0 / (1.0 + diff * 1.4)
        if item.get("id") in unlock_set:
            w *= 1.25
        pool.append((item, w))
    if not pool:
        for item in content.items():
            if item.get("quest_only"):
                continue
            if slot is None or item.get("slot") == slot:
                pool.append((item, 1.0))
    if not pool:
        return None
    return rng.weighted(pool)


def roll_affixes(content, rng, item_tier, rarity):
    low, high = rarity["affixes"]
    if high <= 0:
        return []
    count = rng.randint(low, high)
    if count <= 0:
        return []
    pool = []
    for affix in content.affixes():
        if int(affix.get("tier_min", 1)) <= item_tier <= int(affix.get("tier_max", 5)):
            pool.append((affix, float(affix.get("weight", 1) or 1)))
    if not pool:
        pool = [(affix, float(affix.get("weight", 1) or 1)) for affix in content.affixes()]
    chosen = []
    used = set()
    guard = 0
    while len(chosen) < count and pool and guard < 40:
        guard += 1
        affix = rng.weighted(pool)
        if affix is None:
            break
        if affix.get("id") in used:
            pool = [(a, w) for a, w in pool if a.get("id") != affix.get("id")]
            continue
        used.add(affix.get("id"))
        chosen.append(affix)
    return chosen


def display_name(item):
    base = item.get("name", item.get("id", "item"))
    affixes = item.get("affixes") or []
    if not affixes:
        return base
    parts = []
    prefix = None
    for affix in affixes:
        name = str(affix.get("name", ""))
        if name.startswith("of "):
            parts.append(name)
        elif prefix is None:
            prefix = name
    out = ("%s %s" % (prefix, base)) if prefix else base
    if parts:
        out = out + " " + " ".join(parts)
    return out


def item_stat_summary(item):
    """Flatten base effect + affixes into one stat map."""
    effects = dict(item.get("effect") or {})
    for affix in item.get("affixes") or []:
        for key, value in (affix.get("effect") or {}).items():
            effects[key] = effects.get(key, 0.0) + value
    return effects


def make_item(content, rng, tier=1, luck=0.0, slot=None, force_rarity=None, unlocks=None):
    """Roll a complete item dict: base + rarity + affixes + power scaling."""
    tier = max(1, min(5, int(tier)))
    base = pick_base_item(content, rng, tier=tier, slot=slot, luck=luck, unlocks=unlocks)
    if base is None:
        return None
    rarity = RARITY_BY_ID.get(force_rarity) or roll_rarity(rng, tier, luck)
    item = {
        "id": base.get("id"),
        "name": base.get("name", base.get("id")),
        "slot": base.get("slot", "trinket"),
        "tier": int(base.get("tier", tier)),
        "effect": dict(base.get("effect") or {}),
        "value": int(base.get("value", 10)),
        "sprite": base.get("sprite", "item_%s" % base.get("id")),
        "flavor": base.get("flavor", ""),
    }
    if rarity["power"] != 1.0:
        scaled = {}
        for key, value in item["effect"].items():
            if key == "crit":
                scaled[key] = round(float(value) * rarity["power"], 4)
            elif key in ("speed",):
                scaled[key] = round(float(value) * (1.0 + (rarity["power"] - 1.0) * 0.6), 3)
            else:
                scaled[key] = max(1.0, round(float(value) * rarity["power"], 2))
        item["effect"] = scaled
    item["rarity"] = rarity["id"]
    item["rarity_name"] = rarity["name"]
    item["rarity_color"] = list(rarity["color"])
    item["affixes"] = [dict(a) for a in roll_affixes(content, rng, item["tier"], rarity)]
    item["display"] = display_name(item)
    item["value"] = int(item["value"] * (1.0 + 0.35 * RARITIES.index(rarity)))
    return item


def tier_for_floor(floor, luck=0.0):
    """Item tier band for a floor, nudged upward by luck."""
    base = 1 + int((int(floor) - 1) / 3.0)
    if luck > 6:
        base += 1
    return max(1, min(5, base))


def is_upgrade(player, item):
    """GDD: auto-pickup only when the slot is empty or the tier is higher."""
    slot = item.get("slot")
    if slot == "consumable":
        return len(player.consumables) < len(player.consumables) + 99  # always take consumables
    current = player.equipment.get(slot)
    if current is None:
        return True
    return int(item.get("tier", 1)) > int(current.get("tier", 1))


def rarity_colour(item):
    rarity = RARITY_BY_ID.get(item.get("rarity", "common"))
    return tuple(rarity["color"]) if rarity else (217, 210, 197)
