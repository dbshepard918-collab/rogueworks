"""Settings: persistent accessibility and control options.

P2.6 — Controls & accessibility.  All settings persist in save.json under the
``settings`` key.  Loading tolerates a missing or partial settings dict (every
field has a default) and never raises.

P4.5 — categorized settings: video, audio, controls, accessibility sections.
"""

import json
from pathlib import Path

import pygame

# ---- defaults ---------------------------------------------------------------

DEFAULT_SETTINGS = {
    "shake_enabled": True,
    "damage_numbers": True,
    "reduced_flashing": False,
    "font_scale": 1,
    "hold_to_attack": False,
    "colourblind_mode": "off",
    "gamepad_enabled": False,
    "key_map": {},
    "resolution": "1280x720",
    "fullscreen": False,
    "vsync": True,
    "fps_cap": 60,
}

# Resolution modes: string -> (width, height, scale_factor)
# Render base is always 1280x720.
RESOLUTION_MODES = {
    "1280x720":  (1280, 720, 1),
    "1920x1080": (1920, 1080, 1),   # letterboxing (1.5x isn't integer)
    "2560x1440": (2560, 1440, 2),   # pixel-perfect 2x scale
}

# Default key bindings (action -> pygame key constant)
DEFAULT_KEY_MAP = {
    "move_up": pygame.K_w,
    "move_down": pygame.K_s,
    "move_left": pygame.K_a,
    "move_right": pygame.K_d,
    "attack": pygame.K_SPACE,
    "dash": pygame.K_LSHIFT,
    "ranged": pygame.K_j,
    "interact": pygame.K_e,
    "inventory": pygame.K_TAB,
    "pause": pygame.K_ESCAPE,
}

# Human-readable labels for the settings menu
SETTING_LABELS = {
    "shake_enabled": "Screen Shake",
    "damage_numbers": "Damage Numbers",
    "reduced_flashing": "Reduced Flashing",
    "font_scale": "Font Scale",
    "hold_to_attack": "Hold to Attack",
    "colourblind_mode": "Colourblind Palette",
    "gamepad_enabled": "Gamepad Support",
    "resolution": "Resolution",
    "fullscreen": "Fullscreen",
    "vsync": "VSync",
    "fps_cap": "FPS Cap",
}

COLOURBLIND_MODES = ("off", "protan", "deutan", "tritan")

# Action labels for the remap screen
ACTION_LABELS = {
    "move_up": "Move Up",
    "move_down": "Move Down",
    "move_left": "Move Left",
    "move_right": "Move Right",
    "attack": "Attack / Bolt",
    "dash": "Dash",
    "ranged": "Ranged Bolt",
    "interact": "Interact",
    "inventory": "Inventory",
    "pause": "Pause",
}

# Colourblind-safe rarity colours (tuned for distinguishability)
COLOURBLIND_RARITY = {
    "off": {
        1: (138, 132, 150),   # common — grey
        2: (121, 176, 74),    # uncommon — green
        3: (79, 209, 200),    # rare — teal
        4: (180, 120, 220),   # legendary — purple
        5: (232, 178, 60),    # mythic — gold
    },
    "protan": {
        1: (138, 132, 150),
        2: (79, 209, 200),    # uncommon — teal (not green)
        3: (100, 180, 255),   # rare — blue
        4: (255, 200, 50),    # legendary — yellow
        5: (232, 178, 60),
    },
    "deutan": {
        1: (138, 132, 150),
        2: (79, 209, 200),
        3: (100, 180, 255),
        4: (255, 200, 50),
        5: (232, 178, 60),
    },
    "tritan": {
        1: (138, 132, 150),
        2: (121, 176, 74),
        3: (200, 100, 200),    # rare — magenta (not teal)
        4: (255, 200, 50),
        5: (232, 178, 60),
    },
}


def rarity_colour(tier, mode="off"):
    """Return a (r, g, b) colour for a rarity *tier* (1-5) under *mode*."""
    palette = COLOURBLIND_RARITY.get(mode, COLOURBLIND_RARITY["off"])
    return palette.get(tier, palette[1])


def normalize(raw):
    """Normalize a raw settings dict from save.json into a full dict with defaults."""
    if not isinstance(raw, dict):
        return dict(DEFAULT_SETTINGS)
    out = dict(DEFAULT_SETTINGS)
    for key in DEFAULT_SETTINGS:
        if key in raw:
            val = raw[key]
            if key == "key_map":
                if isinstance(val, dict):
                    out["key_map"] = {str(k): int(v) for k, v in val.items()
                                      if isinstance(v, (int, float))}
            elif key == "font_scale":
                try:
                    out["font_scale"] = 1 if int(val) <= 1 else 2
                except (TypeError, ValueError):
                    out["font_scale"] = 1
            elif key == "colourblind_mode":
                if str(val) in COLOURBLIND_MODES:
                    out["colourblind_mode"] = str(val)
            elif key == "resolution":
                if str(val) in RESOLUTION_MODES:
                    out["resolution"] = str(val)
            elif key == "fps_cap":
                try:
                    out["fps_cap"] = max(1, int(val))
                except (TypeError, ValueError):
                    out["fps_cap"] = 60
            elif isinstance(DEFAULT_SETTINGS[key], bool):
                out[key] = bool(val)
            else:
                out[key] = val
    return out


def default():
    return dict(DEFAULT_SETTINGS)
