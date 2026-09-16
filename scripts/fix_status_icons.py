#!/usr/bin/env python3
"""Map missing status icons to existing UI atlas frames."""
import json

STATUS_MAP = {
    'ui_status_acid_burn': 'ui_status_burn',
    'ui_status_soul_rot': 'ui_status_poison',
    'ui_status_ember_scorch': 'ui_status_burn',
    'ui_status_weaken': 'ui_status_slow',
    'ui_status_corrode': 'ui_status_poison',
    'ui_status_chill': 'ui_status_slow',
    'ui_status_doom_mark': 'ui_status_stun',
    'ui_status_haste': 'ui_status_fortify',
    'ui_status_regeneration': 'ui_status_fortify',
    'ui_status_luck_ward': 'ui_status_fortify',
    'ui_status_lantern_glow': 'ui_status_fortify',
}

with open('assets/atlas/ui.json') as f:
    ui = json.load(f)
existing = set(ui['frames'].keys())

with open('game/data/statuses.json') as f:
    data = json.load(f)

changes = 0
for entry in data.get('entries', []):
    old = entry.get('icon', '')
    if old and old not in existing and old in STATUS_MAP:
        new = STATUS_MAP[old]
        entry['icon'] = new
        changes += 1
        print(f"  {old} -> {new}")

with open('game/data/statuses.json', 'w') as f:
    json.dump(data, f, indent=2)

print(f"\nTotal changes: {changes}")
