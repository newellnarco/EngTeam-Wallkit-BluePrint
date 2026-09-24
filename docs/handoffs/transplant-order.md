# Transplant order -- TEMPLATE

> **G11 / G13.** The first wave ran this procedure five times by re-sending a
> long hand-written brief, and it drifted each time -- once mis-stating a file
> location. This is the order form for one unit's own branch and PR. Under
> DEC-0016 other units' PRs may be open at the same time on disjoint leased
> surfaces, but merges are serialized by the Maestro: the rebase onto the moved
> `main` that precedes each merge is handed out **one at a time**. A host whose
> standing rules mandate a single designated branch runs single-slot mode.
>
> The procedure itself is `.claude/agents/integrator.md` and `WORKFLOW.md`
> section 9. This document supplies the values; it does not restate the steps.

---

## 1. The unit

| Field | Value |
|---|---|
| Integrator agent key | usually the unit's own Builder wearing the Integrator hat |
| Item id / title | |
| `trace_id` | |
| Worktree or source branch | |
| Unit commit SHAs | |
| Declared path scope | the diff must contain these paths and nothing else |

## 2. Target

| Field | Value |
|---|---|
| Designated ref (this unit's PR branch; the host's single designated branch in single-slot mode) | |
| Designated ref SHA **before** the transplant | required for `--force-with-lease` |
| `main` SHA at the start | |
| Merge base | |

Record all three before touching anything. They are the safety proof's inputs
and the rollback's only anchor.

## 3. Commit identity (G1)

```
git -c user.name="NAME" -c user.email="EMAIL" ...
```

**Never `git config`.** It is repo-global; a rebase re-authors every commit in
the unit, so getting this wrong here corrupts the whole unit's authorship rather
than one commit.

Temp files are keyed by agent key (G2): `proof-<agent_key>.diff`,
`commitmsg-<agent_key>.txt`.

## 4. Derived files -- regenerate, never hand-merge

Every conflict in one of these is resolved by taking either side and re-running
its generator. Two conflicts in the first wave were exactly this shape (a
compactor had consumed fragments upstream) and both resolved mechanically.

| Derived file | Regeneration command |
|---|---|
| | |
| | |

A conflict in a **source** file is a real conflict: resolve with the unit's
intent, then re-run the unit's tests over the resolved region. A resolution that
changes behaviour the tests do not cover is a finding, not a judgement call.

## 5. The safety proof (step 3 -- before any push)

1. Diff designated-ref vs `main`, **filtered to the declared path scope**.
   Every hunk must be this unit's work.
2. Diff designated-ref vs `main`, **excluding** the declared path scope.
   **This must be empty.**
3. Non-empty means the ref is carrying someone else's unmerged work or a stale
   copy of merged work. **Stop. Do not push.** Report the exact paths and both
   SHAs; this is a `blocked` outcome and the Maestro's call.

| Field | Value |
|---|---|
| Command 1 | |
| Command 2 | |
| Result | `in-scope only` / `NON-EMPTY -- blocked` |

Push only with `--force-with-lease` carrying the SHA from section 2.

## 6. Budget re-check (G10)

The rebase brought other units' additions into the same counted sections, so the
measurement the unit took pre-rebase is stale. Four units nearly blew one budget
at once for exactly this reason.

| Budget-counted doc | Check command | Measured | Limit | Headroom |
|---|---|---|---|---|
| | | | | |

## 7. Gates -- LAST (G6)

After the rebase, after the regeneration, after the budget re-check. Immediately
before the commit and the push.

```
<gate commands, in order>
```

Quote the output in the report. A summary of a gate is not a gate.

## 8. The draft PR

Open as a **draft**. Body must carry: the unit and item id, what changed and
why, the acceptance criteria with sources, the gate output, the safety-proof
result, and the budget numbers.

| Field | Value |
|---|---|
| Title | |
| Base | |
| Labels / links | |

## 9. Review threads (G7 / G8)

- The unit that owns the PR owns its threads. **One writer per conversation.**
  The coordinator takes a thread only by telling the unit first -- see
  `review-thread-takeover.md`.
- Verify every finding against the actual file **before accepting or
  declining**.
- Truncated-diff findings are a registered class: refute with a **parse proof**,
  never an assertion.
- Declining with a better fix requires a **counterfactual test**.
- A metered lane out of quota is **named, not waited on**.

## 10. Hand back -- green, not merged (G12)

| Field | Value |
|---|---|
| Check runs | names **with conclusions**, read from the check runs themselves |
| Full pyramid or draft-scoped subset? | say which; a draft-scoped green is not the pyramid |
| Safety proof | result + both SHAs |
| Threads | each with state: answered / refuted with proof / declined with counterfactual / owned elsewhere / lane unavailable |
| Still open | |

Then end the run. **The Maestro flips ready and merges.** Bookkeeping follows
the merge immediately: item state flips at merge time, not at compaction time
(G9) -- otherwise the wall claims "in CI" on a merged PR and the next unrelated
unit inherits the mess.
