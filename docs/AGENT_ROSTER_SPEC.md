# AGENT_ROSTER_SPEC.md

Seven roles. What each owns, what it runs on, and where its authority stops.

Derived from `ORIGINAL_OUTLINE.md`, with two additions (Reviewer, Courier) and
several boundaries tightened where the original left them implicit.

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
| Authority | Fable 5.1 | Architect, Adjudicator | Deepest reasoning, lowest volume |
| Execution | Opus 5 | Maestro, Builder (complex) | Dispatch and the work itself |
| Verification | Sonnet 5 | Foreman, Reviewer, Researcher, Builder (mechanical) | Check and find out |

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
