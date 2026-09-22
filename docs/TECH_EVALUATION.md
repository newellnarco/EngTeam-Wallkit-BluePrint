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
registered as a `DEC-NNNN` whose `Revisit if` points at the triggers, and
**carrying three signatures before it reads DECIDED: the Architect authored
it, the Warden signed it (ack or full gate), the engineer ratified it.** The
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

## 3b. Adopting a metered external service — meter first, extrapolate never

Metered tools (hosted reviewers, CI, per-seat services) fail evaluation in a
way benches don't show: the cost model. Every rule here was paid for in a
sibling deployment, where six cost claims were corrected in two days and
every correction came from a meter.

- **Run one complete unit of work end-to-end, with the agents working the
  way they actually work, and read the vendor's billing meter** — never a
  proxy counter, a pricing page, or recollection. Of five readings of one
  billable unit taken in three days, only the metered one survived; one was
  attached to the wrong vendor entirely. Measure a unit only after it
  finishes — mid-flight readings are honest and low.
- **The billable event and how many of it your workflow generates are two
  different questions.** An agent loop produces several times more of most
  priced units — pushes, reviews, runs — per unit of *intent* than any human
  intuition predicts; a page-derived estimate ran five times low against the
  meter.
- **Ask where the tool's compute runs.** A hosted tool can be free on its
  own invoice and still bill a metered resource you own (one bundled
  reviewer executed its runs as workflows in the host's own CI, hundreds of
  minutes a month).
- **Audit coverage settings as pricing levers before tuning them.** A file
  cap or a draft trigger is a spend control under some billing models;
  raising one "for fairness" multiplied billable reviews 2.9× in the field.
- **A trial ends by calendar or by allowance — know which.** A "14-day
  trial" was exhausted in a day and a half of agent-velocity work. And where
  a per-seat allowance's unit price beats the overage price, buying unused
  seats is the cheaper route — arithmetic, not loyalty.
- **A free tier is a dependency with no contract behind it.** Treat its
  sunset as a scheduled event of unknown date; cost the replacement before
  it is urgent, and keep a self-hosted break-glass lane installed-but-
  disabled so a vendor decision cannot leave the repo reviewer-less on the
  vendor's schedule (a sibling's only active reviewer was withdrawn by the
  vendor mid-tenure: "we were not shopping, we were replacing something
  that was removed"). **Count your lanes on every subscription change** — a
  bundled tool can arrive with a plan upgrade and put the repo over its own
  lane cap without anyone deciding it.

## 3c. Comparing live lanes — the controls a bench doesn't need

A head-to-head of live services (two reviewers, two graders) is not a bench:
the subjects act on moving work, and six confounds silently favour one side.
Fix these before the data arrives, with the decision rule and "what would
change the verdict" written down first so neither can be fitted afterwards:

1. **Trigger-point parity** — both lanes see the same head, or one reviews
   already-cleaned diffs.
2. **Grounding parity, or the asymmetry stated** — a tuned incumbent versus
   a cold challenger measures your setup work, not the tools.
3. **Configuration verified by observation**, never by schema validation —
   a config can parse and be inert.
4. **A declined or skipped review is not a clean one.** Never score a
   decline as a pass.
5. **Sole-credit accounting stated as a confound** — it depresses
   overlapping lanes and flatters solo tenures.
6. **Normalize by tenure, with a minimum-tenure guard.** A two-sample tenure
   extrapolated to a rate topped a comparison chart in the field before the
   guard existed.

Add a **negative control**: one surface where the lane is off must correctly
produce zero. And choose second lanes for **disjointness of mechanism**: the
strongest value of a second lane is two lanes finding the same defect
independently — corroboration that converts an opinion into near-fact without
trusting either — so a challenger overlapping the incumbent on the same axis
is disqualified by redundancy even on a better score (one lane was dropped
exactly so, despite the record's best normalized rate). State honestly that
the number that would truly price a second lane — how often both miss — is
unmeasured.

## 4. Who does what

| Step | Owner |
|---|---|
| Demands the bench exists before design proceeds | Architect (it is a design artifact) |
| Runs the harness, records both runs | Builder, on the story |
| Rejects a perf/swap PR carrying no baseline | Reviewer — "adopt only on a measured win" is a DoD line for this change class |
| Rules on a contested trade (target improved, guard arguably held) | Adjudicator, on the numbers |
| Signs **every** evaluation record — a one-line "no security/compliance surface" ack on routine ones, the full Gate 1/Gate 2 treatment when the candidate touches data, auth, secrets or an external surface (which a new integration almost always does). The data read is checkpoint 2 of `DATA_PROTECTION.md` §4: where the candidate PUTS data — its cloud, region, model endpoint, telemetry, retention — with the compliant way forward named, not just a verdict | Warden, always (user direction) |
| Writes the record; proposes the KEEP/SWAP verdict | Architect, always — an evaluation without the Architect's authorship is an opinion with a benchmark |
| Ratifies every DECIDED verdict — a one-word confirm via the human queue; ceilings and spend remain theirs outright | Engineer, always: no record moves from OPEN to DECIDED unseen |

## 5. Cross-references

- `templates/EVAL_RECORD.md.template` — the record's shape
- docs/decisions/ — where the verdict lives, with `Revisit if`
- CAPACITY_REBALANCING.md — the same measure-before-flip discipline applied
  to the crew's own knobs
- DIAGNOSTICS_LOOP.md — where an experiential trigger usually arrives from
- .claude/skills/reviewer-integration/SKILL.md — reviewer lanes follow this
  discipline through their own add/baseline procedure
