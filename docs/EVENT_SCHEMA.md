# EVENT_SCHEMA.md

The event ledger is the foundation everything else derives from: the wall, the
rollups, the integrity checks, the forecasting. It is also the one thing that is
genuinely expensive to change later, because every historical record was written
against the old shape.

Get this right before the first real run.

---

## 1. Three planes, one spine

| Plane | Path | On the dev branch | Retention | Contents |
|---|---|---|---|---|
| Ledger | `.wall/events/` | no — shipped to an isolated branch | forever | Small, schema'd accounting records |
| Trace | `.wall/logs/` | no | 14 days | Diagnostic logs, hook output |
| Artifacts | `.wall/runs/<run_id>/` | no | 7 days | Prompts, responses, diffs, tool calls |

**Shards are never committed on the development branch.** The kit originally
said "committed: yes", and the reconciliation pass reversed it: the reference deployment pushes one
designated branch through a one-PR-at-a-time pipeline, so high-churn shards
would ride every PR and conflict constantly — the exact failure class board
fragments were invented to kill (RECONCILIATION Q7).

Instead the shards live gitignored in the working tree and the courier ships
snapshots to a dedicated `wall-events` branch through an isolated
`GIT_INDEX_FILE`, leaving the working tree and index untouched. That pattern is
already proven in production on the reference deployment (verified during
the first live wave). Nothing about this schema changes: merge is still
idempotent on `event_id`, so a clone of the isolated branch rebuilds the same
ledger byte for byte.

The shipper is a separate module and is deliberately not part of this document
beyond this note: what it moves is defined here, when and how it moves is
defined there.

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

### `hook` — how the terminal record came to exist

Terminal records carry an additive `hook` object describing their own
provenance:

```json
{"event": "run_end", "run_id": "run_0142", "agent_key": "bld_a41f09",
 "outcome": "partial",
 "hook": {"source": "SubagentStop", "resolution": "resolved",
          "agent_reported": true}}
```

| Field | Meaning |
|---|---|
| `source` | Which hook wrote it (`SubagentStop`) |
| `resolution` | `resolved` when the hook could attribute the run; `unresolved` when it could not |
| `agent_reported` | Whether the agent also reported its own outcome |

A stop the hook cannot attribute is written with **`agent_key: null` and
`resolution: "unresolved"`** rather than guessed at. That record still lands,
so the run surfaces as an orphan instead of being quietly filed under whoever
ran last — and `agent_reported: false` next to a `resolved` record is the
signal that an agent is not logging its own outcomes, which is a prompt problem
rather than a ledger one.

`hook` is envelope metadata: it describes the record, not the work, and is
never folded into item state.

### Work item state

| Event | Notes |
|---|---|
| `item_created` | Mints the item. Carries the `trace_id` the item keeps |
| `item_state` | A field change, in either of the two shapes below |
| `item_shipped` | Terminal. Carries the merged `pr` number. See Shipping |
| `lease_taken` / `lease_released` | Path scope claimed for exclusive edit |

Item files under `.wall/items/` are a **materialized view**, not a primary
record. `wall rebuild` regenerates them from events alone; `wall diff-state`
compares that to disk. A non-empty diff means something wrote out of band —
either an agent bypassing the protocol or a bug in the writer. Both are worth
knowing without anyone having to notice.

### Two spellings of `item_state`, both folded

```json
{"event": "item_state", "item_id": "ST-106", "actor": "bld_a41f09",
 "field": "status", "before": "ready", "after": "active"}
```

```json
{"event": "item_state", "item_id": "ST-106", "status": "active",
 "assignee": "Desmond", "estimate": "M"}
```

The first is the **delta** shape: one field, with its previous value, which is
what an audit trail wants. The second is the **snapshot** shape: every
non-envelope key on the record is applied as an item field, which is what a
dispatcher writing four fields at once actually produces.

The fold accepts both, because a ledger that only accepts the tidy shape gets
bypassed by whichever writer finds it inconvenient, and a bypassed ledger is
worse than an untidy one. A delta naming an envelope key (`item_id`, `event`,
`ts`, `seq`, `session_id`, `event_id`) is refused and reported as
`protected_field_write` — that is a writer trying to rewrite history, not
record it.

Envelope keys are never folded into the item. `trace_id` is deliberately not an
envelope key: the item keeps the trace it was minted under, which is what makes
`wall trace <item_id>` resolvable.

### The materialized record

`wall rebuild` writes, per item, `json.dumps(..., indent=2, sort_keys=True)`
plus a trailing newline — one canonical spelling, so a rebuild that changes
nothing produces no diff:

```json
{
  "actual": null,      "arc_id": "ARC-01",     "arc_title": "Event ledger",
  "assignee": "Desmond", "created_at": "...",  "duplicate_of": null,
  "estimate": "M",     "events": 4,            "item_id": "ST-106",
  "kind": "story",     "pr": null,             "scope": ["backend/ledger/"],
  "shipped_at": null,  "status": "active",     "title": "...",
  "trace_id": "tr_st106", "updated_at": "..."
}
```

`title`, `kind` and `status` are always strings, never null: the wall renders
them directly and a null there is a blank panel rather than an honest gap.

### Questions and escalation

| Event | Notes |
|---|---|
| `question_raised` | Builder hit an ambiguity. See WORKFLOW.md §3 |
| `question_assigned` | Researcher picked it up. Carries `assignee` / `assignee_key` |
| `question_answered` | Carries `source`: `decision_log` \| `researcher` \| `architect` \| `human` |
| `question_escalated` | Carries `reason` and the `tier` moved to |
| `human_required` | Surfaces on the Waiting tab |
| `human_answered` | Clears it. Written by `wall answer <ask_id>` |

The lifecycle events carry `question_id`; the two human-queue events carry
`ask_id`. Both are indexed and a folded question carries whichever it was
given, so `wall answer` takes either. A question is open until it is answered —
`question_escalated` moves the tier, it does not close anything.

`question_raised` also carries the two scopes that decide the builder's fate,
because **Maestro decides the outcome, not the builder** (WORKFLOW.md §3):

```json
{"event": "question_raised", "question_id": "q_0042", "item_id": "ST-106",
 "ambiguity_class": "unclear_acceptance", "blocks_criteria": ["AC-3", "AC-4"],
 "dependent_scope":   ["backend/ledger/merge.py"],
 "independent_scope": ["backend/ledger/shard.py"],
 "outcome_hint": "partial"}
```

File-disjoint scopes mean `partial` and the builder keeps its lease; any
overlap means `blocked`, whatever the builder hoped.

### Decisions

| Event | Notes |
|---|---|
| `decision_written` | New `DEC-NNNN` |
| `decision_superseded` | Carries `supersedes` / `superseded_by` |

### Oversight (the RETRO / POSTURE / DOCS tabs — DEC-0026)

| Event | Notes |
|---|---|
| `warden_ruling` | One Warden verdict. Carries `gate` (`architecture` \| `data_use` \| `delivery_audit` \| `playbook` \| `tech_eval`), `subject`, `verdict`, and where applicable `tier` + `obligation` (the citable rule the verdict rests on). The POSTURE tab folds the LATEST ruling per (gate, subject); a ruling with no subject or verdict is counted malformed, never dropped silently |
| `retro_held` | One wave-close retrospective (RETROSPECTIVES.md). Carries `wave`, `signals` `[{role, name, value, prior?}]` (numeric values feed the trend series), `diffs` `[{path, why, horizon?}]`, `remeasured` `[{path, verdict}]`, `requeued`. The RETRO tab shows the latest in full and every signal's series across waves |
| `doc_reviewed` | A human acknowledged a document of record AT a sha: `path`, `sha`, `by`. The DOCS tab compares the acked sha against the file's current hash — an ack at a stale sha does not make a changed document current, which is the point of carrying the sha |
| `doc_feedback` | The review's OTHER answer (DEC-0027): not signed off. Carries `path`, `sha`, `by`, `text` (the correction / remap / discussion). The doc reads **feedback-open** — outranking every readable state — until a NEWER `doc_reviewed` lands; the text routes to the Architect as a finding. Written by `wall ack-doc <path> --feedback "..."` |
| `retro_input` | A Patron note the NEXT retrospective must consume (DEC-0027): `by`, `text`. Pending inputs surface on the RETRO tab until a `retro_held` follows them, and RETROSPECTIVES.md binds that retro to address each one. Written by `wall retro-note --text "..."` |
| `compliance_selected` | The Patron's applicability decision for a regime (DEC-0028): `regime` (from `tools/wall/compliance.py`), `applicable` (bool), `reason` (required — it IS the decision-log entry), `by`. Last selection per regime wins; the fold challenges in both directions but never flips a selection |
| `compliance_attested` | One control's self-attestation (DEC-0028): `regime`, `control` (validated against the registry), `status` (`pass` \| `fail` \| `waiver`), `note` (required for a waiver — a waiver is a recorded exception), `by`. Last attestation per (regime, control) wins; the POSTURE popout renders the full audit |

The FLOW tab (DEC-0027) adds **no** events: iterations are the segments
between `retro_held` records, and velocity / sizing / quality / burndown
read the existing `item_created` / `item_state` (estimate at assignment,
actual at close — §8) / `item_shipped` stream.


### Shipping

| Event | Notes |
|---|---|
| `route_classified` | `fast_track` \| `full_track`, plus the rule that matched |
| `doc_impact` | An architecture or decision doc moved on the fast path |
| `item_shipped` | Terminal. Carries the merged `pr` number |

`item_shipped` replaces the kit's original `drop_shipped`. Drops are
historical: since 2026-06 the reference deployment ships as named PR arcs, squash-merged one at a
time, and arcs close without a drop (RECONCILIATION Q5, Q9). The join that
actually exists is item to merged PR, so that is the one the ledger records.

```json
{"event": "item_shipped", "item_id": "ST-105", "pr": 1654,
 "agent_key": "mst_08de37", "actual": "XL"}
```

**It flips the state at merge time, not at compaction time.** The fold sets a
non-terminal item to `shipped` on this event, which is what closes the G9 hole
below. A repo that still ships drops keeps the join by adding
`shipped_in_drop` to the same record; nothing else changes.

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
shard read order. Every component is coerced to its declared type before
sorting, so a shard carrying a null `seq` sorts instead of killing the sweep.

---

## 7. Integrity, derived from the ledger

Every sweep writes these into `integrity` on the snapshot. They are all
mechanical: no model runs, and each one names a condition somebody would
otherwise have to notice.

| Flag | Condition |
|---|---|
| `seq_gaps` | A hole in a session's `seq`. A lost write shows as a hole rather than vanishing |
| `seq_duplicates` | Two records sharing `(session_id, seq)`. `next_seq` is deliberately not atomic across hook processes, so a race is *visible* here rather than silently overwriting |
| `orphan_runs` | `run_start` with no terminal event, **past its deadline**. In-flight runs do not count, or every working builder lights up the panel |
| `duplicates` | Two items with the same title, or an explicit `duplicate_of` |
| `state_drift` | Item files on disk disagree with the ledger-derived view (count; `state_drift_detail` has the fields) |
| `merged_but_open` | A shipped item that something still claims is open — see below |
| `escalations` | The five WORKFLOW.md §4 invariants: blocked-without-question, unassigned past SLA, assigned-with-no-run, capacity wasted, open past threshold |
| `stale_claims` | An agent reading `working` whose run blew its deadline. Evidence outranks self-report |

`state_drift_checked` is a separate boolean. When `.wall/items/` does not exist
yet, drift is **not checked** rather than reported as zero — a check that has
never run and a check that passed are different answers, and collapsing them is
how a dashboard starts lying.

### `merged_but_open` — a merge can outrun its own bookkeeping

Measured between PRs #1654 and #1655: a PR merged before its board fragments
were compacted left the wall claiming "in CI" on an already-merged PR, and the
next unrelated PR inherited the resulting red lint (RECONCILIATION G9).

Two shapes are detectable, and each names the item once:

- **`reopened_after_ship`** — `item_shipped` is on the ledger, and a *later*
  `item_state` puts the item back to a non-terminal status. The fold is
  faithful; the bookkeeping contradicts itself.
- **`disk_open_after_ship`** — the ledger shipped it; the item file on disk
  still carries a non-terminal status or `pr_state: "open"`.

The fix is in the schema, not the checker: `item_shipped` flips the state at
**merge** time. The flag exists for everything that writes item state without
going through it.

---

## 8. Estimation

Forecasting needs estimate and actual on every item, or there is nothing to
regress on. Pick a scale and hold it: `XS | S | M | L | XL`, recorded at
assignment as `estimate` and at close as `actual`. Both land in `item_state`.

Without this the Ledger tab can report what was spent but never whether it was
more than expected, which is the only question budgeting actually asks.

---

## 9. Diagnostics-loop events

Five events carry the closed loop from a running system's telemetry to
tracked, verified work (`docs/DIAGNOSTICS_LOOP.md`). All ride the normal
shard path with the standard envelope; nothing here invents a second
transport.

| Event | Required fields beyond the envelope | Notes |
|---|---|---|
| `diagnostic_snapshot_shipped` | `snapshot_ref` (branch/path), `generated_epoch`, `stale_after_s`, `trigger` (`heartbeat` \| `new_signature`) | The shipper writes it unconditionally — including when the observed system was unreachable, which the snapshot itself must say |
| `diagnostic_finding` | `signature` (normalized — timestamps/pids/ids collapsed), `class` (`known_playbook` \| `unclassified`), `route` (`auto_repaired` \| `story_filed` \| `escalated`), `snapshot_ref` | A generic string that could match many causes stays `unclassified`; mis-filing is worse than not filing |
| `story_filed` | `finding_ref` (the `diagnostic_finding`'s `event_id`), `item_id` | The join `wall trace` walks from a log line to the merged PR |
| `verify_requested` | `item_id`, `what_changed`, `verify_steps` | Appended at ship for anything the owner could see or feel; append-only queue, persists across releases |
| `verified` | `item_id`, `verdict` (`confirmed` \| `confirmed_with_findings`), `by` | Only ever records a human answer; a `confirmed_with_findings` feeds stage three as a new finding |

Two integrity checks come with them, both courier-side: a
`diagnostic_finding` with `route: story_filed` and no matching `story_filed`
within the SLA is a dropped ball, flagged like an unassigned question; a
`verify_requested` older than the configured horizon surfaces on the WAITING
tab beside unanswered asks — the loop holding a slot open for a human is
visible, never silent.


## Regime lifecycle events (DEC-0030)

| Event | Written by | Carries |
|---|---|---|
| `compliance_scanned` | `wall compliance-scan` (Warden, periodic) | `regimes: [{regime, recommended, evidence[]}]` — the evidence verbatim, one event per scan |
| `compliance_audited` | `wall audit <regime>` (Warden) | `regime`, `by` — the audit marker; the per-control results are the `compliance_attested` events written in the same run |

`compliance_attested` (DEC-0028) is unchanged in shape and tightened in
contract: `note` is mandatory on every row — pass carries its proof, fail
and waiver their reason. `wall audit` refuses a partial audit by name.
