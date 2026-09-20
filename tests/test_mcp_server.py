"""wall-mcp — the wall's MCP server, pinned at the wire (DEC-0019).

Most tests drive handle_request in-process for speed; one end-to-end
test spawns the real server and speaks newline-delimited JSON-RPC over
its stdio, doubling as the reference transcript MCP_INTEGRATION.md
points at. The one-implementation rule (DEC-0018) is pinned by
EQUALITY: wall_status's text is byte-identical to what the `wall
summary` CLI prints from the same snapshot.
"""

from __future__ import annotations

import io
import json
import shutil
import subprocess
import sys
import threading
from pathlib import Path

import mcp_server as srv
import summary as summary_mod

KIT = Path(__file__).resolve().parents[1]
SAMPLE = KIT / "sample"


def call(repo: Path, method: str, params: dict | None = None, msg_id=1):
    return srv.handle_request(repo, {
        "jsonrpc": "2.0", "id": msg_id, "method": method,
        "params": params or {}})


def tool(repo: Path, name: str, arguments: dict | None = None):
    resp = call(repo, "tools/call", {"name": name,
                                     "arguments": arguments or {}})
    result = resp["result"]
    return result["content"][0]["text"], result["isError"]


# ------------------------------------------------------------ protocol

def test_initialize_echoes_protocol_and_names_itself():
    r = call(SAMPLE, "initialize", {"protocolVersion": "2025-03-26"})
    assert r["result"]["protocolVersion"] == "2025-03-26"
    assert r["result"]["serverInfo"]["name"] == "wall-mcp"
    assert "tools" in r["result"]["capabilities"]


def test_tools_list_is_exactly_the_dec_0019_allowlist():
    """Mutation: add or drop a tool without superseding DEC-0019."""
    r = call(SAMPLE, "tools/list")
    names = [t["name"] for t in r["result"]["tools"]]
    assert names == ["wall_status", "wall_item", "wall_waiting",
                     "wall_trace", "wall_answer", "wall_enqueue"]
    for t in r["result"]["tools"]:
        assert t["description"] and t["inputSchema"]["type"] == "object"


def test_unknown_tool_and_method_are_named_errors():
    r = call(SAMPLE, "tools/call", {"name": "wall_delete_everything"})
    assert r["error"]["code"] == srv.INVALID_PARAMS
    assert "DEC-0019" in r["error"]["message"]
    r2 = call(SAMPLE, "resources/list")
    assert r2["error"]["code"] == srv.METHOD_NOT_FOUND


def test_notifications_take_no_response():
    assert srv.handle_request(SAMPLE, {
        "jsonrpc": "2.0", "method": "notifications/initialized"}) is None


def test_malformed_line_answers_and_the_loop_survives():
    """One bad client message must not kill the server every editor is
    attached to. Mutation: let the JSONDecodeError propagate."""
    stdin = io.StringIO('this is not json\n'
                        '{"jsonrpc":"2.0","id":9,"method":"ping"}\n')
    stdout = io.StringIO()
    assert srv.serve(SAMPLE, stdin=stdin, stdout=stdout) == 0
    lines = [json.loads(x) for x in stdout.getvalue().splitlines()]
    assert lines[0]["error"]["code"] == srv.PARSE_ERROR
    assert lines[1] == {"jsonrpc": "2.0", "id": 9, "result": {}}


def test_serve_reconfigures_real_streams_to_utf8():
    """MCP clients speak UTF-8; a Windows console stream defaults to the
    locale codepage, which mojibakes non-ASCII inbound — the engineer's
    own wall_answer text on its way into the s_human shard. serve() must
    re-encode any stream that can be re-encoded, and must not touch one
    that cannot (the StringIO tests above already prove the latter).
    Mutation: drop the reconfigure loop and the recorder stays empty.
    Host-review finding (Gemini, MAX3 PR #1662), fixed kit-first."""

    class Recorder(io.StringIO):
        def __init__(self, *a):
            super().__init__(*a)
            self.encodings: list[str] = []

        def reconfigure(self, *, encoding):
            self.encodings.append(encoding)

    stdin = Recorder('{"jsonrpc":"2.0","id":1,"method":"ping"}\n')
    stdout = Recorder()
    assert srv.serve(SAMPLE, stdin=stdin, stdout=stdout) == 0
    assert stdin.encodings == ["utf-8"], "inbound stream was not re-encoded"
    assert stdout.encodings == ["utf-8"]
    assert json.loads(stdout.getvalue())["result"] == {}


# ------------------------------------------------------------ read tools

def test_wall_status_is_byte_identical_to_the_cli_summary():
    """DEC-0018 pinned as EQUALITY, not resemblance: the MCP text and the
    CLI text come from one build_summary + format_summary."""
    text, is_error = tool(SAMPLE, "wall_status")
    assert not is_error
    snap = json.loads((SAMPLE / ".wall" / "derived" / "wall.json")
                      .read_text(encoding="utf-8"))
    hb = json.loads((SAMPLE / ".wall" / "derived" / "heartbeat.json")
                    .read_text(encoding="utf-8"))
    expected = summary_mod.format_summary(summary_mod.build_summary(snap, hb))
    # the age line moves with the clock; compare everything after it
    assert text.splitlines()[1:] == expected.splitlines()[1:]


def test_wall_status_json_is_the_same_fold():
    text, is_error = tool(SAMPLE, "wall_status", {"json": True})
    assert not is_error
    payload = json.loads(text)
    assert payload["items_total"] == 11 and payload["arcs"] == 3


def test_wall_item_found_and_missing():
    text, is_error = tool(SAMPLE, "wall_item", {"key": "ST-106"})
    assert not is_error
    assert json.loads(text)["item_id"] == "ST-106"
    text2, _ = tool(SAMPLE, "wall_item", {"key": "ST-999"})
    assert "no item 'ST-999'" in text2
    text3, is_error3 = tool(SAMPLE, "wall_item", {})
    assert is_error3 and "key is required" in text3


def test_wall_waiting_lists_the_engineers_queue():
    text, is_error = tool(SAMPLE, "wall_waiting")
    assert not is_error
    assert "waiting on you (3):" in text and "ask_0007" in text
    assert "open questions:" in text


def test_wall_trace_captures_the_cli():
    text, is_error = tool(SAMPLE, "wall_trace", {"target": "ST-106"})
    assert not is_error and "ST-106" in text
    text2, _ = tool(SAMPLE, "wall_trace", {"target": "ST-999"})
    assert "nothing found" in text2


def test_missing_snapshot_reads_as_instruction_not_error(tmp_path):
    text, is_error = tool(tmp_path, "wall_status")
    assert not is_error and "wall run-once" in text


# ------------------------------------------------------------ verb tools

def _sample_copy(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    shutil.copytree(SAMPLE, repo)
    return repo


def test_wall_answer_answers_an_open_ask_and_refuses_an_answered_one(tmp_path):
    """The engineer's verb, with the CLI's own refusal semantics kept
    verbatim: an open ask is answered into the s_human shard; a question
    the ledger already holds an answer for is refused, not overwritten."""
    repo = _sample_copy(tmp_path)
    text, is_error = tool(repo, "wall_answer",
                          {"target": "ask_0007",
                           "text": "A retry is a NEW event; mark the first superseded."})
    assert not is_error and text.startswith("answered")
    assert "s_human" in text  # the answer is recorded as the HUMAN speaking

    text2, is_error2 = tool(repo, "wall_answer",
                            {"target": "q_0042", "text": "second thoughts"})
    assert not is_error2  # a refusal is a RESULT the caller reads
    assert "refused" in text2 and "already answered" in text2


def test_wall_answer_requires_both_fields():
    text, is_error = tool(SAMPLE, "wall_answer", {"target": "ask_0007"})
    assert is_error and "both required" in text


def test_wall_enqueue_unconfigured_is_honest(tmp_path):
    repo = _sample_copy(tmp_path)
    text, is_error = tool(repo, "wall_enqueue",
                          {"directive": "execute_item",
                           "target_key": "ST-1", "title": "Execute ST-1"})
    assert not is_error and "not reachable from here, honestly" in text


def test_wall_enqueue_posts_the_typed_contract(tmp_path):
    """With queue_api.origin configured, the POST that arrives at the
    host is contracts.EnqueuePayload.to_dict() exactly — source, priority
    and directive from the module, never re-typed."""
    import http.server as hs

    seen: list[dict] = []

    class _Host(hs.BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            seen.append({"path": self.path,
                         "body": json.loads(self.rfile.read(length))})
            body = b'{"id": "wq_9", "title": "ok"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    httpd = hs.HTTPServer(("127.0.0.1", 0), _Host)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        repo = _sample_copy(tmp_path)
        cfg_path = repo / ".wall" / "config" / "wall.json"
        cfg = json.loads(cfg_path.read_text(encoding="utf-8")) if cfg_path.exists() else {}
        cfg["queue_api"] = {"origin": f"http://127.0.0.1:{httpd.server_address[1]}",
                            "add": "/api/queue/add"}
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        cfg_path.write_text(json.dumps(cfg), encoding="utf-8")

        text, is_error = tool(repo, "wall_enqueue",
                              {"directive": "execute_arc",
                               "target_arch": "ARC-03",
                               "title": "Execute arc ARC-03"})
        assert not is_error and "wq_9" in text
        assert seen == [{"path": "/api/queue/add", "body": {
            "source": "wall_click", "priority": "P2",
            "directive": "execute_arc", "target_arch": "ARC-03",
            "title": "Execute arc ARC-03"}}]
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_wall_enqueue_bad_directive_is_a_tool_error(tmp_path):
    repo = _sample_copy(tmp_path)
    cfg_path = repo / ".wall" / "config" / "wall.json"
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(json.dumps({"queue_api": {
        "origin": "http://127.0.0.1:1", "add": "/x"}}), encoding="utf-8")
    text, is_error = tool(repo, "wall_enqueue",
                          {"directive": "delete_everything", "title": "no"})
    assert is_error and "delete_everything" in text


def test_enqueue_schema_enum_derives_from_contracts():
    import contracts
    schema = srv.TOOLS["wall_enqueue"]["inputSchema"]
    assert schema["properties"]["directive"]["enum"] == [
        str(d) for d in contracts.Directive]


# ------------------------------------------------------- end to end

def test_spawned_server_speaks_the_wire_protocol():
    """The reference transcript: a real subprocess, real stdio."""
    lines = "\n".join([
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                    "params": {"protocolVersion": "2024-11-05"}}),
        json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
        json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}),
        json.dumps({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                    "params": {"name": "wall_waiting", "arguments": {}}}),
    ]) + "\n"
    proc = subprocess.run(
        [sys.executable, str(KIT / "tools" / "wall" / "mcp_server.py"),
         "--repo", str(SAMPLE)],
        input=lines, capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, proc.stderr
    out = [json.loads(x) for x in proc.stdout.splitlines()]
    assert [m["id"] for m in out] == [1, 2, 3]
    assert "ask_0007" in out[2]["result"]["content"][0]["text"]


# ------------------------------------------------------------ role gate

def test_agent_role_gets_reads_only():
    """DEC-0019 clause 4: the human verbs never reach an agent. Mutation:
    serve TOOLS unfiltered and both pins fail."""
    r = srv.handle_request(SAMPLE, {"jsonrpc": "2.0", "id": 1,
                                    "method": "tools/list"}, role="agent")
    names = [t["name"] for t in r["result"]["tools"]]
    assert names == ["wall_status", "wall_item", "wall_waiting", "wall_trace"]

    r2 = srv.handle_request(SAMPLE, {
        "jsonrpc": "2.0", "id": 2, "method": "tools/call",
        "params": {"name": "wall_answer",
                   "arguments": {"target": "ask_0007", "text": "forged"}}},
        role="agent")
    assert r2["error"]["code"] == srv.INVALID_PARAMS
    assert "not in the 'agent' role's allowlist" in r2["error"]["message"]


def test_unknown_role_degrades_down_never_up():
    r = srv.handle_request(SAMPLE, {"jsonrpc": "2.0", "id": 1,
                                    "method": "tools/list"}, role="superuser")
    names = [t["name"] for t in r["result"]["tools"]]
    assert "wall_answer" not in names and "wall_enqueue" not in names
