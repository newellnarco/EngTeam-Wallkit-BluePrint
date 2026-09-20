"""wall summary — one implementation, two presentations (DEC-0018).

`build_summary` is the single fold the human CLI prints and the MCP
adapter will serve; pinned here over the SAMPLE repo's real snapshot so
the fold is exercised against the same data the quickstart renders.
"""

from __future__ import annotations

import json
import types
from datetime import UTC, datetime
from pathlib import Path

import summary as summary_mod
import wall as wall_mod

KIT = Path(__file__).resolve().parents[1]
SAMPLE_SNAP = json.loads(
    (KIT / "sample" / ".wall" / "derived" / "wall.json").read_text(encoding="utf-8"))


def test_build_summary_counts_canonically():
    """Two spellings of one state never read as two states: the sample's
    ready/triage fold to planned, active to in_progress, in_review to
    review. Mutation: count the raw status and 'planned 4' splinters."""
    s = summary_mod.build_summary(SAMPLE_SNAP)
    assert s.repo == "Atlas-Core" and s.branch == "main"
    assert s.items_total == 11 and s.arcs == 3
    assert s.by_status == {"planned": 4, "blocked": 2, "done": 2,
                           "in_progress": 2, "review": 1}


def test_in_flight_triage_order_blocked_first():
    s = summary_mod.build_summary(SAMPLE_SNAP)
    states = [line.split("[")[1] for line in s.in_flight]
    assert [x.split(" ")[0].rstrip("]") for x in states] == [
        "blocked", "blocked", "review", "in_progress", "in_progress"]


def test_waiting_and_questions_and_integrity():
    s = summary_mod.build_summary(SAMPLE_SNAP)
    assert len(s.waiting_on_you) == 3
    assert all("(" in w and "):" in w for w in s.waiting_on_you)
    answered = sum(1 for q in SAMPLE_SNAP["questions"]
                   if q.get("status") in ("answered", "closed"))
    assert s.questions_open == len(SAMPLE_SNAP["questions"]) - answered
    assert s.integrity_flags > 0  # the sample deliberately carries flags


def test_heartbeat_is_optional_and_honest():
    s = summary_mod.build_summary(SAMPLE_SNAP, heartbeat=None)
    assert s.heartbeat_ok is None
    out = summary_mod.format_summary(s)
    assert "courier:" not in out  # no fabricated health line

    degraded = summary_mod.build_summary(
        SAMPLE_SNAP, heartbeat={"ok": False, "events": 78, "corrupt_lines": 2})
    out2 = summary_mod.format_summary(degraded)
    assert "DEGRADED" in out2 and "2 corrupt" in out2


def test_format_summary_carries_every_section():
    s = summary_mod.build_summary(SAMPLE_SNAP,
                                  heartbeat={"ok": True, "events": 78,
                                             "corrupt_lines": 0})
    now = datetime(2026, 9, 21, tzinfo=UTC)
    out = summary_mod.format_summary(s, now=now)
    assert "Atlas-Core · main" in out
    assert "11 items / 3 arcs" in out
    assert "in flight:" in out and "BG-021" in out
    assert "waiting on you (3):" in out
    assert "budget pace:" in out


def test_cli_summary_over_sample(capsys):
    a = types.SimpleNamespace(repo=str(KIT / "sample"), as_json=False)
    assert wall_mod.cmd_summary(a) == 0
    out = capsys.readouterr().out
    assert "Atlas-Core" in out and "in flight:" in out


def test_cli_summary_json_is_the_same_fold(capsys):
    a = types.SimpleNamespace(repo=str(KIT / "sample"), as_json=True)
    assert wall_mod.cmd_summary(a) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["by_status"]["planned"] == 4
    assert payload["items_total"] == 11


def test_cli_missing_snapshot_is_a_named_instruction(tmp_path, capsys):
    a = types.SimpleNamespace(repo=str(tmp_path), as_json=False)
    assert wall_mod.cmd_summary(a) == 1
    assert "wall run-once" in capsys.readouterr().out
