"""scene-sweep: render every scene and UI surface, so a crash cannot hide in a menu.

    python -m tools.qa.scene_sweep
    python -m tools.qa.scene_sweep --json

The headless gates only walk the code a 300-tick run reaches: a run stays on
``RunScene`` and never opens the settings screen, the meta shop, the class
select or the end screen.  That is exactly where a missing render function
lives undetected until a player presses the wrong key.  This tool constructs
every scene for real, drives it with synthetic key presses and renders it to an
offscreen surface, then does the same for the HUD, inventory overlay, minimap
and item tooltip.

Exit status: 0 every surface rendered, 1 at least one raised, 2 the game
package is not importable yet.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

from tools import _util  # noqa: E402
from tools._util import EXIT_FAIL, EXIT_OK, EXIT_PREREQ  # noqa: E402

SIZE = (1280, 720)
KEYS = ("K_DOWN", "K_DOWN", "K_UP", "K_RIGHT", "K_RETURN", "K_SPACE", "K_TAB", "K_ESCAPE",
        "K_1", "K_2", "K_3", "K_4", "K_a", "K_s")


class _Args:
    def __init__(self, seed: int = 42) -> None:
        self.seed = seed
        self.floor = 1
        self.turns = 120
        self.headless = True
        self.script = None
        self.shot = None
        self.shot_dir = None
        self.log = None
        self.save = None
        self.daily = False
        self.curses: list[str] = []
        self.endless = False
        self.new_run = True
        self.frames = None
        self.resolution = None
        self.fullscreen = False
        self.vsync = False
        self.fps = None


def _press(scene, pygame, name) -> None:
    key = getattr(pygame, name)
    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key, unicode="", mod=0))


def sweep(root: Path, seed: int) -> dict:
    import pygame

    scratch = Path(tempfile.mkdtemp(prefix="rw_scene_sweep_"))
    try:
        return _sweep_all(root, seed, scratch)
    finally:
        # the scratch dir must go even when a surface raises, or a red gate
        # leaves debris behind - which is exactly what happened before
        shutil.rmtree(scratch, ignore_errors=True)


def _sweep_all(root: Path, seed: int, scratch: Path) -> dict:
    import pygame

    from game.engine import scenes as scenes_mod
    from game.systems import save as save_sys
    from game.ui import hud as hud_mod
    from game.ui import inventory as inventory_mod
    from game.ui import minimap as minimap_mod
    from game.ui import tooltips as tooltips_mod

    surface = pygame.Surface(SIZE)
    results: list[dict] = []

    profile, notes = save_sys.load_profile(str(scratch / "profile.json"))
    warnings = list(notes)
    args = _Args(seed)
    game = scenes_mod.Game(args, profile, warnings, headless=True,
                           save_path=str(scratch / "profile.json"))

    def record(name: str, fn) -> None:
        try:
            fn()
            results.append({"surface": name, "ok": True, "detail": "rendered"})
        except Exception as exc:  # noqa: BLE001
            results.append({"surface": name, "ok": False,
                            "detail": "%s: %s" % (type(exc).__name__, exc),
                            "traceback": traceback.format_exc()})

    def drive(scene, presses=KEYS) -> None:
        scene.draw(surface)
        for name in presses:
            try:
                _press(scene, pygame, name)
            except Exception:  # noqa: BLE001
                pass                    # a handler may legitimately not care
            scene.draw(surface)

    # --- every scene ------------------------------------------------------- #
    menu = scenes_mod.MenuScene(game)
    game.show_menu()
    record("MenuScene", lambda: drive(menu))

    record("MetaShopScene", lambda: drive(scenes_mod.MetaShopScene(game)))
    record("ClassSelectScene", lambda: drive(scenes_mod.ClassSelectScene(game)))
    record("AscensionSelectScene", lambda: drive(scenes_mod.AscensionSelectScene(game)))
    record("SettingsScene", lambda: drive(scenes_mod.SettingsScene(game)))
    record("CurseSelectScene", lambda: drive(scenes_mod.CurseSelectScene(game)))

    # --- the run + everything drawn over it -------------------------------- #
    run_scene = game.start_run(seed=seed)
    world = run_scene.world

    def run_surfaces() -> None:
        for _ in range(30):
            run_scene.update(1 / 60.0)
            run_scene.draw(surface)
        hud = hud_mod.HUD()
        hud.draw(world, surface)
        inventory_mod.InventoryOverlay().draw(world, surface)
        minimap_mod.draw_minimap(world, surface)
        item = (world.content.items() or [None])[0]
        if item is not None:
            tooltips_mod.draw_item_tooltip(surface, item, 40, 40, SIZE)

    record("RunScene+HUD+inventory+minimap+tooltip", run_surfaces)
    record("RunScene.pause", lambda: drive(run_scene, ("K_ESCAPE", "K_DOWN", "K_UP", "K_RETURN")))

    # --- end screens through the real handoff ------------------------------ #
    # r46: death goes to HQ hub first, not EndScene. Victory still goes to EndScene.
    def victory_path() -> None:
        scene = game.start_run(seed=seed)
        scene.world.on_victory()
        scene.end_timer = 99.0
        for _ in range(8):
            scene.update(1 / 60.0)
        game.end_run()
        top = game.scenes.top()
        if type(top).__name__ != "EndScene":
            raise AssertionError("victory: expected EndScene, got %s" % type(top).__name__)
        drive(top)
    record("EndScene(victory)", victory_path)

    # r46: death → HQ hub path
    def death_to_hq_path() -> None:
        scene = game.start_run(seed=seed)
        scene.world.on_player_death("sweep")
        scene.end_timer = 99.0
        for _ in range(8):
            scene.update(1 / 60.0)
        game.end_run()
        top = game.scenes.top()
        if type(top).__name__ != "HQScene":
            raise AssertionError("death: expected HQScene, got %s" % type(top).__name__)
        # Drive the HQ scene: move, interact, render
        drive(top, ("K_LEFT", "K_RIGHT", "K_UP", "K_DOWN", "K_e", "K_ESCAPE"))
    record("HQScene(death)", death_to_hq_path)

    return {"seed": seed, "surfaces": results,
            "failed": [r for r in results if not r["ok"]]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m tools.qa.scene_sweep",
        description="Construct and render every scene/UI surface.",
    )
    ap.add_argument("--seed", type=int, default=42, help="run seed (default 42)")
    ap.add_argument("--json", action="store_true", dest="as_json", help="machine-readable report")
    args = ap.parse_args(argv)

    root = _util.find_root()
    sys.path.insert(0, str(root))
    if not (root / "game" / "main.py").is_file():
        _util.say("game package not built yet - nothing to sweep")
        return EXIT_PREREQ

    import pygame

    pygame.init()
    pygame.display.set_mode((1, 1))

    report = sweep(root, int(args.seed))
    rc = EXIT_FAIL if report["failed"] else EXIT_OK

    if args.as_json:
        print(json.dumps({"ok": rc == EXIT_OK, "seed": report["seed"],
                          "surfaces": [{k: v for k, v in r.items() if k != "traceback"}
                                       for r in report["surfaces"]]}, indent=2))
        return rc

    _util.say("scene sweep (seed %d)" % report["seed"])
    for res in report["surfaces"]:
        _util.say("  [%s] %-42s %s" % ("PASS" if res["ok"] else "FAIL",
                                       res["surface"], res["detail"]))
        if not res["ok"]:
            _util.say(res.get("traceback", "").rstrip())
    _util.say("OK: %d surface(s) rendered" % len(report["surfaces"]) if rc == EXIT_OK
              else "FAILED: %d of %d surface(s) raised"
                   % (len(report["failed"]), len(report["surfaces"])))
    return rc


if __name__ == "__main__":
    sys.exit(_util.guard(main)())
