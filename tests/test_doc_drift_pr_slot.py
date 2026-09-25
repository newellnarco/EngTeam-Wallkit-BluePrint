"""Doc drift: the retired single-PR-slot rule must not survive as a general rule.

DEC-0016 replaced "one branch, one PR slot": concurrent PRs are the default on
disjoint leased surfaces, merges are serialized by the Maestro, and
single-slot mode applies only where the host mandates it. These four documents
described the old rule; each now cites DEC-0016 and names the host exception.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

KIT = Path(__file__).resolve().parents[1]

DOCS = (
    ".claude/skills/wave/SKILL.md",
    "docs/SESSION_LIFECYCLE.md",
    ".claude/agents/integrator.md",
    "docs/handoffs/transplant-order.md",
)

#: Phrasings of the old rule. "single-slot mode" (the host exception) is the
#: one sanctioned survivor and does not match any of these.
RETIRED = (
    r"\bone PR slot\b",
    r"\bsingle PR slot\b",
    r"\bthe PR slot\b",
    r"\bone branch, one PR\b",
    r"\bthe one PR branch\b",
    r"\bverify the single PR\b",
)


def _flat(rel: str) -> str:
    text = (KIT / rel).read_text(encoding="utf-8").replace("**", "")
    return " ".join(text.split())


@pytest.mark.parametrize("rel", DOCS)
def test_no_single_pr_slot_rule_survives(rel):
    flat = _flat(rel)
    hits = [p for p in RETIRED if re.search(p, flat, re.IGNORECASE)]
    assert not hits, f"{rel} still states the retired single-slot rule: {hits}"


@pytest.mark.parametrize("rel", DOCS)
def test_cites_dec_0016(rel):
    assert "DEC-0016" in _flat(rel), f"{rel} does not cite DEC-0016"


@pytest.mark.parametrize("rel", DOCS)
def test_single_slot_is_scoped_to_the_host_mandate(rel):
    flat = _flat(rel)
    assert "single-slot mode" in flat, f"{rel} lost the host-mandated exception"
    assert "mandate" in flat
