#!/usr/bin/env python3
"""Generate 9 new P2.3 monster sprites + 3 new VFX sprites (32x32, palette-locked).

Cross-lane edit (art is pixel's lane) — reason: 9 sprites block validate_data +
selftest gates; the game runs on placeholders but validators require real frames.
Simple geometric icons using only the Vaelmoor palette; pixel can refine later.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if not (ROOT / "assets" / "palette.json").exists():
    ROOT = Path.cwd()
    while not (ROOT / "assets" / "palette.json").exists():
        ROOT = ROOT.parent
        if not ROOT.parent or ROOT == ROOT.parent:
            print("ERROR cannot find project root", file=sys.stderr)
            sys.exit(2)

pal_raw = json.loads((ROOT / "assets" / "palette.json").read_text(encoding="utf-8"))
PAL = {n: tuple(int(v[i:i+2], 16) for i in (1, 3, 5)) for n, v in pal_raw["colors"].items()}
KEY = (255, 0, 255)
ALLOWED = set(PAL.values()) | {KEY}

def p3(buf, x, y, rgb):
    i = (y * 32 + x) * 3
    if 0 <= i < len(buf) - 2:
        buf[i] = rgb[0]
        buf[i+1] = rgb[1]
        buf[i+2] = rgb[2]

def rect(buf, x, y, w, h, rgb):
    for py in range(y, min(32, y + h)):
        for px in range(x, min(32, x + w)):
            p3(buf, px, py, rgb)

def circ(buf, cx, cy, r, rgb):
    for dy in range(-r, r+1):
        for dx in range(-r, r+1):
            if dx*dx + dy*dy <= r*r:
                p3(buf, cx+dx, cy+dy, rgb)

def ring(buf, cx, cy, r_outer, r_inner, rgb):
    for dy in range(-r_outer, r_outer+1):
        for dx in range(-r_outer, r_outer+1):
            d2 = dx*dx + dy*dy
            if r_inner*r_inner <= d2 <= r_outer*r_outer:
                p3(buf, cx+dx, cy+dy, rgb)


# --------------------------- MONSTER SPRITES ---------------------------

def draw_summon_skeleton(buf):
    """Red-glowing skeleton with summoned energy around it."""
    B = PAL["bone"]; S = PAL["steel"]; R = PAL["ember"]; RD = PAL["blood_dark"]
    for y in range(8, 24):
        for x in range(10, 22):
            if x == 10 or x == 21 or y == 8 or y == 23:
                p3(buf, x, y, B)
            elif y == 16:
                p3(buf, x, y, S)
    circ(buf, 16, 10, 4, R)
    circ(buf, 16, 10, 2, PAL["white"])
    for i in range(8):
        a = i * math.pi / 4
        px, py = int(16 + 8 * math.cos(a)), int(10 + 8 * math.sin(a))
        if 0 <= px < 32 and 0 <= py < 32:
            p3(buf, px, py, R)
    rect(buf, 13, 24, 6, 4, RD)

def draw_shield_guardian(buf):
    """Blue-shielded knight with a shield in front."""
    S = PAL["steel"]; B = PAL["bone"]; BL = PAL["blood"]; SD = PAL["stone_dark"]
    C = PAL["slate"]
    rect(buf, 11, 12, 10, 14, S)
    rect(buf, 10, 11, 12, 3, B)
    ring(buf, 16, 22, 5, 3, BL)
    for y in range(8, 12):
        for x in range(10, 22):
            if 10 <= x <= 21 and y == 8:
                p3(buf, x, y, SD)
    for y in range(12, 20):
        for x in range(8, 12):
            if y >= 12 and y <= 18:
                p3(buf, x, y, C)
                p3(buf, x+4, y, C)
    circ(buf, 16, 9, 2, C)

def draw_phantom_teleporter(buf):
    """Ghostly purple/teal phantom with a teleport swirl."""
    A = PAL["arcane"]; AS = PAL["arcane_light"]; SD = PAL["stone_dark"]
    for y in range(10, 22):
        for x in range(10, 22):
            d = math.sqrt((x-16)**2 + (y-16)**2)
            if d < 6:
                if int(d) % 2 == 0:
                    p3(buf, x, y, A)
                else:
                    p3(buf, x, y, AS)
            elif d < 8:
                p3(buf, x, y, SD)
    ring(buf, 16, 16, 5, 3, A)
    circ(buf, 16, 16, 2, PAL["white"])
    for i in range(6):
        a = i * math.pi / 3
        px, py = int(16 + 7 * math.cos(a)), int(16 + 7 * math.sin(a))
        if 0 <= px < 32 and 0 <= py < 32:
            p3(buf, px, py, AS)

def draw_charger_brute(buf):
    """Furious brute with charging energy."""
    E = PAL["ember"]; ED = PAL["ember_dark"]; F = PAL["flame"]; SD = PAL["stone_dark"]
    rect(buf, 11, 12, 10, 14, E)
    rect(buf, 10, 11, 12, 3, ED)
    for y in range(8, 12):
        for x in range(10, 22):
            if y == 8 or y == 9:
                p3(buf, x, y, F)
    ring(buf, 16, 22, 6, 4, F)
    for i in range(12):
        a = i * math.pi / 6
        r = 9 + (i % 2) * 2
        px, py = int(16 + r * math.cos(a)), int(16 + r * math.sin(a))
        if 0 <= px < 32 and 0 <= py < 32:
            p3(buf, px, py, F)
    rect(buf, 13, 24, 6, 4, SD)

def draw_hive_splitter(buf):
    """Small insectoid creature that splits into copies."""
    V = PAL["venom"]; VD = PAL["venom_dark"]; S = PAL["slate"]; AS = PAL["arcane_light"]
    for y in range(10, 22):
        for x in range(10, 22):
            d = math.sqrt((x-16)**2 + (y-16)**2)
            if d < 5:
                if int(d) % 2 == 0:
                    p3(buf, x, y, V)
                else:
                    p3(buf, x, y, VD)
            else:
                p3(buf, x, y, S)
    for i in range(4):
        a = i * math.pi / 2 + math.pi / 4
        px, py = int(16 + 7 * math.cos(a)), int(16 + 7 * math.sin(a))
        if 0 <= px < 32 and 0 <= py < 32:
            p3(buf, px, py, AS)
    circ(buf, 16, 12, 2, PAL["white"])

def draw_rune_runner(buf):
    """Swift runner with glowing rune circles."""
    R = PAL["ember"]; RD = PAL["blood_dark"]; G = PAL["moss"]; AS = PAL["arcane_light"]
    for y in range(10, 22):
        for x in range(10, 22):
            if x == 10 or x == 21 or y == 10 or y == 21:
                p3(buf, x, y, R)
            elif y == 16 and x >= 12 and x <= 20:
                p3(buf, x, y, RD)
    for i in range(3):
        r = 6 + i * 3
        ring(buf, 16, 16, r, r-1, AS if i % 2 == 0 else G)
    circ(buf, 16, 12, 2, PAL["white"])
    for y in range(8, 10):
        p3(buf, 16, y, R)

def draw_deep_summoner(buf):
    """Deep-sea summoner with aquatic energy."""
    W = PAL["water"]; WD = PAL["water_dark"]; A = PAL["arcane"]; AS = PAL["arcane_light"]
    rect(buf, 11, 12, 10, 14, WD)
    rect(buf, 10, 11, 12, 3, W)
    ring(buf, 16, 10, 5, 3, A)
    circ(buf, 16, 10, 2, AS)
    for i in range(6):
        a = i * math.pi / 3
        px, py = int(16 + 7 * math.cos(a)), int(16 + 7 * math.sin(a))
        if 0 <= px < 32 and 0 <= py < 32:
            p3(buf, px, py, A)
    ring(buf, 16, 22, 4, 2, W)
    for y in range(22, 26):
        for x in range(12, 20):
            if x == 12 or x == 19 or y == 25:
                p3(buf, x, y, W)

def draw_tide_shield(buf):
    """Ocean guardian with a large tide shield."""
    T = PAL["water"]; TD = PAL["water_dark"]; SD = PAL["stone_dark"]; B = PAL["bone"]
    rect(buf, 11, 12, 10, 14, T)
    rect(buf, 10, 11, 12, 3, TD)
    ring(buf, 16, 22, 7, 5, T)
    for y in range(7, 12):
        for x in range(9, 23):
            if y == 7 or (y == 8 and x >= 11 and x <= 21):
                p3(buf, x, y, SD)
    ring(buf, 16, 10, 4, 2, B)
    circ(buf, 16, 16, 2, PAL["white"])

def draw_bog_teleporter(buf):
    """Bog-dwelling teleporter with green/murky energy."""
    M = PAL["moss"]; MD = PAL["venom_dark"]; SD = PAL["stone_dark"]
    for y in range(10, 22):
        for x in range(10, 22):
            d = math.sqrt((x-16)**2 + (y-16)**2)
            if d < 5:
                if int(d) % 2 == 0:
                    p3(buf, x, y, M)
                else:
                    p3(buf, x, y, MD)
            else:
                p3(buf, x, y, SD)
    ring(buf, 16, 16, 5, 3, PAL["moss"])
    circ(buf, 16, 16, 2, PAL["white"])
    for i in range(4):
        a = i * math.pi / 2
        px, py = int(16 + 8 * math.cos(a)), int(16 + 8 * math.sin(a))
        if 0 <= px < 32 and 0 <= py < 32:
            p3(buf, px, py, PAL["moss"])


# ------------------------------ VFX SPRITES ------------------------------

def draw_guardian_shield(buf):
    """Directional shield VFX indicator."""
    C = PAL["slate"]; A = PAL["arcane_light"]; SD = PAL["stone_dark"]
    ring(buf, 16, 16, 6, 4, C)
    for y in range(10, 23):
        for x in range(10, 23):
            d = math.sqrt((x-16)**2 + (y-16)**2)
            if d < 5 and d > 3:
                if int(d) % 2 == 0:
                    p3(buf, x, y, A)
    p3(buf, 16, 10, PAL["white"])
    p3(buf, 16, 22, PAL["white"])
    p3(buf, 10, 16, PAL["white"])
    p3(buf, 22, 16, PAL["white"])

def draw_teleport_effect(buf):
    """Smoke/twinkle teleport VFX indicator."""
    A = PAL["arcane"]; AS = PAL["arcane_light"]; SD = PAL["stone_dark"]
    for y in range(10, 23):
        for x in range(10, 23):
            d = math.sqrt((x-16)**2 + (y-16)**2)
            if d < 5:
                if int(d) % 2 == 0:
                    p3(buf, x, y, A)
                else:
                    p3(buf, x, y, AS)
    circ(buf, 16, 16, 2, PAL["white"])
    for i in range(4):
        a = i * math.pi / 2 + math.pi / 4
        px, py = int(16 + 5 * math.cos(a)), int(16 + 5 * math.sin(a))
        if 0 <= px < 32 and 0 <= py < 32:
            p3(buf, px, py, AS)
    p3(buf, 16, 8, PAL["white"])
    p3(buf, 16, 24, PAL["white"])

def draw_leap_slam(buf):
    """Shockwave VFX for charger leap impact."""
    F = PAL["flame"]; ED = PAL["ember_dark"]; E = PAL["ember"]
    ring(buf, 16, 16, 7, 5, F)
    ring(buf, 16, 16, 4, 2, E)
    for i in range(8):
        a = i * math.pi / 4
        r = 9
        px, py = int(16 + r * math.cos(a)), int(16 + r * math.sin(a))
        if 0 <= px < 32 and 0 <= py < 32:
            p3(buf, px, py, F)
    circ(buf, 16, 16, 2, PAL["white"])


# -------------------------------------------------------------------------

DRAW = {
    "monster_summon_skeleton": draw_summon_skeleton,
    "monster_shield_guardian": draw_shield_guardian,
    "monster_phantom_teleporter": draw_phantom_teleporter,
    "monster_charger_brute": draw_charger_brute,
    "monster_hive_splitter": draw_hive_splitter,
    "monster_rune_runner": draw_rune_runner,
    "monster_deep_summoner": draw_deep_summoner,
    "monster_tide_shield": draw_tide_shield,
    "monster_bog_teleporter": draw_bog_teleporter,
    "vfx_guardian_shield": draw_guardian_shield,
    "vfx_teleport_effect": draw_teleport_effect,
    "vfx_leap_slam": draw_leap_slam,
}

def main():
    sd = ROOT / "assets" / "sprites" / "monsters"
    sd.mkdir(parents=True, exist_ok=True)
    vsd = ROOT / "assets" / "sprites" / "vfx"
    vsd.mkdir(parents=True, exist_ok=True)
    
    for name, draw_fn in DRAW.items():
        out = vsd / f"{name}.png" if name.startswith("vfx_") else sd / f"{name}.png"
        make_sprite(name, draw_fn, out)
        print(f"generated: {out.relative_to(ROOT)}")

def make_sprite(name, draw_fn, out_path):
    buf = bytearray(32 * 32 * 3)
    draw_fn(buf)
    from PIL import Image
    img = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    pixels = img.load()
    bad = []
    for y in range(32):
        for x in range(32):
            i = (y * 32 + x) * 3
            r, g, b = buf[i], buf[i+1], buf[i+2]
            if (r, g, b) == (0, 0, 0):
                pixels[x, y] = (0, 0, 0, 0)  # transparent
            else:
                pixels[x, y] = (r, g, b, 255)
                if (r, g, b) not in ALLOWED:
                    bad.append((x, y, (r, g, b)))
    if bad:
        for x, y, c in bad[:5]:
            print(f"WARN {name}: non-palette {c} at ({x},{y})", file=sys.stderr)
    img.save(out_path)
    return out_path

if __name__ == "__main__":
    main()
