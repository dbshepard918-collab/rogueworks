"""Quest tracker: active quests, objectives, completion state, and rewards.

Quests are meta-progression: they persist across runs in ``profile["quests"]``.
The tracker reads its state from the profile on construction and writes back on
every mutation, so a quest accepted in the HQ stays accepted into the next run
and objectives tick forward during the run itself (see ``World`` hooks).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"

# Objective types understood by the tracker. Each maps to a check_* method.
_OBJECTIVE_TYPES = ("reach_floor", "kill_boss", "collect_item", "interact")


class QuestTracker:
    """Tracks the player's active and completed quests, persisted in the profile."""

    def __init__(self, profile: dict = None):
        self.profile = profile if profile is not None else {}
        self.active: list[str] = []
        self.completed: list[str] = []
        self.objective_progress: dict[str, dict] = {}
        self._load_quests()
        self._load_state()

    # -- loading ---------------------------------------------------------
    def _load_quests(self):
        quests_data = {}
        qp = DATA_DIR / "quests.json"
        if qp.exists():
            try:
                with open(qp, encoding="utf-8") as f:
                    quests_data = json.load(f)
            except (OSError, ValueError):
                quests_data = {}
        self.quests = {q["id"]: q for q in quests_data.get("quests", [])}

    def _load_state(self):
        state = self.profile.get("quests") or {}
        self.active = [q for q in state.get("active", []) if q in self.quests]
        self.completed = [q for q in state.get("completed", []) if q in self.quests]
        self.objective_progress = state.get("progress", {}) or {}

    def persist(self):
        """Write tracker state back into the profile (meta-progression)."""
        self.profile["quests"] = {
            "active": list(self.active),
            "completed": list(self.completed),
            "progress": self.objective_progress,
        }

    # -- lifecycle -------------------------------------------------------
    def accept(self, quest_id: str) -> bool:
        if quest_id in self.quests and quest_id not in self.active and quest_id not in self.completed:
            self.active.append(quest_id)
            self.objective_progress.setdefault(quest_id, {})
            self.persist()
            return True
        return False

    def accept_available(self):
        """Accept every quest whose prereqs are satisfied and not yet tracked."""
        accepted = []
        for qid, q in self.quests.items():
            if qid in self.active or qid in self.completed:
                continue
            prereqs = q.get("prereqs", []) or []
            if all(p in self.completed for p in prereqs):
                if self.accept(qid):
                    accepted.append(qid)
        return accepted

    def complete(self, quest_id: str) -> dict | None:
        if quest_id in self.active:
            self.active.remove(quest_id)
            self.completed.append(quest_id)
            self.persist()
            return self.quests.get(quest_id, {}).get("rewards", [])
        return None

    def is_complete(self, quest_id: str) -> bool:
        return quest_id in self.completed

    def is_active(self, quest_id: str) -> bool:
        return quest_id in self.active

    def get_quest(self, quest_id: str) -> dict | None:
        return self.quests.get(quest_id)

    # -- objective updates ----------------------------------------------
    def update_objective(self, quest_id: str, objective_type: str, target: str):
        if quest_id not in self.objective_progress:
            self.objective_progress[quest_id] = {}
        key = "%s:%s" % (objective_type, target)
        self.objective_progress[quest_id][key] = self.objective_progress[quest_id].get(key, 0) + 1

    def _objective_done(self, quest_id: str, objective: dict) -> bool:
        key = "%s:%s" % (objective.get("type"), objective.get("target"))
        return self.objective_progress.get(quest_id, {}).get(key, 0) > 0

    def _quest_objectives_complete(self, quest_id: str) -> bool:
        q = self.quests.get(quest_id)
        if not q:
            return False
        objectives = q.get("objectives", []) or []
        if not objectives:
            return False
        return all(self._objective_done(quest_id, obj) for obj in objectives)

    def check_floor_reached(self, floor: int):
        for qid in list(self.active):
            q = self.quests.get(qid, {})
            for obj in q.get("objectives", []):
                if obj.get("type") == "reach_floor" and obj.get("target") == floor:
                    self.update_objective(qid, "reach_floor", str(floor))

    def check_kill(self, monster_id: str):
        for qid in list(self.active):
            q = self.quests.get(qid, {})
            for obj in q.get("objectives", []):
                if obj.get("type") == "kill_boss" and obj.get("target") == monster_id:
                    self.update_objective(qid, "kill_boss", monster_id)

    def check_collect(self, item_id: str):
        for qid in list(self.active):
            q = self.quests.get(qid, {})
            for obj in q.get("objectives", []):
                if obj.get("type") == "collect_item" and obj.get("target") == item_id:
                    self.update_objective(qid, "collect_item", item_id)

    def check_interact(self, target: str):
        for qid in list(self.active):
            q = self.quests.get(qid, {})
            for obj in q.get("objectives", []):
                if obj.get("type") == "interact" and obj.get("target") == target:
                    self.update_objective(qid, "interact", target)

    # -- completion + rewards -------------------------------------------
    def process_completions(self) -> list[dict]:
        """Complete any quest with all objectives done; grant rewards to profile.

        Returns a list of ``{"id", "title", "rewards"}`` for newly-completed
        quests so the caller can surface a notice to the player.
        """
        completed = []
        for qid in list(self.active):
            if self._quest_objectives_complete(qid):
                rewards = self.complete(qid)
                if rewards is None:
                    rewards = []
                self._grant_rewards(qid, rewards)
                q = self.quests.get(qid, {})
                completed.append({"id": qid, "title": q.get("title", qid), "rewards": rewards})
        return completed

    def _grant_rewards(self, quest_id: str, rewards: list):
        """Apply quest rewards to the profile (meta-progression, permanent)."""
        for reward in rewards:
            rtype = reward.get("type")
            if rtype == "essence":
                try:
                    self.profile["essence"] = int(self.profile.get("essence", 0) or 0) + int(reward.get("amount", 0))
                except (TypeError, ValueError):
                    pass
            elif rtype == "unlock":
                target = reward.get("target")
                if target:
                    classes = self.profile.setdefault("unlocked_classes", ["lantern_keeper"])
                    if target not in classes:
                        classes.append(target)
            elif rtype in ("upgrade", "lore", "ending"):
                target = reward.get("target")
                if target:
                    self.profile.setdefault("unlocks", {})[target] = True

    # -- reporting -------------------------------------------------------
    def active_quests_with_progress(self) -> list[dict]:
        result = []
        for qid in self.active:
            q = self.quests.get(qid)
            if not q:
                continue
            progress = self.objective_progress.get(qid, {})
            objectives = []
            for obj in q.get("objectives", []):
                key = "%s:%s" % (obj.get("type"), obj.get("target"))
                count = progress.get(key, 0)
                objectives.append({"label": obj.get("label", ""), "done": count > 0})
            result.append({"id": qid, "title": q.get("title", ""), "objectives": objectives})
        return result
