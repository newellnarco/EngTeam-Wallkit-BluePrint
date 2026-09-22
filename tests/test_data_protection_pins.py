"""Pins on the Warden's data charter (DEC-0025).

Load-bearing phrases only: a charter that silently loses "a prompt to a
hosted model is an egress to a third party" or the forward posture reads
fine and briefs wrong.
"""

from __future__ import annotations

from pathlib import Path

KIT = Path(__file__).resolve().parents[1]
CHARTER = KIT / "docs" / "DATA_PROTECTION.md"
WARDEN = KIT / ".claude" / "agents" / "warden.md"
INTAKE = KIT / "docs" / "PRODUCT_INTAKE.md"
TECH_EVAL = KIT / "docs" / "TECH_EVALUATION.md"
TESTING = KIT / "docs" / "TESTING_STANDARDS.md"
COMPLIANCE = KIT / "docs" / "COMPLIANCE_POSTURE.md"
ROSTER = KIT / "docs" / "AGENT_ROSTER_SPEC.md"
DEC_INDEX = KIT / "docs" / "decisions" / "index.md"
README = KIT / "README.md"


def _text(p: Path) -> str:
    assert p.exists(), f"{p} missing"
    return p.read_text(encoding="utf-8")


# ----------------------------------------------------------------- exposure

def test_exposure_ladder_names_all_five_rungs():
    t = _text(CHARTER)
    for rung in ("**Walled**", "**In containers**", "**In the LLM**",
                 "**Loose on a network**", "**In public**"):
        assert rung in t, f"exposure rung missing: {rung}"


def test_llm_prompt_is_an_egress():
    t = _text(CHARTER)
    assert "a prompt to a hosted model is an egress to a third party" in t
    # And the Warden sheet carries the same law (ASCII form).
    assert "a prompt to a hosted model is an egress to a third\nparty" in _text(WARDEN) or \
        "a prompt to a hosted model is an egress to a third party" in _text(WARDEN).replace("\n", " ").replace("  ", " ") or \
        "egress to a third" in _text(WARDEN)


# ------------------------------------------------------------------ regimes

def test_regime_table_names_the_regimes():
    t = _text(CHARTER)
    for cls in ("**PII**", "**PHI / health data**", "**PCI**",
                "**Government / law-enforcement reach**",
                "**Regulated-industry**", "**Contract-bound**"):
        assert cls in t, f"regime class missing: {cls}"
    for regime in ("GDPR", "HIPAA", "PCI-DSS", "CLOUD Act", "Patriot Act"):
        assert regime in t, f"regime example missing: {regime}"


def test_host_names_regimes_never_guessed():
    t = _text(CHARTER)
    assert "the Warden never\nguesses jurisdiction" in t or "never guesses jurisdiction" in t.replace("\n", " ")
    assert "the strictest obligation wins" in t.lower() or "strictest obligation wins" in t


def test_residency_is_part_of_classification():
    t = _text(CHARTER)
    assert "Residency" in t
    assert '"encrypted" does not answer "may it leave Germany"' in t


# ------------------------------------------------------------------- states

def test_three_states_with_in_use_as_leakiest():
    t = _text(CHARTER)
    for s in ("**At rest**", "**In motion**", "**In use**"):
        assert s in t
    assert "leakiest state and the least audited" in t


def test_ways_forward_catalog_present():
    t = _text(CHARTER)
    for w in ("**minimize**", "**synthesize**", "**mask/tokenize**",
              "**encrypt**", "**segment**", "**localize**", "**paper**"):
        assert w in t, f"catalog entry missing: {w}"


# -------------------------------------------------------------- checkpoints

def test_six_checkpoints_enumerated():
    t = _text(CHARTER)
    for c in ("**1. Requirements**", "**2. Technology selection**",
              "**3. Architecture**", "**4. Test development**",
              "**5. Building**", "**6. Before release**"):
        assert c in t, f"checkpoint missing: {c}"


def test_forward_posture_not_full_stop():
    t = _text(CHARTER)
    assert "recommend ways forward within the rules" in t
    assert "a block is the\nexception" in t or "a block is the exception" in t.replace("\n", " ")
    w = _text(WARDEN)
    assert "The posture is forward, not full-stop" in w
    assert "compliant way forward" in w


def test_production_data_never_test_data():
    assert "Production data never becomes test data by convenience" in _text(CHARTER)
    assert "production data never becomes test data by convenience" in _text(TESTING)


# ------------------------------------------------------------------- wiring

def test_warden_sheet_carries_charter_and_checkpoints():
    w = _text(WARDEN)
    assert "docs/DATA_PROTECTION.md" in w
    assert "The six checkpoints" in w
    assert "cheapest to prevent" in w


def test_lifecycle_hooks_wired():
    assert "DATA_PROTECTION.md" in _text(INTAKE)      # checkpoint 1
    assert "DATA_PROTECTION.md" in _text(TECH_EVAL)    # checkpoint 2
    assert "DATA_PROTECTION.md" in _text(TESTING)      # checkpoint 4
    assert "DATA_PROTECTION.md" in _text(COMPLIANCE)   # auditor mapping
    assert "DATA_PROTECTION.md" in _text(ROSTER)       # the roster summary


def test_registered():
    assert "DEC-0025" in _text(DEC_INDEX)
    assert (KIT / "docs" / "decisions" / "DEC-0025.md").exists()
    assert "`DATA_PROTECTION.md`" in _text(README)
