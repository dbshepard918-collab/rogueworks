"""Menus: main, meta-upgrade shop, death and victory screens, pause.

P1.3 — the meta shop now renders the 5-branch tree with prerequisites, disabled
reasons, and a respec option.  The flat 6-row layout is replaced by a
branch-grouped layout; legacy draw_meta_shop callers that only read
``rows[i]["price"]`` / ``rows[i]["level"]`` / ``rows[i]["affordable"]`` keep
working because those keys are still present.

P4.5 — animated title screen with pulsing lantern effect, categorized
settings screen, pause with run stats.
"""

import math
import pygame

from ..engine.assets import Atlas, draw_text, text_size, load_palette
from ..engine.renderer import Renderer

BUTTON_W = 240
BUTTON_H = 30


def draw_title(surface, title, subtitle=None, y=120):
    draw_text(surface, title, ((surface.get_width() - text_size(title, 4)[0]) // 2, y), 4,
              colour=(232, 178, 60))
    if subtitle:
        draw_text(surface, subtitle, ((surface.get_width() - text_size(subtitle, 1)[0]) // 2, y + 44),
                  1, colour=(138, 132, 150))


def draw_title_animated(surface, title, subtitle=None, y=110, frame_idx=0, pulse=0.5):
    """Draw the animated title with a pulsing lantern effect.

    P4.5: renders the title text with a warm lantern glow that pulses,
    plus a title animation sprite (ui_title_frame_N) that cycles.
    """
    from game.engine.assets import Atlas
    w = surface.get_width()
    title_col = (232, 178, 60)
    # Pulse the title colour brightness
    r = int(232 * (0.7 + 0.3 * pulse))
    g = int(178 * (0.7 + 0.3 * pulse))
    b = int(60 * (0.7 + 0.3 * pulse))
    title_colour = (r, g, b)
    draw_text(surface, title, ((w - text_size(title, 4)[0]) // 2, y), 4,
              colour=title_colour)
    # Draw the title animation sprite (lantern) above the title
    try:
        atlas = Atlas.load("ui")
        frame_name = "ui_title_frame_%d" % (frame_idx % 8)
        if atlas.has(frame_name):
            frame_surf = atlas.frame(frame_name)
            title_top = y - 8 - frame_surf.get_height()
            surface.blit(frame_surf, ((w - frame_surf.get_width()) // 2, title_top))
    except Exception:
        pass
    if subtitle:
        sub_colour = (138, 132, 150)
        draw_text(surface, subtitle, ((w - text_size(subtitle, 1)[0]) // 2, y + 44), 1,
                  colour=sub_colour)


class ListMenu:
    """A simple vertical list menu with index selection and enable/disable per entry.

    Used by the pause menu, main menu and end screen.  Entry format::

        (key, label, enabled)

    where *key* is an arbitrary identifier, *label* is the display string and
    *enabled* is a bool.
    """

    def __init__(self, entries):
        self.entries = list(entries)
        self.index = 0

    def move(self, delta):
        if not self.entries:
            return
        self.index = (self.index + delta) % len(self.entries)

    def enabled_current(self):
        if not self.entries:
            return None
        return self.entries[self.index]


def draw_list(surface, menu, top=280, line=30, extra_labels=None):
    for i, (key, label, enabled) in enumerate(menu.entries):
        text = label if not extra_labels else label % extra_labels.get(key, ())
        col = (246, 242, 232) if enabled else (93, 98, 114)
        x = (surface.get_width() - text_size(text, 2)[0]) // 2
        if i == menu.index:
            draw_text(surface, ">", (x - 24, top + i * line), 2, colour=(232, 178, 60))
            col = (232, 178, 60) if enabled else col
        draw_text(surface, text, (x, top + i * line), 2, colour=col)


def draw_panel(surface, rect, alpha=225):
    panel = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
    panel.fill((15, 13, 22, alpha))
    pygame.draw.rect(panel, (58, 52, 80), pygame.Rect(0, 0, rect.w, rect.h), 2)
    surface.blit(panel, (rect.x, rect.y))


def _branch_header(surface, x, y, color, name, purchased, max_tier):
    col = tuple(int(c) for c in color)
    draw_text(surface, name.upper(), (x, y), 2, colour=col)
    draw_text(surface, "  %d/%d" % (purchased, max_tier), (x + text_size(name.upper(), 2)[0] + 10, y + 2),
              1, colour=(138, 132, 150))


def _tier_line(surface, x, y, row, selected, highlight):
    branch_color = tuple(int(c) for c in row["branch_color"])
    # owned
    if row["owned"]:
        col = (79, 209, 200)
        prefix = "  [OK] "
    elif not row["affordable"]:
        col = (93, 98, 114)
        if row["prereq_missing"]:
            prefix = "  [LOCK] "
        else:
            prefix = "  [%d] " % row["cost"]
    else:
        col = (232, 178, 60) if highlight else (246, 242, 232)
        prefix = "  [%d] " % row["cost"]

    if selected:
        draw_text(surface, ">", (x - 22, y), 1, colour=(232, 178, 60))

    draw_text(surface, prefix, (x, y), 1, colour=col)
    label = row["label"]
    lw = text_size(label, 1, spacing=1)[0]
    draw_text(surface, label, (x + text_size(prefix, 1)[0], y), 1, colour=col, spacing=1)
    # description to the right
    if row["desc"]:
        desc = row["desc"]
        dw = text_size(desc, 1)[0]
        draw_text(surface, desc, (x + 330, y), 1, colour=(138, 132, 150))


def draw_meta_shop(surface, profile, rows, selected, essence, stat_totals):
    draw_title(surface, "META UPGRADES", "essence %d" % essence, y=52)
    rect = pygame.Rect(60, 96, 1160, 540)
    draw_panel(surface, rect)

    x = rect.x + 24
    y = rect.y + 20
    branch_purchased = {}
    # first pass: count purchased per branch for the header
    for row in rows:
        bid = row["branch_id"]
        branch_purchased[bid] = branch_purchased.get(bid, 0) + (1 if row["owned"] else 0)

    last_branch = None
    line = 0
    branch_max = {}
    for row in rows:
        bid = row["branch_id"]
        branch_max[bid] = row["max_level"]
    for row in rows:
        if row["branch_id"] != last_branch:
            # branch header
            _branch_header(surface, x, y, row["branch_color"], row["branch_name"],
                           branch_purchased.get(row["branch_id"], 0), row["max_level"])
            y += 26
            last_branch = row["branch_id"]
            line = 0
        _tier_line(surface, x, y, row, selected == line, highlight=(selected == line))
        y += 20
        line += 1

    y += 14
    draw_text(surface, "current stat bonuses", (rect.x + 24, y), 1, colour=(138, 132, 150))


def draw_pause(surface, menu):
    draw_list(surface, menu, top=300)
    draw_text(surface, "ESC to resume", (surface.get_width() // 2, surface.get_height() - 40),
              1, colour=(93, 98, 114))


# ------------------------------------------------------- end screen (P3.5) -----
DEATH_TITLE = "THE LANTERN GOES OUT"
VICTORY_TITLE = "THE LANTERN STILL BURNS"


def _monster_name(world, monster_id):
    """Best-effort display name for a monster id (falls back to the raw id)."""
    try:
        entry = world.content.monster(monster_id)
        if entry:
            return str(entry.get("name") or monster_id)
    except Exception:
        pass
    return str(monster_id)


def _recap_lines(world, profile):
    """(label, value) rows for the run recap panel."""
    rooms = int(getattr(world, "rooms_visited", 0))
    cause = str(getattr(world, "death_cause", "") or "still standing")
    biome = str(getattr(world, "biome_name", "") or getattr(world, "biome_id", ""))
    return [
        ("SEED", "%d" % int(getattr(world, "seed", 0))),
        ("DEPTH", "floor %d - %s" % (int(getattr(world, "floor", 1)), biome)),
        ("ROOMS", "%d cleared" % rooms),
        ("KILLS", "%d" % int(getattr(world, "kills_run", 0))),
        ("ESSENCE", "%d banked" % int(getattr(world, "essence_run", 0))),
        ("FATE", cause),
    ]


def _history_lines(profile, world, limit=3):
    """Last few runs, newest first, with the just-finished run at the top."""
    history = list(profile.get("run_history", []) or [])
    entries = history[-limit:]
    lines = []
    for run in reversed(entries):
        lines.append("seed %-6s floor %-3s rooms %-3s  %s"
                     % (run.get("seed", "?"), run.get("floor", "?"),
                        run.get("rooms", "?"), run.get("death_cause", "")))
    return lines


def draw_end_screen(surface, world, victory, profile, menu):
    """Death / victory summary (P3.5 run storytelling).

    Renders the death recap the player actually earned: how they died and how
    far they got, what the run added to the codex, the bestiary leaders, and
    the last few runs.  Must never raise - a crash on death is the worst
    possible bug, so every lookup is defensive.
    """
    profile = profile or {}

    title = VICTORY_TITLE if victory else DEATH_TITLE
    subtitle = ("depth %d reached - %s" % (int(getattr(world, "floor", 1)),
                                           str(getattr(world, "biome_name", "") or ""))).strip(" -")
    draw_title(surface, title, subtitle, y=34)

    # -- run recap ---------------------------------------------------------
    left = pygame.Rect(60, 108, 560, 268)
    draw_panel(surface, left)
    draw_text(surface, "RUN RECAP", (left.x + 22, left.y + 16), 2, colour=(232, 178, 60))
    y = left.y + 56
    for label, value in _recap_lines(world, profile):
        draw_text(surface, label, (left.x + 22, y), 1, colour=(138, 132, 150))
        draw_text(surface, value, (left.x + 150, y), 1, colour=(246, 242, 232))
        y += 30

    # -- codex + bestiary --------------------------------------------------
    right = pygame.Rect(660, 108, 560, 268)
    draw_panel(surface, right)
    codex = profile.get("codex", {}) or {}
    seen = sum(1 for entry in codex.values() if isinstance(entry, dict) and entry.get("seen"))
    total = 0
    try:
        total = len(world.content.monsters()) + len(world.content.items())
    except Exception:
        total = 0
    draw_text(surface, "CODEX", (right.x + 22, right.y + 16), 2, colour=(79, 209, 200))
    draw_text(surface, "%d / %d discoveries logged" % (seen, total or seen),
              (right.x + 22, right.y + 52), 1, colour=(246, 242, 232))

    draw_text(surface, "BESTIARY - MOST HUNTED", (right.x + 22, right.y + 92), 1,
              colour=(138, 132, 150))
    bestiary = profile.get("bestiary", {}) or {}
    top = sorted(((k, int(v)) for k, v in bestiary.items() if isinstance(v, (int, float))),
                 key=lambda kv: (-kv[1], str(kv[0])))[:3]
    y = right.y + 122
    if not top:
        draw_text(surface, "no kills recorded yet", (right.x + 22, y), 1,
                  colour=(93, 98, 114))
    for monster_id, count in top:
        draw_text(surface, _monster_name(world, monster_id), (right.x + 22, y), 1,
                  colour=(246, 242, 232))
        draw_text(surface, "x%d" % count, (right.x + 470, y), 1, colour=(232, 178, 60))
        y += 28

    # -- run history -------------------------------------------------------
    hist = pygame.Rect(60, 392, 1160, 132)
    draw_panel(surface, hist)
    draw_text(surface, "RECENT DESCENTS", (hist.x + 22, hist.y + 14), 1, colour=(138, 132, 150))
    lines = _history_lines(profile, world)
    if not lines:
        draw_text(surface, "this was the first descent", (hist.x + 22, hist.y + 46), 1,
                  colour=(93, 98, 114))
    y = hist.y + 46
    for line in lines:
        draw_text(surface, line, (hist.x + 22, y), 1, colour=(246, 242, 232))
        y += 26

    draw_list(surface, menu, top=556, line=28)


def draw_controls(surface, profile=None):
    """Draw current key bindings as a small hint on the title screen.

    P4.5: shows the active key bindings read from settings, so the player
    always knows which keys to press even before starting a run.
    """
    from game.ui.settings import DEFAULT_KEY_MAP, ACTION_LABELS
    settings = (profile or {}).get("settings", {}) if profile else {}
    key_map = settings.get("key_map", {}) or {}
    w = surface.get_width()
    y = surface.get_height() - 60
    draw_text(surface, "CONTROLS", (w // 2 - text_size("CONTROLS", 1)[0] // 2, y - 20),
              1, colour=(138, 132, 150))
    col = (232, 178, 60)
    # Show movement + a few key actions in a compact row
    action_order = ["move_up", "move_down", "move_left", "move_right", "attack", "dash", "interact", "inventory"]
    parts = []
    for action in action_order:
        key_code = key_map.get(action, DEFAULT_KEY_MAP.get(action))
        label = ACTION_LABELS.get(action, action)
        # Convert pygame key constant to a short name
        key_name = _key_name(key_code)
        parts.append("%s: %s" % (label.split(" / ")[0], key_name))
    line_text = "  |  ".join(parts)
    draw_text(surface, line_text, ((w - text_size(line_text, 1)[0]) // 2, y),
              1, colour=col)


def _key_name(key_code):
    """Convert a pygame key constant to a short human-readable name."""
    import pygame
    names = {
        pygame.K_w: "W", pygame.K_s: "S", pygame.K_a: "A", pygame.K_d: "D",
        pygame.K_SPACE: "SPACE", pygame.K_LSHIFT: "SHIFT", pygame.K_e: "E",
        pygame.K_TAB: "TAB", pygame.K_ESCAPE: "ESC",
    }
    return names.get(key_code, str(key_code))
