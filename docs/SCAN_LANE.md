# SCAN_LANE.md

How the structural and security scan lane **grows**. Each scanner in the lane
reads support files that get one more entry every time a finding teaches the
repo something. This document says which files those are, when an entry is
owed, how to write one, how it is proved, and how it graduates from
report-only to blocking.

The lane itself (what runs, where, and in which mode) is
`TESTING_STANDARDS.md` section 5.1. The loop that sends findings here from
every reviewer lane is `/reviewer-integration learn`.

---

## 1. The loop: one finding, one prevention

A finding that is fixed and forgotten comes back. A finding the lane
can recognise gets caught at the next push, before CI minutes or a hosted
reviewer's quota are spent on it. For every **verified** finding, from any
source (a hosted reviewer, the Reviewer subagent, a CI failure, an incident,
this lane itself):

1. **Classify.** Ask whether the class has a **shape** one of the scanners can
   see:
   - a code construct -> ast-grep
   - a secret format -> gitleaks
   - a phrase or pattern in agent instructions -> SkillSpector YARA
   - a workflow construct -> actionlint or zizmor, usually by promotion

   If none of them fits, the prevention is a test and a
   `FAILURE_PATTERNS.md` entry with no scanner block, and this document has
   nothing more to add.
2. **Write the entry** in the support file below that matches the shape.
3. **Prove it can go red.** Every custom entry ships with a fixture or test
   case that must trip it. The lane refuses an entry without one, and fails
   when a fixture stops tripping its rule.
4. **Land it report-only.** A new rule reports and does not block.
5. **Promote it** once the rule has had zero standing findings across a full
   wave (section 4). Secrets are the exception: they block from the first
   day.
6. **Record the source.** Each entry names where the finding came from and
   the date, so the next reader can tell a rule that earned its place from
   one written on a hunch.

The same change that fixes the finding carries its prevention. A prevention
left for a follow-up does not get written.

---

## 2. The support files

| Scanner | File that grows | Grows when | Proof it can go red | Suppression record |
|---|---|---|---|---|
| ast-grep | `FAILURE_PATTERNS.md` / `KNOWN_ISSUES.md`: fenced `ast-grep` + `ast-grep-test` blocks, **derived** into `.ast-grep/rules/generated/` | A registry or intake entry has a code shape | its `invalid:` cases (`ast-grep test`) | none: fix the code, or narrow the rule |
| ast-grep | `.ast-grep/rules/kit/<id>.yml` + `.ast-grep/rule-tests/kit/<id>-test.yml` | A repo-wide convention with a code shape that is not a failure class (e.g. localhost-only binds) | its `invalid:` cases | `ignores:` globs in the rule, with a `note:` saying why |
| gitleaks | `.gitleaks.toml`: one `[[rules]]` block | A secret format the built-in rules missed (an internal token, a vendor key) | `.gitleaks/fixtures/<id>.txt`, a **fake** sample | `.gitleaksignore`: fingerprint under a dated reason |
| SkillSpector | `.skillspector/yara/*.yar`: one `rule` | An unsafe instruction pattern found in a skill, agent or hook | `.skillspector/fixtures/<rule_name>/`, a sample skill | `.skillspector/baselines/<target>.yaml` via `skillspector baseline --reason` |
| ruff (S) | `tools/quality/quality.json` `promotions.ruff` | A bandit rule reaches zero standing findings | ruff's own test suite | inline `# noqa: Sxxx` with the reason on the line above |
| zizmor | `tools/quality/quality.json` `promotions.zizmor` | An audit reaches zero standing findings | zizmor's own test suite | inline `# zizmor: ignore[<audit>]` with the reason |
| actionlint | `tools/quality/quality.json` (promoted whole-tool from day one) | Rarely: `.github/actionlint.yaml` for self-hosted runner labels or config variables | actionlint's own test suite | `.github/actionlint.yaml` `paths:` ignores, with the reason as a comment |
| all | `tools/quality/quality.json` `promotions.<tool>` | A report-only rule has held zero findings for a wave | the scan itself | not applicable |

Derived files are never edited by hand. `.ast-grep/rules/generated/` is
rebuilt by the pre-commit hook and checked by `quality.py rules --check`; a
hand edit is reported as drift.

---

## 3. Adding an entry, per scanner

### ast-grep: a failure class with a code shape

In the `FAILURE_PATTERNS.md` entry (or the `KNOWN_ISSUES.md` intake record,
for a finding that is found but not yet fixed), add two fenced blocks.
`ast-grep` holds the rule body. `ast-grep-test` holds cases:

- `invalid:` must include the instance that was found **and** a `VARIANT:`,
  a form of the same class that has not happened yet.
- `valid:` must include the fixed form.

The generator owns `id`, `severity` and `metadata`, so leave those out.
Commit; the pre-commit hook regenerates the rules, or run
`python3 tools/wall/quality.py rules` by hand. The full convention and an
example are in `templates/FAILURE_PATTERNS.md.template`, "The structural rule".

To try a rule before committing it:
`ast-grep scan --inline-rules "$(cat rule.yml)" path/`, or the ast-grep
playground.

### ast-grep: a repository convention

Write `.ast-grep/rules/kit/<id>.yml` with `severity: warning` and a `note:`
saying why the rule exists and where the finding came from. Write
`.ast-grep/rule-tests/kit/<id>-test.yml` with `valid:` and `invalid:` cases.
Never author `severity: error`; the kit suite refuses it, because promotion
goes through the record (section 4).

### gitleaks: a secret format the defaults missed

1. **Rotate the credential first.** Deleting it from the diff does not remove
   it from history (TESTING_STANDARDS.md section 5).
2. Append a `[[rules]]` block to `.gitleaks.toml` using the template at the
   top of that file:
   - an `id` of the form `kit-<system>-<kind>`
   - a `description` naming the finding and the date
   - a `regex` as tight as the format allows
   - `keywords` giving a literal every match contains
3. Add `.gitleaks/fixtures/<id>.txt` holding a **fake** value in the real
   shape. Make it look random. gitleaks' built-in allowlist drops obvious
   placeholders (a sequential alphabet, repeated characters), and a fixture
   it drops proves nothing. Never paste the real credential, even rotated.
4. Run `bash tools/quality/scan.sh local`. It fails if the rule has no
   fixture, if the fixture has no rule, or if the rule does not fire on its
   fixture.

A **false positive** is not a new rule. Suppress it by fingerprint in
`.gitleaksignore` (the fingerprint is in gitleaks' report). A fingerprint
names one **commit**. Take them from a full-history scan (`git fetch
--unshallow`, then `gitleaks git`), because a shallow clone shows only the
newest commit that carries the line, and CI scans them all. A suppressed
value that is still in the tree **also** carries an inline `gitleaks:allow`
on its line. That marker travels with the content, so the value stays
suppressed in every commit any scan can see. A shallow clone's single grafted
commit "adds" every file under a fingerprint no `.gitleaksignore` entry names,
and without the marker the local scan blocks on a false positive. Put it under a
comment that gives the date and the reason it is not a secret. Prefer an inline
`gitleaks:allow` comment on the line when the line is yours to edit.
`quality.py suppressions` refuses a fingerprint with no dated reason.

### SkillSpector: an unsafe instruction pattern

When a skill, agent definition or hook tells an agent to do something the kit
forbids, add a YARA rule to `.skillspector/yara/`. Examples of forbidden
instructions: skip hooks, push to the default branch, stop writing the
ledger, read credentials.

- **Name:** `kit_<what_it_catches>`.
- **`meta.description`:** the rule it enforces, citing the doc and section,
  and the date added.
- **`strings`:** the instruction's shape as a regex, with `nocase`.
- **`condition`:** usually `any of them`.

Add `.skillspector/fixtures/<rule_name>/SKILL.md`, a minimal fake skill that
contains the instruction. The scan fails if the fixture does not trip its
rule. `kit_skill_bypasses_git_hooks` is the worked example.

A custom rule reports as SkillSpector's generic YARA id. To promote a single
rule, record `yara:<rule_name>` under `promotions.skillspector`.

**Accepted findings on a target** are recorded in that target's baseline:

```
skillspector baseline .claude/agents --no-llm \
  --reason "<why this is acceptable, YYYY-MM-DD>" \
  -o "$(python3 tools/wall/quality.py baseline-path .claude/agents)"
```

- There is one baseline file per target. SkillSpector refuses a shared one.
- `scan.sh` passes each target's baseline automatically.
- Regenerate a baseline only after re-triaging **every** entry in it.

### ruff security rules and zizmor audits

These grow by **promotion**, not by new files. Fix or suppress each
standing finding of a rule, then promote it (section 4).

- A suppression is inline, on the line, with the reason in a comment
  directly above:
  - ruff: `# noqa: S603`
  - zizmor: `# zizmor: ignore[template-injection]`
- A bare `noqa` with no rule code, or one without a reason, is itself a
  finding (TESTING_STANDARDS.md section 5).

---

## 4. Promotion: report-only to blocking

A rule is promoted when it has had **zero standing findings across a full
wave**. Nothing is promoted wholesale: a lane that blocks on everything at
once gets switched off at its first noisy rule, and then nothing runs.

1. Measure the standing count on the current head. Run
   `bash tools/quality/scan.sh local` and count that rule's findings. It must
   be 0.
2. Append to `promotions.<tool>` in `tools/quality/quality.json`:

   ```json
   {"rule": "<id>", "date": "YYYY-MM-DD", "standing_count": 0,
    "reason": "<why this rule now blocks; the finding it came from>"}
   ```

   `rule` takes one of these forms:

   | Rule form | Tool |
   |---|---|
   | ast-grep rule id (`f-substr-001`, `py-shell-true`) | ast-grep |
   | ruff code (`S602`) | ruff |
   | zizmor audit (`unpinned-uses`) | zizmor |
   | SkillSpector id (`EA1`) or `yara:<rule>` | SkillSpector |
   | `*` (the whole tool) | any |
3. `quality.py rules --check` refuses a promotion that lacks its date,
   standing count or reason, or has a non-zero standing count. `scan.sh`
   applies each promotion at scan time (`--error=<id>` for ast-grep, a
   blocking `--select` for ruff, the zizmor and SkillSpector gates).

**Demotion** is also a recorded change. Remove the entry in a PR that says why:
usually a new scanner version changed the rule's meaning and the weekly bump
PR shows new standing findings. Never demote to make a red PR green.

---

## 5. Keeping the files healthy

- **Every week:** the `scanner-bump` PR moves every pin to the latest release
  and shows the canary run on it. New upstream rules arrive report-only;
  triage them on that PR. A new finding is either fixed, suppressed with a
  dated reason, or listed for promotion later.
- **At wave close** (`/reviewer-integration learn`): every verified finding
  from the wave either has its prevention in one of the files above, or has
  a recorded reason why it has no scanner shape.
- **At the roll-up** (every N merged PRs): read the promotion record against
  the lane's report-only output. A rule that has been at zero for a wave and
  is still report-only is a promotion someone owes. A rule whose findings are
  mostly suppressed is too broad and needs narrowing, not more suppressions.
- **Append-only, like the registry.** A rule that stops being useful is
  narrowed or demoted with a record; its history is not rewritten. A
  suppression whose code is gone is deleted in the change that deletes the
  code.
- **Never** weaken a rule, delete a fixture, or add a suppression to get a PR
  green. Each of those is a finding in its own right.
