"""Minimal-diff pre-gate for coder-model candidates.

    python -m tools.studio.minimal_diff_gate --model prism-ml/bonsai-27b
    python -m tools.studio.minimal_diff_gate --model <id> --skip-load   (already loaded)

Why it exists: M-01 measured two candidates (rnj-1, bonsai-27b) that pass every speed and
context gate, emit tool calls correctly, and then DESTROY the file they were asked to edit -
one deleted 59 lines, the other 76, both from a scoped "add one method" instruction, and
neither could read its own traceback to self-diagnose. Context and throughput are table
stakes; surgical editing is the actual bar. This gate measures exactly that.

The gate drives the candidate through the same raw tool loop the M-01 probe used
(read_file -> write_file -> run_tests) against a THROWAWAY copy of a real studio file in
%TEMP%, so a bad edit can never reach the repo. It then scores the diff:

  PASS  - baseline + only the requested change; file still imports; target behaviour works
  FAIL  - anything else (extra deletions, broken syntax, silent loop without a final answer)

Exit 0 = PASS, exit 1 = FAIL, exit 2 = could not run the trial (model missing, etc.).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LMS = Path.home() / ".lmstudio" / "bin" / "lms.exe"
API = "http://localhost:1234/v1/chat/completions"
MAX_TURNS = 12

SOURCE = REPO / "game" / "systems" / "rng.py"

TOOLS = [
    {"type": "function", "function": {
        "name": "read_file",
        "description": "Read a file from disk. Returns its full content.",
        "parameters": {"type": "object",
                        "properties": {"path": {"type": "string"}},
                        "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "write_file",
        "description": "Write complete content to a file, overwriting it.",
        "parameters": {"type": "object",
                        "properties": {"path": {"type": "string"},
                                        "content": {"type": "string"}},
                        "required": ["path", "content"]}}},
    {"type": "function", "function": {
        "name": "run_tests",
        "description": "Run a shell command and return stdout/stderr/exit code.",
        "parameters": {"type": "object",
                        "properties": {"command": {"type": "string"}},
                        "required": ["command"]}}},
]


def say(msg: str) -> None:
    print(msg, flush=True)


def load(model: str, context: int) -> bool:
    p = subprocess.run([str(LMS), "load", model, "--context-length", str(context),
                        "--gpu", "max", "-y"], capture_output=True, text=True, timeout=900)
    out = (p.stdout or "") + (p.stderr or "")
    ok = "Model loaded" in out
    say("load %s" % ("ok" if ok else "FAILED: %s" % out.strip().splitlines()[-1][:200]))
    return ok


def py() -> str:
    venv = REPO / ".venv" / "Scripts" / "python.exe"
    return str(venv) if venv.exists() else sys.executable


def check_target_behaviour(python: str, sandbox: Path) -> tuple[bool, str]:
    """The requested method must work AND the file must still import cleanly."""
    probe = (
        "import sys; sys.path.insert(0, r'%s');\n"
        "from game.systems.rng import RNG\n"
        "r = RNG(42); seq = ['a', 'b', 'c']\n"
        "picks = sorted({r.next_choice(seq) for _ in range(50)})\n"
        "assert picks == ['a', 'b', 'c'], picks\n"
        "assert RNG(7).next_choice(['x']) == 'x'\n"
        "try:\n    RNG(1).next_choice([])\nexcept ValueError:\n    print('BEHAVIOUR-OK')\n"
        % sandbox
    )
    p = subprocess.run([python, "-c", probe], capture_output=True, text=True, timeout=60)
    return p.returncode == 0 and "BEHAVIOUR-OK" in p.stdout, (p.stderr or p.stdout)[-400:]


def trial(model: str, sandbox: Path, python: str) -> dict:
    """Drive the model through the tool loop on the sandbox copy. Returns a verdict dict."""
    rel = "game/systems/rng.py"
    sandbox_file = sandbox / "game" / "systems" / "rng.py"

    system = (
        "You are chip, the coder bot of the Rogueworks studio. Use the provided tools "
        "(read_file, write_file, run_tests) to complete the task. Never fabricate output - "
        "if a tool call fails, read the error and change your approach. Finish by running "
        "the acceptance command with run_tests and reporting its real output."
    )
    task = (
        "Scoped task: %s contains the studio's RNG class. Read it, then add ONE method "
        "next_choice(self, seq) that returns seq[int(self.random() * len(seq))] and raises "
        "ValueError on empty input, with a short docstring. MINIMAL DIFF: change nothing "
        "else - every existing line, helper and method must survive byte-identical. Then "
        "verify by running via run_tests: %s -c \"import sys; sys.path.insert(0,r'%s'); "
        "from game.systems.rng import RNG; r=RNG(42); seq=['a','b','c']; "
        "print(sorted({r.next_choice(seq) for _ in range(50)})); "
        "print(RNG(7).next_choice(['x']))\" and report its real output."
        % (rel, python, sandbox)
    )

    messages = [{"role": "system", "content": system},
                {"role": "user", "content": task}]
    saw_final = False
    same_command_runs: dict[str, int] = {}
    turns_used = 0

    for turn in range(MAX_TURNS):
        turns_used = turn + 1
        body = json.dumps({"model": model, "messages": messages, "tools": TOOLS,
                            "temperature": 0.2, "max_tokens": 4096}).encode()
        req = urllib.request.Request(API, data=body,
                                     headers={"Content-Type": "application/json",
                                                "Authorization": "Bearer lm-studio"})
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                data = json.loads(r.read())
        except urllib.error.HTTPError as exc:
            return {"verdict": "FAIL", "reason": "HTTP %s from completion endpoint" % exc.code,
                    "turns": turns_used}
        msg = data["choices"][0]["message"]
        calls = msg.get("tool_calls") or []
        if not calls:
            saw_final = True
            break
        messages.append(msg)
        for c in calls:
            fn = c["function"]["name"]
            args = json.loads(c["function"]["arguments"])
            if fn == "read_file":
                result = sandbox_file.read_text(encoding="utf-8", errors="replace")
            elif fn == "write_file":
                written = args["content"]
                sandbox_file.write_text(written, encoding="utf-8", newline="\n")
                result = "wrote %d bytes" % len(written)
            elif fn == "run_tests":
                command = args["command"]
                # Detect the silent-loop signature that killed both M-01 candidates:
                # the identical failing command repeated instead of changing approach.
                key = hashlib.sha256(command.encode()).hexdigest()[:12]
                same_command_runs[key] = same_command_runs.get(key, 0) + 1
                p = subprocess.run(command, shell=True, capture_output=True, text=True,
                                    timeout=120, cwd=str(sandbox))
                result = ("exit=%s\nSTDOUT:\n%s\nSTDERR:\n%s"
                            % (p.returncode, p.stdout[-2000:], p.stderr[-1500:]))
            else:
                result = "unknown tool"
            messages.append({"role": "tool", "tool_call_id": c["id"],
                                "content": result[-2500:]})
    looped = max(same_command_runs.values(), default=1)
    return {"verdict": None, "saw_final": saw_final, "turns": turns_used,
            "worst_repeat": looped}


def score(model: str, sandbox: Path, before: bytes, after: bytes, meta: dict) -> dict:
    reasons = []
    baseline_after, after_lines = before.count(b"\n"), after.count(b"\n")

    py_exe = py()
    behaviour_ok, behaviour_detail = check_target_behaviour(py_exe, sandbox)

    # 1. Minimal diff: additions allowed, deletions are not (a scoped method-add should
    #    delete nothing; both M-01 candidates deleted 59-76 lines).
    old_lines = before.decode("utf-8", "replace").splitlines()
    new_lines = after.decode("utf-8", "replace").splitlines()
    removed = [l for l in old_lines if l not in new_lines]
    if removed:
        reasons.append("DELETED %d existing line(s), first: %r" % (len(removed), removed[0][:60]))
    if behaviour_ok:
        added = [l for l in new_lines if l not in old_lines]
        if not any("next_choice" in l for l in added):
            reasons.append("no next_choice added?")
    else:
        reasons.append("file does not behave: %s" % behaviour_detail.replace("\n", " | ")[:200])

    if meta.get("verdict") is not None:
        reasons.append("tool loop ended early: %s" % meta.get("reason", "?"))
    elif not meta.get("saw_final"):
        reasons.append("no final answer in %d turns (silent loop)" % meta.get("turns"))
    if meta.get("worst_repeat", 1) >= 4:
        reasons.append("repeated the same failing command %dx (no self-diagnosis)"
                        % meta["worst_repeat"])

    verdict = "PASS" if not reasons else "FAIL"
    return {"model": model, "verdict": verdict,
            "lines_before": baseline_after, "lines_after": after_lines,
            "lines_deleted": len(removed) if not reasons else len(removed),
            "behaviour_ok": behaviour_ok, "reasons": reasons}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m tools.studio.minimal_diff_gate")
    ap.add_argument("--model", required=True)
    ap.add_argument("--context", type=int, default=65536)
    ap.add_argument("--no-load", action="store_true", help="model is already loaded")
    args = ap.parse_args(argv)

    if not SOURCE.exists():
        raise SystemExit("REFUSED: %s does not exist - the gate benchmarks a real studio file."
                            % SOURCE)

    if not args.no_load:
        if not load(args.model, args.context):
            raise SystemExit(2)

    sandbox = Path(tempfile.mkdtemp(prefix="rw_diffgate_"))
    try:
        (sandbox / "game" / "systems").mkdir(parents=True)
        (sandbox / "game" / "__init__.py").write_text("", encoding="utf-8")
        target = sandbox / "game" / "systems" / "rng.py"
        before = SOURCE.read_bytes()
        target.write_bytes(before)
        # An empty game/__init__ and the copied rng.py must import standalone.
        p = subprocess.run([py(), "-c", "import sys; sys.path.insert(0, r'%s'); "
                            "import game.systems.rng" % sandbox],
                            capture_output=True, text=True, timeout=60)
        if p.returncode != 0:
            say("sandbox baseline failed to import: %s" % p.stderr[-300:])
            raise SystemExit(2)
        say("sandbox ready: %s (baseline %d bytes)" % (sandbox, len(before)))

        meta = trial(args.model, sandbox, py())
        after = target.read_bytes()
        result = score(args.model, sandbox, before, after, meta)
        say("GATE    : %s -> %s" % (args.model, result["verdict"]))
        for reason in result["reasons"]:
            say("  - %s" % reason)
        if result["verdict"] == "PASS":
            say("  minimal diff held: %d -> %d lines, behaviour verified"
                % (result["lines_before"], result["lines_after"]))

        import json as _json
        dest = os.path.join(os.environ.get("TEMP", "."), "rw_minimal_diff_gate.json")
        try:
            with open(dest, encoding="utf-8") as fh:
                doc = _json.load(fh)
        except Exception:
            doc = {}
        doc.setdefault("results", {})[args.model] = result
        tmp = dest + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            _json.dump(doc, fh, indent=2)
        os.replace(tmp, dest)
        say("wrote %s" % dest)
        return 0 if result["verdict"] == "PASS" else 1
    finally:
        shutil.rmtree(sandbox, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
