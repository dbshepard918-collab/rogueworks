"""
Generate game audio (background loops + sound effects) locally using
Stable Audio Open 1.5 via the diffusers pipeline.

Hardware target: Windows, ~12 GB VRAM (uses fp16).

Output: .wav files in ./output/
Each prompt in PROMPTS generates one clip. Clips generated as "loops" are
ambient/textural to loop more cleanly; you'll still want to trim loop points
in a DAW (e.g. Audacity).

Usage:
    1. Install deps:   pip install -r requirements.txt
    2. Run:            python generate.py

First run downloads the model weights (~several GB) from Hugging Face.
"""

import argparse
import os
from pathlib import Path

import numpy as np
import soundfile as sf
import torch
from diffusers import StableAudioPipeline


# ---------------------------------------------------------------------------
# Your prompt list. Edit freely.
# Keep background beds ambient/textural so they loop cleanly.
# ---------------------------------------------------------------------------
PROMPTS = {
    # LOOPS (background music / ambience beds)
    "loop_forest_day": (
        "a seamless ambient background track, calm forest at midday, soft wind "
        "through leaves, gentle birdsong, light warm pad, meditative, subtle "
        "drone, quiet nature ambience, music loop"
    ),
    "loop_cave_dark": (
        "a seamless dark ambient loop, deep cave, dripping water echoes, low "
        "thrumming drone, mysterious, sparse, subtle tension, atmospheric "
        "background loop"
    ),
    "loop_space_drone": (
        "a seamless sci-fi ambient loop, vast empty space, slow evolving synth "
        "drone, ethereal, minimal, cinematic, music loop"
    ),
    "loop_tavern_mood": (
        "a warm tavern background loop, crackling fireplace, faint distant "
        "fiddle melody, cozy low-key folk ambience, instrumental loop"
    ),

    # SOUND EFFECTS (short one-shots / ambience)
    "sfx_sword_hit": (
        "a short sharp metallic sword clash impact sound effect, clean, punchy, "
        "game audio"
    ),
    "sfx_explosion": (
        "a short big explosion sound effect, booming low rumble with sharp "
        "crack, game audio"
    ),
    "sfx_door_creak": (
        "a short creepy wooden door creaking open sound effect, slow, eerie, "
        "game audio"
    ),
    "sfx_pickup": (
        "a short bright sparkling collectible pickup chime sound effect, joyful, "
        "game audio"
    ),
    "sfx_wind_ambience": (
        "an outdoor windy ambience sound effect, gusts and leaves rustling, "
        "medium length, game audio"
    ),
}


def main():
    parser = argparse.ArgumentParser(description="Local game audio generator")
    parser.add_argument("--model", default="stabilityai/stable-audio-open-1.5")
    parser.add_argument("--out", default="output")
    parser.add_argument("--duration_s", type=float, default=10.0, help="clip length in seconds (max ~47)")
    parser.add_argument("--steps", type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.duration_s > 47:
        raise SystemExit("Stable Audio Open maxes out at ~47 s per clip.")

    print(f"Loading {args.model} ... (first run downloads weights)")
    pipe = StableAudioPipeline.from_pretrained(
        args.model, torch_dtype=torch.float16, safety_checker=None
    )

    # Load text encoders in fp32 / CPU to save VRAM on 12 GB cards.
    pipe.to("cuda", dtype=torch.float16)
    pipe.text_encoder.to("cuda", dtype=torch.float32)

    generator = torch.Generator("cuda").manual_seed(args.seed)

    for name, prompt in PROMPTS.items():
        print(f"\nGenerating '{name}' ...")
        result = pipe(
            prompt=prompt,
            audio_end_in_s=args.duration_s,
            num_inference_steps=args.steps,
            generator=generator,
        )

        # result.audios shape: (num_samples, channels, samples)
        audio = result.audios[0]          # (channels, samples)
        audio = audio.transpose()          # -> (samples, channels)

        # Convert to int16 wav
        audio = np.clip(audio, -1.0, 1.0)
        audio_16 = (audio * 32767.0).astype(np.int16)

        fname = out_dir / f"{name}.wav"
        sf.write(str(fname), audio_16, pipe.sample_rate, subtype="PCM_16")
        print(f"  saved {fname}  ({audio_16.shape[0]/pipe.sample_rate:.1f}s, "
              f"{pipe.sample_rate} Hz, {audio_16.shape[1]} ch)")

    print("\nDone. Trim/loop the LOOPS_* files in a DAW if needed.")


if __name__ == "__main__":
    main()
