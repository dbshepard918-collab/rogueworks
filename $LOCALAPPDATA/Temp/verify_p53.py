import json, os

print("=== Profiler metrics in playtest JSONs ===")
for s in [0, 1, 2]:
    path = f'runs/playtest-{s}.json'
    with open(path) as f:
        d = json.load(f)
    m = d.get('metrics_profiler', {})
    print(f"Seed {s}: entities={m.get('entity_count')} tick_ms={m.get('tick_ms')} draw_calls={m.get('draw_calls')} particles={m.get('particle_count')} atlas={m.get('atlas_mem_mb')}MB caps={m.get('caps_violations')}")

print()
print("=== Shot frames ===")
for s in ['p53-seed0', 'p53-seed1', 'p53-seed2']:
    d = f'runs/shots/{s}'
    frames = sorted(os.listdir(d))
    sizes = {f: os.path.getsize(f'{d}/{f}') for f in frames}
    print(f"{s}: {len(frames)} frames {sizes}")

print()
print("=== Playtest files on disk ===")
pts = sorted(f for f in os.listdir('runs') if f.startswith('playtest-') and f.endswith('.json'))
print(f"playtest-*.json files: {pts}")
