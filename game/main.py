"""CLI entry point: ``python -m game.main [options]`` (docs/CONTRACTS.md section 3).

Exit code 0 iff the run completed without an unhandled exception.
"""

import argparse
import json
import os
import sys
import traceback
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from game.engine.scenes import Game                          # noqa: E402
from game.engine.scenes import RESOLUTION_MODES               # noqa: E402
from game.systems import meta as meta_sys                    # noqa: E402
from game.systems import save as save_sys                    # noqa: E402

RUNS_DIR = PROJECT_ROOT / "runs"
DEFAULT_SHOT_DIR = RUNS_DIR / "shots"


def build_parser():
    parser = argparse.ArgumentParser(prog="game.main", add_help=True,
                                     description="Depths of Vaelmoor")
    parser.add_argument("--seed", type=str, default="0",
                        help="run seed, or a range: 0..2 / 0..8..2 / 0,3,7 (default 0)")
    parser.add_argument("--daily", action="store_true",
                        help="daily seeded run (seed = YYYYMMDD from today's date)")
    parser.add_argument("--curses", type=str, default=None,
                        help="comma-separated curse ids to apply at run start")
    parser.add_argument("--endless", action="store_true",
                        help="endless mode: continue past floor 15 with escalating difficulty")
    parser.add_argument("--headless", action="store_true",
                        help="no window, SDL dummy driver (QA + CI path)")
    parser.add_argument("--turns", type=int, default=300,
                        help="headless: max simulation steps (default 300)")
    parser.add_argument("--script", type=str, default=None,
                        help="scripted-input JSON (see CONTRACTS.md 3.2)")
    parser.add_argument("--record", type=str, default=None,
                        help="record all inputs to a replay JSON file (P5.2)")
    parser.add_argument("--replay", type=str, default=None,
                        help="replay a recorded input JSON file deterministically (P5.2)")
    parser.add_argument("--shot", type=str, default=None,
                        help="render frames at those tick numbers to PNGs")
    parser.add_argument("--shot-dir", type=str, default=None,
                        help="directory for --shot output (default runs/shots)")
    parser.add_argument("--floor", type=int, default=1, help="start on floor N (debug)")
    parser.add_argument("--new-run", action="store_true", help="ignore save, start a fresh run")
    parser.add_argument("--log", type=str, default=None,
                        help="write the run summary JSON (default runs/playtest-<seed>.json)")
    parser.add_argument("--save", type=str, default=None, help="profile path (default save.json)")
    parser.add_argument("--frames", type=int, default=None,
                        help="windowed mode: stop after N frames (debug)")
    parser.add_argument("--resolution", type=str, default=None,
                        help="render resolution (1280x720, 1920x1080, 2560x1440)")
    parser.add_argument("--fullscreen", action="store_true",
                        help="fullscreen window")
    parser.add_argument("--vsync", action="store_true",
                        help="enable vsync")
    parser.add_argument("--fps", type=int, default=None,
                        help="FPS cap (windowed mode)")
    parser.add_argument("--data-dir", type=str, default=None,
                        help="override game/data/ content dir (for modding)")
    parser.add_argument("--mod-dir", type=str, default=None,
                        help="mod override folder layered on top of game/data/")
    return parser


def parse_shots(value):
    if not value:
        return []
    ticks = []
    for chunk in str(value).split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            ticks.append(int(chunk))
        except ValueError:
            continue
    return ticks


def parse_seeds(value):
    """Expand the ``--seed`` argument into the list of seeds to run.

    Accepts a single seed (``7``), an inclusive range (``0..2`` -> 0, 1, 2), a
    stepped range (``0..8..2`` -> 0, 2, 4, 6, 8) and comma-separated mixtures
    (``0..2,7``).  Documented gate commands are written as ``--seed 0..2``, so
    the CLI has to accept the shorthand verbatim: a documented command that
    cannot run is a documentation bug with no way to notice it.

    Raises ``ValueError`` on a malformed spec so argparse reports it.
    """
    if value is None:
        return [0]
    text = str(value).strip()
    if not text:
        return [0]
    seeds = []
    for chunk in text.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if ".." in chunk:
            parts = [p.strip() for p in chunk.split("..")]
            if len(parts) not in (2, 3) or not all(parts):
                raise ValueError("expected A..B or A..B..STEP, got %r" % chunk)
            try:
                start, stop = int(parts[0]), int(parts[1])
                step = int(parts[2]) if len(parts) == 3 else 1
            except ValueError:
                raise ValueError("range bounds must be integers, got %r" % chunk) from None
            if step <= 0:
                raise ValueError("range step must be > 0, got %r" % chunk)
            if stop < start:
                raise ValueError("range end must be >= start, got %r" % chunk)
            seeds.extend(range(start, stop + 1, step))
        else:
            try:
                seeds.append(int(chunk))
            except ValueError:
                raise ValueError("seeds must be integers or ranges, got %r" % chunk) from None
    if not seeds:
        raise ValueError("no seeds given")
    return seeds


def setup_sdl(headless):
    if headless:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    return headless


# Display resolution modes available to the player (P4.6)
DISPLAY_MODES = {
    "1280x720": (1280, 720),
    "1920x1080": (1920, 1080),
    "2560x1440": (2560, 1440),
}


def run_headless(args, profile, warnings):
    import pygame

    pygame.init()
    try:
        pygame.display.set_mode((1, 1))
    except pygame.error:
        pass

    # P2.6: apply settings from profile to the game
    settings = profile.get("settings", {}) if profile else {}
    # P4.6: apply CLI resolution overrides to profile settings
    if getattr(args, "resolution", None):
        settings["resolution"] = args.resolution
    if getattr(args, "fullscreen", False):
        settings["fullscreen"] = True
    if getattr(args, "vsync", False):
        settings["vsync"] = True
    if getattr(args, "fps", None):
        settings["fps_cap"] = args.fps
    game = Game(args, profile, warnings, headless=True, save_path=args.save)
    game.last_world_settings = settings
    # P5.2: set up replay or record mode
    if getattr(args, "replay", None):
        from game.engine.input import ReplayInput
        game.replay = ReplayInput.load(args.replay)

    if getattr(args, "record", None):
        game.record_path = args.record
        from game.engine.input import ReplayInput
        game.replay = ReplayInput()
        game.replay.start_recording()
    shots = parse_shots(args.shot)
    shot_dir = args.shot_dir or str(DEFAULT_SHOT_DIR)
    # P4.6: resolve render size from settings instead of hardcoded 1280x720
    resolution = settings.get("resolution", "1280x720")
    if resolution in RESOLUTION_MODES:
        render_size = RESOLUTION_MODES[resolution][:2]
    elif "x" in resolution:
        w, h = resolution.split("x")
        render_size = (int(w), int(h))
    else:
        render_size = (1280, 720)
    canvas = pygame.Surface(render_size)
    world = game.run_headless(turns=max(0, args.turns), shot_ticks=shots, shot_dir=shot_dir,
                              canvas=canvas)

    # bank meta progress (idempotent) and clear run state so the next headless
    # run reproduces exactly from the same seed
    meta_sys.apply_run_results(profile, world)
    meta_sys.clear_run(profile)
    save_sys.save_profile(profile, args.save)

    # P5.2: save recorded replay if --record was used
    if getattr(args, "record", None) and getattr(game, "replay", None) is not None:
        replay_states = game.replay.stop_recording()
        if replay_states:
            game.replay.save(args.record)
            print("  recorded %d input states to %s" % (len(replay_states), args.record))

    log_path = args.log or str(RUNS_DIR / ("playtest-%d.json" % args.seed))
    summary = world.summary()
    violations = summary["invariants"]["violations"]
    summary["ok"] = (not world.errors) and not violations
    try:
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "w", encoding="utf-8") as fh:
            json.dump(summary, fh, indent=2, sort_keys=True)
            fh.write("\n")
    except OSError as exc:
        world.errors.append("could not write %s (%s)" % (log_path, type(exc).__name__))
        summary["ok"] = False
        summary["errors"] = list(world.errors)

    report_run(world, summary, log_path, shot_dir, shots)
    pygame.quit()
    return 0


def report_run(world, summary, log_path, shot_dir, shots):
    counts = summary["world"]
    player = summary["player"]
    print("run summary  seed=%d  ticks=%d  floor=%d  biome=%s  state=%s"
          % (world.seed, world.tick, world.floor, world.biome_id, world.run_state))
    print("  level %dx%d  rooms=%d  entities=%d  monsters=%d  projectiles=%d  pickups=%d"
          % (counts["level_w"], counts["level_h"], counts["rooms"], counts["entities"],
             counts["monsters"], counts["projectiles"], counts["pickups"]))
    print("  player hp=%d/%d level=%d xp=%d gold=%d essence=%d kills=%d items=%s statuses=%s pos=%s"
          % (player["hp"], player["max_hp"], player["level"], player["xp"], player["gold"],
             player["essence"], player["kills"], player["items"], player["statuses"], player["pos"]))
    print("  metrics frames=%d ms_per_tick=%.3f fps_equiv=%d"
          % (summary["metrics"]["frames"], summary["metrics"]["ms_per_tick"],
             summary["metrics"]["fps_equiv"]))
    print("  ok=%s  errors=%s  violations=%s" % (summary["ok"], summary["errors"],
                                                 summary["invariants"]["violations"]))
    print("  warnings=%d (first: %s)" % (len(world.warnings),
                                         world.warnings[0] if world.warnings else "none"))
    print("  summary written: %s" % log_path)
    if shots:
        print("  shots requested at %s -> %s" % (shots, shot_dir))


def run_windowed(args, profile, warnings):
    import pygame

    pygame.init()
    pygame.display.set_caption("Depths of Vaelmoor")

    # Read display settings from profile
    settings = profile.get("settings", {}) if profile else {}
    # P4.6: apply CLI resolution overrides
    if getattr(args, "resolution", None):
        settings["resolution"] = args.resolution
    if getattr(args, "fullscreen", False):
        settings["fullscreen"] = True
    if getattr(args, "vsync", False):
        settings["vsync"] = True
    if getattr(args, "fps", None):
        settings["fps_cap"] = args.fps
    resolution = settings.get("resolution", "1280x720")
    fullscreen = settings.get("fullscreen", False)
    vsync = settings.get("vsync", False)
    fps_cap = settings.get("fps_cap", 60)

    # Resolve display size from DISPLAY_MODES or raw resolution string
    if resolution in DISPLAY_MODES:
        display_size = DISPLAY_MODES[resolution]
    elif "x" in resolution:
        w, h = resolution.split("x")
        display_size = (int(w), int(h))
    else:
        display_size = (1280, 720)

    # Build display flags
    flags = pygame.RESIZABLE
    if fullscreen:
        flags |= pygame.FULLSCREEN
    if vsync:
        flags |= pygame.HWSURFACE | pygame.DOUBLEBUF | pygame.RESIZABLE

    try:
        display_surface = pygame.display.set_mode(display_size, flags)
    except pygame.error as exc:
        print("display unavailable (%s) - falling back to headless" % exc)
        return run_headless(args, profile, warnings)

    # Pass display settings to Game
    game = Game(args, profile, warnings, headless=False, save_path=args.save)
    game.last_world_settings = settings
    game.display_surface = display_surface
    game.display_size = display_size
    game.fps_cap = fps_cap

    if args.script:
        game.start_run()            # scripted demo plays immediately
    elif profile.get("run") and not args.new_run:
        game.continue_run()
    else:
        game.show_menu()
    game.run_gui(max_frames=args.frames)
    pygame.quit()
    return 0


def run_once(args):
    """One run, with ``args.seed`` already resolved to a single int.

    The profile is re-read from disk for every run so that ``--seed 0..2``
    behaves exactly like three separate invocations: no run inherits another
    run's banked meta progression, which is what keeps the seeds deterministic
    and the documented gate command honest.
    """
    setup_sdl(args.headless)
    warnings = []
    profile, notes = save_sys.load_profile(args.save)
    for note in notes:
        warnings.append("save: %s" % note)
    if args.new_run:
        profile["run"] = None

    try:
        if args.headless:
            return run_headless(args, profile, warnings)
        return run_windowed(args, profile, warnings)
    except Exception:
        traceback.print_exc()
        return 1


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.new_run:
        args.__dict__.setdefault("_new_run", True)

    # P1.8: --daily overrides --seed with today's date as YYYYMMDD
    if getattr(args, "daily", False):
        import time
        args.seed = str(int(time.strftime("%Y%m%d")))

    # --seed accepts a single seed, a range (0..2) or a list (0,3,7)
    try:
        seeds = parse_seeds(args.seed)
    except ValueError as exc:
        parser.error("argument --seed: %s" % exc)

    # P1.8: --curses parses comma-separated curse ids into a list (once; the
    # loop below must not re-parse its own output)
    curses = [c.strip() for c in (args.curses or "").split(",") if c.strip()]

    if not args.headless and len(seeds) > 1:
        print("note: --seed ranges apply to --headless runs; using seed %d" % seeds[0])
        seeds = seeds[:1]

    rc = 0
    base_log = args.log
    for index, seed in enumerate(seeds):
        args.seed = seed
        args.curses = curses
        # one --log path cannot hold three runs: give each seed its own file
        if len(seeds) > 1 and base_log:
            path = Path(base_log)
            args.log = str(path.with_name("%s-seed%d%s" % (path.stem, seed, path.suffix)))
        else:
            args.log = base_log
        if len(seeds) > 1:
            print("=== seed %d  (%d/%d) ===" % (seed, index + 1, len(seeds)))
        rc |= run_once(args)
    return rc


if __name__ == "__main__":
    sys.exit(main())
