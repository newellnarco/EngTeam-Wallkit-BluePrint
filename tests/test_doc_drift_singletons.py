"""Doc drift: the roster spec's registry-enforced singletons equal the code's.

`SINGLETON_ROLES` is parsed out of tools/wall/agents.py with `ast` rather than
restated here, so a role added to or dropped from the code fails this test
until the spec (and the /wave skill's caps line) follow.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]
ROSTER = KIT / "docs" / "AGENT_ROSTER_SPEC.md"
WAVE = KIT / ".claude" / "skills" / "wave" / "SKILL.md"
ROLES = ("foreman", "maestro", "architect", "adjudicator", "warden",
         "builder", "reviewer", "researcher", "integrator")


def singleton_roles_from_code() -> set[str]:
    tree = ast.parse((KIT / "tools" / "wall" / "agents.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "SINGLETON_ROLES" for t in node.targets):
            return set(ast.literal_eval(node.value))
    raise AssertionError("SINGLETON_ROLES not found in tools/wall/agents.py")


def _roles_in(text: str) -> set[str]:
    return {r for r in ROLES if re.search(rf"\b{r}\b", text, re.IGNORECASE)}


def test_code_list_is_parseable():
    assert singleton_roles_from_code(), "empty SINGLETON_ROLES"


def test_roster_spec_registry_list_matches_code():
    text = " ".join(ROSTER.read_text(encoding="utf-8").split())
    m = re.search(r"\*\*Registry-enforced\*\*(.*?)(?= - \*\*|$)", text)
    assert m, "roster spec has no 'Registry-enforced' singleton bullet"
    # the bullet names the code constant, then the roles after the colon
    listed = _roles_in(m.group(1).split(":", 1)[1])
    assert listed == singleton_roles_from_code(), (
        f"spec lists {sorted(listed)}, code enforces {sorted(singleton_roles_from_code())}")


def test_roster_spec_does_not_claim_registry_enforces_foreman_or_maestro():
    text = " ".join(ROSTER.read_text(encoding="utf-8").split())
    assert "Foreman, Maestro, Architect, Adjudicator — are enforced by the registry" not in text
    assert "lock file with a heartbeat and a TTL" in text
    assert "never claimed" in text


def test_wave_skill_caps_line_matches_code():
    text = " ".join(WAVE.read_text(encoding="utf-8").split())
    m = re.search(r"([A-Z][^.]*?) are singletons enforced by the registry", text)
    assert m, "wave skill lost its singleton sentence"
    assert _roles_in(m.group(1)) == singleton_roles_from_code()
