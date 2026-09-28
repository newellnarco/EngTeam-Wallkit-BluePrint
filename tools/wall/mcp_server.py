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

Run:  python tools/wall/mcp_server.py --repo .
      python tools/wall/mcp_server.py --repo . --http 127.0.0.1:8124
Client configs: docs/MCP_INTEGRATION.md (Claude Code / Cursor / VS Code).
"""

from __future__ import annotations

import argparse
import contextlib
import http.server
import socket
import io
import ipaddress
import json
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
INTERNAL_ERROR = -32603


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


class _RoutedStream:
    """Stand-in for sys.stdout / sys.stderr that routes each THREAD's writes.

    While a thread is capturing a CLI command (``_capture_cli``) its writes
    go to that capture's buffer; every other thread writes straight through
    to the stream this one replaced. Swapping ``sys.stdout`` per call, as
    ``contextlib.redirect_stdout`` does, is process-global: in a host that
    runs the HTTP server on a thread, the host's own log lines would land in
    a ``wall_answer`` transcript (part of the audit record) and vanish from
    the host's output. Installed once, and only when a capture happens.
    """

    def __init__(self, original):
        self._original = original

    def _target(self):
        return getattr(_CAPTURE, "buf", None) or self._original

    def write(self, text):
        target = self._target()
        if target is None:  # pythonw: no console stream at all
            return len(text)
        return target.write(text)

    def flush(self):
        target = self._target()
        if target is not None:
            target.flush()

    def __getattr__(self, name):  # encoding, isatty, fileno, reconfigure ...
        return getattr(self._original, name)


_CAPTURE = threading.local()
_ROUTING_LOCK = threading.Lock()
#: The verb tools capture the CLI, and ``wall_answer`` appends to the
#: s_human shard: two at once must not interleave a ledger write. Only
#: CLI-capturing calls take it — pings, lists, reads and the enqueue's
#: network call never wait behind it.
_CLI_LOCK = threading.Lock()


def _install_routing() -> None:
    with _ROUTING_LOCK:
        if not isinstance(sys.stdout, _RoutedStream):
            sys.stdout = _RoutedStream(sys.stdout)
        if not isinstance(sys.stderr, _RoutedStream):
            sys.stderr = _RoutedStream(sys.stderr)


def _capture_cli(fn, namespace: types.SimpleNamespace) -> tuple[int, str]:
    """Run an existing wall.py command, capturing what it prints.

    This is DEC-0018 clause 2 as a mechanism: the CLI command IS the
    implementation, and the MCP tool is its second presentation. stdout
    and stderr interleave into one transcript because the reader of a
    tool result wants the whole story in order, not two channels. The
    capture is per-thread (``_RoutedStream``), so nothing else the host
    process prints meanwhile can leak into it or out of it."""
    _install_routing()
    buf = io.StringIO()
    with _CLI_LOCK:
        previous = getattr(_CAPTURE, "buf", None)
        _CAPTURE.buf = buf
        try:
            rc = fn(namespace)
        finally:
            _CAPTURE.buf = previous
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
        name = params.get("name") or ""
        arguments = params.get("arguments") or {}
        # Unhashable or non-string names used to raise TypeError at the
        # `name in allowed` test below — out of this function, out of
        # serve(), taking the server down for every attached client.
        if not isinstance(name, str):
            return err(INVALID_PARAMS, "tool name must be a string")
        if not isinstance(arguments, dict):
            return err(INVALID_PARAMS, "arguments must be an object")
        tool = TOOLS.get(name) if name in allowed else None
        if tool is None:
            reason = (f"tool {name!r} is not in the {role!r} role's allowlist"
                      if name in TOOLS else f"unknown tool {name!r}")
            return err(INVALID_PARAMS,
                       f"{reason}; this server serves exactly "
                       f"{sorted(allowed)} for role {role!r} (DEC-0019)")
        try:
            text = tool["fn"](repo, arguments)
            return ok({"content": [{"type": "text", "text": text}],
                       "isError": False})
        except Exception as exc:  # a tool failure is a RESULT, not a crash
            return ok({"content": [{"type": "text",
                                    "text": f"{type(exc).__name__}: {exc}"}],
                       "isError": True})
    if msg_id is None:
        return None  # unknown notification: ignore, per spec
    return err(METHOD_NOT_FOUND, f"method {method!r} not supported")


def _rpc_error(code: int, message: str, msg_id=None) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id,
            "error": {"code": code, "message": message}}


def _dispatch_one(repo: Path, msg, role: str) -> dict | None:
    """One decoded message → its response. The last line of defence: an
    exception anywhere below becomes an INTERNAL_ERROR response (or, for a
    notification, silence) — never a dead server."""
    if not isinstance(msg, dict):
        return _rpc_error(INVALID_REQUEST, "request is not an object")
    if "id" in msg and msg["id"] is None:
        # JSON-RPC: an explicit null id is an invalid request, not a
        # notification -- the method (and a wall_answer's ledger write)
        # must not run.
        return _rpc_error(INVALID_REQUEST, "id must not be null")
    try:
        return handle_request(repo, msg, role=role)
    except Exception as exc:
        msg_id = msg.get("id")
        if msg_id is None:
            return None
        return _rpc_error(INTERNAL_ERROR, f"internal error: {type(exc).__name__}: {exc}",
                          msg_id)


#: What ``handle_payload`` found, so each transport can say it its own way.
PAYLOAD_OK = "ok"
PAYLOAD_PARSE_ERROR = "parse_error"
PAYLOAD_EMPTY_BATCH = "empty_batch"


def handle_payload(repo: Path, raw: str | bytes, role: str, *,
                   allow_batch: bool) -> tuple[str, object | None]:
    """Decode ONE transport payload and dispatch it: the single path both
    transports share (DEC-0036), so their error envelopes cannot drift.

    Returns ``(kind, response)``; ``response`` is None when nothing is to be
    sent (a notification, or a batch of only notifications). Stdio passes
    ``allow_batch=False`` and a JSON array is then an invalid request, as it
    always was there; HTTP accepts a batch.
    """
    try:
        msg = json.loads(raw)
    except (ValueError, RecursionError) as exc:  # bad JSON, bad UTF-8, absurd nesting
        return PAYLOAD_PARSE_ERROR, _rpc_error(PARSE_ERROR, f"parse error: {exc}")
    if isinstance(msg, list) and allow_batch:
        if not msg:
            return PAYLOAD_EMPTY_BATCH, _rpc_error(INVALID_REQUEST, "empty batch")
        responses = [r for r in (_dispatch_one(repo, m, role) for m in msg) if r is not None]
        return PAYLOAD_OK, (responses or None)
    return PAYLOAD_OK, _dispatch_one(repo, msg, role)


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
        _, response = handle_payload(repo, line, role, allow_batch=False)
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

#: Seconds a connection may sit idle mid-request before its handler thread
#: gives up — a client that declares a Content-Length and never sends it must
#: not park a thread forever.
HTTP_SOCKET_TIMEOUT_S = 30


def is_loopback_host(host: str) -> bool:
    """True for ``localhost`` and any loopback IP literal (v4 or v6)."""
    host = host.strip().strip("[]").lower()
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def origin_allowed(origin: str | None, allow: tuple[str, ...] = ()) -> bool:
    """Only non-browser clients by default (DEC-0036 clause 4).

    Every browser request carries an ``Origin``; MCP clients that are not
    browsers (Claude Code, Claude Desktop, VS Code's and Cursor's extension
    hosts, agent harnesses) send none. Admitting "any loopback origin" would
    let any page served from localhost — a dev server, a notebook — take the
    engineer seat, which stdio never allowed. So a request with an Origin is
    refused unless that exact origin was allowed by the operator.
    """
    if not origin:
        return True
    return origin in allow


def host_header_allowed(host_header: str | None) -> bool:
    """DNS-rebinding defence in depth: the Host a client aimed at must itself
    be loopback. A rebinding page resolves ``evil.example`` to 127.0.0.1 but
    still sends ``Host: evil.example``."""
    if not host_header:
        return False
    value = host_header.strip()
    if value.startswith("["):
        host = value[1:].partition("]")[0]
    else:
        host = value.rsplit(":", 1)[0] if value.count(":") == 1 else value
    return is_loopback_host(host)


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
    kind, response = handle_payload(repo, body, role, allow_batch=True)
    if kind != PAYLOAD_OK:
        return 400, json.dumps(response).encode()
    if response is None:
        return 202, None
    return 200, json.dumps(response).encode()


def address_family_for(host: str) -> int:
    """AF_INET6 for an IPv6 literal (``::1``), AF_INET otherwise. The stock
    ThreadingHTTPServer is IPv4-only, so ``::1`` used to pass the loopback
    guard and then fail to bind at all."""
    return socket.AF_INET6 if ":" in host.strip("[]") else socket.AF_INET


def make_http_server(repo: Path, host: str = "127.0.0.1",
                     port: int = DEFAULT_HTTP_PORT, *,
                     allow_origins: tuple[str, ...] = ()) -> http.server.ThreadingHTTPServer:
    """A ready-to-run loopback MCP server; the caller runs ``serve_forever``.

    Split from ``serve_http`` so a host process that is already resident
    (a service, a supervisor) can run it on a thread of its own instead of
    starting another interpreter — which is the point of DEC-0036.
    Refuses any non-loopback bind: the exposure boundary is structural.
    IPv6 loopback (``::1``, with or without brackets) binds as IPv6.
    """
    host = host.strip()
    bare = host.strip("[]")
    if not is_loopback_host(bare):
        raise ValueError(
            f"refusing to bind {host!r}: the wall MCP server is loopback-only "
            "(DEC-0036); remote exposure is a separate decision")
    if not 0 <= int(port) <= 65535:
        raise ValueError(f"port {port} is out of range")
    repo = Path(repo).resolve()
    allow = tuple(allow_origins)
    family = address_family_for(bare)

    class Server(http.server.ThreadingHTTPServer):
        address_family = family
        # Non-daemon handler threads: server_close() waits for an in-flight
        # wall_answer to finish its ledger write instead of the interpreter
        # killing it halfway through at exit.
        daemon_threads = False

    class Handler(http.server.BaseHTTPRequestHandler):
        server_version = "wall-mcp/" + SERVER_INFO["version"]
        timeout = HTTP_SOCKET_TIMEOUT_S

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
            if not host_header_allowed(self.headers.get("Host")):
                return self._refused(403, "Host must be a loopback name (DNS-rebinding guard)")
            if not origin_allowed(self.headers.get("Origin"), allow):
                return self._refused(403, "browser origins are refused (DEC-0036)")
            role = role_for_path(self.path)
            if role is None:
                return self._refused(404, f"POST {HTTP_PATH_PREFIX}<role>")
            if "chunked" in (self.headers.get("Transfer-Encoding") or "").lower():
                return self._refused(411, "send a Content-Length; chunked bodies are not read")
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                return self._refused(400, "bad Content-Length")
            if length <= 0:
                return self._refused(400, "empty body")
            if length > HTTP_MAX_BODY:
                return self._refused(413, "body too large")
            try:
                body = self.rfile.read(length)
            except OSError:  # includes the socket timeout: the client stalled
                return None
            status, payload = handle_http_body(repo, body, role)
            self._send(status, payload)

        def do_GET(self):  # noqa: N802
            # No server-initiated stream: this server never pushes. 405 is
            # the transport's way of saying so.
            self._send(405, None, {"Allow": "POST"})

        do_DELETE = do_GET  # noqa: N815 - stateless: no session to end

    return Server((bare, int(port)), Handler)


def serve_http(repo: Path, host: str = "127.0.0.1", port: int = DEFAULT_HTTP_PORT, *,
               allow_origins: tuple[str, ...] = ()) -> int:
    return _run_http(make_http_server(repo, host, port, allow_origins=allow_origins))


def _run_http(server: http.server.ThreadingHTTPServer) -> int:
    bound_host, bound_port = server.server_address[:2]
    print(f"[wall-mcp] serving {HTTP_PATH_PREFIX}<role> on "
          f"http://{bound_host}:{bound_port} (loopback only)", file=sys.stderr, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()  # joins in-flight handlers (daemon_threads=False)
    return 0


def _parse_http_arg(value: str) -> tuple[str, int]:
    """``PORT`` · ``HOST`` · ``HOST:PORT`` · ``[V6]`` · ``[V6]:PORT``.

    A bare IPv6 address is refused rather than guessed at: ``::1`` has no
    unambiguous port boundary, so it must be written ``[::1]`` or
    ``[::1]:8124``.
    """
    value = value.strip()
    if not value:
        raise ValueError("empty --http value")
    if value.startswith("["):
        host, sep, rest = value[1:].partition("]")
        if not sep or not host:
            raise ValueError(f"unterminated IPv6 address in {value!r}")
        if not rest:
            return host, DEFAULT_HTTP_PORT
        if not rest.startswith(":") or not rest[1:].isdigit():
            raise ValueError(f"expected [HOST]:PORT, got {value!r}")
        return host, int(rest[1:])
    if value.count(":") > 1:
        raise ValueError(f"write an IPv6 address in brackets, e.g. [{value}]:{DEFAULT_HTTP_PORT}")
    if value.isdigit():
        return "127.0.0.1", int(value)
    host, sep, port = value.rpartition(":")
    if not sep:
        return value, DEFAULT_HTTP_PORT
    if not port.isdigit():
        raise ValueError(f"port must be a number, got {port!r}")
    return host or "127.0.0.1", int(port)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="wall-mcp", description=__doc__.split("\n")[0])
    p.add_argument("--repo", default=".", help="repo root containing .wall/")
    p.add_argument("--role", choices=sorted(ROLE_TOOLS), default=None,
                   help="whose seat this server is: engineer (all six tools) "
                        "or agent (reads only — never the human verbs); stdio only, "
                        "default engineer")
    p.add_argument("--http", metavar="[HOST:]PORT", default=None,
                   help="serve MCP Streamable HTTP on a LOOPBACK address instead "
                        f"of stdio (DEC-0036); roles by path, {HTTP_PATH_PREFIX}<role>")
    p.add_argument("--allow-origin", action="append", default=[], metavar="ORIGIN",
                   help="with --http: admit browser requests from this exact origin "
                        "(repeatable). Default: none — only non-browser clients.")
    a = p.parse_args(argv)
    if a.http:
        if a.role is not None:
            p.error("--role does not apply to --http: the role is the URL path "
                    f"({HTTP_PATH_PREFIX}engineer or {HTTP_PATH_PREFIX}agent)")
        try:
            host, port = _parse_http_arg(a.http)
            server = make_http_server(Path(a.repo).resolve(), host, port,
                                      allow_origins=tuple(a.allow_origin))
        except (ValueError, OSError) as exc:
            p.error(f"--http {a.http}: {exc}")
        return _run_http(server)
    if a.allow_origin:
        p.error("--allow-origin only applies to --http")
    return serve(Path(a.repo).resolve(), role=a.role or "engineer")


if __name__ == "__main__":
    sys.exit(main())
