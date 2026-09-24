"""The consolidated guide stays true to the kit it describes.

`docs/WALL_KIT_GUIDE.md` is the owner's single consolidated source of truth:
what the kit is, how it installs, works, learns and is removed, and every
change made to it. A guide that falls behind the code is worse than none,
because it is believed. Each test below derives its expectation from the
code or the tree, never from a list typed here, so a new command, config
key, integrity flag, role, skill, decision or document fails CI until the
guide describes it -- in the same pull request that added it.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

KIT = Path(__file__).resolve().parents[1]
GUIDE = KIT / "docs" / "WALL_KIT_GUIDE.md"

sys.path.insert(0, str(KIT / "tools" / "wall"))


def _guide() -> str:
    return GUIDE.read_text(encoding="utf-8")


def _wall_subcommands() -> list[str]:
    src = (KIT / "tools" / "wall" / "wall.py").read_text(encoding="utf-8")
    return sorted(set(re.findall(r'add_parser\(\s*"([\w-]+)"', src)))


def _bootstrap_modes() -> list[str]:
    src = (KIT / "tools" / "wall" / "bootstrap.py").read_text(encoding="utf-8")
    block = re.search(r"for name, fn, help_ in \((.*?)\):", src, re.S)
    assert block, "bootstrap's mode table moved; update this test"
    return re.findall(r'\(\s*"(\w+)",\s*cmd_', block.group(1))


def test_the_guide_exists_and_declares_itself_canonical():
    text = _guide()
    assert "consolidated source of truth" in text
    assert "tests/test_guide_current.py" in text


def test_every_wall_command_is_described():
    text = _guide()
    cmds = _wall_subcommands()
    assert len(cmds) > 20, cmds
    missing = [c for c in cmds if not re.search(r"wall %s\b" % re.escape(c), text)]
    assert not missing, "wall commands the guide does not describe: %s" % missing


def test_every_bootstrap_mode_is_described():
    text = _guide()
    modes = _bootstrap_modes()
    assert set(modes) >= {"fresh", "adopt", "upgrade", "remove"}, modes
    missing = [m for m in modes if "**%s**" % m not in text]
    assert not missing, "bootstrap modes the guide does not describe: %s" % missing


def test_every_config_key_is_described():
    text = _guide()
    cfg = json.loads((KIT / "tools" / "wall" / "config" / "wall.example.json")
                     .read_text(encoding="utf-8"))
    keys = [k for k in cfg if not k.startswith("_")]
    missing = [k for k in keys if "`%s" % k not in text]
    assert not missing, "config keys the guide does not describe: %s" % missing


def test_every_integrity_flag_is_described():
    import wall  # noqa: E402  (tools/wall on sys.path above)
    text = _guide()
    missing = [k for k in wall.FLAG_KEYS if "`%s`" % k not in text]
    assert not missing, "integrity flags the guide does not describe: %s" % missing


def test_every_role_and_skill_is_described():
    text = _guide().lower()
    roles = [p.stem for p in (KIT / ".claude" / "agents").glob("*.md")]
    skills = [p.name for p in (KIT / ".claude" / "skills").iterdir() if p.is_dir()]
    missing = [r for r in roles if r not in text] + \
              ["/" + s for s in skills if "/" + s not in text]
    assert not missing, "roles or skills the guide does not describe: %s" % missing


def test_every_decision_is_in_the_guide_index():
    text = _guide()
    decs = sorted(p.stem for p in (KIT / "docs" / "decisions").glob("DEC-*.md"))
    missing = [d for d in decs if not re.search(r"^\| %s \|" % d, text, re.M)]
    assert not missing, "decisions missing from Appendix A: %s" % missing


def test_decision_status_in_the_guide_matches_the_record():
    """A supersession changes the record's status; the guide must follow."""
    text = _guide()
    for p in sorted((KIT / "docs" / "decisions").glob("DEC-*.md")):
        status = re.search(r"^status:\s*(\w+)", p.read_text(encoding="utf-8"), re.M)
        assert status, p.name
        row = re.search(r"^\| %s \| (\w+) \|" % p.stem, text, re.M)
        assert row and row.group(1) == status.group(1), (
            "%s is %s in its record but %s in the guide"
            % (p.stem, status.group(1), row.group(1) if row else "absent"))


def test_every_document_is_in_the_guide_map():
    text = _guide()
    docs = [p.name for p in (KIT / "docs").glob("*.md")]
    docs += ["compliance/" + p.name for p in (KIT / "docs" / "compliance").glob("*.md")]
    docs += [p.name for p in (KIT / "docs" / "handoffs").glob("*.md")]
    docs += [p.name for p in (KIT / "templates").glob("*.template")]
    missing = [d for d in docs if Path(d).name not in text]
    assert not missing, "documents missing from Appendix B: %s" % missing


def test_the_change_log_is_newest_first():
    dates = re.findall(r"^### (\d{4}-\d{2}-\d{2}):", _guide(), re.M)
    assert dates, "the guide has no change log entries"
    assert dates == sorted(dates, reverse=True), dates


@pytest.mark.parametrize("name", ["README.md", ".claude/MAESTRO.md",
                                  ".claude/agents/reviewer.md"])
def test_the_rule_that_keeps_the_guide_current_is_carried(name):
    assert "docs/WALL_KIT_GUIDE.md" in (KIT / name).read_text(encoding="utf-8"), name
