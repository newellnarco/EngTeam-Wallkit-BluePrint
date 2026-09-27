# REVIEWER_LANES.md -- the kit's own review lanes

> Every automated review lane this repository has had, in effect or not. A
> lane is a **lane, not an authority**: it advises, and the authority matrix
> decides. Built from `templates/REVIEWER_LANES.md.template`, the same file
> every adopting repository starts from. Per-vendor meter facts live here,
> once (`docs/WORKFLOW.md` section 10 holds the postures every lane shares).

---

## 1. Lanes at a glance

| Lane | State | Since | Verdict / exact disqualifier |
|---|---|---|---|
| CodeRabbit | in effect | 2026-09-22 | Line-anchored findings on the kit's code and tests; many accepted findings are cited in the suite |

Copilot review also ran on PR #8. Its block is still owed
(`KNOWN_ISSUES.md`, KI-2026-09-22-e).

---

## 2. Per-lane block

### CodeRabbit

- **State:** in effect, since 2026-09-22 (PR #8)
- **Triggers:** the opening push of a ready (non-draft) pull request only.
  Later pushes are reviewed only when asked, through
  `tools/review/coderabbit-review.sh`. Config: `.coderabbit.yaml`
  (`reviews.auto_review`: `auto_incremental_review: false`,
  `auto_pause_after_reviewed_commits: 1`, `drafts: false`).
- **Scope:** the whole tree, except lockfiles, build output, minified files,
  snapshots, images, and generated output (`.ast-grep/rules/generated/`,
  `.ast-grep/rule-tests/generated/`, `sample/.wall/derived/`), which is
  derived and never edited by hand.
- **Instruction files:** none beyond `.coderabbit.yaml`.
- **Meter shape:** a **throttle** (it reopens after a window). Reviews refill on
  a rolling hour; sustained activity over the last 24 hours or 7 days lowers
  the refill rate (the Fair Usage "slow lane"), and only reviewing less brings
  it back. Measured here: the limit hit on PR #8 was 2 reviews per hour after
  the account's spending cap (KI-2026-09-22-e). Source:
  <https://docs.coderabbit.ai/management/rate-limits>.
- **What spends the meter:** **one review per push, not per commit.** A push
  that lands while a review is running (about 5 minutes) supersedes it, and the
  superseded review is still charged. Web-UI edits, the Update branch and
  Resolve conflicts buttons, a force-push, rebase or reopen, marking a draft
  ready, and every `@coderabbitai review` each count as one.
- **What a rate limit looks like:** a CodeRabbit **comment** plus a **passing**
  check titled "Review rate limited". Never HTTP 429, so automation must read
  the comment, and a green check here is UNKNOWN, not a pass
  (`docs/WORKFLOW.md` section 10, review-meter economics).
  `@coderabbitai rate limit` reports the remaining allowance **without**
  spending a review.
- **Reviews drafts:** NO (DEC-0013). Open as a draft while iterating, mark it
  ready once.
- **Caps and measured ceilings:** 2 reviews per hour, measured on PR #8.
- **Standing rules for this lane:**
  - Batch fixes into one push, and do not push for about 5 minutes after a
    review starts.
  - Ask for a re-review only through `tools/review/coderabbit-review.sh`
    (below), never with raw comments in a loop. An agent or tool that asks
    another way follows the same logic: check for a running review first,
    honour the rate-limit comment (its wait time, else exponential backoff with
    jitter), at most one request per push, a retry cap, and never a
    re-request on a timer.
  - A lane that gives up or stays rate-limited is **named in the report, not
    waited on**; it never holds the pull request.
- **Delivery format:** anchored, replyable review threads plus a summary
  comment.
- **Skip rules, classified:** `drafts: false`, `ignore_title_keywords`
  (`WIP`, `[skip review]`, `[no review]`) and `ignore_usernames` (dependabot,
  renovate, github-actions bots) are pre-dispatch gates. `path_filters` narrow
  what is read, and are not yet verified as meter-saving.
- **Expected rejections:** "Review rate limited", "review skipped" on a draft
  or an ignored title. Each is the lane working; re-run at most once.
- **Channel verification:** no canary run yet.
- **Compute and billing:** CodeRabbit's hosted runners; no CI minutes.
- **Disjointness rationale:** reads the diff as a whole-file reviewer; the
  scan lane and the suite do not.
- **Owner actions owed:** none.

### Asking for a re-review: `tools/review/coderabbit-review.sh`

```bash
tools/review/coderabbit-review.sh <pr>            # waits for a running review, honours a rate-limit notice, then asks once
tools/review/coderabbit-review.sh <pr> --full     # full re-review
tools/review/coderabbit-review.sh <pr> --status   # "@coderabbitai rate limit" (free), at most once an hour
tools/review/coderabbit-review.sh <pr> --dry-run  # everything except posting
```

Needs `gh` (authenticated) and `jq`. Environment: `CR_MAX_RETRIES` (4),
`CR_BASE_DELAY` (120 s), `CR_MAX_DELAY` (3600 s). It exits 1 after the retry
cap. It is the kit's own tooling, like `tools/quality/`, and is not vendored by
`bootstrap`. An adopting repository that runs a CodeRabbit lane copies
`.coderabbit.yaml`'s `reviews.auto_review` keys and this script, and records the
lane here through `/reviewer-integration add`.

---

## 3. Standing rules that apply to every lane

The template's section 3 applies unchanged: verify before accepting or
declining, a metered lane is named and not waited on, one writer per thread,
and do not end the head a review is reading.

---

## 4. History

| Date | Lane | Change | Why |
|---|---|---|---|
| 2026-09-22 | CodeRabbit | added | Reviewed PR #8; hit its hourly limit mid-PR (KI-2026-09-22-e) |
| 2026-09-27 | CodeRabbit | throttled | Review the opening push only, skip drafts, re-review on request through the script, so fix-push loops stop spending the allowance |

---

## 5. Salvage

| Finding class the dead lane covered | What covers it now |
|---|---|
| (no lane cancelled yet) | |
