# RETROSPECTIVES.md

The loop that makes each role better: a measured retrospective at every wave
close, whose outputs are **diffs to artifacts, never sentiment**. The wave
report says what happened; the retrospective decides what the process changes
because of it — and lands the change before the session ends.

The discipline extends two laws that already bind this kit: evidence over
self-report (G0b — a retro built on how the wave *felt* ratifies whoever
narrates best), and root-cause-not-repair (`ENGINEERING_STANDARD.md` §4.5,
DIAGNOSTICS_LOOP §4 — a process fix that is a reminder is a bandaid, and
bandaids on bandaids is the exact failure this document exists to prevent).

---

## 1. When, and who

- **At every wave close**, as part of SESSION_LIFECYCLE §3 step 6: the wave
  report's **Retrospective** section is written in the same pass as the report.
- **At arc close** for arcs that outlive several waves — same shape, scoped to
  the arc.
- **The Foreman prepares, the Maestro runs, the Adjudicator breaks ties.**
  The Foreman assembles the measured signals (it owns the ledger and the
  rollups; it never decides). The Maestro decides which diffs land (it owns
  SOPs and the definition of done). A retro finding that contradicts a live
  `DEC-NNNN`, or two consecutive retros reversing the same change, goes to the
  Adjudicator — the same oscillation rule as CAPACITY_REBALANCING §4.
- Every role's record participates; no role's self-report is the measurement.

## 1b. The Patron's input

The Patron does not wait for the retro to notice something. **`wall
retro-note --text "..."`** records an input at any moment; it shows on the
wall's RETRO tab as pending until the next retro, and **that retro must
address every pending input in its record** — adopted as a diff, queued as
a wall item, or declined with a reason. Silence is not one of the three.

## 2. The inputs — per-role signals, all measured

Every signal comes from the ledger, the wall, the host's checks or CI — never
from an agent describing itself. The starting set; hosts extend it:

| Role | Growth signals (trend across waves, not one-wave verdicts) |
|---|---|
| **Builder** | Rework cycles per unit; questions raised by ambiguity class (a rising `unspecified_edge_case` count is an authoring lesson, not a builder fault); gate failures after a green self-claim; token spend per merged unit |
| **Reviewer** | Escape rate — defects found after merge that a cold read of the diff could have caught; findings later refuted vs confirmed; review latency |
| **Researcher** | Answer latency vs SLA per hop; decisions reopened because findings missed a source; decision-log hits that made research unnecessary |
| **Architect** | Criteria that failed the Builder's source-mapping on first contact; drift found by someone other than the drift pass; amendment rate on in-flight stories; trajectories (UX_STANDARDS §3) discovered missing after dispatch |
| **Maestro** | Serialization violations and cancelled CI runs; lease conflicts; dispatches that bounced for an undeclared dependency |
| **Warden** | Findings by risk tier; playbook hit rate vs unknown-signature rate; redaction-audit results |
| **Process-wide** | Bug intake rate vs class-retire rate; **class recurrence** — a failure class recurring after its prevention landed means the prevention failed and goes back through the five whys; coverage growth per tier; wave wall-clock vs the last wave's |

The quality trend the whole table serves: **bug counts falling, rework
falling, wall-clock falling, under the same gates.** A wave that got faster by
relaxing a gate did not get faster (CAPACITY_REBALANCING: quality is a floor,
not an axis).

**A findings spike is a signal about upstream grouping, not about the
finder.** When reviewers or CI start finding more, ask which upstream choice
missed something that had a cost: test scope too narrow, work unit too big
or mixed, design under-thought in the first cut, or a recently-adopted
speed/cost lever letting defects escape. Price the escape — a seven-finding
second review round on one pull request is a full extra CI pyramid plus a
review cycle, traced in the field to a contract the first cut should have
carried — and read every efficiency claim per merged unit of work, never
per run (FAST_TRACK's lever rule).

**Measure the distribution before applying 80/20 — some distributions are
flat, and some 20% is load-bearing.** Pareto is a measurement, not an
assumption. Where the distribution is sharp (one field measurement: 80% of a
suite's clock in ~3% of its tests), concentrate; where it is flat (the same
repo's defect classes: ~100 families, the largest at ~12%), a few deep
defences are the wrong buy — automate cheaply and broadly instead. And
exempt a named floor from every optimisation: Pareto shows where the mass
is, not which parts hold the roof up, so the checks that guard the optimiser
itself are never in scope for the optimiser.

## 3. The five whys, applied to the process itself

Every retro item that names a defect gets the same chained five-whys read the
diagnostics loop demands of system failures — and the same rule: **a level
naming a person or a moment of inattention is not a cause.** Keep asking until
the answer is structural: a rule that could not be violated, a gate that fires
mechanically, a template that carries the field, a handoff form that forces the
question. The bandaid test, stated once:

> If the fix is "remember to", it is not a fix. If the fix is a second bandaid
> over a previous bad design, the retro item is a **replacement candidate** and
> routes through `TECH_EVALUATION.md` — new functionality to overcome an old
> mistake is designed and measured, never accreted.

## 4. Outputs are diffs — the closed list

Each retro item resolves to exactly one of:

1. **A rule change** — RULES / BEST_PRACTICES / the shared criteria.
2. **An SOP change** — WORKFLOW, MAESTRO.md, a role sheet under `.claude/agents/`.
3. **A template or handoff-form change** — the field that was missing rides
   every future use.
4. **A failure class + regression test** — FAILURE_PATTERNS entry with the
   check that would have caught it, test landed in the same change.
5. **A rebalance recommendation** — routed through CAPACITY_REBALANCING, never
   applied inside the retro.
6. **A design/replacement candidate** — routed through TECH_EVALUATION or
   filed as an arc for the Architect.
7. **"No change, watching"** — recorded with the signal to re-read and the
   horizon to re-read it at. A legitimate output; silence is not.

**At most three landed changes per retro.** The rest queue as wall items —
the one-knob-per-cycle law applies to process exactly as to capacity, or the
next retro cannot attribute what worked. An output without an owner and an
artifact diff is not an output.

## 5. The growth ledger

The wave report's Retrospective section carries, wave over wave: the per-role
signal values, the diffs landed (with paths), the queued items, and last
wave's diffs **re-measured** — did the change move the signal it named?
**The same record is emitted as a `retro_held` ledger event** (EVENT_SCHEMA
"Oversight"), which is what the wall's RETRO tab folds into the trend view —
a retro that skips the event has no surface, and a discipline without a
surface decays silently (DEC-0026). The
next session's ground phase (SESSION_LIFECYCLE §1 step 8) vets this section
like the rest of the report: against evidence, before acting on it.

## 6. Anti-patterns, named

- **Blame retro** — any line whose subject is an agent rather than a
  mechanism. Rewrite until the subject is the mechanism.
- **Vibes adoption** — a change with no signal attached. Not adopted.
- **Retro inflation** — ten resolutions, zero re-measured. Three, landed,
  re-measured beats ten remembered.
- **The silent skip** — a wave under pressure skipping the retro. The close
  procedure is a procedure; the retro is step 6's second half, not an
  optional garnish.

## 7. Cross-references

- SESSION_LIFECYCLE.md §3 step 6 — where the retro lives in the close
- docs/handoffs/wave-report.md — the RETROSPECTIVE section shape
- CAPACITY_REBALANCING.md — the capacity half of the same measured loop
- DIAGNOSTICS_LOOP.md §4 — the five-whys law this reuses
- TECH_EVALUATION.md — where replacement candidates go
- ENGINEERING_STANDARD.md §4.5 — root cause, not repair
