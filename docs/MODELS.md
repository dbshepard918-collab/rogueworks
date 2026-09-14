# MODELS — the measured roster (audited 2026-09-13)

Every pin in this studio is a measurement, not a preference. This file is the record of what was
measured, on this machine, on 2026-09-13, and why each bot sits where it sits. Re-audit before
changing a pin; free tiers and local load times move.

Method: a live probe harness that sends a **3-step agentic chain** with real tools —
`read_file` → `write_file` (using the tool result) → `run_tests` — plus a second pass with
`tool_choice="required"` to separate "cannot emit a tool call" from "chose not to".
A model that fails the chain cannot hold a bot seat here, however good its prose is.
Harness: `$TEMP/model_audit/probe3_local.py`, `probe4_verify.py`, `probe5_cloud.py`, `probe6_roster.py`.
Raw results: `$TEMP/model_audit/*.json`.

## The rate-limit reality (why the old pins were failing)

| Pool | Measured limit | Verdict for this studio |
|---|---|---|
| OpenRouter `:free` | **50 free-model requests per DAY** (`X-RateLimit-Limit: 50`), 0 credits on the key | **Unusable as a primary.** One round is 69–278 tool calls = 69–278 requests. Exhausted by mid-morning, every day. |
| Nous portal `:free` | 400 requests/min; burst of 12 → 3× `429` with `retry-after: 30`; ~1.78M tokens/min fairshare | Fine as a primary. 429s are transient and `retry-after` is honoured. |
| HuggingFace router | `x-ratelimit-limit-requests` **2000–6000** per model (GLM-5.3-Flash 2000, DeepSeek-V4.1-Flash 6000, Qwen3-Coder-30B 600), `x-ratelimit-limit-tokens` up to 50M; tool calls verified through hermes in 4s | Good extra pool — but the account is **non-PRO with `canPay: false`**, i.e. credit-METERED with no top-up path. Use it as a middle link, never the last one. |
| OpenCode Zen (keyless) | no account needed; `ling-3.0-flash-fin-free` answered a real tool call in 7.1s; `laguna-s-2.1-free` 401s ("not supported"); `nemotron-3.5-lightning-free` hung past 300s | Spare only. Two of three models are broken; `hermes -m <model> --provider opencode-free` is the way to drive it (raw HTTP hits Cloudflare 1010 / MissingSessionID). |
| LM Studio local | none — it is your GPU | The only pool that can never rate-limit. Always the end of a chain. |

`upstage/solar-pro4:free` (forge's old pin) returned **429 "temporarily at capacity upstream" on the
first request** of the audit, as did `poolside/laguna-s-2.1:free`. That is the single largest cause
of 0-tool-call / timed-out rounds.

## The 12 GB truth (why the bots cannot all be resident)

Measured VRAM with the model loaded at the context Hermes is configured for (65536), card total 12227 MiB,
desktop baseline ~600–950 MiB:

| Model | 32K ctx | 64K ctx | tok/s @64K | 3-step chain |
|---|---|---|---|---|
| `qwen/qwen3-8b` | 10275 MiB | **11598 MiB** | **23.1** | PASS |
| `google/gemma-4-12b-qat` | 10130 MiB | 10524 MiB | 20.0 | PASS |
| `qwen/qwen3-vl-8b` | 11406 MiB | 11566 MiB | 7.5 | PASS |
| `qwen/qwen3-14b` | 11519 MiB | — | — | PASS |
| `qwen/qwen3-coder-30b` | 11484 MiB | — | 5.5 (68s load) | PASS |
| `openai/gpt-oss-20b` | 11813 MiB | — | 11.4 | PASS |

**One model at a time. That is the whole story on 12 GB.** A single 8B at Hermes' 64K context leaves
~600 MiB free — there is no second slot, so any "keep two workers resident" plan is false on this
box. LM Studio reloads a swapped model in 5–16 s, so the pipeline is *load-order*, not residency.

## Disqualified by measurement (cannot emit a tool call, even when forced)

`qwen/qwen2.5-coder-14b` · `mistralai/ministral-3-14b-reasoning` (can when forced, chose not to when
free) · `qwen2.5-vl-3b-instruct` · `qwen2.5-vl-7b-instruct` (see below) · `minicpm-v-4_5` ·
`internvl3_5-8b` · `glm-4.1v-9b-thinking` · `deepseek/deepseek-r1-0528-qwen3-8b` · `ui-tars-7b-dpo` ·
`holo1.5-7b` · `qwen/qwen3-vl-4b-instruct` (does not load)

### Vision: why the pin stays `qwen/qwen3-vl-8b`

The 7B Qwen2.5-VL was benchmarked head-to-head against the pin on the studio's real job (the sprite
contact sheet), scored on **verifiable answers** — counts, colours, and the presence of a known
defect — because prose quality cannot be scored honestly. Harness: `python -m tools.qa.vlm_bench [model]` (versioned in the repo; merge-writes its
per-question answers plus the sheet hash to `%TEMP%/rw_vlm_bench_results.json`).

**Latency caveat:** only one model fits on the card and the VLM is shared with the other bots, so
the second numbers below were taken while other agents were queued on the same endpoint. Treat the
**scores** as the finding and the **latencies** as indicative only.

| Question (known answer) | `qwen2.5-vl-7b-instruct` | `qwen/qwen3-vl-8b` |
|---|---|---|
| sprites in the top row (16) | 8 ✗ | 16 ✓ |
| sprites in the last row (5) | 7 ✗ | 16 ✗ |
| plate colour behind sprites (dark grey) | "white and blue" ✗ | "dark gray" ✓ |
| duplicate sprites present (yes) | "yes" ✓ | "yes" ✓ |
| flat solid rectangles present (yes, 6) | **"no" ✗** | "yes" ✓ |
| **score** | **1/5** (its only successful run) | **4/5, reproduced in 6 separate runs** |
| answer / critique latency | 7.9 s / 15.3 s | 3.2–4.1 s / 4.4–6.2 s |

**It also does not reliably load.** On the retry `lms load qwen2.5-vl-7b-instruct --gpu max -c 8192`
timed out after **600 s**. On a box that holds one model at a time, swap cost *is* part of the model's
cost — a model that cannot be loaded cannot serve as a fallback, regardless of quality.

The challenger is ~2× slower, blind to the one defect class this studio exists to catch, and did not
load on demand. Sheet size matters as much as the model: the same critique took **77 s at
2116×1896** and 4.4–6.2 s at 1092×888. Evidence (`python -m tools.qa.vlm_bench qwen/qwen3-vl-8b`) pins the exact
sheet — canonical `rw_sprite_contact.png`, 197 cells, `sha256 58894dcb…` — so a future run is
comparable rather than merely similar.

Do **not** draw index numbers on a contact sheet to make findings citable. Measured: the model then
regurgitates `1, 2, 3, ... 188` instead of judging art — the labels become the task. Ask for
"row R, column C" instead and resolve it with `cell_for_position()`.

#### VLM claim ledger — every specific claim, tested

A VLM is a **lead generator, not an authority**. Score it: run each concrete claim through a
measurement before acting on it. Current tally on this project, all tests re-runnable:

| VLM claim | Test that settled it | Verdict |
|---|---|---|
| "stray pixels in a few sprites" | connected components (`sprite_critique`) | ✅ **TRUE** — found 43 fragmented sprites / 241 debris px, invisible to every existing check |
| "sprites are anti-aliased" | partial-alpha share | ❌ **FALSE** — 0.00% partial-alpha; the art is hard-edged by construction |
| "add anti-aliasing / softer edges" | house rule vs `art.verify` | ❌ **FALSE** — would break the 26-colour hard-edge contract |
| `monster_ember_imp_elite` ≈ `monster_flame_djinn` | silhouette IoU | ❌ **FALSE** — 0.649 (threshold 0.92) |
| `monster_tide_caller` ≈ `monster_tide_shield` | silhouette IoU | ❌ **FALSE** — 0.447 |
| `prop_chain` ≈ `prop_chains` | silhouette IoU | ❌ **FALSE** — 0.315 … **but the lead found a real orphan frame (P0.6)** |
| R3C5 `monster_hive_splitter` reads as an unreadable blob | IoU vs the measured trio | ✅ **TRUE** — it is one of the 3 confirmed silhouette duplicates |
| "nothing looks like a resized photo / gradient" | `art.verify` palette + partial-alpha | ✅ **TRUE** |
| "9/10 — reads as deliberate game art" | objective defect count | ⚠️ **DISAGREES** — the same round measures 24 objective defects; self-scores are not evidence |
| "anti-aliasing artifacts on the health/mana orbs" (2nd & 3rd time it raised anti-aliasing) | partial-alpha share | ❌ **FALSE** — 0.00% partial-alpha; it repeats this because it "knows" what game art looks like, not because it looked |
| names sprites it cannot know: "Cursed", "Wisp", "Sword", "Dagger", "health/mana orbs" | the sheet carries **no labels** | ❌ **FABRICATED** — it invents plausible names for an unlabelled sheet; never quote a VLM's sprite name, always resolve a position |
| "worst unreadable" picks: top row 3rd–4th from right, then R3C1–R3C5, then top row 3rd–4th again | same input, three runs | ⚠️ **UNSTABLE** — the specific picks move between runs; treat a claim as a lead to check, never as a finding |
| `glm-4.6v-flash`: "excessive anti-aliasing artifacts (blurred edges/color bleed)" | partial-alpha share | ❌ **FALSE** — 0.00% partial-alpha. That is now the **4th** time a VLM has raised anti-aliasing here; it is a prior about what game art "should" look like, not an observation of this art |
| `glm-4.6v-flash` names "question mark icon", "horse pair", "boot pair", "health/mana orbs" | the sheet carries no labels and contains no such sprites | ❌ **FABRICATED** — same invention pattern as the other candidates |

Tally: **3 true, 8 false, 1 unstable.** Verdicts on *its own* advice ("add anti-aliasing") are wrong
far more often than its observations — never let it set the house rules, and always give it the house
rules in the prompt.

Note `qwen2.5-coder-14b` and `ui-tars-7b-dpo` were both recommended to the owner by an external
advisor; both fail the first tool call with real tools attached.

## Candidate assessment — 2026-09-14 (owner-added models)

Five models the owner added, each measured on the harness for the lane it could serve. Numbers, not
opinions; re-runnable with the commands given.

| Model | Lane | Verdict | Measured |
|---|---|---|---|
| `essentialai/rnj-1` | coder (chip) | **trial it** | **40–45 tok/s** (40.1 avg @150 tokens, 45.1 best @200), ~6.6 GiB VRAM, 3.7 s load @8K. Incumbent `qwen/qwen3-coder-30b`: 5.5 tok/s, 18.63 GB, 68 s load. ~8× throughput and the card stays free — but speed is not code quality, so it needs one real edit before any pin moves. Evidence: `%TEMP%/rw_bench_local.json` |
| `zai-org/glm-4.6v-flash` | vision | **No — 3/5, and blind to broken frames** | Sheet bench: **3/5 on a complete reply** (`finish=stop`, reproduced twice) vs the pin's 4/5 (8 runs); Q1 off by one, **Q5 wrong — it denies the flat-rectangle defect**. Frame bench (quality, ground-truthed) is the decider: it rates an **unplayable** frame (34% visible tiles, mean luminance 15 — the exact "unplayable" bug signature) at **7/10 readable**, classification **1/3** vs the pin's 2/3. 13-27 s per frame. ⚠️ An earlier "2/5" in this file was **my harness truncating its reply** — see the correction note. |
| `allenai/olmocr-2-7b` | vision | no | 1/5, generic critique. A document-OCR model — `qwen2vl` arch does not make it a sprite critic. |
| `google/gemma-3-27b` | text | no — **1.3 tok/s** | At 4K context: 74.9 s load, warm-up **158.8 s for 200 tokens = 1.3 tok/s**, 3 runs all 1.3. `qwen/qwen3-8b` does 23.1 tok/s and `gemma-4-12b-qat` 20.0 — ~18× slower, before Hermes' required 64K context. **Two instruments disagree on its footprint:** `bench_local` reports 11,408 MiB after load (11,586 in the summary) against a 12,227 MiB card, while `lms load` reports 15.30 GiB — either way it has no room left for a second model, and 64K cannot fit. |
| `darkmaniac7/TokForge-DreamShaper-LCM-GGUF-q4` | art generation | no — licence | `Lykon/dreamshaper-7` is **creativeml-openrail-m** (registry-verified); our shipping art model is **apache-2.0**. Refused, not wired — see `docs/ART-LICENSES.md`. Needs an SD1.5 VAE regardless. |

Reproduce:

```
python -m tools.qa.vlm_bench <model>                    # vision, known-answer scored
python -m tools.studio.bench_local --model <m> --context 8192   # tok/s + VRAM + load
python -m tools.art.gen --licence-board                 # which art models may ship
```

`bench_local` writes every measurement to `%TEMP%/rw_bench_local.json` (merge-keyed by
`model@context`), so a number quoted here can be re-read instead of re-argued. A rerun at a different
`--tokens` gives a slightly different rate — quote the range, not one lucky run.

### Two traps these measurements set for the measurer

1. **A thinking model bills reasoning against `max_tokens`.** `glm-4.6v-flash` scored **0/5** at a
   300-token budget with `content: ''` and `finish_reason: length` — every token in
   `reasoning_content`. At 2048 it scored 3/5. That is a harness limit, not blindness, and the
   harness now says so in words.
2. **`bench_local`'s default 64K context** makes a model that does not fit look like a model that is
   broken (`HTTP Error 400`). Try `--context 8192` before recording a failure.

#### Quality, not speed: can either model tell a broken frame from a playable one?

Speed was never the deciding axis. `tools/qa/vlm_frame_bench` renders one real frame, degrades it by
known factors (the same multiply-the-frame mechanism behind the original "floor 1 is unplayable" bug),
labels each variant with the numeric legibility gate, and asks the model to rate readability 0-10.
Ground truth and both models, one run:

| frame | ground truth | `qwen3-vl-8b` (pin) | `glm-4.6v-flash` |
|---|---|---|---|
| x1.00 | mean_lum 49.0, **100%** tiles, gate **PASS** | 7.0 ✓ | 8.0 ✓ |
| x0.55 | mean_lum 27.2, 76% tiles, gate **FAIL** | 5.0 (borderline) | **8.0 ✗** |
| x0.30 | mean_lum 15.0, **34%** tiles, gate **FAIL** | 3.0 ✓ | **7.0 ✗** |
| | ordering monotonic | YES | YES (barely) |
| | **classification vs the gate** | **2/3** | **1/3** |

**GLM rates the unplayable frame 7/10 — "readable".** That frame is 34% visible tiles at mean luminance
15, the exact signature of the bug the owner reported as "looks like trash". For the one job the studio
needs a vision model to do — look at a rendered frame and say whether it is playable — GLM cannot
separate broken from good, and it never produced the tile-coverage number at all (the pin's estimates
run 60/30/20 against the true 100/76/34: understated, but directionally right).

So the rejection is **quality, not throughput**: 13-27 s per frame and blind to the defect class. The
pin also misses the middle frame (5.0 on a FAIL), which is the useful part of this result — **neither
VLM is an authority.** `scene_legibility` stays the gate; a VLM is a second opinion that must be
calibrated against ground truth before anyone acts on it.

Reproduce: `python -m tools.qa.vlm_frame_bench qwen/qwen3-vl-8b zai-org/glm-4.6v-flash --max-tokens 8192`
→ `%TEMP%/rw_frame_bench.json`.

#### Correction (same round): "2/5" for glm-4.6v-flash was a truncated reply

I first recorded glm-4.6v-flash as **2/5**, then read the persisted raw answer:

```
1. 16          <- correct
2. 5           <- correct
(finish_reason: length - 2035 reasoning tokens consumed the 2048 budget here)
```

It was **cut off mid-answer** before reaching questions 3-5. Both answers it gave were right, and the
score said otherwise. Re-run with `--max-tokens 8192` (`finish=stop`, complete):
**3/5** — Q2/Q3/Q4 correct, Q1 off by one (15 vs 16), **Q5 wrong: it denies the flat rectangles**.

Verdict unchanged (no — 11× slower and blind to the defect class we care about), but the recorded
number was an artefact of my instrument, not a fact about the model. `vlm_bench` now **retries wider
and prints `[WARNING] any score below is a FLOOR, not a verdict`** when a reply is still truncated, so
a partial answer can no longer masquerade as a capability result. Two lessons, both now in the studio
skill: a truncated response is not a score, and **reading the raw output is what caught it** — a
scoring harness that persists only the score would have hidden this permanently.

## Model health — audited, not assumed (2026-09-14)

`python -m tools.studio.model_health [--probe-local] [--json]` reads every profile, classifies each
pin (**free** / **local** / **cloud?** / **PAID?**) and probes the routes it can. Exit 0 = every pin is
free-tier or local and every probed route answered.

**It found two dead routes.** Four bots carried HuggingFace fallbacks that could not work:

| Route | What the probe returned | Verdict |
|---|---|---|
| `huggingface/zai-org/GLM-5.3-Flash` | `HTTP 402: You have depleted your monthly included credits. Purchase pre-paid credits to continue using Inference Providers.` | **A billing wall.** Not free-tier: it meters and then asks for money, which is precisely what the "never stop the studio on a billing limit" rule exists to prevent |
| `huggingface/deepseek-ai/DeepSeek-V4.1-Flash` | HTTP 200 with **empty content** | Answers nothing — the classic free-endpoint failure mode |

Both were **removed** from forge / chip / tempo / warden (`hermes -p <bot> config set fallback_model
'[...]'`, verified stored as a real list). Every chain is now free-tier or local end-to-end:

```
forge    nous ling-3.0-flash-fin:free -> nous longcat-2.0:free -> nous laguna-xs-2.1:free -> local qwen3-8b
chip     nous longcat-2.0:free        -> nous ling-3.0-flash-fin:free -> local qwen3-8b
tempo    nous ling-3.0-flash-fin:free -> nous longcat-2.0:free -> nous laguna-xs-2.1:free -> local qwen3-8b
warden   nous ling-3.0-flash-sante:free -> nous laguna-xs-2.1:free -> local qwen3-8b
lens     local qwen3-vl-8b
lore     local gemma-4-12b-qat -> local qwen3-8b
pixel    local qwen3-vl-8b
```

Re-audit after any pin change: `python -m tools.studio.model_health` → `OK: every pinned model is
free-tier or local`.

Two notes for the next reader:
- `fallback_model` triggers a "not a recognized config key — did you mean `fallback_providers`?" notice
  from `hermes config set`. It is a **supported legacy alias**: `agent/agent_init.py::_fallback_entries`
  normalises "legacy single-dict `fallback_model` / list `fallback_providers`", and `cli.py` reads it.
  Verified in the code, not assumed from the warning.
- Local load-testing is opt-in (`--probe-local`) because it unloads whatever is resident: during this
  audit the studio loop was mid-round with a model loaded, so evicting it to run a health check would
  have broken a round. The static audit and the live vision benches were the evidence instead.

## The roster (live pins)

| Bot | Primary | Fallback chain (tried in order) | Why |
|---|---|---|---|
| **forge** director | `inclusionai/ling-3.0-flash-fin:free` (nous) — PASS 3.4s, ctx 262k | `meituan/longcat-2.0:free` → `poolside/laguna-xs-2.1:free` → local `qwen/qwen3-8b` | Rounds compact at 100–185k tokens; needs a big-context cloud brain. ling-fin is the fastest chain-passing free model. |
| **chip** coder | `meituan/longcat-2.0:free` (nous) — PASS 9.8s, ctx 1M | `inclusionai/ling-3.0-flash-fin:free` → local `qwen/qwen3-8b` | 1M context for reading a whole module before editing. Off OpenRouter entirely. |
| **warden** reviewer | `inclusionai/ling-3.0-flash-sante:free` (nous) — PASS 5.2s | `poolside/laguna-xs-2.1:free` → local `qwen/qwen3-8b` | Must not be the builder's model, or it is self-review. |
| **tempo** music | `inclusionai/ling-3.0-flash-fin:free` (nous) | `meituan/longcat-2.0:free` → free `zai-org/GLM-5.3-Flash` (huggingface) → local `qwen/qwen3-8b` | Added 2026-09-13. Its **generation** model is a separate, local audio model (below) — the LLM only writes prompts and runs tools, and staying in the cloud leaves the GPU free for rendering. |
| **pixel** art | local `qwen/qwen3-vl-8b` | *(none — deliberate)* | Only VLM on the box that passes the chain. No free cloud VLM exists (nous has none; OpenRouter caps at 50/day). |
| **lens** QA | local `qwen/qwen3-vl-8b` | *(none — deliberate)* | Same. A **text** model "auditing" a frame is exactly how SLAP #17 happened. |
| **lore** content | local `google/gemma-4-12b-qat` | local `qwen/qwen3-8b` | Bulk JSON generation, free forever, 20 tok/s is fine for it. |

`pixel` and `lens` intentionally have **no** fallback: a silent cross-modality fallback would let a
text model answer a vision question — the studio has been burned twice by confident visual claims
with nothing behind them. Loud failure beats a fake pass.

## Fallback verified working (not assumed)

Forcing a rate-limited primary and watching the runtime hand off, 2026-09-13:

```
$ python -m hermes_cli.main -p chip -m cohere/north-mini-code:free --provider openrouter \
    chat -q "Run this exact shell command and reply with only its output: echo chain-ok"

  ┊ 💻 $  echo chain-ok  0.5s
chain-ok
⚠️ Model fallback: cohere/north-mini-code:free via openrouter unavailable (rate limit);
   using inclusionai/ling-3.0-flash-fin:free via nous. Primary retry eligible in ~60 s
Duration: 5s   Messages: 4 (1 user, 2 tool calls)
```

The turn completed through the chain, the tool call ran, and the primary was put on a cooldown
(60 s → 2 m → … → 4 h, `agent/fallback_cooldown.py`). Handoff is automatic; every bot must
therefore end its chain in a **local** model, because local is the only link that cannot 429.

## Rules

1. **A new model joins the roster only after passing the 3-step chain probe.** Prose quality and
   benchmark scores do not count.
2. **Every cloud primary's chain ends in a local model.** A chain that ends in another free cloud
   model on the same exhausted pool is not a fallback.
3. **Never put two models on OpenRouter `:free`.** 50 requests/day is shared by the whole key.
4. **One resident local model at a time.** Check `lms ps` before blaming a slow round; an 18 GB
   model on a 12 GB card is what a 60 s/token round looks like.
5. **Re-audit when a round stalls at 0 tool calls** — that is the signature of a pin that has
   silently become a 429.

## Audio models are a separate roster (added 2026-09-13)

`tempo`'s **generation** model is not an LLM and is not in the table above: it is a local generative
audio model run by `tools.audio.gen_music` under `.venv-audio` (torch 2.11.0+cu128 on the RTX 5070's
sm_120, transformers 5.17, diffusers 0.40). The reasoning is the same as everywhere else in this file —
measured, not assumed — with one addition that outranks speed: **the owner requires assets that are
free to ship**, so a model with non-commercial weights or a gated repo is disqualified no matter how
good it sounds.

| Backend | Repo | Licence (from the registry API) | Gated | Verdict |
|---|---|---|---|---|
| `ace_step` | `ACE-Step/acestep-v15-xl-turbo-diffusers` | `mit` | `False` | **pinned and proven.** 8-step turbo render, 44.1 kHz stereo up to 240 s, bpm/key/time-signature control, instrumental mode. Rendered a shippable cue end-to-end (see below). |
| `ace_step_sft` | `ACE-Step/acestep-v15-xl-sft-diffusers` | `mit` | `False` | **pinned but not yet rendered.** 11.5 GB of weights — expect to need `--offload`; do not cite it as usable until a cue comes out of it. |
| `musicgen` | `facebook/musicgen-medium` | `cc-by-nc-4.0` | `False` | **BLOCKED — non-commercial weights.** Its 15 GB cache was deleted so it cannot silently render unshippable audio. |
| `stable_audio_open` | `stabilityai/stable-audio-open-1.0` | `stable-audio-community` | `auto` | **BLOCKED —** gated (`401` on first fetch) *and* non-permissive. |

### The 12 GB numbers for audio (each measured on the run it is attributed to)

| Mode | dtype | Duration | Peak VRAM | Elapsed |
|---|---|---|---|---|
| GPU-resident | float16 | 31 s | **12,732 MiB** | 136 s |
| GPU-resident | float16 | 5 s (probe) | 11,118 MiB | 1.5 s |
| `--offload` | float16 | 5 s (probe) | 8,026 MiB | 14.8 s |
| `--offload` | bfloat16 | 31 s | **8,092 MiB** | 369 s |
| GPU-resident | bfloat16 | 31 s | *not measured* | ~136 s |

Read it carefully, because an earlier version of this table attributed the 12,732 MiB figure to
bfloat16 and that was wrong — it is the **float16** resident run (the one that produced NaN). The peaks
that matter:

- The only **float16** full-length run peaked *over* the card's 12,227 MiB and was garbage anyway.
- The delivered cue is **bfloat16 + `--offload`: 8,092 MiB**, comfortably inside the card.
- **Offload costs ~2.7x wall-clock** (369 s vs ~136 s) and buys ~4.6 GB of headroom. For an asset
  build that is a trade worth defaulting to when a cue is long or another process wants the GPU.
- An unmeasured cell is left blank on purpose. **Do not fill it in from the neighbouring row.**

**`--offload` does not change the artefact.** Same seed, same prompt, same dtype, rendered resident
and offloaded, are **byte-identical** — SHA-256 `49bf4c25ac3bdfd9fbfab8e4693486e592277f24c8fa52239da68f8140bd839`
both times. So the memory mode is a pure speed/VRAM knob, never a reproducibility factor: a cue
rendered under `--offload` is the same asset a resident run would have produced.

`--dtype float16` produced **all-NaN** output on this checkpoint in *both* modes (probe: `min=nan max=nan mean=nan std=nan` on the raw `audios` tensor, shape `(1, 2, 240000)`), so the NaN is a dtype problem, not a memory problem — `bfloat16` is the default. A NaN buffer written as PCM-16 becomes a full-scale DC block that passes a naive loudness check, which is why the tool now refuses non-finite output before writing.

Two traps worth keeping written down:

- **The obvious pick was wrong.** `facebook/musicgen-*` is widely described as MIT; the registry says
  CC-BY-NC-4.0. One query to `https://huggingface.co/api/models/<repo>` settled it. Query the registry
  for `license` + `gated` before pinning any model that produces a shippable asset.
- **`ACE-Step/Ace-Step1.5` is not runnable here** — the all-in-one repo has no `model_index.json`, so
  `AceStepPipeline.from_pretrained` 404s. The `*-diffusers` conversions are the pipeline repos.

Enforcement, the per-asset ledger and the SFX decision (procedural synthesis is wholly owned, so no SFX
model is used at all) live in **`docs/AUDIO-LICENSES.md`**.

## Routines carry their OWN model pin (added 2026-09-13)

The bot routines (`[bot:forge] continuous build round` / `nightly build round`, `[bot:warden]
review sweep`, `[bot:lens] nightly QA sweep`) live in the **default profile's** cron store
(`$HERMES_HOME/cron/jobs.json`), not in the bots' own profile cron dirs — a routine's *agent run*
executes in the profile that owns the job, and only its delivery (`deliver: bot-chat:<bot>`)
spawns a turn in the bot's profile. A job with no `model`/`provider` therefore inherits the
**Hermes bot's** model, not the bot named in its title.

Each bot routine is pinned to that bot's own roster model above, so the 6 bots keep running on
free or local models even when the owner's Hermes bot is moved to another model:

| Routine | Pinned model | Provider |
|---|---|---|
| `[bot:forge]` ×2 | `inclusionai/ling-3.0-flash-fin:free` | nous |
| `[bot:warden]` | `inclusionai/ling-3.0-flash-sante:free` | nous |
| `[bot:lens]` | `qwen/qwen3-vl-8b` | lmstudio (local) |

Verify after any model change here: `hermes cron list` shows the per-job pin, and the run's
session row is the receipt — `session_model_usage` for `cron_<job-id>_<ts>` must show the bot's
model, never the Hermes bot's. The lens sweep needs LM Studio resident at its 02:00 slot; per
Rule 3 of this roster a text-model substitute is not acceptable, so a failure there is the
intended loud failure, not a prompt to add a fallback.



## Directive framing beats model size (measured 2026-09-17)



Every coder candidate measured this day (essentialai/rnj-1, prism-ml/bonsai-27b,

google/gemma-4-e4b, google/gemma-4-26b-a4b, qwen/qwen3.8-27b) and the two live cloud pins

(meituan/longcat-2.0:free, inclusionai/ling-3.0-flash-fin:free) were put through the same

scoped edit: add one method to `game/systems/rng.py` with a byte-identical minimal diff.



**The result was not about model size.** Under an OPEN-ENDED agentic framing (here is a

file, explore it and make the change) **every** model failed - the cloud pins burned 20

turns on discovery and made **zero** `write_file` calls. Under a PRECISE DIRECTIVE (here is

the file content, insert exactly this method, return the complete file) the **same** cloud

pins both PASSED, 0 lines deleted, in 16-48 s and under 6k tokens:



| Model | Open-ended | Precise directive |

|---|---|---|

| `meituan/longcat-2.0:free` (chip) | 20 turns, 0 writes, FAIL | PASS, 0 deleted, 48 s, 1770 tok |

| `inclusionai/ling-3.0-flash-fin:free` (forge) | 20 turns, 0 writes, FAIL | PASS, 0 deleted, 16 s, 5790 tok |



A two-tier "intern drafter -> senior reviewer" pipeline was also measured end to end

(`gemma-4-e4b` drafting, `longcat` reviewing): **FAIL**, 419 s total, reviewer deleted 58

lines and had to reconstruct intent by exploration. The draft cost more than it saved.

**A fast drafter only helps when the handoff is a precise directive; when it is a broken

file plus 'fix this', the reviewer pays the discovery cost anyway and the pipeline is

slower than a single precise call.**



Consequences for this studio:

- The seat's real requirement is not a bigger brain, it is a **concrete directive**. The

  studio already has the directive-writer: WARDEN's correction orders and forge's ticket

  briefs. Efficiency comes from brief quality, not from model tier.

- Do not pick a candidate coder on tok/s. rnj-1 (45 tok/s) and gemma-4-e4b (51.8 tok/s) are

  both faster than the incumbent and both fail the edit; speed is free and worthless here.

- Test a candidate through the interface it will actually be used through. Testing agentic

  exploration measures the harness, not the model.



### VRAM hazard found the same day: duplicate model instances



Repeated `lms load` calls stack **duplicate instances** of the same model (three copies of

`gemma-4-e4b` = 19 GB requested on a 12 GB card). Always check `lms ps` before a trial and

unload every instance; the earlier trials in this section ran with a second model resident

and produced timeouts that were scored as model failures. One model at a time, verified.



### P0 defect found by this work: the RNG was not random



Driving a minimal edit through `game/systems/rng.py` exposed that `RNG._next()` lost two of

its three xorshift steps to operator precedence (`&` binds tighter than `^`, so

`x ^ (x << 25) & MASK64) ^ (x << 25) & MASK64` cancels to `x`). The generator had an

**8-value cycle**: `randint(0, 9)` could never return 0, 3, 8 or 9, and 10,000 draws

produced 8 distinct values. Fixed (commit `a9529f6`); verified 10,000 distinct values in

10,000 draws, uniform buckets, deterministic per seed, no cycle in 200k draws, all seven

gates green. Invisible to the golden-seed regression, which tests stability, not randomness

quality - a property no gate in this repo asserts (ticket P0.8).

### Multi-stage chained handoff, measured both ways (2026-09-17)

The owner's reframe - local drafter -> second local refiner -> cloud final review - was
built and run end to end against the same acceptance probe. It failed **twice**, and both
failures are the interesting part:

**Attempt 1 (no handoff gates):** the drafter (`gemma-4-e4b`) produced a usable method in
3 s. The refiner (`gemma-4-12b-qat`) returned **0 characters from 4000 tokens** - the
thinking-model trap already documented above, where reasoning is billed against
`max_tokens`. The chain forwarded the empty artefact, the cloud assembler dutifully
inserted nothing, and the result failed with a missing method. **An ungated chain
propagates garbage silently.**

**Attempt 2 (with handoff gates):** the gate rejected attempt 1 (empty) and retried wider -
attempt 1 cost 130 s and returned nothing, attempt 2 cost another 130 s for 244 characters.
The refined method then **failed on indentation** (not attached to the class), and the
cloud assembler call died with `HTTP 524` on the larger payload. Total >260 s for the
refiner stage alone; verdict FAIL.

Against that, a **single precise directive to one cloud model PASSED in 16-48 s** with zero
deletions (table above).

Conclusions, for anyone reframing the studio:
1. **Gates between stages are mandatory.** Without one, a stage that returns empty output
   is indistinguishable from success and poisons every stage after it.
2. **A stage is only worth adding if its output is cheaper to verify than to produce.** The
   refiner spent 260 s to emit a mis-indented method; that is a net loss at this task size.
3. **Tier by measured strength, not by size of budget.** Local models measured strong at
   short isolated generation (53 tokens in 3 s) and weak at any in-place edit; cloud models
   measured strong at executing a precise directive and weak at open-ended exploration.
4. **Chain length is a cost multiplier, not a quality multiplier.** For small, fully-
   specified work, one precise directive to one competent executor beat every chain tried
   here. Chaining should be reserved for work large enough that generation, not
   verification, is the bottleneck.

Harness: `%LOCALAPPDATA%\Temp\chain_trial.py` (sandboxed; unloads each local model before
loading the next so the 12 GB card never holds two).



