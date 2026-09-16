import os, sys, json
os.environ['SDL_VIDEODRIVER'] = 'dummy'
sys.path.insert(0, '.')

import pygame
import numpy as np
from PIL import Image

# Check player atlas frames
with open('assets/atlas/player.json') as f:
    p = json.load(f)

print("Player frames:", sorted(p['frames'].keys())[:5])

# Load player atlas and render first frame to check it's not a blob
img = Image.open('assets/atlas/player.png').convert('RGBA')
print(f"Player atlas: {img.size}")

# Get rect for player_idle_0
rect = p['frames'].get('player_idle_0')
if rect:
    print(f"player_idle_0 rect: {rect}")
    frame = img.crop((rect[0], rect[1], rect[0]+rect[2], rect[1]+rect[3]))
    # Check colors
    arr = np.array(frame)
    rgb = arr[..., :3]
    alpha = arr[..., 3]
    unique_rgb = len(np.unique(rgb.reshape(-1, 3), axis=0))
    print(f"Unique RGB colors in frame: {unique_rgb}")
    # Check if it's just white
    white_pixels = np.sum((rgb[..., 0] > 200) & (rgb[..., 1] > 200) & (rgb[..., 2] > 200) & (alpha > 0))
    total_opaque = np.sum(alpha > 0)
    print(f"White pixels: {white_pixels}/{total_opaque} ({100*white_pixels/max(1,total_opaque):.1f}%)")
    
    # Render as ASCII
    for y in range(32):
        row = ''
        for x in range(32):
            px = frame.getpixel((x, y))
            if px[3] < 128:
                row += ' '
            elif px[0] > 200 and px[1] > 200 and px[2] > 200:
                row += '#'
            elif px[0] < 50 and px[1] < 50 and px[2] < 50:
                row += '.'
            elif px[0] > 150 and px[1] > 100 and px[2] < 100:
                row += 'r'  # red
            elif px[0] > 150 and px[1] > 150 and px[2] < 100:
                row += 'y'  # yellow
            elif px[0] < 100 and px[1] > 150 and px[2] < 100:
                row += 'g'  # green
            elif px[0] < 100 and px[1] < 100 and px[2] > 150:
                row += 'b'  # blue
            elif px[0] > 150 and px[1] < 100 and px[2] > 150:
                row += 'm'  # magenta
            else:
                row += 'x'
        print(row)
