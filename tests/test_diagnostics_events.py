"""The diagnostics-loop events (EVENT_SCHEMA section 9) and their two
courier-side integrity checks: a finding routed story_filed with no
story_filed past the SLA (`dropped_findings`), and a verify_requested older
than the horizon (`verify_overdue`, beside the `verify_waiting` queue).

Stdlib + pytest.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import courier
import wall


def cli(repo: Path, *args: str) -> int:
    old = sys.argv
    sys.argv = ["wall", "--repo", str(repo), *args]
    try:
        return wall.main()
    finally:
        sys.argv = old


def of(repo: Path, kind: str) -> list[dict]:
    return [e for e in wall.fresh_events(repo) if e.get("event") == kind]


def iso(minutes_from_now: float) -> str:
    t = datetime.now(timezone.utc) + timedelta(minutes=minutes_from_now)
    return t.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def finding(repo: Path, route: str = "story_filed", cls: str = "unclassified") -> int:
    return cli(repo, "finding", "--signature",
               "worker 4411 timed out at 2026-09-19T12:00:03Z req deadbeefcafe",
               "--class", cls, "--route", route, "--snapshot-ref",
               "wall-events:diag/snapshot.json")


# ------------------------------------------------------------- the events

def test_finding_normalizes_the_signature(repo):
    assert finding(repo) == 0
    ev = of(repo, "diagnostic_finding")[0]
    assert ev["signature"] == "worker <n> timed out at <ts> req <hex>"
    assert ev["class"] == "unclassified" and ev["route"] == "story_filed"
    assert ev["snapshot_ref"] == "wall-events:diag/snapshot.json"


def test_only_a_known_playbook_is_auto_repaired(repo):
    assert finding(repo, route="auto_repaired", cls="unclassified") == 1
    assert of(repo, "diagnostic_finding") == []
    assert finding(repo, route="auto_repaired", cls="known_playbook") == 0


def test_story_filed_joins_finding_to_item(repo):
    finding(repo)
    ref = of(repo, "diagnostic_finding")[0]["event_id"]
    assert cli(repo, "story-filed", "--finding", ref[:8], "--item", "BG-7") == 0
    ev = of(repo, "story_filed")[0]
    assert ev["finding_ref"] == ref and ev["item_id"] == "BG-7"
    # Once per finding.
    assert cli(repo, "story-filed", "--finding", ref, "--item", "BG-8") == 1


def test_story_filed_refuses_an_unknown_finding(repo):
    assert cli(repo, "story-filed", "--finding", "0123456789ab", "--item", "BG-7") == 1
    assert cli(repo, "story-filed", "--finding", "0123", "--item", "BG-7") == 1
    assert of(repo, "story_filed") == []


def test_verify_request_and_the_human_answer(repo):
    assert cli(repo, "verify-request", "--item", "ST-3", "--what", "export button",
               "--steps", "open the report", "--steps", "click export") == 0
    req = of(repo, "verify_requested")[0]
    assert req["what_changed"] == "export button"
    assert req["verify_steps"] == ["open the report", "click export"]
    assert cli(repo, "verified", "--item", "ST-3", "--verdict", "confirmed") == 0
    ans = of(repo, "verified")[0]
    assert ans["session_id"] == "s_human" and ans["source"] == "human"
    assert ans["verdict"] == "confirmed" and ans["by"] == "engineer"


def test_verify_refusals(repo):
    assert cli(repo, "verify-request", "--item", "ST-3", "--what", "x") == 2
    assert cli(repo, "verified", "--item", "ST-3", "--verdict", "confirmed") == 1
    cli(repo, "verify-request", "--item", "ST-3", "--what", "x", "--steps", "look")
    assert cli(repo, "verified", "--item", "ST-3",
               "--verdict", "confirmed_with_findings") == 2
    assert cli(repo, "verified", "--item", "ST-3", "--verdict",
               "confirmed_with_findings", "--note", "colour is off") == 0
    assert of(repo, "verified")[0]["note"] == "colour is off"


# -------------------------------------------------- courier: dropped ball

def test_a_finding_with_no_story_past_the_sla_is_flagged(repo, config, write_shard):
    config({"sla_minutes": {"story_filed": 30}})
    rows = write_shard("s_diag", [
        {"event": "diagnostic_finding", "signature": "a", "class": "unclassified",
         "route": "story_filed", "snapshot_ref": "x", "ts": iso(-45)},
        {"event": "diagnostic_finding", "signature": "b", "class": "unclassified",
         "route": "story_filed", "snapshot_ref": "x", "ts": iso(-45)},
        {"event": "diagnostic_finding", "signature": "c", "class": "unclassified",
         "route": "story_filed", "snapshot_ref": "x", "ts": iso(-5)},
        {"event": "diagnostic_finding", "signature": "d", "class": "known_playbook",
         "route": "auto_repaired", "snapshot_ref": "x", "ts": iso(-45)},
    ])
    write_shard("s_maestro", [{"event": "story_filed", "item_id": "BG-1",
                               "finding_ref": rows[1]["event_id"], "ts": iso(-40)}])
    flags = courier.run_once(repo)["integrity"]["dropped_findings"]
    assert [f["signature"] for f in flags] == ["a"], \
        "filed, inside the SLA, and auto-repaired findings are not dropped balls"
    assert flags[0]["finding_ref"] == rows[0]["event_id"] and flags[0]["sla_min"] == 30


def test_story_filed_sla_has_a_default(repo, write_shard):
    write_shard("s_diag", [
        {"event": "diagnostic_finding", "signature": "a", "route": "story_filed",
         "ts": iso(-30)},
        {"event": "diagnostic_finding", "signature": "b", "route": "story_filed",
         "ts": iso(-(courier.DEFAULT_STORY_FILED_SLA_MIN + 5))},
    ])
    flags = courier.run_once(repo)["integrity"]["dropped_findings"]
    assert [f["signature"] for f in flags] == ["b"]


# -------------------------------------------------- courier: verify queue

def test_verify_queue_and_overdue(repo, config, write_shard):
    config({"verify_horizon_days": 2})
    write_shard("s_maestro", [
        {"event": "verify_requested", "item_id": "ST-1", "what_changed": "old",
         "verify_steps": ["look"], "ts": iso(-3 * 1440)},
        {"event": "verify_requested", "item_id": "ST-2", "what_changed": "new",
         "verify_steps": ["look"], "ts": iso(-60)},
        {"event": "verify_requested", "item_id": "ST-3", "what_changed": "done",
         "verify_steps": ["look"], "ts": iso(-4 * 1440)},
        {"event": "verified", "item_id": "ST-3", "verdict": "confirmed",
         "ts": iso(-1440)},
    ])
    snap = courier.run_once(repo)
    assert [v["item_id"] for v in snap["verify_waiting"]] == ["ST-1", "ST-2"]
    assert [v["item_id"] for v in snap["integrity"]["verify_overdue"]] == ["ST-1"]


def test_doctor_names_the_new_flags(repo, config, write_shard, capsys):
    config({"verify_horizon_days": 1, "role_limits": {"builder": 0}})
    write_shard("s_maestro", [
        {"event": "verify_requested", "item_id": "ST-1", "what_changed": "x",
         "ts": iso(-3 * 1440)},
        {"event": "run_start", "run_id": "r1", "role": "builder", "ts": iso(-1)},
    ])
    courier.run_once(repo)
    capsys.readouterr()
    cli(repo, "doctor")
    out = capsys.readouterr().out
    assert "verify_overdue   1 flagged" in out
    assert "over_cap         1 flagged" in out
    assert "dropped_findings clean" in out
