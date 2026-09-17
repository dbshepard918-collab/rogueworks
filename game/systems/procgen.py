"""Procgen: room-and-corridor level generation for Depths of Vaelmoor.

Tile values (must stay in sync with biome_mods.TILE_BURNING/WATER and the
renderer's procgen.STAIRS/WALL checks):

    0  floor
    1  wall
    2  stairs
    3  (unused)
    4  burning  (ember_heat biome)
    5  water    (drowned_water biome)

The ``Level`` object carries the tile grid, the room list, props, spawn/stairs
tiles, a fog-of-war mask, and the pathfinding helpers the rest of the codebase
depends on (world.check_invariants, ai._step_toward, renderer.draw, etc.).

``generate(content, floor_rng, floor, biome_id, world_profile=None)`` is the
single public entry point and is fully deterministic from *floor_rng*.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

TILE = 64

# -- tile values --------------------------------------------------------------- #
FLOOR = 0
WALL = 1
STAIRS = 2
BURNING = 4
WATER = 5
DOOR = 6
DOOR_OPEN = 7
CRACKED_WALL = 8
HIDDEN_DOOR = 9

# -- room placement grid ------------------------------------------------------
# Levels are built on a coarse grid so rooms never overlap.  The grid cell
# size grows with floor depth so later levels feel more cavernous.
GRID_CELL_MIN = 9          # tiles per grid cell at floor 1


def _grid_cell_for(floor):
    return GRID_CELL_MIN + int(floor / 3)


def _level_extents(floor, biome_id, content, rng):
    """Return (level_w, level_h) in tiles for *floor* / *biome_id*."""
    cell = _grid_cell_for(floor)
    # 3x2 base room grid, plus corridor margins
    cols = 3
    rows = 2
    w = cols * cell + 6 + rng.randint(0, 16)
    h = rows * cell + 6 + rng.randint(0, 16)
    # clamp into the GDD band (48x32 .. 80x56)
    w = max(96, min(160, w))
    h = max(64, min(112, h))
    return w, h


def _room_slots(w, h, cell):
    """List of (col, row) grid slots on a 3x2 arrangement."""
    slots = []
    for col in range(3):
        for row in range(2):
            slots.append((col, row))
    return slots


def _place_rooms(content, biome_id, level_w, level_h, cell, rng):
    """Choose rooms from content and assign each a grid slot + pixel origin.

    Returns (rooms, props, spawn_candidate, stairs_candidate) where each room
    is a dict with the content room plus ``x``, ``y``, ``center`` keys.
    """
    pool = content.rooms_for(biome_id)
    if not pool:
        # fallback: build a minimal set from the room kind palette
        pool = _fallback_rooms(biome_id)
    # shuffle the pool deterministically so different floors pick different rooms
    pool = list(pool)
    rng.shuffle(pool)

    rooms = []
    used_slots = set()
    slot_list = _room_slots(level_w, level_h, cell)

    # We want 9-10 rooms: 1 entrance, 1 boss, combat/treasure/shrine/shop, plus secrets
    desired = 7 + (1 if level_w > 60 else 0) + (1 if level_w > 70 else 0)
    kind_want = ["entrance", "boss", "combat", "treasure", "shrine",
                 "shop", "gambling", "blacksmith", "fountain", "omen"]

    chosen = []
    for kind in kind_want:
        if len(chosen) >= desired:
            break
        for room in pool:
            if room.get("kind") == kind and room not in chosen:
                chosen.append(room)
                break
        else:
            # no exact match — grab any unchosen room
            for room in pool:
                if room not in chosen:
                    chosen.append(room)
                    break

    # assign slots
    spawn_room = None
    stairs_room = None
    for i, room in enumerate(chosen[:desired]):
        if i >= len(slot_list):
            break
        col, row = slot_list[i]
        key = (col, row)
        if key in used_slots:
            continue
        used_slots.add(key)

        # origin in tiles, clamped so the room fits inside the level
        max_x = level_w - int(room.get("w", 8))
        max_y = level_h - int(room.get("h", 8))
        x = col * cell + 2 + (0 if i != 0 else 0)
        y = row * cell + 2 + (0 if i != 0 else 0)
        x = max(0, min(max_x, x))
        y = max(0, min(max_y, y))
        room_d = dict(room)
        room_d["x"] = x
        room_d["y"] = y
        room_d["center"] = (x + int(room.get("w", 8)) // 2,
                            y + int(room.get("h", 8)) // 2)
        rooms.append(room_d)
        if room.get("kind") == "entrance" and spawn_room is None:
            spawn_room = room_d
        if room.get("kind") == "boss":
            stairs_room = room_d

    if spawn_room is None and rooms:
        spawn_room = rooms[0]
        spawn_room["kind"] = "entrance"
    if stairs_room is None and len(rooms) > 1:
        stairs_room = rooms[-1]

    # props: place each room's declared props at deterministic positions inside it
    props = []
    for room in rooms:
        prop_list = list(room.get("props", []))
        if not prop_list:
            continue
        rw = int(room.get("w", 8))
        rh = int(room.get("h", 8))
        rx = int(room.get("x", 0))
        ry = int(room.get("y", 0))
        for j, prop_name in enumerate(prop_list):
            px = rx + 2 + (j * 3) % (rw - 3)
            py = ry + 2 + (j * 5) % (rh - 3)
            props.append({"tx": px, "ty": py, "sprite": prop_name})

    return rooms, props, spawn_room, stairs_room


def _place_cracked_walls(tiles, rooms, level_w, level_h, rng):
    """Place CRACKED_WALL tiles adjacent to some rooms (not entrance/boss).

    Returns a dict mapping (tx, ty) -> room_id for each cracked wall placed.
    """
    cracked = {}
    for room in rooms:
        kind = room.get("kind", "")
        if kind in ("entrance", "boss", "secret"):
            continue
        rx = int(room.get("x", 0))
        ry = int(room.get("y", 0))
        rw = int(room.get("w", 8))
        rh = int(room.get("h", 8))
        # Place 1-3 cracked walls on the perimeter of the room
        count = 1 + rng.randint(0, 2)
        placed = 0
        attempts = 0
        while placed < count and attempts < 50:
            attempts += 1
            # Pick a random wall tile adjacent to the room
            side = rng.choice(["top", "bottom", "left", "right"])
            if side == "top":
                tx = rx + rng.randint(0, max(0, rw - 1))
                ty = ry - 1
            elif side == "bottom":
                tx = rx + rng.randint(0, max(0, rw - 1))
                ty = ry + rh
            elif side == "left":
                tx = rx - 1
                ty = ry + rng.randint(0, max(0, rh - 1))
            else:
                tx = rx + rw
                ty = ry + rng.randint(0, max(0, rh - 1))
            if not (0 <= tx < level_w and 0 <= ty < level_h):
                continue
            if tiles[tx][ty] != WALL:
                continue
            # Check it's adjacent to a floor tile of this room
            adjacent_to_floor = False
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = tx + dx, ty + dy
                if 0 <= nx < level_w and 0 <= ny < level_h:
                    if tiles[nx][ny] == FLOOR:
                        adjacent_to_floor = True
                        break
            if not adjacent_to_floor:
                continue
            tiles[tx][ty] = CRACKED_WALL
            cracked[(tx, ty)] = room.get("id", "")
            placed += 1
    return cracked


def _place_hidden_doors(tiles, rooms, level_w, level_h, rng):
    """Place HIDDEN_DOOR tiles adjacent to cracked walls.

    Hidden doors are the visible doorway representations that lead
    to secret rooms. They appear on the minimap when the player is
    adjacent to them.

    Returns a dict mapping (tx, ty) -> room_id for each hidden door.
    """
    hidden = {}
    for room in rooms:
        kind = room.get("kind", "")
        if kind not in ("secret",):
            continue
        rid = room.get("id", "")
        sx = int(room.get("x", 0))
        sy = int(room.get("y", 0))
        sw = int(room.get("w", 8))
        sh = int(room.get("h", 8))
        # Place hidden doors on the perimeter walls of the secret room
        # that face outward (toward the crack path)
        for tx in range(sx, min(level_w, sx + sw)):
            for ty in [sy - 1, sy + sh]:
                if 0 <= tx < level_w and 0 <= ty < level_h:
                    if tiles[tx][ty] == WALL:
                        if (0 <= tx - 1 < level_w and tiles[tx - 1][ty] == FLOOR) or \
                           (0 <= tx + 1 < level_w and tiles[tx + 1][ty] == FLOOR) or \
                           (0 <= ty - 1 >= 0 and tiles[tx][ty - 1] == FLOOR) or \
                           (0 <= ty + 1 < level_h and tiles[tx][ty + 1] == FLOOR):
                            tiles[tx][ty] = HIDDEN_DOOR
                            hidden[(tx, ty)] = rid
        for ty in range(sy, min(level_h, sy + sh)):
            for tx in [sx - 1, sx + sw]:
                if 0 <= tx < level_w and 0 <= ty < level_h:
                    if tiles[tx][ty] == WALL:
                        if (0 <= ty - 1 >= 0 and tiles[tx][ty - 1] == FLOOR) or \
                           (0 <= ty + 1 < level_h and tiles[tx][ty + 1] == FLOOR) or \
                           (0 <= tx - 1 >= 0 and tiles[tx - 1][ty] == FLOOR) or \
                           (0 <= tx + 1 < level_w and tiles[tx + 1][ty] == FLOOR):
                            tiles[tx][ty] = HIDDEN_DOOR
                            hidden[(tx, ty)] = rid
    return hidden


def _place_secret_rooms(content, biome_id, level_w, level_h, cell, rng, rooms):
    """Add secret rooms to the room list. Secret rooms are placed near
    cracked wall positions and are initially not in the tile grid.

    Returns a list of secret room dicts to be added to rooms.
    """
    secret_rooms = []
    # Place 1-2 secret rooms per level
    if level_w < 56:
        return secret_rooms
    count = 1 + (1 if level_w > 64 and rng.chance(0.5) else 0)

    # Count pre-seeded secret rooms for this biome so generated ids
    # (biome_secret_N) never collide with shipped rooms.json entries.
    existing_secret_nums = []
    prefix = biome_id + "_secret_"
    for room in rooms:
        rid = room.get("id", "")
        if rid.startswith(prefix):
            try:
                existing_secret_nums.append(int(rid[len(prefix):]))
            except ValueError:
                pass
    # Also scan content.registry for pre-seeded rooms.json entries
    # that may not be in the procgen rooms list
    try:
        _rooms_path = Path(__file__).resolve().parents[2] / "game" / "data" / "rooms.json"
        if _rooms_path.exists():
            _rdata = json.loads(_rooms_path.read_text(encoding="utf-8"))
            for _room in _rdata.get("entries", []):
                if _room.get("biome") == biome_id and _room.get("kind") == "secret":
                    _rid = _room.get("id", "")
                    if _rid.startswith(prefix):
                        try:
                            existing_secret_nums.append(int(_rid[len(prefix):]))
                        except ValueError:
                            pass
    except Exception:
        pass
    next_num = max(existing_secret_nums) + 1 if existing_secret_nums else 1

    for i in range(count):
        # Find a spot near a cracked wall or in a corner
        secret_w = 6 + rng.randint(0, 4)
        secret_h = 6 + rng.randint(0, 4)
        # Try to place near a room but not overlapping
        placed = False
        for attempt in range(30):
            tx = rng.randint(1, max(1, level_w - secret_w - 1))
            ty = rng.randint(1, max(1, level_h - secret_h - 1))
            # Check it doesn't overlap with existing rooms
            overlap = False
            for room in rooms:
                rx = int(room.get("x", 0))
                ry = int(room.get("y", 0))
                rw = int(room.get("w", 8))
                rh = int(room.get("h", 8))
                if not (tx + secret_w < rx or tx > rx + rw or
                        ty + secret_h < ry or ty > ry + rh):
                    overlap = True
                    break
            if overlap:
                continue
            # Check it's not on the entrance/boss path
            secret_rooms.append({
                "id": "%s_secret_%d" % (biome_id, next_num + i),
                "biome": biome_id,
                "kind": "secret",
                "w": secret_w,
                "h": secret_h,
                "x": tx,
                "y": ty,
                "center": (tx + secret_w // 2, ty + secret_h // 2),
                "props": [],
                # A secret room holds treasure, not a fight - and it MUST carry this key:
                # spawn.populate_floor reads room["spawn_budget"] for every non-entrance
                # room, so a room built here without it crashed the run on any floor that
                # rolled a secret room. Content rooms all carry 0 here; match them.
                "spawn_budget": 0,
            })
            placed = True
            break
    return secret_rooms


def _carve_corridors(tiles, rooms, rng):
    """Carve L-shaped walkable corridors connecting consecutive rooms.

    rooms[0] is the entrance (spawn); the last combat/boss room gets the stairs.
    """
    if len(rooms) < 2:
        return
    for i in range(len(rooms) - 1):
        a = rooms[i]
        b = rooms[i + 1]
        ax = a["x"] + int(a.get("w", 8)) // 2
        ay = a["y"] + int(a.get("h", 8)) // 2
        bx = b["x"] + int(b.get("w", 8)) // 2
        by = b["y"] + int(b.get("h", 8)) // 2
        _carve_l(tiles, ax, ay, bx, by, rng)


def _carve_l(tiles, x0, y0, x1, y1, rng):
    """Carve an L-shaped corridor (horizontal-then-vertical or vice-versa)."""
    w = len(tiles)
    h = len(tiles[0]) if tiles else 0
    horizontal_first = rng.choice([True, False])
    if horizontal_first:
        _carve_line(tiles, w, h, x0, y0, x1, y0)
        _carve_line(tiles, w, h, x1, y0, x1, y1)
    else:
        _carve_line(tiles, w, h, x0, y0, x0, y1)
        _carve_line(tiles, w, h, x0, y1, x1, y1)


def _carve_line(tiles, w, h, x0, y0, x1, y1):
    """Carve walkable floor along a straight axis-aligned line."""
    dx = 1 if x1 >= x0 else -1
    dy = 1 if y1 >= y0 else -1
    x, y = x0, y0
    if x0 == x1:
        while y != y1:
            if 0 <= x < w and 0 <= y < h:
                tiles[x][y] = FLOOR
                _open_neighbours(tiles, w, h, x, y)
            y += dy
    else:
        while x != x1:
            if 0 <= x < w and 0 <= y < h:
                tiles[x][y] = FLOOR
                _open_neighbours(tiles, w, h, x, y)
            x += dx
    if 0 <= x1 < w and 0 <= y1 < h:
        tiles[x1][y1] = FLOOR
        _open_neighbours(tiles, w, h, x1, y1)


def _open_neighbours(tiles, w, h, x, y):
    """Floors the 4 neighbours so corridors connect cleanly."""
    for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
        if 0 <= nx < w and 0 <= ny < h and tiles[nx][ny] == WALL:
            tiles[nx][ny] = FLOOR


def _build_tile_grid(level_w, level_h, rooms, rng):
    """Start from all-wall, carve out each room's interior as floor.
    Place DOOR tiles at room boundaries where corridors do not connect.
    Place CRACKED_WALL tiles adjacent to rooms (not entrance/boss).
    """
    tiles = [[WALL for _ in range(level_h)] for _ in range(level_w)]
    for room in rooms:
        rx = int(room.get("x", 0))
        ry = int(room.get("y", 0))
        rw = int(room.get("w", 8))
        rh = int(room.get("h", 8))
        for tx in range(rx, min(level_w, rx + rw)):
            for ty in range(ry, min(level_h, ry + rh)):
                tiles[tx][ty] = FLOOR
    _place_doors(tiles, rooms, level_w, level_h)
    _place_cracked_walls(tiles, rooms, level_w, level_h, rng)
    _place_hidden_doors(tiles, rooms, level_w, level_h, rng)
    return tiles


def _place_doors(tiles, rooms, level_w, level_h):
    """Mark door tiles at room boundaries not connected by corridors."""
    corridor_tiles = set()
    room_floors = set()
    for room in rooms:
        rx = int(room.get("x", 0))
        ry = int(room.get("y", 0))
        rw = int(room.get("w", 8))
        rh = int(room.get("h", 8))
        for tx in range(rx, min(level_w, rx + rw)):
            for ty in range(ry, min(level_h, ry + rh)):
                room_floors.add((tx, ty))
    for tx in range(level_w):
        for ty in range(level_h):
            if tiles[tx][ty] == FLOOR and (tx, ty) not in room_floors:
                corridor_tiles.add((tx, ty))
    for room in rooms:
        kind = room.get("kind", "")
        if kind in ("entrance", "boss"):
            continue
        rx = int(room.get("x", 0))
        ry = int(room.get("y", 0))
        rw = int(room.get("w", 8))
        rh = int(room.get("h", 8))
        for tx in range(rx, min(level_w, rx + rw)):
            for ty in range(ry, min(level_h, ry + rh)):
                if tiles[tx][ty] != FLOOR:
                    continue
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = tx + dx, ty + dy
                    if 0 <= nx < level_w and 0 <= ny < level_h and tiles[nx][ny] == WALL:
                        has_corridor = False
                        for dx2, dy2 in ((dx * 2, 0), (-dx * 2, 0), (0, dy * 2), (0, -dy * 2)):
                            if (nx + dx2, ny + dy2) in corridor_tiles:
                                has_corridor = True
                                break
                        if not has_corridor:
                            for dx3, dy3 in ((dx * 2, 0), (-dx * 2, 0), (0, dy * 2), (0, -dy * 2)):
                                rx2, ry2 = nx + dx3, ny + dy3
                                if (rx2, ry2) in room_floors:
                                    if kind in ("combat", "treasure", "shrine", "shop", "gambling", "blacksmith", "fountain", "omen"):
                                        tiles[tx][ty] = DOOR
                                    break


def _place_stairs_and_spawn(tiles, rooms, spawn_room, stairs_room, level_w, level_h):
    """Pick concrete spawn/stairs tiles inside the designated rooms."""
    spawn_tile = _pick_in_room(tiles, spawn_room, level_w, level_h, prefer_edge=True)
    stairs_tile = _pick_in_room(tiles, stairs_room, level_w, level_h, prefer_far=True)
    if stairs_tile is None:
        stairs_tile = (level_w - 2, level_h - 2)
    return spawn_tile, stairs_tile


def _pick_in_room(tiles, room, level_w, level_h, prefer_edge=False, prefer_far=False):
    """Return a walkable (tx, ty) inside *room*."""
    rw = int(room.get("w", 8))
    rh = int(room.get("h", 8))
    rx = int(room.get("x", 0))
    ry = int(room.get("y", 0))
    cands = []
    for tx in range(rx, min(level_w, rx + rw)):
        for ty in range(ry, min(level_h, ry + rh)):
            if 0 <= tx < level_w and 0 <= ty < level_h and tiles[tx][ty] == FLOOR:
                cands.append((tx, ty))
    if not cands:
        return None
    if prefer_edge:
        # pick a tile near the room's outer edge, away from centre
        cx = rx + rw // 2
        cy = ry + rh // 2
        cands.sort(key=lambda p: abs(p[0] - cx) + abs(p[1] - cy), reverse=True)
    if prefer_far:
        # pick a tile far from spawn — deterministic tie-break by hash
        cands.sort(key=lambda p: (p[0] + p[1] * 7) % 13)
    return cands[0]


def _place_biome_tiles(tiles, level_w, level_h, biome_id, rng):
    """Overlay burning or water tiles for the active biome modifier.

    Ember floors get scattered burning tiles; drowned floors get water pools.
    The renderer and biome_mods read these via the level's *_biome_* attributes.
    """
    burning = set()
    water = set()
    if biome_id == "ember_warrens":
        # 3-6 burning tiles scattered across the level
        count = 3 + rng.randint(0, 3)
        for _ in range(count):
            tx = rng.randint(2, max(3, level_w - 3))
            ty = rng.randint(2, max(3, level_h - 3))
            if 0 <= tx < level_w and 0 <= ty < level_h and tiles[tx][ty] == FLOOR:
                # don't place on top of the spawn area
                burning.add((tx, ty))
                tiles[tx][ty] = BURNING
    elif biome_id == "sunken_ossuary":
        # 3-6 caustic pools (2x2), more of them than the drowned vaults and smaller:
        # the biome's hazard is the water itself, not the dark.
        count = 3 + rng.randint(0, 3)
        for _ in range(count):
            tx = rng.randint(2, max(3, level_w - 4))
            ty = rng.randint(2, max(3, level_h - 4))
            for dx in range(2):
                for dy in range(2):
                    xx, yy = tx + dx, ty + dy
                    if 0 <= xx < level_w and 0 <= yy < level_h and tiles[xx][yy] == FLOOR:
                        water.add((xx, yy))
                        tiles[xx][yy] = WATER
    elif biome_id == "drowned_vaults":
        # 2-4 water pools (2x2 blocks)
        count = 2 + rng.randint(0, 2)
        for _ in range(count):
            tx = rng.randint(2, max(3, level_w - 4))
            ty = rng.randint(2, max(3, level_h - 4))
            for dx in range(2):
                for dy in range(2):
                    xx, yy = tx + dx, ty + dy
                    if 0 <= xx < level_w and 0 <= yy < level_h and tiles[xx][yy] == FLOOR:
                        water.add((xx, yy))
                        tiles[xx][yy] = WATER
    return burning, water


def _fallback_rooms(biome_id):
    """Minimal room set when content.rooms_for returns nothing."""
    return [
        {"id": "fallback_entrance", "biome": biome_id, "kind": "entrance",
         "w": 10, "h": 8, "spawn_budget": 0, "props": []},
        {"id": "fallback_combat", "biome": biome_id, "kind": "combat",
         "w": 12, "h": 10, "spawn_budget": 5, "props": []},
        {"id": "fallback_combat2", "biome": biome_id, "kind": "combat",
         "w": 14, "h": 12, "spawn_budget": 6, "props": []},
        {"id": "fallback_treasure", "biome": biome_id, "kind": "treasure",
         "w": 9, "h": 8, "spawn_budget": 2, "props": []},
        {"id": "fallback_shrine", "biome": biome_id, "kind": "shrine",
         "w": 8, "h": 8, "spawn_budget": 1, "props": []},
        {"id": "fallback_shop", "biome": biome_id, "kind": "shop",
         "w": 7, "h": 7, "spawn_budget": 0, "props": []},
        {"id": "fallback_gambling", "biome": biome_id, "kind": "gambling",
         "w": 8, "h": 7, "spawn_budget": 0, "props": ["prop_coffer", "prop_gold_pile"]},
        {"id": "fallback_blacksmith", "biome": biome_id, "kind": "blacksmith",
         "w": 9, "h": 8, "spawn_budget": 0, "props": ["prop_anvil", "prop_hammer"]},
        {"id": "fallback_fountain", "biome": biome_id, "kind": "fountain",
         "w": 7, "h": 7, "spawn_budget": 0, "props": ["prop_fountain"]},
        {"id": "fallback_omen", "biome": biome_id, "kind": "omen",
         "w": 7, "h": 7, "spawn_budget": 0, "props": ["prop_eye"]},
        {"id": "fallback_boss", "biome": biome_id, "kind": "boss",
         "w": 18, "h": 14, "spawn_budget": 1, "props": []},
        {"id": "fallback_secret", "biome": biome_id, "kind": "secret",
         "w": 6, "h": 6, "spawn_budget": 0, "props": [], "secret_wall": "north"},
    ]


# --------------------------------------------------------------------------- Room
class Room:
    """A placed room: content dict plus pixel origin, computed centre, and
    a per-room fog-of-war flag for the minimap.

    Provides both attribute access (``room.x``, ``room.kind``) and dict-style
    access (``room["kind"]``) so that existing consumers that use either
    convention keep working.
    """

    __slots__ = ("_data", "_revealed")

    def __init__(self, data, revealed=True):
        self._data = dict(data)
        self._revealed = revealed

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        try:
            return self._data[name]
        except KeyError:
            raise AttributeError(name)

    def __setattr__(self, name, value):
        if name in ("_data", "_revealed"):
            super().__setattr__(name, value)
        else:
            self._data[name] = value

    def __getitem__(self, key):
        return self._data[key]

    def __contains__(self, key):
        return key in self._data

    def get(self, key, default=None):
        return self._data.get(key, default)

    @property
    def center(self):
        cx = int(self._data.get("x", 0)) + int(self._data.get("w", 8)) // 2
        cy = int(self._data.get("y", 0)) + int(self._data.get("h", 8)) // 2
        return (cx, cy)

    @property
    def revealed(self):
        return self._revealed

    @revealed.setter
    def revealed(self, value):
        self._revealed = bool(value)


def _room_from_data(data, **extra):
    d = dict(data)
    d.update(extra)
    return Room(d)


# --------------------------------------------------------------------------- Level
class Level:
    """A single floor's tile grid, rooms, props and navigation helpers."""

    __slots__ = ("w", "h", "tiles", "rooms", "props", "spawn_tile", "stairs_tile",
                 "stairs_room", "_revealed", "_burning", "_water", "_rng",
                 "_cracked_walls", "_secret_rooms", "_hidden_doors")

    def __init__(self, w, h, tiles, rooms, props, spawn_tile, stairs_tile,
                 stairs_room, burning, water, rng, cracked_walls=None,
                 secret_rooms=None, hidden_doors=None):
        self.w = w
        self.h = h
        self.tiles = tiles
        self.rooms = rooms
        self.props = props
        self.spawn_tile = spawn_tile
        self.stairs_tile = stairs_tile
        self.stairs_room = stairs_room
        self._revealed = [[False for _ in range(h)] for _ in range(w)]
        self._burning = burning
        self._water = water
        self._rng = rng
        self._cracked_walls = cracked_walls or {}
        self._secret_rooms = secret_rooms or []
        self._hidden_doors = hidden_doors or {}

    @property
    def cracked_walls(self):
        """Return the dict of cracked wall positions -> room_id."""
        return self._cracked_walls

    @property
    def secret_rooms(self):
        """Return the list of secret room dicts."""
        return self._secret_rooms

    def room_at(self, tx, ty):
        """Return the Room object at tile (tx, ty), or None."""
        for room in self.rooms:
            rx = int(room.get("x", 0))
            ry = int(room.get("y", 0))
            rw = int(room.get("w", 8))
            rh = int(room.get("h", 8))
            if rx <= tx < rx + rw and ry <= ty < ry + rh:
                return room
        return None

    @property
    def hidden_doors(self):
        """Return the dict of hidden door positions -> room_id."""
        return self._hidden_doors

    def reveal_around(self, px, py, radius=8):
        """Reveal tiles around a world pixel for fog-of-war."""
        tx = int(px // TILE)
        ty = int(py // TILE)
        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                if dx * dx + dy * dy > radius * radius:
                    continue
                xx, yy = tx + dx, ty + dy
                if 0 <= xx < self.w and 0 <= yy < self.h:
                    self._revealed[xx][yy] = True

    def walkable(self, tx, ty):
        """Is (tx, ty) a non-wall tile inside the level?"""
        if not self.in_bounds(tx, ty):
            return False
        return self.tiles[tx][ty] != WALL

    def walkable_px(self, x, y):
        """Is the pixel (x, y) on a non-wall tile?"""
        return self.walkable(int(x // TILE), int(y // TILE))

    def blocked_px(self, x, y, radius=0):
        """Is the pixel (x, y) blocked by a wall (or out of bounds)?"""
        tx = int(x // TILE)
        ty = int(y // TILE)
        if not self.in_bounds(tx, ty):
            return True
        if self.tiles[tx][ty] == WALL:
            return True
        # also block if any corner of the entity's radius hits a wall
        if radius > 0:
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    nx, ny = tx + dx, ty + dy
                    if 0 <= nx < self.w and 0 <= ny < self.h and self.tiles[nx][ny] == WALL:
                        # entity corner check
                        px = x + dx * radius
                        py = y + dy * radius
                        if int(px // TILE) == nx and int(py // TILE) == ny:
                            return True
        return False

    def in_bounds(self, tx, ty):
        return 0 <= tx < self.w and 0 <= ty < self.h

    def line_walkable(self, x0, y0, x1, y1):
        """Bresenham check: can a line of sight travel between two world pixels?"""
        tx0, ty0 = int(x0 // TILE), int(y0 // TILE)
        tx1, ty1 = int(x1 // TILE), int(y1 // TILE)
        dx = abs(tx1 - tx0)
        dy = abs(ty1 - ty0)
        sx = 1 if tx0 < tx1 else -1
        sy = 1 if ty0 < ty1 else -1
        err = dx - dy
        x, y = tx0, ty0
        while True:
            if not self.walkable(x, y):
                return False
            if x == tx1 and y == ty1:
                break
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x += sx
            if e2 < dx:
                err += dx
                y += sy
        return True

    def bfs(self, start, cap=20000):
        """Set of reachable walkable tiles from *start* (tx, ty)."""
        if not self.in_bounds(*start) or not self.walkable(*start):
            return set()
        visited = {start}
        queue = [start]
        head = 0
        while head < len(queue) and len(visited) < cap:
            cx, cy = queue[head]
            head += 1
            for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                if self.in_bounds(nx, ny) and self.walkable(nx, ny) and (nx, ny) not in visited:
                    visited.add((nx, ny))
                    queue.append((nx, ny))
        return visited

    def bfs_path(self, start, goal, cap=12000):
        """Shortest path (list of (tx,ty)) from *start* to *goal*, or None."""
        if not self.in_bounds(*start) or not self.in_bounds(*goal):
            return None
        if start == goal:
            return [start]
        came = {start: None}
        queue = [start]
        head = 0
        found = False
        while head < len(queue) and len(came) < cap:
            cx, cy = queue[head]
            head += 1
            if (cx, cy) == goal:
                found = True
                break
            for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                if self.in_bounds(nx, ny) and self.walkable(nx, ny) and (nx, ny) not in came:
                    came[(nx, ny)] = (cx, cy)
                    queue.append((nx, ny))
        if not found:
            return None
        path = []
        cur = goal
        while cur is not None:
            path.append(cur)
            cur = came[cur]
        path.reverse()
        return path

    def spawn_tile_in(self, room, rng, avoid=(0, 0), margin=2):
        """Pick a walkable tile inside *room* at least *margin* tiles from *avoid*."""
        rw = int(room.get("w", 8))
        rh = int(room.get("h", 8))
        rx = int(room.get("x", 0))
        ry = int(room.get("y", 0))
        cands = []
        for tx in range(rx + margin, min(self.w, rx + rw - margin)):
            for ty in range(ry + margin, min(self.h, ry + rh - margin)):
                if self.walkable(tx, ty):
                    cands.append((tx, ty))
        if not cands:
            for tx in range(rx, min(self.w, rx + rw)):
                for ty in range(ry, min(self.h, ry + rh)):
                    if self.walkable(tx, ty):
                        cands.append((tx, ty))
        if not cands:
            return avoid
        # prefer tiles far from avoid
        def score(p):
            ax, ay = avoid
            return (p[0] - ax) ** 2 + (p[1] - ay) ** 2
        cands.sort(key=score, reverse=True)
        # deterministic pick from the top candidates
        top = cands[:max(1, len(cands) // 3)]
        return rng.choice(top)


def _place_quest_props(rooms, biome_id, rng):
    """Place biome-specific quest interactables (flood gates, bone altar).

    Returns a list of props with a ``quest_id`` field so the world can trigger
    the matching quest objective when the player interacts adjacent to them.
    """
    if biome_id == "drowned_vaults":
        ids = ["flood_gate_1", "flood_gate_2", "flood_gate_3"]
        sprite = "prop_pillar_drowned"
    elif biome_id == "sunken_ossuary":
        ids = ["bone_altar"]
        sprite = "prop_altar"
    else:
        return []

    candidates = [r for r in rooms
                  if r.get("kind") not in ("entrance", "boss", "secret")]
    if not candidates:
        return []
    rng.shuffle(candidates)
    quest_props = []
    for i, qid in enumerate(ids):
        room = candidates[i % len(candidates)]
        rx = int(room.get("x", 0))
        ry = int(room.get("y", 0))
        rw = int(room.get("w", 8))
        rh = int(room.get("h", 8))
        tx = rx + 2 + (i * 3) % max(1, rw - 3)
        ty = ry + 2 + (i * 5) % max(1, rh - 3)
        quest_props.append({"tx": tx, "ty": ty, "sprite": sprite, "quest_id": qid})
    return quest_props


# --------------------------------------------------------------------------- generate
def generate(content, floor_rng, floor, biome_id, world_profile=None):
    """Build a ``Level`` for *floor* in *biome_id*, deterministic from *floor_rng*.

    ``content`` is a ``game.systems.data.Content`` instance.
    ``world_profile`` is the player save dict (may be None); currently unused
    for layout but accepted so the call site in world.py stays stable.
    """
    level_w, level_h = _level_extents(floor, biome_id, content, floor_rng)
    cell = _grid_cell_for(floor)

    rooms, props, spawn_room, stairs_room = _place_rooms(
        content, biome_id, level_w, level_h, cell, floor_rng)

    # Place biome-specific quest interactables (flood gates, bone altar)
    props.extend(_place_quest_props(rooms, biome_id, floor_rng))

    tiles = _build_tile_grid(level_w, level_h, rooms, floor_rng)
    _carve_corridors(tiles, rooms, floor_rng)

    burning, water = _place_biome_tiles(tiles, level_w, level_h, biome_id, floor_rng)

    # Place cracked walls adjacent to rooms
    cracked_walls = _place_cracked_walls(tiles, rooms, level_w, level_h, floor_rng)

    # Place secret rooms (not yet carved into tiles)
    secret_rooms = _place_secret_rooms(content, biome_id, level_w, level_h, cell, floor_rng, rooms)
    rooms.extend(secret_rooms)

    spawn_tile, stairs_tile = _place_stairs_and_spawn(
        tiles, rooms, spawn_room, stairs_room, level_w, level_h)

    # stamp the stairs tile value
    if stairs_tile:
        sx, sy = stairs_tile
        if 0 <= sx < level_w and 0 <= sy < level_h:
            tiles[sx][sy] = STAIRS

    # Wrap room dicts in Room objects so attribute-style consumers
    # (minimap: room.x, room.kind, room.revealed) work alongside the
    # dict-style consumers (_carve_corridors, _build_tile_grid) that
    # already ran above on the raw dicts.
    room_objs = [_room_from_data(r) for r in rooms]
    if spawn_room is not None:
        si = rooms.index(spawn_room)
        spawn_room = room_objs[si]
    if stairs_room is not None:
        ti = rooms.index(stairs_room)
        stairs_room = room_objs[ti]
    # Place hidden doors (adjacent to secret rooms, on the tile grid)
    hidden_doors = _place_hidden_doors(tiles, room_objs, level_w, level_h, floor_rng)
    # Mark secret rooms as not revealed
    for room in room_objs:
        if room.get("kind") == "secret":
            room._revealed = False

    return Level(level_w, level_h, tiles, room_objs, props,
                 spawn_tile, stairs_tile, stairs_room,
                 burning, water, floor_rng, cracked_walls, secret_rooms,
                 hidden_doors)


# --------------------------------------------------------------------------- helpers for consumers that reference procgen constants
# (the renderer and biome_mods import these by name)
__all__ = ["FLOOR", "WALL", "STAIRS", "BURNING", "WATER", "DOOR", "DOOR_OPEN",
           "CRACKED_WALL", "HIDDEN_DOOR", "generate", "Level"]
