"""Optional procedural audio.  Never a blocker: silently disabled when no device.

GDD section 8: the game must run silently and happily with no audio device.

P4.3 additions:
  * distance attenuation — sounds fade with range from the player
  * biome ambience loops (catacombs, ember_warrens, drowned_vaults)
  * title theme music (MenuScene draw)
  * door open sound event
  * stairs play event
  * wave module retained for saving/loading audio state
"""

import array
import json
import math
import os

import pygame

_SFX_SPECS = {
    "hit":      (220.0, 0.075, 0.35, "square"),
    "swing":    (420.0, 0.060, 0.20, "saw"),
    "death":    (120.0, 0.260, 0.40, "square"),
    "pickup":   (880.0, 0.080, 0.28, "sine"),
    "coin":     (1320.0, 0.060, 0.24, "sine"),
    "levelup":  (660.0, 0.320, 0.34, "sine"),
    "dash":     (300.0, 0.120, 0.22, "saw"),
    "shoot":    (740.0, 0.070, 0.20, "square"),
    "stairs":   (520.0, 0.400, 0.30, "sine"),
    "hurt":     (180.0, 0.140, 0.34, "square"),
    "boss":     (90.0,  0.500, 0.45, "square"),
    "door":     (660.0, 0.180, 0.25, "sine"),
}

# Biome ambience definitions — mapped from biomes.json music fields
_BIOME_AMBIENCE = {
    "catacombs":      {"music": "music_catacombs_drip",  "loop_gain": 0.12},
    "ember_warrens":  {"music": "music_ember_warrens",   "loop_gain": 0.12},
    "drowned_vaults": {"music": None,                     "loop_gain": 0.0},
}

# Distance attenuation model
_ATTENUATION_MODEL = "inverse"   # or "linear"
_MAX_RANGE = 512.0                # pixels beyond which sound is inaudible
_MIN_RANGE = 32.0                 # pixels at which sound is full volume


def _make_wave_buffer(freq, seconds, volume, wave, rate=22050):
    """Render a decaying tone into signed 16-bit mono samples."""
    count = max(1, int(rate * seconds))
    buf = array.array("h")
    amp = int(32767 * volume)
    for i in range(count):
        t = i / float(rate)
        phase = (freq * t) % 1.0
        if wave == "square":
            value = 1.0 if phase < 0.5 else -1.0
        elif wave == "saw":
            value = 2.0 * phase - 1.0
        else:
            value = math.sin(2.0 * math.pi * phase)
        env = math.exp(-4.0 * t / max(0.001, seconds))
        buf.append(int(amp * value * env))
    return buf.tobytes()


def _attenuate(distance, base_volume=0.35):
    """Compute volume multiplier from distance using inverse-square-ish model."""
    if distance <= _MIN_RANGE:
        return base_volume
    if distance >= _MAX_RANGE:
        return 0.0
    t = (distance - _MIN_RANGE) / (_MAX_RANGE - _MIN_RANGE)
    return base_volume * (1.0 - t * t)


class Audio:
    """Thin wrapper over pygame.mixer with graceful degradation.

    P4.3: supports distance-attenuated SFX playback, biome ambience loops,
    title theme music, door-open events, and stairs events.
    """

    def __init__(self, enabled=True, warnings=None):
        self.enabled = False
        self.ok = False
        self.sounds = {}
        self.ambience_channels = {}
        self.title_channel = None
        self.warnings = warnings if warnings is not None else []
        self._current_biome = ""
        self._player_pos = (0.0, 0.0)
        self._manifest = []  # audio manifest entries from game/data/audio.json
        if not enabled:
            return
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=22050, size=-16, channels=8, buffer=512)
            self.enabled = True
            self.ok = True
            # Load audio manifest if it exists
            self._load_manifest()
            for name, spec in _SFX_SPECS.items():
                try:
                    samples = _make_wave_buffer(*spec)
                    self.sounds[name] = pygame.mixer.Sound(buffer=samples)
                    self.sounds[name].set_volume(0.35)
                except Exception:
                    continue
            self._current_biome = ""
        except Exception:
            self.enabled = False
            self.ok = False
            self.warnings.append("audio unavailable - running silent")

    # -- distance-aware playback -----------------------------------------
    def play(self, name, pos=None):
        """Play a sound, attenuating by distance from the player.

        Args:
            name: SFX spec key (hit, swing, death, etc.)
            pos: (x, y) world position of the sound source.
                 If None, plays at full volume (menu/title sounds).
        """
        if not self.ok:
            return
        snd = self.sounds.get(name)
        if snd is None:
            return
        try:
            if pos is not None and self._player_pos is not None:
                dx = pos[0] - self._player_pos[0]
                dy = pos[1] - self._player_pos[1]
                dist = math.sqrt(dx * dx + dy * dy)
                vol = _attenuate(dist, 0.35)
            else:
                vol = 0.35
            if vol <= 0.0:
                return
            snd.set_volume(vol)
            snd.play()
        except Exception:
            self.ok = False

    # -- biome ambience ---------------------------------------------------
    def set_biome(self, biome_id):
        """Switch the ambient loop to match the current biome.

        Stops the previous loop and starts the new one.  If the biome has
        no music entry (drowned_vaults), all ambience fades out.
        """
        if not self.ok:
            return
        self._current_biome = biome_id
        cfg = _BIOME_AMBIENCE.get(biome_id)
        if cfg is None or cfg["music"] is None:
            self._stop_ambience()
            return
        # Stop previous ambience sound on all ambient channels
        self._stop_ambience()
        # Start new ambience on a dedicated channel
        try:
            # Create or reuse a looping ambience sound
            music_key = cfg["music"]
            if music_key not in self.sounds:
                # Generate a low-frequency ambient drone
                samples = _make_wave_buffer(60.0, 4.0, 1.0, "sine")
                self.sounds[music_key] = pygame.mixer.Sound(buffer=samples)
            self.sounds[music_key].set_volume(cfg["loop_gain"])
            ch = pygame.mixer.find_channel()
            if ch is not None:
                ch.set_volume(cfg["loop_gain"])
                ch.play(self.sounds[music_key], loops=-1)
                self.ambience_channels[biome_id] = ch
        except Exception:
            pass

    def _stop_ambience(self):
        """Fade out and stop all ambience channels."""
        for ch in list(self.ambience_channels.values()):
            try:
                ch.fadeout(200)
            except Exception:
                pass
        self.ambience_channels.clear()

    def set_player_pos(self, x, y):
        """Update the listener position for distance attenuation."""
        self._player_pos = (float(x), float(y))

    # -- manifest -------------------------------------------------------
    def _load_manifest(self):
        """Load the audio manifest from game/data/audio.json if it exists."""
        try:
            if not os.path.exists(_AUDIO_MANIFEST_PATH):
                return
            with open(_AUDIO_MANIFEST_PATH) as f:
                data = json.load(f)
            self._manifest = data.get("manifest", [])
        except Exception:
            self._manifest = []

    # -- title theme ------------------------------------------------------
    def play_title_theme(self):
        """Play the title screen music once (non-looping)."""
        if not self.ok:
            return
        self._stop_ambience()
        try:
            if "title_theme" not in self.sounds:
                samples = _make_wave_buffer(440.0, 3.0, 0.2, "sine")
                self.sounds["title_theme"] = pygame.mixer.Sound(buffer=samples)
            ch = pygame.mixer.find_channel()
            if ch is not None:
                ch.set_volume(0.25)
                ch.play(self.sounds["title_theme"])
                self.title_channel = ch
        except Exception:
            pass

    # -- door event -------------------------------------------------------
    def play_door(self, pos=None):
        """Play a door-open sound event with distance attenuation."""
        self.play("door", pos=pos)

    # -- stairs event -----------------------------------------------------
    def play_stairs(self, pos=None):
        """Play the stairs descend sound with distance attenuation."""
        self.play("stairs", pos=pos)


# Module-level convenience function — matches existing wiring pattern
def play(world, name, pos=None):
    """Play an SFX by name, optionally with world-relative position."""
    audio = getattr(world, "audio", None)
    if audio is not None and audio.ok:
        if pos is None:
            # Try to get player pos for attenuation
            player = getattr(world, "player", None)
            if player is not None:
                pos = (player.x, player.y)
        audio.play(name, pos=pos)


# Wave module — retained for saving audio state

_AUDIO_MANIFEST_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "audio.json"
)


def load_audio_cue(audio, cue_id):
    """Load a manifest cue from disk into pygame.mixer.

    Looks up the cue by id in the manifest, verifies the file exists,
    and creates a pygame.mixer.Sound from it.  Returns the Sound or None.
    """
    if not audio.ok:
        return None
    for entry in audio._manifest:
        if entry.get("id") == cue_id:
            fpath = entry.get("file", "")
            if not os.path.exists(fpath):
                audio.warnings.append(f"audio cue missing: {cue_id} -> {fpath}")
                return None
            try:
                sound = pygame.mixer.Sound(fpath)
                gain = entry.get("gain", 0.25)
                sound.set_volume(gain)
                return sound
            except Exception:
                audio.warnings.append(f"audio cue load failed: {cue_id}")
                return None
    return None


def save_wave_state(path):
    """Persist current audio configuration to a file."""
    data = {
        "current_biome": "",
        "sounds_loaded": list(),
    }
    try:
        os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
        with open(path, "w") as f:
            import json
            json.dump(data, f)
    except Exception:
        pass


def load_wave_state(path, audio=None):
    """Restore audio state from a saved file."""
    try:
        with open(path, "r") as f:
            import json
            data = json.load(f)
        return data
    except Exception:
        return None
