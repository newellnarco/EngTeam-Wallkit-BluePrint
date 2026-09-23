# WALL_STANDARDS.md

How the agent workforce and the wall fit into an existing repository's
conventions, using the reference deployment as the worked example.

This document is a mapping, not a new system. Where the host repository already
has a rule, the wall adopts it. Where the wall needs something the host does not
have, this says so explicitly and explains why it is not folded into an existing
mechanism.

**Status: verified.** Everything here was reconstructed blind and then checked
against the real tree on 2026-09-19. The *(inferred)* markers are gone because
the inferences were resolved - several of them against what this document
originally said. `docs/RECONCILIATION.md` Part 1 is the record and is binding
where the two disagree.

---

## 1. Folder layout

The wall adds one top-level directory. Everything else uses existing homes.

```
.wall/                          NEW - agent state, one directory, repo root
  config/wall.json              budget meters, role caps, thresholds
  registry/agents.md            key -> name roster (markdown, hand-editable)
  registry/leases.json          file-scope leases, prevents concurrent edits
  events/<YYYY-MM-DD>/<sid>.jsonl   append-only, sharded per session, GITIGNORED
  items/<item_id>.json          one file per arc / story / bug
  derived/                      GITIGNORED - regenerated, never merged
    wall.html  wall.json  ledger.jsonl  heartbeat.json
  logs/                         GITIGNORED - trace, 14-day TTL
  runs/<run_id>/                GITIGNORED - prompts, diffs, tool calls, 7-day TTL

tools/wall/                     NEW - wall tooling, joins existing tools/
  courier.py  agents.py  wall.py  install/

templates/                      NEW - root context documents for a new project
docs/decisions/                 NEW - one file per decision + index.md
docs/diagrams/                  NEW - component, sequence and loop diagrams
docs/architecture/              EXISTING - the Architect's output lands here
backend/tests/system/           EXISTING - the wall integrity test joins its siblings
```

`tools/wall/` rather than a product package because this is repository tooling,
not product code.

**Verified, and it cuts the other way from the original note.** In the reference
deployment `tools/` **is** shipped: the deployment is a clone of the repository,
hard-reset to the default branch by its own pull script, and the box runs
scripts directly out of the tree. So `tools/wall/` is the right home *and*
anything placed there is live on the machine one automatic pull after merge.
Plan accordingly: wall tooling is production code on that box, not a developer
convenience.

**Where the integrity test lands.** One root package manifest with the source
under a single package directory means the wall's system test sits in
`backend/tests/system/` beside the other system-tier tests, and runs in the same
job. Check your host's layout; the rule is "beside its siblings", not the
literal path.

---

## 2. What goes in version control

| Path | Committed | Covered by the integrity manifest | Why |
|---|---|---|---|
| `.wall/config/**` | yes | automatically | Durable, hand-edited, drift is a real bug |
| `.wall/registry/agents.md` | yes | automatically | Roster is a document; a surprise diff matters |
| `.wall/registry/leases.json` | yes | automatically | Tracked file, so it is covered; see below |
| `.wall/registry/open_runs.json` | yes | automatically | High-churn dispatch state, but it **must survive a session restart** - see below |
| `.wall/items/**` | yes | automatically | The ledger reconstructs them, but a diff is useful |
| `.wall/events/**` | **no** | n/a | Ships to an isolated branch instead - see below |
| `.wall/derived/**` | **no** | n/a | Reproducible output; committing it conflicts every sweep |
| `.wall/logs/`, `.wall/runs/` | **no** | n/a | May contain scrubbed-but-sensitive prompt text |

**The "in the ledger?" question no longer exists.** The reference deployment
retired its hand-maintained integrity ledger and collapsed it into a manifest
**derived from the tracked file list**, auto-synced by a pre-commit hook and
checked by a system test. Every tracked file is covered automatically and the
manifest regenerates per commit, so nobody decides whether a file "belongs" -
the question that took up two of the kit's original open items dissolved.

The consequence for high-churn tracked files like `leases.json` is that they are
covered but harmless: the manifest regenerates with the commit that changed
them. Manifest drift only fails the gate when a file changed **without** the
manifest being regenerated, which is exactly the condition worth failing on.

**`open_runs.json` is the same class, and is deliberately not gitignored.** It
holds the runs the Maestro registered before dispatch, and the session hooks
read it to resolve which run a record belongs to. It churns like `leases.json` -
which is an argument for ignoring it, and the argument loses. The file is what
lets a dispatched run be identified **after a session restart**; ignoring it
would orphan every run that was in flight when the session ended, and an
orphaned run is indistinguishable from a run that never started. Same treatment
as `leases.json`: committed, covered automatically by the derived manifest, and
not worth a rule of its own.

The line between the two cases is worth stating, because it is the line for
anything added later: **`.wall/events/` and `.wall/derived/` are reconstructible
or shipped elsewhere; `.wall/registry/` is the state that identifies things.**
Churn decides nothing on its own - what decides is whether losing the file
loses information that nothing else holds.

**Event shards are gitignored and ship to an isolated branch.** This reverses
the kit's original design and it is the most important correction in this
document. A repository that ships through a one-pull-request-at-a-time pipeline
cannot carry high-churn shards on the development branch: they would ride every
pull request and conflict constantly - the same class of pain that forced the
reference deployment to invent per-change fragment files for its board state.

Instead the courier ships snapshots to a dedicated telemetry branch using an
isolated index, so the working tree and the current index are never touched.
Durability, reproducibility and isolation all hold, and no pull request ever
carries a shard. The pattern was already running in production before the kit
adopted it. Full reasoning: `docs/decisions/DEC-0004.md`.

Add to `.gitignore`:

```
.wall/derived/
.wall/events/
.wall/logs/
.wall/runs/
.wall/registry/*.lock
```

---

## 3. Fast-track routing

**This is not new.** Most repositories already classify changed files into
documentation and source buckets somewhere - in a script, in a skill, in
somebody's head. Fast-track promotes that rule into `.wall/config/wall.json` so
the courier, CI and the agents read one definition instead of three copies
drifting apart.

```json
{
  "fast_track": {
    "allow": ["**/*.md", "docs/**/*.docx", "MANIFEST.sha256"],
    "deny":  ["frontend/src/**", "backend/**/*.py", "**/*.bat", "**/*.ps1",
              ".github/workflows/**", "tools/**", ".wall/config/**",
              "**/AGENTS.md", "**/CLAUDE.md"]
  }
}
```

Deny beats allow, always. Four entries are worth defending:

- `.github/workflows/**` - a builder editing CI to turn its own tests green is
  the classic escape hatch. It is code.
- `**/AGENTS.md`, `**/CLAUDE.md` - they are `.md`, so the glob would fast-track
  them, but they change the behaviour of every future agent. `AGENTS.md` is the
  master and `CLAUDE.md` its generated copy (docs/CONTEXT_FILES.md); both are
  code, and both get full review.
- `tools/**` - wall tooling can corrupt the ledger, and in this deployment it is
  shipped. Not a doc.
- Every document a generator or prompt-builder consumes - an edit there
  changes a generated artifact and can fail the build (FAST_TRACK.md; every
  generator-source row of the budget register belongs here).

Mixed changesets split rather than get an exception.

**CI: defer to the host repository's scoping.** The kit originally specified
`paths-ignore` plus a no-op companion workflow reporting the same check name.
That design is **superseded**. The reference deployment does not use
`paths-ignore` at all: it detects documentation-only changes in a job, scopes
test tiers by draft state through a tested helper, uses static literal job names,
and gates the merge on an attestation job whose conclusion is the real required
check. That mechanism already achieves zero-wasted-minutes routing, and it got
there by surviving five recurrences of one failure class - a skipped job whose
name was computed from an expression, which a merge gate then could not match.

So: the *classification* logic here stays, because it is how agent work is
routed. The *CI plumbing* is the host repository's, and the kit does not add
path filters beside it. If your host has no scoping yet, build it there; do not
build a second one in the wall.

Fast-track's destination is a pull request, never the default branch
(`docs/decisions/DEC-0005.md`).

---

## 4. Work items and shipping

The reference deployment once shipped in numbered drops; since mid-2026 it ships
as **named pull-request arcs** tracked on a board, squash-merged one at a time.
The kit follows the same axis split:

- An **arc** is a theme of work. It may span many pull requests.
- An **item** - arc, story or bug - is what the wall tracks.
- Every item records the **merged pull-request number** once it lands. That is
  the only join needed, and the shipping event carries it.

An arc may close **without** a release of any kind. Nothing in the kit requires
a shipping ceremony to close an item; if your host has a release protocol, it
fires on its own trigger, and the Foreman checks that it did rather than
replacing it.

Item ids stay human-typeable: `ARC-01`, `ST-104`, `BG-021`.

Four lifecycle rules keep an item's history readable after the fact:

- **Bugs only move UP the lanes.** A bug that was admitted is worked, fixed or
  explicitly closed with a reason - it is never parked back into the backlog to
  make a board look calm. A defect demoted to "someday" is a defect nobody
  decided about, and the decision is the only artifact worth having.
- **An item flips to in-progress the moment work starts, with its pull-request
  number attached.** Not when the first commit lands, not at review. An item
  that reads as unclaimed while an agent is inside it is how two units pick up
  the same work, and the pull-request number is what makes the claim checkable
  against the host.
- **The FIRST pull-request number recorded on an item is permanent.** Later
  pull requests are appended; the first one is never overwritten by the one that
  happened to merge. It is the anchor that makes the item's history
  reconstructible, and an overwritten first number silently deletes everything
  that happened before the rewrite.
- **Shipped status is DERIVED from the merge log, never asserted.** An agent
  saying a thing shipped is a claim; the host saying the pull request merged is
  evidence. The courier computes the flip from the merge, which is also why the
  integrity flag below can exist at all.

**The shipping event fires at merge, not at bookkeeping time.** A merge that
outruns its own bookkeeping leaves the wall claiming an open pull request that
GitHub says is merged - and in the reference deployment the resulting stale
state produced a red lint that the *next, unrelated* pull request inherited.
The courier treats "item claims an open pull request that is merged or closed"
as an integrity flag.

**Bookkeeping rides the work's own commit, never a follow-up push.** Status
fragments, ledger entries and board flips go into the FIRST commit of a
change, before the first push; a late one batches with the next genuine fix
push. A bookkeeping-only push moves the pull-request head, which kills any
running review and re-spends the meter — a measured quota exhaustion in the
field traced largely to status fragments pushed as separate follow-up
commits.

**A close-out written inside the change that carries it is conditional, by
construction.** An entry riding the very pull request it describes cannot
state the post-merge state truthfully — the merge has not happened and the
commit it would name does not exist — and care does not fix it; the sentence
form does: *"pull request #N carries this entry, and when it lands, X is
true."* That is true while the change is open and true after it lands, which
no flat claim about either state can be. The flat "nothing in flight" is
written only by a later session that independently confirmed every idle
condition (mainline clean, no CI running, no review pending, no pull request
open) — for that session it is a fact, not a forecast. Two corollaries: a
correct conditional about this pull request says nothing about the items
beside it in the same section, and "the pull request open for this branch"
is not a referent — it never becomes false or checkable; name the number.
(A sibling deployment's in-flight tracker was wrong six times in six
distinct ways before this form was adopted, the last caught by an external
reviewer seconds before merge.)

**Three records, three tenses.** What is happening now (the wall / in-flight
tracker), what is found but not yet worked (the known-issues intake,
DIAGNOSTICS_LOOP), and what is fixed and guarded (the failure registry) are
different tenses of the same story and live in different surfaces on
purpose. A finding parked in the wrong tense — a defect living only in a
review thread, a fixed class still listed as open — is invisible to exactly
the reader who needs it.

---

## 5. Branches, leases and shared state

Branch convention is the host's, unchanged. Every change rides a pull request.

**Cooperation, with serialized merges (DEC-0016).** Multiple builders
cooperate on concurrent open pull requests when their leased surfaces are
disjoint — the one-open-PR limit is retired as a general rule. What remains
serialized: never push to a branch whose checks are still running (the push
cancels the run and restarts the meter — measured: eleven cancelled runs
across seventy-seven minutes on one pull request), and merges go through the
coordinator one at a time with the next PR rebasing first. A host whose
standing rules mandate a single designated branch runs single-slot mode, and
which mode a repo runs is recorded as a decision.

**Leases (the invariant in every topology - DEC-0015).** Worktree isolation
is recommended for any agent that writes version control, and mandated where
the host's standing rules say so; the lease check below applies unchanged
either way. Subagents inside one session share a working tree, so two builders
editing at once corrupts it. Maestro assigns each item a declared path scope and
writes a lease; it refuses to dispatch a second builder whose scope overlaps.
Leases carry a TTL so a dead agent does not hold a path forever. Separate
working copies go underneath the same lease check; the check does not change.

**Shared mutable state that leases do not cover.** Leases protect *files*. Two
other surfaces are shared and bit the reference deployment's first wave:

- **Version-control identity.** Repository-level configuration is global. One
  agent writing `git config user.*` changed a sibling's in-flight commit
  authorship. Agents never write it; identity is set per invocation with
  `git -c user.name=... -c user.email=...` or the `GIT_AUTHOR_*` /
  `GIT_COMMITTER_*` environment variables.
- **The scratch directory.** A sibling overwrote another agent's commit-message
  file between write and use, and a commit briefly carried the wrong unit's
  message. Every agent temp file is keyed by agent key.

**Environment seams.** A working copy created for isolation typically has no
virtual environment, so any guard or test that resolves an interpreter relative
to the checkout produces phantom failures - seven of them were chased
independently by three agents in one wave before being written down. Tests
resolve interpreters by injection, and the dispatch brief lists the known
phantoms for your repository.

**Start clean.** Whatever your host's pull-and-verify routine is, it runs before
any agent work begins. A dirty or ahead-of-origin tree is not a safe base for a
crew.

---

## 6. Decisions

One file per decision, `docs/decisions/DEC-NNNN.md`, plus an `index.md`. This
mirrors the way per-unit release notes work - one file per unit, never
rewritten, an index for navigation - so it needs no new habits.

Front matter carries what the contradiction check needs:

```yaml
id: DEC-0042
status: active          # active | superseded
supersedes: DEC-0018
superseded_by: null
scope: backend/ledger/
expert: Edmund          # who ruled
expert_key: arc_bb1740
asked_by: bld_7e33d1
decided: 2026-09-19T14:03Z
```

Free-text markdown stops scaling around a hundred entries, which is why status
and supersession live in structured fields rather than prose. The kit's own
settled decisions ship as `DEC-0001` through `DEC-0012` and are the worked
example of the format.

---

## 7. Identity

Keys are identity; names are labels.

- Key: `<role3>_<6 hex>` - `bld_a41f09`, `arc_bb1740`. Permanent, never reused.
- Name: a first name, unique among **live** agents repo-wide across all
  sessions. Released when the agent ends, reusable afterwards.
- Every event, lease, trace, decision and item references the **key**.
- Every human-facing surface shows the **name**.

`.wall/registry/agents.md` is the store, written by `tools/wall/agents.py`.
Names bind to the instance rather than to a role slot: `docs/decisions/DEC-0009.md`.

---

## 8. CI

Add a wall integrity test built like the host's other system-tier tests and run
in the same job:

1. Every event line parses and carries `event_id`, `seq`, `ts`, `session_id`.
2. No duplicate `event_id` across shards.
3. No `seq` gaps within a session.
4. Every `.wall/items/*.json` matches its ledger-derived state (`wall diff-state`).
5. `agents.md` parses, no duplicate keys, no two live agents sharing a name.
6. Every `blocked` item has an open question; every open question past SLA has
   an assignment.
7. No item claims an open pull request that is already merged or closed.
8. No living tracker document names as open a pull request the host says is
   merged (the WORKFLOW section 8 tracker class; the item-state half is the
   courier's `merged_but_open` check — the tracker half is a host-side grep
   over the documents DOCS_MAP.md registers, honest about being host-specific).

Checks 4, 6 and 7 catch an agent or a process misbehaving rather than a file
being malformed, which is the whole point.

**Check-in cadence for in-flight pull requests.** Event delivery reports
failures reliably and success unreliably: a webhook can be dropped entirely
under rapid pushes, and a run that finishes green sometimes announces itself to
nobody. So the belt-and-suspenders is a **fixed, short re-check interval** that
sweeps every open pull request, re-arming silently whether or not anything
changed. Fixed and short, because the failure it covers is silence, and a long
interval simply means a longer stall: a lengthened cadence was measured as the
dominant source of dead wall-clock in a wave, with green checks sitting
unnoticed. The config key is `ci_checkin_minutes` in `.wall/config/wall.json`,
advisory default **10**. The discipline around it matters as much as the number:
**poll only on the timer, and wait on events otherwise** - a session that polls
because it is curious converts a cheap timer into an expensive loop, and a
session that waits on events alone stalls forever the first time one is dropped.

Because shards are not committed, the test reads whatever shards are present in
the working tree plus, optionally, the fetched telemetry branch. It must pass on
a clean checkout with **no** shards at all - an empty ledger is a valid state,
not a failure, and a test that cannot tell those apart trains people to ignore
it.

---

## 9. Models

| Role | Tier | Note |
|---|---|---|
| Foreman | verification | Mechanical work is script; the model does judgment only |
| Maestro | execution | The main session, not a subagent |
| Architect | authority | Deepest reasoning, lowest volume |
| Adjudicator | authority | |
| Builder | execution or verification, by task class | Dominant cost line |
| Integrator | same as the Builder that assumes the hat | |
| Reviewer | verification | Reads the diff cold |
| Researcher | verification | |

The ledger records `model_requested` and `model_used` separately. Requests are
sometimes routed elsewhere by safeguards, and per-model cost is wrong if the
ledger stores the intent instead of the fact. Tiering rationale and the measured
numbers behind it: `docs/decisions/DEC-0007.md`.

---

## 10. Budget

Advisory. Nothing stops work. Meters render on the ledger tab and warn; the
human decides. An agent that needs a ruling emits `human_required` and appears
on the waiting tab.

Limits are static configuration; **actuals come from the harness** - every
subagent completion reports its token usage, tool-use count and duration, and
the dispatcher writes them into the `run_end` event. Nothing is estimated for
the dominant cost line (`docs/decisions/DEC-0008.md`).

The value is the accumulated history, so the event schema matters more than any
threshold. Get it right before the first real run.

---

## 11. Context-document budgets

A standards file that feeds model prompts is a metered resource. Hosted
reviewers load instruction files against a hard limit, and when a document
crosses it the review does not degrade - it fails, on whatever change happens to
be in flight.

Growth is distributed: in one wave, three parked units each added rules to the
same counted sections while the shared budget sat 53 characters from a hard
failure. So: every prompt-loading document is registered with a declared budget
and a measuring command, extending one means measuring it **in the same change**
and recording the number, and a trimmed document gets a ratchet test so the next
wave cannot refill it. `templates/BUDGETED_DOCS.md.template` is the register.

---

## Answered questions

Everything this document used to list as open is resolved in
`docs/RECONCILIATION.md` Part 1 and recorded in `docs/decisions/`. The current
open set - which is a different, shorter list - is `docs/OPEN_QUESTIONS.md`.
