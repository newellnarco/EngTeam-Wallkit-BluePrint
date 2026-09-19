# WORKFLOW.md

How work moves through the crew, and why the shape is what it is.

---

## 1. The execution model

**Claude Code subagents do not persist.** They are single-shot invocations with
their own context that end when the task ends. Nothing polls, nothing watches,
nothing runs in the background between calls.

This kills three designs that look natural on paper:

- A Foreman that keeps the wall fresh every two minutes.
- An Adjudicator that watches the workflow.
- A Maestro that holds an in-memory map of who is assigned what.

All three presuppose daemons. The fix is to move persistence out of the agents
and into **state on disk**, then trigger short agent invocations off events.

| Presupposed | Actual mechanism |
|---|---|
| Foreman polls the wall | Courier script runs on hooks + a system timer |
| Maestro remembers assignments | `.wall/items/` and `.wall/registry/leases.json` |
| Adjudicator watches | Integrity checks run every sweep; flags surface on the wall |
| Foreman singleton "running" | A lock file with a heartbeat and a TTL |

### Maestro is the session, not a subagent

Subagents cannot spawn subagents. If Maestro is a subagent it cannot dispatch
builders. So **the top-level Claude Code session is Maestro**, and everything
else is a subagent it invokes.

This breaks one link in the original outline. Researchers cannot take a question
to the Architect and bring the answer back to the Builder directly — a subagent
cannot call a sibling. Everything is mediated:

```
Builder (subagent)   → returns OPEN_QUESTION to Maestro
Maestro              → searches the decision log first
                     → if no hit, dispatches Researcher (subagent)
Researcher           → returns findings
Maestro              → dispatches Architect (subagent) with findings
Architect            → returns ruling
Maestro              → writes DEC-NNNN, re-dispatches Builder with it attached
```

More round trips, but every decision now passes through a single writer, which
is what makes "no answer contradicts another" enforceable rather than aspirational.

---

## 2. Dispatch

Before assigning any work, Maestro:

1. **Checks the budget.** Advisory, but recorded. Admission control belongs
   before dispatch, not after the overrun.
2. **Checks the lease table.** Subagents in one session share a working tree.
   Two builders editing at once corrupts it. Each item declares a path scope; a
   second builder whose scope overlaps is not dispatched.
3. **Attaches decisions.** Any `DEC-NNNN` in scope goes into the prompt and into
   `decisions_in_context` on the run record.
4. **Writes `run_start`** with agent key, item, deadline and scopes.

Leases carry a TTL so a dead agent does not hold a path forever. When parallel
sessions arrive, git worktrees go underneath the same lease check — the check
itself does not change.

---

## 3. Ambiguity: detection, not good intentions

Builders are reliably bad at noticing ambiguity. The failure mode is not a
builder that blocks too often; it is one that reads a vague requirement, picks a
plausible interpretation, builds it confidently, and is discovered two days later.

"Be smart enough to know" has to become mechanical.

### The forcing function

Before writing code, a builder maps **every acceptance criterion to a source**:
a requirement section, a decision id, or an existing test. Any criterion with no
citable source *is* an ambiguity, by definition. This turns a judgment call into
a lookup, and it is checkable afterwards because the sources land in the run's
`meta.json` beside `decisions_in_context`.

### Classification

```
missing_requirement     conflicting_decisions   undefined_interface
unclear_acceptance      unspecified_edge_case   dependency_unknown
```

Closed vocabulary so it aggregates. Patterns in this field tell you which
handoff is thin.

### Continuing safely

"Work on something else meanwhile" has a trap: if the independent slice touches
files the answer might change, the builder is still building on the guess it was
trying to avoid, just indirectly.

So the builder declares two scopes, and **Maestro decides the outcome**, not the
builder:

```json
{"event": "question_raised", "question_id": "q_0042", "item_id": "ST-106",
 "ambiguity_class": "unclear_acceptance",
 "blocks_criteria": ["AC-3", "AC-4"],
 "dependent_scope":   ["backend/ledger/merge.py", "backend/tests/test_merge.py"],
 "independent_scope": ["backend/ledger/shard.py"],
 "outcome_hint": "partial"}
```

- Scopes **file-disjoint** → `partial`. Builder keeps its lease and continues.
- Scopes **overlap** → `blocked`, whatever the builder thinks.

A `blocked` builder releases its slot back to Maestro; the item is parked on a
question nobody can rush. A `partial` builder keeps it. Otherwise the builder cap
gets consumed by agents doing nothing.

### Decision log first

Maestro searches `docs/decisions/` **before** dispatching a researcher. A hit
answers the question immediately at near-zero cost, logged as
`question_answered` with `source: decision_log`.

This is also the first defensible definition of "tokens saved" — see
EVENT_SCHEMA.md §5.

---

## 4. Escalation as an invariant

"Ensure a researcher has been assigned" must not depend on anyone remembering.
Courier checks these every sweep, so the wall catches a lapse whether or not
Maestro behaved:

| Condition | Flag |
|---|---|
| Item `blocked`, no open question | Contradiction — blocked without asking |
| Open question, no `question_assigned` past SLA | Nobody picked it up |
| Assigned, no researcher `run_start` past SLA | Assigned on paper only |
| Builder `blocked` while a researcher slot is idle | Capacity wasted |
| Question open past threshold | Escalate a tier |

### The ladder

Time-driven, not attempt-driven:

```
Researcher  →  second researcher pass  →  Architect direct
            →  Adjudicator (if the answer conflicts with an existing decision)
            →  the human queue
```

Each hop writes `question_escalated` with a reason, so `wall trace` shows the
full path when something took six hours to answer.

Suggested starting SLAs, all configurable in `.wall/config/wall.json`:

| Hop | Default |
|---|---|
| Assignment after `question_raised` | 5 min |
| Researcher first run after assignment | 10 min |
| Researcher → Architect | 30 min |
| Architect → Adjudicator or human | 60 min |

---

## 5. Definition of done

A builder is not done when its tests pass. Minimum gate:

- [ ] Every acceptance criterion maps to a source
- [ ] Tests written and passing
- [ ] Lint and typecheck clean
- [ ] CI green (or fast-track route confirmed — see FAST_TRACK.md)
- [ ] `.wall/items/<id>.json` updated
- [ ] Docs touched if the change is architectural
- [ ] Any `DEC-NNNN` consumed is referenced
- [ ] Reviewer pass complete

Maestro cannot enforce a checklist that is not written down. This one lives in
config so it is one definition, not three drifting copies.

---

## 6. Review

A builder that writes its own tests and declares them passing has **no
adversary**. The Reviewer subagent reads the diff cold, with no access to the
builder's reasoning, and returns only pass or fail-with-findings.

Architect signs off on requirements; Maestro signs off on process. Neither reads
code. The Reviewer is the only agent that does.

Cap rework at three rejection cycles, then escalate to Adjudicator, then to the
human. Two parties who can both reject, with no cap, is an infinite loop.

---

## 7. Authority

When agents disagree, **evidence outranks rhetoric**. Tiebreak order:

```
1. A failing test or CI result
2. An existing decision-log entry
3. The expert of record for that domain
4. Adjudicator
5. The human
```

Two agents arguing, resolved by a third agent's judgment, ratifies whichever was
more confident. Anchoring on tests and written decisions avoids that.

| | Foreman | Maestro | Architect | Adjudicator | Builder | Reviewer | Researcher |
|---|---|---|---|---|---|---|---|
| Assign work | | ✔ | | | | | |
| Write ledger/wall | ✔ | | | | | | |
| Own requirements | | | ✔ | | | | |
| Own process | | ✔ | | | | | |
| Break ties | | | | ✔ | | | |
| Edit source | | | | | ✔ | | |
| Reject work | | ✔ | ✔ | | | ✔ | |

Foreman never assigns work. Maestro never edits ledgers. Keeping those separate
is what stops the observability layer from becoming a second control plane.

---

## 8. Status is verified, not reported

Agents self-reporting status is unreliable. Ground truth comes from git, test
results and CI, with Courier reconciling claims against evidence.

The clearest case, already implemented: a `run_start` with no terminal event past
its deadline reclassifies the agent as `stale`, not `working` — regardless of
what its last event claimed. A dead agent must never read as busy.
