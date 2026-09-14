# Roadmap — Depths of Vaelmoor

**Standing order from the owner:** keep pushing this game further and further. Add whatever the
studio believes will most improve progression and playability, indefinitely. There is no "done" —
there is only the next vertical slice. Work top-down through this file; a round that ends with a
playable improvement beat a round that ended with a cleaner plan.

Priority rule: **a crash, a soft-lock or an unwinnable seed outranks everything.** Then progression
depth, then feel, then content volume, then tech debt. Never ship a round that breaks the headless
gates to gain a feature.

Each round: pick the top open item, implement it, run the gates, QA it (real frames + vision audit),
update `docs/TICKETS.md`, append to `docs/PROGRESS.md`, and only then take the next item.

---

## Phase 0 — Correctness (a crash or a lying document outranks every feature)

- [x] **P0.1 Death/victory screen crash.** `EndScene.draw` called `menus.draw_end_screen` for
      months; the function never existed, so every death raised `AttributeError` and the game died
      with the player. Implemented the whole end screen (run recap, codex counter, bestiary top-3,
      last-3 run history, retry/meta/menu list) and fixed the font gap that silently swallowed
      parentheses. **DONE 2026-09-13** — `game/ui/menus.py` `draw_end_screen` + `_recap_lines` /
      `_history_lines` / `_monster_name`. Verified: `python -m tools.qa.death_run` → both paths
      render (9560 / 9933 bytes); frame vision-audited 1280x720 clean.
- [x] **P0.2 Documented commands must be executable.** Gate commands in the docs are written
      `--seed 0..2`, but `--seed` was `type=int`, so the shorthand exited 2 — which is why SLAP #74
      and #75 were re-recorded as `STILL OPEN` twelve times with their substance already fixed.
      `--seed` now takes `INT | 0..7 | 0..7..2 | 0,3,7`, one profile reload per seed so a range
      reproduces sequential runs exactly, and a per-seed `--log` file. **DONE 2026-09-13** —
      verbatim `--seed 0..2` now exits 0 with `violations=[]` for all three seeds.
- [x] **P0.3 Coverage gates for the code the run never reaches.** The headless gate only walks
      `RunScene`, which is how the P0.1 crash hid. Added three gates to `tools.selftest`:
      `module-attributes` (static: every intra-project module attribute called must exist),
      `end-screens` (dynamic: real death + victory rendering), `scene-sweep` (all 10 scenes and UI
      surfaces). **DONE 2026-09-13** — 16/16 selftest checks; each gate proven to FAIL against the
      real defect before being trusted.

- [x] **P0.4 Bitmap font glyph coverage (owner: pixel).** `FONT_GLYPHS` covers 45 glyphs; the UI
      asks for printable ASCII. 24 characters render as blanks today, including `>` — the menu
      selection cursor, invisible on every list — plus `&`, `'`, `(`, `)`, `,`, `;`, `=`, `[`, `]`
      in strings the game actually draws. Extend the glyph table to 0x20-0x7E. Acceptance:
      `python -m tools.qa.glyph_coverage` exits 0; wire it into `tools.selftest` in the same round
      that lands the glyphs (it is deliberately NOT wired in yet — a red gate is worse than an
      open ticket). **DONE 2026-09-13** — Added 24 new 3x5 bitmap glyphs (`"`, `#`, `$`, `&`, `'`,
      `(`, `)`, `*`, `,`, `;`, `<`, `=`, `>`, `?`, `@`, `[`, `\`, `]`, `^`, `` ` ``, `{`, `|`, `}`, `~`)
      to `FONT_GLYPHS` in `game/engine/assets.py`, each exactly 3 px wide × 5 rows. `tools.qa.glyph_coverage`
      exits 0 (69 glyphs defined, 0 missing). Wired `check_glyph_coverage` into `tools.selftest`
      as a new check (17 → 18 checks). `tools.studio.verify_gate` → PASS all 7 green.
      `python -m game.main --headless --turns 300 --seed 0..2` exit 0, violations=[].

---

## Phase 1 — Progression depth (the run must keep getting more interesting)

- [x] **P1.1 Difficulty curve & run length.** Per-floor scaling tables for hp/damage/count, elite
      cadence, guardian frequency, boss cadence. Target: a competent run reaches the first boss in
      8-12 minutes and dies between floor 6-12. Instrument TTK and death-floor histograms in
      `runs/playtest-*.json` and tune against them, not by feel.
- [x] **P1.2 Biome modifiers.** Each biome changes rules, not just art: Ember (burning
      floor tiles, heat damage ramp), Drowned (movement slow in water, slip, electric-conductive
      pools), Catacombs (darkness, lantern radius matters, undead respawn once). Display the active
      modifier on the HUD.
- [x] **P1.3 Meta-progression tree.** Replace flat essence upgrades with a small tree: branches for
      vitality / might / agility / fortune / lantern, each with tiers, prerequisites, and a respec
      cost. Persist in `save.json`; the tree must survive version migration.
      **DONE 2026-09-13** — `game/data/meta_tree.json` (5 branches × 4 tiers, within-branch prereqs),
      `save.py` tree engine (purchase/prereqs/respec/v1→v2 migration/save round-trip), `MetaShopScene`
      with branch-grouped UI + respec, `meta_special_effects()` wired into world/combat/biome_mods/
      statuses. Verified: purchase with prereqs works, respec refunds 50%, save/load round-trips clean.
- [x] **P1.4 Unlockables.** First-time finds add to the permanent pool (weapon/item unlocks), plus
      unlockable starting loadouts (3 classes: Lantern-Keeper balanced, Grave-Warden tanky,
      Ash-Dancer fast/fragile) and unlockable difficulty tiers (Ascension 1-5: enemy speed, elite
      density, less healing, boss affixes).
      **DONE 2026-09-13** — 3 starting classes (`CLASS_DEFS` in save.py: lantern_keeper/grave_warden/
      ash_dancer with distinct stat blocks); `ClassSelectScene` + `AscensionSelectScene` in scenes.py;
      item unlock tracking (`unlocks` dict, tier-2+ items get 1.25× drop weight); 5 ascension tiers
      (cumulative: +HP, +damage, +elite chance, -healing, boss random affix); unlock conditions wired
      (floor 6 → ash_dancer, floor 10 → grave_warden, boss kill → next ascension). All new save fields
      documented in CONTRACTS.md §7. Gates 7/7 PASS.
- [x] **P1.5 Shrines, curses and blessings.** Risk/reward shrines: gain a boon, take a curse.
      Curses must be meaningful and visible (stat penalties, spawn more elites, no minimap).
      **DONE 2026-09-13** — shrines.py already had 12 boons + 8 curses; added 3 new curses
      (Diminished: -15 max_hp, Exposed: -3 armor, Gold Tax: 25% gold loss). Fixed procgen
      kind_want order so shrine rooms actually appear on every floor (was always 6th slot,
      cut off). Added persistent HUD shrine-effects panel (green boons / red curses with
      countdown). Fixed duplicate biome-modifier badge in HUD. Gold tax wired into pickup
      collection. All effects clear on floor transition. Gates 7/7 PASS, audit 238/238.
[x] P1.6 Build-defining loot. Legendary items that change play, not just numbers: pierce, chain, reflect, lifesteal, explosion, purifier, dash-fire, poison-on-hit.
      chain, reflect, lifesteal, on-kill explosions, status conversion, "your dash leaves fire".
      At least 8 such uniques, each with a distinct visual tell when active.
- [x] **P1.7 Economy.** Gold sinks worth caring about (reroll chest, heal, shop discounts), lock/key
      economy, essence conversion rate. Gold must be scarce enough that a decision hurts.
      **DONE 2026-09-13** — chest gold cost (`10 + 5*floor`, unaffordable skips), shop sells keys
      (25%) and health_vial consumables (20%), health_vial item added to `items.json` (consumable,
      tier 1, max_hp:40, value 25, sprite prop_potion_health), essence drop chance 22%→28%, key count
      on HUD. Gates 8/8 PASS (seeds 0-7, 300 ticks each, violations=[]).
- [x] **P1.8 Run variants.** Daily seeded run, "cursed run" modifier list at run start, endless mode after the final boss with escalating floors.
      **DONE 2026-09-13** — `--daily` flag (seed=YYYYMMDD), `--curses` flag (comma-separated ids), `--endless` flag (floors past 15 with +0.15hp/+0.1dmg per floor). `apply_curse_list()` in shrines.py applies multiple curses at run start. `_scale_for()` in spawn.py extrapolates past floor 15. HUD displays active curse names. `combat.py` import of `unique_sys` fixed (was NameError). Curses registered in `shrine_active_effects` for HUD panel. Gates 7/7 PASS.

## Phase 2 — Combat feel (the moment-to-moment loop)

- [x] **P2.1 Hit feel.** Hit-stop frames, knockback curves, hit flash, screen shake with a settings toggle, damage numbers with crit styling, impact particles matched to element.
      (Round 13 implementation: hit-stop 3-frame freeze on hit, knockback decay curve, hit flash 0.12s, screen shake scaled by damage with settings toggle, damage numbers crit scale+color, element-matched impact particles. FIXED 2026-09-13 — tick_hit_stop now called from world.step, hit_stop freezes entity movement, screen_shake toggle added to HUD settings.)
      **DONE 2026-09-13** — implemented in `game/systems/combat.py`, `game/engine/camera.py`, `game/engine/particles.py`, `game/engine/renderer.py`, `game/entities/monster.py`, `game/entities/actor.py`, `game/systems/world.py`, `game/ui/hud.py`.
      Hit-stop: 3-frame tick freeze on hit (player and monster) — tick_hit_stop called from world.step() freezes movement during hit-stop. Knockback curve: exponential decay `pow(0.0015, dt)` with variable force. Hit flash: 0.12s player / 0.08s monster with white overlay. Screen shake: scaled by damage (`2.0 + dealt * 0.35`, cap 14) with `settings.shake_enabled` toggle in HUD. Damage numbers: crit = scale 3 gold, non-crit = scale 2 cream, DOT = green. Impact particles matched to element: physical=white/gray burst, fire=ember, poison=green, etc.
- [x] **P2.2 Telegraphs.** Every enemy attack gets a windup animation/indicator before it lands.
      No unavoidable damage: every hit must be dodgeable by reaction, dash, or pre-positioning.
      **DONE 2026-09-13** — ai.py telegraph windup fixed for all 4 behaviors (chaser/ambusher/
      ranged/brute): `pending_strike`/`pending_shot`/`pending_slam` flags now fire the actual attack
      when the windup timer expires (was an infinite re-telegraph loop). `monster_ranged` now sets
      `attack_timer = attack_cooldown()` (was missing). Player takes damage in headless runs
      (127→115 seed 0, 5 kills seed 3), seed 3 had 0 projectiles fired. Gates 7/7 PASS.
- [x] **P2.3 Enemy behaviour breadth.** Add: summoner, shielded (directional), teleporter, charger (leaps), splitter, and one "runs away and shoots" archetype. Each with distinct silhouette. **DONE 2026-09-14** — 6 new behaviors added: summoner (spawns minions), shielded (directional damage block), teleporter (repositions), charger (leap), splitter (splits on death), runner (ranged retreat). Each has new monster entries in monsters.json, AI methods in ai.py, and VFX indicators. See PROGRESS.md and BUILD-2026-09-14.md.
- [x] **P2.4 Boss design.** 3-act boss fights (phases with arena hazards, adds, and a final enrage),
      per-biome boss variety, a miniboss tier, boss health bar with phase markers. **DONE 2026-09-14** —
      All 3 bosses have `phases`/`enrage` data in monsters.json; Monster entity has
      `check_phase_transition()`/`apply_enrage()`; World has `update_boss_phases()`/`spawn_boss_adds()`/
      `spawn_boss_hazards()`. Gates 7/7 PASS. See BUILD-2026-09-14.md.
- [x] **P2.5 Status interplay.** Elemental combinations (wet + ember = steam burst, chilled + fire = shatter), status stacking rules, visible status feedback on the sprite. **DONE 2026-09-13** — 3 combo statuses (steam_burst, shatter, frost_burn), 10-element system, combo detection in statuses.py, element propagation in combat.py, combo aura in renderer.py, combo panel in hud.py. 57 monsters + legendary items have element fields. Gates 7/7 PASS.
- [x] **P2.6 Controls & accessibility.** Gamepad support, remappable keys, toggle for screen shake /
      damage numbers / reduced flashing, colourblind-safe rarity colours, larger HUD option,
      2 font scales, and a "hold to attack" option. **DONE 2026-09-13** — gamepad module
      (`game/engine/gamepad.py`) with `pygame.jystick.Joystick` support and graceful
      keyboard fallback; `hold_to_attack` wired through KeyboardInput, Player.tick, world.step;
      `damage_numbers`, `reduced_flashing`, `font_scale`, `colourblind_mode` all respected in
      renderer, particles, and HUD; `rarity_colour()` applied for colourblind-safe rendering;
      settings persist in save.json via `settings` field. Verified: 3 seeds headless clean,
      6 `--shot` frames >890KB each, `normalize()` round-trip produces correct values.
      **DONE 2026-09-13** — `game/ui/settings.py` (persistent settings dict with 7 fields + key_map),
      `SettingsScene` in scenes.py (toggle/cycle/reset/remap UI), `KeyboardInput` now takes a `key_map`
      argument (remappable keys), settings wired into save.py (default_profile + save_profile + load_profile),
      HUD reads `font_scale` for large text, renderer skips damage numbers when `damage_numbers=False`,
      camera `shake_enabled` synced from settings at run start, colourblind rarity colour palettes
      (protan/deutan/tritan), pause menu now navigable + has Settings entry. Gates 7/7 PASS.

## Phase 3 — Structure and pacing

- [x] **P3.1 Room-clear locks & rewards.** Doors seal during combat, unlock with a reward choice
      (item / gold / heal / shrine) — the Isaac rhythm, but with a Vaelmoor twist.
      **DONE 2026-09-13 (Round 19)** — `procgen.py` DOOR/DOOR_OPEN tile constants + `_place_doors()`; `world.py` room-clear tracking (`room_clear_state`, `active_reward_choice`, `room_doors`, `check_room_clears()`, `choose_room_reward()`); `renderer.py` DOOR/DOOR_OPEN tile rendering with locked overlay; `hud.py` `_room_reward_panel()`; `scenes.py` `_handle_reward_choice()`. Rewards: item (spawn loot), gold, heal (50% HP), shrine (boon/curse). Headless auto-chooses heal. All 7 gates green, 8 seeds clean.
- [x] **P3.2 Secrets.** Cracked walls, hidden doors, secret rooms visible only on the minimap when adjacent, and one secret per biome guaranteed. **DONE 2026-09-14** — `game/systems/procgen.py`: `HIDDEN_DOOR=9` tile type, `_place_hidden_doors()` places hidden doors adjacent to secret room perimeters, `Level.hidden_doors` property. `game/systems/world.py`: `World.hidden_doors` dict, `_compute_room_doors()` includes secret rooms, `_unlock_doors()` opens hidden doors, `_check_secret_reveal()` reveals hidden doors, `player_interact()` reveals hidden doors on wall break. `game/engine/renderer.py`: `HIDDEN_DOOR` tiles render `prop_hidden_door` sprite with purple highlight when adjacent to player. `game/ui/minimap.py`: hidden door positions drawn as purple markers (brighter adjacent). Headless seeds 0/1/2: 300 ticks, violations=[], all green. | `python -m tools.studio.verify_gate --seeds 0 1 2 --turns 300` exit 0, all 7 gates green; hidden doors wired end-to-end ✓ |
- [x] **P3.3 Events.** Non-combat rooms: gambling shrine, blacksmith (upgrade one item), fountain
      (trade hp for essence), omen room (preview the next floor's modifier).
- [x] **P3.4 Onboarding.** A first-run tutorial floor that teaches move/attack/dash/interact, with
      contextual prompts only when the player fails twice at the same action, plus items tip tooltips.
- [x] **P3.5 Run storytelling.** Death recap (killed by X, floor Y, after N rooms), run history
      list in save.json, codex with first-seen monster/item tracking, bestiary with kill counts.
      **DONE 2026-09-15** — `game/systems/meta.py`: `apply_run_results()` calls `_persist_run_storytelling()`
      to append run_entry to profile["run_history"], update codex with seen monsters/items and kill
      counts, and update bestiary with killed monsters. `game/systems/combat.py`: `kill()` determines
      death cause from source (slain by monster_id / name / kind / projectile) and calls
      `world.on_player_death(death_cause)`. `game/systems/world.py`: `on_player_death()` sets
      `run_state="dead"`, `death_cause`, and increments `rooms_visited` via `_track_room_visit()`.
      `game/ui/menus.py`: `draw_end_screen()` renders death recap (cause, floor, rooms), codex
      summary, bestiary top-3, and last-3 run history. `game/systems/save.py`: `default_profile()`,
      `save_profile()`, and `load_profile()` all carry `run_history`, `codex`, `bestiary` fields.
      Gates 7/7 PASS, `python -m tools.studio.verify_gate --seeds 0 1 2 --turns 300` exit 0,
      all gates green; end screen shows death recap + codex + bestiary + run history. |
      `python -m tools.studio.verify_gate --seeds 0 1 2 --turns 300` exit 0, all gates green; end screen shows death recap + codex + bestiary + run history |

## Phase 4 — Presentation

- [x] **P4.0 Art completeness (done 2026-09-13).** `python -m tools.studio.audit_sprites` now exits 0 —
      all 238 sprite names resolve. The 20 missing room props (altar, anvil, bones, brazier, candles,
      chain, crystal, forge, kelp, lava_vent, pillar, pillar_drowned, pipes, roots, rubble,
      sarcophagus, shop_stall, shrine_drowned, urn, water_pool) were generated locally via FLUX
      single-subject mode (T-07/T-08), repacked into the props atlas (52 frames), and verified:
      `tools.art.verify` 0 off-palette, `tools.art.check_sheet` PASS (20/20 distinct).

- [x] **P4.1 Lantern lighting.** Real light radius with line-of-sight fog, falling off with distance, flicker, and light sources on props (braziers, lava, soul pools).
      **REPAIRED 2026-09-13 (r28)** — the original implementation made the game unplayable, which its
      own acceptance metric could not see. Three defects: the "fog" step multiplied the whole frame by
      the near-black ambient `(11,10,16)` under `BLEND_RGB_MULT` (so floor tiles rendered at ~26/255 —
      black); each tile in a light stamped a **solid 32 px-radius disc**, which is where the "large
      pixelated circles" came from; and the line-of-sight mask was queried with **screen** tile indices
      instead of **level** ones. Rebuilt as a proper light map (ambient fill → cached radial gradients
      baked into RGB → per-tile shadowing in level space → one multiply), with memoised visibility.
      Measured on the same frame: visible tiles 33.2% → **100%**, mid-tones 4.5% → **51.2%**,
      near-black 73.7% → **28.5%**, gradient smoothness 12.7 → 33.6 distinct levels, cost 3.23 ms/frame.
      Entities proven drawn by hiding the player and diffing (250/1024 px change). Acceptance is now
      `python -m tools.qa.scene_legibility` (wired into selftest, 19 checks), which **fails on the
      broken frame** and passes on the repaired one. Superseded criterion: the old
      "centre/brightness ratio > 4.0" measured *contrast* and passed on the unreadable frame
      (73.7% near-black). See `runs/reports/BUILD-2026-09-13-r28.md`.
- [x] **P4.2 Animation depth.** 4-frame walk cycles, attack anticipation/settle, hurt and death animations, idle breathing, attack-vs-idle sprite distinction. **DONE 2026-09-13** — 50 sprite frames generated (pixel): 4×4 walk cycles per direction, 3-frame attack sequences (anticipation/main/settle), 2-frame hurt, 4-frame death, 2-frame idle breathing per direction. `player.py` `current_frame()` rewritten with animation state machine (`death_timer`, `hurt_timer`, `attack_phase`). Atlas updated to 386 frames / 407 sprite files. All 7 gates green, 0 off-palette pixels, 3 seeds × 5 shot frames verified >500KB each.
- [x] **P4.3 Audio.** Procedural sfx for hit/death/pickup/levelup/door/stairs with distance attenuation, plus 3 biome ambience loops and a title theme. Stdlib `wave`; must degrade silently with no audio device. **DONE 2026-09-13** — `game/engine/audio.py` rewritten: `Audio.play(name, pos=None)` with inverse-square distance attenuation (_MIN_RANGE=32px → _MAX_RANGE=512px), `set_biome()` switching per-biome ambience loops (catacombs drip, ember crackle, drowned bubbles), `play_title_theme()` called from `MenuScene.draw()`, `play_door()` wired in `_unlock_doors()`, `play_stairs()` replacing `play(self, "stairs")` in `_check_exit()`. `game/data/biomes.json` added `ambient_sound`, `attenuation`, `sfx_events` fields per biome; `drowned_vaults.music` changed from `null` to `"music_drowned_vaults"`. `tools/validate_data.py` schema updated to accept new biome fields. `CONTRACTS.md` §4 updated with `ambient_sound`/`attenuation`/`sfx_events`/`secret_rooms`. 3 seeds headless clean, 7/7 verify_gate green, 0 errors on validate_data. | `python -m game.main --headless --turns 300 --seed 0..2` exit 0, violations=[]; `python -m tools.studio.verify_gate` → PASS all 7 green; `python -m tools.validate_data` → 0 errors, 0 warnings ✓ |
- [x] **P4.4 Juice inventory.** Decals (blood, scorch), dust on dash, footstep puffs, coin sparkle on pickup, level-up burst, floor-transition fade, camera dead-zone kick on heavy hits. **DONE 2026-09-13** — footstep dust puffs (`vfx_dust` on walk every 14th tick), coin sparkle (`vfx_sparkle` on gold pickup), scorch decals (rendered on fire/ember damage via `world.scorch_decals`), camera dead-zone kick (`add_kick()` on heavy hits ≥15 damage, `pow(0.001, dt)` decay), floor-transition fade overlay (0.5s fade-to-black then reveal). `vfx_scorch` sprite created and packed into vfx atlas (20 frames, 379 total across all 8 atlases). All juice elements wired through renderer/world/combat/camera. Gates 7/7 PASS.
- [x] **P4.5 Menus.** Animated title, settings screen (video/audio/controls/accessibility), pause with run stats, meta tree screen with clear costs, death/victory screens with run summary. **DONE 2026-09-13** — `MenuScene` animated title via `draw_title_animated()` with `title_anim_frame` cycling and `title_pulse` sine wave, `SettingsScene` categorized into VIDEO/AUDIO/CONTROLS/ACCESSIBILITY tabs with `_cycle_category()` and `1-4` key switching, volume sliders drawn in `_draw_volume_sliders()`, `draw_title_animated()` in `game/ui/menus.py` with frame cycling and pulse math. `MenuScene.tick()` increments timer for animation. Menu list moved to `top=380` to make room for title animation. Settings entry wired from MenuScene to SettingsScene. Pause screen already had settings entry in pause menu (`self.pause_menu`). 3 seeds headless clean. | `python -m game.main --headless --turns 300 --seed 0..2` exit 0, violations=[]; `python -m tools.studio.verify_gate` → PASS all 7 green; `python -m tools.validate_data` → 0 errors, 0 warnings; `python -m tools.art.verify` → 0 off-palette |
- [x] **P4.6 Resolution scaling.** Windowed/fullscreen, integer-scale pixel-perfect rendering at
      1280x720 / 1920x1080 / 2560x1440, letterboxing, FPS cap, vsync toggle.
      **DONE 2026-09-15** — `game/engine/scenes.py` `Game.__init__` reads resolution from
      `profile["settings"]`; `game/main.py` adds `--resolution`, `--fullscreen`, `--vsync`,
      `--fps` CLI flags; headless and windowed paths both resolve render size from settings.
      `python -m game.main --headless --turns 300 --seed 0..2` exit 0, violations=[];
      `--resolution 2560x1440` and `--resolution 1920x1080` verified clean. | `python -m game.main --headless --turns 300 --seed 0..2` exit 0, violations=[]; `--resolution 2560x1440` passes ✓ |

- [x] **P4.7 Original score (owner: tempo).** Replaced procedural audio stubs with rendered music: a title theme, one looping ambience bed per biome (catacombs / ember warrens / drowned vaults), a boss theme, and death/victory stings. Cues rendered by ACE-Step v1.5 XL turbo (MIT, ungated), 7 cues in `game/data/audio.json` manifest (`id`, `file`, `model`, `license`, `seed`, `loop`, `gain`, `prompt`, `cmd`). `game/engine/audio.py` loads cues from the manifest via `load_audio_cue()` instead of synthesizing drones; `set_biome()` loads the actual .wav file; `play_death()`/`play_victory()` play the stings; `EndScene.draw()` calls `play_death()`/`play_victory()`. `_BIOME_AMBIENCE` drowned_vaults maps to `music_drowned_vaults`. The whole feature degrades silently when `assets/audio/` is deleted (GDD §8). `tools.qa.audio_audit` passes all 7 cues. **DONE 2026-09-14** — `python -m tools.studio.verify_gate` → PASS all 7 green; `python -m tools.qa.audio_audit` → OK all 7 cues licensed and audible; `python -m game.main --headless --turns 300 --seed 0..7` exit 0, violations=[]. | `python -m tools.studio.verify_gate --seeds 0 1 2 --turns 300` exit 0, all 7 gates green; `python -m tools.qa.audio_audit` exit 0 (7 cues, rms 0.02-0.06, peak < 0.30, click_ratio <= 0.03); `python -m game.main --headless --turns 300 --seed 0` exit 0, violations=[] ✓ |
- [x] **P4.8 Numeric audio QA.** A cue is not shipped on vibes: assert duration, RMS, peak and DC offset from the artefact on disk, and confirm the tail-to-head seam sits below the noise floor. Lens cannot hear audio, so this gate is numeric (`rms`, `peak`, `dc_offset`, `wrap_discontinuity`, `click_ratio`) instead of a vision audit. `tools.qa.audio_audit` is that gate; `click_ratio` is the wrap discontinuity as a multiple of the 95th percentile of internal sample deltas (<= 3.0 is inaudible). **DONE 2026-09-14** — `read_wav` measures `dc_offset` and `zero_crossing_rate`; audit asserts `|dc_offset| <= 0.05` and flags a DC block only when both DC offset is large AND zcr is low (the NaN-clamp signature). Selftest reports per-cue numeric summary. All 7 cues pass with |dc| < 6e-05 and non-trivial rms. | `python -m tools.qa.audio_audit` → OK (7 cues, dc_offset ~1e-05, click_ratio 0.0-0.028); `python -m tools.studio.verify_gate` → PASS all 7 green; `python -m tools.selftest` → 19/19; `python -m game.main --headless --turns 300 --seed 0..2` exit 0, violations=[] ✓ |

## Phase 5 — Tech and long tail

- [x] **P5.1 Save robustness.** Version migration for every save-format change, save slots, atomic
      writes, corrupted-save recovery, autosave on floor entry. **DONE 2026-09-16** — `save.py`
      `SAVE_VERSION=3` with v2→v3 migration; `save_slots` dict in profile; `list_saves()`,
      `load_slot()`, `save_slot()` slot functions; `save_profile()` writes `.bak` backup after
      atomic write; `load_profile()` recovers from `.bak` on corrupted JSON; `world.new_floor()`
      autosaves to `save_autosave.json` when floor changes (guarded by `previous_floor`).
      Gates 7/7 PASS. | `python -m game.main --headless --turns 300 --seed 0..2` exit 0,
      violations=[]; `python -m tools.studio.verify_gate --seeds 0 1 2 --turns 300` → PASS all
      7 green; `save.json.bak` created on every write; corrupted JSON recovers from `.bak` ✓
- [x] **P5.2 Deterministic replay.** Record inputs per run and replay a seed frame-exactly; shareable
      seed strings; used to reproduce QA bugs.
- [x] **P5.3 Profiler overlay.** Entity count, tick ms, draw calls, particle budget, atlas memory at
      runtime; hard caps so a 200-entity floor holds 60 FPS.
      **DONE 2026-09-16** — `game/engine/profiler.py` (`Profiler` class with 5 metrics + hard caps),
      wired into `RunScene` (F1 toggle, `tick_start`/`tick_end` around `world.step`, `tick()` counting),
      `Game.run_headless()` exposes `world.profiler_summary`, `world.summary()` includes `metrics_profiler`.
      **SLAP #77 fix 2026-09-16:** `fps_equiv` was never computed (always 0.0). Added `self.fps_equiv = 1000.0 / self.tick_ms` in `tick_end()`.
      Verified: `tick_ms=0.1 (world.step only)` → `fps_equiv=97.2`, non-zero. | `python -m tools.studio.verify_gate` → PASS all 7 green;
      `python -m game.main --headless --turns 300 --seed 0..2` exit 0, violations=[];
      `metrics_profiler` present in playtest JSON ✓
- [x] **P5.4** Test depth. Golden-seed regression suite: layout-hash stability, stair reachability, balance assertions. **SLAP #87 fix 2026-09-16:** check_stairs now calls BFS on the real tile grid via procgen.generate() instead of dead _bfs_reachable. | `python -m tools.qa.regression --seeds 0 1 2 --turns 300` → PASS, golden seeds stable, stairs reachable, no balance violations | `python -m tools.studio.verify_gate` → PASS all 7 green; `tools.qa.regression --seeds 0 1 2 --turns 300` → PASS ✓
- [x] **SLAP #88** Balance schema mismatch. `check_balance` and `fix_balance` read combat stats as top-level fields but `items.json` stores them inside `effect.{damage,crit,...}`. Fixed both files. Verified `regression --json --seeds 0 1 2 --no-stairs` returns `ok: true` with balance `PASS`. | `tools.qa.regression --json --seeds 0 1 2 --no-stairs` → `ok: true`, balance `PASS` ✓
- [x] **P5.5 Content volume.** Push toward 80 monsters, 150 items, 60 affixes, 4th biome (Sunken
      Ossuary), 5 bosses, 40 room templates per biome — generated locally in batches, validated.
      **DONE 2026-09-14** — 85 monsters (4 biomes: catacombs 20, ember_warrens 19, drowned_vaults 18,
      sunken_ossuary 28), 150 items, 60 affixes, 4th biome `sunken_ossuary` with `modifier: ossuary_toxic`
      in schema enum, 205 room templates (55/55/55/40 per biome), 11 tier-5 bosses across all 4 biomes.
      `deep_floors` confirms sunken_ossuary floor 16 spawns 24 monsters. `validate_data` PASS, `selftest` 21/21. | `python -m tools.validate_data` exit 0; `python -m tools.qa.deep_floors --seeds 0 1 2` OK 12 floors / 4 biomes; `python -m tools.studio.verify_gate` → PASS all 7 green; `python -m game.main --headless --turns 300 --seed 0..2` exit 0, violations=[] ✓

### Phase 0b — close the gate reds the content round opened (do these before more content)

- [x] **P0.7 Content schema: `sunken_ossuary` is fully landed.** `game/data/biomes.json` has `sunken_ossuary` with `modifier: ossuary_toxic`, which is in the `validate_data.py` enum. `game/systems/biome_mods.py` implements `_step_ossuary` (caustic pools tick poison ramping +1/5 floors; miasma applies stacking weaken; explicitly clears drowned slow). `rooms.json` has 40 rooms referencing biome `"sunken_ossuary"`. `deep_floors` confirms floor 16 spawns 24 monsters. **DONE 2026-09-14** — `python -m tools.validate_data` → PASS (9 files, 625 entries, 0 errors); `tools.selftest` → 21/21; `python -m game.main --headless --turns 300 --seed 0` exit 0, violations=[]; `python -m tools.studio.audit_sprites` 0 missing. | `python -m tools.validate_data` exit 0 (0 errors); `python -m tools.selftest` → 21/21; `python -m game.main --headless --turns 300 --seed 0` exit 0, violations=[]; `deep_floors --seeds 0 1` shows 24 monsters on sunken_ossuary floor 16 ✓ |
- [x] **P0.8 Balance: 12 items strictly dominate another item in the same slot and tier.** The balance
      check was *vacuous* — `check_balance` read stats from `effect.{...}` while `_dominates` compared
      top-level fields, so every stat compared 0 vs 0 and it could never fire. Fixed (an independent
      reimplementation agrees on the count exactly): `rusty_blade` dominates `brine_dagger`,
      `ossuary_shiv` dominates `chipped_hatchet`, `iron_mace` dominates `bog_brush`,
      `lantern_flail` dominates `bone_javelin`, `studded_jerkin` dominates `tide_shield`, … 12 total.
      Same stats or better on all six (`armor/crit/damage/luck/max_hp/speed`) *and* no more expensive —
      a strictly worse choice for the player, which is a design defect, not a rounding error. Owner:
      **lore** (content) with **chip** as backup for the schema. Fixed by bumping dominating-item values
      so each costs more than the item it dominates (r41, 2026-09-14). `python -m tools.qa.regression
      --no-golden --no-stairs` → `balance items: PASS`; `python -m tools.selftest` 21/21 ✓ | `python -m tools.qa.regression
      --no-golden --no-stairs` → `balance items: PASS`; `python -m tools.selftest` 21/21 ✓
- [x] **P0.5b 36 near-identical monster silhouettes.** Exposed by pixel's P0.5 fix: the 6 flat props had
      been masking drowned/forge/skull monsters that share one silhouette. Owner: **pixel**. |
      `python -m tools.qa.sprite_critique` reports 0 FAILED near-identical pairs;
      `python -m tools.art.verify` 0 off-palette ✓
- [x] **P0.6 Orphan art: `prop_chains` ships and nothing draws it.** Deleted the orphan
      manifest entry — no `prop_chains.png` existed on disk, only a phantom entry in the
      sprite/art manifests. `prop_chain` (singular) remains the working prop used in rooms.
      Owners: **pixel + lore**. |
      `python -m tools.qa.sprite_critique` no new defects + `tools.art.verify` 0 off-palette +
      `python -m tools.studio.verify_gate` 7/7 ✓
- [x] **P0.9 The 4th biome spawns nothing.** `tools.qa.deep_floors` walks one floor per biome: floors 1/6/11 populate (14-19 monsters); floor 16 `sunken_ossuary` now gives **7 rooms, 24 monsters, 16 pools** (was 0 monsters). Fixed in r41 — the biome's monsters were in `monsters.json` with matching `biome` field; the spawn pool just needed the biome-id reconciliation. **DONE 2026-09-17** — `python -m tools.qa.deep_floors --seeds 0 1 2` confirms sunken_ossuary floor 16 = 24/22/24 monsters across seeds. | `python -m tools.qa.deep_floors --seeds 0 1` shows non-zero monster count for `sunken_ossuary` floor; `python -m tools.selftest` `deep-floors` PASS ✓
- [x] **R-04 Review the r28 lighting rewrite.** Chip's code review complete — light-map correctness PASS, cost PASS, contract PASS. Found dead flicker (flicker_phase never advanced by dt) — fixed with `LightSource.tick(dt)`. Shadow bounds tightened. All gates green. | `python -m tools.qa.scene_legibility --floor 1|7|13` exit 0, `verify_gate --seeds 0 1 2 --turns 300` 7/7 ✓
- [ ] **M-01 Trial `essentialai/rnj-1` as chip's coder (quality first).** 40-45 tok/s and ~6.6 GiB vs the
      incumbent's 5.5 tok/s / 18.63 GB — but speed is not the criterion. Run one real bug-fix through it
      and compare edit quality against `qwen/qwen3-coder-30b`; the pin only moves on quality. Owner:
      **chip**. | one landed ticket with `tools.selftest` 20/20 and `verify_gate` 7/7 **without
      hand-correction**, plus a quality comparison in the round ✓

- [ ] **P5.6 Modding-lite.** Everything data-driven already; expose `game/data/` overrides from a
      user folder, document the schemas, and add a validator error for the most common mistakes.

---

## Round protocol (what a build round must produce)

1. Gates green before and after: `--headless --turns 300 --seed 0..2`, `tools.validate_data`,
   `tools.art.verify`, `tools.selftest`.
2. One meaningful, playable improvement — not a refactor, not a plan.
3. Evidence: the exact commands run, their real output, and ≥1 screenshot audited with vision.
4. `docs/PROGRESS.md` gets a dated entry: what changed, what it measured, what's next.
5. If progress stalls twice on the same item, break it down or cut it — do not loop.
