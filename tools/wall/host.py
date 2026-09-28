#!/usr/bin/env python3
"""wall-host -- the one resident wall process per machine (DEC-0037).

Two things used to start interpreters on a schedule or per client, and this
process does both from ONE interpreter instead:

* **MCP for every registered repo.** Every MCP client session opened in a
  repo whose ``.mcp.json`` runs ``mcp_server.py`` over stdio used to start
  its own interpreter per configured seat. The host serves the same
  ``handle_request`` over loopback Streamable HTTP (DEC-0036) for every repo
  in ``~/.wall/registry.json``, one path per repo and role::

      POST http://127.0.0.1:8124/r/<name>/mcp/engineer
      POST http://127.0.0.1:8124/r/<name>/mcp/agent
      GET  http://127.0.0.1:8124/health

  Clients on this machine reach it through Claude Code's LOCAL scope
  (``mcp_local.py``); the committed ``.mcp.json`` stays stdio, so a machine
  without the host -- a cloud session, CI -- is unchanged.

* **The courier sweep.** The machine timer used to start ``sweep_all.py``
  every two minutes, and that started one more interpreter per repo for
  ``wall run-once``. The host sweeps on the same interval, in-process, for
  every repo whose vendored ``tools/wall`` is byte-identical to the code the
  host is running; a repo on a different kit version is swept exactly as
  before, in a subprocess of its own ``wall.py``. The heartbeat, log and
  registry pruning are the sweeper's, line for line. The timer stays, as a
  watchdog at a relaxed interval: while the host answers ``/health`` the
  sweeper exits at once; when it does not, the sweeper sweeps itself and
  restarts the host.

Single instance by construction: the listener's bind is exclusive
(``mcp_server.ExclusiveHTTPServer``), so a second host exits at once with
"already running" and exit code 0. The host runs while ``~/.wall/host.json``
exists; ``wall host uninstall`` deletes it and the host exits within seconds.

Stdlib only (DEC-0017). Loopback only (DEC-0036). No network beyond that.

Run:  python tools/wall/host.py            (reads ~/.wall/host.json)
      python tools/wall/host.py --once     (one sweep, no server)
"""

from __future__ import annotations

import argparse
import contextlib
import errno
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
import types
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import mcp_server  # noqa: E402

#: What ``/health`` names itself, so a probe can tell the host from some
#: other server that happens to hold the port.
SERVICE = "wall-host"
HOST_CONFIG_NAME = "host.json"
DEFAULT_PORT = mcp_server.DEFAULT_HTTP_PORT
#: The courier's cadence, unchanged from the timer it replaces.
DEFAULT_SWEEP_INTERVAL_S = 120
#: How often the host checks that it should still be running.
TICK_S = 5
#: The sweeper's own bounds, so a folded sweep behaves exactly like one.
SWEEP_TIMEOUT_S = 240
LOG_MAX_BYTES = 1000000
REPO_PREFIX = "/r/"
#: One place to ask, so the Windows paths are testable anywhere.
IS_WINDOWS = os.name == "nt"

_SLUG_BAD = re.compile(r"[^A-Za-z0-9._-]+")


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def slug(name: str) -> str:
    """A registry name as one URL path segment: ``My Repo`` -> ``My-Repo``."""
    out = _SLUG_BAD.sub("-", str(name)).strip("-.")
    return out or "repo"


def repo_base_url(port: int, name: str, host: str = "127.0.0.1") -> str:
    """Where one repo's seats live: append ``/mcp/<role>``."""
    return "http://%s:%d%s%s" % (host, port, REPO_PREFIX, slug(name))


def kit_fingerprint(kit_dir: Path) -> str | None:
    """sha256 over every file of a ``tools/wall`` tree (paths and bytes),
    caches excluded. None when the tree is absent.

    Equal fingerprints mean the repo vendors exactly the code this host runs,
    so an in-process sweep is the sweep that repo's own ``wall run-once``
    would have done."""
    if not kit_dir.is_dir():
        return None
    digest = hashlib.sha256()
    for path in sorted(kit_dir.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        digest.update(path.relative_to(kit_dir).as_posix().encode("utf-8") + b"\0")
        try:
            digest.update(path.read_bytes())
        except OSError:
            return None
        digest.update(b"\0")
    return digest.hexdigest()


def host_command(home: Path, python: str | None = None) -> list[str]:
    """The argv that starts this host: the windowless interpreter on Windows
    (a console binary would flash a window -- ``install.windows``)."""
    python = python or sys.executable
    if IS_WINDOWS:
        from install import windows
        python = windows.windowless_python(python)
    return [python, str(HERE / "host.py"), "--home", str(home)]


def spawn_detached(argv: list[str]) -> int:
    """Start ``argv`` so it outlives the caller (a sweep task, an installer).
    Returns its pid. The generated sweeper (``service.SWEEPER_SOURCE``)
    carries the same flags in its ``start_host``: it runs without the kit.

    On Windows it breaks away from the caller's job object where the job
    allows it -- a scheduled task's job may otherwise take the host down
    with the task -- and runs detached without a console. Elsewhere it
    starts a new session."""
    kwargs = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL,
              "stderr": subprocess.DEVNULL, "close_fds": True}
    if not IS_WINDOWS:
        return subprocess.Popen(argv, start_new_session=True, **kwargs).pid
    flags = (getattr(subprocess, "DETACHED_PROCESS", 0x8)
             | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x200))
    breakaway = getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0x1000000)
    try:
        return subprocess.Popen(argv, creationflags=flags | breakaway, **kwargs).pid
    except OSError:  # the job forbids breakaway: start inside it instead
        return subprocess.Popen(argv, creationflags=flags, **kwargs).pid


def read_host_config(home: Path) -> dict | None:
    """``host.json`` as a dict, or None when the host is not enabled."""
    try:
        payload = json.loads((home / HOST_CONFIG_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def read_rows(home: Path) -> list[dict]:
    """The registry's rows; empty on anything unreadable (the sweep logs it)."""
    payload = json.loads((home / "registry.json").read_text(encoding="utf-8"))
    return [r for r in payload.get("repos", []) if isinstance(r, dict) and r.get("path")]


def _write_json(path: Path, payload: dict) -> None:
    try:
        tmp = path.with_name(".tmp-host-%d-%s" % (os.getpid(), path.name))
        tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        tmp.replace(path)
    except OSError:
        pass


class Host:
    """The resident host: routes, health and the folded sweep. No sockets
    here -- ``serve`` binds; everything below is testable without one."""

    def __init__(self, home: Path, port: int = DEFAULT_PORT,
                 interval_s: int = DEFAULT_SWEEP_INTERVAL_S,
                 kit_dir: Path = HERE, python: str = sys.executable):
        self.home = Path(home)
        self.port = port
        self.interval_s = max(10, int(interval_s))
        self.kit_dir = Path(kit_dir)
        self.python = python
        self.fingerprint = kit_fingerprint(self.kit_dir)
        self.started = now()
        self._started_at = time.monotonic()
        self._swept_at: float | None = None
        self.last_sweep: dict | None = None
        self.stop = threading.Event()
        #: Set when the kit this host runs from changed on disk (an
        #: upgrade): ``serve`` then hands the port to a fresh host.
        self.restart = False

    # ----------------------------------------------------------- routing

    def routes(self) -> dict[str, Path]:
        """``{slug: repo}`` for every live registered repo. A slug two rows
        share serves neither: a guessed repo would answer for the wrong one."""
        try:
            rows = read_rows(self.home)
        except (OSError, ValueError):
            return {}
        seen: dict[str, list[Path]] = {}
        for row in rows:
            path = Path(row["path"])
            seen.setdefault(slug(row.get("name") or path.name), []).append(path)
        return {name: paths[0] for name, paths in seen.items()
                if len(paths) == 1 and paths[0].is_dir()}

    def route(self, path: str):
        """``/r/<name>/mcp/<role>`` -> ``(repo, role)``; anything else None."""
        path = urllib.parse.urlsplit(path).path
        if not path.startswith(REPO_PREFIX):
            return None
        name, sep, rest = path[len(REPO_PREFIX):].partition("/")
        if not sep:
            return None
        role = mcp_server.role_for_path("/" + rest)
        repo = self.routes().get(name)
        if role is None or repo is None:
            return None
        return repo, role

    def health(self) -> dict:
        repos = []
        for name, repo in sorted(self.routes().items()):
            repos.append({"name": name, "path": str(repo),
                          "kit_match": kit_fingerprint(repo / "tools" / "wall")
                          == self.fingerprint})
        # ok means SWEEPING, not merely listening: a host whose sweep loop
        # stalled answers ok=false, and the watchdog sweeps in its place.
        since = self._swept_at if self._swept_at is not None else self._started_at
        fresh = time.monotonic() - since <= 3 * self.interval_s
        return {"ok": fresh and not self.stop.is_set(), "service": SERVICE,
                "pid": os.getpid(),
                "port": self.port, "started": self.started,
                "kit": str(self.kit_dir), "sweep_interval_s": self.interval_s,
                "last_sweep": (self.last_sweep or {}).get("last_sweep"),
                "repos": repos}

    # ------------------------------------------------------------- sweep

    def log(self, line: str) -> None:
        log = self.home / "courier.log"
        try:
            if log.exists() and log.stat().st_size > LOG_MAX_BYTES:
                tail = log.read_text(encoding="utf-8", errors="replace").splitlines()[-2000:]
                log.write_text("\n".join(tail) + "\n", encoding="utf-8")
            with log.open("a", encoding="utf-8") as handle:
                handle.write("%s %s\n" % (now(), line))
        except OSError:
            pass

    def _sweep_in_process(self, repo: Path) -> tuple[bool, str]:
        """``wall run-once`` for one repo, in this interpreter. Goes through
        the verb tools' own capture, which serialises CLI calls on
        ``_CLI_LOCK`` and routes this thread's output only (DEC-0036
        amended) -- so a sweep never interleaves a ledger write with a
        concurrent ``wall_answer``."""
        import wall as wall_mod
        rc, out = mcp_server._capture_cli(
            wall_mod.cmd_run_once,
            types.SimpleNamespace(repo=str(repo), rebuild=False))
        lines = out.strip().splitlines()
        return rc in (0, None), lines[-1] if lines else "no output"

    def _sweep_subprocess(self, wall_py: Path, repo: Path) -> tuple[bool, str]:
        """The sweeper's own call, unchanged: the repo's own ``wall.py``."""
        try:
            done = subprocess.run(
                [self.python, str(wall_py), "--repo", str(repo), "run-once"],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=SWEEP_TIMEOUT_S, check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            detail = (done.stdout or done.stderr).strip().splitlines()
            return done.returncode == 0, detail[-1] if detail else "no output"
        except subprocess.TimeoutExpired:
            return False, "timed out after %ss" % SWEEP_TIMEOUT_S
        except (OSError, ValueError) as exc:
            return False, "could not run: %s" % exc

    def sweep(self) -> dict:
        """One pass over the registry -- ``sweep_all.py``'s contract: dead
        paths dropped, ``last_seen`` stamped, heartbeat and log written."""
        registry, heartbeat = self.home / "registry.json", self.home / "heartbeat.json"
        try:
            rows = read_rows(self.home)
        except (OSError, ValueError) as exc:
            self.log("registry unreadable: %s" % exc)
            beat = {"last_sweep": now(), "ok": False, "error": str(exc)}
            _write_json(heartbeat, beat)
            self.last_sweep = beat
            self._swept_at = time.monotonic()
            return beat
        kept, results = [], []
        for row in rows:
            repo = Path(row["path"])
            if not repo.is_dir():
                self.log("dropped %s -- path no longer exists" % repo)
                continue
            kept.append(row)
            wall_py = repo / "tools" / "wall" / "wall.py"
            if not wall_py.is_file():
                results.append({"path": str(repo), "ok": False,
                                "detail": "no tools/wall/wall.py"})
                self.log("%s: no tools/wall/wall.py" % repo)
                continue
            same_kit = (self.fingerprint is not None and
                        kit_fingerprint(repo / "tools" / "wall") == self.fingerprint)
            if same_kit:
                try:
                    ok, detail = self._sweep_in_process(repo)
                except Exception as exc:  # one repo must not stop the sweep
                    ok, detail = False, "%s: %s" % (type(exc).__name__, exc)
            else:
                ok, detail = self._sweep_subprocess(wall_py, repo)
            results.append({"path": str(repo), "ok": ok, "detail": detail,
                            "in_process": same_kit})
            self.log("%s: %s -- %s" % (repo, "ok" if ok else "FAILED", detail))
            if ok:
                row["last_seen"] = now()
        _write_json(registry, {"repos": kept})
        beat = {"last_sweep": now(),
                "ok": all(r["ok"] for r in results) if results else True,
                "repos": len(kept), "results": results,
                "host": {"pid": os.getpid(), "port": self.port}}
        _write_json(heartbeat, beat)
        self.last_sweep = beat
        self._swept_at = time.monotonic()
        return beat

    def enabled(self) -> bool:
        return (self.home / HOST_CONFIG_NAME).is_file()

    def run_loop(self, server=None) -> None:
        """Sweep every interval until ``host.json`` goes away or ``stop``."""
        next_sweep = 0.0
        while not self.stop.is_set():
            if not self.enabled():
                self.log("host.json removed -- host exiting")
                break
            if time.monotonic() >= next_sweep:
                on_disk = kit_fingerprint(self.kit_dir)
                # A kit that vanished (its repo deleted) is no reason to exit:
                # the replacement could not start, and the loaded code still works.
                if on_disk is not None and on_disk != self.fingerprint:
                    # Serving yesterday's code to every client until someone
                    # notices is the drift this kit exists to prevent.
                    self.log("kit at %s changed on disk -- restarting the host"
                             % self.kit_dir)
                    self.restart = True
                    break
                try:
                    self.sweep()
                except Exception as exc:  # the loop outlives any one pass
                    self.log("sweep failed: %s: %s" % (type(exc).__name__, exc))
                next_sweep = time.monotonic() + self.interval_s
            self.stop.wait(TICK_S)
        self.stop.set()
        if server is not None:
            server.shutdown()


def serve(home: Path, port: int, interval_s: int) -> int:
    host = Host(home, port, interval_s)
    try:
        server = mcp_server.make_routed_server(host.route, "127.0.0.1", port,
                                               health=host.health)
    except OSError as exc:
        if exc.errno in (errno.EADDRINUSE, getattr(errno, "WSAEADDRINUSE", -1)) \
                or getattr(exc, "winerror", None) in (10048, 10013):
            print("[wall-host] already running on 127.0.0.1:%d -- exiting" % port,
                  file=sys.stderr)
            return 0
        raise
    host.log("host started pid %d on 127.0.0.1:%d" % (os.getpid(), port))
    sweeper = threading.Thread(target=host.run_loop, args=(server,),
                               name="wall-host-sweep", daemon=True)
    sweeper.start()
    try:
        server.serve_forever(poll_interval=1.0)
    except KeyboardInterrupt:
        pass
    finally:
        host.stop.set()
        server.server_close()
    if host.restart:
        spawn_detached(host_command(home))
    return 0


def main(argv: list[str] | None = None) -> int:
    import service  # the one definition of the wall home (WALL_HOME honoured)
    p = argparse.ArgumentParser(prog="wall-host", description=__doc__.split("\n")[0])
    p.add_argument("--home", help="wall home (default: ~/.wall, or WALL_HOME)")
    p.add_argument("--port", type=int, help="default: host.json's, else %d" % DEFAULT_PORT)
    p.add_argument("--interval", type=int,
                   help="sweep seconds (default: host.json's, else %d)"
                        % DEFAULT_SWEEP_INTERVAL_S)
    p.add_argument("--once", action="store_true", help="one sweep, no server")
    a = p.parse_args(argv)
    home = Path(a.home).expanduser() if a.home else service.wall_home()
    cfg = read_host_config(home) or {}
    port = int(a.port or cfg.get("port") or DEFAULT_PORT)
    interval = int(a.interval or cfg.get("interval") or DEFAULT_SWEEP_INTERVAL_S)
    if a.once:
        beat = Host(home, port, interval).sweep()
        print(json.dumps(beat, indent=1))
        return 0 if beat.get("ok") else 1
    if not cfg:
        print("[wall-host] no %s in %s -- enable it with `wall host install --yes`"
              % (HOST_CONFIG_NAME, home), file=sys.stderr)
        return 1
    # pythonw has no console streams; nothing here needs them.
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            with contextlib.suppress(Exception):
                stream.reconfigure(encoding="utf-8")
    return serve(home, port, interval)


if __name__ == "__main__":
    sys.exit(main())
