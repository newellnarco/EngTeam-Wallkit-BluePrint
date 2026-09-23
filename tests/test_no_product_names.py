"""Kit-wide name guard: the kit describes its source deployments, never names them.

The skills library already refuses the names of the deployments it was mined
from (`test_skills_library.forbidden_names`). The owner directive widens that
to the whole kit: every tracked text file -- docs, templates, decision records,
code, tests, sample and demo data -- describes a source by its SHAPE ("the
resident desktop app", "the network appliance", "the research-publishing
repo", "the browser extension"), and a name anywhere turns a lesson back into
an anecdote about somebody else's system.

One list of names, owned by `test_skills_library`; this file reuses it rather
than restating it, so the two guards cannot drift apart. The only file exempt
is the one that defines the list (it has to spell the names to refuse them).

Stdlib + pytest only.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from test_skills_library import forbidden_names

KIT = Path(__file__).resolve().parents[1]

#: Text files the guard reads, by extension. Binary assets (png) carry no prose.
TEXT_SUFFIXES = frozenset({
    ".md", ".template", ".py", ".json", ".jsonl", ".yml", ".yaml", ".html",
    ".js", ".css", ".toml", ".sh", ".bat", ".svg", ".txt", ".example", ".yar",
})

#: The one file allowed to spell the names: it defines the refusal list.
EXEMPT = frozenset({"tests/test_skills_library.py"})


def tracked_text_files(root: Path = KIT) -> list[str]:
    """Repo-relative paths of every tracked text file under `root`.

    `git ls-files` is the source of truth (untracked scratch is not the kit);
    without git -- an exported tarball -- the tree is walked instead, skipping
    `.git`, so the guard is never silently empty.
    """
    try:
        out = subprocess.run(["git", "ls-files", "-z"], cwd=root, check=True,
                             capture_output=True).stdout.decode("utf-8")
        paths = [p for p in out.split("\0") if p]
    except (OSError, subprocess.CalledProcessError):
        paths = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in (".git", "__pycache__")]
            for f in filenames:
                paths.append(Path(dirpath, f).relative_to(root).as_posix())
    return sorted(p for p in paths
                  if not p.startswith(".git/") and _is_text(root, p))


def _is_text(root: Path, rel: str) -> bool:
    """A known text suffix, or -- for a file with no suffix or a dotfile
    (Dockerfile, Makefile, .gitignore) -- content with no NUL byte. A guard
    that skips those files reports clean on files it never read."""
    p = Path(rel)
    if p.suffix in TEXT_SUFFIXES:
        return True
    if p.suffix and not p.name.startswith("."):
        return False
    try:
        with open(root / rel, "rb") as fh:
            return b"\0" not in fh.read(8192)
    except OSError:
        return False


def name_hits(root: Path = KIT) -> list[str]:
    """`path:line: names` for every line of every scanned file that names a source."""
    hits: list[str] = []
    for rel in tracked_text_files(root):
        if rel in EXEMPT:
            continue
        path = root / rel
        if not path.is_file():      # tracked but deleted in the working tree
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for n, line in enumerate(text.splitlines(), 1):
            found = forbidden_names(line)
            if found:
                hits.append("%s:%d: %s" % (rel, n, sorted(set(found))))
    return hits


def test_no_tracked_text_file_names_a_source_deployment():
    hits = name_hits()
    assert not hits, "source-deployment names in the kit:\n" + "\n".join(hits)


def test_the_scan_is_not_vacuous():
    """A guard over zero files passes forever. The scan must reach the kit's
    docs, code, tests and templates -- including a known file of each kind."""
    files = set(tracked_text_files())
    for must in ("README.md", "docs/TEMPLATE_INTAKE.md", "tools/wall/adapters/board_import.py",
                 "tests/test_board_import.py", "templates/FAILURE_PATTERNS.md.template",
                 "docs/decisions/DEC-0029.md"):
        assert must in files, must
    assert len(files) > 150, len(files)


def test_the_scan_catches_a_planted_name(tmp_path: Path):
    """Mutation, in miniature: a name planted in an otherwise clean tree is
    reported with its path and line; the exempt list file is not."""
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "clean.md").write_text("a resident desktop app\n", encoding="utf-8")
    # Assembled from parts so this file itself stays name-free.
    names = ("M" + "AX3", "R" + "EEF", "net" + "sniff")
    for i, name in enumerate(names):
        (tmp_path / "docs" / ("n%d.md" % i)).write_text("ok\nsee %s here\n" % name,
                                                         encoding="utf-8")
    # Files with no suffix and dotfiles are text too; a binary one is skipped.
    (tmp_path / "Dockerfile").write_text("FROM x\n# %s\n" % names[0], encoding="utf-8")
    (tmp_path / ".gitignore").write_text("*.pyc\n%s/\n" % names[2], encoding="utf-8")
    (tmp_path / "blob").write_bytes(b"\0\1" + names[0].encode())
    hits = name_hits(tmp_path)          # no git here: exercises the walk fallback
    assert sorted(h.split(":")[0] for h in hits) == [
        ".gitignore", "Dockerfile", "docs/n0.md", "docs/n1.md", "docs/n2.md"]
    assert all(":2: " in h for h in hits), hits


@pytest.mark.parametrize("word", ["max-age=60", "max(n, 1)", "maximum", "a reef metaphor",
                                  "scouting", "LIMIT"])
def test_ordinary_words_are_not_names(word):
    assert not forbidden_names(word), word
