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
