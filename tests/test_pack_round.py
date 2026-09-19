"""Pins on the round-3 process-pack material.

Same contract as test_process_docs.py and test_fleet_round.py: every phrase
below is a rule somebody is briefed from, and each of these documents reads
perfectly well with the rule quietly removed -- which is the failure mode. A
standard that loses "the test derives from the requirement, never from the
code" still looks like a standard and starts accepting tests written after the
mechanism; an upgrade document that loses the cold soak still looks complete
and starts calling an import success a verified bump.

Three of the pins here are about what is DELIBERATELY ABSENT: the three parked
conflicts must stay parked, with both positions quoted, rather than resolving
into whichever default a later editor happened to prefer. A silent pick is the
defect this material exists to prevent, and it is invisible in a diff.

The two new templates inherit the parametrized scaffolding pins (ASCII,
placeholders, header block, no host-specific detail) through
test_scaffolding.EXPECTED_TEMPLATES; this file pins their content.
"""

from __future__ import annotations

from pathlib import Path

from test_scaffolding import EXPECTED_TEMPLATES

KIT = Path(__file__).resolve().parents[1]

STANDARD_T = KIT / "templates" / "ENGINEERING_STANDARD.md.template"
DESIGN_T = KIT / "templates" / "DESIGN_DOC.md.template"
OWNER_DECISIONS_T = KIT / "templates" / "OWNER_DECISIONS.md.template"
FAILURE_PATTERNS_T = KIT / "templates" / "FAILURE_PATTERNS.md.template"
BEST_PRACTICES_T = KIT / "templates" / "BEST_PRACTICES.md.template"
SHIP_CHECKLIST_T = KIT / "templates" / "SHIP_CHECKLIST.md.template"
RULES_T = KIT / "templates" / "RULES.md.template"
DOCS_MAP_T = KIT / "templates" / "DOCS_MAP.md.template"

UPGRADE = KIT / "docs" / "UPGRADE_DISCIPLINE.md"
GIT_HOOKS = KIT / "docs" / "GIT_HOOKS.md"
ITEM_AUTHORING = KIT / "docs" / "ITEM_AUTHORING.md"
TESTING = KIT / "docs" / "TESTING_STANDARDS.md"
COMPLIANCE = KIT / "docs" / "COMPLIANCE_POSTURE.md"
FAST_TRACK = KIT / "docs" / "FAST_TRACK.md"
DEPLOY = KIT / "docs" / "DEPLOYMENT_TARGETS.md"
INSTALL = KIT / "docs" / "INSTALL.md"
INTAKE = KIT / "docs" / "TEMPLATE_INTAKE.md"
WAVE_REPORT = KIT / "docs" / "handoffs" / "wave-report.md"
HOOKS_README = KIT / ".claude" / "hooks" / "README.md"
HOOKS_EXAMPLE = KIT / ".claude" / "hooks" / "hooks.json.example"
README = KIT / "README.md"

PARKED = "PARKED - conflicting fleet evidence; the engineer rules."


def _text(p: Path) -> str:
    assert p.exists(), f"{p} missing"
    return p.read_text(encoding="utf-8")


def _flat(p: Path) -> str:
    """Whitespace-flattened, with blockquote markers dropped.

    The parked-conflict blocks are blockquotes, so a `>` lands in the middle of
    every sentence that wraps. Dropping the marker token compares the prose
    somebody reads rather than the markdown it is wrapped in.
    """
    return " ".join(w for w in _text(p).split() if w != ">")


# ------------------------------------------------- the adopted standard

def test_both_new_templates_are_in_the_scaffolding_roster():
    """They must inherit the ASCII/placeholder/header/no-host-detail pins
    rather than being a pair of documents nothing checks."""
    for name in ("ENGINEERING_STANDARD.md.template", "DESIGN_DOC.md.template"):
        assert name in EXPECTED_TEMPLATES, f"{name} is not in EXPECTED_TEMPLATES"
        assert (KIT / "templates" / name).is_file()


def test_standard_carries_its_attribution():
    t = _flat(STANDARD_T).lower()
    assert "distilled from a fleet-distributed engineering standard proven " \
        "across three deployments" in t


def test_standard_keeps_the_bindings_zone_as_the_distribution_seam():
    t = _text(STANDARD_T)
    assert "## Bindings - the parts specific to this repository" in t
    for slot in ("<REGISTRY>", "<IRREVERSIBLE>", "<MUTATION>", "<SESSION_LOG>"):
        assert slot in t, f"Bindings lost the {slot} slot"
    assert "A slot with nothing to bind to is not an exemption" in _flat(STANDARD_T)


def test_standard_says_the_shared_body_is_not_edited_locally():
    """The whole point of the split: a locally-edited body is the third copy."""
    t = _flat(STANDARD_T)
    assert "Everything above **Bindings** is the shared body" in t
    assert "change it upstream, never locally" in t


def test_all_three_conflicts_carry_the_patron_rulings():
    """Originally pinned three PARKED markers. The Patron ruled all three on
    2026-09-19 (DEC-0013/0014/0015), so the pin now asserts the RULED form:
    each marker cites its decision AND both weighed positions remain quoted -
    a ruling that erases the losing evidence is how it gets re-litigated."""
    t = _text(STANDARD_T)
    assert "PARKED" not in t, "a parked marker survived the rulings"
    for dec in ("DEC-0013", "DEC-0014", "DEC-0015"):
        assert f"RULED ({dec}, the Patron, 2026-09-19)" in t, f"{dec} ruling missing"
    assert t.count("The two\n> positions that were weighed:") + t.count("The two positions that were weighed:") >= 1
    assert t.count("Position A:") >= 3 and t.count("Position B:") >= 3


def test_each_parked_conflict_quotes_both_positions():
    t = _text(STANDARD_T)
    assert t.count("Position A:") == 3
    assert t.count("Position B:") == 3


def test_the_ruled_conflicts_are_the_three_known_ones():
    """Evolved with the rulings (DEC-0013/14/15): the three topics must still
    be identifiable in their ruled form."""
    t = _flat(STANDARD_T)
    assert "Draft-review is a per-lane pin" in t
    assert "full pyramid runs at the ready flip and gates the merge" in t
    assert "worktree isolation is RECOMMENDED" in t


def test_standard_does_not_duplicate_the_reviewer_vendor_tables():
    """Per-vendor meter facts live once, in the lane register."""
    t = _text(STANDARD_T)
    for vendor in ("CodeRabbit", "Copilot"):
        assert vendor not in t, f"{vendor} meter facts duplicated into the standard"
    flat = _flat(STANDARD_T)
    assert "REVIEWER_LANES.md" in flat and "docs/WORKFLOW.md` section 10" in flat


def test_standard_points_at_the_digest_instead_of_re_listing_the_taxonomy():
    t = _flat(STANDARD_T)
    assert "recurring-classes digest at the top of `FAILURE_PATTERNS.md`" in t
    assert "scanning the description instead of the thing" not in t, (
        "the shared taxonomy is duplicated here; it merges into the registry digest"
    )
    assert "`VARIANT:` fixture" in t


def test_standard_states_the_order_and_forbids_tests_derived_from_code():
    t = _flat(STANDARD_T)
    assert "RCA -> requirement -> test -> code. Always that order." in t
    assert "Write the tests from the requirement - never from the code." in t
    assert "Writing code first makes test-first impossible" in t


def test_standard_carries_the_three_clause_kinds():
    t = _flat(STANDARD_T)
    for kind in ("Must always be true", "Must never be true",
                 "Must survive refutation"):
        assert kind in t, f"clause-kind table lost {kind!r}"
    assert "A clause that cannot be decided is not a requirement, it is a hope" in t


def test_standard_done_definition_keeps_counts_and_the_last_review_round():
    t = _flat(STANDARD_T)
    assert "Every **count the documentation states** has been compared against reality" in t
    assert "The last reviewer round has landed" in t


def test_standard_binds_irreversibility_to_the_register_and_the_probe():
    t = _flat(STANDARD_T)
    assert "can a revert restore it?" in t
    assert "A green suite describes a runner; only the probe describes the world" in t


# ------------------------------------------------- P-1 in the authoring rules

def test_item_authoring_carries_the_order_and_the_clause_kinds():
    t = _flat(ITEM_AUTHORING)
    assert "root cause -> requirement -> test -> code, and it is an order, not a set" in t
    assert "a test derives from the requirement, never from the code" in t
    for kind in ("must always be true", "must never be true",
                 "must survive refutation"):
        assert kind in t, f"authoring rules lost the {kind!r} clause kind"


def test_item_authoring_rejects_the_slogan_requirement():
    t = _flat(ITEM_AUTHORING)
    assert "Compressing it to a slogan is the same defect as omitting it" in t


# ------------------------------------------------- P-2 irreversible register

def test_owner_decisions_carries_the_irreversible_register():
    t = _text(OWNER_DECISIONS_T)
    assert "## 7. The irreversible-surfaces register" in t
    flat = _flat(OWNER_DECISIONS_T)
    assert "can a revert restore it?" in flat
    assert "IR-001" in t and "the probe that reports after a change" in t


def test_irreversible_register_requires_a_probe_not_a_green_suite():
    t = _flat(OWNER_DECISIONS_T)
    assert "the evidence is a probe against the real system" in t
    assert "A green suite describes a runner; only the probe describes the world" in t
    assert "An empty register is not an exemption - it is the first gap to close" in t


def test_irreversible_register_is_cross_referenced_from_the_compliance_posture():
    t = _flat(COMPLIANCE)
    assert "irreversible-surfaces register" in t
    assert "OWNER_DECISIONS template" in t


# ------------------------------------------------- P-3 upgrade discipline

def test_upgrade_discipline_classifies_by_semver_and_isolates_a_major():
    t = _flat(UPGRADE)
    for word in ("**Patch**", "**Minor**", "**Major**"):
        assert word in t, f"upgrade classes lost {word}"
    assert "its own narrow change** and never rides along" in t
    assert "The publisher's classification is a claim like any other" in t


def test_upgrade_discipline_carries_the_transitive_native_class():
    t = _flat(UPGRADE)
    assert "transitive dependency that ships native code is treated as a direct major" in t
    assert "no stack trace in the host language" in t


def test_upgrade_discipline_requires_a_cold_soak_not_an_import():
    t = _flat(UPGRADE)
    assert "cold soak" in t
    assert "`import` succeeding is not the bar" in t


def test_upgrade_discipline_reads_a_surviving_reinstall_as_a_bad_artifact():
    t = _flat(UPGRADE)
    assert "survives a forced reinstall of the suspect package is a bad artifact" in t
    assert "lifting condition" in t and "OWNER_DECISIONS.md" in t


def test_failure_patterns_seeds_the_native_wheel_class_with_a_variant():
    t = _text(FAILURE_PATTERNS_T)
    assert "### F-NATIVE-WHEEL-001" in t
    block = t.split("### F-NATIVE-WHEEL-001", 1)[1].split("\n### ", 1)[0]
    for field in ("**Symptom:**", "**Root cause:**", "**Check:**"):
        assert field in block, f"F-NATIVE-WHEEL-001 is missing {field}"
    assert "> class-guard:" in block and "VARIANT:" in block


def test_inherited_classes_do_not_inflate_the_seeded_registry():
    """The seeded set is 'shipped and failed here'; inherited classes have not.
    Two other suites pin the count at 17, so this pins the STRUCTURE that keeps
    it true rather than re-asserting the number."""
    body = _text(FAILURE_PATTERNS_T)
    assert "## Inherited classes - paid for elsewhere, not yet bitten here" in body
    seeded = [b for b in body.split("\n## ")[1:] if b.startswith("F-")]
    inherited = [b for b in body.split("\n### ")[1:] if b.startswith("F-")]
    assert len(seeded) == 17, f"inherited classes leaked into the seeded set: {len(seeded)}"
    assert len(inherited) >= 4, "the inherited block lost its entries"
    assert "On first occurrence here, an inherited class is promoted" in _flat(
        FAILURE_PATTERNS_T)


def test_class_guard_convention_requires_a_variant_fixture():
    t = _flat(FAILURE_PATTERNS_T)
    assert "Every class guard carries a `VARIANT:` fixture" in t
    assert "can only find what the registry already knows" in t


def test_ship_checklist_gates_dependencies_and_irreversible_surfaces():
    t = _flat(SHIP_CHECKLIST_T)
    assert "no unaddressed major bump rides along" in t
    assert "cold soak" in t
    assert "probe against the real system has reported" in t


def test_ship_checklist_closes_the_done_definition_residue():
    t = _flat(SHIP_CHECKLIST_T)
    assert "Every count this change's documentation states was compared against reality" in t
    assert "The last review round has landed" in t


# ------------------------------------------------- P-4 / P-8 / P-17 practices

def test_best_practices_records_a_bandaid_loudly_and_keeps_the_root_open():
    t = _flat(BEST_PRACTICES_T)
    assert "RECORDED as a bandaid, loudly" in t
    assert "with the root left open as a work item" in t
    assert "A bandaid presented as a fix is the most expensive lie in the registry" in t


def test_best_practices_allows_inconclusive_and_pre_arms_the_evidence():
    t = _flat(BEST_PRACTICES_T)
    assert "Inconclusive is an honest verdict" in t
    assert "pre-arm the missing evidence" in t
    assert "a failure you will debug by hand twice" in t


def test_best_practices_keeps_the_troubleshooting_tree_and_the_instrument_check():
    t = _flat(BEST_PRACTICES_T)
    assert "written troubleshooting tree" in t
    assert "A surprising number is usually the MEASUREMENT, not the system" in t
    assert "never report a metric without its baseline" in t


def test_best_practices_distrusts_a_rule_satisfied_in_its_own_session():
    t = _flat(BEST_PRACTICES_T)
    assert "A rule written and satisfied in the same session is suspect" in t
    assert "Scope is chosen for a reason about evidence, never about workload" in t


def test_best_practices_seeds_the_three_logging_rules():
    t = _flat(BEST_PRACTICES_T)
    assert "Pre-arm the evidence for failures whose evidence lives outside your logs" in t
    assert "one line per interval, not sixty a second" in t
    assert "comes from the live collection, never a literal" in t


def test_best_practices_forbids_no_verify():
    t = _flat(BEST_PRACTICES_T)
    assert "never `--no-verify`" in t
    assert "named** environment-variable escape hatch" in t


# ------------------------------------------------- P-5 local hooks

def test_git_hooks_doc_exists_and_is_indexed():
    assert GIT_HOOKS.is_file()
    r = _text(README)
    assert "`GIT_HOOKS.md`" in r, "GIT_HOOKS.md has no row in the docs table"
    assert "`UPGRADE_DISCIPLINE.md`" in r, "UPGRADE_DISCIPLINE.md has no row"


def test_git_hooks_makes_install_step_zero():
    t = _flat(GIT_HOOKS)
    assert "Hook install is step 0 of provisioning - before any step that can fail" in t


def test_git_hooks_blocks_default_branch_and_runs_the_free_gate():
    t = _flat(GIT_HOOKS)
    assert "Block a direct push to the default branch" in t
    assert "Only definite failures block" in t


def test_git_hooks_forbids_no_verify_and_names_the_escape_hatch():
    t = _flat(GIT_HOOKS)
    assert "Never bypass with `--no-verify`" in t
    assert "named** environment-variable escape hatch" in t
    assert "greppable" in t


def test_git_hooks_pins_line_endings_and_the_baseline_ratchet():
    t = _flat(GIT_HOOKS)
    assert "eol=lf" in t and "eol=crlf" in t
    assert "git add --renormalize ." in t
    assert "fail only on **new** drift" in t
    assert "The baseline **shrinks**" in t


# ------------------------------------------------- P-6 / P-15 testing

def test_mutation_protocol_aborts_on_an_injection_that_changes_nothing():
    t = _flat(TESTING)
    assert "An injection that changes nothing is an ERROR that aborts the sweep" in t
    assert '"Not caught" and "never applied" are indistinguishable' in t


def test_mutation_protocol_anchors_from_the_file_and_breaks_the_call_site():
    t = _flat(TESTING)
    assert "Derive the anchor from the file, never from memory" in t
    assert "Attach the verdict to the exit status" in t
    assert "Break the call site as well as the function" in t


def test_testing_standards_treats_flaky_as_broken():
    t = _flat(TESTING)
    assert "Flaky is broken" in t
    assert "fixed or quarantined with a work item the day it flakes" in t


def test_testing_standards_converts_owner_found_defects_into_guards():
    t = _flat(TESTING)
    assert "Every defect the owner finds by hand converts into a guard" in t
    assert "owner-found becomes self-found" in t


# ------------------------------------------------- P-9 session scaffolding

def test_hooks_readme_documents_both_session_start_patterns():
    t = _flat(HOOKS_README)
    assert "Pattern A -- instruction injection" in t
    assert "additionalContext" in t
    assert "Pattern B -- the provisioning skeleton" in t


def test_provisioning_skeleton_carries_the_honesty_accumulator():
    """Both halves pinned on their own artifact: the fragment's verdict line,
    and the rule beside it. The prose repeats the phrase the fragment prints,
    so an assertion on the phrase alone survives deleting either one (the
    dead-assertion class, TESTING_STANDARDS section 3c -- measured here: the
    first version of this test survived its own mutation)."""
    t = _flat(HOOKS_README)
    assert 'note "provisioning INCOMPLETE -- degraded: $DEGRADED"' in t, (
        "the skeleton's verdict line is gone; the fragment now claims ready"
    )
    assert 'DEGRADED="${DEGRADED:+$DEGRADED, }$1"' in t, "no accumulator"
    assert 'A masked failure reports "provisioning INCOMPLETE" and exits ' \
        "non-zero." in t
    assert "Status lies at provision time surface as mystery failures an hour later" in t


def test_hooks_readme_says_why_no_session_start_script_ships():
    """Documented as patterns, not shipped as executables -- and the reason is
    stated, or the absence reads as an oversight."""
    t = _flat(HOOKS_README)
    assert "The kit ships **facts-layer hooks only**" in t
    assert "you write the script" in t
    assert "A provisioning hook may legitimately exit non-zero" in t


def test_hooks_example_explains_the_missing_session_start_block():
    t = _flat(HOOKS_EXAMPLE)
    assert "No SessionStart entry is configured here on purpose" in t


# ------------------------------------------------- templates + intake

def test_design_doc_template_carries_the_slice_plan_and_the_rollback():
    t = _flat(DESIGN_T)
    assert "Each slice is independently shippable and is **one pull request**" in t
    assert "A design without a rollback story is not done" in t


def test_design_doc_template_carries_the_arc_fields_item_authoring_requires():
    t = _text(DESIGN_T)
    for heading in ("## 1. Intent", "## 2. Boundary - explicit non-goals",
                    "## 5. Decisions in scope", "## 6. Declared data uses",
                    "## 7. Slice plan", "## 10. Open questions"):
        assert heading in t, f"design template is missing {heading}"


def test_intake_has_sections_for_both_new_templates_and_ends_with_the_usage():
    t = _text(INTAKE)
    s10 = t.find("## 10. ENGINEERING_STANDARD.md.template")
    s11 = t.find("## 11. DESIGN_DOC.md.template")
    usage = t.find("## Using this document")
    assert -1 < s10 < s11 < usage, "intake sections 10/11 are missing or misordered"
    assert "run the eleven sections as one batched question round" in _flat(INTAKE)


def test_intake_asks_for_the_irreversible_surfaces_and_the_parked_rulings():
    t = _flat(INTAKE)
    assert "Which surfaces here are irreversible" in t
    assert "Which of the three parked conflicts does this repository need ruled?" in t


def test_docs_map_template_schedules_the_periodic_full_tree_audit():
    t = _flat(DOCS_MAP_T)
    assert "## 3.5 The periodic full-tree audit" in t
    assert "an audit whose findings live only in its own report changed nothing" in t.lower()
    assert "index hygiene **in both directions**" in t


# ------------------------------------------------- remaining rows

def test_fast_track_carries_the_three_cost_levers():
    t = _flat(FAST_TRACK)
    assert "Scope the push trigger to the default branch and pull requests" in t
    assert "One concurrency group per branch, cancelling in progress" in t
    assert "SPLIT restore and save steps, with the save after the install" in t


def test_deployment_targets_carries_the_never_reap_discipline():
    t = _flat(DEPLOY)
    assert "never treat **not serving** as **dead** without positive liveness evidence" in t
    assert "cannot prove it owns" in t
    assert "F-REAP-001" in t


def test_install_carries_the_two_credential_stores_and_the_headless_tick():
    t = _flat(INSTALL)
    assert "reads the MACHINE credential store" in t
    assert "GIT_TERMINAL_PROMPT=0" in t
    assert "fails fast with an exit code" in t


def test_rules_template_reads_an_unsigned_file_as_all_grants_off():
    t = _flat(RULES_T)
    assert "An unsigned file reads as all-grants-off" in t
    assert "A grant that is no longer wanted is **deleted**, not ignored" in t


def test_rules_template_fails_closed_on_an_unattended_loop():
    t = _flat(RULES_T)
    assert "throwaway working copy, never the live checkout" in t
    assert "Fail closed:** could not verify means block" in t
    assert "documented kill switch" in t


def test_wave_report_carries_the_vetting_notes_section():
    t = _text(WAVE_REPORT)
    assert "## VETTED -- don't re-litigate" in t
    flat = _flat(WAVE_REPORT)
    assert "don't re-diagnose" in flat
    assert "Every line names the evidence" in flat
