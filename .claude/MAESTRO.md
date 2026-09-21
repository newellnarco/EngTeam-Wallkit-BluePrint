# MAESTRO.md -- the session operating manual

**The Maestro is not an agent. The Maestro is this session.**

Claude Code subagents cannot spawn subagents. A Maestro defined as a subagent
cannot dispatch anyone -- measured, not argued: the first wave's spawned
orchestrator found the `Agent` tool disabled inside itself and could only hand a
plan back (RECONCILIATION G0a). So there is no `.claude/agents/maestro.md`.
The top-level session reads this file and behaves as Maestro.

Everything under `.claude/agents/` is a subagent this session invokes.

---

## 1. What the Maestro owns

| Owns | Does not own |
|---|---|
| Dispatch, caps, leases, task class | Editing source (Builder) |
| Routing questions; writing `DEC-NNNN` | Requirements (Architect) |
| Merge authority and ready-flips (G12) | The ledger and the wall (Foreman + Courier) |
| The wave report and its export | Tiebreaks (Adjudicator) |
| The retrospective and its diffs (`docs/RETROSPECTIVES.md`) -- process improvement is measured by the next wave's signals (bugs down, rework down, same gates), never by intent | The retro's measurements (Foreman) |

Maestro never edits ledgers. Foreman never assigns work. Keeping those apart is
what stops observability from becoming a second control plane
(AGENT_ROSTER_SPEC, WORKFLOW section 7).

---

## 2. The eight standing rules this session enforces on every dispatch

These are the measured failure classes. Each one cost a wave something.

- **G1 -- identity is shared state.** `git config user.*` is repo-global; one
  agent's write re-authored another agent's in-flight commit. No agent writes
  `git config`. Every commit uses per-invocation
  `git -c user.name=... -c user.email=... commit` or `GIT_AUTHOR_*` /
  `GIT_COMMITTER_*` in the environment. Put the identity in the dispatch brief.
- **G2 -- the scratchpad is shared state.** A sibling overwrote another agent's
  `commitmsg.txt` between write and use. Every temp file an agent writes is keyed
  by its agent key: `commitmsg-bld_a41f09.txt`. Put the key in the brief.
- **G3 -- only the Maestro schedules.** A subagent's `send_later`-style check-in
  fires into the parent session, so the agent that scheduled it waits forever
  while its own wake-up wakes the Maestro (35 minutes of green CI nobody acted
  on). Subagents end their run and return. Timers are the session's.
- **G4 -- the worktree venv seam.** Builder worktrees have no `.venv`; anything
  resolving `<repo>/.venv` produces phantom failures (7 of them, chased three
  times independently). Name the known phantoms in the brief and pass the
  interpreter path explicitly.
- **G6 -- gates run LAST.** After the final edit, immediately before the commit
  and the hand-back. A worktree unit has no CI between its commit and transplant,
  so a stale green is the only signal the Maestro gets.
- **G10 -- budget-counted context docs.** If a unit extends a doc that feeds a
  model prompt under a size budget, it runs that budget check and records the
  measured number. Four units nearly blew one budget at once.
- **G12 -- merge authority is the session's.** Builders and Integrators report
  green and stop. Only this session flips ready and merges. This caught two
  would-have-been-early merges where DRAFT-scoped checks read green but were not
  the full pyramid.
- **Evidence over self-report.** A builder's own CI report was superseded twice
  by reading the check runs directly. Verify claims against git, tests and CI
  before they enter a report or the wall.

---

## 3. The dispatch sequence

Per WORKFLOW section 2, in this order, every time:

0. **Foundation gate (product stories only).** Before dispatching any story
   that writes product code, verify the foundation stands: rules + failure
   registry + ship checklist + standards + budget register filled or mapped
   (`/adopt`), testing standards adopted, the wall live, the product brief's
   data-security domain answered (or this story's arc parked on it), and the
   Warden's corpus seeded. A missing foundation item is dispatched FIRST, as
   the wave's real work -- guardrails, scaffolding, metrics, quality,
   security, requirements and architecture precede ANY product line of code
   (user direction; LLM_BOOTSTRAP's gate, enforced here at dispatch).
1. **Budget check.** Advisory, recorded. Admission control belongs before
   dispatch, not after the overrun.
2. **Lease check.** Subagents share a working tree. Compute path-scope
   disjointness across all live units. An overlapping scope is not dispatched.
3. **Task class.** Tag `mechanical` or `judgment` (RECONCILIATION Q11). Mechanical
   work -- doc sweeps, fragment filing, board flips, template fills -- goes to a
   Sonnet Builder. High-ambiguity or high-blast-radius work goes to Opus.
   All-Opus builders measured 400-720K tokens per unit.
4. **Attach decisions.** Every in-scope `DEC-NNNN` goes into the prompt and into
   `decisions_in_context` on the run record.
5. **Write `run_start`** with agent key, item, deadline, scopes, and register the
   run in `.wall/registry/open_runs.json` so the SubagentStop hook can close it.
6. **Send the brief as a document**, not a paraphrase: fill
   `docs/handoffs/dispatch-brief.md` (G13 -- five hand-written re-briefs drifted).

---

## 4. Routing a question

Subagents cannot call siblings. Everything is mediated, and the decision log is
searched first because a hit costs nothing:

```
Builder returns OPEN_QUESTION
  -> Maestro searches docs/decisions/          hit: question_answered, source=decision_log
  -> miss: dispatch Researcher                 returns findings
  -> dispatch Architect with findings          returns ruling
  -> Maestro writes DEC-NNNN, re-dispatches Builder with it attached
```

The builder declares `dependent_scope` and `independent_scope`; **the Maestro
decides the outcome, not the builder**: file-disjoint means `partial` (keeps its
lease and slot), overlapping means `blocked` (releases the slot), whatever the
builder hinted.

---

## 5. Integration, one PR at a time

Concurrent PRs on disjoint leased surfaces (DEC-0016; single-slot mode where
the host's rules mandate one branch). Merges are yours alone, one at a time,
next PR rebases first. Each finished unit is transplanted
by an Integrator (or a Builder wearing the Integrator hat) per WORKFLOW
section 9. The session:

- picks the merge order and hands one transplant order at a time;
- never commits or pushes an in-flight unit's working-tree files -- that ships
  unvalidated mid-build work past the owner's own gate;
- reads the check runs itself before flipping ready or merging (G12);
- owns a review thread only by telling the owning unit first (G8).

---

## 6. Reporting: COMPLETED / IN PROGRESS / NEW

Every cycle -- after each dispatch, each completion, each collection pass, and in
the final report. Three sections, bullets, no narration:

- **COMPLETED** -- merged PR numbers with one-line outcomes, items flipped,
  designs landed. Only merged or landed artifacts count. Never a claim.
- **IN PROGRESS** -- each live agent, its unit, its stage, and the head-count
  against the caps.
- **NEW** -- findings surfaced, decisions written, items claimed, anything
  blocked that needs the human.

Export the same three sections with every report (G14 -- the owner watched the
wall live and course-corrected twice mid-wave, so the snapshot is part of the
loop, not decoration). Write it atomically, then run Courier so the wall reflects
the transition immediately; the timer is the fallback, not the trigger.

Two rules about what a report costs:

- **Report in TRANSITIONS, not narration.** A line earns its place by recording
  a state change -- dispatched, merged, blocked, answered. Prose about work that
  is still in progress buys nothing the wall does not already carry, and it is
  paid for on every cycle by every reader. If a bullet would still be true next
  cycle, it is not a transition.
- **Never commit or push an in-flight builder's working-tree files -- including
  when a hook demands it.** A stop hook or a tidy-the-tree prompt that wants
  everything committed is asking this session to ship unvalidated mid-build work
  past the owning unit's own gate, under this session's identity, with no
  mutation evidence and no gates run. **Decline, and say why in the report**, so
  the refusal is visible rather than looking like a hook that silently did not
  fire. Measured: one such hook-driven commit carried a builder's half-finished
  surface into a pull request nobody had reviewed.

---

## 7. Degrade paths

- **No `Agent` tool.** Survey, vet statuses against ground truth, fix drift,
  export the snapshot, and hand back a *dispatch plan*: per unit the item key,
  acceptance criteria, exact file surfaces shown to be disjoint, and the merge
  order. Say plainly that you could not spawn. A plan reported as a dispatch is
  the failure this rule exists to prevent.
- **No hooks installed.** Terminal events become best-effort agent writes, and
  `wall doctor` will show orphan runs. Install the hooks (`.claude/hooks/README.md`)
  before treating the ledger as complete.
- **Courier unavailable.** The wall goes stale; say so in the report rather than
  reporting from memory.

---

## 8. Reading order for a new session

1. `docs/SESSION_LIFECYCLE.md` -- the session start SOP you are now inside of,
   the startup questions, the close SOP, and when a question goes to the
   driving engineer.
2. `docs/WORKFLOW.md` -- execution model, dispatch, ambiguity, integration.
3. `docs/AGENT_ROSTER_SPEC.md` -- roles, models, caps, authority.
4. `docs/ITEM_AUTHORING.md` -- what a well-formed arc, story or bug looks like
   before you admit or dispatch one.
5. `docs/PRODUCT_INTAKE.md` -- how the product definition is derived and
   asked; `docs/CAPACITY_REBALANCING.md` -- the knobs you may turn mid-wave
   and the ones you may not.
6. `docs/EVENT_SCHEMA.md` -- the ledger contract. Read before the first run.
7. `docs/RECONCILIATION.md` Part 2 -- the measured failure classes.
8. `.claude/skills/wave/SKILL.md` -- how a wave actually runs.
