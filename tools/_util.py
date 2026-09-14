"""Shared helpers for the ``tools`` package (rogueworks).

Nothing in here is game-facing; the game must never import ``tools``.  These are
project-root discovery, palette loading, JSON IO, and the "never traceback"
entry-point guard used by every command-line tool in ``tools/``.

Exit codes (documented in docs/CONTRACTS.md-adjacent README):

===== ==========================================================
0     success (including "nothing to do because input is empty")
1     checked something and it failed (validation / run errors)
2     prerequisite missing or bad usage (game not built, no file)
===== ==========================================================
"""

from __future__ import annotations

import functools
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, Sequence

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_PREREQ = 2

SNAKE_RE = re.compile(r"^[a-z][a-z0-9_]*$")
HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")

TILE = 32
"""Base tile size in pixels (docs/CONTRACTS.md section 2)."""

MAGENTA_KEY = (255, 0, 255)
"""The chroma key colour: pixels this colour are cut, not shipped."""


class ToolError(Exception):
    """An expected, user-facing failure: printed as one line, exit code 2."""


# --------------------------------------------------------------------------- #
# paths
# --------------------------------------------------------------------------- #
def find_root(start: str | os.PathLike | None = None) -> Path:
    """Walk up from ``start`` (default cwd) until the project root is found.

    The project root is the directory holding ``assets/palette.json`` or
    ``docs/CONTRACTS.md``; falls back to the starting directory.
    """
    p = Path(start) if start else Path.cwd()
    try:
        p = p.resolve()
    except OSError:  # pragma: no cover - defensive
        p = Path.cwd()
    for cand in (p, *p.parents):
        if (cand / "assets" / "palette.json").is_file() or (cand / "docs" / "CONTRACTS.md").is_file():
            return cand
    return p


def ensure_dir(path: str | os.PathLike) -> Path:
    """mkdir -p, returning the Path."""
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def rel_posix(path: str | os.PathLike, root: str | os.PathLike) -> str:
    """Path relative to root, with forward slashes (atlas JSON uses this)."""
    p, r = Path(path).resolve(), Path(root).resolve()
    try:
        return p.relative_to(r).as_posix()
    except ValueError:
        return Path(path).as_posix()


def iter_files(directory: str | os.PathLike, suffixes: Sequence[str]) -> list[Path]:
    """Sorted recursive file listing filtered by suffix (missing dir -> [])."""
    d = Path(directory)
    if not d.is_dir():
        return []
    wanted = tuple(s.lower() for s in suffixes)
    out = [p for p in d.rglob("*") if p.is_file() and p.name.lower().endswith(wanted)]
    return sorted(out, key=lambda p: p.as_posix().lower())


def iter_pngs(directory: str | os.PathLike) -> list[Path]:
    return iter_files(directory, (".png",))


# --------------------------------------------------------------------------- #
# json
# --------------------------------------------------------------------------- #
def load_json(path: str | os.PathLike):
    """json.load with the errors turned into one-line ToolErrors."""
    p = Path(path)
    if not p.is_file():
        raise ToolError(f"file not found: {p}")
    try:
        with p.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError as exc:
        raise ToolError(f"{p}: invalid JSON (line {exc.lineno} col {exc.colno}): {exc.msg}") from None
    except OSError as exc:
        raise ToolError(f"{p}: cannot read ({exc})") from None


def write_json(path: str | os.PathLike, obj) -> Path:
    p = Path(path)
    ensure_dir(p.parent)
    with p.open("w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2)
        fh.write("\n")
    return p


# --------------------------------------------------------------------------- #
# palette
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Palette:
    """The locked palette from ``assets/palette.json`` (docs/CONTRACTS.md section 6)."""

    version: int
    colors: dict[str, tuple[int, int, int]]
    key_names: tuple[str, ...]
    key_rgb: tuple[int, int, int] | None
    source: Path
    name: str = ""

    # -- lookups ----------------------------------------------------------- #
    @property
    def rgb_set(self) -> frozenset[tuple[int, int, int]]:
        return frozenset(self.colors.values())

    def exact_name(self, rgb: tuple[int, int, int]) -> str | None:
        """Palette colour name for an exact RGB match, else None."""
        for cname, crgb in self.colors.items():
            if crgb == rgb:
                return cname
        return None

    def contains(self, rgb: tuple[int, int, int]) -> bool:
        return rgb in self.rgb_set

    def nearest(self, rgb: tuple[int, int, int]) -> tuple[str, tuple[int, int, int], int]:
        """Nearest palette colour (Euclidean RGB distance) -> (name, rgb, dist)."""
        best: tuple[str, tuple[int, int, int], int] | None = None
        r, g, b = rgb
        for cname, (cr, cg, cb) in self.colors.items():
            d = (r - cr) ** 2 + (g - cg) ** 2 + (b - cb) ** 2
            if best is None or d < best[2]:
                best = (cname, (cr, cg, cb), d)
        assert best is not None  # load_palette rejects empty palettes
        return best

    def is_key(self, rgb: tuple[int, int, int]) -> bool:
        return rgb == MAGENTA_KEY

    @property
    def chroma_key(self) -> tuple[int, int, int]:
        """The colour to key out: ``magenta_key`` if the palette has one, else #ff00ff.

        The palette deliberately does **not** contain the chroma key (a key colour
        in the palette would ship as real art and could never be keyed safely), so
        this normally falls back to the nominal magenta.
        """
        return self.key_rgb if self.key_rgb is not None else MAGENTA_KEY

    def __len__(self) -> int:
        return len(self.colors)


def load_palette(path: str | os.PathLike | None = None, root: str | os.PathLike | None = None) -> Palette:
    """Load and validate ``assets/palette.json``."""
    proj = Path(root) if root else find_root()
    p = Path(path) if path else proj / "assets" / "palette.json"
    if not p.is_absolute() and not p.is_file():
        p = proj / p
    obj = load_json(p)
    if not isinstance(obj, dict):
        raise ToolError(f"{p}: top level must be a JSON object")
    colors = obj.get("colors")
    if not isinstance(colors, dict) or not colors:
        raise ToolError(f"{p}: missing non-empty 'colors' object")
    parsed: dict[str, tuple[int, int, int]] = {}
    bad: list[str] = []
    for cname, value in colors.items():
        if not isinstance(value, str) or not HEX_RE.match(value):
            bad.append(str(cname))
            continue
        parsed[str(cname)] = (int(value[1:3], 16), int(value[3:5], 16), int(value[5:7], 16))
    if bad:
        raise ToolError(f"{p}: bad colour value for {', '.join(sorted(bad))} (want '#rrggbb')")
    key_names = tuple(sorted(n for n, c in parsed.items() if n == "magenta_key" or c == MAGENTA_KEY))
    return Palette(
        version=int(obj.get("version", 1)),
        colors=parsed,
        key_names=key_names,
        key_rgb=MAGENTA_KEY if key_names else None,
        source=Path(p),
        name=str(obj.get("name", "")),
    )


# --------------------------------------------------------------------------- #
# subprocess probe: is the game built yet?
# --------------------------------------------------------------------------- #
_PROBE = (
    "import importlib.util,sys;"
    "sys.exit(0 if importlib.util.find_spec(sys.argv[1]) else 3)"
)


def module_available(python: str, module: str, cwd: str | os.PathLike) -> tuple[bool, str]:
    """Is ``module`` importable by ``python`` from ``cwd``? -> (bool, detail)."""
    try:
        proc = subprocess.run(
            [python, "-c", _PROBE, module],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"{type(exc).__name__}: {exc}"
    if proc.returncode == 0:
        return True, "importable"
    detail = (proc.stderr or proc.stdout or "").strip().splitlines()
    tail = detail[-1] if detail else f"exit {proc.returncode}"
    return False, tail


# --------------------------------------------------------------------------- #
# output helpers
# --------------------------------------------------------------------------- #
def say(msg: str = "") -> None:
    print(msg)


def note(msg: str) -> None:
    print(f"note: {msg}")


def warn(msg: str) -> None:
    print(f"WARN {msg}")


def err(msg: str) -> None:
    print(f"ERROR {msg}", file=sys.stderr)


def status(tag: str, name: str, detail: str = "") -> None:
    """One aligned PASS/SKIP/FAIL line for the self-test harness."""
    print(f"[{tag:4}] {name:28} {detail}".rstrip())


# --------------------------------------------------------------------------- #
# entry-point guard
# --------------------------------------------------------------------------- #
def guard(fn):
    """Wrap a tool's ``main(argv) -> int`` so it can never traceback.

    ToolError -> exit 2, any other exception -> exit 1 with a one-liner.
    ``TOOLS_DEBUG=1`` re-raises instead (for development).
    """

    @functools.wraps(fn)
    def wrapper(argv: Sequence[str] | None = None) -> int:
        try:
            return int(fn(argv))
        except KeyboardInterrupt:  # pragma: no cover
            err("interrupted")
            return 130
        except ToolError as exc:
            if os.environ.get("TOOLS_DEBUG"):
                raise
            err(str(exc))
            return EXIT_PREREQ
        except SystemExit:
            raise
        except Exception as exc:  # noqa: BLE001 - deliberate catch-all
            if os.environ.get("TOOLS_DEBUG"):
                raise
            err(f"{type(exc).__name__}: {exc}")
            return EXIT_FAIL

    return wrapper


def cli(fn):
    """Decorator for a module entry point: ``sys.exit(guard(main)())``."""
    return guard(fn)


def run_tool_subprocess(python: str, module: str, root: Path, timeout: int = 300,
                        extra_args: list[str] | None = None) -> tuple[dict | None, str]:
    """Run a tools.* module as a subprocess, return (report_dict_or_None, error_detail)."""
    cmd = [python, "-m", module, "--json"] + list(extra_args or [])
    try:
        env = {**os.environ, "MSYS_NO_PATHCONV": "1",
               "SDL_VIDEODRIVER": "dummy", "SDL_AUDIODRIVER": "dummy"}
        proc = subprocess.run(cmd, cwd=str(root), capture_output=True, text=True,
                               timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        return None, f"{module} timed out after {timeout}s"
    except OSError as exc:
        return None, f"cannot launch {module}: {exc}"
    text = proc.stdout or ""
    # 1. the whole stdout is one JSON document (normal case)
    try:
        return json.loads(text), ""
    except json.JSONDecodeError:
        pass
    # 2. otherwise take the LAST balanced {...} block. Tools pretty-print their JSON
    #    (indent=2), which the old line-by-line scan could not read: it looked for a
    #    line starting with '{', found the closing brace's line, failed to parse, and
    #    reported the last output line ('}') as the error - so six healthy checks were
    #    marked FAIL while the tools were exiting 0.
    depth, start, last = 0, None, ""
    in_str, esc = False, False
    for i, ch in enumerate(text):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth:
                depth -= 1
                if depth == 0 and start is not None:
                    try:
                        last = json.loads(text[start:i + 1])
                    except json.JSONDecodeError:
                        pass
                    start = None
    if isinstance(last, dict):
        return last, ""
    tail = (proc.stderr or text).strip().splitlines()
    return None, f"{module} exited {proc.returncode}: {tail[-1] if tail else 'no output'}"
