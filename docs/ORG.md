# ORG — who decides what at Rogueworks

The studio is seven Hermes bots building one game. `docs/STUDIO.md` describes *what* they do;
this file is the **authority structure** — who decides, who reports to whom, and what happens when
someone is stuck. Every bot's `SOUL.md` carries its own row of this chart, so it governs behaviour
rather than sitting in a document nobody reads.

## 1. The authority chain

```
                        OWNER  (the user — final authority, approves scope)
                          |
        +-----------------+------------------+
        |                                    |
   FORGE  (director)                    WARDEN  (editor)
   CEO / Studio Director /               Standards & QA Director
   Game Director  (one game,             Independent. Does NOT report
   so the roles are merged)              to forge — see §3.
        |
        +-- CHIP   Technical Director    game/ , tools/        (all game code)
        +-- PIXEL  Art Director          assets/ , tools/art/   (sprites, atlases, VFX)
        +-- LORE   Design & Content Lead game/data/            (monsters, items, rooms, biomes)
        +-- TEMPO  Audio Director        assets/audio/         (score, ambience, manifest)
        +-- LENS   QA / Playtest Lead    runs/ , tools/qa/      (playtests, frame audits, reports)
```

**One game, seven agents, three real levels of authority.** Every bot is an individual contributor:
there is no bot managing another bot, because a team of one needs no lead. Where the corporate
template has both a Director and a Lead for a discipline, this studio has a single bot who is both.

## 2. Reporting lines

| Bot | Reports to | Receives reports from | Escalates to |
|---|---|---|---|
| **forge** | Owner | chip, pixel, lore, tempo, lens, narrative | Owner |
| **narrative** | forge | — | forge |
| **chip** | forge | — (sole engineer) | forge |
| **pixel** | forge | — | forge |
| **lore** | forge | — | forge |
| **tempo** | forge | — | forge |
| **lens** | forge | — | forge |
| **warden** | **Owner** | — (audits every bot) | Owner |

## 3. Why WARDEN does not report to forge

The corporate template puts QA under the COO or Studio Director. **This studio deliberately does
not.** The five laws say the reviewer must not be the builder, and forge both assigns the work and
integrates it — so a warden reporting to forge would be reviewing its own director's output. That is
self-review, and it is exactly how a studio talks itself into shipping something broken.

WARDEN therefore reports to the **Owner**, with a working relationship to forge (not a reporting
line): forge cannot overrule a slap, and cannot dismiss one. A slap that cannot be verified as fixed
stays open and escalates on its own schedule (`docs/STANDARDS.md`).

The same rule decides model pins: **warden never runs the builder's model** (`docs/MODELS.md`), for
the same reason.

## 4. What each role owns and decides

| Role | Decides alone | Must ask forge | Must ask the Owner |
|---|---|---|---|
| **forge** (director) | ticket order, decomposition, briefs, integration, what "done" means | — | scope changes, new model pins, anything spending money |
| **chip** (eng) | implementation, module layout inside `game/`/`tools/` | interface changes (contract first) | — |
| **pixel** (art) | art technique, palette-locked rendering, silhouette design | adding/removing a shipped frame's name | — |
| **lore** (design/content) | content values within schema, flavour text | new field or id convention (= contract change) | — |
| **tempo** (audio) | composition, cue structure, licence-clean backend choice | shipping a new cue into the manifest | — |
| **lens** (QA) | test strategy, what counts as a defect, verdict on a build | — | — (files findings; never fixes them) |
| **warden** (editor) | APPROVE / SLAP, severity, the rule text, lane freeze | — | — (escalation is automatic by repeat count) |

**Nobody may approve their own work.** The builder runs its own gates (that is law 2, not review);
WARDEN's independent pass is what makes an artifact *accepted*.

## 5. The IC ladder is a MODEL ladder

The template's bottom four rows (Senior / Mid / Junior / Intern) are not four more bots. In this
studio they are **model tiers inside a lane**, and which tier may do which work is measured, not
assumed. This is the single most important structural finding of the 2026-09-14 audit
(`docs/MODELS.md`):

| Template row | Studio equivalent | Measured capability | May be trusted with |
|---|---|---|---|
| Intern / contractor | fast local models: `gemma-4-e4b` (51.8 tok/s, 5.1 GB), `gemma-4-12b-qat` | strong at **short isolated generation** (53 tokens in 3 s); **destroys any file it edits in place** (58-76 lines lost on a one-method request) | drafting into a **fresh file** only — a method body, a JSON blob, a candidate. Never an in-place edit on a shared file. |
| Mid specialist | local bulk model: `gemma-4-12b-qat` (`lore`'s seat) | generates bulk content fine **under a strict schema + validator** | hundreds of JSON entries, behind `tools.validate_data` |
| Senior specialist | free-tier cloud executing a **precise directive**: `longcat-2.0:free`, `ling-3.0-flash-fin:free` | **PASS** on a scoped edit in 16-48 s, 0 lines deleted, <6k tokens | the actual edit, once forge has written the directive |
| Principal / reviewer | **WARDEN**'s own model, never a builder's | independent judgment | APPROVE / SLAP |

**The load-bearing role is not a model tier — it is the brief-writer.** Measured on identical work:
the same cloud models **failed** an open-ended task (20 turns, zero write calls) and **passed** the
same edit when handed a concrete directive. So `forge` writing a precise brief *is* the studio's
compression step: it is what lets an inexpensive model do senior work.

### Training a tier (the HR analogue)

There is no HR bot and no hiring, but the real analogue exists and has an owner: **onboarding a
model.** It is a measured process, owned by `forge`, and recorded in `docs/MODELS.md`:

1. It must pass the **3-step tool chain** (`read_file` → `write_file` → `run_tests`) — prose quality
   does not count.
2. It must pass the **interface it will actually be used through** (a precise directive, not an
   agentic exploration — those measure different things).
3. Its **GGUF must report ≥64K context** or it cannot hold an agent seat at all.
4. Only then may a pin move; free-tier or local only, and the chain must end in a local model.

Correction rules are the other half: a repeated mistake escalates into the offender's `SOUL.md`, so
it loads in every future session. That is the studio's institutional memory.

## 6. Escalation

```
bot is blocked ──> says BLOCKED, loudly, in its round report
      │
      ├─ can forge unblock it?  ──> forge re-briefs, reassigns, or fixes the contract
      │
      └─ no ──> OWNER (scope, model pin, money, or a decision only a human can make)

warden slaps ──> automatic: correction order into the offender's chat
      ├─ level 1  warns, fix verified by re-running the acceptance command
      ├─ level 2  the rule is appended to the offender's SOUL.md (permanent)
      └─ level 3  the lane is FROZEN — forge must reassign the work
                   a frozen lane or an unverified slap escalates to the OWNER
```

**A blocked bot that tells the truth is fine. A blocked bot that invents a pass is out** (P0).

## 7. Roles from the template this studio does NOT staff, and why

Recorded so nobody "fixes" the chart by adding them:

| Template role | Verdict | Reason |
|---|---|---|
| Board of Directors / Shareholders | **= the Owner** | one stakeholder; no board to convene |
| CFO, finance teams | **not staffed** | no money is spent. The real constraint is *token* and *rate-limit* discipline, and it is law 5 ("cheap by default"), enforced by warden — not a budget office. |
| CMO, marketing, community, PR | **not staffed** | the game is not sold or announced. If it ever ships publicly, this becomes a real seat; today it would be a bot with no work. |
| HR Director, recruiters, specialists | **not staffed** | no humans are hired. The analogue — model onboarding and correction rules — is owned by forge (§5). |
| Associate Producers, Coordinators | **not staffed** | zero-coordination cost: there are no humans to schedule and seven agents who report in writing. |
| Separate Lead + Senior + Mid + Junior per discipline | **collapsed** | each discipline has exactly one bot; it is its own lead and its own IC. The tier variation lives in the **model** it delegates to, not in more bots (§5). |

**The test for adding a seat: does it have a distinct acceptance command and an artifact only it can
produce?** If not, it is a role that will generate meetings instead of artifacts.

## 8. How to change this document

`forge` owns it. A change to the authority chain or a reporting line is a **structural change**: state
it in the round report, update every affected `SOUL.md` in the same change, and note it in
`docs/PROGRESS.md`. Reporting lines that disagree with the SOULs are worse than no chart at all.
