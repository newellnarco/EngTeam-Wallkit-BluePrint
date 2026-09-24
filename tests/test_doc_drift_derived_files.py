"""Doc drift: WALL_STANDARDS' derived/ layout names every file the code writes.

The list is taken from the code by running it: `courier.run_once` on an empty
repo, and `wall.write_doctor_json` (what `wall doctor --json` calls). Whatever
lands in .wall/derived/ must appear in the layout block.
"""

from __future__ import annotations

import re
from pathlib import Path

import courier
import wall

KIT = Path(__file__).resolve().parents[1]
STANDARDS = KIT / "docs" / "WALL_STANDARDS.md"


def _layout_block() -> str:
    text = STANDARDS.read_text(encoding="utf-8")
    m = re.search(r"```\n(\.wall/.*?)```", text, re.DOTALL)
    assert m, "WALL_STANDARDS lost its .wall/ layout block"
    block = m.group(1)
    start = block.index("derived/")
    end = block.index("\n  logs/", start)
    return block[start:end]


def _written_by_code(tmp_path: Path) -> set[str]:
    (tmp_path / ".wall" / "events").mkdir(parents=True)
    courier.run_once(tmp_path)
    wall.write_doctor_json(tmp_path)
    derived = tmp_path / ".wall" / "derived"
    return {p.name for p in derived.iterdir() if p.is_file()}


def test_code_writes_the_known_core(tmp_path):
    written = _written_by_code(tmp_path)
    assert {"wall.json", "wall.html", "ledger.jsonl", "heartbeat.json",
            "doctor.json"} <= written


def test_layout_lists_every_derived_file(tmp_path):
    block = _layout_block()
    listed = {tok.strip("`(),:") for tok in block.split()}
    missing = _written_by_code(tmp_path) - listed
    assert not missing, f"derived/ layout omits files the code writes: {sorted(missing)}"


def test_decision_range_cannot_go_stale():
    text = " ".join(STANDARDS.read_text(encoding="utf-8").split())
    assert not re.search(r"DEC-0001` (through|to) `DEC-\d{4}", text)
    assert "docs/decisions/index.md" in text
