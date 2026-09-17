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

    def _draw_room(self, surface, room):
        rx = room.get("x", 0) * self.TILE - self.camera_x
        ry = room.get("y", 0) * self.TILE - self.camera_y
        rw = room.get("w", 8) * self.TILE
        rh = room.get("h", 8) * self.TILE
        room_id = room.get("id", "")
        kind = room.get("kind", "hub")
        palettes = {
            "hub": ((36, 32, 50), (58, 52, 80), (87, 80, 112), (121, 176, 74)),
            "blacksmith": ((58, 32, 28), (92, 32, 24), (168, 60, 28), (226, 113, 29)),
            "quest_hub": ((16, 40, 60), (31, 95, 128), (79, 209, 200), (147, 160, 180)),
            "omen": ((36, 32, 50), (58, 52, 80), (123, 79, 209), (180, 140, 240)),
            "recap": ((58, 52, 80), (87, 80, 112), (217, 210, 197), (138, 132, 150)),
            "exit": ((21, 19, 31), (36, 32, 50), (87, 80, 112), (232, 178, 60)),
        }
        floor, wall, highlight, accent = palettes.get(kind, palettes["hub"])
        pygame.draw.rect(surface, floor, (rx, ry, rw, rh))
        # Large, quiet material bands read as stone/wood/water without noisy stamps.
        for row in range(2, max(2, rh // self.TILE), 2):
            yy = ry + row * self.TILE
            pygame.draw.line(surface, wall, (rx + 8, yy), (rx + rw - 9, yy), 1)
        for col in range(2, max(2, rw // self.TILE), 2):
            xx = rx + col * self.TILE
            pygame.draw.line(surface, wall, (xx, ry + 8), (xx, ry + rh - 9), 1)
        if kind == "blacksmith":
            for xx in range(rx + 18, rx + rw - 18, 96):
                pygame.draw.rect(surface, accent, (xx, ry + rh // 2 - 3, 26, 6))
        elif kind == "quest_hub":
            for yy in range(ry + 20, ry + rh - 20, 48):
                pygame.draw.arc(surface, highlight, (rx + 12, yy, rx + rw - 24, yy + 18), 0.2, 2.8, 2)
        elif kind == "omen":
            pygame.draw.circle(surface, accent, (rx + rw // 2, ry + rh // 2), min(rw, rh) // 5, 3)
        elif kind == "recap":
            for yy in range(ry + 24, ry + rh - 20, 42):
                pygame.draw.line(surface, highlight, (rx + 18, yy), (rx + rw - 18, yy), 2)
        elif kind == "exit":
            pygame.draw.circle(surface, accent, (rx + rw // 2, ry + rh // 2), min(rw, rh) // 4, 3)
        # Recessed wall frame and bottom shadow give rooms a solid architectural edge.
        pygame.draw.rect(surface, wall, (rx, ry, rw, rh), 6)
        pygame.draw.line(surface, (11, 10, 16), (rx + 8, ry + rh - 8), (rx + rw - 8, ry + rh - 8), 4)
        name = room.get("name", "")
        tw, th = text_size(name, 2)
        if tw > 0:
            label_w = tw + 20
            pygame.draw.rect(surface, (11, 10, 16), (rx + rw // 2 - label_w // 2, ry + 10, label_w, 26))
            draw_text(surface, name, (rx + rw // 2 - tw // 2, ry + 14), 2, colour=(217, 210, 197))

    def _draw_npc(self, surface, npc_state):
        nx = npc_state.x - self.camera_x
        ny = npc_state.y - self.camera_y
        npc_id = npc_state.definition.get("id", "")
        
        # Draw NPC sprite from procedural atlas
        frame_name = f"npc_{npc_id}" if npc_id else None
        if frame_name:
            try:
                atlas = Atlas.load("npcs")
                if atlas and frame_name in atlas.frames:
                    surf = atlas.frame(frame_name)
                    if surf:
                        # HQ character frames are 64px world tiles; center the
                        # full authored silhouette on the NPC's interaction
                        # point instead of offsetting as if it were 32px art.
                        surface.blit(surf, (nx - surf.get_width() // 2,
                                            ny - surf.get_height() // 2))
                        name = npc_state.definition.get("name", "")
                        tw, th = text_size(name, 2)
                        if tw > 0:
                            draw_text(surface, name, (nx - tw // 2, ny - 32), 2, colour=(217, 210, 197))
                        hint = "[E] Talk"
                        hw, hh = text_size(hint, 2)
                        if hw > 0:
                            draw_text(surface, hint, (nx - hw // 2, ny + 22), 2, colour=(121, 176, 74))
                        return
            except Exception:
                pass
        
        # Fallback: colored rectangle
        npc_col = (121, 176, 74) if "keeper" in npc_id else \
                  (232, 178, 60) if "forge" in npc_id else \
                  (100, 180, 200) if "tide" in npc_id else \
                  (180, 140, 240) if "raven" in npc_id else \
                  (196, 99, 95)
        pygame.draw.rect(surface, npc_col, (nx - 12, ny - 12, 24, 24))
        name = npc_state.definition.get("name", "")
        tw, th = text_size(name, 2)
        if tw > 0:
            draw_text(surface, name, (nx - tw // 2, ny - 28), 2, colour=(217, 210, 197))

    def _draw_player(self, surface):
        px = self.hq_state.player_tx * self.TILE - self.camera_x
        py = self.hq_state.player_ty * self.TILE - self.camera_y
        # Draw a real directional human silhouette from the shipped atlas.
        # ``player_idle_0`` is a runtime alias used by the combat entity, not
        # a frame in the HQ atlas JSON.
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

    def _draw_hud(self, surface):
        pygame.draw.rect(surface, (11, 10, 16), (8, 8, 270, 42))
        pygame.draw.rect(surface, (87, 80, 112), (8, 8, 270, 42), 2)
        # Room name
        if self.hq_state.active_room:
            room = hq_sys.room_by_id(self.hq_state.active_room)
            if room:
                draw_text(surface, room.get("name", ""), (18, 16), 2, colour=(217, 210, 197))
        # Controls hint
        pygame.draw.rect(surface, (11, 10, 16), (8, 680, 390, 28))
        draw_text(surface, "WASD MOVE   E INTERACT   ESC MENU", (18, 689), 1, colour=(138, 132, 150))
        # Active quests
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
        # r49: dialogue panel background
        box_h = 160
        box_y = 720 - box_h  # = 560
        panel = pygame.Surface((surface.get_width(), box_h), pygame.SRCALPHA)
        panel.fill((11, 10, 16, 245))
        surface.blit(panel, (0, box_y))
        pygame.draw.rect(surface, (87, 80, 112),
                         (0, box_y, surface.get_width(), box_h), 2)
        pygame.draw.line(surface, (121, 176, 74),
                         (20, box_y + 36), (surface.get_width() - 20, box_y + 36), 1)
        # NPC name
        if self.dialogue.npc_name:
            draw_text(surface, self.dialogue.npc_name, (20, box_y + 10), 2, colour=(217, 210, 197))
        # Dialogue text
        if self.dialogue.active and self.dialogue.active.current_line():
            line = self.dialogue.active.current_line()
            text = line.get("text", "") if isinstance(line, dict) else str(line)
            draw_text(surface, text[:80], (20, box_y + 40), 2, colour=(232, 178, 60))
        draw_text(surface, "ENTER: Continue | ESC: Close", (20, box_y + 130), 1, colour=(138, 132, 150))

    def _draw_message(self, surface):
        # Center message box
        if self.message:
            tw, th = text_size(self.message[:60], 2)
            box_w = tw + 40
            box_h = 50
            bx = 640 - box_w // 2
            by = 100
            pygame.draw.rect(surface, (15, 13, 22, 240), (bx, by, box_w, box_h))
            pygame.draw.rect(surface, (58, 52, 80), (bx, by, box_w, box_h), 2)
            draw_text(surface, self.message[:60], (bx + 20, by + 15), 2, colour=(217, 210, 197))
