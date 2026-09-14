"""attr-audit: catch calls to module attributes that do not exist.

    python -m tools.qa.attr_audit
    python -m tools.qa.attr_audit --json

Statically scans ``game/**/*.py`` for ``<alias>.<attr>`` where ``<alias>`` is an
intra-project module (absolute or relative import), imports each module for
real, and reports every attribute that would raise ``AttributeError`` at
runtime.  Headless gates only walk the code paths a 300-tick run reaches, so a
missing function on a rarely-hit path (death screen, menu branch, settings
toggle) stays invisible until a player triggers it.  This check closes that
class: if it is called, it must exist.

Exit status: 0 every referenced attribute resolves, 1 at least one does not,
2 the game package is not importable yet.
"""

from __future__ import annotations

import argparse
import ast
import importlib
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

from tools import _util  # noqa: E402
from tools._util import EXIT_FAIL, EXIT_OK, EXIT_PREREQ  # noqa: E402


def _module_name(path: Path, root: Path) -> str:
    rel = _util.rel_posix(path, root)[:-3]
    name = rel.replace("/", ".")
    return name[: -len(".__init__")] if name.endswith(".__init__") else name


def _bound_names(tree: ast.AST) -> set:
    """Every name this module binds anywhere, plus builtins.

    Deliberately broad (module scope, function args, locals, comprehension and
    loop targets, nested defs, imports) because a false positive would make the
    gate red for no reason. Precision over recall: it will miss exotic dynamic
    binding, but anything it flags really is unbound.
    """
    import builtins
    bound = set(dir(builtins)) | {"__file__", "__name__", "__doc__", "__package__",
                                  "__spec__", "__loader__", "__builtins__"}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bound.add(node.name)
        elif isinstance(node, ast.Import):
            for a in node.names:
                bound.add((a.asname or a.name).split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for a in node.names:
                bound.add(a.asname or a.name)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            bound.add(node.id)
        elif isinstance(node, ast.arg):
            bound.add(node.arg)
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            bound.update(node.names)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            bound.add(node.name)
        elif isinstance(node, ast.alias):
            bound.add((node.asname or node.name).split(".")[0])
    return bound


def undefined_names(path: Path, tree: ast.AST) -> list:
    """Names read but never bound anywhere in the module (a pyflakes-lite check).

    Catches the class of bug that broke the game: a call to a function that was
    never defined (`set_audio_singleton(self)`), which the attribute audit below
    cannot see because it only inspects `module.attr` accesses. Files using a star
    import are skipped - their name set is unknowable.
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and any(a.name == "*" for a in node.names):
            return []
    bound = _bound_names(tree)
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) and node.id not in bound:
            out.append((node.id, node.lineno))
    return out


def _aliases(tree: ast.AST, pkg: str) -> dict[str, str]:
    """Map local alias -> dotted module path for intra-project imports."""
    alias: dict[str, str] = {}
    pkg_parts = pkg.split(".")[:-1]
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            if node.level:
                base = ".".join(pkg_parts[: len(pkg_parts) - node.level + 1])
                target = (base + "." + node.module).strip(".")
            else:
                target = node.module
            if not target.startswith("game"):
                continue
            for entry in node.names:
                alias[entry.asname or entry.name] = target + "." + entry.name
        elif isinstance(node, ast.Import):
            for entry in node.names:
                if entry.name.startswith("game"):
                    alias[entry.asname or entry.name] = entry.name
    return alias


def audit(root: Path) -> dict:
    """Return {"files": n, "checked": n, "missing": [ {file, ref, why} ]}."""
    game_dir = root / "game"
    files = sorted(game_dir.rglob("*.py"))
    mods: dict[str, object] = {}

    def load(name: str):
        if name not in mods:
            try:
                mods[name] = importlib.import_module(name)
            except Exception as exc:  # noqa: BLE001
                mods[name] = exc
        return mods[name]

    missing: list[dict] = []
    checked = 0
    for path in files:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError as exc:
            missing.append({"file": _util.rel_posix(path, root), "ref": "<module>",
                            "why": "syntax error: %s" % exc})
            continue
        for name, lineno in undefined_names(path, tree):
            missing.append({
                "file": _util.rel_posix(path, root),
                "ref": "%s (line %d)" % (name, lineno),
                "why": "name is read but never defined in this module",
            })
        alias = _aliases(tree, _module_name(path, root))
        if not alias:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Attribute) or not isinstance(node.value, ast.Name):
                continue
            target = alias.get(node.value.id)
            if target is None:
                continue
            mod = load(target)
            if isinstance(mod, Exception):
                continue          # the import itself is reported by other checks
            checked += 1
            if not hasattr(mod, node.attr):
                missing.append({
                    "file": _util.rel_posix(path, root),
                    "ref": "%s.%s (line %d)" % (node.value.id, node.attr, node.lineno),
                    "why": "module '%s' has no attribute '%s'" % (target, node.attr),
                })
    return {"files": len(files), "modules": len(mods), "checked": checked, "missing": missing}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m tools.qa.attr_audit",
        description="Report intra-project module attribute calls that do not exist.",
    )
    ap.add_argument("--json", action="store_true", dest="as_json", help="machine-readable report")
    args = ap.parse_args(argv)

    root = _util.find_root()
    sys.path.insert(0, str(root))

    try:
        import importlib as _il
        _il.import_module("pygame")
    except Exception as exc:  # noqa: BLE001
        _util.say("pygame unavailable (%s) - cannot import game modules" % exc)
        return EXIT_PREREQ
    if not (root / "game" / "main.py").is_file():
        _util.say("game package not built yet - nothing to audit")
        return EXIT_PREREQ

    report = audit(root)
    rc = EXIT_FAIL if report["missing"] else EXIT_OK

    if args.as_json:
        print(json.dumps({"ok": rc == EXIT_OK, **report}, indent=2))
        return rc

    _util.say("attr-audit: %d file(s), %d module(s) imported, %d attribute access(es) checked"
              % (report["files"], report["modules"], report["checked"]))
    for item in report["missing"]:
        _util.say("  [FAIL] %s  %s  (%s)" % (item["file"], item["ref"], item["why"]))
    _util.say("OK: every referenced attribute resolves" if rc == EXIT_OK
              else "FAILED: %d unresolved reference(s) - an attribute that does not exist, a bare "
                   "name never defined in its module, or a syntax error" % len(report["missing"]))
    return rc


if __name__ == "__main__":
    sys.exit(_util.guard(main)())
