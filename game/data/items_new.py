"""Generate 77 new items for P5.5 content volume and write to items.json."""
import json
import copy

# Load existing data
with open('game/data/items.json') as f:
    items_data = json.load(f)
with open('assets/atlas/items.json') as f:
    atlas_data = json.load(f)

existing_ids = {e['id'] for e in items_data['entries']}
existing_sprites = set(atlas_data['frames'].keys())
existing_uniques = {e.get('unique') for e in items_data['entries'] if e.get('unique')}

print(f"Existing entries: {len(items_data['entries'])}")
print(f"Existing uniques: {existing_uniques}")
print(f"Atlas frames: {len(atlas_data['frames'])}")

# Sprite coordinate generator: arrange in a grid starting after existing entries
# Find max x in atlas to start new entries
max_x = 0
max_y = 0
for coords in atlas_data['frames'].values():
    x, y, w, h = coords
    max_x = max(max_x, x)
    max_y = max(max_y, y)

# Grid is 32px tiles
tile = 32
cols = (max_x // tile) + 3  # leave some room
# Start after existing content
start_col = (max_x // tile) + 2
start_row = (max_y // tile)

sprite_counter = 0
def next_sprite():
    global sprite_counter
    col = (start_col + sprite_counter) % 16
    row = start_row + (start_col + sprite_counter) // 16
    sprite_counter += 1
    name = f"item_gen_{sprite_counter:03d}"
    coords = [col * tile, row * tile, tile, tile]
    atlas_data['frames'][name] = coords
    return name

# New unique legendary effects to add
new_uniques_list = [
    'frost_bite', 'storm_call', 'bone_crusader', 'void_step',
    'soul_harvest', 'molten_core', 'thorn_vine', 'gravity_weight',
    'shadow_veil', 'star_forge'
]

# Build 77 new items
new_items = []

def add_item(item_id, name, slot, tier, effect, value, flavor, sprite=None, unique=None, element=None):
    if sprite is None:
        sprite = next_sprite()
    item = {
        'id': item_id,
        'name': name,
        'slot': slot,
        'tier': tier,
        'effect': effect,
        'value': value,
        'sprite': sprite,
        'flavor': flavor,
    }
    if unique is not None:
        item['unique'] = unique
    if element is not None:
        item['element'] = element
    assert item_id not in existing_ids, f"Duplicate ID: {item_id}"
    assert sprite not in existing_sprites, f"Duplicate sprite: {sprite}"
    new_items.append(item)
    existing_ids.add(item_id)
    existing_sprites.add(sprite)

# === WEAPONS (target ~20 items) ===
# Tier 1 weapons
add_item('rusty_nail', 'Rusty Nail', 'weapon', 1, {'damage': 3}, 15, 'A thumbtack with ambitions.', 'item_rusty_nail')
add_item('short_stick', 'Short Stick', 'weapon', 1, {'damage': 2, 'speed': 0.1}, 12, 'Better than nothing, and lighter too.', 'item_short_stick')
add_item('hobble_blade', 'Hobble Blade', 'weapon', 1, {'damage': 4, 'speed': -0.1}, 16, 'Slow and heavy, like its owner.', 'item_hobble_blade')

# Tier 2 weapons
add_item('serrated_knife', 'Serrated Knife', 'weapon', 2, {'damage': 7, 'crit': 2}, 50, 'The edge is dishonest about its origin.', 'item_serrated_knife')
add_item('iron_hatchet', 'Iron Hatchet', 'weapon', 2, {'damage': 8, 'armor': 2}, 44, 'Sharp on both sides and on the conscience.', 'item_iron_hatchet')
add_item('weighted_club', 'Weighted Club', 'weapon', 2, {'damage': 9, 'speed': -0.15}, 42, 'The weight makes up for the wit.', 'item_weighted_club')
add_item('venom_dagger', 'Venom Dagger', 'weapon', 2, {'damage': 6, 'crit': 3}, 55, 'A scratch that itches for days.', 'item_venom_dagger')

# Tier 3 weapons
add_item('frost_bite_weapon', 'Frost Bite', 'weapon', 3, {'damage': 11, 'crit': 2}, 130, 'Each strike steals warmth from the wound.', 'item_frost_bite_weapon', unique='frost_bite', element='ice')
add_item('venom_stiletto', 'Venom Stiletto', 'weapon', 3, {'damage': 10, 'crit': 5}, 115, 'A needle that carries more than poison.', 'item_venom_stiletto')
add_item('obsidian_blade', 'Obsidian Blade', 'weapon', 3, {'damage': 12, 'armor': 3}, 125, 'Sharp enough to cut shadows.', 'item_obsidian_blade')
add_item('storm_call_weapon', 'Storm Call', 'weapon', 3, {'damage': 13, 'speed': 0.1}, 140, 'Thunder answers every swing.', 'item_storm_call_weapon', unique='storm_call', element='lightning')
add_item('skull_saw', 'Skull Saw', 'weapon', 3, {'damage': 10, 'crit': 3}, 108, 'Rotating blades and worse intentions.', 'item_skull_saw')

# Tier 4 weapons
add_item('star_forge_weapon', 'Star Forge', 'weapon', 4, {'damage': 17, 'crit': 8}, 320, 'Each critical builds toward something greater.', 'item_star_forge_weapon', unique='star_forge')
add_item('ice_reaver', 'Ice Reaver', 'weapon', 4, {'damage': 16, 'crit': 6, 'armor': 5}, 260, 'The cold lingers long after the cut.', 'item_ice_reaver', element='ice')
add_item('lightning_brand', 'Lightning Brand', 'weapon', 4, {'damage': 15, 'armor': 8}, 250, 'Zaps anything that gets too close.', 'item_lightning_brand', element='lightning')
add_item('shadow_cleaver', 'Shadow Cleaver', 'weapon', 4, {'damage': 18, 'crit': 4}, 280, 'It cuts through morale as well as flesh.', 'item_shadow_cleaver', element='shadow')
add_item('bone_maul', 'Bone Maul', 'weapon', 4, {'damage': 19, 'speed': -0.1}, 270, 'Forged from the femur of something enormous.', 'item_bone_maul')

# Tier 5 weapons (non-unique)
add_item('void_sting', 'Void Sting', 'weapon', 5, {'damage': 26, 'crit': 11}, 650, 'A wound from nowhere, healing nothing.', 'item_void_sting', element='shadow')
add_item('thunder_fork', 'Thunder Fork', 'weapon', 5, {'damage': 24, 'armor': 5}, 620, 'Forks of static electricity on every swing.', 'item_thunder_fork', element='lightning')
add_item('paladin_sword', 'Paladin Blade', 'weapon', 5, {'damage': 25, 'crit': 9, 'armor': 8}, 640, 'Blessed steel, unforgiving to the wicked.', 'item_paladin_sword', element='holy')

# === ARMOR (target ~20 items) ===
# Tier 1 armor
add_item('torn_shirt', 'Torn Shirt', 'armor', 1, {'armor': 2}, 10, 'Fashionable in a desperate sort of way.', 'item_torn_shirt')
add_item('leather_patch', 'Leather Patch', 'armor', 1, {'armor': 3}, 14, 'Held together by thread and stubbornness.', 'item_leather_patch')
add_item('rag_armor', 'Rag Armor', 'armor', 1, {'armor': 1, 'max_hp': 5}, 11, 'It is barely armor and barely a shirt.', 'item_rag_armor')

# Tier 2 armor
add_item('chain_patch', 'Chain Patch', 'armor', 2, {'armor': 6, 'damage': 4}, 46, 'Rusty links sewn over a worn tunic.', 'item_chain_patch')
add_item('iron_vambraces', 'Iron Vambraces', 'armor', 2, {'armor': 7}, 44, 'Protects the forearms, nothing more.', 'item_iron_vambraces')
add_item('leather_chest', 'Leather Chest', 'armor', 2, {'armor': 8, 'max_hp': 8}, 48, 'Stitched tight, hides what it defends.', 'item_leather_chest')
add_item('iron_greaves', 'Iron Greaves', 'armor', 2, {'armor': 9, 'speed': -0.1}, 47, 'Heavy steps, heavy protection.', 'item_iron_greaves')

# Tier 3 armor
add_item('bone_crusader', 'Bone Crusader', 'armor', 3, {'armor': 10, 'max_hp': 15}, 135, 'Each kill feeds the armor with calcium.', 'item_bone_crusader_armor', unique='bone_crusader')
add_item('thorn_vine_armor', 'Thorn Vine', 'armor', 3, {'armor': 9, 'damage': 3}, 125, 'Attackers find themselves equally wounded.', 'item_thorn_vine_armor', unique='thorn_vine')
add_item('molten_core_armor', 'Molten Core', 'armor', 3, {'armor': 11, 'crit': 2}, 130, 'Absorbs fire and returns it tenfold.', 'item_molten_core_armor', unique='molten_core', element='fire')
add_item('shadow_robes', 'Shadow Robes', 'armor', 3, {'armor': 8, 'speed': 0.15, 'damage': 5}, 122, 'Worn by those who have nothing to hide.', 'item_shadow_robes', element='shadow')
add_item('crystal_plate', 'Crystal Plate', 'armor', 3, {'armor': 12, 'max_hp': 12}, 128, 'Fragile-looking but impossibly hard.', 'item_crystal_plate')

# Tier 4 armor
add_item('void_step_armor', 'Void Step', 'armor', 4, {'armor': 14, 'speed': 0.2}, 280, 'Phases through attacks when you dodge.', 'item_void_step_armor', unique='void_step')
add_item('shadow_veil_armor', 'Shadow Veil', 'armor', 4, {'armor': 15, 'damage': 4}, 260, 'Grants a chance to slip past blows entirely.', 'item_shadow_veil_armor', unique='shadow_veil', element='shadow')
add_item('gravity_weight_armor', 'Gravity Weight', 'armor', 4, {'armor': 16, 'speed': 0.15, 'max_hp': 20}, 290, 'Heavy when you are strong, light when you are not.', 'item_gravity_weight_armor', unique='gravity_weight')
add_item('dragon_scale_mail', 'Dragon Scale Mail', 'armor', 4, {'armor': 17, 'crit': 3}, 300, 'Scales that shed fire like water.', 'item_dragon_scale_mail', element='fire')
add_item('warden_spaulders', 'Warden Spaulders', 'armor', 4, {'armor': 13, 'max_hp': 20, 'damage': 8}, 255, 'The Warden left them behind for good reason.', 'item_warden_spaulders')

# Tier 5 armor (non-unique)
add_item('abyss_shroud', 'Abyss Shroud', 'armor', 5, {'armor': 22, 'max_hp': 40, 'damage': 10}, 520, 'Woven from the darkness between stars.', 'item_abyss_shroud', element='shadow')
add_item('celestial_plate', 'Celestial Plate', 'armor', 5, {'armor': 20, 'crit': 6, 'armor': 20}, 530, 'Blessed by forgotten gods.', 'item_celestial_plate', element='holy')
add_item('void_tunic', 'Void Tunic', 'armor', 5, {'armor': 21, 'speed': 0.2, 'max_hp': 35}, 510, 'Existence is optional while you wear it.', 'item_void_tunic', element='shadow')
add_item('fire_plate', 'Fireplate Armor', 'armor', 5, {'armor': 19, 'damage': 8, 'crit': 5}, 500, 'Burns on contact with anything alive.', 'item_fire_plate', element='fire')

# === TRINKETS (target ~20 items) ===
# Tier 1 trinkets
add_item('copper_ring', 'Copper Ring', 'trinket', 1, {'luck': 1}, 10, 'Cheap metal, cheap luck.', 'item_copper_ring')
add_item('iron_chip', 'Iron Chip', 'trinket', 1, {'armor': 3}, 11, 'A shard of something bigger.', 'item_iron_chip')
add_item('string_bead', 'String Bead', 'trinket', 1, {'crit': 1, 'luck': 1}, 12, 'Strung together with hope and thread.', 'item_string_bead')

# Tier 2 trinkets
add_item('silver_earring', 'Silver Earring', 'trinket', 2, {'crit': 2, 'luck': 2}, 42, 'Subtle shimmer catches the eye.', 'item_silver_earring')
add_item('amber_amulet', 'Amber Amulet', 'trinket', 2, {'luck': 3, 'armor': 4}, 44, 'Petrified resin holding ancient light.', 'item_amber_amulet')
add_item('iron_spur', 'Iron Spur', 'trinket', 2, {'speed': 0.1, 'crit': 2}, 46, 'Keeps you moving forward.', 'item_iron_spur')
add_item('dark_crystal', 'Dark Crystal', 'trinket', 2, {'damage': 4, 'luck': 2}, 48, 'Absorbs light and radiates malice.', 'item_dark_crystal')

# Tier 3 trinkets
add_item('void_step_trinket', 'Void Step', 'trinket', 3, {'speed': 0.2, 'luck': 3}, 115, 'Phase through walls in a pinch.', 'item_void_step_trinket', unique='void_step')
add_item('soul_harvest', 'Soul Harvest', 'trinket', 3, {'crit': 4, 'max_hp': 10}, 125, 'Every kill feeds your essence.', 'item_soul_harvest_trinket', unique='soul_harvest')
add_item('gravity_weight_trinket', 'Gravity Weight', 'trinket', 3, {'luck': 4, 'speed': 0.1, 'max_hp': 12}, 120, 'Binds to the body, accelerates the will.', 'item_gravity_weight_trinket', unique='gravity_weight')
add_item('frost_shard', 'Frost Shard', 'trinket', 3, {'damage': 5, 'armor': 6, 'crit': 2}, 118, 'Cracks with cold on every impact.', 'item_frost_shard', element='ice')
add_item('lightning_coil', 'Lightning Coil', 'trinket', 3, {'crit': 5, 'damage': 4}, 122, 'Stores static like a trapped storm.', 'item_lightning_coil', element='lightning')
add_item('shadow_essence', 'Shadow Essence', 'trinket', 3, {'luck': 5, 'damage': 5}, 115, 'Darkness concentrates in small spaces.', 'item_shadow_essence', element='shadow')

# Tier 4 trinkets
add_item('star_forge_trinket', 'Star Forge', 'trinket', 4, {'crit': 8, 'luck': 4}, 310, 'Each critical amplifies the next.', 'item_star_forge_trinket', unique='star_forge')
add_item('shadow_veil_trinket', 'Shadow Veil', 'trinket', 4, {'luck': 6, 'armor': 10, 'crit': 3}, 280, 'Shadows guard the bearer.', 'item_shadow_veil_trinket', unique='shadow_veil', element='shadow')
add_item('frost_bite_trinket', 'Frost Bite', 'trinket', 4, {'damage': 8, 'armor': 8, 'speed': 0.1}, 270, 'The cold never truly leaves.', 'item_frost_bite_trinket', unique='frost_bite', element='ice')
add_item('molten_core_trinket', 'Molten Core', 'trinket', 4, {'damage': 7, 'crit': 5, 'max_hp': 15}, 290, 'Burns away weakness.', 'item_molten_core_trinket', unique='molten_core', element='fire')
add_item('storm_call_trinket', 'Storm Call', 'trinket', 4, {'crit': 6, 'luck': 4, 'armor': 8}, 275, 'Thunder follows the bearer.', 'item_storm_call_trinket', unique='storm_call', element='lightning')
add_item('bone_crusader_trinket', 'Bone Crusader', 'trinket', 4, {'armor': 10, 'max_hp': 18, 'luck': 3}, 285, 'The dead strengthen the living.', 'item_bone_crusader_trinket', unique='bone_crusader')
add_item('thorn_vine_trinket', 'Thorn Vine', 'trinket', 4, {'armor': 8, 'damage': 5, 'crit': 4}, 265, 'Retaliation is the best defense.', 'item_thorn_vine_trinket', unique='thorn_vine')

# Tier 5 trinkets (non-unique)
add_item('void_lantern_new', 'Void Lantern', 'trinket', 5, {'luck': 8, 'crit': 7, 'armor': 12}, 480, 'Illuminates what others cannot find.', 'item_void_lantern_new', element='shadow')
add_item('fate_dice', 'Fate Dice', 'trinket', 5, {'luck': 10, 'crit': 5, 'armor': 15}, 490, 'The universe rolls for you now.', 'item_fate_dice')
add_item('storm_ring', 'Storm Ring', 'trinket', 5, {'damage': 15, 'crit': 8, 'luck': 5}, 470, 'Thunder in every heartbeat.', 'item_storm_ring', element='lightning')
add_item('life_seed', 'Life Seed', 'trinket', 5, {'max_hp': 80, 'luck': 6, 'armor': 15}, 500, 'Bears fruit from the darkest soil.', 'item_life_seed')
add_item('chaos_shard', 'Chaos Shard', 'trinket', 5, {'damage': 12, 'crit': 10, 'luck': 5}, 495, 'Order shatters around the bearer.', 'item_chaos_shard')

# === CONSUMABLES (target ~17 items) ===
# Tier 1 consumables
add_item('bandage', 'Bandage', 'consumable', 1, {'max_hp': 10}, 8, 'Clean cloth, rough press.', 'item_bandage')
add_item('salt_water', 'Salt Water', 'consumable', 1, {'armor': 2}, 7, 'Stings but disinfects.', 'item_salt_water')
add_item('bitter_root', 'Bitter Root', 'consumable', 1, {'damage': 2}, 7, 'Mouth-puckering, spirit-quickening.', 'item_bitter_root')
add_item('dust_knuckle', 'Dust Knuckle', 'consumable', 1, {'speed': 0.1}, 8, 'A punch of powdered speed.', 'item_dust_knuckle')

# Tier 2 consumables
add_item('iron_brew', 'Iron Brew', 'consumable', 2, {'armor': 6, 'damage': 5}, 42, 'Tastes like metal and motivation.', 'item_iron_brew')
add_item('swift_root', 'Swift Root', 'consumable', 2, {'speed': 0.2}, 38, 'Roots that run faster than the drinker.', 'item_swift_root')
add_item('shield_brew', 'Shield Brew', 'consumable', 2, {'armor': 8}, 40, 'Hardens the skin momentarily.', 'item_shield_brew')
add_item('crit_draught', 'Crit Draught', 'consumable', 2, {'crit': 5}, 44, 'Eyes sharpen and edges glow.', 'item_crit_draught')

# Tier 3 consumables
add_item('frost_tonic', 'Frost Tonic', 'consumable', 3, {'damage': 6, 'armor': 8}, 108, 'Burns cold down to the marrow.', 'item_frost_tonic', element='ice')
add_item('soul_tonic', 'Soul Tonic', 'consumable', 3, {'max_hp': 40, 'luck': 3}, 110, 'Distilled from residual spirit energy.', 'item_soul_tonic')
add_item('thunder_drop', 'Thunder Drop', 'consumable', 3, {'crit': 8, 'speed': 0.1}, 112, 'Zaps the system into alertness.', 'item_thunder_drop', element='lightning')
add_item('healing_mist', 'Healing Mist', 'consumable', 3, {'max_hp': 50}, 105, 'A fog that mends what it touches.', 'item_healing_mist')
add_item('iron_will', 'Iron Will', 'consumable', 3, {'armor': 12, 'max_hp': 20}, 115, 'Steel resolves meet flesh and hold.', 'item_iron_will')

# Tier 4 consumables
add_item('void_elixir', 'Void Elixir', 'consumable', 4, {'max_hp': 100, 'crit': 6}, 220, 'Nothingness made drinkable.', 'item_void_elixir', element='shadow')
add_item('storm_potion', 'Storm Potion', 'consumable', 4, {'damage': 12, 'crit': 10}, 230, 'Lightning in a bottle, handle with care.', 'item_storm_potion', element='lightning')
add_item('molten_elixir', 'Molten Elixir', 'consumable', 4, {'armor': 15, 'damage': 10}, 225, 'Liquid fire for the bloodstream.', 'item_molten_elixir', element='fire')
add_item('shadow_brew', 'Shadow Brew', 'consumable', 4, {'luck': 8, 'speed': 0.15}, 215, 'Darkness settles into the veins.', 'item_shadow_brew', element='shadow')
add_item('frost_elixir', 'Frost Elixir', 'consumable', 4, {'damage': 9, 'armor': 12, 'crit': 4}, 220, 'Freezes the blood and wakes the senses.', 'item_frost_elixir', element='ice')
add_item('bone_meal', 'Bone Meal', 'consumable', 4, {'max_hp': 60, 'armor': 10}, 210, 'Powdered calcium that rebuilds the frame.', 'item_bone_meal')

# Tier 5 consumables (non-unique)
add_item('ultimate_draught', 'Ultimate Draught', 'consumable', 5, {'max_hp': 200, 'armor': 25}, 420, 'The last drop from the gods own flask.', 'item_ultimate_draught')
add_item('chaos_brew', 'Chaos Brew', 'consumable', 5, {'damage': 20, 'crit': 12, 'armor': 15}, 440, 'Pure entropy in liquid form.', 'item_chaos_brew', element='shadow')
add_item('divine_fountain', 'Divine Fountain', 'consumable', 5, {'max_hp': 180, 'armor': 22, 'luck': 5}, 430, 'Water from a well that never runs dry.', 'item_divine_fountain', element='holy')
add_item('inferno_potion', 'Inferno Potion', 'consumable', 5, {'damage': 22, 'armor': 18}, 410, 'The entire fire of a dying star.', 'item_inferno_potion', element='fire')
add_item('void_walker', 'Void Walker', 'consumable', 5, {'max_hp': 150, 'speed': 0.3, 'crit': 8}, 450, 'Step between dimensions for a fleeting moment.', 'item_void_walker', element='shadow')

# === Write updated items.json ===
items_data['entries'].extend(new_items)
print(f"\nTotal items after addition: {len(items_data['entries'])}")
print(f"New items added: {len(new_items)}")

# Write items.json
with open('game/data/items.json', 'w') as f:
    json.dump(items_data, f, indent=2)

# Write updated atlas
with open('assets/atlas/items.json', 'w') as f:
    json.dump(atlas_data, f, indent=2)

print("\nWritten items.json with", len(items_data['entries']), "entries")

print("\nDone! Files written successfully.")