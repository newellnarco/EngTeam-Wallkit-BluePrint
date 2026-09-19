#!/usr/bin/env python3
"""Server -- serves .wall/derived/ on 127.0.0.1 so the wall can poll its snapshot.

Opening ``wall.html`` from ``file://`` works (the courier inlines the snapshot
and the page meta-refreshes), but the served mode is better: the page polls
``wall.json`` every ten seconds and repaints in place, so scroll position, the
active tab and focus all survive. That needs an origin, which needs a server.

Four safety properties, copied from MAX3's ``tools/board_wall_server.py`` which
has been serving this exact page in production:

1. **Bind 127.0.0.1 explicitly.** ``.wall/derived/`` also holds
   ``ledger.jsonl`` and ``heartbeat.json``, so a ``0.0.0.0`` bind publishes the
   full event history to anything on the network. The host is a module
   constant, not a flag.
2. **No-store on the polled files.** A cached snapshot shows a finished wave as
   still running, which is the one thing a live status board must never do.
3. **Path-traversal safe.** Every request resolves to a real path and is
   refused unless that path is inside the derived directory.
4. **A tiny exact allowlist.** Four filenames. Not a prefix rule, not a
   directory listing: the derived directory is a working area and a rule that
   serves whatever lands there is a rule that serves the next thing that lands
   there.

The handler implements GET and HEAD only, so writes are 501 whatever the path.

Usage::

    python server.py --repo .              # foreground, 127.0.0.1:8123
    python server.py --repo . --port 9123
    python server.py --check               # probe an already-running server
"""

from __future__ import annotations

import argparse
import http.server
import json
import socket
import sys
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

#: Localhost only. Deliberately not configurable -- see property 1 above.
BIND_HOST = "127.0.0.1"

DEFAULT_PORT = 8123

#: Exactly what may be served. wall.html is the page; wall.json is what it
#: polls; heartbeat.json is how it knows the courier is alive; ledger.jsonl is
#: the full history the Ledger tab reads.
ALLOWLIST = frozenset({"wall.html", "wall.json", "heartbeat.json", "ledger.jsonl"})

#: The page itself and every machine-readable file it polls. Serving any of
#: these from cache turns a stale wall into one that looks current.
NO_STORE_SUFFIXES = (".json", ".jsonl")

NO_STORE_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
}

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".jsonl": "application/x-ndjson; charset=utf-8",
}

#: Cap on any single response. The snapshot is small; the ledger grows. A
#: request for a ledger larger than this is answered 413 with the reason rather
#: than read wholly into memory on a long-lived server.
MAX_BYTES = 32 * 1024 * 1024


def derived_dir(repo: Path | str) -> Path:
    """The directory this server is rooted at."""
    return Path(repo).resolve() / ".wall" / "derived"


def requested_name(path: str) -> str:
    """The basename a request asks for, query string and trailing slash removed.

    ``/`` and ``""`` mean the page itself: the wall is the only thing here a
    person opens by hand.
    """
    bare = path.split("?", 1)[0].split("#", 1)[0]
    name = bare.rstrip("/").rsplit("/", 1)[-1]
    return name or "wall.html"


def is_allowed(name: str) -> bool:
    """True when ``name`` is one of the four files this server may serve."""
    return name in ALLOWLIST


def wants_no_store(name: str) -> bool:
    """True when ``name`` must never be served from cache."""
    return name == "wall.html" or name.endswith(NO_STORE_SUFFIXES)


def content_type(name: str) -> str:
    return CONTENT_TYPES.get("." + name.rsplit(".", 1)[-1], "application/octet-stream")


def resolve_request(root: Path, path: str) -> tuple[Path | None, str]:
    """``(file, "")`` for a servable request, or ``(None, reason)``.

    Two independent gates, both required. The allowlist decides what may be
    named; the resolve-and-prefix check decides where the named thing may live.
    Either alone is a hole: a symlink named ``wall.json`` passes the allowlist,
    and ``../../secrets`` passes nothing but would pass a looser name rule.
    """
    name = requested_name(path)
    if not is_allowed(name):
        return None, "not served: %r is not one of %s" % (name, sorted(ALLOWLIST))
    try:
        root_resolved = root.resolve()
        candidate = (root_resolved / name).resolve()
    except OSError as exc:
        return None, "cannot resolve %r: %s" % (name, exc)
    try:
        candidate.relative_to(root_resolved)
    except ValueError:
        return None, "refused: %r resolves outside the derived directory" % name
    if not candidate.is_file():
        return None, "not found: %s has not been written yet (run `wall run-once`)" % name
    return candidate, ""


class WallHandler(http.server.BaseHTTPRequestHandler):
    """Serve the four derived files, read-only, uncached, traversal-checked."""

    server_version = "wall-kit"
    sys_version = ""  # do not advertise the Python version to anything local

    def version_string(self) -> str:  # stdlib naming
        return self.server_version

    #: Set by make_server(); a class attribute so the stdlib can instantiate us.
    root: Path = Path(".")
    quiet: bool = True

    def do_GET(self) -> None:  # stdlib naming
        self._respond(body=True)

    def do_HEAD(self) -> None:  # stdlib naming
        self._respond(body=False)

    def _respond(self, *, body: bool) -> None:
        target, reason = resolve_request(self.root, self.path)
        if target is None:
            self._send_json(404, {"error": reason, "served": sorted(ALLOWLIST)},
                            body=body, name="")
            return
        try:
            if target.stat().st_size > MAX_BYTES:
                self._send_json(413, {"error": "%s exceeds the %d-byte serve cap"
                                               % (target.name, MAX_BYTES)},
                                body=body, name="")
                return
            payload = target.read_bytes()
        except OSError as exc:
            self._send_json(500, {"error": "could not read %s: %s" % (target.name, exc)},
                            body=body, name="")
            return
        self._send(200, content_type(target.name), payload, body=body, name=target.name)

    def _send_json(self, status: int, payload: dict, *, body: bool, name: str) -> None:
        self._send(status, CONTENT_TYPES[".json"],
                   json.dumps(payload).encode("utf-8"), body=body, name=name)

    def _send(self, status: int, ctype: str, payload: bytes, *,
              body: bool, name: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(payload)))
        if not name or wants_no_store(name):
            for key, value in NO_STORE_HEADERS.items():
                self.send_header(key, value)
        self.end_headers()
        if body:
            self.wfile.write(payload)

    def log_message(self, fmt: str, *args) -> None:  # stdlib naming
        if not self.quiet:
            sys.stderr.write("[wall-server] %s %s\n" % (self.address_string(), fmt % args))


def make_server(repo: Path | str, port: int = DEFAULT_PORT, *,
                quiet: bool = True) -> http.server.ThreadingHTTPServer:
    """Build (but do not run) the server bound to 127.0.0.1:port.

    ``port=0`` binds an ephemeral port; read it back from
    ``server.server_address[1]``. Raises ``OSError`` when the port is taken --
    the caller decides whether that is fatal.
    """
    root = derived_dir(repo)
    handler = type("BoundWallHandler", (WallHandler,), {"root": root, "quiet": quiet})
    return http.server.ThreadingHTTPServer((BIND_HOST, port), handler)


def _default_fetch(url: str, timeout: float) -> tuple[int, dict, bytes]:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return response.status, dict(response.headers), response.read(MAX_BYTES)


def check(port: int = DEFAULT_PORT, *,
          fetch_fn: Callable[[str, float], tuple[int, dict, bytes]] = _default_fetch,
          timeout: float = 2.0) -> dict:
    """Probe an already-running server. Never raises.

    Returns ``{"ok", "reason", "url", "generated_at", "no_store"}``. ``ok`` means
    a wall server answered with a parseable snapshot AND said not to cache it --
    a server that serves the snapshot cacheable is serving a wall that can go
    quietly stale, which is the failure this whole file is shaped around.
    """
    url = "http://%s:%d/wall.json" % (BIND_HOST, port)
    out = {"ok": False, "reason": "", "url": url, "generated_at": None, "no_store": False}
    try:
        status, headers, payload = fetch_fn(url, timeout)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        out["reason"] = "nothing answered at %s: %s: %s" % (url, type(exc).__name__, exc)
        return out
    if status != 200:
        out["reason"] = "server answered HTTP %s" % status
        return out
    cache_control = ""
    for key, value in headers.items():
        if key.lower() == "cache-control":
            cache_control = value
    out["no_store"] = "no-store" in cache_control.lower()
    try:
        snapshot = json.loads(payload.decode("utf-8", errors="replace"))
    except ValueError as exc:
        out["reason"] = "wall.json did not parse: %s" % exc
        return out
    if not isinstance(snapshot, dict) or "generated_at" not in snapshot:
        out["reason"] = "wall.json is not a wall snapshot"
        return out
    out["generated_at"] = snapshot.get("generated_at")
    if not out["no_store"]:
        out["reason"] = "served without no-store -- the wall could cache stale state"
        return out
    out["ok"] = True
    out["reason"] = "serving, snapshot generated at %s" % out["generated_at"]
    return out


def serve(repo: Path | str, port: int = DEFAULT_PORT, *, quiet: bool = True) -> int:
    """Run in the foreground until interrupted. 0 on clean exit, 1 on bind failure."""
    root = derived_dir(repo)
    if not root.is_dir():
        print("[wall-server] %s does not exist -- run `wall run-once` first" % root,
              file=sys.stderr)
        return 1
    try:
        httpd = make_server(repo, port, quiet=quiet)
    except OSError as exc:
        print("[wall-server] cannot bind %s:%d: %s" % (BIND_HOST, port, exc), file=sys.stderr)
        return 1
    bound = httpd.server_address[1]
    print("[wall-server] serving %s on http://%s:%d/wall.html" % (root, BIND_HOST, bound))
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0


def port_is_free(port: int, host: str = BIND_HOST) -> bool:
    """True when nothing is listening on ``host:port``. Advisory, racy by nature."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.5)
        return probe.connect_ex((host, port)) != 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="wall-server",
                                     description="Serve .wall/derived/ on 127.0.0.1.")
    parser.add_argument("--repo", default=".", help="repo root containing .wall/")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--check", action="store_true",
                        help="probe an already-running server instead of starting one")
    parser.add_argument("--verbose", action="store_true", help="log every request")
    args = parser.parse_args(argv)

    if args.check:
        outcome = check(args.port)
        print("[wall-server] %s -- %s" % ("ok" if outcome["ok"] else "FAIL", outcome["reason"]))
        return 0 if outcome["ok"] else 1
    return serve(args.repo, args.port, quiet=not args.verbose)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
