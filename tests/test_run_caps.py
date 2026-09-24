"""`wall run-start` / `wall run-end` and the courier's `over_cap` flag.

run-start writes the run_start MAESTRO.md step 5 names and registers the run
where the SubagentStop hook resolves it; it refuses a run past
`role_limits[role]`. run-end is the no-hooks terminal record, in the hook's
shape. The courier flag catches runs opened by hand, outside the command.

Stdlib + pytest. The hook is driven as a real subprocess, as the harness runs it.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import courier
import wall

KIT = Path(__file__).resolve().parents[1]
SUBAGENT_STOP = KIT / ".claude" / "hooks" / "subagent_stop.py"
SESSION = "s_disp01"


def cli(repo: Path, *args: str) -> int:
    old = sys.argv
    sys.argv = ["wall", "--repo", str(repo), *args]
    try:
        return wall.main()
    finally:
        sys.argv = old


def events(repo: Path) -> list[dict]:
    return wall.fresh_events(repo)


def registry(repo: Path) -> dict:
    return json.loads((repo / ".wall" / "registry" / "open_runs.json").read_text())


def iso(minutes_from_now: float) -> str:
    t = datetime.now(timezone.utc) + timedelta(minutes=minutes_from_now)
    return t.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def start(repo: Path, key: str, item: str = "ST-1", *extra: str) -> int:
    return cli(repo, "run-start", "--key", key, "--role", "builder", "--item", item,
               "--deadline-min", "30", "--session", SESSION, *extra)


@pytest.fixture
def capped(repo, config):
    config({"role_limits": {"builder": 2}, "stale_after_min": 30})
    return repo


# ------------------------------------------------------------- run-start

def test_run_start_writes_the_event_and_registers_the_run(capped, write_shard):
    write_shard("s_other", [{"event": "item_created", "item_id": "ST-1",
                             "trace_id": "tr_st1", "title": "t", "ts": iso(-5)}])
    assert start(capped, "bld_a1", "ST-1", "--scope", "backend/x/",
                 "--model", "m-large", "--decision", "DEC-0001",
                 "--run-id", "run_0001", "--parent-run", "run_0000") == 0
    ev = next(e for e in events(capped) if e.get("event") == "run_start")
    for field, want in (("run_id", "run_0001"), ("agent_key", "bld_a1"),
                        ("role", "builder"), ("item_id", "ST-1"),
                        ("trace_id", "tr_st1"), ("model_requested", "m-large"),
                        ("scope", ["backend/x/"]), ("parent_run_id", "run_0000"),
                        ("decisions_in_context", ["DEC-0001"]),
                        ("session_id", SESSION)):
        assert ev[field] == want, field
    assert ev["deadline"] > ev["ts"]
    rec = registry(capped)["run_0001"]
    # Every field the SubagentStop hook reads off a registry row.
    for field in ("run_id", "session_id", "agent_key", "role", "item_id",
                  "trace_id", "parent_run_id", "model_requested", "started",
                  "decisions_in_context"):
        assert field in rec, field
    assert rec["session_id"] == SESSION and rec["started"] == ev["ts"]


def test_the_hook_resolves_a_run_the_command_registered(capped):
    assert start(capped, "bld_a1", "ST-1", "--run-id", "run_0007") == 0
    env = {k: v for k, v in os.environ.items()
           if k not in ("WALL_RUN_ID", "WALL_SESSION_ID")}
    env["WALL_ROOT"] = str(capped / ".wall")
    proc = subprocess.run([sys.executable, str(SUBAGENT_STOP)],
                          input=json.dumps({"session_id": SESSION}),
                          capture_output=True, text=True, env=env, timeout=60)
    assert proc.returncode == 0
    end = [e for e in events(capped) if e.get("event") == "run_end"]
    assert len(end) == 1
    assert end[0]["run_id"] == "run_0007"
    assert end[0]["hook"]["resolution"] == "open_runs_unique"
    assert end[0]["agent_key"] == "bld_a1" and end[0]["item_id"] == "ST-1"


def test_run_start_refuses_past_the_role_cap(capped, capsys):
    assert start(capped, "bld_a1") == 0
    assert start(capped, "bld_a2") == 0
    capsys.readouterr()
    assert start(capped, "bld_a3") == 1
    err = capsys.readouterr().err
    assert "refusing" in err and "role_limits.builder = 2" in err
    starts = [e for e in events(capped) if e.get("event") == "run_start"]
    assert len(starts) == 2, "a refused run writes nothing"
    assert len(registry(capped)) == 2


def test_over_cap_reason_overrides_and_is_recorded(capped):
    start(capped, "bld_a1")
    start(capped, "bld_a2")
    assert start(capped, "bld_a3", "ST-1", "--over-cap-reason", "prod hotfix") == 0
    ev = [e for e in events(capped) if e.get("event") == "run_start"][-1]
    assert ev["over_cap_reason"] == "prod hotfix"
    assert ev["over_cap"] == {"limit": 2, "open": 3}


def test_cap_counts_only_open_runs(capped, write_shard):
    # One past its deadline, one closed: neither holds a slot.
    write_shard(SESSION, [
        {"event": "run_start", "run_id": "r_old", "role": "builder",
         "ts": iso(-90), "deadline": iso(-60)},
        {"event": "run_start", "run_id": "r_done", "role": "builder", "ts": iso(-5)},
        {"event": "run_end", "run_id": "r_done", "outcome": "pass", "ts": iso(-1)},
        {"event": "run_start", "run_id": "r_rev", "role": "reviewer", "ts": iso(-1)},
    ])
    assert start(capped, "bld_a1") == 0
    assert start(capped, "bld_a2") == 0
    assert start(capped, "bld_a3") == 1


def test_a_hand_written_registry_row_holds_a_slot(capped):
    reg = capped / ".wall" / "registry"
    reg.mkdir(parents=True)
    (reg / "open_runs.json").write_text(json.dumps({"runs": [
        {"run_id": "r_hand", "role": "builder", "session_id": SESSION,
         "started": iso(-1)}]}))
    assert start(capped, "bld_a1") == 0
    assert start(capped, "bld_a2") == 1
    # The list shape the hook accepts is kept on rewrite.
    assert isinstance(registry(capped)["runs"], list)


def test_unreadable_registry_is_refused_not_overwritten(capped):
    reg = capped / ".wall" / "registry"
    reg.mkdir(parents=True)
    (reg / "open_runs.json").write_text("{not json")
    assert start(capped, "bld_a1") == 1
    assert (reg / "open_runs.json").read_text() == "{not json"


def test_duplicate_run_id_and_bad_deadline(capped):
    assert start(capped, "bld_a1", "ST-1", "--run-id", "run_x") == 0
    assert start(capped, "bld_a2", "ST-1", "--run-id", "run_x") == 1
    assert cli(capped, "run-start", "--key", "k", "--role", "builder", "--item",
               "ST-1", "--deadline-min", "0") == 2


def test_no_cap_configured_for_the_role_admits(repo, config):
    config({"role_limits": {"builder": 1}})
    for key in ("r1", "r2", "r3"):
        assert cli(repo, "run-start", "--key", key, "--role", "warden",
                   "--item", "ST-1", "--deadline-min", "5") == 0


# --------------------------------------------------------------- run-end

def test_run_end_writes_the_hook_shape_and_unregisters(capped):
    start(capped, "bld_a1", "ST-1", "--run-id", "run_9", "--model", "m-large")
    assert cli(capped, "run-end", "--run", "run_9", "--outcome", "partial",
               "--cost-usd", "1.5") == 0
    end = [e for e in events(capped) if e.get("event") == "run_end"]
    assert len(end) == 1
    e = end[0]
    assert e["session_id"] == SESSION, "same shard the hook dedupes on"
    for field in ("trace_id", "run_id", "parent_run_id", "agent_key", "agent_name",
                  "role", "model_requested", "model_used", "item_id", "outcome",
                  "error_class", "tokens", "cost_usd", "gh_minutes", "duration_s",
                  "decisions_in_context", "hook"):
        assert field in e, field
    assert e["outcome"] == "partial" and e["cost_usd"] == 1.5
    assert set(e["tokens"]) == {"in", "out", "cache_read", "cache_write"}
    assert e["hook"]["source"] == "wall run-end"
    assert "run_9" not in registry(capped)


def test_run_end_error_outcome_is_run_error_and_folds_outcome_json(capped):
    start(capped, "bld_a1", "ST-1", "--run-id", "run_e")
    run_dir = capped / ".wall" / "runs" / "run_e"
    run_dir.mkdir(parents=True)
    (run_dir / "outcome.json").write_text(json.dumps(
        {"outcome": "timeout", "tokens": {"in": 10, "out": 2}}))
    assert cli(capped, "run-end", "--run", "run_e") == 0
    e = [x for x in events(capped) if x.get("event") == "run_error"][0]
    assert e["outcome"] == "timeout" and e["error_class"] == "model_error"
    assert e["tokens"] == {"in": 10, "out": 2, "cache_read": 0, "cache_write": 0}
    assert e["hook"]["agent_reported"] is True


def test_run_end_refusals(capped):
    assert cli(capped, "run-end", "--run", "nope", "--outcome", "pass") == 1
    start(capped, "bld_a1", "ST-1", "--run-id", "run_1")
    assert cli(capped, "run-end", "--run", "run_1") == 2, "no outcome anywhere"
    assert cli(capped, "run-end", "--run", "run_1", "--outcome", "pass") == 0
    assert cli(capped, "run-end", "--run", "run_1", "--outcome", "pass") == 1
    assert len([e for e in events(capped) if e.get("event") == "run_end"]) == 1


def test_run_end_frees_the_slot(capped):
    start(capped, "bld_a1", "ST-1", "--run-id", "run_1")
    start(capped, "bld_a2", "ST-1", "--run-id", "run_2")
    assert start(capped, "bld_a3") == 1
    cli(capped, "run-end", "--run", "run_1", "--outcome", "pass")
    assert start(capped, "bld_a3") == 0


# ------------------------------------------------------ courier: over_cap

def test_courier_flags_hand_written_runs_over_the_cap(capped, write_shard):
    write_shard(SESSION, [
        {"event": "run_start", "run_id": f"r{n}", "role": "builder",
         "ts": iso(-1), "deadline": iso(30)} for n in range(3)])
    snap = courier.run_once(capped)
    flags = snap["integrity"]["over_cap"]
    assert len(flags) == 1
    assert flags[0]["role"] == "builder" and flags[0]["open"] == 3
    assert flags[0]["limit"] == 2 and flags[0]["run_ids"] == ["r0", "r1", "r2"]


def test_courier_over_cap_is_clean_at_or_under_the_cap(capped, write_shard):
    write_shard(SESSION, [
        {"event": "run_start", "run_id": "r0", "role": "builder", "ts": iso(-1)},
        {"event": "run_start", "run_id": "r1", "role": "builder", "ts": iso(-1)},
        {"event": "run_start", "run_id": "r2", "role": "builder",
         "ts": iso(-90), "deadline": iso(-60)},
    ])
    snap = courier.run_once(capped)
    assert snap["integrity"]["over_cap"] == []
    # The past-deadline run is an orphan on its own deadline instead.
    assert [o["run_id"] for o in snap["integrity"]["orphan_runs"]] == ["r2"]


def test_a_run_deadline_later_than_stale_after_min_is_not_an_orphan(capped, write_shard):
    write_shard(SESSION, [{"event": "run_start", "run_id": "long", "role": "builder",
                           "ts": iso(-45), "deadline": iso(60)}])
    assert courier.run_once(capped)["integrity"]["orphan_runs"] == []
