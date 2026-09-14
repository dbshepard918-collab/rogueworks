# Game Audio Generator (local)

Generate looping background tracks and sound effects for your game using
**Stable Audio Open 1.5**, running fully on your own machine (no cloud).

Requires: ~12 GB VRAM GPU, Windows (or any OS), Python 3.10+.

## Setup

```bat
cd game_audio_gen
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

> Note: install PyTorch with CUDA first if you don't have it:
> `pip install torch --index-url https://download.pytorch.org/whl/cu121`

## Run

```bat
python generate.py
```

First run downloads the model weights (~several GB). Output `.wav` files land
in `game_audio_gen/output/`.

## Edit the prompt list

Open `generate.py` and edit the `PROMPTS` dict. Add/replace entries as needed.
Keep loop prompts ambient/textural so they loop cleanly.

## Making loops seamless

Stable Audio Open produces a fixed clip; it is not guaranteed to loop perfectly.
Standard workflow:
1. Generate the clip.
2. Open in **Audacity** (free).
3. Trim to a clean section and align the start/end at a zero crossing (or use
   the built-in "Loop" / selection tools).
4. Export. Optionally crossfade the last ~50 ms into the start.

## Optional extras

- **Discrete SFX / one-shots:** also try `cvssp/audioldm2` (diffusers:
  `AudioLDMPipeline`) for short punchy effects.
- **Node-based:** ComfyUI with `ComfyUI-Audio` nodes can orchestrate multiple
  audio models if you prefer a visual workflow.

## Licensing note

Stable Audio Open ships under the **Stability AI Community License** — it
allows commercial use for projects under a revenue threshold. Verify the
current terms on the Hugging Face model card before you ship your game.
