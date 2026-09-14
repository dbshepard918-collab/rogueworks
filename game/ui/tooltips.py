"""Item tooltips: rarity colour, stats, affixes, flavour."""

import pygame

from ..engine.assets import draw_text, text_size

STAT_LABELS = {
    "damage": "DMG",
    "armor": "ARM",
    "max_hp": "HP",
    "speed": "SPD",
    "luck": "LUCK",
    "crit": "CRIT",
}


def _fmt(stat, value):
    if stat == "crit":
        return "%s +%d%%" % (STAT_LABELS[stat], int(round(float(value) * 100)))
    if stat == "armor":
        return "%s +%.0f%%" % (STAT_LABELS[stat], float(value) * 300.0 / 100.0 * 100 / 3)
    if stat == "speed":
        return "%s +%.2f" % (STAT_LABELS[stat], float(value))
    return "%s +%d" % (STAT_LABELS[stat], int(round(float(value))))


def stat_lines(item):
    lines = []
    for stat, value in (item.get("effect") or {}).items():
        lines.append(_fmt(stat, value))
    for affix in item.get("affixes") or []:
        for stat, value in (affix.get("effect") or {}).items():
            lines.append("%s (%s)" % (_fmt(stat, value), affix.get("name", "?")))
    return lines


def tooltip_size(item):
    lines = ["%s" % (item.get("display") or item.get("name", "item")),
             "%s  T%d  %s" % (item.get("slot", "?").upper(), int(item.get("tier", 1)),
                              (item.get("rarity_name") or item.get("rarity", "common")).upper())]
    lines += stat_lines(item)
    value = "value %d gold" % int(item.get("value", 0))
    lines.append(value)
    if item.get("flavor"):
        lines.append(item["flavor"])
    width = max(text_size(line, 1)[0] for line in lines) + 16
    height = len(lines) * 12 + 12
    return (width, height)


def draw_item_tooltip(surface, item, x, y, screen_size=(1280, 720)):
    """Draw a tooltip at (x, y), clamped to the screen."""
    width, height = tooltip_size(item)
    x = max(4, min(x, screen_size[0] - width - 4))
    y = max(4, min(y, screen_size[1] - height - 4))
    panel = pygame.Surface((width, height), pygame.SRCALPHA)
    panel.fill((21, 19, 31, 238))
    pygame.draw.rect(panel, (58, 52, 80), pygame.Rect(0, 0, width, height), 1)
    rarity = tuple(item.get("rarity_color") or (217, 210, 197))
    pygame.draw.rect(panel, rarity, pygame.Rect(0, 0, width, 2))
    surface.blit(panel, (x, y))

    ty = y + 6
    draw_text(surface, "%s" % (item.get("display") or item.get("name", "item")),
              (x + 8, ty), 1, colour=(246, 242, 232))
    ty += 12
    draw_text(surface, "%s  T%d  %s" % (item.get("slot", "?").upper(), int(item.get("tier", 1)),
                                        (item.get("rarity_name") or "Common").upper()),
              (x + 8, ty), 1, colour=rarity)
    ty += 12
    for line in stat_lines(item):
        draw_text(surface, line, (x + 8, ty), 1, colour=(121, 176, 74))
        ty += 12
    draw_text(surface, "value %d gold" % int(item.get("value", 0)), (x + 8, ty), 1,
              colour=(232, 178, 60))
    ty += 12
    if item.get("flavor"):
        draw_text(surface, item["flavor"][:44], (x + 8, ty), 1, colour=(138, 132, 150))
    return pygame.Rect(x, y, width, height)
