"""Head-to-head benchmark for local vision models on THIS studio's real task.

Why it exists: a VLM that writes a confident critique is not evidence that it can see.
This asks questions with KNOWN answers about the sprite contact sheet (counts, colours,
presence of a measured defect) so two models can be compared on facts rather than prose,
and it writes its evidence to JSON including the sheet's sha256 so runs stay comparable.

Usage:
    python -m tools.qa.vlm_bench                      # every candidate
    python -m tools.qa.vlm_bench qwen/qwen3-vl-8b     # one model (the box holds one at a time)

Results: %TEMP%/rw_vlm_bench_results.json  (append-safe: one record per model)
Verdicts and the full claim ledger: docs/MODELS.md
"""
import base64
import json
import os
import subprocess
import sys
import time
import urllib.request

ENDPOINT = "http://localhost:1234/v1/chat/completions"
IMG = os.environ.get("RW_BENCH_SHEET") or os.path.join(
    os.environ.get("TEMP", "."), "rw_sprite_contact.png")   # the sheet sprite_critique produces
LMS = os.path.expanduser("~/.lmstudio/bin/lms.exe")
# Budget for a THINKING model: it bills reasoning against max_tokens, so a tight
# budget yields empty content and a false "cannot see" verdict.
MAX_TOKENS = 2048

# ground truth from how the sheet was generated (see tools/qa/sprite_critique.py):
#   197 frames, 16 columns, 13 rows, last row partial with 5
#   tile plate colour (70, 64, 86)  |  6 flat-rectangle props exist
QUESTIONS = [
    ("row1", "How many sprites are in the TOP row? Answer with just a number."),
    ("lastrow", "How many sprites are in the BOTTOM (last) row? Just a number."),
    ("plate", "What colour are the square plates behind each sprite? One or two words."),
    ("dupes", "Do any sprites look visually identical to each other? Answer yes or no, "
              "then name at most two pairs."),
    ("flat", "Are any of these sprites flat solid rectangles rather than pictures of objects? "
             "Answer yes or no."),
]
EXPECT = {
    "row1": lambda t: "16" in t,
    "lastrow": lambda t: "5" in t.split("\n")[0] or t.strip().startswith("5"),
    "plate": lambda t: any(w in t.lower() for w in ("grey", "gray", "purple", "violet", "dark")),
    "dupes": lambda t: t.strip().lower().startswith("yes") or "yes" in t[:40].lower(),
    "flat": lambda t: t.strip().lower().startswith("yes") or "yes" in t[:40].lower(),
}

CRITIQUE = (
    "You are the art director for a top-down roguelite. Sprites are hard-edged pixel art on a "
    "26-colour palette; anti-aliasing is a DEFECT here, never a fix. In 3 short bullets: which "
    "sprites are unreadable blobs, which are near-duplicates, and the single best in-medium "
    "improvement."
)


def lms(*args, timeout=600):
    try:
        return subprocess.run([LMS, *args], capture_output=True, text=True, timeout=timeout)
    except Exception as exc:                                     # noqa: BLE001
        print("   lms %s failed: %s" % (args[0], exc))
        return None


def ask(model, prompt, b64, max_tokens=2048):
    body = {"model": model, "messages": [{"role": "user", "content": [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64," + b64}}]}],
        "max_tokens": max_tokens, "temperature": 0.1}
    req = urllib.request.Request(ENDPOINT, data=json.dumps(body).encode(),
                                headers={"Content-Type": "application/json"})
    started = time.time()
    with urllib.request.urlopen(req, timeout=900) as resp:
        data = json.loads(resp.read().decode())
    choice = data["choices"][0]
    msg = choice.get("message") or {}
    usage = data.get("usage", {}) or {}
    # A THINKING model bills its reasoning against max_tokens. Measured: glm-4.6v-flash
    # returned content='' with finish_reason=length and 299/300 tokens in
    # reasoning_content, mid-sentence - which scored 0/5 and looked like a vision
    # failure when it was a budget failure. Report it instead of guessing.
    return {"text": msg.get("content") or "",
            "reasoning": msg.get("reasoning_content") or msg.get("reasoning") or "",
            "finish": choice.get("finish_reason"),
            "elapsed": time.time() - started,
            "usage": usage,
            "reasoning_tokens": (usage.get("completion_tokens_details") or {}).get("reasoning_tokens", 0)}


def bench(model):
    print("=" * 74)
    print("MODEL: %s" % model)
    lms("unload", "--all")
    load = lms("load", model, "--gpu", "max", "-c", "8192")
    if load is None or load.returncode != 0:
        print("  could not load:", (load.stderr or load.stdout or "")[:200])
        return None
    with open(IMG, "rb") as fh:
        b64 = base64.b64encode(fh.read()).decode()

    combined = "You are looking at a contact sheet of 2D game sprites. Answer each question " \
               "tersely, numbered 1-5.\n" + "\n".join("%d. %s" % (i + 1, q) for i, (_, q) in
                                                      enumerate(QUESTIONS))
    r = ask(model, combined, b64, max_tokens=MAX_TOKENS)
    text, usage = r["text"], r["usage"]
    print("  answers in %.1fs (%s tokens, finish=%s, reasoning=%s):"
          % (r["elapsed"], usage.get("total_tokens"), r["finish"], r["reasoning_tokens"]))
    if not text.strip():
        print("     [EMPTY content] the model returned no answer text.")
        if r["reasoning_tokens"]:
            print("     DIAGNOSIS: %d reasoning tokens consumed the %d-token budget - raise "
                  "--max-tokens (this is a harness limit, NOT a vision failure)"
                  % (r["reasoning_tokens"], MAX_TOKENS))
        elif r["reasoning"]:
            print("     DIAGNOSIS: text went to reasoning_content: %r" % r["reasoning"][:120])
    for line in text.splitlines():
        if line.strip():
            print("     %s" % line.strip()[:96])

    # score each question against its known answer, matching by position
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    correct = 0
    for i, (key, _) in enumerate(QUESTIONS):
        segment = ""
        for ln in lines:
            if ln.lstrip("*- ").startswith(str(i + 1)):
                segment = ln
                break
        if not segment:
            segment = text
        ok = EXPECT[key](segment)
        correct += 1 if ok else 0
        print("     [%s] Q%d %s" % ("OK " if ok else "MISS", i + 1, key))
    print("  SCORE: %d/%d known answers" % (correct, len(QUESTIONS)))

    cr = ask(model, CRITIQUE, b64, max_tokens=max(700, MAX_TOKENS))
    crit, celapsed, cusage = cr["text"], cr["elapsed"], cr["usage"]
    print("  critique in %.1fs:" % celapsed)
    for line in crit.splitlines():
        if line.strip():
            print("     %s" % line.strip()[:96])
    lms("unload", "--all")
    return {"model": model, "max_tokens": MAX_TOKENS, "answer_latency_s": round(r["elapsed"], 1),
            "answer_finish": r["finish"], "reasoning_tokens": r["reasoning_tokens"],
            "answer_raw": text[:2000], "answer_empty": not text.strip(),
            "critique_latency_s": round(celapsed, 1), "critique_raw": crit[:3000],
            "critique_empty": not crit.strip(), "score": correct,
            "total": len(QUESTIONS)}


results = []
for _i, _a in enumerate(sys.argv):
    if _a == "--max-tokens" and _i + 1 < len(sys.argv):
        MAX_TOKENS = int(sys.argv[_i + 1])
_only = [a for a in sys.argv[1:] if not a.startswith("-") and not a.isdigit()]
for m in (_only or ("qwen2.5-vl-7b-instruct", "qwen/qwen3-vl-8b")):
    try:
        r = bench(m)
        if r:
            results.append(r)
    except Exception as exc:                                     # noqa: BLE001
        print("  FAILED: %s: %s" % (type(exc).__name__, exc))

print("=" * 74)
print("SUMMARY")
for r in results:
    print("  %-26s score %d/%d   answers %.1fs   critique %.1fs"
          % (r["model"], r["score"], r["total"], r["answer_latency_s"], r["critique_latency_s"]))

# Evidence file: merge, never clobber - a rerun of one model must not erase the other
# model's measured record, and the dump runs even if a later model fails to load.
import hashlib
_blob = open(IMG, "rb").read()
_dest = os.path.join(os.environ.get("TEMP", "."), "rw_vlm_bench_results.json")
try:
    with open(_dest, encoding="utf-8") as _fh:
        _doc = json.load(_fh)
except Exception:
    _doc = {}
_doc["sheet"] = IMG
_doc["sheet_sha256"] = hashlib.sha256(_blob).hexdigest()
_doc["sheet_bytes"] = len(_blob)
_doc["questions"] = [k for k, _ in QUESTIONS]
_records = [r for r in _doc.get("results", []) if r.get("model") not in {r2["model"] for r2 in results}]
_doc["results"] = _records + results
# Atomic: build the whole document, then replace. Opening the target for write first
# truncates it, so a failure mid-dump destroys the evidence you already had.
_tmp = _dest + ".tmp"
with open(_tmp, "w", encoding="utf-8") as _fh:
    json.dump(_doc, _fh, indent=2)
os.replace(_tmp, _dest)
print("wrote %s (%d model record(s) kept)" % (_dest, len(_doc["results"])))
