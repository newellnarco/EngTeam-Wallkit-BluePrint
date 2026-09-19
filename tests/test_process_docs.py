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
                 "BEST_PRACTICES.md.template", "BUDGETED_DOCS.md.template"):
        assert name in t, f"intake missing template {name}"
    assert t.count("**Required:**") >= 6
    assert t.count("**LLM probes:**") >= 6


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
                 "BEST_PRACTICES.md.template", "BUDGETED_DOCS.md.template"):
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
               "Prompt budgets"):
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
