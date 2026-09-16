"""Scene stack and the Game loop (shared by headless QA and windowed play)."""

import os
import math
import time

import pygame

from ..systems import meta as meta_sys
from ..systems import save as save_sys
from ..systems import shrines as shrine_sys
from ..systems import world as world_mod
from ..ui import hud as hud_mod
from ..ui import inventory as inventory_mod
from ..ui import menus as menus_mod
from ..ui import minimap as minimap_mod
from ..engine.assets import Atlas, colour, draw_text, text_size, load_palette
from ..engine.input import KeyboardInput, ScriptedInput, ReplayInput
from ..engine.gamepad import GamepadInput
from ..engine.renderer import Renderer
from ..engine.audio import Audio, play, play_death, play_victory
from ..engine.profiler import Profiler  # noqa: E402
from ..ui.settings import RESOLUTION_MODES

tree_state = meta_sys.tree_state

VICTORY_TEXT = "THE LANTERN STILL BURNS"


class Scene:
    """Base scene: one of these is on top of the stack at any time."""

    transparent = False

    def __init__(self, game):
        self.game = game

    def handle_event(self, event):
        return None

    def update(self, dt):
        return None

    def draw(self, surface):
        return None


class RunScene(Scene):
    """The playable run: world stepping, HUD, minimap, inventory overlay."""

    def __init__(self, game, seed=None, floor=1, data_dir=None, mod_dir=None):
        super().__init__(game)
        settings = (game.profile or {}).get("settings", {}) or {}
        self.world = world_mod.World(
            seed=game.args.seed if seed is None else seed,
            profile=game.profile,
            headless=game.headless,
            start_floor=floor,
            audio=not game.headless,
            warnings=game.warnings,
            settings=settings,
            data_dir=data_dir,
            mod_dir=mod_dir,
        )
        # P1.8: endless mode and run curses from CLI args
        self.world.endless = bool(getattr(game.args, "endless", False))
        self.world.run_curses = list(getattr(game.args, "curses", []) or [])
        self.world._curses_applied = False  # reset flag for new run
        # P1.8: apply run_curses to player now that they're set
        if self.world.run_curses:
            shrine_sys.apply_curse_list(self.world, self.world.run_curses)
            self.world._curses_applied = True
            # Register curses in shrine_active_effects for HUD display
            for _cid in self.world.run_curses:
                _cdef = None
                for _c in shrine_sys.CURSES:
                    if _c["id"] == _cid:
                        _cdef = _c
                        break
                if _cdef:
                    if not hasattr(self.world, "shrine_active_effects"):
                        self.world.shrine_active_effects = []
                    self.world.shrine_active_effects.append({
                        "name": "CURSE: " + _cdef["name"],
                        "color": (196, 99, 95),
                        "remaining": 0.0,  # permanent, no timer
                    })
        self.hud = hud_mod.HUD()
        self.inventory = inventory_mod.InventoryOverlay()
        # P5.3: profiler overlay (toggled by F1)
        self.profiler = Profiler()
        # P2.6: apply settings to the run
        settings = (game.profile or {}).get("settings", {}) or {}
        if game.script is not None:
            self.world.input_source = game.script
            self.input_source = game.script
        else:
            if not game.headless:
                km = settings.get("key_map", {})
                hold_to_attack = settings.get("hold_to_attack", False)
                self.input_source = KeyboardInput(key_map=km, hold_to_attack=hold_to_attack)
                # P2.6: gamepad support
                if settings.get("gamepad_enabled", False):
                    self.gamepad = GamepadInput()
                    if self.gamepad.available:
                        self.input_source = self.gamepad
                    else:
                        self.gamepad = None  # fallback to keyboard
                else:
                    self.gamepad = None
                # P2.6: sync shake_enabled from settings
                self.world.camera.shake_enabled = settings.get("shake_enabled", True)
                # P2.6: store settings on world for combat/renderer to read
                self.world.settings = settings
            else:
                self.input_source = None
            # P5.2: wire replay input source if provided
            if getattr(game, "replay", None) is not None:
                self.world.input_source = game.replay
                self.input_source = game.replay
        self.paused = False
        self._ended = False
        self.pause_menu = menus_mod.ListMenu([("resume", "Resume", True),
                                              ("inventory", "Inventory (TAB)", True),
                                              ("settings", "Settings", True),
                                              ("save", "Save & quit to menu", True)])
        self.end_timer = 0.0

    # -- input -----------------------------------------------------------
    def _handle_reward_choice(self):
        """Handle the reward choice UI for a cleared room.

        Headless mode auto-selects 'heal'. Windowed mode waits
        for player input via the input source.
        """
        if self.world._pending_room is None:
            return
        if self.world.headless:
            # Auto-choose in headless mode
            self.world.choose_room_reward("heal")
            return
        # Windowed mode: check for player input
        inp = self.sample_input()
        if inp is None:
            return
        # Auto-select first option if no input (safety for testing)
        # In real game, this would show a menu and wait for Enter
        import pygame
        keys = pygame.key.get_pressed()
        if keys[pygame.K_e]:
            # Choose the first available option
            choice = self.world.active_reward_choice
            if choice:
                options = choice.get("options", ["heal"])
                self.world.choose_room_reward(options[0])


    def handle_event(self, event):
        if event.type == pygame.KEYDOWN:
            if self.inventory.open:
                if self.inventory.handle_key(self.world, event.key):
                    return None
            if event.key == pygame.K_f:
                # P2.1: toggle screen shake
                self.world.camera.shake_enabled = not self.world.camera.shake_enabled
                return None
            elif event.key == pygame.K_F1:
                # P5.3: toggle profiler overlay
                self.profiler.visible = not self.profiler.visible
                return None
            elif event.key == pygame.K_TAB:
                self.inventory.toggle()
            elif event.key in (pygame.K_ESCAPE, pygame.K_p):
                self.paused = not self.paused
            elif event.key == pygame.K_RETURN and self.world.run_state != "running":
                self.game.end_run()
            elif self.paused:
                # pause menu navigation
                if event.key in (pygame.K_UP, pygame.K_w):
                    self.pause_menu.move(-1)
                elif event.key in (pygame.K_DOWN, pygame.K_s):
                    self.pause_menu.move(1)
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    entry = self.pause_menu.enabled_current()
                    if entry:
                        key = entry[0]
                        if key == "resume":
                            self.paused = False
                        elif key == "inventory":
                            self.inventory.toggle()
                            self.paused = False
                        elif key == "settings":
                            self.game.push(SettingsScene(self.game))
                        elif key == "save":
                            self._ended = True
                            self.game.end_run()
        return None

    def sample_input(self):
        if self.input_source is None:
            return None
        return self.input_source.sample(self.world)

    def update(self, dt):
        if self._ended:
            return
        if self.paused or self.inventory.open:
            return
        if self.world.run_state != "running":
            self.end_timer += dt
            if self.end_timer > 1.2:
                self._ended = True
                self.game.end_run()
            return
        # P3.1: if a reward choice is pending, handle it
        if self.world.active_reward_choice is not None:
            self._handle_reward_choice()
            return
        self.profiler.tick_start()
        self.world.step(world_mod.TICK, self.sample_input())
        self.profiler.tick_end()
        self.hud.update(self.world, dt)
        # P5.3: update profiler (count entities, particles, atlas mem)
        self.profiler.tick(self.world)

    # -- drawing ---------------------------------------------------------
    def draw(self, surface, dt=0.0):
        self.game.renderer.draw(self.world, surface, dt)
        self.hud.draw(self.world, surface)
        minimap_mod.draw_minimap(self.world, surface)
        self.inventory.draw(self.world, surface)
        # P5.3: profiler overlay
        self.profiler.draw(surface, self.world)
        if self.paused:
            menus_mod.draw_pause(surface, self.pause_menu)


class MenuScene(Scene):
    """Main menu: new run / continue / meta upgrades / class / ascension / quit."""

    def __init__(self, game):
        super().__init__(game)
        self.rebuild()
        self.title_anim_timer = 0.0
        self.title_anim_frame = 0
        self.title_pulse = 0.0
        # r51: title particles
        self.title_particles = []
        self.title_particle_timer = 0.0

    def rebuild(self):
        profile = self.game.profile
        run = profile.get("run") if profile else None
        entries = [("new", "New descent", True)]
        # P1.8: daily descent — deterministic seed from today's date
        import time as _time
        daily_seed = int(_time.strftime("%Y%m%d"))
        entries.append(("daily", "Daily descent  (seed %d)" % daily_seed, True))
        # P1.8: cursed descent entry
        entries.append(("curses", "Cursed descent", True))
        if run:
            entries.append(("continue", "Continue (floor %d)" % int(run.get("floor", 1)), True))
        entries.append(("meta", "Meta upgrades  (%d essence)" % int(profile.get("essence", 0)), True))
        # P2.6: settings entry
        entries.append(("settings", "Settings", True))
        # P1.4: class select entry — show current class
        class_id = str(profile.get("class_id", "lantern_keeper") or "lantern_keeper")
        class_def = save_sys.CLASS_DEFS.get(class_id, save_sys.CLASS_DEFS["lantern_keeper"])
        entries.append(("class", "Class: %s" % class_def["name"], True))
        # P1.4: ascension entry — show current ascension
        asc = int(profile.get("ascension", 0) or 0)
        unlocked_asc = int(profile.get("unlocked_ascension", 0) or 0)
        asc_label = "Ascension: %d (unlocked: %d)" % (asc, unlocked_asc)
        entries.append(("ascension", asc_label, True))
        entries.append(("quit", "Quit", True))
        self.menu = menus_mod.ListMenu(entries)

    def handle_event(self, event):
        if event.type != pygame.KEYDOWN:
            return None
        if event.key in (pygame.K_UP, pygame.K_w):
            self.menu.move(-1)
        elif event.key in (pygame.K_DOWN, pygame.K_s):
            self.menu.move(1)
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            entry = self.menu.enabled_current()
            if entry is None:
                return None
            key = entry[0]
            if key == "new":
                self.game.start_run()
            elif key == "daily":
                import time as _time
                self.game.start_run(seed=int(_time.strftime("%Y%m%d")))
            elif key == "curses":
                self.game.push(CurseSelectScene(self.game))
            elif key == "continue":
                self.game.continue_run()
            elif key == "meta":
                self.game.push(MetaShopScene(self.game))
            elif key == "settings":
                self.game.push(SettingsScene(self.game))
            elif key == "class":
                self.game.push(ClassSelectScene(self.game))
            elif key == "ascension":
                self.game.push(AscensionSelectScene(self.game))
            elif key == "quit":
                self.game.quit_requested = True
        return None

    def update(self, dt):
        """r51: update title particles (deterministic pattern, no RNG)."""
        self.title_particle_timer += dt
        # Spawn new particles every 0.1s using a counter for determinism
        if self.title_particle_timer > 0.1:
            self.title_particle_timer = 0.0
            idx = len(self.title_particles)
            # Deterministic positions based on index
            x = (idx * 37) % 1280
            vx = float((idx % 5) - 2) * 4.0  # -8 to 8
            vy = -20.0 - float(idx % 10) * 1.5  # -20 to -35
            life = 3.0 + float(idx % 30) / 10.0  # 3.0 to 6.0
            size = 2 + (idx % 4)  # 2 to 5
            self.title_particles.append({
                "x": float(x), "y": 720.0 + 10.0,
                "vx": vx, "vy": vy,
                "life": life, "size": size,
            })
        # Update positions
        alive = []
        for p in self.title_particles:
            p["life"] -= dt
            if p["life"] <= 0:
                continue
            p["x"] += p["vx"] * dt
            p["y"] += p["vy"] * dt
            alive.append(p)
        self.title_particles = alive

    def draw(self, surface):
        # r49: title background image
        try:
            atlas = Atlas.load("title")
            if atlas and atlas.has("background"):
                bg = atlas.frame("background")
                if bg:
                    surface.blit(bg, (0, 0))
            else:
                surface.fill(colour("void", (11, 10, 16)))
        except Exception:
            surface.fill(colour("void", (11, 10, 16)))
        # P4.5: animated title with pulsing lantern effect
        self.title_anim_timer += 0.016
        self.title_pulse = 0.5 + 0.5 * math.sin(self.title_anim_timer * 2.0)
        frame_idx = int(self.title_anim_timer * 6) % 8
        menus_mod.draw_title_animated(surface, "DEPTHS OF VAELMOOR",
                                      "a lantern, five floors at a time",
                                      y=110, frame_idx=frame_idx,
                                      pulse=self.title_pulse)
        # P4.3: play title theme music
        if not self.game.headless:
            audio = getattr(self.game, "_audio", None)
            if audio is None:
                audio = Audio(enabled=not self.game.headless)
                self.game._audio = audio
            audio.play_title_theme()
        stats = self.game.profile.get("stats", {}) if self.game.profile else {}
        draw_text(surface, "runs %d   best floor %d   kills %d"
                  % (int(stats.get("runs", 0)), int(stats.get("best_floor", 1)),
                     int(stats.get("kills", 0))),
                  ((surface.get_width() - text_size("runs 0   best floor 1   kills 0", 1)[0]) // 2, 200),
                  1, colour=(138, 132, 150))
        # r51: title particles (soul wisps)
        for p in self.title_particles:
            alpha = max(0.1, min(1.0, p["life"] / 3.0))
            col = tuple(int(c * alpha) for c in (100, 180, 220))
            pygame.draw.circle(surface, col, (int(p["x"]), int(p["y"])), p["size"])
        menus_mod.draw_list(surface, self.menu, top=380)
        menus_mod.draw_controls(surface, self.game.profile)
        # P4.5: draw run stats below menu
        if self.game.headless:
            draw_text(surface, "SEED: %d" % (getattr(self.game, "_seed", 0) or 0),
                      (80, 500), 1, colour=(93, 98, 114))


class MetaShopScene(Scene):
    def __init__(self, game):
        super().__init__(game)
        from ..systems import save as save_sys
        from ..systems import meta as meta_sys
        self.profile = game.profile
        self.rows = meta_sys.tree_state(self.profile)
        self.index = 0

    def handle_event(self, event):
        if event.type != pygame.KEYDOWN:
            return None
        if event.key in (pygame.K_UP, pygame.K_w):
            self.index = (self.index - 1) % max(1, len(self.rows))
        elif event.key in (pygame.K_DOWN, pygame.K_s):
            self.index = (self.index + 1) % max(1, len(self.rows))
        elif event.key == pygame.K_RETURN and self.rows:
            row = self.rows[self.index]
            if save_sys.purchase(self.profile, row["id"]):
                save_sys.save_profile(self.profile)
                self.rows = meta_sys.tree_state(self.profile)
                self.index = 0
        elif event.key == pygame.K_ESCAPE:
            self.game.pop()
            if isinstance(self.game.top(), MenuScene):
                self.game.top().rebuild()
        return None

    def draw(self, surface):
        from ..systems.save import meta_stat_totals
        surface.fill(colour("void", (11, 10, 16)))
        menus_mod.draw_meta_shop(surface, self.profile, self.rows, self.index,
                                 int(self.profile.get("essence", 0)),
                                 meta_stat_totals(self.profile))


class ClassSelectScene(Scene):
    """P1.4: choose a starting loadout (class).  Locked classes show unlock conditions."""

    def __init__(self, game):
        super().__init__(game)
        self.profile = game.profile
        self.class_ids = save_sys.CLASS_IDS
        self.index = 0

    def handle_event(self, event):
        if event.type != pygame.KEYDOWN:
            return None
        if event.key in (pygame.K_UP, pygame.K_w):
            self.index = (self.index - 1) % len(self.class_ids)
        elif event.key in (pygame.K_DOWN, pygame.K_s):
            self.index = (self.index + 1) % len(self.class_ids)
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            cid = self.class_ids[self.index]
            unlocked = set(self.profile.get("unlocked_classes", ["lantern_keeper"]))
            if cid in unlocked:
                self.profile["class_id"] = cid
                save_sys.save_profile(self.profile)
                self._back()
        elif event.key == pygame.K_ESCAPE:
            self._back()
        return None

    def _back(self):
        self.game.pop()
        if isinstance(self.game.top(), MenuScene):
            self.game.top().rebuild()

    def draw(self, surface):
        surface.fill(colour("void", (11, 10, 16)))
        menus_mod.draw_title(surface, "CHOOSE YOUR KEEPER", "pick a loadout for the next descent", y=52)
        unlocked = set(self.profile.get("unlocked_classes", ["lantern_keeper"]))
        current = str(self.profile.get("class_id", "lantern_keeper") or "lantern_keeper")
        y = 120
        for i, cid in enumerate(self.class_ids):
            defn = save_sys.CLASS_DEFS[cid]
            is_unlocked = cid in unlocked
            is_current = cid == current
            selected = (i == self.index)
            col = (232, 178, 60) if selected else ((246, 242, 232) if is_unlocked else (93, 98, 114))
            x = 80
            prefix = "> " if selected else ("* " if is_current else "  ")
            name = defn["name"]
            draw_text(surface, prefix + name, (x, y), 2, colour=col)
            st = defn["stats"]
            stat_line = "HP %d  DMG %d  SPD %.1f  ARM %d%%  LUCK %d  CRIT %d%%" % (
                int(st["max_hp"]), int(st["damage"]), st["speed"],
                int(round(st["armor"] * 100)), int(st["luck"]), int(round(st["crit"] * 100)))
            draw_text(surface, "  " + stat_line, (x, y + 28), 1, colour=(138, 132, 150))
            if not is_unlocked:
                draw_text(surface, "  [LOCKED] %s" % defn["unlock_desc"],
                          (x, y + 44), 1, colour=(93, 98, 114))
            y += 68
        draw_text(surface, "UP/DOWN choose   ENTER select   ESC back",
                  (80, surface.get_height() - 40), 1, colour=(93, 98, 114))


class AscensionSelectScene(Scene):
    """P1.4: choose an ascension tier (0-5).  Only unlocked tiers are selectable."""

    ASCENSION_LABELS = [
        (0, "Ascension 0", "No modifiers — the standard descent."),
        (1, "Ascension 1", "+10% enemy HP."),
        (2, "Ascension 2", "+10% enemy damage."),
        (3, "Ascension 3", "+15% elite chance."),
        (4, "Ascension 4", "-15% healing from all sources."),
        (5, "Ascension 5", "All of the above + boss gets a random affix."),
    ]

    def __init__(self, game):
        super().__init__(game)
        self.profile = game.profile
        self.index = 0

    def handle_event(self, event):
        if event.type != pygame.KEYDOWN:
            return None
        if event.key in (pygame.K_UP, pygame.K_w):
            self.index = (self.index - 1) % len(self.ASCENSION_LABELS)
        elif event.key in (pygame.K_DOWN, pygame.K_s):
            self.index = (self.index + 1) % len(self.ASCENSION_LABELS)
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            level = self.ASCENSION_LABELS[self.index][0]
            unlocked_asc = int(self.profile.get("unlocked_ascension", 0) or 0)
            if level <= unlocked_asc:
                self.profile["ascension"] = level
                save_sys.save_profile(self.profile)
                self._back()
        elif event.key == pygame.K_ESCAPE:
            self._back()
        return None

    def _back(self):
        self.game.pop()
        if isinstance(self.game.top(), MenuScene):
            self.game.top().rebuild()

    def draw(self, surface):
        surface.fill(colour("void", (11, 10, 16)))
        menus_mod.draw_title(surface, "ASCENSION", "higher tiers = harder depths", y=52)
        unlocked_asc = int(self.profile.get("unlocked_ascension", 0) or 0)
        current_asc = int(self.profile.get("ascension", 0) or 0)
        y = 130
        for i, (level, label, desc) in enumerate(self.ASCENSION_LABELS):
            is_unlocked = level <= unlocked_asc
            is_current = level == current_asc
            selected = (i == self.index)
            col = (232, 178, 60) if selected else ((246, 242, 232) if is_unlocked else (93, 98, 114))
            x = 80
            prefix = "> " if selected else ("* " if is_current else "  ")
            draw_text(surface, prefix + label, (x, y), 2, colour=col)
            draw_text(surface, "  " + desc, (x, y + 28), 1, colour=(138, 132, 150))
            if not is_unlocked:
                draw_text(surface, "  [LOCKED] beat the boss at ascension %d to unlock" % (level - 1),
                          (x, y + 44), 1, colour=(93, 98, 114))
            y += 62
        draw_text(surface, "UP/DOWN choose   ENTER select   ESC back",
                  (80, surface.get_height() - 40), 1, colour=(93, 98, 114))


class SettingsScene(Scene):
    """P2.6: accessibility and controls settings, persisted to save.json.
    
    Toggles: screen shake, damage numbers, reduced flashing, hold-to-attack,
    gamepad.  Cycles: font scale (1/2), colourblind mode (off/protan/deutan/tritan).
    Key remapping: enter remap mode for a bound action, press any key to bind it.
    
    P4.5: categorized display into Video / Audio / Controls / Accessibility sections.
    """

    CATEGORIES = {
        "video": ["resolution", "fullscreen", "vsync", "fps_cap",
                   "screen_shake", "damage_numbers", "reduced_flashing", "font_scale"],
        "audio": ["volume", "music_volume", "sfx_volume"],
        "controls": ["gamepad_enabled", "key_map", "hold_to_attack"],
        "accessibility": ["colourblind_mode"],
    }
    # Add settings that exist in defaults for volume
    SETTING_LABELS_EXTRA = {
        "volume": "Volume",
        "music_volume": "Music Volume",
        "sfx_volume": "SFX Volume",
        "screen_shake": "Screen Shake",
        "resolution": "Resolution",
        "fullscreen": "Fullscreen",
        "vsync": "VSync",
        "fps_cap": "FPS Cap",
    }

    def __init__(self, game):
        super().__init__(game)
        self.profile = game.profile
        from ..ui.settings import normalize
        self.settings = normalize(self.profile.get("settings", {}))
        # Add volume settings if missing
        for vol_key in ("volume", "music_volume", "sfx_volume"):
            if vol_key not in self.settings:
                self.settings[vol_key] = 0.8 if vol_key == "volume" else 0.7
        self.index = 0
        self.category_index = 0
        self.remap_mode = False
        self.remap_action = None
        self._remap_index = 0
        self.category_names = list(self.CATEGORIES.keys())
        self.cursor_names = self._category_entries()
        self.cursor_names.append("remap")
        self.cursor_names.append("reset")
        self.cursor_names.append("back")

    def handle_event(self, event):
        if event.type != pygame.KEYDOWN:
            return None
        if self.remap_mode:
            self._handle_remap(event)
            return None
        if event.key in (pygame.K_UP, pygame.K_w):
            self.index = (self.index - 1) % len(self.cursor_names)
        elif event.key in (pygame.K_DOWN, pygame.K_s):
            self.index = (self.index + 1) % len(self.cursor_names)
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            self._activate()
        elif event.key in (pygame.K_LEFT, pygame.K_RIGHT):
            self._cycle(event.key == pygame.K_RIGHT)
        elif event.key == pygame.K_ESCAPE:
            self._back()
        elif event.key in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4):
            # P4.5: category switching with 1-4 keys
            idx = event.key - pygame.K_1
            if idx < len(self.category_names):
                self._cycle_category(idx >= self.category_index)
                # Determine direction: cycle to the target category
                target = idx
                if target != self.category_index:
                    self.category_index = target
                    self.cursor_names = self._category_entries()
                    self.index = 0
        return None

    def _category_entries(self):
        """Build the flat cursor list from current category."""
        cat = self.category_names[self.category_index]
        entries = self.CATEGORIES.get(cat, [])
        # Only include entries that have settings or are meaningful
        result = []
        for e in entries:
            if e == "key_map" and e not in self.settings:
                continue
            result.append(e)
        return result

    def _cycle_category(self, forward):
        """Switch to the next/previous category tab."""
        n = len(self.category_names)
        if forward:
            self.category_index = (self.category_index + 1) % n
        else:
            self.category_index = (self.category_index - 1) % n
        self.cursor_names = self._category_entries()
        self.index = 0  # reset cursor within category

    def _activate(self):
        name = self.cursor_names[self.index]
        if name == "back":
            self._back()
        elif name == "reset":
            from ..ui.settings import default
            self.settings = default()
        elif name == "remap":
            self.remap_mode = True
            self._remap_index = 0
            self.remap_action = self._remap_actions()[0]
        elif name in self.settings:
            if name == "font_scale":
                self.settings["font_scale"] = 2 if self.settings["font_scale"] <= 1 else 1
            elif name == "colourblind_mode":
                from ..ui.settings import COLOURBLIND_MODES
                idx = COLOURBLIND_MODES.index(self.settings.get("colourblind_mode", "off"))
                self.settings["colourblind_mode"] = COLOURBLIND_MODES[(idx + 1) % len(COLOURBLIND_MODES)]
            elif name == "resolution":
                resolutions = ["1280x720", "1920x1080", "2560x1440"]
                idx = resolutions.index(self.settings.get("resolution", "1280x720"))
                self.settings["resolution"] = resolutions[(idx + 1) % len(resolutions)]
            elif name == "fullscreen":
                self.settings["fullscreen"] = not self.settings["fullscreen"]
            elif name == "vsync":
                self.settings["vsync"] = not self.settings["vsync"]
            elif name == "fps_cap":
                fps_options = [30, 60, 120, "unlimited"]
                current = self.settings.get("fps_cap", 60)
                idx = fps_options.index(current)
                self.settings["fps_cap"] = fps_options[(idx + 1) % len(fps_options)]
            else:
                # toggle a boolean
                self.settings[name] = not self.settings[name]

    def _cycle(self, forward):
        name = self.cursor_names[self.index]
        if name == "font_scale":
            self.settings["font_scale"] = 2 if forward and self.settings["font_scale"] <= 1 else 1
        elif name == "colourblind_mode":
            from ..ui.settings import COLOURBLIND_MODES
            idx = COLOURBLIND_MODES.index(self.settings.get("colourblind_mode", "off"))
            self.settings["colourblind_mode"] = COLOURBLIND_MODES[(idx + (1 if forward else -1)) % len(COLOURBLIND_MODES)]

    def _handle_remap(self, event):
        if event.key == pygame.K_ESCAPE:
            if self.remap_action is not None:
                self.remap_action = None
            else:
                self.remap_mode = False
            return
        # Bind the pressed key to the current remap target
        if self.remap_action is not None:
            self.settings.setdefault("key_map", {})[self.remap_action] = event.key
            self.remap_action = None
            # Advance to next action automatically
            actions = self._remap_actions()
            idx = self._remap_index
            if idx + 1 < len(actions):
                self._remap_index = idx + 1
                self.remap_action = actions[idx + 1]
            else:
                self.remap_mode = False
                self._back()

    def _remap_actions(self):
        return ["move_up", "move_down", "move_left", "move_right",
                "attack", "dash", "interact", "inventory"]

    def _back(self):
        self.profile["settings"] = self.settings
        save_sys.save_profile(self.profile)
        self.game.pop()
        if isinstance(self.game.top(), MenuScene):
            self.game.top().rebuild()

    def draw(self, surface):
        from ..ui.settings import SETTING_LABELS, ACTION_LABELS, COLOURBLIND_MODES
        surface.fill(colour("void", (11, 10, 16)))
        menus_mod.draw_title(surface, "SETTINGS", "accessibility & controls", y=52)
        # P4.5: category tabs
        cat = self.category_names[self.category_index]
        cat_labels = {"video": "VIDEO", "audio": "AUDIO", "controls": "CONTROLS", "accessibility": "ACCESSIBILITY"}
        tab_x = 80
        for ci, cn in enumerate(self.category_names):
            is_active = ci == self.category_index
            col = (232, 178, 60) if is_active else (93, 98, 114)
            draw_text(surface, cat_labels.get(cn, cn), (tab_x, 100), 2, colour=col)
            tab_x += text_size(cat_labels.get(cn, cn), 2)[0] + 20
        # Draw category separator line
        pygame.draw.line(surface, (58, 52, 80), (80, 126), (1200, 126), 1)
        y = 140
        for i, name in enumerate(self.cursor_names):
            selected = (i == self.index)
            x = 80
            if name == "back":
                label = "Back"
                col = (232, 178, 60) if selected else (246, 242, 232)
            elif name == "reset":
                label = "Reset to Defaults"
                col = (196, 99, 95) if selected else (246, 242, 232)
            elif name == "remap":
                label = "Remap Keys"
                col = (232, 178, 60) if selected else (246, 242, 232)
            else:
                label = SETTING_LABELS.get(name, self.SETTING_LABELS_EXTRA.get(name, name))
                val = self.settings.get(name)
                if isinstance(val, bool):
                    val_str = "ON" if val else "OFF"
                    val_col = (121, 176, 74) if val else (196, 99, 95)
                elif name == "font_scale":
                    val_str = "Large" if val == 2 else "Normal"
                    val_col = (121, 176, 74)
                elif name == "colourblind_mode":
                    val_str = val if val != "off" else "Off"
                    val_col = (121, 176, 74) if val == "off" else (232, 178, 60)
                elif name == "resolution":
                    val_str = val
                    val_col = (232, 178, 60)
                elif name == "fullscreen":
                    val_str = "ON" if val else "OFF"
                    val_col = (121, 176, 74) if val else (196, 99, 95)
                elif name == "vsync":
                    val_str = "ON" if val else "OFF"
                    val_col = (121, 176, 74) if val else (196, 99, 95)
                elif name == "fps_cap":
                    val_str = str(val)
                    val_col = (121, 176, 74)
                elif name in ("volume", "music_volume", "sfx_volume"):
                    val_str = "%d%%" % int(val * 100)
                    val_col = (121, 176, 74)
                elif name == "key_map":
                    val_str = "Press a key..." if self.remap_mode else "Click to remap"
                    val_col = (138, 132, 150) if not self.remap_mode else (232, 178, 60)
                else:
                    val_str = str(val)
                    val_col = (246, 242, 232)
                full = "%-22s %s" % (label, val_str)
                col = val_col if not selected else (232, 178, 60)
                if selected:
                    draw_text(surface, ">", (x - 20, y), 2, colour=(232, 178, 60))
                draw_text(surface, label, (x, y), 2, colour=col)
                draw_text(surface, val_str, (x + 300, y), 2, colour=val_col)
                y += 28
                continue
            if selected:
                draw_text(surface, ">", (x - 20, y), 2, colour=(232, 178, 60))
            draw_text(surface, label, (x, y), 2, colour=col)
            y += 28
        # Category navigation hint
        if not self.remap_mode:
            draw_text(surface, "1-4 switch category   UP/DOWN navigate   ENTER toggle   ESC back",
                      (80, surface.get_height() - 40), 1, colour=(93, 98, 114))
        self._draw_volume_sliders(surface)

    def _draw_volume_sliders(self, surface):
        """Draw volume sliders for the current audio category."""
        cat = self.category_names[self.category_index]
        if cat != "audio":
            return
        audio_keys = ("volume", "music_volume", "sfx_volume")
        y_start = 140
        for ki, kname in enumerate(audio_keys):
            if kname not in self.cursor_names:
                continue
            idx_in_list = self.cursor_names.index(kname)
            y = y_start + idx_in_list * 28
            val = self.settings.get(kname, 0.8)
            bar_w = 200
            bar_h = 12
            bar_x = 420
            bar_y = y - 4
            # Background bar
            pygame.draw.rect(surface, (58, 52, 80), (bar_x, bar_y, bar_w, bar_h))
            # Fill
            fill_w = int(bar_w * val)
            if fill_w > 0:
                pygame.draw.rect(surface, (121, 176, 74), (bar_x, bar_y, fill_w, bar_h))
            # Label
            draw_text(surface, "%s: %d%%" % (kname.replace("_", " ").title(), int(val * 100)),
                      (bar_x + bar_w + 10, y), 1, colour=(246, 242, 232))

    def _cycle(self, forward):
        name = self.cursor_names[self.index]
        if name == "font_scale":
            self.settings["font_scale"] = 2 if forward and self.settings["font_scale"] <= 1 else 1
        elif name == "colourblind_mode":
            from ..ui.settings import COLOURBLIND_MODES
            idx = COLOURBLIND_MODES.index(self.settings.get("colourblind_mode", "off"))
            self.settings["colourblind_mode"] = COLOURBLIND_MODES[(idx + (1 if forward else -1)) % len(COLOURBLIND_MODES)]
        elif name == "resolution":
            resolutions = ["1280x720", "1920x1080", "2560x1440"]
            idx = resolutions.index(self.settings.get("resolution", "1280x720"))
            self.settings["resolution"] = resolutions[(idx + (1 if forward else -1)) % len(resolutions)]
        elif name == "fps_cap":
            fps_options = [30, 60, 120, "unlimited"]
            current = self.settings.get("fps_cap", 60)
            idx = fps_options.index(current)
            self.settings["fps_cap"] = fps_options[(idx + (1 if forward else -1)) % len(fps_options)]
        elif name == "volume":
            self.settings["volume"] = min(1.0, self.settings["volume"] + 0.1) if forward else max(0.0, self.settings["volume"] - 0.1)
        elif name == "music_volume":
            self.settings["music_volume"] = min(1.0, self.settings["music_volume"] + 0.1) if forward else max(0.0, self.settings["music_volume"] - 0.1)
        elif name == "sfx_volume":
            self.settings["sfx_volume"] = min(1.0, self.settings["sfx_volume"] + 0.1) if forward else max(0.0, self.settings["sfx_volume"] - 0.1)


class CurseSelectScene(Scene):
    """P1.8: pick optional curse modifiers before a run. Each curse boosts essence reward."""

    CURSE_DEFS = [
        {"id": "heavy_boots", "name": "Heavy Boots", "desc": "-20% move speed for the run."},
        {"id": "fragile",     "name": "Fragile",      "desc": "-15 max HP for the run."},
        {"id": "diminished",  "name": "Diminished",   "desc": "-2 damage for the run."},
        {"id": "exposed",     "name": "Exposed",       "desc": "-3 armor for the run."},
        {"id": "gold_tax",    "name": "Gold Tax",      "desc": "25% of gold drops lost."},
    ]

    def __init__(self, game):
        super().__init__(game)
        self.profile = game.profile
        self.selected = set()

    def handle_event(self, event):
        if event.type != pygame.KEYDOWN:
            return None
        if event.key in (pygame.K_UP, pygame.K_w):
            self._move_cursor(-1)
        elif event.key in (pygame.K_DOWN, pygame.K_s):
            self._move_cursor(1)
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            cid = self.CURSE_DEFS[self._cursor]["id"]
            if cid in self.selected:
                self.selected.discard(cid)
            else:
                self.selected.add(cid)
        elif event.key == pygame.K_ESCAPE:
            self._confirm()
        return None

    def _move_cursor(self, delta):
        n = len(self.CURSE_DEFS)
        if not hasattr(self, "_cursor"):
            self._cursor = 0
        self._cursor = (self._cursor + delta) % n

    def _confirm(self):
        if hasattr(self.game, "args") and self.game.args is not None:
            self.game.args.curses = sorted(self.selected)
        self.game.pop()
        if isinstance(self.game.top(), MenuScene):
            self.game.top().rebuild()

    def draw(self, surface):
        surface.fill(colour("void", (11, 10, 16)))
        n_curses = len(self.selected)
        menus_mod.draw_title(surface, "CURSED DESCENT",
                             "%d curses selected  (+%d%% essence)" % (n_curses, int(n_curses * 15)),
                             y=52)
        if not hasattr(self, "_cursor"):
            self._cursor = 0
        y = 130
        for i, cdef in enumerate(self.CURSE_DEFS):
            is_selected = cdef["id"] in self.selected
            is_cursor = (i == self._cursor)
            col = (232, 178, 60) if is_cursor else ((196, 99, 95) if is_selected else (246, 242, 232))
            x = 80
            prefix = "> " if is_cursor else ("* " if is_selected else "  ")
            draw_text(surface, prefix + cdef["name"], (x, y), 2, colour=col)
            draw_text(surface, "  " + cdef["desc"], (x, y + 28), 1, colour=(138, 132, 150))
            y += 56
        draw_text(surface, "UP/DOWN move   ENTER toggle   ESC confirm & start",
                  (80, surface.get_height() - 40), 1, colour=(93, 98, 114))


class EndScene(Scene):
    """Death or victory summary."""

    def __init__(self, game, world, victory):
        super().__init__(game)
        self.world = world
        self.victory = victory
        self.menu = menus_mod.ListMenu([
            ("retry", "Descend again", True),
            ("meta", "Meta upgrades  (%d essence)" % int(game.profile.get("essence", 0)), True),
            ("menu", "Main menu", True),
        ])

    def handle_event(self, event):
        if event.type != pygame.KEYDOWN:
            return None
        if event.key in (pygame.K_UP, pygame.K_w):
            self.menu.move(-1)
        elif event.key in (pygame.K_DOWN, pygame.K_s):
            self.menu.move(1)
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            entry = self.menu.enabled_current()
            if entry is None:
                return None
            key = entry[0]
            if key == "retry":
                self.game.start_run(seed=self.world.seed + 1)
            elif key == "meta":
                self.game.push(MetaShopScene(self.game))
            else:
                self.game.show_menu()
        return None

    def draw(self, surface):
        surface.fill(colour("void", (11, 10, 16)))
        # P4.7: play death/victory sting
        if self.victory:
            play_victory()
        else:
            play_death()
        menus_mod.draw_end_screen(surface, self.world, self.victory, self.game.profile, self.menu)


class SceneStack:
    def __init__(self):
        self.stack = []

    def push(self, scene):
        self.stack.append(scene)

    def pop(self):
        if self.stack:
            return self.stack.pop()
        return None

    def top(self):
        return self.stack[-1] if self.stack else None

    def replace(self, scene):
        self.stack = [scene]

    def update(self, dt):
        scene = self.top()
        if scene is not None:
            scene.update(dt)

    def handle_event(self, event):
        scene = self.top()
        if scene is not None:
            scene.handle_event(event)

    def draw(self, surface, dt=0.0):
        scene = self.top()
        if scene is None:
            return
        if isinstance(scene, RunScene):
            scene.draw(surface, dt)
        else:
            scene.draw(surface)


class Game:
    """Owns the profile, the scene stack and the main loop."""

    RENDER_SIZE = (1280, 720)

    def __init__(self, args, profile, warnings, headless=False, save_path=None):
        self.args = args
        self.profile = profile
        self.warnings = warnings
        self.headless = headless
        self.save_path = save_path or save_sys.DEFAULT_SAVE_PATH
        self.data_dir = getattr(args, "data_dir", None)
        self.mod_dir = getattr(args, "mod_dir", None)
        # P4.6: resolution scaling from profile settings
        settings = profile.get("settings", {}) if profile else {}
        resolution = settings.get("resolution", "1280x720")
        if resolution in RESOLUTION_MODES:
            self.render_size = list(RESOLUTION_MODES[resolution][:2])
        elif "x" in resolution:
            w, h = resolution.split("x")
            self.render_size = [int(w), int(h)]
        else:
            self.render_size = [1280, 720]
        self.render_size = tuple(self.render_size)
        self.display_size = self.render_size
        self.display_scale = 1
        self.size = self.render_size  # backward compat alias
        self.render_surface = pygame.Surface(self.render_size)
        self.display_surface = None
        self.renderer = Renderer(self.render_size)
        self.scenes = SceneStack()
        self.script = None
        self.replay = None
        self.record_path = None
        if getattr(args, "script", None):
            self.script = ScriptedInput(args.script)
        self.quit_requested = False
        self.last_world = None

    # -- scene helpers ---------------------------------------------------
    def push(self, scene):
        self.scenes.push(scene)

    def pop(self):
        return self.scenes.pop()

    def top(self):
        return self.scenes.top()

    def show_menu(self):
        self.scenes.replace(MenuScene(self))

    # -- run lifecycle ---------------------------------------------------
    def start_run(self, seed=None, floor=None):
        seed = self.args.seed if seed is None else seed
        if floor is None:
            floor = max(1, int(getattr(self.args, "floor", 1) or 1))
        scene = RunScene(self, seed=seed, floor=floor,
                         data_dir=getattr(self, "data_dir", None),
                         mod_dir=getattr(self, "mod_dir", None))
        self.scenes.replace(scene)
        self.last_world = scene.world
        return scene

    def continue_run(self):
        run = (self.profile or {}).get("run") or {}
        return self.start_run(seed=int(run.get("seed", self.args.seed)),
                              floor=int(run.get("floor", 1)))

    def end_run(self):
        world = self.last_world
        if world is None:
            self.show_menu()
            return
        meta_sys.apply_run_results(self.profile, world)
        meta_sys.clear_run(self.profile)
        save_sys.save_profile(self.profile, self.save_path)
        # r46: death goes to HQ hub instead of straight to EndScene
        if world.run_state == "dead":
            from ..ui.hq_scene import HQScene
            self.scenes.replace(HQScene(self))
        else:
            self.scenes.replace(EndScene(self, world, world.run_state == "victory"))

    def show_hq(self):
        """Show the headquarters hub scene."""
        from ..ui.hq_scene import HQScene
        self.scenes.replace(HQScene(self))

    def save_run_state(self):
        world = self.last_world
        if world is not None and world.run_state == "running":
            meta_sys.start_run(self.profile, world.seed, world.floor, world.biome_id)
        save_sys.save_profile(self.profile, self.save_path)

    # -- headless QA loop -------------------------------------------------
    def run_headless(self, turns, shot_ticks=(), shot_dir="runs/shots", canvas=None):
        import time

        canvas = canvas or pygame.Surface(self.render_size)
        scene = self.start_run()
        world = scene.world
        shots = set(int(t) for t in shot_ticks)
        rendered = 0
        start = time.perf_counter()
        steps = 0
        while steps < turns and world.run_state == "running":
            scene.update(world_mod.TICK)
            scene.draw(canvas, world_mod.TICK)
            rendered += 1
            steps += 1
            if world.tick in shots:
                self.save_shot(canvas, shot_dir, world.tick)
        elapsed = time.perf_counter() - start
        world.frames_rendered = rendered
        world.ms_per_tick = (elapsed * 1000.0) / max(1, rendered)
        self.last_world = world
        # P5.3: expose profiler summary in the world summary
        world.profiler_summary = scene.profiler.summary()
        return world

    def save_shot(self, canvas, shot_dir, tick):
        os.makedirs(shot_dir, exist_ok=True)
        path = os.path.join(shot_dir, "frame-%06d.png" % int(tick))
        pygame.image.save(canvas, path)
        return path

    # -- windowed loop ----------------------------------------------------
    def game_surface(self):
        return self.render_surface

    def apply_resolution_settings(self):
        """Recreate the display surface based on profile settings."""
        settings = self.profile.get("settings", {}) if self.profile else {}
        resolution = settings.get("resolution", "1280x720")
        fullscreen = settings.get("fullscreen", False)
        vsync = settings.get("vsync", True)

        if resolution in RESOLUTION_MODES:
            self.display_size = RESOLUTION_MODES[resolution][:2]
        elif "x" in resolution:
            w, h = resolution.split("x")
            self.display_size = (int(w), int(h))
        else:
            self.display_size = (1280, 720)

        flags = pygame.RESIZABLE
        if fullscreen:
            flags |= pygame.FULLSCREEN

        # Use vsync=1 parameter for proper vsync (Pygame 2.0+)
        vsync_arg = 1 if vsync else 0

        self.display_surface = pygame.display.set_mode(
            self.display_size, flags, vsync=vsync_arg
        )
        self.display_scale = min(
            self.display_size[0] // self.render_size[0],
            self.display_size[1] // self.render_size[1],
        )
        if self.display_scale < 1:
            self.display_scale = 1

    def run_gui(self, max_frames=None):
        self.apply_resolution_settings()
        settings = self.profile.get("settings", {}) if self.profile else {}
        fps_cap = settings.get("fps_cap", 60)
        if fps_cap == "unlimited":
            fps_cap = 0
        clock = pygame.time.Clock()
        accumulator = 0.0
        fixed = world_mod.TICK
        frames = 0
        while not self.quit_requested:
            dt = clock.tick(fps_cap) / 1000.0
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.quit_requested = True
                elif event.type == pygame.VIDEORESIZE:
                    # Handle display change during runtime
                    self.display_size = event.size
                    if self.display_surface is not None:
                        self.display_surface = pygame.display.set_mode(
                            self.display_size,
                            self.display_surface.get_flags()
                        )
                else:
                    self.scenes.handle_event(event)
            if self.quit_requested:
                break
            scene = self.top()
            if scene is None:
                self.show_menu()
                scene = self.top()
            if isinstance(scene, RunScene):
                scene.draw(self.game_surface(), dt)
                accumulator += dt
                while accumulator >= fixed:
                    scene.update(fixed)
                    accumulator -= fixed
            else:
                scene.draw(self.game_surface())
            # Scale render_surface to display_size
            if self.display_scale > 1:
                # Integer scale: scale up the render surface
                scaled = pygame.transform.scale(
                    self.render_surface, self.display_size
                )
                self.display_surface.blit(scaled, (0, 0))
            else:
                # Scale=1: blit render directly (native or letterbox)
                if self.display_size == self.render_size:
                    self.display_surface.blit(self.render_surface, (0, 0))
                else:
                    # Letterbox: fill with void, center the render
                    self.display_surface.fill(colour("void", (11, 10, 16)))
                    x = (self.display_size[0] - self.render_size[0]) // 2
                    y = (self.display_size[1] - self.render_size[1]) // 2
                    self.display_surface.blit(self.render_surface, (x, y))
            pygame.display.flip()
            frames += 1
            if max_frames is not None and frames >= max_frames:
                break
        if isinstance(self.top(), RunScene):
            self.save_run_state()
        return frames
