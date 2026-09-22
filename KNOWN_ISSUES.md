# KNOWN_ISSUES.md -- the kit's own intake

> Found, not yet worked. Every issue is recorded here **the moment it is
> found**, before anything is touched, whoever found it: an agent, CI, a
> hosted reviewer, a scanner, or the owner. Built from
> `templates/KNOWN_ISSUES.md.template`, which is also where the generic
> **families** live.

**Three records, three tenses** (`docs/WALL_STANDARDS.md` section 4). The wall
shows what is **in flight**. This file holds what is **known**.
`FAILURE_PATTERNS.md` holds what is **fixed and guarded**. An entry leaves this
file in one of two ways, and there is no third state:

- **Guarded:** it lands in `FAILURE_PATTERNS.md` with a check, and its row
  here names that class.
- **Declined:** it moves to "Declined" below, with the reason.

Silence is not a disposition. An entry with a code shape may carry a fenced
`ast-grep` block; it is generated report-only like any other rule
(`docs/SCAN_LANE.md`).

## Entry format

```
## KI-<YYYY-MM-DD>-<letter> - <one line: what is wrong, as a mechanism>
- Found by      who or what raised it, and where
- Symptom       what it looks like from outside
- Family        the shared root (a letter from the template's families, or new)
- Blast radius  what it touches if left
- Owner         who moves it next
- Closes when   the checkable condition that ends it
- Next step     the cheapest action that moves it to guarded or declined
- Disposition   open | guarded -> F-<SCOPE>-<NNN> | declined (see below)
```

---

## Open

## KI-2026-09-22-a - the ruff security rules have 20 standing findings, so none can be promoted

- **Found by:** the scan lane on its first run (PR #8)
- **Symptom:** `scan.sh` reports 20 ruff `S` findings in `tools/wall` and
  `.claude/hooks`: subprocess calls with partial executable paths (S603,
  S607), `urlopen` audits (S310), `try`/`except`/`pass` (S110), one `assert`
  (S101), one SHA-1 (S324). All report-only.
- **Family:** D (the rule is written down, but nothing makes it fire: the lane reports and cannot yet block)
- **Blast radius:** none today. But no ruff security rule can be promoted to
  blocking until its standing count is zero, so the lane cannot tighten.
- **Owner:** the engineer, with the Builder doing the triage
- **Closes when:** every ruff S rule is fixed, suppressed with a reason, or promoted
- **Next step:** triage per rule. Most of the S603/S607 hits are fixed-argv
  git calls: suppress them inline with the reason, as `quality.py` does. The
  SHA-1 is an id digest, not security: `usedforsecurity=False`. Then promote
  each rule that reaches zero.
- **Disposition:** open

## KI-2026-09-22-b - three agent definitions trip SkillSpector's excessive-agency checks

- **Found by:** SkillSpector, static mode, first run (PR #8)
- **Symptom:** EA1 "unrestricted tool access" on `.claude/agents/builder.md`
  and `integrator.md` (`tools: "*"`), and EA2 "autonomous decision making" on
  `.claude/agents/foreman.md` (a table row about questions nobody asked). All
  MEDIUM and report-only.
- **Family:** D (a rule only reports, so nothing makes it fire)
- **Blast radius:** any SkillSpector finding in an agent the kit ships is
  inherited by every adopting repository.
- **Owner:** the engineer (a per-agent tools decision)
- **Closes when:** each finding is narrowed away or baselined with its reason
- **Next step:** an owner decision per agent. Either narrow `tools:` to what
  the role uses (the Reviewer and Researcher already do), or accept it and
  record it in `.skillspector/baselines/claude__agents.yaml` with the reason.
  EA2 on the Foreman looks like a false positive (the matched phrase is
  "blocked without asking"): baseline it with that reason.
- **Disposition:** open

## KI-2026-09-22-c - the pinned checkout and setup-python actions target a deprecated Node runtime

- **Found by:** CI log warning (PR #8)
- **Symptom:** "Node.js 20 is deprecated ... forced to run on Node.js 24" for
  `actions/checkout@v4.4.0` and `actions/setup-python@v5.6.0`.
- **Family:** E (the box that runs it is not the box CI tested: the runner moves
  under an unchanged pin)
- **Blast radius:** the runner forces Node 24 today. When forcing stops,
  every workflow fails at its first step.
- **Owner:** the Builder
- **Closes when:** no Node deprecation warning in a CI log, and action pins ride the weekly bump
- **Next step:** re-pin both to their Node 24 majors by commit SHA, and add
  them to the weekly scanner-bump run so action pins move the way scanner
  pins do.
- **Disposition:** open

## KI-2026-09-22-d - the scanner-bump PR path is unverified until it runs from the default branch

- **Found by:** design review of the zero-configuration change (PR #8)
- **Symptom:** none yet. `workflow_dispatch` only runs a workflow that exists
  on the default branch, so the dispatched-CI path and the issue fallback
  cannot run before this lands on `main`.
- **Family:** I (the machinery is built and the last inch is not wired: unproven
  until it first runs)
- **Blast radius:** a bump PR arrives with no CI, or no bump arrives at all.
  Both are silent.
- **Owner:** the engineer (one manual dispatch after merge)
- **Closes when:** one run shows a canary summary, a PR or issue, and CI checks on the bump commit
- **Next step:** after merge, run the workflow once by hand (Actions >
  Scanner bump > Run workflow) and confirm: a canary summary, a draft PR or
  an issue, and CI checks on the bump commit.
- **Disposition:** open

## KI-2026-09-22-e - both hosted review lanes ran out of meter mid-PR

- **Found by:** the lanes themselves (PR #8)
- **Symptom:** CodeRabbit hit its review limit (2 per hour after the
  account's spending cap), and Copilot review reported its quota exhausted.
  Later pushes waited, or were not reviewed at all.
- **Family:** M (review capacity treated as unlimited)
- **Blast radius:** a push lands with no hosted review and looks reviewed,
  because the earlier approval-by-silence still shows.
- **Owner:** the engineer (lane budgets)
- **Closes when:** each lane's meter shape is recorded in REVIEWER_LANES.md
- **Next step:** record each lane's meter shape in `REVIEWER_LANES.md` (the
  throttle reopens, the quota does not until the period rolls), and batch
  review requests at open/ready rather than every push (`docs/FAST_TRACK.md`,
  the meter economics).
- **Disposition:** open

---

## Guarded

| Entry | Guarded as |
|---|---|
| (none yet: entries found and fixed within PR #8 went straight to `FAILURE_PATTERNS.md`) | |

## Declined

| Entry | Reason | Decided by |
|---|---|---|
| (none yet) | | |
