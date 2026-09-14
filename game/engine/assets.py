"""Asset loading: palette, packed atlases, and procedural placeholder synthesis.

ART-PAUPER CONTRACT (docs/CONTRACTS.md section 5):
``Atlas.load(name)`` -> ``.frame(name) -> pygame.Surface``.  A missing atlas or a
missing frame NEVER raises: it returns a synthesized placeholder surface
(flat palette colour + 1-2 letter tag, 32x32) and appends a warning string to the
world's ``warnings`` list.  The whole game is playable on placeholders alone.
"""

import json
from pathlib import Path

import pygame

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ASSETS_DIR = PROJECT_ROOT / "assets"
ATLAS_DIR = ASSETS_DIR / "atlas"
PALETTE_PATH = ASSETS_DIR / "palette.json"

TILE = 32

# ---------------------------------------------------------------- palette ----
_FALLBACK_PALETTE = {
    "void": "#0b0a10", "ink": "#15131f", "stone_dark": "#242032", "stone": "#3a3450",
    "stone_light": "#575070", "bone": "#d9d2c5", "white": "#f6f2e8", "ash": "#8a8496",
    "slate": "#5d6272", "steel": "#93a0b4", "ember_dark": "#5c2018", "ember": "#a83c1c",
    "flame": "#e2711d", "gold": "#e8b23c", "gold_dark": "#9a6f1c", "blood_dark": "#4d1220",
    "blood": "#8c1f34", "flesh": "#c4635f", "venom_dark": "#1f3b2a", "venom": "#3f8f57",
    "moss": "#79b04a", "water_dark": "#10283c", "water": "#1f5f80", "arcane": "#7b4fd1",
    "arcane_light": "#b48cf0", "soul": "#4fd1c8", "magenta_key": "#ff00ff",
}

_palette_cache = None
_palette_warnings = []

# keyword -> palette colour name, checked in order against the frame name
_COLOUR_RULES = [
    ("wall", "stone"), ("rock", "stone_dark"), ("pillar", "stone_light"),
    ("floor", "stone_dark"), ("ground", "stone_dark"), ("carpet", "blood_dark"),
    ("door", "gold_dark"), ("stairs", "bone"), ("exit", "bone"),
    ("player", "steel"), ("keeper", "steel"), ("hero", "steel"),
    ("gold", "gold"), ("coin", "gold"), ("chest", "gold_dark"), ("key", "gold_dark"),
    ("essence", "soul"), ("soul", "soul"), ("shrine", "arcane_light"),
    ("health", "flesh"), ("heart", "flesh"), ("potion", "flesh"),
    ("arrow", "bone"), ("bolt", "bone"), ("projectile", "bone"), ("bullet", "bone"),
    ("fire", "flame"), ("ember", "ember"), ("flame", "flame"), ("burn", "flame"),
    ("lava", "ember"), ("ash", "ash"),
    ("water", "water"), ("tide", "water"), ("brine", "water"), ("drown", "water_dark"),
    ("poison", "venom"), ("venom", "venom"), ("plague", "moss"), ("slime", "moss"),
    ("bone", "bone"), ("skeleton", "bone"), ("skull", "bone"), ("wraith", "arcane"),
    ("ghost", "arcane"), ("spirit", "arcane"), ("imp", "flame"), ("demon", "ember"),
    ("spider", "venom_dark"), ("rat", "ash"), ("hound", "ember_dark"), ("wolf", "slate"),
    ("golem", "stone"), ("brute", "ember_dark"), ("knight", "steel"), ("witch", "arcane"),
    ("ghoul", "venom_dark"), ("lurker", "water_dark"), ("boss", "blood"), ("tyrant", "blood"),
    ("icon", "ash"), ("frame", "ink"), ("panel", "ink"), ("ui", "ink"),
]

_BOSS_TAG = "\u2020"

FONT_GLYPHS = {
    "A": ".#./#.#/###/#.#/#.#", "B": "##./#.#/##./#.#/##.", "C": ".##/#../#../#../.##",
    "D": "##./#.#/#.#/#.#/##.", "E": "###/#../##./#../###", "F": "###/#../##./#../#..",
    "G": ".##/#../#.#/#.#/.##", "H": "#.#/#.#/###/#.#/#.#", "I": "###/.#./.#./.#./###",
    "J": "..#/..#/..#/#.#/.#.", "K": "#.#/#.#/##./#.#/#.#", "L": "#../#../#../#../###",
    "M": "#.#/###/###/#.#/#.#", "N": "#.#/##./#.#/#.#/#.#", "O": ".#./#.#/#.#/#.#/.#.",
    "P": "##./#.#/##./#../#..", "Q": ".#./#.#/#.#/##./.##", "R": "##./#.#/##./#.#/#.#",
    "S": ".##/#../.#./..#/##.", "T": "###/.#./.#./.#./.#.", "U": "#.#/#.#/#.#/#.#/.#.",
    "V": "#.#/#.#/#.#/.#./.#.", "W": "#.#/#.#/###/###/#.#", "X": "#.#/#.#/.#./#.#/#.#",
    "Y": "#.#/#.#/.#./.#./.#.", "Z": "###/..#/.#./#../###",
    "0": "###/#.#/#.#/#.#/###", "1": ".#./##./.#./.#./###", "2": "###/..#/###/#../###",
    "3": "###/..#/.##/..#/###", "4": "#.#/#.#/###/..#/..#", "5": "###/#../###/..#/###",
    "6": "###/#../###/#.#/###", "7": "###/..#/.#./.#./.#.", "8": "###/#.#/###/#.#/###",
    "9": "###/#.#/###/..#/###",
    "_": ".../.../.../.../###", "-": ".../.../###/.../...", ".": ".../.../.../.../.#.",
    "!": ".#./.#./.#./.../.#.", ":": ".../.#./.../.#./...", "+": ".../.#./###/.#./...",
    "/": "..#/..#/.#./#../#..", "%": "#.#/..#/.#./#../#.#", " ": ".../.../.../.../...",
    '"': "#../#../.../..#/..#", '#': "###/#.#/###/#.#/###", '$': "###/#../###/..#/###",
    '&': ".##/#.#/#.#/##./#..", "'": "..#/..#/..#/..#/..#", '(': "..#/.#./#../.#./..#",
    ')': "#../.#./..#/.#./#..", '*': ".../.#./#.#/.#./...", ',': ".../.../.../.#./#..",
    ';': "..#/..#/..#/..#/.#.", '<': "#../#.#/.#./#.#/#..", '=': ".../###/.../###/...",
    '>': "..#/#.#/.#./#.#/..#", '?': "###/#.#/..#/.../.#.", '@': ".##/#.#/#.#/#.#/.##",
    '[': "###/#.#/#.#/#.#/###", '\\': "#../.#./.#./.#./..#", ']': "###/.#./.#./.#./###",
    '^': ".../.#./#.#/.../...", '`': ".../.#./.#./.../...", '{': ".#./#../#../#../.#.",
    '|': "..#/..#/..#/..#/..#", '}': ".#./..#/..#/..#/.#.", '~': ".../#.#/.../#.#/...",
}


def load_palette(warnings=None):
    """Return {name: (r, g, b)} from assets/palette.json, with a built-in fallback."""
    global _palette_cache
    if _palette_cache is not None:
        return _palette_cache
    colors = dict(_FALLBACK_PALETTE)
    try:
        with open(PALETTE_PATH, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
        found = raw.get("colors") if isinstance(raw, dict) else None
        if isinstance(found, dict) and found:
            for name, value in found.items():
                if isinstance(value, str) and value.startswith("#") and len(value) == 7:
                    colors[name] = value
        else:
            msg = "palette.json has no usable 'colors' object - using built-in palette"
            _palette_warnings.append(msg)
            if warnings is not None:
                warnings.append(msg)
    except (OSError, ValueError):
        msg = "assets/palette.json missing or unreadable - using built-in palette"
        _palette_warnings.append(msg)
        if warnings is not None:
            warnings.append(msg)

    parsed = {}
    for name, value in colors.items():
        try:
            parsed[name] = (int(value[1:3], 16), int(value[3:5], 16), int(value[5:7], 16))
        except (ValueError, IndexError):
            continue
    _palette_cache = parsed
    return parsed


def colour(name, default=(200, 200, 200)):
    return load_palette().get(name, default)


# ------------------------------------------------------------- bitmap font ----
class BitmapFont:
    """Tiny 3x5 pixel font.  No font files, no pygame.font dependency."""

    def __init__(self):
        self._cache = {}

    def glyph(self, ch, scale=1, colour=(255, 255, 255)):
        key = (ch, scale, colour)
        surf = self._cache.get(key)
        if surf is None:
            rows = FONT_GLYPHS.get(ch.upper(), FONT_GLYPHS[" "]).split("/")
            w = 3 * scale
            h = 5 * scale
            surf = pygame.Surface((w, h), pygame.SRCALPHA)
            for ry, row in enumerate(rows):
                for rx, cell in enumerate(row):
                    if cell == "#":
                        surf.fill(colour, pygame.Rect(rx * scale, ry * scale, scale, scale))
            self._cache[key] = surf
        return surf

    def render(self, text, scale=1, colour=(255, 255, 255), spacing=1):
        text = str(text)
        if not text:
            return pygame.Surface((0, 0), pygame.SRCALPHA)
        glyphs = [self.glyph(ch, scale, colour) for ch in text]
        width = sum(g.get_width() for g in glyphs) + spacing * scale * (len(glyphs) - 1)
        height = 5 * scale
        out = pygame.Surface((max(1, width), max(1, height)), pygame.SRCALPHA)
        x = 0
        for g in glyphs:
            out.blit(g, (x, 0))
            x += g.get_width() + spacing * scale
        return out

    def measure(self, text, scale=1, spacing=1):
        text = str(text)
        n = len(text)
        return (n * 3 * scale + max(0, n - 1) * spacing * scale, 5 * scale)


FONT = BitmapFont()


def draw_text(surface, text, pos, scale=1, colour=(246, 242, 232), shadow=True, spacing=1):
    """Blit bitmap text; returns the rect it occupied."""
    img = FONT.render(text, scale, colour, spacing)
    x, y = int(pos[0]), int(pos[1])
    if shadow:
        shadow_img = FONT.render(text, scale, (11, 10, 16), spacing)
        surface.blit(shadow_img, (x + scale, y + scale))
    surface.blit(img, (x, y))
    return pygame.Rect(x, y, img.get_width(), img.get_height())


def text_size(text, scale=1, spacing=1):
    return FONT.measure(text, scale, spacing)


# ---------------------------------------------------------------- atlas ------
def _tag_for(name):
    tokens = [t for t in str(name).split("_") if t]
    if not tokens:
        return "?"
    if len(tokens) == 1:
        return tokens[0][:2].upper()
    return (tokens[0][:1] + tokens[-1][:1]).upper()


def _colour_name_for(name):
    low = str(name).lower()
    for keyword, colour_name in _COLOUR_RULES:
        if keyword in low:
            return colour_name
    # deterministic fallback across the palette
    names = sorted(load_palette().keys())
    if not names:
        return None
    idx = sum(str(name).encode("utf-8")) % len(names)
    return names[idx]


def _luminance(rgb):
    return 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]


def make_placeholder(name, size=TILE):
    """Flat palette colour + 1-2 letter tag.  Always succeeds."""
    tag = _tag_for(name)
    colour_name = _colour_name_for(name)
    rgb = colour(colour_name, (93, 98, 114)) if colour_name else colour("slate")
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    surf.fill(rgb)
    # darker 1px border + corner notch so placeholders read as "missing art"
    edge = tuple(max(0, int(c * 0.55)) for c in rgb)
    surf.fill(edge, pygame.Rect(0, 0, size, 1))
    surf.fill(edge, pygame.Rect(0, size - 1, size, 1))
    surf.fill(edge, pygame.Rect(0, 0, 1, size))
    surf.fill(edge, pygame.Rect(size - 1, 0, 1, size))
    surf.fill(edge, pygame.Rect(size - 3, size - 3, 3, 3))
    ink = (11, 10, 16) if _luminance(rgb) > 140 else (246, 242, 232)
    scale = 2 if len(tag) <= 2 else 1
    img = FONT.render(tag, scale, ink)
    surf.blit(img, ((size - img.get_width()) // 2, (size - img.get_height()) // 2))
    return surf


class Atlas:
    """Packed atlas: ``assets/atlas/<name>.png`` + ``.json``."""

    _cache = {}
    _placeholder_cache = {}

    def __init__(self, name, image=None, frames=None, meta=None, missing_reason=None):
        self.name = name
        self.image = image
        self.frames = frames or {}
        self.meta = meta or {}
        self.missing_reason = missing_reason

    # -- loading ---------------------------------------------------------
    @classmethod
    def load(cls, name, warnings=None):
        key = str(name)
        if key in cls._cache:
            atlas = cls._cache[key]
            if atlas.missing_reason:
                _warn(warnings, "atlas:%s" % key,
                      "atlas '%s' missing (%s) - placeholders in use" % (key, atlas.missing_reason))
            return atlas

        json_path = ATLAS_DIR / ("%s.json" % key)
        atlas = None
        reason = None
        if not json_path.exists():
            reason = "no %s.json" % key
        else:
            try:
                with open(json_path, "r", encoding="utf-8") as fh:
                    raw = json.load(fh)
                image_rel = raw.get("image") or ("assets/atlas/%s.png" % key)
                image_path = PROJECT_ROOT / image_rel
                if not image_path.exists():
                    image_path = ATLAS_DIR / ("%s.png" % key)
                image = pygame.image.load(str(image_path))
                try:
                    image = image.convert_alpha()
                except pygame.error:
                    pass
                frames = {}
                for frame_name, rect in (raw.get("frames") or {}).items():
                    if isinstance(rect, (list, tuple)) and len(rect) == 4:
                        frames[frame_name] = tuple(int(v) for v in rect)
                atlas = cls(key, image=image, frames=frames, meta=raw.get("meta") or {}, missing_reason=None)
            except (OSError, ValueError, TypeError, pygame.error) as exc:
                reason = "unreadable atlas (%s)" % type(exc).__name__
        if atlas is None:
            atlas = cls(key, image=None, frames={}, meta={}, missing_reason=reason or "missing")
        cls._cache[key] = atlas
        if atlas.missing_reason:
            _warn(warnings, "atlas:%s" % key,
                  "atlas '%s' missing (%s) - placeholders in use" % (key, atlas.missing_reason))
        else:
            _warn(warnings, "atlas-ok:%s" % key,
                  "atlas '%s' loaded (%d frames)" % (key, len(atlas.frames)))
        return atlas

    # -- frame access ----------------------------------------------------
    def frame(self, name, warnings=None, size=TILE):
        """Return the Surface for a frame, or a synthesized placeholder.

        Resolution order: this atlas -> the merged multi-atlas registry (with
        loader aliases applied) -> synthesized placeholder surface.
        """
        name = str(name)
        rect = self.frames.get(name)
        if rect is not None and self.image is not None:
            try:
                return self.image.subsurface(pygame.Rect(rect)).copy()
            except (ValueError, pygame.error):
                _warn(warnings, "frame-rect:%s:%s" % (self.name, name),
                      "frame '%s' has an out-of-bounds rect - placeholder used" % name)
                return placeholder(name, size, warnings=None)
        if frame_bank():
            return find_frame(name, warnings=warnings, size=size)
        _warn(warnings, "frame-miss:%s:%s" % (self.name, name),
              "frame '%s' missing from atlas '%s' - placeholder used" % (name, self.name))
        return placeholder(name, size, warnings=None)

    def has(self, name):
        return str(name) in self.frames

    def frame_names(self):
        return sorted(self.frames.keys())


def placeholder(name, size=TILE, warnings=None):
    key = (str(name), size)
    surf = Atlas._placeholder_cache.get(key)
    if surf is None:
        surf = make_placeholder(name, size)
        Atlas._placeholder_cache[key] = surf
    if warnings is not None:
        _warn(warnings, "placeholder:%s" % key,
              "no art for '%s' - synthesized placeholder surface" % name)
    return surf


# ------------------------------------------------- manifest + aliases -------
_warned_keys = set()
_manifest_cache = None
_bank_cache = None


def _warn(warnings, key, message):
    """Append a warning at most once per key (runs render thousands of frames)."""
    if key in _warned_keys:
        return
    _warned_keys.add(key)
    if warnings is not None:
        warnings.append(message)


def load_manifest():
    """Loader aliases + atlas names.

    Reads, in order: assets/aliases.json (CONTRACTS 5 update), assets/atlas/aliases.json
    (where the packed set actually lives) and assets/art_manifest.json.  Never raises.
    """
    global _manifest_cache
    if _manifest_cache is not None:
        return _manifest_cache
    aliases = {}
    atlas_names = []
    for path in (ASSETS_DIR / "aliases.json", ATLAS_DIR / "aliases.json"):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
            found = raw.get("aliases") if isinstance(raw, dict) else None
            if isinstance(found, dict):
                aliases.update({str(k): str(v) for k, v in found.items()})
        except (OSError, ValueError):
            continue
    try:
        with open(ASSETS_DIR / "art_manifest.json", "r", encoding="utf-8") as fh:
            raw = json.load(fh)
        if isinstance(raw, dict):
            found = raw.get("aliases")
            if isinstance(found, dict):
                for key, value in found.items():
                    aliases.setdefault(str(key), str(value))
            for sheet in raw.get("sheets") or []:
                if isinstance(sheet, dict) and sheet.get("atlas"):
                    name = str(sheet["atlas"])
                    if name not in atlas_names:
                        atlas_names.append(name)
    except (OSError, ValueError):
        pass
    _manifest_cache = (aliases, atlas_names)
    return _manifest_cache


def resolve_alias(name):
    """Follow art_manifest aliases (bounded, cycle safe)."""
    aliases, _ = load_manifest()
    seen = set()
    current = str(name)
    for _ in range(6):
        if current in seen:
            break
        seen.add(current)
        nxt = aliases.get(current)
        if not nxt:
            break
        current = nxt
    return current


def frame_bank(warnings=None):
    """name -> (atlas_name, rect) across every atlas in assets/atlas/.

    Built once from whatever atlases the art agent has packed; an empty or
    absent atlas directory simply means everything falls back to placeholders.
    """
    global _bank_cache
    if _bank_cache is not None:
        return _bank_cache
    bank = {}
    _aliases, atlas_names = load_manifest()
    paths = []
    if ATLAS_DIR.exists():
        for path in sorted(ATLAS_DIR.glob("*.json")):
            if path.stem.startswith("_"):
                continue                      # pipeline test / scratch atlases
            paths.append(path)
    for name in atlas_names:
        candidate = ATLAS_DIR / ("%s.json" % name)
        if candidate.exists() and candidate not in paths:
            paths.append(candidate)
    loaded = 0
    for path in paths:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
            if not isinstance(raw, dict):
                continue
            frames = raw.get("frames") or {}
            if not isinstance(frames, dict) or not frames:
                continue
            image_rel = raw.get("image") or str(path.with_suffix(".png")).replace("\\", "/")
            image_path = PROJECT_ROOT / image_rel
            if not image_path.exists():
                continue
            for frame_name, rect in frames.items():
                if isinstance(rect, (list, tuple)) and len(rect) == 4:
                    bank[str(frame_name)] = (path.stem, tuple(int(v) for v in rect))
            loaded += 1
        except (OSError, ValueError, TypeError):
            continue
    _bank_cache = bank
    if warnings is not None and not bank:
        _warn(warnings, "bank:empty",
              "no packed atlases under assets/atlas/ - every frame is a placeholder")
    return bank


def find_frame(name, warnings=None, size=TILE):
    """Resolve a frame by canonical name (aliases applied), else placeholder.

    Never raises and never returns None.
    """
    wanted = str(name)
    resolved = resolve_alias(wanted)
    bank = frame_bank()
    for candidate in (resolved, wanted):
        entry = bank.get(candidate)
        if entry is not None:
            atlas_name, rect = entry
            atlas = Atlas.load(atlas_name, warnings=None)
            if atlas.image is not None:
                try:
                    return atlas.image.subsurface(pygame.Rect(rect)).copy()
                except (ValueError, pygame.error):
                    break
    _warn(warnings, "frame:%s" % wanted,
          "frame '%s' not in any atlas - placeholder surface used" % wanted)
    return placeholder(resolved, size, warnings=None)


def has_frame(name):
    """True when real art exists for this frame name (aliases applied)."""
    bank = frame_bank()
    if not bank:
        return False
    return resolve_alias(name) in bank or str(name) in bank


def clear_caches():
    Atlas._cache.clear()
    Atlas._placeholder_cache.clear()
    _warned_keys.clear()
    global _palette_cache, _manifest_cache, _bank_cache
    _palette_cache = None
    _manifest_cache = None
    _bank_cache = None


def tile_size():
    return TILE
