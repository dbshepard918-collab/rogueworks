"""Audit: does EVERY sprite name the game will ask for actually resolve to shipped art.

Runs the real loader, so it catches exactly what the game would hit at runtime: an atlas frame, a
loader alias, or nothing (meaning a synthesized placeholder box appears in-game).

    python -m tools.studio.audit_sprites [--json] [--list-missing]

Exit 0 = everything resolves, 1 = gaps (each one will render as a placeholder).
Owned by forge. Re-run it after any content or art change; it is the contract between `lore`'s data
and `pixel`'s atlases.
"""
from __future__ import annotations

import argparse
import json
import re
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

TILE_KINDS = ["floor", "floor_alt", "floor_alt2", "floor_rubble", "floor_cracked", "floor_blood",
              "floor_bones", "floor_coins", "wall", "wall_alt", "wall_torch", "wall_corner",
              "wall_decor", "wall_cracked", "wall_skull", "doorway", "door", "door_open",
              "stairs_down", "stairs_up", "pillar", "pool", "pool_alt", "grate", "brazier",
              "slab", "gate", "rune_floor", "shrine_floor", "treasure_floor", "pit", "barricade"]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m tools.studio.audit_sprites")
    ap.add_argument("--json", action="store_true", dest="as_json")
    ap.add_argument("--list-missing", action="store_true")
    ap.add_argument("--fallback", action="store_true",
                    help="check only the EMBEDDED fallback content in game/systems/data.py "
                         "(the data-less checkout path) against the atlases")
    args = ap.parse_args(argv)

    import pygame
    pygame.init()
    pygame.display.set_mode((32, 32))
    import game.engine.assets as A

    frames, aliases = set(), {}
    for path in (ROOT / "assets" / "atlas").glob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data.get("frames"), dict):
            frames |= set(data["frames"])
    alias_path = ROOT / "assets" / "aliases.json"
    if alias_path.is_file():
        aliases = json.loads(alias_path.read_text(encoding="utf-8")).get("aliases", {})

    def load(name):
        return json.loads((ROOT / "game" / "data" / ("%s.json" % name)).read_text(encoding="utf-8"))

    def entries(name):
        return load(name)["entries"]

    def resolves(name: str) -> bool:
        if name in frames or name in aliases:
            return True
        # the game's own loader is the final authority (it merges atlases + aliases + fallbacks)
        for atlas_name in ("monsters", "items", "tiles", "props", "vfx", "ui", "bosses", "player"):
            atlas = A.Atlas.load(atlas_name)
            if atlas.has(name):
                return True
        return False

    def is_placeholder(name: str) -> bool:
        """A frame the loader synthesizes looks nothing like the shipped art; detect the fallback."""
        try:
            for atlas_name in ("props", "tiles", "ui", "monsters", "items", "vfx", "bosses",
                               "player"):
                atlas = A.Atlas.load(atlas_name)
                if atlas.has(name):
                    return False
        except Exception:  # noqa: BLE001
            pass
        return True

    needed: dict[str, list[str]] = {}

    def need(name: str, why: str) -> None:
        needed.setdefault(name, [])
        if why not in needed[name]:
            needed[name].append(why)

    for mon in entries("monsters"):
        need(mon["sprite"], "monster %s" % mon["id"])
    for item in entries("items"):
        need(item["sprite"], "item %s" % item["id"])
    for room in entries("rooms"):
        for prop in room.get("props", []):
            need(prop, "room %s" % room["id"])
    for biome in entries("biomes"):
        for kind in TILE_KINDS:
            need("%s_%s" % (biome["tileset"], kind), "tile %s" % biome["id"])
    for status in entries("statuses"):
        need(status["icon"], "status %s" % status["id"])

    missing = sorted(n for n in needed if not resolves(n))

    if args.fallback:
        # the data-less path: whatever the game falls back to must resolve to real art too,
        # otherwise a checkout without game/data/ silently ships a second, uglier game.
        import game.systems.data as GData

        PREFIXES = ("prop_", "tile_", "ui_", "monster_", "item_", "vfx_", "player_")
        BARE = ("brazier", "rubble", "bones", "urn", "altar", "pillar", "candles", "crystal",
                "chest", "coin", "key", "potion", "torch", "web", "crate", "barrel", "anvil",
                "forge", "kelp", "roots", "sarcophagus", "pipes", "chain", "lava_vent",
                "water_pool", "shop_stall", "tomb")
        fb_needed: list[tuple[str, str]] = []

        def walk(node, attr, depth=0):
            if depth > 6:
                return
            if isinstance(node, str):
                if re.fullmatch(r"item_\d+", node):        # flavour ids, not sprites
                    return
                if re.fullmatch(r"tile_(catacombs|ember|drowned)", node):   # biome tileset prefix
                    return
                if node.startswith(PREFIXES) or node in BARE:
                    fb_needed.append((attr, node))
                return
            if isinstance(node, dict):
                for v in node.values():
                    walk(v, attr, depth + 1)
                return
            if isinstance(node, (list, tuple)):
                for v in node:
                    walk(v, attr, depth + 1)

        for attr in dir(GData):
            if attr.startswith("__"):
                continue
            walk(getattr(GData, attr), attr, 0)

        fb_missing = sorted({cell for _, cell in fb_needed if not resolves(cell)})
        print("audit_sprites --fallback: %d embedded sprite name(s) walked out of "
              "game/systems/data.py" % len({c for _, c in fb_needed}))
        print("  unresolved: %d" % len(fb_missing))
        for name in fb_missing:
            who = sorted({attr for attr, cell in fb_needed if cell == name})[:3]
            print("    %-24s <- %s" % (name, ", ".join(who)))
        if fb_missing:
            print("  FIX: the embedded fallback must use the same sprite names as shipped content "
                  "(see docs/CONTENT.md conventions) - one agreed naming list, no second dialect.")
        return 0 if not fb_missing else 1

    report = {"referenced": len(needed), "resolved": len(needed) - len(missing),
              "missing": missing,
              "missing_with_reasons": {n: needed[n] for n in missing}}

    if args.as_json:
        print(json.dumps(report, indent=2))
    else:
        print("audit_sprites: %d sprite name(s) referenced by content" % report["referenced"])
        print("  resolved: %d" % report["resolved"])
        print("  MISSING : %d%s" % (len(missing), " (each renders as a placeholder box)" if missing
                                    else ""))
        if missing and args.list_missing:
            for name in missing:
                print("    %-26s <- %s" % (name, ", ".join(needed[name][:3])))
    return 0 if not missing else 1


if __name__ == "__main__":
    sys.exit(main())
