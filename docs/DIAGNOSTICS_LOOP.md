# DIAGNOSTICS_LOOP.md

The closed loop from a running system's diagnostics to reviewed, designed,
tracked work — with no human in the loop except where a human is the point.
Four stages, each proven in production on the reference deployment before it
was written here: the machine ships evidence, freshness is enforced, an
automated review triages under a standing autonomy grant, and every finding
becomes a story carrying its evidence and solution design. A fifth section
closes the loop in the other direction: the owner-verification queue.

The transport is the kit's existing plumbing — the machine-wide timer, the
isolated telemetry branch, `doctor.json` (INSTALL.md, WALL_STANDARDS §2) —
this document adds the *contract* on top of it.

---

## 1. Stage one — ship, honestly

A script invoked by the existing machine-wide timer gathers the running
system's status surfaces and the WARN/ERROR log tail, **redacts to metrics
and states only** — never secrets, never user content, never raw payloads —
and ships the snapshot to the isolated telemetry branch through the isolated
index (the shard-shipping pattern, reused verbatim).

Two triggers, not one:

- **Heartbeat interval** — every sweep, unconditionally.
- **Event-driven on a NEW failure signature** — errors are normalized
  (timestamps, pids, ids, hex collapsed) so a recurring error is ONE
  signature; a signature not seen before ships immediately, debounced and
  rate-capped per hour so a storm cannot hammer the branch.

The one rule that cannot bend: **the shipper runs unconditionally**. A dead
application must not silence the channel that reports applications dying
(seeded class F-OBS-COUPLED). "Could not reach the subject" is shipped as
content, never expressed as silence.

## 2. Stage two — freshness is first-class

Every snapshot carries `generated_epoch` and `stale_after_s`. Readers
compute age before trusting anything; a reader-side check exits non-zero on
stale, and **an undated snapshot is stale by definition**. A scheduled CI
job (or the courier, where CI is absent) runs the check and maintains **one
idempotent alarm** — opened when stale, auto-closed on recovery, never
duplicated. The measured incidents behind this: a two-day-old snapshot read
as current, and a heartbeat gap that looked like a quiet system instead of a
dead timer (F-SCHED-001's rule, applied to the diagnostics feed itself).

## 3. Stage three — automated review, under a standing grant

Any session that observes the snapshot moved — the wave skill's ground
phase, the Foreman's session-start pass, or a dedicated scheduled session —
triages it under this standing autonomy grant:

1. **Read, then advise in one message**: what broke, the root-cause read,
   the fix plan. This is a heads-up, **not a permission request** — the
   grant is act-and-audit, and it sits above queued work and below an atomic
   unit mid-flight.
2. **"Not enough detail" never goes to the engineer.** A signal the
   snapshot should have carried and did not is itself a P1 story — extend
   the snapshot, then fix from the evidence. The diagnostics channel gets
   better every time it fails to answer a question.
3. **Diagnose-first routing** by a deterministic classifier over the
   normalized signature: a known signature maps to a written playbook —
   every playbook Architect- and Warden-signed before arming (section 7)
   (auto-repairable → repair now + audit entry); an unknown signature files
   a story (stage four) and — only where a spend gate is explicitly armed,
   default OFF — escalates to a live session. The classifier is deliberately
   conservative: a generic string like "timed out" stays *unclassified*
   rather than mis-filing an external blip as a system-down finding.
4. **The grant's ceiling is unchanged.** Irreversible or outward-facing
   repairs, credential changes, spend — the six engineer classes
   (SESSION_LIFECYCLE §4) apply inside this loop exactly as outside it.

## 4. Stage four — story creation, with the design attached

Every classified finding becomes a wall item through the normal authoring
path (ITEM_AUTHORING.md), and the story is not "look into X". It carries:

| Field | Content |
|---|---|
| **Evidence** | The normalized signature, the snapshot excerpt, its age, the occurrence count |
| **Root cause** | The chained five-whys read (a level naming a person or a moment of inattention is not a cause) |
| **Solution design** | The Researcher's output, routed the normal way: findings → research → design written to the wall — never code from the researcher |
| **Prevention** | The rule + regression test + checklist line that retires the class, authored in the same arc |

The ledger carries the chain: `diagnostic_finding` (signature, class, route)
→ `story_filed` (finding id → item id), so `wall trace` walks from a log
line on the box to the merged PR that closed it.

## 5. The owner-verification queue — the loop's other direction

Every shipped change that alters something the owner could see or feel
appends an item to an **append-only verification queue**: title, what
changed, and the exact steps to verify it. Rules:

- **Only the owner's explicit sign-off retires an item.** `verify_requested`
  is written at ship; `verified` only ever records a human answer.
- **Unverified items persist across releases.** They are not nagging; they
  are the honest backlog of "believed working, not yet seen working".
- **"Too small to list" is not the shipper's call.** The owner deletes
  noise; the shipper never pre-filters it.
- Feedback rides the same diagnostics channel back: "verified, but X" is a
  finding like any other and enters stage three.

## 6. Never ask the owner to run anything — except to LOOK

The automation channels exist so that every piece of machine-side work has a
carrier: the scheduled task (recurring), the one-time script runner (apply
once per machine, then never again), and the always-on loop (continuous).
Two rules make the discipline real:

1. **Any sentence of the form "run this on the machine" must name the
   channel that cannot carry it** — or the sentence is a defect in the plan,
   not a task for the owner. The one legitimate owner ask is *verification
   by looking* (section 5), because seeing is the point.
2. **Automate the result back, not just the work.** A channel that applies
   a fix but does not ship the outcome to the diagnostics branch has only
   changed the question from "please run this" to "did it work?". One-time
   scripts are trusted by exit code alone: **non-zero on every path where
   the work did not complete** — a success marker stamped on a
   dependency-absent skip path means the fix never applies anywhere
   (seeded class F-ONESHOT).

## 7. Sign-off — who is always in this loop

The loop is autonomous, not unsupervised. Three parties are involved in every
cycle, by standing rule (user direction), each at the point where their
authority means something — none of them as a per-event speed bump:

| Party | Always involved as |
|---|---|
| **Architect** | Every playbook (an auto-repair recipe the classifier may run) carries the Architect's written sign-off **before it is armed** — a repair recipe is a design. Every story filed from a finding gets its solution design authored or signed by the Architect before dispatch, per the normal authoring path. At wave close the Architect reviews the cycle's auto-repairs for design drift. |
| **Warden** | Signs every playbook beside the Architect (a repair that touches data, credentials or an external surface is exactly what the Warden exists to see **before** it runs). Owns the standing **redaction audit**: the snapshot's metrics-and-states-only rule is verified by the Warden at wave close, every wave. Triage of every filed finding includes the Warden's risk-tier read; an in-scope finding's story hits the normal Gate 1 before dispatch. |
| **Engineer** | Receives the advise-in-one-message heads-up per cycle (stage three), owns the verification queue (section 5), and holds the ceiling: the six escalation classes apply inside this loop exactly as outside. A playbook neither the Architect nor the Warden will sign goes to the engineer — it does not run unsigned. |

The asymmetry that keeps this fast: **repairs already covered by a signed
playbook run immediately** (the sign-off happened when the playbook was
written); only a *new* playbook, a *new* story design, or an in-scope finding
waits on a person — and what it waits on is written, so the wait is one
review, not a meeting.

## 8. Events

Three ledger events carry this loop (EVENT_SCHEMA.md §9):
`diagnostic_snapshot_shipped`, `diagnostic_finding`, `story_filed` — plus
the verification pair `verify_requested` / `verified`. All ride the normal
shard → courier → wall path; the WAITING tab shows unverified items beside
unanswered asks, because both are the same thing: the loop holding a slot
open for a human.

## 9. Cross-references

- INSTALL.md — the timer, the shipper, `doctor.json`
- WALL_STANDARDS.md §2 — the isolated-branch transport
- SESSION_LIFECYCLE.md §4 — the grant's ceiling
- ITEM_AUTHORING.md — the story path findings enter
- docs/TECH_EVALUATION.md — when a finding proposes replacing something
- CAPACITY_REBALANCING.md — diagnostics-driven signals feeding pace
