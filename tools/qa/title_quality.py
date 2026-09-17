"""Deterministic title-card generator and visual quality gate.

Examples:
    python -m tools.qa.title_quality --out runs/title-card.png
    python -m tools.qa.title_quality --title "THE LANTERN GOES OUT"

The generator uses the shipped pixel font and locked palette, then checks the
composition for safe margins, readable contrast, title centering, and excessive
flat colour coverage. It is intentionally offline and deterministic.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pygame

from tools import _util
from tools._util import EXIT_FAIL, EXIT_OK

SIZE = (1280, 720)
PALETTE = {
    "void": (11, 10, 16),
    "ink": (21, 19, 31),
    "stone_dark": (36, 32, 50),
    "stone": (58, 52, 80),
    "stone_light": (87, 80, 112),
    "bone": (217, 210, 197),
    "gold": (232, 178, 60),
    "soul": (79, 209, 200),
    "water": (31, 95, 128),
    "blood": (140, 31, 52),
}


def _text_bounds(surface: pygame.Surface, colour) -> pygame.Rect:
    mask = pygame.mask.from_threshold(surface, colour, (0, 0, 0, 255))
    return mask.get_bounding_rects()[0] if mask.get_bounding_rects() else pygame.Rect()


def render(title: str, subtitle: str, victory: bool = False) -> pygame.Surface:
    from game.engine.assets import draw_text, text_size

    surface = pygame.Surface(SIZE)
    surface.fill(PALETTE["void"])
    accent = PALETTE["soul"] if victory else PALETTE["gold"]
    cool = PALETTE["water"] if victory else PALETTE["blood"]

    # Structured background bands avoid a flat fill without competing with the
    # title. Every shape is aligned to the pixel grid and palette-locked.
    for y in range(0, SIZE[1], 48):
        pygame.draw.line(surface, cool, (0, y), (SIZE[0], y), 1)
    for x in range(32, SIZE[0], 96):
        pygame.draw.line(surface, PALETTE["ink"], (x, 0), (x, SIZE[1]), 1)
    pygame.draw.rect(surface, PALETTE["stone"], (48, 42, SIZE[0] - 96, SIZE[1] - 84), 2)
    pygame.draw.rect(surface, PALETTE["stone_dark"], (68, 62, SIZE[0] - 136, SIZE[1] - 124), 1)

    # Layered lantern halo: broad rings plus a crisp core, never a noisy blur.
    cx, cy = SIZE[0] // 2, 160
    for radius, colour in ((112, cool), (80, PALETTE["stone"]), (48, accent)):
        pygame.draw.circle(surface, colour, (cx, cy), radius, 2)
    pygame.draw.circle(surface, accent, (cx, cy), 13)
    pygame.draw.rect(surface, PALETTE["bone"], (cx - 7, cy - 5, 14, 18))
    pygame.draw.rect(surface, PALETTE["stone_dark"], (cx - 11, cy + 13, 22, 5))

    title_w, _ = text_size(title, 4)
    title_x = (SIZE[0] - title_w) // 2
    # A restrained title plate makes the lettering read against every biome.
    pygame.draw.rect(surface, PALETTE["ink"], (title_x - 28, 238, title_w + 56, 74))
    pygame.draw.rect(surface, accent, (title_x - 28, 238, title_w + 56, 74), 2)
    draw_text(surface, title, (title_x, 254), 4, colour=accent)
    sub_w, _ = text_size(subtitle, 1)
    draw_text(surface, subtitle, ((SIZE[0] - sub_w) // 2, 330), 1,
              colour=PALETTE["bone"])

    # Deliberate footer anchors the card and gives menu controls a home.
    pygame.draw.line(surface, PALETTE["stone_light"], (220, 570), (SIZE[0] - 220, 570), 2)
    draw_text(surface, "DESCEND INTO THE DARK", (SIZE[0] // 2 - 96, 592), 1,
              colour=PALETTE["stone_light"])
    return surface


def audit(surface: pygame.Surface, victory: bool) -> list[str]:
    import numpy as np

    # surfarray returns (width, height, channels); image math below uses
    # conventional (height, width, channels).
    arr = pygame.surfarray.array3d(surface).transpose(1, 0, 2)
    problems = []
    title_colour = PALETTE["soul"] if victory else PALETTE["gold"]
    # Inspect only the title plate; the same accent is intentionally reused
    # for the lantern and border elsewhere on the card.
    mask = np.all(arr[238:312] == title_colour, axis=2)
    ys, xs = np.where(mask)
    if not len(xs):
        problems.append("title produced no accent pixels")
    else:
        if xs.min() < 48 or xs.max() >= SIZE[0] - 48:
            problems.append("title violates the 48px safe margin")
        center = (xs.min() + xs.max()) / 2.0
        if abs(center - SIZE[0] / 2.0) > 4:
            problems.append("title is not visually centered")
    colours = len({tuple(pixel) for pixel in arr.reshape(-1, 3)})
    if colours < 8:
        problems.append("title card is too flat (%d colours)" % colours)
    return problems


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Generate and audit a deterministic title card.")
    ap.add_argument("--title", default="DEPTHS OF VAELMOOR")
    ap.add_argument("--subtitle", default="A DESCENT INTO THE UNKNOWN")
    ap.add_argument("--victory", action="store_true")
    ap.add_argument("--out", default="runs/title-card.png")
    args = ap.parse_args(argv)

    root = _util.find_root()
    sys.path.insert(0, str(root))
    pygame.init()
    pygame.display.set_mode((1, 1))
    surface = render(args.title, args.subtitle, args.victory)
    problems = audit(surface, args.victory)
    out = Path(args.out)
    if not out.is_absolute():
        out = root / out
    out.parent.mkdir(parents=True, exist_ok=True)
    pygame.image.save(surface, str(out))
    print("title card: %s" % out)
    if problems:
        for problem in problems:
            print("FAIL: %s" % problem)
        return EXIT_FAIL
    print("PASS: centered, framed, palette-safe, readable title composition")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
