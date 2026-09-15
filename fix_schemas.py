import re

with open('tools/validate_data.py') as f:
    content = f.read()

# Find and replace the broken SCHEMAS section (meta_tree.json through hq_rooms.json closing brace)
old = '''    "meta_tree.json": {
            "_special": True,
        },
        "npcs.json": {
            "version": {"type": "num", "min": 1},
            "npcs": {"type": "list", "items": {"type": "dict"}, "required": False},
        },
        "storyline.json": {
            "version": {"type": "num", "min": 1},
            "plot": {"type": "dict", "required": False},
        },
        "hq_rooms.json": {
            "version": {"type": "num", "min": 1},
            "rooms": {"type": "list", "items": {"type": "dict"}, "required": False},
        },
    }'''

new = '''    "meta_tree.json": {
        "_special": True,
    },
    "npcs.json": {
        "_special": True,
    },
    "storyline.json": {
        "_special": True,
    },
    "hq_rooms.json": {
        "_special": True,
    },
}'''

if old in content:
    content = content.replace(old, new)
    with open('tools/validate_data.py', 'w') as f:
        f.write(content)
    print("Fixed SCHEMAS section")
else:
    print("Pattern not found!")
    # Show what's around meta_tree
    idx = content.find('meta_tree.json')
    print(repr(content[idx-10:idx+200]))
