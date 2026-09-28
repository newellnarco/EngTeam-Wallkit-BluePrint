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
import time
import types
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
    Host-review finding (Gemini), fixed kit-first."""

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


def test_array_params_are_invalid_params_not_a_crash():
    """JSON-RPC allows array params but every method here is by-name: a
    request gets INVALID_PARAMS, a notification is ignored, and the
    AttributeError that would kill every attached editor never escapes
    serve(). Host-review finding (CodeRabbit), fixed
    kit-first. Mutation: drop the isinstance guard and this raises."""
    r = srv.handle_request(SAMPLE, {
        "jsonrpc": "2.0", "id": 5, "method": "initialize", "params": [1]})
    assert r["error"]["code"] == srv.INVALID_PARAMS
    assert srv.handle_request(SAMPLE, {
        "jsonrpc": "2.0", "method": "notifications/initialized",
        "params": [1]}) is None
    stdin = io.StringIO(
        '{"jsonrpc":"2.0","id":6,"method":"tools/list","params":[7]}\n'
        '{"jsonrpc":"2.0","id":7,"method":"ping"}\n')
    stdout = io.StringIO()
    assert srv.serve(SAMPLE, stdin=stdin, stdout=stdout) == 0
    lines = [json.loads(x) for x in stdout.getvalue().splitlines()]
    assert lines[0]["error"]["code"] == srv.INVALID_PARAMS
    assert lines[1]["result"] == {}


# ------------------------------------------------- loopback HTTP (DEC-0036)

import urllib.error  # noqa: E402
import urllib.request  # noqa: E402

import pytest  # noqa: E402


@pytest.fixture
def http_server():
    """A real loopback server on an ephemeral port, torn down after."""
    server = srv.make_http_server(SAMPLE, "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    yield base
    server.shutdown()
    server.server_close()


def post(url: str, payload, headers: dict | None = None):
    body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read()
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        return exc.code, (json.loads(raw) if raw else None)


def test_http_speaks_the_same_protocol_as_stdio(http_server):
    status, init = post(f"{http_server}/mcp/engineer", {
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-03-26"}})
    assert status == 200 and init["result"]["serverInfo"]["name"] == "wall-mcp"
    status, listed = post(f"{http_server}/mcp/engineer",
                          {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    assert [t["name"] for t in listed["result"]["tools"]] == list(srv.ROLE_TOOLS["engineer"])
    status, called = post(f"{http_server}/mcp/engineer", {
        "jsonrpc": "2.0", "id": 3, "method": "tools/call",
        "params": {"name": "wall_status", "arguments": {}}})
    assert called["result"]["content"][0]["text"] == srv.tool_wall_status(SAMPLE, {})


def test_http_role_comes_from_the_path_and_never_degrades_up(http_server):
    """Mutation: serve the engineer allowlist on /mcp/agent or /mcp/<unknown>."""
    for path in ("/mcp/agent", "/mcp/root"):
        _, listed = post(f"{http_server}{path}",
                         {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        assert [t["name"] for t in listed["result"]["tools"]] == list(srv.ROLE_TOOLS["agent"])
    _, refused = post(f"{http_server}/mcp/agent", {
        "jsonrpc": "2.0", "id": 2, "method": "tools/call",
        "params": {"name": "wall_answer", "arguments": {"target": "x", "text": "y"}}})
    assert "allowlist" in refused["error"]["message"]


def test_http_notification_is_202_with_no_body(http_server):
    status, body = post(f"{http_server}/mcp/engineer",
                        {"jsonrpc": "2.0", "method": "notifications/initialized"})
    assert (status, body) == (202, None)


def test_http_batch_answers_every_request_in_order(http_server):
    status, body = post(f"{http_server}/mcp/agent", [
        {"jsonrpc": "2.0", "id": "a", "method": "ping"},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": "b", "method": "ping"}])
    assert status == 200 and [r["id"] for r in body] == ["a", "b"]


def test_http_refuses_every_browser_origin_by_default(http_server):
    """DEC-0036 clause 4: a browser always sends Origin, an MCP client never
    does. Loopback pages (a dev server on :5173) are browsers too, and must
    not get the engineer seat stdio never offered them."""
    for origin in ("https://evil.example", "http://localhost:5173", "http://127.0.0.1:8124", "null"):
        status, _ = post(f"{http_server}/mcp/engineer",
                         {"jsonrpc": "2.0", "id": 1, "method": "ping"},
                         headers={"Origin": origin})
        assert status == 403, origin
    assert post(f"{http_server}/mcp/engineer",
                {"jsonrpc": "2.0", "id": 1, "method": "ping"})[0] == 200


def test_http_admits_an_origin_only_when_the_operator_allows_it():
    server = srv.make_http_server(SAMPLE, "127.0.0.1", 0,
                                  allow_origins=("http://localhost:6274",))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        ok = post(f"{base}/mcp/agent", {"jsonrpc": "2.0", "id": 1, "method": "ping"},
                  headers={"Origin": "http://localhost:6274"})
        other = post(f"{base}/mcp/agent", {"jsonrpc": "2.0", "id": 1, "method": "ping"},
                     headers={"Origin": "http://localhost:6275"})
    finally:
        server.shutdown()
        server.server_close()
    assert ok[0] == 200 and other[0] == 403


def test_http_refuses_a_non_loopback_host_header(http_server):
    """DNS rebinding: the page resolves its own name to 127.0.0.1 but still
    names itself in Host."""
    status, _ = post(f"{http_server}/mcp/engineer",
                     {"jsonrpc": "2.0", "id": 1, "method": "ping"},
                     headers={"Host": "evil.example:8124"})
    assert status == 403


def test_http_bad_input_is_answered_not_crashed(http_server):
    assert post(f"{http_server}/mcp/engineer", b"{not json")[0] == 400
    assert post(f"{http_server}/mcp/engineer", [])[0] == 400
    assert post(f"{http_server}/other", {"jsonrpc": "2.0", "id": 1, "method": "ping"})[0] == 404
    # The server is still up after all of that.
    assert post(f"{http_server}/mcp/engineer",
                {"jsonrpc": "2.0", "id": 9, "method": "ping"})[0] == 200


def test_http_get_is_405_no_server_stream(http_server):
    try:
        urllib.request.urlopen(f"{http_server}/mcp/engineer", timeout=10)
        raise AssertionError("GET must not succeed")
    except urllib.error.HTTPError as exc:
        assert exc.code == 405 and exc.headers["Allow"] == "POST"


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.10", "example.com", "::"])
def test_http_never_binds_beyond_loopback(host):
    """Mutation: drop the bind guard. The exposure boundary is structural."""
    with pytest.raises(ValueError, match="loopback-only"):
        srv.make_http_server(SAMPLE, host, 0)


@pytest.mark.parametrize(("origin", "allow", "ok"), [
    (None, (), True), ("", (), True),
    ("http://127.0.0.1:8124", (), False), ("http://localhost", (), False),
    ("null", (), False), ("https://evil.example", (), False),
    ("http://localhost:6274", ("http://localhost:6274",), True),
    ("http://localhost:6274/", ("http://localhost:6274",), False)])
def test_origin_rule(origin, allow, ok):
    assert srv.origin_allowed(origin, allow) is ok


@pytest.mark.parametrize(("host", "ok"), [
    ("127.0.0.1:8124", True), ("localhost:8124", True), ("[::1]:8124", True),
    ("127.0.0.1", True), ("evil.example:8124", False), (None, False),
    ("", False), ("192.168.1.2:8124", False)])
def test_host_header_rule(host, ok):
    assert srv.host_header_allowed(host) is ok


def test_cli_captures_are_serialized_and_nothing_else_is(monkeypatch):
    """Only CLI-capturing tools share a lock (a wall_answer ledger write must
    not interleave). Pings and reads — and wall_enqueue's network call — must
    not queue behind one. Mutation: drop _CLI_LOCK, or put a lock back
    around the whole dispatch."""
    inside, peak = [], []
    gate = threading.Event()

    def slow_cli(ns):
        inside.append(1)
        peak.append(len(inside))
        gate.wait(0.2)
        inside.pop()
        return 0

    def capture_tool(repo, args):
        return srv._capture_cli(slow_cli, types.SimpleNamespace())[1] or "ok"

    monkeypatch.setitem(srv.TOOLS["wall_trace"], "fn", capture_tool)
    call_body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                            "params": {"name": "wall_trace"}}).encode()
    threads = [threading.Thread(target=srv.handle_http_body, args=(SAMPLE, call_body, "agent"))
               for _ in range(3)]
    for th in threads:
        th.start()
    ping = json.dumps({"jsonrpc": "2.0", "id": 9, "method": "ping"}).encode()
    started = time.monotonic()
    assert srv.handle_http_body(SAMPLE, ping, "agent")[0] == 200
    assert time.monotonic() - started < 0.15, "a ping waited behind a CLI capture"
    gate.set()
    for th in threads:
        th.join()
    assert max(peak) == 1


def test_capture_is_per_thread_so_a_host_s_output_never_leaks_in(capsys):
    """In a resident host the server runs on a thread; the host keeps printing.
    Its lines must stay on its own stream, not land in a wall_answer transcript.
    Mutation: capture with contextlib.redirect_stdout again."""
    in_capture = threading.Event()
    release = threading.Event()

    def cli(ns):
        print("from the tool")
        in_capture.set()
        release.wait(2)
        return 0

    result = {}
    worker = threading.Thread(
        target=lambda: result.update(out=srv._capture_cli(cli, types.SimpleNamespace())[1]))
    worker.start()
    assert in_capture.wait(2)
    print("from the host")  # another thread, same process, mid-capture
    release.set()
    worker.join()
    assert result["out"] == "from the tool\n"
    assert "from the host" in capsys.readouterr().out


@pytest.mark.parametrize("name", [["x"], {"a": 1}, 7, None])
def test_a_non_string_tool_name_is_an_error_not_a_crash(name):
    """Was: TypeError (unhashable) out of handle_request, killing stdio's loop
    and resetting the HTTP connection."""
    r = call(SAMPLE, "tools/call", {"name": name})
    if name is None:  # falsy → empty name → unknown tool
        assert "unknown tool" in r["error"]["message"]
    else:
        assert r["error"]["code"] == srv.INVALID_PARAMS


def test_non_object_arguments_are_invalid_params():
    r = call(SAMPLE, "tools/call", {"name": "wall_status", "arguments": [1]})
    assert r["error"]["code"] == srv.INVALID_PARAMS


def test_stdio_survives_an_unhashable_name_and_absurd_nesting():
    lines = [
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                    "params": {"name": ["x"]}}),
        "[" * 100000,
        json.dumps({"jsonrpc": "2.0", "id": 2, "method": "ping"}),
    ]
    out = io.StringIO()
    srv.serve(SAMPLE, stdin=io.StringIO("\n".join(lines) + "\n"), stdout=out)
    replies = [json.loads(x) for x in out.getvalue().splitlines()]
    assert replies[0]["error"]["code"] == srv.INVALID_PARAMS
    assert replies[1]["error"]["code"] == srv.PARSE_ERROR
    assert replies[2] == {"jsonrpc": "2.0", "id": 2, "result": {}}


def test_an_unexpected_exception_is_an_internal_error_response(monkeypatch):
    def explode(repo, msg, role="engineer"):
        raise RuntimeError("boom")

    monkeypatch.setattr(srv, "handle_request", explode)
    kind, resp = srv.handle_payload(SAMPLE, b'{"jsonrpc":"2.0","id":3,"method":"ping"}',
                                    "agent", allow_batch=True)
    assert kind == srv.PAYLOAD_OK
    assert resp["id"] == 3 and resp["error"]["code"] == srv.INTERNAL_ERROR
    kind, resp = srv.handle_payload(SAMPLE, b'{"jsonrpc":"2.0","method":"x"}',
                                    "agent", allow_batch=True)
    assert resp is None, "a notification gets no response, even an error"


def test_both_transports_share_one_error_envelope():
    """Mutation: rebuild the parse-error dict inline in serve() or the HTTP path."""
    status, body = srv.handle_http_body(SAMPLE, b"{nope", "agent")
    out = io.StringIO()
    srv.serve(SAMPLE, stdin=io.StringIO("{nope\n"), stdout=out)
    assert status == 400
    assert json.loads(body)["error"]["code"] == json.loads(out.getvalue())["error"]["code"]
    assert json.loads(body)["error"]["message"] == json.loads(out.getvalue())["error"]["message"]


def test_http_deeply_nested_body_is_a_400(http_server):
    assert post(f"{http_server}/mcp/agent", b"[" * 100000)[0] == 400


def test_http_chunked_body_is_411(http_server):
    import http.client
    host, port = http_server.rsplit("/", 1)[-1].split(":")
    conn = http.client.HTTPConnection(host, int(port), timeout=10)
    conn.putrequest("POST", "/mcp/agent")
    conn.putheader("Transfer-Encoding", "chunked")
    conn.putheader("Content-Type", "application/json")
    conn.endheaders()
    conn.send(b"0\r\n\r\n")
    assert conn.getresponse().status == 411
    conn.close()


def test_a_stalled_body_times_out_instead_of_parking_a_thread(monkeypatch):
    import socket as _socket
    monkeypatch.setattr(srv, "HTTP_SOCKET_TIMEOUT_S", 0.3)
    server = srv.make_http_server(SAMPLE, "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        s = _socket.create_connection(server.server_address[:2], timeout=5)
        s.sendall(b"POST /mcp/agent HTTP/1.1\r\nHost: 127.0.0.1\r\n"
                  b"Content-Length: 1000\r\n\r\n{")
        s.settimeout(5)
        assert s.recv(100) == b"", "the server should drop a stalled request"
        s.close()
    finally:
        server.shutdown()
        server.server_close()


def test_handler_threads_are_joined_on_close():
    server = srv.make_http_server(SAMPLE, "127.0.0.1", 0)
    try:
        assert server.daemon_threads is False
        assert server.block_on_close is True
    finally:
        server.server_close()


def test_ipv6_gets_an_ipv6_socket_without_needing_to_bind():
    """Pure half of the IPv6 fix, so it is pinned even where the host has no
    IPv6 stack. Mutation: always return AF_INET."""
    import socket as _socket
    assert srv.address_family_for("::1") == _socket.AF_INET6
    assert srv.address_family_for("[::1]") == _socket.AF_INET6
    assert srv.address_family_for("127.0.0.1") == _socket.AF_INET
    assert srv.address_family_for("localhost") == _socket.AF_INET


def test_ipv6_loopback_actually_binds():
    import socket as _socket
    if not _socket.has_ipv6:
        pytest.skip("no IPv6 on this host")
    for host in ("::1", "[::1]"):
        try:
            server = srv.make_http_server(SAMPLE, host, 0)
        except OSError as exc:  # IPv6 disabled in this container
            pytest.skip(f"IPv6 loopback unavailable: {exc}")
        try:
            assert server.address_family == _socket.AF_INET6
        finally:
            server.server_close()


def test_cli_usage_errors_are_argparse_errors_not_tracebacks(capsys):
    for argv in (["--http", "localhost:x"], ["--http", "0.0.0.0:8124"],
                 ["--http", "::1"], ["--http", "8124", "--role", "agent"],
                 ["--allow-origin", "http://x"]):
        with pytest.raises(SystemExit) as exc:
            srv.main(["--repo", str(SAMPLE), *argv])
        assert exc.value.code == 2, argv
    assert "Traceback" not in capsys.readouterr().err


def test_http_arg_parsing():
    assert srv._parse_http_arg("8124") == ("127.0.0.1", 8124)
    assert srv._parse_http_arg("127.0.0.1:9000") == ("127.0.0.1", 9000)
    assert srv._parse_http_arg(":9000") == ("127.0.0.1", 9000)
    assert srv._parse_http_arg("localhost") == ("localhost", srv.DEFAULT_HTTP_PORT)
    assert srv._parse_http_arg("[::1]:9000") == ("::1", 9000)
    assert srv._parse_http_arg("[::1]") == ("::1", srv.DEFAULT_HTTP_PORT)
    for bad in ("::1", "[::1", "[::1]x", "localhost:x", ""):
        with pytest.raises(ValueError):
            srv._parse_http_arg(bad)
