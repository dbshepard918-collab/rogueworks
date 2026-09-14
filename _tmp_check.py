from PIL import Image
import os

for d in ['p04-glyph-0', 'p04-glyph-1', 'p04-glyph-2', 'p04', 'p04-v', 'p04-glyph-v2']:
    p = f'/c/Users/dbshe/rogueworks/runs/shots/{d}/frame-000050.png'
    if os.path.exists(p):
        im = Image.open(p)
        px = list(im.convert('RGB').getdata())
        distinct = len(set(px))
        print(f'{d}: {os.path.getsize(p)} bytes, {im.size}, distinct_colors={distinct}')
    else:
        print(f'{d}: MISSING')
