"""Shared fixtures. pytest is a dev dependency; the modules under test are
stdlib-only and must stay that way, so nothing here leaks into them."""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

import pytest

KIT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KIT / "tools" / "wall"))
sys.path.insert(0, str(KIT / "sample"))


@pytest.fixture
def repo(tmp_path):
    """An empty repo with a .wall/ skeleton and no git."""
    (tmp_path / ".wall" / "events" / "2026-09-19").mkdir(parents=True)
    (tmp_path / ".wall" / "config").mkdir(parents=True)
    return tmp_path


@pytest.fixture
def write_shard(repo):
    """Write a list of event dicts to one shard, filling the envelope."""
    def _write(session_id, events, day="2026-09-19", renumber=True):
        rows = []
        for n, e in enumerate(events, 1):
            row = {"schema_version": 1, "event_id": str(uuid.uuid4()),
                   "seq": n if renumber else e.get("seq"),
                   "ts": e.get("ts", f"2026-09-19T12:{n:02d}:00.000Z"),
                   "session_id": session_id}
            row.update(e)
            if renumber:
                row["seq"] = n
            rows.append(row)
        path = repo / ".wall" / "events" / day / f"{session_id}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
        return rows
    return _write


@pytest.fixture
def config(repo):
    def _write(payload):
        (repo / ".wall" / "config" / "wall.json").write_text(
            json.dumps(payload), encoding="utf-8")
        return payload
    return _write
