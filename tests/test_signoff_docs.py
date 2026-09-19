"""The always-involved rule: Architect + Warden + engineer on the diagnostics
loop and on tech evaluations (user direction). Pins keep the involvement from
silently eroding back to conditional."""

from __future__ import annotations

from pathlib import Path

KIT = Path(__file__).resolve().parents[1]


def _flat(p):
    return " ".join((KIT / p).read_text(encoding="utf-8").replace("**", "").split())


def test_diagnostics_loop_names_all_three_standing_parties():
    t = _flat("docs/DIAGNOSTICS_LOOP.md")
    assert "who is always in this loop" in t.lower()
    assert "before it is armed" in t
    assert "unsigned" in t or "does not run unsigned" in t
    assert "redaction audit" in t
    for party in ("Architect", "Warden", "Engineer"):
        assert party in t


def test_playbooks_are_signed_before_arming_and_signed_ones_run_fast():
    t = _flat("docs/DIAGNOSTICS_LOOP.md")
    assert "every playbook Architect- and Warden-signed before arming" in t
    assert "repairs already covered by a signed playbook run immediately" in t


def test_eval_records_need_three_signatures_to_read_decided():
    t = _flat("docs/TECH_EVALUATION.md")
    assert "carrying three signatures before it reads DECIDED" in t
    assert "Warden, always" in t
    assert "Engineer, always: no record moves from OPEN to DECIDED unseen" in t


def test_eval_template_carries_the_signoff_block():
    t = _flat("templates/EVAL_RECORD.md.template")
    assert "Sign-offs (all three before Status may read DECIDED)" in t
    for row in ("Architect (authored)", "Warden", "Engineer (ratified)"):
        assert row in t


def test_role_sheets_carry_the_standing_duties():
    w = _flat(".claude/agents/warden.md")
    a = _flat(".claude/agents/architect.md")
    assert "Standing duties in the diagnostics loop and tech evaluations" in w
    assert "Standing duties in the diagnostics loop and tech evaluations" in a
    assert "redaction audit" in w.lower()
    assert "an opinion with a benchmark" in a
