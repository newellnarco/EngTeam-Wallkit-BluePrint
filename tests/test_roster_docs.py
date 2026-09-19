"""Roster-document tests: the definitions are loadable, and no lesson drops out.

Two properties are pinned here.

1. **Shape.** Every `.claude/agents/*.md` carries frontmatter with `name`,
   `description` and `model`, and `name` matches the filename -- a definition the
   harness cannot parse is a role that silently does not exist.

2. **Lesson coverage.** Every G-lesson id in `docs/RECONCILIATION.md` Part 2
   appears somewhere in the roster, workflow or handoff documents. Each of those
   ids is a measured failure that cost a wave something; this test is the pin
   that stops one being quietly dropped in an edit.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

KIT = Path(__file__).resolve().parents[1]
CLAUDE = KIT / ".claude"
AGENTS = CLAUDE / "agents"
HANDOFFS = KIT / "docs" / "handoffs"
ROSTER_SPEC = KIT / "docs" / "AGENT_ROSTER_SPEC.md"
WORKFLOW = KIT / "docs" / "WORKFLOW.md"

EXPECTED_ROLES = {
    "foreman", "architect", "adjudicator", "builder",
    "integrator", "reviewer", "researcher",
}
# The harness resolves these; the authority tier is written as `fable` with a
# per-host note in the definition (see AGENT_ROSTER_SPEC, model tiering).
KNOWN_MODELS = {"opus", "sonnet", "haiku", "fable", "inherit"}

G_LESSONS = ["G0a", "G0b", "G0c"] + ["G%d" % n for n in range(1, 15)]

REQUIRED_FILES = [
    CLAUDE / "MAESTRO.md",
    CLAUDE / "skills" / "wave" / "SKILL.md",
    CLAUDE / "hooks" / "subagent_stop.py",
    CLAUDE / "hooks" / "tool_use.py",
    CLAUDE / "hooks" / "hooks.json.example",
    CLAUDE / "hooks" / "README.md",
    HANDOFFS / "dispatch-brief.md",
    HANDOFFS / "finding-route.md",
    HANDOFFS / "transplant-order.md",
    HANDOFFS / "wave-report.md",
    HANDOFFS / "review-thread-takeover.md",
]


def agent_files() -> list[Path]:
    return sorted(AGENTS.glob("*.md"))


def split_frontmatter(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), "%s: no frontmatter block" % path.name
    end = text.find("\n---\n", 3)
    assert end != -1, "%s: unterminated frontmatter" % path.name
    block, body = text[4:end], text[end + 5:]

    fields: dict[str, object] = {}
    key = None
    for line in block.splitlines():
        if not line.strip():
            continue
        if line.lstrip().startswith("- ") and key:
            fields.setdefault(key, [])
            if isinstance(fields[key], list):
                fields[key].append(line.split("- ", 1)[1].strip())
            continue
        match = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
        if match:
            key, value = match.group(1), match.group(2).strip()
            fields[key] = value.strip('"') if value else []
    return fields, body


# ------------------------------------------------------------- shape

def test_every_expected_role_has_a_definition():
    assert {p.stem for p in agent_files()} == EXPECTED_ROLES


def test_maestro_is_the_session_not_an_agent():
    """Subagents cannot spawn subagents (G0a), so there is no maestro agent."""
    assert not (AGENTS / "maestro.md").exists()
    assert (CLAUDE / "MAESTRO.md").exists()


@pytest.mark.parametrize("path", agent_files(), ids=lambda p: p.stem)
def test_frontmatter_is_complete(path: Path):
    fields, body = split_frontmatter(path)
    for key in ("name", "description", "model", "tools"):
        assert key in fields, "%s: missing frontmatter key %r" % (path.name, key)
    assert fields["name"] == path.stem
    assert isinstance(fields["model"], str) and fields["model"] in KNOWN_MODELS
    assert isinstance(fields["description"], str)
    # The description is the harness's invocation guidance, not a label.
    assert len(fields["description"]) >= 80, "%s: description too thin" % path.name
    assert fields["tools"], "%s: empty tools list" % path.name
    assert body.strip(), "%s: frontmatter with no role brief" % path.name


@pytest.mark.parametrize("path", agent_files(), ids=lambda p: p.stem)
def test_no_subagent_claims_the_spawn_tool(path: Path):
    """A subagent cannot spawn siblings; advertising Agent would promise routing
    the roster deliberately mediates through the Maestro session."""
    fields, _ = split_frontmatter(path)
    tools = fields["tools"]
    if isinstance(tools, list):
        assert "Agent" not in tools, path.name


@pytest.mark.parametrize("path", agent_files(), ids=lambda p: p.stem)
def test_every_definition_carries_the_standing_constraints(path: Path):
    """G1/G2/G3/G4/G6/G12 bind every role. A definition missing one hands the
    agent a failure the crew has already paid for."""
    text = path.read_text(encoding="utf-8")
    for lesson in ("G1", "G2", "G3", "G4", "G6", "G12"):
        assert re.search(r"\b%s\b" % lesson, text), "%s: %s not encoded" % (path.name, lesson)


# -------------------------------------------------------- lesson coverage

def corpus() -> dict[Path, str]:
    paths = list(agent_files()) + REQUIRED_FILES + [ROSTER_SPEC, WORKFLOW]
    return {p: p.read_text(encoding="utf-8") for p in paths if p.exists()}


@pytest.mark.parametrize("lesson", G_LESSONS)
def test_every_g_lesson_is_carried_somewhere(lesson: str):
    pattern = re.compile(r"\b%s\b" % re.escape(lesson))
    hits = [p.name for p, text in corpus().items() if pattern.search(text)]
    assert hits, "lesson %s appears in no roster, workflow or handoff document" % lesson


def test_required_files_exist():
    missing = [str(p.relative_to(KIT)) for p in REQUIRED_FILES if not p.exists()]
    assert not missing, "missing: %s" % missing


# --------------------------------------------------------- integrator pin

def test_integrator_is_in_the_roster_and_the_authority_matrix():
    spec = ROSTER_SPEC.read_text(encoding="utf-8")
    flow = WORKFLOW.read_text(encoding="utf-8")
    assert "## Integrator" in spec
    assert "G11" in spec
    matrix = [ln for ln in flow.splitlines() if ln.startswith("| Merge / flip ready")]
    assert matrix, "authority matrix has no merge row"
    assert "| Integrator |" in flow, "Integrator missing from the authority matrix"


def test_workflow_carries_the_new_sections():
    flow = WORKFLOW.read_text(encoding="utf-8")
    assert "## 9. Integration" in flow
    assert "## 10. Hosted reviewer lanes" in flow
    assert "force-with-lease" in flow
    assert "counterfactual" in flow


def test_wave_skill_has_frontmatter():
    fields, body = split_frontmatter(CLAUDE / "skills" / "wave" / "SKILL.md")
    assert fields["name"] == "wave"
    assert len(fields["description"]) >= 80
    assert body.strip()


# ------------------------------------------------------------- hygiene

@pytest.mark.parametrize("path", sorted(
    list(CLAUDE.rglob("*.md")) + list(CLAUDE.rglob("*.py")) +
    list(CLAUDE.rglob("*.example")) + list(HANDOFFS.rglob("*.md")),
), ids=lambda p: str(p.relative_to(KIT)))
def test_kit_owned_files_are_ascii(path: Path):
    """These files are read by agents on hosts with unknown console encodings;
    a smart quote in an operating document has broken a run before."""
    raw = path.read_bytes()
    bad = [(i, b) for i, b in enumerate(raw) if b > 127]
    assert not bad, "%s: non-ASCII byte at offset %d" % (path.name, bad[0][0])
