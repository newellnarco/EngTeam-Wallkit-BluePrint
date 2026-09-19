# WALL_STANDARDS.md

How the agent workforce and the wall fit into MAX3's existing conventions.

This document is a mapping, not a new system. Where MAX3 already has a rule, the
wall adopts it. Where the wall needs something MAX3 doesn't have, this says so
explicitly and explains why it isn't folded into an existing mechanism.

**Status:** reconstructed from the five `max3-*` skills, not from a direct read of
the repo. Every line marked *(inferred)* needs confirming against the tree before
this becomes normative.

---

## 1. Folder layout

The wall adds one top-level directory. Everything else uses existing homes.

```
.wall/                          NEW — agent state, one directory, repo root
  config/wall.json              budget meters, role caps, thresholds
  registry/agents.md            key → name roster (markdown, hand-editable)
  registry/leases.json          file-scope leases, prevents concurrent edits
  events/<YYYY-MM-DD>/<sid>.jsonl   append-only, sharded per session
  items/<item_id>.json          one file per arc / story / bug
  derived/                      GITIGNORED — regenerated, never merged
    wall.html  wall.json  ledger.jsonl  heartbeat.json
  logs/                         GITIGNORED — trace, 14-day TTL
  runs/<run_id>/                GITIGNORED — prompts, diffs, tool calls, 7-day TTL

tools/wall/                     NEW — wall tooling, joins existing tools/
  courier.py  agents.py  wall.py  install/

docs/decisions/                 NEW — one file per decision + index.md
docs/md/                        EXISTING — PATCH_NOTES_DROPNN.md unchanged
docs/architecture/              EXISTING — Architect agent's output lands here
backend/tests/system/           EXISTING — wall integrity test joins the ledger test
```

`tools/wall/` rather than `backend/` because this is repo tooling, not product
code. It sits beside `tools/check-local-unpushed.ps1`, which is the same kind of
thing. *(inferred: that `tools/` is for repo tooling and not shipped.)*

---

## 2. What goes in git

| Path | Committed | In TREE_INTEGRITY_LEDGER | Why |
|---|---|---|---|
| `.wall/config/**` | yes | yes | Durable, hand-edited, drift is a real bug |
| `.wall/registry/agents.md` | yes | yes | Roster is a document; a surprise diff matters |
| `.wall/registry/leases.json` | yes | **no** | Changes every dispatch; would thrash the ledger |
| `.wall/items/**` | yes | **no** | High churn, and the ledger reconstructs them anyway |
| `.wall/events/**` | yes | **no** | Append-only, grows constantly, sharded so it never conflicts |
| `.wall/derived/**` | **no** | no | Reproducible output; committing it conflicts every 2 min |
| `.wall/logs/`, `.wall/runs/` | **no** | no | May contain scrubbed-but-sensitive prompt text |

The ledger is append-only history of *things that should not change silently*.
Event shards are the opposite: they change by design, every minute. Putting them
in the ledger would make `test_tree_integrity_ledger` fail on every sweep.

Add to `.gitignore`:

```
.wall/derived/
.wall/logs/
.wall/runs/
.wall/registry/*.lock
```

---

## 3. Fast-track routing

**This is not new.** `max3-docs-push` already classifies changed files into doc
and source buckets and blocks on source. Fast-track promotes that rule from skill
prose into `.wall/config/wall.json` so Courier, CI, and the agents all read one
definition instead of three copies drifting apart.

```json
{
  "fast_track": {
    "allow": ["**/*.md", "docs/**/*.docx", "TREE_INTEGRITY_LEDGER.txt",
              "MANIFEST.sha256"],
    "deny":  ["frontend/src/**", "backend/**/*.py", "**/*.bat", "**/*.ps1",
              ".github/workflows/**", "tools/**", ".wall/config/**", "**/CLAUDE.md"]
  }
}
```

Deny beats allow, always. Three entries are worth defending:

- `.github/workflows/**` — a builder editing CI to turn its own tests green is the
  classic escape hatch. It's code.
- `**/CLAUDE.md` — it's `.md`, so the glob would fast-track it, but it changes the
  behavior of every future agent. It's code, and it gets full review.
- `tools/**` — wall tooling can corrupt the ledger. Not a doc.

Mixed changesets split rather than get an exception, which matches what
`max3-docs-push` already tells the user to do.

**CI:** add `paths-ignore` for the allow list so no minutes are queued, plus a
companion no-op workflow on the inverse paths reporting the same check name, or
branch protection blocks the merge forever.

---

## 4. Work items and drops

MAX3 ships in numbered **drops**. The wall tracks **arcs / stories / bugs**. They
are different axes and shouldn't be collapsed.

- An **arc** is a theme of work. It may span several drops or fit inside one.
- A **drop** is a shipped unit with an install bat and a `PATCH_NOTES` file.
- Every item records `shipped_in_drop` once merged. That's the only join needed.

An arc closing is the natural trigger for a drop, and when one is cut,
`DROP_PROTOCOL.md` §5 applies unchanged: bump `CLAUDE.md`, append to
`PATCH_INDEX.md`, append a ledger section, write `PATCH_NOTES_DROPNN.md`, then
regenerate `MANIFEST.sha256` via `regen_manifest.bat`. The Foreman checks those
four landed; it does not replace the protocol.

Item IDs stay human-typeable and distinct from drop numbers: `ARC-01`, `ST-104`,
`BG-021`.

---

## 5. Branches and leases

Branch convention is unchanged: `work/YYYY-MM-DD[-suffix]`, squash-merged to main.

Concurrency is the new part. Subagents inside one session share a working tree, so
two builders editing at once corrupts it. Maestro assigns each item a declared
path scope and writes a lease; it refuses to dispatch a second builder whose scope
overlaps. Leases carry a TTL so a dead agent doesn't hold a path forever.

When parallel sessions arrive, worktrees go underneath the same lease check. The
check does not change.

`max3-pull-smart` runs before any agent work begins. A dirty or ahead-of-origin
tree is not a safe base for a crew.

---

## 6. Decisions

One file per decision, `docs/decisions/DEC-NNNN.md`, plus a generated `index.md`.
This mirrors how `PATCH_NOTES` works — one file per unit, never rewritten, an
index for navigation — so it needs no new habits.

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

Free-text markdown stops scaling around a hundred entries, which is why the
status and supersession live in structured fields rather than prose.

---

## 7. Identity

Keys are identity; names are labels.

- Key: `<role3>_<6 hex>` — `bld_a41f09`, `arc_bb1740`. Permanent, never reused.
- Name: a first name, unique among **live** agents repo-wide across all sessions.
  Released when the agent ends, reusable afterward.
- Every event, lease, trace, decision and item references the **key**.
- Every human-facing surface shows the **name**.

`.wall/registry/agents.md` is the store, written by `tools/wall/agents.py`.

---

## 8. CI

Add `backend/tests/system/test_wall_integrity.py`, built the same way as
`test_tree_integrity_ledger.py` and run in the same job:

1. Every event line parses and carries `event_id`, `seq`, `ts`, `session_id`.
2. No duplicate `event_id` across shards.
3. No `seq` gaps within a session.
4. Every `.wall/items/*.json` matches its ledger-derived state (`wall diff-state`).
5. `agents.md` parses, no duplicate keys, no two live agents sharing a name.
6. Every `blocked` item has an open question; every open question past SLA has an
   assignment.

Checks 4 and 6 are the ones that catch an agent misbehaving rather than a file
being malformed, which is the whole point.

---

## 9. Models

| Role | Model | Note |
|---|---|---|
| Foreman | Sonnet 5 | Mechanical work is script; the model does judgment only |
| Maestro | Opus 5 | The main session, not a subagent |
| Architect | Fable 5.1 | Deepest reasoning, lowest volume |
| Adjudicator | Fable 5.1 | |
| Builder | Opus 5 / Sonnet 5 by task class | Dominant cost line |
| Reviewer | Sonnet 5 | Reads the diff cold |
| Researcher | Sonnet 5 | |

The ledger records `model_requested` and `model_used` separately. Fable requests
are sometimes routed to Opus by safeguards, and per-model cost is wrong if the
ledger stores the intent instead of the fact.

---

## 10. Budget

Advisory. Nothing stops work. Meters render on the Ledger tab and warn; the human
decides. An agent that needs a ruling emits `human_required` and appears on the
Waiting tab with `wall answer <ask_id>`.

The value is the accumulated history, so the event schema matters more than any
threshold. Get it right before the first real run.

---

## Open questions

1. Is `tools/` shipped to users, or repo-only? If shipped, `tools/wall/` moves.
2. Does `pyproject.toml` at root mean `backend/` is the package, or is the whole
   repo one package? Affects where the wall test lands.
3. Should an arc closing *require* a drop, or can arcs close without shipping?
4. Do `.wall/config/**` and `agents.md` belong in the ledger, or is per-drop
   hashing too coarse for files that change between drops?
5. Fast-track destination: straight to main, or auto-merge PR?
