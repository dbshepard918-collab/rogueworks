"""Headquarters hub scene — where the player loads after death."""
from __future__ import annotations

import pygame
from ..engine.assets import Atlas, colour, draw_text, text_size
from ..systems import hq as hq_sys
from ..systems.quest_tracker import QuestTracker
from ..systems.dialogue import DialogueSystem


class HQScene:
    """The headquarters hub: NPCs, rooms, quest tracking, dialogue."""

    TILE = 64

    def __init__(self, game):
        self.game = game
        self.hq_state = hq_sys.HQState()
        self.quest_tracker = QuestTracker(game.profile)
        self.dialogue = DialogueSystem()
        self.font_height = 16
        self.active_npc = None
        self.message = ""
        self.message_timer = 0.0
        # Camera offset for HQ
        self.camera_x = 0
        self.camera_y = 0
        self.hq_state.update_room()
        self._update_camera()
        # Accept any quest whose prereqs are satisfied (chain progression)
        self.quest_tracker.accept_available()

    def _update_camera(self):
        """Center camera on player."""
        self.camera_x = self.hq_state.player_tx * self.TILE - 640 + self.TILE // 2
        self.camera_y = self.hq_state.player_ty * self.TILE - 360 + self.TILE // 2

    def handle_event(self, event):
        if event.type == pygame.KEYDOWN:
            if self.dialogue.is_active():
                if event.key == pygame.K_RETURN or event.key == pygame.K_SPACE:
                    self.dialogue.update()
                    if not self.dialogue.is_active():
                        self.dialogue.close()
                elif event.key == pygame.K_ESCAPE:
                    self.dialogue.close()
            else:
                if event.key == pygame.K_LEFT or event.key == pygame.K_a:
                    self.hq_state.move_player(-1, 0)
                elif event.key == pygame.K_RIGHT or event.key == pygame.K_d:
                    self.hq_state.move_player(1, 0)
                elif event.key == pygame.K_UP or event.key == pygame.K_w:
                    self.hq_state.move_player(0, -1)
                elif event.key == pygame.K_DOWN or event.key == pygame.K_s:
                    self.hq_state.move_player(0, 1)
                elif event.key == pygame.K_e:
                    self._try_interact()
                elif event.key == pygame.K_TAB:
                    pass  # Could open quest log
                elif event.key == pygame.K_ESCAPE:
                    # Save and quit to menu
                    self.game.show_menu()
        self._update_camera()

    def _try_interact(self):
        npc_def = self.hq_state.interact()
        if npc_def:
            self.dialogue.start(npc_def)
            self.active_npc = npc_def.get("name", "")
        else:
            # Check for room interactions
            room = hq_sys.room_at(
                self.hq_state.player_tx * self.TILE,
                self.hq_state.player_ty * self.TILE,
            )
            if room and room.get("kind") == "exit":
                # Start a new run
                self.game.start_run()
            elif room:
                self.message = room.get("description", "")
                self.message_timer = 3.0

    def update(self, dt):
        if self.message_timer > 0:
            self.message_timer -= dt

    def draw(self, surface, dt=0.0):
        surface.fill(colour("void", (11, 10, 16)))
        # Draw rooms
        for room in hq_sys.hq_rooms().get("rooms", []):
            self._draw_room(surface, room)
        # Draw NPCs
        for npc_id, npc_state in self.hq_state.npc_states.items():
            if npc_state.visible:
                self._draw_npc(surface, npc_state)
        # Draw player
        self._draw_player(surface)
        # Draw HUD
        self._draw_hud(surface)
        # Draw dialogue
        if self.dialogue.is_active():
            self._draw_dialogue(surface)
        # Draw message
        if self.message_timer > 0 and self.message:
            self._draw_message(surface)

    THEMES = {
        "hq_hall": {
            "floor": "tile_catacombs_floor",
            "floor_alt": "tile_catacombs_floor_alt",
            "wall": "tile_catacombs_wall",
            "wall_torch": "tile_catacombs_wall_torch",
            "brazier": "tile_catacombs_brazier",
            "pillar": "tile_catacombs_pillar",
        },
        "hq_forge": {
            "floor": "tile_ember_floor",
            "floor_alt": "tile_ember_floor_alt",
            "wall": "tile_ember_wall",
            "wall_torch": "tile_ember_wall_torch",
            "brazier": "tile_ember_brazier",
            "pillar": "tile_ember_pillar",
        },
        "hq_dock": {
            "floor": "tile_drowned_floor",
            "floor_alt": "tile_drowned_floor_alt",
            "wall": "tile_drowned_wall",
            "wall_torch": "tile_drowned_wall",
            "water": "tile_drowned_floor_water",
            "pillar": "tile_drowned_pillar",
        },
        "hq_omen_room": {
            "floor": "tile_catacombs_floor_alt2",
            "floor_alt": "tile_catacombs_floor",
            "wall": "tile_catacombs_wall_skull",
            "wall_torch": "tile_catacombs_wall_torch",
            "brazier": "tile_catacombs_brazier",
            "rune": "tile_catacombs_rune_floor",
        },
        "hq_memorial": {
            "floor": "tile_catacombs_floor_alt",
            "floor_alt": "tile_catacombs_floor",
            "wall": "tile_catacombs_wall",
            "wall_torch": "tile_catacombs_wall_torch",
            "slab": "tile_catacombs_slab",
            "brazier": "tile_catacombs_brazier",
        },
        "depths_entrance": {
            "floor": "tile_catacombs_floor",
            "wall": "tile_catacombs_wall",
            "stairs": "tile_catacombs_stairs_down",
            "brazier": "tile_catacombs_brazier",
        },
    }

    CORRIDORS = [
        {"x": 20, "y": 4, "w": 2, "h": 3, "floor": "tile_catacombs_floor", "top_wall": True, "bot_wall": True},
        {"x": 6, "y": 14, "w": 3, "h": 2, "floor": "tile_catacombs_floor", "left_wall": True, "right_wall": True},
        {"x": 18, "y": 14, "w": 3, "h": 2, "floor": "tile_catacombs_floor", "left_wall": True, "right_wall": True},
        {"x": 26, "y": 17, "w": 2, "h": 3, "floor": "tile_catacombs_floor", "top_wall": True, "bot_wall": True},
        {"x": 29, "y": 10, "w": 3, "h": 2, "floor": "tile_ember_floor", "left_wall": True, "right_wall": True},
    ]

    def _draw_corridors(self, surface):
        try:
            tiles_atlas = Atlas.load("tiles")
            if not tiles_atlas:
                return
            fl_tile = tiles_atlas.frame("tile_catacombs_floor")
            w_tile = tiles_atlas.frame("tile_catacombs_wall")
            for c in self.CORRIDORS:
                cx, cy, cw, ch = c["x"], c["y"], c["w"], c["h"]
                c_fl = tiles_atlas.frame(c.get("floor", "tile_catacombs_floor")) or fl_tile
                for ty in range(cy, cy + ch):
                    for tx in range(cx, cx + cw):
                        sx = tx * self.TILE - self.camera_x
                        sy = ty * self.TILE - self.camera_y
                        if -self.TILE <= sx <= 1280 and -self.TILE <= sy <= 720 and c_fl:
                            surface.blit(c_fl, (sx, sy))
                if c.get("top_wall") and w_tile:
                    for tx in range(cx, cx + cw):
                        sx = tx * self.TILE - self.camera_x
                        sy = (cy - 1) * self.TILE - self.camera_y
                        if -self.TILE <= sx <= 1280 and -self.TILE <= sy <= 720:
                            surface.blit(w_tile, (sx, sy))
                if c.get("bot_wall") and w_tile:
                    for tx in range(cx, cx + cw):
                        sx = tx * self.TILE - self.camera_x
                        sy = (cy + ch) * self.TILE - self.camera_y
                        if -self.TILE <= sx <= 1280 and -self.TILE <= sy <= 720:
                            surface.blit(w_tile, (sx, sy))
                if c.get("left_wall") and w_tile:
                    for ty in range(cy, cy + ch):
                        sx = (cx - 1) * self.TILE - self.camera_x
                        sy = ty * self.TILE - self.camera_y
                        if -self.TILE <= sx <= 1280 and -self.TILE <= sy <= 720:
                            surface.blit(w_tile, (sx, sy))
                if c.get("right_wall") and w_tile:
                    for ty in range(cy, cy + ch):
                        sx = (cx + cw) * self.TILE - self.camera_x
                        sy = ty * self.TILE - self.camera_y
                        if -self.TILE <= sx <= 1280 and -self.TILE <= sy <= 720:
                            surface.blit(w_tile, (sx, sy))
        except Exception:
            pass

    def _draw_room(self, surface, room):
        rid = room.get("id", "")
        rx = room.get("x", 0)
        ry = room.get("y", 0)
        rw = room.get("w", 8)
        rh = room.get("h", 8)
        theme = self.THEMES.get(rid, self.THEMES["hq_hall"])

        tiles_atlas = None
        props_atlas = None
        try:
            tiles_atlas = Atlas.load("tiles")
            props_atlas = Atlas.load("props")
        except Exception:
            pass

        # If tiles atlas is missing, fallback to clean solid rectangle
        if not tiles_atlas:
            floor_col = (36, 32, 50)
            wall_col = (58, 52, 80)
            px = rx * self.TILE - self.camera_x
            py = ry * self.TILE - self.camera_y
            pygame.draw.rect(surface, floor_col, (px, py, rw * self.TILE, rh * self.TILE))
            pygame.draw.rect(surface, wall_col, (px, py, rw * self.TILE, rh * self.TILE), 4)
            return

        for ty in range(ry, ry + rh):
            for tx in range(rx, rx + rw):
                sx = tx * self.TILE - self.camera_x
                sy = ty * self.TILE - self.camera_y
                if sx < -self.TILE or sx > 1280 or sy < -self.TILE or sy > 720:
                    continue

                is_north = (ty == ry)
                is_south = (ty == ry + rh - 1)
                is_west = (tx == rx)
                is_east = (tx == rx + rw - 1)

                if rid == "depths_entrance":
                    if (tx, ty) in [(rx + 1, ry + 1), (rx + 2, ry + 1), (rx + 1, ry + 2), (rx + 2, ry + 2)]:
                        st = tiles_atlas.frame(theme["stairs"])
                        if st:
                            surface.blit(st, (sx, sy))
                    elif (tx, ty) in [(rx, ry), (rx + rw - 1, ry)]:
                        bz = tiles_atlas.frame(theme["brazier"])
                        if bz:
                            surface.blit(bz, (sx, sy))
                    else:
                        fl = tiles_atlas.frame(theme["floor"])
                        if fl:
                            surface.blit(fl, (sx, sy))
                    continue

                # Openings in perimeter walls for corridors
                is_door = False
                if rid == "hq_hall":
                    if is_east and 4 <= ty <= 6: is_door = True
                    if is_south and 6 <= tx <= 8: is_door = True
                    if is_south and 18 <= tx <= 20: is_door = True
                elif rid == "hq_forge":
                    if is_west and 4 <= ty <= 6: is_door = True
                    if is_south and 7 <= (tx - rx) <= 9: is_door = True
                elif rid == "hq_dock":
                    if is_north and 6 <= tx <= 8: is_door = True
                elif rid == "hq_omen_room":
                    if is_north and 18 <= tx <= 20: is_door = True
                    if is_east and 17 <= ty <= 19: is_door = True
                elif rid == "hq_memorial":
                    if is_west and 17 <= ty <= 19: is_door = True
                    if is_north and 1 <= (tx - rx) <= 3: is_door = True

                if (is_north or is_south or is_west or is_east) and not is_door:
                    if is_north and tx % 4 == 2 and "wall_torch" in theme:
                        wt = tiles_atlas.frame(theme["wall_torch"])
                        if wt:
                            surface.blit(wt, (sx, sy))
                    elif is_north and rid == "hq_memorial" and tx % 3 == 1 and "slab" in theme:
                        sl = tiles_atlas.frame(theme["slab"])
                        if sl:
                            surface.blit(sl, (sx, sy))
                    else:
                        w = tiles_atlas.frame(theme["wall"])
                        if w:
                            surface.blit(w, (sx, sy))
                    continue

                # Room floor
                if rid == "hq_dock" and ty >= ry + rh - 3:
                    wt = tiles_atlas.frame(theme["water"])
                    if wt:
                        surface.blit(wt, (sx, sy))
                    if ty == ry + rh - 3 and (tx == rx + 3 or tx == rx + rw - 4):
                        pl = tiles_atlas.frame(theme["pillar"])
                        if pl:
                            surface.blit(pl, (sx, sy))
                elif rid == "hq_omen_room" and (tx, ty) == (rx + rw // 2, ry + rh // 2) and "rune" in theme:
                    rn = tiles_atlas.frame(theme["rune"])
                    if rn:
                        surface.blit(rn, (sx, sy))
                elif (tx + ty * 3) % 7 == 0 and "floor_alt" in theme:
                    fa = tiles_atlas.frame(theme["floor_alt"])
                    if fa:
                        surface.blit(fa, (sx, sy))
                else:
                    fl = tiles_atlas.frame(theme["floor"])
                    if fl:
                        surface.blit(fl, (sx, sy))

                # Structural pillars & props
                if rid == "hq_hall":
                    if (tx, ty) in [(rx + 3, ry + 3), (rx + rw - 4, ry + 3), (rx + 3, ry + rh - 4), (rx + rw - 4, ry + rh - 4)]:
                        pl = tiles_atlas.frame(theme["pillar"])
                        if pl:
                            surface.blit(pl, (sx, sy))
                    elif (tx, ty) in [(rx + 8, ry + 6), (rx + 12, ry + 6)]:
                        bz = tiles_atlas.frame(theme["brazier"])
                        if bz:
                            surface.blit(bz, (sx, sy))
                elif rid == "hq_forge":
                    if (tx, ty) in [(rx + 2, ry + 4), (rx + rw - 3, ry + 4)]:
                        bz = tiles_atlas.frame(theme["brazier"])
                        if bz:
                            surface.blit(bz, (sx, sy))
                    elif (tx, ty) == (rx + 4, ry + 5) and props_atlas:
                        anv = props_atlas.frame("prop_anvil")
                        if anv:
                            anv_scaled = pygame.transform.scale_by(anv, 2)
                            surface.blit(anv_scaled, (sx + 32 - anv_scaled.get_width() // 2,
                                                      sy + 32 - anv_scaled.get_height() // 2))
                    elif (tx, ty) == (rx + rw - 4, ry + 3) and props_atlas:
                        fg = props_atlas.frame("prop_forge")
                        if fg:
                            fg_scaled = pygame.transform.scale_by(fg, 2)
                            surface.blit(fg_scaled, (sx + 32 - fg_scaled.get_width() // 2,
                                                     sy + 32 - fg_scaled.get_height() // 2))
                elif rid == "hq_omen_room":
                    if (tx, ty) in [(rx + 2, ry + 2), (rx + rw - 3, ry + 2)]:
                        bz = tiles_atlas.frame(theme["brazier"])
                        if bz:
                            surface.blit(bz, (sx, sy))
                elif rid == "hq_memorial":
                    if (tx, ty) in [(rx + 2, ry + rh - 2), (rx + rw - 3, ry + rh - 2)] and props_atlas:
                        cnd = props_atlas.frame("prop_candles")
                        if cnd:
                            cnd_scaled = pygame.transform.scale_by(cnd, 2)
                            surface.blit(cnd_scaled, (sx + 32 - cnd_scaled.get_width() // 2,
                                                      sy + 32 - cnd_scaled.get_height() // 2))
                    elif (tx, ty) in [(rx + 3, ry + 3), (rx + rw - 4, ry + 3)] and props_atlas:
                        alt = props_atlas.frame("prop_altar")
                        if alt:
                            alt_scaled = pygame.transform.scale_by(alt, 2)
                            surface.blit(alt_scaled, (sx + 32 - alt_scaled.get_width() // 2,
                                                      sy + 32 - alt_scaled.get_height() // 2))

    def _draw_room_banners(self, surface):
        for room in hq_sys.hq_rooms().get("rooms", []):
            rname = room.get("name", "").upper()
            rx = room.get("x", 0) * self.TILE - self.camera_x
            ry = room.get("y", 0) * self.TILE - self.camera_y
            rw = room.get("w", 8) * self.TILE
            tw, th = text_size(rname, 2)
            if tw > 0:
                bx = rx + rw // 2 - tw // 2 - 14
                by = ry + 12
                if -300 <= bx <= 1300 and -100 <= by <= 800:
                    pygame.draw.rect(surface, (11, 10, 16), (bx, by, tw + 28, 28))
                    pygame.draw.rect(surface, (58, 52, 80), (bx, by, tw + 28, 28), 2)
                    draw_text(surface, rname, (bx + 14, by + 6), 2, colour=(217, 210, 197))

    def _draw_npc(self, surface, npc_state):
        nx = npc_state.x - self.camera_x
        ny = npc_state.y - self.camera_y
        npc_id = npc_state.definition.get("id", "")

        if not (-100 <= nx <= 1380 and -100 <= ny <= 820):
            return

        # Contact shadow
        shadow_surf = pygame.Surface((44, 16), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow_surf, (11, 10, 16, 140), (0, 0, 44, 16))
        surface.blit(shadow_surf, (nx - 22, ny + 14))

        # NPC sprite
        frame_name = f"npc_{npc_id}" if npc_id else None
        drawn_sprite = False
        if frame_name:
            try:
                atlas = Atlas.load("npcs")
                if atlas and frame_name in atlas.frames:
                    surf = atlas.frame(frame_name)
                    if surf:
                        surface.blit(surf, (nx - surf.get_width() // 2,
                                            ny - surf.get_height() // 2))
                        drawn_sprite = True
            except Exception:
                pass

        if not drawn_sprite:
            npc_col = (121, 176, 74) if "keeper" in npc_id else \
                      (232, 178, 60) if "forge" in npc_id else \
                      (100, 180, 200) if "tide" in npc_id else \
                      (180, 140, 240) if "raven" in npc_id else \
                      (196, 99, 95)
            pygame.draw.rect(surface, npc_col, (nx - 12, ny - 12, 24, 24))

        # Formatted name pill badge
        name = npc_state.definition.get("name", "").upper()
        tw, th = text_size(name, 2)
        if tw > 0:
            bx = nx - tw // 2 - 8
            by = ny - 42
            pygame.draw.rect(surface, (11, 10, 16, 220), (bx, by, tw + 16, 22))
            pygame.draw.rect(surface, (58, 52, 80), (bx, by, tw + 16, 22), 1)
            draw_text(surface, name, (bx + 8, by + 3), 2, colour=(217, 210, 197))

        # Talk hint badge only when player is near (<= 2 tiles distance)
        p_dist = abs(npc_state.tx - self.hq_state.player_tx) + abs(npc_state.ty - self.hq_state.player_ty)
        if p_dist <= 2:
            hint = "[E] TALK"
            hw, hh = text_size(hint, 2)
            if hw > 0:
                hbx = nx - hw // 2 - 8
                hby = ny + 26
                pygame.draw.rect(surface, (11, 10, 16, 220), (hbx, hby, hw + 16, 20))
                pygame.draw.rect(surface, (121, 176, 74), (hbx, hby, hw + 16, 20), 1)
                draw_text(surface, hint, (hbx + 8, hby + 2), 2, colour=(121, 176, 74))

    def _draw_player(self, surface):
        px = self.hq_state.player_tx * self.TILE - self.camera_x
        py = self.hq_state.player_ty * self.TILE - self.camera_y

        # Contact shadow
        shadow_surf = pygame.Surface((44, 16), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow_surf, (11, 10, 16, 140), (0, 0, 44, 16))
        surface.blit(shadow_surf, (px - 22, py + 14))

        try:
            atlas = Atlas.load("player")
            if atlas:
                frame_name = next(
                    (name for name in ("player_idle_down",
                                       "player_idle_breath_down_0",
                                       "player_idle_right")
                     if name in atlas.frames),
                    None,
                )
                if frame_name:
                    surf = atlas.frame(frame_name)
                    if surf:
                        surface.blit(surf, (px - surf.get_width() // 2,
                                            py - surf.get_height() // 2))
                        return
        except Exception:
            pass
        # Fallback: gold rectangle
        pygame.draw.rect(surface, (232, 178, 60), (px - 10, py - 10, 20, 20))

    def _draw_descent_prompt(self, surface):
        ptx, pty = self.hq_state.player_tx, self.hq_state.player_ty
        # Depths entrance is at tx: 8..11, ty: 8..11
        if 7 <= ptx <= 12 and 7 <= pty <= 12:
            dhint = "[E] DESCEND INTO VAELMOOR"
            dw, dh = text_size(dhint, 2)
            dx = 10 * self.TILE - self.camera_x
            dy = 9 * self.TILE - self.camera_y
            dbx = dx - dw // 2 - 12
            dby = dy + 50
            pygame.draw.rect(surface, (11, 10, 16), (dbx, dby, dw + 24, 26))
            pygame.draw.rect(surface, (232, 178, 60), (dbx, dby, dw + 24, 26), 2)
            draw_text(surface, dhint, (dbx + 12, dby + 5), 2, colour=(232, 178, 60))

    def _draw_hud(self, surface):
        # Room badge
        pygame.draw.rect(surface, (11, 10, 16), (8, 8, 270, 42))
        pygame.draw.rect(surface, (87, 80, 112), (8, 8, 270, 42), 2)
        if self.hq_state.active_room:
            room = hq_sys.room_by_id(self.hq_state.active_room)
            if room:
                draw_text(surface, room.get("name", "").upper(), (18, 16), 2, colour=(217, 210, 197))
        else:
            draw_text(surface, "HEADQUARTERS", (18, 16), 2, colour=(217, 210, 197))

        # Controls hint
        pygame.draw.rect(surface, (11, 10, 16), (8, 680, 390, 28))
        draw_text(surface, "WASD MOVE   E INTERACT   ESC MENU", (18, 689), 1, colour=(138, 132, 150))

        # Active quests panel
        quests = self.quest_tracker.active_quests_with_progress()
        if quests:
            pygame.draw.rect(surface, (11, 10, 16), (902, 8, 366, 184))
            pygame.draw.rect(surface, (87, 80, 112), (902, 8, 366, 184), 2)
            draw_text(surface, "ACTIVE QUESTS", (918, 16), 2, colour=(217, 210, 197))
            for i, q in enumerate(quests[:3]):
                draw_text(surface, q["title"][:30], (918, 40 + i * 40), 2, colour=(121, 176, 74))
                for j, obj in enumerate(q["objectives"][:2]):
                    check = "[x]" if obj["done"] else "[ ]"
                    draw_text(surface, f"  {check} {obj['label'][:25]}", (918, 58 + i * 40 + j * 16), 2, colour=(138, 132, 150))

    def _draw_dialogue(self, surface):
        box_h = 160
        box_y = 720 - box_h - 16
        box_w = 1100
        box_x = (1280 - box_w) // 2

        # Shadow
        shadow = pygame.Surface((box_w, box_h), pygame.SRCALPHA)
        shadow.fill((0, 0, 0, 180))
        surface.blit(shadow, (box_x + 4, box_y + 4))

        # Panel
        panel = pygame.Surface((box_w, box_h), pygame.SRCALPHA)
        panel.fill((15, 13, 22, 250))
        surface.blit(panel, (box_x, box_y))
        pygame.draw.rect(surface, (58, 52, 80), (box_x, box_y, box_w, box_h), 2)
        pygame.draw.rect(surface, (87, 80, 112), (box_x + 3, box_y + 3, box_w - 6, box_h - 6), 1)

        # NPC Portrait Frame
        port_size = 96
        port_x = box_x + 20
        port_y = box_y + (box_h - port_size) // 2
        pygame.draw.rect(surface, (11, 10, 16), (port_x, port_y, port_size, port_size))
        pygame.draw.rect(surface, (87, 80, 112), (port_x, port_y, port_size, port_size), 2)

        # Blit portrait sprite
        try:
            npcs_atlas = Atlas.load("npcs")
            sp_name = self.dialogue.npc_sprite or (f"npc_{self.active_npc_id}" if self.active_npc_id else "")
            if npcs_atlas and sp_name in npcs_atlas.frames:
                sp = npcs_atlas.frame(sp_name)
                if sp:
                    surface.blit(sp, (port_x + (port_size - sp.get_width()) // 2,
                                      port_y + (port_size - sp.get_height()) // 2))
        except Exception:
            pass

        text_x = port_x + port_size + 24
        # NPC name
        name_str = (self.dialogue.npc_name or self.active_npc or "UNKNOWN").upper()
        draw_text(surface, name_str, (text_x, box_y + 18), 2, colour=(232, 178, 60))

        # Divider line
        pygame.draw.line(surface, (58, 52, 80), (text_x, box_y + 46), (box_x + box_w - 24, box_y + 46), 1)

        # Dialogue text
        if self.dialogue.active and self.dialogue.active.current_line():
            line = self.dialogue.active.current_line()
            text = line.get("text", "") if isinstance(line, dict) else str(line)
            draw_text(surface, text[:85], (text_x, box_y + 60), 2, colour=(217, 210, 197))

        draw_text(surface, "[ENTER / SPACE] CONTINUE    [ESC] CLOSE", (text_x, box_y + box_h - 26), 1, colour=(138, 132, 150))

    def _draw_message(self, surface):
        if self.message:
            tw, th = text_size(self.message[:60], 2)
            box_w = tw + 40
            box_h = 50
            bx = 640 - box_w // 2
            by = 100
            pygame.draw.rect(surface, (15, 13, 22, 240), (bx, by, box_w, box_h))
            pygame.draw.rect(surface, (58, 52, 80), (bx, by, box_w, box_h), 2)
            draw_text(surface, self.message[:60], (bx + 20, by + 15), 2, colour=(217, 210, 197))
