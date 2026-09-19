# TECH_EVALUATION.md

The discipline for technology swaps, product-integration candidates, A/B
comparisons and performance changes: **measure before you flip, flip behind a
flag, adopt only on a measured win, and record the decision with the triggers
that would reopen it.** Every rule here has a running precedent in the
reference deployment; the measured incidents are restated generically.

The one-sentence law: **a change whose benefit is the point carries the
measurement that shows the benefit — no baseline for the thing a change
guards means the change is not designed yet.**

---

## 1. Phase zero — the bench harness (the guardrail, not optional)

Before any swap, integration adoption, or performance change:

- A **small, repeatable, dependency-light harness** that measures two things:
  - the **target metric** — what the change hopes to improve (e.g. a status
    endpoint's p95 under realistic concurrent load), and
  - the **guard metric** — the hard floor that must not regress (e.g. the
    interactive path's p95). A change with no named guard metric is a change
    that has not asked what it might break.
- The harness treats a down or slow subject as a **recorded error sample,
  not a crash** — an evaluation that dies on the first bad response cannot
  measure a flaky candidate, which is precisely the candidate that needs
  measuring.
- **Benches rot unless something executes them.** Bench tooling drifts from
  the runtime API because nothing runs it between evaluations (a measured
  incident: a bench unusable at decision time because the API had moved
  under it). Give every bench a CI-adjacent smoke run, or accept in writing
  that re-evaluation starts with repairing the bench.

## 2. The flip protocol — flag-gated adoption, instant revert

1. The change ships **behind a flag, defaulted to the current behaviour**.
2. Baseline run recorded — same harness, same environment, same dataset.
3. Flip the flag, warm restart, second run.
4. **Adopt as default only if the target metric improves AND the guard
   metric holds.** Both halves are the rule; a win that costs the guard is a
   loss that photographs well.
5. The flag stays after adoption as the **instant, documented revert** —
   one setting back to the old behaviour, no rollback engineering under
   pressure. (The reference deployment's shape: "default ON — validated
   on-box; =0 instant revert.")

A/B on live behaviour follows the same shape with the flag as the arm
switch: ship default-OFF, arm on the real installation, compare, then decide
— an integration is not "adopted" while its flag is OFF; it is *staged*.

## 3. The decision record

Every evaluation ends in a record — `templates/EVAL_RECORD.md.template`,
registered as a `DEC-NNNN` whose `Revisit if` points at the triggers. The
load-bearing fields, and why each earns its place:

- **Status: DECIDED KEEP / DECIDED SWAP / OPEN**, with the owner of the
  call named separately from who collected the data.
- **Decision basis:** the bench actually run, on the actual target
  environment, with the dataset named — or the honest statement that it
  could not run, and why. A decision recorded over an unrun bench says so;
  the record never launders "we couldn't test it" into "it lost".
- **Disqualification criteria are first-class, and deployment cost counts
  independent of accuracy.** A challenger that cannot start on the target
  environment is *clearly not better*, whatever its paper numbers; patching
  the working incumbent's runtime to let a challenger boot is an
  unacceptable trade. Being disqualified on deployment is a full verdict,
  not a footnote.
- **The candidate-fix recipe is recorded, not executed.** If a known change
  would make the challenger viable, write the recipe down so the
  re-evaluation is cheap — do not perform it now to force a contest the
  incumbent already won.
- **Re-evaluation triggers, enumerated:** environmental (a dependency
  pairing that newly resolves, a new deployment target, an upstream release
  that removes the disqualifier) and experiential (a live quality problem
  the owner actually feels). Any one firing reopens the decision — and the
  bench assets stay on disk so the re-run is two commands, not a project.
- **Default philosophy: the incumbent wins ties.** Swap only on *clearly*
  better; churn has a cost the bench never shows.

## 4. Who does what

| Step | Owner |
|---|---|
| Demands the bench exists before design proceeds | Architect (it is a design artifact) |
| Runs the harness, records both runs | Builder, on the story |
| Rejects a perf/swap PR carrying no baseline | Reviewer — "adopt only on a measured win" is a DoD line for this change class |
| Rules on a contested trade (target improved, guard arguably held) | Adjudicator, on the numbers |
| Signs off an evaluation that touches data, auth, or an external surface | Warden, per its normal gates |
| Writes the record; owns the KEEP/SWAP call within the product brief | Architect proposes, the engineer rules where it is a ceiling or a spend |

## 5. Cross-references

- `templates/EVAL_RECORD.md.template` — the record's shape
- docs/decisions/ — where the verdict lives, with `Revisit if`
- CAPACITY_REBALANCING.md — the same measure-before-flip discipline applied
  to the crew's own knobs
- DIAGNOSTICS_LOOP.md — where an experiential trigger usually arrives from
- .claude/skills/reviewer-integration/SKILL.md — reviewer lanes follow this
  discipline through their own add/baseline procedure
