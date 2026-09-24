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

Two extensions from the appliance shape, where an installed system runs
beside the repo:

- **Registration is not execution.** A scheduler reporting a task "ready"
  says nothing about whether the process is alive. Ask of every liveness
  check *"what would make this go red?"* — if the component dying is not on
  the list, the check checks something else. (Measured: a disabled logon
  task killed five daemons, telemetry went 7.4 days stale, and the check
  stayed green because the scheduler reports registration, not execution.)
- **An integration certifies itself from live signal, on a cadence.** A
  tool, feed, sensor or integration is not done when coded and green — only
  when demonstrably producing value on the live system, proven by a
  timestamped liveness certificate the system writes from its own telemetry,
  re-written on a cadence, never a human running a check. This extends
  §6.3's machine-verifier from one-shot-at-ship to standing. And one recruit
  reaches the frontline before the next starts: finish bringing an
  integration to live value before adopting another.

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
4. **The classifier consults the owner-decisions registry before filing.**
   A subject covered by a standing owner decision
   (`templates/OWNER_DECISIONS.md.template`) is off on purpose — the third
   state beside working and broken — so the finding is **converted to a
   report-with-evidence citing the entry id, never a story**, and never
   re-raised as a proactive issue or a footnote. Two limits keep this from
   becoming a suppression list: the entry must name both a reason and a
   lifting condition, and it is **never applied to an `unknown` reading** —
   a decision covers a known state of a subject, while unknown is a fact
   about the instrument. Once the lifting condition has fired, the entry no
   longer converts anything and the finding files normally.
5. **The grant's ceiling is unchanged.** Irreversible or outward-facing
   repairs, credential changes, spend — the six engineer classes
   (SESSION_LIFECYCLE §4) apply inside this loop exactly as outside it.

## 4. Stage four — story creation, with the design attached

Every classified finding becomes a wall item through the normal authoring
path (ITEM_AUTHORING.md), and the story is not "look into X". It carries:

| Field | Content |
|---|---|
| **Evidence** | The normalized signature, the snapshot excerpt, its age, the occurrence count |
| **Hypotheses** | Every candidate cause considered, the measurement that separates it from the others, and the verdict -- refuted ones stay on the record (`SKILLS_LIBRARY.md` section 1) |
| **Root cause** | The chained five-whys read (a level naming a person or a moment of inattention is not a cause) |
| **Solution design** | The Researcher's output, routed the normal way: findings → research → design written to the wall — never code from the researcher |
| **Prevention** | The rule + regression test + checklist line that retires the class, authored in the same arc |

The ledger carries the chain: `diagnostic_finding` (signature, class, route)
→ `story_filed` (finding id → item id), so `wall trace` walks from a log
line on the box to the merged PR that closed it.

**A finding is recorded on arrival — before reproducing, before fixing,
before replying.** A finding that exists only in a review thread disappears
when the pull request merges (one sat unanswered for days in the field
because the thread was the only place it existed). The intake record is
cheap: symptom, where seen, one line. Grouping comes second: findings are
grouped into a FAMILY by shared mechanism, not symptom, and a family
reaching three members is elevated to a guarded recurring class. The
three-tense split (WALL_STANDARDS §4) says where each record lives — and the
test-selection for a fix is chosen *from the known-issues list*, because a
selection made without it is a guess about what could be wrong made without
the list of what is.

**An alarm's text must be entailed by its measurement.** A monitoring
surface must not render a true observation as its unproven consequence —
"tunnel down" alarmed as "your traffic is exposed right now" while the
actual exposure probe, measured two lines below, was never consulted.
Severity and the alarmed condition are different axes: a finding can be
legitimately high and definitionally not the specific harm the sentence
claims. The check on every alarm text: name the measurement, and verify it
entails the sentence. And **an alert channel is armed by measured precision,
not by feature completion** — paging on findings the system is not yet
confident in trains the owner to ignore the alarm, which is worse than no
alarm; the arming condition is real work, recorded in the owner-decisions
register with its lifting condition.

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
Three rules make the discipline real:

1. **Any sentence of the form "run this on the machine" must name the
   channel that cannot carry it** — or the sentence is a defect in the plan,
   not a task for the owner. The one legitimate owner ask is *verification
   by looking* (section 5), because seeing is the point. The single
   exception (DEC-0034): **while no closed loop ships telemetry and logs
   from the environment back to the repository**, one hand-run diagnostic
   may be asked -- it names the missing loop, and building that loop is
   filed as a P1 item in the same breath. Once the loop exists, a
   diagnostic question is answered from it or the loop is extended; it is
   never handed to the owner.
2. **Automate the result back, not just the work.** A channel that applies
   a fix but does not ship the outcome to the diagnostics branch has only
   changed the question from "please run this" to "did it work?". One-time
   scripts are trusted by exit code alone: **non-zero on every path where
   the work did not complete** — a success marker stamped on a
   dependency-absent skip path means the fix never applies anywhere
   (seeded class F-ONESHOT).
3. **An ask shipped to the machine carries its own machine-verifier**, landed
   in the same change, so the result channel reports proof rather than hope —
   an ask the system cannot verify is not done, and "tell me when you did it"
   is not a verification.

Where a step genuinely must be run by a human on a machine (the
installed-system shapes force some), the command block is held to a written
standard, because the reader pastes the whole block:

- **Every block is headed by the exact shell/window and the privilege
  level** — privilege stated even when it is "none", because silence is an
  omission, not a default. An elevation-needing command run unelevated can
  answer quietly and wrongly ("Access is denied" as ordinary output).
- **The fence contains only pasteable commands.** No prose, no comments, no
  prompt characters — explanatory text inside the fence executes as garbage.
  One window per block; multi-window steps get labeled blocks and a note on
  which stays running.
- **Nothing executable is handed over unrun.** A command goes out only if it
  was actually run here, or with an explicit "I have not run this" in the
  same breath — the label is the accuracy, not an apology. Every path in an
  offered command is checked to exist first; a runbook example is never
  presented as a verified instruction, because docs drift and the code
  (`--help`, the entrypoint) is the authority. The tell is the phrasing:
  "probably" or "should be" means the next action is a check, not a send.
- **The standard is enforced mechanically** where the product ships operator
  instructions: a linter over the shipped instruction strings, wired into
  CI. (It found nine violations the day it was written in the field; the
  owner had pasted markdown into a shell twice in one session before that.)

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

The writers are commands, each refusing what this document forbids: `wall
finding` (normalizes the signature; an `unclassified` finding cannot be
`auto_repaired`), `wall story-filed --finding <event_id> --item <id>`, `wall
verify-request --item --what --steps`, and `wall verified --item --verdict
confirmed|confirmed_with_findings` (the owner's answer, on the `s_human`
shard like `wall answer`). The courier flags a finding routed `story_filed`
with no `story_filed` past `sla_minutes.story_filed` (`dropped_findings`) and
a verification waiting past `verify_horizon_days` (`verify_overdue`); the
open queue rides the snapshot as `verify_waiting`.

## 9. Cross-references

- INSTALL.md — the timer, the shipper, `doctor.json`
- WALL_STANDARDS.md §2 — the isolated-branch transport; §4 — the
  three-tense record split this loop's intake writes into
- templates/FAILURE_PATTERNS.md.template — where a three-member family
  graduates to
- SESSION_LIFECYCLE.md §4 — the grant's ceiling
- ITEM_AUTHORING.md — the story path findings enter
- docs/TECH_EVALUATION.md — when a finding proposes replacing something
- CAPACITY_REBALANCING.md — diagnostics-driven signals feeding pace
