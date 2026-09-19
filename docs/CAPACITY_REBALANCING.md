# CAPACITY_REBALANCING.md

The decision-making discipline for tuning the machine while it runs: PR
creation pacing, the number of builders and researchers, and CI test sharding
— optimized for **cost, time and throughput, under a quality floor that is
never traded**.

Quality is a constraint, not an axis. The Definition of Done and the testing
standards do not flex when the wave is behind; the knobs below trade time
against cost against throughput *inside* that floor. A rebalance that would
relax a gate is not a rebalance — it is a change to the rules, and rules
change only by their own procedure.

---

## 1. Who decides what

Three roles participate, and the authority matrix (WORKFLOW §7) still binds —
rebalancing does not create a second control plane:

| Role | In rebalancing | May NOT |
|---|---|---|
| **Foreman** | Measures and recommends: reads the ledger, the wall's flags, CI timings and the shard report; narrates anomalies; files a rebalance recommendation with the numbers attached | Assign work, change any knob, or dispatch anyone — the Foreman's output is a *recommendation event*, always |
| **Maestro** | Decides and executes, **within the configured caps**: shifts the builder/researcher split, paces dispatch and PR creation, adopts a regenerated shard map, re-orders the integration queue | Exceed a `role_limits` cap or a budget meter — those ceilings are the engineer's |
| **Adjudicator** | Rules when signals conflict: throughput says more builders, rework says fewer; a recommendation contradicts a live `DEC-NNNN`; two consecutive rebalances reversed each other (oscillation) | Originate a rebalance — it answers questions put to it |
| **Engineer** | Owns the ceilings: raising caps, budgets, runner spend, adding CI capacity — via the human queue like every engineer decision | — |

The chain is always: **mechanical measurement → Foreman recommendation →
Maestro decision → (Adjudicator on conflict) → engineer only at a ceiling.**
A knob turned without a measurement attached is a hunch, and hunches do not
move config.

## 2. The signals (all measured, none self-reported)

Every signal comes from the ledger, the harness or CI — never from an agent
describing itself:

| Signal | Source | What it indicates |
|---|---|---|
| Builder utilization: `blocked` / `working` ratio | run + question events | Too many builders for the answerable work |
| Blocked builders while researcher slots idle | courier escalation flags (WORKFLOW §4 table) | Capacity on the wrong side of the split |
| Question latency vs SLA, per hop | `question_raised`→`question_answered` deltas | Research is the bottleneck, not building |
| Rework cycles per unit | reviewer reject events | Quality strain — parallelism outrunning specification |
| Integration queue depth (finished units awaiting the PR slot) | item states | Building outruns integrating; more builders will not help |
| PR slot occupancy + cancelled-run count | host checks | Serialization violations burning CI minutes (measured: 11 cancelled runs / 77 min on one PR) |
| CI wall-clock p50/p95 + queue time | check runs | The time cost of every merge |
| Test shard imbalance + drift | `testkit check` (exit 1 on either) | Sharding no longer matches the suite |
| Token spend per merged unit | harness usage in `run_end` (DEC-0008: actuals, never estimates) | The cost line the budget meters aggregate |
| Review-lane latency / quota state | lane postures (WORKFLOW §10) | A metered lane about to be named-not-waited-on |

## 3. The decision table

Default responses, applied by the Maestro when the trigger is measured true.
Each is a starting rule, not a law — but departing from one gets a recorded
reason:

| Trigger (measured) | Default rebalance |
|---|---|
| ≥2 builders `blocked` on questions, researcher slots idle | Shift 1 builder slot to researchers (the elastic rule: researcher cap tracks builders + 2) |
| Question SLA breaches recurring at one hop | Add a researcher; if the hop is Architect-bound, queue rulings in batches instead |
| Integration queue ≥ 2 finished units | **Pause new dispatches** (PR pacing); current builder takes the Integrator hat; drain the queue before building more |
| Cancelled CI runs > 0 this wave | Stop and re-read serialization — this is a rule violation, not a load signal; no knob fixes it |
| Rework cycles ≥ 2 on ≥ 2 units | Reduce parallel builders by 1; route the next stories through a design-review pass before dispatch (quality strain = specification debt, not reviewer excess) |
| CI wall-clock p95 rising across waves | `testkit durations` → `balance` → adopt the regenerated map **only on a measured wall-clock win** on the same suite; record both numbers |
| `testkit check` exits 1 (imbalance or drift) | Regenerate the shard map — never hand-edit it (the reviewer rejects a hand-edited map on sight) |
| Token spend per merged unit rising | Author smaller stories (ITEM_AUTHORING §4) before adding or removing agents — unit size, not headcount, is the first lever |
| Budget meter warns | Report to the engineer with the trend; advisory means the human decides, not that nobody does |
| A metered review lane exhausted | Name it unavailable in the report and proceed; do not idle the PR on a lane that cannot answer |

Two standing preferences behind the table: **drain before you widen** (a
deeper integration queue is never fixed by more builders) and **one knob per
cycle** — change one thing, re-measure, then change the next, or the
measurement cannot attribute the effect.

## 4. The rebalance record — reversible by construction

Every executed rebalance writes one event carrying: the signal values that
triggered it, the knob changed, **from → to**, the expected effect, and the
review horizon (when it gets re-measured). The *from* value makes every
rebalance a one-step revert; the horizon makes "did it work" a scheduled
question instead of a vibe. At the horizon the Foreman reports the same
signals again: improved → keep; regressed → revert and record why; two
reversals of the same knob → the oscillation goes to the Adjudicator rather
than a third flip.

Shard-map adoption follows the same shape with its own artifact: the map is
regenerated (never edited), the before/after wall-clock is recorded, and the
old map remains one commit back.

## 5. Cadence

- **Continuously:** the mechanical plane measures; courier flags surface on
  the wall as they occur.
- **At each wave phase boundary** (design done, building done, integration
  drained): Foreman recommendation → Maestro decision, using the table.
- **At wave close** (SESSION_LIFECYCLE §3): signals and every rebalance with
  its outcome go in the wave report — budget actuals beside config — so the
  next wave starts from measured capacity, not remembered capacity.
- **Never mid-transplant:** the integration procedure runs to completion;
  rebalancing between units, not inside one.

## 6. Cross-references

- `docs/diagrams/AGENT_TOPOLOGY.md` — where these roles and edges sit
- `docs/WORKFLOW.md` §4, §7 — escalation flags, the authority matrix
- `docs/TESTING_STANDARDS.md` — sharding, measurement and rebalance mechanics
- `tools/wall/testkit.py` — `durations` / `balance` / `check`
- `docs/SESSION_LIFECYCLE.md` — wave close, the engineer's queue
- `.claude/agents/foreman.md`, `adjudicator.md`, `.claude/MAESTRO.md` — the deciders
