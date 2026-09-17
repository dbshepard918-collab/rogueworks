"""Dialogue system for NPC conversations in the HQ."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "game" / "data"


class DialogueLine:
    def __init__(self, speaker: str, text: str, options: list = None):
        self.speaker = speaker
        self.text = text
        self.options = options or []


class DialogueTree:
    """A simple dialogue tree for an NPC."""

    def __init__(self, npc_id: str, lines: list[dict]):
        self.npc_id = npc_id
        self.lines = lines
        self.current = 0
        self.finished = False

    def current_line(self) -> Optional[dict]:
        if self.current < len(self.lines):
            return self.lines[self.current]
        return None

    def advance(self):
        self.current += 1
        if self.current >= len(self.lines):
            self.finished = True

    def choose(self, index: int):
        """Choose an option and advance."""
        self.advance()


class DialogueSystem:
    """Manages active dialogue with NPCs."""

    def __init__(self):
        self.active: Optional[DialogueTree] = None
        self.npc_name = ""
        self.npc_sprite = ""

    def start(self, npc: dict):
        """Start a dialogue with an NPC."""
        dialogue_id = npc.get("dialogue", "")
        lines = self._load_dialogue(dialogue_id)
        self.active = DialogueTree(npc["id"], lines)
        self.npc_name = npc.get("name", "")
        self.npc_sprite = npc.get("sprite", "")

    def _load_dialogue(self, dialogue_id: str) -> list[dict]:
        """Load dialogue lines from file, or generate default."""
        dp = DATA_DIR / "dialogue" / f"{dialogue_id}.json"
        if dp.exists():
            with open(dp, encoding="utf-8") as f:
                return json.load(f).get("lines", [])
        # Default dialogue
        return [
            {"speaker": "npc", "text": "Welcome, traveler."},
            {"speaker": "npc", "text": "The Depths are growing. Be careful down there."},
        ]

    def is_active(self) -> bool:
        return self.active is not None and not self.active.finished

    def update(self, choice: int = -1):
        if self.active:
            if choice >= 0:
                self.active.choose(choice)
            else:
                self.active.advance()

    def close(self):
        self.active = None
