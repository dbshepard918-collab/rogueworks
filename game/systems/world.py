"""World: the simulation.  All gameplay advances only in ``World.step(dt)``.

Holds the level, the player, monsters, projectiles, pickups, particles and run
state; owns the single seeded RNG and the invariant checks promised by
docs/CONTRACTS.md section 3.1.
"""

from ..engine import assets
from ..engine.audio import Audio, play
from ..engine.camera import Camera
from ..engine.input import KeyboardInput
from ..engine.gamepad import GamepadInput
from ..engine.particles import DamageNumbers, FloatingText, ParticleSystem
from ..entities.pickup import Pickup
from ..entities.player import Player
from . import ai, combat, loot, procgen, spawn, statuses as status_sys, shrines as shrine_sys
from . import save as save_sys
from . import tutorial as tutorial_sys
from .spawn import make_monster
from .data import Content
from .rng import RNG
from . import unique as unique_sys
from ..engine import assets
from ..entities.pickup import Pickup
import math

TICK = 1.0 / 60.0
TILE = 32
FLOOR_PER_BIOME = 5
MAX_FLOOR = 15
CONSUMABLE_BUFF_TIME = 720          # ticks (12 s) for consumable-granted buffs
SHOP_PRICE_BASE = 34


class World:
    """A single run's simulation state."""

    def __init__(self, seed=0, content=None, profile=None, headless=True, start_floor=1,
                 audio=True, input_source=None, data_dir=None, warnings=None,
                 settings=None):
        self.seed = int(seed)
        self.headless = bool(headless)
        self.profile = profile
        self.warnings = warnings if warnings is not None else []
        self.errors = []
        self.content = Content(warnings=self.warnings, data_dir=data_dir)
        self.rng = RNG(self.seed)
        self.audio = Audio(enabled=audio and not headless, warnings=self.warnings)
        self.settings = settings or {}
        self.input_source = input_source or KeyboardInput()

        # P4.3: set initial player position for distance attenuation
        self.audio.set_player_pos(0, 0)

        self.tick = 0
        self.time = 0.0
        self._next_entity_id = 1
        self.entities = []
        self.monsters = []
        self.projectiles = []
        self.pickups = []
        self.particles = ParticleSystem()
        self.damage_numbers = DamageNumbers()
        self.floating = FloatingText()
        self.camera = Camera()
        self.level = None
        self.player = None

        self.floor = 0
        self.previous_floor = 0  # P5.1: track previous floor to avoid duplicate autosaves
        self.biome_id = ""
        self.biome_name = ""
        self.run_state = "running"          # running | dead | victory
        self.keys = 0
        self.kills_run = 0
        self.gold_run = 0
        self.essence_run = 0
        self.damage_dealt = 0.0
        self.damage_taken = 0.0
        self.floor_spawned = 0
        self.floor_killed = 0
        self.guardian_id = None
        self.boss_alive = False
        self.boss_phase = 0
        self.boss_phase_name = ''
        self.boss_hazard_timer = 0
        self.boss_add_timer = 0
        self.unknown_statuses = set()
        self.level_bonus = {}
        self.consumable_buffs = []
        self.shrine_temp_effects = []   # temp stat mods from shrines
        self.tutorial = None          # P3.4: onboarding tutorial system
        self.endless = False            # P1.8: endless mode (floor 16+)
        self.run_curses = []            # P1.8: selected curse ids
        self.endless_scale = 1.0        # P1.8: scaling for floors past MAX_FLOOR
        self.essence_mult = 1.0         # P1.8: curse-based essence multiplier
        self.elite_bonus = 0.0          # additional elite chance from curse
        self.no_minimap = False         # minimap disabled from curse
        self.gold_tax = 0.0             # fraction of gold lost to curse (P1.5)
        self.screen_flash = 0.0
        self.notice = ""
        self.notice_timer = 0.0
        self.render_list = None
        self.stairs_unlocked_flag = False
        self.frames_rendered = 0
        self.ms_per_tick = 0.0
        self.start_floor = max(1, int(start_floor))
        self.pending_floor_transition = False
        self.transition_timer = 0.0
        # P4.4: floor transition fade + scorch decals
        self.floor_transition_fade = 0.0
        self.transition_fade_active = False
        self.scorch_decals = []
        # P3.1: room-clear locks & rewards
        self.room_clear_state = {}      # room_id -> {cleared, reward_chosen, reward_type}
        self.active_reward_choice = None  # {room_id, options}
        self.room_doors = {}            # room_id -> {doors, locked}
        self.cracked_walls = {}         # (tx,ty) -> room_id for cracked walls
        self.hidden_doors = {}          # (tx,ty) -> room_id for hidden doors
        self.discovered_secrets = set()  # set of secret room ids discovered
        self._pending_room = None       # room that just cleared, awaiting reward choice
        # P3.3: event-room tracking
        self.event_room_state = {}      # room_id -> {visited, interaction_done}
        self.next_floor_modifier = None  # omen preview
        # P3.5: run storytelling
        self.rooms_visited = 0          # count of distinct rooms entered
        self.death_cause = ""           # e.g. "slain by bone_rat", "killed by projectile"
        self.seen_monsters = set()      # monster IDs seen this run
        self.seen_items = set()         # item IDs seen this run
        self.killed_monsters = {}       # {monster_id: count}
        self._last_room_id = ""         # track room changes for visit counting
        self._last_room_tile = None     # (tx, ty) of last room check
        self.meta_totals = save_sys.meta_stat_totals(profile) if profile else {}
        self.ascension_modifiers = save_sys.ascension_modifiers(
            int(profile.get("ascension", 0)) if profile else 0
        )
        self._spawn_player()
        self.tutorial = tutorial_sys.TutorialSystem()
        self._curses_applied = False  # set in RunScene.__init__ after run_curses
        self.new_floor(self.start_floor)

    # -- ids / entities --------------------------------------------------
    def next_id(self):
        eid = self._next_entity_id
        self._next_entity_id += 1
        return eid

    def add_entity(self, entity):
        self.entities.append(entity)
        kind = getattr(entity, "kind", "entity")
        if kind == "monster":
            self.monsters.append(entity)
        elif kind == "projectile":
            self.projectiles.append(entity)
        elif kind == "pickup":
            self.pickups.append(entity)
        return entity

    def _spawn_player(self):
        effects = save_sys.meta_special_effects(self.profile) if self.profile else {}
        if self.profile:
            class_id = self.profile.get("class_id", "lantern_keeper")
        else:
            class_id = "lantern_keeper"
        base = save_sys.class_stats(class_id, self.meta_totals)
        self.player = Player(self.next_id(), TILE * 2 + 16, TILE * 2 + 16,
                             base_stats=base,
                             meta_totals=self.meta_totals, meta_effects=effects)
        self.entities.append(self.player)

    def heal_amount(self, amount):
        """Apply the ascension healing multiplier (P1.4: ascension 4 = -15%)."""
        mult = float(self.ascension_modifiers.get("healing_mult", 1.0))
        return float(amount) * mult

    def _compact(self):
        alive = [e for e in self.entities if e.alive]
        if len(alive) != len(self.entities):
            self.entities = alive
        self.monsters = [m for m in self.monsters if m.alive]
        self.projectiles = [p for p in self.projectiles if p.alive]
        self.pickups = [p for p in self.pickups if p.alive and not p.collected]

    # -- floors ----------------------------------------------------------
    def biome_for_floor(self, floor):
        order = self.content.biome_order()
        if not order:
            return "catacombs"
        index = max(0, min(len(order) - 1, (max(1, floor) - 1) // FLOOR_PER_BIOME))
        return order[index]

    def new_floor(self, floor):
        self.floor = int(floor)
        self.biome_id = self.biome_for_floor(self.floor)
        biome = self.content.biome(self.biome_id) or {}
        self.biome_name = biome.get("name", self.biome_id)
        floor_rng = self.rng.fork("floor:%d" % self.floor)
        self.level = procgen.generate(self.content, floor_rng, self.floor, self.biome_id,
                                      world_profile=self.profile)

        # Cracked walls and secret rooms from procgen
        if hasattr(self.level, '_cracked_walls'):
            self.cracked_walls = dict(self.level._cracked_walls)
        if hasattr(self.level, '_hidden_doors'):
            self.hidden_doors = dict(self.level._hidden_doors)
        else:
            self.hidden_doors = {}
        if hasattr(self.level, '_secret_rooms'):
            self._level_secret_rooms = list(self.level._secret_rooms)
        else:
            self._level_secret_rooms = []
        # Also grab hidden_doors from Level object if available
        if hasattr(self.level, 'hidden_doors'):
            self.hidden_doors = dict(self.level.hidden_doors)

        # biome modifier (P1.2) — set per biome so rules change, not just art
        from . import biome_mods as _bm
        _bm.set_modifier(self, biome.get("modifier"))
        _bm.clear_moved_flag(self)
        # P4.3: switch biome ambience loop
        self.audio.set_biome(self.biome_id)
        # P1.3: refresh player meta-derived runtime tuning (dash, etc.) after each floor
        if self.player is not None:
            self.player._meta_effects = save_sys.meta_special_effects(self.profile) if self.profile else {}

        self.monsters = []
        self.projectiles = []
        self.pickups = []
        self.particles.clear()
        self.damage_numbers.clear()
        self.scorch_decals = []    # P4.4: clear scorch decals on new floor
        self.entities = [self.player]
        self.guardian_id = None
        self.boss_alive = False
        self.boss_phase = 0
        self.boss_phase_name = ''
        self.boss_hazard_timer = 0
        self.boss_add_timer = 0
        self.keys = 0
        self.floor_spawned = 0
        self.floor_killed = 0
        self.stairs_unlocked_flag = False
        self.elite_bonus = 0.0
        self.no_minimap = False
        self.gold_tax = 0.0
        self.shrine_active_effects = []
        # P3.3: event-room tracking
        self.event_room_state = {}
        self.next_floor_modifier = None
        # P3.5: reset room tracking for new floor
        self._last_room_id = ""
        # P3.5: count the first room entered on a new floor
        self.rooms_visited += 1

        player = self.player
        player.x = self.level.spawn_tile[0] * TILE + 16
        player.y = self.level.spawn_tile[1] * TILE + 16
        # P4.3: update audio listener position for distance attenuation
        if self.audio.ok:
            self.audio.set_player_pos(player.x, player.y)
        player.knock_x = 0.0
        player.knock_y = 0.0
        if floor > self.start_floor:
            # a lantern-keeper catches their breath on the stair (floor mercy)
            player.heal(self.heal_amount(player.stats.max_hp() * 0.25))
        # P1.3: vitality tree tiers grant extra floor-transition heal
        se = save_sys.meta_special_effects(self.profile)
        heal_pct = float(se.get("heal_on_floor_pct", 0.0))
        if heal_pct > 0 and player.alive:
            player.heal(self.heal_amount(player.stats.max_hp() * 0.25 / 100.0 * heal_pct))
            player.clamp_hp()
            player.floor_transitions += 1

        spawn.populate_floor(self, self.floor, self.biome_id)
        self._compute_room_doors()
        # P3.1: reset room clear state for new floor
        self._reset_room_clear_state()
        # P3.3: reset event-room tracking for new floor
        self.event_room_state = {}
        self.next_floor_modifier = None
        # P1.8: curse-based essence multiplier (1 + 0.15 per active curse)
        if self.run_curses:
            self.essence_mult = 1.0 + 0.15 * len(self.run_curses)
        # P1.8: endless mode — escalate monster HP and damage past MAX_FLOOR
        if self.endless and self.floor > MAX_FLOOR:
            self.endless_scale = 1.0 + 0.2 * (self.floor - MAX_FLOOR)
            dmg_pct = 0.1 * (self.floor - MAX_FLOOR)
            for mon in self.monsters:
                mon.stats.set_pct("endless", {"max_hp": self.endless_scale - 1.0,
                                              "damage": dmg_pct})
                mon.hp = mon.stats.max_hp()
        if self.endless and self.floor > MAX_FLOOR:
            spawn._scale_for_endless(self, self.floor)
        self.level.reveal_around(player.x, player.y)
        # Reveal secret rooms near the player
        self._check_secret_reveal(player)
        self.floating.add("Floor %d - %s" % (self.floor, self.biome_name),
                          color=(232, 178, 60), life=2.6)
        self.notice = "Floor %d - %s" % (self.floor, self.biome_name)
        self.notice_timer = 2.5
        # P4.4: floor transition fade
        self.floor_transition_fade = 0.5
        self.transition_fade_active = True

        # P1.4: unlock classes based on floor reached
        if self.profile is not None:
            unlocked = set(self.profile.get("unlocked_classes", ["lantern_keeper"]))
            if self.floor >= 6:
                unlocked.add("ash_dancer")
            if self.floor >= 10:
                unlocked.add("grave_warden")
            self.profile["unlocked_classes"] = sorted(unlocked)

        # P1.8: apply run_curses to player on first floor start — handled in RunScene.__init__ now
        self._curses_applied = True  # already applied in RunScene.__init__
        # P5.1: autosave on floor entry
        if self.profile is not None and self.floor != self.previous_floor:
            try:
                save_sys.save_slot_autosave(self.profile)
            except Exception:
                pass  # autosave failure must not break gameplay
            self.previous_floor = self.floor

    def stairs_unlocked(self):
        """Biome-dependent exit condition (GDD section 2)."""
        if self.keys > 0:
            return True
        guardian_alive = any(m.alive and (m.guardian or m.boss) for m in self.monsters)
        if not guardian_alive:
            return True
        if self.biome_id == "ember_warrens" and self.floor_spawned:
            return self.floor_killed >= 0.7 * self.floor_spawned
        return False

    def objective_tile(self):
        """The floor's goal tile - the stairs down that ends the floor.

        Consumed by AutoPilotInput (QA autopilot) as the navigation objective
        when there is no threat worth engaging.
        """
        level = getattr(self, "level", None)
        if level is None:
            return (0, 0)
        return getattr(level, "stairs_tile", (0, 0))

    def path_to(self, sx, sy, gx, gy, cap=12000):
        """Pathfind from tile (sx, sy) to (gx, gy) on the current level.

        Returns a list of (tx, ty) tiles from start to goal, or None when no
        path exists. Consumed by AutoPilotInput (QA autopilot) and by monster
        re-pathing in ai.py (_step_toward).
        """
        level = getattr(self, "level", None)
        if level is None:
            return None
        return level.bfs_path((sx, sy), (gx, gy), cap=cap)

    def _reset_room_clear_state(self):
        """Reset room-clear tracking for a new floor."""
        self.room_clear_state = {}
        self.active_reward_choice = None
        self._pending_room = None
        for room in self.level.rooms:
            rid = room.get("id", "")
            kind = room.get("kind", "")
            if kind in ("combat", "treasure", "shrine", "shop", "gambling", "blacksmith", "fountain", "omen"):
                self.room_clear_state[rid] = {"cleared": False, "reward_chosen": False, "reward_type": None}
        self._compute_room_doors()

    def _compute_room_doors(self):
        """Scan the tile grid and build a map of door positions per room."""
        self.room_doors = {}
        self.hidden_doors = {}
        if not self.level:
            return
        tiles = self.level.tiles
        level_w = self.level.w
        level_h = self.level.h
        for room in self.level.rooms:
            rid = room.get("id", "")
            kind = room.get("kind", "")
            if kind not in ("combat", "treasure", "shrine", "shop", "gambling", "blacksmith", "fountain", "omen", "secret"):
                continue
            doors = []
            rx = int(room.get("x", 0))
            ry = int(room.get("y", 0))
            rw = int(room.get("w", 8))
            rh = int(room.get("h", 8))
            for tx in range(rx, min(level_w, rx + rw)):
                for ty in range(ry, min(level_h, ry + rh)):
                    if tiles[tx][ty] == procgen.DOOR:
                        doors.append((tx, ty))
            if doors:
                self.room_doors[rid] = {"doors": doors, "locked": True}

    def check_room_clears(self):
        """Check if any combat rooms have been cleared of all monsters."""
        for room in self.level.rooms:
            rid = room.get("id", "")
            kind = room.get("kind", "")
            if kind not in ("combat", "treasure", "shrine", "shop", "gambling", "blacksmith", "fountain", "omen"):
                continue
            # Event rooms (gambling, blacksmith, fountain, omen) don't need monsters cleared
            if kind in ("gambling", "blacksmith", "fountain", "omen"):
                state = self.room_clear_state.get(rid)
                if state and not state["cleared"]:
                    state["cleared"] = True
                    self._pending_room = rid
                    self.notice = "%s room - interact to use" % kind.capitalize()
                    self.notice_timer = 3.0
                    self._open_door_tiles(rid)
                    return rid
                continue
            state = self.room_clear_state.get(rid)
            if state is None or state["cleared"] or state["reward_chosen"]:
                continue
            # Count alive monsters in this room
            alive_count = 0
            for mon in self.monsters:
                if not mon.alive:
                    continue
                mtx = int(mon.x // TILE)
                mty = int(mon.y // TILE)
                rx = int(room.get("x", 0))
                ry = int(room.get("y", 0))
                rw = int(room.get("w", 8))
                rh = int(room.get("h", 8))
                if rx <= mtx < rx + rw and ry <= mty < ry + rh:
                    alive_count += 1
            if alive_count == 0:
                state["cleared"] = True
                self._pending_room = rid
                self.notice = "Room cleared - choose a reward"
                self.notice_timer = 3.0
                # Set active reward choice for windowed mode
                if not self.headless:
                    self.active_reward_choice = {
                        "room_id": rid,
                        "options": ["item", "gold", "heal", "shrine"]
                    }
                # Open door tiles visually
                self._open_door_tiles(rid)
                return rid
        return None

    def _open_door_tiles(self, room_id):
        """Temporarily show doors as open (but still locked until reward chosen)."""
        if room_id in self.room_doors:
            # Doors are still locked - we just update the tile value for rendering
            pass  # The renderer will check room_clear_state for locked status

    def choose_room_reward(self, reward_type):
        """Apply the reward choice for the pending cleared room and unlock doors."""
        if self._pending_room is None or self.active_reward_choice is None:
            return False
        room_id = self._pending_room
        state = self.room_clear_state.get(room_id)
        if state is None or not state["cleared"] or state["reward_chosen"]:
            return False
        if reward_type not in ("item", "gold", "heal", "shrine"):
            return False
        state["reward_chosen"] = True
        state["reward_type"] = reward_type
        self.active_reward_choice = None
        # Apply reward
        player = self.player
        if reward_type == "item":
            from . import loot
            tier = loot.tier_for_floor(self.floor, player.stats.luck())
            item = loot.make_item(self.content, self.rng, tier=tier, luck=player.stats.luck())
            if item is not None:
                self.add_entity(Pickup(self.next_id(), player.x, player.y, "item", item=item,
                                       sprite=item.get("sprite")))
                self.floating.add("Reward: %s" % item.get("display", item.get("name")),
                                  color=tuple(item.get("rarity_color") or (246, 242, 232)), life=2.0)
        elif reward_type == "gold":
            amount = 20 + self.floor * 5
            player.gold += amount
            self.gold_run += amount
            self.floating.add("Reward: %d gold" % amount, color=(232, 178, 60), life=2.0)
        elif reward_type == "heal":
            healed = player.heal(self.heal_amount(player.stats.max_hp() * 0.5))
            if healed > 0:
                self.damage_numbers.add(player.x, player.y - 22, int(healed),
                                        color=(121, 176, 74), label="+%d" % int(healed))
            self.floating.add("Reward: +%d HP" % int(healed), color=(121, 176, 74), life=2.0)
        elif reward_type == "shrine":
            from . import shrines as shrine_sys
            boon, curse = shrine_sys.activate_shrine(self)
            if boon:
                self.floating.add("Reward: %s" % boon.get("name", "boon"), color=(121, 176, 74), life=2.0)
        # Unlock doors
        self._unlock_doors(room_id)
        return True

    def _unlock_doors(self, room_id):
        """Unlock doors for a cleared room by changing tile values."""
        if room_id not in self.room_doors:
            return
        self.room_doors[room_id]["locked"] = False
        tiles = self.level.tiles
        for tx, ty in self.room_doors[room_id]["doors"]:
            if 0 <= tx < self.level.w and 0 <= ty < self.level.h:
                tiles[tx][ty] = procgen.DOOR_OPEN
        # Unlock hidden doors for secret rooms
        if room_id in self.hidden_doors:
            for tx, ty in self.hidden_doors[room_id]:
                if 0 <= tx < self.level.w and 0 <= ty < self.level.h:
                    tiles[tx][ty] = procgen.DOOR_OPEN
        # P4.3: play door open sound event
        play(self, "door")

    def _interact_event_room(self, room_id, kind):
        """Handle player interaction with an event room."""
        player = self.player
        if kind == "gambling":
            self._gamble(room_id)
        elif kind == "blacksmith":
            self._blacksmith(room_id)
        elif kind == "fountain":
            self._fountain(room_id)
        elif kind == "omen":
            self._omen(room_id)
        # Mark as interacted
        state = self.event_room_state.get(room_id)
        if state:
            state["interaction_done"] = True

    def _gamble(self, room_id):
        """Gambling: player bets gold, wins random loot or loses bet."""
        player = self.player
        bet = min(50 + self.floor * 5, player.gold)
        if bet < 10:
            if self.notice_timer <= 0.0:
                self.notice = "Need at least 10 gold to gamble"
                self.notice_timer = 2.0
            return
        player.gold -= bet
        # 40% chance to win (2x-3x bet), 60% chance to lose
        if self.rng.chance(0.4):
            multiplier = 2 + self.rng.randint(0, 1)
            winnings = bet * multiplier
            player.gold += winnings
            self.gold_run += winnings
            self.floating.add("Gamble wins! +%d gold" % (winnings - bet),
                              color=(121, 176, 74), life=2.0)
            play(self, "coin")
        else:
            self.floating.add("Gamble loses! -%d gold" % bet,
                              color=(196, 99, 95), life=2.0)
            play(self, "coin")
        if self.notice_timer <= 0.0:
            self.notice = "Gambling complete"
            self.notice_timer = 2.0

    def _blacksmith(self, room_id):
        """Blacksmith: upgrade one equipped item by +1 tier (max tier 5)."""
        player = self.player
        upgraded = False
        for item in player.equipment.values():
            if item is None:
                continue
            tier = int(item.get("tier", 1))
            if tier < 5:
                item["tier"] = tier + 1
                upgraded = True
                self.floating.add("Upgraded %s to tier %d" % (
                    item.get("display", item.get("name", "item")), tier + 1),
                    color=(232, 178, 60), life=2.2)
                play(self, "levelup")
                break
        if not upgraded:
            if self.notice_timer <= 0.0:
                self.notice = "Nothing to upgrade (max tier 5)"
                self.notice_timer = 2.0
            return
        state = self.event_room_state.get(room_id)
        if state:
            state["interaction_done"] = True

    def _fountain(self, room_id):
        """Fountain: trade 5 HP for 2 essence."""
        player = self.player
        if player.hp < 6:
            if self.notice_timer <= 0.0:
                self.notice = "Need at least 5 HP to use the fountain"
                self.notice_timer = 2.0
            return
        player.hp = max(0, player.hp - 5)
        player.essence += 2
        self.essence_run += 2
        self.floating.add("Fountain: -5 HP, +2 essence",
                          color=(121, 176, 74), life=2.0)
        play(self, "pickup")

    def _omen(self, room_id):
        """Omen: preview next floor's biome modifier."""
        next_floor = self.floor + 1
        biome_id = self.biome_for_floor(next_floor)
        biome = self.content.biome(biome_id) or {}
        modifier = biome.get("modifier")
        self.next_floor_modifier = modifier
        label = biome.get("name", biome_id)
        mod_text = " %s" % modifier if modifier else ""
        if self.notice_timer <= 0.0:
            self.notice = "Omen: Floor %d will be %s%s" % (next_floor, label, mod_text)
            self.notice_timer = 3.0
        play(self, "levelup")

    def _check_exit(self):
        player = self.player
        stairs = self.level.stairs_tile
        if (player.tile_x, player.tile_y) != stairs:
            return
        if self.stairs_unlocked():
            if self.floor >= MAX_FLOOR and not self.endless:
                self.on_victory()
                self.audio.play_stairs(pos=(player.x, player.y))
                return
            self.audio.play_stairs(pos=(player.x, player.y))
            self.floating.add("Descending...", color=(246, 242, 232), life=1.2)
            self.new_floor(self.floor + 1)
        else:
            if self.notice_timer <= 0.0:
                self.notice = "The stair is sealed - break the guardian or find a key"
                self.notice_timer = 2.0

    def frame(self, name, size=TILE):
        return assets.find_frame(name, warnings=self.warnings, size=size)

    def tileset(self):
        return self.content.tileset_for(self.biome_id)

    def tile_frames(self):
        ts = self.tileset()
        keys = ("floor", "floor_alt", "floor_alt2", "floor_rubble", "floor_cracked",
                "floor_blood", "floor_bones", "floor_coins", "wall", "wall_alt", "wall_torch",
                "wall_corner", "wall_decor", "wall_cracked", "wall_skull", "doorway",
                "door", "door_open", "stairs_down", "stairs_up", "pillar", "pool",
                "pool_alt", "grate", "brazier", "slab", "gate", "rune_floor",
                "shrine_floor", "treasure_floor", "pit", "barricade",
                "floor_burning", "floor_water")
        return {key: "%s_%s" % (ts, key) for key in keys}

    # -- events ----------------------------------------------------------
    def grant_xp(self, amount):
        player = self.player
        player.xp += int(amount)
        while player.xp >= player.xp_needed():
            player.xp -= player.xp_needed()
            player.level += 1
            self._level_up()

    def _level_up(self):
        player = self.player
        stats = ("max_hp", "damage", "armor", "speed", "crit", "luck")
        weights = (30.0, 30.0, 16.0, 12.0, 8.0, 10.0)
        picked = stats[self.rng.weighted_index(list(weights))]
        gain = {"max_hp": 8.0, "damage": 1.0, "armor": 0.02, "speed": 0.18,
                "crit": 0.02, "luck": 1.0}[picked]
        self.level_bonus[picked] = self.level_bonus.get(picked, 0.0) + gain
        player.stats.set_mod("level", dict(self.level_bonus))
        healed = 0.0
        if player.level % 3 == 0:
            healed = player.heal(self.heal_amount(player.stats.max_hp()))
        else:
            healed = player.heal(self.heal_amount(player.stats.max_hp() * 0.25))
        label = {"max_hp": "+HP", "damage": "+DMG", "armor": "+ARM", "speed": "+SPD",
                 "crit": "+CRIT", "luck": "+LUCK"}[picked]
        self.floating.add("LEVEL %d  %s" % (player.level, label), color=(232, 178, 60), life=2.2)
        self.damage_numbers.add(player.x, player.y - 30, 0, label="LEVEL UP",
                                color=(232, 178, 60), scale=2)
        self.particles.burst(player.x, player.y, self.rng, count=26, color=(232, 178, 60),
                             speed=130.0, life=0.7, size=3)
        self.particles.sprite_burst(player.x, player.y, "vfx_levelup", life=0.6, scale=1.5)
        play(self, "levelup")
        self.notice = "Level %d! %s" % (player.level, label)
        self.notice_timer = 2.0

    def on_monster_death(self, mon, source=None):
        self.kills_run += 1
        self.floor_killed += 1
        self.player.kills += 1
        # P3.5: track killed monsters
        mon_id = getattr(mon, 'monster_id', getattr(mon, 'name', 'unknown'))
        self.killed_monsters[mon_id] = self.killed_monsters.get(mon_id, 0) + 1
        self.seen_monsters.add(mon_id)
        self.grant_xp(mon.xp)
        self.particles.burst(mon.x, mon.y, self.rng, count=16 if not mon.boss else 40,
                             color=(140, 31, 52), speed=120.0, life=0.55, size=4)
        if mon.boss:
            self.camera.add_shake(12.0)
            self.boss_alive = False
            self.boss_phase = 0
            self.boss_phase_name = ''
            self.floating.add("GUARDIAN SLAIN", color=(232, 178, 60), life=3.0)
            # P1.4: unlock the next ascension tier (beating the boss at the
            # current ascension level unlocks ascension level + 1)
            if self.profile is not None:
                current = int(self.profile.get("unlocked_ascension", 0) or 0)
                if current < 5:
                    self.profile["unlocked_ascension"] = current + 1
        play(self, "death")
        spawn.drop_loot_for(self, mon)
        if mon.elite and self.rng.chance(0.25):
            item = loot.make_item(self.content, self.rng,
                                  tier=loot.tier_for_floor(self.floor, self.player.stats.luck()),
                                  luck=self.player.stats.luck(),
                                  unlocks=(self.profile or {}).get("unlocks") if self.profile else None)
            if item is not None:
                self.add_entity(Pickup(self.next_id(), mon.x, mon.y, "item", item=item,
                                       sprite=item.get("sprite")))
        if not mon.guardian and not mon.boss and self.keys == 0 and self.rng.chance(0.04):
            self.add_entity(Pickup(self.next_id(), mon.x, mon.y, "key", amount=1,
                                   sprite="prop_key"))
        # biome: catacombs undead may respawn once
        from . import biome_mods as _bm
        _bm.on_monster_death_add_respawn(self, mon)
        # P1.6: trinket death_spark — splash damage on kill
        unique_sys.apply_unique(self, self.player.equipment.get("trinket"),
                                "monster_killed", killed_mon=mon)

    def on_player_death(self, death_cause=""):
        if self.run_state != "running":
            return
        self.run_state = "dead"
        self.death_cause = death_cause
        self.particles.burst(self.player.x, self.player.y, self.rng, count=40,
                             color=(79, 209, 200), speed=150.0, life=0.9, size=4)
        self.camera.add_shake(10.0)
        play(self, "death")
        self.audio.play_death()
        # P3.5: ensure rooms_visited is counted on death
        self._track_room_visit()
        self.floating.add(self.content.flavor_for("death", self.rng) or "You fall.",
                          color=(79, 209, 200), life=4.0)

    def on_victory(self):
        if self.run_state != "running":
            return
        self.run_state = "victory"
        self.audio.play_victory()
        self.floating.add("VAELMOOR IS EMPTY. THE LANTERN STILL BURNS.",
                          color=(232, 178, 60), life=5.0)

    # -- main loop -------------------------------------------------------
    def step(self, dt=None, input_state=None):
        """Advance the simulation one fixed tick."""
        if self.run_state != "running":
            return
        dt = TICK if dt is None else float(dt)
        self.tick += 1
        self.time += dt
        self.screen_flash = max(0.0, self.screen_flash - dt * 2.4)
        self.notice_timer = max(0.0, self.notice_timer - dt)
        # P4.4: floor transition fade timer
        if self.transition_fade_active:
            self.floor_transition_fade = max(0.0, self.floor_transition_fade - dt)
            if self.floor_transition_fade <= 0.0:
                self.transition_fade_active = False

        inp = input_state if input_state is not None else self.input_source.sample(self)
        player = self.player
        hold_to_attack = self.settings.get("hold_to_attack", False)
        player.tick(dt, hold_to_attack=hold_to_attack)

        # statuses (player first so DOTs can kill before actions resolve)
        for mon in list(self.monsters):
            status_sys.tick_statuses(self, mon, dt)
        status_sys.tick_statuses(self, player, dt)
        from . import biome_mods as _bm
        _bm.clear_moved_flag(self)
        _bm.step(self, dt)
        self._tick_consumable_buffs(dt)
        shrine_sys.tick_shrine_effects(self, dt)
        if self.run_state != "running":
            self._compact()
            return

        # player intent
        # P3.4: track tutorial attempts
        _tut = self.tutorial
        if _tut and self.floor == self.start_floor:
            if inp.has("move") or (inp.move[0] != 0 or inp.move[1] != 0):
                _tut.record_attempt("move")
            if inp.has("attack"):
                _tut.record_attempt("attack")
            if inp.has("dash"):
                _tut.record_attempt("dash")
            if inp.has("interact"):
                _tut.record_attempt("interact")

        if inp.has("dash") and player.dash_ready() and (inp.move[0] or inp.move[1]):
            player.start_dash(inp.move, world=self)
            if _tut and self.floor == self.start_floor:
                _tut.record_success("dash")
        moved = player.move(inp.move, dt, self.level)
        player.set_moving(moved)
        # biome: drowned "slip" tracks whether the player moved this tick
        if moved:
            _bm.mark_moved(self)
        if _tut and self.floor == self.start_floor and moved:
            _tut.record_success("move")
        if player.dash_timer > 0.0 and self.tick % 3 == 0:
            self.particles.trail(player.x, player.y, self.rng, count=1,
                                 color=(138, 132, 150), life=0.25, size=2)
        if moved and self.tick % 14 == 0:
            self.particles.trail(player.x, player.y + 8, self.rng, count=1,
                                 color=(87, 80, 112), life=0.3, size=2)
            # P4.4: footstep dust puffs
            self.particles.sprite_burst(player.x, player.y + 8, "vfx_dust", life=0.28, scale=1.5)
        if player.attack_ready() and (not hold_to_attack or inp.has("attack")):
            combat.player_melee(self, player)
            if _tut and self.floor == self.start_floor:
                _tut.record_success("attack")
        else:
            if inp.has("attack") and _tut and self.floor == self.start_floor:
                if not player.attack_ready():
                    _tut.record_failure("attack")
        if inp.has("ranged") and player.ranged_ready():
            combat.player_ranged(self, player)
            if _tut and self.floor == self.start_floor:
                _tut.record_success("attack")
        player.apply_knockback(self.level, dt)
        # P3.3: event-room interaction (E key)
        if inp.has("interact"):
            self.player_interact_event()
            if _tut and self.floor == self.start_floor:
                _tut.record_success("interact")

        # P3.4: update tutorial (prompt display)
        if _tut and self.floor == self.start_floor:
            _tut.update(dt)
            if not _tut.completed:
                # Check for failures on actions that haven't succeeded yet
                for _action in ("move", "attack", "dash", "interact"):
                    if _tut.should_show_prompt(_action):
                        _tut.get_active_prompt()  # set shown flag + timer
                        break
                if _tut.check_complete():
                    _tut.completed = True

        # monsters
        for mon in list(self.monsters):
            if not mon.alive:
                continue
            ai.update_monster(self, mon, dt)
            mon.tick(dt)
            mon.apply_knockback(self.level, dt)
        self._separate_monsters()

        # Update boss phase system
        self.update_boss_phases(dt)

        combat.update_projectiles(self, dt)
        self._update_pickups(dt)

        self.particles.update(dt)
        self.damage_numbers.update(dt)
        self.floating.update(dt)

        # P2.1: tick hit-stop on all actors — freeze movement during hit-stop
        for entity in self.entities:
            if hasattr(entity, "tick_hit_stop"):
                entity.tick_hit_stop(dt)

        self.camera.follow(player.x, player.y, self.level.w, self.level.h, dt)
        self.camera.update_shake(dt, self.rng)
        self.level.reveal_around(player.x, player.y)
        self._track_room_visit()
        self.stairs_unlocked_flag = self.stairs_unlocked()
        # P3.1: check for room clears after monster updates
        cleared_room = self.check_room_clears()
        if cleared_room and self.active_reward_choice is None:
            # Auto-choose for headless mode
            if self.headless:
                self.choose_room_reward("heal")

        self._check_exit()
        self._compact()

    def _tick_consumable_buffs(self, dt):
        if not self.consumable_buffs:
            return
        survivors = []
        for buff in self.consumable_buffs:
            buff["remaining"] -= dt * 60.0
            if buff["remaining"] > 0:
                survivors.append(buff)
        self.consumable_buffs = survivors
        merged = {}
        for buff in survivors:
            for key, value in buff["effects"].items():
                merged[key] = merged.get(key, 0.0) + value
        if merged:
            self.player.stats.set_mod("buff:consumable", merged)
        else:
            self.player.stats.remove_mod("buff:consumable")

    def _separate_monsters(self):
        """Light deterministic separation so monsters do not stack up."""
        mons = self.monsters
        n = len(mons)
        if n < 2 or n > 60:
            return
        for i in range(n):
            a = mons[i]
            if not a.alive or a.boss:
                continue
            for j in range(i + 1, n):
                b = mons[j]
                if not b.alive or b.boss:
                    continue
                dx = b.x - a.x
                dy = b.y - a.y
                min_dist = a.radius + b.radius
                d2 = dx * dx + dy * dy
                if d2 >= min_dist * min_dist or d2 < 0.0001:
                    continue
                d = d2 ** 0.5
                push = (min_dist - d) * 0.5
                nx = dx / d * push
                ny = dy / d * push
                ab = a.radius + 0.0
                if not self.level.blocked_px(a.x - nx, a.y - ny, a.radius):
                    a.x -= nx
                    a.y -= ny
                if not self.level.blocked_px(b.x + nx, b.y + ny, b.radius):
                    b.x += nx
                    b.y += ny

    # -- boss phases -----------------------------------------------------
    def update_boss_phases(self, dt):
        """Check boss HP for phase transitions and update timers."""
        boss_mon = self._get_boss_monster()
        if boss_mon is None or not boss_mon.alive:
            return
        # Check enrage trigger
        enrage = boss_mon.defn.get("enrage")
        if enrage and not boss_mon.enraged:
            trigger_hp = enrage.get("trigger_hp", 0.0)
            if boss_mon.hp / boss_mon.stats.max_hp() <= trigger_hp:
                boss_mon.apply_enrage()
        # Check phase transition
        if boss_mon.check_phase_transition():
            self.boss_phase = boss_mon.current_phase_index
            self.boss_phase_name = boss_mon.phase.get("name", "")
            self.boss_hazard_timer = 0
            self.boss_add_timer = 0
            # Spawn hazards for new phase
            self.spawn_boss_hazards(boss_mon)
        # Update enrage timer
        if boss_mon.enraged:
            boss_mon.enrage_timer = max(0.0, boss_mon.enrage_timer - dt * 60)
            if boss_mon.enrage_timer <= 0:
                boss_mon.enraged = False
        # Update phase transition timer
        if boss_mon.phase_transition_timer > 0:
            boss_mon.phase_transition_timer = max(0.0, boss_mon.phase_transition_timer - dt)
        # Spawn adds on timer
        phase = boss_mon.phase
        adds = phase.get("adds", [])
        if adds and boss_mon.phase_transition_timer <= 0:
            self.boss_add_timer = max(0.0, self.boss_add_timer - dt)
            if self.boss_add_timer <= 0:
                self.spawn_boss_adds(boss_mon)
                self.boss_add_timer = 3.0  # respawn adds every 3 seconds
        # Update hazard timers
        if self.boss_hazard_timer > 0:
            self.boss_hazard_timer = max(0.0, self.boss_hazard_timer - dt)

    def _get_boss_monster(self):
        """Return the boss monster by guardian_id, or None."""
        if not self.boss_alive or self.guardian_id is None:
            return None
        for mon in self.monsters:
            if mon.id == self.guardian_id and mon.alive and mon.boss:
                return mon
        return None

    def spawn_boss_adds(self, boss_mon):
        """Spawn add monsters listed in the boss's current phase."""
        adds = boss_mon.phase.get("adds", [])
        if not adds or not boss_mon.alive:
            return
        for add_id in adds:
            add_defn = self.content.monster(add_id)
            if add_defn is None:
                continue
            # Spawn near the boss (the world owns the RNG, not the monster)
            angle = self.rng.random() * 6.28318530718
            dist = 40 + self.rng.random() * 40
            ax = boss_mon.x + math.cos(angle) * dist
            ay = boss_mon.y + math.sin(angle) * dist
            mon = make_monster(self, add_defn, ax, ay,
                               difficulty=self.endless_scale if getattr(self, "endless", False) else 1.0)
            if mon:
                mon.guardian = True  # adds are considered guardians for targeting

    def spawn_boss_hazards(self, boss_mon):
        """Spawn hazard VFX effects for the boss's current phase."""
        hazards = boss_mon.phase.get("hazards", [])
        if not hazards or not boss_mon.alive:
            return
        for hazard_type in hazards:
            hazard_defn = boss_mon.defn.get("hazards", {}).get(hazard_type)
            if hazard_defn is None:
                continue
            vfx = hazard_defn.get("visual", "vfx_boss_phase_glow")
            if assets.has_frame(vfx):
                self.particles.sprite_burst(boss_mon.x, boss_mon.y, vfx, life=1.5, scale=1.5)
            self.boss_hazard_timer = hazard_defn.get("telegraph", 1.0)

    def _check_exit(self):
        player = self.player
        stairs = self.level.stairs_tile
        if (player.tile_x, player.tile_y) != stairs:
            return
        if self.stairs_unlocked():
            if self.floor >= MAX_FLOOR and not self.endless:
                self.on_victory()
                self.audio.play_stairs(pos=(player.x, player.y))
                return
            self.audio.play_stairs(pos=(player.x, player.y))
            self.floating.add("Descending...", color=(246, 242, 232), life=1.2)
            self.new_floor(self.floor + 1)
        else:
            if self.notice_timer <= 0.0:
                self.notice = "The stair is sealed - break the guardian or find a key"
                self.notice_timer = 2.0

    # -- pickups ---------------------------------------------------------
    def _update_pickups(self, dt):
        player = self.player
        for pk in self.pickups:
            if not pk.alive or pk.collected:
                continue
            pk.tick(dt)
            dx = player.x - pk.x
            dy = player.y - pk.y
            dist = (dx * dx + dy * dy) ** 0.5
            if pk.magnet and dist < player.MAGNET_RADIUS and dist > 1.0:
                pull = 240.0
                pk.x += dx / dist * pull * dt
                pk.y += dy / dist * pull * dt
                dist = max(0.0, dist - pull * dt)
            if dist <= player.PICKUP_RADIUS + pk.radius:
                self._collect(pk)

    def _collect(self, pk):
        player = self.player
        kind = pk.pickup_kind
        if kind == "gold":
            gross = int(pk.amount)
            tax = int(gross * getattr(self, "gold_tax", 0.0))
            net = max(0, gross - tax)
            player.gold += net
            self.gold_run += net
            pk.collected = True
            play(self, "coin")
            # P4.4: coin sparkle on pickup
            self.particles.sprite_burst(pk.x, pk.y, "vfx_sparkle", life=0.3, scale=1.5)
        elif kind == "essence":
            mult = float(getattr(self, "essence_mult", 1.0))
            try:
                from . import save as save_sys
                se = save_sys.meta_special_effects(self.profile)
                mult *= float(se.get("essence_drop_mult", 1.0))
            except Exception:
                pass
            amount = int(pk.amount * mult)
            player.essence += amount
            self.essence_run += amount
            pk.collected = True
            play(self, "pickup")
        elif kind == "health":
            healed = player.heal(self.heal_amount(pk.amount))
            if healed > 0:
                self.damage_numbers.add(player.x, player.y - 22, healed, color=(121, 176, 74),
                                        label="+%d" % int(healed))
            pk.collected = True
            play(self, "pickup")
        elif kind == "key":
            self.keys += int(pk.amount or 1)
            pk.collected = True
            self.notice = "Vault key taken - the stair is open"
            self.notice_timer = 3.0
            self.floating.add("VAULT KEY", color=(232, 178, 60), life=2.4)
            play(self, "pickup")
        elif kind == "chest":
            cost = 10 + 5 * self.floor
            if player.gold < cost:
                if self.notice_timer <= 0.0:
                    self.notice = "Chest: %d gold needed" % cost
                    self.notice_timer = 1.5
                return
            player.gold -= cost
            pk.collected = True
            spawn.chest_loot(self, pk.x, pk.y)
            self.particles.burst(pk.x, pk.y, self.rng, count=18, color=(232, 178, 60),
                                 speed=110.0, life=0.6, size=3)
            self.floating.add("Chest opened", color=(232, 178, 60), life=1.8)
            play(self, "pickup")
        elif kind == "shrine":
            pk.collected = True
            self._use_shrine(pk)
        elif kind == "shop":
            player = self.player
            price = SHOP_PRICE_BASE + 12 * self.floor
            try:
                from . import save as save_sys
                se = save_sys.meta_special_effects(self.profile)
                price = int(round(price * float(se.get("shop_price_mult", 1.0))))
            except Exception:
                pass
            if player.gold < price:
                if self.notice_timer <= 0.0:
                    self.notice = "Shop: %d gold needed" % price
                    self.notice_timer = 1.5
                return False
            tier = min(5, loot.tier_for_floor(self.floor, player.stats.luck()) + 1)
            unlocks = (self.profile or {}).get("unlocks") if self.profile else None
            item = loot.make_item(self.content, self.rng, tier=tier, luck=player.stats.luck() + 6, unlocks=unlocks)
            if item is None:
                return False
            player.gold -= price
            self.add_entity(Pickup(self.next_id(), pk.x + 24, pk.y, "item", item=item,
                                   sprite=item.get("sprite")))
            self.floating.add("Bought %s for %d gold" % (item.get("display") or item.get("name"), price),
                              color=(232, 178, 60), life=2.2)
            play(self, "coin")
            # P1.7: shop sells keys (25%) and health_vial consumables (20%)
            if self.rng.chance(0.25):
                key_pickup = Pickup(self.next_id(), pk.x + 8, pk.y + 24, "key", amount=1,
                                    sprite="prop_key")
                self.add_entity(key_pickup)
                self.floating.add("Key - stall stock", color=(232, 178, 60), life=1.6)
            if self.rng.chance(0.20):
                vial = self.content.item_by_id("health_vial")
                if vial:
                    vp = Pickup(self.next_id(), pk.x - 8, pk.y + 24, "item",
                                item=dict(vial), sprite=vial.get("sprite"))
                    self.add_entity(vp)
                    self.floating.add("Health Vial - stall stock", color=(121, 176, 74), life=1.6)
            return False        # the stall stays open all floor
        elif kind == "item":
            self._collect_item(pk)
        else:
            pk.collected = True

    def _collect_item(self, pk):
        player = self.player
        item = pk.item
        if item is None:
            pk.collected = True
            return
        item = dict(item)
        # P3.5: track items seen
        item_id = item.get("id")
        if item_id:
            self.seen_items.add(item_id)
        item_tier = int(item.get("tier", 1) or 1)
        if item_id and item_tier >= 2 and self.profile is not None:
            save_sys.unlock_item(self.profile, item_id)
        slot = item.get("slot")
        if slot == "consumable":
            if player.add_consumable(item):
                player.items_owned.append(item.get("id"))
                pk.collected = True
                self.floating.add("%s" % item.get("display") or item.get("name"),
                                  color=tuple(item.get("rarity_color") or (246, 242, 232)), life=1.6)
                play(self, "pickup")
            return
        if loot.is_upgrade(player, item):
            old = player.equip(item)
            player.items_owned.append(item.get("id"))
            pk.collected = True
            rarity = item.get("rarity", "common")
            self.floating.add("%s (%s)" % (item.get("display") or item.get("name"), rarity),
                              color=tuple(item.get("rarity_color") or (246, 242, 232)), life=2.0)
            if rarity == "legendary":
                self.floating.add(self.content.flavor_for("item", self.rng) or "Legendary!",
                                  color=(232, 178, 60), life=2.6)
            play(self, "pickup")
            if old is not None:
                if len(player.backpack) < 8:
                    player.backpack.append(old)
                else:
                    self.add_entity(Pickup(self.next_id(), pk.x + 18, pk.y + 18, "item",
                                           item=old, sprite=old.get("sprite")))
            return
        if len(player.backpack) < 8:
            player.backpack.append(item)
            player.items_owned.append(item.get("id"))
            pk.collected = True
            self.floating.add("%s (stowed)" % (item.get("display") or item.get("name")),
                              color=tuple(item.get("rarity_color") or (246, 242, 232)), life=1.4)
            play(self, "pickup")

    def _use_shrine(self, pk):
        shrine_sys.activate_shrine(self)
        self.particles.burst(pk.x, pk.y, self.rng, count=14, color=(121, 176, 74),
                             speed=80.0, life=0.5, size=3)
        self.particles.burst(pk.x, pk.y, self.rng, count=10, color=(196, 99, 95),
                             speed=70.0, life=0.5, size=3)
        play(self, "levelup")

    def _use_shop(self, pk):
        player = self.player
        price = SHOP_PRICE_BASE + 12 * self.floor
        try:
            from . import save as save_sys
            se = save_sys.meta_special_effects(self.profile)
            price = int(round(price * float(se.get("shop_price_mult", 1.0))))
        except Exception:
            pass
        if player.gold < price:
            if self.notice_timer <= 0.0:
                self.notice = "Shop: %d gold needed" % price
                self.notice_timer = 1.5
            return False
        tier = min(5, loot.tier_for_floor(self.floor, player.stats.luck()) + 1)
        unlocks = (self.profile or {}).get("unlocks") if self.profile else None
        item = loot.make_item(self.content, self.rng, tier=tier, luck=player.stats.luck() + 6, unlocks=unlocks)
        if item is None:
            return False
        player.gold -= price
        self.add_entity(Pickup(self.next_id(), pk.x + 24, pk.y, "item", item=item,
                               sprite=item.get("sprite")))
        self.floating.add("Bought %s for %d gold" % (item.get("display") or item.get("name"), price),
                          color=(232, 178, 60), life=2.2)
        play(self, "coin")
        return False        # the stall stays open all floor

    def use_consumable(self, index=0):
        player = self.player
        pool = player.consumables or player.backpack
        if not pool:
            return False
        item = pool.pop(index) if index < len(pool) else pool.pop(0)
        effects = {}
        for key, value in (item.get("effect") or {}).items():
            if key == "max_hp":
                healed = player.heal(self.heal_amount(value))
                if healed > 0:
                    self.damage_numbers.add(player.x, player.y - 24, healed,
                                            color=(121, 176, 74), label="+%d" % int(healed))
            else:
                effects[key] = value
        if effects:
            if "armor" in effects:
                from ..entities.monster import ARMOR_PER_POINT, ARMOR_FRACTION_CAP
                effects["armor"] = min(ARMOR_FRACTION_CAP, effects["armor"] * ARMOR_PER_POINT)
            self.consumable_buffs.append({"effects": effects, "remaining": CONSUMABLE_BUFF_TIME})
            self._tick_consumable_buffs(0.0)
        self.floating.add("Drank %s" % (item.get("name") or "potion"), color=(121, 176, 74), life=1.6)
        play(self, "pickup")
        return True

    # -- invariants ------------------------------------------------------
    def check_invariants(self):
        """docs/CONTRACTS.md 3.1 - returns a list of violation strings (empty = pass)."""
        violations = []
        level = self.level
        if level is None:
            return ["no level generated"]
        max_x = level.w * TILE
        max_y = level.h * TILE

        for entity in self.entities:
            if not getattr(entity, "alive", False):
                continue
            if entity.x < 0 or entity.y < 0 or entity.x > max_x or entity.y > max_y:
                violations.append("entity %s#%d outside level bounds at (%.1f, %.1f)"
                                  % (getattr(entity, "kind", "?"), entity.id, entity.x, entity.y))

        player = self.player
        top = player.stats.max_hp()
        if player.hp < 0 or player.hp > top + 1e-6:
            violations.append("player hp %.3f outside [0, %.3f]" % (player.hp, top))

        # P3.5: invariant check for rooms_visited
        if self.rooms_visited < 0:
            violations.append("rooms_visited is negative")

        seen = set()
        for entity in self.entities:
            if entity.id in seen:
                violations.append("duplicate entity id %d" % entity.id)
            seen.add(entity.id)

        # stairs reachable from spawn (BFS over walkable tiles, cap 20 000)
        reach = level.bfs(level.spawn_tile, cap=20000)
        if level.stairs_tile not in reach:
            violations.append("stairs %r unreachable from spawn %r"
                              % (level.stairs_tile, level.spawn_tile))

        # every item id the player owns exists in the content registry
        known = self.content.item_ids()
        for item_id in player.owned_item_ids():
            if item_id not in known:
                violations.append("item id %r not present in content" % item_id)
        for pickup in self.pickups:
            if pickup.item is not None and pickup.item.get("id") not in known:
                violations.append("pickup item id %r not present in content"
                                  % pickup.item.get("id"))

        # no None in the last render list
        if self.render_list is not None:
            for entry in self.render_list:
                if entry is None:
                    violations.append("None in render list")
                    break
        # P4.4: validate scorch_decals have valid positions
        for decal in self.scorch_decals:
            if decal["life"] > 0 and (decal["x"] < 0 or decal["y"] < 0):
                violations.append("scorch_decal outside bounds")
        return violations

    def _track_room_visit(self):
        """Increment rooms_visited when the player enters a new room."""
        if self.player is None or self.level is None:
            return
        tx = int(self.player.tile_x)
        ty = int(self.player.tile_y)
        room = self.level.room_at(tx, ty)
        if room is not None:
            room_id = room.get("id", "")
            if room_id and room_id != self._last_room_id:
                self.rooms_visited += 1
                self._last_room_id = room_id

    def _check_secret_reveal(self, player):
        """Reveal secret rooms adjacent to the player."""
        if not self.level:
            return
        ptx = int(player.x // TILE)
        pty = int(player.y // TILE)
        for secret in self._level_secret_rooms:
            if secret.get("kind") != "secret":
                continue
            rid = secret.get("id", "")
            if rid in self.discovered_secrets:
                continue
            sx = int(secret.get("x", 0))
            sy = int(secret.get("y", 0))
            sw = int(secret.get("w", 8))
            sh = int(secret.get("h", 8))
            # Check if player is adjacent to the secret room
            for dx in range(-1, sw + 1):
                for dy in range(-1, sh + 1):
                    tx = sx + dx
                    ty = sy + dy
                    if (abs(ptx - tx) <= 1 and abs(pty - ty) <= 1):
                        self.discovered_secrets.add(rid)
                        # Carve the secret room into the tile grid
                        for rx in range(sx, min(self.level.w, sx + sw)):
                            for ry in range(sy, min(self.level.h, sy + sh)):
                                if 0 <= rx < self.level.w and 0 <= ry < self.level.h:
                                    self.level.tiles[rx][ry] = procgen.FLOOR
                        # Add to level.rooms if not already there
                        already = any(r.get("id") == rid for r in self.level.rooms)
                        if not already:
                            from .procgen import _room_from_data
                            room_obj = _room_from_data(dict(secret))
                            room_obj._revealed = True
                            self.level.rooms.append(room_obj)
                        # Also reveal hidden doors for this secret
                        if rid in self.level.hidden_doors:
                            for (hdx, hdy) in self.level.hidden_doors[rid]:
                                if 0 <= hdx < self.level.w and 0 <= hdy < self.level.h:
                                    self.level.tiles[hdx][hdy] = procgen.DOOR_OPEN
                        break

    def player_interact(self):
        """Check if player is adjacent to a cracked wall and break it.

        When cracked wall is broken: remove CRACKED_WALL tile, reveal
        the secret room, add to level.rooms.
        """
        if not self.level or not self.player:
            return False
        ptx = int(self.player.x // TILE)
        pty = int(self.player.y // TILE)
        for (tx, ty), room_id in list(self.cracked_walls.items()):
            if abs(ptx - tx) <= 1 and abs(pty - ty) <= 1:
                # Break the cracked wall
                self.level.tiles[tx][ty] = procgen.FLOOR
                self.cracked_walls.pop((tx, ty), None)
                # Find and reveal the associated secret room
                for secret in self._level_secret_rooms:
                    if secret.get("id") == room_id or secret.get("kind") == "secret":
                        rid = secret.get("id", "")
                        if rid not in self.discovered_secrets:
                            self.discovered_secrets.add(rid)
                            sx = int(secret.get("x", 0))
                            sy = int(secret.get("y", 0))
                            sw = int(secret.get("w", 8))
                            sh = int(secret.get("h", 8))
                            for rx in range(sx, min(self.level.w, sx + sw)):
                                for ry in range(sy, min(self.level.h, sy + sh)):
                                    if 0 <= rx < self.level.w and 0 <= ry < self.level.h:
                                        self.level.tiles[rx][ry] = procgen.FLOOR
                            already = any(r.get("id") == rid for r in self.level.rooms)
                            if not already:
                                from .procgen import _room_from_data
                                room_obj = _room_from_data(dict(secret))
                                room_obj._revealed = True
                                self.level.rooms.append(room_obj)
                        # Also reveal hidden doors for this secret
                        if rid in self.level.hidden_doors:
                            for (hdx, hdy) in self.level.hidden_doors[rid]:
                                if 0 <= hdx < self.level.w and 0 <= hdy < self.level.h:
                                    self.level.tiles[hdx][hdy] = procgen.DOOR_OPEN
                        return True
                return True
        return False

    def player_interact_event(self):
        """Check if player is adjacent to an event room and interact."""
        if not self.level or not self.player:
            return False
        ptx = int(self.player.x // TILE)
        pty = int(self.player.y // TILE)
        for room in self.level.rooms:
            kind = room.get("kind", "")
            if kind not in ("gambling", "blacksmith", "fountain", "omen"):
                continue
            rid = room.get("id", "")
            rx = int(room.get("x", 0))
            ry = int(room.get("y", 0))
            rw = int(room.get("w", 8))
            rh = int(room.get("h", 8))
            # Check if player is adjacent to the room
            if (rx - 1 <= ptx <= rx + rw and ry - 1 <= pty <= ry + rh and
                    abs(ptx - (rx + rw // 2)) <= 1 and abs(pty - (ry + rh // 2)) <= 1):
                state = self.event_room_state.setdefault(rid, {"visited": False, "interaction_done": False})
                state["visited"] = True
                if not state["interaction_done"]:
                    # P3.5: track room visits
                    if rid and rid != self._last_room_id:
                        self.rooms_visited += 1
                        self._last_room_id = rid
                    self._interact_event_room(rid, kind)
                return True
        return False

    def _break_cracked_wall(self, tx, ty):
        """Break a specific cracked wall at (tx, ty) and reveal its secret room."""
        if not self.level:
            return
        room_id = self.cracked_walls.pop((tx, ty), None)
        if room_id:
            self.level.tiles[tx][ty] = procgen.FLOOR
            for secret in self._level_secret_rooms:
                if secret.get("id") == room_id or (secret.get("kind") == "secret"):
                    rid = secret.get("id", "")
                    if rid not in self.discovered_secrets:
                        self.discovered_secrets.add(rid)
                        sx = int(secret.get("x", 0))
                        sy = int(secret.get("y", 0))
                        sw = int(secret.get("w", 8))
                        sh = int(secret.get("h", 8))
                        for rx in range(sx, min(self.level.w, sx + sw)):
                            for ry in range(sy, min(self.level.h, sy + sh)):
                                if 0 <= rx < self.level.w and 0 <= ry < self.level.h:
                                    self.level.tiles[rx][ry] = procgen.FLOOR
                        already = any(r.get("id") == rid for r in self.level.rooms)
                        if not already:
                            from .procgen import _room_from_data
                            room_obj = _room_from_data(dict(secret))
                            room_obj._revealed = True
                            self.level.rooms.append(room_obj)

    # -- reporting -------------------------------------------------------
    def counts(self):
            tiles = self.level.tiles if self.level else []
            # Encode tiles as a compact hex string: each row is a hex byte per tile
            tiles_hex = ";".join(
                "".join(f"{t:02x}" for t in row) for row in tiles
            ) if tiles else ""
            return {
                "entities": sum(1 for e in self.entities if e.alive),
                "monsters": sum(1 for m in self.monsters if m.alive),
                "projectiles": sum(1 for p in self.projectiles if p.alive),
                "pickups": sum(1 for p in self.pickups if p.alive and not p.collected),
                "rooms": len(self.level.rooms) if self.level else 0,
                "level_w": self.level.w if self.level else 0,
                "level_h": self.level.h if self.level else 0,
                "spawn_tile": list(self.level.spawn_tile) if self.level else None,
                "stairs_tile": list(self.level.stairs_tile) if self.level else None,
                "tiles": tiles_hex,
            }

    def summary(self, ok=None):
        player = self.player
        violations = self.check_invariants()
        counts = self.counts()
        metrics = {
            "frames": self.frames_rendered,
            "ms_per_tick": round(float(self.ms_per_tick), 4),
            "fps_equiv": int(round(1000.0 / self.ms_per_tick)) if self.ms_per_tick > 0 else 0,
        }
        # P5.3: include profiler summary if available
        profiler_data = {}
        if hasattr(self, 'profiler_summary') and self.profiler_summary:
            profiler_data = self.profiler_summary
        return {
            "ok": bool(ok) if ok is not None else not self.errors,
            "seed": self.seed,
            "ticks": self.tick,
            "biome": self.biome_id,
            "floor": self.floor,
            "player": {
                "hp": int(round(player.hp)),
                "max_hp": int(round(player.stats.max_hp())),
                "level": int(player.level),
                "xp": int(player.xp),
                "gold": int(player.gold),
                "essence": int(player.essence),
                "kills": int(player.kills),
                "items": list(player.owned_item_ids()),
                "statuses": status_sys.status_ids(player),
                "pos": [int(player.tile_x), int(player.tile_y)],
            },
            "world": counts,
            "metrics": metrics,
            "metrics_profiler": profiler_data,
            "endless": bool(self.endless),
            "curses": list(self.run_curses),
            "errors": list(self.errors),
            "invariants": {"violations": violations},
        }
