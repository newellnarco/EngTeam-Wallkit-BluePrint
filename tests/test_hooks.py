"""Hook-layer tests: the ledger shape, the scrubber, and the never-block guarantee.

The hooks are driven as real subprocesses with synthetic stdin payloads, because
that is exactly how the harness runs them -- importing them would test a
different thing than the one that ships.

Zero model calls. Stdlib plus pytest.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

KIT = Path(__file__).resolve().parents[1]
HOOKS = KIT / ".claude" / "hooks"
SUBAGENT_STOP = HOOKS / "subagent_stop.py"
TOOL_USE = HOOKS / "tool_use.py"

SESSION = "s_test01"
RUN_ID = "run_0142"

REQUIRED_EVENT_FIELDS = ("schema_version", "event_id", "seq", "ts", "session_id", "event")
TERMINAL_EVENTS = ("run_end", "run_error")
VALID_OUTCOMES = ("pass", "partial", "blocked", "timeout", "error", "human_required")


# --------------------------------------------------------------- harness

def run_hook(script: Path, payload, *, wall: Path | None = None,
             cwd: Path | None = None, env_extra: dict | None = None):
    env = dict(os.environ)
    env.pop("WALL_ROOT", None)
    env.pop("WALL_RUN_ID", None)
    env.pop("WALL_SESSION_ID", None)
    if wall is not None:
        env["WALL_ROOT"] = str(wall)
    env.update(env_extra or {})
    raw = payload if isinstance(payload, str) else json.dumps(payload)
    return subprocess.run(
        [sys.executable, str(script)],
        input=raw, capture_output=True, text=True,
        cwd=str(cwd) if cwd else str(KIT), env=env, timeout=60,
    )


@pytest.fixture()
def wall(tmp_path: Path) -> Path:
    """A .wall with one run registered, as the Maestro does at dispatch."""
    root = tmp_path / ".wall"
    (root / "registry").mkdir(parents=True)
    (root / "registry" / "open_runs.json").write_text(json.dumps({
        RUN_ID: {
            "run_id": RUN_ID, "session_id": SESSION, "agent_key": "bld_a41f09",
            "agent_name": "Desmond", "role": "builder", "item_id": "ST-106",
            "trace_id": "tr_st106", "parent_run_id": "run_0139",
            "model_requested": "claude-opus-5", "started": "2026-09-19T14:00:00.000Z",
        }
    }), encoding="utf-8")
    return root


def read_events(wall: Path) -> list[dict]:
    out = []
    for shard in sorted((wall / "events").rglob("*.jsonl")):
        for line in shard.read_text(encoding="utf-8").splitlines():
            if line.strip():
                out.append(json.loads(line))
    return out


def hooks_log(wall: Path) -> str:
    path = wall / "logs" / "hooks.log"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def read_tools(wall: Path, run_id: str = RUN_ID) -> list[dict]:
    path = wall / "runs" / run_id / "tools.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


# --------------------------------------------------- subagent_stop: ledger

def test_writes_a_well_formed_terminal_event(wall: Path):
    proc = run_hook(SUBAGENT_STOP, {"session_id": SESSION,
                                    "hook_event_name": "SubagentStop",
                                    "cwd": str(wall.parent)}, wall=wall)
    assert proc.returncode == 0

    events = read_events(wall)
    assert len(events) == 1
    ev = events[0]
    for field in REQUIRED_EVENT_FIELDS:
        assert field in ev, field
    assert ev["event"] in TERMINAL_EVENTS
    assert ev["outcome"] in VALID_OUTCOMES
    assert ev["schema_version"] == 1
    assert ev["ts"].endswith("Z")
    assert ev["session_id"] == SESSION
    # Resolved from open_runs.json, so the identity spine is intact.
    assert ev["run_id"] == RUN_ID
    assert ev["agent_key"] == "bld_a41f09"
    assert ev["trace_id"] == "tr_st106"
    assert ev["parent_run_id"] == "run_0139"
    assert ev["item_id"] == "ST-106"
    # Keys are identity, names are labels -- but both are carried for display.
    assert ev["agent_name"] == "Desmond"
    assert set(ev["tokens"]) == {"in", "out", "cache_read", "cache_write"}
    assert ev["hook"]["resolution"] == "open_runs_unique"
    assert ev["hook"]["agent_reported"] is False


def test_event_is_one_line_per_record(wall: Path):
    for _ in range(3):
        run_hook(SUBAGENT_STOP, {"session_id": SESSION,
                                 "hook_event_name": "SubagentStop",
                                 "run_id": "run_x%d" % _}, wall=wall)
    shards = list((wall / "events").rglob("*.jsonl"))
    assert len(shards) == 1
    text = shards[0].read_text(encoding="utf-8")
    assert text.endswith("\n")
    assert len(text.splitlines()) == 3
    for line in text.splitlines():
        json.loads(line)  # no interleaving, every line is a whole record


def test_seq_is_monotonic_per_session(wall: Path):
    for i in range(3):
        run_hook(SUBAGENT_STOP, {"session_id": SESSION, "hook_event_name": "SubagentStop",
                                 "run_id": "run_seq%d" % i}, wall=wall)
    assert [e["seq"] for e in read_events(wall)] == [1, 2, 3]


def test_payload_error_becomes_run_error(wall: Path):
    proc = run_hook(SUBAGENT_STOP, {"session_id": SESSION,
                                    "hook_event_name": "SubagentStop",
                                    "error": "tool exploded"}, wall=wall)
    assert proc.returncode == 0
    ev = read_events(wall)[0]
    assert ev["event"] == "run_error"
    assert ev["outcome"] == "error"
    assert ev["error_class"] == "tool_error"


def test_agent_outcome_file_is_folded_in(wall: Path):
    run_dir = wall / "runs" / RUN_ID
    run_dir.mkdir(parents=True)
    (run_dir / "outcome.json").write_text(json.dumps({
        "outcome": "partial", "tokens": {"in": 10, "out": 2, "cache_read": 900},
        "cost_usd": 1.84, "duration_s": 212, "decisions_in_context": ["DEC-0043"],
        "model_used": "claude-opus-5",
    }), encoding="utf-8")

    run_hook(SUBAGENT_STOP, {"session_id": SESSION, "hook_event_name": "SubagentStop"},
             wall=wall)
    ev = read_events(wall)[0]
    assert ev["event"] == "run_end" and ev["outcome"] == "partial"
    assert ev["tokens"] == {"in": 10, "out": 2, "cache_read": 900, "cache_write": 0}
    assert ev["cost_usd"] == 1.84
    assert ev["decisions_in_context"] == ["DEC-0043"]
    assert ev["hook"]["agent_reported"] is True


def test_does_not_duplicate_a_terminal_event_the_agent_already_wrote(wall: Path):
    shard = wall / "events" / "2026-09-19" / ("%s.jsonl" % SESSION)
    shard.parent.mkdir(parents=True)
    shard.write_text(json.dumps({
        "schema_version": 1, "event_id": "pre-existing", "seq": 1,
        "ts": "2026-09-19T14:03:22.441Z", "session_id": SESSION,
        "run_id": RUN_ID, "event": "run_end", "outcome": "pass",
    }) + "\n", encoding="utf-8")

    proc = run_hook(SUBAGENT_STOP, {"session_id": SESSION,
                                    "hook_event_name": "SubagentStop"}, wall=wall)
    assert proc.returncode == 0
    events = read_events(wall)
    assert len(events) == 1 and events[0]["event_id"] == "pre-existing"
    assert "already_terminal" in hooks_log(wall)


def test_a_closed_run_is_not_replaced_by_a_phantom_unresolved_event(wall: Path):
    """Regression: with the only registered run already terminal, resolution used
    to fall through to a synthetic `run_unknown_*` id, so the dedupe never fired
    and the ledger gained a second, unattributed terminal record for work that
    was already accounted for."""
    shard = wall / "events" / "2026-09-19" / ("%s.jsonl" % SESSION)
    shard.parent.mkdir(parents=True)
    shard.write_text(json.dumps({
        "schema_version": 1, "event_id": "agent-written", "seq": 1,
        "ts": "2026-09-19T14:03:22.441Z", "session_id": SESSION,
        "run_id": RUN_ID, "event": "run_error", "outcome": "error",
    }) + "\n", encoding="utf-8")

    run_hook(SUBAGENT_STOP, {"session_id": SESSION, "hook_event_name": "SubagentStop"},
             wall=wall)
    events = read_events(wall)
    assert len(events) == 1
    assert not any(e["run_id"].startswith("run_unknown_") for e in events)
    assert "resolution=open_runs_all_closed" not in hooks_log(wall)  # skipped, not written
    assert "already_terminal" in hooks_log(wall)


def test_unresolvable_run_is_marked_not_guessed(tmp_path: Path):
    wall = tmp_path / ".wall"
    wall.mkdir()
    run_hook(SUBAGENT_STOP, {"session_id": SESSION, "hook_event_name": "SubagentStop"},
             wall=wall)
    ev = read_events(wall)[0]
    assert ev["hook"]["resolution"] == "unresolved"
    assert ev["run_id"].startswith("run_unknown_")
    assert ev["agent_key"] is None  # honest absence, never a fabricated identity


def test_ambiguous_open_runs_are_marked_inferred(tmp_path: Path):
    wall = tmp_path / ".wall"
    (wall / "registry").mkdir(parents=True)
    (wall / "registry" / "open_runs.json").write_text(json.dumps({"runs": [
        {"run_id": "run_b", "session_id": SESSION, "started": "2026-09-19T15:00:00.000Z"},
        {"run_id": "run_a", "session_id": SESSION, "started": "2026-09-19T14:00:00.000Z"},
    ]}), encoding="utf-8")

    run_hook(SUBAGENT_STOP, {"session_id": SESSION, "hook_event_name": "SubagentStop"},
             wall=wall)
    ev = read_events(wall)[0]
    assert ev["run_id"] == "run_a"  # oldest
    assert ev["hook"]["resolution"] == "open_runs_inferred_oldest"


def test_env_run_id_wins_over_inference(wall: Path):
    run_hook(SUBAGENT_STOP, {"session_id": SESSION, "hook_event_name": "SubagentStop"},
             wall=wall, env_extra={"WALL_RUN_ID": "run_from_env"})
    ev = read_events(wall)[0]
    assert ev["run_id"] == "run_from_env"
    assert ev["hook"]["resolution"] == "env"


def test_wall_is_found_by_walking_up_from_cwd(tmp_path: Path):
    repo = tmp_path / "repo"
    (repo / ".wall" / "registry").mkdir(parents=True)
    nested = repo / "backend" / "app"
    nested.mkdir(parents=True)

    proc = run_hook(SUBAGENT_STOP, {"session_id": SESSION, "cwd": str(nested),
                                    "hook_event_name": "SubagentStop"}, cwd=nested)
    assert proc.returncode == 0
    assert len(read_events(repo / ".wall")) == 1


# ----------------------------------------------- never block, never speak

@pytest.mark.parametrize("script", [SUBAGENT_STOP, TOOL_USE], ids=["stop", "tools"])
@pytest.mark.parametrize("payload", [
    "", "   ", "not json at all", "[1, 2, 3]", "null", '{"unclosed": ',
], ids=["empty", "blank", "garbage", "array", "null", "truncated"])
def test_malformed_stdin_never_blocks(script: Path, payload: str, wall: Path):
    proc = run_hook(script, payload, wall=wall)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == ""


@pytest.mark.parametrize("script", [SUBAGENT_STOP, TOOL_USE], ids=["stop", "tools"])
def test_missing_wall_never_blocks(script: Path, tmp_path: Path):
    empty = tmp_path / "nowall"
    empty.mkdir()
    proc = run_hook(script, {"session_id": SESSION, "cwd": str(empty),
                             "hook_event_name": "PreToolUse", "tool_name": "Read"},
                    cwd=empty)
    assert proc.returncode == 0
    assert proc.stdout == ""


@pytest.mark.parametrize("script", [SUBAGENT_STOP, TOOL_USE], ids=["stop", "tools"])
def test_stdout_stays_empty_on_the_happy_path(script: Path, wall: Path):
    """A PreToolUse hook that prints a decision object can deny the tool call."""
    proc = run_hook(script, {"session_id": SESSION, "hook_event_name": "PreToolUse",
                             "tool_name": "Bash", "tool_input": {"command": "ls"}},
                    wall=wall)
    assert proc.returncode == 0
    assert proc.stdout == ""


@pytest.mark.parametrize("script,name", [(SUBAGENT_STOP, "subagent_stop"),
                                         (TOOL_USE, "tool_use")])
def test_every_hook_logs_its_own_exit(script: Path, name: str, wall: Path):
    run_hook(script, {"session_id": SESSION, "hook_event_name": "PreToolUse",
                      "tool_name": "Read", "tool_input": {"file_path": "x"}},
             wall=wall)
    log = hooks_log(wall)
    assert name in log
    assert "exit=0" in log


# --------------------------------------------------------- tool_use: trace

def test_pre_tool_use_writes_a_record(wall: Path):
    proc = run_hook(TOOL_USE, {"session_id": SESSION, "hook_event_name": "PreToolUse",
                               "tool_name": "Bash",
                               "tool_input": {"command": "pytest -q"}}, wall=wall)
    assert proc.returncode == 0
    records = read_tools(wall)
    assert len(records) == 1
    rec = records[0]
    assert rec["phase"] == "pre"
    assert rec["tool_name"] == "Bash"
    assert rec["run_id"] == RUN_ID
    assert rec["args_truncated"] is False
    assert "pytest -q" in rec["args"]
    assert rec["duration_ms"] is None


def test_post_tool_use_records_duration_and_exit_code(wall: Path):
    run_hook(TOOL_USE, {"session_id": SESSION, "hook_event_name": "PreToolUse",
                        "tool_name": "Bash", "tool_input": {"command": "ls"}}, wall=wall)
    run_hook(TOOL_USE, {"session_id": SESSION, "hook_event_name": "PostToolUse",
                        "tool_name": "Bash", "tool_input": {"command": "ls"},
                        "tool_response": {"exit_code": 2}}, wall=wall)
    records = read_tools(wall)
    assert [r["phase"] for r in records] == ["pre", "post"]
    assert records[1]["exit_code"] == 2
    assert isinstance(records[1]["duration_ms"], int)
    assert records[1]["duration_ms"] >= 0


def test_error_response_without_exit_code_is_recorded_as_failure(wall: Path):
    run_hook(TOOL_USE, {"session_id": SESSION, "hook_event_name": "PostToolUse",
                        "tool_name": "Read", "tool_input": {"file_path": "/x"},
                        "tool_response": {"is_error": True}}, wall=wall)
    assert read_tools(wall)[0]["exit_code"] == 1


def test_unknown_hook_event_is_ignored_not_guessed(wall: Path):
    proc = run_hook(TOOL_USE, {"session_id": SESSION, "hook_event_name": "SessionStart"},
                    wall=wall)
    assert proc.returncode == 0
    assert read_tools(wall) == []
    assert "unknown_event" in hooks_log(wall)


# ------------------------------------------------------- tool_use: scrubbing

SECRETS = {
    "bearer": "abcdef1234567890XYZ",
    "api_key": "supersecretvalue123",
    "anthropic": "sk-ant-api03-AAAABBBBCCCCDDDD",
    "github": "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ012345",
    "aws": "AKIAIOSFODNN7EXAMPLE",
}


def test_secrets_are_scrubbed_before_they_are_written(wall: Path):
    run_hook(TOOL_USE, {
        "session_id": SESSION, "hook_event_name": "PreToolUse", "tool_name": "Bash",
        "tool_input": {
            "command": "curl -H 'Authorization: Bearer %s' https://api.example" % SECRETS["bearer"],
            "api_key": SECRETS["api_key"],
            "env": {"ANTHROPIC_API_KEY": SECRETS["anthropic"],
                    "GH_TOKEN": SECRETS["github"],
                    "AWS_ACCESS_KEY_ID": SECRETS["aws"]},
        }}, wall=wall)

    args = read_tools(wall)[0]["args"]
    for label, secret in SECRETS.items():
        assert secret not in args, label
    assert "[scrubbed]" in args
    # Non-secret context survives -- a scrubber that eats everything is useless.
    assert "curl" in args and "api.example" in args


def test_private_key_block_is_scrubbed(wall: Path):
    body = ("-----BEGIN RSA PRIVATE KEY-----\n"
            "MIIEowIBAAKCAQEAxxxxSECRETKEYMATERIALxxxx\n"
            "-----END RSA PRIVATE KEY-----")
    run_hook(TOOL_USE, {"session_id": SESSION, "hook_event_name": "PreToolUse",
                        "tool_name": "Write",
                        "tool_input": {"content": body}}, wall=wall)
    args = read_tools(wall)[0]["args"]
    assert "SECRETKEYMATERIAL" not in args
    assert "[scrubbed]" in args


def test_artifact_is_capped_at_256kb(wall: Path):
    run_hook(TOOL_USE, {"session_id": SESSION, "hook_event_name": "PreToolUse",
                        "tool_name": "Write",
                        "tool_input": {"content": "A" * (400 * 1024)}}, wall=wall)
    rec = read_tools(wall)[0]
    assert rec["args_truncated"] is True
    assert rec["args"].endswith("[truncated at 256KB]")
    assert len(rec["args"].encode("utf-8")) <= 256 * 1024 + 64
