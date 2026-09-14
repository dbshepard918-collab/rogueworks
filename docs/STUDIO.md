# Rogueworks — how the studio works

Six Hermes bots that build the game at `C:\Users\dbshe\rogueworks`. They are ordinary Hermes
profiles, so every one of them is also a CLI agent and shows up in the desktop **Bots** tab.

| Bot | Job | Model | Fallback |
|---|---|---|---|
| **forge** | director: GDD, tickets, review, integration, talks to you | free `inclusionai/ling-3.0-flash-fin:free` (nous) | free `meituan/longcat-2.0:free` → free `zai-org/GLM-5.3-Flash` (huggingface) → free `poolside/laguna-xs-2.1:free` → local `qwen3-8b` |
| **chip** | writes the game code | free `meituan/longcat-2.0:free` (nous, 1M ctx) | free `inclusionai/ling-3.0-flash-fin:free` → free `deepseek-ai/DeepSeek-V4.1-Flash` (huggingface) → local `qwen3-8b` |
| **pixel** | sprites, tiles, VFX, UI → packed atlases | local `qwen3-vl-8b` (vision) + **local FLUX** for new art | *(none — a text model must never answer a vision question)* |
| **lore** | monsters, items, affixes, rooms, biomes, flavour (JSON) | local `gemma-4-12b-qat` | local `qwen3-8b` |
| **lens** | headless playtests, screenshot audits, bug reports | local `qwen3-vl-8b` (vision) | *(none — same reason)* |
| **tempo** | music director: score, ambience loops, audio manifest | free `inclusionai/ling-3.0-flash-fin:free` (nous) | free `meituan/longcat-2.0:free` → free `zai-org/GLM-5.3-Flash` (huggingface) → free `poolside/laguna-xs-2.1:free` → local `qwen3-8b` |
| **warden** | editor: reviews everything, slaps what falls short | free `inclusionai/ling-3.0-flash-sante:free` (nous) | free `poolside/laguna-xs-2.1:free` → free `zai-org/GLM-5.3-Flash` (huggingface) → local `qwen3-8b` |

**The full audit — every number behind these pins — is `docs/MODELS.md`. Read it before changing a
model.** Headline findings, all measured on this machine: OpenRouter `:free` allows **50 requests
per day for the whole key** (one round is 69–278 tool calls, so it is structurally unusable as a
primary); `upstage/solar-pro4:free` returned a capacity 429 on the *first* request; and a single
8B model at Hermes' 64K context already fills 11.6 GB of the 12 GB card, so **one local model can
be resident at a time** — the pipeline is load-order, not six resident bots. `qwen2.5-coder-14b`,
`deepseek-r1-0528-qwen3-8b`, `ui-tars-7b-dpo` and every mid-size VLM here except `qwen3-vl-8b`
cannot emit a tool call at all, even when forced.

**Every cloud pin ends its chain in a local model**, because local is the only link that cannot
rate-limit. Handoff is automatic and verified: a 429 on the primary switches to the next chain entry
mid-turn (primary goes on a 60 s → 4 h cooldown), tool calls continue, the round survives.

**No paid model is pinned anywhere, on purpose.** A studio that can be stopped by a billing limit is
not autonomous. Free models fail in ways paid ones do not (429s, empty completions, tool calls
silently skipped) — when one misbehaves, switch to another free one or go local; never spend money
to route around it. A model joins the roster only after passing the **3-step chain probe**
(`read_file` → `write_file` → `run_tests`); prose quality and benchmark scores do not count.

## The law, and the slaps

`docs/STANDARDS.md` is the law every bot reads at the start of every round: five rules (no claim
without a command; never break `main`; contracts are frozen; stay in your lane; cheap by default),
a severity table, and a review protocol that grows a rule each time someone breaks one.

**WARDEN** reviews artifacts, re-runs the acceptance commands itself, and either APPROVES or SLAPS. A
slap is a workflow, not a complaint:

```bash
cd /c/Users/dbshe/rogueworks
MSYS_NO_PATHCONV=1 .venv/Scripts/python.exe -m tools.studio.slap \
  --bot chip --severity P2 \
  --violation "left test fixtures in assets/atlas/, breaking verify for every other bot" \
  --evidence "verify: 'FAIL: 15 warning(s)'; files present in assets/atlas/" \
  --rule "Never leave test fixtures in assets/, runs/ or game/ — write them to Temp and delete them." \
  --fix "python -m tools.studio.verify_gate"          # acceptance command that must now pass
```

It records the violation + evidence + rule in `docs/SLAPS.md` (permanent ledger), **dispatches a
correction order into the offending bot's own chat** so that bot must take a turn and fix it, then
re-runs the acceptance command and records whether the fix actually verified. Escalation is automatic
by repeat count: **level 1** warns → **level 2** appends the rule to the offender's `SOUL.md` (so it
loads in every session that bot will ever run) → **level 3** freezes that lane until the fix verifies.
An unverified fix never closes.

Live example: SLAP #1 went to `chip` for test debris. It took a 144-message / 142-tool-call turn
(7m33s) and fixed it; the ledger closes clean.

## Talking to the studio

**Desktop:** open the **Bots** tab → pick a bot → type. `forge` is the front door; ask it for status,
the next ticket, or "build the next item and prove it". `warden` will tell you what it rejected and
why. (The `.exe` launcher is blocked by device policy on this box, so the CLI goes through the venv
python.)

```bash
H="MSYS_NO_PATHCONV=1 /c/Users/dbshe/AppData/Local/hermes/hermes-agent/venv/Scripts/python.exe -m hermes_cli.main"
$H -p forge  chat -q "Status from docs/TICKETS.md and runs/, then do the top ticket."
$H -p warden chat -q "Review the newest work and slap anything below standard."
$H -p lens   chat -q "QA pass on seed 3: run, screenshot, audit, file the report."
```

## A normal round

1. `forge` reads `docs/ROADMAP.md` (priority queue), `docs/PROGRESS.md` (what the last rounds did),
   `docs/SLAPS.md` (any open slap on itself) and picks the top item.
2. Work goes out: `chip` (code), `pixel` (art), `lore` (data) — via `delegate_task` or the Bot chat.
3. `lens` runs the build across seeds, screenshots real frames, audits them with local vision.
4. `forge` runs the gates itself, updates tickets/roadmap/progress, and reports with pasted output.
5. `warden` reviews the artifacts independently and approves or slaps.

## Gates (nothing is "done" without these)

```bash
cd /c/Users/dbshe/rogueworks && P="MSYS_NO_PATHCONV=1 .venv/Scripts/python.exe"
$P -m game.main --headless --turns 300 --seed 0     # exit 0, invariants empty (run seeds 0..7)
$P -m tools.validate_data                            # content JSON valid
$P -m tools.art.verify                               # sprites palette-locked, grid-aligned
$P -m tools.selftest                                 # imports + invariants
$P -m tools.studio.audit_sprites                     # every sprite the content asks for exists
$P -m tools.art.check_sheet <sheet.png>              # a generated sheet is usable before you build it
$P -m game.main --seed 3 --shot 20,100,199 --shot-dir runs/shots   # real frames for the art audit
```

## Free art generation (local)

New art is generated **on your own GPU**, not via a paid API: `tools/art/gen.py` wraps
`stable-diffusion.cpp` + FLUX.1-schnell GGUF (`C:\Users\dbshe\models\flux`). ~11s per sheet, ~8s per
single sprite. It unloads the local LLMs first (`lms unload --all`) because a chat model and the
diffusion model do not co-reside in 12 GB. Local sheets are gated by `tools.art.check_sheet` before
they are allowed near the atlas — measure, don't trust the prompt.

## Free music generation (local) — added 2026-09-13

Music is generated **on your own GPU** too, by **tempo**. Generation is a studio job, never a game
dependency: the game still ships on pygame + stdlib, and the only runtime change is that
`pygame.mixer` plays the resulting `.wav`/`.ogg` files.

```bash
cd /c/Users/dbshe/rogueworks
.venv-audio/Scripts/python.exe -m tools.audio.gen_music --list-backends        # licence board
.venv-audio/Scripts/python.exe -m tools.audio.gen_music --backend ace_step --seed 7 \
  --seconds 30 --loop-fade 1500 --prompt "<mood prompt>" --out assets/audio/<cue>.wav
.venv-audio/Scripts/python.exe -m tools.audio.gen_music --analyze assets/audio/<cue>.wav
```

`.venv-audio` is the studio's audio interpreter alone (torch 2.11.0+cu128 on the RTX 5070's sm_120,
transformers 5.17, diffusers 0.40 — which ships `AceStepPipeline` natively, so nothing extra to
install). **The game venv never gets torch** — that is the whole point of a separate environment. The
tool refuses to render silently: it reports `rms`/`peak`/duration and exits non-zero on a blank
render, `--loop-fade MS` crossfades tail into head so ambience loops have no seam, and `--analyze`
prints the wrap discontinuity that proves the seam is clean.

### Licence policy — enforced in the tool, not in a document

Every rendered cue must be **free to ship**, so the backend's weights must be permissively licensed
*and* ungated. `tools.audio.gen_music` refuses to render with anything else unless
`--allow-noncommercial` is passed, and that flag is for throwaway experiments only:

| Backend | Repo | Licence | Verdict |
|---|---|---|---|
| `ace_step` | `ACE-Step/acestep-v15-xl-turbo-diffusers` | **MIT** | **SHIPPABLE — the shipping backend, proven end to end.** Ungated, no account, 44.1 kHz stereo, bpm/key/time-signature control, up to 240 s. |
| `ace_step_sft` | `ACE-Step/acestep-v15-xl-sft-diffusers` | **MIT** | SHIPPABLE licence, **not yet rendered** (11.5 GB — use `--offload`). Not to be cited as usable until a cue comes out of it. |
| `musicgen` | `facebook/musicgen-medium` | **CC-BY-NC-4.0** | **BLOCKED — non-commercial.** Every cue it renders is unusable in a shipping game. |
| `stable_audio_open` | `stabilityai/stable-audio-open-1.0` | community (gated) | **BLOCKED — gated repo + bespoke commercial terms.** Needs an account and an acceptance step. |

**Memory on a 12 GB card, measured per run (dtype matters — the numbers are not interchangeable):**
the **float16** resident run peaked at **12,732 MiB** for a 31 s cue, over the card's 12,227 MiB, and
produced garbage anyway. The delivered cue — **bfloat16 + `--offload`** — peaks at **8,092 MiB** and
takes ~2.7× longer (369 s vs ~136 s). `--dtype` defaults to **bfloat16** because float16 returns
all-NaN on this checkpoint in *both* memory modes (measured), and the tool refuses non-finite output
before it can reach the disk. `--offload` is a pure speed/VRAM knob: the same seed, prompt and dtype
render **byte-identical** either way, so it never changes what ships.

Shipping allowlist: `apache-2.0`, `mit`, `cc0-1.0`, `bsd-3-clause`, `unlicense`.
Provenance and the per-asset ledger live in `docs/AUDIO-LICENSES.md`. Sound effects are **not** model-
generated: they are synthesised procedurally in `game/engine/audio.py` from stdlib `wave`, so they are
wholly owned with zero third-party claim — no SFX model here is permissively licensed enough to beat
that. That is a licence decision, not a technical one.

## Recoverability and budgets (hardened 2026-09-13 after a real loss)

A sibling cron agent overwrote `docs/PROGRESS.md` with `write_file` — 515 lines became 20. Nothing
recovered it: the repo had **no commits** and the filesystem checkpoint store was **empty**. Three
changes went in so that cannot repeat silently:

1. **`docs/PROGRESS.md`, `TICKETS.md`, `ROADMAP.md`, `SLAPS.md` are append/prepend-only.** Read them,
   then `patch`. Never `write_file` a shared log — that is how the history was lost.
2. **Git is the first line of defence: commit every round.** The repo now has a history, so the next
   overwrite is a one-line revert. `.gitignore` keeps venvs, saves, shot dirs and the ~2 GB of vendored
   `tools/art/sd/bin` CUDA runtimes out of it.
3. **Filesystem checkpoints are ON** for the default profile and all seven bots
   (`hermes -p <bot> config set checkpoints.enabled true`). They snapshot the working directory once
   per turn on the first `write_file`/`patch` and are restorable with `/rollback`. They ship **off** —
   `hermes_cli/setup_quick.py` writes `checkpoints.enabled: false` — which is why the original loss had
   no snapshot. Verified working, not assumed:

   ```
   $ hermes -p forge checkpoints status
   Projects:        2
     WORKDIR                            COMMITS  LAST TOUCH  STATE
     C:\Users\dbshe\rogueworks                1   6s ago     live
   ```

4. **The session database is the last resort.** Every `read_file` result is a `messages` row in
   `<HERMES_HOME>/state.db`, so a file that was read at least once is recoverable verbatim — that is
   how the 515-line log came back, searched across *every* profile's database. The recipe is in the
   studio skill, §10.

**Memory budgets were raised at the owner's request** so lessons survive instead of being evicted:
`memory.memory_char_limit` 2200 → **12000**, `memory.user_char_limit` 1375 → **4000**, set on the
default profile and all seven bots. Each bot now has room to carry its own corrective rules.

## Bot toolchain config (what every bot must be pointed at)

Two settings live in each profile's `config.yaml` and were wrong by default. Both are per-profile, so
they must be set on all eight (`default` + the seven bots) and verified with `-p <bot>`:

```bash
# 1. VISION ROUTING. Hermes resolves vision through agent/auxiliary_client.py; with no
#    `auxiliary:` block it auto-routes to CLOUD (_VISION_AUTO_PROVIDER_ORDER = openrouter,
#    nous, deepinfra). That 404'd on every call for two rounds while a free local VLM sat
#    loaded on the box.
hermes -p <bot> config set auxiliary.vision.provider lmstudio
hermes -p <bot> config set auxiliary.vision.model qwen/qwen3-vl-8b
hermes -p <bot> config set auxiliary.vision.base_url http://localhost:1234/v1
hermes -p <bot> config set auxiliary.vision.timeout 600      # default 120s is too tight locally

# 2. THE STUDIO SKILL. Each profile keeps its OWN copy, so an edit to forge's copy reaches
#    nobody else — this one sat frozen at 172 lines in six bots while forge accumulated the
#    audio, recoverability, vision and metric lessons.
SRC="$HOME/AppData/Local/hermes/profiles/forge/skills/roguelite-game-factory/SKILL.md"
for p in chip pixel lore lens warden tempo; do
  cp "$SRC" "$HOME/AppData/Local/hermes/profiles/$p/skills/roguelite-game-factory/SKILL.md"
done
md5sum "$HOME/AppData/Local/hermes/profiles"/*/skills/roguelite-game-factory/SKILL.md \
  | awk '{print $1}' | sort -u | wc -l     # must print 1
```

Check the vision route **mechanically** rather than through an agent turn — an agent one-shot only
proves the model *chose* to call the tool (two attempts returned `0 tool calls`, proving nothing):

```python
from agent import auxiliary_client as aux
print(aux.resolve_vision_provider_client())   # expect base_url=http://localhost:1234/v1/
```

## Play it

```bash
cd /c/Users/dbshe/rogueworks
MSYS_NO_PATHCONV=1 .venv/Scripts/python.exe -m game.main
# WASD/arrows move · SPACE attack · SHIFT dash · TAB inventory · ESC pause/menu
```

## Routines (all free/local, all running)

| Job | Cadence | What it does |
|---|---|---|
| `[bot:forge] continuous build round` | every 2h | one roadmap item, gates, QA, docs, self-review |
| `[bot:warden] review sweep` | every 2h | independent review; approves or slaps |
| `[bot:lens] nightly QA sweep` | 2am | multi-seed runs, real frames, ranked report + tickets |

`hermes cron list` shows them; output lands in each bot's Bot Chat. The gateway runs as a login item,
so this survives reboots.
