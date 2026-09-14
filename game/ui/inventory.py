"""Inventory overlay (TAB): equipment, backpack, consumables, tooltips."""

import pygame

from ..engine.assets import draw_text
from .tooltips import draw_item_tooltip

PANEL = pygame.Rect(240, 90, 800, 540)
SLOT = 64
SLOT_GAP = 12


class InventoryOverlay:
    """Read-mostly overlay; 1-4 quaff consumables, TAB/ESC closes."""

    def __init__(self):
        self.open = False
        self.hover = None
        self.message = ""

    def toggle(self):
        self.open = not self.open

    def handle_key(self, world, key):
        if key in (pygame.K_TAB, pygame.K_ESCAPE):
            self.open = False
            return True
        if pygame.K_1 <= key <= pygame.K_4:
            index = key - pygame.K_1
            pool = world.player.consumables
            if index < len(pool):
                world.use_consumable(index)
            else:
                self.message = "no consumable in that slot"
            return True
        return False

    def draw(self, world, surface):
        if not self.open:
            return
        player = world.player
        panel = pygame.Surface((PANEL.w, PANEL.h), pygame.SRCALPHA)
        panel.fill((15, 13, 22, 240))
        pygame.draw.rect(panel, (58, 52, 80), pygame.Rect(0, 0, PANEL.w, PANEL.h), 2)
        surface.blit(panel, (PANEL.x, PANEL.y))
        draw_text(surface, "KEEPER'S KIT", (PANEL.x + 20, PANEL.y + 16), 2, colour=(232, 178, 60))

        # -- equipment ---------------------------------------------------
        draw_text(surface, "EQUIPPED", (PANEL.x + 24, PANEL.y + 56), 1, colour=(138, 132, 150))
        hover_item = None
        hover_rect = None
        for i, slot in enumerate(("weapon", "armor", "trinket")):
            rect = pygame.Rect(PANEL.x + 24, PANEL.y + 74 + i * (SLOT + SLOT_GAP), SLOT, SLOT)
            self._slot(surface, world, rect, player.equipment.get(slot), slot)
            if rect.collidepoint(pygame.mouse.get_pos()) and player.equipment.get(slot):
                hover_item = player.equipment[slot]
                hover_rect = rect

        # -- backpack ----------------------------------------------------
        draw_text(surface, "BACKPACK", (PANEL.x + 140, PANEL.y + 56), 1, colour=(138, 132, 150))
        for i in range(8):
            col = i % 4
            row = i // 4
            rect = pygame.Rect(PANEL.x + 140 + col * (SLOT + SLOT_GAP),
                               PANEL.y + 74 + row * (SLOT + SLOT_GAP), SLOT, SLOT)
            item = player.backpack[i] if i < len(player.backpack) else None
            self._slot(surface, world, rect, item, None)
            if item and rect.collidepoint(pygame.mouse.get_pos()):
                hover_item = item
                hover_rect = rect

        # -- consumables -------------------------------------------------
        draw_text(surface, "FLASKS (1-4)", (PANEL.x + 456, PANEL.y + 56), 1, colour=(138, 132, 150))
        for i in range(4):
            rect = pygame.Rect(PANEL.x + 456, PANEL.y + 74 + i * (44 + 6), 40, 40)
            item = player.consumables[i] if i < len(player.consumables) else None
            self._slot(surface, world, rect, item, "%d" % (i + 1))
            if item and rect.collidepoint(pygame.mouse.get_pos()):
                hover_item = item
                hover_rect = rect

        # -- stats -------------------------------------------------------
        x = PANEL.x + 540
        y = PANEL.y + 74
        draw_text(surface, "STATS", (x, y - 18), 1, colour=(138, 132, 150))
        stats = player.stats.snapshot()
        rows = [("HP", "%d" % int(round(stats["max_hp"]))),
                ("DMG", "%d" % int(round(stats["damage"]))),
                ("ARM", "%d%%" % int(round(stats["armor"] * 100))),
                ("SPD", "%.2f" % stats["speed"]),
                ("CRIT", "%d%%" % int(round(stats["crit"] * 100))),
                ("LUCK", "%d" % int(round(stats["luck"]))),
                ("KILLS", "%d" % player.kills),
                ("FLOOR", "%d" % world.floor)]
        for key, value in rows:
            draw_text(surface, key, (x, y), 1, colour=(138, 132, 150))
            draw_text(surface, value, (x + 70, y), 1, colour=(246, 242, 232))
            y += 14

        if self.message:
            draw_text(surface, self.message, (PANEL.x + 24, PANEL.y + PANEL.h - 26), 1,
                      colour=(196, 99, 95))
        else:
            draw_text(surface, "TAB closes   1-4 drink", (PANEL.x + 24, PANEL.y + PANEL.h - 26), 1,
                      colour=(93, 98, 114))

        if hover_item is not None:
            draw_item_tooltip(surface, hover_item, hover_rect.right + 10, hover_rect.top)

    def _slot(self, surface, world, rect, item, label):
        frame = world.frame("ui_slot", size=32)
        surface.blit(pygame.transform.scale(frame, (rect.w, rect.h)), (rect.x, rect.y))
        if item is not None:
            icon = pygame.transform.scale(world.frame(item.get("sprite", "prop_backpack"), size=32),
                                          (rect.w - 12, rect.h - 12))
            surface.blit(icon, (rect.x + 6, rect.y + 6))
            rarity = tuple(item.get("rarity_color") or (217, 210, 197))
            pygame.draw.rect(surface, rarity, pygame.Rect(rect.x, rect.y, rect.w, 2))
        if label:
            draw_text(surface, label, (rect.x + 2, rect.y + 2), 1, colour=(138, 132, 150))
