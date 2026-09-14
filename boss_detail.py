import json
# Find boss monsters and check what rooms reference
with open('game/data/monsters.json') as f:
    m = json.load(f)
bosses = [e for e in m['entries'] if e.get('tier') == 5]
print("All tier-5 bosses:")
for b in bosses:
    has_phases = 'phases' in b
    has_enrage = 'enrage' in b
    print(f"  {b['id']} ({b['biome']}) name={b['name']} phases={has_phases} enrage={has_enrage}")

print()
# Check what boss rooms exist per biome and what monster each should reference
# The naming convention suggests:
# catacombs_boss_ossuary -> skull_overlord (catacomb_guardian is the mini-boss)
# ember_warrens_boss_foundry -> forge_colossus
# drowned_vaults_boss_sanctum -> drowned_leviathan
# ossuary_boss_boss_1 -> ossuary_kraken
print()
# Check if rooms have a boss_id or monster_ref field
with open('game/data/rooms.json') as f:
    r = json.load(f)
boss_rooms = [e for e in r['entries'] if e['kind'] == 'boss']
print("Boss rooms (checking for boss_id/monster_ref fields):")
for br in boss_rooms:
    extra_fields = [k for k in br if k not in ('id','biome','kind','w','h','spawn_budget','props')]
    print(f"  {br['id']}: extra fields = {extra_fields}")
