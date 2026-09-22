"""The structural-scan lane (TESTING_STANDARDS section 5.1): ast-grep rules
derived from the failure registry, SkillSpector's gate, and the scanner pins."""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path

import pytest

import quality

KIT = Path(__file__).resolve().parent.parent

ENTRY = """# FAILURE_PATTERNS.md

## F-SUBSTR-001 - a substring where an identity is required

- **Check:** Parse, then compare.

```ast-grep
language: python
rule:
  pattern: $NEEDLE in $URL
```

```ast-grep-test
valid:
  - "urlparse(url).hostname == host"
invalid:
  - "host in url"
```

## <F-SCOPE-NNN> - placeholder, not an id

```ast-grep
language: python
rule:
  pattern: never_generated()
```

## F-PROSE-001 - a class with no code shape

Prose only.
"""


def host(tmp_path, registry=ENTRY, known=None):
    (tmp_path / "tools" / "quality").mkdir(parents=True)
    cfg = json.loads((KIT / quality.CONFIG).read_text(encoding="utf-8"))
    cfg["promotions"] = {"ast-grep": [], "skillspector": []}
    (tmp_path / quality.CONFIG).write_text(json.dumps(cfg), encoding="utf-8")
    if registry is not None:
        (tmp_path / "FAILURE_PATTERNS.md").write_text(registry, encoding="utf-8")
    if known is not None:
        (tmp_path / "KNOWN_ISSUES.md").write_text(known, encoding="utf-8")
    return tmp_path, cfg


# ------------------------------------------------------------ generation

def test_an_entry_block_becomes_a_report_only_rule_and_its_test():
    out = quality.render_rules("FAILURE_PATTERNS.md", ENTRY)
    assert sorted(out) == ["rules/f-substr-001.yml", "tests/f-substr-001-test.yml"]
    rule = out["rules/f-substr-001.yml"]
    assert "\nid: f-substr-001\n" in rule
    assert "\nseverity: warning\n" in rule
    assert "failure_class: F-SUBSTR-001" in rule
    assert 'message: "F-SUBSTR-001 - a substring where an identity is required"' in rule
    assert "pattern: $NEEDLE in $URL" in rule
    test = out["tests/f-substr-001-test.yml"]
    assert "\nid: f-substr-001\n" in test and "- \"host in url\"" in test


def test_placeholders_and_prose_only_entries_generate_nothing():
    ids = [e["id"] for e in quality.parse_entries(ENTRY)]
    assert "F-SCOPE-NNN" not in ids
    out = quality.render_rules("FAILURE_PATTERNS.md", ENTRY)
    assert not any("never_generated" in c for c in out.values())
    assert not any("f-prose-001" in k for k in out)


def test_a_second_rule_in_one_entry_gets_a_suffixed_id():
    two = ENTRY.replace("```ast-grep-test", "```ast-grep\nlanguage: python\n"
                        "rule:\n  pattern: $A.find($B)\n```\n\n```ast-grep-test", 1)
    two = two.replace('  - "host in url"\n```', '  - "host in url"\n```\n\n'
                      '```ast-grep-test\ninvalid:\n  - "url.find(host)"\n```', 1)
    out = quality.render_rules("FAILURE_PATTERNS.md", two)
    assert "rules/f-substr-001-2.yml" in out
    assert "tests/f-substr-001-2-test.yml" in out


@pytest.mark.parametrize("mutate, why", [
    (lambda t: t.replace("```ast-grep-test\nvalid:", "```text\nvalid:"), "no test block"),
    (lambda t: t.replace("invalid:\n  - \"host in url\"", "valid2:\n  - x"), "no invalid case"),
    (lambda t: t.replace("language: python\nrule:\n  pattern: $NEEDLE",
                         "id: mine\nlanguage: python\nrule:\n  pattern: $NEEDLE"), "owned id"),
    (lambda t: t.replace("language: python\nrule:\n  pattern: $NEEDLE",
                         "severity: error\nlanguage: python\nrule:\n  pattern: $NEEDLE"),
     "owned severity: promotion bypassing the record"),
    (lambda t: t.replace("language: python\nrule:\n  pattern: $NEEDLE",
                         "rule:\n  pattern: $NEEDLE"), "no language"),
])
def test_a_malformed_block_is_refused_with_its_location(mutate, why):
    with pytest.raises(quality.RuleError) as exc:
        quality.render_rules("FAILURE_PATTERNS.md", mutate(ENTRY))
    assert "FAILURE_PATTERNS.md:3 F-SUBSTR-001" in str(exc.value), why


def test_write_then_check_is_clean_and_every_drift_kind_is_named(tmp_path):
    root, cfg = host(tmp_path)
    assert quality.check_rules(root, cfg) == [
        "missing: .ast-grep/rule-tests/generated/f-substr-001-test.yml",
        "missing: .ast-grep/rules/generated/f-substr-001.yml"]
    quality.write_rules(root, cfg)
    assert quality.check_rules(root, cfg) == []

    # A new registry entry without regeneration: missing.
    reg = root / "FAILURE_PATTERNS.md"
    reg.write_text(ENTRY.replace("## F-PROSE-001", "## F-NEW-001 - new\n\n"
                                 "```ast-grep\nlanguage: python\nrule:\n  pattern: eval($X)\n```\n\n"
                                 "```ast-grep-test\ninvalid:\n  - eval(s)\n```\n\n## F-PROSE-001"),
                   encoding="utf-8")
    assert "missing: .ast-grep/rules/generated/f-new-001.yml" in quality.check_rules(root, cfg)
    quality.write_rules(root, cfg)

    # An edited rule body: stale.
    reg.write_text(reg.read_text(encoding="utf-8").replace("eval($X)", "exec($X)"),
                   encoding="utf-8")
    assert "stale: .ast-grep/rules/generated/f-new-001.yml" in quality.check_rules(root, cfg)
    quality.write_rules(root, cfg)

    # A block removed from its entry: the orphaned rule is named, then deleted.
    reg.write_text(ENTRY, encoding="utf-8")
    drift = quality.check_rules(root, cfg)
    assert any(d.startswith("orphaned") and "f-new-001.yml" in d for d in drift)
    quality.write_rules(root, cfg)
    assert not (root / ".ast-grep/rules/generated/f-new-001.yml").exists()
    assert quality.check_rules(root, cfg) == []


def test_a_hand_edit_to_a_generated_rule_is_drift(tmp_path):
    root, cfg = host(tmp_path)
    quality.write_rules(root, cfg)
    f = root / ".ast-grep/rules/generated/f-substr-001.yml"
    f.write_text(f.read_text(encoding="utf-8").replace("warning", "error"),
                 encoding="utf-8")
    assert quality.check_rules(root, cfg) == [
        "stale: .ast-grep/rules/generated/f-substr-001.yml"]


def test_known_issues_are_a_source_and_absent_sources_are_not_errors(tmp_path):
    known = "# KNOWN_ISSUES.md\n\n## KI-7 - found, not yet worked\n\n" \
            "```ast-grep\nlanguage: python\nrule:\n  pattern: os.system($X)\n```\n\n" \
            "```ast-grep-test\ninvalid:\n  - os.system(cmd)\n```\n"
    root, cfg = host(tmp_path, registry=None, known=known)
    tree = quality.expected_tree(root, cfg)
    assert root / cfg["generated_rules_dir"] / "ki-7.yml" in tree
    root2, cfg2 = host(tmp_path / "empty", registry=None)
    assert quality.expected_tree(root2, cfg2) == {}


def test_one_id_generated_from_two_sources_is_refused(tmp_path):
    known = ENTRY.replace("# FAILURE_PATTERNS.md", "# KNOWN_ISSUES.md")
    root, cfg = host(tmp_path, known=known)
    with pytest.raises(quality.RuleError, match="one definition per name"):
        quality.expected_tree(root, cfg)


def test_the_cli_check_exits_nonzero_on_drift_and_zero_after_regen(tmp_path, capsys):
    root, _ = host(tmp_path)
    assert quality.main(["--root", str(root), "rules", "--check"]) == 1
    assert "run `python3 tools/wall/quality.py rules`" in capsys.readouterr().err
    assert quality.main(["--root", str(root), "rules"]) == 0
    assert quality.main(["--root", str(root), "rules", "--check"]) == 0


# ------------------------------------------------------------ the kit's own tree

def test_the_kits_generated_rules_are_in_sync_with_its_registry():
    cfg = quality.load_config(KIT)
    assert quality.check_rules(KIT, cfg) == []
    assert quality.promotion_problems(cfg) == []


def test_every_kit_rule_is_report_only_and_has_a_test_that_can_go_red():
    """A rule file that sets `severity: error` is a promotion with no record;
    promotion goes through quality.json and --error at scan time."""
    rules = sorted((KIT / ".ast-grep" / "rules").rglob("*.yml"))
    assert rules, "the kit ships no ast-grep rules"
    tests = {re.search(r"^id: (\S+)", p.read_text(encoding="utf-8"), re.M).group(1): p
             for p in (KIT / ".ast-grep" / "rule-tests").rglob("*.yml")}
    for r in rules:
        text = r.read_text(encoding="utf-8")
        rid = re.search(r"^id: (\S+)", text, re.M).group(1)
        assert re.search(r"^severity: warning$", text, re.M), \
            "%s is not authored report-only" % r.name
        assert rid in tests, "%s has no rule test" % rid
        assert "\ninvalid:" in tests[rid].read_text(encoding="utf-8"), \
            "%s's test has no invalid case" % rid


# ------------------------------------------------------------ promotions

def test_a_promotion_without_its_record_is_named():
    cfg = {"promotions": {"ast-grep": [{"rule": "py-eval-exec"}],
                          "skillspector": [{"rule": "EA1", "date": "2026-09-22",
                                            "standing_count": 3, "reason": "x"}]}}
    problems = quality.promotion_problems(cfg)
    assert any("py-eval-exec" in p and "lacks date" in p for p in problems)
    assert any("EA1" in p and "measured zero standing" in p for p in problems)


@pytest.mark.parametrize("count", [None, False, 0.0, "0", 3])
def test_a_promotion_records_a_measured_integer_zero(count):
    """null records no measurement; False == 0 in Python but is not a count."""
    cfg = {"tools": {"ruff": {}}, "promotions": {"ruff": [
        {"rule": "S602", "date": "2026-09-22", "standing_count": count, "reason": "r"}]}}
    assert quality.promotion_problems(cfg), count
    cfg["promotions"]["ruff"][0]["standing_count"] = 0
    assert quality.promotion_problems(cfg) == []


# ------------------------------------------------------------ SkillSpector gate

def report(issues, recommendation="SAFE", score=10):
    return {"skill": {"source": ".claude/agents"},
            "risk_assessment": {"score": score, "recommendation": recommendation},
            "issues": [{"id": i, "pattern": "p", "severity": "HIGH",
                        "location": {"file": "a.md", "start_line": 1}} for i in issues]}


def test_secrets_class_ids_block_from_day_one_and_the_rest_report():
    cfg = quality.load_config(KIT)
    blocking, advisory = quality.judge_skillspector([report(["PE3", "EA1"])], cfg)
    assert len(blocking) == 1 and " PE3 " in blocking[0]
    assert len(advisory) == 1 and " EA1 " in advisory[0]


def test_a_promoted_skillspector_id_blocks_and_do_not_install_blocks():
    cfg = copy.deepcopy(quality.load_config(KIT))
    cfg["promotions"]["skillspector"] = [{"rule": "EA1", "date": "2026-09-22",
                                          "standing_count": 0, "reason": "r"}]
    blocking, _ = quality.judge_skillspector([report(["EA1"])], cfg)
    assert blocking
    blocking, _ = quality.judge_skillspector(
        [report([], recommendation="DO_NOT_INSTALL", score=80)], cfg)
    assert blocking == [".claude/agents: recommendation DO_NOT_INSTALL (score 80)"]


# ------------------------------------------------------------ pins

def test_a_bump_names_the_rollback_and_a_no_op_moves_nothing():
    cfg = copy.deepcopy(quality.load_config(KIT))
    cfg["tools"]["ast-grep"]["rollback"] = "0.0.1"   # a stale rollback to overwrite
    old = cfg["tools"]["ast-grep"]["version"]
    moved = quality.bump(cfg, {"ast-grep": "99.0.0", "skillspector": ""})
    assert moved == ["ast-grep %s -> 99.0.0 (rollback %s)" % (old, old)]
    assert cfg["tools"]["ast-grep"]["version"] == "99.0.0"
    assert cfg["tools"]["ast-grep"]["rollback"] == old
    assert quality.bump(cfg, {"ast-grep": "99.0.0"}) == []


def test_every_pin_carries_its_reason_and_lifting_condition():
    for name, pin in quality.load_config(KIT)["tools"].items():
        for field in ("version", "rollback", "reason", "lifting", "install"):
            assert pin.get(field), "%s pin lacks %s (UPGRADE_DISCIPLINE)" % (name, field)


# ------------------------------------------------------------ wiring

def test_the_lane_is_wired_into_ci_the_hooks_and_the_standard():
    ci = (KIT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "bash tools/quality/scan.sh ci" in ci
    assert "bash tools/quality/install.sh\n" in ci, "CI must install the PINNED scanners"
    bump = (KIT / ".github/workflows/scanner-bump.yml").read_text(encoding="utf-8")
    assert "schedule:" in bump and "quality.py bump" in bump and "--draft" in bump
    assert "gh workflow run ci.yml" in bump and "workflow_dispatch:" in ci, \
        "the bump PR must get CI without a secret: dispatch it"
    assert "gh issue create" in bump, "a repo that forbids Actions PRs still hears of the bump"
    scan = (KIT / "tools/quality/scan.sh").read_text(encoding="utf-8")
    assert "rules --check" in scan and "--no-llm" in scan and "--error=" in scan
    pre_commit = (KIT / "tools/git-hooks/pre-commit").read_text(encoding="utf-8")
    assert "quality.py rules" in pre_commit
    assert pre_commit.rstrip().endswith("exit 0"), "pre-commit must never block"
    assert "SKIP_PUSH_GATE" in (KIT / "tools/git-hooks/pre-push").read_text(encoding="utf-8")
    for tool in ("gitleaks git", "zizmor --offline", "actionlint", "--select \"$rsel\"",
                 "--yara-rules-dir", "quality.py baseline-path", "$q proofs",
                 "$q suppressions"):
        assert tool.replace("quality.py ", "$q ") in scan or tool in scan, tool
    assert "fetch-depth: 0" in ci, "gitleaks needs the full history in CI"
    assert "docs/SCAN_LANE.md" in (KIT / ".claude/skills/reviewer-integration/SKILL.md") \
        .read_text(encoding="utf-8"), "the learn loop must route findings to the scan lane"
    standards = (KIT / "docs/TESTING_STANDARDS.md").read_text(encoding="utf-8")
    assert "### 5.1 The structural-scan lane" in standards
    template = (KIT / "templates/FAILURE_PATTERNS.md.template").read_text(encoding="utf-8")
    assert "a fenced `ast-grep` block" in template


def test_quality_stays_stdlib_only():
    source = (KIT / "tools" / "wall" / "quality.py").read_text(encoding="utf-8")
    for banned in ("import yaml", "import requests", "import pytest"):
        assert banned not in source


# ------------------------------------------------------------ zizmor gate

def zfinding(ident, ignored=False, path=".github/workflows/ci.yml", row=24):
    return {"ident": ident, "desc": "d", "ignored": ignored,
            "determinations": {"severity": "High"},
            "locations": [{"symbolic": {"kind": "Primary",
                                        "key": {"Local": {"verbatim_path": path}}},
                           "concrete": {"location": {"start_point": {"row": row}}}}]}


def test_zizmor_is_report_only_until_an_audit_is_promoted():
    cfg = copy.deepcopy(quality.load_config(KIT))
    blocking, advisory = quality.judge_zizmor([zfinding("unpinned-uses")], cfg)
    assert blocking == [] and advisory == [
        ".github/workflows/ci.yml:25 unpinned-uses [High] d"]
    cfg["promotions"]["zizmor"] = [{"rule": "unpinned-uses", "date": "2026-09-22",
                                    "standing_count": 0, "reason": "r"}]
    blocking, _ = quality.judge_zizmor([zfinding("unpinned-uses"),
                                        zfinding("artipacked")], cfg)
    assert [b.split()[1] for b in blocking] == ["unpinned-uses"]


def test_an_inline_zizmor_ignore_is_neither_blocking_nor_reported():
    cfg = copy.deepcopy(quality.load_config(KIT))
    cfg["promotions"]["zizmor"] = [{"rule": "*", "date": "d", "standing_count": 0,
                                    "reason": "r"}]
    assert quality.judge_zizmor([zfinding("artipacked", ignored=True)], cfg) == ([], [])


def test_an_unreadable_zizmor_report_is_unknown_not_clean(tmp_path, capsys):
    bad = tmp_path / "z.json"
    bad.write_text("", encoding="utf-8")
    assert quality.main(["gate-zizmor", str(bad)]) == 1
    assert "not clean" in capsys.readouterr().err


# ------------------------------------------------------------ gitleaks record

def test_a_suppression_needs_a_dated_reason_directly_above_it():
    ok = "# 2026-09-22: fake RSA block, the scrubber test's fixture\nabc:f.py:private-key:3\n"
    assert quality.suppression_problems(ok) == []
    for bad in ("abc:f.py:private-key:3\n",
                "# fake RSA block, the scrubber test's fixture\nabc:f.py:rule:3\n",
                "# 2026-09-22\nabc:f.py:rule:3\n",
                "# 2026-09-22: fake RSA block, the fixture\n\nabc:f.py:rule:3\n"):
        assert len(quality.suppression_problems(bad)) == 1, bad


def test_the_kits_suppressions_and_fixtures_are_in_order():
    ignore = (KIT / quality.GITLEAKSIGNORE).read_text(encoding="utf-8")
    assert quality.suppression_problems(ignore) == []
    found, problems = quality.proofs(KIT)
    assert problems == []
    assert ("yara", "kit_skill_bypasses_git_hooks",
            quality.YARA_FIXTURES / "kit_skill_bypasses_git_hooks") in found


# ------------------------------------------------------------ custom-rule proofs

GL_RULE = '\n[[rules]]\nid = "kit-demo-token"\nregex = \'\'\'kitdemo_[a-z]{8}\'\'\'\n'


def test_rule_ids_are_read_from_rules_blocks_only():
    text = '[extend]\nuseDefault = true\n# [[rules]]\n# id = "commented"\n' + GL_RULE + \
           '\n[[allowlists]]\ndescription = "x"\n'
    assert quality.gitleaks_rule_ids(text) == ["kit-demo-token"]
    yar = "rule kit_a {\n condition: true\n}\nprivate rule kit_b { condition: true }\n"
    assert quality.yara_rule_names(yar) == ["kit_a", "kit_b"]


def test_a_custom_rule_without_its_fixture_and_a_fixture_without_its_rule_are_named(tmp_path):
    (tmp_path / quality.GITLEAKS_CONFIG).write_text(GL_RULE, encoding="utf-8")
    (tmp_path / quality.GITLEAKS_FIXTURES).mkdir(parents=True)
    (tmp_path / quality.GITLEAKS_FIXTURES / "kit-gone.txt").write_text("x", encoding="utf-8")
    (tmp_path / quality.YARA_DIR).mkdir(parents=True)
    (tmp_path / quality.YARA_DIR / "a.yar").write_text("rule kit_a { condition: true }",
                                                       encoding="utf-8")
    (tmp_path / quality.YARA_FIXTURES / "kit_old").mkdir(parents=True)
    found, problems = quality.proofs(tmp_path)
    assert found == []
    assert len(problems) == 4
    assert any("'kit-demo-token' has no fixture" in p for p in problems)
    assert any("kit-gone.txt has no rule" in p for p in problems)
    assert any("'kit_a' has no fixture directory" in p for p in problems)
    assert any("kit_old/ has no YARA rule" in p for p in problems)
    # An EMPTY fixture directory proves nothing either.
    (tmp_path / quality.YARA_FIXTURES / "kit_a").mkdir()
    assert any("'kit_a' has no fixture" in p for p in quality.proofs(tmp_path)[1])


def test_each_target_gets_its_own_baseline_file():
    assert quality.baseline_path(".claude/agents") == \
        quality.BASELINES / "claude__agents.yaml"
    assert quality.baseline_path(".claude/skills/wave/") == \
        quality.BASELINES / "claude__skills__wave.yaml"


def test_one_custom_yara_rule_is_promoted_by_name_not_the_whole_yr_id():
    cfg = copy.deepcopy(quality.load_config(KIT))
    cfg["promotions"]["skillspector"] = [{"rule": "yara:kit_a", "date": "d",
                                          "standing_count": 0, "reason": "r"}]
    r = report(["YR4", "YR4"])
    r["issues"][0]["pattern"] = "YARA rule 'kit_a': x"
    r["issues"][1]["pattern"] = "YARA rule 'kit_b': x"
    blocking, advisory = quality.judge_skillspector([r], cfg)
    assert len(blocking) == 1 and "kit_a" in blocking[0]
    assert len(advisory) == 1 and "kit_b" in advisory[0]


# ------------------------------------------------------------ install + latest

def test_the_install_plan_covers_every_pin_by_its_scheme():
    cfg = quality.load_config(KIT)
    plan = quality.install_plan(cfg)
    assert len(plan) == len(cfg["tools"])
    assert "pip ast-grep-cli==%s" % cfg["tools"]["ast-grep"]["version"] in plan
    assert "release gitleaks/gitleaks %s" % cfg["tools"]["gitleaks"]["version"] in plan
    assert any(p.startswith("pip skillspector @ git+https://") for p in plan)
    bad = {"tools": {"x": {"install": "brew:x", "version": "1"}}}
    with pytest.raises(ValueError, match="unknown install scheme"):
        quality.install_plan(bad)


def test_release_tags_sort_numerically_and_prereleases_are_dropped():
    tags = ["v2.9.6", "v2.10.0", "v2.11.0-rc1", "v2.9.10", "nightly"]
    assert max(quality._stable(tags), key=quality.version_key) == "v2.10.0"


def test_bump_refuses_a_tool_with_no_pin(capsys):
    with pytest.raises(SystemExit):
        quality.main(["bump", "--set", "nope=1.0"])
    assert "unknown tool 'nope'" in capsys.readouterr().err


# ------------------------------------------------------------ the kit's workflows

def test_every_action_is_pinned_to_a_sha_and_checkout_persists_no_credentials():
    for wf in sorted((KIT / ".github" / "workflows").glob("*.yml")):
        text = wf.read_text(encoding="utf-8")
        for ref in re.findall(r"uses:\s*(\S+)", text):
            if ref.startswith(("./", "$/")):
                continue  # this repository's own action or workflow, at this commit
            assert re.fullmatch(r"[\w.-]+/[\w./-]+@[0-9a-f]{40}", ref), \
                "%s: %s is not pinned to a commit SHA" % (wf.name, ref)
        checkouts = text.count("actions/checkout@")
        assert text.count("persist-credentials: false") == checkouts, wf.name
        assert re.search(r"^permissions: \{\}$", text, re.M), \
            "%s grants workflow-wide permissions; grant them per job" % wf.name


# ------------------------------------------------------------ fence parsing

RULE_BODY = "language: python\nrule:\n  pattern: eval($X)\n"
TEST_BODY = "invalid:\n  - eval(s)\n"


def fenced(rule_open="```ast-grep", rule_close="```", test_open="```ast-grep-test",
           test_close="```"):
    return ("## F-X-001 - x\n\n%s\n%s%s\n\n%s\n%s%s\n"
            % (rule_open, RULE_BODY, rule_close, test_open, TEST_BODY, test_close))


@pytest.mark.parametrize("kw", [
    {"rule_close": "`````"},                                   # longer closer
    {"rule_open": "````ast-grep", "rule_close": "````"},       # longer opener
    {"rule_open": "  ```ast-grep", "rule_close": "   ```"},    # up to 3 spaces
    {"rule_open": "~~~ast-grep", "rule_close": "~~~~"},         # tilde fences
    {"rule_close": "```   "},                                  # trailing spaces
])
def test_commonmark_fences_all_generate_the_rule(kw):
    out = quality.render_rules("F.md", fenced(**kw))
    assert "pattern: eval($X)" in out["rules/f-x-001.yml"]


def test_a_shorter_or_mixed_closer_does_not_close_the_block():
    # A ``` inside a ```` block is content; a ~~~ does not close a ``` block.
    for kw in ({"rule_open": "````ast-grep", "rule_close": "```\n````"},
               {"rule_close": "~~~\n```"}):
        out = quality.render_rules("F.md", fenced(**kw))
        assert "pattern: eval($X)" in out["rules/f-x-001.yml"], kw


def test_a_four_space_indented_example_is_prose_not_a_rule():
    text = "## F-X-001 - x\n\n    ```ast-grep\n    language: python\n    rule: x\n    ```\n"
    assert quality.render_rules("F.md", text) == {}


def test_an_unclosed_rule_block_is_refused_not_dropped():
    text = "## F-X-001 - x\n\n```ast-grep\n" + RULE_BODY
    with pytest.raises(quality.RuleError, match=r"^F\.md:3 F-X-001: .* never closed"):
        quality.render_rules("F.md", text)


def test_a_bump_to_a_non_version_string_is_refused():
    cfg = copy.deepcopy(quality.load_config(KIT))
    for bad in ("1.0; rm -rf ~", "$(id)", "v1.0-rc1", ""):
        if bad:
            with pytest.raises(ValueError, match="not a release version"):
                quality.bump(cfg, {"ruff": bad})
    assert quality.bump(cfg, {"skillspector": "v9.9.9"})


def test_the_kits_workflows_need_no_secrets():
    """A kit adopted into any repository must run on the built-in token alone:
    a workflow that reads a secret is one step every adopter has to finish,
    and the ones who do not get a lane that silently does less."""
    for wf in sorted((KIT / ".github" / "workflows").glob("*.yml")):
        assert "secrets." not in wf.read_text(encoding="utf-8"), wf.name


# ------------------------------------------------------------ F-PARTIAL-VIEW-001

def _git(*args, cwd):
    import subprocess
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                   env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
                        "PATH": __import__("os").environ["PATH"],
                        "HOME": str(cwd)})


def test_ci_scan_refuses_a_shallow_history(tmp_path, capsys):
    """The class-guard for F-PARTIAL-VIEW-001. A secrets scan over a shallow
    clone passes on the commits it holds; the ones it cannot see are the ones
    the full-history gate fails on. In ci mode that is unknown, not clean."""
    origin = tmp_path / "origin"
    origin.mkdir()
    _git("init", "-q", "-b", "main", cwd=origin)
    for n in (1, 2):
        (origin / "f.txt").write_text(str(n), encoding="utf-8")
        _git("add", "f.txt", cwd=origin)
        _git("commit", "-q", "-m", "c%d" % n, cwd=origin)
    shallow, full = tmp_path / "shallow", tmp_path / "full"
    _git("clone", "-q", "--depth", "1", "file://%s" % origin, str(shallow), cwd=tmp_path)
    _git("clone", "-q", "file://%s" % origin, str(full), cwd=tmp_path)
    for clone in (shallow, full):
        (clone / quality.CONFIG).parent.mkdir(parents=True)
        (clone / quality.CONFIG).write_text(
            (KIT / quality.CONFIG).read_text(encoding="utf-8"), encoding="utf-8")

    assert quality.main(["--root", str(shallow), "history", "--ci"]) == 1
    assert "UNKNOWN, not clean" in capsys.readouterr().err
    assert quality.main(["--root", str(shallow), "history"]) == 3, \
        "local mode reports UNKNOWN (3): never blocking, never 'clean' (F-STATUS-001)"
    assert "covers less than CI will" in capsys.readouterr().err
    assert quality.main(["--root", str(full), "history", "--ci"]) == 0
    bare = tmp_path / "no-git"
    (bare / quality.CONFIG).parent.mkdir(parents=True)
    (bare / quality.CONFIG).write_text(
        (KIT / quality.CONFIG).read_text(encoding="utf-8"), encoding="utf-8")
    assert quality.main(["--root", str(bare), "history", "--ci"]) == 1, \
        "no git history at all is unknown too"


def test_the_scan_lane_wires_the_full_view_check_and_the_registry_names_it():
    scan = (KIT / "tools/quality/scan.sh").read_text(encoding="utf-8")
    assert "$q history --ci || fail=1" in scan
    assert "3) skipped=$((skipped + 1))" in scan, "a local partial history is UNKNOWN, not clean"
    template = (KIT / "templates/FAILURE_PATTERNS.md.template").read_text(encoding="utf-8")
    block = template.split("### F-PARTIAL-VIEW-001", 1)[1].split("\n### ", 1)[0]
    assert "`test_ci_scan_refuses_a_shallow_history`" in block
    assert "VARIANT:" in block


# ------------------------------------------------------------ the kit's own registry

def test_the_canary_that_runs_new_releases_holds_no_write_token():
    """F-TRUST-SPLIT-001. The job that installs and EXECUTES the newest
    third-party releases may read the repository and nothing else; only the
    job that runs this repository's own code may write."""
    bump = (KIT / ".github/workflows/scanner-bump.yml").read_text(encoding="utf-8")
    canary = bump.split("\n  canary:", 1)[1].split("\n  propose:", 1)[0]
    propose = bump.split("\n  propose:", 1)[1]
    perms = canary.split("permissions:", 1)[1].split("outputs:", 1)[0]
    assert [ln.strip() for ln in perms.strip().splitlines()] == ["contents: read"], perms
    assert "GH_TOKEN" not in canary and "token:" not in canary
    assert "persist-credentials: false" in canary
    run = "bash tools/quality/install.sh"
    assert run in canary and run not in propose, \
        "third-party code must run only in the read-only job"
    assert "quality.py bump" in propose, "the writer re-applies the validated bump itself"


def test_pre_commit_generates_rules_from_the_staged_registry(tmp_path):
    """F-DERIVED-INDEX-001. Stage one registry entry, leave a second unstaged,
    commit: the commit must carry exactly the staged entry's rule, and the
    committed tree must pass `rules --check`."""
    import shutil
    import subprocess
    repo = tmp_path / "host"
    repo.mkdir()
    env = dict(__import__("os").environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t", HOME=str(tmp_path))

    def git(*args):
        return subprocess.run(["git", *args], cwd=repo, env=env, check=True,
                              capture_output=True, text=True).stdout

    git("init", "-q", "-b", "work")
    shutil.copytree(KIT / "tools", repo / "tools",
                    ignore=shutil.ignore_patterns("__pycache__"))
    (repo / quality.CONFIG).write_text(
        json.dumps(dict(quality.load_config(KIT), promotions={})), encoding="utf-8")
    git("add", "-A")
    git("commit", "-q", "-m", "base")
    subprocess.run(["bash", "tools/git-hooks/install.sh"], cwd=repo, env=env,
                   check=True, capture_output=True)
    reg = repo / "FAILURE_PATTERNS.md"
    reg.write_text(ENTRY, encoding="utf-8")
    git("add", "FAILURE_PATTERNS.md")
    reg.write_text(ENTRY.replace("## F-PROSE-001", "## F-EXTRA-001 - unstaged\n\n"
                                 "```ast-grep\nlanguage: python\nrule:\n  pattern: exec($X)\n```\n\n"
                                 "```ast-grep-test\ninvalid:\n  - exec(s)\n```\n\n## F-PROSE-001"),
                   encoding="utf-8")
    git("commit", "-q", "-m", "add a class")

    committed = git("show", "--name-only", "--format=", "HEAD").split()
    assert ".ast-grep/rules/generated/f-substr-001.yml" in committed
    assert not any("f-extra-001" in f for f in committed), \
        "the unstaged entry's rule was committed"
    tree = tmp_path / "tree"
    tree.mkdir()
    subprocess.run("git archive HEAD | tar -x -C %s" % tree, shell=True, cwd=repo,  # noqa: S602
                   env=env, check=True)
    assert quality.check_rules(tree, quality.load_config(tree)) == []


def test_no_global_gitleaks_allowlist_hides_the_fixture_directory():
    """A global path allowlist over the fixtures would hide a real credential
    committed there from every rule, built-in ones included. Exemptions are
    per rule, for that rule's own fixture file only."""
    text = (KIT / quality.GITLEAKS_CONFIG).read_text(encoding="utf-8")
    live = "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith("#"))
    assert not re.search(r"^\[\[allowlists\]\]", live, re.M), \
        "a global [[allowlists]] block is back in .gitleaks.toml"
    for block in live.split("[[rules]]")[1:]:
        rid = re.search(r"^id\s*=\s*['\"]([^'\"]+)", block, re.M).group(1)
        for path in re.findall(r"paths\s*=\s*\[([^\]]*)\]", block):
            assert rid in path and ".txt" in path, \
                "rule %s allowlists more than its own fixture: %s" % (rid, path)


def test_the_bump_workflow_runs_with_pipefail():
    bump = (KIT / ".github/workflows/scanner-bump.yml").read_text(encoding="utf-8")
    assert re.search(r"^defaults:\n  run:\n    shell: bash$", bump, re.M), \
        "without shell: bash, a failed lookup piped through tee passes"
