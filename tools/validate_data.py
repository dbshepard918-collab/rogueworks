"""content schema validator for ``game/data/*.json`` (docs/CONTRACTS.md section 4).

    python -m tools.validate_data
    python -m tools.validate_data --data-dir /tmp/broken --json

Exit status: **0** when every file is clean (including "0 files found" on an empty
or missing ``game/data``), **1** when at least one content error was found, **2**
for bad usage.

What is checked per file:

* the envelope is ``{"version": 1, "entries": [...]}`` with ``entries`` an array
  of objects;
* every required field is present with the right **type** (numbers are numbers,
  booleans are booleans, never strings);
* enums, numeric ranges and snake_case ids match the contract table;
* ids are unique per file;
* cross-file references resolve when the referenced file is present:
  ``monsters.biome`` -> biomes, ``biomes.monsters[]`` -> monsters,
  ``monsters.status_on_hit`` -> statuses;
* ``sprite`` values exist as frames in ``assets/atlas/*.json`` (skipped with a
  note when no atlas has been packed yet - the art pipeline runs in parallel).
  Only ``sprite`` is cross-checked, exactly as contract section 4 says; other
  free-text art fields (``icon``, ``tileset``, ``props``) are not.

Unknown extra fields are reported as warnings, never errors: content may grow
before the contract does.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from tools import _util
from tools._util import EXIT_FAIL, EXIT_OK

SNAKE_RE = _util.SNAKE_RE
STAT_KEYS = ("damage", "armor", "max_hp", "speed", "luck", "crit")

# --------------------------------------------------------------------------- #
# schemas - one dict per content file, field -> spec
# spec keys: type, required, nullable, enum, min, max, gt, snake, id, ref,
#            atlas, items, stats, list_of, len_min, nonempty
# --------------------------------------------------------------------------- #
ELEMENTS = {"physical", "fire", "water", "ice", "lightning", "poison", "shadow", "holy", "wind", "earth"}

STR = {"type": "str", "nonempty": True}

SCHEMAS: dict[str, dict[str, dict]] = {
    "monsters.json": {
        "id": {"type": "str", "id": True},
        "name": STR,
        "biome": {"type": "str", "ref": "biomes", "snake": True},
        "tier": {"type": "int", "min": 1, "max": 5},
        "hp": {"type": "num", "gt": 0},
        "damage": {"type": "num", "min": 0},
        "armor": {"type": "num", "min": 0},
        "speed": {"type": "num", "min": 0.2, "max": 3.0},
        "xp": {"type": "num", "min": 0},
        "weight": {"type": "num", "gt": 0},
        "behavior": {"type": "str", "enum": {"chaser", "ranged", "ambusher", "brute", "summoner", "shielded", "teleporter", "charger", "splitter", "runner"}},
        "sprite": {"type": "str", "atlas": True},
        "element": {"type": "str", "enum": ELEMENTS, "required": False},
        "status_on_hit": {"type": "str", "nullable": True, "ref": "statuses"},
        "telegraph_duration": {"type": "num", "min": 0.25, "max": 0.55},
        "telegraph_sprite": {"type": "str", "atlas": True, "required": False},
        "shield_angle": {"type": "num", "required": False},
        "summon_count": {"type": "int", "required": False},
        "leap_range": {"type": "num", "required": False},
        "split_count": {"type": "int", "required": False},
        "telegraph_sprite": {"type": "str", "atlas": True},
        "phases": {"type": "list", "items": {"type": "dict"}, "required": False},
        "hazards": {"type": "dict", "required": False},
        "minibosses": {"type": "list", "items": {"type": "str"}, "required": False},
        "enrage": {"type": "dict", "required": False},
        "miniboss": {"type": "bool", "required": False},
        "miniboss_of": {"type": "str", "required": False},
    },
    "items.json": {
        "id": {"type": "str", "id": True},
        "name": STR,
        "slot": {"type": "str", "enum": {"weapon", "armor", "trinket", "consumable"}},
        "tier": {"type": "int", "min": 1, "max": 5},
        "effect": {"type": "dict", "stats": True},
        "value": {"type": "num", "min": 0},
        "sprite": {"type": "str", "atlas": True},
        "flavor": STR,
        "unique": {"type": "str", "nullable": True, "required": False},
        "element": {"type": "str", "enum": ELEMENTS, "required": False},
    },
    "affixes.json": {
        "id": {"type": "str", "id": True},
        "name": STR,
        "effect": {"type": "dict", "stats": True},
        "tier_min": {"type": "int", "min": 1, "max": 5},
        "tier_max": {"type": "int", "min": 1, "max": 5},
        "weight": {"type": "num", "gt": 0},
    },
    "rooms.json": {
        "id": {"type": "str", "id": True},
        "biome": {"type": "str", "ref": "biomes", "snake": True},
        "kind": {"type": "str", "enum": {"combat", "treasure", "shrine", "shop", "boss", "entrance", "secret", "gambling", "blacksmith", "fountain", "omen"}},
        "w": {"type": "int", "min": 5, "max": 24},
        "h": {"type": "int", "min": 5, "max": 24},
        "spawn_budget": {"type": "num", "min": 0},
        "props": {"type": "list", "items": {"type": "str"}, "len_min": 0},
        "secret_wall": {"type": "str", "required": False},
    },
    "biomes.json": {
        "id": {"type": "str", "id": True},
        "name": STR,
        "tileset": {"type": "str", "snake": True},
        "monsters": {"type": "list", "items": {"type": "str", "ref": "monsters"}, "len_min": 0},
        "ambient": {"type": "list", "items": {"type": "int", "min": 0, "max": 255}, "len": 3},
        "fog": {"type": "num", "min": 0.0, "max": 1.0},
        "music": {"type": "str", "nullable": True},
        "modifier": {"type": "str", "enum": {"catacombs_darkness", "ember_heat", "drowned_water", "ossuary_toxic", None}, "nullable": True},
        "secret_rooms": {"type": "list", "required": False},
        "ambient_sound": {"type": "dict", "required": False},
        "attenuation": {"type": "dict", "required": False},
        "sfx_events": {"type": "dict", "required": False},
        "secret_rooms": {"type": "list", "required": False},
    },
    "audio.json": {
        "version": {"type": "num", "min": 1},
        "manifest": {"type": "list", "items": {"type": "dict"}, "required": False},
    },
    "statuses.json": {
        "id": {"type": "str", "id": True},
        "name": STR,
        "kind": {"type": "str", "enum": {"dot", "debuff", "buff"}},
        "magnitude": {"type": "num"},
        "duration": {"type": "int", "min": 0},
        "tick_every": {"type": "int", "min": 0},
        "icon": {"type": "str", "nonempty": True},
    },
    "flavor.json": {
        "id": {"type": "str", "id": True},
        "context": {"type": "str", "enum": {"death", "levelup", "item", "shrine", "boss"}},
        "text": STR,
    },
    "meta_tree.json": {
        "_special": True,
    },
}

TYPE_NAMES = {"str": "a string", "num": "a number", "int": "an integer", "bool": "a boolean",
              "dict": "an object", "list": "an array"}


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.notes: list[str] = []
        self.files: list[dict] = []

    def error(self, where: str, msg: str) -> None:
        self.errors.append(f"{where}: {msg}")

    def warn(self, where: str, msg: str) -> None:
        self.warnings.append(f"{where}: {msg}")


# --------------------------------------------------------------------------- #
# type + value checks
# --------------------------------------------------------------------------- #
def type_ok(value, tname: str) -> bool:
    if tname == "num":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if tname == "int":
        return isinstance(value, int) and not isinstance(value, bool)
    if tname == "str":
        return isinstance(value, str)
    if tname == "bool":
        return isinstance(value, bool)
    if tname == "dict":
        return isinstance(value, dict)
    if tname == "list":
        return isinstance(value, list)
    return True


def describe(value) -> str:
    if isinstance(value, bool):
        return f"boolean {value!r}"
    if isinstance(value, str):
        return f"string {value!r}"
    if isinstance(value, (int, float)):
        return f"number {value!r}"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    if value is None:
        return "null"
    return type(value).__name__


def check_value(field: str, value, spec: dict, refs: dict[str, set[str] | None]) -> list[str]:
    """Validate one present, non-null value -> list of error strings."""
    errs: list[str] = []
    tname = spec.get("type", "any")
    if not type_ok(value, tname):
        return [f"field '{field}' must be {TYPE_NAMES.get(tname, 'a value')}, got {describe(value)}"]

    if tname == "str":
        if spec.get("nonempty") and not value.strip():
            errs.append(f"field '{field}' must not be empty")
        if spec.get("snake") and not SNAKE_RE.match(value):
            errs.append(f"field '{field}' = {value!r} is not snake_case")
        enum = spec.get("enum")
        if enum and value not in enum:
            errs.append(f"field '{field}' = {value!r} is off-schema; allowed: {', '.join(sorted(x for x in enum if x is not None))}")
        ref = spec.get("ref")
        if ref:
            known = refs.get(ref)
            if known is None:
                pass  # referenced file absent: cannot cross-check
            elif value not in known:
                errs.append(f"field '{field}' = {value!r} references unknown {ref} id "
                            f"(known: {len(known)})")
        if spec.get("atlas"):
            known = refs.get("atlas")
            if known and value not in known:
                errs.append(f"field '{field}' = {value!r} is not a frame in any assets/atlas/*.json "
                            f"({len(known)} frame(s) known)")

    if tname in ("num", "int"):
        if "min" in spec and value < spec["min"]:
            errs.append(f"field '{field}' = {value!r} is below the minimum {spec['min']}")
        if "max" in spec and value > spec["max"]:
            errs.append(f"field '{field}' = {value!r} is above the maximum {spec['max']}")
        if "gt" in spec and value <= spec["gt"]:
            errs.append(f"field '{field}' = {value!r} must be greater than {spec['gt']}")

    if tname == "dict" and spec.get("stats"):
        if not value:
            errs.append(f"field '{field}' must be a non-empty stat map "
                        f"({{{', '.join(STAT_KEYS)}}})")
        for key, amount in value.items():
            if key not in STAT_KEYS:
                errs.append(f"field '{field}' has unknown stat {key!r}; allowed: {', '.join(STAT_KEYS)}")
            elif not type_ok(amount, "num"):
                errs.append(f"field '{field}'[{key!r}] must be a number, got {describe(amount)}")

    if tname == "list":
        if "len" in spec and len(value) != spec["len"]:
            errs.append(f"field '{field}' must have exactly {spec['len']} item(s), got {len(value)}")
        min_len = spec.get("len_min")
        if field == "props" and min_len is None:
            min_len = 0
        if min_len is not None and len(value) < min_len:
            errs.append(f"field '{field}' must have at least {min_len} item(s), got {len(value)}")
        item_spec = spec.get("items")
        if item_spec:
            for i, item in enumerate(value):
                if not type_ok(item, item_spec.get("type", "any")):
                    errs.append(f"field '{field}'[{i}] must be "
                                f"{TYPE_NAMES.get(item_spec.get('type'), 'a value')}, got {describe(item)}")
                else:
                    for sub in check_value(f"{field}[{i}]", item, item_spec, refs):
                        errs.append(sub)

    return errs


def check_entry(fname: str, idx: int, entry, schema: dict, refs, report: Report) -> str | None:
    """Validate one entry; returns its id when usable."""
    where = f"{fname} [{idx}]"
    if not isinstance(entry, dict):
        report.error(where, f"entry must be a JSON object, got {describe(entry)}")
        return None

    entry_id = entry.get("id")
    label = f"{where} {entry_id!r}" if isinstance(entry_id, str) else where

    for field, spec in schema.items():
        if field not in entry:
            if spec.get("required", True):
                report.error(label, f"missing required field '{field}'")
            continue
        value = entry[field]
        if value is None:
            if spec.get("nullable") or not spec.get("required", True):
                continue
            report.error(label, f"field '{field}' must not be null")
            continue
        for msg in check_value(field, value, spec, refs):
            report.error(label, msg)

    for field in entry:
        if field not in schema:
            report.warn(label, f"unknown field '{field}' (not in the section-4 contract)")

    # cross-field rules the table implies but does not spell out as ranges
    if fname == "affixes.json":
        lo, hi = entry.get("tier_min"), entry.get("tier_max")
        if isinstance(lo, int) and isinstance(hi, int) and not isinstance(lo, bool) and not isinstance(hi, bool):
            if lo > hi:
                report.error(label, f"tier_min ({lo}) is greater than tier_max ({hi})")

    return entry_id if isinstance(entry_id, str) else None


# --------------------------------------------------------------------------- #
# file loading + cross-file references
# --------------------------------------------------------------------------- #
def collect_atlas_frames(atlas_dir: Path) -> tuple[set[str], list[str]]:
    frames: set[str] = set()
    notes: list[str] = []
    for jp in _util.iter_files(atlas_dir, (".json",)):
        try:
            data = _util.load_json(jp)
        except _util.ToolError as exc:
            notes.append(f"{jp.name}: unreadable ({exc}); skipped for sprite cross-check")
            continue
        if isinstance(data, dict) and isinstance(data.get("frames"), dict):
            frames |= {str(k) for k in data["frames"]}
        else:
            notes.append(f"{jp.name}: no 'frames' object; skipped for sprite cross-check")
    return frames, notes


def _validate_meta_tree(data: dict, report: Report) -> None:
    """Validate ``game/data/meta_tree.json`` (section 4 contract extension)."""
    where = "meta_tree.json"
    if data.get("version") != 1:
        report.error(where, f"top-level 'version' must be 1, got {data.get('version')!r}")

    branches = data.get("branches")
    if not isinstance(branches, list):
        report.error(where, f"'branches' must be an array, got {describe(branches)}")
        return
    if not branches:
        report.warn(where, "'branches' is empty — no meta-progression tree defined")
        return

    seen_branch_ids: dict[str, int] = {}
    for bi, branch in enumerate(branches):
        bwhere = f"{where} [branch {bi}]"
        if not isinstance(branch, dict):
            report.error(bwhere, "branch must be a JSON object, got " + describe(branch))
            continue
        bid = branch.get("id")
        if not isinstance(bid, str) or not bid.strip():
            report.error(bwhere, "missing or invalid 'id' (must be a non-empty string)")
            continue
        if bid in seen_branch_ids:
            report.error(bwhere, f"duplicate branch id '{bid}' (first seen at branch {seen_branch_ids[bid]})")
        seen_branch_ids[bid] = bi

        bname = branch.get("name")
        if not isinstance(bname, str) or not bname.strip():
            report.error(bwhere, "missing or invalid 'name' (must be a non-empty string)")
        bcolor = branch.get("color")
        if not isinstance(bcolor, list) or len(bcolor) != 3 or not all(isinstance(v, int) and 0 <= v <= 255 for v in bcolor):
            report.error(bwhere, "'color' must be a list of three ints in [0, 255]")
        btiers = branch.get("tiers")
        if not isinstance(btiers, list) or not btiers:
            report.error(bwhere, "'tiers' must be a non-empty array")
            continue

        seen_tier_levels: dict[int, int] = {}
        for ti, tier in enumerate(btiers):
            twhere = f"{bwhere} [tier {ti}]"
            if not isinstance(tier, dict):
                report.error(twhere, "tier must be a JSON object, got " + describe(tier))
                continue
            lvl = tier.get("level")
            if not isinstance(lvl, int) or lvl < 1:
                report.error(twhere, "'level' must be an integer >= 1")
            else:
                if lvl in seen_tier_levels:
                    report.error(twhere, f"duplicate tier level {lvl} in branch '{bid}'")
                seen_tier_levels[lvl] = ti
            if not isinstance(tier.get("label"), str) or not tier.get("label", "").strip():
                report.error(twhere, "missing or invalid 'label' (must be a non-empty string)")
            stat = tier.get("stat")
            if stat is not None and not isinstance(stat, str):
                report.error(twhere, "'stat' must be a string or null")
            elif isinstance(stat, str) and not SNAKE_RE.match(stat):
                report.error(twhere, f"'stat' = {stat!r} is not snake_case")
            if not isinstance(tier.get("bonus"), (int, float)) or isinstance(tier.get("bonus"), bool):
                report.error(twhere, "'bonus' must be a number")
            if not isinstance(tier.get("cost"), int) or isinstance(tier.get("cost"), bool) or tier.get("cost", 0) < 0:
                report.error(twhere, "'cost' must be a non-negative integer")
            if not isinstance(tier.get("desc"), str) or not tier.get("desc", "").strip():
                report.error(twhere, "missing or invalid 'desc' (must be a non-empty string)")
            prereq = tier.get("prereq")
            if prereq is not None and (not isinstance(prereq, str) or not prereq.strip()):
                report.error(twhere, "'prereq' must be a non-empty string or null")


def _ids(entries) -> set[str]:
    return {e["id"] for e in entries if isinstance(e, dict) and isinstance(e.get("id"), str)}


def validate_dir(data_dir: Path, atlas_dir: Path, project_root: Path) -> Report:
    report = Report()
    files = sorted(p for p in _util.iter_files(data_dir, (".json",)) if p.parent == data_dir)
    if not files:
        return report

    loaded: dict[str, dict] = {}
    for path in files:
        if path.name not in SCHEMAS:
            report.warn(path.name, "unrecognised content file (contract section 4 lists "
                                   f"{', '.join(sorted(SCHEMAS))})")
            continue
        try:
            data = _util.load_json(path)
        except _util.ToolError as exc:
            report.error(path.name, str(exc))
            continue
        if not isinstance(data, dict):
            report.error(path.name, f"top level must be a JSON object, got {describe(data)}")
            continue
        loaded[path.name] = data

    atlas_frames, atlas_notes = collect_atlas_frames(atlas_dir)
    refs: dict[str, set[str] | None] = {
        "monsters": _ids(loaded.get("monsters.json", {}).get("entries", []) or []) or None,
        "biomes": _ids(loaded.get("biomes.json", {}).get("entries", []) or []) or None,
        "statuses": _ids(loaded.get("statuses.json", {}).get("entries", []) or []) or None,
        "atlas": atlas_frames or None,
    }

    for fname, data in loaded.items():
        path = data_dir / fname
        file_errors_before = len(report.errors)
        schema = SCHEMAS[fname]

        if schema.get("_special") and fname == "meta_tree.json":
            _validate_meta_tree(data, report)
            report.files.append({
                "file": fname,
                "entries": 0,
                "errors": len(report.errors) - file_errors_before,
            })
            continue

        # audio.json uses "manifest" instead of "entries"
        if fname == "audio.json":
            manifest = data.get("manifest", [])
            if not isinstance(manifest, list):
                report.error(fname, f"'manifest' must be an array, got {describe(manifest)}")
            else:
                for idx, entry in enumerate(manifest):
                    if not isinstance(entry, dict):
                        report.error(f"{fname} [{idx}]", "entry must be an object")
                        continue
                    for req_field in ("id", "file", "model", "license", "seed", "loop", "gain"):
                        if req_field not in entry:
                            report.error(f"{fname} [{idx}]", f"missing required field '{req_field}'")
            report.files.append({
                "file": fname,
                "entries": len(manifest),
                "errors": len(report.errors) - file_errors_before,
            })
            continue

        version = data.get("version")
        if version != 1:
            report.error(fname, f"top-level 'version' must be 1, got {version!r}")
        entries = data.get("entries")
        if not isinstance(entries, list):
            report.error(fname, f"'entries' must be an array, got {describe(entries)}")
            report.files.append({"file": fname, "entries": 0, "errors": len(report.errors) - file_errors_before})
            continue

        seen: dict[str, int] = {}
        for idx, entry in enumerate(entries):
            entry_id = check_entry(fname, idx, entry, schema, refs, report)
            if entry_id:
                if entry_id in seen:
                    report.error(f"{fname} [{idx}] {entry_id!r}",
                                 f"duplicate id '{entry_id}' (first seen at entry {seen[entry_id]})")
                else:
                    seen[entry_id] = idx
        report.files.append({
            "file": fname,
            "entries": len(data.get("entries", [])) if not schema.get("_special") else 0,
            "errors": len(report.errors) - file_errors_before,
        })

    # things we could not cross-check are stated out loud, never silently skipped
    for ref, known in refs.items():
        if known is None and ref != "atlas":
            report.notes.append(f"cross-check of '{ref}' ids skipped: {ref}.json absent or empty")
    if refs["atlas"] is None:
        report.notes.append("sprite cross-check skipped: no frames in assets/atlas/*.json yet")
    report.notes += [f"atlas note: {n}" for n in atlas_notes]

    return report


# --------------------------------------------------------------------------- #
# entry point
# --------------------------------------------------------------------------- #
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m tools.validate_data",
        description="Validate game/data/*.json against the section-4 content contract.",
    )
    ap.add_argument("--data-dir", default="game/data", help="content dir (default game/data)")
    ap.add_argument("--atlas", default="assets/atlas", help="atlas dir for sprite cross-check")
    ap.add_argument("--palette", default=None, help="palette JSON (default assets/palette.json)")
    ap.add_argument("--json", action="store_true", dest="as_json", help="machine-readable report")
    ap.add_argument("--quiet", action="store_true", help="only print the summary line")
    ap.add_argument("--max-print", type=int, default=200, help="max error lines to print")
    args = ap.parse_args(argv)

    root = _util.find_root()
    _util.load_palette(args.palette, root)  # fail early on a broken palette

    data_dir = Path(args.data_dir) if Path(args.data_dir).is_absolute() else root / args.data_dir
    atlas_dir = Path(args.atlas) if Path(args.atlas).is_absolute() else root / args.atlas

    report = validate_dir(data_dir, atlas_dir, root)
    n_files = len(report.files)
    ok = not report.errors

    if not data_dir.is_dir() and not n_files:
        if args.as_json:
            print(json.dumps({"ok": True, "files": 0, "errors": [], "warnings": [], "notes": []}, indent=2))
        else:
            _util.say(f"0 files found in {_util.rel_posix(data_dir, root)} - nothing to validate")
            _util.say("hint: content lands there when the lore agent writes game/data/*.json")
        return EXIT_OK

    if args.as_json:
        print(json.dumps({
            "ok": ok,
            "data_dir": _util.rel_posix(data_dir, root),
            "files": report.files,
            "errors": report.errors,
            "warnings": report.warnings,
            "notes": report.notes,
        }, indent=2))
        return EXIT_OK if ok else EXIT_FAIL

    if not n_files:
        _util.say(f"0 files found in {_util.rel_posix(data_dir, root)} - nothing to validate")
        for n in report.notes:
            _util.note(n)
        return EXIT_OK

    if not args.quiet:
        for item in report.files:
            tag = "ok" if item["errors"] == 0 else f"{item['errors']} error(s)"
            _util.say(f"{_util.rel_posix(data_dir / item['file'], root)}: {item['entries']} entries, {tag}")

    shown = 0
    for line in report.errors:
        if shown >= args.max_print:
            _util.say(f"... {len(report.errors) - shown} more error(s) suppressed (--max-print)")
            break
        _util.err(line)
        shown += 1
    if not args.quiet:
        for line in report.warnings:
            _util.warn(line)
        for n in report.notes:
            _util.note(n)

    n_entries = sum(i["entries"] for i in report.files)
    if ok:
        _util.say(f"PASS: {n_files} file(s), {n_entries} entries, 0 error(s), {len(report.warnings)} warning(s)")
        return EXIT_OK
    _util.say(f"FAIL: {n_files} file(s), {n_entries} entries, {len(report.errors)} error(s), "
              f"{len(report.warnings)} warning(s)")
    return EXIT_FAIL


if __name__ == "__main__":
    sys.exit(_util.guard(main)())
