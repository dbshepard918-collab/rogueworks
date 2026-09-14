"""Profiler overlay: entity count, tick ms, draw calls, particle budget,
atlas memory at runtime. Hard caps so a 200-entity floor holds 60 FPS.

Toggle with F1 during a run (visible only then). Data exposed in
``world.profiler_summary`` for QA regression.
"""

import pygame
import time

from ..engine.assets import Atlas, draw_text, text_size, colour as _colour


# ── Hard caps ────────────────────────────────────────────────────────
MAX_ENTITIES = 200       # cap: 200 entities holds 60 FPS
TARGET_FPS = 60
TARGET_FRAME_MS = 1000.0 / TARGET_FPS   # ~16.67 ms

ATLAS_WARN_BYTES = 20 * 1024 * 1024   # 20 MB
ATLAS_CAP_BYTES = 40 * 1024 * 1024    # 40 MB

PARTICLE_WARN = 300
PARTICLE_CAP = 420   # ParticleSystem.MAX_PARTICLES


class Profiler:
    """Runtime performance profiler."""

    def __init__(self):
        self.enabled = False          # toggled by F1
        self.visible = False          # drawn on screen when True
        self.entity_count = 0
        self.tick_ms = 0.0
        self.draw_calls = 0
        self.particle_count = 0
        self.atlas_mem = 0
        self.fps_equiv = 0.0
        self._tick_ms_history = []
        self._history_len = 60
        self._caps_violations = []

    # ── tick timing ────────────────────────────────────────────────

    def tick_start(self):
        """Call just before world.step() to time the tick."""
        self._tick_start = time.perf_counter()

    def tick_end(self):
        """Call just after world.step() returns."""
        self.tick_ms = (time.perf_counter() - self._tick_start) * 1000.0
        self.fps_equiv = 1000.0 / self.tick_ms if self.tick_ms > 0 else 0.0
        self._tick_ms_history.append(self.tick_ms)
        if len(self._tick_ms_history) > self._history_len:
            self._tick_ms_history.pop(0)

    # ── counting ───────────────────────────────────────────────────

    def count_entities(self, world):
        self.entity_count = sum(1 for m in world.monsters if m.alive) \
            + sum(1 for p in world.projectiles if p.alive) \
            + sum(1 for p in world.pickups if p.alive and not p.collected) \
            + (1 if getattr(world, 'player', None) and world.player.alive else 0)

    def count_particles(self, world):
        total = 0
        if hasattr(world, 'particles'):
            total += len(world.particles.items)
            total += len(world.particles.sprites)
        if hasattr(world, 'damage_numbers'):
            total += len(world.damage_numbers.items)
        if hasattr(world, 'floating'):
            total += len(world.floating.items)
        self.particle_count = total

    def count_atlas_mem(self):
        total = 0
        for _name, atlas in Atlas._cache.items():
            if atlas.image is not None:
                try:
                    total += atlas.image.get_width() * atlas.image.get_height() * 4
                except (ValueError, pygame.error):
                    pass
        self.atlas_mem = total

    def count_draw_calls(self, world):
        """Count entries in world.render_list if available."""
        rl = getattr(world, 'render_list', None)
        self.draw_calls = len(rl) if rl is not None else 0

    # ── full tick cycle ────────────────────────────────────────────

    def tick(self, world):
        """Full update: count everything, check caps."""
        self.count_entities(world)
        self.count_particles(world)
        self.count_atlas_mem()
        self.count_draw_calls(world)
        self._caps_violations = self.check_caps(world)
        return self._caps_violations

    # ── caps ───────────────────────────────────────────────────────

    def check_caps(self, world):
        violations = []
        if self.entity_count > MAX_ENTITIES:
            violations.append(
                "entity_cap: %d > %d" % (self.entity_count, MAX_ENTITIES))
        if self.tick_ms > TARGET_FRAME_MS * 2:
            violations.append(
                "tick_ms: %.1f > %.1f" % (self.tick_ms, TARGET_FRAME_MS * 2))
        if self.particle_count > PARTICLE_CAP:
            violations.append(
                "particle_cap: %d > %d" % (self.particle_count, PARTICLE_CAP))
        if self.atlas_mem > ATLAS_CAP_BYTES:
            violations.append(
                "atlas_mem: %.1f MB > %.1f MB" % (
                    self.atlas_mem / (1024*1024), ATLAS_CAP_BYTES / (1024*1024)))
        return violations

    @property
    def tick_ms_smoothed(self):
        if not self._tick_ms_history:
            return self.tick_ms
        return sum(self._tick_ms_history) / len(self._tick_ms_history)

    def summary(self):
        return {
            "entity_count": self.entity_count,
            "entity_cap": MAX_ENTITIES,
            "tick_ms": round(self.tick_ms, 2),
            "tick_ms_smoothed": round(self.tick_ms_smoothed, 2),
            "draw_calls": self.draw_calls,
            "particle_count": self.particle_count,
            "particle_cap": PARTICLE_CAP,
            "atlas_mem_bytes": self.atlas_mem,
            "atlas_mem_mb": round(self.atlas_mem / (1024*1024), 1),
            "fps_equiv": round(self.fps_equiv, 1),
            "target_fps": TARGET_FPS,
            "caps_violations": self._caps_violations,
        }

    # ── rendering ──────────────────────────────────────────────────

    def draw(self, surface, world):
        """Draw profiler overlay in the bottom-left corner."""
        if not self.visible or not self.enabled:
            return

        pad = 8
        line_h = 14
        x = pad
        panel_w = 300
        num_rows = 7  # title + 6 metrics + violations
        panel_h = num_rows * line_h + 12
        y = surface.get_height() - pad - panel_h

        # Background panel
        panel = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
        panel.fill((11, 10, 16, 180))
        surface.blit(panel, (x, y))

        # Title
        draw_text(surface, "PROFILER  [F1 to close]", (x + pad, y + 2), 1,
                  colour=(232, 178, 60))

        # Separator
        pygame.draw.line(surface, (58, 52, 80),
                         (x + pad, y + 16), (x + panel_w - pad, y + 16), 1)

        # Metrics
        row = 0
        metrics = [
            ("entities",  "%d / %d" % (self.entity_count, MAX_ENTITIES)),
            ("tick ms",   "%.1f (avg %.1f)" % (self.tick_ms, self.tick_ms_smoothed)),
            ("draw calls", str(self.draw_calls)),
            ("particles", "%d / %d" % (self.particle_count, PARTICLE_CAP)),
            ("atlas mem", "%.1f MB" % (self.atlas_mem / (1024*1024))),
            ("fps equiv", "%.0f" % self.fps_equiv),
        ]
        for label, val in metrics:
            text = "%-12s %s" % (label, val)
            col = _colour("white")
            if label == "entities" and self.entity_count > MAX_ENTITIES * 0.9:
                col = (255, 200, 50) if self.entity_count > MAX_ENTITIES * 0.95 else (200, 200, 200)
            elif label == "tick ms" and self.tick_ms > TARGET_FRAME_MS:
                col = (255, 80, 60)
            elif label == "particles" and self.particle_count > PARTICLE_WARN:
                col = (255, 200, 50)
            elif label == "atlas mem" and self.atlas_mem > ATLAS_WARN_BYTES:
                col = (255, 80, 60)
            draw_text(surface, text, (x + pad, y + 22 + row * line_h), 1, colour=col)
            row += 1

        # Violations
        if self._caps_violations:
            vy = y + panel_h - pad - line_h - 2
            if vy < y + 16 + line_h:
                vy = y + 16 + line_h
            draw_text(surface, "CAPS:", (x + pad, vy), 1, colour=(255, 80, 60))
            for i, v in enumerate(self._caps_violations[:3]):
                draw_text(surface, "  " + v, (x + pad, vy + 12 + i * line_h), 1,
                          colour=(255, 120, 100))
