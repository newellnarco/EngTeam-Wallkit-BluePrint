# LOGGING_AND_AUDIT.md

Enough logging to troubleshoot in minutes, and enough auditing to prove the wall
matches reality.

See EVENT_SCHEMA.md §1 for the three planes and the `trace_id` / `run_id` /
`parent_run_id` spine. This document covers what gets captured and how you
interrogate it.

---

## Per-run artifacts

Normal application logging is not enough here, because the failures are about
what the model was handed, not what the code did.

```
.wall/runs/<run_id>/
  meta.json     agent_key, role, model_requested, model_used, item, trace_id,
                started, ended, outcome, error_class, tokens, cost,
                decisions_in_context, criteria_sources
  prompt.md     the RESOLVED prompt: system + task + every injected decision
                record, file excerpt and context blob
  response.md   full text returned
  tools.jsonl   every tool call: name, args (scrubbed), exit code, duration
  diff.patch    git diff attributable to this run
  tests.txt     test output
```

**`prompt.md` is the highest-value artifact in the system.** When a builder
ignores an architectural ruling, the only question that matters is whether it
ignored the ruling or was never given it. You can only answer that by reading
exactly what went in.

---

## Hooks own the mandatory records

An agent that forgets to log is a bug you cannot prompt away.

| Hook | Writes |
|---|---|
| PreToolUse / PostToolUse | `tools.jsonl` — no agent cooperation required |
| SubagentStop | The terminal ledger event, written regardless |
| The hook wrapper itself | Its own exit code to `.wall/logs/hooks.log` |

That last row matters: a silently failing hook corrupts everything downstream and
is otherwise completely invisible.

Agents write the semantic content — rationale, open questions, level of effort.
Hooks write the facts.

---

## Auditing is a different property than logging

Auditing means you can **prove** the wall matches reality. You get that by making
item state a materialized view rather than a primary record.

Every state change emits a ledger event with actor, field, before and after. Item
files are then derivable:

- `wall rebuild` — regenerate all item state from events alone.
- `wall diff-state` — compare that to what is on disk.

A non-empty diff means something wrote out of band: an agent bypassing the
protocol, or a bug in the writer. Both are worth knowing without anyone having to
notice.

Paired with the `seq` gap check, you have integrity on both the stream and the
derived state.

---

## Scrubbing and volume

Prompts and tool arguments will pick up environment variables, tokens and file
contents. Run a scrubber against a pattern list before writing, and keep
`.wall/logs/` and `.wall/runs/` gitignored so a miss stays local.

Cap any single artifact at 256 KB with a truncation marker, or one runaway test
log eats the disk.

---

## Testing without spending tokens

`sample/make_sample.py` writes canned event shards -- a deliberately unhealthy
sample -- so the merge, validator, renderer, trace commands and timer are
exercisable end to end with **zero model calls**. There is no `--fake-agent`
flag on any command; the script is the whole fake-agent mode (see the planned
list below).

Golden-file test for the merge: shuffled shard order must produce byte-identical
output. Already verified — `courier.py --rebuild` equals an incremental run.

Fixture library of nasty streams worth keeping: sequence gaps, duplicate
`event_id`s, a `run_start` with no terminal event, clock skew between sessions,
a trailing partial line mid-append.

---

## Commands you will live in

Every command below exists in `tools/wall/wall.py` today:

```
wall trace <item_id|trace_id>   causal timeline across agents and sessions
wall why <item_id>              decisions in effect, and which runs actually saw them
wall rebuild [--prune]          regenerate .wall/items/ from events alone
wall diff-state                 ledger-derived item state vs on-disk
wall doctor [--json]            heartbeat, integrity flags (seq gaps, orphan
                                runs, ...), roster and plumbing health;
                                --json also writes .wall/derived/doctor.json
```

The learning-loop records, each validated before it is written (the command
refuses what the governing document forbids):

```
wall run-start --key --role --item --deadline-min   run_start + open_runs.json;
                                refuses past role_limits unless
                                --over-cap-reason is recorded
wall run-end --run <run_id>     no-hooks path: the terminal record the
                                SubagentStop hook would write
wall retro --wave --file        retro_held, validated against RETROSPECTIVES.md
wall rebalance --knob --from --to --signal --expect --horizon
                                rebalance_applied; one knob per cycle, a second
                                reversal goes to the Adjudicator
wall finding --signature --class --route --snapshot-ref
                                diagnostic_finding (DIAGNOSTICS_LOOP.md)
wall story-filed --finding --item   joins a finding to the story that carries it
wall verify-request --item --what --steps   owner-verification queue
wall verified --item --verdict  the owner's answer (human only)
```

**Planned -- not built.** Nothing in this list exists yet; do not script
against it:

- `wall run <run_id>` -- inputs and outputs of one invocation
- `wall tail [--role builder]` -- live event stream, filterable by role
- `wall replay <run_id>` -- re-dispatch with identical resolved inputs. It would
  not reproduce output exactly, but re-running an agent against a
  byte-identical prompt is how you tell a bad prompt from a bad roll.
- `--fake-agent` -- a flag emitting canned event sequences; today
  `sample/make_sample.py` plays that role
