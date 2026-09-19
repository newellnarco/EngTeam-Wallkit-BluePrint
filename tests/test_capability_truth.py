"""Capability truth: every role/carrier claim cites instructions that exist.

The README's organization table now carries an "Actual instructions" column
(user direction: under-promise and over-deliver). These tests make the
promise mechanical: a cited instruction file that disappears, a role sheet
the table forgot, or a phantom role with no sheet each fail the suite —
a claim that loses its instructions must never quietly become marketing.
"""

from __future__ import annotations

import re
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]
README = KIT / "README.md"
ORG = KIT / "docs" / "diagrams" / "ORG_MAPPING.md"
AGENTS = KIT / ".claude" / "agents"

PATH_RE = re.compile(r"`((?:\.claude|docs|tools|templates)/[A-Za-z0-9_/.-]+?\.(?:md|py|json))`")


def org_table_rows() -> list[str]:
    t = README.read_text(encoding="utf-8")
    start = t.index("| Role (org term) |")
    block = t[start:]
    end = block.index("\n\n")
    return [ln for ln in block[:end].splitlines()[2:] if ln.startswith("|")]


def test_every_org_row_cites_at_least_one_real_instruction_file():
    rows = org_table_rows()
    assert len(rows) >= 13, "org table lost rows"
    for row in rows:
        cells = [c.strip() for c in row.strip("|").split("|")]
        assert len(cells) == 4, f"row lost its instructions column: {row[:60]}"
        cited = PATH_RE.findall(cells[3])
        assert cited, f"no instruction path cited for: {cells[0]}"
        for path in cited:
            assert (KIT / path).is_file(), \
                f"{cells[0]} cites a missing instruction file: {path}"


def test_every_role_sheet_is_claimed_by_the_org_table():
    table = " ".join(org_table_rows())
    for sheet in sorted(AGENTS.glob("*.md")):
        assert f".claude/agents/{sheet.name}" in table, \
            f"role sheet with no org-table row (phantom capability): {sheet.name}"


def test_the_maestro_manual_is_cited_for_the_manager_row():
    table = " ".join(org_table_rows())
    assert ".claude/MAESTRO.md" in table


def test_readme_states_the_three_enforcement_grades():
    t = " ".join(README.read_text(encoding="utf-8").replace("**", "").split())
    for grade in ("structural", "procedural", "advisory"):
        assert grade in t
    assert "Under-promising on purpose" in t
    assert "tests/test_capability_truth.py" in t


def test_org_mapping_carries_the_enforcement_grades_table():
    t = ORG.read_text(encoding="utf-8")
    assert "2b" in t and "Enforcement grades" in t
    flat = " ".join(t.split())
    for grade in ("structural", "procedural", "advisory"):
        assert grade in flat
    # each structural claim names the code file that refuses the violation
    for path in ("tools/wall/agents.py", "tools/wall/server.py", "tools/wall/courier.py"):
        assert path in flat, f"grades table missing structural mechanism {path}"
        assert (KIT / path).is_file()
