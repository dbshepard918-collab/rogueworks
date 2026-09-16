"""Input: keyboard, scripted JSON (CONTRACTS.md 3.2), and a QA autopilot source.

An InputSource returns an ``InputState`` per tick:
    move    : (mx, my) unit-ish vector in [-1, 1]^2
    actions : set of "attack" | "dash" | "ranged" | "interact" | "inventory" | "confirm"
Scripted input repeats the last action vector on ticks with no step of their own.
"""

import json

import pygame

TILE = 64

ACTION_NAMES = ("attack", "dash", "ranged", "interact", "inventory", "confirm", "quit", "pause")


class InputState:
    __slots__ = ("move", "actions")

    def __init__(self, move=(0.0, 0.0), actions=()):
        self.move = (float(move[0]), float(move[1]))
        self.actions = set(actions)

    def has(self, action):
        return action in self.actions

    @staticmethod
    def idle():
        return InputState()


class ScriptedInput:
    """Parses CONTRACTS.md 3.2 scripted input JSON."""

    def __init__(self, path=None, steps=None, name="script"):
        self.name = name
        self.steps = {}
        self.ordered = []
        if path is not None:
            data = load_script(path)
            self.name = data.get("name", name)
            steps = data.get("steps", [])
        for step in steps or []:
            tick = int(step.get("tick", 0))
            move = step.get("move", (0.0, 0.0))
            try:
                mx = float(move[0])
                my = float(move[1])
            except (TypeError, ValueError, IndexError):
                mx, my = 0.0, 0.0
            # clamp to the promised [-1,1]^2 unit-ish vector
            mx = max(-1.0, min(1.0, mx))
            my = max(-1.0, min(1.0, my))
            actions = tuple(str(a) for a in (step.get("actions") or []))
            self.steps[tick] = InputState((mx, my), actions)
            self.ordered.append(tick)
        self.ordered.sort()
        self._last = InputState.idle()

    def sample(self, world=None, keys=None):
        tick = world.tick if world is not None else 0
        if tick in self.steps:
            self._last = self.steps[tick]
        return self._last


def load_script(path):
    """Read a scripted-input file.  Bad files degrade to an empty script, never crash."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict) and isinstance(data.get("steps"), list):
            return data
    except (OSError, ValueError):
        pass
    return {"name": "empty", "steps": []}


class KeyboardInput:
    """WASD/arrows + SPACE (attack) + J (ranged) + SHIFT (dash) + TAB (inventory) + E (interact).
    
    P2.6: supports remappable keys via settings.key_map.  Falls back to defaults
    when a key is missing from the map.  Also supports hold-to-attack mode:
    when settings["hold_to_attack"] is True, holding attack key while holding
    a direction registers "attack" continuously (not just edge-triggered).
    """

    def __init__(self, key_map=None, hold_to_attack=False):
        from ..ui.settings import DEFAULT_KEY_MAP
        self.key_map = dict(DEFAULT_KEY_MAP)
        if key_map:
            self.key_map.update({k: int(v) for k, v in key_map.items()})
        self.hold_to_attack = hold_to_attack

    def sample(self, world=None, keys=None):
        if keys is None:
            keys = pygame.key.get_pressed()
        km = self.key_map
        mx = 0.0
        my = 0.0
        if keys[km.get("move_left", pygame.K_a)] or keys[pygame.K_LEFT]:
            mx -= 1.0
        if keys[km.get("move_right", pygame.K_d)] or keys[pygame.K_RIGHT]:
            mx += 1.0
        if keys[km.get("move_up", pygame.K_w)] or keys[pygame.K_UP]:
            my -= 1.0
        if keys[km.get("move_down", pygame.K_s)] or keys[pygame.K_DOWN]:
            my += 1.0
        if mx and my:
            inv = 0.7071067811865476
            mx *= inv
            my *= inv
        actions = set()
        # edge-triggered actions are drained by the scene which owns the key state
        for key, action in ((km.get("attack", pygame.K_SPACE), "attack"),
                            (km.get("dash", pygame.K_LSHIFT), "dash"),
                            (km.get("ranged", pygame.K_j), "ranged"),
                            (pygame.K_RSHIFT, "dash"),
                            (km.get("interact", pygame.K_e), "interact"),
                            (km.get("inventory", pygame.K_TAB), "inventory"),
                            (pygame.K_F5, "attack")):
            if keys[key]:
                actions.add(action)
        # P2.6: hold-to-attack — when holding a direction and the attack key,
        # continuously register "attack" instead of only edge-triggering
        if self.hold_to_attack:
            attack_key = km.get("attack", pygame.K_SPACE)
            if keys[attack_key] and (mx != 0.0 or my != 0.0):
                actions.add("attack")
        return InputState((mx, my), actions)


class AutoPilotInput:
    """QA input source: clears the room it is in, then walks to the objective.

    Used by tools/qa/autopilot.py to prove that floors generate, connect and are
    completable.  Implements exactly the same InputState surface as the others.
    """

    ENGAGE_RANGE = 230.0       # fight anything this close
    RANGED_MIN = 70.0
    RANGED_MAX = 300.0
    RETREAT_HP = 0.4
    STRAFE_TICKS = 60            # r47: ticks between strafe direction changes
    # r59: stair-first navigation
    STAIR_FIRST_HP = 0.8         # r59: below this HP, go for stairs first
    STAIR_CLEAR_RADIUS = 150.0   # r59: fight monsters within this range of stairs path
    HEAL_THRESHOLD = 0.6         # r59: use consumables above retreat threshold

    def __init__(self, world):
        self.path = []
        self.path_goal = None
        self.repath_at = 0
        self.avoid = set()
        self.stuck_ref = None
        self.stuck_tick = 0
        self.strafe_dir = 1         # r47: current strafe direction (1 or -1)
        self.strafe_tick = 0        # r47: ticks until next strafe flip
        self.last_threat = None     # r47: last monster that damaged us
        self.recovery_mode = False  # r57: follow recovery path ignoring threats
        self.recovery_target = None
        self.stuck_recovery = 0

    def _nearest(self, world, player, max_range=1e9):
        best = None
        best_dist = max_range
        for mon in world.monsters:
            if not mon.alive or mon.id in self.avoid:
                continue
            dist = mon.dist_to(player)
            if dist < best_dist:
                best = mon
                best_dist = dist
        return best, best_dist

    def _is_between(self, ax, ay, bx, by, cx, cy2, threshold=15):
        """r59: is point A between points B and C?"""
        dist_bc = abs(bx - cx) + abs(by - cy2)
        dist_ba = abs(ax - bx) + abs(ay - by)
        dist_ac = abs(ax - cx) + abs(ay - cy2)
        return dist_ba + dist_ac <= dist_bc + threshold

    def _recovery_target(self, world, player):
        """r57: pick a target tile when stuck - nearest walkable room center to stairs."""
        px, py = player.tile_x, player.tile_y
        stairs = world.objective_tile()
        best = None
        best_score = 1e9
        for room in world.level.rooms:
            rx = room.get("x", 0) + room.get("w", 8) // 2
            ry = room.get("y", 0) + room.get("h", 8) // 2
            if not world.level.walkable(rx, ry):
                found = False
                for dx in range(-3, 4):
                    for dy in range(-3, 4):
                        if world.level.walkable(rx + dx, ry + dy):
                            rx, ry = rx + dx, ry + dy
                            found = True
                            break
                    if found:
                        break
            if not world.level.walkable(rx, ry):
                continue
            dist_to_stairs = abs(rx - stairs[0]) + abs(ry - stairs[1])
            dist_to_player = abs(rx - px) + abs(ry - py)
            score = dist_to_stairs + dist_to_player * 0.5
            if score < best_score:
                best = (rx, ry)
                best_score = score
        if best is not None:
            return best
        return stairs

    def _nearest_walkable(self, world, tx, ty, radius=5):
        """r57: find nearest walkable tile to (tx, ty) within radius."""
        for r in range(radius + 1):
            for dx in range(-r, r + 1):
                for dy in range(-r, r + 1):
                    if abs(dx) + abs(dy) != r:
                        continue
                    if world.level.walkable(tx + dx, ty + dy):
                        return (tx + dx, ty + dy)
        return (tx, ty)

    def _ranged_threat(self, world, player, threat, threat_dist):
        """Detect a ranged monster holding beyond melee range but within gun range."""
        if threat is None:
            return None, None
        if threat_dist > self.RANGED_MAX:
            return None, None
        # Is this monster actually ranged?
        if getattr(threat, 'kind', '') not in ('ranged', 'ranged_ranged') and threat_dist > self.ENGAGE_RANGE:
            # Not confirmed ranged, but still plinking us — treat as ranged
            return threat, threat_dist
        return None, None

    def sample(self, world=None, keys=None):
        if world is None:
            return InputState.idle()
        player = world.player
        if player is None or not player.alive:
            return InputState.idle()

        actions = set()
        # r57: in recovery mode, skip threat detection until we reach target
        if self.recovery_mode and self.recovery_target is not None:
            threat = None
            threat_dist = 1e9
            ranged_at = None
            dist_to_recovery = abs(player.tile_x - self.recovery_target[0]) + abs(player.tile_y - self.recovery_target[1])
            if dist_to_recovery <= 2:
                self.recovery_mode = False
                self.recovery_target = None
                self.path = []
                self.path_goal = None
        else:
            threat, threat_dist = self._nearest(world, player, self.ENGAGE_RANGE)
        ranged_at = None
        if threat is None:
            # r44: A ranged monster can hold beyond ENGAGE_RANGE and plink us.
            far, far_dist = self._nearest(world, player, self.RANGED_MAX)
            if far is not None:
                threat, threat_dist = far, far_dist
                ranged_at = far
        low_hp = player.hp < player.stats.max_hp() * self.RETREAT_HP
        objective = world.objective_tile()
        # r59: count nearby monsters for retreat decision
        nearby_count = sum(1 for m in world.monsters if m.alive and m.dist_to(player) < 150)

        # r47: track last threat that hit us for kiting
        if player.last_damage_taken > 0 and threat is not None:
            self.last_threat = threat.id

        # r57: stuck detection with recovery mode
        if self.stuck_ref is None:
            self.stuck_ref = (player.x, player.y)
            self.stuck_tick = world.tick
        elif world.tick - self.stuck_tick >= 45:
            moved = abs(player.x - self.stuck_ref[0]) + abs(player.y - self.stuck_ref[1])
            if moved < 4.0:
                self.stuck_recovery += 1
                if threat is not None:
                    self.avoid.add(threat.id)
                    threat = None
                self.path = []
                self.path_goal = None
                recovery_target = self._recovery_target(world, player)
                if recovery_target is not None:
                    path = world.path_to(player.tile_x, player.tile_y,
                                        recovery_target[0], recovery_target[1],
                                        cap=4000)
                    if path:
                        self.path = path
                        self.path_goal = recovery_target
                        self.recovery_target = recovery_target
                        self.recovery_mode = True
                        self.repath_at = world.tick + 30
                if self.stuck_recovery > 4:
                    self.avoid.clear()
                    self.stuck_recovery = 0
            else:
                if self.recovery_mode:
                    self.recovery_mode = False
                    self.recovery_target = None
                    self.path = []
                    self.path_goal = None
                self.stuck_recovery = max(0, self.stuck_recovery - 1)
            self.stuck_ref = (player.x, player.y)
            self.stuck_tick = world.tick
        if len(self.avoid) > 8:
            self.avoid.clear()


        reach = threat_dist - threat.radius if threat is not None else 1e9

        # 0. never stand in a telegraphed slam
        for mon in world.monsters:
            if mon.alive and mon.telegraph > 0.0 and mon.dist_to(player) < mon.slam_radius + 12:
                dx = player.x - mon.x
                dy = player.y - mon.y
                length = max(0.001, (dx * dx + dy * dy) ** 0.5)
                if player.dash_ready():
                    actions.add("dash")
                return InputState((dx / length, dy / length), actions)



        # r59: stair-first logic — go for stairs, only fight blocking monsters
        very_low_hp = player.hp < player.stats.max_hp() * 0.3



        # r62: ranged thinning — when 3+ monsters nearby, use ranged to reduce numbers
        if threat is not None and nearby_count >= 3 and player.ranged_ready() and self.RANGED_MIN < threat_dist < self.RANGED_MAX:
            actions.add("ranged")
            # Also dash away if very low hp
            if very_low_hp and player.dash_ready():
                actions.add("dash")
                dx = player.x - threat.x
                dy = player.y - threat.y
                length = max(0.001, (dx * dx + dy * dy) ** 0.5)
                return InputState((dx / length, dy / length), actions)

        # r62: emergency escape — lower threshold (was 0.4, now 0.5) OR overwhelmed
        if threat is not None and (low_hp or (nearby_count > 3 and low_hp)) and player.dash_ready() and threat_dist < 120.0:
            dx = player.x - threat.x
            dy = player.y - threat.y
            length = max(0.001, (dx * dx + dy * dy) ** 0.5)
            actions.add("dash")
            return InputState((dx / length, dy / length), actions)

        # r59: target selection — stairs first, but fight back when attacked
        target = objective  # default: go to stairs
        taking_damage = player.last_damage_taken > 0
        if threat is not None:
            on_path = self._is_between(threat.tile_x, threat.tile_y, player.tile_x, player.tile_y, objective[0], objective[1], self.STAIR_CLEAR_RADIUS)
            if on_path or taking_damage or threat_dist < self.ENGAGE_THRESHOLD:
                target = (threat.tile_x, threat.tile_y)

        # 3. combat actions — only when monster is our chosen target
        if threat is not None and target == (threat.tile_x, threat.tile_y):
            if player.attack_ready() and reach <= player.ATTACK_REACH:
                actions.add("attack")
            if player.ranged_ready() and self.RANGED_MIN < threat_dist < self.RANGED_MAX:
                actions.add("ranged")
                if not player.attack_ready():
                    target = (threat.tile_x, threat.tile_y)

        # r47: strafe — don't stand still in combat, orbit the target
        if threat is not None and target == (threat.tile_x, threat.tile_y) and reach <= player.ATTACK_REACH * 1.5:
            dx = threat.x - player.x
            dy = threat.y - player.y
            length = max(0.001, (dx * dx + dy * dy) ** 0.5)
            px = -dy / length * self.strafe_dir
            py = dx / length * self.strafe_dir
            dx_move = dx / length * 0.7 + px * 0.3
            dy_move = dy / length * 0.7 + py * 0.3
            self.strafe_tick += 1
            if self.strafe_tick >= self.STRAFE_TICKS:
                self.strafe_dir *= -1
                self.strafe_tick = 0
            return InputState((dx_move, dy_move), actions)

        # 4. point blank and recharged: step into the swing so we face the target
        if threat is not None and target == (threat.tile_x, threat.tile_y) and player.attack_ready() and reach <= player.ATTACK_REACH * 0.8:
            dx = threat.x - player.x
            dy = threat.y - player.y
            length = max(0.001, (dx * dx + dy * dy) ** 0.5)
            return InputState((dx / length, dy / length), actions)

        # 5. navigate (always pathfind: rooms and corridors need it)
        # r57: in recovery mode, use recovery target instead of objective
        nav_target = self.recovery_target if (self.recovery_mode and self.recovery_target is not None) else target
        if (self.path_goal != nav_target or world.tick >= self.repath_at or not self.path):
            self.path = world.path_to(player.tile_x, player.tile_y, nav_target[0], nav_target[1],
                                      cap=4000) or []
            self.path_goal = nav_target
            self.repath_at = world.tick + 30
        while self.path and (self.path[0][0] - player.tile_x) ** 2 + \
                (self.path[0][1] - player.tile_y) ** 2 <= 1:
            self.path.pop(0)
        waypoint = self.path[0] if self.path else target

        dx = (waypoint[0] * TILE + 16) - player.x
        dy = (waypoint[1] * TILE + 16) - player.y
        length = (dx * dx + dy * dy) ** 0.5
        if length > 1.0:
            dx /= length
            dy /= length
        else:
            dx = dy = 0.0
        return InputState((dx, dy), actions)


class ReplayInput:
    """Feeds a recorded list of InputState, used by the selftest and
    deterministic replay (P5.2).  Supports both playback and recording.

    When --record is active, sample() delegates to AutoPilotInput for
    real gameplay input, captures each tick's state, and replays them
    back verbatim on --replay.  Frame-exact: same seed + same replay ->
    identical run.  """

    def __init__(self, states=None, world=None):
        self.states = list(states) if states else []
        self.index = 0
        self.last = InputState.idle()
        self._recording = False
        self._recorded = []          # used when --record is active
        self._auto_pilot = None      # wrapped AutoPilotInput during record
        self._world_ref = world      # weak ref to pass to AutoPilotInput

    def sample(self, world=None, keys=None):
        # P5.2: during recording, delegate to AutoPilotInput for real input
        if self._recording:
            if self._auto_pilot is None and world is not None:
                from game.engine.input import AutoPilotInput
                self._auto_pilot = AutoPilotInput(world)
            if self._auto_pilot is not None:
                inp = self._auto_pilot.sample(world, keys)
                self._recorded.append(
                    InputState(inp.move, tuple(sorted(inp.actions))))
                self.last = inp
                return inp
            # fallback: capture idle if no world
            self._recorded.append(InputState(self.last.move, tuple(sorted(self.last.actions))))
        if self.index < len(self.states):
            self.last = self.states[self.index]
            self.index += 1
        return self.last

    def start_recording(self):
        """Begin capturing input states.  Called before a headless run."""
        self._recording = True
        self._recorded = []
        self.index = 0
        self.last = InputState.idle()
        self._auto_pilot = None

    def stop_recording(self):
        """Stop capturing and return the recorded list."""
        self._recording = False
        self._auto_pilot = None
        return list(self._recorded)

    def save(self, path):
        """Serialize recorded states to a JSON replay file."""
        data = {"version": 1, "seed": 0, "ticks": len(self._recorded),
                "states": [{"move": list(s.move),
                            "actions": list(s.actions)}
                           for s in self._recorded]}
        import json
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        return path

    @classmethod
    def load(cls, path):
        """Load a replay file and return a ReplayInput ready to play."""
        import json
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        states = [InputState(tuple(s["move"]), tuple(s["actions"]))
                  for s in data.get("states", [])]
        return cls(states)
