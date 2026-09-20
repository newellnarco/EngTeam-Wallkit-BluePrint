# AGENT_ROSTER_SPEC.md

Eight roles. What each owns, what it runs on, and where its authority stops.

Derived from `ORIGINAL_OUTLINE.md`, with three additions (Reviewer, Courier,
Integrator) and several boundaries tightened where the original left them
implicit.

**The executable form is `.claude/`.** Each role below has a definition at
`.claude/agents/<role>.md` that a session invokes directly. Maestro has no
definition: it is the session itself, and its operating manual is
`.claude/MAESTRO.md`. A wave runs through `.claude/skills/wave/SKILL.md`.

---

## Standing constraints on every role

Measured in the first live wave (`RECONCILIATION.md` Part 2). Every agent
definition carries the ones it needs; they are listed here once so the roster
reads as one set of rules rather than seven copies.

| Lesson | Rule |
|---|---|
| **G1** | No agent writes `git config`. It is repo-global and re-authored a sibling's in-flight commit. Identity is per invocation: `git -c user.name=... -c user.email=...` or `GIT_AUTHOR_*` / `GIT_COMMITTER_*`. |
| **G2** | Every temp file an agent writes is keyed by its agent key. An unkeyed `commitmsg.txt` was overwritten between write and use. |
| **G3** | No agent schedules itself. A subagent's timer fires into the parent session; a builder once waited forever on its own wake-up. Only the Maestro schedules. |
| **G4** | Worktrees have no `.venv`. Interpreters are passed in, never resolved from the checkout. Seven phantom failures, chased three times independently. |
| **G6** | Gates run last, after the final edit. A worktree unit has no CI between its commit and transplant. |
| **G12** | Only the Maestro merges or flips a PR to ready. Everyone else reports green and stops. |
| **G0b** | Evidence over self-report, for every role. A builder's own CI claim was superseded twice by reading the check runs. |
| **G14** | Report in transitions, not narration. A bullet earns its place by recording a state change; prose about in-progress work buys nothing the wall does not already carry, and every reader pays for it every cycle. |
| **In-flight files** | No role commits or pushes another unit's working-tree files while that unit is live -- **including when a hook demands it**. That ships unvalidated mid-build work past the owning unit's own gate. Decline and say why, so the refusal is visible. |
| **G15** | Drift-first (DEC-0020, Patron direction 2026-09-20). Every role's first act on taking a surface is reading its documents of record; drift found there is reported to the Architect via the question queue (or fixed in-scope where the role owns the document), never silently built over. The Architect's drift PASS over docs, diagrams and instructions precedes dispatch of any wave or arc. |

---

## Identity

Keys are identity. Names are labels.

- **Key** — `<role3>_<6 hex>`, e.g. `bld_a41f09`, `arc_bb1740`. Permanent, never
  reused, referenced by every event, lease, trace, decision and item.
- **Name** — a first name. Unique among **live** agents repo-wide across all
  sessions. Released when the agent ends; reusable afterwards.
- Every machine surface uses the key. Every human surface shows the name.

Store: `.wall/registry/agents.md`, written by `tools/wall/agents.py`.

The allocator refuses a name that shares its first two letters with a live agent,
plus a hand-listed confusable set. With one name to identify by, "tell Theo to
stop" landing on Otto is a real failure. Uniqueness is a hard rule; distinctness
degrades gracefully when the pool is tight.

---

## Model tiering

| Tier | Model | Roles | Rationale |
|---|---|---|---|
| Authority | Fable 5.1 (or Opus 5 -- never lighter) | Architect, Adjudicator, Warden | Deepest reasoning, lowest volume |
| Execution | Opus 5 | Maestro, Builder (complex), Integrator | Dispatch and the work itself |
| Verification | Sonnet 5 | Foreman, Reviewer, Researcher, Builder (mechanical) | Check and find out |

The authority tier is written as `model: fable` in the definitions. On a host
that does not resolve that alias, set `model: opus` -- **never** a
verification-tier model, because the tier is the point.

The ledger records `model_requested` and `model_used` separately, because Fable
requests are occasionally routed to Opus 5 by safeguards.

**Builders dominate cost.** They do the most token-heavy work: file reads, edit
and test loops, retries. All-Opus builders are roughly 3–5× a tiered scheme.
Maestro tags each item with a task class at dispatch; mechanical work goes to
Sonnet, high-ambiguity or high-blast-radius work to Opus.

---

## Foreman — Sonnet 5

**One per repo, spanning all sessions.**

Owns observability. Never assigns work.

- Attestation, not transport: which agent should have reported and did not; which
  claimed status contradicts git or CI; which items look duplicated; which arc
  has been "in progress" for two days with no commits.
- Maintains the wall's accuracy, via Courier, and raises what Courier's validator
  flags.
- Owns the token, cost and GitHub-minute ledger and the rollups behind it.

**The mechanical half is script, not model.** Counting tokens, summing minutes,
rendering the grid and detecting staleness are deterministic. A Foreman that runs
as an LLM every two minutes across concurrent sessions outspends the builders
while producing no code. The model is invoked at SessionStart, at Stop, and when
Courier raises a flag — dozens of calls a day, not hundreds.

Singleton enforcement is a lock file with a heartbeat and a TTL. A session that
finds a stale lock takes it over.

---

## Maestro — Opus 5

**One per repo. This is the top-level Claude Code session, not a subagent.**
There is deliberately no `.claude/agents/maestro.md`; the operating manual is
`.claude/MAESTRO.md`. Confirmed the hard way (G0a): the first wave's spawned
orchestrator found the `Agent` tool disabled inside itself and could only hand a
dispatch plan back.

Owns process and dispatch.

- Assigns arcs, items and defects; holds the builder cap.
- Computes lease disjointness and decides `partial` vs `blocked` — the builder
  proposes, the dispatcher decides.
- Searches the decision log before spending a researcher.
- Routes questions: Builder → Researcher → Architect → back, since subagents
  cannot call siblings.
- Maintains standard operating procedures and the definition of done.
- Signs off on process. Never edits ledgers.

---

## Architect — Fable 5.1

**One per repo.**

Owns requirements, design and documentation.

- **First act of any wave or arc: the drift pass (DEC-0020).** Audit
  the platform docs, diagrams and instructions the coming work touches
  against what is actually built; update, add or REMOVE (a stale
  document kept is drift with a byline). Only then are stories written
  and briefs cut — builders build from current documents, and the
  Maestro sequences from current dependencies and order of operations,
  never from memory of them.
- Expert of record for enterprise, solution and product architecture.
- Reconciles documentation, diagrams and decisions; output lands in
  `docs/architecture/`.
- Answers escalated questions and writes the ruling.
- Signs off on requirements. Does not read code — that is the Reviewer.

A doc-only change by the Architect can silently invalidate work already built
against the old version. Changes under `docs/architecture/**` or
`docs/decisions/**` emit a `doc_impact` event naming affected arcs. No review, no
CI, no delay: one event write, and it surfaces on the wall.

---

## Adjudicator — Fable 5.1

**One per repo.**

Resolves disputes — but only after evidence is exhausted. See WORKFLOW.md §7 for
the tiebreak order. The Adjudicator is tier 4, below tests and written decisions,
because an AI arbitrating between two AIs with no ground truth ratifies whichever
was more confident.

Also receives conflicts where a new answer contradicts an existing `DEC-NNNN`,
and decides which supersedes.

---

## Warden — Fable 5.1 or Opus 5

**Exactly one per repo, enforced by the roster** (a second live claim is
refused; audit flags a violation). The security, compliance and
data-governance authority: holds
the guardrail corpus (regulatory frames, data-classification decisions,
standing security rules), signs off in-scope architecture BEFORE its stories
dispatch, rules on every declared data use (development and product), and
audits delivery at wave close. **Block without grant**: it can refuse
autonomously; widening any access or privilege remains the engineer's,
through the human queue with the Warden's evaluation attached. Overrulable
only by the engineer, in writing, with the objection preserved in the record.
Never edits source, never merges, never assigns work. Risk tiering keeps it a
gate, not a bottleneck: arcs declaring no data/auth/external surface get
act-and-audit spot checks instead of a mandatory gate. Role sheet:
`.claude/agents/warden.md`.

## Builder — Opus 5 or Sonnet 5

**Capped per repo by Maestro. Default 4.**

- Takes an item, maps every acceptance criterion to a source, and raises anything
  uncitable as a question before writing code.
- Declares dependent and independent path scopes when raising a question.
- Writes pass/fail tests against the requirements.
- Owns the item until Maestro says otherwise.
- Keeps `.wall/items/<id>.json` current.

A `blocked` builder releases its slot. A `partial` builder keeps it.

---

## Integrator -- Opus 5

**Not a seat. A hat a Builder wears when the PR slot frees.** *(Not in the
original outline; added from the first wave -- lesson G11.)*

Between "built in a worktree" and "merged" there is a distinct job: rebase onto
the moved `main`, resolve mechanical conflicts **by regenerating derived files
with their tooling**, run the path-filtered safety proof before any
force-with-lease, re-check budgets that other units moved, run the gates **last**,
author the draft PR, and drive its review threads.

The wave ran this five times by re-sending a long hand-written brief, and it
drifted every time -- once mis-stating where a file lived. So it is a written
role sheet (`.claude/agents/integrator.md`) plus an order form
(`docs/handoffs/transplant-order.md`), and the same agent that built the unit
assumes it. The procedure is WORKFLOW section 9.

Authority stops in exactly the same place as the Builder's: **reports green,
never merges, never flips ready** (G12). The Integrator consumes the single PR
slot, not a builder slot, which is why it is a hat and not a cap line.

---

## Reviewer — Sonnet 5

**Capped per repo. Default 2.** *(Not in the original outline.)*

Reads the diff **cold**, with no access to the builder's reasoning, and returns
only pass or fail-with-findings. Cannot edit source.

This role exists because the original design had builders writing their own
tests and declaring them passing, with sign-off from two parties who do not read
code. An agent that can both write the test and declare it green has no adversary.

---

## Researcher — Sonnet 5

**Capped at builders + 2.**

- Investigates questions Maestro routes to it; searches the repo, docs, and —
  subject to the permission gate below — external sources.
- Returns findings to Maestro, never directly to the requesting builder.
- Expands an existing `DEC-NNNN` rather than writing a contradicting one.

**Network access is gated.** The original outline has researchers searching
GitHub and the internet. Under a local-only operating preference this needs an
explicit allowlist, or researchers are scoped to the repo and local docs. Decide
this before the first run; it is listed in OPEN_QUESTIONS.md.

---

## Courier — script, no model

*(Not in the original outline.)*

Merges event shards, builds the snapshot, renders the wall, writes the heartbeat.
Entirely deterministic and listed on the agent grid as a non-LLM row showing runs
and last-run time with zero tokens.

It is a script rather than an agent on purpose: a model consolidating the ledger
could silently drop, reorder or paraphrase a record, and the audit trail is the
one thing that must be reproducible byte for byte.

---

## Caps

```json
{"role_limits": {"builder": 4, "reviewer": 2, "researcher": 6}}
```

Singletons — Foreman, Maestro, Architect, Adjudicator — are enforced by the
registry, not by the cap table. Researcher cap should track builders + 2; if the
builder cap moves, move it too.

**Integrator is absent from the cap table on purpose.** It is a hat a Builder
puts on, and the thing it consumes is the single PR slot, which is already
serialized. Giving it its own cap would imply two transplants can run at once;
they cannot.

Courier is a script and has no cap. It is listed on the agent grid as a non-LLM
row -- runs and last-run time, zero tokens -- because an invisible bookkeeper is
one whose failure is also invisible (G0c: it ran a whole wave as one Python file
pushing an isolated branch, zero model calls).
