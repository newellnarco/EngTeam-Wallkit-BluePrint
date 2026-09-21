"""Pins on the retrospective + UX/test-lineage disciplines (DEC-0023/0024).

Same rationale as test_process_docs.py: these documents brief agents, so the
load-bearing phrases are pinned. A retro doc that silently loses "diffs, never
sentiment", or a UX doc that loses the ditch prohibitions, reads fine and
briefs wrong.
"""

from __future__ import annotations

from pathlib import Path

KIT = Path(__file__).resolve().parents[1]
RETRO = KIT / "docs" / "RETROSPECTIVES.md"
UX = KIT / "docs" / "UX_STANDARDS.md"
TESTING = KIT / "docs" / "TESTING_STANDARDS.md"
AUTHORING = KIT / "docs" / "ITEM_AUTHORING.md"
ROSTER = KIT / "docs" / "AGENT_ROSTER_SPEC.md"
MAESTRO = KIT / ".claude" / "MAESTRO.md"
LIFECYCLE = KIT / "docs" / "SESSION_LIFECYCLE.md"
WAVE_REPORT = KIT / "docs" / "handoffs" / "wave-report.md"
ADOPT = KIT / ".claude" / "skills" / "adopt" / "SKILL.md"
TEMPLATE_INTAKE = KIT / "docs" / "TEMPLATE_INTAKE.md"
DEC_INDEX = KIT / "docs" / "decisions" / "index.md"
README = KIT / "README.md"


def _text(p: Path) -> str:
    assert p.exists(), f"{p} missing"
    return p.read_text(encoding="utf-8")


# ------------------------------------------------------------- retrospectives

def test_retro_outputs_are_diffs_never_sentiment():
    t = _text(RETRO)
    assert "diffs to artifacts, never sentiment" in t
    assert "At most three landed changes per retro" in t


def test_retro_signals_are_measured_not_self_reported():
    t = _text(RETRO)
    assert "never\nfrom an agent describing itself" in t or (
        "never" in t and "from an agent describing itself" in t
    )
    # Every role in the roster's cast has a signal row.
    for role in ("**Builder**", "**Reviewer**", "**Researcher**",
                 "**Architect**", "**Maestro**", "**Warden**"):
        assert role in t, f"retro signal table missing {role}"


def test_retro_applies_five_whys_and_bandaid_test():
    t = _text(RETRO)
    assert "five-whys" in t or "five whys" in t.lower()
    assert "a level\nnaming a person or a moment of inattention is not a cause" in t or \
        "naming a person or a moment of inattention is not a cause" in t
    assert 'If the fix is "remember to", it is not a fix' in t
    assert "TECH_EVALUATION" in t  # bandaid-over-bad-design routes to replacement


def test_retro_diffs_are_remeasured():
    t = _text(RETRO)
    assert "re-measured" in t
    assert "recurring after its prevention landed means the prevention failed" in t


def test_retro_authority_split_holds():
    t = _text(RETRO)
    assert "The Foreman prepares, the Maestro runs, the Adjudicator breaks ties." in t


def test_lifecycle_close_holds_the_retro_slot():
    t = _text(LIFECYCLE)
    assert "RETROSPECTIVE section is written in the same pass" in t
    assert "landed as an artifact change before the session ends" in t


def test_wave_report_template_carries_retro_section():
    t = _text(WAVE_REPORT)
    assert "## RETROSPECTIVE" in t
    assert "Last wave's diffs, re-measured" in t


def test_foreman_and_maestro_carry_the_duty():
    assert "Prepares the wave retrospective" in _text(ROSTER)
    t = _text(MAESTRO)
    assert "RETROSPECTIVES.md" in t
    assert "measured by the next wave's signals" in t


# ---------------------------------------------------------------- UX standard

def test_ux_four_qualities_present():
    t = _text(UX)
    for q in ("**Fewer interactions**", "**Actionable**",
              "**Legible and comfortable**", "**Aesthetically coherent**"):
        assert q in t, f"UX quality missing: {q}"
    assert "counted, not felt" in t


def test_ux_trajectories_named_three_kinds():
    t = _text(UX)
    for k in ("basic trajectory", "Advanced trajectories", "Recovery trajectories"):
        assert k in t
    assert "A trajectory the design does not name is a trajectory nobody tested." in t


def test_ux_four_ditch_prohibitions():
    t = _text(UX)
    for p in ("**No dead ends.**", "**No silent data loss.**",
              "**No misrepresentation.**", "**No unnecessary complexity.**"):
        assert p in t, f"ditch prohibition missing: {p}"
    assert "success or a recoverable, explained\nstate" in t or \
        "success or a recoverable, explained state" in t


def test_ux_user_docs_move_with_code():
    t = _text(UX)
    for s in ("**Quickstart**", "**User guide**", "**In-app help**"):
        assert s in t
    assert "same PR" in t
    assert "DOCS_MAP" in t


def test_ux_owner_look_is_final_judge():
    t = _text(UX)
    assert "the owner's eye decides" in t
    assert "never automates" in t


def test_architect_owns_ux_and_betterment():
    t = _text(ROSTER)
    assert "Standing betterment duty" in t
    assert "UX_STANDARDS.md" in t
    assert "never as silent scope creep" in t


# ------------------------------------------------- lineages + families

def test_testing_standards_names_both_lineages():
    t = _text(TESTING)
    assert "## 1b. Two lineages, five families" in t
    assert "**Validation**" in t and "**Verification**" in t
    assert '"built as specified, not\nwhat was wanted"' in t or \
        "built as specified, not" in t


def test_five_families_enumerated_with_declaration_rule():
    t = _text(TESTING)
    for fam in ("**Guardrails**", "**Data integrity**", "**Security**",
                "**Scalability**", "**Performance**"):
        assert fam in t, f"family missing: {fam}"
    assert "recorded declaration with a reason, never an omission" in t


def test_story_contract_carries_lineage_and_trajectory():
    t = _text(AUTHORING)
    assert "which lineage each expected test serves" in t
    assert "UX_STANDARDS.md" in t
    assert "Trajectories and families" in t  # arc anatomy item 8


# ------------------------------------------------------- adopt growth loop

def test_adopt_inventory_reports_unmapped_kinds():
    t = _text(ADOPT)
    assert "unmapped-kind" in t
    assert "The kit learns from every adoption" in t
    assert "never invented speculatively" in t


def test_template_intake_has_growth_section():
    t = _text(TEMPLATE_INTAKE)
    assert "## How this set grows" in t
    assert "graduates to a template" in t
    assert "candidate for removal" in t  # the reverse rule


# ------------------------------------------------------------ registration

def test_decisions_indexed():
    t = _text(DEC_INDEX)
    assert "DEC-0023" in t and "DEC-0024" in t
    assert (KIT / "docs" / "decisions" / "DEC-0023.md").exists()
    assert (KIT / "docs" / "decisions" / "DEC-0024.md").exists()


def test_readme_lists_both_docs():
    t = _text(README)
    assert "`RETROSPECTIVES.md`" in t
    assert "`UX_STANDARDS.md`" in t
