"""Headquarters hub scene — where the player loads after death."""
from __future__ import annotations

import pygame
from ..engine.assets import colour, draw_text, text_size
from ..systems import hq as hq_sys
from ..systems.quest_tracker import QuestTracker
from ..systems.dialogue import DialogueSystem


class HQScene:
    """The headquarters hub: NPCs, rooms, quest tracking, dialogue."""

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
        self._update_camera()
        # Accept starting quests
        for q in self.quest_tracker.quests.values():
            if not q.get("prereqs"):
                self.quest_tracker.accept(q["id"])

    def _update_camera(self):
        """Center camera on player."""
        self.camera_x = self.hq_state.player_tx * 32 - 640 + 16
        self.camera_y = self.hq_state.player_ty * 32 - 360 + 16

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
            room = hq_sys.room_at(self.hq_state.player_tx * 32, self.hq_state.player_ty * 32)
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
        rx = room.get("x", 0) * 32 - self.camera_x
        ry = room.get("y", 0) * 32 - self.camera_y
        rw = room.get("w", 8) * 32
        rh = room.get("h", 8) * 32
        # Floor
        floor_col = (40, 36, 52)
        pygame.draw.rect(surface, floor_col, (rx, ry, rw, rh))
        # Walls (border)
        wall_col = (58, 52, 80)
        pygame.draw.rect(surface, wall_col, (rx, ry, rw, 4))
        pygame.draw.rect(surface, wall_col, (rx, ry + rh - 4, rw, 4))
        pygame.draw.rect(surface, wall_col, (rx, ry, 4, rh))
        pygame.draw.rect(surface, wall_col, (rx + rw - 4, ry, 4, rh))
        # Room name
        name = room.get("name", "")
        tw, th = text_size(name, 1)
        if tw > 0:
            draw_text(surface, name, (rx + rw // 2 - tw // 2, ry + 8), 1, colour=(217, 210, 197))

    def _draw_npc(self, surface, npc_state):
        nx = npc_state.x - self.camera_x
        ny = npc_state.y - self.camera_y
        # Draw NPC as a colored rectangle (placeholder until sprites are painted)
        npc_col = (121, 176, 74) if "keeper" in npc_state.definition.get("id", "") else \
                  (232, 178, 60) if "forge" in npc_state.definition.get("id", "") else \
                  (100, 180, 200) if "tide" in npc_state.definition.get("id", "") else \
                  (180, 140, 240) if "raven" in npc_state.definition.get("id", "") else \
                  (196, 99, 95)
        pygame.draw.rect(surface, npc_col, (nx - 12, ny - 12, 24, 24))
        # Name above head
        name = npc_state.definition.get("name", "")
        tw, th = text_size(name, 1)
        if tw > 0:
            draw_text(surface, name, (nx - tw // 2, ny - 24), 1, colour=(217, 210, 197))

    def _draw_player(self, surface):
        px = self.hq_state.player_tx * 32 - self.camera_x
        py = self.hq_state.player_ty * 32 - self.camera_y
        # Player as a white rectangle
        pygame.draw.rect(surface, (232, 178, 60), (px - 10, py - 10, 20, 20))
        # Direction indicator
        draw_text(surface, "YOU", (px - 14, py - 22), 1, colour=(232, 178, 60))

    def _draw_hud(self, surface):
        # Room name
        if self.hq_state.active_room:
            room = hq_sys.room_by_id(self.hq_state.active_room)
            if room:
                draw_text(surface, room.get("name", ""), (10, 10), 2, colour=(217, 210, 197))
        # Controls hint
        draw_text(surface, "WASD: Move | E: Interact | ESC: Menu", (10, 700), 1, colour=(138, 132, 150))
        # Active quests
        quests = self.quest_tracker.active_quests_with_progress()
        if quests:
            draw_text(surface, "QUESTS:", (900, 10), 1, colour=(217, 210, 197))
            for i, q in enumerate(quests[:3]):
                draw_text(surface, q["title"][:30], (900, 30 + i * 40), 1, colour=(121, 176, 74))
                for j, obj in enumerate(q["objectives"][:2]):
                    check = "[x]" if obj["done"] else "[ ]"
                    draw_text(surface, f"  {check} {obj['label'][:25]}", (900, 48 + i * 40 + j * 14), 1, colour=(138, 132, 150))

    def _draw_dialogue(self, surface):
        # Dialogue box at bottom
        box_h = 160
        box_y = 720 - box_h
        pygame.draw.rect(surface, (15, 13, 22, 240), (0, box_y, 1280, box_h))
        pygame.draw.rect(surface, (58, 52, 80), (0, box_y, 1280, 2))
        # NPC name
        if self.dialogue.npc_name:
            draw_text(surface, self.dialogue.npc_name, (20, box_y + 10), 2, colour=(217, 210, 197))
        # Dialogue text
        if self.dialogue.active and self.dialogue.active.current_line():
            line = self.dialogue.active.current_line()
            text = line.get("text", "") if isinstance(line, dict) else str(line)
            draw_text(surface, text[:80], (20, box_y + 40), 1, colour=(232, 178, 60))
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
