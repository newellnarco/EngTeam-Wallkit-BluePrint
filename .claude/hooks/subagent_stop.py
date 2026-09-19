#!/usr/bin/env python3
"""SubagentStop hook -- writes the terminal ledger event, always.

An agent that forgets to log is a bug you cannot prompt away. This hook fires on
subagent termination and writes the `run_end` / `run_error` record from the hook
payload, whether or not the agent wrote one itself (LOGGING_AND_AUDIT, "Hooks own
the mandatory records").

Contract:
  - stdlib only, no imports outside the standard library, no network.
  - one `os.write` per record, O_APPEND, so concurrent lines never interleave
    (EVENT_SCHEMA section 6).
  - idempotent: if the agent already wrote a terminal event for this run, this
    hook writes nothing.
  - NEVER blocks the session. Every failure path logs and exits 0.
  - writes nothing to stdout. A PreToolUse-style JSON decision on stdout could
    change harness behaviour; this hook only records.

Deliberately self-contained rather than importing a shared helper: a hook that
cannot import is a hook that does not fire, and the duplication is 60 lines.

Run identity, in precedence order:
  1. `run_id` in the hook payload, if the harness supplies one.
  2. `WALL_RUN_ID` in the environment.
  3. `.wall/registry/open_runs.json` -- the runs the Maestro registered at
     dispatch, filtered to this session and to runs with no terminal event yet.
     Exactly one match is used directly; several means the oldest is used and the
     record is marked `inferred_oldest` so the ambiguity is visible rather than
     assumed away.
  4. None of the above -- a synthetic id, marked `unresolved`. The integrity
     panel will show the real run as an orphan, which is the honest outcome.
"""

import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

HOOK_NAME = "subagent_stop"
SCHEMA_VERSION = 1

TERMINAL_EVENTS = ("run_end", "run_error")
ERROR_OUTCOMES = ("error", "timeout")
VALID_OUTCOMES = ("pass", "partial", "blocked", "timeout", "error", "human_required")
ZERO_TOKENS = {"in": 0, "out": 0, "cache_read": 0, "cache_write": 0}


def now_iso():
    return (datetime.now(timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"))


def read_payload():
    """Read the hook payload. Anything unreadable becomes an empty dict."""
    try:
        raw = sys.stdin.read()
    except (OSError, ValueError):
        return {}, "stdin_unreadable"
    if not raw or not raw.strip():
        return {}, "empty_stdin"
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return {}, "bad_json"
    return (data, "ok") if isinstance(data, dict) else ({}, "not_an_object")


def find_wall(payload):
    """Locate the .wall root. Env wins; then walk up from the payload cwd."""
    env = os.environ.get("WALL_ROOT")
    if env:
        return Path(env)
    start = payload.get("cwd") or os.getcwd()
    try:
        here = Path(start).resolve()
    except (OSError, ValueError):
        here = Path(os.getcwd())
    for candidate in [here, *here.parents]:
        if (candidate / ".wall").is_dir():
            return candidate / ".wall"
    return here / ".wall"


def log_exit(wall, code, detail):
    """Every hook writes its own exit. A silently failing hook is invisible."""
    try:
        logs = Path(wall) / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        line = "%s %s exit=%d %s\n" % (now_iso(), HOOK_NAME, code, detail)
        fd = os.open(str(logs / "hooks.log"),
                     os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
        try:
            os.write(fd, line.encode("utf-8", "replace"))
        finally:
            os.close(fd)
    except (OSError, ValueError):
        pass


def session_shards(wall, session_id):
    events = Path(wall) / "events"
    if not events.is_dir():
        return []
    try:
        return sorted(events.rglob("%s.jsonl" % session_id))
    except OSError:
        return []


def next_seq(wall, session_id):
    """Monotonic per session: one past the records already written for it.

    Counting is O(shard) and is not atomic across concurrent writers, so a race
    can duplicate a number. That is deliberate: a duplicate is visible in the
    ledger, while a gap reads as a lost write, and a lost write is the failure
    the `seq` field exists to surface.
    """
    total = 0
    for shard in session_shards(wall, session_id):
        try:
            with shard.open("rb") as fh:
                for line in fh:
                    if line.strip():
                        total += 1
        except OSError:
            continue
    return total + 1


def terminal_run_ids(wall, session_id):
    seen = set()
    for shard in session_shards(wall, session_id):
        try:
            with shard.open("r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except ValueError:
                        continue
                    if isinstance(rec, dict) and rec.get("event") in TERMINAL_EVENTS:
                        if rec.get("run_id"):
                            seen.add(rec["run_id"])
        except OSError:
            continue
    return seen


def load_open_runs(wall):
    """Accept either {run_id: record} or {"runs": [record, ...]}."""
    path = Path(wall) / "registry" / "open_runs.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if isinstance(data, dict) and isinstance(data.get("runs"), list):
        data = {r.get("run_id"): r for r in data["runs"] if isinstance(r, dict)}
    if not isinstance(data, dict):
        return {}
    return {k: v for k, v in data.items() if isinstance(v, dict) and k}


def resolve_run(wall, payload, session_id, closed):
    for key in ("run_id", "agent_run_id", "subagent_run_id"):
        if payload.get(key):
            return str(payload[key]), "payload"
    if os.environ.get("WALL_RUN_ID"):
        return os.environ["WALL_RUN_ID"], "env"

    candidates, already_closed = [], []
    for run_id, rec in load_open_runs(wall).items():
        if rec.get("session_id") and session_id and rec["session_id"] != session_id:
            continue
        stamped = (rec.get("started") or rec.get("ts") or "", run_id)
        (already_closed if run_id in closed else candidates).append(stamped)
    if len(candidates) == 1:
        return candidates[0][1], "open_runs_unique"
    if candidates:
        candidates.sort()
        return candidates[0][1], "open_runs_inferred_oldest"
    if already_closed:
        # Every run this session registered already has a terminal event, so this
        # stop belongs to one of them and the agent logged it first. Return the
        # most recent so the caller's dedupe fires. Writing a synthetic id here
        # would manufacture a second, unattributed terminal record for work that
        # is already accounted for.
        already_closed.sort()
        return already_closed[-1][1], "open_runs_all_closed"

    return "run_unknown_%s_%d" % (session_id or "nosession", int(time.time() * 1000)), "unresolved"


def load_agent_outcome(wall, run_id):
    """The agent writes the semantic half here; the hook writes the facts."""
    path = Path(wall) / "runs" / str(run_id) / "outcome.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def build_record(payload, wall, session_id, run_id, resolution):
    registered = load_open_runs(wall).get(run_id, {})
    stated = load_agent_outcome(wall, run_id)

    outcome = stated.get("outcome") or payload.get("outcome")
    if outcome not in VALID_OUTCOMES:
        outcome = None
    failed = bool(payload.get("error") or payload.get("is_error"))
    if outcome is None:
        outcome = "error" if failed else "pass"

    error_class = stated.get("error_class")
    if error_class is None and outcome in ERROR_OUTCOMES:
        error_class = "tool_error" if failed else "model_error"

    tokens = stated.get("tokens")
    if not isinstance(tokens, dict):
        tokens = dict(ZERO_TOKENS)
    else:
        tokens = {k: tokens.get(k, 0) or 0 for k in ZERO_TOKENS}

    record = {
        "schema_version": SCHEMA_VERSION,
        "event_id": str(uuid.uuid4()),
        "seq": next_seq(wall, session_id),
        "ts": now_iso(),
        "session_id": session_id,
        "trace_id": stated.get("trace_id") or registered.get("trace_id"),
        "run_id": run_id,
        "parent_run_id": registered.get("parent_run_id"),
        "agent_key": stated.get("agent_key") or registered.get("agent_key"),
        "agent_name": stated.get("agent_name") or registered.get("agent_name"),
        "role": stated.get("role") or registered.get("role"),
        "model_requested": registered.get("model_requested"),
        "model_used": stated.get("model_used") or registered.get("model_used"),
        "item_id": stated.get("item_id") or registered.get("item_id"),
        "event": "run_error" if outcome in ERROR_OUTCOMES else "run_end",
        "outcome": outcome,
        "error_class": error_class,
        "tokens": tokens,
        "cost_usd": stated.get("cost_usd", 0) or 0,
        "gh_minutes": stated.get("gh_minutes"),
        "duration_s": stated.get("duration_s"),
        "decisions_in_context": stated.get("decisions_in_context") or
                                registered.get("decisions_in_context") or [],
        "hook": {"source": "SubagentStop", "resolution": resolution,
                 "agent_reported": bool(stated)},
    }
    return record


def append_event(wall, session_id, record):
    day = record["ts"][:10]
    shard = Path(wall) / "events" / day / ("%s.jsonl" % session_id)
    shard.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
    fd = os.open(str(shard), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        os.write(fd, line.encode("utf-8"))
    finally:
        os.close(fd)
    return shard


def main():
    wall = None
    try:
        payload, parse_state = read_payload()
        wall = find_wall(payload)
        session_id = str(payload.get("session_id") or
                         os.environ.get("WALL_SESSION_ID") or "s_unknown")

        closed = terminal_run_ids(wall, session_id)
        run_id, resolution = resolve_run(wall, payload, session_id, closed)

        if run_id in closed:
            log_exit(wall, 0, "payload=%s run=%s already_terminal" % (parse_state, run_id))
            return 0

        record = build_record(payload, wall, session_id, run_id, resolution)
        append_event(wall, session_id, record)
        log_exit(wall, 0, "payload=%s run=%s resolution=%s event=%s outcome=%s" % (
            parse_state, run_id, resolution, record["event"], record["outcome"]))
        return 0
    except BaseException as exc:  # a hook must never take the session down
        try:
            log_exit(wall or Path(os.getcwd()) / ".wall", 0,
                     "failed %s: %s" % (type(exc).__name__, exc))
        except BaseException:
            pass
        return 0


if __name__ == "__main__":
    sys.exit(main())
