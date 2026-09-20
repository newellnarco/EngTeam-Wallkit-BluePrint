"""DEC-0017: portability is a standing requirement, mechanically ratcheted.

The Patron's direction (2026-09-20): the kit must be useful and deployable
without major effort to any local machine, server, Docker or cluster —
fresh clean install, or deployed onto an existing setup and assimilating
what was there. The property every deployment document rides on is
STDLIB-ONLY: one pip install and the 30-second sample render stops being
true on a clean box, the Dockerfile grows a build step, and the air-gapped
install dies.

So the promise is a test, not prose: an AST walk over EVERY kit module
asserting each absolute import resolves to the standard library or to the
kit's own modules. The old guard was a per-file string check on testkit.py
("import requests" not in source); this one cannot be dodged by a new
file, a new dependency name, or a `from x import y` spelling.

Mutation that kills it: add `import requests` (or any third-party module)
anywhere under tools/ and the failure names the file and the module.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]


def _absolute_imports(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom):
            # level > 0 is a relative import — kit-local by construction
            if node.level == 0 and node.module:
                yield node.module.split(".")[0]


def _kit_local_names() -> set[str]:
    """Every name an intra-kit absolute import can legitimately use: module
    stems and package directories under tools/ and sample/ (the kit runs
    with those directories on sys.path)."""
    names: set[str] = set()
    for root in (KIT / "tools", KIT / "sample"):
        for py in root.rglob("*.py"):
            if "__pycache__" not in py.parts:
                names.add(py.stem)
        for d in root.rglob("*"):
            if d.is_dir() and d.name != "__pycache__":
                names.add(d.name)
        names.add(root.name)
    return names


def _walk_kit_modules():
    for root in (KIT / "tools", KIT / "sample"):
        for py in sorted(root.rglob("*.py")):
            if "__pycache__" not in py.parts:
                yield py


def test_every_kit_module_imports_only_stdlib_or_kit(monkeypatch=None):
    local = _kit_local_names()
    offenders = []
    for py in _walk_kit_modules():
        for name in _absolute_imports(py):
            if name in sys.stdlib_module_names or name in local:
                continue
            offenders.append(f"{py.relative_to(KIT)} imports {name!r}")
    assert not offenders, (
        "DEC-0017: the kit is stdlib-only. A third-party dependency must be "
        "a separate, optional, consent-gated adapter with its own DEC, "
        "never a core import:\n  " + "\n  ".join(offenders)
    )


def test_the_ratchet_actually_walks_something():
    """A ratchet over an empty set is a green light wired to nothing —
    prove the walk sees the courier and at least a dozen modules."""
    files = list(_walk_kit_modules())
    assert len(files) >= 12
    assert any(p.name == "courier.py" for p in files)


def test_dec_0017_is_on_the_index():
    index = (KIT / "docs" / "decisions" / "index.md").read_text(encoding="utf-8")
    assert "DEC-0017" in index
    assert "Portability" in index
