#!/usr/bin/env python3
"""Fix item_purifier sprite — replace off-palette SOUL_DARK with palette soul."""
from __future__ import annotations
import json
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
pal_raw = json.loads((ROOT / "assets" / "palette.json").read_text())
PAL = {n: tuple(int(v[i:i+2], 16) for i in (1,3,5)) for n,v in pal_raw["colors"].items()}
ALLOWED = set(PAL.values()) | {(255,0,255)}

def p3(buf, x, y, rgb):
    i = (y*32+x)*3
    buf[i]=rgb[0]; buf[i+1]=rgb[1]; buf[i+2]=rgb[2]

def rect(buf,x,y,w,h,rgb):
    for py in range(y,min(32,y+h)):
        for px in range(x,min(32,x+w)):
            p3(buf,px,py,rgb)

SO=PAL["soul"]; AL=PAL["arcane_light"]

rgb = bytearray(32*32*3)
# outer diamond
for y in range(4,29):
    t=(y-4)/24.0; h=int(10*(1-abs(t-0.5)*2))
    rect(rgb,16-h,y,2*h+1,1,SO)
# inner facets: alternate soul/arcane_light
for y in range(8,24):
    t=(y-4)/24.0; h=int(6*(1-abs(t-0.5)*2))
    for x in range(16-h,16+h+1):
        p3(rgb,x,y, AL if (x+y)%2==0 else SO)
# core
rect(rgb,13,12,6,8,SO)
p3(rgb,16,6,AL)

img = Image.new("RGBA",(32,32),(0,0,0,0))
bad = 0
for y in range(32):
    for x in range(32):
        i=(y*32+x)*3
        r,g,b = rgb[i],rgb[i+1],rgb[i+2]
        if (r,g,b)!=(0,0,0):
            img.putpixel((x,y),(r,g,b,255))
            if (r,g,b) not in ALLOWED:
                bad += 1
out = ROOT / "assets" / "sprites" / "items" / "item_purifier.png"
img.save(out)
print(f"fixed: {out.relative_to(ROOT)}")
print(f"off-palette pixels: {bad}")
