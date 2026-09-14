"""audio-audit: every shipped cue must be licensed, present and actually audible.

    python -m tools.qa.audio_audit
    python -m tools.qa.audio_audit --json

This is the half of the licence policy that runs on **every build**. `gen_music`
refuses to *render* with a non-shippable backend; this tool refuses to let a
non-shippable file *ship* — it reads the shipped artefacts themselves, with the
stdlib only (no torch, no soundfile), so it belongs in the game venv and in
`tools.selftest`.

Checks per manifest entry in ``game/data/audio.json``:

* required fields present (`id`, `file`, `model`, `license`, `seed`, `loop`, `gain`)
* the declared licence is on the shipping allowlist
* the file exists under ``assets/audio/``
* the file is real audio: non-zero duration, not silent, not clipping
* loop cues pass the wrap-discontinuity check (a click at the seam is a bug)

Exit status: 0 all cues valid (or no manifest yet), 1 a cue failed a check,
2 the manifest is unreadable.
"""

from __future__ import annotations

import argparse
import array
import json
import sys
import wave
from pathlib import Path

from tools import _util  # noqa: E402
from tools._util import EXIT_FAIL, EXIT_OK, EXIT_PREREQ  # noqa: E402

MANIFEST = "game/data/audio.json"
AUDIO_DIR = "assets/audio"

#: Where the cue ids are used, so a missing cue is caught.  Kept next to the
#: allowlist because both are policy, not preference.
REQUIRED_FIELDS = ("id", "file", "model", "license", "seed", "loop", "gain")
SILENT_RMS = 1e-4
MIN_RMS = 5e-3
CLICK_RATIO_MAX = 3.0


def _allowlist() -> set[str]:
    """The shipping allowlist, read from the generator (single source of truth)."""
    from tools.audio import gen_music
    return set(gen_music.COMMERCIAL_OK_LICENSES)


def read_wav(path: Path) -> dict:
    """Decode a PCM wav with the stdlib: duration, rms, peak, wrap discontinuity."""
    with wave.open(str(path), "rb") as fh:
        channels = fh.getnchannels()
        width = fh.getsampwidth()
        rate = fh.getframerate()
        frames = fh.getnframes()
        raw = fh.readframes(frames)
    if width != 2:
        return {"error": "unsupported sample width %d bytes (expected 16-bit PCM)" % width}
    samples = array.array("h")
    samples.frombytes(raw[: (len(raw) // 2) * 2])
    if not samples:
        return {"error": "no samples"}
    peak = max(abs(s) for s in samples) / 32768.0
    mean_sq = sum((s / 32768.0) ** 2 for s in samples) / len(samples)
    rms = mean_sq ** 0.5
    # mono fold for the seam measure
    mono = samples[::channels] if channels > 1 else samples
    wrap = abs(mono[0] - mono[-1]) / 32768.0
    diffs = sorted(abs(mono[i + 1] - mono[i]) for i in range(0, len(mono) - 1, max(1, len(mono) // 4000)))
    p95 = (diffs[int(len(diffs) * 0.95)] / 32768.0) if diffs else 0.0
    return {
        "rate": rate, "channels": channels,
        "seconds": round(frames / float(rate), 3),
        "rms": round(rms, 5), "peak": round(peak, 5),
        "wrap_discontinuity": round(wrap, 6),
        "click_ratio": round(wrap / p95, 3) if p95 > 0 else None,
    }


def audit(root: Path, manifest_rel: str = MANIFEST, audio_rel: str = AUDIO_DIR) -> dict:
    path = root / manifest_rel
    if not path.is_file():
        return {"manifest": manifest_rel, "present": False, "cues": [], "problems": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"manifest": manifest_rel, "present": True, "unreadable": str(exc),
                "cues": [], "problems": ["manifest unreadable: %s" % exc]}

    entries = data.get("manifest", data.get("entries", [])) if isinstance(data, dict) else data
    if not isinstance(entries, list):
        return {"manifest": manifest_rel, "present": True, "cues": [],
                "problems": ["manifest must be {\"entries\": [...]} - got %s"
                             % type(entries).__name__]}

    allow = _allowlist()
    cues, problems = [], []
    for entry in entries:
        if not isinstance(entry, dict):
            problems.append("entry is %s, expected an object" % type(entry).__name__)
            continue
        cue_id = entry.get("id") or "<no id>"
        missing = [f for f in REQUIRED_FIELDS if entry.get(f) in (None, "")]
        if missing:
            problems.append("%s: missing field(s) %s" % (cue_id, ", ".join(missing)))
        licence = str(entry.get("license", ""))
        if licence and licence not in allow:
            problems.append("%s: licence %r is not shippable (allowlist: %s)"
                            % (cue_id, licence, ", ".join(sorted(allow))))
        file_rel = entry.get("file") or ""
        # manifest entries may carry a bare filename OR a repo-relative path; accept
        # both and resolve against the project root so the same entry works either way
        wav = None
        if file_rel:
            candidate = root / file_rel
            wav = candidate if candidate.is_file() else root / audio_rel / Path(file_rel).name
        info: dict = {}
        if wav is None or not wav.is_file():
            problems.append("%s: file not found (%s)"
                            % (cue_id, _util.rel_posix(candidate, root) if file_rel else "<no file>"))
        else:
            try:
                info = read_wav(wav)
            except (wave.Error, OSError, ValueError) as exc:
                problems.append("%s: cannot decode %s (%s)" % (cue_id, wav.name, exc))
                info = {}
            else:
                if "error" in info:
                    problems.append("%s: %s" % (cue_id, info["error"]))
                else:
                    if info["seconds"] <= 0.1:
                        problems.append("%s: only %.2fs long" % (cue_id, info["seconds"]))
                    if info["rms"] < SILENT_RMS:
                        problems.append("%s: SILENT (rms %.5f)" % (cue_id, info["rms"]))
                    elif info["rms"] < MIN_RMS:
                        problems.append("%s: barely audible (rms %.5f < %.3f)"
                                        % (cue_id, info["rms"], MIN_RMS))
                    if info["peak"] >= 0.999:
                        problems.append("%s: CLIPPING (peak %.5f)" % (cue_id, info["peak"]))
                    if entry.get("loop") and info.get("click_ratio") is not None:
                        if info["click_ratio"] > CLICK_RATIO_MAX:
                            problems.append("%s: audible loop seam (click_ratio %.2f > %.1f)"
                                            % (cue_id, info["click_ratio"], CLICK_RATIO_MAX))
        cues.append({"id": cue_id, "file": file_rel, "model": entry.get("model"),
                     "license": licence, "loop": bool(entry.get("loop")), "verify": info})
    return {"manifest": MANIFEST, "present": True, "cues": cues, "problems": problems}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m tools.qa.audio_audit",
        description="Validate shipped audio cues: licence, presence, loudness, loop seam.",
    )
    ap.add_argument("--json", action="store_true", dest="as_json")
    ap.add_argument("--manifest", default=MANIFEST,
                    help="manifest path relative to the repo root (default %s)" % MANIFEST)
    ap.add_argument("--audio-dir", default=AUDIO_DIR,
                    help="cue directory relative to the repo root (default %s)" % AUDIO_DIR)
    ap.add_argument("--root", default=None,
                    help="treat this directory as the project root (staging/audit only)")
    args = ap.parse_args(argv)

    root = Path(args.root) if args.root else _util.find_root()
    sys.path.insert(0, str(_util.find_root()))
    report = audit(root, args.manifest, args.audio_dir)

    if "unreadable" in report:
        if args.as_json:
            print(json.dumps({"ok": False, **report}, indent=2))
        else:
            _util.say("audio-audit: %s is unreadable (%s)" % (report["manifest"],
                                                              report["unreadable"]))
        return EXIT_PREREQ
    if not report["present"]:
        if args.as_json:
            print(json.dumps({"ok": True, **report}, indent=2))
        else:
            _util.say("audio-audit: no %s yet - no cues to check" % report["manifest"])
        return EXIT_OK

    rc = EXIT_FAIL if report["problems"] else EXIT_OK
    if args.as_json:
        print(json.dumps({"ok": rc == EXIT_OK, **report}, indent=2))
        return rc

    _util.say("audio-audit: %d cue(s) in %s" % (len(report["cues"]), report["manifest"]))
    for cue in report["cues"]:
        v = cue.get("verify") or {}
        detail = ("%.2fs rms=%s peak=%s click=%s" % (v.get("seconds", 0), v.get("rms"),
                                                     v.get("peak"), v.get("click_ratio"))
                  if v and "error" not in v else "unverified")
        _util.say("  %-22s %-28s %-8s %s" % (cue["id"], cue["model"] or "?", cue["license"], detail))
    for problem in report["problems"]:
        _util.say("  [FAIL] %s" % problem)
    _util.say("OK: every shipped cue is licensed and audible" if rc == EXIT_OK
              else "FAILED: %d problem(s) - those cues must not ship" % len(report["problems"]))
    return rc


if __name__ == "__main__":
    sys.exit(_util.guard(main)())
