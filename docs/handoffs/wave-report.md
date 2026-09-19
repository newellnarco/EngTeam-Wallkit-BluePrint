# Wave report -- TEMPLATE

> **G14.** The status stream is part of the loop, not decoration: the owner
> watched it live and course-corrected twice mid-wave. Emit this after every
> dispatch, every completion, and every collection pass -- not only at the end
> -- and **export the same three sections** so the wall updates on the
> transition. The timer is the fallback, not the trigger.
>
> Three sections, bullets, no narration. Prose about work in progress is tokens
> that buy nothing the wall does not already carry.

---

**Wave:** ____   **Cycle:** ____   **At:** `<ISO-8601 UTC>`
**Wall:** courier last run `____`, heartbeat `fresh` / `STALE -- numbers below
are suspect`

---

## COMPLETED

Only merged or landed artifacts. **Never a claim.** A unit reporting itself
done is not a completion; a merged PR is.

- `ITEM-___` -- PR #___ merged -- one line on what it did
- `ITEM-___` -- decision `DEC-____` written -- one line
- `ITEM-___` -- design landed at `<path>` -- one line

## IN PROGRESS

Every live agent, its unit, its stage, and the head-count against caps.

| Agent (key / name) | Role | Unit | Stage | Since |
|---|---|---|---|---|
| | | | building / tests / reviewer / transplant / PR in CI / awaiting merge slot / researching | |

**Head-count:** builders _/4, reviewers _/2, researchers _/6. PR slot: `ITEM-___`.

**Stale (evidence, not self-report):** any run past its deadline with no
terminal event reads `stale` regardless of what it last claimed. List them here
with what you are doing about it.

## NEW

Everything that entered the system since the last cycle.

- **Findings** -- from `<agent>`: what, where (repo-relative path), disposition
  (filed as `ITEM-___` / dispatched / declined with reason)
- **Questions** -- `q_____` class `______`, blocks AC-_, outcome `partial` /
  `blocked`
- **Decisions** -- `DEC-____`, and what it supersedes
- **Items claimed** from the backlog
- **Integrity flags** raised by Courier or the Foreman
- **BLOCKED ON THE HUMAN** -- call these out first; they are the only thing in
  the report that cannot progress without someone reading it

---

## Export

Write the same three sections atomically (temp file then rename, so a reader
never sees a partial), then run Courier so the wall reflects this transition
immediately.

| Field | Value |
|---|---|
| Snapshot path | |
| Written at | |
| Courier run | `ok` / `failed -- say so in the report` |

## Closing cycle only

- [ ] Every status vetted against ground truth, not against what an agent said
- [ ] Every open question answered, escalated with a reason, or on the human
      queue -- none silently dropped
- [ ] Every finding dispatched, filed, or explicitly declined with a reason
- [ ] Leases released
- [ ] A `run_end` for every `run_start` (`wall doctor` proves it; the
      SubagentStop hook writes them)
- [ ] Budget actuals recorded against estimates
- [ ] **What the next wave should start with:**
