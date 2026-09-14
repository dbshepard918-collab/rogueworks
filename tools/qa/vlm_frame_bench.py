"""Benchmark a VLM on frame-quality judgement, with ground truth instead of vibes.

Why this exists: `vlm_bench` scores a model on a contact sheet - counting and spotting
flat fills. The job the studio actually needs (lens's scene audit) is different: look at
a rendered gameplay frame and say whether it is *readable*. That is a judgement, so prose
cannot be scored... unless the frames have known answers.

Method: render one real frame through the game's own scene stack, then degrade it by known
factors (the same multiply-the-frame mechanism that caused the original "floor 1 is
unplayable" bug). Measure each variant with the numeric legibility gate, which supplies
the ground truth label. Then ask the model, per frame:

    1. rate readability 0-10
    2. what percentage of map tiles are clearly visible

and score the model on whether its judgements ORDER and CLASSIFY the frames the way the
numeric gate does. Speed is recorded but quality is the point.

    python -m tools.qa.vlm_frame_bench qwen/qwen3-vl-8b
    python -m tools.qa.vlm_frame_bench zai-org/glm-4.6v-flash --max-tokens 8192
"""
from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ENDPOINT = "http://localhost:1234/v1/chat/completions"
LMS = os.path.expanduser("~/.lmstudio/bin/lms.exe")
TEMP = os.environ.get("TEMP", ".")
# A thinking model bills its chain-of-thought against this; too small and it answers nothing.
MAX_TOKENS = 8192
DEGRADATIONS = [1.0, 0.55, 0.30]          # multiply factor applied to the whole frame

QUESTIONS = (
    "You are QA for a top-down roguelite. Look at this rendered gameplay frame and answer "
    "with two numbers only, no explanation:\n"
    "1. How readable is this frame, 0-10? (0 = unplayable, a black or near-black screen; "
    "10 = perfectly readable, you can see the map, the player and the monsters)\n"
    "2. Roughly what percentage of the MAP TILES are clearly visible? 0-100."
)


def lms(*args, timeout=900):
    try:
        return subprocess.run([LMS, *args], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None


def ask(model, prompt, b64, max_tokens):
    body = {"model": model, "messages": [{"role": "user", "content": [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64," + b64}}]}],
        "max_tokens": max_tokens, "temperature": 0.1}
    req = urllib.request.Request(ENDPOINT, data=json.dumps(body).encode(),
                                headers={"Content-Type": "application/json"})
    started = time.time()
    try:
        with urllib.request.urlopen(req, timeout=900) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", "replace")[:300]
        except Exception:
            pass
        raise SystemExit("REFUSED: %s did not answer.\n  LM Studio said: %s" % (model, detail))
    choice = data["choices"][0]
    msg = choice.get("message") or {}
    usage = data.get("usage") or {}
    return {"text": msg.get("content") or "", "finish": choice.get("finish_reason"),
            "elapsed": time.time() - started, "usage": usage,
            "reasoning_tokens": (usage.get("completion_tokens_details") or {}).get(
                "reasoning_tokens", 0)}


def build_frames():
    """Render one real frame and its degraded variants; return records with ground truth.

    Ground truth comes from `tools.qa.scene_legibility.measure` - the same numbers the
    gate uses - so a model's judgement can be compared against a measurement rather than
    against my opinion of its prose.
    """
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    import pygame
    from tools.qa.scene_legibility import measure, render_frame

    pygame.init()
    pygame.display.set_mode((1, 1))
    surface, biome = render_frame(0, 120, 1)
    out = []
    for factor in DEGRADATIONS:
        frame = surface.copy()
        if factor < 1.0:
            grey = int(round(255 * factor))
            frame.fill((grey, grey, grey), special_flags=pygame.BLEND_RGB_MULT) \
                if hasattr(pygame, "BLEND_RGB_MULT") else frame.fill((grey, grey, grey))
        metrics = measure(frame)
        path = os.path.join(TEMP, "rw_frame_%02d.png" % int(factor * 100))
        pygame.image.save(frame, path)
        out.append({"factor": factor, "path": path, "biome": biome, "metrics": metrics})
    return out


def parse_two_numbers(text):
    """Pull a 0-10 rating and a 0-100 percentage out of a terse reply."""
    import re
    rating = percent = None
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    for ln in lines:
        nums = re.findall(r"\d+(?:\.\d+)?", ln)
        if not nums:
            continue
        if ln.lstrip("*- ").startswith("2") and percent is None:
            percent = float(nums[-1])
        elif rating is None:
            rating = float(nums[0])
        elif percent is None:
            percent = float(nums[0])
    if rating is None and lines:
        nums = re.findall(r"\d+(?:\.\d+)?", lines[0])
        if nums:
            rating = float(nums[0])
    return rating, percent


def bench(model, frames):
    print("=" * 74)
    print("MODEL: %s" % model)
    lms("unload", "--all")
    load = lms("load", model, "--gpu", "max", "-c", "8192", "-y")
    # `lms()` returns None on a subprocess timeout, so this branch must not assume a
    # CompletedProcess - it did, and a model that timed out while loading raised
    # `AttributeError: 'NoneType' object has no attribute 'stdout'` instead of saying so.
    output = ((load.stdout or "") + (load.stderr or "")) if load is not None else ""
    if load is None or "Model loaded" not in output:
        detail = "timed out while loading" if load is None else             " | ".join(output.strip().splitlines()[-2:])
        raise SystemExit("REFUSED: could not load %s at context=8192.\n  LM Studio said: %s\n"
                         "  Means: it does not fit at this context, or the id is wrong."
                         % (model, detail[:300]))

    rows = []
    for fr in frames:
        with open(fr["path"], "rb") as fh:
            b64 = base64.b64encode(fh.read()).decode()
        r = ask(model, QUESTIONS, b64, MAX_TOKENS)
        escalated = 0
        while r["finish"] == "length" and escalated < 2:
            escalated += 1
            r = ask(model, QUESTIONS, b64, MAX_TOKENS * (4 ** escalated))
        rating, percent = parse_two_numbers(r["text"])
        truthful = r["finish"] != "length"
        rows.append({"factor": fr["factor"], "ground_truth": fr["metrics"],
                     "rating": rating, "percent": percent, "latency_s": round(r["elapsed"], 1),
                     "reasoning_tokens": r["reasoning_tokens"], "complete": truthful,
                     "raw": r["text"][:400], "finish": r["finish"]})
        print("  x%-5s mean_lum %6.1f  tiles %5.1f%%  gate %-4s -> model rating %-4s tiles %-5s "
              "(%.1fs%s)"
              % (fr["factor"], fr["metrics"]["mean_luminance"],
                 100 * fr["metrics"]["visible_tile_coverage"],
                 "PASS" if _gate_passes(fr["metrics"]) else "FAIL",
                 rating, percent, r["elapsed"],
                 ", ESCALATED" if escalated else ""))

    # --- scoring: does the model ORDER and CLASSIFY the frames like the gate does? ---
    scored = [r for r in rows if r["rating"] is not None]
    order_ok = None
    if len(scored) == len(rows) and len(scored) > 1:
        order_ok = all(scored[i]["rating"] >= scored[i + 1]["rating"]
                       for i in range(len(scored) - 1))
    truth_pass = [_gate_passes(r["ground_truth"]) for r in rows]
    verdicts = [(r["rating"] is not None and r["rating"] >= 5) for r in rows]
    classify_ok = sum(1 for t, v in zip(truth_pass, verdicts) if t == v)
    print("  ORDER  : ratings %s  (monotonic with the gate: %s)"
          % ([r["rating"] for r in rows], "YES" if order_ok else "NO"))
    print("  CLASSIFY: %d/%d frames called the same way as the numeric gate"
          % (classify_ok, len(rows)))
    return {"model": model, "rows": rows, "order_monotonic": order_ok,
            "classify_correct": classify_ok, "classify_total": len(rows)}


def _gate_passes(metrics):
    """The numeric gate's own verdict - the ground truth a VLM is being compared against."""
    from tools.qa.scene_legibility import (MAX_DARK_SHARE, MEAN_LUMINANCE_BAND,
                                           MIN_DISTINCT_COLOURS, MIN_MIDTONE_SHARE,
                                           MIN_VISIBLE_TILE_COVERAGE)
    lo, hi = MEAN_LUMINANCE_BAND
    return (metrics["visible_tile_coverage"] >= MIN_VISIBLE_TILE_COVERAGE
            and metrics["mid_tone_share"] >= MIN_MIDTONE_SHARE
            and metrics["dark_share"] <= MAX_DARK_SHARE
            and lo <= metrics["mean_luminance"] <= hi
            and metrics["distinct_colours"] >= MIN_DISTINCT_COLOURS)


def main(argv=None):
    models = [a for a in (argv or sys.argv[1:]) if not a.startswith("-")]
    for i, a in enumerate(argv or sys.argv):
        if a == "--max-tokens" and i + 1 < len(argv or sys.argv):
            global MAX_TOKENS
            MAX_TOKENS = int((argv or sys.argv)[i + 1])
    frames = build_frames()
    print("frames built: " + ", ".join(
        "%s(mean_lum %.1f, tiles %.0f%%, gate %s)"
        % (Path(f["path"]).name, f["metrics"]["mean_luminance"],
           100 * f["metrics"]["visible_tile_coverage"],
           "PASS" if _gate_passes(f["metrics"]) else "FAIL") for f in frames))
    results = []
    for m in models:
        results.append(bench(m, frames))
    dest = os.path.join(TEMP, "rw_frame_bench.json")
    tmp = dest + ".tmp"
    try:
        with open(dest, encoding="utf-8") as fh:
            doc = json.load(fh)
    except Exception:
        doc = {}
    doc["ground_truth_frames"] = [{"factor": f["factor"], "path": f["path"],
                                   "gate_pass": _gate_passes(f["metrics"]),
                                   "metrics": f["metrics"]} for f in frames]
    doc.setdefault("results", {})
    for r in results:
        doc["results"][r["model"]] = r
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2)
    os.replace(tmp, dest)
    print("wrote %s" % dest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
