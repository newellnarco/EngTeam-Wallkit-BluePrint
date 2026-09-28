"""wall-host -- one resident process per machine (DEC-0037), pinned.

Four promises, each with its own section:

1. **Parity.** A seat reached through the host answers byte-for-byte what the
   same seat answers over stdio, for both roles -- the host is a second
   transport, never a second implementation.
2. **Single instance.** The bind is exclusive; a second host exits 0 without
   serving.
3. **The folded sweep keeps the sweeper's contract.** Same heartbeat, same
   log, same pruning; in-process only for a repo on the host's exact kit,
   the repo's own ``wall.py`` otherwise. The timer becomes a watchdog that
   exits at once while the host is healthy and sweeps + restarts it when not.
4. **Local-scope registration** (``mcp_local``) is idempotent, preserves every
   other entry, never clobbers a stranger's, and reverts cleanly.

Every test runs against a temporary WALL_HOME and a temporary Claude config;
nothing touches a real home, a real scheduler or a non-loopback socket.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import types
import urllib.error
import urllib.request
from pathlib import Path

import pytest

KIT = Path(__file__).resolve().parents[1]
WALL_DIR = KIT / "tools" / "wall"
SAMPLE = KIT / "sample"
if str(WALL_DIR) not in sys.path:
    sys.path.insert(0, str(WALL_DIR))

import host as host_mod  # noqa: E402
import mcp_local  # noqa: E402
import mcp_server as srv  # noqa: E402
import service  # noqa: E402

NO_PROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))


# ---------------------------------------------------------------- scaffolding

@pytest.fixture()
def home(tmp_path: Path, monkeypatch) -> Path:
    target = tmp_path / "wallhome"
    target.mkdir()
    monkeypatch.setenv("WALL_HOME", str(target))
    return target


def register(home: Path, *rows: tuple[str, Path]) -> None:
    (home / "registry.json").write_text(json.dumps({"repos": [
        {"path": str(path), "name": name, "installed_version": "t", "last_seen": None}
        for name, path in rows]}), encoding="utf-8")


def vendored_repo(root: Path) -> Path:
    """A repo carrying the sample ledger and an exact copy of this kit."""
    shutil.copytree(SAMPLE, root, ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(WALL_DIR, root / "tools" / "wall",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    return root


def run_host(host: host_mod.Host):
    server = srv.make_routed_server(host.route, "127.0.0.1", 0, health=host.health)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, "http://127.0.0.1:%d" % server.server_address[1]


@pytest.fixture()
def live_host(home: Path):
    register(home, ("sample", SAMPLE))
    host = host_mod.Host(home, port=0)
    server, base = run_host(host)
    yield host, base
    server.shutdown()
    server.server_close()


def post(url: str, payload) -> tuple[int, object]:
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with NO_PROXY.open(req, timeout=10) as resp:
            raw = resp.read()
            return resp.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        return exc.code, json.loads(raw) if raw else None


def get(url: str) -> tuple[int, object]:
    try:
        with NO_PROXY.open(url, timeout=10) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, None


# ------------------------------------------------------------- 1. parity

#: One conversation per role: handshake, discovery, every read, a verb the
#: agent must be refused, an unknown tool, a malformed argument set.
SCRIPT = [
    {"jsonrpc": "2.0", "id": 1, "method": "initialize",
     "params": {"protocolVersion": "2025-03-26"}},
    {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "wall_status"}},
    {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
     "params": {"name": "wall_status", "arguments": {"json": True}}},
    {"jsonrpc": "2.0", "id": 5, "method": "tools/call",
     "params": {"name": "wall_item", "arguments": {"key": "ST-106"}}},
    {"jsonrpc": "2.0", "id": 6, "method": "tools/call", "params": {"name": "wall_waiting"}},
    {"jsonrpc": "2.0", "id": 7, "method": "tools/call",
     "params": {"name": "wall_trace", "arguments": {"target": "ST-106"}}},
    {"jsonrpc": "2.0", "id": 8, "method": "tools/call",
     "params": {"name": "wall_answer", "arguments": {"target": "x"}}},
    {"jsonrpc": "2.0", "id": 9, "method": "tools/call", "params": {"name": "nope"}},
    {"jsonrpc": "2.0", "id": 10, "method": "tools/call",
     "params": {"name": "wall_item", "arguments": {}}},
    {"jsonrpc": "2.0", "id": 11, "method": "ping"},
]


def over_stdio(repo: Path, role: str) -> list[dict]:
    stdin = io.StringIO("".join(json.dumps(m) + "\n" for m in SCRIPT))
    stdout = io.StringIO()
    srv.serve(repo, stdin=stdin, stdout=stdout, role=role)
    return [json.loads(line) for line in stdout.getvalue().splitlines()]


@pytest.mark.parametrize("role", ["engineer", "agent"])
def test_a_host_seat_is_byte_identical_to_the_stdio_seat(live_host, role):
    """Mutation: route a role to the other role's allowlist, or serve a
    different repo's snapshot, and the transcripts diverge."""
    _, base = live_host
    via_host = [post("%s/r/sample/mcp/%s" % (base, role), m)[1] for m in SCRIPT]
    assert via_host == over_stdio(SAMPLE, role)


def test_the_agent_seat_through_the_host_never_holds_the_verbs(live_host):
    _, base = live_host
    _, listed = post(base + "/r/sample/mcp/agent", SCRIPT[1])
    names = [t["name"] for t in listed["result"]["tools"]]
    assert "wall_answer" not in names and "wall_enqueue" not in names
    _, sneaky = post(base + "/r/sample/mcp/root", SCRIPT[1])
    assert [t["name"] for t in sneaky["result"]["tools"]] == names, "unknown role -> agent"


def test_unknown_repo_and_bad_paths_are_404(live_host):
    _, base = live_host
    for path in ("/r/other/mcp/agent", "/r/sample", "/r/sample/", "/mcp/agent",
                 "/r/sample/mcp/agent/extra", "/"):
        assert post(base + path, SCRIPT[1])[0] == 404, path


def test_a_slug_two_rows_share_serves_neither(home: Path, tmp_path: Path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    register(home, ("same", a), ("same", b), ("solo", SAMPLE))
    host = host_mod.Host(home)
    assert host.routes() == {"solo": SAMPLE}
    assert host.route("/r/same/mcp/agent") is None


def test_slugs_are_one_url_segment():
    assert host_mod.slug("My Repo") == "My-Repo"
    assert host_mod.slug("a/b\\c") == "a-b-c"
    assert host_mod.slug("...") == "repo"
    assert host_mod.repo_base_url(8124, "My Repo") == "http://127.0.0.1:8124/r/My-Repo"


def test_health_names_the_host_and_its_repos(live_host):
    host, base = live_host
    status, body = get(base + "/health")
    assert status == 200
    assert body["service"] == host_mod.SERVICE and body["ok"] is True
    assert body["pid"] == os.getpid()
    assert [r["name"] for r in body["repos"]] == ["sample"]
    assert body["repos"][0]["kit_match"] is False, "the sample carries no vendored kit"


def test_health_goes_false_when_the_sweep_stalls(home: Path):
    host = host_mod.Host(home, interval_s=10)
    assert host.health()["ok"] is True
    host._started_at -= 31
    assert host.health()["ok"] is False, "no sweep in 3 intervals is not healthy"
    host._swept_at = time.monotonic()
    assert host.health()["ok"] is True


def test_health_refuses_a_foreign_origin(live_host):
    _, base = live_host
    req = urllib.request.Request(base + "/health", headers={"Origin": "https://evil.example"})
    with pytest.raises(urllib.error.HTTPError) as err:
        NO_PROXY.open(req, timeout=10)
    assert err.value.code == 403


def test_get_elsewhere_and_delete_stay_405(live_host):
    _, base = live_host
    assert get(base + "/r/sample/mcp/agent")[0] == 405
    req = urllib.request.Request(base + "/health", method="DELETE")
    with pytest.raises(urllib.error.HTTPError) as err:
        NO_PROXY.open(req, timeout=10)
    assert err.value.code == 405


def test_the_single_repo_server_answers_health_too():
    server = srv.make_http_server(SAMPLE, "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, body = get("http://127.0.0.1:%d/health" % server.server_address[1])
        assert status == 200 and body["service"] == "wall-mcp"
    finally:
        server.shutdown()
        server.server_close()


def test_the_host_still_never_binds_beyond_loopback(home: Path):
    with pytest.raises(ValueError, match="loopback"):
        srv.make_routed_server(host_mod.Host(home).route, "0.0.0.0", 0)


# ------------------------------------------------------ 2. single instance

def test_a_second_bind_on_the_same_port_fails():
    first = srv.make_routed_server(lambda path: None, "127.0.0.1", 0)
    try:
        with pytest.raises(OSError):
            srv.make_routed_server(lambda path: None, "127.0.0.1",
                                   first.server_address[1])
    finally:
        first.server_close()


def test_a_second_host_exits_zero_without_serving(home: Path, capsys):
    first = srv.make_routed_server(lambda path: None, "127.0.0.1", 0)
    try:
        assert host_mod.serve(home, first.server_address[1], 120) == 0
        assert "already running" in capsys.readouterr().err
    finally:
        first.server_close()


def test_windows_binds_exclusively(monkeypatch):
    """Windows' SO_REUSEADDR lets a second process share a listening port, so
    the guard there is SO_EXCLUSIVEADDRUSE with reuse off. Pinned without
    Windows: the bind is driven against a recording socket."""
    calls = []

    class FakeSocket:
        def setsockopt(self, level, name, value):
            calls.append((level, name, value))

        def bind(self, address):
            calls.append(("bind", address))

        def getsockname(self):
            return ("127.0.0.1", 9)

    monkeypatch.setattr(srv.socket, "SO_EXCLUSIVEADDRUSE", 4, raising=False)
    server = srv.ExclusiveHTTPServer.__new__(srv.ExclusiveHTTPServer)
    server.socket = FakeSocket()
    server.server_address = ("127.0.0.1", 9)
    server.allow_reuse_address = False
    server.allow_reuse_port = False
    srv.ExclusiveHTTPServer.server_bind(server)
    assert (socket.SOL_SOCKET, 4, 1) in calls
    assert not any(c[1] == socket.SO_REUSEADDR for c in calls if len(c) == 3)
    assert srv.ExclusiveHTTPServer.allow_reuse_address is (not sys.platform.startswith("win"))


# ----------------------------------------------------------- 3. the sweep

def test_the_folded_sweep_keeps_the_sweepers_contract(home: Path, tmp_path: Path):
    """Same repo, swept once by the generated sweeper and once by the host:
    the same heartbeat keys, per-repo verdicts and pruning -- plus the host's
    in-process marker for a repo on its exact kit."""
    repo = vendored_repo(tmp_path / "vendored")
    gone = tmp_path / "deleted"
    register(home, ("vendored", repo), ("gone", gone))
    service.write_sweeper()
    classic = subprocess.run([sys.executable, str(home / "sweep_all.py")],
                             capture_output=True, text=True, timeout=120)
    assert classic.returncode == 0, classic.stderr
    classic_beat = json.loads((home / "heartbeat.json").read_text(encoding="utf-8"))

    register(home, ("vendored", repo), ("gone", gone))
    host = host_mod.Host(home)
    beat = host.sweep()
    assert set(beat) - {"host"} == set(classic_beat)
    assert beat["ok"] is classic_beat["ok"] is True
    assert beat["repos"] == classic_beat["repos"] == 1
    assert [(r["path"], r["ok"]) for r in beat["results"]] == \
        [(r["path"], r["ok"]) for r in classic_beat["results"]]
    assert beat["results"][0]["in_process"] is True
    assert beat["results"][0]["detail"] == classic_beat["results"][0]["detail"]
    rows = json.loads((home / "registry.json").read_text(encoding="utf-8"))["repos"]
    assert [r["name"] for r in rows] == ["vendored"], "a dead path is dropped"
    assert rows[0]["last_seen"]
    log = (home / "courier.log").read_text(encoding="utf-8")
    assert "dropped %s" % gone in log and "%s: ok" % repo in log
    assert (repo / ".wall" / "derived" / "wall.json").is_file()


def test_a_repo_on_another_kit_is_swept_by_its_own_wall_py(home: Path, tmp_path: Path,
                                                           monkeypatch):
    repo = vendored_repo(tmp_path / "older")
    (repo / "tools" / "wall" / "summary.py").write_text("# an older kit\n", encoding="utf-8")
    register(home, ("older", repo))
    seen = []
    monkeypatch.setattr(host_mod.Host, "_sweep_subprocess",
                        lambda self, wall_py, r: seen.append((wall_py, r)) or (True, "sub"))
    monkeypatch.setattr(host_mod.Host, "_sweep_in_process",
                        lambda self, r: pytest.fail("a different kit ran in-process"))
    beat = host_mod.Host(home).sweep()
    assert seen == [(repo / "tools" / "wall" / "wall.py", repo)]
    assert beat["results"][0]["in_process"] is False


def test_the_subprocess_path_is_the_sweepers_argv(home: Path, tmp_path: Path, monkeypatch):
    calls = []

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs["timeout"]))
        return subprocess.CompletedProcess(argv, 0, "swept 1 events\n", "")

    monkeypatch.setattr(host_mod.subprocess, "run", fake_run)
    wall_py = tmp_path / "r" / "tools" / "wall" / "wall.py"
    host = host_mod.Host(home, python="py")
    assert host._sweep_subprocess(wall_py, tmp_path / "r") == (True, "swept 1 events")
    assert calls == [(["py", str(wall_py), "--repo", str(tmp_path / "r"), "run-once"],
                      host_mod.SWEEP_TIMEOUT_S)]


def test_one_failing_repo_does_not_stop_the_sweep(home: Path, tmp_path: Path, monkeypatch):
    a, b = vendored_repo(tmp_path / "a"), vendored_repo(tmp_path / "b")
    register(home, ("a", a), ("b", b))

    def boom(self, repo):
        if repo == a:
            raise RuntimeError("bad shard")
        return True, "ok"

    monkeypatch.setattr(host_mod.Host, "_sweep_in_process", boom)
    beat = host_mod.Host(home).sweep()
    assert [r["ok"] for r in beat["results"]] == [False, True]
    assert "RuntimeError: bad shard" in beat["results"][0]["detail"]
    assert beat["ok"] is False


def test_an_unreadable_registry_is_a_failed_heartbeat(home: Path):
    (home / "registry.json").write_text("{", encoding="utf-8")
    beat = host_mod.Host(home).sweep()
    assert beat["ok"] is False and "error" in beat


def test_the_loop_exits_when_host_json_goes_away(home: Path, monkeypatch):
    (home / "host.json").write_text("{}", encoding="utf-8")
    host = host_mod.Host(home, interval_s=10)
    sweeps = []
    monkeypatch.setattr(host, "sweep", lambda: sweeps.append(1) or {})
    monkeypatch.setattr(host_mod, "TICK_S", 0.01)
    thread = threading.Thread(target=host.run_loop, daemon=True)
    thread.start()
    time.sleep(0.2)
    assert sweeps == [1], "one sweep, then wait out the interval"
    (home / "host.json").unlink()
    thread.join(5)
    assert not thread.is_alive() and host.stop.is_set() and not host.restart


def test_the_loop_restarts_when_its_own_kit_changes(home: Path, tmp_path: Path,
                                                    monkeypatch):
    (home / "host.json").write_text("{}", encoding="utf-8")
    kit = tmp_path / "kit"
    kit.mkdir()
    (kit / "a.py").write_text("1", encoding="utf-8")
    host = host_mod.Host(home, interval_s=10, kit_dir=kit)
    (kit / "a.py").write_text("2", encoding="utf-8")
    monkeypatch.setattr(host, "sweep", lambda: pytest.fail("swept with stale code"))
    host.run_loop()
    assert host.restart is True


def test_a_vanished_kit_does_not_restart_the_host(home: Path, tmp_path: Path, monkeypatch):
    """Its repo deleted, the kit cannot start a replacement: keep serving."""
    (home / "host.json").write_text("{}", encoding="utf-8")
    kit = tmp_path / "kit"
    kit.mkdir()
    (kit / "a.py").write_text("1", encoding="utf-8")
    host = host_mod.Host(home, interval_s=10, kit_dir=kit)
    shutil.rmtree(kit)
    swept = []
    monkeypatch.setattr(host, "sweep", lambda: swept.append(1) or (home / "host.json").unlink())
    monkeypatch.setattr(host_mod, "TICK_S", 0.01)
    host.run_loop()
    assert swept == [1] and host.restart is False


def test_the_fingerprint_ignores_caches_and_sees_bytes(tmp_path: Path):
    kit = tmp_path / "kit"
    (kit / "__pycache__").mkdir(parents=True)
    (kit / "a.py").write_text("x", encoding="utf-8")
    first = host_mod.kit_fingerprint(kit)
    (kit / "__pycache__" / "a.cpython-312.pyc").write_bytes(b"\0")
    assert host_mod.kit_fingerprint(kit) == first
    (kit / "a.py").write_text("y", encoding="utf-8")
    assert host_mod.kit_fingerprint(kit) != first
    assert host_mod.kit_fingerprint(tmp_path / "absent") is None


def test_the_host_command_is_windowless_on_windows(home: Path, monkeypatch, tmp_path):
    exe = tmp_path / "python.exe"
    exe.write_text("", encoding="utf-8")
    (tmp_path / "pythonw.exe").write_text("", encoding="utf-8")
    monkeypatch.setattr(host_mod, "IS_WINDOWS", True)
    argv = host_mod.host_command(home, str(exe))
    assert argv[0] == str(tmp_path / "pythonw.exe")
    assert argv[1:] == [str(WALL_DIR / "host.py"), "--home", str(home)]


# ---------------------------------------------------------- the watchdog

def run_sweeper(home: Path) -> subprocess.CompletedProcess:
    service.write_sweeper()
    return subprocess.run([sys.executable, str(home / "sweep_all.py")],
                          capture_output=True, text=True, timeout=120)


def test_the_watchdog_exits_at_once_while_the_host_is_healthy(home: Path, tmp_path: Path):
    register(home, ("sample", tmp_path))  # would fail a real sweep: no wall.py
    host = host_mod.Host(home)
    server, _ = run_host(host)
    try:
        (home / "host.json").write_text(json.dumps({
            "port": server.server_address[1], "command": ["false"]}), encoding="utf-8")
        assert run_sweeper(home).returncode == 0
        assert not (home / "heartbeat.json").exists(), "a healthy host means no sweep here"
        assert not (home / "courier.log").exists()
    finally:
        server.shutdown()
        server.server_close()


def test_the_watchdog_sweeps_and_restarts_a_dead_host(home: Path, tmp_path: Path):
    register(home, ("empty", tmp_path))
    marker = tmp_path / "started"
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    free_port = probe.getsockname()[1]
    probe.close()
    (home / "host.json").write_text(json.dumps({
        "port": free_port,
        "command": [sys.executable, "-c",
                    "import pathlib; pathlib.Path(%r).write_text('up')" % str(marker)]}),
        encoding="utf-8")
    assert run_sweeper(home).returncode == 0
    assert json.loads((home / "heartbeat.json").read_text(encoding="utf-8"))["repos"] == 1
    for _ in range(100):
        if marker.exists():
            break
        time.sleep(0.05)
    assert marker.read_text() == "up"
    assert "host not answering or not sweeping -- swept directly; started host" in \
        (home / "courier.log").read_text(encoding="utf-8")


def test_without_host_json_the_sweeper_is_unchanged(home: Path, tmp_path: Path):
    register(home, ("empty", tmp_path))
    assert run_sweeper(home).returncode == 0
    assert "host not answering" not in (home / "courier.log").read_text(encoding="utf-8")


def test_a_port_held_by_something_else_is_not_the_host(home: Path):
    server = srv.make_http_server(SAMPLE, "127.0.0.1", 0)  # wall-mcp, not wall-host
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        assert service.host_health(server.server_address[1]) is None
    finally:
        server.shutdown()
        server.server_close()


# ------------------------------------------------ 4. local-scope registration

PREFIX = "http://127.0.0.1:8124/r/"
BASE = PREFIX + "proj"


@pytest.fixture()
def proj(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    root.mkdir()
    (root / ".mcp.json").write_text(json.dumps({"mcpServers": {
        "wall": {"command": "python", "args": ["tools/wall/mcp_server.py", "--repo", ".",
                                               "--role", "engineer"]},
        "wall-agent": {"command": "python",
                       "args": ["tools\\wall\\mcp_server.py", "--role", "agent"]},
        "wall-plain": {"command": "python", "args": ["tools/wall/mcp_server.py"]},
        "wall-http": {"command": "python",
                      "args": ["tools/wall/mcp_server.py", "--http", "8124"]},
        "remote": {"type": "http", "url": "https://example.invalid/mcp"},
        "other": {"command": "node", "args": ["server.js"]}}}), encoding="utf-8")
    return root


@pytest.fixture()
def claude(tmp_path: Path) -> Path:
    path = tmp_path / "cc" / ".claude.json"
    path.parent.mkdir()
    path.write_text(json.dumps({
        "numStartups": 12, "theme": "dark",
        "projects": {"/elsewhere": {"allowedTools": ["x"], "mcpServers": {
            "wall": {"type": "stdio", "command": "keep-me"}}}}}), encoding="utf-8")
    return path


def test_only_stdio_wall_entries_are_shadowed_with_their_own_roles(proj: Path):
    assert mcp_local.wall_stdio_entries(proj) == {
        "wall": "engineer", "wall-agent": "agent", "wall-plain": "engineer"}


def test_link_writes_same_named_http_twins(proj: Path, claude: Path):
    out = mcp_local.link(proj, BASE, PREFIX, claude)
    assert out["error"] is None and out["added"] == ["wall", "wall-agent", "wall-plain"]
    cfg = json.loads(claude.read_text(encoding="utf-8"))
    servers = cfg["projects"][proj.resolve().as_posix()]["mcpServers"]
    assert servers == {
        "wall": {"type": "http", "url": BASE + "/mcp/engineer"},
        "wall-agent": {"type": "http", "url": BASE + "/mcp/agent"},
        "wall-plain": {"type": "http", "url": BASE + "/mcp/engineer"}}


def test_link_preserves_every_other_entry(proj: Path, claude: Path):
    before = json.loads(claude.read_text(encoding="utf-8"))
    mcp_local.link(proj, BASE, PREFIX, claude)
    after = json.loads(claude.read_text(encoding="utf-8"))
    del after["projects"][proj.resolve().as_posix()]
    assert after == before


def test_link_is_idempotent_and_does_not_rewrite(proj: Path, claude: Path):
    mcp_local.link(proj, BASE, PREFIX, claude)
    stamp = claude.stat().st_mtime_ns
    text = claude.read_text(encoding="utf-8")
    again = mcp_local.link(proj, BASE, PREFIX, claude)
    assert again["added"] == [] and again["unchanged"] == ["wall", "wall-agent", "wall-plain"]
    assert claude.stat().st_mtime_ns == stamp and claude.read_text(encoding="utf-8") == text


def test_link_follows_a_moved_port(proj: Path, claude: Path):
    mcp_local.link(proj, BASE, PREFIX, claude)
    moved = mcp_local.link(proj, "http://127.0.0.1:9000/r/proj",
                           "http://127.0.0.1:8124/r/", claude)
    assert moved["added"] == ["wall", "wall-agent", "wall-plain"]


def test_link_never_clobbers_a_strangers_entry(proj: Path, claude: Path):
    cfg = json.loads(claude.read_text(encoding="utf-8"))
    cfg["projects"][proj.resolve().as_posix()] = {"mcpServers": {
        "wall": {"type": "stdio", "command": "my-own-wall"}}}
    claude.write_text(json.dumps(cfg), encoding="utf-8")
    out = mcp_local.link(proj, BASE, PREFIX, claude)
    assert out["conflicts"] == ["wall"]
    servers = json.loads(claude.read_text(encoding="utf-8"))[
        "projects"][proj.resolve().as_posix()]["mcpServers"]
    assert servers["wall"] == {"type": "stdio", "command": "my-own-wall"}
    assert servers["wall-agent"]["url"] == BASE + "/mcp/agent"


def test_link_uses_claude_codes_own_key_spelling(proj: Path, claude: Path):
    key = proj.resolve().as_posix() + "/"
    cfg = json.loads(claude.read_text(encoding="utf-8"))
    cfg["projects"][key] = {"hasTrustDialogAccepted": True}
    claude.write_text(json.dumps(cfg), encoding="utf-8")
    assert mcp_local.link(proj, BASE, PREFIX, claude)["key"] == key
    project = json.loads(claude.read_text(encoding="utf-8"))["projects"][key]
    assert project["hasTrustDialogAccepted"] is True and "wall" in project["mcpServers"]


def test_windows_keys_match_across_slashes_and_case():
    """A drive-letter key compares case- and slash-blind, as Windows paths do;
    a POSIX key stays case-sensitive."""
    assert mcp_local._norm("C:/Users/Me/Repo") == mcp_local._norm("c:\\users\\me\\repo\\")
    if os.name != "nt":
        assert mcp_local._norm("/home/Me") != mcp_local._norm("/home/me")


def test_link_refuses_an_unreadable_config(proj: Path, claude: Path):
    claude.write_text("{not json", encoding="utf-8")
    out = mcp_local.link(proj, BASE, PREFIX, claude)
    assert "unreadable" in out["error"]
    assert claude.read_text(encoding="utf-8") == "{not json"


def test_link_with_no_config_yet_creates_one(proj: Path, tmp_path: Path):
    path = tmp_path / "fresh" / ".claude.json"
    assert mcp_local.link(proj, BASE, PREFIX, path)["added"]
    assert "wall" in json.loads(path.read_text(encoding="utf-8"))["projects"][
        proj.resolve().as_posix()]["mcpServers"]


def test_a_repo_without_stdio_wall_entries_links_nothing(tmp_path: Path, claude: Path):
    before = claude.read_text(encoding="utf-8")
    out = mcp_local.link(tmp_path, BASE, PREFIX, claude)
    assert "nothing to shadow" in out["error"]
    assert claude.read_text(encoding="utf-8") == before


def test_unlink_removes_only_the_hosts_entries(proj: Path, claude: Path):
    before = json.loads(claude.read_text(encoding="utf-8"))
    mcp_local.link(proj, BASE, PREFIX, claude)
    cfg = json.loads(claude.read_text(encoding="utf-8"))
    cfg["projects"][proj.resolve().as_posix()]["mcpServers"]["mine"] = {
        "type": "http", "url": "http://127.0.0.1:9999/mine"}
    claude.write_text(json.dumps(cfg), encoding="utf-8")
    out = mcp_local.unlink(proj, PREFIX, claude)
    assert out["removed"] == ["wall", "wall-agent", "wall-plain"]
    after = json.loads(claude.read_text(encoding="utf-8"))
    assert after["projects"][proj.resolve().as_posix()]["mcpServers"] == {
        "mine": {"type": "http", "url": "http://127.0.0.1:9999/mine"}}
    del after["projects"][proj.resolve().as_posix()]
    assert after == before
    assert mcp_local.unlink(proj, PREFIX, claude)["removed"] == [], "absent is success"


def test_unlink_all_reaches_every_project(proj: Path, claude: Path, tmp_path: Path):
    other = tmp_path / "other"
    shutil.copytree(proj, other)
    mcp_local.link(proj, BASE, PREFIX, claude)
    mcp_local.link(other, PREFIX + "other", PREFIX, claude)
    out = mcp_local.unlink_all(PREFIX, claude)
    assert sorted(out["removed"]) == sorted([proj.resolve().as_posix(),
                                            other.resolve().as_posix()])
    assert mcp_local.linked(proj, PREFIX, claude) == {}
    kept = json.loads(claude.read_text(encoding="utf-8"))["projects"]["/elsewhere"]
    assert kept["mcpServers"]["wall"]["command"] == "keep-me"


def test_claude_config_path_honours_its_override(tmp_path: Path):
    assert mcp_local.claude_config_path({"CLAUDE_CONFIG_DIR": str(tmp_path)}) == \
        tmp_path / ".claude.json"
    assert mcp_local.claude_config_path({"HOME": str(tmp_path)}) == tmp_path / ".claude.json"


# ------------------------------------------------------------ wall host ...

def fake_adapter(installed=True):
    record = []
    return types.SimpleNamespace(
        record=record,
        verify=lambda: {"installed": installed, "running": True},
        install=lambda interval, python=None, sweeper=None: record.append(interval)
        or "fake timer every %ds" % interval,
        describe_install=lambda py, sw, iv: ["  schedule   fake --every %d" % iv])


def host_args(action, **kwargs):
    kwargs.setdefault("repo", ".")
    return types.SimpleNamespace(action=action, **kwargs)


@pytest.fixture()
def machine(home: Path, proj: Path, claude: Path, monkeypatch):
    register(home, ("proj", proj))
    adapter = fake_adapter()
    monkeypatch.setattr(service, "get_adapter", lambda system=None: adapter)
    health = {"service": host_mod.SERVICE, "ok": True, "pid": 42, "port": 8124,
              "repos": []}
    state = {"up": True, "started": 0}
    monkeypatch.setattr(service, "host_health",
                        lambda port, timeout=3.0: health if state["up"] else None)

    def start(env, port):
        state["started"] += 1
        return health if state["up"] else None

    monkeypatch.setattr(service, "_start_host", start)
    return types.SimpleNamespace(home=home, proj=proj, claude=claude, adapter=adapter,
                                 state=state)


def test_host_install_without_yes_changes_nothing(machine, capsys):
    before = machine.claude.read_text(encoding="utf-8")
    assert service.cmd_host(host_args("install", claude_config=str(machine.claude))) == 1
    out = capsys.readouterr().out
    assert "wall -> %s/r/proj/mcp/engineer" % "http://127.0.0.1:8124" in out
    assert "wall-agent -> http://127.0.0.1:8124/r/proj/mcp/agent" in out
    assert "fake --every %d" % service.WATCHDOG_INTERVAL_S in out
    assert not (machine.home / "host.json").exists()
    assert machine.claude.read_text(encoding="utf-8") == before
    assert machine.adapter.record == [] and machine.state["started"] == 0


def test_host_install_links_retimes_and_uninstall_reverts(machine):
    before = json.loads(machine.claude.read_text(encoding="utf-8"))
    assert service.cmd_host(host_args("install", yes=True,
                                      claude_config=str(machine.claude))) == 0
    cfg = json.loads((machine.home / "host.json").read_text(encoding="utf-8"))
    assert cfg["port"] == 8124 and cfg["command"][1].endswith("host.py")
    assert "host.json" in (machine.home / "sweep_all.py").read_text(encoding="utf-8")
    assert machine.adapter.record == [service.WATCHDOG_INTERVAL_S]
    assert mcp_local.linked(machine.proj, PREFIX, machine.claude) == {
        "wall": BASE + "/mcp/engineer", "wall-agent": BASE + "/mcp/agent",
        "wall-plain": BASE + "/mcp/engineer"}
    assert service.default_interval() == service.WATCHDOG_INTERVAL_S

    assert service.cmd_host(host_args("uninstall", claude_config=str(machine.claude))) == 0
    assert not (machine.home / "host.json").exists()
    assert machine.adapter.record[-1] == service.DEFAULT_INTERVAL_S
    after = json.loads(machine.claude.read_text(encoding="utf-8"))
    after["projects"].pop(machine.proj.resolve().as_posix())
    assert after == before
    assert service.default_interval() == service.DEFAULT_INTERVAL_S


def test_host_install_links_nothing_while_the_host_is_down(machine, capsys):
    machine.state["up"] = False
    before = machine.claude.read_text(encoding="utf-8")
    assert service.cmd_host(host_args("install", yes=True,
                                      claude_config=str(machine.claude))) == 1
    assert "NOT answering" in capsys.readouterr().err
    assert machine.claude.read_text(encoding="utf-8") == before, "no entry to a dead host"
    assert machine.adapter.record == [], "the timer keeps its sweeping cadence"
    assert (machine.home / "host.json").exists(), "the watchdog keeps retrying"


def test_host_link_refuses_while_the_host_is_down(machine):
    machine.state["up"] = False
    assert service.cmd_host(host_args("link", repo=str(machine.proj),
                                      claude_config=str(machine.claude))) == 1
    assert mcp_local.linked(machine.proj, PREFIX, machine.claude) == {}


def test_host_link_and_unlink_one_repo(machine):
    assert service.cmd_host(host_args("link", repo=str(machine.proj),
                                      claude_config=str(machine.claude))) == 0
    assert set(mcp_local.linked(machine.proj, PREFIX, machine.claude)) == {
        "wall", "wall-agent", "wall-plain"}
    assert service.cmd_host(host_args("unlink", repo=str(machine.proj),
                                      claude_config=str(machine.claude))) == 0
    assert mcp_local.linked(machine.proj, PREFIX, machine.claude) == {}


def test_host_link_needs_a_registered_repo(machine, tmp_path: Path):
    assert service.cmd_host(host_args("link", repo=str(tmp_path),
                                      claude_config=str(machine.claude))) == 1


def test_host_status_reports_the_seats(machine, capsys):
    service.cmd_host(host_args("install", yes=True, claude_config=str(machine.claude)))
    capsys.readouterr()
    assert service.cmd_host(host_args("status", claude_config=str(machine.claude))) == 0
    out = capsys.readouterr().out
    assert "pid 42" in out and "wall -> %s/mcp/engineer" % BASE in out


def test_wall_install_keeps_the_watchdog_cadence(machine):
    (machine.home / "host.json").write_text('{"port": 8124}', encoding="utf-8")
    service.cmd_install(types.SimpleNamespace(repo=str(machine.proj), yes=True))
    assert machine.adapter.record == [service.WATCHDOG_INTERVAL_S]


def test_doctor_flags_an_enabled_host_that_is_down(machine):
    (machine.home / "host.json").write_text('{"port": 8124}', encoding="utf-8")
    machine.state["up"] = False
    checks = {c["name"]: c for c in service.doctor_checks(
        machine.proj, adapter=machine.adapter)}
    assert checks["host"]["status"] == "fail"
    assert "wall host uninstall" in checks["host"]["detail"]
    machine.state["up"] = True
    checks = {c["name"]: c for c in service.doctor_checks(
        machine.proj, adapter=machine.adapter)}
    assert checks["host"]["status"] == "ok"


def test_doctor_has_no_host_check_when_it_is_not_enabled(machine):
    names = [c["name"] for c in service.doctor_checks(machine.proj, adapter=machine.adapter)]
    assert "host" not in names
