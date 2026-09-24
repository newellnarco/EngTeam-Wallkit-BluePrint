"""Doc drift: the INSTALL.md CLI table lists exactly the subcommands wall.py has.

The subcommands are read from tools/wall/wall.py's `add_parser` calls with
`ast`, so the test follows the code without running `main()`. The table rows
are read from the "## CLI surface" section of docs/INSTALL.md: every row whose
first cell is `` `wall <command>` ``. A command added to the parser without a
row, a row for a command that does not exist, and a command listed twice all
fail.

Stdlib + pytest only.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]
WALL = KIT / "tools" / "wall" / "wall.py"
INSTALL = KIT / "docs" / "INSTALL.md"
SECTION = "## CLI surface"
ROW = re.compile(r"^\|\s*`wall ([a-z][a-z0-9-]*)`\s*\|")


def parser_commands() -> list[str]:
    """Every subcommand name passed to an `add_parser(...)` call, in order."""
    tree = ast.parse(WALL.read_text(encoding="utf-8"))
    cmds = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "add_parser" and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)):
            cmds.append(node.args[0].value)
    return cmds


def cli_section(text: str) -> str:
    start = text.index(SECTION + "\n")
    nxt = text.find("\n## ", start + len(SECTION))
    return text[start:] if nxt < 0 else text[start:nxt]


def table_commands(text: str) -> list[str]:
    return [m.group(1) for line in cli_section(text).splitlines()
            if (m := ROW.match(line))]


def test_parser_is_read():
    """A positive control: the reader must find the parser's commands, or an
    empty set on both sides would pass the equality below."""
    cmds = parser_commands()
    assert len(cmds) >= 30
    for known in ("run-once", "doctor", "run-start", "retro", "install",
                  "fetch-events"):
        assert known in cmds


def test_parser_has_no_duplicate_subcommands():
    cmds = parser_commands()
    assert len(cmds) == len(set(cmds))


def test_table_lists_every_subcommand_once():
    rows = table_commands(INSTALL.read_text(encoding="utf-8"))
    dupes = sorted({c for c in rows if rows.count(c) > 1})
    assert not dupes, "listed more than once in the INSTALL.md CLI table: %s" % dupes


def test_table_matches_the_parser_exactly():
    rows = set(table_commands(INSTALL.read_text(encoding="utf-8")))
    cmds = set(parser_commands())
    missing = sorted(cmds - rows)
    extra = sorted(rows - cmds)
    assert not missing, "wall.py subcommands missing from the INSTALL.md table: %s" % missing
    assert not extra, "INSTALL.md table rows with no wall.py subcommand: %s" % extra


def test_repo_is_documented_as_a_global_flag():
    """`--repo` is on the top-level parser, so it goes before the subcommand;
    the old summary showed it after `register`, which argparse rejects."""
    section = cli_section(INSTALL.read_text(encoding="utf-8"))
    assert "[--repo PATH] <command>" in section
    for line in section.splitlines():
        if ROW.match(line):
            assert "--repo" not in line, "--repo placed after a subcommand: %s" % line


def test_table_reader_catches_a_missing_and_an_extra_row():
    """The reader itself, against a doctored copy: drop one row, add a bogus one."""
    text = INSTALL.read_text(encoding="utf-8")
    doctored = text.replace("| `wall diff-state` |", "| `wall diff-states` |", 1)
    assert doctored != text
    rows = set(table_commands(doctored))
    cmds = set(parser_commands())
    assert "diff-state" in cmds - rows
    assert "diff-states" in rows - cmds
