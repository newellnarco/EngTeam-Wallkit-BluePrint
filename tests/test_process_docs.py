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
    for actor in ("Maestro", "Architect", "Adjudicator", "Builders", "Researchers",
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
