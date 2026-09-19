"""server -- a real server on an ephemeral port, asserted over real HTTP.

The four properties that matter are bind host, no-store, traversal refusal and
the allowlist, and none of them can be proved by reading the handler: they are
properties of what actually comes back over a socket. So the tests spin the
server, ask it, and read the answer.
"""

from __future__ import annotations

import http.client
import json
import sys
import threading
from pathlib import Path

import pytest

WALL_DIR = Path(__file__).resolve().parents[1] / "tools" / "wall"
if str(WALL_DIR) not in sys.path:
    sys.path.insert(0, str(WALL_DIR))

import server  # noqa: E402

SNAPSHOT = {
    "schema_version": 1,
    "generated_at": "2026-09-19T12:00:00.000Z",
    "repo": {"name": "demo"},
    "integrity": {},
    "crew": [],
    "board": {"arcs": []},
}


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    derived = tmp_path / ".wall" / "derived"
    derived.mkdir(parents=True)
    (derived / "wall.json").write_text(json.dumps(SNAPSHOT), encoding="utf-8")
    (derived / "wall.html").write_text("<html>the wall</html>", encoding="utf-8")
    (derived / "heartbeat.json").write_text('{"last_run": "2026-09-19T12:00:00Z"}',
                                            encoding="utf-8")
    (derived / "ledger.jsonl").write_text('{"event_id":"e1"}\n', encoding="utf-8")
    (derived / "secrets.json").write_text('{"token": "hunter2"}', encoding="utf-8")
    return tmp_path


@pytest.fixture()
def live(repo: Path):
    """A running server on an ephemeral port. Yields (port, address)."""
    httpd = server.make_server(repo, 0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield httpd.server_address
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


def get(port: int, path: str, method: str = "GET"):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        conn.request(method, path)
        response = conn.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        conn.close()


# --------------------------------------------------------------------- bind

def test_binds_localhost_only(live):
    host, port = live
    assert host == "127.0.0.1", "a LAN bind publishes ledger.jsonl to the network"
    assert server.BIND_HOST == "127.0.0.1"


def test_bind_host_is_not_configurable_from_the_cli():
    # Deliberate: a --host flag would turn the one property that keeps
    # ledger.jsonl off the network into something passable by accident.
    with pytest.raises(SystemExit):
        server.main(["--host", "0.0.0.0"])


# ------------------------------------------------------------------ serving

def test_serves_the_snapshot(live):
    status, headers, body = get(live[1], "/wall.json")
    assert status == 200
    assert json.loads(body)["schema_version"] == 1
    assert headers["Content-Type"].startswith("application/json")


def test_root_serves_the_wall_page(live):
    status, _, body = get(live[1], "/")
    assert status == 200 and b"the wall" in body


def test_all_four_allowlisted_files_are_reachable(live):
    for name in sorted(server.ALLOWLIST):
        status, _, _ = get(live[1], "/" + name)
        assert status == 200, "%s should be served" % name


# ----------------------------------------------------------------- no-store

@pytest.mark.parametrize("path", ["/wall.json", "/wall.html", "/heartbeat.json",
                                  "/ledger.jsonl"])
def test_polled_files_are_never_cacheable(live, path):
    _, headers, _ = get(live[1], path)
    assert "no-store" in headers["Cache-Control"], \
        "%s cached means a finished wave still reads as running" % path


def test_cache_buster_query_still_gets_no_store(live):
    _, headers, _ = get(live[1], "/wall.json?_=1758000000")
    assert "no-store" in headers["Cache-Control"]


# ---------------------------------------------------------------- allowlist

def test_a_file_in_the_directory_is_not_thereby_served(live, repo: Path):
    assert (repo / ".wall" / "derived" / "secrets.json").is_file()
    status, _, body = get(live[1], "/secrets.json")
    assert status == 404
    assert b"hunter2" not in body
    assert b"wall.json" in body, "the refusal should name what IS served"


def test_directory_listing_is_not_offered(live):
    status, _, _ = get(live[1], "/subdir/")
    assert status == 404


# ---------------------------------------------------------------- traversal

@pytest.mark.parametrize("path", [
    "/../../../etc/passwd",
    "/%2e%2e%2f%2e%2e%2fetc%2fpasswd",
    "/....//....//etc/passwd",
    "/..%5c..%5cwindows/win.ini",
])
def test_traversal_attempts_are_refused(live, path):
    status, _, body = get(live[1], path)
    assert status == 404
    assert b"root:" not in body


def test_a_symlink_escaping_the_directory_is_refused(repo: Path, tmp_path: Path):
    outside = tmp_path / "outside.json"
    outside.write_text('{"secret": true}', encoding="utf-8")
    link = repo / ".wall" / "derived" / "heartbeat.json"
    link.unlink()
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):  # pragma: no cover - platform dependent
        pytest.skip("symlinks unavailable here")
    target, reason = server.resolve_request(server.derived_dir(repo), "/heartbeat.json")
    assert target is None and "outside" in reason


def test_resolve_request_accepts_only_the_allowlist(repo: Path):
    root = server.derived_dir(repo)
    assert server.resolve_request(root, "/wall.json")[0] is not None
    assert server.resolve_request(root, "/secrets.json")[0] is None


def test_missing_file_says_what_to_run(repo: Path):
    (repo / ".wall" / "derived" / "ledger.jsonl").unlink()
    target, reason = server.resolve_request(server.derived_dir(repo), "/ledger.jsonl")
    assert target is None and "run-once" in reason


# --------------------------------------------------------------- write path

def test_writes_are_refused(live):
    conn = http.client.HTTPConnection("127.0.0.1", live[1], timeout=5)
    try:
        conn.request("POST", "/wall.json", body=b"{}")
        assert conn.getresponse().status == 501
    finally:
        conn.close()


def test_head_returns_headers_without_a_body(live):
    status, headers, body = get(live[1], "/wall.json", method="HEAD")
    assert status == 200 and body == b""
    assert int(headers["Content-Length"]) > 0


# -------------------------------------------------------------------- check

def test_check_passes_against_the_live_server(live):
    outcome = server.check(live[1])
    assert outcome["ok"] is True
    assert outcome["generated_at"] == SNAPSHOT["generated_at"]


def test_check_names_the_failure_when_nothing_is_listening():
    free = _free_port()
    outcome = server.check(free)
    assert outcome["ok"] is False and "nothing answered" in outcome["reason"]


def test_check_fails_a_server_that_serves_the_snapshot_cacheable():
    def cacheable(url, timeout):
        return 200, {"Cache-Control": "max-age=60"}, json.dumps(SNAPSHOT).encode()

    outcome = server.check(1, fetch_fn=cacheable)
    assert outcome["ok"] is False and "no-store" in outcome["reason"]


def test_check_names_a_non_wall_server_on_the_port():
    def squatter(url, timeout):
        return 200, {"Cache-Control": "no-store"}, b'{"hello": "i am not a wall"}'

    outcome = server.check(1, fetch_fn=squatter)
    assert outcome["ok"] is False and "not a wall snapshot" in outcome["reason"]


# ---------------------------------------------------------------- utilities

@pytest.mark.parametrize("path, expected", [
    ("/", "wall.html"),
    ("", "wall.html"),
    ("/wall.json", "wall.json"),
    ("/wall.json?_=12", "wall.json"),
    ("/a/b/wall.json", "wall.json"),
    ("/wall.json#frag", "wall.json"),
])
def test_requested_name(path, expected):
    assert server.requested_name(path) == expected


def test_serve_refuses_before_the_first_sweep(tmp_path: Path, capsys):
    assert server.serve(tmp_path, 0) == 1
    assert "run-once" in capsys.readouterr().err


def _free_port() -> int:
    import socket
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]
