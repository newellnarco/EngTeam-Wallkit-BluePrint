#!/usr/bin/env python3
"""wall-mcp — the wall as an MCP server, for every editor and agent.

Patron direction (2026-09-20): the team, the wall, the project and its
blueprints must be operable from VS Code, Cursor, Claude Code and other
MCP interfaces — the engineer answers questions, provides information
and new instructions, and stays up to date through ONE integration
point. That point is this file: a Model Context Protocol server over
stdio (newline-delimited JSON-RPC 2.0), which every MCP client speaks
natively. One server, N interfaces, zero per-editor code.

Ruled by three standing decisions:

* **DEC-0017 (portability)** — stdlib only. The protocol subset MCP
  needs over stdio (initialize / tools/list / tools/call / ping) is
  small enough to carry without an SDK, and a pip install here would
  break the fresh-clone promise everywhere.
* **DEC-0018 (reporting economy)** — every read tool is a DERIVED
  presentation: `wall_status` serves the same `summary.build_summary`
  the `wall summary` CLI prints; `wall_item` reads the same derived
  snapshot the wall page renders; `wall_answer` and `wall_trace`
  CAPTURE the existing CLI commands rather than reimplementing them.
  One implementation per fact, presented here a second time.
* **DEC-0019 (this server's own charter)** — the tool set below is an
  exact allowlist; growing it is a decision, not an edit. Transport is
  stdio/local only: a remote (HTTP) exposure for claude.ai would cross
  the localhost-only line and needs its own DEC.

Run:  python tools/wall/mcp_server.py --repo .
Client configs: docs/MCP_INTEGRATION.md (Claude Code / Cursor / VS Code).
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
import types
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

import contracts  # noqa: E402
import summary as summary_mod  # noqa: E402

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "wall-mcp", "version": "1.0"}

# The JSON-RPC error codes this file uses; the spec's names, spelled out.
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602


def _load_snapshot(repo: Path) -> dict | None:
    path = repo / ".wall" / "derived" / "wall.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _load_heartbeat(repo: Path) -> dict | None:
    path = repo / ".wall" / "derived" / "heartbeat.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _load_config(repo: Path) -> dict:
    path = repo / ".wall" / "config" / "wall.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _capture_cli(fn, namespace: types.SimpleNamespace) -> tuple[int, str]:
    """Run an existing wall.py command, capturing what it prints.

    This is DEC-0018 clause 2 as a mechanism: the CLI command IS the
    implementation, and the MCP tool is its second presentation. stdout
    and stderr interleave into one transcript because the reader of a
    tool result wants the whole story in order, not two channels."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        rc = fn(namespace)
    return rc, buf.getvalue()


# --------------------------------------------------------------- the tools

def tool_wall_status(repo: Path, args: dict) -> str:
    snap = _load_snapshot(repo)
    if snap is None:
        return ("no snapshot at .wall/derived/wall.json — run "
                "`wall run-once` in the repo first")
    s = summary_mod.build_summary(snap, _load_heartbeat(repo))
    if args.get("json"):
        from dataclasses import asdict
        return json.dumps(asdict(s), indent=1, sort_keys=True)
    return summary_mod.format_summary(s)


def tool_wall_item(repo: Path, args: dict) -> str:
    key = str(args.get("key") or "").strip()
    if not key:
        raise ValueError("key is required (an item_id, e.g. ST-106)")
    snap = _load_snapshot(repo)
    if snap is None:
        return "no snapshot — run `wall run-once` first"
    for arc in (snap.get("board") or {}).get("arcs") or []:
        for it in arc.get("items") or []:
            if it.get("item_id") == key:
                return json.dumps(it, indent=1, sort_keys=True)
    return f"no item {key!r} on the wall"


def tool_wall_waiting(repo: Path, args: dict) -> str:
    snap = _load_snapshot(repo)
    if snap is None:
        return "no snapshot — run `wall run-once` first"
    s = summary_mod.build_summary(snap, None)
    lines = [f"waiting on you ({len(s.waiting_on_you)}):"]
    lines += ["  " + w for w in s.waiting_on_you] or ["  (none)"]
    lines.append(f"open questions: {s.questions_open}")
    return "\n".join(lines)


def tool_wall_trace(repo: Path, args: dict) -> str:
    target = str(args.get("target") or "").strip()
    if not target:
        raise ValueError("target is required (an item_id or trace_id)")
    import wall as wall_mod
    rc, out = _capture_cli(
        wall_mod.cmd_trace, types.SimpleNamespace(repo=str(repo), target=target))
    return out if out.strip() else f"trace exited {rc} with no output"


def tool_wall_answer(repo: Path, args: dict) -> str:
    target = str(args.get("target") or "").strip()
    text = str(args.get("text") or "").strip()
    if not target or not text:
        raise ValueError("target (ask_id/question_id) and text are both required")
    import wall as wall_mod
    rc, out = _capture_cli(wall_mod.cmd_answer, types.SimpleNamespace(
        repo=str(repo), target=target, text=text,
        decision=bool(args.get("decision")), session="s_human"))
    status = "answered" if rc == 0 else f"refused (exit {rc})"
    return f"{status}\n{out}".strip()


def tool_wall_enqueue(repo: Path, args: dict) -> str:
    """The one write beyond the ledger: the DEC-0004 host-queue add,
    built from the typed contract and sent through the host's own
    allowlisted endpoint (the same one the wall page's EXECUTE uses)."""
    config = _load_config(repo)
    qa = config.get("queue_api") or {}
    origin = (qa.get("origin") or "").rstrip("/")
    add_path = qa.get("add") or ""
    if not origin or not add_path:
        return ("queue_api.origin and queue_api.add are not configured in "
                ".wall/config/wall.json — the host queue is not reachable "
                "from here, honestly")
    directive = contracts.Directive(str(args.get("directive")))
    payload = contracts.EnqueuePayload(
        directive=directive,
        title=str(args.get("title") or ""),
        target_key=args.get("target_key"),
        target_arch=args.get("target_arch"),
    )
    body = json.dumps(payload.to_dict()).encode()
    request = urllib.request.Request(
        f"{origin}{add_path}", data=body, method="POST",
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=10) as resp:
        answer = resp.read(65536).decode("utf-8", errors="replace")
    return f"enqueued via {origin}{add_path}: {answer}"


#: DEC-0019: the exact tool allowlist. Schemas lean on contracts.py —
#: the enum below IS Directive's values, never a re-typed copy.
TOOLS: dict[str, dict] = {
    "wall_status": {
        "fn": tool_wall_status,
        "description": ("The wall's one-screen summary — the same "
                        "summary.build_summary the `wall summary` CLI prints "
                        "(board counts, in-flight triage, waiting-on-you, "
                        "integrity, budget pace)."),
        "inputSchema": {"type": "object", "properties": {
            "json": {"type": "boolean",
                     "description": "machine-readable instead of text"},
        }},
    },
    "wall_item": {
        "fn": tool_wall_item,
        "description": "One board item by item_id, as the wall knows it.",
        "inputSchema": {"type": "object", "properties": {
            "key": {"type": "string", "description": "item_id, e.g. ST-106"},
        }, "required": ["key"]},
    },
    "wall_waiting": {
        "fn": tool_wall_waiting,
        "description": ("What the wall is waiting on the ENGINEER for: the "
                        "human-queue asks and the open-question count."),
        "inputSchema": {"type": "object", "properties": {}},
    },
    "wall_trace": {
        "fn": tool_wall_trace,
        "description": ("Causal timeline for an item or trace id — the "
                        "`wall trace` CLI, captured."),
        "inputSchema": {"type": "object", "properties": {
            "target": {"type": "string",
                       "description": "item_id (ST-106) or trace_id (tr_st106)"},
        }, "required": ["target"]},
    },
    "wall_answer": {
        "fn": tool_wall_answer,
        "description": ("Resolve a human-queue question AS THE ENGINEER — the "
                        "`wall answer` CLI, captured. Refusals (already "
                        "answered, unknown id) come back verbatim."),
        "inputSchema": {"type": "object", "properties": {
            "target": {"type": "string", "description": "ask_id or question_id"},
            "text": {"type": "string", "description": "the answer"},
            "decision": {"type": "boolean",
                         "description": "also write a DEC-NNNN skeleton"},
        }, "required": ["target", "text"]},
    },
    "wall_enqueue": {
        "fn": tool_wall_enqueue,
        "description": ("Enqueue work on the host queue (the DEC-0004 write, "
                        "same endpoint the wall page's EXECUTE uses). Needs "
                        "queue_api.origin + queue_api.add in wall.json."),
        "inputSchema": {"type": "object", "properties": {
            "directive": {"type": "string",
                          "enum": [str(d) for d in contracts.Directive],
                          "description": "; ".join(
                              f"{d}: {doc}" for d, doc in
                              contracts.DIRECTIVE_DOCS.items())},
            "title": {"type": "string"},
            "target_key": {"type": "string"},
            "target_arch": {"type": "string"},
        }, "required": ["directive", "title"]},
    },
}


#: DEC-0019 role gate. The server is the ENGINEER's seat by default —
#: the human-queue answer and the queue write are the Patron's verbs,
#: and an agent attached to the same server must not be able to forge a
#: human ruling (`wall_answer` writes to the s_human shard: an answer
#: from that shard IS the record of the engineer speaking). An agent
#: client is configured with --role agent and gets the reads only; its
#: instructions still come FROM the engineer, through the queue, not
#: from itself through this server.
ROLE_TOOLS: dict[str, tuple[str, ...]] = {
    "engineer": ("wall_status", "wall_item", "wall_waiting",
                 "wall_trace", "wall_answer", "wall_enqueue"),
    "agent": ("wall_status", "wall_item", "wall_waiting", "wall_trace"),
}


# ------------------------------------------------------------ the protocol

def handle_request(repo: Path, msg: dict, role: str = "engineer") -> dict | None:
    """One JSON-RPC message in, one response out (None for notifications)."""
    msg_id = msg.get("id")
    method = msg.get("method")
    params = msg.get("params") or {}

    def ok(result: dict) -> dict:
        return {"jsonrpc": "2.0", "id": msg_id, "result": result}

    def err(code: int, message: str) -> dict:
        return {"jsonrpc": "2.0", "id": msg_id,
                "error": {"code": code, "message": message}}

    if method == "initialize":
        return ok({
            "protocolVersion": params.get("protocolVersion") or PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": SERVER_INFO,
        })
    if method in ("notifications/initialized", "notifications/cancelled"):
        return None  # notifications take no response
    if method == "ping":
        return ok({})
    allowed = ROLE_TOOLS.get(role, ROLE_TOOLS["agent"])
    if method == "tools/list":
        return ok({"tools": [
            {"name": name, "description": t["description"],
             "inputSchema": t["inputSchema"]}
            for name, t in TOOLS.items() if name in allowed]})
    if method == "tools/call":
        name = (params.get("name") or "")
        tool = TOOLS.get(name) if name in allowed else None
        if tool is None:
            reason = (f"tool {name!r} is not in the {role!r} role's allowlist"
                      if name in TOOLS else f"unknown tool {name!r}")
            return err(INVALID_PARAMS,
                       f"{reason}; this server serves exactly "
                       f"{sorted(allowed)} for role {role!r} (DEC-0019)")
        try:
            text = tool["fn"](repo, params.get("arguments") or {})
            return ok({"content": [{"type": "text", "text": text}],
                       "isError": False})
        except Exception as exc:  # a tool failure is a RESULT, not a crash
            return ok({"content": [{"type": "text",
                                    "text": f"{type(exc).__name__}: {exc}"}],
                       "isError": True})
    if msg_id is None:
        return None  # unknown notification: ignore, per spec
    return err(METHOD_NOT_FOUND, f"method {method!r} not supported")


def serve(repo: Path, stdin=None, stdout=None, role: str = "engineer") -> int:
    """Newline-delimited JSON-RPC over stdio until EOF. A malformed line
    answers a parse error and the loop continues — one bad client
    message must not kill the server every editor is attached to."""
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError as exc:
            response = {"jsonrpc": "2.0", "id": None,
                        "error": {"code": PARSE_ERROR,
                                  "message": f"parse error: {exc}"}}
            print(json.dumps(response), file=stdout, flush=True)
            continue
        if not isinstance(msg, dict):
            response = {"jsonrpc": "2.0", "id": None,
                        "error": {"code": INVALID_REQUEST,
                                  "message": "request is not an object"}}
            print(json.dumps(response), file=stdout, flush=True)
            continue
        response = handle_request(repo, msg, role=role)
        if response is not None:
            print(json.dumps(response), file=stdout, flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="wall-mcp", description=__doc__.split("\n")[0])
    p.add_argument("--repo", default=".", help="repo root containing .wall/")
    p.add_argument("--role", choices=sorted(ROLE_TOOLS), default="engineer",
                   help="whose seat this server is: engineer (all six tools) "
                        "or agent (reads only — never the human verbs)")
    a = p.parse_args(argv)
    return serve(Path(a.repo).resolve(), role=a.role)


if __name__ == "__main__":
    sys.exit(main())
