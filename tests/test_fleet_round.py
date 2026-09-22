"""Pins on the round-2 fleet-mined material.

Same contract as test_process_docs.py: every phrase below is a rule an agent is
briefed from, and each of these documents reads perfectly well with the rule
quietly removed -- which is exactly the failure mode. A registry that loses
"never applied to an UNKNOWN reading" still looks like a registry and starts
sanctioning broken instruments; a probe roster that loses "ERROR is never a
pass" still looks like a protocol and starts passing probes that did not run.

The two new templates inherit the parametrized scaffolding pins (ASCII,
placeholders, header block, no host-specific detail) through
test_scaffolding.EXPECTED_TEMPLATES; this file pins their content.
"""

from __future__ import annotations

from pathlib import Path

KIT = Path(__file__).resolve().parents[1]

OWNER_DECISIONS_T = KIT / "templates" / "OWNER_DECISIONS.md.template"
REVIEWER_LANES_T = KIT / "templates" / "REVIEWER_LANES.md.template"
FAILURE_PATTERNS_T = KIT / "templates" / "FAILURE_PATTERNS.md.template"
BEST_PRACTICES_T = KIT / "templates" / "BEST_PRACTICES.md.template"
SHIP_CHECKLIST_T = KIT / "templates" / "SHIP_CHECKLIST.md.template"
DIAG = KIT / "docs" / "DIAGNOSTICS_LOOP.md"
TESTING = KIT / "docs" / "TESTING_STANDARDS.md"
FAST_TRACK = KIT / "docs" / "FAST_TRACK.md"
FLEET = KIT / "docs" / "FLEET.md"
LIFECYCLE = KIT / "docs" / "SESSION_LIFECYCLE.md"
INTAKE = KIT / "docs" / "TEMPLATE_INTAKE.md"
REVIEWER_SKILL = KIT / ".claude" / "skills" / "reviewer-integration" / "SKILL.md"
README = KIT / "README.md"


def _text(p: Path) -> str:
    assert p.exists(), f"{p} missing"
    return p.read_text(encoding="utf-8")


def _flat(p: Path) -> str:
    """Whitespace-normalised: every pin here is a sentence that wraps, so
    matching raw bytes would pin the line breaks rather than the rule."""
    return " ".join(_text(p).split())


# ------------------------------------------------------- OWNER_DECISIONS (P1-1)

def test_owner_decisions_states_the_third_state():
    t = _flat(OWNER_DECISIONS_T)
    assert "off on purpose" in t
    assert "Three states, not two" in t
    assert "Deliberate decisions are not defects" in t


def test_owner_decisions_requires_reason_and_lifts_when():
    """An entry with a reason and no lifting condition is a permanent
    suppression nobody has to justify -- the strongest thing in the repo."""
    t = _flat(OWNER_DECISIONS_T)
    assert "Both `reason` and `lifts-when` are required" in t
    assert "ignored loudly" in t
    assert "lifting condition is real work, not a date" in t


def test_owner_decisions_is_never_re_raised_but_is_still_reported():
    t = _flat(OWNER_DECISIONS_T)
    assert "A standing entry is never re-raised" in t
    assert "a footnote is a re-raise wearing a smaller font" in t
    assert "It is still REPORTED, with evidence" in t
    assert "moves an item off the **proactive** list" in t


def test_owner_decisions_never_applies_to_an_unknown_reading():
    t = _flat(OWNER_DECISIONS_T)
    assert "never applied to an UNKNOWN reading" in t
    assert "a fact about the instrument" in t


def test_owner_decisions_forbids_wildcards_and_stale_promises():
    t = _flat(OWNER_DECISIONS_T)
    assert "One id per entry, never a wildcard" in t
    assert "No other surface may promise the deferred behavior" in t


def test_owner_decisions_is_owner_written_only():
    t = _flat(OWNER_DECISIONS_T)
    assert "A crew that can write its own suppressions has no findings" in t


# ------------------------------------------------------- REVIEWER_LANES (P1-5)

def test_reviewer_lanes_register_carries_states_and_exact_disqualifiers():
    t = _flat(REVIEWER_LANES_T)
    assert "A disqualifier is exact or it is not a disqualifier" in t
    for state in ("in effect", "cancelled", "declined", "removed"):
        assert state in t, f"lane register missing state {state!r}"


def test_reviewer_lanes_records_meter_shape_and_measured_ceilings():
    t = _flat(REVIEWER_LANES_T)
    assert "a throttle reopens after a window, a hard stop does not reopen" in t
    assert "measured, not quoted from documentation" in t
    assert "keep running **on its defaults**" in t


def test_reviewer_lanes_tracks_owner_actions_owed():
    t = _flat(REVIEWER_LANES_T)
    assert "A cancellation an agent cannot finish is **tracked here**" in t


def test_reviewer_lanes_prevents_re_litigation():
    t = _flat(REVIEWER_LANES_T)
    assert "so a later session does not re-litigate this" in t
    assert "not re-adopted by amnesia" in t


def test_reviewer_lanes_salvages_a_dead_lanes_findings():
    t = _flat(REVIEWER_LANES_T)
    assert "A cancelled scanner's real findings are worked, not discarded with it" in t
    assert "It was never a verdict on the defects it found" in t


def test_reviewer_skill_writes_the_lane_register_on_all_three_verbs():
    t = _flat(REVIEWER_SKILL)
    assert "`REVIEWER_LANES.md`** (from `templates/REVIEWER_LANES.md.template`)" in t
    assert "Record the cancellation in `REVIEWER_LANES.md`" in t
    assert "Reconcile `REVIEWER_LANES.md` in the same pass" in t


# --------------------------------------------------------- the canary (P1-2)

def test_reviewer_canary_is_pre_registered_before_the_result():
    t = _flat(REVIEWER_SKILL)
    assert "Pre-register the expected readings BEFORE the result arrives" in t
    assert "A reading interpreted after the fact is a story" in t


def test_reviewer_canary_is_first_and_last_and_asymmetric():
    t = _flat(REVIEWER_SKILL)
    assert "One in the FIRST guideline file, one in the LAST" in t
    assert "break only ONE of the two" in t
    assert "recalling or replaying rather than reading" in t


def test_reviewer_canary_treats_a_miss_as_a_file_never_loaded():
    t = _flat(REVIEWER_SKILL)
    assert "is treated as NOT loading the file**, whatever its own status check says" in t
    assert "invalid on any diff that touches the criteria files" in t


def test_reviewer_canary_rules_are_token_free():
    """If the required text contains the canary's id, deleting the rule leaks
    the id into the diff and the lane can echo it without reading anything."""
    t = _flat(REVIEWER_SKILL)
    assert "must NOT contain the canary's own identifier" in t


# ------------------------------------------------- mutation probe roster (P1-3)

def test_probe_roster_is_a_standing_muster_with_a_why_per_probe():
    t = _flat(TESTING)
    assert "mutation is a standing muster, not a one-shot" in t
    assert "recorded in a roster and re-mustered on a cadence in CI" in t
    assert "The `why` is not decoration" in t


def test_probe_roster_verdicts_survived_is_a_finding_error_never_a_pass():
    t = _flat(TESTING)
    assert "a **finding about the test**, filed like any other" in t
    assert "**Never a pass.**" in t
    assert "a probe testing nothing while reading green" in t


def test_probe_roster_mutates_through_the_artifact_the_tests_read():
    t = _flat(TESTING)
    assert "Mutate through the artifact the tests actually read" in t
    assert ("The derived artifact is rebuilt after the mutation and before the "
            "run, or the probe does not count") in t


# ------------------------------------------------- recurring-class guards (P1-4)

def test_failure_patterns_opens_with_the_recurring_classes_digest():
    body = _text(FAILURE_PATTERNS_T)
    digest = body.find("## Recurring classes - watch these hardest")
    fmt = body.find("## Format")
    first_entry = body.find("## F-")
    assert digest != -1, "no recurring-classes digest"
    assert digest < fmt < first_entry, "the digest must sit above Format and the entries"
    t = _flat(FAILURE_PATTERNS_T)
    assert "Read this digest at session start" in t
    assert "the bugs you are statistically about to write again today" in t


def test_recurring_class_promotion_is_by_recurrence_and_sweeps_the_class():
    t = _flat(FAILURE_PATTERNS_T)
    assert "Promotion is by recurrence, not by severity" in t
    assert 'what else is in that class right now?' in t
    assert "which class the new guard is itself an instance of" in t


def test_class_guard_convention_is_documented_and_machine_checkable():
    t = _flat(FAILURE_PATTERNS_T)
    assert "> class-guard:" in t
    assert "machine-checkable assertion" in t
    assert "to **exist**, to **run**, and to have a **mutation proving it can fail**" in t
    assert "A class-guard nobody can watch go red is a sentence about intentions" in t


def test_class_guard_is_the_one_permitted_amendment_to_an_existing_entry():
    """The registry is append-only; this names the single exception so nobody
    infers a general licence to rewrite entries."""
    t = _flat(FAILURE_PATTERNS_T)
    assert "the **one** amendment the append-only rule permits" in t


def test_testing_standards_names_the_class_guard_convention():
    t = _flat(TESTING)
    assert "carries a **`> class-guard:`** line" in t
    assert "that guard is itself a roster probe" in t


def test_failure_patterns_still_has_seventeen_seeded_entries():
    """The digest is additive. Re-pinned here because this change is the one
    that could have turned a seeded entry into a digest row."""
    blocks = _text(FAILURE_PATTERNS_T).split("\n## ")[1:]
    seeded = [b for b in blocks if b.startswith("F-")]
    assert len(seeded) == 17, f"expected 17 seeded classes, found {len(seeded)}"


# ------------------------------------------------- CI meter economics (P1-6)

def test_meter_economics_names_the_question_before_the_spend():
    t = _flat(FAST_TRACK)
    assert "The meter is part of the design" in t
    assert ("Name the question a run answers, and the cheapest meter that answers "
            "it, BEFORE spending it") in t
    assert "an action that cannot name its question is a guess" in t


def test_meter_economics_carries_the_five_earned_rules():
    t = _flat(FAST_TRACK)
    for rule in (
        "Every job carries a `timeout-minutes`",
        "must state why the work cannot be event-driven",
        "Cancelled runs still bill for the time they ran",
        "Jobs bill rounded up to the minute",
        "report the reading beside the result",
    ):
        assert rule in t, f"meter economics missing: {rule}"


def test_meter_economics_makes_the_free_local_gate_the_baseline():
    t = _flat(FAST_TRACK)
    assert ("a hosted reviewer finding something the local gate would have caught "
            "is a registered process failure") in t


def test_ship_checklist_records_the_meter_beside_the_result():
    t = _flat(SHIP_CHECKLIST_T)
    assert "The CI meter reading for this change is recorded in the report" in t


# ------------------------------------------------- blast-radius matrix (P1-7)

def test_blast_radius_is_derived_from_the_real_graph():
    t = _flat(TESTING)
    assert "## 8.5 The blast-radius matrix" in t
    assert ("DERIVED from the real import or dependency graph, never remembered") in t
    assert "Name the dependency cores" in t


def test_blast_radius_widening_rule():
    t = _flat(TESTING)
    assert ("A failure in a higher tier than the matrix predicted means the blast "
            "radius was wider than the diff -- widen the row in the same change") in t


def test_blast_radius_is_groomed_with_every_ci_change():
    t = _flat(TESTING)
    assert "grooms the matrix in the same pull request" in t
    assert "two definitions of the gate" in t


def test_blast_radius_does_not_renumber_the_cited_reviewer_section():
    t = _text(TESTING)
    assert "## 9. What the Reviewer rejects" in t
    assert "## 8. Gates run LAST" in t


# ------------------------------------------- diagnostics + registry wiring (P1-1)

def test_diagnostics_classifier_consults_the_owner_decisions_registry():
    t = _flat(DIAG)
    assert "The classifier consults the owner-decisions registry before filing" in t
    assert "**converted to a report-with-evidence citing the entry id, never a story**" in t
    assert "never applied to an `unknown` reading" in t


def test_diagnostics_stage_three_kept_its_ceiling_item():
    """The insert must not have displaced the grant's ceiling."""
    t = _flat(DIAG)
    assert "The grant's ceiling is unchanged" in t


def test_diagnostics_asks_ship_with_their_own_verifier():
    t = _flat(DIAG)
    assert "An ask shipped to the machine carries its own machine-verifier" in t
    assert "an ask the system cannot verify is not done" in t


# ------------------------------------------------------- cheap P2 one-liners

def test_best_practices_pins_config_choices_in_both_directions():
    t = _flat(BEST_PRACTICES_T)
    assert "pinned by a CI assertion in BOTH directions" in t
    assert "deliberately ABSENT file" in t
    assert '"Configured but inert" and "silently reverted" are the same class' in t


def test_best_practices_feature_removal_evicts_state_and_stays_gone():
    t = _flat(BEST_PRACTICES_T)
    assert "Removing a feature evicts its state and ships a stays-gone test" in t
    assert "a test asserts the behaviour stays gone with the stale key present" in t
    assert "**removed** (practical) or **retired**" in t


def test_best_practices_new_rules_are_additive_not_a_renumber():
    """3.19/3.20 append (fleet round); 3.21/3.22 append (DEC-0029); the
    project-specific slot moves to 3.23 and the numbered sections other
    docs cite are untouched."""
    t = _text(BEST_PRACTICES_T)
    assert "**3.18 Test a guard through the seam that actually runs.**" in t
    assert "**3.21 A command or claim handed to a human was verified first" in t
    assert "**3.22 A defensive default is honest only if the caller can tell" in t
    assert "**3.23 <PROJECT_SPECIFIC_HONESTY_RULE>.**" in t
    for heading in ("## 3. Honesty discipline", "## 4. Recurring bug classes",
                    "## 4.5 Root cause, not repair", "## 5. Style and structure",
                    "## 6. Before you push"):
        assert heading in t, f"BEST_PRACTICES lost or renumbered {heading}"


def test_reviewer_budget_step_measures_the_vendor_ceiling():
    t = _flat(REVIEWER_SKILL)
    assert "Vendor caps can silently revert a lane to its defaults" in t
    assert "measure the ceiling and print the headroom rather than assuming the config held" in t


def test_wave_report_shape_is_tested_and_open_items_is_the_only_todo_list():
    t = _flat(LIFECYCLE)
    assert "the report itself is under a shape test" in t
    assert "if it is not there, it is not open" in t


# --------------------------------------------------------------- fleet (row 22)

def test_fleet_doc_opens_by_saying_what_it_does_not_do():
    body = _text(FLEET)
    assert "## What this document does NOT do" in body
    first = body.find("## What this document does NOT do")
    second = body.find("## 1. The verdict is an exit code")
    assert -1 < first < second, "the not-this section comes first"


def test_fleet_verdict_is_an_exit_code_and_unknown_never_passes():
    t = _flat(FLEET)
    assert "**UNKNOWN is never a pass.**" in t
    assert "**0** in sync, **1** diverged and acted on, **2** UNKNOWN" in t


def test_fleet_a_run_is_not_an_action():
    t = _flat(FLEET)
    assert "a run is not an action" in t
    assert "reporting drift is not the same as filing the work that closes it" in t
    assert "ends in a tracked item with an owner" in t


def test_fleet_exchange_runs_at_both_ends_in_a_spinoff_that_ends():
    t = _flat(FLEET)
    assert "runs at session **start** and session **end**" in t
    assert "that session ends when the exchange is done" in t.lower()
    assert "competes directly with wanting to be finished" in t
    assert "measured in artifacts" in t


def test_fleet_exactly_one_byte_identical_artifact_with_local_bindings():
    t = _flat(FLEET)
    assert "Exactly one artifact is byte-identical" in t
    assert "local bindings zone" in t
    assert "A local hash proves no local edit, not fleet agreement" in t


def test_fleet_delivery_is_a_draft_pull_request_never_a_push():
    t = _flat(FLEET)
    assert "Delivery is a draft pull request, never a push" in t
    assert "Nobody pushes to a sibling's mainline" in t
    assert "inbound pull requests before hand-syncing" in t


def test_fleet_answers_rules():
    t = _flat(FLEET)
    assert "An answer riding an unmerged branch is not an answer" in t
    assert "A rewording that changes the claim is a decline in costume" in t
    assert "I recognise my rule in the result" in t
    assert '"Answered" is a stated disposition, never a comment count' in t
    assert "**silence is not one of the three**" in t
    assert "An absent row is invisible to a checker that only refuses unanswered rows" in t


def test_fleet_scheduled_check_goes_red_when_it_cannot_compare():
    t = _flat(FLEET)
    assert "goes **RED when it cannot compare**" in t
    assert "an unreachable sibling is a red, not a skip" in t
    assert "Escalation is event-driven, not scheduled" in t


def test_readme_points_at_the_fleet_doc_and_lists_it():
    t = _flat(README)
    assert "The mechanics are [`docs/FLEET.md`](docs/FLEET.md)" in t
    assert "| `FLEET.md` |" in t
    assert "A run is not an action" in t


def test_readme_runbook_table_lists_both_new_templates():
    body = _text(README)
    start = body.find("## The empty-repo runbook")
    section = body[start:body.find("\n## ", start + 1)]
    for name in ("templates/OWNER_DECISIONS.md.template",
                 "templates/REVIEWER_LANES.md.template"):
        assert name in section, f"empty-repo runbook does not name {name}"


def test_template_intake_has_sections_eight_and_nine_before_using_this_document():
    body = _text(INTAKE)
    eight = body.find("## 8. OWNER_DECISIONS.md.template")
    nine = body.find("## 9. REVIEWER_LANES.md.template")
    using = body.find("## Using this document")
    assert -1 < eight < nine < using, "sections 8/9 must precede 'Using this document'"
    t = _flat(INTAKE)
    assert "each gets reason + lifts-when" in t.lower() or "the **reason**" in t
    assert "closed-wontfix issues" in t
    assert "Dashboard-side settings that are not in the repository" in t
