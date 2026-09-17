"""P3.4 Onboarding: first-run tutorial that teaches move/attack/dash/interact.

A TutorialSystem lives inside World and tracks the player's action attempts
within a session. Contextual prompts appear on the HUD only when the player
fails twice at the same action (repeated attempts without success).

The tutorial fires ONLY on the first floor for first-time players
(floor_transitions == 0 and no prior save data), so returning players
never see it.

Design decisions:
- Track per-action counters: move_attempts, attack_attempts, dash_attempts,
  interact_attempts. A "failure" is when the player presses the action but
  nothing useful happens (e.g. attack but no enemy in range, dash but no
  direction, etc.).
- Prompts render via the HUD's existing draw_text infrastructure.
- After 3 successful uses of an action, the tutorial for that action is
  considered complete and the prompt stops showing.
- The tutorial is session-scoped: it resets on floor transition.
"""
from __future__ import annotations


class TutorialSystem:
    """Tracks player action attempts and drives onboarding prompts."""

    # action_id -> label text shown to the player
    ACTION_LABELS = {
        "move": "Move (WASD)",
        "attack": "Attack (SPACE)",
        "ranged": "Ranged (J)",
        "dash": "Dash (SHIFT + direction)",
        "interact": "Interact (E)",
    }

    # How many failed attempts before the prompt appears
    FAIL_THRESHOLD = 2

    # How many successful uses to complete the tutorial for an action
    SUCCESS_THRESHOLD = 3

    def __init__(self):
        # action -> {attempts: int, failures: int, successes: int, shown: bool}
        self.actions: dict[str, dict] = {a: self._blank() for a in self.ACTION_LABELS}
        self._active_prompt: str | None = None
        self._prompt_timer = 0.0
        # True when the player has completed all tutorial actions
        self.completed = False
        # The floor where the tutorial started
        self.start_floor = 0

    @staticmethod
    def _blank() -> dict:
        return {"attempts": 0, "failures": 0, "successes": 0, "shown": False}

    def record_attempt(self, action: str) -> None:
        """Called when the player presses an action key."""
        if action not in self.actions:
            return
        self.actions[action]["attempts"] += 1

    def record_success(self, action: str) -> None:
        """Called when the action had a meaningful result."""
        if action not in self.actions:
            return
        d = self.actions[action]
        d["successes"] += 1
        d["failures"] = max(0, d["failures"] - 1)  # partial forgiveness

    def record_failure(self, action: str) -> None:
        """Called when the action had no useful result."""
        if action not in self.actions:
            return
        self.actions[action]["failures"] += 1

    def should_show_prompt(self, action: str) -> bool:
        """Return True if the onboarding prompt should appear for this action."""
        if action not in self.actions:
            return False
        d = self.actions[action]
        if d["successes"] >= self.SUCCESS_THRESHOLD:
            return False
        if d["failures"] >= self.FAIL_THRESHOLD and not d["shown"]:
            return True
        return False

    def get_active_prompt(self) -> str | None:
        """Return the label of the action to prompt, or None."""
        # Find the first action that needs help and hasn't been shown yet
        for action, d in self.actions.items():
            if self.should_show_prompt(action):
                d["shown"] = True
                self._active_prompt = action
                self._prompt_timer = 180.0  # ~3 seconds at 60fps
                return self.ACTION_LABELS[action]
        return None

    def update(self, dt: float) -> None:
        """Tick the prompt timer."""
        if self._prompt_timer > 0:
            self._prompt_timer -= dt
            if self._prompt_timer <= 0:
                self._active_prompt = None

    def check_complete(self) -> bool:
        """Check if all tutorial actions have been successfully demonstrated."""
        if self.completed:
            return True
        for action, d in self.actions.items():
            if d["successes"] < self.SUCCESS_THRESHOLD:
                return False
        self.completed = True
        return True

    def reset_for_floor(self, floor: int) -> None:
        """Reset per-floor (called at new_floor). Keeps totals across floors
        within the same run so the tutorial can span floors 1-2."""
        pass  # Totals persist within a run

    def active_prompt(self) -> str | None:
        """Return the label of the currently active prompt or None."""
        if self._prompt_timer > 0 and self._active_prompt:
            return self.ACTION_LABELS.get(self._active_prompt)
        return None
