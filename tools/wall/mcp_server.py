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
  exact allowlist; growing it is a decision, not an edit.
* **DEC-0036 (transport, supersedes DEC-0019 clause 3)** — stdio stays
  the default. A second transport, MCP Streamable HTTP, is allowed on
  the LOOPBACK interface only, so one resident process can serve every
  editor on the machine instead of each client session spawning its
  own copies. Remote exposure (claude.ai connectors) is still out.
* **DEC-0037 (hosting)** — ``host.py`` is that resident process, one per
  machine, serving every registered repo through ``make_routed_server``.

Run:  python tools/wall/mcp_server.py --repo .
      python tools/wall/mcp_server.py --repo . --http 127.0.0.1:8124
Client configs: docs/MCP_INTEGRATION.md (Claude Code / Cursor / VS Code).
"""

from __future__ import annotations

import argparse
import contextlib
import http.server
import io
import ipaddress
import json
import socket
import sys
import threading
import types
import urllib.parse
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
        action=args.get("action"),
        path=args.get("path"),
        sha=args.get("sha"),
        reason=args.get("reason"),
        regime=args.get("regime"),
        mode=args.get("mode"),
        item_id=args.get("item_id"),
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
            "action": {"type": "string",
                       "description": ("warden_regime: enable|disable; "
                                       "doc_review: approve|changes|deny")},
            "path": {"type": "string",
                     "description": "doc_review: the document of record"},
            "sha": {"type": "string",
                    "description": "doc_review: the sha the reviewer read"},
            "reason": {"type": "string",
                       "description": ("recorded verbatim; required for "
                                       "resolve_blocked and for doc_review "
                                       "changes/deny")},
            "regime": {"type": "string"},
            "mode": {"type": "string",
                     "description": "resolve_blocked: build|research"},
            "item_id": {"type": "string"},
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

    # JSON-RPC allows array params; this server's methods are all
    # by-name, so a non-object is INVALID_PARAMS for a request and
    # silently ignored for a notification — never an AttributeError
    # escaping serve() and taking down every attached editor.
    if not isinstance(params, dict):
        return None if msg_id is None else err(
            INVALID_PARAMS, "params must be an object")

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
    # MCP clients speak UTF-8; a Windows console stream defaults to the
    # locale codepage (cp1252), which silently mojibakes any non-ASCII in
    # an inbound message — including the engineer's own wall_answer text
    # on its way into the s_human shard, the audit record. Re-encode both
    # ways where the stream allows it (a test's StringIO does not, and
    # needs nothing: it is already text). Output is ensure_ascii JSON, so
    # the stdout half is belt-and-braces, not a live crash path.
    for stream in (stdin, stdout):
        if hasattr(stream, "reconfigure"):
            with contextlib.suppress(Exception):
                stream.reconfigure(encoding="utf-8")
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


# ------------------------------------------------- loopback HTTP (DEC-0036)

#: Where a role is chosen over HTTP: ``/mcp/<role>``. The path, not a
#: header, because it is what every client config can express, and an
#: unknown role degrades to ``agent`` exactly as ``--role`` does.
HTTP_PATH_PREFIX = "/mcp/"
#: A tool call is a few hundred bytes; anything this large is not MCP.
HTTP_MAX_BODY = 1_048_576
DEFAULT_HTTP_PORT = 8124
#: ``GET`` here answers liveness JSON; every other GET is 405 (DEC-0037).
HEALTH_PATH = "/health"

#: One tool call at a time. The verb tools CAPTURE the CLI by swapping
#: sys.stdout (``_capture_cli``), which is process-global: two concurrent
#: calls would interleave each other's transcripts, and ``wall_answer``'s
#: transcript is part of the audit record.
_TOOL_LOCK = threading.Lock()


def is_loopback_host(host: str) -> bool:
    """True for ``localhost`` and any loopback IP literal (v4 or v6)."""
    host = host.strip("[]").lower()
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def origin_allowed(origin: str | None) -> bool:
    """DNS-rebinding guard (the MCP transport spec's MUST): a browser page
    on any other site can POST to 127.0.0.1, and only its Origin header
    gives it away. No Origin means a non-browser client — allowed; an
    Origin must itself be a loopback origin."""
    if not origin:
        return True
    if origin == "null":
        return False
    parsed = urllib.parse.urlsplit(origin)
    return parsed.scheme in ("http", "https") and is_loopback_host(parsed.hostname or "")


def role_for_path(path: str) -> str | None:
    """``/mcp/engineer`` → ``engineer``; unknown role → ``agent``; any
    other path → None (404)."""
    path = urllib.parse.urlsplit(path).path.rstrip("/")
    if not path.startswith(HTTP_PATH_PREFIX):
        return None
    role = path[len(HTTP_PATH_PREFIX):]
    if not role or "/" in role:
        return None
    return role if role in ROLE_TOOLS else "agent"


def handle_http_body(repo: Path, body: bytes, role: str) -> tuple[int, bytes | None]:
    """One POST body in → (HTTP status, JSON body or None).

    Pure of sockets so the whole transport contract is testable without a
    server. A single message or a batch; a notification-only body answers
    202 with no body, per the Streamable HTTP transport.
    """
    try:
        msg = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return 400, json.dumps({"jsonrpc": "2.0", "id": None, "error": {
            "code": PARSE_ERROR, "message": f"parse error: {exc}"}}).encode()
    batch = isinstance(msg, list)
    messages = msg if batch else [msg]
    if batch and not messages:
        return 400, json.dumps({"jsonrpc": "2.0", "id": None, "error": {
            "code": INVALID_REQUEST, "message": "empty batch"}}).encode()
    responses = []
    for one in messages:
        if not isinstance(one, dict):
            responses.append({"jsonrpc": "2.0", "id": None, "error": {
                "code": INVALID_REQUEST, "message": "request is not an object"}})
            continue
        with _TOOL_LOCK:
            response = handle_request(repo, one, role=role)
        if response is not None:
            responses.append(response)
    if not responses:
        return 202, None
    payload = responses if batch else responses[0]
    return 200, json.dumps(payload).encode()


class ExclusiveHTTPServer(http.server.ThreadingHTTPServer):
    """A ThreadingHTTPServer whose bind is EXCLUSIVE on every platform.

    This is the single-instance guard (DEC-0037): a second host binding the
    same port must fail, not share it. ``http.server`` sets SO_REUSEADDR,
    which on POSIX only lets a restart reuse a TIME_WAIT port -- but on
    Windows it lets a second process bind a port another process is already
    listening on, and the two then split the traffic. So on Windows the
    reuse flag is off and SO_EXCLUSIVEADDRUSE is on.
    """

    daemon_threads = True
    allow_reuse_address = not sys.platform.startswith("win")

    def server_bind(self):
        exclusive = getattr(socket, "SO_EXCLUSIVEADDRUSE", None)
        if exclusive is not None:
            self.socket.setsockopt(socket.SOL_SOCKET, exclusive, 1)
        super().server_bind()


def make_routed_server(route, host: str = "127.0.0.1",
                       port: int = DEFAULT_HTTP_PORT,
                       health=None) -> ExclusiveHTTPServer:
    """The loopback MCP transport over any routing: the one Handler both the
    single-repo server and the machine host (``host.py``) run.

    ``route(path)`` answers ``(repo, role)`` for a POST path it serves, or
    None (404). ``health()`` answers the JSON dict ``GET /health`` returns;
    None means the stock ``{"ok": true, ...}``. Refuses any non-loopback
    bind: the exposure boundary is structural (DEC-0036). The bind is
    exclusive, so a second server on the same port raises OSError -- the
    single-instance guard (DEC-0037).
    """
    if not is_loopback_host(host):
        raise ValueError(
            f"refusing to bind {host!r}: the wall MCP server is loopback-only "
            "(DEC-0036); remote exposure is a separate decision")

    class Handler(http.server.BaseHTTPRequestHandler):
        server_version = "wall-mcp/" + SERVER_INFO["version"]

        def log_message(self, fmt, *args):  # quiet: editors poll
            return

        def _send(self, status: int, body: bytes | None = None,
                  extra: dict | None = None) -> None:
            self.send_response(status)
            for key, value in (extra or {}).items():
                self.send_header(key, value)
            if body is not None:
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
            else:
                self.send_header("Content-Length", "0")
            self.end_headers()
            if body is not None:
                self.wfile.write(body)

        def _refused(self, status: int, message: str) -> None:
            self._send(status, json.dumps({"error": message}).encode())

        def do_POST(self):  # noqa: N802 - http.server naming
            if not origin_allowed(self.headers.get("Origin")):
                return self._refused(403, "origin not allowed (loopback only)")
            target = route(self.path)
            if target is None:
                return self._refused(404, f"POST {HTTP_PATH_PREFIX}<role>")
            repo, role = target
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                return self._refused(400, "bad Content-Length")
            if length <= 0:
                return self._refused(400, "empty body")
            if length > HTTP_MAX_BODY:
                return self._refused(413, "body too large")
            status, body = handle_http_body(repo, self.rfile.read(length), role)
            self._send(status, body)

        def do_GET(self):  # noqa: N802
            if urllib.parse.urlsplit(self.path).path.rstrip("/") == HEALTH_PATH:
                # Liveness for a watchdog, an installer or a person: never
                # takes the tool lock, so a long tool call cannot make a
                # live server look dead.
                if not origin_allowed(self.headers.get("Origin")):
                    return self._refused(403, "origin not allowed (loopback only)")
                payload = health() if health is not None else {
                    "ok": True, "service": "wall-mcp"}
                return self._send(200, json.dumps(payload).encode())
            # No server-initiated stream: this server never pushes. 405 is
            # the transport's way of saying so.
            self._send(405, None, {"Allow": "POST"})

        def do_DELETE(self):  # noqa: N802 - stateless: no session to end
            self._send(405, None, {"Allow": "POST"})

    return ExclusiveHTTPServer((host, port), Handler)


def make_http_server(repo: Path, host: str = "127.0.0.1",
                     port: int = DEFAULT_HTTP_PORT) -> ExclusiveHTTPServer:
    """A ready-to-run loopback MCP server for ONE repo; the caller runs
    ``serve_forever``. Roles by path, ``/mcp/<role>``.

    Split from ``serve_http`` so a host process that is already resident
    (a service, a supervisor) can run it on a thread of its own instead of
    starting another interpreter -- which is the point of DEC-0036. The
    machine-wide host that serves every registered repo is ``host.py``
    (DEC-0037).
    """
    repo = Path(repo).resolve()

    def route(path: str):
        role = role_for_path(path)
        return None if role is None else (repo, role)

    return make_routed_server(route, host, port, health=lambda: {
        "ok": True, "service": "wall-mcp", "repo": str(repo)})


def serve_http(repo: Path, host: str = "127.0.0.1", port: int = DEFAULT_HTTP_PORT) -> int:
    server = make_http_server(repo, host, port)
    bound_host, bound_port = server.server_address[:2]
    print(f"[wall-mcp] serving {HTTP_PATH_PREFIX}<role> on "
          f"http://{bound_host}:{bound_port} (loopback only)", file=sys.stderr, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def _parse_http_arg(value: str) -> tuple[str, int]:
    host, sep, port = value.rpartition(":")
    if not sep:
        return "127.0.0.1", int(value)
    return host or "127.0.0.1", int(port)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="wall-mcp", description=__doc__.split("\n")[0])
    p.add_argument("--repo", default=".", help="repo root containing .wall/")
    p.add_argument("--role", choices=sorted(ROLE_TOOLS), default="engineer",
                   help="whose seat this server is: engineer (all six tools) "
                        "or agent (reads only — never the human verbs); stdio only")
    p.add_argument("--http", metavar="[HOST:]PORT", default=None,
                   help="serve MCP Streamable HTTP on a LOOPBACK address instead "
                        f"of stdio (DEC-0036); roles by path, {HTTP_PATH_PREFIX}<role>")
    a = p.parse_args(argv)
    if a.http:
        host, port = _parse_http_arg(a.http)
        return serve_http(Path(a.repo).resolve(), host, port)
    return serve(Path(a.repo).resolve(), role=a.role)


if __name__ == "__main__":
    sys.exit(main())
