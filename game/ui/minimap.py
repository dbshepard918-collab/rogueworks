"""Minimap: revealed rooms, player, stairs, shops."""

import pygame

from ..engine.assets import draw_text
from ..systems.procgen import TILE

MINIMAP_W = 160
MINIMAP_H = 120
MARGIN = 12


def minimap_rect(screen_size=(1280, 720)):
    return pygame.Rect(screen_size[0] - MINIMAP_W - MARGIN,
                       screen_size[1] - MINIMAP_H - MARGIN,
                       MINIMAP_W, MINIMAP_H)


def draw_minimap(world, surface, screen_size=(1280, 720), show_frame=True):
    level = world.level
    if level is None:
        return
    rect = minimap_rect(screen_size)
    if getattr(world, "no_minimap", False):
        if show_frame:
            frame = world.frame("ui_minimap_frame", size=32)
            surface.blit(pygame.transform.scale(frame, (rect.w, rect.h)), (rect.x, rect.y))
        overlay = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
        overlay.fill((11, 10, 16, 200))
        surface.blit(overlay, (rect.x, rect.y))
        draw_text(surface, "MINIMAP LOST", (rect.x + rect.w // 2 - 44, rect.y + rect.h // 2 - 6), 1, colour=(196, 99, 95))
        return
    panel = pygame.Surface(rect.size, pygame.SRCALPHA)
    panel.fill((11, 10, 16, 232))
    pygame.draw.rect(panel, (87, 80, 112), panel.get_rect(), 2)
    pygame.draw.line(panel, (232, 178, 60), (2, 2), (36, 2), 2)
    surface.blit(panel, rect.topleft)

    inner = rect.inflate(-12, -12)
    surface.set_clip(inner)

    # Dynamic bounding box: frame active rooms and points of interest tightly
    xs = []
    ys = []
    for room in level.rooms:
        rx = int(room.get("x", 0))
        ry = int(room.get("y", 0))
        rw = int(room.get("w", 8))
        rh = int(room.get("h", 8))
        xs.extend([rx, rx + rw])
        ys.extend([ry, ry + rh])
    if level.stairs_tile:
        xs.append(level.stairs_tile[0])
        ys.append(level.stairs_tile[1])
    player = world.player if hasattr(world, "player") else None
    if player:
        xs.append(int(player.tile_x))
        ys.append(int(player.tile_y))

    if xs and ys:
        pad = 2
        min_x = max(0, min(xs) - pad)
        min_y = max(0, min(ys) - pad)
        max_x = min(level.w, max(xs) + pad)
        max_y = min(level.h, max(ys) + pad)
        span_w = max(1, max_x - min_x)
        span_h = max(1, max_y - min_y)
    else:
        min_x, min_y = 0, 0
        span_w, span_h = level.w, level.h

    scale = min(inner.w / float(span_w), inner.h / float(span_h))
    offset_x = inner.x + (inner.w - span_w * scale) / 2.0 - min_x * scale
    offset_y = inner.y + (inner.h - span_h * scale) / 2.0 - min_y * scale

    def to_map(tx, ty):
        return (int(offset_x + tx * scale), int(offset_y + ty * scale))

    ptx = int(player.tile_x) if player else -1
    pty = int(player.tile_y) if player else -1

    for room in level.rooms:
        rx = int(room.get("x", 0))
        ry = int(room.get("y", 0))
        rw = int(room.get("w", 8))
        rh = int(room.get("h", 8))
        x, y = to_map(rx, ry)
        w = max(2, int(rw * scale))
        h = max(2, int(rh * scale))
        kind = room.get("kind", "")
        is_revealed = bool(room.get("revealed") or getattr(room, "revealed", False))

        if kind == "secret":
            # Secret rooms shown differently based on discovery
            if is_revealed or room.get("id", "") in getattr(world, "discovered_secrets", set()):
                colour = (180, 140, 240)  # brighter purple for revealed secrets
                border_col = (220, 190, 255)
            else:
                # Pulsing indicator for undiscovered secret rooms near player
                room_center_x = rx + rw // 2
                room_center_y = ry + rh // 2
                dist = max(abs(ptx - room_center_x), abs(pty - room_center_y))
                if dist <= 8:
                    colour = (120, 80, 180)  # dimmer purple for nearby undiscovered
                    border_col = (140, 100, 200)
                else:
                    colour = (36, 32, 50)  # hidden
                    border_col = None
        elif is_revealed:
            colour = (87, 80, 112) if kind != "shop" else (180, 140, 240)
            border_col = (120, 112, 148)
        else:
            colour = (36, 32, 50)
            border_col = None

        pygame.draw.rect(surface, colour, pygame.Rect(x, y, w, h))
        if border_col:
            pygame.draw.rect(surface, border_col, pygame.Rect(x, y, w, h), 1)

        # Highlight current room player is inside
        if is_revealed and rx <= ptx < rx + rw and ry <= pty < ry + rh:
            pygame.draw.rect(surface, (232, 178, 60), pygame.Rect(x, y, w, h), 1)

    # Draw cracked wall indicators on minimap
    if hasattr(world, "cracked_walls"):
        for (tx, ty) in world.cracked_walls:
            cx, cy = to_map(tx, ty)
            pygame.draw.rect(surface, (140, 100, 60), pygame.Rect(cx - 1, cy - 1, 3, 3))

    # Draw hidden door indicators on minimap
    if hasattr(world, "hidden_doors"):
        for (tx, ty) in world.hidden_doors:
            cx, cy = to_map(tx, ty)
            if player and abs(ptx - tx) <= 1 and abs(pty - ty) <= 1:
                colour = (180, 140, 240)  # brighter purple when adjacent
            else:
                colour = (100, 60, 160)  # dimmer purple
            pygame.draw.rect(surface, colour, pygame.Rect(cx - 1, cy - 1, 3, 3))

    stairs = world.level.stairs_tile
    sx, sy = to_map(stairs[0], stairs[1])
    stairs_colour = (217, 210, 197) if world.stairs_unlocked() else (140, 31, 52)
    pygame.draw.rect(surface, stairs_colour, pygame.Rect(sx - 2, sy - 2, 5, 5))

    if player:
        px, py = to_map(player.tile_x, player.tile_y)
        pygame.draw.rect(surface, (232, 178, 60), pygame.Rect(px - 2, py - 2, 4, 4))

    surface.set_clip(None)

    draw_text(surface, "MAP F%d" % world.floor, (rect.x + 6, rect.y + 5), 1,
              colour=(217, 210, 197))
