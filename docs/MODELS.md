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
defect — because prose quality cannot be scored honestly. Harness: `%TEMP%/rw_vlm_bench.py` (writes
its per-question answers to `%TEMP%/rw_vlm_bench_results.json` when it completes).

**Latency caveat:** only one model fits on the card and the VLM is shared with the other bots, so
the second numbers below were taken while other agents were queued on the same endpoint. Treat the
**scores** as the finding and the **latencies** as indicative only.

| Question (known answer) | `qwen2.5-vl-7b-instruct` | `qwen/qwen3-vl-8b` |
|---|---|---|
| sprites in the top row (16) | 8 ✗ | 16 ✓ |
| sprites in the last row (5) | 7 ✗ | 16 ✗ |
| plate colour behind sprites (dark grey) | "white and blue" ✗ | "dark gray" ✓ |
| duplicate sprites present (yes) | "yes" ✓ | "yes" ✓ |
| flat solid rectangles present (yes, 6) | "no" ✗ | "yes" ✓ |
| **score** | **1/5** | **4/5** |
| answer latency / critique latency | 7.9 s / 15.3 s | 4.1 s / 5.5 s |

The challenger is ~2× slower and missed the one defect class this studio exists to catch. Sheet size
matters as much as the model: the same critique took **77 s at 2116×1896** and **5.5 s at 1092×888**.

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

Tally: **3 true, 4 false, 1 false claim whose lead found a real defect.** Verdicts on *its own*
advice ("add anti-aliasing") are wrong far more often than its observations — never let it set the
house rules, and always give it the house rules in the prompt.

Note `qwen2.5-coder-14b` and `ui-tars-7b-dpo` were both recommended to the owner by an external
advisor; both fail the first tool call with real tools attached.

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
