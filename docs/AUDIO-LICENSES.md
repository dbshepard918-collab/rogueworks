# AUDIO LICENCES — what may ship, and the proof

**Owner:** forge (director). **Applies to:** every file in `assets/audio/` and every model that
generated one. The rule is short: **if a cue's provenance is not in this file, it does not ship.**

## The requirement

The owner's standing instruction: music and effects must be *ready to ship* with no licence paperwork,
no attribution chores, no account-gated terms. So the bar for a generator is:

1. **Permissively licensed weights** — MIT, Apache-2.0, CC0, BSD or Unlicense.
2. **Ungated** — no HuggingFace account, no licence-acceptance click, no token.

Condition 2 is not a detail: a gated repo returns `401` before it will download, which turns a
one-command asset build into an account dependency. Both conditions are enforced by tooling, not by
good intentions.

## The allowlist (enforced)

`tools.audio.gen_music` holds the allowlist and **refuses to render** with any backend outside it
unless `--allow-noncommercial` is passed — a flag for throwaway experiments whose output must never
reach `assets/audio/`.

```
allowlist: apache-2.0, mit, cc0-1.0, bsd-3-clause, unlicense
```

Verify the current board any time:

```bash
cd /c/Users/dbshe/rogueworks
.venv-audio/Scripts/python.exe -m tools.audio.gen_music --list-backends
```

## Model provenance (measured 2026-09-13 via the HuggingFace model API, not from memory)

Every row below is the `gated` and `license` field the registry itself returns for that repo.

| Backend | Repo | Licence (registry) | Gated | Verdict |
|---|---|---|---|---|
| `ace_step` | `ACE-Step/acestep-v15-xl-turbo-diffusers` | `mit` | `False` | **SHIPPABLE — the shipping backend.** |
| `ace_step_sft` | `ACE-Step/acestep-v15-xl-sft-diffusers` | `mit` | `False` | SHIPPABLE — higher-quality sibling. |
| `musicgen` | `facebook/musicgen-medium` | `cc-by-nc-4.0` | `False` | **BLOCKED — non-commercial.** |
| `stable_audio_open` | `stabilityai/stable-audio-open-1.0` | `stable-audio-community` | `auto` | **BLOCKED — gated + non-permissive.** |

Notes that matter:

- **Meta's MusicGen is CC-BY-NC-4.0, not MIT.** The weights are non-commercial, so every cue it
  renders is unusable in a game that ships for money. This was discovered by querying the registry
  after a MusicGen cue had already been rendered as a probe; that probe was never shipped, and the
  model's 15 GB of cached weights were **deleted** so nothing can silently render non-shippable audio.
- **Stability's Stable Audio Open is gated** (`GatedRepoError: 401` on the first attempt) and carries a
  bespoke community licence. Two independent reasons to keep it out of the pipeline.
- **`ACE-Step/Ace-Step1.5` (the all-in-one repo) is not a diffusers pipeline** — it has no
  `model_index.json`. The `*-diffusers` conversions are the runnable ones; both are MIT and ungated.
- ACE-Step v1.5 supports bpm / key / time-signature control and instrumental (empty-lyrics) generation,
  which is what a game score actually needs.

## Sound effects: no model, no claim

The game's SFX (`hit`, `swing`, `death`, `pickup`, `coin`, `levelup`, `dash`, `shoot`, `stairs`,
`hurt`, `boss`, `door`) are **synthesised procedurally at runtime** in `game/engine/audio.py` from
stdlib `wave` — square/saw/sine oscillators with envelopes. They are wholly owned by this project:
zero third-party claim, nothing to attribute, nothing to relicense.

That is deliberate, and it is the licence answer for effects. The usual open SFX models
(`facebook/audiogen-medium`, AudioLDM2 and friends) are CC-BY-NC or similar, so they would *lower*
the licensing quality of the project, not raise it. **Do not add a model-generated SFX pipeline.**
If the effects need to sound better, improve the synthesis — that work is free of legal surface.

## Per-asset ledger (tempo fills this in as cues ship)

Every shipped cue needs a row. A cue without a row is a build failure, not a warning.

| Cue id | File | Backend | Repo | Licence | Seed | Verified (`rms` / `peak` / `click_ratio`) |
|---|---|---|---|---|---|---|
| *(none shipped yet — A-01 is the first)* | | | | | | |

The generation command for each cue is also stored in `game/data/audio.json` so any cue can be
re-rendered from a documented command. **A cue nobody can regenerate is not an asset.**

## What would break this policy (and must not be merged)

- Adding a backend to `tools.audio.gen_music` without a `license` + `gated` field, or with a licence
  outside the allowlist. The tool refuses such a render, and `--list-backends` shows it as BLOCKED.
- Committing a `.wav`/`.ogg` to `assets/audio/` without a ledger row above and a manifest entry.
- Shipping anything rendered under `--allow-noncommercial`.
