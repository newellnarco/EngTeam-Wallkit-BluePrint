# FAILURE_PATTERNS.md -- the kit's own registry

> Append-only registry of bug classes that shipped **in this repository** and
> failed. Every entry is a contract: check your change against this list before
> declaring it ready. Built from `templates/FAILURE_PATTERNS.md.template`, the
> same file every adopting repository starts from.

**Two registries, on purpose.** This file records what the kit itself has paid
for. The **library** -- the seeded classes and the inherited corpus
genericized from three production deployments (a resident desktop app, a
network appliance and a research-publishing repo) -- lives in
`templates/FAILURE_PATTERNS.md.template`, because that is the file `bootstrap`
copies into an adopting repository. When an inherited class first happens
here, it is **promoted** into this file with its real `Discovered` line, exactly
as the template's own rule says. Read both before a ship: this file for what
has already happened here, the template's inherited section for what is
statistically next.

A class whose mistake has a **code shape** carries a fenced `ast-grep` block;
`tools/wall/quality.py rules` derives it into `.ast-grep/rules/generated/`, the
pre-commit hook keeps it in sync, and the scan lane runs it
(`docs/SCAN_LANE.md`). Findings not yet worked live in `KNOWN_ISSUES.md`.

**The kit's own roles count as "here".** When the kit's roles and procedures
are run in an adopting repository and the *method* fails -- a role sheet
allowed the mistake, or no role owned the duty -- the class is the kit's, and
it is recorded here with a `Discovered` line naming the shape of the adopting
setup (never the adopter). Its guard lives in the kit: a pinned rule in the
role sheet or document that owns the duty. The entries from F-OPS-011 onward
came from one day of running the roles across several adopting repositories on
one workstation (DEC-0038).

## Recurring classes - watch these hardest

| Class | The reminder, in one line | class-guard |
|---|---|---|
| F-PARTIAL-VIEW-001 | A local verdict covers less than CI sees, in either direction: it misses what CI finds, or blocks on what CI would clear. | `test_ci_scan_refuses_a_shallow_history` |

---

## Format

```
ID            stable, never reused: F-<SCOPE>-<NNN>
Title         one line
Discovered    when and where it first hurt
Symptom       what the failure looks like from outside
Root cause    the actual mistake
Check         the gate that catches the next one, automated where possible
Command       the exact command, when there is one
ast-grep      when the class has a code shape: the rule and its test cases
class-guard   the named assertion that fails when any member recurs
```

---

## F-PARTIAL-VIEW-001 - a gate verified against less than the real gate sees

- **Discovered:** 2026-09-22, PR #8 (promoted from the inherited library)
- **Symptom:** The secrets scan passed locally and failed in CI on the same
  commit. A `.gitleaksignore` fingerprint had been written from a shallow
  clone, which held only the newer of the two commits carrying a deliberately
  fake test key. CI scans the full history and failed on the older one.
- **Root cause:** The local run checked part of CI's input and reported the
  result as "clean". The suppression derived from it inherited the gap.
- **Check:** `quality.py history --ci` fails a shallow or absent history as
  unknown, not clean, and `scan.sh ci` uses it. Fingerprints are taken from a
  full-history scan (`docs/SCAN_LANE.md`, gitleaks).
- **Command:** `bash tools/quality/scan.sh ci`; `git fetch --unshallow` before
  recording a fingerprint

> class-guard: `test_ci_scan_refuses_a_shallow_history`
> VARIANT: a pre-push gate that lints only the outgoing diff while CI lints
> the tree.

**Second occurrence, 2026-09-22, same PR, the other direction.** A local scan
of a shallow clone blocked on a false positive. The clone's single grafted
commit "added" the fake test key under a fingerprint `.gitleaksignore` did not
name. Same class: the local view was not the view the suppression was written
for. Fixed by an inline `gitleaks:allow` on the line, which travels with the
content through every commit and graft, and by counting a shallow local
history as UNKNOWN instead of clean. The class entered the digest above.

---

## F-TEST-SELFCMP-001 - an assertion whose expected side is derived from the actual side

- **Discovered:** 2026-09-22, PR #8 (caught by the mutation protocol before
  push)
- **Symptom:** A test of the pin-bump rollback passed with the rollback line
  deleted. It compared the config against a copy of itself with the expected
  fields overlaid (`x == dict(x, ...)`), so it could only ever agree. The
  fixture also started with rollback already equal to the old version, so even
  a correct comparison could not have failed.
- **Root cause:** The expected value was computed from the value under test
  instead of being stated independently, and the fixture already sat in the
  final state.
- **Check:** State expected values as literals or from an independent source.
  Start the fixture in a state the code must CHANGE. Run the mutation
  protocol (`docs/TESTING_STANDARDS.md` section 4): a guard that stays green
  with its anchor deleted is not a guard.
- **Command:** `ast-grep scan --filter f-test-selfcmp-001`

```ast-grep
language: python
rule:
  any:
    - pattern: assert $X == $X
    - pattern: assert $X == dict($X, $$$)
    - pattern: $T.assertEqual($X, $X)
constraints:
  X:
    not:
      kind: call
note: The expected side is derived from the actual side, so this can never fail. State the expected value independently. A repeated CALL compared with itself is a determinism check and is deliberately not matched.
```

```ast-grep-test
valid:
  - "assert cfg['rollback'] == '0.45.3'"
  - "assert trace_for('ST-70') == trace_for('ST-70')"
  - "self.assertEqual(result, expected)"
invalid:
  - "assert cfg['tools'] == dict(cfg['tools'], version='9')"
  - "assert state.value == state.value"
  # VARIANT: the unittest spelling of the same tautology
  - "self.assertEqual(report.count, report.count)"
```

> class-guard: the generated ast-grep rule `f-test-selfcmp-001`, proven by its
> `invalid:` cases in `ast-grep test`
> VARIANT: an expected snapshot regenerated from the output it checks.

---

## F-PROOF-DROPPED-001 - a proof fixture the tool silently discards proves nothing

- **Discovered:** 2026-09-22, PR #8 (caught while building the lane)
- **Symptom:** A custom gitleaks rule and its fake fixture looked correct, but
  the rule "never fired". The fixture's sample was an alphabet run, which
  gitleaks' built-in allowlist drops as an obvious placeholder, so the proof
  scanned nothing it would ever report.
- **Root cause:** The fixture was trusted because it existed. Nobody checked
  that the tool actually matched it, and the tool gave no sign that it had
  discarded the sample.
- **Check:** Every custom rule's fixture is run through the real tool on every
  scan, and the scan fails if the rule does not fire on it (`scan.sh`, the
  proofs step). Fixture samples look random.
- **Command:** `bash tools/quality/scan.sh local`

> class-guard: the scan lane's proofs step (`did not fire on its fixture`),
> mutation-proven by breaking the YARA and gitleaks fixtures
> VARIANT: a test fixture a framework skips (a filename it does not collect, a
> marker filtered out), so the "red" the author saw was a different test.

---

## F-CI-EXPR-COMMENT-001 - a comment is not inert where a template engine runs first

- **Discovered:** 2026-09-22, PR #8 (caught by actionlint before push)
- **Symptom:** A workflow's `run:` script had a shell comment containing a
  literal Actions expression, written to explain why expressions were
  avoided. GitHub expands expressions before the shell runs, so the comment
  was parsed as an (empty, invalid) expression and the workflow would have
  failed to start.
- **Root cause:** A comment was treated as inert, but a layer ahead of the
  commenting language (Actions expressions, Jinja, Helm, a preprocessor) reads
  it first.
- **Check:** actionlint in the scan lane, promoted to blocking. Never put a
  template engine's delimiters in a comment inside a templated field.
- **Command:** `actionlint`

> class-guard: actionlint, promoted whole-tool in `tools/quality/quality.json`
> VARIANT: a `{{ }}` example in a comment inside a Helm or Jinja template,
> which renders or fails at deploy time.

---

## F-TRUST-SPLIT-001 - untrusted code executed where a write credential is reachable

- **Discovered:** 2026-09-22, PR #8 (review finding, rated critical)
- **Symptom:** The weekly scanner-bump job installed and ran the newest,
  unreviewed third-party releases in the same job that held a
  repository-write token, with checkout credentials persisted on disk.
  Release names from outside went into shell source through expression
  expansion.
- **Root cause:** One job did two things with different trust levels:
  executing outside code, and writing to the repository. The job's
  permissions were set for the writing half.
- **Check:** Split by trust. The job that runs third-party code is
  read-only, with credentials never persisted. The writing job runs only this
  repository's code and takes outside values only through `env:`, after
  validating them (`quality.py bump` refuses anything that is not a plain
  version). zizmor audits every workflow.
- **Command:** `zizmor --offline .github/workflows`

> class-guard: `test_the_canary_that_runs_new_releases_holds_no_write_token`
> VARIANT: a PR workflow on `pull_request_target` that checks out and builds
> the fork's code with the base repository's token.

---

## F-DERIVED-INDEX-001 - a derived artifact generated from the working tree, committed against the index

- **Discovered:** 2026-09-22, PR #8 (review finding)
- **Symptom:** With a registry file partially staged, the pre-commit hook
  generated rules from the working tree, including edits that were not being
  committed. The commit then carried rules that did not match its own
  registry, and CI's drift check refused it.
- **Root cause:** The hook read its inputs from one snapshot (the working
  tree) and wrote its outputs into another (the index).
- **Check:** A hook that regenerates committed artifacts reads its inputs
  from the index (`git checkout-index` into a temporary tree) and writes its
  outputs straight into the index.
- **Command:** `bash tools/git-hooks/install.sh`, then commit a partially
  staged registry

> class-guard: `test_pre_commit_generates_rules_from_the_staged_registry`
> VARIANT: a formatter hook that formats the working-tree file and re-stages
> all of it, sweeping unstaged hunks into the commit.

---

## F-OPS-011 - co-located agent services, model servers and runners exhaust one machine

- **Discovered:** 2026-09-29, a workstation running several adopting
  repositories' agent services, a local model server, hosted-review clients
  and self-hosted CI runners
- **Symptom:** The machine stopped responding to its owner. Memory and every
  core were taken; each consumer, measured alone, was within reason, and
  nothing on the machine could say which one to shed first.
- **Root cause:** Every consumer sized itself as if it were alone. There was no
  machine-wide plan, no launcher applied an operating-system limit, and the
  runners took jobs whenever they were offered one, whatever the machine's
  load. Where a load probe existed, a probe that failed read as "idle".
- **Check:** One throttle plan per machine: a file with a ceiling per consumer
  and **floors** always left for the owner. The launcher caps each process it
  starts from that plan (job objects, cgroups, container limits). Runners take
  a job only through a load gate, and **"could not look" closes the gate**. The
  fleet operator reads the plan and measures against it
  (`.claude/agents/fleet-operator.md` section 1).
- **Command:** none in the kit; the plan and the launcher live on the machine

> class-guard: `test_the_fleet_operator_carries_the_machine_throttle_plan`
> VARIANT: one consumer that honours its own limit but spawns children that
> the limit does not cover, because the cap was set on the process rather than
> on the job or group that contains its children.

---

## F-OPS-012 - a restorer re-enables what the owner turned off

- **Discovered:** 2026-09-29, the same workstation
- **Symptom:** The owner stopped and disabled a service to take load off the
  machine. Minutes later it was running again. A watchdog, a reconcile pass
  and an installer re-run each, separately, brought something back that the
  owner had turned off on purpose.
- **Root cause:** Each restorer compared the machine against its own idea of
  "should be running" and treated every difference as damage. None of them
  could tell a crash from a clean stop, or an absent item from a removed one,
  so the owner's decision read as a fault to repair.
- **Check:** Only a **crashed** thing is restarted: an abnormal exit while it
  was meant to run. A clean stop, a disable or a pause stays off. Every
  re-register reads the item's current state first and leaves a disabled item
  disabled (`.claude/agents/fleet-operator.md` section 3).
- **Command:** none in the kit; a restorer's own tests construct the stopped and
  disabled cases

> class-guard: `test_only_a_crashed_thing_is_restarted`
> VARIANT: an upgrade script that re-registers every scheduled task from its
> template and silently flips a disabled task back to enabled.

---

## F-GIT-005 - parallel PRs in one repository each bump the version

- **Discovered:** 2026-09-29, an adopting repository with two sessions' PRs
  open at once
- **Symptom:** Two PRs, each correct alone, both raised the version from the
  same base. The first merged; the second conflicted on the version line, and
  a hand-resolved rebase could have shipped two releases under one number.
- **Root cause:** The version is shared, derived state (a counter), and each
  change claimed it at authoring time, when neither could see the other.
- **Check:** The version bump happens at integration time: the Integrator
  bumps it after rebasing onto the moved main, immediately before the gates
  (`.claude/agents/integrator.md` step 1b). Or the Maestro, or the program
  lead across repositories, assigns the numbers up front. Nobody bumps it in
  the unit.
- **Command:** none; the rule is procedural

> class-guard: `test_the_version_bump_happens_at_integration`
> VARIANT: a changelog heading or a migration sequence number claimed by two
> parallel changes.

---

## F-REVIEW-013 - every hosted reviewer lane is exhausted, and a sensitive change merges unreviewed

- **Discovered:** 2026-09-29, an adopting repository
- **Symptom:** A PR that handled credentials reached green with no reviewer
  comment at all. Every hosted review lane had hit its spending cap or quota,
  each was correctly recorded as unavailable, and the rule "an unavailable
  lane does not hold the PR" let it through.
- **Root cause:** The rule that stops a metered lane from blocking work was
  written for one lane being down, not all of them. With every lane down, the
  change had no adversarial read, and the most sensitive change of the day got
  the least review.
- **Check:** When hosted lanes are down, a **cold in-house security review**
  (Warden or Reviewer) is mandatory before merge for anything touching
  secrets, credentials, authentication or the machine it runs on. The review
  is recorded before the merge (`.claude/agents/reviewer.md` section 5,
  `.claude/agents/warden.md` section 6).
- **Command:** none; the rule is procedural

> class-guard: `test_lanes_down_means_a_cold_security_review`
> VARIANT: one lane up, but it is the lane configured to skip the changed
> paths, so the sensitive files are still unread.

---

## F-PROC-004 - a "merge on green" driver goes idle after green, and nothing merges

- **Discovered:** 2026-09-29, several adopting repositories
- **Symptom:** A PR sat green for a long time. The driver had reported green
  and ended, exactly as its role sheet says; the session that owned the merge
  read the report as the work being finished.
- **Root cause:** "Report green and stop" and "the Maestro merges" were two
  halves with no owner of the moment between them. The report was taken as
  the merge.
- **Check:** The Maestro's check-in merges green PRs; **a driver's report is
  not the merge** (`.claude/MAESTRO.md` section 5,
  `.claude/agents/program-lead.md` section 3).
- **Command:** none; the rule is procedural

> class-guard: `test_the_check_in_merges_green`
> VARIANT: an auto-merge flag set on a PR whose required checks were later
> changed, so it never fires and nobody looks.

---

## F-PROC-005 - a global quiet rule several sessions cannot satisfy

- **Discovered:** 2026-09-29, an adopting repository with several sessions
- **Symptom:** A standing rule said "no push while ANY CI run is in progress".
  With several sessions sharing the repository's CI, some run was always in
  progress, so every session either waited forever or broke the rule.
- **Root cause:** A rule written for one session was stated over shared state
  every session changes. No session could make it true by its own actions.
- **Check:** Serialize through one owner: a push/merge queue held by one
  Maestro per repository (its merge seat), or scope the rule to the session's
  own PRs (`.claude/MAESTRO.md` section 5).
- **Command:** none; the rule is procedural

> class-guard: `test_push_serialization_is_owned_not_global`
> VARIANT: "do not deploy while anyone has a change open", on a repository
> where someone always has a change open.

---

## F-OPS-013 - a removal with no recorded way back

- **Discovered:** 2026-09-29, the same workstation (the guard held; recorded so
  it is not simplified away)
- **Symptom:** A retire script meant to delete services and tasks the owner
  had retired refused several of them. The refusal looked like a bug.
- **Root cause:** Not a bug: the script saves each item's settings before
  deleting and refuses any item it could not recreate on rollback. The hazard
  it prevents is a deletion that cannot be undone because nothing recorded
  what was there.
- **Check:** Deletion is owner-run, never automatic. It saves settings first,
  records a rollback, and refuses an item it could not recreate
  (`.claude/agents/fleet-operator.md` section 4).
- **Command:** none in the kit; the retire tool lives on the machine

> class-guard: `test_deletion_is_owner_run_and_leaves_a_way_back`
> VARIANT: a cleanup that deletes a branch or a stored record whose only copy
> of its contents was the thing deleted.
