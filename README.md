# wall kit

A standalone, dependency-free scaffold that drops into an empty repository - or
an existing one - and gives a Claude Code session everything a first agent wave
otherwise has to improvise: a role roster with written authority boundaries, an
event ledger with integrity checking, a live wall, a closed-loop timer, dispatch
and handoff and transplant procedures with the measured failure classes already
encoded, and the context documents - rules, failure registry, ship checklist,
decision log - that make the next wave start where the last one ended.

Everything here is stdlib Python, plain CSS and plain HTML. No dependencies, no
network calls, no build step.

The design was originally done blind, against no real tree. It has since been
reconciled against a production deployment and a seven-hour live agent wave;
`docs/RECONCILIATION.md` is that record, and it is **binding** where it
disagrees with anything else in this repository.

---

## Try it in 30 seconds

```bash
cd sample
python3 make_sample.py                  # writes fake event shards
python3 ../tools/wall/courier.py --repo .
open .wall/derived/wall.html            # or double-click it
```

The sample deliberately contains four integrity problems, all real conditions
the system has to survive:

- A **sequence gap** - a record was deleted from one shard. A lost write shows
  as a hole rather than vanishing.
- Two **orphaned runs** past deadline. In-flight runs correctly do not count, or
  every working builder would light up the panel.
- **Nadia reads `stale`, not `working`**, though her last event claims a run in
  progress. A blown deadline reclassifies the agent regardless of what it said
  about itself. Evidence over self-report, made mechanical.
- **Coretta shows `claude-opus-5 -> routed`** - she requested one model and
  safeguards sent her to another. The ledger records what ran, so per-model
  costs stay honest.

---

## The five ideas everything else follows from

**1. Agents don't persist; state does.** Claude Code subagents are single-shot.
Nothing polls, nothing watches. So persistence lives on disk and short agent
invocations fire off hooks and a timer. This is why the courier is a script
(DEC-0001), why Maestro is the top-level session rather than a subagent
(DEC-0002), and why the Foreman's singleton is a lock file rather than a
process. The live wave added a corollary: **subagents do not schedule either** -
a check-in registered by a subagent fires into the parent, so the agent that
scheduled it waits forever while its wake-up wakes somebody else.

**2. Bookkeeping is code, not cognition.** Counting tokens, merging shards and
rendering a grid are deterministic. A foreman running as a model every two
minutes outspends the builders while producing no code. Models are invoked for
judgment: contradiction triage, stale-claim narration, anomaly. Measured: a
status stream ran all night as one Python file, zero model calls.

**3. Evidence outranks self-report.** Status comes from the repository, the
tests and the checks, not from agents describing themselves (DEC-0011). A
`run_start` with no terminal event past its deadline reclassifies the agent as
`stale`. Item files are a materialized view of the event log, so `diff-state`
catches anything written out of band. In the live wave a builder's own report of
its checks was superseded twice by reading the check runs directly.

**4. Keys are identity; names are labels.** `bld_a41f09` is permanent and
appears in every event. "Desmond" is a reusable display name, unique among live
agents repo-wide (DEC-0003, DEC-0009). Reuse is safe *because* nothing
downstream depends on the name. The wave extended this to the working tree
itself: repository-level git configuration and unkeyed temp filenames are shared
mutable state, so identity is set per invocation and every temp file is keyed by
agent key.

**5. The ledger must be reproducible.** Merge is idempotent on `event_id` and
totally ordered on `(ts, session_id, seq)`, so a full rebuild from shards yields
a byte-identical ledger to an incremental run. Verified. That property is what
makes the audit trail trustworthy, and it is why the courier is not an agent -
and why shards ship to an isolated branch rather than riding pull requests
(DEC-0004).

---

## The empty-repo runbook

Start to first wave. Each step is a real command or a real decision; none of it
assumes anything already exists.

**1. Copy the kit in.** Drop `tools/wall/`, `docs/`, `frontend/theme/` and
`.gitignore` into the new repository. Nothing is installed and nothing runs yet;
these are files.

**2. Copy the context documents to the root and fill them.** From
`templates/`, copy and rename:

| Template | Becomes | What it is |
|---|---|---|
| `templates/CLAUDE.md.template` | `CLAUDE.md` | Entry point: what the project is, current state, doc index, pointer to the rules. |
| `templates/RULES.md.template` | `RULES.md` | The binding rules. Part 1 is yours to write; Part 2 ships as-is. |
| `templates/FAILURE_PATTERNS.md.template` | `FAILURE_PATTERNS.md` | Append-only registry of bug classes, seeded with seven general ones. |
| `templates/SHIP_CHECKLIST.md.template` | `SHIP_CHECKLIST.md` | The pre-ship gate, including gates-run-last and the budget check. |
| `templates/BEST_PRACTICES.md.template` | `BEST_PRACTICES.md` | The coding standards the whole roster and any hosted reviewers judge against. |
| `templates/BUDGETED_DOCS.md.template` | `BUDGETED_DOCS.md` | Which documents feed model prompts, their budgets, and measured headroom. |

Replace every `<PLACEHOLDER>` and delete the leading comment block from each.
The only one that needs real thought today is `RULES.md` Part 1 - the hard
rules. Everything else can start thin and grow.

**3. Initialize and make the first commit.** `git init`, then commit the kit and
the filled templates together. This commit is the base every agent rebases onto,
so it should already contain the rules they are supposed to follow.

**4. Claim the roster.** Agents need keys before they have anything to write
into an event.

```bash
python3 tools/wall/wall.py agents claim --role builder --session <sid>
python3 tools/wall/wall.py agents            # see the roster
python3 tools/wall/wall.py agents audit      # duplicate keys, name collisions
```

**Maestro is not claimed.** It is the session you are already talking to, not a
row in the roster (DEC-0002). If you find yourself allocating a key for the
orchestrator, something has gone wrong - most likely an attempt to spawn one,
which the harness will refuse anyway.

**5. Install the timer, with consent.** One scheduled task per machine, not one
per repository (DEC-0010). The session-start hook **detects only**; it never
writes a system task. When something is missing it surfaces the exact command
and waits for you.

```bash
python3 tools/wall/wall.py install       # explicit say-so; prints what it wrote
python3 tools/wall/wall.py register      # adds this repo; no privileges needed
python3 tools/wall/wall.py verify        # task alive? heartbeat fresh?
```

After the first yes on a machine, adding another repository is a plain file
write.

The platform adapters are real: a scheduled task on Windows, a launch agent on
macOS, a user timer on Linux. `install` prints the schedule it is about to
create and waits for you before creating it, and `verify` reports what the
platform says is actually installed rather than what the kit believes.

`run-once` remains the universal entry point - it is what the timer calls, and
it can be driven by hand, from a git hook, or from CI without any timer at all:

```bash
python3 tools/wall/wall.py run-once
```

**6. Open the wall.** Serve it locally and leave it open.

```bash
python3 tools/wall/wall.py doctor        # heartbeat, integrity flags, roster
open .wall/derived/wall.html
```

Two properties are not optional if you serve it yourself: bind `127.0.0.1`
explicitly, and send no-cache headers on the polled JSON. A wall showing a
cached snapshot is worse than no wall, because it is confidently wrong. Check
the `generated_at` stamp before believing anything on the page.

**7. Run the first wave.** With the roster claimed and the wall live, invoke the
`/wave` skill in the session. Maestro surveys the items, vets them, dispatches
against **disjoint file surfaces**, and integrates through one pull-request slot
in a set merge order.

Expect the first wave to teach you something the kit did not know. When it does,
the response is a `FAILURE_PATTERNS.md` entry plus the matching
`SHIP_CHECKLIST.md` item - in the same change. That pairing is the whole
mechanism by which this gets better.

---

## The existing-repo adoption runbook

A project that already has its own context documents does **not** copy the
templates over them. Duplicating a rule is worse than not having it: two copies
drift, and the next agent reads whichever it found first. The job here is to
**map**, and to add only what is genuinely missing.

**1. Inventory what exists - by function, not by filename.** Every mature
repository has grown some of these under names of its own. Find them:

| Function | Common names | What the kit expects it to do |
|---|---|---|
| Entry point | `CLAUDE.md`, `AGENTS.md`, `CONTRIBUTING.md`, the README | Orient a session: what this is, where it stands, where the rules are |
| Standing rules | `RULES.md`, `STANDING_RULES.md`, a "conventions" doc | Bind behaviour; change only by the owner, in writing |
| Failure registry | `KNOWN_FAILURE_PATTERNS.md`, a postmortem folder | Name bug classes already paid for, each with a check |
| Ship checklist | `SHIP_CHECKLIST.md`, a release runbook, a PR template | Gate a change before it ships |
| Coding standards | `BEST_PRACTICES.md`, a style guide, a reviewer config | One shared body of criteria every reviewer judges against |
| Decision log | `docs/decisions/`, ADRs, a decisions page | One record per ruling, superseded rather than rewritten |
| Prompt budgets | usually nothing | Declare and measure what feeds model prompts |

**2. Map, do not duplicate.** For each file in `templates/`, if the project
already has the equivalent, write a **stub at the kit's expected location** that
points at the real document and says what that document must additionally carry:

```markdown
<!-- Pointer, not a document. -->
# RULES.md
This project's standing rules live at `docs/STANDING_RULES.md`.

Kit rules that document must carry, and where they are in it:
- Identity is per-invocation; agents never write repository-level git config. [section N]
- Merge authority is the coordinator's; builders report green and stop. [section N]
- Gates run last, after the final edit. [section N]
```

Three rules are non-negotiable on adoption, because each one exists to stop a
measured corruption rather than to express a preference: **per-invocation
identity** (a shared configuration write lands on a sibling's commit),
**coordinator merge authority** (a green check is not necessarily the gating
check), and **gates last** (a gate run before the final edit proves nothing).
If the host's documents do not carry them, adding them there is the first
change - not a second rulebook.

Only where nothing exists do you copy the template and fill it. A project with
no failure registry should get `FAILURE_PATTERNS.md` on day one; the seven
seeded classes apply to any agent crew.

**3. Install the machinery alongside.** `.wall/` and `tools/wall/` are new
directories and collide with nothing. The agent roster in `.claude/` is the one
place that can collide: **merge by adding files, never by overwriting**. If a
role name already exists in the host, the project decides which definition wins
and records that as a decision in `docs/decisions/` - both because it is a
ruling somebody will otherwise re-litigate, and because a silently replaced role
sheet changes the behaviour of every future run.

**4. Register and install, consent-gated.** Exactly as the empty-repo path:
`wall register` adds the repository to the machine registry and needs no
privileges; `wall install` runs on explicit say-so and prints what it wrote. If
the host already serves a wall or dashboard of its own, register the kit's files
with that server rather than standing up a second one.

**5. Shake it down on one small item.** Claim the roster, then run `/wave`
scoped to a **single low-blast-radius item**. The point is not throughput; it is
to find out which of your assumptions the host repository does not share -
interpreter resolution, the name of the gating check, where derived files come
from - while only one unit is exposed to the answer. The findings from that one
item usually belong in the host's rules appendix as environment seams.

### Adoption checklist

| Exists? | Action |
|---|---|
| Entry-point doc | Add a "mandatory reading" block pointing at the rules, failure registry and checklist. Do not replace the doc. |
| Standing rules | Verify the three non-negotiables are present; add the missing ones **there**. Stub `RULES.md` as a pointer. |
| Failure registry | Keep it; add any of the seven seeded classes that can happen here, in its existing format. |
| Ship checklist | Keep it; ensure gates-run-last and the budget check are items in it. |
| Coding standards | Keep it, and check it against the seeded honesty rules - a standards file that lets a surface report a state it did not establish is missing the class these exist to stop. Add the missing rules **there**; register it in the budget table. |
| Decision log | Keep it; adopt the front-matter contract so the contradiction check can read it. |
| Prompt budgets | Almost certainly missing. Copy `templates/BUDGETED_DOCS.md.template` and register every document a tool loads into a prompt. |
| `.claude/` roster | Merge by adding files. A name collision is a decision, recorded as one. |
| None of the above | Follow the empty-repo runbook from step 2. |

MAX3 is the reference adoption: an existing repository with its own rules,
registry and checklist, where the kit's job was mapping and filling gaps rather
than installing a second set of standards.

---

## Status

Capability by design. The kit is built in parallel by several units, so this
table describes what each part is *for*, not what is finished this hour -
**see `tools/wall/` and run `wall doctor` for live status**. Where a command
is not built yet it says so and exits distinctly, printing what it would have
needed; that is a stub by design rather than a bug, and `wall --help` is the
authority on which commands are in that state today.

| Area | Purpose | Notes |
|---|---|---|
| Consolidation | Merge shards, order totally, render the wall, write a heartbeat | Reproducibility is verified by test, not asserted |
| Roster | Key and name allocation, audit, release | Keys permanent; names reusable when released |
| Classification | Route a changeset from its file set alone | Never agent-asserted; deny beats allow |
| Wall and theme | Static page, local server, tokens with light and dark verified to contrast standards | No build step |
| Install adapters | One machine-wide timer per platform - scheduled task, launch agent, user timer | Consent-gated: the schedule is printed before it is created |
| Questions and escalation | Raise, route, answer, record as a decision | Blocking work stops; non-blocking work continues |
| Integration | Rebase, regenerate derived files, prove, gate, open the pull request | The role sheet exists so the procedure stops being re-typed |
| Context templates | The five root documents a new project starts from | `templates/`, this repository |
| Decision log | One file per ruling, superseded rather than rewritten | `docs/decisions/` |

---

## Layout

```
docs/
  RECONCILIATION.md      BINDING - the 16 questions answered, the wave's lessons
  WALL_STANDARDS.md      folder layout, git boundaries, reference-deployment mapping
  AGENT_ROSTER_SPEC.md   the roles, models, caps, authority
  EVENT_SCHEMA.md        the contract - read this before the first real run
  WORKFLOW.md            execution model, dispatch, ambiguity, escalation, integration
  LOGGING_AND_AUDIT.md   three planes, per-run artifacts, trace commands
  FAST_TRACK.md          doc-only routing
  INSTALL.md             machine-wide timer, serving, platform specifics
  OPEN_QUESTIONS.md      settled decisions, and whatever is open now
  ORIGINAL_OUTLINE.md    the source outline, unedited
  decisions/             DEC-NNNN.md, one per ruling, plus index.md
  diagrams/              components, one item's journey, the closed loop
  handoffs/              dispatch brief, finding routing, transplant order, wave report

templates/               the five root context documents, with placeholders
tools/wall/              courier, roster, CLI, install adapters, renderer
frontend/theme/          tokens, primitives, preview
sample/make_sample.py    fixture generator, zero model calls
tests/                   scaffolding and integrity tests
```

---

## Reference deployment

The kit was reconciled against MAX3, a local-first application that ships
through a single-pull-request pipeline. That deployment is where every measured
number in `docs/RECONCILIATION.md` comes from. The mapping is
`docs/WALL_STANDARDS.md`; in short:

- **`tools/` is shipped**, because the deployment *is* a clone of the
  repository. Anything placed in `tools/wall/` is live on the box one automatic
  pull after merge.
- **Integrity is a generated manifest**, derived from the tracked file list and
  auto-synced per commit - so "does this file belong in the ledger" is not a
  decision anyone makes any more.
- **Work ships as named arcs, not numbered drops.** The kit's shipping event
  carries the merged pull-request number.
- **CI scoping belongs to the host repository.** It already routes by change
  class and by draft state; the kit defers to it rather than adding path filters
  of its own.
- **Event shards never ride a pull request.** They ship to an isolated branch,
  the pattern that deployment was already running in production.

Your repository will differ. The mapping document is the shape of the questions
to answer, not a claim about your tree.
