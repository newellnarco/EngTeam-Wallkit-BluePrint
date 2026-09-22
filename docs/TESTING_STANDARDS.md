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

## 1b. Two lineages, five families

Every expected test serves one of two lineages, and the story names which:

| Lineage | Derives from | Proves | Cites |
|---|---|---|---|
| **Validation** | The product outcome — the intake answers and the story's acceptance criteria | The built thing does what the user needed | PRODUCT_INTAKE.md answers, the story's `AC-n`, the named trajectory (UX_STANDARDS.md §2) |
| **Verification** | The architecture and technical design | It is built as designed — contracts, invariants, boundaries hold | The `docs/architecture/` section, the `DEC-NNNN`, the schema |

The two catch different failures: validation catches "built as specified, not
what was wanted"; verification catches "wanted, but not built as designed".
A suite that is all verification proves a design nobody asked for; all
validation proves outcomes on an architecture nobody can maintain. The story's
test expectation (ITEM_AUTHORING §4) names the lineage per expected test so
the gap is visible at authoring time, not at post-mortem.

On top of both lineages, five **non-functional families**. The Architect
declares, per arc, which apply — and a family declared inapplicable is a
recorded declaration with a reason, never an omission:

| Family | Applies when | The tests |
|---|---|---|
| **Guardrails** | The arc touches an autonomy grant, a role gate, a ceiling | Prove the refusals refuse: the forbidden call errors, the gate blocks, the override window works — fixtures that must fire and must not |
| **Data integrity** | The arc touches persistence, migration, or a destructive trajectory | No loss or corruption on the named trajectories; migrations proven forward and (where claimed) back; the no-silent-data-loss sweeps (UX_STANDARDS §3) |
| **Security** | The arc's risk tier is `in-scope` (ITEM_AUTHORING §3) | The Warden's criteria as tests where testable, plus the standing SAST/secrets lane (§5) — a tier-declared arc without its security tests fails Gate 1, not review. Test DATA is in scope too: fixtures and seeds obey the Warden's checkpoint-4 verdicts (`DATA_PROTECTION.md` §4) — production data never becomes test data by convenience, and a fixture with real PII is a finding whoever wrote it |
| **Scalability** | The design states a volume, concurrency or growth boundary | Boundary tests at the stated numbers — the limit is exercised, not believed |
| **Performance** | A budget exists, or the change's benefit is speed | The TECH_EVALUATION law verbatim: the measurement that shows the benefit, baseline first — no baseline means the change is not designed yet |

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

**(g) Flaky is broken.** A test that passes and fails over the same code is not
a weak test, it is a test whose result is not evidence — and it costs more than
a missing one, because it trains everyone to re-run rather than to read. It is
**fixed or quarantined with a work item the day it flakes**, never left in the
suite cycling red-green-red. A quarantine with no item is a deletion with extra
steps.

**(h) Every defect the owner finds by hand converts into a guard.** The owner's
own use is the tier no runner can reach — real hardware, real data, real
"does this feel right" — and a fix that closes one of its findings with nothing
but the fix leaves the tier exactly as loaded as it was. Each one closes with
**more** than its repair: the regression pin, and a guard over the class so the
next member is found by the suite. The trajectory is deliberate and
measurable — owner-found becomes self-found — and a repository where it is not
happening is one where the owner is the test suite.

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

Four properties of the harness itself, which is code and gets none of the
attention code gets because it feels like scratch. Its failure mode is not
silence; it is a confident wrong verdict printed next to its own disproof.

- **Derive the anchor from the file, never from memory.** Read the line, then
  mutate the bytes you just read. Recall holds meaning, not byte sequences, and
  fault injection is a byte operation — an anchor typed from memory that
  "worked" before was one where the two happened to coincide.
- **An injection that changes nothing is an ERROR that aborts the sweep**,
  never a row in the results. "Not caught" and "never applied" are
  indistinguishable in the output and opposite in meaning, and the second one
  reads as a clean bill of health for a probe that did not run.
- **Attach the verdict to the exit status.** A sweep that prints its findings
  and exits zero is decoration: nothing downstream can fail on it, so nothing
  downstream does.
- **Break the call site as well as the function.** A correct, well-fixtured,
  unreachable function passes every mutation aimed at its body. Mutate the
  wiring too, or the sweep proves the code is right about a question nobody
  asks it.

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

### 4.1 The probe roster -- mutation is a standing muster, not a one-shot

A mutation check run once proves the test could fail **that day**. Tests get
refactored, renamed, narrowed and accidentally decoupled from the thing they
defend, and none of that shows up as a red: the suite stays green while the
frontline quietly empties. So every probe that matters is **recorded in a
roster and re-mustered on a cadence in CI**.

**The roster.** One machine-readable file (`docs/mutation_probes.json` or the
host's equivalent), one record per probe:

```
id          stable: MP-<NNN>
target      the file and the exact anchor text (asserted to occur ONCE)
mutation    the precise edit applied
tests       the covering test ids to run
why         the defect class this probe claims to catch -- one sentence
```

**The `why` is not decoration.** A probe whose `why` is "checks the guard"
cannot be evaluated when it later survives, because nobody can say what was
supposed to have been caught. The `why` names the defect the probe is standing
guard against, in the terms the failure registry uses.

**The muster.** A scheduled or per-wave CI job runs the whole roster through the
section 4 protocol -- copy aside, anchor, mutate, prove the mutant is what runs,
run only the covering tests, restore, byte-diff, re-run -- and reports one row
per probe.

Three readings, one pass:

- **KILLED** -- the covering test failed on the mutant. The probe still guards.
- **SURVIVED** -- a **finding about the test**, filed like any other. Something
  that used to be load-bearing no longer is: the test narrowed, the code moved,
  or a second path now satisfies the assertion.
- **ERROR** -- the probe could not run (anchor absent, anchor duplicated,
  tests uncollectable). **Never a pass.** An anchor that no longer matches is
  a probe testing nothing while reading green, which is the exact false-clean
  the roster exists to prevent.

**Mutate through the artifact the tests actually read.** Where the suite runs
against a build, a bundle, a generated file or a bytecode cache, a source-only
mutation proves nothing -- the tests never saw it. **The derived artifact is
rebuilt after the mutation and before the run, or the probe does not count**,
and the roster records which artifact each probe goes through.

A recurring class in `FAILURE_PATTERNS.md` carries a **`> class-guard:`** line
naming the assertion that fails when any member of the class recurs; that guard
is itself a roster probe, so CI requires it to exist, to run, and to have a
mutation proving it can fail.

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

### 5.1 The structural-scan lane: ast-grep, SkillSpector, gitleaks, ruff S, actionlint, zizmor

The kit's own instance of this lane, and the shape a host copies. Six scanners,
one script -- `tools/quality/scan.sh` -- run identically in three places:

| Where | Mode | Blocks on |
|---|---|---|
| CI, every PR and push to main (`ci.yml`, job *Structural and security scans*) | `ci`: a missing scanner fails | promoted rules, always-block ids, drift |
| pre-push hook (`tools/git-hooks/pre-push`) | `local`: a missing scanner warns through | the same, when the scanner is installed |
| A builder's gates-last step (G6) | `local` | the same; the output is quoted in the report |

**ast-grep** runs structural rules from `sgconfig.yml`: hand-written rules in
`.ast-grep/rules/kit/`, and rules **derived from the failure registry** in
`.ast-grep/rules/generated/`. A registry entry that can be caught structurally
carries a fenced `ast-grep` block (the rule) and a fenced `ast-grep-test`
block (its `valid:` and `invalid:` cases, the `VARIANT:` among them).
`tools/wall/quality.py rules` regenerates the derived rules from
`FAILURE_PATTERNS.md` and `KNOWN_ISSUES.md`. **The rules can never drift from
the registry:** the pre-commit hook regenerates and re-stages them whenever
either file changes, and CI and the kit suite run `rules --check`, which fails on
a missing, stale or orphaned rule. `ast-grep test` runs every rule against its
`invalid:` cases first, so a rule nobody can watch go red never reaches the scan.

**SkillSpector** scans the agent surface (`.claude/skills/*`, `.claude/agents`,
`.claude/hooks`) in static mode (`--no-llm`): no API key, no file content
leaves the runner, and the same answer on every run. Its semantic mode is an
LLM call, and that makes it a data-use decision for the Warden, not a per-PR
default.

**gitleaks** scans the full git history (CI checks out with `fetch-depth: 0`)
and always blocks. **ruff's `S` rules** (the bandit set) cover `tools/` and
`.claude/hooks`. **actionlint** and **zizmor** (`--offline`) cover
`.github/workflows`; actionlint is promoted whole from day one, because what
it reports fails on the first run anyway. The kit's own workflows pin every
action to a commit SHA, keep checkout credentials unpersisted, and grant
permissions per job, so zizmor starts at zero.

**The lane grows with every finding.** Each scanner reads support files that
gain one entry per verified finding: registry blocks for ast-grep, custom
rules in `.gitleaks.toml`, YARA rules in `.skillspector/yara/`, and the
promotion record. Each custom rule ships with a fixture that must trip it,
and the lane fails when one stops tripping. How to build and maintain those
files is `SCAN_LANE.md`.

**Promotion is recorded, not edited in.** Every rule is authored
`severity: warning`. Promoting one adds an entry under `promotions` in
`tools/quality/quality.json` with its date, its measured standing count (zero)
and the reason, and `scan.sh` applies it with `--error=<id>`. A rule file
that sets `severity: error` directly is a promotion with no record, and the
kit suite refuses it. Two classes block from day one: SkillSpector's
secrets-class ids (`PE3`, `E2`, `TT3`; a secrets finding is never
report-only), and a `DO_NOT_INSTALL` recommendation.

**Latest without floating.** The blocking job runs **pinned** versions. The
weekly `scanner-bump` workflow installs the latest releases, runs the full lane
on them as a canary, and opens a draft PR that moves the pins and names the
rollback (`UPGRADE_DISCIPLINE.md`). New upstream rules arrive report-only and
are triaged on that PR.

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

## 8.5 The blast-radius matrix

Numbered 8.5 so the reviewer-rejects section keeps the number other documents
cite. The matrix is the artifact that lets a scoped run be responsible: it says,
per area of the repository, what a change there can break and therefore what
must run.

| Area | Primary tests | Blast radius | Must verify | Fast-track eligible |
|---|---|---|---|---|
| `<AREA_PATH>` | `<TEST_IDS>` | the modules that import it, derived | `<INVARIANT>` | yes / no |

Five rules keep it honest:

1. **The blast radius is DERIVED from the real import or dependency graph,
   never remembered.** A hand-written radius agrees with the author's mental
   model and with nothing else, and it is wrong in exactly the direction that
   feels safe. Regenerate it from the graph and diff.
2. **Name the dependency cores.** Some modules are imported by nearly
   everything -- the config loader, the event schema, the shared client. Their
   radius is the whole system: touch one, run the full suite. A core is listed
   by name so the answer is not re-derived under time pressure.
3. **A failure in a higher tier than the matrix predicted means the blast
   radius was wider than the diff -- widen the row in the same change.** The
   red is not a nuisance on the way to a merge; it is the matrix being
   corrected by reality, and a merge that discards the correction buys the same
   surprise again next month.
4. **Fast-track eligibility is a column here, not a judgment call.** The route
   is computed from the file set (`docs/FAST_TRACK.md`); this column is what a
   reviewer checks the computation against.
5. **Any change to the CI pipeline grooms the matrix in the same pull
   request.** A pipeline that runs a different set than the matrix describes has
   two definitions of the gate, and the cheaper one wins by default.

## 8.6 Derived and published surfaces — check where the reader reads

When committed output is generated from sources — and above all when the
published output IS the product (a site, a catalog, a rendered report) — the
checks that keep it honest have shapes of their own, each one paid for in a
sibling deployment's production:

1. **Regeneration is proven in BOTH directions.** Rebuild from source in a
   throwaway tree and compare byte-for-byte both ways: a committed file whose
   bytes differ is **stale**, and a committed file no build produces is an
   **orphan** — a live surface served from bytes the generator never wrote.
   The staleness half alone misses the orphan entirely. And the comparison
   must not be a tautology: ask where side B came from — a clean room seeded
   from the tree it grades compares each file against a copy of itself, and
   no tampering can fail it.
2. **Every build writes every output.** A "skip-if-exists" path goes quietly
   inert: the file is present, current-looking, and permanently stale.
3. **No build clock in derived surfaces.** Bytes change only when content
   does. Output that embeds a timestamp restamps itself on every build — a
   feed that does so tells every aggregator the whole archive was just
   republished — and drowns the diff that regeneration checks depend on. Give
   output a total ordering (tie-break on a stable key) so it never reshuffles
   on an unrelated edit.
4. **One fact, two paths: compare them where they LAND.** When one fact
   reaches a reader by two independent routes — a field on an index card and
   on the item's own page, two report sections computed from one input — no
   per-surface check can see the disagreement, because each surface is
   individually well-formed. The join goes where both paths end, on the
   rendered surfaces, and fixing the source field must provably move both.
   (Measured: one article carrying two different topic names on two pages,
   both pages valid; one digest printing "100% internal traffic" above "no
   movement recorded".)
5. **Membership is checked in the direction that catches absence.** "Every
   record names a real item" is true of every registry that shrinks; "every
   item has a record" is the direction that catches silent absence. State at
   the check site which direction is meant — `both-ways`, or `one-way-ok`
   with a reason.
6. **Count requirements the way the builder counts.** Required companion
   fields (summaries, citations, keywords) are counted after the consumer's
   own filtering — three authored entries can be one usable one once blanks
   and duplicates drop. A breakdown is checked against its PARTS, never only
   its total ("23 moved and 9 more, so 33" can add overlapping sets and land
   on the right number by cancelling its own error), and a tool states its
   own total rather than anyone counting by eye off its output.
7. **A backfill exemption list only ever shrinks, and is DELETED at zero.**
   An exemption list nobody can be in is a clause that cannot fail, and an
   empty one invites the next item into it; replace it with a non-vacuity
   check on the derived population.
8. **Numbers stated in prose get a counted-noun register.** A count written
   in a document with nothing comparing it to reality goes stale unseen.
   Register every stated count keyed on its noun, derive the true value from
   the artifact it describes, and run the arithmetic on every "N of M — P%"
   claim. The register is only as wide as its nouns and the files it scans —
   a count restated with the noun dropped, or a file the register never
   reads, is invisible to it (three counts drifted at once in the field
   through exactly that seam).

## 9. What the Reviewer rejects

The list is in `.claude/agents/reviewer.md`. It is short by design: an assertion
satisfiable by the untouched baseline, a new guard with no mutation evidence, a
hand-edited shard map, an unaddressed SAST finding, and a gate run before the
final edit.
