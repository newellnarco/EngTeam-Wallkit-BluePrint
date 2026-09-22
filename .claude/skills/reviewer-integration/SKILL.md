---
name: reviewer-integration
description: Add or remove an external PR/code reviewer (CodeRabbit, Qodo, Copilot review, Gemini, a self-hosted PR-Agent, ...) as a review lane. Imports the reviewer's existing files and settings to establish a baseline, incorporates its rules into the shared criteria, registers the lane's posture and budget, and wires the finding-to-prevention loop so agents, the LLM roster and the external reviewers all learn from the same record. Invoke as /reviewer-integration add <lane> | remove <lane> | baseline <lane> | learn.
---

# reviewer-integration -- external review lanes, added, removed, and learned from

An external reviewer is a **lane, not an authority** (WORKFLOW.md section 10). This
skill is the one procedure for attaching one, detaching one, and -- the part
that compounds -- making every lane's findings feed one shared body of criteria
so the same defect class is never re-learned per grader.

**The one-body-of-criteria rule, stated up front.** The repo's coding
standards file (`BEST_PRACTICES.md` or the host's equivalent, per the adoption
runbook) is the primary record. Every grader -- the Reviewer subagent, hosted
reviewers, CI lint -- reads that body through its own native mechanism. Rules
are written once and *mirrored* into each reviewer's config, never authored
separately per reviewer: two independently-evolving rule sets is how one
grader keeps making a mistake the others already learned.

## `add <lane>`

1. **Discover what the reviewer already has.** Search the repo for the lane's
   native files (e.g. `.coderabbit.yaml`, `.github/copilot-instructions.md`,
   a PR-Agent workflow + config, `best_practices` knowledge-base entries).
   Also list the lane's settings that live *off*-repo (app dashboard,
   org-level config) and ask the engineer to export or paste them -- the repo
   cannot derive what it does not hold.
2. **Establish the baseline.** Record, in `docs/decisions/` as one DEC:
   the lane's name, trigger events (every push? open/ready only?), the paths
   it reviews, its instruction files, and its metering (quota, rate limit,
   cost). Trigger scope is a cost decision the engineer confirms -- reviewing
   every synchronize on a busy repo is a measured waste (the reference
   deployment cut a lane from every-push to open/ready and saved ~1,200
   runner-minutes/month). **Record the lane's meter SHAPE beside its metering:
   a throttle reopens after a window, a hard stop does not reopen until the
   period rolls** -- the two demand opposite reactions, and a lane whose shape
   is unrecorded gets waited on when it will never answer (WORKFLOW section 10,
   review-meter economics). Write the lane's block into the repo's
   **`REVIEWER_LANES.md`** (from `templates/REVIEWER_LANES.md.template`) as
   part of this step: state, triggers, meter shape, caps, standing rules, and
   any owner action owed - the config records the wiring, that file records the
   reasons.
3. **Import its rules INTO the shared criteria -- not beside them.** Diff the
   reviewer's imported rules/policies against the standards file. A rule the
   body lacks is added *to the body* (with the lane named as its source); a
   rule that contradicts the body goes to the engineer as a question, never
   silently either way. Then regenerate the lane's native config *from* the
   body's rules.
4. **Verify each reviewer actually loads each rule -- with a probe, not a
   glance.** Config scoping is where this silently fails: a rule entry can
   parse cleanly and govern nothing (measured: a directory-scoped guideline
   entry under `.github/` governed only `.github/**`, so rules targeting
   the backend never reached that grader -- it parsed fine and did nothing).
   Open a throwaway PR containing one deliberate violation per imported rule
   and confirm each lane flags it. A rule no lane flags is not integrated,
   whatever the config says.
5. **Register the instruction files as budgeted.** Every file a reviewer
   loads into its prompt goes in `BUDGETED_DOCS.md` with the lane's hard
   limit and a measuring command. Hosted reviewers fail closed at their cap,
   on whatever PR happens to be in flight (measured: an instruction file at
   ~80% of one lane's token cap failed every review until carved down).
   **Vendor caps can silently revert a lane to its defaults**, so measure the
   ceiling and print the headroom rather than assuming the config held: past
   the cap a reviewer may reject the whole configuration, keep posting reviews,
   and apply none of your rules - which looks exactly like a working lane.
6. **Write the lane's posture** into the WORKFLOW section 10 table: verify before
   accepting OR declining; truncated-diff findings refuted with a parse
   proof; declining-with-better-fix needs a counterfactual test; a metered
   lane that cannot answer is named in the report, never waited on; one
   writer per thread.

## `remove <lane>`

Removal is the add, reversed, plus the part everyone forgets:

1. Confirm with the engineer (an outward-facing integration change -- an
   engineer-class decision, SESSION_LIFECYCLE section 4).
2. Delete or disable the lane's native config and triggers; record the
   removal as a DEC superseding the add.
3. **Rules the lane contributed STAY in the shared body** -- they were
   adopted on their merits and other graders enforce them. Strike only the
   lane's posture row and its budget registrations.
4. Sweep open PRs for threads owned by that lane; close each with a
   disposition (silence is not a disposition), and reassign any pending
   required check so the merge gate cannot wait forever on a lane that will
   never report.
5. **Record the cancellation in `REVIEWER_LANES.md`**: flip the lane's state,
   write the **exact disqualifier** (a re-checkable fact, never "did not work
   out"), list the owner actions still owed, and fill its salvage row naming
   what now covers the finding classes that lane used to catch. The dead lane's
   block stays in the file so the next session does not re-adopt it by amnesia.

## `baseline <lane>`

Re-run discovery + diff (add steps 1-4) without changing triggers: reports
where the lane's live config has drifted from the shared body, and
regenerates it. Run it after any bulk edit to the standards file. **Reconcile
`REVIEWER_LANES.md` in the same pass** - meter shape, measured ceiling and
headroom, triggers, owner actions still owed - and report any row that the
live configuration contradicts rather than quietly rewriting the record.

## The canary - proving a guideline file is READ, not merely present

A lane can load a rules file, parse it cleanly, and govern nothing. Config
scoping, a vendor cap, a stale cache and a directory-scoped entry all produce
the same symptom: reviews keep posting and none of your rules are applied. The
canary is the instrument that separates "the file is configured" from "the file
was read on this diff".

1. **Plant arbitrary, token-free rules.** Each canary rule requires a short
   phrase that cannot be derived from general knowledge about the code, and the
   required text must NOT contain the canary's own identifier - otherwise
   removing the rule leaks the identifier into the diff and the lane can echo
   it without ever having read the file.
2. **One in the FIRST guideline file, one in the LAST.** Both firing is the
   only evidence that the whole list loads rather than the first entry.
3. **Pre-register the expected readings BEFORE the result arrives.** Write down
   what each outcome would mean - both fire, only the first, only the last,
   neither - and then run it. A reading interpreted after the fact is a story
   about whatever happened.
4. **Run an asymmetric round: break only ONE of the two.** A lane that still
   names the intact rule is reading; a lane that names the broken one, or names
   both unchanged, is recalling or replaying rather than reading this diff.
5. **A lane that misses its canary is treated as NOT loading the file**,
   whatever its own status check says. The check reports that the lane ran; the
   canary reports that the rules arrived, and only the second one is the claim
   being made.
6. **State the instrument's limits beside its result.** It cannot separate a
   config channel from ordinary file reading, and it is **invalid on any diff
   that touches the criteria files themselves** - the lane can read the rule
   out of the diff. Re-run canaries after any bulk edit to the shared body, on
   a diff that does not include it.

## `learn` -- the collective long-term learning loop

Findings must outlive the PR they were raised on, for every kind of reviewer
at once:

1. **Every real finding lands in the findings ledger** (append-only,
   `docs/REVIEW_FINDINGS.md` or the host's equivalent): the finding, the
   lane that raised it, verified-or-refuted, and the prevention.
2. **A recurring class graduates** -- in the same change: a rule in the
   shared criteria body, an entry in `FAILURE_PATTERNS.md`, a regression
   test where one is possible, and a checklist line if the class is
   pre-ship-checkable. That is how the *agents* learn. Where the class has a
   shape a scanner can see (a code construct, a secret format, an
   instruction pattern), the same change adds the scanner's entry and its
   fixture (`docs/SCAN_LANE.md`), so the next instance is caught at the push,
   before a CI minute or a hosted review is spent on it.
3. **The mirrors regenerate** so every external lane's native config carries
   the new rule (step 3 of `add`, re-run). That is how the *external
   reviewers* learn.
4. **Refutations are preventions too.** A false-positive class (e.g. a lane
   reporting its own diff truncation as a file defect) gets a posture line
   naming the class and the required proof, so the next wave refutes it in
   one reply instead of re-litigating it.
5. **Close the loop on the lane's side**: reply and resolve on the lane's
   own threads with the verdict and the proof -- reviewer products tune on
   outcome signals, and a thread left dangling teaches the lane nothing.

Run `learn` at wave close (SESSION_LIFECYCLE section 3) over the wave's accumulated
findings; the wave report links the ledger entries it graduated.

### The roll-up -- every N merged pull requests

Graduating findings one at a time fixes instances. The roll-up is what finds
the *shape* of what this repo keeps getting wrong, and it only works on a
cadence, because a pattern is not visible inside a single PR.

1. **Cadence.** Every **N merged pull requests** (default **10**; set it in
   config so it is one number, not a habit). Missing a roll-up is recorded, not
   skipped silently -- the next one covers the wider range.
2. **Collect ALL findings, including the ones that lost.** Applied, declined,
   and **false-positive** alike. A corpus of only-accepted findings measures
   the lanes' agreeableness, not the code's defects, and it hides the noise
   axis entirely.
3. **Pareto by category.** Group into defect categories, sort by count, and
   read the top of the list. The vital few categories are where a prevention
   pays for itself; the long tail is where a prevention costs more than the
   defect.
4. **Promote the vital few** through the normal graduation path (step 2 above):
   rule in the shared body, `FAILURE_PATTERNS.md` entry, regression test,
   checklist line.
5. **Reviewer noise is a lane-configuration trigger, not a rule.** A category
   dominated by false positives from one lane does NOT become a standard --
   writing a rule to appease a mis-scoped grader teaches the crew a fiction.
   It becomes a lane-config tuning task (`baseline <lane>`), and if the lane
   cannot be tuned, an engineer question about keeping it.
6. **A category recurring across TWO consecutive roll-ups escalates to a
   structural closer.** Recurrence after a prevention means the prevention was
   advisory; the escalation is something mechanical -- a lint rule, a CI gate,
   a type, a deleted affordance -- that makes the class impossible rather than
   discouraged.
7. **Track the cost axis beside the quality axis.** Count, per roll-up:
   **review rounds per merged PR**, **review restarts we caused** (a push while
   a review was in flight), and **rate-limit or quota hits per lane**. Quality
   findings tell you what to fix; these three tell you whether the review
   system itself is getting cheaper or more expensive, which nothing else
   measures.

The roll-up's output is one section appended to the findings ledger: the date,
the PR range, the category table, what was promoted, what was declined as
noise, and the three cost numbers.

## Boundaries

- This skill edits review configuration and criteria documents. It never
  edits CI to make a lane pass, never disables a required check to unblock a
  merge, and never grants a lane merge or approval authority -- lanes advise,
  the authority matrix decides (WORKFLOW section 7).
- Adding/removing a lane and widening its triggers are engineer decisions;
  everything else here is autonomous.
- The Reviewer subagent is not a lane and is not managed here; it is part of
  the roster (AGENT_ROSTER_SPEC.md).
