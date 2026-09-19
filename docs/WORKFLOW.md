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

This is not a design preference, it is a measured constraint (G0a). The first
wave spawned an orchestrator as a subagent; it found the `Agent` tool disabled
inside itself and could not dispatch anyone.

### The degrade path when dispatch is unavailable (G0a)

A session that cannot spawn must not stall, and must not quietly become the
Builder. It runs the half of the loop it can run:

1. Survey the backlog and the wall.
2. **Vet** every candidate's status against ground truth, and fix drift.
3. Export the snapshot so the wall is current.
4. Hand back a **dispatch plan**, not a wish list: per unit, the item key, the
   acceptance criteria, the **exact file surfaces shown to be disjoint** (the
   lease check still applies), and the merge order for the single PR slot.
5. **Say plainly that it could not spawn, and why.**

The failure this prevents is a plan reported as a dispatch. The reader must be
able to tell "four agents are working" from "here is what four agents should
work on".

### Everything is mediated

Researchers cannot take a question to the Architect and bring the answer back to
the Builder directly — a subagent cannot call a sibling:

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
- [ ] Tests written and passing, at the tiers the change class requires
      (TESTING_STANDARDS.md section 2)
- [ ] **Mutation evidence** for every new guard: the table, one row each, with
      the anchor proven unique and the restore byte-verified (section 4)
- [ ] Every new public symbol is named by at least one test (section 7)
- [ ] **SAST and secrets lane** read, and every finding fixed or refuted with
      proof; a secrets finding blocks and the credential is rotated (section 5)
- [ ] **Test durations recorded**, and no shard map hand-edited (section 6)
- [ ] Lint and typecheck clean
- [ ] CI green (or fast-track route confirmed — see FAST_TRACK.md)
- [ ] `.wall/items/<id>.json` updated
- [ ] Docs touched if the change is architectural
- [ ] Any `DEC-NNNN` consumed is referenced
- [ ] Reviewer pass complete

Maestro cannot enforce a checklist that is not written down. This one lives in
config so it is one definition, not three drifting copies.

The testing half is normative in `docs/TESTING_STANDARDS.md`; the section
numbers above point into it. It is the document a Builder reads before writing
its first test and a Reviewer cites when rejecting.

---

## 6. Review

A builder that writes its own tests and declares them passing has **no
adversary**. The Reviewer subagent reads the diff cold, with no access to the
builder's reasoning, and returns only pass or fail-with-findings.

Architect signs off on requirements; Maestro signs off on process. Neither reads
code. The Reviewer is the only agent that does.

Cap rework at three rejection cycles, then escalate to Adjudicator, then to the
human. Two parties who can both reject, with no cap, is an infinite loop.

### Thread ownership is exclusive (G8)

**The unit that owns the PR owns its threads. One writer per conversation** --
the same rule decisions already follow, for the same reason.

The coordinator and a builder both answered the same hosted-reviewer thread
within minutes, under one shared platform identity, and double-replied. Under a
shared identity a reader cannot tell two writers apart afterwards; it reads as
one writer contradicting itself.

A thread changes hands only through an explicit handshake: the requester tells
the owner **before** posting anything, the owner acknowledges or is declared
unreachable (its run has ended), and from the effective time the owner stops
writing in that thread. The form is `docs/handoffs/review-thread-takeover.md`,
and "it was faster" is not a listed reason.

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

| | Foreman | Maestro | Architect | Adjudicator | Builder | Integrator | Reviewer | Researcher |
|---|---|---|---|---|---|---|---|---|
| Assign work | | yes | | | | | | |
| Write ledger/wall | yes | | | | | | | |
| Own requirements | | | yes | | | | | |
| Own process | | yes | | | | | | |
| Break ties | | | | yes | | | | |
| Edit source | | | | | yes | yes | | |
| Reject work | | yes | yes | | | | yes | |
| Rebase / force-push the PR ref | | | | | | yes | | |
| Own a PR's review threads | | | | | | yes | | |
| Merge / flip ready | | yes | | | | | | |

Foreman never assigns work. Maestro never edits ledgers. Keeping those separate
is what stops the observability layer from becoming a second control plane.

The Integrator edits source only to land a unit that is already built: rebase
resolution and derived-file regeneration. It is the only role that may force-push
the designated ref, and only behind the safety proof in section 9. **Merge and
ready-flip belong to the Maestro alone** (G12) -- that authority caught two
would-have-been-early merges where draft-scoped checks read green but were not
the full pyramid.

---

## 8. Status is verified, not reported

Agents self-reporting status is unreliable. Ground truth comes from git, test
results and CI, with Courier reconciling claims against evidence.

The clearest case, already implemented: a `run_start` with no terminal event past
its deadline reclassifies the agent as `stale`, not `working` — regardless of
what its last event claimed. A dead agent must never read as busy.

Two corollaries the wave added:

- **Read the evidence, do not accept the summary** (G0b). A builder's own
  draft-CI report was superseded twice by reading the check runs directly. A
  check-run name with its conclusion is evidence; "CI is green" is a claim.
- **Bookkeeping cannot lag the merge** (G9). A PR merged before its item state
  was updated left the wall claiming "in CI" on a merged PR, and the next
  unrelated unit inherited the resulting red. Item state flips at **merge**
  time. An item claiming an open PR that the host says is merged or closed is an
  integrity flag, checked every sweep.

---

## 9. Integration: transplanting one unit through the single PR slot

N units build in parallel worktrees; there is **one branch and one PR slot**. So
every finished unit is transplanted, one at a time, and the transplant is its own
procedure (G5). The wave executed it five times; by the third run it was handling
two compactor-consumed-fragment conflicts and a placeholder-lease rejection
exactly as written. Two more things it proved: the procedure must be a document
(G11, G13), and the person running it is best served by being the unit's own
Builder wearing the Integrator hat.

Role sheet: `.claude/agents/integrator.md`. Order form:
`docs/handoffs/transplant-order.md`. The steps, in order, because the order is
the procedure:

**0. Record the starting state.** The designated ref's SHA, `main`'s SHA, the
unit's commit SHAs. These are the safety proof's inputs and the only rollback
anchor.

**1. Rebase onto the moved `main`.** It has moved. That is the normal case.

**2. Resolve conflicts mechanically -- regenerate, never hand-merge.**

- A **derived file** (manifest, generated matrix, compacted index, lockfile with
  a generator): take either side, then **re-run the generator**. Never hand-merge
  one and never resolve it by picking the side that looks right.
- A **source file** is a real conflict: resolve with the unit's intent, then
  re-run the unit's tests over the resolved region. A resolution that changes
  behaviour the tests do not cover is a finding, not a judgement call.

**3. The safety proof, before any push.** Force-with-lease protects against
someone else's push, not against your own mistake. The proof is a diff you run
and read:

1. Designated ref vs `main`, **filtered to the unit's declared path scope** --
   every hunk must be this unit's work.
2. Designated ref vs `main`, **excluding** that path scope -- this must be
   **empty**.
3. Non-empty means the ref is carrying someone else's unmerged work, or a stale
   copy of merged work, and the next push destroys it. **Stop, do not push,
   report both SHAs and the exact paths.** That is a `blocked` outcome and the
   Maestro's call.

Push only then, with `--force-with-lease` carrying the SHA from step 0.

**4. Re-check budgets (G10).** The rebase pulled other units' additions into the
same budget-counted sections, so the unit's pre-rebase measurement is stale. Four
units nearly blew one budget at once, each having measured only its own addition.
Record the measured number and the headroom.

**4b. Re-score the test shards.** The rebase moved tests into shards that were
balanced without them: `testkit check` (TESTING_STANDARDS.md section 6), and
regenerate the map -- never hand-edit it -- if it reports imbalance or drift.

**5. Gates LAST (G6).** After steps 1 to 4, immediately before the commit and the
push. Never earlier. There is **no CI** between a worktree commit and this
transplant, so the gate output is the only signal covering everything the
transplant just did. Quote the output; a summary of a gate is not a gate.

**6. Open the PR as a draft**, with the unit, the criteria and their sources, the
gate output, the safety-proof result, and the budget numbers in the body.

**7. Drive the review threads** -- section 10 for the lane postures, section 6
for thread ownership.

**8. Report green and stop (G12).** Check-run names **with conclusions**, read
from the check runs; say whether that was the full pyramid or a draft-scoped
subset. The Maestro flips ready and merges, and the bookkeeping follows the merge
immediately (section 8, G9).

---

## 10. Hosted reviewer lanes

Automated review lanes are useful and are not authorities. Measured across the
wave's PRs, each lane needs a written posture (G7); without one, agents either
obey a wrong finding or dismiss a right one.

**Verify before accepting OR declining.** Both directions require checking the
finding against the actual file. Accepting an unverified finding ships a change
nobody needed; dismissing one unverified is how a real defect survives review.

**Truncated-diff findings are a registered class.** A reviewer handed a truncated
diff will report *its own truncation boundary* as a defect in the file -- "this
file is truncated", "this function is unterminated". The same false finding was
refuted twice in one wave. Refute it with a **parse proof**: read the real file,
show the construct is complete, and quote the proof in the reply. **Never refute
by assertion** -- an assertion is indistinguishable from an agent brushing off a
finding it did not want.

**Declining with a proven better fix is legitimate**, and it requires a
**counterfactual test**: a test that fails under the suggested fix and passes
under yours, or the reverse, shown in the reply. Three findings were closed this
way. Without the counterfactual it is a preference, not a refutation.

**Metered lanes are named, not waited on.** A quota-exhausted or rate-limited
lane is recorded as unavailable in the wave report and does not hold the PR.
Waiting on a lane that cannot answer is indistinguishable, from the outside, from
a stalled unit.

**One writer per thread** -- section 6.

**Every real finding leaves a prevention behind**: the rule, the regression test,
and the doc line that stop the class recurring. A finding closed without one is a
finding you will receive again.
