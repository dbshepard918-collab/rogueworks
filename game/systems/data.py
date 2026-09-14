"""Content registry: loads game/data/*.json (owned by `lore`) to CONTRACTS.md section 4.

Two hard requirements:
  * a file that is MISSING entirely falls back to a built-in seed set embedded in
    this module and logs a warning - the game stays playable;
  * extra unknown fields are ignored, never fatal.

The built-in seed set uses the canonical frame names from assets/art_manifest.json
so that fallback content still renders real art once the atlases are packed.
"""

import json
from pathlib import Path

GAME_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = GAME_DIR / "data"

STAT_KEYS = ("damage", "armor", "max_hp", "speed", "luck", "crit")
SLOTS = ("weapon", "armor", "trinket", "consumable")
BEHAVIORS = ("chaser", "ranged", "ambusher", "brute", "summoner", "shielded", "teleporter", "charger", "splitter", "runner")
ROOM_KINDS = ("combat", "treasure", "shrine", "shop", "boss", "entrance", "secret",
                "gambling", "blacksmith", "fountain", "omen")

# ---------------------------------------------------------------------------
# Built-in seed content.  Only used when game/data/<file>.json is absent/empty.
# ---------------------------------------------------------------------------

_MONSTER_FIELDS = ("id", "name", "biome", "tier", "hp", "damage", "armor", "speed", "xp",
                   "weight", "behavior", "sprite", "status_on_hit")

_MONSTER_ROWS = [
    # catacombs
    ("bone_rat", "Bone Rat", "catacombs", 1, 14, 3, 0, 1.7, 4, 30, "chaser", "monster_bone_rat", None),
    ("ash_skeleton", "Ash Skeleton", "catacombs", 1, 26, 5, 1, 1.0, 6, 26, "chaser", "monster_ash_skeleton", None),
    ("grave_moth", "Grave Moth", "catacombs", 1, 12, 4, 0, 2.0, 5, 16, "ambusher", "monster_grave_moth", "slow"),
    ("ossuary_archer", "Ossuary Archer", "catacombs", 2, 18, 4, 0, 0.9, 7, 18, "ranged", "monster_ossuary_archer", None),
    ("putrid_ghoul", "Putrid Ghoul", "catacombs", 2, 30, 6, 1, 1.1, 8, 20, "chaser", "monster_putrid_ghoul", "poison"),
    ("crypt_crawler", "Crypt Crawler", "catacombs", 2, 22, 5, 1, 1.5, 8, 14, "ambusher", "monster_crypt_crawler", "poison"),
    ("tomb_lurker", "Tomb Lurker", "catacombs", 3, 34, 7, 2, 0.9, 11, 12, "ambusher", "monster_tomb_lurker", None),
    ("crypt_brute", "Crypt Brute", "catacombs", 3, 54, 10, 3, 0.55, 15, 10, "brute", "monster_crypt_brute", "slow"),
    ("skull_warden", "Skull Warden", "catacombs", 3, 40, 9, 3, 1.0, 14, 9, "chaser", "monster_skull_warden", None),
    ("bone_stalker", "Bone Stalker", "catacombs", 4, 44, 11, 2, 1.4, 17, 8, "ambusher", "monster_bone_stalker", "bleed"),
    ("shroud_haunt", "Shroud Haunt", "catacombs", 4, 36, 10, 1, 1.2, 16, 9, "chaser", "monster_shroud_haunt", "slow"),
    ("catacomb_guardian", "Catacomb Guardian", "catacombs", 4, 70, 12, 4, 0.8, 22, 6, "brute", "monster_catacomb_guardian", "stun"),
    ("skull_overlord", "Skull Overlord", "catacombs", 5, 260, 14, 4, 0.85, 95, 1, "brute", "boss_skull_overlord", "bleed"),
    # ember warrens
    ("coal_hound", "Coal Hound", "ember_warrens", 2, 24, 7, 1, 1.8, 9, 22, "chaser", "monster_coal_hound", "burn"),
    ("ember_imp", "Ember Imp", "ember_warrens", 2, 18, 6, 0, 1.5, 8, 20, "ranged", "monster_ember_imp", "burn"),
    ("spark_moth", "Spark Moth", "ember_warrens", 2, 14, 5, 0, 2.2, 7, 16, "ambusher", "monster_spark_moth", "burn"),
    ("cinder_wretch", "Cinder Wretch", "ember_warrens", 3, 30, 8, 1, 1.3, 12, 18, "chaser", "monster_cinder_wretch", "burn"),
    ("ash_wraith", "Ash Wraith", "ember_warrens", 3, 28, 9, 1, 1.2, 13, 14, "ambusher", "monster_ash_wraith", "burn"),
    ("magma_slinger", "Magma Slinger", "ember_warrens", 3, 24, 8, 1, 1.0, 12, 12, "ranged", "monster_magma_slinger", "burn"),
    ("slag_drudge", "Slag Drudge", "ember_warrens", 3, 58, 11, 3, 0.5, 16, 11, "brute", "monster_slag_drudge", "burn"),
    ("bellows_brute", "Bellows Brute", "ember_warrens", 4, 66, 13, 4, 0.6, 19, 9, "brute", "monster_bellows_brute", "burn"),
    ("molten_crawler", "Molten Crawler", "ember_warrens", 4, 40, 10, 2, 1.6, 15, 10, "ambusher", "monster_molten_crawler", "burn"),
    ("forge_colossus", "Forge Colossus", "ember_warrens", 5, 320, 17, 5, 0.8, 115, 1, "brute", "boss_forge_colossus", "burn"),
    # drowned vaults
    ("brine_thrall", "Brine Thrall", "drowned_vaults", 3, 32, 8, 1, 1.3, 12, 22, "chaser", "monster_brine_thrall", "slow"),
    ("pale_diver", "Pale Diver", "drowned_vaults", 3, 28, 9, 1, 1.6, 13, 16, "ambusher", "monster_pale_diver", "slow"),
    ("drowned_soldier", "Drowned Soldier", "drowned_vaults", 3, 44, 10, 3, 0.9, 15, 18, "chaser", "monster_drowned_soldier", None),
    ("bog_lurker", "Bog Lurker", "drowned_vaults", 3, 34, 9, 2, 1.5, 13, 12, "ambusher", "monster_bog_lurker", "slow"),
    ("abyss_lamprey", "Abyss Lamprey", "drowned_vaults", 4, 30, 11, 1, 1.8, 15, 16, "chaser", "monster_abyss_lamprey", "bleed"),
    ("tide_caller", "Tide Caller", "drowned_vaults", 4, 30, 9, 1, 1.0, 16, 14, "ranged", "monster_tide_caller", "slow"),
    ("deep_priest", "Deep Priest", "drowned_vaults", 4, 34, 10, 2, 1.0, 18, 10, "ranged", "monster_deep_priest", "bleed"),
    ("vault_sifter", "Vault Sifter", "drowned_vaults", 4, 36, 10, 2, 1.4, 16, 9, "ambusher", "monster_vault_sifter", None),
    ("waterlogged_husk", "Waterlogged Husk", "drowned_vaults", 4, 52, 11, 3, 0.9, 17, 14, "chaser", "monster_waterlogged_husk", None),
    ("mire_hulk", "Mire Hulk", "drowned_vaults", 4, 80, 14, 5, 0.55, 22, 10, "brute", "monster_mire_hulk", "slow"),
    ("coral_horror", "Coral Horror", "drowned_vaults", 4, 60, 12, 4, 0.7, 19, 9, "brute", "monster_coral_horror", "stun"),
    ("drowned_leviathan", "Drowned Leviathan", "drowned_vaults", 5, 380, 20, 6, 0.9, 140, 1, "brute",
     "boss_drowned_leviathan", "bleed"),
]

_FALLBACK_MONSTERS = [dict(zip(_MONSTER_FIELDS, row)) for row in _MONSTER_ROWS]

# id, name, slot, tier, effect, value, sprite, flavor
_ITEM_ROWS = [
    # weapons
    ("rusty_blade", "Rusty Blade", "weapon", 1, {"damage": 2}, 12, "item_rusty_blade",
     "Notched, but it remembers being sharp."),
    ("chipped_hatchet", "Chipped Hatchet", "weapon", 1, {"damage": 3}, 16, "item_chipped_hatchet",
     "Half a blade and twice the spite."),
    ("iron_mace", "Iron Mace", "weapon", 2, {"damage": 4}, 30, "item_iron_mace",
     "Swung by someone who never counted the swings."),
    ("bone_shiv", "Bone Shiv", "weapon", 2, {"damage": 3, "crit": 0.05}, 34, "item_bone_shiv",
     "Ground from a femur that walked."),
    ("serrated_falchion", "Serrated Falchion", "weapon", 3, {"damage": 5, "crit": 0.03}, 62,
     "item_serrated_falchion", "It saws rather than cuts."),
    ("venom_dirk", "Venom Dirk", "weapon", 3, {"damage": 4, "crit": 0.06}, 66, "item_venom_dirk",
     "The blade sweats a green bead."),
    ("lantern_flail", "Lantern Flail", "weapon", 3, {"damage": 6, "luck": 1}, 70, "item_lantern_flail",
     "Its light swings ahead of you, recklessly."),
    ("ember_club", "Ember Club", "weapon", 3, {"damage": 5}, 58, "item_ember_club",
     "Still smoking from the warrens."),
    ("steel_glaive", "Steel Glaive", "weapon", 4, {"damage": 8}, 100, "item_steel_glaive",
     "Reach is its own armour."),
    ("wraithfang", "Wraithfang", "weapon", 4, {"damage": 8, "crit": 0.05}, 112, "item_wraithfang",
     "Cold enough to hurt the hand that holds it."),
    ("magma_warhammer", "Magma Warhammer", "weapon", 4, {"damage": 9}, 118, "item_magma_warhammer",
     "Forged in a warren floor that is still burning."),
    ("vault_cleaver", "Vault Cleaver", "weapon", 5, {"damage": 12, "crit": 0.06}, 175, "item_vault_cleaver",
     "It opens doors and everything behind them."),
    ("keepers_edge", "Keeper's Edge", "weapon", 5, {"damage": 11, "crit": 0.08}, 190, "item_keepers_edge",
     "Every Lantern-Keeper sharpens it the same way."),
    ("soul_reaver", "Soul Reaver", "weapon", 5, {"damage": 10, "luck": 3}, 195, "item_soul_reaver",
     "Essence clings to the haft."),
    ("drowned_maul", "Drowned Maul", "weapon", 5, {"damage": 13, "speed": -0.2}, 180, "item_drowned_maul",
     "Heavy with water that never left."),
    # armor
    ("torn_leather_cap", "Torn Leather Cap", "armor", 1, {"armor": 1}, 10, "item_torn_leather_cap",
     "Keeps the dripping off your neck."),
    ("rag_wraps", "Rag Wraps", "armor", 1, {"armor": 1, "max_hp": 4}, 12, "item_rag_wraps",
     "Someone tore these into bandages and back."),
    ("cracked_buckler", "Cracked Buckler", "armor", 1, {"armor": 2}, 18, "item_cracked_buckler",
     "It has stopped one blow already."),
    ("studded_jerkin", "Studded Jerkin", "armor", 2, {"armor": 3}, 40, "item_studded_jerkin",
     "Quilted by someone who expected to survive."),
    ("iron_helm", "Iron Helm", "armor", 2, {"armor": 3, "max_hp": 6}, 44, "item_iron_helm",
     "Dented inward. Best not to look."),
    ("oak_shield", "Oak Shield", "armor", 2, {"armor": 4, "speed": -0.1}, 48, "item_oak_shield",
     "Grown above ground. A rarity here."),
    ("ring_mail", "Ring Mail", "armor", 3, {"armor": 4}, 74, "item_ring_mail", "Rings, all still linked."),
    ("bone_plate", "Bone Plate", "armor", 3, {"armor": 5}, 80, "item_bone_plate",
     "Interlocking ribs, all facing out."),
    ("ember_visor", "Ember Visor", "armor", 3, {"armor": 4, "damage": 1}, 86, "item_ember_visor",
     "The slit glows when you breathe."),
    ("warden_carapace", "Warden Carapace", "armor", 4, {"armor": 6, "max_hp": 12}, 124,
     "item_warden_carapace", "The skull warden wore it long before you."),
    ("magma_cuirass", "Magma Cuirass", "armor", 4, {"armor": 6, "damage": 2}, 130, "item_magma_cuirass",
     "Warm enough to sleep in. Do not."),
    ("drownscale_mail", "Drownscale Mail", "armor", 4, {"armor": 6, "max_hp": 14}, 132,
     "item_drownscale_mail", "Still cold. Still wet."),
    ("keepers_bulwark", "Keeper's Bulwark", "armor", 4, {"armor": 7}, 138, "item_keepers_bulwark",
     "Hold the lantern up. Hold the line."),
    ("vaelmoor_aegis", "Vaelmoor Aegis", "armor", 5, {"armor": 8, "max_hp": 20}, 205,
     "item_vaelmoor_aegis", "The city's last door, worn as a coat."),
    ("soulforged_plate", "Soulforged Plate", "armor", 5, {"armor": 9, "max_hp": 18, "luck": 2}, 215,
     "item_soulforged_plate", "Something kind was melted into it."),
    # trinkets
    ("tin_ring", "Tin Ring", "trinket", 1, {"luck": 1}, 14, "item_tin_ring",
     "Turned green, like everything down here."),
    ("rat_tooth_charm", "Rat Tooth Charm", "trinket", 1, {"crit": 0.02}, 16, "item_rat_tooth_charm",
     "Thirty-one teeth. You counted."),
    ("lucky_coin", "Lucky Coin", "trinket", 2, {"luck": 2}, 36, "item_lucky_coin",
     "Heads you live. Tails, you learn."),
    ("garnet_ring", "Garnet Ring", "trinket", 2, {"damage": 1, "luck": 1}, 40, "item_garnet_ring",
     "The stone is warm for no reason."),
    ("hunters_token", "Hunter's Token", "trinket", 2, {"speed": 0.25}, 42, "item_hunters_token",
     "Be first, or be food."),
    ("etched_amulet", "Etched Amulet", "trinket", 3, {"luck": 2, "crit": 0.02}, 78, "item_etched_amulet",
     "The etching is a map that no longer applies."),
    ("cinder_talisman", "Cinder Talisman", "trinket", 3, {"damage": 2}, 82, "item_cinder_talisman",
     "Ash in a bottle, angry about it."),
    ("rusted_censer", "Rusted Censer", "trinket", 3, {"max_hp": 12, "luck": 1}, 84,
     "item_rusted_censer", "It still swings when you walk."),
    ("abyssal_band", "Abyssal Band", "trinket", 4, {"luck": 3, "damage": 2}, 128, "item_abyssal_band",
     "The tide answers, slowly."),
    ("soul_prism", "Soul Prism", "trinket", 4, {"crit": 0.04, "luck": 2}, 134, "item_soul_prism",
     "Light goes in clean and comes out coloured."),
    ("void_lantern", "Void Lantern", "trinket", 5, {"luck": 4, "crit": 0.04}, 200, "item_void_lantern",
     "It lights the way it wants to go."),
    ("crown_of_depths", "Crown of Depths", "trinket", 5, {"damage": 4, "luck": 3, "crit": 0.03}, 220,
     "item_crown_of_depths", "It was here before the catacombs were."),
    # consumables
    ("small_health_draught", "Small Health Draught", "consumable", 1, {"max_hp": 20}, 12,
     "item_small_health_draught", "Tastes of iron and mint."),
    ("health_draught", "Health Draught", "consumable", 1, {"max_hp": 35}, 20, "item_health_draught",
     "Burns going down, closes everything."),
    ("lantern_oil", "Lantern Oil", "consumable", 1, {"luck": 1}, 14, "item_lantern_oil",
     "Keeps the flame honest a while longer."),
    ("swift_tonic", "Swift Tonic", "consumable", 2, {"speed": 1.0}, 32, "item_swift_tonic",
     "Drink fast. Run faster."),
    ("iron_skin_brew", "Iron Skin Brew", "consumable", 2, {"armor": 5}, 34, "item_iron_skin_brew",
     "Skin remembers being rock."),
    ("ember_tonic", "Ember Tonic", "consumable", 2, {"damage": 4}, 30, "item_ember_tonic",
     "Anger, bottled in the warrens."),
    ("focus_tea", "Focus Tea", "consumable", 2, {"crit": 0.06}, 33, "item_focus_tea",
     "Steady hands, steady eye."),
    ("greater_draught", "Greater Draught", "consumable", 3, {"max_hp": 65}, 46, "item_greater_draught",
     "Everything closes at once. Almost everything."),
    ("hunters_elixir", "Hunter's Elixir", "consumable", 3, {"damage": 2, "crit": 0.05}, 50,
     "item_hunters_elixir", "You will hear the heartbeats."),
    ("assassin_draught", "Assassin Draught", "consumable", 3, {"crit": 0.08, "speed": 0.4}, 54,
     "item_assassin_draught", "One clean strike or none at all."),
    ("vault_elixir", "Vault Elixir", "consumable", 3, {"max_hp": 55, "armor": 3}, 52,
     "item_vault_elixir", "Bottled at the bottom of the vault."),
    ("keepers_draught", "Keeper's Draught", "consumable", 4, {"max_hp": 85, "damage": 2}, 72,
     "item_keepers_draught", "A Lantern-Keeper's last secret."),
    ("dragonsblood_flask", "Dragonsblood Flask", "consumable", 4, {"damage": 6}, 76,
     "item_dragonsblood_flask", "No dragon was involved. Probably."),
    ("soulfire_tonic", "Soulfire Tonic", "consumable", 5, {"damage": 5, "crit": 0.06}, 96,
     "item_soulfire_tonic", "Essence, distilled and furious."),
]

_ITEM_FIELDS = ("id", "name", "slot", "tier", "effect", "value", "sprite", "flavor", "unique")
_FALLBACK_ITEMS = [dict(zip(_ITEM_FIELDS, row)) for row in _ITEM_ROWS]

_AFFIX_FIELDS = ("id", "name", "effect", "tier_min", "tier_max", "weight")
_AFFIX_ROWS = [
    ("of_strength", "of Strength", {"damage": 1}, 1, 3, 30),
    ("of_might", "of Might", {"damage": 2}, 2, 5, 18),
    ("of_ember", "of Ember", {"damage": 3}, 3, 5, 8),
    ("of_warding", "of Warding", {"armor": 1}, 1, 4, 26),
    ("of_bulwark", "of Bulwark", {"armor": 2}, 2, 5, 14),
    ("of_vigor", "of Vigor", {"max_hp": 8}, 1, 4, 24),
    ("of_blood", "of Blood", {"max_hp": 16}, 2, 5, 12),
    ("of_haste", "of Haste", {"speed": 0.15}, 1, 4, 22),
    ("of_wind", "of Wind", {"speed": 0.3}, 3, 5, 10),
    ("of_fortune", "of Fortune", {"luck": 2}, 1, 4, 20),
    ("of_omen", "of Omen", {"luck": 4}, 3, 5, 9),
    ("of_precision", "of Precision", {"crit": 0.03}, 2, 5, 16),
    ("of_ruin", "of Ruin", {"crit": 0.06}, 4, 5, 6),
    ("of_the_grave", "of the Grave", {"damage": 1, "armor": 1}, 3, 5, 7),
    ("of_the_vault", "of the Vault", {"luck": 2, "max_hp": 6}, 2, 5, 11),
]
_FALLBACK_AFFIXES = [dict(zip(_AFFIX_FIELDS, row)) for row in _AFFIX_ROWS]

_ROOM_FIELDS = ("id", "biome", "kind", "w", "h", "spawn_budget", "props", "secret_wall")
_ROOM_ROWS = [
    ("cat_entrance", "catacombs", "entrance", 9, 7, 0, ["prop_brazier", "prop_rubble"]),
    ("cat_hall_small", "catacombs", "combat", 11, 9, 4, ["prop_pillar", "prop_bones"]),
    ("cat_gallery", "catacombs", "combat", 14, 8, 5, ["prop_pillar", "prop_bones", "prop_web"]),
    ("cat_hall_wide", "catacombs", "combat", 16, 10, 6, ["prop_pillar", "prop_sarcophagus", "prop_bones"]),
    ("cat_crypt", "catacombs", "treasure", 10, 8, 2, ["prop_sarcophagus", "prop_chest"]),
    ("cat_shrine", "catacombs", "shrine", 9, 9, 1, ["prop_shrine", "prop_candles"]),
    ("cat_shop", "catacombs", "shop", 9, 8, 0, ["prop_shop_stall", "prop_candles"]),
    ("cat_boss", "catacombs", "boss", 18, 14, 2, ["prop_bones", "prop_brazier"]),
    ("emb_entrance", "ember_warrens", "entrance", 9, 7, 0, ["prop_lava_vent"]),
    ("emb_tunnel", "ember_warrens", "combat", 14, 8, 5, ["prop_lava_vent", "prop_water_pool"]),
    ("emb_forge", "ember_warrens", "combat", 15, 11, 7, ["prop_anvil", "prop_water_pool", "prop_lava_vent"]),
    ("emb_hoard", "ember_warrens", "treasure", 10, 9, 3, ["prop_chest", "prop_water_pool"]),
    ("emb_shop", "ember_warrens", "shop", 9, 8, 0, ["prop_shop_stall", "prop_candles"]),
    ("emb_shrine", "ember_warrens", "shrine", 9, 9, 1, ["prop_shrine", "prop_lava_vent"]),
    ("emb_boss", "ember_warrens", "boss", 19, 15, 2, ["prop_water_pool", "prop_anvil"]),
    ("drown_entrance", "drowned_vaults", "entrance", 9, 7, 0, ["prop_water_pool"]),
    ("drown_gallery", "drowned_vaults", "combat", 17, 10, 6, ["prop_water_pool", "prop_statue_head"]),
    ("drown_cistern", "drowned_vaults", "combat", 13, 12, 5, ["prop_water_pool", "prop_statue_head", "prop_pillar"]),
    ("drown_vault", "drowned_vaults", "treasure", 11, 9, 3, ["prop_chest", "prop_statue_head"]),
    ("drown_shrine", "drowned_vaults", "shrine", 10, 10, 2, ["prop_shrine", "prop_water_pool"]),
    ("drown_shop", "drowned_vaults", "shop", 9, 8, 0, ["prop_shop_stall", "prop_water_pool"]),
    ("drown_boss", "drowned_vaults", "boss", 20, 16, 3, ["prop_water_pool", "prop_statue_head", "prop_pillar"]),
    # P3.3 event rooms - one per biome
    ("cat_gambling", "catacombs", "gambling", 8, 7, 0, ["prop_coffer", "prop_gold_pile"]),
    ("cat_blacksmith", "catacombs", "blacksmith", 9, 8, 0, ["prop_anvil", "prop_hammer"]),
    ("cat_fountain", "catacombs", "fountain", 7, 7, 0, ["prop_fountain"]),
    ("cat_omen", "catacombs", "omen", 7, 7, 0, ["prop_eye"]),
    ("emb_gambling", "ember_warrens", "gambling", 8, 7, 0, ["prop_coffer", "prop_gold_pile"]),
    ("emb_blacksmith", "ember_warrens", "blacksmith", 9, 8, 0, ["prop_anvil", "prop_hammer"]),
    ("emb_fountain", "ember_warrens", "fountain", 7, 7, 0, ["prop_fountain"]),
    ("emb_omen", "ember_warrens", "omen", 7, 7, 0, ["prop_eye"]),
    ("drown_gambling", "drowned_vaults", "gambling", 8, 7, 0, ["prop_coffer", "prop_gold_pile"]),
    ("drown_blacksmith", "drowned_vaults", "blacksmith", 9, 8, 0, ["prop_anvil", "prop_hammer"]),
    ("drown_fountain", "drowned_vaults", "fountain", 7, 7, 0, ["prop_fountain"]),
    ("drown_omen", "drowned_vaults", "omen", 7, 7, 0, ["prop_eye"]),
]
_FALLBACK_ROOMS = [dict(zip(_ROOM_FIELDS, row)) for row in _ROOM_ROWS]

_FALLBACK_BIOMES = [
    {"id": "catacombs", "name": "The Catacombs", "tileset": "tile_catacombs",
     "monsters": ["bone_rat", "ash_skeleton", "grave_moth", "ossuary_archer", "putrid_ghoul",
                  "crypt_crawler", "tomb_lurker", "crypt_brute", "skull_warden", "bone_stalker",
                  "shroud_haunt", "catacomb_guardian", "skull_overlord"],
     "ambient": [11, 10, 16], "fog": 0.30, "music": None,
     "ambient_sound": {"frequency": 120.0, "pattern": "drip_pause", "volume": 0.25},
     "attenuation": {"min_distance": 1.0, "max_distance": 32.0, "rolloff": 1.5},
     "sfx_events": {"footstep": "tile_catacombs_floor", "door": "tile_catacombs_door", "hit": "hit_metal", "death": "death_cave_echo"}},
    {"id": "ember_warrens", "name": "The Ember Warrens", "tileset": "tile_ember",
     "monsters": ["coal_hound", "ember_imp", "spark_moth", "cinder_wretch", "ash_wraith",
                  "magma_slinger", "slag_drudge", "bellows_brute", "molten_crawler",
                  "forge_colossus"],
     "ambient": [36, 12, 8], "fog": 0.38, "music": None,
     "ambient_sound": {"frequency": 440.0, "pattern": "crackle_hiss", "volume": 0.30},
     "attenuation": {"min_distance": 1.0, "max_distance": 28.0, "rolloff": 1.8},
     "sfx_events": {"footstep": "tile_ember_floor", "door": "tile_ember_door", "hit": "hit_spark", "death": "death_ember_fizzle"}},
    {"id": "drowned_vaults", "name": "The Drowned Vaults", "tileset": "tile_drowned",
     "monsters": ["brine_thrall", "pale_diver", "drowned_soldier", "bog_lurker", "abyss_lamprey",
                  "tide_caller", "deep_priest", "vault_sifter", "waterlogged_husk", "mire_hulk",
                  "coral_horror", "drowned_leviathan"],
     "ambient": [16, 40, 60], "fog": 0.46, "music": None,
     "ambient_sound": {"frequency": 200.0, "pattern": "bubble_rise", "volume": 0.20},
     "attenuation": {"min_distance": 1.0, "max_distance": 40.0, "rolloff": 1.2},
     "sfx_events": {"footstep": "tile_drowned_floor", "door": "tile_drowned_door", "hit": "hit_splash", "death": "death_bubble_pop"}},
]

_STATUS_FIELDS = ("id", "name", "kind", "magnitude", "duration", "tick_every", "icon")
_STATUS_ROWS = [
    ("poison", "Poison", "dot", 2, 300, 30, "ui_status_poison"),
    ("burn", "Burn", "dot", 3, 240, 20, "ui_status_burn"),
    ("bleed", "Bleed", "dot", 3, 300, 40, "ui_status_bleed"),
    ("stun", "Stunned", "debuff", 1, 60, 60, "ui_status_stun"),
    ("slow", "Slowed", "debuff", 0.45, 180, 60, "ui_status_slow"),
    ("fortify", "Fortified", "buff", 4, 420, 60, "ui_status_fortify"),
    ("rage", "Rage", "buff", 4, 420, 60, "ui_status_rage"),
]
_FALLBACK_STATUSES = [dict(zip(_STATUS_FIELDS, row)) for row in _STATUS_ROWS]

_FALLBACK_FLAVOR = [
    {"id": "death_1", "context": "death",
     "text": "The lantern gutters. Vaelmoor keeps what you found."},
    {"id": "death_2", "context": "death",
     "text": "You were the ninth this week to reach the third stair."},
    {"id": "death_3", "context": "death",
     "text": "Essence drifts up. Something below inhales."},
    {"id": "levelup_1", "context": "levelup", "text": "The flame steadies; your arms remember."},
    {"id": "levelup_2", "context": "levelup", "text": "Another Lock-Keeper's trick, learned cold."},
    {"id": "item_1", "context": "item", "text": "Still warm from whoever held it last."},
    {"id": "item_2", "context": "item", "text": "The vault smiles, and pays."},
    {"id": "shrine_1", "context": "shrine", "text": "A price is named. You pay it standing."},
    {"id": "shrine_2", "context": "shrine", "text": "Offerings rot slowly in Vaelmoor."},
    {"id": "boss_1", "context": "boss", "text": "The floor's guardian uncoils from the dark."},
    {"id": "boss_2", "context": "boss", "text": "Something that was a person counts your steps."},
]

_FALLBACKS = {
    "monsters": _FALLBACK_MONSTERS,
    "items": _FALLBACK_ITEMS,
    "affixes": _FALLBACK_AFFIXES,
    "rooms": _FALLBACK_ROOMS,
    "biomes": _FALLBACK_BIOMES,
    "statuses": _FALLBACK_STATUSES,
    "flavor": _FALLBACK_FLAVOR,
}

# Required fields per CONTRACTS.md section 4.
REQUIRED = {
    "monsters": ("id", "name", "biome", "tier", "hp", "damage", "armor", "speed", "xp",
                 "weight", "behavior", "sprite", "status_on_hit"),
    "items": ("id", "name", "slot", "tier", "effect", "value", "sprite", "flavor"),
    "affixes": ("id", "name", "effect", "tier_min", "tier_max", "weight"),
    "rooms": ("id", "biome", "kind", "w", "h", "spawn_budget", "props", "secret_wall"),
    "biomes": ("id", "name", "tileset", "monsters", "ambient", "fog", "music"),
    "statuses": ("id", "name", "kind", "magnitude", "duration", "tick_every", "icon"),
    "flavor": ("id", "context", "text"),
}


class Content:
    """Validated, tolerant content registry."""

    def __init__(self, warnings=None, data_dir=None, mod_dir=None):
        self.warnings = warnings if warnings is not None else []
        self.data_dir = Path(data_dir) if data_dir else DATA_DIR
        self.mod_dir = Path(mod_dir) if mod_dir else None
        self.tables = {}
        self.by_id = {}
        self.sources = {}
        self.load_all()

    # -- loading ---------------------------------------------------------
    def load_all(self):
        for name in ("monsters", "items", "affixes", "rooms", "biomes", "statuses", "flavor"):
            entries, source = self._load_table_with_mod(name)
            self.tables[name] = entries
            self.by_id[name] = {e["id"]: e for e in entries}
            self.sources[name] = source
        self._repair_references()

    def _load_table_with_mod(self, name):
        entries, source = self._load_table(name)
        if not self.mod_dir:
            return entries, source
        mod_path = self.mod_dir / ("%s.json" % name)
        if not mod_path.exists():
            return entries, source
        try:
            with open(mod_path, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
        except (OSError, ValueError) as exc:
            self.warnings.append("mod_dir/%s.json unreadable (%s) - skipping mod overrides"
                                 % (name, type(exc).__name__))
            return entries, source
        mod_entries = raw.get("entries") if isinstance(raw, dict) else None
        if not isinstance(mod_entries, list):
            self.warnings.append("mod_dir/%s.json has no 'entries' list - skipping mod overrides"
                                 % name)
            return entries, source
        mod_entries = [dict(e) for e in mod_entries]
        entries = self._merge_table(name, entries, mod_entries)
        if source == "fallback":
            source = "mod-only"
        else:
            source = source + "+mod"
        return entries, source

    def _load_table(self, name):
        path = self.data_dir / ("%s.json" % name)
        if not path.exists():
            self.warnings.append("game/data/%s.json missing - using built-in seed content" % name)
            return [dict(e) for e in _FALLBACKS[name]], "fallback"
        try:
            with open(path, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
        except (OSError, ValueError) as exc:
            self.warnings.append("game/data/%s.json unreadable (%s) - using built-in seed content"
                                 % (name, type(exc).__name__))
            return [dict(e) for e in _FALLBACKS[name]], "fallback"

        entries = raw.get("entries") if isinstance(raw, dict) else None
        if not isinstance(entries, list):
            self.warnings.append("game/data/%s.json has no 'entries' list - using built-in seed content"
                                 % name)
            return [dict(e) for e in _FALLBACKS[name]], "fallback"

        required = REQUIRED[name]
        # secret_wall is optional, so skip it in required check
        required = tuple(f for f in required if f != "secret_wall")
        good = []
        seen = set()
        skipped = 0
        for entry in entries:
            if not isinstance(entry, dict):
                skipped += 1
                continue
            missing = [f for f in required if f not in entry]
            if missing:
                skipped += 1
                self.warnings.append("game/data/%s.json entry missing %s - skipped"
                                     % (name, ",".join(missing)))
                continue
            if entry["id"] in seen:
                skipped += 1
                self.warnings.append("game/data/%s.json duplicate id %r - skipped" % (name, entry["id"]))
                continue
            seen.add(entry["id"])
            good.append(dict(entry))
        if skipped:
            self.warnings.append("game/data/%s.json: %d entr%s skipped"
                                 % (name, skipped, "y" if skipped == 1 else "ies"))
        if not good:
            self.warnings.append("game/data/%s.json had no usable entries - using built-in seed content"
                                 % name)
            return [dict(e) for e in _FALLBACKS[name]], "fallback"
        return good, "data-file"

    def _merge_table(self, name, base_entries, mod_entries):
        """Merge mod_entries into base_entries, overlaying by id.

        Entries with a matching id replace the base entry; new ids are appended.
        Duplicate ids in mod warn but the mod entry wins.
        """
        merged = {e["id"]: dict(e) for e in base_entries}
        for entry in mod_entries:
            if not isinstance(entry, dict):
                continue
            eid = entry.get("id")
            if not eid:
                continue
            if eid in merged:
                self.warnings.append("mod_dir/%s.json: id %r overrides base entry"
                                     % (name, eid))
            merged[eid] = dict(entry)
        result = list(merged.values())
        return result

    def _repair_references(self):
        """Biomes referencing unknown monster ids get the unknown ids dropped."""
        known = self.by_id["monsters"]
        for biome in self.tables["biomes"]:
            ids = [m for m in biome.get("monsters", []) if m in known]
            if len(ids) != len(biome.get("monsters", [])):
                dropped = [m for m in biome.get("monsters", []) if m not in known]
                self.warnings.append("biome %r references unknown monsters %s - dropped"
                                     % (biome.get("id"), ",".join(map(str, dropped))))
            if not ids:
                ids = [e["id"] for e in _FALLBACK_MONSTERS if e["biome"] == biome.get("id")]
                self.warnings.append("biome %r had no valid monsters - seeded from fallback"
                                     % (biome.get("id"),))
            biome["monsters"] = ids

        # items with unknown slots are demoted to trinkets rather than crashing
        for item in self.tables["items"]:
            if item.get("slot") not in SLOTS:
                self.warnings.append("item %r has unknown slot %r - treated as trinket"
                                     % (item.get("id"), item.get("slot")))
                item["slot"] = "trinket"
            effect = item.get("effect")
            if not isinstance(effect, dict):
                item["effect"] = {}
            else:
                item["effect"] = {k: v for k, v in effect.items()
                                  if k in STAT_KEYS and isinstance(v, (int, float))}
        for affix in self.tables["affixes"]:
            effect = affix.get("effect")
            if not isinstance(effect, dict):
                affix["effect"] = {}
            else:
                affix["effect"] = {k: v for k, v in effect.items()
                                   if k in STAT_KEYS and isinstance(v, (int, float))}
        for monster in self.tables["monsters"]:
            if monster.get("behavior") not in BEHAVIORS:
                self.warnings.append("monster %r has unknown behavior %r - treated as chaser"
                                     % (monster.get("id"), monster.get("behavior")))
                monster["behavior"] = "chaser"
        status_ids = self.by_id["statuses"]
        for monster in self.tables["monsters"]:
            soh = monster.get("status_on_hit")
            if soh is not None and soh not in status_ids:
                self.warnings.append("monster %r status_on_hit %r unknown - cleared"
                                     % (monster.get("id"), soh))
                monster["status_on_hit"] = None
        for room in self.tables["rooms"]:
            if room.get("kind") not in ROOM_KINDS:
                self.warnings.append("room %r has unknown kind %r - treated as combat"
                                     % (room.get("id"), room.get("kind")))
                room["kind"] = "combat"
            if not isinstance(room.get("props"), list):
                room["props"] = []
            if "secret_wall" in room and not isinstance(room["secret_wall"], str):
                room["secret_wall"] = None
            if room.get("kind") == "secret" and "secret_wall" not in room:
                self.warnings.append("room %r is kind=secret but missing secret_wall"
                                     % room.get("id"))

    # -- accessors -------------------------------------------------------
    def monsters(self):
        return self.tables["monsters"]

    def items(self):
        return self.tables["items"]

    def item_ids(self):
        return set(self.by_id["items"].keys())

    def item(self, item_id):
        return self.by_id["items"].get(item_id)

    def monster(self, monster_id):
        return self.by_id["monsters"].get(monster_id)

    def affixes(self):
        return self.tables["affixes"]

    def rooms(self):
        return self.tables["rooms"]

    def biomes(self):
        return self.tables["biomes"]

    def biome(self, biome_id):
        return self.by_id["biomes"].get(biome_id)

    def biome_order(self):
        return [b["id"] for b in self.tables["biomes"]]

    def tileset_for(self, biome_id):
        biome = self.biome(biome_id) or {}
        prefix = biome.get("tileset") or "tile_catacombs"
        # the manifest's tileset field is already the full prefix ("tile_catacombs")
        if not str(prefix).startswith("tile_"):
            prefix = "tile_%s" % prefix
        return str(prefix)

    def status(self, status_id):
        return self.by_id["statuses"].get(status_id)

    def statuses(self):
        return self.tables["statuses"]

    def monster_pool(self, biome_id, max_tier=4):
        biome = self.biome(biome_id)
        if not biome:
            return []
        out = []
        for mid in biome.get("monsters", []):
            mon = self.monster(mid)
            if mon and int(mon.get("tier", 1)) <= max_tier:
                out.append(mon)
        return out

    def boss_for(self, biome_id):
        best = None
        for mon in self.monster_pool(biome_id, max_tier=5):
            if int(mon.get("tier", 1)) >= 5:
                if best is None or int(mon.get("hp", 0)) > int(best.get("hp", 0)):
                    best = mon
        return best

    def rooms_for(self, biome_id, kind=None):
        out = []
        for room in self.tables["rooms"]:
            if room.get("biome") != biome_id:
                continue
            if kind is not None and room.get("kind") != kind:
                continue
            out.append(room)
        return out

    def flavor_for(self, context, rng):
        pool = [e for e in self.tables["flavor"] if e.get("context") == context]
        if not pool:
            return ""
        if rng is None:
            return pool[0].get("text", "")
        entry = rng.choice(pool)
        return entry.get("text", "")
