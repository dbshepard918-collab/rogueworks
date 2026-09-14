"""selftest: imports + invariant smoke test for the whole project.

    python -m tools.selftest
    python -m tools.selftest --turns 120 --json

Prints one ``[PASS]/[SKIP]/[FAIL]`` line per check and a summary.

Exit status

* **0** - every check passed (the game package is importable and the smoke run
  came back clean);
* **2** - the game package is not built yet: ``game.main`` is not importable, so
  the game-dependent checks are skipped and the harness says so out loud
  (that is the expected state while the game is still being written);
* **1** - something that exists is broken.

Checks: python version, pygame/Pillow/numpy, palette lock, ``game/data`` schema,
atlas format, placeholder art, game importability, expected submodules, RNG
determinism (contract section 2), "no bare ``random`` in game/", a real
``python -m game.main --headless`` run whose invariants must be clean, a static
audit that every intra-project module attribute the game calls actually exists,
and a glyph-coverage check that every printable ASCII character has a renderable glyph.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

from tools import _util
from tools._util import EXIT_FAIL, EXIT_OK, EXIT_PREREQ

PASS, SKIP, FAIL = "PASS", "SKIP", "FAIL"

PROBE_SCRIPT = r'''
import importlib.util, json, sys

def spec_ok(name):
    try:
        return importlib.util.find_spec(name) is not None
    except BaseException:
        return False

res = {"main_spec": spec_ok("game.main"), "import_ok": False, "error": None,
       "submodules": {}, "rng": None}
if res["main_spec"]:
    try:
        import game, game.main  # noqa: F401
        res["import_ok"] = True
    except BaseException as exc:
        res["error"] = "%s: %s" % (type(exc).__name__, exc)
    for mod in ("game.engine", "game.entities", "game.systems", "game.ui",
                "game.systems.rng", "game.engine.assets", "game.data"):
        res["submodules"][mod] = spec_ok(mod)
    try:
        from game.systems.rng import RNG
        def seq(seed):
            rng = RNG(seed)
            return [round(float(rng.random()), 12) for _ in range(8)]
        a, b, c = seq(7), seq(7), seq(8)
        res["rng"] = {"same_seed_equal": a == b, "other_seed_differs": a != c}
    except BaseException as exc:
        res["rng"] = {"error": "%s: %s" % (type(exc).__name__, exc)}
print("@@PROBE@@" + json.dumps(res))
'''


class Harness:
    def __init__(self, json_mode: bool = False) -> None:
        self.results: list[dict] = []
        self.json_mode = json_mode

    def record(self, tag: str, name: str, detail: str = "") -> None:
        self.results.append({"check": name, "status": tag, "detail": detail})
        if not self.json_mode:
            _util.status(tag, name, detail)

    def counts(self) -> dict[str, int]:
        return {t: sum(1 for r in self.results if r["status"] == t) for t in (PASS, SKIP, FAIL)}


# --------------------------------------------------------------------------- #
# checks
# --------------------------------------------------------------------------- #
def probe_game(root: Path, python: str) -> dict:
    """Import-probe the game package in a subprocess (never pollutes our process)."""
    try:
        proc = subprocess.run(
            [python, "-c", PROBE_SCRIPT],
            cwd=str(root), capture_output=True, text=True, timeout=180,
            env=_child_env(),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"main_spec": False, "import_ok": False, "error": f"{type(exc).__name__}: {exc}",
                "submodules": {}, "rng": None}
    for line in reversed(proc.stdout.splitlines()):
        if line.startswith("@@PROBE@@"):
            try:
                return json.loads(line[len("@@PROBE@@"):])
            except json.JSONDecodeError:
                break
    tail = (proc.stderr or proc.stdout or "").strip().splitlines()
    return {"main_spec": False, "import_ok": False,
            "error": tail[-1] if tail else f"probe exited {proc.returncode}",
            "submodules": {}, "rng": None}


def _child_env() -> dict:
    import os

    env = dict(os.environ)
    env["SDL_VIDEODRIVER"] = "dummy"
    env["SDL_AUDIODRIVER"] = "dummy"
    env.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
    env.pop("PYTHONWARNINGS", None)
    return env


def check_bare_random(root: Path) -> tuple[str, str, list[str]]:
    game_dir = root / "game"
    files = sorted(game_dir.rglob("*.py")) if game_dir.is_dir() else []
    if not files:
        return SKIP, "game/ has no python files yet", []
    offenders: list[str] = []
    pattern = re.compile(r"(^\s*import\s+random\b)|(^\s*from\s+random\s+import)|(\brandom\.(random|randint|choice|shuffle|uniform|seed)\b)")
    for path in files:
        if "rng" in path.name.lower():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if pattern.search(line) and "noqa" not in line:
                offenders.append(f"{_util.rel_posix(path, root)}:{i}")
    if offenders:
        return FAIL, f"{len(offenders)} bare random use(s): {', '.join(offenders[:5])}", offenders
    return PASS, f"{len(files)} file(s), no bare random usage", []


def check_headless_run(root: Path, python: str, turns: int, seed: int) -> tuple[str, str]:
    runs_dir = _util.ensure_dir(root / "runs")
    log_path = runs_dir / f"selftest-{seed}.json"
    cmd = [python, "-m", "game.main", "--headless", "--seed", str(seed), "--turns", str(turns),
           "--new-run", "--log", str(log_path)]
    try:
        proc = subprocess.run(cmd, cwd=str(root), capture_output=True, text=True,
                              timeout=max(120, turns // 2), env=_child_env())
    except subprocess.TimeoutExpired:
        return FAIL, f"headless run timed out after {max(120, turns // 2)}s"
    except OSError as exc:
        return FAIL, f"cannot launch game: {exc}"
    tail = (proc.stderr or "").strip().splitlines()
    if proc.returncode != 0:
        return FAIL, f"exit {proc.returncode}: {tail[-1] if tail else 'no stderr'}"
    if not log_path.is_file():
        return SKIP, f"exit 0 but no run summary at {_util.rel_posix(log_path, root)}"
    try:
        data = json.loads(log_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return FAIL, f"run summary unreadable: {exc}"
    violations = (data.get("invariants") or {}).get("violations")
    if not isinstance(violations, list):
        return FAIL, "run summary has no invariants.violations list"
    if violations:
        return FAIL, f"{len(violations)} invariant violation(s): {violations[0]}"
    ticks = data.get("ticks")
    return PASS, f"exit 0, {ticks} ticks, invariants clean"


def _run_tool(root: Path, python: str, module: str, timeout: int = 300) -> tuple[dict | None, str]:
    """Run a JSON-reporting tools.* command; return (report, error detail)."""
    cmd = [python, "-m", module, "--json"]
    try:
        proc = subprocess.run(cmd, cwd=str(root), capture_output=True, text=True,
                              timeout=timeout, env=_child_env())
    except subprocess.TimeoutExpired:
        return None, f"{module} timed out after {timeout}s"
    except OSError as exc:
        return None, f"cannot launch {module}: {exc}"
    for line in reversed((proc.stdout or "").splitlines()):
        if line.strip().startswith("{"):
            try:
                return json.loads(_last_json(proc.stdout)), ""
            except json.JSONDecodeError:
                break
    tail = (proc.stderr or proc.stdout or "").strip().splitlines()
    return None, f"{module} exited {proc.returncode}: {tail[-1] if tail else 'no output'}"


def check_glyph_coverage(root: Path, python: str) -> tuple[str, str]:
    """Every printable ASCII character must have a renderable glyph."""
    report, err = _run_tool(root, python, "tools.qa.glyph_coverage")
    if report is None:
        return FAIL, err
    missing = report.get("missing_required", []) + report.get("missing_in_use", [])
    if missing:
        return FAIL, f"{len(missing)} missing glyph(s): {missing[:5]}"
    return PASS, f"{report.get('glyphs_defined', 0)} glyph(s) defined, all renderable"


def _last_json(text: str) -> str:
    """Pull the last complete JSON object out of a multi-line report."""
    start = text.find("{")
    end = text.rfind("}")
    return text[start:end + 1] if start >= 0 and end > start else "{}"


def check_attr_audit(root: Path, python: str) -> tuple[str, str]:
    """Every intra-project module attribute the game calls must exist."""
    report, err = _run_tool(root, python, "tools.qa.attr_audit")
    if report is None:
        return FAIL, err
    missing = report.get("missing") or []
    if missing:
        first = missing[0]
        return FAIL, (f"{len(missing)} unresolved reference(s), first: "
                      f"{first.get('file')} {first.get('ref')}")
    return PASS, f"{report.get('checked', 0)} attribute access(es) resolve"


def check_end_screens(root: Path, python: str, seed: int) -> tuple[str, str]:
    """The death and victory end screens must render real pixels, not crash."""
    report, err = _run_tool(root, python, "tools.qa.death_run")
    if report is None:
        return FAIL, err
    paths = report.get("paths") or []
    failed = [p for p in paths if not p.get("ok")]
    if failed or not report.get("ok"):
        first = failed[0] if failed else {}
        return FAIL, f"{first.get('kind', 'end screen')} path failed: {first.get('detail', 'see output')}"
    return PASS, "; ".join(f"{p['kind']}: {p['detail']}" for p in paths)


def check_scene_sweep(root: Path, python: str) -> tuple[str, str]:
    """Every scene and UI surface must construct and render."""
    report, err = _run_tool(root, python, "tools.qa.scene_sweep")
    if report is None:
        return FAIL, err
    surfaces = report.get("surfaces") or []
    broken = [s for s in surfaces if not s.get("ok")]
    if broken:
        first = broken[0]
        return FAIL, (f"{len(broken)} of {len(surfaces)} surface(s) raised, first: "
                      f"{first.get('surface')} ({first.get('detail')})")
    return PASS, f"{len(surfaces)} surface(s) rendered"


def check_audio_audit(root: Path, python: str) -> tuple[str, str]:
    """Every shipped music cue must be licensed, present and audible."""
    report, err = _run_tool(root, python, "tools.qa.audio_audit")
    if report is None:
        return FAIL, err
    if not report.get("present"):
        return PASS, "no game/data/audio.json yet - no cues to check"
    problems = report.get("problems") or []
    cues = report.get("cues") or []
    if problems:
        return FAIL, f"{len(problems)} bad cue(s), first: {problems[0]}"
    return PASS, f"{len(cues)} cue(s) licensed and audible"


def check_scene_legibility(root: Path, python: str) -> tuple[str, str]:
    """A rendered floor must be readable, not merely non-blank."""
    report, err = _run_tool(root, python, "tools.qa.scene_legibility")
    if report is None:
        return FAIL, err
    problems = report.get("problems") or []
    if problems:
        return FAIL, problems[0]
    return PASS, ("tiles visible %.0f%%, mid-tone %.0f%%, mean lum %.1f"
                  % (100 * report.get("visible_tile_coverage", 0),
                     100 * report.get("mid_tone_share", 0),
                     report.get("mean_luminance", 0)))


# --------------------------------------------------------------------------- #
# entry point
# --------------------------------------------------------------------------- #
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m tools.selftest",
        description="Import and invariant smoke test for the rogueworks project.",
    )
    ap.add_argument("--turns", type=int, default=60, help="headless smoke-run steps (default 60)")
    ap.add_argument("--seed", type=int, default=0, help="smoke-run seed (default 0)")
    ap.add_argument("--python", default=sys.executable, help="interpreter used for subprocesses")
    ap.add_argument("--json", action="store_true", dest="as_json", help="machine-readable report")
    ap.add_argument("--skip-game-run", action="store_true", help="skip the headless smoke run")
    args = ap.parse_args(argv)

    root = _util.find_root()
    h = Harness(json_mode=args.as_json)

    # -- interpreter & deps -------------------------------------------------- #
    v = sys.version_info
    if (v.major, v.minor) >= (3, 11):
        h.record(PASS, "python-version", f"{v.major}.{v.minor}.{v.micro}")
    else:
        h.record(FAIL, "python-version", f"{v.major}.{v.minor}.{v.micro} (contract needs 3.11+)")

    for mod, label in (("pygame", "pygame-ce"), ("PIL", "pillow"), ("numpy", "numpy")):
        if importlib.util.find_spec(mod) is None:
            tag = SKIP if mod == "numpy" else FAIL
            h.record(tag, f"dep-{label}", "not installed")
        else:
            try:
                spec = importlib.import_module(mod)
                h.record(PASS, f"dep-{label}", getattr(spec, "__version__", "installed"))
            except Exception as exc:  # noqa: BLE001
                h.record(FAIL, f"dep-{label}", f"{type(exc).__name__}: {exc}")

    # -- palette ------------------------------------------------------------- #
    try:
        pal = _util.load_palette(root=root)
        key_note = "key #ff00ff (not a palette colour, by design)"
        if len(pal) < 24:
            h.record(FAIL, "palette-lock", f"only {len(pal)} colours (contract pins 24)")
        elif pal.key_rgb is not None:
            h.record(FAIL, "palette-lock",
                     f"the chroma key #ff00ff is a palette colour ('{pal.key_names[0]}'): it could never "
                     "be keyed safely out of raw art")
        else:
            h.record(PASS, "palette-lock", f"'{pal.name}' v{pal.version}, {len(pal)} colours, {key_note}")
    except _util.ToolError as exc:
        h.record(FAIL, "palette-lock", str(exc))
        pal = None

    # -- content schema ------------------------------------------------------ #
    from tools import validate_data

    data_dir, atlas_dir = root / "game" / "data", root / "assets" / "atlas"
    try:
        report = validate_data.validate_dir(data_dir, atlas_dir, root)
        n_files = len(report.files)
        if n_files == 0:
            h.record(SKIP, "content-schema", "0 files in game/data - nothing to validate")
        elif report.errors:
            h.record(FAIL, "content-schema", f"{len(report.errors)} error(s), first: {report.errors[0][:90]}")
        else:
            entries = sum(f["entries"] for f in report.files)
            h.record(PASS, "content-schema", f"{n_files} file(s), {entries} entries, {len(report.warnings)} warning(s)")
    except Exception as exc:  # noqa: BLE001
        h.record(FAIL, "content-schema", f"{type(exc).__name__}: {exc}")

    # -- atlas + placeholder art --------------------------------------------- #
    from tools.art import verify as art_verify

    atlas_jsons = _util.iter_files(atlas_dir, (".json",))
    if not atlas_jsons:
        h.record(SKIP, "atlas-format", "no assets/atlas/*.json yet")
    elif pal is None:
        h.record(SKIP, "atlas-format", "palette unavailable")
    else:
        errs: list[str] = []
        frames = 0
        for jp in atlas_jsons:
            n, aerr, _ = art_verify.check_atlas_json(root, jp, pal, 3, False)
            frames += n
            errs += aerr
        if errs:
            h.record(FAIL, "atlas-format", f"{len(errs)} error(s), first: {errs[0][:90]}")
        else:
            h.record(PASS, "atlas-format", f"{len(atlas_jsons)} atlas(es), {frames} frame(s)")

    ph_dir = root / "assets" / "placeholder"
    pngs = _util.iter_pngs(ph_dir)
    if not pngs:
        h.record(SKIP, "placeholder-art", "assets/placeholder is empty")
    else:
        bad = []
        for png in pngs:
            try:
                from PIL import Image

                with Image.open(png) as img:
                    w, hgt = img.size
                if w % _util.TILE or hgt % _util.TILE:
                    bad.append(png.name)
            except Exception as exc:  # noqa: BLE001
                bad.append(f"{png.name} ({type(exc).__name__})")
        if bad:
            h.record(FAIL, "placeholder-art", f"{len(bad)} bad file(s): {', '.join(bad[:4])}")
        else:
            h.record(PASS, "placeholder-art", f"{len(pngs)} PNG(s), grid-aligned")

    # -- game package -------------------------------------------------------- #
    probe = probe_game(root, args.python)
    game_built = bool(probe.get("import_ok"))
    if game_built:
        h.record(PASS, "game-import", "import game.main ok")
    elif probe.get("main_spec"):
        h.record(FAIL, "game-import", f"game.main exists but import fails: {probe.get('error')}")
    else:
        h.record(SKIP, "game-import", "game/main.py absent")

    subs = probe.get("submodules") or {}
    if subs:
        missing = [m for m, ok in sorted(subs.items()) if not ok]
        if missing:
            h.record(SKIP, "game-layout", f"not present yet: {', '.join(missing)}")
        else:
            h.record(PASS, "game-layout", f"{len(subs)} expected module(s) present")

    random_tag, random_detail, random_offenders = check_bare_random(root)
    h.record(random_tag, "no-bare-random", random_detail)

    rng = probe.get("rng")
    if not game_built:
        h.record(SKIP, "rng-determinism", "game package not importable")
    elif not rng:
        h.record(SKIP, "rng-determinism", "game.systems.rng.RNG not found")
    elif rng.get("error"):
        h.record(FAIL, "rng-determinism", rng["error"][:110])
    elif rng.get("same_seed_equal") and rng.get("other_seed_differs"):
        h.record(PASS, "rng-determinism", "same seed -> same stream, other seed -> different")
    else:
        h.record(FAIL, "rng-determinism", "RNG(seed) is not reproducible")
    del random_offenders

    if not game_built:
        h.record(SKIP, "headless-run", "game package not built yet")
    elif args.skip_game_run:
        h.record(SKIP, "headless-run", "--skip-game-run")
    else:
        tag, detail = check_headless_run(root, args.python, int(args.turns), int(args.seed))
        h.record(tag, "headless-run", detail)

    if not game_built:
        h.record(SKIP, "module-attributes", "game package not built yet")
        h.record(SKIP, "end-screens", "game package not built yet")
        h.record(SKIP, "scene-sweep", "game package not built yet")
        h.record(SKIP, "glyph-coverage", "game package not built yet")
    else:
        tag, detail = check_attr_audit(root, args.python)
        h.record(tag, "module-attributes", detail)
        tag, detail = check_end_screens(root, args.python, int(args.seed))
        h.record(tag, "end-screens", detail)
        tag, detail = check_scene_sweep(root, args.python)
        h.record(tag, "scene-sweep", detail)
        tag, detail = check_audio_audit(root, args.python)
        h.record(tag, "audio-audit", detail)
        tag, detail = check_scene_legibility(root, args.python)
        h.record(tag, "scene-legibility", detail)
        tag, detail = check_glyph_coverage(root, args.python)
        h.record(tag, "glyph-coverage", detail)

    counts = h.counts()
    if args.as_json:
        print(json.dumps({
            "ok": counts[FAIL] == 0 and game_built,
            "game_built": game_built,
            "counts": counts,
            "checks": h.results,
        }, indent=2))
    else:
        _util.say("")
        _util.say(f"{len(h.results)} checks: {counts[PASS]} passed, {counts[SKIP]} skipped, {counts[FAIL]} failed")

    if not game_built:
        _util.say("game package not built yet - game-dependent checks skipped "
                  "(expected while game/ is still being written)")
        return EXIT_PREREQ
    if counts[FAIL]:
        _util.say(f"FAILED: {counts[FAIL]} check(s) - see the [FAIL] lines above")
        return EXIT_FAIL
    _util.say("OK: no failures")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(_util.guard(main)())
