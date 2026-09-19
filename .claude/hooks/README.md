# .claude/hooks -- the facts layer

Agents write the semantic content: rationale, open questions, level of effort.
**Hooks write the facts.** An agent that forgets to log is a bug you cannot
prompt away; a hook that fires on termination is guaranteed
(`docs/LOGGING_AND_AUDIT.md`).

| Script | Fires on | Writes |
|---|---|---|
| `subagent_stop.py` | `SubagentStop` | The terminal `run_end` / `run_error` ledger event, in the shard format of `docs/EVENT_SCHEMA.md` |
| `tool_use.py` | `PreToolUse`, `PostToolUse` | `.wall/runs/<run_id>/tools.jsonl` -- tool name, scrubbed args, exit code, duration |
| both | every invocation | Their own exit to `.wall/logs/hooks.log` |

That last row is not decoration. A silently failing hook corrupts everything
downstream and is otherwise completely invisible.

---

## Install

1. Copy the `hooks` block from `hooks.json.example` into `.claude/settings.json`
   (shared) or `.claude/settings.local.json` (per machine). Merge it with hooks
   you already have; do not overwrite the file.
2. On Windows, change `python3` to `python`.
3. Verify: run one subagent, then

   ```
   tail -n 5 .wall/logs/hooks.log
   ls .wall/events/$(date -u +%F)/
   ```

   The log should carry a `subagent_stop exit=0` line and the shard should carry
   a terminal event. If the log is empty, the hook is not wired.
4. `wall doctor` reports hook health alongside heartbeat and seq gaps. Treat
   "no hook events" as "the ledger is incomplete", not as "no work happened".

Nothing needs installing beyond that: stdlib only, no dependencies, no build.

---

## The two guarantees

**Never blocks.** Both scripts wrap everything in `try/except BaseException`,
log the failure, and `exit 0` on every path -- including unreadable stdin,
malformed JSON, a missing `.wall`, and an unwritable disk. A `PreToolUse` hook
that exits non-zero or prints a decision object on stdout can **deny the tool
call**, so neither script writes anything to stdout, ever. If you extend them,
keep both properties; they are what makes the audit layer safe to leave on.

**Append-only, one write per record.** Records are written with
`os.open(..., O_APPEND)` and a single `os.write`, so concurrent lines never
interleave (`docs/EVENT_SCHEMA.md` section 6). Shards are never rewritten.

---

## How a run is identified

The `SubagentStop` payload does not name the subagent that stopped, so identity
is resolved in precedence order:

1. `run_id` in the payload, if the harness supplies one.
2. `WALL_RUN_ID` in the environment.
3. `.wall/registry/open_runs.json` -- the runs the Maestro registered at
   dispatch, filtered to this session and to runs with no terminal event yet.
   One match is used directly; several means the oldest is used and the record
   is marked `inferred_oldest`.
4. None of the above: a synthetic id marked `unresolved`. The real run then
   shows as an orphan in the integrity panel, which is the honest outcome --
   better a visible hole than a confident wrong attribution.

**So the Maestro must register each dispatch.** Write `open_runs.json` as either
`{"<run_id>": {...}}` or `{"runs": [{...}]}`; both are accepted. Useful fields:
`run_id`, `session_id`, `agent_key`, `agent_name`, `role`, `item_id`,
`trace_id`, `parent_run_id`, `model_requested`, `started`.

An agent may leave its own semantic half at `.wall/runs/<run_id>/outcome.json`
(`outcome`, `error_class`, `tokens`, `cost_usd`, `duration_s`,
`decisions_in_context`). The hook folds it in and marks `hook.agent_reported`.
If the agent already wrote its own terminal event, the hook writes **nothing** --
the dedupe is on `run_id`, so the hook is safe to leave enabled everywhere.

---

## Scrubbing and caps

`tool_use.py` runs every argument blob through `SCRUB_PATTERNS` before writing:
private key blocks, `Authorization` headers, `sk-ant-` / `sk-` / `gh?_` /
`xox?-` / `AKIA` tokens, and a generic
`api_key|secret|token|password|private_key` assignment sweep. Any single
artifact is capped at 256 KB with a `...[truncated at 256KB]` marker, because
one runaway test log otherwise eats the disk.

The scrubber is **defence in depth, not a guarantee.** `.wall/runs/` and
`.wall/logs/` are gitignored so a miss stays local. Add patterns to
`SCRUB_PATTERNS` rather than post-processing the files.

---

## Two SessionStart patterns the kit documents but does not ship

The kit ships **facts-layer hooks only** -- scripts that record what happened
and can never change what happens. A session-start script does the opposite: it
runs commands, installs things and injects text into the model's context, and
what those commands are is the host's business, not the kit's. So these two are
documented as patterns with fragments, and you write the script.

**Pattern A -- instruction injection.** One hook emits the repository's standing
boot routine as `additionalContext` on **every** session, so the owner says only
"new session" and the routine is already in context. Keep it in its own script,
separate from provisioning: provisioning is often guarded to remote or container
sessions, and the instructions must land on local ones too.

```
INSTRUCTIONS="$CLAUDE_PROJECT_DIR/.claude/SESSION_INSTRUCTIONS.md"
[ -f "$INSTRUCTIONS" ] || exit 0
# emit {"hookSpecificOutput":{"hookEventName":"SessionStart",
#       "additionalContext": <file contents>}} as JSON on stdout
```

One source of truth: the routine lives in a human-editable file and the hook
reads it. A routine inlined into the script is a copy that drifts from the
document everyone else edits.

**Pattern B -- the provisioning skeleton, with an honesty accumulator.** A fresh
container or clone needs dependencies, data files and hooks before any gate can
run. Two properties are load-bearing, and both are about lying rather than about
provisioning:

```
DEGRADED=""
note()    { echo "[session-start] $*"; }
degrade() { DEGRADED="${DEGRADED:+$DEGRADED, }$1"; note "DEGRADED: $1"; }

# step 0, BEFORE any failable step: install the version-control hooks
bash scripts/setup-git-hooks.sh && note "git hooks installed" \
  || degrade "git hooks install failed"

# then each provisioning step, wrapped the same way:
#   <cmd> && note "<what> ok" || degrade "<what> failed"

if [ -n "$DEGRADED" ]; then
  note "provisioning INCOMPLETE -- degraded: $DEGRADED"
  exit 1
fi
note "ready"
```

- **Hook install is step 0**, before anything that can fail. A provisioning
  abort must never skip it, or the session's first commit ships a stale derived
  artifact and spends a full pipeline cycle finding out
  (`docs/GIT_HOOKS.md` section 1).
- **A masked failure reports "provisioning INCOMPLETE" and exits non-zero.**
  Every step is wrapped in `ok || degrade` so one failure does not abort the
  rest, and the accumulator is what stops the script claiming ready anyway.
  **Status lies at provision time surface as mystery failures an hour later**,
  by which point nobody connects the two.

A provisioning hook may legitimately exit non-zero; the facts-layer hooks above
never may. That is the line between the two kinds.

---

## Why these are self-contained

Each script duplicates about sixty lines of helpers instead of importing a
shared module. A hook that cannot import is a hook that does not fire, and the
whole point of the layer is that it fires when the agent did not. Duplication is
the cheaper failure.

Tests: `tests/test_hooks.py` drives both scripts as subprocesses with synthetic
payloads and asserts the ledger shape, the scrubbing, the 256 KB cap, the empty
stdout, and the never-block guarantee.
