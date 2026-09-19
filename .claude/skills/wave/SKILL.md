---
name: wave
description: Run one wave of agent work with the wall-kit roster -- ground, scope, dispatch under leases, collect findings, route questions decision-log-first, integrate one PR at a time, and report COMPLETED / IN PROGRESS / NEW every cycle with a snapshot export. Use when the user asks to run a wave, work the backlog with agents, start or continue the crew, or dispatch builders. The invoking session IS the Maestro and keeps merge authority.
---

# /wave -- run a wave

The session that invokes this skill **is the Maestro** (`.claude/MAESTRO.md`).
Subagents cannot spawn subagents, so dispatch only works from here.

A wave is one pass of: ground, scope, dispatch, collect, route, integrate,
report, close. It ends when the backlog drains, the budget runs out, or the
human stops it -- not between units. Do not ask permission per unit.

---

## Phase 1 -- Ground

1. Read `.claude/MAESTRO.md`, `docs/WORKFLOW.md`, `docs/AGENT_ROSTER_SPEC.md`.
2. Run Courier once and read the snapshot. If the heartbeat is stale or Courier
   fails, **say so before reporting any number from the wall.**
3. Invoke the **Foreman** (SessionStart pass). Take its integrity flags as the
   first work of the wave: an item claiming an open PR the host says is merged
   is fixed before anything is dispatched (G9).
4. Confirm the hooks are installed (`.claude/hooks/README.md`). Without them the
   terminal ledger events are best-effort and `wall doctor` will read orphaned
   runs as live agents.
5. Check budget. Advisory, but recorded before dispatch, never after the overrun.

**Degrade path (G0a).** If the `Agent` tool is unavailable in this session you
cannot dispatch. Do not stall, and do not quietly become the Builder. Run
phases 1 and 2, vet every candidate's status against ground truth, fix drift,
export the snapshot, and hand back a **dispatch plan**: per unit the item key,
the acceptance criteria, the exact file surfaces shown to be disjoint, and the
merge order for the single PR slot. State plainly that you could not spawn and
why. A plan reported as a dispatch is the one failure this path exists to stop.

## Phase 2 -- Scope

For each candidate unit:

- **Path scope**, explicit. Compute disjointness across every unit you intend to
  run at once. Overlap is not dispatched; it is queued.
- **Task class** -- `mechanical` or `judgment`. Mechanical goes to a Sonnet
  Builder. All-Opus builders measured 400-720K tokens per unit.
- **Acceptance criteria**, each with a source. A criterion you cannot cite is an
  ambiguity you are handing down; resolve it now or dispatch it as a question.
- **Known worktree phantoms** (G4) -- list them, so three agents do not
  independently chase the same phantom failure.
- **Merge order** -- decided at scoping, because there is one PR slot.

## Phase 3 -- Dispatch

Per WORKFLOW section 2, in order: budget, leases, decisions attached, `run_start`
written and registered in `.wall/registry/open_runs.json`, then the brief.

**The brief is a document, not a paraphrase.** Fill
`docs/handoffs/dispatch-brief.md`. Five hand-written re-briefs drifted in one
wave, one of them mis-stating a file location (G13). The fields that proved
load-bearing: agent key, commit identity (G1), temp-file key (G2), file surface,
the out-of-scope ban, gates-last (G6), interpreter path (G4), and the report
shape.

## Phase 4 -- Collect

Read what comes back as **evidence, not status**:

- A reported "CI green" is checked against the check runs themselves. A builder's
  own draft-CI report was superseded twice in one wave by reading them directly.
- A reported gate is checked for **ordering**: run before the final edit, it
  measured a tree that no longer exists (G6).
- **Findings** are captured verbatim with their paths -- they are the cheapest
  thing a builder produces and the easiest to lose.
- A **`partial`** unit keeps its slot; a **`blocked`** unit releases it. You
  decide which, from the scopes, not from the builder's hint.

## Phase 5 -- Route questions, decision log first

```
search docs/decisions/   -- hit: answered, source=decision_log, cost ~0
   miss -> Researcher     -- returns findings, states its network mode
        -> Architect      -- returns the ruling
        -> Maestro writes DEC-NNNN and re-dispatches the Builder with it attached
```

Escalate on **time**, not on attempts, and write `question_escalated` with a
reason at every hop. A finding that contradicts a live decision goes to the
Adjudicator, never quietly into a second decision record.

Route each one with `docs/handoffs/finding-route.md`.

## Phase 6 -- Integrate, one PR at a time

One branch, one PR slot, N worktrees. Hand **one** transplant order at a time
(`docs/handoffs/transplant-order.md`) to an Integrator -- usually the unit's own
Builder wearing that hat.

The procedure is WORKFLOW section 9 and is followed literally: rebase onto moved
main, regenerate derived files by tooling (never hand-merge them), run the
path-filtered safety proof, re-check budgets, run the gates **last**, open the
PR as a **draft**, drive the review threads with one writer each (G8).

**You flip ready and you merge. Nobody else** (G12). Read the check runs
yourself: a draft-scoped check that reads green is not the full pyramid, and
that distinction caught two would-have-been-early merges.

A merge is followed immediately by its bookkeeping. Item state flips at merge
time, not at compaction time (G9).

## Phase 7 -- Report every cycle

After each dispatch, each completion, and each collection pass:

- **COMPLETED** -- merged PR numbers with one-line outcomes, items flipped,
  designs landed. Only merged or landed artifacts. Never a claim.
- **IN PROGRESS** -- each live agent, its unit, its stage, head-count vs caps.
- **NEW** -- findings surfaced, decisions written, items claimed, blockers for
  the human.

Then **export the snapshot** (G14): write the same three sections atomically and
run Courier so the wall updates on the transition. The owner watches it live and
course-corrected twice mid-wave from it; the timer is the fallback, not the
trigger.

## Phase 8 -- Close

- Every status **vetted against ground truth**, not against what an agent said.
- Every open question either answered, escalated with a reason, or on the human
  queue -- none silently dropped.
- Every finding either dispatched, filed as an item, or explicitly declined with
  a reason.
- Leases released; `run_end` present for every `run_start` (the SubagentStop
  hook writes these, but `wall doctor` is what proves it).
- Final report in the same three sections, plus what the next wave should start
  with.

---

## Caps

`{"builder": 4, "reviewer": 2, "researcher": 6}` by default -- researcher tracks
builders + 2. Foreman, Architect and Adjudicator are singletons enforced by the
registry. The Integrator is a hat a Builder wears, not a seat: it consumes the
PR slot, not a builder slot.

## The five things that cost the last wave something

1. An agent wrote `git config` and re-authored a sibling's commit (G1).
2. An unkeyed temp file was overwritten between write and use (G2).
3. A subagent scheduled its own check-in; it fired into the parent and the unit
   waited forever (G3).
4. Three agents independently chased the same worktree venv phantom (G4).
5. A gate ran before the final edit and shipped a stale generated file (G6).

Every one of them is a line in the dispatch brief. Fill the brief.
