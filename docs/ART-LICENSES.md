# Art licences — what we ship and what we refuse

The audio lane has an enforced allowlist (`docs/AUDIO-LICENSES.md` + `COMMERCIAL_OK_LICENSES` in
`tools/audio/gen_music.py`). The art lane had **nothing** — no ledger, no gate — until this round.
Same standard, same reason: art that ships must be free to ship, and "I think that model is open"
is not a licence.

Every licence below was read from the HuggingFace registry API
(`https://huggingface.co/api/models/<repo>` → `cardData.license`), **not** from a model card summary,
a blog post, or memory. Re-check with the same command before adding a row.

## Shipping now

| Component | Repo | Licence (registry) | Gated | Shippable |
|---|---|---|---|---|
| Diffusion model | `black-forest-labs/FLUX.1-schnell` (GGUF `flux1-schnell-Q4_K_S.gguf`) | **apache-2.0** | auto | ✅ yes — permissive, commercial use unrestricted |

`tools/art/gen.py` runs FLUX.1-schnell through the vendored `stable-diffusion.cpp` CLI
(`tools/art/sd/bin/sd-cli.exe`). Apache-2.0 is on the studio allowlist, so every sprite currently in
`assets/sprites/` is produced by a licence-clean path.

## Assessed and refused

| Component | Repo | Licence (registry) | Why refused |
|---|---|---|---|
| Diffusion model | `Lykon/dreamshaper-7` (GGUF `dreamshaper-7-lcm-q4_0.gguf`, 1.63 GB) | **creativeml-openrail-m** | Not an OSI-approved licence. OpenRAIL-M grants commercial use but attaches **use-based restrictions that must be passed downstream**, which is a policy decision for the owner — not something a tool should assume. It is **not** on `ART_COMMERCIAL_OK`. |

That is not a claim that DreamShaper is unusable — it is a statement that adopting it *lowers* the
licence quality of shipped art relative to what we already run, for a speed gain. The same reasoning
kept SFX procedural: every open SFX model checked was CC-BY-NC, so a model would have *reduced*
licence quality versus generating the sounds ourselves.

## Components a DreamShaper run would need (both checked)

| Component | Repo | Licence (registry) | Note |
|---|---|---|---|
| SD1.5 VAE | `stabilityai/sd-vae-ft-mse` | **mit** | ✅ clean. FLUX's `ae.safetensors` is a 16-channel VAE and is **incompatible** with an SD1.5 UNet, so DreamShaper cannot run on what is already on disk |
| CLIP-L text encoder | already present (`clip_l.safetensors`, 246 MB) | shared with FLUX | SD1.5 and FLUX both use CLIP-L as a text encoder |

## Policy

```python
ART_COMMERCIAL_OK = {"apache-2.0", "bsd-3-clause", "cc0-1.0", "mit", "unlicense"}
```

A backend whose licence is outside this set may be *run* for comparison, but its output must not be
promoted into `assets/sprites/` without the owner accepting the licence in writing. Record the
decision here, in the same round, with the numbers that justified it.

## Provenance of shipped sprites

`python -m tools.art.gen --licence-board` prints the board above. The atlas provenance chain is:
model → `tools/art/gen.py` (single-subject, auto-keyed border, palette-locked to 32×32) →
`tools/art/pack_atlas.py` → `assets/atlas/*.png` + `*.json`, verified by `tools.art.verify`
(0 off-palette) and audited by `tools/qa/sprite_critique`.
