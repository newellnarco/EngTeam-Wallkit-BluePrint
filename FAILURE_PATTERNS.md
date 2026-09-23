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
