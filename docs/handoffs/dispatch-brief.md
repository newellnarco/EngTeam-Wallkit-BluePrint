# Dispatch brief -- TEMPLATE

> **G13.** Handoffs are documents, not paraphrases. Every re-brief in the first
> wave was hand-written and each drifted. Fill this in; do not summarise it.
>
> **Every field below is load-bearing.** A field left blank is a question the
> agent will answer by guessing. If you cannot fill one, say `UNKNOWN -- raise
> before starting` rather than deleting the row.

---

## 0b. Declared data uses

| Dataset / credential / source | Dev or product | Warden verdict + date |
|---|---|---|
| | | |

Every data use this story touches, with its verdict from the Warden already
attached -- a story dispatched with an unruled data use is a process defect.

## 1. Identity and accounting

| Field | Value |
|---|---|
| Agent role | `builder` / `reviewer` / `researcher` / `architect` / `adjudicator` / `foreman` |
| Agent key | `bld_______` -- permanent, appears in every event and every temp filename |
| Agent name | display label only |
| Model / task class | `opus` + `judgment`, or `sonnet` + `mechanical` |
| `run_id` | registered in `.wall/registry/open_runs.json` before dispatch |
| `trace_id` | the item's whole journey, across agents and sessions |
| `parent_run_id` | this session's run |
| Deadline | after which the run reclassifies as `stale`, whatever it last claimed |

**Commit identity (G1).** Never run `git config` -- it is repo-global and has
re-authored another agent's in-flight commit. Use per invocation:

```
git -c user.name="NAME" -c user.email="EMAIL" commit ...
```

**Temp-file key (G2).** Every temp file you write is
`<purpose>-<agent_key>.<ext>`. A sibling overwrote an unkeyed `commitmsg.txt`
between write and use and the commit carried the wrong unit's message.

## 2. The unit

| Field | Value |
|---|---|
| Item id | |
| Title | |
| Arc | |
| Estimate | `XS` / `S` / `M` / `L` / `XL` -- recorded now so `actual` has something to regress on |
| Task class | `mechanical` / `judgment` |

**What done looks like, in one sentence:**

## 3. Acceptance criteria, each with its source

Every criterion maps to a requirement section, a `DEC-NNNN`, or an existing
test. **A criterion with no citable source is an ambiguity by definition** --
raise it before writing code rather than picking a plausible reading.

| ID | Criterion | Source |
|---|---|---|
| AC-1 | | |
| AC-2 | | |

## 4. File surface (the lease)

Exclusive to this unit for its duration. Subagents share a working tree.

```
<paths>
```

**Out of scope, explicitly:**

```
<paths this unit must not touch>
```

**Out-of-scope findings are reported, never fixed.** Record what, where by
repo-relative path, why it matters, and the evidence. In-scope trivial fixes
ride this change; everything else comes back as a finding.

## 5. Decisions in context

Attached `DEC-NNNN` records, in full, and recorded on the run as
`decisions_in_context`. When a builder ignores a ruling, the only question that
matters is whether it ignored it or was never given it.

| Decision | Binds |
|---|---|
| | |

## 6. Environment (G4 -- the worktree venv seam)

| Field | Value |
|---|---|
| Worktree / branch | |
| Interpreter path | pass it explicitly; **never resolve `<repo>/.venv` from the checkout** |
| Known phantom failures | list them -- three agents chased the same seven independently |

## 7. Gates -- run LAST (G6)

After the final edit, immediately before the commit and the hand-back. Never
earlier: a worktree unit has **no CI** between its commit and the transplant, so
a stale green is the only signal this session gets.

```
<gate commands, in order>
```

**Budget-counted docs (G10):** if this unit extends a document that feeds a
model prompt under a size budget, run its budget check and record the measured
number and the headroom.

## 8. Report shape

- **Outcome** -- `pass` / `partial` / `blocked` / `timeout` / `error` /
  `human_required`, with an `error_class` from the closed list if not `pass`.
- **Criteria map** -- each criterion and its source.
- **Gates** -- what ran, at which point in the sequence, and the exact output.
- **Evidence** -- commands, check-run names with conclusions, test counts.
  Evidence over self-report: a summary of a check run is not a check run.
- **Findings** -- out of scope, with paths and evidence.
- **Questions** -- class, blocked criteria, `dependent_scope`,
  `independent_scope`. You propose `partial` or `blocked`; **the Maestro
  decides.**

## 9. Standing limits

- **G3 -- never schedule yourself.** No `send_later`, no timers, no check-ins:
  a subagent's wake-up fires into the parent session. End your run and return.
- **G12 -- never merge and never flip a PR to ready.** Report green and stop.
- You cannot call a sibling agent. Everything is routed through this session.
