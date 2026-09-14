"""Measure a local LM Studio model honestly: load it, time a real generation, report tok/s + VRAM.

    python -m tools.studio.bench_local --model qwen/qwen3-coder-30b [--context 65536] [--tokens 200]

Why it exists: "it should be faster with offload" is not a measurement. This prints the numbers the
studio pins models on, and it loads at >=64K context because that is what Hermes requires.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

LMS = Path.home() / ".lmstudio" / "bin" / "lms.exe"
API = "http://localhost:1234/v1/chat/completions"

PROMPT = ("Write a Python function that takes a list of (x, y) points and returns the two points "
          "with the greatest distance between them. Code only.")


def say(msg: str) -> None:
    print(msg, flush=True)


def vram() -> str:
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used,memory.total",
                              "--format=csv,noheader"], capture_output=True, text=True,
                             timeout=30).stdout.strip()
        return out or "?"
    except Exception:  # noqa: BLE001
        return "?"


def load(model: str, context: int) -> None:
    say("loading %s at %d context ..." % (model, context))
    t0 = time.time()
    p = subprocess.run([str(LMS), "load", model, "--context-length", str(context), "--gpu", "max",
                        "-y"], capture_output=True, text=True, timeout=900)
    ok = "Model loaded" in (p.stdout + p.stderr) or p.returncode == 0
    say("  load %s in %.1fs (VRAM %s)" % ("ok" if ok else "FAILED", time.time() - t0, vram()))


def generate(model: str, tokens: int, context: int = 0) -> dict:
    body = {"model": model, "max_tokens": tokens, "temperature": 0,
            "messages": [{"role": "user", "content": PROMPT}]}
    req = urllib.request.Request(API, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json",
                                          "Authorization": "Bearer lm-studio"})
    t0 = time.time()
    try:
        data = json.load(urllib.request.urlopen(req, timeout=900))
    except urllib.error.HTTPError as exc:
        # A model that will not run at this context must say so in words. Reported here
        # as a bare `HTTPError: HTTP Error 400` - indistinguishable from a broken model.
        detail = ""
        try:
            detail = exc.read().decode("utf-8", "replace")[:300]
        except Exception:
            pass
        raise SystemExit(
            "REFUSED: %s did not serve a completion at context=%s.\n"
            "  LM Studio said: %s\n"
            "  Means: the model is not loaded, or it does not fit the card at this context.\n"
            "  Try a smaller --context (e.g. 8192) or load it first and pass --no-load."
            % (model, context, detail or "<no body>"))
    secs = time.time() - t0
    usage = data.get("usage") or {}
    out_tokens = usage.get("completion_tokens") or 0
    return {"seconds": round(secs, 2), "completion_tokens": out_tokens,
            "tok_per_s": round(out_tokens / secs, 1) if secs and out_tokens else 0.0,
            "chars": len((data["choices"][0]["message"].get("content") or ""))}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m tools.studio.bench_local")
    ap.add_argument("--model", required=True)
    ap.add_argument("--context", type=int, default=65536)
    ap.add_argument("--tokens", type=int, default=200)
    ap.add_argument("--no-load", action="store_true", help="model is already loaded")
    args = ap.parse_args(argv)

    if not args.no_load:
        load(args.model, args.context)
    say("VRAM after load: %s" % vram())
    first = generate(args.model, args.tokens, args.context)
    say("warm-up : %(seconds)ss, %(completion_tokens)s tokens, %(tok_per_s)s tok/s" % first)
    runs = [generate(args.model, args.tokens, args.context) for _ in range(3)]
    best = max(r["tok_per_s"] for r in runs)
    avg = sum(r["tok_per_s"] for r in runs) / len(runs)
    say("3 runs  : %s" % ", ".join("%.1f" % r["tok_per_s"] for r in runs))
    say("RESULT  : %s -> %.1f tok/s (best), %.1f tok/s (avg), VRAM %s"
        % (args.model, best, avg, vram()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
