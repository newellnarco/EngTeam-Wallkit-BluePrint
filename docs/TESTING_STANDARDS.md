# TESTING_STANDARDS.md

Normative. What a Builder owes in tests, how a test is proven able to fail, how
the static-analysis lane is triaged, and how test shards are measured and
rebalanced.

Every rule here is traceable to a measured incident or to a named principle. A
rule with neither does not belong in this file.

Related: WORKFLOW.md section 5 (definition of done) and section 10 (reviewer
lanes), `.claude/agents/builder.md` (Tests you owe), `.claude/agents/reviewer.md`
(what to reject), `.claude/agents/integrator.md` (rebalance on transplant),
`tools/wall/testkit.py` (the shard tooling), and the per-repo best-practices file
the templates provide (`templates/BEST_PRACTICES.md.template`), which carries the
host repo's own defect classes beside these standards.

---

## 1. One definition

The gate list lives in `.wall/config/wall.json` under `definition_of_done`. This
document explains the items; the config **is** the list. Three drifting copies of
a checklist is how a checklist stops being enforced, so a rule added here that
changes the gate is added there in the same change.

---

## 2. The tier pyramid

Three tiers, three questions:

| Tier | Directory | Answers | Must not |
|---|---|---|---|
| unit | `tests/unit/` | Does this function or class do what it claims, including its degraded branches? | Touch the network, the clock, the box, or a sibling module's internals |
| integration | `tests/integration/` | Do two real modules agree at the seam between them? | Mock the seam it exists to test |
| system | `tests/system/` | Does the contract, config, workflow or document still hold? | Assert behaviour a unit test can decide more cheaply |

**Kit-internal exception.** This kit's own suite is a flat `tests/` of about
eight modules; the tier is carried by each test's subject, not by a directory.
That is the exception, recorded so it is not read as the pattern. A target repo
gets the three directories.

### Required tiers per change class

| Change class | Required |
|---|---|
| Pure module or pure function | unit |
| Cross-module seam (a caller wired to a new collaborator) | unit + integration |
| Contract, config, CI workflow, docs gate, roster definition | system pin (+ unit where there is logic) |
| Bug fix | a regression test **at the tier the bug reached**, landing with the fix |
| New public symbol | at least one test that NAMES it (section 7) |
| New capability | the full triad |

A "system pin" is a test that fails when the artifact in the repository changes
in the way the rule forbids. It reads the real artifact, never a fixture copy of
it: a validator tested only against fixtures is tested only against its author's
assumptions.

---

## 3. Tests must be able to fail

A design property of each test, not a slogan. A green test is evidence of
nothing until it has been seen red for the right reason.

**(a) Every new guard or branch gets a mutation check.** One guard, one row in
the mutation table (section 4). "Guard" means anything whose job is to refuse:
a validation, a range check, a fail-closed default, a boundary, an early return.

**(b) No assertion may be satisfiable by the untouched baseline.** For every new
test, one of two things is recorded: it was watched failing against the
pre-change code, **or** a mutation killed it. One of the two, written down. This
is the only check that separates a test from a description of the code beside
it -- and the pull toward a satisfiable assertion is strongest exactly when the
test was written right after the code, or because a reviewer asked for it.

Ask the polarity question: *what does the un-fixed code return for this input?*
If it returns what you are asserting, the test proves nothing.

**(c) The dead-assertion class.** An assertion whose string is matched elsewhere
in the same output survives deletion of the feature it is named after.
*Measured: reference wave, services-honesty unit -- a closing-line assertion kept
passing after the closing line was deleted, because the same word appeared in the
per-service detail above it.*

The cure is to **assert the UNIQUE artifact**: the exact line, the specific
count, the one field only this code path writes. Three shapes of the same defect:

- `or` in an assertion makes each branch optional. Assert both, on their own
  lines, or delete the one that does not matter.
- A substring is not a member. Only `str` does substrings; tuple and list
  membership compares whole elements, so `"fence" in ("fenced_output",)` is
  always `False` and whatever carries the `or` is what you actually tested.
- A valid name can be a prefix of another valid name. Over any namespace --
  selectors, JSON keys, env vars, node ids, paths -- `in` will eventually match
  a different member, and it fails in the misleading direction: a pass on a
  deleted subject.

Before accepting a red-then-green, ask **what else could be making this
assertion true**: an `any`/`or` over a set, a longer name containing the shorter
one, a fallback path, a second copy of the fixture. Then remove those too, or
narrow the assertion until only the subject can satisfy it.

**(d) Fixtures must construct the edge.** Hand-written fixtures reach for the
happy case; the edges are what nobody constructs. Every fixture set covers, or
states why it cannot: **ties** (equal sort keys -- the tie is the only case where
tuple comparison reaches the second element, and a frozen dataclass has no
`__lt__`), **boundaries** (the threshold value itself, not one either side of
it), **empty**, **malformed**, and **wrong type**.

A fixture that builds its own schema is a second implementation and drifts
toward what the test needs. Import the production definition.

**(e) Hermetic.** No real network, no real model, no host state in the standard
suite. A real-runtime probe is a separate bench, not a unit test.

**(f) Bind every double to its subject's live signature.** Mutation cannot catch
a fake written from the call you just typed rather than from the class it stands
in for: the tests pass, each mutant goes red on cue, and the code raises
`AttributeError` on its first real call. Bind the double's method to
`inspect.signature(Real.method)` and read the real dataclass's fields. The
one-line smell test: a keyword that appears only at its own call site is
invented.

---

## 4. The mutation-check protocol

Verbatim procedure. Deviating from it produces a mutation check that reads green
and proves nothing, which is the same defect class as the tests it is checking.

```
 1. SELECT one guard. One guard = one row. A property defended in two places
    needs BOTH removed, or the claim that either line is load-bearing is a
    claim the code does not support.
 2. COPY the file aside:  cp <file> <scratch>/<file>.mut-<agent_key>.bak
    NEVER a VCS checkout, stash or reset to undo a mutation. A mutation harness
    that shelled out to `git checkout` to revert itself destroyed six
    uncommitted ledger rows. Hold the bytes yourself.
 3. ANCHOR. Assert the text you are about to replace occurs EXACTLY ONCE
    (count == 1, not `in`). A pattern that is absent changes nothing and reads
    exactly like "the code is fine"; a pattern that occurs twice may edit the
    wrong one, and the red then proves only that SOMETHING mattered.
 4. MUTATE. Apply the inverse or breaking edit. Assert the file changed.
 5. PROVE THE GUARD MOVED, not just the file. Exercise the guard and print what
    it now does -- call the function, match the pattern, run the check. A
    mutation that lands in a comment above the pattern changes the file and not
    the guard.
 6. PROVE THE MUTANT IS WHAT RUNS. Clear `__pycache__` between mutants, or
    assert the running module's source contains the mutation. Two writes inside
    one mtime tick let CPython reuse stale bytecode, and the mutant never
    executes while reporting "survived".
 7. RUN ONLY the covering test. Require RED -- and READ the failure. It must be
    the assertion about the guard, not an import error or a collection error.
 8. RESTORE from the copy in step 2.
 9. BYTE-DIFF the restore against the copy (digest compare). "git status is
    clean" is a different question with a different answer.
10. RE-RUN. Require GREEN.
11. RECORD the row.
```

Restore on **every** path, including an interrupted run. A harness that can
leave the tree modified is worse than none.

### The table the Builder reports

| Guard | Mutation applied | Covering test | Result | Restore |
|---|---|---|---|---|
| `select()` rejects index 0 | `if index < 1` -> `if index < 0` | `test_select_rejects_zero` | RED | digest match |

Three outcomes, one pass: **KILLED** (the check works), **SURVIVED** (a finding
about the test, not a nuisance -- ask what else reaches this result),
**ERROR** (the probe could not run, which is never a pass).

A mutation that **no longer applies** -- because the code it targets moved -- is
a failure, not a skip. It silently tests nothing while reading green, which is
the exact false-clean it exists to prevent.

When no mutant can be made to fail, the finding you were about to pin may not
exist. That is worth knowing and worth saying, in preference to shipping a test
that documents a property the code does not have.

---

## 5. SAST and secrets

A static-analysis lane runs on **every PR**: a bandit-class scanner for Python,
the language-appropriate equivalent elsewhere (a security-rule linter for
JS/TS, `gosec`, `cargo audit`). Secrets scanning runs in the same lane.

**Report-only at first.** A lane promoted to blocking wholesale gets disabled on
its first noisy rule, and then nothing runs. So promotion is **per rule**: a rule
with zero standing findings across a full wave is promoted to blocking, and the
promotion is recorded with the date and the measured standing count.

**Triage is the reviewer-lane posture** (WORKFLOW section 10), unchanged:
verify before accepting **or** declining; refute with a parse proof, never by
assertion; decline a suggested fix only with a counterfactual test; a metered or
unavailable lane is **named, not waited on**.

Two rules specific to this lane:

- **A secrets finding is never report-only.** It blocks, and the credential is
  **rotated** -- removing it from the diff does not remove it from history.
- **Every suppression is named and dated with its reason.** A blanket inline
  suppression with no reason is itself a finding. A suppression is a claim that
  a reviewer should be able to re-check.

A finding closed without a prevention -- the rule, the regression test, and the
doc line -- is a finding you will receive again.

---

## 6. Sharding, measurement, rebalance

**Terminology.** "Test shards" here are parallel slices of the test suite. They
are unrelated to the ledger's **event shards** (`.wall/events/<day>/<sid>.jsonl`)
and the two never share a file, a directory or a command.

**Measure.** Every CI test job records per-test durations (`--durations=0`) and
publishes them. A scheduled or on-demand job merges the latest run into the
durations record.

**Balance by measured duration, never by file count.** Without measured
durations a splitter falls back to splitting by test COUNT, and the slow tests
clump: measured, one shard ran about 20 minutes while its siblings finished in 4
to 14. The algorithm is greedy longest-first bin-packing (`testkit.balance`):
longest test first, into the lightest shard, ties broken by a stable field so a
re-run produces the same map.

**The imbalance signal.** Slowest shard greater than **1.5x** the median shard
total triggers a rebalance (`testkit.needs_rebalance`, `>` strictly -- exactly
1.5 is balanced).

**The rebalance process.**

1. A scheduled or on-demand job regenerates the map from the latest durations.
2. It commits the map **through the normal PR path**. No job pushes to the
   default branch directly, and no rebalance rides an unrelated PR.
3. After adoption, measure the **job wall clock**, not the shard totals. Per-test
   duration is a proxy that cannot see fixture setup, module import or a
   subprocess join, so a perfectly balanced split can still be slower. If the
   wall clock did not move, say so and keep the old map.

**The shard map is derived state.** `.wall/config/shards.json` is regenerated by
tooling and **never hand-edited**. A hand-edited derived file is a merge conflict
resolved by picking the side that looks right, which is the resolution this crew
does not do (WORKFLOW section 9, step 2).

**New test files land in the lightest shard by default.** An unmeasured test has
no duration; the lightest shard bounds what one wrong guess can cost until the
next measurement.

**A stale map is honest about being stale.** A map whose test ids no longer exist
is reported as drift, not silently filtered: a shard that quietly runs fewer
tests than it names is a gate that stopped gating.

---

## 7. The new-symbol coverage gate

**Every new public symbol must be NAMED by at least one test, or the push gate
blocks.** It is the one large finding class a machine can decide without
understanding intent, and it is decided before anything is billed.

- Private symbols (leading underscore) and dispatch hooks are excluded by an
  **explicit, reviewable list** -- never by a heuristic nobody can audit.
- **If the gate cannot read the diff or cannot enumerate the tests, it reports
  that it could not decide.** It never reports zero uncovered symbols, because
  "I could not look" and "there is nothing" are different facts and collapsing
  them is a false clean delivered with confidence.

*Measured: this gate fired twice in the reference wave and both times found a
real gap -- a symbol added with no test naming it.*

---

## 8. Gates run LAST

Gates run after the final edit, immediately before the commit and the hand-back
(WORKFLOW section 9, step 5 -- lesson G6). Never earlier. A worktree unit has
**no CI** between its commit and its transplant, so the gate output is the only
signal covering everything that happened.

Quote the output. A summary of a gate is not a gate.

The recurring shape is the derived artifact: appending one test that imports a
new package can stale a generated matrix or shard map that passed ten minutes
ago.

**When the same derived-artifact drift recurs, it graduates out of the
checklist.** A checklist item that is forgotten three times is not a discipline
problem, it is a design telling you where the automation belongs: move the
regeneration into a pre-commit hook or an on-mainline job so the stale state
cannot be committed at all, and the class becomes impossible rather than
remembered. The graduating hook **degrades to a warning, never blocks** -- a
gate that can wedge a commit gets disabled within a week, and then nothing runs.
The reciprocal rule is about repair cost: **a CI failure caused only by a
derived artifact is repaired mechanically -- regenerate, push, re-gate on the
cheap lane** -- never by re-running the full pyramid to re-prove code that did
not change. Confirm the failure really is derived-only by reading which check
failed and on which paths; a derived-file red beside a source-file red is a
source-file red.

---

## 9. What the Reviewer rejects

The list is in `.claude/agents/reviewer.md`. It is short by design: an assertion
satisfiable by the untouched baseline, a new guard with no mutation evidence, a
hand-edited shard map, an unaddressed SAST finding, and a gate run before the
final edit.
