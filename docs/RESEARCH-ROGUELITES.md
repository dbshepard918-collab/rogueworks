# Roguelite Game Architecture Research

> **Date:** 2026-09-16  
> **Repos analyzed:** 8 (Pixel Dungeon, BevyRoguelike, Rusted Ruins, DeathtrapDungeon, tomuxmon/bevy_roguelike, Moloch, GodotRoguelite, vorlac/godot-roguelite)  
> **Focus areas:** ECS/entity architecture, procedural generation, sprite/atlas pipelines, combat/loot, save/load  
> **Local game:** Depths of Vaelmoor (C:\Users\dbshe\rogueworks) — commit 3db19d3, selftest 22/22 green

---

## Current Game State

- **Commit:** `3db19d3 r59: upgrade TILE 32→64 across game, art, and atlases`
- **Selftest:** `playtest-0.json` — `ok=true`, floor=1, biome=catacombs, 17 entities (13 monsters, 3 pickups, player), 7 rooms, level=96×64 tiles
- **Performance:** tick_ms=0.11, tick_ms_smoothed=0.13, draw_calls=272, atlas_mem=15.9MB
- **Profile metrics:** fps_equiv=8771.9 (headless), entity_count=17/200, particle_count=0/420
- **PROGRESS.md:** Not found in docs/ — likely renamed/removed (roadmap/standards exist)
- **Untracked:** `scripts/check_64.py`, modified `runs/playtest-0.json`

---

## 1. ECS / Entity Architecture

### Pattern Summary

| Repo | Approach | Entity Storage | Components |
|------|----------|---------------|------------|
| **BevyRoguelike** | Pure ECS (Bevy) | `Entity` (u32) + `Query` filters | `Player`, `Enemy`, `Health`, `Position`, `FieldOfView`, `WantsToMove`, `Carried` |
| **Pixel Dungeon** | OOP hierarchy | `Actor` list + `Level` arrays | `Mob extends Char extends Hero`, state pattern for AI |
| **Rusted Ruins** | Component-based | Separate crates/modules | `XXObject` pattern (ItemObject, CharObject, etc.) in pak files |
| **DeathtrapDungeon** | Unity Component | GameObject + MonoBehaviour | `Mover`, `Fighter`, `Collectable` as base classes |
| **Moloch** | Godot Node tree | Scene tree + Autoload singletons | `Classes/`, `Enemies/`, `Elements/` directories |
| **Depths of Vaelmoor** | System-component | `World` owns entity lists (`entities`, `monsters`, `projectiles`) | `Actor` base class + `Stats` object |

### Key Architectural Patterns

**Pure ECS (BevyRoguelike — Rust)**
```rust
#[derive(Component)]
pub struct Player { pub map_level: u32 }

#[derive(Component)]
pub struct Health { pub current: i32, pub max: i32 }

#[derive(Component)]
pub struct FieldOfView {
    pub visible_tiles: HashSet<Point>,
    pub radius: i32,
    pub is_dirty: bool
}

// Systems process entities by query
pub fn fov(mb: Res<MapBuilder>, mut views_query: Query<(&Position, &mut FieldOfView)>) {
    views_query.iter_mut()
        .filter(|(_, fov)| fov.is_dirty)
        .for_each(|(pos, mut fov)| {
            fov.visible_tiles = field_of_view_set((*pos).into(), fov.radius, &mb.map);
            fov.is_dirty = false;
        });
}
```
- **Strengths:** Cache-friendly, parallelizable, clean separation of data/behavior
- **Weaknesses:** Steep learning curve, verbose for simple games

**Message-based combat (BevyRoguelike)**
```rust
#[derive(Component)]
pub struct WantsToAttack { pub attacker: Entity, pub victim: Entity }

#[derive(Component)]
pub struct WantsToMove { pub entity: Entity, pub destination: Position }
```
- Attacker/victim intents are spawned as entities with message components
- A `combat` system processes all `WantsToAttack` messages, applies damage, removes messages
- Clean separation: input produces messages, systems resolve them

**OOP Hierarchy (Pixel Dungeon — Java)**
```java
// Static arrays for tile properties — extremely cache-friendly
public static boolean[] passable = new boolean[LENGTH];
public static boolean[] losBlocking = new boolean[LENGTH];
public static boolean[] water = new boolean[LENGTH];
public static boolean[] pit = new boolean[LENGTH];

// Dungeon.java — singleton world controller
public static Hero hero;
public static Level level;
public static int depth;
public static boolean[] visible = new boolean[LENGTH];
```
- **Length = WIDTH × HEIGHT** (32×32 = 1024 tiles) — fixed-size, stack-allocated feel
- `Room` extends `Rect` and implements `Graph.Node` — rooms are graph nodes with neighbors/doors

**Pak-file asset system (Rusted Ruins — Rust)**
```
rusted-ruins-pak/
  ├── item-objects/     (ItemObject)
  ├── char-objects/     (CharObject)
  ├── tile-objects/     (TileObject)
  └── map-templates/    (MapTemplate)
```
- Assets compiled to `.pak` binary format via `makepak` tool
- Runtime loads pak files into typed registries
- **Modding-friendly:** users drop new pak files without code changes

### Recommendations for Depths of Vaelmoor

1. **Keep the system-component model** — it's working well for Python/Pygame. The `Stats` layered-modifier design is solid.
2. **Consider message-based combat intents** — for networked/multiplayer future, or just cleaner combat code
3. **Static tile property arrays** — Pixel Dungeon's `boolean[] passable/losBlocking/water` pattern is ~10x faster than per-tile dict lookups. Consider numpy arrays for tileprops.
4. **Pak-file packaging** — for shipping, bundle assets into a single `.pak` or `.zip` rather than loose atlas files

---

## 2. Procedural Generation Algorithms

### Pattern Summary

| Repo | Primary Algorithm | Secondary | Themes |
|------|------------------|-----------|--------|
| **BevyRoguelike** | Rooms + Corridors | Drunkard's Walk, Cellular Automata | Dungeon, Forest, Cave (themes swap tile→sprite mappings) |
| **Pixel Dungeon** | Room placement + BSP | Painter pattern per room type | Sewer, Prison, Caves, City, Halls (biome per depth bracket) |
| **Rusted Ruins** | Template + random fill | Map editor for towns | Wilderness, ruins, towns |
| **Depths of Vaelmoor** | Grid-based rooms + corridors | Burning/water tile variants | Catacombs, Ossuary, Ember_heat, Drowned_water |

### Key Algorithms

**Room + Corridor (BevyRoguelike)**
```rust
impl MapArchitect for RoomsArchitect {
    fn new(&mut self) -> MapBuilder {
        let mut mb = MapBuilder { ... };
        mb.fill(TileType::Void);           // Start with void (not walls)
        mb.build_random_rooms();           // Random non-overlapping rectangles
        mb.build_corridors();              // L-shaped corridors between room centers
        mb.player_start = Position::from(mb.rooms[0].center());
        mb.amulet_start = mb.find_most_distant();  // Dijkstra-based furthest point
        // Enemies in all other rooms
        for room in mb.rooms.iter().skip(1) { mb.enemies_start.push(room.center().into()); }
        mb
    }
}
```
- **Key insight:** Start with Void, not Wall — only generated areas are traversable. Reduces edge artifacts.
- **`find_most_distant()`** uses Dijkstra distance map to place the exit far from entrance.

**Drunkard's Walk (BevyRoguelike)**
```rust
fn drunkard(&mut self, start: &Position, map: &mut Map) {
    let mut drunkard_pos = start.clone();
    let mut distance_staggered = 0;
    loop {
        let drunk_idx = map.point2d_to_index(drunkard_pos.into());
        map.tiles[drunk_idx] = TileType::Floor;
        // Random direction
        match rng.gen_range(0..4) {
            0 => drunkard_pos.x -= 1, 1 => drunkard_pos.x += 1,
            2 => drunkard_pos.y -= 1, _ => drunkard_pos.y += 1,
        }
        if !map.in_bounds(drunkard_pos) { break; }
        distance_staggered += 1;
        if distance_staggered > STAGGERED_DISTANCE { break; }
    }
}
```
- Combined with connectivity cleanup: runs Dijkstra from center, converts tiles >2000 distance back to walls.

**Cellular Automata (BevyRoguelike)**
```rust
fn random_noise_map(&mut self, map: &mut Map) {
    map.tiles.iter_mut().for_each(|t| {
        let roll = rng.gen_range(0..100);
        *t = if roll > 55 { TileType::Floor } else { TileType::Wall };
    });
}

fn iteration(&mut self, mb: &mut MapBuilder) {
    for y in 1..H-1 { for x in 1..W-1 {
        let neighbors = mb.count_neighbors(x, y, &mb.map);
        let idx = map_idx(x, y);
        new_tiles[idx] = if neighbors > 4 || neighbors == 0 { TileType::Wall } else { TileType::Floor };
    }}
    mb.map.tiles = new_tiles;
}
```
- 10 iterations of CA smoothing on 55% initial fill → cave-like structures

**Pixel Dungeon — Painter Pattern**
```java
public enum Room.Type {
    STANDARD(StandardPainter.class), ENTRANCE(EntrancePainter.class),
    EXIT(ExitPainter.class), SHOP(ShopPainter.class),
    BLACKSMITH(BlacksmithPainter.class), /* ... 25 total */ }
    
public void paint(Level level, Room room) {
    paint.invoke(null, level, room);  // Each painter fills a room with specific tiles/traps/mobs
}
```
- **Strengths:** 25 room types with unique decoration, all data-driven
- Each painter adds specific features (alchemy lab, garden, traps, etc.)

**Pixel Dungeon — Depth-based biome selection**
```java
public static Level newLevel() {
    switch (depth) {
        case 1-4:   level = new SewerLevel(); break;
        case 5:     level = new SewerBossLevel(); break;
        case 6-9:   level = new PrisonLevel(); break;
        case 10:    level = new PrisonBossLevel(); break;
        case 11-14: level = new CavesLevel(); break;
        case 15:    level = new CavesBossLevel(); break;
        // ... 5 biomes × 5 floors each
    }
    level.create();
}
```

### Recommendations for Depths of Vaelmoor

1. **Add cellular automata or drunkard's walk as alternative room shapes** — current rooms are all rectangles. Caves/ossuary benefit from organic shapes.
2. **Pixel Dungeon's Painter pattern** — add per-room-type decoration (treasury, armory, traps room, garden) for visual variety
3. **Distance-based exit placement** — `find_most_distant()` using Dijkstra is trivial to add and guarantees maximum exploration
4. **Multiple floor algorithms** — currently grid-based for all. Add CA for catacombs/ossuary to feel more cavernous.
5. **Room template expansion** — Pixel Dungeon has 25 room types, your content doc says 231 room templates (70/biome). Verify the room templates actually produce visually distinct rooms.

---

## 3. Sprite / Atlas Pipelines

### Pattern Summary

| Repo | Art Style | Atlas Method | Pipeline |
|------|-----------|-------------|----------|
| **Pixel Dungeon** | Individual PNG sprites | `tiles0.png..tiles4.png` (5 tile sheets) + individual mob PNGs | Pre-rendered at 16×16, loaded directly |
| **BevyRoguelike** | 8×8 ASCII/tileset | `terminal8x8.png` 256-glyph atlas | Code page 437 character mapping via `CharsetAsset` |
| **Rusted Ruins** | Pixel art | Pak file system (image→pak→runtime) | `makepak` tool compiles source images |
| **Depths of Vaelmoor** | Procedural 64×64 | `Atlas.load()` + `frame()` with placeholder fallback | Generated sprites + palette-locked, `FONT_GLYPHS` for text |

### Key Pipeline Patterns

**Pixel Dungeon — Per-monster sprite sheets**
```
assets/
  ├── rat.png          (single sprite, ~16x16)
  ├── skeleton.png
  ├── tiles0.png       (dungeon tilesheet, 16x16 grid)
  ├── tiles1.png       (sewer tilesheet)
  ├── tiles2.png       (prison tilesheet)
  ├── items.png        (items spritesheet)
  ├── chrome.png       (UI elements)
  └── effects.png      (VFX sprites)
```
- Each mob has its own PNG file
- Tile set varies by biome (5 tile sheets for 5 biomes)
- **Simple, fast, but artist-heavy:** adding a new biome requires a full tilesheet

**BevyRoguelike — Single atlas + theme swaps**
```rust
pub struct Glyph {
    pub index: usize,       // index in the 16x16 atlas grid
    pub color: Color,       // tint color
    pub bkg_color: Option<Color>
}

pub trait MapTheme {
    fn tile_to_render(&self, tile_type: TileType) -> Option<Glyph>;
}

// Different themes just swap glyph index + color
impl MapTheme for DungeonTheme {
    fn tile_to_render(&self, tile_type: TileType) -> Option<Glyph> {
        match tile_type {
            TileType::Floor => Some(Glyph::new_nobkg(219, floor_color)),
            TileType::Wall => Some(Glyph::new('#' as usize, glyph_color, wall_color)),
            _ => None,
        }
    }
}
```
- One 8×8 font atlas renders everything
- Themes are just color/index swaps — no new art needed
- **Limitation:** all biomes look similar (same glyph set, different colors)

**Depths of Vaelmoor — Procedural + placeholder system**
```python
# assets.py — keyword→color mapping for placeholder generation
_COLOUR_RULES = [
    ("wall", "stone"), ("rock", "stone_dark"), ("floor", "stone_dark"),
    ("player", "steel"), ("gold", "gold"), ("fire", "flame"),
    ("water", "water"), ("poison", "venom"), ("boss", "blood"),
    # ... 40+ rules
]

# FONT_GLYPHS — 5x7 pixel font for tags/UI text
FONT_GLYPHS = {
    "A": ".#./#.#/###/#.#/#.#",
    # ... full alphabet + digits + punctuation
}
```
- **Strengths:** Game is fully playable on placeholder sprites alone
- **Weaknesses:** Procedural sprites can feel homogeneous ("pixel soup")
- **235 procedural sprites** in current state — same base templates with palette swaps

### The "Pixel Soup" Problem — Diagnosis & Solutions

**Root cause:** Procedural generation creates sprites from the same base templates with minor color variations → everything looks similar.

**Solutions from research:**

1. **Pixel Dungeon's approach:** Hand-crafted per-monster sprites. Each mob (rat, skeleton, brute, elemental, dm300, ghost, etc.) is a distinct pixel art asset. **Labor-intensive but visually distinct.**

2. **BevyRoguelike's approach:** Use ASCII + themes. Not applicable to pixel art.

3. **DeathtrapDungeon's approach:** Use pre-made tilesets from itch.io (0x72's 16×16 Dungeon Tileset). **Mix hand-authored + procedural placement.**

4. **Rusted Ruins' approach:** Pak file system allows community-made art packs. **Modding as art pipeline.**

5. **Hybrid (recommended):** Procedural base + hand-crafted detail layers:
   - Base body: procedural shape
   - Overlay: hand-crafted "signature" features (horns, weapons, glowing eyes)
   - Palette: biome-specific (fire biome = red/orange, ice = blue/white, etc.)
   - Silhouette variation: ensure each monster type has a distinct outline

### Recommendations for Depths of Vaelmoor

1. **Add 2-3 signature details per sprite** — a glowing eye, a weapon, a crown — anything that breaks the template look
2. **Per-biome palette enforcement** — fire monsters MUST use fire palette, ice MUST use ice → instant visual differentiation
3. **Silhouette checker** — verify each monster type has a distinct outline (fill ratio, width/height ratio, protrusion count)
4. **Atlas optimization** — Pixel Dungeon uses 5 separate biome tilesheets to keep per-biome tiles cohesive. Consider per-biome atlases.
5. **Consider hand-crafted hero + boss sprites** — procedural for generic mobs, but the player and bosses deserve unique art

---

## 4. Combat / Loot Systems

### Pattern Summary

| Repo | Combat Model | Damage Resolution | Loot |
|------|-------------|-------------------|------|
| **BevyRoguelike** | Bump-to-attack, turn-based | `base_damage + equipped_weapon_damage` | Items on ground → pick up → equip |
| **Pixel Dungeon** | Turn-based with energy | `attackSkill` vs `defenseSkill`, buffs modify | `Generator` class per item category, depth-scaled |
| **Rusted Ruins** | Real-time with stats | Stat-based with equip slots | Crafting, cooking, mining |
| **Depths of Vaelmoor** | Auto-melee + ranged + dash | Element→status mapping, armor mitigation | 5 rarities × affix rolling, tier-weighted |
| **DeathtrapDungeon** | Melee swing animation | `Damag` struct (amount + origin + pushForce) | Rage/怒气 system, chest drops |
| **Moloch** | Wand-based + physics | Body-part conditions (not HP) | Wandcrafting, inventory management |

### Key Combat Patterns

**Element → Status mapping (Depths of Vaelmoor)**
```python
ELEMENT_TO_STATUS = {
    "fire": "burn", "ice": "chilled", "water": "wet",
    "poison": "poison", "shadow": "doom_mark", "lightning": "stun",
    "holy": "regeneration", "wind": "haste", "earth": "fortify",
    "physical": None,
}

def damage_target(world, target, amount, ..., element="physical"):
    raw = max(0.0, float(amount))
    if crit: raw *= 2.0
    armor = target.stats.armor()
    dealt = raw * (1.0 - armor)
    target.hp -= dealt
    # P2.5: propagate element as status
    if element and element != "physical":
        _apply_element_on_hit(world, target, element)
```
- **Clean, extensible:** adding a new element = one dict entry + one status
- **Crit, armor, DOT bypass, knockback** all handled in single funnel

**BevyRoguelike — Message-based combat**
```rust
// Combat system processes all attack messages
let w_damage: i32 = damage_query.iter()
    .filter(|(_, c, e)| c.is_some() && e.is_some())  // Has Carried + Equipped
    .map(|(dmg, carried, _)| (dmg, carried.unwrap()))
    .filter(|(_, carried)| carried.0 == *attacker)    // Carried by attacker
    .map(|(dmg, _)| dmg.0)
    .sum();
let final_damage = base_damage + w_damage;
```
- Weapon damage is calculated by querying equipped weapons, not hardcoded in combat
- **Easy to extend:** shields, dual-wielding, etc. just add more queries

**Pixel Dungeon — State-pattern AI**
```java
public class Mob extends Char {
    public AiState SLEEPEING = new Sleeping();
    public AiState HUNTING = new Hunting();
    public AiState WANDERING = new Wandering();
    public AiState FLEEING = new Fleeing();
    public AiState state = SLEEPEING;
    
    // States serialize as string tags for save compatibility
    public void storeInBundle(Bundle bundle) {
        if (state == SLEEPEING) bundle.put(STATE, Sleeping.TAG);
        else if (state == HUNTING) bundle.put(STATE, Hunting.TAG);
        // ...
    }
}
```

### Key Loot Patterns

**Depths of Vaelmoor — Rarity + Affixes**
```python
RARITIES = [
    {"id": "common",     "affixes": (0, 1), "power": 1.00},
    {"id": "uncommon",   "affixes": (1, 1), "power": 1.10},
    {"id": "rare",       "affixes": (1, 2), "power": 1.25},
    {"id": "epic",       "affixes": (2, 2), "power": 1.40},
    {"id": "legendary",  "affixes": (2, 3), "power": 1.60},
]

def roll_affixes(content, rng, item_tier, rarity):
    low, high = rarity["affixes"]
    count = rng.randint(low, high)
    # Filter affixes by tier_min <= item_tier <= tier_max
    # Weighted random selection from pool
```
- **5 rarities, 70 affixes** — good depth
- Tier-weighted base item selection + luck-modified rarity roll

**Pixel Dungeon — Generator pattern**
```java
public abstract class Item implements Bundlable {
    public static Generator generator;
    public static Item random() {
        return generator.random();  // Weighted across all item categories
    }
}
```
- Single `Generator` holds all item type weights
- **Simpler but less flexible** than your affix system

### Recommendations for Depths of Vaelmoor

1. **Add more loot variety sources** — Pixel Dungeon has special rooms (Armory, Treasury, Vault) that drop specific item types. Your 231 room templates should have loot tables.
2. **Telegraph verification** — you already have `DEFAULT_TELEGRAPH` dict. Verify ALL monster attacks actually play the telegraph sprite before the hit.
3. **Combat log** — BevyRoguelike's `GameLog` is great for combat feedback. Your `damage_numbers` are good but a text log helps debugging.
4. **Combo system depth** — you have COMBO_IDS. Make sure combos are discoverable (tooltips, tutorial) or they feel random.
5. **Elemental weapon modifiers** — currently elements come from monsters. Add elemental weapons that inflict statuses (flame sword = burn on hit).

---

## 5. Save / Load Patterns

### Pattern Summary

| Repo | Format | Strategy | Versioning |
|------|--------|----------|------------|
| **Pixel Dungeon** | JSON Bundle (Bundlable interface) | `storeInBundle`/`restoreFromBundle` per class | `Dungeon.version` constant |
| **BevyRoguelike** | Not implemented (single-session) | N/A | N/A |
| **Rusted Ruins** | Custom binary (pak-like) | Per-crate serialization | Pre-1.0: format may change |
| **Depths of Vaelmoor** | JSON (`save.json`) | Atomic writes with `.bak` backup | `SAVE_VERSION = 3`, migrate/reset on mismatch |
| **DeathtrapDungeon** | LitJson (`SaveData.json`) | `GameManager.instance.Save()`/`Load()` | Implicit |

### Key Save Patterns

**Pixel Dungeon — Bundlable interface + class aliasing**
```java
public class Bundle {
    private static final String CLASS_NAME = "__className";
    private static HashMap<String, String> aliases = new HashMap<>();
    
    private Bundlable get() {
        String clName = getString(CLASS_NAME);
        if (aliases.containsKey(clName)) clName = aliases.get(clName);  // Rename ref
        Class<?> cl = Class.forName(clName);
        Bundlable object = (Bundlable)cl.newInstance();
        object.restoreFromBundle(this);
        return object;
    }
}
```
- **Class aliasing** allows renaming classes without breaking old saves
- Every game object implements `Bundlable.storeInBundle()/restoreFromBundle()`
- **Serialized as nested JSON** — human-readable, debuggable

**Depths of Vaelmoor — Version-tolerant save**
```python
SAVE_VERSION = 3
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SAVE_PATH = PROJECT_ROOT / "save.json"

# P5.1: atomic writes with .bak backup
# P5.1: corrupted-save recovery (try .bak if save.json fails)
# P5.1: named save slots
```
- **3 save slots + autosave**
- **Atomic write:** write to temp → rename → prevents corruption on crash
- **.bak fallback:** if save.json is corrupt, load .bak
- **Version migration:** if `save["version"] != SAVE_VERSION`, migrate or reset

**Rusted Ruins — Pre-1.0 flexibility**
```
"Binary format of pak files and save files may be changed before version 1.0."
```
- **Brutally honest** about breaking changes — no migration, just tells users.

### Save File Structure Comparison

**Pixel Dungeon:**
```
save/
  ├── game.json       (current run state)
  ├── badges.json     (unlocked badges)
  ├── rankings.json   (past run records)
  └── backup/         (auto-backups)
```

**Depths of Vaelmoor:**
```
save.json         (active run + meta-progression)
save.json.bak     (backup of previous save)
save_autosave.json (autosave slot)
save_autosave.json.bak
```

### Recommendations for Depths of Vaelmoor

1. **Class aliasing for save compatibility** — if you rename a system/class, old saves break. Pixel Dungeon's alias map is the fix.
2. **Separate run saves from meta-progression** — Pixel Dungeon has `GamesInProgress` (per-class run state) separate from `Statistics`/`Badges` (lifetime). Your `save.json` mixes them.
3. **Periodic backups** — every N minutes, save to `save_slot_{n}.json` so players can recover from bad decisions.
4. **Human-readable saves** — you already use JSON. Keep it that way. Binary saves are harder to debug.
5. **Save file integrity** — add a CRC/checksum to detect corruption before parsing. If CRC fails, fall back to .bak.
6. **Version migration chain** — don't just check `version == 3`. Write `migrate_v1_to_v2()`, `migrate_v2_to_v3()` so old saves upgrade incrementally.

---

## 6. Cross-Cutting Design Patterns

### Singleton Pattern (Use Sparingly)

Pixel Dungeon and DeathtrapDungeon both use singletons heavily:
```java
// Pixel Dungeon
public static Hero hero;
public static Level level;

// DeathtrapDungeon  
GameManager.instance.OnUIChange()
```

**Depths of Vaelmoor** avoids this — `World` is passed explicitly. **Good choice** — singletons make testing and multiplayer harder.

### Trait/Interface Pattern

```java
// Pixel Dungeon
public interface Bundlable {
    void storeInBundle(Bundle bundle);
    void restoreFromBundle(Bundle bundle);
}
```

```rust
// BevyRoguelike
pub trait MapArchitect {
    fn new(&mut self) -> MapBuilder;
}
```

**Depths of Vaelmoor** uses duck-typing (Pythonic) — works but lacks compile-time checks. Consider Protocol classes for critical interfaces.

### Data-Driven Design

All successful repos externalize game data:
- Pixel Dungeon: `Scroll.initLabels()`, `Potion.initColors()`, `Bestiary` for mob spawning
- Rusted Ruins: Pak files with all assets/data
- **Depths of Vaelmoor:** `content/items.json`, `content/monsters.json` — good, but verify schema validation catches errors early

---

## 7. Actionable Recommendations Summary

### Priority 1 — Visual Quality (addresses "pixel soup")

| # | Action | Effort | Impact |
|---|--------|--------|--------|
| 1.1 | Add signature details (horns, weapons, glowing eyes) per monster type | Medium | High |
| 1.2 | Enforce per-biome palettes (fire=always warm colors) | Low | High |
| 1.3 | Distinct silhouette check per monster (outline uniqueness) | Low | Medium |
| 1.4 | Hand-craft hero + boss sprites (procedural only for fodder) | High | Very High |
| 1.5 | Per-biome atlas separation (not one giant atlas) | Medium | Medium |

### Priority 2 — Architecture

| # | Action | Effort | Impact |
|---|--------|--------|--------|
| 2.1 | Message-based combat intents (for cleaner combat code) | Medium | Medium |
| 2.2 | Static tile property arrays (numpy boolean arrays) | Low | High (perf) |
| 2.3 | Pak-file asset packaging (for shipping/modding) | Medium | Low |

### Priority 3 — Content Depth

| # | Action | Effort | Impact |
|---|--------|--------|--------|
| 3.1 | Add CA/drunkard's walk for organic room shapes | Medium | Medium |
| 3.2 | Distance-based exit placement (Dijkstra) | Low | Medium |
| 3.3 | Per-room-type loot tables (treasury→gold, armory→weapons) | Medium | High |
| 3.4 | Combo system discoverability (tutorial + tooltips) | Low | Medium |

### Priority 4 — Save/Load Robustness

| # | Action | Effort | Impact |
|---|--------|--------|--------|
| 4.1 | Class aliasing for save compatibility | Low | Medium |
| 4.2 | CRC/checksum for save integrity | Low | Medium |
| 4.3 | Version migration chain (v1→v2→v3) | Medium | Low |
| 4.4 | Separate run saves from meta-progression | Medium | Low |

---

## 8. Repos Referenced

| Repo | Stars | Language | Key Takeaway |
|------|-------|----------|-------------|
| [watabou/pixel-dungeon](https://github.com/watabou/pixel-dungeon) | 3957 | Java | Hand-crafted art, Bundlable save interface, Painter room decoration |
| [thephet/BevyRoguelike](https://github.com/thephet/BevyRoguelike) | 256 | Rust/Bevy | Pure ECS, message-based combat, MapArchitect trait, theme swaps |
| [garkimasera/rusted-ruins](https://github.com/garkimasera/rusted-ruins) | 555 | Rust | Pak file system, extensible by modders, open-world |
| [SouthBegonia/DeathtrapDungeon](https://github.com/SouthBegonia/DeathtrapDungeon) | 157 | C#/Unity | Component-based, Rage system, async scene loading |
| [tomuxmon/bevy_roguelike](https://github.com/tomuxmon/bevy_roguelike) | 55 | Rust/Bevy | Separated crates (combat/inventory/UI), turn-based |
| [Lilith-In-Starlight/Moloch](https://github.com/Lilith-In-Starlight/Moloch) | 17 | GDScript/Godot | Condition-based health (not HP), wandcrafting, Godot nodes |
| [vorlac/godot-roguelite](https://github.com/vorlac/godot-roguelite) | 220 | C++/Godot | GDExtension patterns, CMake/VCPKG, native performance |
| [Bozar/GodotRoguelikeTutorial](https://github.com/Bozar/GodotRoguelikeTutorial) | 280 | GDScript | Incremental Godot learning, turn-based grid |

---

## Appendix: Quick Reference Code Snippets

### Stats with Layered Modifiers (from Depths of Vaelmoor)
```python
class Stats:
    def __init__(self, base=None):
        self.base = dict(BASE_STATS)
        self.mods = {}       # source -> {stat: additive}
        self.pct_mods = {}   # source -> {stat: multiplier}
        self._cache = None
    
    def resolve(self, stat):
        """Compute final stat value from base + mods + pct_mods."""
        base_val = self.base.get(stat, 0.0)
        additive = sum(s.get(stat, 0.0) for s in self.mods.values())
        pct = sum(s.get(stat, 0.0) for s in self.pct_mods.values())
        return (base_val + additive) * (1.0 + pct)
```

### Dijkstra Distance Map (exit placement)
```python
def find_most_distant(level, start):
    """Find the floor tile furthest from start using BFS/Dijkstra."""
    dist = {start: 0}
    queue = deque([start])
    while queue:
        pos = queue.popleft()
        for dx, dy in [(1,0),(-1,0),(0,1),(0,-1)]:
            npos = (pos[0]+dx, pos[1]+dy)
            if level.in_bounds(npos) and npos not in dist and level.is_floor(npos):
                dist[npos] = dist[pos] + 1
                queue.append(npos)
    return max(dist, key=dist.get)
```

### Per-Biome Palette Enforcement
```python
BIOME_PALETTES = {
    "catacombs": ["bone", "stone_dark", "ink", "ash", "blood_dark"],
    "ossuary":   ["bone", "stone_dark", "arcane", "white"],
    "ember_heat":["ember", "ember_dark", "flame", "gold", "blood"],
    "drowned_water": ["water", "water_dark", "venom", "moss", "soul"],
}

def validate_palette(sprite, biome):
    """Ensure sprite only uses colors from its biome palette."""
    palette = BIOME_PALETTES.get(biome, [])
    for pixel in sprite.pixels():
        if pixel.color.name not in palette:
            return False
    return True
```

---

*Document auto-generated from GitHub API analysis + local codebase inspection.  
Verify recommendations against actual codebase state before implementation.*
