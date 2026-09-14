# tools/ — rogueworks build tooling

Run everything with the project venv (the `.exe` launcher is blocked by device policy):

```bash
cd /c/Users/dbshe/rogueworks && P="MSYS_NO_PATHCONV=1 .venv/Scripts/python.exe"
```

| Tool | Command | What it does |
|---|---|---|
| content validator | `$P -m tools.validate_data` | `game/data/*.json` against CONTRACTS §4 |
| self-test | `$P -m tools.selftest` | deps, palette, atlas, content, imports, invariants, headless run |
| raw → sprites | `$P -m tools.art.pixelize --split panels` | background key + palette lock + 32px slicing |
| sprites → atlas | `$P -m tools.art.pack_atlas --name <set>` | `assets/atlas/<set>.png` + `<set>.json` |
| art gate | `$P -m tools.art.verify` | palette lock at tolerance 0, atlas geometry, aliases |
| placeholders | `$P -m tools.art.placeholders` | flat fallback art in `assets/placeholder/` |
| screenshots | `$P -m tools.qa.shot --seed 1 --frames 10,60 --out runs/shots` | drives `game.main --headless --shot` |
| scripted run | `$P -m tools.qa.scripted_run --seed 1 --turns 300` | scripts a run, audits the §3.1 summary |

Every tool supports `--help` and `--json`. Exit codes: **0** ok (an empty input dir is ok, it
prints `0 ... found`), **1** something failed, **2** prerequisite missing (e.g. game not built).
Every tool prints one clear `ERROR:` line instead of a traceback; `TOOLS_DEBUG=1` restores the
traceback while developing.

## Art pipeline

```
assets/raw/*.png --pixelize--> assets/sprites/<set>/ --pack_atlas--> assets/atlas/<set>.{png,json} --verify--> exit 0
```

* **Chroma key** `#ff00ff` is deliberately *not* a palette colour, so it can be cut safely.
  Default `--key family` additionally removes the off-key magenta AI sheets come back with
  (`r > 140 and b > 100 and g < 0.75*min(r,b)`); pixelize refuses any rule that would key out a
  locked palette colour. Slicing: `--split grid` (fixed 32px cells), `--split panels`
  (auto-detect the sprite panels on an AI sheet, snapped outward to the 32px grid),
  `--split manifest` (named rects, below).
* **Frame names** for `--split manifest` come from `assets/raw/manifest.json`:

  ```json
  {"version": 1,
   "sheets": [{"raw": "assets/raw/monsters_catacombs.png", "name": "monsters_catacombs", "cell": 128,
               "frames": {"monster_bone_rat": [0, 0, 128, 128], "bone_rat_walk_1": [1, 0]}}]}
  ```

  `[x, y, w, h]` is a pixel rect; `[col, row]` uses the sheet's `cell`. This is the only way to
  get frame names that match the `sprite` fields in `game/data/*.json`.
* **Aliases** live in `assets/aliases.json` (`{"version":1,"aliases":{alias: frame}}`) and are
  resolved by the game's Atlas loader. `verify` checks them read-only — it never duplicates an
  alias into atlas JSON, because two frames sharing a rect is an error.

## Known gaps

* Contract §4 only cross-checks `sprite` values against atlases; `statuses.icon`, `biomes.tileset`
  and `rooms.props` are free strings the validator does not resolve.
* `qa.shot` and `qa.scripted_run` are read-only CLI drivers; they never import game internals.
