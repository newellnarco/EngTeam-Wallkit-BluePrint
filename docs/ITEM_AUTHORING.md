# ITEM_AUTHORING.md

How arcs, stories and bugs are designed, written, amended, and enriched by
research — the authoring contract between the Architect who writes them and the
Builders who consume them.

WALL_STANDARDS.md section 4 defines what the wall *tracks*. This document
defines how the content of those items gets *written* so a Builder can execute
one without guessing. WORKFLOW.md section 3 is the enforcement mechanism: any
acceptance criterion a Builder cannot map to a source is, by definition, an
ambiguity — so the authoring rules here exist to make that mapping possible
before dispatch instead of discovering the gap after it.

---

## 1. The three shapes

| Shape | Id | What it is | Typical life |
|---|---|---|---|
| **Arc** | `ARC-NN` | A theme of work with one design intent. Spans many stories and usually many pull requests. | Weeks |
| **Story** | `ST-NNN` | One dispatchable unit: a Builder takes it, builds it, it merges. | One dispatch |
| **Bug** | `BG-NNN` | A defect against behaviour that was already accepted. Carries a reproduction, not a design. | One dispatch |

The invariant that keeps dispatch sane: **one story = one dispatch = one
declared path scope = one lease.** A story too big to state a single disjoint
path scope for is two stories. A story whose acceptance criteria need a design
discussion to interpret is an arc that skipped its design step.

Bugs differ from stories in what grounds them: a story's criteria cite the
design; a bug's criteria cite the **reproduction** (the failing case, verbatim)
and the accepted behaviour it violates. A bug with no reproduction is a finding,
not a bug — route it through `docs/handoffs/finding-route.md` until someone can
reproduce it.

## 2. Who writes what

| | Designs the arc | Writes the stories | Files bugs | Admits to the wall | Amends requirements |
|---|---|---|---|---|---|
| Architect | **yes** | **yes** | yes | | **yes** |
| Maestro | | | yes | **yes** | records only |
| Builder | | | yes (via finding) | | never |
| Researcher | | | yes (via finding) | | never |
| Reviewer | | | yes (via finding) | | never |

- **The Architect designs the arc and writes its stories from that design.**
  The design lands in `docs/architecture/` (the host's existing home); the
  stories reference it by section. Stories written without a design section to
  cite fail the Builder's source-mapping check on first contact — author-time
  is the cheap place to catch that.
- **The Maestro admits items to the wall** — writes `.wall/items/<id>.json`
  and the ledger event — and attaches any `DEC-NNNN` already in scope. One
  writer for wall state, same as one writer for decisions.
- **A Builder never authors its own requirements.** A Builder that writes its
  own acceptance criteria and then meets them has graded its own homework; the
  Reviewer reads diffs, not intent, so nobody would ever check the intent.
  When a Builder discovers missing scope mid-story, that is a `question_raised`
  or a finding — never a self-amended criterion.

## 3. Anatomy of an arc

An arc's item record and its design doc together answer, before any story is
dispatched:

1. **Intent** — one paragraph: what is true after this arc that is not true now.
2. **Boundary** — explicit non-goals. The most common cross-Builder collision
   in practice is two stories both "improving" the same neighbouring surface
   that neither owned; the boundary line is what makes that a citable refusal.
3. **Design reference** — the `docs/architecture/` sections that ground it.
4. **Stories, ordered** — with dependencies between them stated (`ST-105
   needs ST-104's interface`), because dispatch order and lease scheduling read
   this, not the prose.
5. **Decisions in scope** — every `DEC-NNNN` that constrains the arc, so the
   Maestro attaches them at dispatch instead of a Researcher rediscovering them.

An arc closes when its stories are done or explicitly moved out — never by
drifting. An arc may close without any release ceremony (WALL_STANDARDS
section 4).

## 4. Anatomy of a story — the Builder contract

Every story carries, at authoring time:

- **Acceptance criteria** (`AC-1`, `AC-2`, ...) — each one **testable and
  citable**: it names the design section, decision id, or existing test that
  grounds it. This is the other half of WORKFLOW section 3's forcing function —
  the Builder maps every criterion to a source before coding, and the author
  writes criteria so the mapping exists. A criterion neither side can cite is
  the author's bug.
- **Declared path scope** — the files the story is expected to touch. This
  feeds the lease check verbatim, so it is stated in globs, honestly wide
  enough to be true and no wider. A scope discovered wrong mid-build goes back
  through the Maestro (the lease table is not self-service).
- **Test expectation** — which tiers this story must add to (per
  `docs/TESTING_STANDARDS.md`) and any specific regression that must be pinned.
- **Dependencies** — stories, decisions, or external facts this one waits on.
- **Out of scope** — the one line that saves a rejection cycle.

### Writing rules

1. **Criteria state observable outcomes, not implementations.** "`wall verify`
   exits non-zero when the heartbeat is stale" — not "add a staleness check to
   verify". The Builder owns the how; the Reviewer can only reject against a
   what.
2. **No solution-in-disguise.** If the design genuinely constrains the
   implementation (it sometimes does), cite the design section that says so
   rather than embedding the constraint as an unexplained instruction.
3. **Every "must" is a criterion; everything else is context.** Builders
   execute the numbered list. Prose that secretly contains a fourth requirement
   is how "built as specified" and "not what was wanted" happen simultaneously.
4. **State failure behaviour.** Half of all real ambiguities
   (`unspecified_edge_case`) are "and what happens when it's empty / missing /
   malformed". Say it, or expect the question.

## 5. Amending items — the design is living, the change is not silent

The Architect adjusts and modifies the design as reality pushes back. The rules
keep the adjustment from invalidating in-flight work invisibly:

1. **Only the Architect amends requirements** — anyone can propose (via
   finding or question), only the Architect's ruling changes a criterion, and
   the Maestro writes the resulting record. Same single-writer discipline as
   decisions.
2. **A design or decision edit is a broadcast, not a file change.** Any change
   under `docs/architecture/**` or `docs/decisions/**` emits `doc_impact`
   naming the affected arcs (architect.md section 3). Courier surfaces it on
   the wall, so a Builder mid-story on an affected arc finds out from the wall
   rather than from a rejected review.
3. **An in-flight story is amended through re-dispatch, never in place.** If
   the amendment touches a criterion a working Builder holds, the Maestro
   delivers the delta as an updated brief (the same channel every answer
   travels), and the run record shows which version of the criteria the work
   was built against. Editing `.wall/items/<id>.json` under a working Builder
   produces work that satisfies criteria nobody can reconstruct.
4. **An amendment that contradicts a live `DEC-NNNN` goes through the
   Adjudicator first.** Supersede explicitly or don't change it — a criterion
   quietly diverging from a live decision is the `conflicting_decisions`
   ambiguity class, manufactured at the source.
5. **Superseded criteria stay visible.** Strike-through or a `superseded_by`
   note on the item, not deletion — the trace from "why was this built this
   way" back to "the criterion said so at the time" must survive the amendment.

## 6. The research loop — how questions leave an item and how answers return

Everything is mediated (WORKFLOW section 1): a Researcher cannot talk to the
Builder who asked, and neither can hand the Architect anything directly. The
loop, end to end:

```
Builder hits ambiguity on ST-106
  → question_raised (class, blocked criteria, dependent/independent scopes)
  → Maestro: decision log FIRST (a hit answers at near-zero cost, stop here)
  → miss: Maestro fills docs/handoffs/finding-route.md, dispatches Researcher
  → Researcher: findings with sources + confidence + conflicts (researcher.md §3)
  → Maestro routes findings to the Architect (this IS the "discussion" —
     mediated, written, one hop at a time; SLA ladder in WORKFLOW §4)
  → Architect: ruling in DEC-consumable shape (architect.md §2)
  → Maestro writes DEC-NNNN, updates the item, re-dispatches the Builder
```

**Where the researcher's work lands** — the answer is written into three
places, and the Builder only ever receives it through the third:

| Place | What lands there | Why |
|---|---|---|
| `docs/decisions/DEC-NNNN.md` | The ruling, with scope + rationale + supersessions | Durable; the next question searches here first |
| `.wall/items/<id>.json` | The question's trail: `question_raised` → assignment → escalations → the closing decision id | The wall shows the item's full Q&A history; anyone reading the story sees what was asked and what bound it |
| The re-dispatch brief | The decision text, attached, recorded in `decisions_in_context` | The Builder builds from the brief — never from a chat, a memory, or a sibling's paraphrase |

The Researcher's raw findings (the option analysis, the costs, the sources)
attach to the question's trail on the item — not into the decision record,
which stays one paragraph of ruling. A later reader who wants "why" follows the
item's trail; a later reader who wants "what binds me" reads the DEC. Keeping
those separate is what keeps decision records searchable at a hundred entries.

**Discussion is written and hop-by-hop, by design.** "The Researcher discusses
with the Architect" is, mechanically: findings → Maestro → Architect →
ruling → Maestro. If the Architect needs more from the Researcher, that is a
second research pass with a narrower question — logged as its own hop on the
ladder, visible in `wall trace`. Synchronous back-and-forth between subagents
is not a thing the execution model has; pretending otherwise produces answers
nobody recorded.

**Two researcher deliverables, two routes:**

- **An answer to the question asked** → the loop above.
- **Something bigger than the question** (the research reveals the story is
  mis-designed, or a new arc is warranted) → a **finding**, routed per
  `docs/handoffs/finding-route.md` section 7, typically dispositioned as
  "filed as item" — the Architect designs from it, and it enters the wall as
  authored work. Researchers never write stories directly; they write the
  evidence stories get designed from.

## 7. Cross-references

- WORKFLOW.md sections 1, 3, 4 — mediation, ambiguity mechanics, the ladder
- WALL_STANDARDS.md sections 4, 6 — item tracking, decision records
- docs/handoffs/finding-route.md — the routing document itself
- docs/handoffs/dispatch-brief.md — where criteria + decisions reach a Builder
- .claude/agents/architect.md, researcher.md — the role sheets
- docs/SESSION_LIFECYCLE.md — when a question leaves the crew entirely and
  goes to the driving engineer
