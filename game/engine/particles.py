"""Particles and floating damage numbers.  All randomness via the world RNG."""

import math

import pygame

from .assets import FONT, colour
from ..ui.settings import rarity_colour


class ParticleSystem:
    """Bounded, deterministic particle pool plus named VFX sprite flashes."""

    MAX_PARTICLES = 420

    def __init__(self):
        self.items = []
        self.sprites = []          # [{"x","y","name","life","max_life","scale"}]

    def clear(self):
        self.items = []
        self.sprites = []

    def sprite_burst(self, x, y, name, life=0.25, scale=1.0):
        """One-shot VFX frame from the vfx atlas (deterministic, no RNG)."""
        self.sprites.append({"x": x, "y": y, "name": name, "life": life,
                             "max_life": life, "scale": scale})
        if len(self.sprites) > 48:
            self.sprites.pop(0)

    def burst(self, x, y, rng, count=8, color=(232, 178, 60), speed=90.0, life=0.45, size=3, spread=360.0):
        if rng is None:
            return
        room = self.MAX_PARTICLES - len(self.items)
        count = max(0, min(count, room))
        for _ in range(count):
            ang = rng.random() * spread
            spd = speed * (0.35 + rng.random() * 0.9)
            vx, vy = _dir_vec(ang)
            self.items.append({
                "x": x, "y": y,
                "vx": spd * vx, "vy": spd * vy,
                "life": life * (0.6 + rng.random() * 0.7), "max_life": life,
                "color": color, "size": size if rng.random() > 0.3 else max(1, size - 1),
            })

    def trail(self, x, y, rng, count=2, color=(138, 132, 150), life=0.3, size=2):
        if rng is None:
            return
        for _ in range(count):
            if len(self.items) >= self.MAX_PARTICLES:
                return
            self.items.append({
                "x": x + (rng.random() * 8.0 - 4.0), "y": y + (rng.random() * 8.0 - 4.0),
                "vx": rng.random() * 28.0 - 14.0, "vy": rng.random() * 28.0 - 14.0,
                "life": life, "max_life": life, "color": color, "size": size,
            })

    def update(self, dt):
        alive = []
        for p in self.items:
            p["life"] -= dt
            if p["life"] <= 0:
                continue
            p["x"] += p["vx"] * dt
            p["y"] += p["vy"] * dt
            p["vx"] *= (1.0 - min(1.0, 3.0 * dt))
            p["vy"] *= (1.0 - min(1.0, 3.0 * dt))
            alive.append(p)
        self.items = alive
        if self.sprites:
            for s in self.sprites:
                s["life"] -= dt
            self.sprites = [s for s in self.sprites if s["life"] > 0]

    def draw(self, surface, camera):
        ox, oy = camera.world_offset()
        for p in self.items:
            sx = int(p["x"] - ox)
            sy = int(p["y"] - oy)
            if sx < -8 or sy < -8 or sx > camera.view_w + 8 or sy > camera.view_h + 8:
                continue
            size = p["size"]
            fade = max(0.15, min(1.0, p["life"] / max(0.0001, p["max_life"])))
            col = tuple(int(c * (0.45 + 0.55 * fade)) for c in p["color"])
            surface.fill(col, pygame.Rect(sx, sy, size, size))


class DamageNumbers:
    """Floating numbers that rise and fade."""

    def __init__(self):
        self.items = []

    def clear(self):
        self.items = []

    def add(self, x, y, amount, color=(246, 242, 232), scale=2, label=None):
        if len(self.items) > 120:
            self.items.pop(0)
        self.items.append({
            "x": x, "y": y, "vy": -34.0, "life": 0.7, "max_life": 0.7,
            "text": label if label is not None else str(int(amount)),
            "color": color, "scale": scale,
        })

    def update(self, dt):
        alive = []
        for d in self.items:
            d["life"] -= dt
            if d["life"] <= 0:
                continue
            d["y"] += d["vy"] * dt
            d["vy"] += 42.0 * dt
            alive.append(d)
        self.items = alive

    def draw(self, surface, camera, colourblind_mode="off"):
        ox, oy = camera.world_offset()
        for d in self.items:
            sx = int(d["x"] - ox)
            sy = int(d["y"] - oy)
            if sx < -40 or sy < -40 or sx > camera.view_w + 40 or sy > camera.view_h + 40:
                continue
            # P2.6: colourblind-safe rendering
            cb_colour = rarity_colour(d.get("tier", 1), colourblind_mode)
            if d.get("tier", None) is not None:
                text_colour = cb_colour
            else:
                text_colour = d["color"]
            img = FONT.render(d["text"], d["scale"], text_colour)
            sh = FONT.render(d["text"], d["scale"], (11, 10, 16))
            surface.blit(sh, (sx + 1, sy + 1))
            surface.blit(img, (sx, sy))


class FloatingText:
    """Short non-damage messages (level up, item pickup, floor name)."""

    def __init__(self):
        self.items = []

    def add(self, text, color=None, life=2.0):
        self.items.append({"text": text, "life": life, "max_life": life,
                           "color": color or colour("white")})

    def update(self, dt):
        for item in self.items:
            item["life"] -= dt
        self.items = [i for i in self.items if i["life"] > 0]

    def draw(self, surface, x, y, scale=2, line=18):
        for i, item in enumerate(self.items):
            alpha = max(0.0, min(1.0, item["life"] / max(0.01, item["max_life"])))
            col = tuple(int(c * (0.35 + 0.65 * alpha)) for c in item["color"])
            img = FONT.render(item["text"], scale, col)
            surface.blit(img, (x - img.get_width() // 2, y + i * line))


def _dir_vec(deg):
    rad = math.radians(deg)
    return (math.cos(rad), math.sin(rad))
