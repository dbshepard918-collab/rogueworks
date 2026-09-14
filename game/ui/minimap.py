"""Minimap: revealed rooms, player, stairs, shops."""

import pygame

from ..engine.assets import draw_text
from ..systems.procgen import TILE

MINIMAP_W = 208
MINIMAP_H = 152
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
    if show_frame:
        frame = world.frame("ui_minimap_frame", size=32)
        surface.blit(pygame.transform.scale(frame, (rect.w, rect.h)), (rect.x, rect.y))
    else:
        pygame.draw.rect(surface, (11, 10, 16), rect)

    inner = rect.inflate(-10, -10)
    surface.set_clip(inner)
    scale = min(inner.w / float(level.w), inner.h / float(level.h))
    offset_x = inner.x + (inner.w - level.w * scale) / 2.0
    offset_y = inner.y + (inner.h - level.h * scale) / 2.0

    def to_map(tx, ty):
        return (int(offset_x + tx * scale), int(offset_y + ty * scale))

    for room in level.rooms:
        x, y = to_map(room["x"], room["y"])
        w = max(2, int(room["w"] * scale))
        h = max(2, int(room["h"] * scale))
        kind = room.get("kind", "")
        if kind == "secret":
            # Secret rooms shown differently based on discovery
            if room.revealed or room.get("id", "") in getattr(world, "discovered_secrets", set()):
                colour = (180, 140, 240)  # brighter purple for revealed secrets
            else:
                # Pulsing indicator for undiscovered secret rooms near player
                px = world.player.tile_x if hasattr(world, "player") and world.player else -1
                py = world.player.tile_y if hasattr(world, "player") and world.player else -1
                room_center_x = room["x"] + w // 2
                room_center_y = room["y"] + h // 2
                dist = max(abs(px - room_center_x), abs(py - room_center_y))
                if dist <= 8:
                    colour = (120, 80, 180)  # dimmer purple for nearby undiscovered
                else:
                    colour = (36, 32, 50)  # hidden
        elif room.get("revealed"):
            colour = (87, 80, 112) if kind != "shop" else (180, 140, 240)
        else:
            colour = (36, 32, 50)
        pygame.draw.rect(surface, colour, pygame.Rect(x, y, w, h))

    # Draw cracked wall indicators on minimap
    if hasattr(world, "cracked_walls"):
        for (tx, ty) in world.cracked_walls:
            cx, cy = to_map(tx, ty)
            pygame.draw.rect(surface, (140, 100, 60), pygame.Rect(cx - 1, cy - 1, 3, 3))

    # Draw hidden door indicators on minimap
    if hasattr(world, "hidden_doors"):
        for (tx, ty) in world.hidden_doors:
            cx, cy = to_map(tx, ty)
            # Purple marker for hidden doors, brighter when adjacent to player
            player = world.player
            if player:
                ptx = int(player.x // TILE)
                pty = int(player.y // TILE)
                if abs(ptx - tx) <= 1 and abs(pty - ty) <= 1:
                    colour = (120, 80, 180)  # brighter purple when adjacent
                else:
                    colour = (100, 60, 160)  # dimmer purple
            else:
                colour = (100, 60, 160)
            pygame.draw.rect(surface, colour, pygame.Rect(cx - 1, cy - 1, 3, 3))

    stairs = world.level.stairs_tile
    sx, sy = to_map(stairs[0], stairs[1])
    stairs_colour = (217, 210, 197) if world.stairs_unlocked() else (140, 31, 52)
    pygame.draw.rect(surface, stairs_colour, pygame.Rect(sx - 2, sy - 2, 5, 5))

    player = world.player
    px, py = to_map(player.tile_x, player.tile_y)
    pygame.draw.rect(surface, (232, 178, 60), pygame.Rect(px - 2, py - 2, 4, 4))
    surface.set_clip(None)

    draw_text(surface, "F%d" % world.floor, (rect.x + 6, rect.y + 6), 1, colour=(217, 210, 197))
