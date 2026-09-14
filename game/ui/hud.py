"""HUD: HP/XP bars, essence, floor label, status icons, ability cooldowns.

P3.2 Secrets: cracked wall interaction prompt, secret room count.
"""

import math

import pygame

from ..engine.assets import draw_text, text_size
from ..ui.settings import rarity_colour
from game.systems.procgen import TILE

BAR_W = 240
BAR_H = 18
PANEL = pygame.Rect(10, 10, 320, 84)
FONT_SCALE = 1


class HUD:
    """Draws the in-run heads-up display.

    P3.2: includes cracked wall interaction prompt and secret room count.
    """

    def __init__(self):
        self.wobble = 0.0
        self._scaled = {}
        self.font_scale = 1
        self.settings = {}

    def _img(self, world, name, size):
        key = (name, size)
        img = self._scaled.get(key)
        if img is None:
            img = pygame.transform.scale(world.frame(name, size=32), size)
            self._scaled[key] = img
        return img

    def update(self, world, dt):
        player = world.player
        target = 1.0 if player.last_damage_taken > 0 else 0.0
        self.wobble += (target - self.wobble) * min(1.0, dt * 10.0)
        self.shake_enabled = world.camera.shake_enabled
        self.settings = getattr(world, "settings", {}) or {}
        self.font_scale = self.settings.get("font_scale", 1)

    def draw(self, world, surface):
        player = world.player
        self.settings = getattr(world, "settings", {}) or {}
        fs = self.settings.get("font_scale", 1)
        self.font_scale = fs
        panel_w = PANEL.w * fs
        panel_h = PANEL.h * fs
        panel_rect = pygame.Rect(PANEL.x, PANEL.y, panel_w, panel_h)
        self._panel(surface, panel_rect)

        cb_mode = self.settings.get("colourblind_mode", "off")
        wobble_x = int(math.sin(world.time * 26.0) * 4.0 * self.wobble)
        bar_x = 24 + wobble_x

        self._bar(world, surface, "ui_hp_frame", "ui_hp_fill", bar_x, 22 * fs,
                  BAR_W * fs, BAR_H * fs, player.hp_fraction())
        draw_text(surface, "%d/%d" % (int(round(player.hp)), int(round(player.stats.max_hp()))),
                  (bar_x + 6, 27 * fs), fs)

        need = max(1, player.xp_needed())
        self._bar(world, surface, "ui_xp_frame", "ui_xp_fill", bar_x, 46 * fs, BAR_W * fs, 12 * fs,
                  player.xp / float(need))
        draw_text(surface, "LVL %d" % player.level, (bar_x + 6, 60 * fs), fs, colour=(180, 140, 240))

        surface.blit(self._img(world, "prop_essence", (16, 16)), (bar_x + 196, 44))
        draw_text(surface, "%d" % player.essence, (bar_x + 216, 48), 1, colour=rarity_colour(3, cb_mode))
        surface.blit(self._img(world, "prop_gold_pile", (16, 16)), (bar_x + 196, 62))
        draw_text(surface, "%d" % player.gold, (bar_x + 216, 66), 1, colour=rarity_colour(4, cb_mode))
        surface.blit(self._img(world, "prop_key", (16, 16)), (bar_x + 284, 62))
        draw_text(surface, "%d" % world.keys, (bar_x + 304, 66), 1, colour=rarity_colour(4, cb_mode))

        from ..systems import biome_mods as _bm
        badge = _bm.hud_badge(world)
        if badge is not None:
            b_label, b_color = badge
            badge_w = text_size(b_label, 1)[0] + 16
            bx = (surface.get_width() - badge_w) // 2
            by = 42
            b_surf = pygame.Surface((badge_w, 18), pygame.SRCALPHA)
            b_surf.fill((21, 19, 31, 180))
            pygame.draw.rect(b_surf, b_color, pygame.Rect(0, 0, badge_w, 18), 1)
            surface.blit(b_surf, (bx, by))
            draw_text(surface, b_label, (bx + 8, by + 2), 1, colour=b_color)

        if world.run_curses:
            x_curse = bar_x + BAR_W + 8
            y_curse = 22
            from ..systems import shrines as _shrine
            for i, cid in enumerate(world.run_curses):
                cdef = None
                for _c in _shrine.CURSES:
                    if _c["id"] == cid:
                        cdef = _c
                        break
                if cdef is None:
                    continue
                draw_text(surface, cdef["name"], (x_curse, y_curse + i * 18), 1,
                          colour=rarity_colour(5, cb_mode))

        label = "FLOOR %d  %s" % (world.floor, world.biome_name.upper())
        draw_text(surface, label, ((surface.get_width() - text_size(label, 1)[0]) // 2, 12 * fs), 1,
                  colour=(217, 210, 197))

        self._shrine_panel(world, surface)

        unlocked = world.stairs_unlocked_flag or world.stairs_unlocked()
        state = "STAIR OPEN" if unlocked else "STAIR SEALED"
        state_colour = rarity_colour(2, cb_mode) if unlocked else rarity_colour(4, cb_mode)
        draw_text(surface, state, ((surface.get_width() - text_size(state, 1)[0]) // 2, 27 * fs), 1,
                  colour=state_colour)

        if world.active_reward_choice is not None:
            self._room_reward_panel(world, surface)

        # P3.2: cracked wall interaction prompt
        self._cracked_wall_prompt(world, surface)

        # P3.2: secret room count indicator
        self._secret_count_indicator(world, surface)

        # P3.3: event-room interaction prompt
        self._event_room_prompt(world, surface)

        # P3.3: omen preview
        if world.next_floor_modifier:
            self._omen_panel(world, surface)

        # P3.4: onboarding tutorial prompt
        self._tutorial_prompt(world, surface)

        self._combo_panel(world, surface)

        x = 24
        y = 70 * fs
        for inst in player.statuses:
            surface.blit(self._img(world, inst.icon or "ui_status_poison", (20, 20)), (x, y))
            remaining = max(0.0, min(1.0, inst.remaining / 420.0))
            pygame.draw.rect(surface, (11, 10, 16), pygame.Rect(x, y + 20 * fs, 20, 3))
            if inst.kind == "dot":
                bar_color = (226, 113, 29)
            elif inst.kind == "debuff":
                bar_color = (196, 99, 95)
            else:
                bar_color = (121, 176, 74)
            pygame.draw.rect(surface, bar_color, pygame.Rect(x, y + 20 * fs, int(20 * remaining), 3))
            x += 24 * fs

        self._cooldown(world, surface, "ui_icon_sword", player.attack_timer,
                       player.ATTACK_COOLDOWN, 12, 676)
        self._cooldown(world, surface, "ui_icon_dash", player.dash_cooldown,
                       player.DASH_COOLDOWN, 46, 676)

        shake_label = "SHAKE: ON" if getattr(self, "shake_enabled", True) else "SHAKE: OFF"
        shake_col = rarity_colour(2, cb_mode) if getattr(self, "shake_enabled", True) else rarity_colour(4, cb_mode)
        draw_text(surface, shake_label, (bar_x + 6, 80 * fs), 1, colour=shake_col)

        dn_on = self.settings.get("damage_numbers", True)
        dn_label = "DAMAGE NUMS: ON" if dn_on else "DAMAGE NUMS: OFF"
        dn_col = rarity_colour(2, cb_mode) if dn_on else rarity_colour(4, cb_mode)
        draw_text(surface, dn_label, (bar_x + 6, 95 * fs), 1, colour=dn_col)

    def _panel(self, surface, rect):
        panel = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
        panel.fill((21, 19, 31, 200))
        pygame.draw.rect(panel, (58, 52, 80), pygame.Rect(0, 0, rect.w, rect.h), 1)
        surface.blit(panel, (rect.x, rect.y))

    def _bar(self, world, surface, frame_name, fill_name, x, y, w, h, fraction):
        surface.blit(self._img(world, frame_name, (w, h)), (x, y))
        filled = int(w * max(0.0, min(1.0, fraction)))
        if filled > 2:
            surface.blit(self._img(world, fill_name, (w, h)), (x, y), pygame.Rect(0, 0, filled, h))

    def _cooldown(self, world, surface, icon, timer, total, x, y):
        surface.blit(self._img(world, icon, (32, 32)), (x, y))
        if timer > 0.0 and total > 0:
            frac = max(0.0, min(1.0, timer / float(total)))
            overlay = pygame.Surface((32, int(32 * frac)), pygame.SRCALPHA)
            overlay.fill((11, 10, 16, 150))
            surface.blit(overlay, (x, y))

    def _shrine_panel(self, world, surface):
        effects = getattr(world, "shrine_active_effects", None)
        if not effects:
            return
        panel_w = 200
        line_h = 16
        panel_h = len(effects) * line_h + 8
        px = surface.get_width() - panel_w - 12
        py = 80
        panel = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
        panel.fill((21, 19, 31, 200))
        pygame.draw.rect(panel, (58, 52, 80), pygame.Rect(0, 0, panel_w, panel_h), 1)
        surface.blit(panel, (px, py))
        y = py + 4
        for eff in effects:
            name = eff.get("name", "?")
            color = eff.get("color", (246, 242, 232))
            remaining = eff.get("remaining", 0)
            secs = max(0, int(remaining / 60.0))
            text = "%s %ds" % (name, secs)
            draw_text(surface, text, (px + 6, y), 1, colour=color)
            y += line_h

    def _combo_panel(self, world, surface):
        from ..systems.statuses import COMBO_IDS
        player = world.player
        if not player or not getattr(player, "statuses", None):
            return
        combo_insts = [inst for inst in player.statuses if inst.status_id in COMBO_IDS]
        if not combo_insts:
            return

        panel_w = 160
        line_h = 16
        panel_h = len(combo_insts) * line_h + 8
        px = surface.get_width() // 2 - panel_w // 2
        py = 22

        panel = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
        panel.fill((21, 19, 31, 200))
        pygame.draw.rect(panel, (200, 180, 120, 200), pygame.Rect(0, 0, panel_w, panel_h), 1)
        surface.blit(panel, (px, py))
        y = py + 4
        for inst in combo_insts:
            remaining = max(0.0, min(1.0, inst.remaining / 120.0))
            if inst.status_id == "steam_burst":
                bar_color = (200, 180, 120)
            elif inst.status_id == "shatter":
                bar_color = (100, 180, 230)
            elif inst.status_id == "frost_burn":
                bar_color = (100, 200, 80)
            else:
                bar_color = (255, 255, 255)
            text = "%s %.1fs" % (inst.name, inst.seconds_left())
            draw_text(surface, text, (px + 6, y), 1, colour=bar_color)
            pygame.draw.rect(surface, (11, 10, 16), pygame.Rect(px + 6, y + 11, panel_w - 12, 2))
            pygame.draw.rect(surface, bar_color, pygame.Rect(px + 6, y + 11, int((panel_w - 12) * remaining), 2))
            y += line_h

    def _room_reward_panel(self, world, surface):
        choice = world.active_reward_choice
        if choice is None:
            return
        room_id = choice.get("room_id", "")
        options = choice.get("options", ["item", "gold", "heal", "shrine"])
        panel_w = 260
        panel_h = len(options) * 30 + 24
        px = surface.get_width() // 2 - panel_w // 2
        py = 100

        panel = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
        panel.fill((21, 19, 31, 220))
        pygame.draw.rect(panel, (232, 178, 60, 255), pygame.Rect(0, 0, panel_w, panel_h), 2)
        surface.blit(panel, (px, py))

        draw_text(surface, "Choose a reward", (px + panel_w // 2 - 50, py + 6), 1,
                  colour=(232, 178, 60))

        y = py + 26
        option_labels = {"item": "Item", "gold": "Gold", "heal": "Heal", "shrine": "Shrine"}
        for opt in options:
            label = option_labels.get(opt, opt.capitalize())
            draw_text(surface, label, (px + 12, y), 1, colour=(246, 242, 232))
            y += 30

    def _cracked_wall_prompt(self, world, surface):
        """P3.2: Show interaction prompt when player is adjacent to a cracked wall."""
        player = world.player
        if not player or not hasattr(world, "cracked_walls"):
            return
        if not world.cracked_walls:
            return
        ptx = int(player.x // TILE)
        pty = int(player.y // TILE)
        for (tx, ty) in world.cracked_walls:
            if abs(ptx - tx) <= 1 and abs(pty - ty) <= 1:
                prompt = "Press E to break wall"
                text_w = text_size(prompt, 1)[0]
                cam_x = world.camera.world_offset()[0]
                cam_y = world.camera.world_offset()[1]
                wall_sx = tx * TILE + TILE // 2 - cam_x
                wall_sy = ty * TILE - cam_y
                px = surface.get_width() // 2 + wall_sx - text_w // 2
                py = wall_sy - 36
                if 0 < px < surface.get_width() - text_w and py > 0:
                    draw_text(surface, prompt, (px, py), 1, colour=(232, 178, 60))
                break

    def _secret_count_indicator(self, world, surface):
        """P3.2: Show secret room count/indicator on HUD."""
        if not hasattr(world, "discovered_secrets"):
            return
        total = len(getattr(world, "_level_secret_rooms", []))
        discovered = len(world.discovered_secrets)
        if total > 0:
            label = "SECRETS: %d/%d" % (discovered, total)
            # `fs` is a local of draw(); this method had no such name, so any floor with a
            # secret room raised NameError here and the whole frame failed to render. The
            # scale lives on the instance.
            draw_text(surface, label, (24, 96 * self.font_scale), self.font_scale,
                      colour=(180, 140, 240))

    def _event_room_prompt(self, world, surface):
        """P3.3: Show interaction prompt when player is adjacent to an event room."""
        player = world.player
        if not player or not hasattr(world, "level"):
            return
        ptx = int(player.x // TILE)
        pty = int(player.y // TILE)
        for room in world.level.rooms:
            kind = room.get("kind", "")
            if kind not in ("gambling", "blacksmith", "fountain", "omen"):
                continue
            rx = int(room.get("x", 0))
            ry = int(room.get("y", 0))
            rw = int(room.get("w", 8))
            rh = int(room.get("h", 8))
            if (rx - 1 <= ptx <= rx + rw and ry - 1 <= pty <= ry + rh and
                    abs(ptx - (rx + rw // 2)) <= 1 and abs(pty - (ry + rh // 2)) <= 1):
                labels = {"gambling": "Gamble", "blacksmith": "Blacksmith",
                          "fountain": "Fountain", "omen": "Omen"}
                prompt = "Press E to use %s" % labels.get(kind, kind)
                text_w = text_size(prompt, 1)[0]
                cam_x = world.camera.world_offset()[0]
                cam_y = world.camera.world_offset()[1]
                room_sx = (rx + rw // 2) * TILE + TILE // 2 - cam_x
                room_sy = (ry + rh // 2) * TILE - cam_y
                px = surface.get_width() // 2 + room_sx - text_w // 2
                py = room_sy - 36
                if 0 < px < surface.get_width() - text_w and py > 0:
                    draw_text(surface, prompt, (px, py), 1, colour=(232, 178, 60))
                break

    def _omen_panel(self, world, surface):
        """P3.3: Show omen preview panel."""
        modifier = world.next_floor_modifier
        if not modifier:
            return
        panel_w = 200
        panel_h = 32
        px = surface.get_width() - panel_w - 12
        py = 120
        panel = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
        panel.fill((21, 19, 31, 200))
        pygame.draw.rect(panel, (232, 178, 60, 255), pygame.Rect(0, 0, panel_w, panel_h), 1)
        surface.blit(panel, (px, py))
        draw_text(surface, "OMEN: %s" % modifier, (px + 6, py + 8), 1,
                  colour=(232, 178, 60))

    def _tutorial_prompt(self, world, surface):
        """P3.4: Show onboarding tutorial prompt when player struggles."""
        tut = getattr(world, "tutorial", None)
        if not tut or tut.completed:
            return
        prompt = tut.active_prompt()
        if prompt:
            text = "Try: %s" % prompt
            text_w = text_size(text, 1)[0]
            px = (surface.get_width() - text_w) // 2
            py = surface.get_height() - 40
            draw_text(surface, text, (px, py), 1, colour=(232, 178, 60))
