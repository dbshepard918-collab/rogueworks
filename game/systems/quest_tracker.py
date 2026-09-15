"""Quest tracker: active quests, objectives, completion state."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"


class QuestTracker:
    """Tracks the player's active and completed quests."""

    def __init__(self, profile: dict = None):
        self.profile = profile or {}
        self.active: list[str] = []
        self.completed: list[str] = []
        self.objective_progress: dict[str, dict] = {}
        self._load()

    def _load(self):
        quests_data = {}
        qp = DATA_DIR / "quests.json"
        if qp.exists():
            with open(qp, encoding="utf-8") as f:
                quests_data = json.load(f)
        self.quests = {q["id"]: q for q in quests_data.get("quests", [])}

    def accept(self, quest_id: str) -> bool:
        if quest_id in self.quests and quest_id not in self.active and quest_id not in self.completed:
            self.active.append(quest_id)
            self.objective_progress[quest_id] = {}
            return True
        return False

    def complete(self, quest_id: str) -> dict | None:
        if quest_id in self.active:
            self.active.remove(quest_id)
            self.completed.append(quest_id)
            return self.quests.get(quest_id, {}).get("rewards", {})
        return None

    def update_objective(self, quest_id: str, objective_type: str, target: str):
        if quest_id not in self.objective_progress:
            self.objective_progress[quest_id] = {}
        key = f"{objective_type}:{target}"
        self.objective_progress[quest_id][key] = self.objective_progress[quest_id].get(key, 0) + 1

    def is_complete(self, quest_id: str) -> bool:
        return quest_id in self.completed

    def is_active(self, quest_id: str) -> bool:
        return quest_id in self.active

    def get_quest(self, quest_id: str) -> dict | None:
        return self.quests.get(quest_id)

    def check_floor_reached(self, floor: int):
        for qid in self.active:
            q = self.quests.get(qid, {})
            for obj in q.get("objectives", []):
                if obj.get("type") == "reach_floor" and obj.get("target") == floor:
                    self.update_objective(qid, "reach_floor", str(floor))

    def active_quests_with_progress(self) -> list[dict]:
        result = []
        for qid in self.active:
            q = self.quests.get(qid)
            if not q:
                continue
            progress = self.objective_progress.get(qid, {})
            objectives = []
            for obj in q.get("objectives", []):
                key = f"{obj.get('type')}:{obj.get('target')}"
                count = progress.get(key, 0)
                if obj.get("type") == "reach_floor":
                    objectives.append({"label": obj.get("label", ""), "done": count > 0})
                elif obj.get("type") == "kill_boss":
                    objectives.append({"label": obj.get("label", ""), "done": count > 0})
                elif obj.get("type") == "collect_item":
                    objectives.append({"label": obj.get("label", ""), "done": count > 0})
                elif obj.get("type") == "interact":
                    objectives.append({"label": obj.get("label", ""), "done": count > 0})
            result.append({"id": qid, "title": q.get("title", ""), "objectives": objectives})
        return result
