"""Gamepad input: pygame.jockey Joystick wrapper implementing InputState surface.

P2.6 — gamepad_enabled setting.  Falls back gracefully when no joystick is
present (returns InputState.idle() every tick).  The same InputState surface
as KeyboardInput so scenes can swap between them transparently.
"""

import pygame
from .input import InputState

# Dead-zone threshold for analog sticks
STICK_DEADZONE = 0.65

# Button mapping: action -> (button_index, trigger_threshold)
# Xbox/PS layout; pygame assigns indices by detection order.
GAMEPAD_BUTTONS = {
    "attack": 0,      # A (Xbox) / Cross (PS)
    "dash": 1,        # B (Xbox) / Circle (PS) — or RT button
    "ranged": 2,      # X (Xbox) / Square (PS)
    "interact": 3,    # Y (Xbox) / Triangle (PS)
}

# Axis mapping: (axis_index, negative_direction, positive_direction)
# left stick: axis 0 = X (left/right), axis 1 = Y (up/down)
# triggers: axis 2 = left trigger, axis 5 = right trigger
GAMEPAD_AXES = {
    "move_left":  (0, -1, 1),
    "move_right": (0, 1, -1),
    "move_up":    (1, -1, 1),
    "move_down":  (1, 1, -1),
}


class GamepadInput:
    """Reads a connected gamepad and returns InputState per tick.

    Implements the same ``sample(world, keys)`` interface as KeyboardInput.
    Falls back gracefully if no joystick is present: always returns
    ``InputState.idle()`` so the game remains perfectly playable with keyboard
    alone when settings["gamepad_enabled"] is False or no hardware exists.
    """

    def __init__(self):
        self._joystick = None
        self._num_buttons = 0
        self._num_axes = 0
        self._last_move = (0.0, 0.0)
        self._init_joystick()

    def _init_joystick(self):
        """Try to open the first available joystick."""
        try:
            if pygame.joystick.get_count() > 0:
                self._joystick = pygame.joystick.Joystick(0)
                self._joystick.init()
                self._num_buttons = self._joystick.get_numbuttons()
                self._num_axes = self._joystick.get_numaxes()
        except pygame.error:
            self._joystick = None
            self._num_buttons = 0
            self._num_axes = 0

    def _axis_value(self, axis_idx):
        """Return the normalised axis value with dead-zone applied."""
        if self._joystick is None or axis_idx >= self._num_axes:
            return 0.0
        val = self._joystick.get_axis(axis_idx)
        if abs(val) < STICK_DEADZONE:
            return 0.0
        return val

    def _button_pressed(self, button_idx):
        """Return True if the given button is pressed."""
        if self._joystick is None or button_idx >= self._num_buttons:
            return False
        return self._joystick.get_button(button_idx) == 1

    def sample(self, world=None, keys=None):
        """Return an InputState from the gamepad.

        Args:
            world: optional world reference (unused here, kept for interface).
            keys: unused; kept for interface compatibility.

        Returns:
            InputState with move vector and actions set.
        """
        if self._joystick is None:
            return InputState.idle()

        # Left stick movement
        mx = self._axis_value(0)
        my = self._axis_value(1)
        if mx and my:
            inv = 0.7071067811865476
            mx *= inv
            my *= inv

        actions = set()

        # Face buttons (A/X = attack, B/RT = dash, X/A = ranged, Y = interact)
        if self._button_pressed(GAMEPAD_BUTTONS.get("attack", 0)):
            actions.add("attack")
        if self._button_pressed(GAMEPAD_BUTTONS.get("dash", 1)):
            actions.add("dash")
        if self._button_pressed(GAMEPAD_BUTTONS.get("ranged", 2)):
            actions.add("ranged")
        if self._button_pressed(GAMEPAD_BUTTONS.get("interact", 3)):
            actions.add("interact")

        # Right trigger for dash alternative
        if self._axis_value(2) > 0.5:
            actions.add("dash")

        # Add attack and ranged based on face buttons too
        # X/A mapped to ranged (button 2), A/X mapped to attack (button 0)
        # In the task spec: A/X to attack, B/RT to dash, X/A to ranged, Y to interact
        # Button 0 (A) = attack, Button 2 (X) = ranged (handled above)

        return InputState((mx, my), actions)

    @property
    def available(self):
        """True if a joystick was successfully opened."""
        return self._joystick is not None
