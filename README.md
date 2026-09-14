# Depths of Vaelmoor

A top-down action roguelite built by the Rogueworks studio (five Hermes agents, no paid
dependencies). Descend through 15 floors across 4 biomes — Catacombs, Ember Warrens, Drowned
Vaults, Sunken Ossuary — fight 85 monster entries with 10 enemy behaviour archetypes, take
3-act boss fights, collect 150 items including 8 build-defining legendaries, and spend the
essence you die with on a 5-branch meta-progression tree.

Runs on pygame-ce. Fully deterministic: every run is reproducible from a seed.

## Quickstart

```bash
cd C:\Users\dbshe\rogueworks
.venv\Scripts\python.exe -m game.main
```

That opens the title menu. To launch straight into a run, add `--new-run`.

## Controls (defaults; remappable in Settings → Controls)

| Action | Key |
|---|---|
| Move | W A S D / arrow keys |
| Attack | SPACE |
| Dash | LEFT SHIFT |
| Ranged | J |
| Interact | E |
| Inventory | TAB |
| Pause / menus | ESC |
| Profiler overlay | F1 |

Gamepad is supported (enable it in Settings → Controls).

## CLI

```
python -m game.main [--seed N | 0..2 | 0,3,7]   run seed or seed list/range
                    [--daily]                   daily run, seed = today's date
                    [--curses id,id,...]        apply curses at run start
                    [--endless]                 keep descending past floor 15
                    [--new-run]                 ignore save, start fresh
                    [--floor N]                 start on floor N (debug)
                    [--headless --turns N]      no window; QA / CI path
                    [--shot T,T,... --shot-dir DIR]  render frames to PNGs
                    [--record F / --replay F]   deterministic input replay
                    [--resolution WxH]          1280x720 / 1920x1080 / 2560x1440
                    [--fullscreen] [--vsync] [--fps N]
                    [--data-dir D / --mod-dir D] content / mod overrides
```

## Modes

- **Daily run** — one fixed seed per calendar day; everyone faces the same dungeon.
- **Cursed runs** — stack curses for a +15% essence multiplier each.
- **Endless** — after the final boss, floors keep coming with escalating stats.
- **Meta-progression** — death bankrolls a 5-branch tree (Vitality / Might / Agility /
  Fortune / Lantern) with respec; unlocks 3 classes and 5 ascension tiers.

## Verifying a build

```bash
.venv\Scripts\python.exe -m game.main --headless --turns 300 --seed 0..2
.venv\Scripts\python.exe -m tools.validate_data
.venv\Scripts\python.exe -m tools.art.verify
.venv\Scripts\python.exe -m tools.selftest
.venv\Scripts\python.exe -m tools.studio.verify_gate --seeds 0 1 2 --turns 300
```

A healthy build exits 0 everywhere with `violations=[]` and all 7 gates green.

## Modding

Content lives in `game/data/*.json` (monsters, items, affixes, rooms, biomes, statuses).
Point `--mod-dir` at a folder with override JSONs to layer changes on top without editing
the base files; `python -m tools.validate_data --mod-dir D` validates an override set.
Schema reference: `docs/CONTRACTS.md`.

## The studio

Built by five agents — **forge** (director: design, tickets, review, integration),
**chip** (game code), **pixel** (sprites, tiles, VFX, UI art), **lore** (bulk game-data
JSON), **lens** (headless playtests, frame audits) — plus **tempo** (original score) and
**WARDEN** (independent editor). Design docs in `docs/`, round history in
`docs/PROGRESS.md` and `runs/reports/`. All models are free-tier cloud or local; the game
itself runs offline on pygame-ce + stdlib.
