# EVENT_SCHEMA.md

The event ledger is the foundation everything else derives from: the wall, the
rollups, the integrity checks, the forecasting. It is also the one thing that is
genuinely expensive to change later, because every historical record was written
against the old shape.

Get this right before the first real run.

---

## 1. Three planes, one spine

| Plane | Path | Committed | Retention | Contents |
|---|---|---|---|---|
| Ledger | `.wall/events/` | yes | forever | Small, schema'd accounting records |
| Trace | `.wall/logs/` | no | 14 days | Diagnostic logs, hook output |
| Artifacts | `.wall/runs/<run_id>/` | no | 7 days | Prompts, responses, diffs, tool calls |

They are separate because their requirements conflict. The ledger must stay
small enough to keep forever and stable enough to aggregate. Artifacts are large,
messy, and occasionally sensitive. Merging them makes the ledger useless for
forecasting and the artifacts too expensive to retain.

The spine joining them is three identifiers on every record:

- **`trace_id`** — one work item's entire journey, across agents and sessions.
  Builder blocks, researcher investigates, architect rules, decision is written,
  builder resumes. That multi-hop chain is what you actually troubleshoot, and it
  is invisible unless the id survives every handoff. Maestro mints it at item
  creation.
- **`run_id`** — one subagent invocation.
- **`parent_run_id`** — the run that dispatched this one.

---

## 2. Record shape

One JSON object per line, in `.wall/events/<YYYY-MM-DD>/<session_id>.jsonl`.

```json
{
  "schema_version": 1,
  "event_id": "a3f1c9e2-7b04-4d18-9c55-1e8f3b2a0d61",
  "seq": 1487,
  "ts": "2026-09-19T14:03:22.441Z",
  "session_id": "s_7f3a",
  "trace_id": "tr_st106",
  "run_id": "run_0142",
  "parent_run_id": "run_0139",
  "agent_key": "bld_a41f09",
  "agent_name": "Desmond",
  "role": "builder",
  "model_requested": "claude-opus-5",
  "model_used": "claude-opus-5",
  "item_id": "ST-106",
  "event": "run_end",
  "outcome": "partial",
  "error_class": null,
  "tokens": {"in": 18432, "out": 3120, "cache_read": 96204, "cache_write": 4180},
  "cost_usd": 1.84,
  "gh_minutes": null,
  "duration_s": 212,
  "decisions_in_context": ["DEC-0043", "DEC-0112"]
}
```

### Required on every record

| Field | Why it exists |
|---|---|
| `schema_version` | Old shards stay readable when the shape changes |
| `event_id` | UUID4. Makes consolidation idempotent — a full rebuild equals an incremental run, byte for byte. That property is what lets you trust the ledger |
| `seq` | Monotonic per session. A gap means a lost write, surfaced as corruption rather than a silent hole |
| `ts` | UTC, millisecond precision, `Z` suffix |
| `session_id` | Also the shard filename, so two sessions never write the same file |
| `event` | See §3 |

### Required where applicable

`trace_id`, `run_id`, `parent_run_id`, `agent_key`, `role`, `item_id`.

**`agent_key`, never `agent_name`.** Names are reusable display labels; keys are
permanent. A ledger keyed on names would merge two different agents into one row
the first time a name is recycled.

---

## 3. Event types

### Run lifecycle

| Event | Written by | Notes |
|---|---|---|
| `run_start` | Maestro, before dispatch | Carries `item_id`, deadline, scopes |
| `run_end` | SubagentStop hook | Written whether or not the agent wrote one |
| `run_error` | SubagentStop hook | Crash, timeout, tool failure |

The hook owns the terminal event. An agent that forgets to log is a bug you
cannot prompt away; a hook that fires on termination is guaranteed.

### Work item state

| Event | Notes |
|---|---|
| `item_state` | Any field change. Carries actor, field, before, after |
| `item_created` | |
| `lease_taken` / `lease_released` | Path scope claimed for exclusive edit |

Item files under `.wall/items/` are a **materialized view**, not a primary
record. `wall rebuild` regenerates them from events alone; `wall diff-state`
compares that to disk. A non-empty diff means something wrote out of band —
either an agent bypassing the protocol or a bug in the writer. Both are worth
knowing without anyone having to notice.

### Questions and escalation

| Event | Notes |
|---|---|
| `question_raised` | Builder hit an ambiguity. See WORKFLOW.md §3 |
| `question_assigned` | Researcher picked it up |
| `question_answered` | Carries `source`: `decision_log` \| `researcher` \| `architect` \| `human` |
| `question_escalated` | Carries `reason` and the tier moved to |
| `human_required` | Surfaces on the Waiting tab |
| `human_answered` | Clears it |

### Decisions

| Event | Notes |
|---|---|
| `decision_written` | New `DEC-NNNN` |
| `decision_superseded` | Carries `supersedes` / `superseded_by` |

### Shipping

| Event | Notes |
|---|---|
| `route_classified` | `fast_track` \| `full_track`, plus the rule that matched |
| `drop_shipped` | Links items to a MAX3 drop number |

---

## 4. Outcomes and failures

`outcome` is a closed vocabulary:

```
pass | partial | blocked | timeout | error | human_required
```

`partial` is the important one. It means the agent raised a question but had
file-disjoint independent work remaining, so it kept going. Collapsing `partial`
into `blocked` wastes a builder slot every time someone asks a question.

`error_class` is also closed, because free-text errors cannot be aggregated:

```
test_failure       lint_failure        ci_failure        merge_conflict
lease_denied       missing_decision    ambiguous_requirement
unspecified_edge_case   undefined_interface   dependency_unknown
tool_error         model_error         budget_exceeded   human_required
```

The payoff is a month later being able to say "42% of builder failures are
`undefined_interface`, so the Architect handoff is thin on contracts." That is
worth more than any individual failure.

---

## 5. Tokens and cost

`tokens` is **four numbers, not one**. Input, output, cache-creation and
cache-read are priced very differently, and cache reads will dominate volume.
Collapsing them makes cost estimates wrong by an order of magnitude.

`model_requested` and `model_used` are separate fields. Fable requests are
sometimes routed to Opus 5 by safeguards, and a ledger that stores the intent
instead of the fact will misattribute those costs silently. Always read the model
from the response.

`gh_minutes` is nullable. GitHub billing lags and arrives by a different API, so
records get backfilled after the fact. Design for it rather than blocking on it.

`decisions_in_context` is a first-class field, not something to infer from the
prompt. When a builder ignores an architectural ruling, the only question that
matters is whether it ignored the ruling or was never given it. This field turns
that from archaeology into a lookup.

### "Tokens saved"

Undefined metrics are unfalsifiable. Two defensible definitions, both countable:

1. **Cache savings** — `cache_read` tokens at the discounted rate versus full
   input price.
2. **Decision-log short-circuits** — questions answered from an existing
   `DEC-NNNN` without dispatching a researcher, times the median researcher run
   cost. This one should rise as the project matures, which is exactly the curve
   worth watching.

---

## 6. Writing safely

- Open `O_APPEND`, one `write()` per record. Concurrent lines then never
  interleave.
- Never rewrite a shard. Append only.
- Roll shards by day: `events/2026-09-19/s_7f3a.jsonl`. Bounds any one file and
  keeps incremental reads cheap.
- A reader that finds a trailing partial line leaves it for the next pass rather
  than parsing a record a writer is still appending. `courier.py` does this.

Total order on merge is `(ts, session_id, seq)` — deterministic regardless of
shard read order.

---

## 7. Estimation

Forecasting needs estimate and actual on every item, or there is nothing to
regress on. Pick a scale and hold it: `XS | S | M | L | XL`, recorded at
assignment as `estimate` and at close as `actual`. Both land in `item_state`.

Without this the Ledger tab can report what was spent but never whether it was
more than expected, which is the only question budgeting actually asks.
