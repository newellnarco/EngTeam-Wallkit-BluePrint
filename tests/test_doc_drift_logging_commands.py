"""Doc drift: every `wall <cmd>` in LOGGING_AND_AUDIT.md exists, or is marked planned.

The real subcommands are parsed from tools/wall/wall.py's argparse calls with
`ast`, so the test follows the code. A command in the "Planned -- not built"
list must NOT exist yet: once it is built, it moves out of that list.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]
DOC = KIT / "docs" / "LOGGING_AND_AUDIT.md"
WALL = KIT / "tools" / "wall" / "wall.py"
PLANNED_MARK = "**Planned -- not built.**"


def parser_commands() -> set[str]:
    tree = ast.parse(WALL.read_text(encoding="utf-8"))
    cmds = set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "add_parser" and node.args
                and isinstance(node.args[0], ast.Constant)):
            cmds.add(node.args[0].value)
    return cmds


def parser_flags() -> set[str]:
    flags = set()
    for path in (KIT / "tools").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "add_argument"):
                flags.update(a.value for a in node.args
                             if isinstance(a, ast.Constant) and isinstance(a.value, str))
    return flags


def _split() -> tuple[str, str]:
    text = DOC.read_text(encoding="utf-8")
    assert PLANNED_MARK in text, "the planned list lost its label"
    head, planned = text.split(PLANNED_MARK, 1)
    # the planned list ends at the next section break, if any
    planned = re.split(r"\n---\n|\n## ", planned, maxsplit=1)[0]
    rest = head + text.split(PLANNED_MARK, 1)[1][len(planned):]
    return rest, planned


def _mentions(text: str) -> set[str]:
    """`wall <cmd>` in inline code, or at the start of a fenced-block line."""
    inline = re.findall(r"`wall ([a-z][a-z-]*)", text)
    fenced = re.findall(r"^wall ([a-z][a-z-]*)", text, re.MULTILINE)
    return set(inline) | set(fenced)


def test_parser_is_found():
    assert {"trace", "why", "rebuild", "diff-state", "doctor"} <= parser_commands()


def test_every_documented_command_exists():
    rest, _ = _split()
    missing = _mentions(rest) - parser_commands()
    assert not missing, f"documented but not in wall.py (mark them planned): {sorted(missing)}"


def test_planned_commands_are_really_unbuilt():
    _, planned = _split()
    cmds = _mentions(planned)
    assert cmds, "planned list is empty -- drop the label or the list"
    built = cmds & parser_commands()
    assert not built, f"built now, move out of the planned list: {sorted(built)}"


def test_fake_agent_flag_only_in_planned_list():
    rest, planned = _split()
    assert "--fake-agent" not in parser_flags()
    assert "`--fake-agent`" in planned
    # outside the list it may only be named to say it does not exist
    for line in rest.splitlines():
        if "--fake-agent" in line:
            assert "no `--fake-agent`" in line, line
