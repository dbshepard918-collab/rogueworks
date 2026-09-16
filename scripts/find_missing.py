import os, sys, json
os.environ['SDL_VIDEODRIVER'] = 'dummy'
sys.path.insert(0, '.')

# Load ALL atlas frames
all_frames = set()
for name in ['items', 'monsters', 'npcs', 'props', 'player', 'vfx', 'ui', 'bosses', 'hq', 'title', 'tiles']:
    path = f'assets/atlas/{name}.json'
    if os.path.exists(path):
        with open(path) as f:
            frames = json.load(f).get('frames', {})
            all_frames.update(frames.keys())

print(f"Total atlas frames: {len(all_frames)}")

# Check ALL content files for sprite references
content_files = [
    'game/data/items.json',
    'game/data/monsters.json', 
    'game/data/npcs.json',
    'game/data/props.json',
    'game/data/statuses.json',
    'game/data/hq_rooms.json',
    'game/data/quests.json',
    'game/data/storyline.json',
]

missing = {}
for fname in content_files:
    if not os.path.exists(fname):
        continue
    with open(fname) as f:
        data = json.load(f)
    
    missing[fname] = []
    
    def check_entries(entries, field='sprite'):
        if not isinstance(entries, list):
            return
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            sprite = entry.get(field, '')
            if sprite and sprite not in all_frames:
                missing[fname].append(sprite)
            # Check nested
            for k, v in entry.items():
                if isinstance(v, list):
                    check_entries(v, field)
    
    if isinstance(data, dict):
        for k, v in data.items():
            if isinstance(v, list):
                check_entries(v, 'sprite')
                check_entries(v, 'icon')
                check_entries(v, 'telegraph_sprite')

for fname, miss in missing.items():
    if miss:
        print(f"\n{fname}: {len(miss)} missing sprites")
        for m in miss[:10]:
            print(f"  {m}")
        if len(miss) > 10:
            print(f"  ... and {len(miss)-10} more")
