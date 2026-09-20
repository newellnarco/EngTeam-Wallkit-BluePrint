"""Scaffolding integrity: templates, decision log, diagrams, README runbook.

These are cheap structural checks on the documents a new project copies and on
the records the kit ships. They exist because every one of them is a thing that
silently rots: a template that lost its placeholders reads like finished text, a
decision file with malformed front matter is invisible to the contradiction
check, a runbook that stops naming a template quietly drops it from the install,
and an empty mermaid fence renders as nothing at all rather than as an error.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

KIT = Path(__file__).resolve().parents[1]
TEMPLATES = KIT / "templates"
DECISIONS = KIT / "docs" / "decisions"
DIAGRAMS = KIT / "docs" / "diagrams" / "ARCHITECTURE.md"
README = KIT / "README.md"
OPEN_QUESTIONS = KIT / "docs" / "OPEN_QUESTIONS.md"

EXPECTED_TEMPLATES = [
    "CLAUDE.md.template",
    "RULES.md.template",
    "FAILURE_PATTERNS.md.template",
    "SHIP_CHECKLIST.md.template",
    "BEST_PRACTICES.md.template",
    "DOCS_MAP.md.template",
    "EVAL_RECORD.md.template",
    "BUDGETED_DOCS.md.template",
    "OWNER_DECISIONS.md.template",
    "REVIEWER_LANES.md.template",
    "ENGINEERING_STANDARD.md.template",
    "DESIGN_DOC.md.template",
]

# <PLACEHOLDER>: uppercase, digits, underscores. Deliberately does not match
# things like <br/> or an HTML comment, so a template full of markup but no
# actual blanks still fails.
PLACEHOLDER = re.compile(r"<[A-Z][A-Z0-9_]{2,}>")

MERMAID_BLOCK = re.compile(r"```mermaid\n(.*?)```", re.DOTALL)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------- templates

def test_every_expected_template_exists():
    missing = [n for n in EXPECTED_TEMPLATES if not (TEMPLATES / n).is_file()]
    assert not missing, f"missing templates: {missing}"


def test_no_unexpected_templates():
    """A new template must be added to the list AND to the README runbook."""
    found = sorted(p.name for p in TEMPLATES.glob("*.template"))
    assert found == sorted(EXPECTED_TEMPLATES), (
        "templates/ and EXPECTED_TEMPLATES disagree; if you added one, add it "
        "to the README runbook table too"
    )


@pytest.mark.parametrize("name", EXPECTED_TEMPLATES)
def test_template_has_placeholders(name):
    body = read(TEMPLATES / name)
    found = PLACEHOLDER.findall(body)
    assert found, f"{name} has no <PLACEHOLDER>; it is a document, not a template"


@pytest.mark.parametrize("name", EXPECTED_TEMPLATES)
def test_template_header_explains_itself(name):
    """Each template opens with a comment saying what it is and why it exists."""
    body = read(TEMPLATES / name)
    head = body[:1200]
    assert head.lstrip().startswith("<!--"), f"{name} does not open with a header comment"
    for marker in ("TEMPLATE:", "WHAT THIS IS", "WHY IT EXISTS", "HOW TO USE"):
        assert marker in head, f"{name} header is missing {marker}"


@pytest.mark.parametrize("name", EXPECTED_TEMPLATES)
def test_template_body_is_generic(name):
    """No host-specific paths inside a template.

    The reference deployment may be cited as the source of an incident; it may
    not appear as a path somebody is expected to have.
    """
    body = read(TEMPLATES / name)
    for bad in ("C:\\Dev", "newellnarco", "backend/max3", "MAX3"):
        assert bad not in body, f"{name} leaks host-specific detail: {bad}"


@pytest.mark.parametrize("name", EXPECTED_TEMPLATES)
def test_template_is_ascii(name):
    body = read(TEMPLATES / name)
    assert body.isascii(), f"{name} contains non-ASCII characters"


def test_best_practices_seeds_every_honesty_rule():
    """The six seeded rules are measured failure classes; trimming one to make
    a diff pass is the failure they exist to stop."""
    body = read(TEMPLATES / "BEST_PRACTICES.md.template").lower()
    for phrase, label in [
        ("never returns green", "green-on-failed-read"),
        ("measured zero", "absence vs measured zero vs failure"),
        ("is not a fallback", "fallback that can equal its input"),
        ("same preconditions", "two verbs, one end state"),
        ("hardcoded", "platform-varying spellings derived"),
        ("durable keys", "persisted position vs ordinal"),
    ]:
        assert phrase in body, f"BEST_PRACTICES template lost the {label} rule"


def test_best_practices_declares_a_budget_and_cross_references():
    body = read(TEMPLATES / "BEST_PRACTICES.md.template")
    assert "BUDGETED_DOCS.md" in body, "no cross-reference to the budget register"
    assert "budget" in body.lower() and "measure" in body.lower()
    assert "docs/TESTING_STANDARDS.md" in body, (
        "the pre-push section must point at the testing standards by path"
    )


def test_best_practices_has_the_required_sections():
    body = read(TEMPLATES / "BEST_PRACTICES.md.template")
    for heading in ("## 2. Architecture invariants", "## 3. Honesty discipline",
                    "## 4. Recurring bug classes", "## 6. Before you push"):
        assert heading in body, f"BEST_PRACTICES template is missing {heading}"


# ---------------------------------------------------------------- decisions

def decision_files() -> list[Path]:
    return sorted(DECISIONS.glob("DEC-*.md"))


def parse_front_matter(body: str) -> dict[str, str]:
    """Minimal front-matter reader: key: value pairs between the first fences."""
    lines = body.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    out: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return out
        if ":" in line:
            key, _, value = line.partition(":")
            out[key.strip()] = value.strip()
    return {}  # unterminated front matter is not front matter


def test_decision_seed_set_present():
    names = [p.name for p in decision_files()]
    # 13-16 are the Patron's recorded rulings (2026-09-19); 17-18 the
    # portability + reporting-economy charters (Patron, 2026-09-20). The equality
    # still guards against holes and strays.
    expected = [f"DEC-{n:04d}.md" for n in range(1, 19)]
    assert names == expected, f"decision seed set drifted: {names}"


def test_decision_index_exists_and_links_every_file():
    index = DECISIONS / "index.md"
    assert index.is_file(), "docs/decisions/index.md is missing"
    body = read(index)
    for path in decision_files():
        assert path.name in body, f"{path.name} has no row in the decision index"


@pytest.mark.parametrize("path", decision_files(), ids=lambda p: p.name)
def test_decision_front_matter_parses(path):
    fm = parse_front_matter(read(path))
    assert fm, f"{path.name}: front matter missing or unterminated"
    for key in ("id", "status", "decided"):
        assert key in fm, f"{path.name}: front matter missing '{key}'"
        assert fm[key], f"{path.name}: front matter '{key}' is empty"
    assert fm["id"] == path.stem, f"{path.name}: id '{fm['id']}' does not match filename"
    assert fm["status"] in {"active", "superseded"}, (
        f"{path.name}: status '{fm['status']}' is not active or superseded"
    )


@pytest.mark.parametrize("path", decision_files(), ids=lambda p: p.name)
def test_decision_cites_reconciliation(path):
    body = read(path)
    assert "RECONCILIATION" in body or "reconcil" in body.lower(), (
        f"{path.name}: a kit decision cites the reconciliation record"
    )


@pytest.mark.parametrize("path", decision_files(), ids=lambda p: p.name)
def test_decision_has_the_required_sections(path):
    body = read(path)
    for heading in ("## Question", "## Decision", "## Why", "## Revisit if"):
        assert heading in body, f"{path.name}: missing section {heading}"


# ---------------------------------------------------------------- diagrams

def test_architecture_diagrams_are_fenced_and_non_empty():
    assert DIAGRAMS.is_file(), "docs/diagrams/ARCHITECTURE.md is missing"
    body = read(DIAGRAMS)
    blocks = MERMAID_BLOCK.findall(body)
    assert len(blocks) >= 3, f"expected at least 3 mermaid blocks, found {len(blocks)}"
    for i, block in enumerate(blocks, start=1):
        content = [ln for ln in block.splitlines() if ln.strip()]
        assert len(content) > 3, f"mermaid block {i} is empty or trivial"
        assert content[0].strip().split()[0] in {
            "flowchart", "graph", "sequenceDiagram", "stateDiagram-v2", "erDiagram"
        }, f"mermaid block {i} does not declare a diagram type: {content[0]!r}"


def test_architecture_diagrams_stay_small():
    """Under about 25 nodes each; past that a diagram stops being readable."""
    body = read(DIAGRAMS)
    for i, block in enumerate(MERMAID_BLOCK.findall(body), start=1):
        lines = [ln for ln in block.splitlines() if ln.strip()]
        assert len(lines) <= 60, f"mermaid block {i} has {len(lines)} lines; split it"


def test_architecture_covers_the_three_views():
    body = read(DIAGRAMS).lower()
    for phrase in ("component", "journey", "closed loop"):
        assert phrase in body, f"ARCHITECTURE.md does not cover the {phrase} view"


# ---------------------------------------------------------------- readme

def runbook_section(body: str) -> str:
    start = body.find("## The empty-repo runbook")
    assert start != -1, "README has no empty-repo runbook section"
    nxt = body.find("\n## ", start + 1)
    return body[start:] if nxt == -1 else body[start:nxt]


def test_readme_runbook_names_every_template():
    section = runbook_section(read(README))
    missing = [n for n in EXPECTED_TEMPLATES if n not in section]
    assert not missing, f"runbook does not name: {missing}"


def test_readme_runbook_is_ordered_steps():
    section = runbook_section(read(README))
    steps = re.findall(r"^\*\*(\d+)\.", section, flags=re.MULTILINE)
    assert len(steps) >= 7, f"runbook has {len(steps)} numbered steps, expected 7+"
    assert steps == [str(n) for n in range(1, len(steps) + 1)], (
        f"runbook steps are not consecutively numbered: {steps}"
    )


def adoption_section(body: str) -> str:
    start = body.find("## The existing-repo adoption runbook")
    assert start != -1, "README has no existing-repo adoption runbook"
    nxt = body.find("\n## ", start + 1)
    return body[start:] if nxt == -1 else body[start:nxt]


def test_readme_has_both_runbooks():
    body = read(README)
    assert "## The empty-repo runbook" in body
    assert "## The existing-repo adoption runbook" in body


def test_adoption_runbook_is_ordered_steps():
    section = adoption_section(read(README))
    steps = re.findall(r"^\*\*(\d+)\.", section, flags=re.MULTILINE)
    assert len(steps) >= 5, f"adoption runbook has {len(steps)} steps, expected 5+"
    assert steps == [str(n) for n in range(1, len(steps) + 1)], (
        f"adoption steps are not consecutively numbered: {steps}"
    )


def test_adoption_runbook_maps_rather_than_duplicates():
    section = adoption_section(read(README))
    lowered = section.lower()
    assert "do not duplicate" in lowered or "not duplicate" in lowered
    # The three non-negotiable kit rules must be named on adoption.
    assert "per-invocation" in lowered and "git config" in lowered, "identity rule missing"
    assert "merge authority" in lowered, "merge-authority rule missing"
    assert "gates last" in lowered or "gates run last" in lowered, "gates-last rule missing"
    # Roster merge, never overwrite.
    assert ".claude/" in section and "overwrit" in lowered, "roster merge rule missing"


def test_adoption_runbook_ends_with_a_checklist():
    section = adoption_section(read(README))
    assert "### Adoption checklist" in section
    tail = section[section.find("### Adoption checklist"):]
    rows = [ln for ln in tail.splitlines() if ln.strip().startswith("|")]
    assert len(rows) >= 6, f"adoption checklist has {len(rows)} table lines"


def test_readme_keeps_the_sample_and_the_five_ideas():
    body = read(README)
    assert "make_sample.py" in body, "README dropped the 30-second sample"
    assert "The five ideas everything else follows from" in body
    ideas = re.findall(r"^\*\*(\d)\. ", body, flags=re.MULTILINE)
    assert ideas.count("1") >= 1 and len(set(ideas)) >= 5, "fewer than five ideas"


def test_readme_status_table_is_not_hardcoded_as_built():
    """Other units build in parallel; the status table describes design intent."""
    body = read(README)
    assert "tools/wall/" in body
    assert "see `tools/wall/`" in body.lower() or "see tools/wall/" in body.lower(), (
        "status section should point at live status rather than freezing it"
    )


# ---------------------------------------------------------- open questions

def test_open_questions_has_nothing_outside_settled():
    body = read(OPEN_QUESTIONS)
    start = body.find("## Open")
    settled = body.find("## Settled")
    assert start != -1 and settled != -1, "OPEN_QUESTIONS needs Open and Settled sections"
    assert start < settled, "Open comes before Settled"
    open_section = body[start:settled]

    rows = [ln for ln in open_section.splitlines() if ln.strip().startswith("|")]
    assert not rows, f"open questions remain as table rows: {rows}"

    numbered = re.findall(r"^\s*\d+\.\s+\S", open_section, flags=re.MULTILINE)
    assert not numbered, f"open questions remain as a numbered list: {numbered}"

    assert "Nothing." in open_section, (
        "the Open section should state plainly that nothing is open"
    )


def test_settled_section_covers_all_sixteen_questions():
    body = read(OPEN_QUESTIONS)
    settled = body[body.find("## Settled"):]
    numbered = re.findall(r"^(\d+)\.\s+\*\*", settled, flags=re.MULTILINE)
    assert numbered == [str(n) for n in range(1, 17)], (
        f"expected the 16 original questions in order, got {numbered}"
    )


# ---------------------------------------------------------------- gitignore

def test_gitignore_covers_the_derived_surfaces():
    body = read(KIT / ".gitignore")
    for pattern in (".wall/derived/", ".wall/events/", ".wall/logs/", ".wall/runs/",
                    "*.lock", "__pycache__/", ".pytest_cache/"):
        assert pattern in body, f".gitignore is missing {pattern}"


def test_gitignore_wall_patterns_are_root_anchored():
    """Unanchored .wall/ patterns would sweep the committed sample fixtures."""
    lines = [ln.strip() for ln in read(KIT / ".gitignore").splitlines()]
    unanchored = [ln for ln in lines if ln.startswith(".wall/")]
    assert not unanchored, (
        f"unanchored .wall/ patterns would match sample/.wall/: {unanchored}"
    )
    assert "/.wall/events/" in lines, "event shards must be ignored at the root"


def test_sample_event_fixtures_are_not_swept_by_gitignore():
    """The 30-second sample depends on fixtures being in the clone."""
    fixtures = list((KIT / "sample" / ".wall" / "events").rglob("*.jsonl"))
    assert fixtures, "sample event fixtures are missing"
    lines = [ln.strip() for ln in read(KIT / ".gitignore").splitlines()]
    for pattern in lines:
        if pattern and not pattern.startswith("#"):
            assert not pattern.startswith("sample/"), (
                f".gitignore sweeps committed sample fixtures: {pattern}"
            )


def test_readme_does_not_claim_install_adapters_are_stubs():
    """Adapters are real - schtasks, launch agent, user timer."""
    body = read(README)
    for line in body.splitlines():
        if "Install adapters" in line:
            assert "stub" not in line.lower(), f"stale stub claim: {line.strip()}"
            break
    else:
        pytest.fail("status table has no install-adapters row")
