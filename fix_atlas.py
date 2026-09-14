import json
with open('assets/atlas/props.json') as f: d = json.load(f)
if 'prop_chains' in d.get('frames', {}):
    del d['frames']['prop_chains']
    print('REMOVED prop_chains from atlas frames')
    with open('assets/atlas/props.json', 'w') as f: json.dump(d, f, indent=2)
    print('frames now:', len(d.get('frames', {})))
else:
    print('prop_chains already not in frames')
