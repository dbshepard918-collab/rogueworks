"""shot: render simulation ticks to PNGs by driving the game CLI.

    python -m tools.qa.shot --seed 1 --frames 10,60 --out runs/shots

Runs ``python -m game.main --headless --seed S --shot <ticks> --shot-dir <dir>``
(section 3 of docs/CONTRACTS.md: ``--shot`` names the ticks to render,
``--shot-dir`` says where the PNGs go) and then reports every PNG that appeared,
with its size in pixels and bytes, so a QA report can cite real evidence.

Exit status: 0 shots written, 1 the run failed or produced no PNGs, 2 the game
package is not importable yet (the expected state during development) or the
arguments were bad.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

from tools import _util
from tools._util import EXIT_FAIL, EXIT_OK, EXIT_PREREQ, ToolError


def parse_frames(text: str) -> list[int]:
    frames: list[int] = []
    for chunk in str(text).replace(";", ",").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            value = int(chunk)
        except ValueError:
            raise ToolError(f"--frames expects comma-separated integers, got {chunk!r}") from None
        if value < 0:
            raise ToolError(f"--frames values must be >= 0, got {value}")
        frames.append(value)
    if not frames:
        raise ToolError("--frames is empty; example: --frames 10,60,120")
    return frames


def _snapshot(dirs: list[Path]) -> dict[str, float]:
    seen: dict[str, float] = {}
    for d in dirs:
        for png in _util.iter_pngs(d):
            try:
                seen[str(png)] = png.stat().st_mtime
            except OSError:
                continue
    return seen


def _describe(png: Path) -> str:
    try:
        from PIL import Image

        with Image.open(png) as img:
            w, h = img.size
        size = f"{w}x{h}"
    except Exception:  # noqa: BLE001
        size = "size unknown"
    try:
        kb = png.stat().st_size / 1024.0
    except OSError:
        kb = 0.0
    return f"{png.as_posix()}  {size}  {kb:.1f} KB"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m tools.qa.shot",
        description="Render game frames to PNGs through the documented game CLI.",
    )
    ap.add_argument("--seed", type=int, default=0, help="run seed (default 0)")
    ap.add_argument("--frames", default="10,60", help="comma-separated ticks to render (default 10,60)")
    ap.add_argument("--out", default="runs/shots", help="shot directory (default runs/shots)")
    ap.add_argument("--turns", type=int, default=None, help="simulation steps to run first")
    ap.add_argument("--floor", type=int, default=None, help="start on floor N (debug)")
    ap.add_argument("--timeout", type=float, default=180.0, help="subprocess timeout seconds (default 180)")
    ap.add_argument("--python", default=sys.executable, help="interpreter for the game (default: this one)")
    ap.add_argument("--game-module", default="game.main", help="entry module (default game.main)")
    ap.add_argument("--json", action="store_true", dest="as_json", help="machine-readable report")
    args = ap.parse_args(argv)

    root = _util.find_root()
    frames = parse_frames(args.frames)
    out_dir = Path(args.out) if Path(args.out).is_absolute() else root / args.out
    _util.ensure_dir(out_dir)

    available, detail = _util.module_available(args.python, args.game_module, root)
    if not available:
        _util.say(
            f"game package not built yet - '{args.game_module}' is not importable ({detail}); "
            "nothing to shoot"
        )
        _util.say("hint: this is expected until game/main.py lands; the driver stays CLI-only on purpose")
        return EXIT_PREREQ

    cmd = [args.python, "-m", args.game_module, "--headless", "--seed", str(int(args.seed)),
           "--shot", ",".join(str(f) for f in frames), "--shot-dir", str(out_dir)]
    if args.turns is not None:
        cmd += ["--turns", str(int(args.turns))]
    if args.floor is not None:
        cmd += ["--floor", str(int(args.floor))]

    watch = [out_dir, root / "runs" / "shots", root]
    before = _snapshot(watch)

    if not args.as_json:
        _util.say(f"$ {' '.join(cmd)}")
        _util.say("--- game output ---")

    started = time.time()
    env = _child_env()

    try:
        proc = subprocess.run(cmd, cwd=str(root), capture_output=True, text=True,
                              timeout=float(args.timeout), env=env)
        rc, stdout, stderr = proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        _util.say(f"game run timed out after {args.timeout}s - no shots reported")
        return EXIT_FAIL
    except OSError as exc:
        _util.say(f"cannot launch the game ({args.python}): {exc}")
        return EXIT_PREREQ

    if not args.as_json:
        for line in (stdout or "").splitlines():
            _util.say(f"  {line}")
        if stderr:
            for line in stderr.splitlines():
                _util.say(f"  ! {line}")
        _util.say("--- end game output ---")

    after = _snapshot(watch)
    new_pngs = sorted(
        Path(p) for p, mtime in after.items() if p not in before or mtime > before[p] + 1e-6
    )
    requested = [(out_dir / f"{t}.png") for t in frames]
    produced = [p for p in new_pngs if p.suffix.lower() == ".png"]

    if args.as_json:
        print(json.dumps({
            "ok": rc == 0 and bool(produced),
            "cmd": cmd,
            "exit_code": rc,
            "seed": int(args.seed),
            "frames": frames,
            "out": _util.rel_posix(out_dir, root),
            "shots": [{"path": _util.rel_posix(p, root), "bytes": p.stat().st_size}
                      for p in produced if p.exists()],
            "elapsed_s": round(time.time() - started, 3),
        }, indent=2))
        return EXIT_OK if (rc == 0 and produced) else EXIT_FAIL

    _util.say(f"game exit code: {rc}   ({time.time() - started:.2f}s)")
    if rc != 0:
        _util.say(f"FAIL: the game exited {rc}; fix that before trusting shots")
        return EXIT_FAIL
    if not produced:
        _util.say(f"FAIL: run succeeded but no PNG appeared in {_util.rel_posix(out_dir, root)}")
        _util.say(f"      expected one of: {', '.join(p.name for p in requested[:6])}")
        return EXIT_FAIL

    _util.say(f"{len(produced)} shot(s) written:")
    for png in produced:
        _util.say(f"  {_describe(png)}")
    return EXIT_OK


def _child_env() -> dict:
    import os

    env = dict(os.environ)
    env["SDL_VIDEODRIVER"] = "dummy"
    env["SDL_AUDIODRIVER"] = "dummy"
    env.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
    return env


if __name__ == "__main__":
    sys.exit(_util.guard(main)())
