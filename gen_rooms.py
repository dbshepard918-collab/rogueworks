import json
import random
from collections import Counter

# Load existing rooms.json
with open("game/data/rooms.json") as f:
    data = json.load(f)

entries = data["entries"]
existing_ids = {e["id"] for e in entries}

# Ossuary-specific props from task description
ossuary_props = [
    "prop_brazier", "prop_crystal", "prop_chain", "prop_candles", "prop_pillar",
    "prop_bones", "prop_urn", "prop_sarcophagus", "prop_water_pool", "prop_jelly",
    "prop_coral", "prop_anchor", "prop_shipwreck", "prop_tentacle", "prop_mussel"
]

# Biome-specific decorative props
catacombs_extra = ["prop_bones", "prop_sarcophagus", "prop_brazier", "prop_candles", "prop_pillar", "prop_rubble", "prop_chest", "prop_urn", "prop_chain", "prop_torch"]
ember_extra = ["prop_forge", "prop_anvil", "prop_lava_vent", "prop_pipes", "prop_rubble", "prop_chest", "prop_chain", "prop_crystal", "prop_sword", "prop_shield"]
drowned_extra = ["prop_water_pool", "prop_crystal", "prop_kelp", "prop_roots", "prop_pillar_drowned", "prop_coral", "prop_urn", "prop_rubble", "prop_jelly", "prop_candles"]

def rand_w(rng):
    return rng.randint(5, 24)

def rand_h(rng):
    return rng.randint(5, 24)

def pick_props(rng, props_list, min_count=1, max_count=4):
    n = rng.randint(min_count, min(max_count, len(props_list)))
    return rng.sample(props_list, n)

def make_unique_id(biome, kind, suffix, used_ids, existing_ids):
    room_id = f"{biome}_{kind}_{suffix}"
    counter = 1
    while room_id in used_ids or room_id in existing_ids:
        room_id = f"{biome}_{kind}_{suffix}_{counter}"
        counter += 1
    used_ids.add(room_id)
    return room_id

def generate_biome_rooms(biome_id, prop_pool, count=40, seed=42):
    rooms = []
    used_ids = set()
    rng = random.Random(hash(biome_id) + seed)
    
    # 2 Boss rooms (spawn_budget 20+)
    for i in range(2):
        rooms.append({
            "id": make_unique_id(biome_id, "boss", f"boss_{i+1}", used_ids, existing_ids),
            "biome": biome_id, "kind": "boss",
            "w": rng.randint(20, 24), "h": rng.randint(16, 20),
            "spawn_budget": 20 + rng.randint(0, 5),
            "props": pick_props(rng, prop_pool, 2, 3)
        })
    
    # 2 Entrance rooms
    for i in range(2):
        rooms.append({
            "id": make_unique_id(biome_id, "entrance", f"entrance_{i+1}", used_ids, existing_ids),
            "biome": biome_id, "kind": "entrance",
            "w": rng.randint(12, 16), "h": rng.randint(10, 14),
            "spawn_budget": 0,
            "props": pick_props(rng, prop_pool, 1, 2)
        })
    
    # 2 Shop rooms
    for i in range(2):
        rooms.append({
            "id": make_unique_id(biome_id, "shop", f"shop_{i+1}", used_ids, existing_ids),
            "biome": biome_id, "kind": "shop",
            "w": rng.randint(7, 9), "h": rng.randint(6, 8),
            "spawn_budget": 0,
            "props": ["prop_shop_stall"] + pick_props(rng, prop_pool, 1, 2)
        })
    
    # 2 Shrine rooms
    shrine_prop = "prop_shrine_drowned" if biome_id == "drowned_vaults" else "prop_shrine"
    for i in range(2):
        rooms.append({
            "id": make_unique_id(biome_id, "shrine", f"shrine_{i+1}", used_ids, existing_ids),
            "biome": biome_id, "kind": "shrine",
            "w": rng.randint(8, 10), "h": rng.randint(8, 10),
            "spawn_budget": 1,
            "props": [shrine_prop] + pick_props(rng, prop_pool, 1, 2)
        })
    
    # 3 Treasure rooms
    for i in range(3):
        rooms.append({
            "id": make_unique_id(biome_id, "treasure", f"treasure_{i+1}", used_ids, existing_ids),
            "biome": biome_id, "kind": "treasure",
            "w": rng.randint(8, 12), "h": rng.randint(8, 10),
            "spawn_budget": rng.randint(2, 4),
            "props": ["prop_chest", "prop_gold_pile"] + pick_props(rng, prop_pool, 1, 2)
        })
    
    # 2 Blacksmith rooms
    for i in range(2):
        rooms.append({
            "id": make_unique_id(biome_id, "blacksmith", f"blacksmith_{i+1}", used_ids, existing_ids),
            "biome": biome_id, "kind": "blacksmith",
            "w": rng.randint(9, 11), "h": rng.randint(8, 10),
            "spawn_budget": 0,
            "props": ["prop_anvil", "prop_hammer"] + pick_props(rng, prop_pool, 1, 2)
        })
    
    # 2 Gambling rooms
    for i in range(2):
        rooms.append({
            "id": make_unique_id(biome_id, "gambling", f"gambling_{i+1}", used_ids, existing_ids),
            "biome": biome_id, "kind": "gambling",
            "w": rng.randint(8, 10), "h": rng.randint(7, 9),
            "spawn_budget": 0,
            "props": ["prop_coffer", "prop_gold_pile"] + pick_props(rng, prop_pool, 1, 2)
        })
    
    # 2 Fountain rooms
    for i in range(2):
        rooms.append({
            "id": make_unique_id(biome_id, "fountain", f"fountain_{i+1}", used_ids, existing_ids),
            "biome": biome_id, "kind": "fountain",
            "w": rng.randint(7, 9), "h": rng.randint(7, 9),
            "spawn_budget": 0,
            "props": ["prop_fountain"]
        })
    
    # 3 Omen rooms
    for i in range(3):
        rooms.append({
            "id": make_unique_id(biome_id, "omen", f"omen_{i+1}", used_ids, existing_ids),
            "biome": biome_id, "kind": "omen",
            "w": rng.randint(7, 9), "h": rng.randint(7, 9),
            "spawn_budget": 0,
            "props": ["prop_eye"] + pick_props(rng, prop_pool, 1, 2)
        })
    
    # 3 Secret rooms
    walls = ["north", "east", "south", "west"]
    for i in range(3):
        rooms.append({
            "id": make_unique_id(biome_id, "secret", f"secret_{i+1}", used_ids, existing_ids),
            "biome": biome_id, "kind": "secret",
            "w": rng.randint(5, 8), "h": rng.randint(5, 7),
            "spawn_budget": 0,
            "props": pick_props(rng, prop_pool, 1, 2),
            "secret_wall": walls[i % len(walls)]
        })
    
    # Remaining rooms: combat + extra treasure variety
    remaining = count - len(rooms)
    for i in range(remaining):
        kind = rng.choice(["combat", "combat", "combat", "treasure", "combat", "treasure"])
        w = rng.randint(8, 22)
        h = rng.randint(8, 20)
        if kind == "combat":
            sb = rng.randint(4, 15)
            props = pick_props(rng, prop_pool, 2, 3)
        else:
            sb = rng.randint(2, 5)
            props = ["prop_chest", "prop_gold_pile"] + pick_props(rng, prop_pool, 1, 2)
        rooms.append({
            "id": make_unique_id(biome_id, kind, f"variety_{i+1}", used_ids, existing_ids),
            "biome": biome_id, "kind": kind,
            "w": w, "h": h, "spawn_budget": sb,
            "props": props
        })
    
    return rooms

# Generate all rooms
all_new_rooms = []

catacombs_rooms = generate_biome_rooms("catacombs", catacombs_extra, 40, seed=101)
all_new_rooms.extend(catacombs_rooms)
print(f"Catacombs: {len(catacombs_rooms)} rooms")

ember_rooms = generate_biome_rooms("ember_warrens", ember_extra, 40, seed=202)
all_new_rooms.extend(ember_rooms)
print(f"Ember Warrens: {len(ember_rooms)} rooms")

drowned_rooms = generate_biome_rooms("drowned_vaults", drowned_extra, 40, seed=303)
all_new_rooms.extend(drowned_rooms)
print(f"Drowned Vaults: {len(drowned_rooms)} rooms")

ossuary_rooms = generate_biome_rooms("ossuary", ossuary_props, 40, seed=404)
all_new_rooms.extend(ossuary_rooms)
print(f"Sunken Ossuary: {len(ossuary_rooms)} rooms")

print(f"\nTotal new rooms: {len(all_new_rooms)}")

# Validation
for biome in ["catacombs", "ember_warrens", "drowned_vaults", "ossuary"]:
    biome_rooms = [r for r in all_new_rooms if r["biome"] == biome]
    kind_counts = Counter(r["kind"] for r in biome_rooms)
    bosses = [r for r in biome_rooms if r["kind"] == "boss"]
    for b in bosses:
        assert b["spawn_budget"] >= 20, f"Boss {b['id']} spawn_budget too low"
    for r in biome_rooms:
        assert 5 <= r["w"] <= 24, f"{r['id']} w out of range"
        assert 5 <= r["h"] <= 24, f"{r['id']} h out of range"
    print(f"{biome}: {len(biome_rooms)} rooms, boss count={len(bosses)}, kinds={dict(kind_counts)}")

# Merge with existing entries
all_entries = entries + all_new_rooms

# Update the rooms.json
data["entries"] = all_entries

with open("game/data/rooms.json", "w") as f:
    json.dump(data, f, indent=2)

print(f"\nTotal entries in rooms.json: {len(all_entries)}")
print("Rooms written to game/data/rooms.json")
