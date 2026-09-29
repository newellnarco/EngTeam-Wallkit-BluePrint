"""The roles above the repository, and the rules a day across repos paid for.

DEC-0038 added a program lead (one per engineer, across all their repos) and a
fleet operator (one per machine), and seven failure classes
(FAILURE_PATTERNS F-OPS-011 to F-OPS-013, F-GIT-005, F-REVIEW-013, F-PROC-004,
F-PROC-005). Each rule is procedural: it lives as written instruction in the
role sheet that owns the duty. These tests are the class-guards named in the
registry -- each asserts the rule's UNIQUE wording in the one document that
owns it, so deleting the rule from its owner fails here even if the same
words survive elsewhere.

Stdlib + pytest only.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

KIT = Path(__file__).resolve().parents[1]
AGENTS = KIT / ".claude" / "agents"
PROGRAM_LEAD = AGENTS / "program-lead.md"
FLEET_OPERATOR = AGENTS / "fleet-operator.md"
INTEGRATOR = AGENTS / "integrator.md"
REVIEWER = AGENTS / "reviewer.md"
WARDEN = AGENTS / "warden.md"
MAESTRO = KIT / ".claude" / "MAESTRO.md"
DEC = KIT / "docs" / "decisions" / "DEC-0038.md"

sys.path.insert(0, str(KIT / "tools" / "wall"))


def _flat(path: Path) -> str:
    """The document with its line breaks folded, so a wrapped rule still reads
    as one sentence."""
    return " ".join(path.read_text(encoding="utf-8").split())


def _section(path: Path, heading: str) -> str:
    """The body under one `## ` heading, folded. A rule must sit in the section
    the registry cites, not merely somewhere in the file."""
    text = path.read_text(encoding="utf-8")
    m = re.search(r"(?ms)^## %s\n(.*?)(?=^## |\Z)" % re.escape(heading), text)
    assert m, "%s has no section %r" % (path.name, heading)
    return " ".join(m.group(1).split())


# ------------------------------------------------------------- the roles

CONSENT_GATES = ("Start or enable on a machine", "Delete", "Widen access",
                 "Spend", "Production")


def test_the_program_lead_never_takes_a_patron_consent_decision():
    body = _section(PROGRAM_LEAD, "2. What stays the engineer's -- the Patron consent gates")
    assert "You **never** take any of these decisions" in body
    rows = re.findall(r"\| \*\*([^*]+)\*\* \|", body)
    assert tuple(rows) == CONSENT_GATES, rows


def test_the_program_lead_merges_only_from_the_seat():
    body = _section(PROGRAM_LEAD, "3. Merging, within the rules")
    assert "**One merge seat per repository at any moment.**" in body
    assert "You never merge in a repository whose seat another live session holds" in body


def test_the_fleet_operator_never_starts_enables_or_raises():
    fields = _flat(FLEET_OPERATOR)
    assert "Never starts, enables or raises anything; the engineer does." in fields
    body = _section(FLEET_OPERATOR, "2. What you may apply, and how")
    for clause in ("It **lowers** something", "It stays **inside the floors**",
                   "It is **reversible**", "It carries an **override window**"):
        assert clause in body, clause


def test_the_decision_records_the_owner_acceptance_verbatim():
    text = _flat(DEC)
    assert "status: active" in DEC.read_text(encoding="utf-8")
    assert "expert: the-patron" in DEC.read_text(encoding="utf-8")
    assert '**"Yes, that split"**' in text
    assert ("you stay the Patron for > anything that turns things on on your box, "
            "deletes, widens access, spends > money, or goes to production") in text


def test_the_new_roles_have_key_prefixes_and_are_not_repo_singletons():
    import agents  # noqa: E402  (tools/wall on sys.path above)
    assert agents.ROLE_PREFIX["program-lead"] == "prl"
    assert agents.ROLE_PREFIX["fleet-operator"] == "fop"
    assert agents.mint_key("program-lead").startswith("prl_")
    assert agents.mint_key("fleet-operator").startswith("fop_")
    assert {"program-lead", "fleet-operator"}.isdisjoint(agents.SINGLETON_ROLES)
    for role in ("program-lead", "fleet-operator"):
        assert len(agents.POOL[role]) >= 5, role


def test_the_new_roles_claim_their_own_pools(tmp_path):
    import agents  # noqa: E402
    reg = agents.AgentRegistry(tmp_path)
    lead = reg.claim("program-lead", "ses_test01")
    op = reg.claim("fleet-operator", "ses_test01")
    assert lead["key"].startswith("prl_") and lead["name"] in agents.POOL["program-lead"]
    assert op["key"].startswith("fop_") and op["name"] in agents.POOL["fleet-operator"]


# ------------------------------------------------ the seven class-guards

def test_the_fleet_operator_carries_the_machine_throttle_plan():
    """F-OPS-011."""
    body = _section(FLEET_OPERATOR, "1. The machine throttle plan")
    assert "the **floors**" in body
    assert "caps the process it starts (a job object, a cgroup, a container limit)" in body
    assert '**"Could not look" closes the gate**' in body


def test_only_a_crashed_thing_is_restarted():
    """F-OPS-012."""
    body = _section(FLEET_OPERATOR, "3. Owner intent is state you read, never state you overwrite")
    assert "**Only a crashed thing is restarted.**" in body
    assert "A clean stop, a disable or a paused state **stays off**." in body
    assert "**Every re-register reads current state first.**" in body


def test_the_version_bump_happens_at_integration():
    """F-GIT-005."""
    body = _section(INTEGRATOR, "Step 1b -- the version bump happens here, not in the unit")
    assert "**the version bump happens at integration time**" in body
    assert "A unit never bumps the version while it is being built" in body


def test_lanes_down_means_a_cold_security_review():
    """F-REVIEW-013: the reviewer and the warden both carry it."""
    rev = _section(REVIEWER, "5. Hosted reviewer lanes (G7)")
    assert "**Lanes down means a cold in-house security review.**" in rev
    assert "**mandatory before merge**" in rev
    war = _section(WARDEN, "6. Binding rules")
    assert "**Lanes down, you read.**" in war


def test_the_check_in_merges_green():
    """F-PROC-004: the Maestro's manual and the program lead's sheet."""
    mae = _section(MAESTRO, "5. Integration, one PR at a time")
    assert "**merges at its own check-in.**" in mae
    assert "**a driver's report is not the merge**" in mae
    lead = _section(PROGRAM_LEAD, "3. Merging, within the rules")
    assert "**The check-in merges.**" in lead
    assert "**A driver's report is not the merge.**" in lead


def test_push_serialization_is_owned_not_global():
    """F-PROC-005."""
    mae = _section(MAESTRO, "5. Integration, one PR at a time")
    assert "**holds the repository's merge seat, one holder at a time.**" in mae
    assert "rule is scoped to this session's own PRs" in mae


def test_deletion_is_owner_run_and_leaves_a_way_back():
    """F-OPS-013."""
    body = _section(FLEET_OPERATOR, "4. Deletion is the engineer's, and it leaves a way back")
    assert "You never delete." in body
    assert "**saves the item's settings first**" in body
    assert "**refuses any item it could not recreate**" in body


@pytest.mark.parametrize("cls", ["F-OPS-011", "F-OPS-012", "F-OPS-013", "F-GIT-005",
                                 "F-REVIEW-013", "F-PROC-004", "F-PROC-005"])
def test_each_class_names_a_guard_defined_here(cls):
    """A class-guard that names a test nobody wrote is a guard in name only."""
    reg = (KIT / "FAILURE_PATTERNS.md").read_text(encoding="utf-8")
    m = re.search(r"(?ms)^## %s - .*?> class-guard: `(\w+)`" % re.escape(cls), reg)
    assert m, "%s has no class-guard line" % cls
    assert m.group(1) in globals() and callable(globals()[m.group(1)]), m.group(1)
