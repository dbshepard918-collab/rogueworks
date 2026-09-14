"""Is every bot's model actually good to go? Answer with evidence, not a feeling.

The studio must never be stoppable by a billing limit, so two things have to be true and stop
being assumptions:

  1. **No paid pin.** Every model in every profile's chain is free-tier or local. A paid model
     in a fallback chain is the exact failure the studio's cost rule exists to prevent.
  2. **The models answer.** A pin that is configured but unreachable is not a pin - the bot
     silently fails over, or fails.

    python -m tools.studio.model_health                  # config audit + local presence + cloud probe
    python -m tools.studio.model_health --probe-local     # also load and answer with each local pin
    python -m tools.studio.model_health --json

Exit 0 = every pin is free/local and every probed route answered.
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

PROFILES = Path(os.path.expanduser("~")) / "AppData" / "Local" / "hermes" / "profiles"
ENV_FILE = Path(os.path.expanduser("~")) / "AppData" / "Local" / "hermes" / ".env"
LMS = os.path.expanduser("~/.lmstudio/bin/lms.exe")
LMSTUDIO = "http://localhost:1234/v1"

# Provider-level classification. `nous`/`openrouter` are only acceptable with a ':free' suffix;
# `lmstudio` is the local GPU and can never bill.
FREE_SUFFIX = ":free"


def load_env_names() -> dict:
    """Keys we may probe with, read from the Hermes .env. Values stay in memory, never printed."""
    out = {}
    try:
        for line in ENV_FILE.read_text(encoding="utf-8", errors="replace").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip()
    except OSError:
        pass
    return out


def classify(provider: str, model: str) -> str:
    """free | local | cloud (needs a probe) | PAID (rule violation)."""
    p = (provider or "").lower()
    m = (model or "")
    if p == "lmstudio":
        return "local"
    if m.endswith(FREE_SUFFIX):
        return "free"
    if p in ("huggingface", "openrouter", "nous"):
        # These providers host both free and paid models; a non-':free' pin is unverified.
        return "cloud?"
    return "PAID?"


def lmstudio_models() -> set:
    try:
        with urllib.request.urlopen(LMSTUDIO + "/models", timeout=10) as r:
            return {m["id"] for m in json.load(r).get("data", [])}
    except Exception:
        return set()


def probe_local(model: str, tokens: int = 8) -> dict:
    """Load and answer with a local pin. Slow, so it is opt-in."""
    unload = subprocess.run([LMS, "unload", "--all"], capture_output=True, text=True, timeout=120)
    t0 = time.time()
    load = subprocess.run([LMS, "load", model, "--gpu", "max", "-c", "8192", "-y"],
                          capture_output=True, text=True, timeout=900)
    out = (load.stdout or "") + (load.stderr or "")
    loaded = "Model loaded" in out
    load_s = round(time.time() - t0, 1)
    if not loaded:
        return {"ok": False, "load_s": load_s, "detail": "did not load: " +
                " | ".join(out.strip().splitlines()[-2:])[:200]}
    body = {"model": model, "max_tokens": tokens, "temperature": 0,
            "messages": [{"role": "user", "content": "Reply with the single word: ready"}]}
    req = urllib.request.Request(LMSTUDIO + "/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    t1 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            d = json.load(r)
        text = (d["choices"][0]["message"].get("content") or "").strip()
        return {"ok": bool(text), "load_s": load_s, "answer_s": round(time.time() - t1, 1),
                "said": text[:40] or "<empty>",
                "finish": d["choices"][0].get("finish_reason")}
    except urllib.error.HTTPError as exc:
        return {"ok": False, "load_s": load_s, "detail": "HTTP %s: %s" % (
            exc.code, exc.read().decode("utf-8", "replace")[:160])}
    except Exception as exc:
        return {"ok": False, "load_s": load_s, "detail": "%s: %s" % (type(exc).__name__, exc)}


def probe_hf(model: str, key: str, tokens: int = 8) -> dict:
    """Cheapest possible proof that a HuggingFace route answers (and is not gated)."""
    body = {"model": model, "max_tokens": tokens,
            "messages": [{"role": "user", "content": "Reply with one word: ready"}]}
    req = urllib.request.Request(
        "https://router.huggingface.co/v1/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + key})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            d = json.load(r)
        text = (d["choices"][0]["message"].get("content") or "").strip()
        return {"ok": bool(text), "answer_s": round(time.time() - t0, 1), "said": text[:40]}
    except urllib.error.HTTPError as exc:
        return {"ok": False, "detail": "HTTP %s: %s" % (
            exc.code, exc.read().decode("utf-8", "replace")[:160])}
    except Exception as exc:
        return {"ok": False, "detail": "%s: %s" % (type(exc).__name__, exc)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m tools.studio.model_health")
    ap.add_argument("--probe-local", action="store_true",
                    help="load and answer with each distinct local pin (slow; needs the GPU)")
    ap.add_argument("--json", action="store_true", dest="as_json")
    args = ap.parse_args(argv)

    try:
        import yaml
    except ImportError:
        print("PyYAML is required (run with the Hermes python, not the game venv)")
        return 2

    env = load_env_names()
    installed = lmstudio_models()
    report = {"profiles": [], "problems": [], "probes": {}}

    for prof in sorted(PROFILES.iterdir()):
        cfg = prof / "config.yaml"
        if not cfg.is_file():
            continue
        d = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
        prim = d.get("model") or {}
        chain = [(prim.get("provider"), prim.get("default"), "primary")]
        for f in (d.get("fallback_model") or []):
            chain.append((f.get("provider"), f.get("model"), "fallback"))
        row = {"bot": prof.name, "chain": []}
        for provider, model, role in chain:
            if not model:
                continue
            kind = classify(provider, model)
            entry = {"role": role, "provider": provider, "model": model, "kind": kind}
            if kind in ("PAID?",) and provider == "lmstudio":
                kind = entry["kind"] = "local"
            if kind == "PAID?":
                report["problems"].append(
                    "%s %s pins '%s' (%s) which is not free-tier or local - the studio must not "
                    "be stoppable by a billing limit" % (prof.name, role, model, provider))
            if kind == "local" and model not in installed:
                entry["installed"] = False
                report["problems"].append(
                    "%s %s pins local '%s' which is NOT installed in LM Studio"
                    % (prof.name, role, model))
            elif kind == "local":
                entry["installed"] = True
            row["chain"].append(entry)
        report["profiles"].append(row)

    # live probes: one per distinct local pin (opt-in) and per distinct cloud model we hold a key for
    if args.probe_local:
        for model in sorted({e["model"] for p in report["profiles"] for e in p["chain"]
                             if e["kind"] == "local"}):
            report["probes"]["local:" + model] = probe_local(model)
    hf_key = env.get("HF_TOKEN") or ""
    if hf_key:
        for model in sorted({e["model"] for p in report["profiles"] for e in p["chain"]
                             if e.get("provider") == "huggingface"}):
            report["probes"]["huggingface:" + model] = probe_hf(model, hf_key)

    for name, pr in report["probes"].items():
        if not pr.get("ok"):
            report["problems"].append("probe failed: %s -> %s"
                                      % (name, pr.get("detail", "no answer")))

    if args.as_json:
        print(json.dumps(report, indent=2))
        return 1 if report["problems"] else 0

    print("MODEL HEALTH — every pin must be free-tier or local, and every probed route must answer")
    for p in report["profiles"]:
        print("  %-13s %s" % (p["bot"], ""))
        for e in p["chain"]:
            mark = {"local": "LOCAL", "free": "FREE", "cloud?": "CLOUD?"}.get(e["kind"], "PAID?")
            extra = "" if e.get("installed", True) else "  <- NOT INSTALLED"
            print("      %-9s %-6s %-12s %-42s%s"
                  % (e["role"], mark, e["provider"], e["model"], extra))
    for name, pr in report["probes"].items():
        print("  probe %-42s %s" % (name, "ok (%ss)" % pr.get("answer_s", pr.get("load_s"))
                                    if pr.get("ok") else "FAILED: " + str(pr.get("detail"))[:90]))
    if report["problems"]:
        print("PROBLEMS (%d):" % len(report["problems"]))
        for pr in report["problems"]:
            print("  - %s" % pr)
        return 1
    print("OK: every pinned model is free-tier or local, and every probed route answered")
    return 0


if __name__ == "__main__":
    sys.exit(main())
