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
   runner-minutes/month).
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

## `baseline <lane>`

Re-run discovery + diff (add steps 1-4) without changing triggers: reports
where the lane's live config has drifted from the shared body, and
regenerates it. Run it after any bulk edit to the standards file.

## `learn` -- the collective long-term learning loop

Findings must outlive the PR they were raised on, for every kind of reviewer
at once:

1. **Every real finding lands in the findings ledger** (append-only,
   `docs/REVIEW_FINDINGS.md` or the host's equivalent): the finding, the
   lane that raised it, verified-or-refuted, and the prevention.
2. **A recurring class graduates** -- in the same change: a rule in the
   shared criteria body, an entry in `FAILURE_PATTERNS.md`, a regression
   test where one is possible, and a checklist line if the class is
   pre-ship-checkable. That is how the *agents* learn.
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

## Boundaries

- This skill edits review configuration and criteria documents. It never
  edits CI to make a lane pass, never disables a required check to unblock a
  merge, and never grants a lane merge or approval authority -- lanes advise,
  the authority matrix decides (WORKFLOW section 7).
- Adding/removing a lane and widening its triggers are engineer decisions;
  everything else here is autonomous.
- The Reviewer subagent is not a lane and is not managed here; it is part of
  the roster (AGENT_ROSTER_SPEC.md).
