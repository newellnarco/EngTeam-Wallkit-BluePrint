# MAX3 wall kit

An agent workforce and a status wall for software built by agents, designed to
drop into the MAX3 repo and run under Claude Code.

Everything here is stdlib Python, plain CSS and plain HTML. No dependencies, no
network calls, no build step.

---

## Status at a glance

| | |
|---|---|
| **Built and verified** | `courier.py`, `agents.py`, the wall renderer and template, the theme, `wall run-once` / `doctor` / `classify` / `agents` |
| **Designed, not built** | Question lifecycle, escalation ladder, lease enforcement, `diff-state`, `trace`, `why`, `fast-track`, install adapters |
| **Open** | 16 decisions in `docs/OPEN_QUESTIONS.md`, 5 of which need the repo tree to answer |

The design was done without access to the MAX3 tree — GitHub blocks automated
fetching and the local checkout was not reachable from the session. Everything in
`WALL_STANDARDS.md` marked *(inferred)* was reconstructed from the five `max3-*`
skill files and needs confirming.

---

## Try it in 30 seconds

```bash
cd sample
python3 make_sample.py                  # writes fake event shards
python3 ../tools/wall/courier.py --repo .
open .wall/derived/wall.html            # or double-click it
```

The sample deliberately contains four integrity problems, all real conditions the
system has to survive:

- A **sequence gap** — a record was deleted from one shard. A lost write shows as
  a hole rather than vanishing.
- Two **orphaned runs** past deadline. In-flight runs correctly do not count, or
  every working builder would light up the panel.
- **Nadia reads `stale`, not `working`**, though her last event claims a run in
  progress. A blown deadline reclassifies the agent regardless of what it said
  about itself. Evidence over self-report, made mechanical.
- **Coretta shows `claude-opus-5 ⇢ routed`** — she requested Fable and safeguards
  sent her to Opus. The ledger records what ran, so per-model costs stay honest.

---

## Layout

```
docs/
  WALL_STANDARDS.md      folder layout, git boundaries, MAX3 conventions mapping
  AGENT_ROSTER_SPEC.md   the seven roles, models, caps, authority
  EVENT_SCHEMA.md        the contract — read this before the first real run
  WORKFLOW.md            execution model, dispatch, ambiguity, escalation
  LOGGING_AND_AUDIT.md   three planes, per-run artifacts, trace commands
  FAST_TRACK.md          doc-only routing, zero CI minutes
  INSTALL.md             machine-wide timer, serving, Windows specifics
  OPEN_QUESTIONS.md      decisions still needed, grouped by what they block
  ORIGINAL_OUTLINE.md    the source outline, unedited

tools/wall/
  courier.py             merge, snapshot, render, heartbeat        WORKING
  agents.py              markdown-backed key/name registry          WORKING
  wall.py                CLI; stubs raise with what they need       PARTIAL
  wall.bat               Windows shim, beside push-to-github.bat
  render/wall_template.html
  install/               windows.py / macos.py / linux.py           STUBS
  config/wall.example.json

frontend/theme/
  theme.css              tokens, light + dark, WCAG AA verified
  primitives.css         component classes, zero raw hex
  preview.html           the system on app chrome, with a toggle
  ADOPTION.md

sample/make_sample.py    fixture generator, zero model calls
.gitignore.fragment
```

---

## The five ideas everything else follows from

**1. Agents don't persist; state does.** Claude Code subagents are single-shot.
Nothing polls, nothing watches. So persistence lives on disk and short agent
invocations fire off hooks and a timer. This is why Courier is a script, why
Maestro is the top-level session rather than a subagent, and why the Foreman's
singleton is a lock file rather than a process.

**2. Bookkeeping is code, not cognition.** Counting tokens, merging shards and
rendering a grid are deterministic. A Foreman running as an LLM every two minutes
outspends the builders while producing no code. Models are invoked for judgment:
contradiction triage, stale-claim narration, anomaly.

**3. Evidence outranks self-report.** Status comes from git, tests and CI, not
from agents describing themselves. A `run_start` with no terminal event past its
deadline reclassifies the agent as `stale`. Item files are a materialized view of
the event log, so `diff-state` catches anything written out of band.

**4. Keys are identity; names are labels.** `bld_a41f09` is permanent and appears
in every event. "Desmond" is a reusable display name, unique among live agents
repo-wide. Reuse is safe because nothing downstream depends on the name.

**5. The ledger must be reproducible.** Merge is idempotent on `event_id` and
totally ordered on `(ts, session_id, seq)`, so a full rebuild from shards yields
a byte-identical ledger to an incremental run. Verified. That property is what
makes the audit trail trustworthy, and it is why Courier is not an agent.

---

## Where to start

1. **Answer questions 1–5** in `OPEN_QUESTIONS.md`. They need `git ls-files`,
   `pyproject.toml`, the ledger header format, the workflows, and
   `DROP_PROTOCOL.md` §5. Everything inferred becomes verified.
2. **Settle question 6** — whether `.wall/config/` and `agents.md` belong in
   `TREE_INTEGRITY_LEDGER.txt`. Low confidence, and it decides whether the
   integrity test is useful or noisy.
3. **Settle question 10** — researcher network access. Must be decided before the
   first real run.
4. **Then run `wall run-once` against a real `.wall/`** and see what the
   integrity panel says about an empty project.

The rest can be built incrementally. `wall run-once` works today, so the whole
system can be driven by hand or from a git hook while the adapters are stubs.
