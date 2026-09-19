"""Pins on the process documents: item authoring and session lifecycle.

Same rationale as test_scaffolding.py: these documents carry rules agents are
briefed from, so the load-bearing phrases are pinned. A doc that silently loses
"the dispatcher decides" or "never manufacture consent" reads fine and briefs
wrong.
"""

from __future__ import annotations

from pathlib import Path

KIT = Path(__file__).resolve().parents[1]
ITEM_AUTHORING = KIT / "docs" / "ITEM_AUTHORING.md"
LIFECYCLE = KIT / "docs" / "SESSION_LIFECYCLE.md"
README = KIT / "README.md"
MAESTRO = KIT / ".claude" / "MAESTRO.md"


def _text(p: Path) -> str:
    assert p.exists(), f"{p} missing"
    return p.read_text(encoding="utf-8")


# ---------------------------------------------------------------- authoring

def test_item_authoring_defines_all_three_shapes():
    t = _text(ITEM_AUTHORING)
    for shape in ("**Arc**", "**Story**", "**Bug**"):
        assert shape in t


def test_one_story_one_dispatch_invariant_pinned():
    t = _text(ITEM_AUTHORING)
    assert "one story = one dispatch = one declared path scope = one lease" in t.replace("\n", " ").replace("  ", " ") or \
        "one story = one dispatch" in t


def test_builder_never_authors_own_requirements():
    t = _text(ITEM_AUTHORING)
    assert "A Builder never authors its own requirements" in t


def test_acceptance_criteria_must_be_citable():
    t = _text(ITEM_AUTHORING)
    assert "citable" in t
    assert "acceptance criteria" in t.lower()


def test_amendment_rules_present():
    t = _text(ITEM_AUTHORING)
    assert "Only the Architect amends requirements" in t
    assert "doc_impact" in t
    assert "re-dispatch" in t


def test_research_loop_lands_answer_in_three_places():
    t = _text(ITEM_AUTHORING)
    for place in ("DEC-NNNN", ".wall/items/", "decisions_in_context"):
        assert place in t


def test_research_discussion_is_mediated():
    t = _text(ITEM_AUTHORING)
    assert "question_raised" in t
    assert "Researcher cannot talk to the Builder" in t or "cannot call a sibling" in t or "mediated" in t


def test_researchers_never_write_stories():
    t = _text(ITEM_AUTHORING)
    assert "Researchers never write stories directly" in t


# ---------------------------------------------------------------- lifecycle

def test_lifecycle_has_all_four_sections():
    t = _text(LIFECYCLE)
    for heading in ("## 1. Session start", "## 2. Startup questions",
                    "## 3. Session close", "## 4. Escalation to the driving engineer"):
        assert heading in t


def test_startup_answers_config_first():
    t = _text(LIFECYCLE)
    flat = " ".join(t.replace("**", "").split())
    assert "if config or the decision log answers it, it is not a question" in flat


def test_start_reconciles_orphans_honestly():
    t = _text(LIFECYCLE)
    assert "open_runs.json" in t
    assert "`stale`" in t
    assert "never back-filled" in t


def test_close_names_unpushed_work():
    t = _text(LIFECYCLE)
    assert "Name unpushed work" in t
    assert "wave report" in t


def test_escalation_classes_enumerated():
    t = _text(LIFECYCLE)
    for cls in ("Irreversible", "Permission and credential", "Spend",
                "Policy conflicts", "Scope changes", "Security findings"):
        assert cls in t, f"escalation class {cls!r} missing"


def test_escalation_mechanics_use_human_queue():
    t = _text(LIFECYCLE)
    for token in ("human_required", "wall answer", "human_answered", "waiting tab"):
        assert token in t


def test_no_answer_is_not_an_answer():
    t = _text(LIFECYCLE)
    assert "Never manufacture consent" in t
    assert "No answer is not an answer" in t


def test_escalation_parks_item_not_wave():
    t = _text(LIFECYCLE)
    assert "parks the item, never the wave" in t


# ---------------------------------------------------------------- wiring

def test_readme_layout_lists_both_docs():
    t = _text(README)
    assert "ITEM_AUTHORING.md" in t
    assert "SESSION_LIFECYCLE.md" in t


def test_maestro_reading_order_includes_both_docs():
    t = _text(MAESTRO)
    assert "docs/SESSION_LIFECYCLE.md" in t
    assert "docs/ITEM_AUTHORING.md" in t


# ---------------------------------------------------------------- topology

TOPOLOGY = KIT / "docs" / "diagrams" / "AGENT_TOPOLOGY.md"
INTAKE = KIT / "docs" / "PRODUCT_INTAKE.md"
REBALANCE = KIT / "docs" / "CAPACITY_REBALANCING.md"
REVIEWER_SKILL = KIT / ".claude" / "skills" / "reviewer-integration" / "SKILL.md"


def test_topology_has_two_mermaid_diagrams():
    t = _text(TOPOLOGY)
    assert t.count("```mermaid") == 2
    assert "flowchart TB" in t and "sequenceDiagram" in t


def test_topology_names_every_actor():
    t = _text(TOPOLOGY)
    for actor in ("Maestro", "Architect", "Adjudicator", "Warden", "Builders", "Researchers",
                  "Reviewer", "Integrator", "Foreman", "Courier",
                  "SessionStart hook", "SubagentStop hook"):
        assert actor in t, f"topology missing actor {actor!r}"


def test_topology_states_parallel_vs_sequential():
    t = _text(TOPOLOGY)
    assert "build in parallel, decide and integrate in\nseries" in t or \
        "build in parallel, decide and integrate in series" in " ".join(t.split())
    assert "ONE PR slot" in t


def test_topology_concern_map_covers_every_stated_goal():
    t = _text(TOPOLOGY)
    for concern in ("**Security**", "**Quality**", "**Backlog generation**",
                    "**Grooming**", "**Architectural design**", "**Logging**",
                    "**Auditing**", "**Reversibility**", "**Checks and balances**",
                    "**Extensible quality**", "**Autonomy with minimal input**"):
        assert concern in t, f"concern map missing {concern}"


# ---------------------------------------------------------------- intake

def test_intake_reduces_engineer_input_to_two_classes():
    t = _text(INTAKE)
    assert "Effort variables" in t
    assert "Product clarification and specificity" in t


def test_intake_covers_all_six_product_domains():
    t = _text(INTAKE)
    for d in ("Product requirements", "Data security requirements",
              "Hosting locations", "Technology choices", "Architecture choices",
              "End-user experience"):
        assert d in t, f"intake missing domain {d!r}"


def test_intake_derives_before_asking():
    t = _text(INTAKE)
    assert "Derive first, ask second" in t
    assert "Every derived answer cites its evidence" in t
    assert "Strong evidence records; weak evidence asks" in t


def test_intake_supports_injection_mid_flight():
    t = _text(INTAKE)
    assert "Injection" in t and "amendment" in t
    assert "parks what it invalidates" in t


def test_intake_never_fabricates_an_answer():
    t = _text(INTAKE)
    assert "No answer is not an answer" in t


# ---------------------------------------------------------------- rebalancing

def test_rebalance_quality_is_a_floor_not_an_axis():
    t = _text(REBALANCE)
    assert "Quality is a constraint, not an axis" in t


def test_rebalance_decision_chain_respects_the_authority_matrix():
    t = _text(REBALANCE)
    flat = " ".join(t.split())
    assert "Foreman" in t and "Maestro" in t and "Adjudicator" in t
    assert "recommendation" in t.lower()
    assert "within the configured caps" in flat
    assert "the engineer's" in t


def test_rebalance_covers_the_three_knob_families():
    t = _text(REBALANCE)
    assert "PR" in t and ("pacing" in t or "creation" in t)
    assert "builder/researcher split" in t or "builders and researchers" in t
    assert "shard" in t.lower()


def test_rebalance_is_measured_and_reversible():
    t = _text(REBALANCE)
    flat = " ".join(t.split())
    assert "from → to" in flat or "from -> to" in flat
    assert "one knob per cycle" in flat.lower()
    assert "measured wall-clock win" in flat


def test_rebalance_wired_into_the_decider_role_sheets():
    foreman = _text(KIT / ".claude" / "agents" / "foreman.md")
    adj = _text(KIT / ".claude" / "agents" / "adjudicator.md")
    maestro = _text(MAESTRO)
    for t in (foreman, adj, maestro):
        assert "CAPACITY_REBALANCING" in t


# ---------------------------------------------------------------- reviewer skill

def test_reviewer_skill_exists_with_all_four_commands():
    t = _text(REVIEWER_SKILL)
    for cmd in ("`add <lane>`", "`remove <lane>`", "`baseline <lane>`", "`learn`"):
        assert cmd in t, f"reviewer skill missing {cmd}"


def test_reviewer_skill_one_body_of_criteria():
    t = _text(REVIEWER_SKILL)
    assert "one-body-of-criteria" in t or "one shared body" in t
    assert "mirrored" in t


def test_reviewer_skill_verifies_with_a_probe_not_a_glance():
    t = _text(REVIEWER_SKILL)
    assert "probe" in t
    assert "A rule no lane flags is not integrated" in t


def test_reviewer_skill_removal_keeps_adopted_rules():
    t = _text(REVIEWER_SKILL)
    assert "STAY in the shared body" in t


def test_reviewer_skill_never_grants_merge_authority():
    t = _text(REVIEWER_SKILL)
    flat = " ".join(t.split())
    assert "never grants a lane merge or approval authority" in flat


def test_new_docs_listed_in_readme_layout():
    t = _text(README)
    for name in ("PRODUCT_INTAKE.md", "CAPACITY_REBALANCING.md",
                 "AGENT_TOPOLOGY", "reviewer-integration"):
        assert name in t, f"README layout missing {name}"


# ---------------------------------------------------------------- org mapping

ORG = KIT / "docs" / "diagrams" / "ORG_MAPPING.md"


def test_org_mapping_has_a_diagram_and_maps_every_function():
    t = _text(ORG)
    assert "```mermaid" in t
    for fn in ("Product ownership", "Engineering management", "Project management",
               "PMO / metrics", "architecture", "Governance", "analysis",
               "Engineering", "Release engineering", "Quality assurance",
               "Security", "Metrics"):
        assert fn in t, f"org mapping missing function {fn!r}"


def test_org_mapping_addresses_ddd_honestly():
    t = _text(ORG)
    for term in ("Ubiquitous language", "Bounded contexts", "Thin by design"):
        assert term in t


# ------------------------------------------------- bootstrap / targets / compliance

BOOTSTRAP = KIT / "docs" / "LLM_BOOTSTRAP.md"
TARGETS = KIT / "docs" / "DEPLOYMENT_TARGETS.md"
COMPLIANCE = KIT / "docs" / "COMPLIANCE_POSTURE.md"


def test_bootstrap_has_all_phases_and_the_ask_ledger():
    t = _text(BOOTSTRAP)
    for h in ("Phase 0", "Phase 1", "Phase 2", "Phase 3", "Phase 4", "Phase 5",
              "The ask/verify ledger"):
        assert h in t, f"bootstrap missing {h}"


def test_bootstrap_never_bypasses_the_consent_gate():
    t = _text(BOOTSTRAP)
    assert "ASK THE ENGINEER (run)" in t
    flat = " ".join(t.replace(">", " ").split())
    assert "Never schedule anything silently" in flat
    assert "never work around a declined install" in flat


def test_bootstrap_derive_do_not_reask():
    t = _text(BOOTSTRAP)
    assert "You ask; you do not assume" in t
    assert "You derive; you do not re-ask" in t


def test_deployment_targets_cover_docker_vm_k8s():
    t = _text(TARGETS)
    for h in ("## 1. Docker", "## 2. VMs", "## 3. Kubernetes"):
        assert h in t


def test_deployment_invariants_hold_on_every_target():
    t = _text(TARGETS)
    assert "One sweeper per checkout" in t
    assert "concurrencyPolicy: Forbid" in t
    assert "ClusterIP" in t
    assert "never" in t and "0.0.0.0" in t  # host-wide publish forbidden
    assert "applying the manifest" in t or "applying it is the engineer" in t.lower() or "manifest: applying" in t.lower() or "Consent** is the manifest" in t


def test_compliance_maps_the_control_families():
    t = _text(COMPLIANCE)
    for fam in ("Segregation of duties", "Change management", "Audit trail",
                "Traceability", "least privilege", "Reversibility",
                "Independent review", "Security testing", "Data classification"):
        assert fam in t, f"compliance posture missing {fam}"


def test_compliance_is_honest_about_what_it_is_not():
    t = _text(COMPLIANCE)
    assert "not a certification" in t
    assert "does not make a\nproduct compliant" in t or "does not make a product compliant" in " ".join(t.split())


def test_readme_carries_the_turnkey_identity_and_visuals():
    t = _text(README)
    assert "turnkey" in t.lower()
    for c in ("Complaint", "auditability" if "auditability" in t else "audit",
              "docs/COMPLIANCE_POSTURE.md"):
        assert c in t
    assert "docs/diagrams/assets/org-mapping.svg" in t
    assert "docs/diagrams/assets/agent-topology.svg" in t
    assert "docs/screenshots/wall-stories.png" in t
    assert "## The path: quick start to full implementation" in t


# ---------------------------------------------------------------- warden

import sys as _sys
_sys.path.insert(0, str(KIT / "tools" / "wall"))
from agents import SINGLETON_ROLES, AgentRegistry  # noqa: E402

WARDEN = KIT / ".claude" / "agents" / "warden.md"


def test_warden_blocks_but_never_grants():
    t = _text(WARDEN)
    flat = " ".join(t.split())
    assert "You can BLOCK on your own judgment" in flat
    assert "You can never GRANT" in flat
    assert "widening any privilege remains the engineer's" in flat.lower() or \
        "remains the engineer's" in flat


def test_warden_has_three_gates_and_risk_tiering():
    t = _text(WARDEN)
    for g in ("Gate 1 -- architecture sign-off", "Gate 2 -- data-use evaluation",
              "Gate 3 -- delivery audit"):
        assert g in t, f"warden missing {g}"
    assert "in-scope" in t and "routine" in t
    for v in ("`allowed`", "`synthetic-only`", "`masked`", "`engineer`", "`refused`"):
        assert v in t, f"warden missing data verdict {v}"


def test_warden_is_overrulable_only_in_writing():
    t = _text(WARDEN)
    flat = " ".join(t.split())
    assert "overrulable" in flat.lower()
    assert "objection preserved" in flat


def test_warden_is_a_structural_singleton(tmp_path):
    assert "warden" in SINGLETON_ROLES
    reg = AgentRegistry(tmp_path)
    reg.claim("warden", "s_test")
    try:
        reg.claim("warden", "s_test2")
    except ValueError as e:
        assert "singleton" in str(e)
    else:
        raise AssertionError("second live warden claim must be refused")


def test_singleton_audit_flags_a_hand_edited_violation(tmp_path):
    reg = AgentRegistry(tmp_path)
    r1 = reg.claim("warden", "s_a")
    rows = reg.read()
    rows.append({**r1, "key": "wrd_deadbee", "name": "Aurelius"})
    reg.write(rows)
    problems = reg.audit()
    assert any("singleton violation" in p for p in problems)


def test_warden_wired_into_workflow_and_authoring():
    wf = _text(KIT / "docs" / "WORKFLOW.md")
    assert "Sign off security / compliance / data use" in wf
    assert "The Warden blocks; only the engineer grants" in wf
    ia = _text(ITEM_AUTHORING)
    assert "Risk tier" in ia and "Declared data uses" in ia
    dod = _text(KIT / "tools" / "wall" / "config" / "wall.example.json")
    assert "warden sign-off recorded for in-scope arcs" in dod


# ------------------------------------------------- template intake + adopt

TEMPLATE_INTAKE = KIT / "docs" / "TEMPLATE_INTAKE.md"
ADOPT_SKILL = KIT / ".claude" / "skills" / "adopt" / "SKILL.md"


def test_template_intake_covers_every_template_with_both_layers():
    t = _text(TEMPLATE_INTAKE)
    for name in ("CLAUDE.md.template", "RULES.md.template",
                 "FAILURE_PATTERNS.md.template", "SHIP_CHECKLIST.md.template",
                 "BEST_PRACTICES.md.template", "BUDGETED_DOCS.md.template",
                 "DOCS_MAP.md.template"):
        assert name in t, f"intake missing template {name}"
    assert t.count("**Required:**") >= 7
    assert t.count("**LLM probes:**") >= 7
    # EVAL_RECORD is per-evaluation, not an adoption-time doc; the intake must
    # say so rather than silently lacking a section for a listed template.
    assert "EVAL_RECORD.md.template" in t and "per evaluation" in t


def test_template_intake_uses_the_four_project_shapes():
    t = _text(TEMPLATE_INTAKE)
    for shape in ("MAX3", "REEF", "MRC", "feedhacker"):
        assert shape in t, f"intake missing shape {shape}"


def test_template_intake_graduates_its_own_probes():
    t = _text(TEMPLATE_INTAKE)
    assert "graduates questions the way the failure registry graduates bugs" in \
        " ".join(t.split())


def test_every_template_points_at_its_question_set():
    for name in ("CLAUDE.md.template", "RULES.md.template",
                 "FAILURE_PATTERNS.md.template", "SHIP_CHECKLIST.md.template",
                 "BEST_PRACTICES.md.template", "BUDGETED_DOCS.md.template",
                 "DOCS_MAP.md.template"):
        t = _text(KIT / "templates" / name)
        assert "TEMPLATE_INTAKE.md" in t, f"{name} lacks its question-set pointer"


def test_adopt_skill_has_the_three_commands_and_the_law():
    t = _text(ADOPT_SKILL)
    for cmd in ("## `inventory`", "## `map`", "## `consolidate`"):
        assert cmd in t
    flat = " ".join(t.split())
    assert "map, do not duplicate" in flat
    assert "Inventory never edits anything" in flat


def test_adopt_classifies_by_function_not_filename():
    t = _text(ADOPT_SKILL)
    assert "Classify by FUNCTION, not filename" in t
    for fn in ("Entry point", "Standing rules", "Failure registry",
               "Ship checklist", "Coding standards", "Decision log",
               "Prompt budgets", "Docs map"):
        assert fn in t, f"adopt missing function {fn}"


def test_adopt_conflicts_go_to_the_engineer():
    t = _text(ADOPT_SKILL)
    flat = " ".join(t.split())
    assert "always** the engineer's call" in flat or "always the engineer's call" in flat.replace("**", "")
    assert "The skill stages the diff; it does not pick" in flat


# ------------------------------------------------- diagnostics loop + evals

DIAG = KIT / "docs" / "DIAGNOSTICS_LOOP.md"
EVAL = KIT / "docs" / "TECH_EVALUATION.md"
EVAL_T = KIT / "templates" / "EVAL_RECORD.md.template"
SCHEMA = KIT / "docs" / "EVENT_SCHEMA.md"


def test_diagnostics_loop_has_the_five_stages():
    t = _text(DIAG)
    for h in ("ship, honestly", "freshness is first-class",
              "automated review, under a standing grant",
              "story creation, with the design attached",
              "owner-verification queue"):
        assert h in t, f"diagnostics loop missing stage: {h}"


def test_diagnostics_shipper_runs_unconditionally():
    t = _text(DIAG)
    flat = " ".join(t.split())
    assert "the shipper runs unconditionally" in flat.replace("**", "")
    assert "F-OBS-COUPLED" in t


def test_diagnostics_missing_signal_is_a_story_not_a_question():
    t = _text(DIAG)
    flat = " ".join(t.replace("**", "").split())
    assert '"Not enough detail" never goes to the engineer' in flat
    assert "itself a P1 story" in flat


def test_diagnostics_grant_keeps_the_engineer_ceiling():
    t = _text(DIAG)
    assert "The grant's ceiling is unchanged" in t


def test_verification_queue_rules():
    t = _text(DIAG)
    flat = " ".join(t.replace("**", "").split())
    assert "Only the owner's explicit sign-off retires an item" in flat
    assert "Unverified items persist across releases" in flat
    assert '"Too small to list" is not the shipper\'s call' in flat


def test_never_ask_the_owner_to_run_anything():
    t = _text(DIAG)
    flat = " ".join(t.replace("**", "").split())
    assert "must name the channel that cannot carry it" in flat
    assert "Automate the result back, not just the work" in flat
    assert "non-zero on every path where the work did not complete" in flat


def test_event_schema_carries_the_diagnostics_events():
    t = _text(SCHEMA)
    for ev in ("diagnostic_snapshot_shipped", "diagnostic_finding",
               "story_filed", "verify_requested", "verified"):
        assert f"`{ev}`" in t, f"schema missing event {ev}"


def test_tech_evaluation_law_and_flip_protocol():
    t = _text(EVAL)
    flat = " ".join(t.replace("**", "").split())
    assert "no baseline for the thing a change guards means the change is not designed yet" in flat
    assert "target metric improves AND the guard" in flat
    assert "instant, documented revert" in flat
    assert "the incumbent wins ties" in flat.lower()


def test_tech_evaluation_disqualifiers_are_first_class():
    t = _text(EVAL)
    flat = " ".join(t.replace("*", "").split())
    assert "deployment cost counts independent of accuracy" in flat.lower().replace(",", "")
    assert "challenger that cannot start" in flat
    assert "recorded, not executed" in flat


def test_eval_record_template_carries_the_load_bearing_fields():
    t = _text(EVAL_T)
    for f in ("Status | DECIDED KEEP / DECIDED SWAP / OPEN", "Decision basis",
              "Disqualifiers checked", "Candidate-fix recipe (recorded, not executed)",
              "Re-evaluation triggers", "Guard metric"):
        assert f in t, f"eval template missing {f}"


# ==================================================================
# Mined-gap pins (G-3 to G-21): the lessons absorbed from the reference
# deployment's failure registry and standing rules.
#
# Each assertion below fails against the tree as it stood before this
# change -- none of these phrases existed anywhere. They are pinned
# because each one is a rule an agent is briefed from: a document that
# silently loses "the code wins" or "Silence is not one of them" still
# reads fine and briefs wrong, which is the whole reason this file
# exists.
# ==================================================================

BEST_PRACTICES_T = KIT / "templates" / "BEST_PRACTICES.md.template"
FAILURE_PATTERNS_T = KIT / "templates" / "FAILURE_PATTERNS.md.template"
RULES_T = KIT / "templates" / "RULES.md.template"
DOCS_MAP_T = KIT / "templates" / "DOCS_MAP.md.template"
WORKFLOW_DOC = KIT / "docs" / "WORKFLOW.md"
WALL_STANDARDS = KIT / "docs" / "WALL_STANDARDS.md"
FAST_TRACK = KIT / "docs" / "FAST_TRACK.md"
TESTING = KIT / "docs" / "TESTING_STANDARDS.md"
INSTALL = KIT / "docs" / "INSTALL.md"
ROSTER = KIT / "docs" / "AGENT_ROSTER_SPEC.md"
FINDING_ROUTE = KIT / "docs" / "handoffs" / "finding-route.md"


def _flat(p: Path) -> str:
    """Whitespace-normalised text.

    Every pin below is a sentence that wraps in its source document, so
    matching the raw bytes would pin the line breaks rather than the rule and
    would break on a reflow that changed nothing.
    """
    return " ".join(_text(p).split())


# ------------------------------------------------- G-16 honesty rules

def test_best_practices_seeds_the_mined_honesty_rules():
    """Each is a measured class; trimming one to make a diff pass is the
    failure the section exists to stop (same contract as the original six)."""
    t = _flat(BEST_PRACTICES_T)
    for phrase, label in [
        ("A swallowed exception is judged by what the CALLER now believes",
         "caller's belief"),
        ("must not be consumed as a conclusion", "observation vs conclusion"),
        ("evidence of absence only if the query could have HIT",
         "empty lookup needs a positive control"),
        ("A probe that cannot reach its subject returns UNKNOWN",
         "probe reports about itself, not its subject"),
        ("its timeout branch must not equal its absence branch",
         "timeout is not absence"),
        ("One root of trust per resource", "two sources of truth"),
        ("Bind every test double to the live signature",
         "doubles bound to the real signature"),
        ("A fixture that builds its own schema is a second implementation",
         "fixture schema drift"),
        ("A mutation anchor is unique", "unique mutation anchor"),
        ("Test a guard through the seam that actually runs",
         "guard tested through the seam"),
    ]:
        assert phrase in t, f"BEST_PRACTICES template lost the {label} rule"


def test_best_practices_keeps_the_original_six_honesty_rules():
    """The mined additions are additive. A rule replaced rather than added is
    the trimming this section forbids."""
    t = _flat(BEST_PRACTICES_T).lower()
    for phrase in ("never returns green", "measured zero", "is not a fallback",
                   "same preconditions", "hardcoded", "durable keys"):
        assert phrase in t, f"an original seeded rule was dropped: {phrase}"


def test_best_practices_carries_the_owner_facing_automation_rule():
    """G-15: a request for the owner to RUN something names the channel that
    cannot carry it, or the plan is defective."""
    t = _flat(BEST_PRACTICES_T)
    assert 'form "run this on the target machine" must name the' in t
    assert "automation channel that cannot carry it" in t
    assert "The owner is asked to LOOK at a result, not to produce one" in t


def test_best_practices_requires_nonzero_exit_on_incomplete_work():
    t = _flat(BEST_PRACTICES_T)
    assert "exits non-zero on every path where the work did not complete" in t
    assert "recorded as applied on every machine and never runs again" in t


# --------------------------------------------- G-13 / G-14 new sections

def test_best_practices_has_the_root_cause_section():
    t = _text(BEST_PRACTICES_T)
    assert "## 4.5 Root cause, not repair" in t
    flat = _flat(BEST_PRACTICES_T)
    assert "The whys are CHAINED" in flat
    assert "not the original symptom" in flat
    assert "amount of attention is not a cause" in flat
    assert "Start the chain at the earliest observable symptom" in flat
    assert "Detection is luck and is listed under prevention" in flat
    assert "names WHO owns closing it and WHAT would close it" in flat
    assert "deferral wearing acceptance's name" in flat


def test_best_practices_binds_verification_to_events_not_doubt():
    t = _text(BEST_PRACTICES_T)
    assert "## 4.6 Verification fires on events, not on doubt" in t
    flat = _flat(BEST_PRACTICES_T)
    for trigger in (
        "whole existing population",          # wrote a rule
        "one must-reject and one must-accept",  # wrote a matcher
        "Land the guarantee in the **same edit**",  # comment claiming a guarantee
        "Re-diagnose the **model**, not the patch",  # a fix failed twice
        "**Verify that claim too.**",        # reviewer says it is already fixed
    ):
        assert trigger in flat, f"verification trigger missing: {trigger}"


def test_best_practices_does_not_renumber_the_cited_sections():
    """Other documents cite these by number; 4.5/4.6 were chosen precisely so
    sections 5 and 6 keep their numbers."""
    t = _text(BEST_PRACTICES_T)
    for heading in ("## 3. Honesty discipline", "## 4. Recurring bug classes",
                    "## 5. Style and structure", "## 6. Before you push"):
        assert heading in t, f"BEST_PRACTICES lost or renumbered {heading}"


# ---------------------------------------------------------- G-3 docs map

def test_docs_map_template_exists_and_states_its_four_rules():
    t = _flat(DOCS_MAP_T)
    assert "Same change, not a follow-up" in t
    assert "the code wins" in t
    assert "Silence is not allowed" in t
    assert "Every new document registers itself in the same change" in t


def test_docs_map_template_is_a_kind_to_surface_map():
    t = _text(DOCS_MAP_T)
    assert "| Change kind | Doc surfaces that must update in the same change |" in t
    # The rows are the host's to fill, so the shipped ones carry placeholders.
    assert "<DESIGN_DOC_PATH>" in t and "<CHANGE_KIND>" in t


def test_docs_map_is_wired_into_the_runbook_and_the_inventory():
    t = _text(README)
    assert "templates/DOCS_MAP.md.template" in t, "runbook does not name the template"
    assert "| Docs map |" in t, "adoption inventory has no docs-map function row"


# ---------------------------------------------- G-6 observability in DoD

def _workflow_section(name: str) -> str:
    flow = _text(WORKFLOW_DOC)
    start = flow.find(name)
    assert start != -1, f"WORKFLOW has no {name} section"
    nxt = flow.find("\n## ", start + 1)
    return flow[start:] if nxt == -1 else flow[start:nxt]


def test_definition_of_done_requires_registration_and_failure_telemetry():
    gate = " ".join(_workflow_section("## 5. Definition of done").split())
    assert "system/topology map" in gate
    assert "honest stub status" in gate
    assert "Wins-only telemetry is not done" in gate


def test_definition_of_done_requires_a_measured_baseline_for_perf_changes():
    gate = " ".join(_workflow_section("## 5. Definition of done").split())
    assert "adopt only on a measured win" in gate
    assert "docs/TECH_EVALUATION.md" in gate, (
        "the perf-class rule must point at the evaluation doc by path"
    )


def test_definition_of_done_keeps_its_existing_obligations():
    gate = _workflow_section("## 5. Definition of done")
    for owed in ("Mutation evidence", "SAST", "Test durations recorded"):
        assert owed in gate, f"definition of done no longer requires: {owed}"


# ------------------------------------------------ G-8 review economics

def test_review_meter_economics_are_written_into_the_lane_posture():
    s = " ".join(_workflow_section("## 10. Hosted reviewer lanes").split())
    assert "proves the check RAN, not that the diff was READ" in s
    assert "posted findings are proof" in s
    assert "anything else is UNKNOWN" in s
    assert "Unknown is never upgraded to pass" in s
    assert "Never move the PR head while a review is in flight" in s
    assert "Batch fixes into one push" in s
    assert "Record each lane's meter SHAPE" in s
    assert "Never spend money to recover a self-inflicted review restart" in s
    assert "Attribute the waste: ours, the partner's, or the infrastructure's" in s


def test_reviewer_skill_records_the_lane_meter_shape_on_add():
    t = " ".join(_text(REVIEWER_SKILL).split())
    assert "Record the lane's meter SHAPE beside its metering" in t


# --------------------------------------------------- G-7 findings roll-up

def test_reviewer_skill_has_the_rollup_cadence():
    t = " ".join(_text(REVIEWER_SKILL).split())
    assert "Every **N merged pull requests**" in t
    assert "Pareto by category" in t
    assert "false-positive" in t, "the roll-up must collect the findings that lost"


def test_rollup_separates_reviewer_noise_from_real_rules():
    t = " ".join(_text(REVIEWER_SKILL).split())
    assert "Reviewer noise is a lane-configuration trigger, not a rule" in t


def test_rollup_escalates_a_twice_recurring_category_to_a_structural_closer():
    t = " ".join(_text(REVIEWER_SKILL).split())
    assert "recurring across TWO consecutive roll-ups escalates to a structural" in t


def test_rollup_tracks_the_cost_axis_beside_quality():
    t = " ".join(_text(REVIEWER_SKILL).split())
    for metric in ("review rounds per merged PR", "review restarts we caused",
                   "rate-limit or quota hits per lane"):
        assert metric in t, f"roll-up cost axis missing: {metric}"


# ------------------------------------------- G-4 post-merge propagation

def test_workflow_has_the_post_merge_propagation_pass():
    s = " ".join(_workflow_section("## 9. Integration").split())
    assert "The post-merge propagation pass" in s
    assert "one docs change per merge" in s
    assert "DOCS_MAP.md" in s


def test_a_stale_tracker_is_the_same_integrity_class_as_a_stale_item():
    s = " ".join(_workflow_section("## 8. Status is verified").split())
    assert ("A tracker or status document naming an open PR the host says is "
            "merged is the same integrity class") in s


# ------------------------------------------------- G-9 session continuity

def test_session_start_vets_the_handoff_against_ground_truth():
    t = _flat(LIFECYCLE)
    assert "Vet the handoff against ground truth before acting on any of it" in t
    assert "Trust the repo over the doc" in t


def test_wave_report_supersedes_and_deletes_its_predecessor():
    t = _flat(LIFECYCLE)
    assert "supersedes and deletes its predecessor" in t
    assert "Two reports that both look current" in t


def test_standing_directives_are_recorded_in_the_same_working_chunk():
    t = _flat(LIFECYCLE)
    assert "in the same working chunk it was issued" in t
    assert "A directive that exists only in the conversation is a bug" in t
    r = _flat(RULES_T)
    assert "## 2.12 A standing directive is recorded in the same working chunk" in r
    assert "A directive that exists only in a conversation is a bug" in r


# ------------------------------------------- G-10 structural prevention

def test_recurring_derived_drift_graduates_to_a_hook():
    t = _flat(TESTING)
    assert ("When the same derived-artifact drift recurs, it graduates out of "
            "the checklist") in t
    assert "degrades to a warning, never blocks" in t


def test_derived_only_ci_failure_is_repaired_on_the_cheap_lane():
    t = _flat(TESTING)
    assert "re-gate on the cheap lane" in t
    assert "never by re-running the full pyramid" in t


# ----------------------------------------- G-11 contradiction escalation

def test_item_authoring_escalates_a_contradicting_requirement():
    t = _flat(ITEM_AUTHORING)
    assert ("A new requirement that contradicts a recorded one is quoted "
            "beside it and escalated") in t
    assert "Superseding marks are written in BOTH directions" in t


def test_finding_route_carries_the_contradiction_case():
    t = _flat(FINDING_ROUTE)
    assert "The contradiction case routes differently" in t
    assert "skips the researcher hop and goes to the Architect" in t


# ------------------------------------- G-5 / G-18 wall cadence + lifecycle

def test_wall_standards_has_a_fixed_short_checkin_cadence():
    t = _flat(WALL_STANDARDS)
    assert "Check-in cadence for in-flight pull requests" in t
    assert "`ci_checkin_minutes`" in t
    assert "advisory default **10**" in t
    assert "poll only on the timer, and wait on events otherwise" in t


def test_wall_standards_pins_the_four_item_lifecycle_rules():
    t = _flat(WALL_STANDARDS)
    for rule in (
        "Bugs only move UP the lanes",
        "An item flips to in-progress the moment work starts, with its "
        "pull-request number attached",
        "The FIRST pull-request number recorded on an item is permanent",
        "Shipped status is DERIVED from the merge log, never asserted",
    ):
        assert rule in t, f"board lifecycle rule missing: {rule}"


# ------------------------------------------------- G-19 CI scope honesty

def test_fast_track_retires_a_leaky_scope_in_code():
    t = _flat(FAST_TRACK)
    assert "a scope that lets broken work through green is retired IN CODE" in t
    assert "one quiet edit away from being back" in t


def test_fast_track_keeps_a_scheduled_full_run_as_backstop():
    t = _flat(FAST_TRACK)
    assert "A scheduled full run stays as the backstop" in t


# --------------------------------------------- G-21 crew spend discipline

def test_maestro_reports_in_transitions_and_refuses_a_hook_commit():
    t = _flat(MAESTRO)
    assert "Report in TRANSITIONS, not narration" in t
    assert "including when a hook demands it" in t
    assert "Decline, and say why in the report" in t


def test_roster_standing_constraints_carry_both_crew_rules():
    t = _flat(ROSTER)
    assert "Report in transitions, not narration" in t
    assert "including when a hook demands it" in t


# ------------------------------------------------ G-17 two-cadence split

def test_install_documents_the_two_cadence_split():
    t = _flat(INSTALL)
    assert "The two-cadence split, for any job with a metered half" in t
    assert "runs **every tick**, offline-safe, zero API calls" in t
    assert "A sentinel range, not a sentinel point" in t
    assert "A minimum interval batches bursts" in t


# ------------------------------------------- seeded failure classes (10)

def test_failure_patterns_template_seeds_the_mined_classes():
    t = _text(FAILURE_PATTERNS_T)
    for cls in ("F-DERIVED-001", "F-ONESHOT-001", "F-PROBE-CACHE-001",
                "F-GATE-ABSENT-001", "F-OBS-COUPLED-001", "F-RETIRE-001",
                "F-RETRY-SAME-001", "F-GUARD-ORDER-001",
                "F-TEXTMATCH-STATE-001", "F-DUPDEF-001"):
        assert f"## {cls}" in t, f"failure registry lost the {cls} class"


def test_failure_patterns_template_keeps_the_original_seven():
    t = _text(FAILURE_PATTERNS_T)
    for cls in ("F-REVIEW-001", "F-IDENT-001", "F-GUARD-001", "F-STATE-001",
                "F-STATUS-001", "F-IDENT-002", "F-SCHED-001"):
        assert f"## {cls}" in t, f"append-only registry lost {cls}"


def test_every_seeded_failure_class_has_symptom_cause_and_check():
    """An entry with no check is a story, not a defence -- the template says
    so, and this is the pin that keeps it true of the seeded set."""
    body = _text(FAILURE_PATTERNS_T)
    blocks = body.split("\n## ")[1:]
    seeded = [b for b in blocks if b.startswith("F-")]
    assert len(seeded) == 17, f"expected 17 seeded classes, found {len(seeded)}"
    for block in seeded:
        name = block.splitlines()[0]
        for field in ("**Symptom:**", "**Root cause:**", "**Check:**"):
            assert field in block, f"{name} is missing {field}"


# --------------------------------------------------------------- readme

def test_readme_org_table_names_the_warden_as_the_security_authority():
    """The table predated the Warden; a missing carrier reads as a missing
    function to anyone arriving with org vocabulary."""
    t = _text(README)
    assert "| Security & compliance authority |" in t
    assert "singleton-enforced" in t
    assert "blocks autonomously, never grants" in t


def test_readme_org_table_covers_every_org_mapping_carrier():
    """Drift check: the README summary must not silently lose a function the
    full mapping carries."""
    t = _text(README)
    for fn in ("Product owner", "Engineering manager", "PMO / metrics",
               "Solution architect", "Governance board",
               "Security & compliance authority", "Analysts", "Engineers",
               "Release engineer", "QA / code review", "Security",
               "Project management", "Metrics"):
        assert fn in t, f"README org table is missing the {fn!r} function"


def test_readme_documents_what_activates_by_itself():
    t = _flat(README)
    assert "## Skills" in _text(README)
    assert "Skills and role sheets activate by themselves" in t
    assert ".claude/skills/*/SKILL.md" in t and ".claude/agents/*.md" in t


def test_readme_skills_table_lists_all_three_skills():
    t = _text(README)
    section = t[t.find("## Skills"):]
    section = section[:section.find("\n## ", 1)]
    for skill in ("`/adopt`", "`/wave`", "`/reviewer-integration`"):
        assert skill in section, f"skills table is missing {skill}"
    assert "`wall run-once` first" in section, (
        "/wave's precondition (the wall must exist) is its whole setup note"
    )


def test_readme_says_hooks_are_not_automatic():
    t = _flat(README)
    assert "Hooks are NOT automatic, by design" in t
    assert "hooks.json.example" in t
    assert "the ledger degrades honestly" in t


def test_readme_carries_the_forward_looking_fleet_note():
    t = _flat(README)
    assert "Shared rules cross repositories additively" in t
    assert "adopted, reworded, or declined-with-reason" in t
    assert "Silence is not one of them" in t
    assert "A sync verdict is never UNKNOWN" in t


# ------------------------------------------------- foundation-first gate

def test_the_foundation_gate_is_stated_everywhere_it_binds():
    flatten = lambda p: " ".join(_text(p).replace("**", "").replace(">", " ").split())
    boot = flatten(KIT / "docs" / "LLM_BOOTSTRAP.md")
    assert "The order is the rule" in boot
    assert "THE FOUNDATION GATE" in boot
    assert "No product story dispatches before this gate" in boot
    maestro = flatten(MAESTRO)
    assert "Foundation gate (product stories only)" in maestro
    assert "precede ANY product line of code" in maestro
    readme = flatten(README)
    assert "a gate, not a suggestion" in readme
