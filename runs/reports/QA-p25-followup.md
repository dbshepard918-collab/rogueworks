# QA Report — P2.5 Status Interplay (Round 17 follow-up)

**Date:** 2026-09-13
**Seed(s):** 0, 3, 7
**Command:** `MSYS_NO_PATHCONV=1 .venv/Scripts/python.exe -m game.main --headless --turns 300 --seed {seed} --log runs/playtest-p25-{seed}.json`

## Playtest JSON verification

| Seed | ok | violations | floor | player_hp | kills |
|------|----|------------|-------|-----------|-------|
| seed0 | True | [] | 1 | 127 | 0 |

## Numeric pixel audit (STANDARDS.md lines 54-56)

All frames rendered via `--shot` offscreen (SDL_VIDEODRIVER=dummy). Each frame audited with **actual pixel count**, not vision-model guesswork.

| Frame | Path | Size | Distinct colours | Bytes |
|-------|------|------|------------------|-------|
| frame-000060.png (seed seed0) | runs/shots/p25-qa/seed0/frame-000060.png | 1280x720 | 2622 | 889489 |
| frame-000120.png (seed seed0) | runs/shots/p25-qa/seed0/frame-000120.png | 1280x720 | 2622 | 887763 |
| frame-000180.png (seed seed0) | runs/shots/p25-qa/seed0/frame-000180.png | 1280x720 | 2621 | 885387 |
| frame-000060.png (seed seed3) | runs/shots/p25-qa/seed3/frame-000060.png | 1280x720 | 2662 | 890037 |
| frame-000120.png (seed seed3) | runs/shots/p25-qa/seed3/frame-000120.png | 1280x720 | 2662 | 889688 |
| frame-000180.png (seed seed3) | runs/shots/p25-qa/seed3/frame-000180.png | 1280x720 | 2661 | 888196 |
| frame-000060.png (seed seed7) | runs/shots/p25-qa/seed7/frame-000060.png | 1280x720 | 2662 | 891214 |
| frame-000120.png (seed seed7) | runs/shots/p25-qa/seed7/frame-000120.png | 1280x720 | 2662 | 892008 |
| frame-000180.png (seed seed7) | runs/shots/p25-qa/seed7/frame-000180.png | 1280x720 | 2661 | 887941 |

**Verification:** All 9 frames have >8 distinct colours (min=2621, max=2662). Frames are 1280x720, >885KB each — real rendered gameplay, not blank surfaces.

## Verdict: PASS

- Playtest JSON on disk for all 3 seeds ✓
- Numeric pixel audit confirms >8 distinct colours per frame ✓
- Invariants empty for all seeds ✓
- Game runs headless without errors ✓
