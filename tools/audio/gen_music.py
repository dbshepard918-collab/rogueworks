"""gen-music: render game music locally with a generative audio model.

    python -m tools.audio.gen_music --list-backends
    python -m tools.audio.gen_music --backend stable_audio_open \
        --prompt "..." --seconds 30 --seed 7 --out assets/audio/title_theme.wav

MUST run under the studio audio interpreter (``.venv-audio``), because torch is a
studio dependency and never a game one:

    .venv-audio/Scripts/python.exe -m tools.audio.gen_music ...

Design notes
------------
* **Local and free by construction.** Nothing here calls an API: the model runs on
  the box, so there is no rate limit and no key. A music cue is a build artefact
  that gets regenerated rarely, which is exactly the workload a local model wins.
* **Deterministic.** A fixed ``--seed`` reproduces the same cue, so an asset that
  ships can be regenerated from the command written in its manifest entry.
* **Loop-safe.** Game music has to loop without a seam. ``--loop-fade MS``
  crossfades the tail into the head so the join is inaudible, and ``--seconds`` is
  rounded to a whole number of bars where possible.
* ``--out`` is required and explicit: the tool never guesses where an asset goes.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

from tools import _util  # noqa: E402
from tools._util import EXIT_FAIL, EXIT_OK, EXIT_PREREQ  # noqa: E402

#: Sample rate the game mixer is opened at (CONTRACTS section 2 / audio.py).
GAME_RATE = 44100

#: Licences whose outputs may ship in a commercial game without further work.
COMMERCIAL_OK_LICENSES = {"mit", "apache-2.0", "cc0-1.0", "bsd-3-clause", "unlicense"}

#: Enforcement, not documentation: a backend whose weights are non-commercial or
#: gated is REFUSED unless --allow-noncommercial is passed, and that flag is for
#: throwaway experiments only.  Every shipped cue has to be free to ship.
BACKENDS = {
    "ace_step": {
        "repo": "ACE-Step/acestep-v15-xl-turbo-diffusers",
        "library": "diffusers",
        "native_rate": 44100,
        "max_seconds": 240.0,
        "license": "mit",
        "gated": False,
        "provenance": "ACE-Step v1.5 XL turbo (diffusers format); MIT weights, ungated, no account "
                      "or licence acceptance needed. Renders in 8 steps (guidance distilled).",
        "why": "the shipping backend: MIT weights, 44.1 kHz stereo, instrumental or full song, "
               "bpm/key/time-signature control, fast enough to re-render a cue on a whim",
    },
    "ace_step_sft": {
        "repo": "ACE-Step/acestep-v15-xl-sft-diffusers",
        "library": "diffusers",
        "native_rate": 44100,
        "max_seconds": 240.0,
        "license": "mit",
        "gated": False,
        "provenance": "ACE-Step v1.5 XL SFT (diffusers format); MIT weights, ungated.",
        "why": "higher-quality sibling when a cue is worth more compute than the turbo pass",
    },
    "musicgen": {
        "repo": "facebook/musicgen-medium",
        "library": "transformers",
        "native_rate": 32000,
        "max_seconds": 30.0,
        "license": "cc-by-nc-4.0",
        "gated": False,
        "provenance": "Meta MusicGen; weights are CC-BY-NC-4.0 (NON-COMMERCIAL).",
        "why": "BLOCKED for shipping: CC-BY-NC-4.0 makes every rendered cue non-commercial. Kept "
               "only for throwaway experiments with --allow-noncommercial.",
    },
    "stable_audio_open": {
        "repo": "stabilityai/stable-audio-open-1.0",
        "library": "diffusers",
        "native_rate": 44100,
        "max_seconds": 47.0,
        "license": "stable-audio-community",
        "gated": True,
        "provenance": "Stability AI; gated repo + bespoke community licence (commercial terms "
                      "and an account/acceptance step required).",
        "why": "BLOCKED for shipping on two counts: the repo is gated (401 without a login) and "
               "the licence is not a permissive one.",
    },
}


def license_ok(name: str) -> bool:
    spec = BACKENDS[name]
    return bool(spec.get("license") in COMMERCIAL_OK_LICENSES and not spec.get("gated"))


def blocked_reason(name: str) -> str:
    spec = BACKENDS[name]
    bits = []
    if spec.get("gated"):
        bits.append("repo is gated (needs an account + licence acceptance)")
    if spec.get("license") not in COMMERCIAL_OK_LICENSES:
        bits.append("licence %r is not in the shipping allowlist %s"
                    % (spec.get("license"), sorted(COMMERCIAL_OK_LICENSES)))
    return "; ".join(bits) or "usable"


# --------------------------------------------------------------------------- #
# backends
# --------------------------------------------------------------------------- #
def render_ace_step(prompt, seconds, seed, steps, negative, dtype, repo=None):
    """ACE-Step text-to-music. Works for both the v1.5 and v1 checkpoints."""
    import torch
    from diffusers import AceStepPipeline

    repo = repo or BACKENDS["ace_step"]["repo"]
    pipe = AceStepPipeline.from_pretrained(repo, dtype=dtype)
    pipe = pipe.to("cuda")
    pipe.set_progress_bar_config(disable=True)
    generator = torch.Generator("cuda").manual_seed(int(seed))
    out = pipe(
        prompt=prompt,
        lyrics="",                       # instrumental: the game has no vocals
        audio_duration=min(float(seconds), BACKENDS["ace_step"]["max_seconds"]),
        num_inference_steps=int(steps),
        guidance_scale=1.0,              # turbo checkpoints are guidance-distilled
        generator=generator,
    )
    audio = out.audios if hasattr(out, "audios") else out[0]
    # [batch, channels, samples] -> [samples, channels] float32 numpy
    return audio[0].transpose(0, 1).float().cpu().numpy(), BACKENDS["ace_step"]["native_rate"]


def render_musicgen(prompt, seconds, seed, steps, negative, dtype):
    import torch
    from transformers import AutoProcessor, MusicgenForConditionalGeneration

    torch.manual_seed(int(seed))
    proc = AutoProcessor.from_pretrained(BACKENDS["musicgen"]["repo"])
    model = MusicgenForConditionalGeneration.from_pretrained(
        BACKENDS["musicgen"]["repo"], torch_dtype=dtype).to("cuda")
    inputs = proc(text=[prompt], padding=True, return_tensors="pt").to("cuda")
    # MusicGen emits 50 tokens per second of audio
    tokens = int(min(float(seconds), BACKENDS["musicgen"]["max_seconds"]) * 50)
    audio = model.generate(**inputs, max_new_tokens=tokens, do_sample=True,
                           guidance_scale=3.0)
    arr = audio[0].transpose(0, 1).float().cpu().numpy()
    return arr, BACKENDS["musicgen"]["native_rate"]


RENDERERS = {
    "ace_step": render_ace_step,
    "ace_step_sft": lambda p, s, seed, steps, neg, dt: render_ace_step(
        p, s, seed, steps, neg, dt, repo=BACKENDS["ace_step_sft"]["repo"]),
    "musicgen": render_musicgen,
}


# --------------------------------------------------------------------------- #
# audio helpers
# --------------------------------------------------------------------------- #
def to_stereo(samples, channels):
    if samples.ndim == 1:
        samples = samples[:, None]
    if samples.shape[1] == 1 and channels == 2:
        samples = samples.repeat(2, axis=1)
    return samples[:, :channels]


def write_wav(path: Path, samples, rate: int, target_rate: int = GAME_RATE) -> dict:
    """Write 16-bit PCM, resampling to the game's mixer rate when needed."""
    import numpy as np
    import soundfile as sf

    channels = 2
    data = to_stereo(samples, channels)
    peak = float(np.max(np.abs(data))) or 1.0
    if peak > 1.0:                       # models overshoot; normalise, never clip
        data = data / peak
    if rate != target_rate:
        n_out = int(round(data.shape[0] * target_rate / float(rate)))
        idx = np.linspace(0, data.shape[0] - 1, n_out)
        data = np.stack([np.interp(idx, np.arange(data.shape[0]), data[:, ch])
                         for ch in range(data.shape[1])], axis=1).astype(np.float32)
        rate = target_rate
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), data.astype(np.float32), rate, subtype="PCM_16")
    return {"path": str(path), "rate": rate, "channels": int(data.shape[1]),
            "seconds": round(data.shape[0] / float(rate), 3)}


def make_loop(path: Path, fade_ms: int, rate: int = GAME_RATE) -> dict:
    """Crossfade the tail into the head so the file loops without a seam."""
    import numpy as np
    import soundfile as sf

    data, sr = sf.read(str(path), always_2d=True)
    n = max(1, int(sr * fade_ms / 1000.0))
    if data.shape[0] <= 2 * n:
        return {"applied": False, "reason": "clip shorter than the crossfade"}
    head, tail = data[:n].copy(), data[-n:].copy()
    ramp = np.linspace(0.0, 1.0, n)[:, None]
    data = data[:-n].copy()
    data[:n] = head * ramp + tail * (1.0 - ramp)
    sf.write(str(path), data.astype(np.float32), sr, subtype="PCM_16")
    return {"applied": True, "fade_ms": fade_ms,
            "seconds": round(data.shape[0] / float(sr), 3)}


def describe(path: Path) -> dict:
    """Verify the artefact that actually landed on disk.

    Loop quality is measured as a **wrap discontinuity**: the jump between the
    last sample and the first sample has to be no worse than the jumps that
    occur naturally inside the file.  Comparing average levels at head and tail
    says nothing about a click, which is what a bad loop actually sounds like.
    """
    import numpy as np
    import soundfile as sf

    data, sr = sf.read(str(path), always_2d=True)
    mono = data.mean(axis=1)
    rms = float(np.sqrt(np.mean(mono ** 2)))
    peak = float(np.max(np.abs(data)))

    seam = None
    click_ratio = None
    if mono.shape[0] > 1000:
        wrap = float(abs(float(mono[0]) - float(mono[-1])))
        diffs = np.abs(np.diff(mono))
        internal_p95 = float(np.percentile(diffs, 95)) or 1e-9
        seam = round(wrap, 6)
        click_ratio = round(wrap / internal_p95, 3)
    zcr = None
    dc = float(np.mean(mono))
    if rms > 1e-6:
        zcr = round(float(np.mean(np.abs(np.diff(np.sign(mono))) > 0)), 5)

    silent = rms < 1e-4
    clipping = peak >= 0.999
    # A DC-only buffer (every sample the same value) has high "rms" and can look
    # like a healthy loud signal while being pure garbage - a real failure mode
    # of a diffusion decode that ran out of memory.  Treat it as invalid.
    dc_broken = abs(dc) > 0.05 and (zcr is None or zcr < 0.001)

    return {"bytes": path.stat().st_size, "rate": sr, "channels": int(data.shape[1]),
            "seconds": round(data.shape[0] / float(sr), 3),
            "rms": round(rms, 5), "peak": round(peak, 5),
            "dc_offset": round(dc, 6),
            "zero_crossing_rate": zcr,
            "silent": silent, "clipping": clipping, "dc_broken": bool(dc_broken),
            "invalid": bool(silent or clipping or dc_broken),
            "wrap_discontinuity": seam, "click_ratio": click_ratio,
            "loop_clean": (click_ratio is not None and click_ratio <= 3.0)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m tools.audio.gen_music",
        description="Render game music with a local generative audio model.",
    )
    ap.add_argument("--backend", default="stable_audio_open", choices=sorted(BACKENDS))
    ap.add_argument("--prompt", default=None, help="text prompt describing the cue")
    ap.add_argument("--negative", default="", help="negative prompt (stable_audio_open)")
    ap.add_argument("--seconds", type=float, default=30.0)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--steps", type=int, default=100, help="diffusion steps (stable_audio_open)")
    ap.add_argument("--loop-fade", type=int, default=0,
                    help="crossfade MS between tail and head to close the loop")
    ap.add_argument("--out", default=None, help="output .wav path (required to render)")
    ap.add_argument("--analyze", default=None,
                    help="analyse an existing .wav (duration, loudness, loop seam) and exit")
    ap.add_argument("--dtype", default="bfloat16", choices=("float16", "bfloat16", "float32"),
                    help="compute dtype; bfloat16 is the default because fp16 overflows to NaN "
                         "on the ACE-Step checkpoints")
    ap.add_argument("--allow-noncommercial", action="store_true",
                    help="render with a NON-COMMERCIAL/gated backend - experiments only, "
                         "the output must never ship")
    ap.add_argument("--list-backends", action="store_true")
    ap.add_argument("--json", action="store_true", dest="as_json")
    args = ap.parse_args(argv)

    if args.analyze:
        path = Path(args.analyze)
        if not path.is_absolute():
            path = _util.find_root() / path
        if not path.is_file():
            _util.say("no such file: %s" % path)
            return EXIT_PREREQ
        report = {"path": str(path), "verify": describe(path)}
        if args.as_json:
            print(json.dumps(report, indent=2))
        else:
            v = report["verify"]
            _util.say("%s" % path)
            _util.say("  %d bytes  %d Hz  %dch  %.2fs" % (v["bytes"], v["rate"], v["channels"],
                                                          v["seconds"]))
            _util.say("  rms=%.5f peak=%.5f dc=%.6f zcr=%s%s%s%s"
                      % (v["rms"], v["peak"], v["dc_offset"], v["zero_crossing_rate"],
                         "  SILENT" if v["silent"] else "",
                         "  CLIPPING" if v["clipping"] else "",
                         "  DC-BROKEN" if v.get("dc_broken") else ""))
            _util.say("  loop: wrap=%.6f  click_ratio=%.2f (<= 3.0 is clean) -> %s"
                      % (v["wrap_discontinuity"] or 0.0, v["click_ratio"] or 0.0,
                         "CLEAN" if v["loop_clean"] else "AUDIBLE SEAM"))
        return EXIT_FAIL if report["verify"]["invalid"] else EXIT_OK

    if args.list_backends:
        payload = {"backends": BACKENDS,
                   "commercial_ok_licenses": sorted(COMMERCIAL_OK_LICENSES)}
        if args.as_json:
            print(json.dumps(payload, indent=2))
        else:
            for name, spec in sorted(BACKENDS.items()):
                verdict = "SHIPPABLE" if license_ok(name) else "BLOCKED"
                _util.say("%-20s %-11s %-9s license=%-24s gated=%s"
                          % (name, spec["library"], verdict, spec["license"], spec["gated"]))
                _util.say("%-20s repo=%s  native=%d Hz  max=%.0fs"
                          % ("", spec["repo"], spec["native_rate"], spec["max_seconds"]))
                _util.say("%-20s %s" % ("", spec["provenance"]))
                if not license_ok(name):
                    _util.say("%-20s -> %s" % ("", blocked_reason(name)))
            _util.say("")
            _util.say("Shipping allowlist: %s" % ", ".join(sorted(COMMERCIAL_OK_LICENSES)))
            _util.say("A BLOCKED backend needs --allow-noncommercial and its output must never ship.")
        return EXIT_OK

    if not args.prompt or not args.out:
        _util.say("--prompt and --out are both required to render (see --list-backends)")
        return EXIT_PREREQ

    # licence gate: refuse to render a cue that could not legally ship
    if not license_ok(args.backend) and not args.allow_noncommercial:
        _util.say("REFUSING to render with backend %r: %s"
                  % (args.backend, blocked_reason(args.backend)))
        _util.say("Use a shippable backend: %s"
                  % ", ".join(n for n in sorted(BACKENDS) if license_ok(n)))
        _util.say("(--allow-noncommercial renders anyway, for throwaway experiments only)")
        return EXIT_PREREQ
    if not license_ok(args.backend):
        _util.say("WARNING: %s is NOT shippable (%s) - this render is an experiment"
                  % (args.backend, blocked_reason(args.backend)))

    try:
        import torch
    except ImportError:
        _util.say("torch is not installed in this interpreter - run this tool with "
                  ".venv-audio/Scripts/python.exe (see docs/STUDIO.md)")
        return EXIT_PREREQ
    if not torch.cuda.is_available():
        _util.say("CUDA is not available to torch - refusing to render on CPU (hours per cue)")
        return EXIT_PREREQ

    import numpy as np

    dtype = {"float16": torch.float16, "bfloat16": torch.bfloat16,
             "float32": torch.float32}[args.dtype]
    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = _util.find_root() / out_path

    _util.say("backend %s  prompt %r  %.0fs  seed %d  steps %d  dtype %s"
              % (args.backend, args.prompt, args.seconds, args.seed, args.steps, args.dtype))
    started = time.time()
    try:
        samples, rate = RENDERERS[args.backend](args.prompt, args.seconds, args.seed,
                                                args.steps, args.negative, dtype)
    except Exception as exc:                                  # noqa: BLE001
        import traceback
        traceback.print_exc()
        _util.say("render FAILED: %s: %s" % (type(exc).__name__, exc))
        return EXIT_FAIL

    # A degenerate decode must never reach the disk as an asset.  fp16 on the
    # ACE-Step checkpoints overflows to NaN, and an int16 write then turns that
    # into a silent full-scale DC block - which "looks" like audio to a naive
    # loudness check.  Catch it here, retry once in a safe dtype, then give up.
    if not np.isfinite(samples).all():
        bad = int((~np.isfinite(samples)).sum())
        _util.say("  degenerate output: %d non-finite sample(s) in %s" % (bad, args.dtype))
        if args.dtype == "float16":
            _util.say("  retrying once in bfloat16 (fp16 overflow on this checkpoint)")
            try:
                samples, rate = RENDERERS[args.backend](args.prompt, args.seconds, args.seed,
                                                        args.steps, args.negative,
                                                        torch.bfloat16)
            except Exception as exc:                          # noqa: BLE001
                _util.say("  retry FAILED: %s: %s" % (type(exc).__name__, exc))
                return EXIT_FAIL
            if not np.isfinite(samples).all():
                _util.say("  retry also produced non-finite samples - not writing an asset")
                return EXIT_FAIL
        else:
            _util.say("  not writing an asset from a degenerate decode; try --dtype float32")
            return EXIT_FAIL
    elapsed = time.time() - started
    peak_vram = torch.cuda.max_memory_allocated() / (1024 ** 2)

    written = write_wav(out_path, samples, rate)
    loop = None
    if args.loop_fade > 0:
        loop = make_loop(out_path, args.loop_fade, written["rate"])
    report = {"backend": args.backend, "repo": BACKENDS[args.backend]["repo"],
              "license": BACKENDS[args.backend]["license"],
              "shippable": license_ok(args.backend),
              "prompt": args.prompt, "seed": args.seed, "steps": args.steps,
              "elapsed_s": round(elapsed, 2), "peak_vram_mib": int(peak_vram),
              "device": torch.cuda.get_device_name(0), "loop": loop, **written}
    report["verify"] = describe(out_path)
    report["cmd"] = ("python -m tools.audio.gen_music --backend %s --seed %d --seconds %.0f "
                     "--steps %d --prompt %r --out %s"
                     % (args.backend, args.seed, args.seconds, args.steps, args.prompt,
                        _util.rel_posix(out_path, _util.find_root())))

    if args.as_json:
        print(json.dumps(report, indent=2))
    else:
        _util.say("rendered in %.2fs (peak VRAM %d MiB) -> %s" % (elapsed, peak_vram,
                                                                 _util.rel_posix(out_path, _util.find_root())))
        v = report["verify"]
        _util.say("  %d bytes  %d Hz  %dch  %.2fs  rms=%.5f peak=%.5f%s%s%s"
                  % (v["bytes"], v["rate"], v["channels"], v["seconds"], v["rms"], v["peak"],
                     "  SILENT!" if v["silent"] else "",
                     "  CLIPPING!" if v["clipping"] else "",
                     "  DC-BROKEN!" if v.get("dc_broken") else ""))
        if loop:
            _util.say("  loop crossfade: %s" % loop)
    return EXIT_FAIL if report["verify"]["invalid"] else EXIT_OK


if __name__ == "__main__":
    sys.exit(_util.guard(main)())
