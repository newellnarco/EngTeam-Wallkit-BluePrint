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
    assert any("EA1" in p and "zero standing" in p for p in problems)


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
    scan = (KIT / "tools/quality/scan.sh").read_text(encoding="utf-8")
    assert "rules --check" in scan and "--no-llm" in scan and "--error=" in scan
    pre_commit = (KIT / "tools/git-hooks/pre-commit").read_text(encoding="utf-8")
    assert "quality.py rules" in pre_commit
    assert pre_commit.rstrip().endswith("exit 0"), "pre-commit must never block"
    assert "SKIP_PUSH_GATE" in (KIT / "tools/git-hooks/pre-push").read_text(encoding="utf-8")
    standards = (KIT / "docs/TESTING_STANDARDS.md").read_text(encoding="utf-8")
    assert "### 5.1 The structural-scan lane" in standards
    template = (KIT / "templates/FAILURE_PATTERNS.md.template").read_text(encoding="utf-8")
    assert "a fenced `ast-grep` block" in template


def test_quality_stays_stdlib_only():
    source = (KIT / "tools" / "wall" / "quality.py").read_text(encoding="utf-8")
    for banned in ("import yaml", "import requests", "import pytest"):
        assert banned not in source
