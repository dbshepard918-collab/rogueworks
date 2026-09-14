from PIL import Image
import os

base = '/c/Users/dbshe/rogueworks/runs/shots'
for d in ['p04-glyph-0', 'p04-glyph-1', 'p04-glyph-2', 'p04', 'p04-v', 'p04-glyph-v2']:
    p = os.path.join(base, d, 'frame-000050.png')
    print('checking', p, 'exists=', os.path.exists(p))
    if os.path.exists(p):
        im = Image.open(p)
        px = list(im.convert('RGB').getdata())
        distinct = len(set(px))
        print('{}: {} bytes, {}, distinct_colors={}'.format(d, os.path.getsize(p), im.size, distinct))