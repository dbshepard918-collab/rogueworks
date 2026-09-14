"""Input: keyboard, scripted JSON (CONTRACTS.md 3.2), and a QA autopilot source.

An InputSource returns an ``InputState`` per tick:
    move    : (mx, my) unit-ish vector in [-1, 1]^2
    actions : set of "attack" | "dash" | "ranged" | "interact" | "inventory" | "confirm"
Scripted input repeats the last action vector on ticks with no step of their own.
"""

import json

import pygame

TILE = 32

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

    def __init__(self, world):
        self.path = []
        self.path_goal = None
        self.repath_at = 0
        self.avoid = set()             # monster ids we could not reach
        self.stuck_ref = None
        self.stuck_tick = 0

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

    def sample(self, world=None, keys=None):
        if world is None:
            return InputState.idle()
        player = world.player
        if player is None or not player.alive:
            return InputState.idle()

        actions = set()
        threat, threat_dist = self._nearest(world, player, self.ENGAGE_RANGE)
        low_hp = player.hp < player.stats.max_hp() * self.RETREAT_HP
        objective = world.objective_tile()

        # stuck detection: if we are grinding against geometry, drop the target
        if self.stuck_ref is None:
            self.stuck_ref = (player.x, player.y)
            self.stuck_tick = world.tick
        elif world.tick - self.stuck_tick >= 45:
            moved = abs(player.x - self.stuck_ref[0]) + abs(player.y - self.stuck_ref[1])
            if moved < 4.0:
                if threat is not None:
                    self.avoid.add(threat.id)
                    threat = None
                self.path = []
                self.path_goal = None
            self.stuck_ref = (player.x, player.y)
            self.stuck_tick = world.tick
        if len(self.avoid) > 8:
            self.avoid.clear()
        # drink something when hurt
        if low_hp and (player.consumables or player.backpack):
            world.use_consumable(0)

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

        # 1. emergency: dash away from the pack, hard
        if threat is not None and low_hp and player.dash_ready() and threat_dist < 120.0:
            dx = player.x - threat.x
            dy = player.y - threat.y
            length = max(0.001, (dx * dx + dy * dy) ** 0.5)
            actions.add("dash")
            return InputState((dx / length, dy / length), actions)

        # 2. target selection: nearest monster to clear, else the floor objective
        target = (threat.tile_x, threat.tile_y) if threat is not None else objective

        # 3. combat actions
        if threat is not None:
            if player.attack_ready() and reach <= player.ATTACK_REACH:
                actions.add("attack")
            if player.ranged_ready() and self.RANGED_MIN < threat_dist < self.RANGED_MAX:
                actions.add("ranged")
                if not player.attack_ready():
                    target = (threat.tile_x, threat.tile_y)

        # 4. point blank and recharged: step into the swing so we face the target
        if threat is not None and player.attack_ready() and reach <= player.ATTACK_REACH * 0.8:
            dx = threat.x - player.x
            dy = threat.y - player.y
            length = max(0.001, (dx * dx + dy * dy) ** 0.5)
            return InputState((dx / length, dy / length), actions)

        # 5. navigate (always pathfind: rooms and corridors need it)
        if (self.path_goal != target or world.tick >= self.repath_at or not self.path):
            self.path = world.path_to(player.tile_x, player.tile_y, target[0], target[1],
                                      cap=4000) or []
            self.path_goal = target
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
