"""HQ system: NPCs, rooms, and interactions for the headquarters hub."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"

_loaded = {}
TILE = 64

def _load(name):
    if name not in _loaded:
        with open(DATA_DIR / name, encoding="utf-8") as f:
            _loaded[name] = json.load(f)
    return _loaded[name]


def npcs():
    return _load("npcs.json")


def hq_rooms():
    return _load("hq_rooms.json")


def quests():
    return _load("quests.json")


def storyline():
    return _load("storyline.json")


def npc_by_id(nid: str) -> Optional[dict]:
    for n in npcs().get("npcs", []):
        if n.get("id") == nid:
            return n
    return None


def room_by_id(rid: str) -> Optional[dict]:
    for r in hq_rooms().get("rooms", []):
        if r.get("id") == rid:
            return r
    return None


def room_at(x: float, y: float) -> Optional[dict]:
    """Return the room at world pixel coordinates, or None."""
    tx, ty = x / TILE, y / TILE
    for r in hq_rooms().get("rooms", []):
        rx, ry = r.get("x", 0), r.get("y", 0)
        rw, rh = r.get("w", 8), r.get("h", 8)
        if rx <= tx < rx + rw and ry <= ty < ry + rh:
            return r
    return None


def npcs_in_room(rid: str) -> list:
    """Return NPC definitions for a given room id."""
    room = room_by_id(rid)
    if not room:
        return []
    result = []
    for nid in room.get("npcs", []):
        n = npc_by_id(nid)
        if n:
            result.append(n)
    return result


def quest_by_id(qid: str) -> Optional[dict]:
    for q in quests().get("quests", []):
        if q.get("id") == qid:
            return q
    return None


class NPCState:
    """Tracks interaction state for one NPC in the HQ."""
    def __init__(self, npc_def: dict):
        self.definition = npc_def
        self.talked = False
        self.dialogue_index = 0
        self.visible = True
        # Position in world tiles (center of room)
        room = room_by_id(npc_def.get("location", ""))
        if room:
            self.tx = room.get("x", 0) + room.get("w", 8) // 2
            self.ty = room.get("y", 0) + room.get("h", 8) // 2
        else:
            self.tx = 10
            self.ty = 10

    @property
    def x(self):
        return self.tx * 64

    @property
    def y(self):
        return self.ty * 64


class HQState:
    """Headquarters hub state: NPCs, player position, room layout."""
    def __init__(self):
        self.player_tx = 10  # Tile coords
        self.player_ty = 7
        self.npc_states: dict[str, NPCState] = {}
        self.active_room: Optional[str] = None
        self._init_npcs()

    def _init_npcs(self):
        for n in npcs().get("npcs", []):
            self.npc_states[n["id"]] = NPCState(n)

    def npc_at(self, tx: int, ty: int) -> Optional[NPCState]:
        for ns in self.npc_states.values():
            if ns.visible and ns.tx == tx and ns.ty == ty:
                return ns
        return None

    def update_room(self):
        room = room_at(self.player_tx * 64, self.player_ty * 64)
        if room:
            self.active_room = room.get("id")
        else:
            self.active_room = None

    def move_player(self, dx: int, dy: int):
        self.player_tx += dx
        self.player_ty += dy
        self.update_room()

    def interact(self) -> Optional[dict]:
        """Try to interact with an NPC in front of the player."""
        # Check all 4 adjacent tiles + current tile
        for dx, dy in [(0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)]:
            ns = self.npc_at(self.player_tx + dx, self.player_ty + dy)
            if ns:
                ns.talked = True
                return ns.definition
        return None
