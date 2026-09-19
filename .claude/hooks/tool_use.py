#!/usr/bin/env python3
"""PreToolUse / PostToolUse hook -- writes .wall/runs/<run_id>/tools.jsonl.

Every tool call, with scrubbed arguments, exit code and duration, captured with
no agent cooperation required (LOGGING_AND_AUDIT, "Hooks own the mandatory
records"). One script serves both events; the phase comes from the payload's
`hook_event_name`.

Contract:
  - stdlib only, no network.
  - one `os.write` per record, O_APPEND (EVENT_SCHEMA section 6 applies to every
    append-only stream in the system, not only the ledger).
  - arguments pass through the scrubber before they are written, and any single
    artifact is capped at 256 KB with a truncation marker.
  - NEVER blocks the session. Every failure path logs and exits 0, and nothing
    is written to stdout -- a PreToolUse hook that prints a decision object can
    deny a tool call, and this hook only records.

Trace files are gitignored (`.wall/runs/`), so a scrubber miss stays local. The
scrubber is a defence in depth, not a guarantee.
"""

import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HOOK_NAME = "tool_use"
MAX_ARTIFACT_BYTES = 256 * 1024
TRUNCATION_MARKER = "...[truncated at 256KB]"
SCRUBBED = "[scrubbed]"

# Ordered: the specific forms run before the generic key=value sweep.
SCRUB_PATTERNS = [
    (re.compile(r"-----BEGIN[A-Z ]*PRIVATE KEY-----.*?-----END[A-Z ]*PRIVATE KEY-----",
                re.DOTALL), SCRUBBED),
    (re.compile(r"(?i)(authorization\"?\s*[:=]\s*\"?(?:bearer\s+|basic\s+)?)"
                r"([A-Za-z0-9._~+/=-]{6,})"), r"\1" + SCRUBBED),
    (re.compile(r"sk-ant-[A-Za-z0-9._-]{8,}"), SCRUBBED),
    (re.compile(r"\bsk-[A-Za-z0-9]{16,}"), SCRUBBED),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{16,}"), SCRUBBED),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{8,}"), SCRUBBED),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), SCRUBBED),
    (re.compile(r"(?i)(\b(?:api[_-]?key|apikey|secret|client[_-]?secret|"
                r"access[_-]?token|auth[_-]?token|token|password|passwd|pwd|"
                r"private[_-]?key)\b\"?\s*[:=]\s*\"?)"
                r"([^\"'\s,}\]]{4,})"), r"\1" + SCRUBBED),
]


def now_iso():
    return (datetime.now(timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"))


def read_payload():
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


def scrub(text):
    """Apply every pattern. Arguments carry environment values and file bodies."""
    for pattern, replacement in SCRUB_PATTERNS:
        try:
            text = pattern.sub(replacement, text)
        except re.error:
            continue
    return text


def serialize_args(value):
    """Scrubbed JSON text for the tool arguments, capped at 256 KB."""
    try:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    except (TypeError, ValueError):
        text = str(value)
    text = scrub(text)
    encoded = text.encode("utf-8", "replace")
    if len(encoded) <= MAX_ARTIFACT_BYTES:
        return text, False
    head = encoded[:MAX_ARTIFACT_BYTES].decode("utf-8", "ignore")
    return head + TRUNCATION_MARKER, True


def load_open_runs(wall):
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


def resolve_run(wall, payload, session_id):
    for key in ("run_id", "agent_run_id", "subagent_run_id"):
        if payload.get(key):
            return str(payload[key])
    if os.environ.get("WALL_RUN_ID"):
        return os.environ["WALL_RUN_ID"]
    candidates = []
    for run_id, rec in load_open_runs(wall).items():
        if rec.get("session_id") and session_id and rec["session_id"] != session_id:
            continue
        candidates.append((rec.get("started") or rec.get("ts") or "", run_id))
    if candidates:
        candidates.sort()
        return candidates[0][1]
    return "run_unknown_%s" % (session_id or "nosession")


def phase_of(payload):
    name = str(payload.get("hook_event_name") or
               os.environ.get("CLAUDE_HOOK_EVENT") or "").lower()
    if "pretooluse" in name:
        return "pre"
    if "posttooluse" in name:
        return "post"
    return None


def exit_code_of(payload):
    """Best-effort: the harness names this field differently by tool."""
    response = payload.get("tool_response")
    if isinstance(response, dict):
        for key in ("exit_code", "exitCode", "returncode", "status_code"):
            if isinstance(response.get(key), int):
                return response[key]
        if response.get("is_error") is True or response.get("error"):
            return 1
        if response.get("success") is True:
            return 0
    if payload.get("is_error") or payload.get("error"):
        return 1
    return None


def pending_path(run_dir):
    return run_dir / ".tool-pending.json"


def push_pending(run_dir, tool_name):
    path = pending_path(run_dir)
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(state, dict):
            state = {}
    except (OSError, ValueError):
        state = {}
    stack = state.get(tool_name)
    state[tool_name] = (stack if isinstance(stack, list) else []) + [time.time()]
    try:
        path.write_text(json.dumps(state), encoding="utf-8")
    except OSError:
        pass


def pop_pending(run_dir, tool_name):
    path = pending_path(run_dir)
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(state, dict):
            return None
    except (OSError, ValueError):
        return None
    stack = state.get(tool_name)
    if not isinstance(stack, list) or not stack:
        return None
    started = stack.pop()
    state[tool_name] = stack
    try:
        path.write_text(json.dumps(state), encoding="utf-8")
    except OSError:
        pass
    try:
        return int((time.time() - float(started)) * 1000)
    except (TypeError, ValueError):
        return None


def append_record(run_dir, record):
    run_dir.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
    fd = os.open(str(run_dir / "tools.jsonl"),
                 os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        os.write(fd, line.encode("utf-8"))
    finally:
        os.close(fd)


def main():
    wall = None
    try:
        payload, parse_state = read_payload()
        wall = find_wall(payload)
        phase = phase_of(payload)
        if phase is None:
            log_exit(wall, 0, "payload=%s ignored unknown_event=%r" % (
                parse_state, payload.get("hook_event_name")))
            return 0

        session_id = str(payload.get("session_id") or
                         os.environ.get("WALL_SESSION_ID") or "s_unknown")
        run_id = resolve_run(wall, payload, session_id)
        run_dir = Path(wall) / "runs" / run_id
        tool_name = str(payload.get("tool_name") or "unknown")

        args_text, truncated = serialize_args(payload.get("tool_input"))

        run_dir.mkdir(parents=True, exist_ok=True)
        if phase == "pre":
            push_pending(run_dir, tool_name)
            duration_ms = None
        else:
            duration_ms = pop_pending(run_dir, tool_name)

        append_record(run_dir, {
            "ts": now_iso(),
            "phase": phase,
            "session_id": session_id,
            "run_id": run_id,
            "tool_name": tool_name,
            "args": args_text,
            "args_truncated": truncated,
            "exit_code": exit_code_of(payload),
            "duration_ms": duration_ms,
        })
        log_exit(wall, 0, "payload=%s run=%s phase=%s tool=%s truncated=%s" % (
            parse_state, run_id, phase, tool_name, truncated))
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
