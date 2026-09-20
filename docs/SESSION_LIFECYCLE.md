# SESSION_LIFECYCLE.md

The SOP for starting a session, closing a session, the startup questions, and
when a question leaves the crew and goes to the driving engineer.

The Maestro **is** the top-level session (WORKFLOW.md section 1), so "session
start" and "session close" are the moments the whole crew comes into and out of
existence. Everything durable lives on disk between sessions; these two
procedures are what make that true in practice instead of aspirationally. A
session that starts without grounding builds on a stale picture; a session that
ends without closing out orphans every run that was in flight — and an orphaned
run is indistinguishable from a run that never started.

---

## 1. Session start

In order. Each step exists because skipping it produced a measured failure.

1. **Read the root context documents.** The host's `CLAUDE.md` (or equivalent
   entry point), `RULES.md`, `FAILURE_PATTERNS.md`, `SHIP_CHECKLIST.md`,
   `BEST_PRACTICES.md` — whatever the adoption mapped them to (README adoption
   runbook). These are the standing rules; a session that has not read them
   will re-learn one the expensive way.
2. **Verify identity and authorization.** Confirm the version-control identity
   the host requires (per-invocation `git -c`, never `git config` — G1) and
   that the authenticated platform identity is the expected one. If it is
   anything else, **stop and surface it** — pushing under the wrong identity is
   not fixable after the fact.
3. **Start clean.** Run the host's pull-and-verify routine. A dirty or
   ahead-of-origin tree is not a safe base for a crew (WALL_STANDARDS
   section 5). If the tree is dirty with work a previous session left, that is
   startup question Q4 — do not stash it silently and do not build on it.
3b. **The drift pass (DEC-0020).** Before any dispatch: confirm the
   Architect's drift pass covered the platform docs, diagrams and
   instructions for the surfaces this session will touch — or run it
   now. Update, add or remove; a stale document kept is drift with a
   byline. A session that dispatches from stale documents has its
   builders building a different system that shares file names with
   this one.
4. **Sweep and diagnose the wall.** `wall run-once` then `wall doctor`. The
   integrity flags and the roster audit are the previous session's honest
   residue; read them before trusting any item's status.
5. **Reconcile orphans.** `.wall/registry/open_runs.json` holds the runs
   registered before dispatch — the file that survives a session restart so an
   in-flight run can still be identified. Any run with no terminal event is
   closed **honestly**: `stale`, with the evidence checked (did its commits
   land? did its PR merge?) — never back-filled as `done` from a guess, never
   deleted. Expired leases are released. A dead agent must not hold a path or
   read as busy.
6. **Read the waiting tab.** Answers the engineer left via `wall answer` since
   the last session unpark items — those resume first, because a human already
   paid for those answers.
7. **Verify the single PR slot.** If a previous session left an open PR on the
   designated branch, this session adopts it (drive it to done per the
   transplant procedure's tail) or asks — it never opens a second one beside
   it, and never pushes while that PR's checks are running.
8. **Vet the handoff against ground truth before acting on any of it.** The
   previous session's wave report and any handoff document are *claims*, not
   evidence — written by a session that could not see what happened after it
   ended, and sometimes stale before it was saved. Every claim that would change
   this session's behaviour is checked against the repository, CI and the merge
   log: does that branch still exist, did that PR merge, is that blocker still
   blocking, does that file still say what the report says it says. **Trust the
   repo over the doc**, and correct the doc where they disagree. A measured
   case: a session spent its opening hour working around a blocker the report
   described, which had been resolved by the merge immediately after the report
   was written.
9. **Survey the backlog** and answer the startup questions below. Only then
   dispatch.

## 2. Startup questions

The session answers these before the first dispatch. The rule for each: **if
config or the decision log answers it, it is not a question** — the engineer is
asked only what nothing on disk can answer. Every answer that comes from the
engineer is written down (a `DEC-NNNN` or a config edit), so the same question
is never asked twice.

| # | Question | Answered by | Escalate to the engineer when |
|---|---|---|---|
| Q1 | What is this wave's scope? | The engineer's instruction, or the backlog in priority order if the standing instruction says so | No standing instruction and no explicit scope. On a first wave, scope comes out of the product intake (`docs/PRODUCT_INTAKE.md`) |
| Q2 | What budget applies? | `.wall/config/wall.json` meters | Config missing or the engineer signalled a change |
| Q3 | Any `human_required` items still unanswered? | The waiting tab | Never assumed — an unanswered ask stays parked, period |
| Q4 | Did the last session leave in-flight state? | open_runs, leases, the open PR, dirty tree | The evidence is contradictory (e.g. commits exist that no run claims) |
| Q5 | What network mode do researchers run under? | `research.network` in config (default `none`) | A wave needs more network than the configured mode allows — widening it is always the engineer's call, never the session's |
| Q6 | Is the previous wave report's "next session must know" list actioned? | `docs/handoffs/wave-report.md` output from last close | An entry requires an engineer decision |

Batch the escalations: one message with every open startup question beats six
interruptions, and the wave can usually start on the items no question touches
while answers are pending.

## 3. Session close

A close is a procedure, not an exit. In order:

1. **Stop admitting work.** No new dispatches. Running units finish or are
   recorded honestly — a unit interrupted mid-build gets a terminal event with
   what actually happened (`stale` or `failed` with evidence), not an
   optimistic `done`.
2. **Verify every item's status against evidence** before it is left behind
   (G9, WORKFLOW section 8): an item claiming an open PR that the host says is
   merged is fixed *now*, not inherited by the next session as a mystery flag.
3. **Release what this session holds.** Leases released or left to TTL-expire
   with their runs closed; the roster updated so no agent this session spawned
   still reads `live`.
4. **Name unpushed work.** Any commits that exist only locally are listed with
   SHAs and their branch in the wave report. Silent local-only work is how a
   container reclaim or a machine sleep destroys a day — if it matters, push
   it to the designated branch or the telemetry branch before ending; if it
   deliberately stays local, say so and say why.
5. **Final sweep and export.** `wall run-once` so the wall the next reader
   opens reflects this session's last true state; ship the event shards
   (`wall ship`) so the ledger survives the machine.
6. **Write the wave report** (`docs/handoffs/wave-report.md`): what shipped
   with PR numbers, what is in flight and exactly where it stopped, findings
   with dispositions, budget actuals vs config, and the **"next session must
   know"** list — the parking instructions the next session's step 6 reads.
   The report is the handoff; anything only in this session's memory is lost
   by design, so the report is written as if the author will never be asked a
   follow-up.
   **The report supersedes and deletes its predecessor.** One current copy
   exists, at one path — the previous wave's report is replaced, not archived
   beside it under a dated name. Two reports that both look current is how a
   session reads the older one and acts on a picture that is two waves out of
   date; if something in the old report must survive, it is carried forward into
   the new one, which is also the moment it gets re-vetted (section 1, step 8).
   **Where the host has CI, the report itself is under a shape test** — sections
   present and ordered, open items a real table — and its **Open items section
   is the only to-do list**: if it is not there, it is not open.
7. **Every standing directive the engineer issued this session is written into
   the rules or the config, in the same working chunk it was issued.** A
   directive that exists only in the conversation is a bug: the session that
   heard it ends, and the next one re-learns the rule by breaking it. "Written
   down" means the binding surface — `RULES.md` (or the host's equivalent) for a
   rule, `.wall/config/wall.json` for a threshold, a `DEC-NNNN` for a ruling —
   never the wave report alone, which is a handoff and not an authority. Doing
   it at session close is too late; the rule is "same chunk", and this step is
   the audit that it happened.
8. **Escalations left open are surfaced, not abandoned.** Every unanswered
   `human_required` ask appears in the wave report's top section with what it
   blocks, so the engineer sees the queue without opening the wall.

## 4. Escalation to the driving engineer

The escalation ladder (WORKFLOW section 4) ends at **the human queue**:
Researcher → second pass → Architect → Adjudicator → engineer. Time-driven,
every hop written as `question_escalated`. But the ladder is for *answerable*
questions that happen to be hard. Some classes skip the ladder and go straight
to the engineer, because no agent has the authority to answer them at all:

| Class | Why no agent may answer |
|---|---|
| **Irreversible or outward-facing actions** — deleting shared state, publishing, force-pushing outside the safety proof, anything that leaves the machine | Reversibility is the property that makes act-first safe; where it is absent, authority is absent |
| **Permission and credential boundaries** — new access, wider network for researchers (Q5), a tool the host has gated | A crew that can widen its own permissions has no permissions |
| **Spend beyond the advisory budget** — the meters warn, the engineer decides (WALL_STANDARDS section 10) | Budgets are advisory precisely because the human owns the trade-off |
| **Policy conflicts between live decisions** — two `DEC-NNNN`s that contradict on values rather than facts | The Adjudicator ranks evidence; it cannot rank the engineer's priorities |
| **Scope changes** — a new arc, or a story whose criteria the design cannot ground | The engineer owns what gets built; the Architect owns how it is specified |
| **Security findings** — credentials in the tree, an injection path, data leaving a boundary | Surfaced immediately and verbatim; never "handled" quietly |

**How an escalation travels.** The asking agent (or the Maestro on its behalf)
emits `human_required` with the ask, the item it parks, and what the answer
unblocks. The ask appears on the wall's **waiting tab**. The engineer answers
with `wall answer <ask_id>`, which writes `human_answered`, records the ruling
as a `DEC-NNNN` (durable — the engineer's answer is a decision record, not a
chat message, so the next wave finds it in the decision-log search instead of
asking again), and signals the Maestro to unpark the item.

**Rules that keep escalation cheap in both directions:**

- **An escalation parks the item, never the wave.** The Maestro re-checks the
  parked item's scopes: work file-disjoint from the pending answer continues
  (the `partial` mechanics of WORKFLOW section 3).
- **Urgency is honest.** An ask that blocks the whole wave says so; an ask
  that can wait for the wave report waits for the wave report. Every ask
  marked urgent trains the engineer to read none of them.
- **The question reaching the engineer is a document, not a paraphrase**
  (G13): the finding-route form, with the ambiguity class, the options
  considered, each option's cost, and the crew's recommendation. The engineer
  rules; the crew does the staff work.
- **Never manufacture consent.** No answer is not an answer. An expired SLA on
  the human hop parks harder, it never defaults to "proceed" — and an agent
  claiming the engineer approved something must trace to a `human_answered`
  event or it did not happen.

## 5. Cross-references

- WORKFLOW.md sections 1, 3, 4, 8 — execution model, ambiguity, the ladder,
  verified status
- WALL_STANDARDS.md sections 5, 10 — clean start, budgets
- docs/ITEM_AUTHORING.md — the authoring side of questions and amendments
- docs/handoffs/wave-report.md — the close-out artifact
- docs/handoffs/finding-route.md — the escalation document
- docs/PRODUCT_INTAKE.md — the product-definition Q&A behind Q1
- docs/CAPACITY_REBALANCING.md — the mid-wave knobs and who turns them
- .claude/MAESTRO.md — the session manual this SOP slots into
