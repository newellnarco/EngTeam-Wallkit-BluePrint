# UX_STANDARDS.md

Human usability as a requirement axis, not a garnish. Every user-facing story
carries usability acceptance criteria that are testable like any other AC, and
every user-facing arc names the workflows a person will actually walk — and
proves they cannot end in a ditch.

The Architect owns this standard and applies it at authoring time; the Builder
implements and tests against it; the Reviewer rejects against its criteria
exactly as against any AC; the owner's eye (the verification queue,
DIAGNOSTICS_LOOP §5) is the final judge of the qualities only a human can
judge.

---

## 1. The four qualities

Usability criteria are written against four named qualities. Each is stated so
a test — or at minimum a countable check — exists:

| Quality | The bar | How it is checked |
|---|---|---|
| **Fewer interactions** | The primary action of a surface is reachable in the fewest clicks/keystrokes the workflow allows. The count is stated in the story ("create-and-save ≤ 2 interactions") and **counted, not felt**. | Trajectory test walks the path and counts the steps |
| **Actionable** | Every state tells the user what to do next. An error without a next step, an empty state without a starting point, a spinner without a bound is a defect. | must-always criteria per state; the honest-degrade rule below |
| **Legible and comfortable** | Easy on the eyes: contrast, type scale, spacing and information density come from the theme tokens (`frontend/theme/` is the palette of record), not per-page invention. | token-derivation check — a hard-coded color/size where a token exists is a reviewable defect |
| **Aesthetically coherent** | Colors, shapes, layout and motion read as one system across surfaces. New surfaces compose existing primitives before inventing. | Reviewer reads against the theme's ADOPTION.md; final judgment is the owner's LOOK |

**Honest-degrade is a UX law, not just a wall law:** the UI never claims a
state the system does not hold. A stale number renders as stale, a dead
backend renders as OFFLINE, a partial load says so. Misrepresentation to look
healthy is the UX equivalent of a fabricated test.

### The untrained-reader bar

Where the product's job is making expert-grade data usable by a non-expert
owner, **translation is the product, not a garnish on it**: every surface
carries a plain-language "what am I seeing", and every finding states its
observation in human terms with its evidence — "talked to a newly-registered
domain every 58±3 seconds for two hours", never a bare code or a raw
indicator. The acceptance test for such a surface is written as a criterion:
*would the untrained owner see what is happening and understand it well
enough to decide what to do?* Piping an expert surface through unchanged is
not shipping it; visibility without comprehension is another dashboard.
(The appliance shape's doctrine, adopted kit-wide because every shape has at
least one expert surface — a CI matrix, a budget gauge, a compliance
register — that some reader meets untrained.)

One paid corollary: **when two surfaces show the same quantity over
different time windows, the window is part of the answer** — render it on
both, or the reader reads a disagreement where there is none.

## 2. Trajectories — the workflows, named

Every user-facing arc's design names its **trajectories**:

- **The basic trajectory** — the shortest path from intent to outcome for the
  common case. This is the path the interaction budget (§1) is counted on.
- **Advanced trajectories** — the power paths, the bulk paths, the
  configuration paths.
- **Recovery trajectories** — what the user walks after a mistake, a timeout,
  a crash mid-flow.

A trajectory the design does not name is a trajectory nobody tested. The
Architect writes them into the arc (ITEM_AUTHORING §3); stories cite them.

## 3. No ditches — the four prohibitions

Every named trajectory must terminate in **success or a recoverable, explained
state**. Four prohibitions, each written as a must-never criterion
(ITEM_AUTHORING §4, rule 7) so its test is a sweep that must fire and must
not:

1. **No dead ends.** No state without an exit the user can see. Back always
   goes somewhere sane; cancel always cancels.
2. **No silent data loss.** A destructive step confirms, and is either
   undoable or explicitly, visibly final *before* it runs. Navigation away
   from unsaved work warns or preserves. Crash mid-flow loses at most the
   step in flight, never the work behind it.
3. **No misrepresentation.** The honest-degrade law of §1: state shown =
   state held.
4. **No unnecessary complexity.** A value the system can derive is derived,
   not asked (the same law as PRODUCT_INTAKE's derive-before-asking, applied
   to the user). A step that exists for the system's convenience rather than
   the user's is a defect with a name.

## 4. Trajectory validation is tests

Each named trajectory gets an end-to-end test at the system tier: the walk,
scripted — basic and advanced both, and the recovery paths' entry conditions
forced, not hoped for. The ditch prohibitions are must-never sweeps. A
user-facing story whose test expectation names no trajectory is the authoring
half of the same defect as an untestable AC.

Where the surface is visual, the host's screenshot tooling captures the
trajectory's states so the owner's verification (below) is a LOOK at real
pixels, not a description of them.

## 5. User support surfaces move with the code

The docs-move-with-code law, applied to the user's documents:

| Surface | Rule |
|---|---|
| **Quickstart** | Exists from the first user-facing release; the basic trajectory, written down. A changed basic trajectory changes the quickstart in the same PR. |
| **User guide** | The advanced trajectories' home. Same-PR rule. |
| **In-app help** | Every surface links its guide section or carries its one-paragraph "what is this". A new surface without its help entry is DOCS_MAP drift. |

These are rows in the host's `DOCS_MAP.md` (change-kind → doc surfaces), so
the gate that already catches design-doc drift catches user-doc drift too.

## 6. The feedback loop

The owner-verification queue (DIAGNOSTICS_LOOP §5) is the usability channel:
every shipped user-visible change lands there with the steps to LOOK, and
"verified, but X" re-enters the loop as a finding. Aesthetic judgment is the
one call this kit never automates — the machinery gets the owner to the right
pixels with the right question, and the owner's eye decides.

## 7. Cross-references

- ITEM_AUTHORING.md §3, §4 — where trajectories and usability criteria are authored
- TESTING_STANDARDS.md §1b — validation lineage; the trajectory tests' tier
- DIAGNOSTICS_LOOP.md §5 — the owner-verification queue
- PRODUCT_INTAKE.md — the end-user-experience intake axis this refines
- frontend/theme/ADOPTION.md — the tokens of record


## The page gutter

A full-width shell's side padding IS the page gutter on every screen — there
is no max-width margin to hide behind. It scales with the viewport:
`clamp(16px, 3vw, 48px)`, both sides equal, defined once on the shell so
every tab inherits it (a per-screen gutter drifts). Measured failure: a
fixed thin padding read as "content flush against the left edge" on every
tab of a wide window (Patron report 2026-09-22).
