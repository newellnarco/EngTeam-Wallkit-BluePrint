#!/usr/bin/env python3
"""mcp_local -- point one machine's Claude Code at the shared host (DEC-0037).

A repo's committed ``.mcp.json`` runs the wall over stdio, and it must keep
doing so: a cloud session or a CI runner has no host behind a loopback URL.
On a machine that DOES run the host (``host.py``), each Claude Code session
opened in the repo would still start its own stdio interpreters -- one per
configured seat -- unless something outranks the project entry.

Claude Code's LOCAL scope does. A local-scope server is private to one user
and one project path, lives in the user's ``~/.claude.json`` under
``projects[<path>].mcpServers``, and takes precedence over a project-scope
(``.mcp.json``) server of the same name. So this module writes, for every
stdio entry in the repo's ``.mcp.json`` that runs ``tools/wall/mcp_server.py``,
a local-scope entry of the SAME NAME pointing at the host::

    "wall":       {"type": "http", "url": "http://127.0.0.1:8124/r/<repo>/mcp/engineer"}
    "wall-agent": {"type": "http", "url": "http://127.0.0.1:8124/r/<repo>/mcp/agent"}

The role comes from the stdio entry's own ``--role`` (engineer when absent),
so a seat never changes role on the way over. The equivalent by hand::

    claude mcp add --scope local --transport http wall http://127.0.0.1:8124/r/<repo>/mcp/engineer

Rules, each pinned by a test:

* **Idempotent.** An entry already equal is not rewritten; a file with no
  change is not touched at all.
* **Preserves everything else.** Other projects, other servers, every other
  key of ``~/.claude.json`` round-trip unchanged.
* **Never clobbers a stranger.** A local entry of the same name that does not
  point at this host's ``/r/`` paths is the user's own: it is reported as a
  conflict and left alone. ``unlink`` removes only entries pointing at the
  host.
* **Refuses a config it cannot read.** Invalid JSON is named, never
  overwritten.
* **Uses Claude Code's own key.** When ``projects`` already has a key for the
  repo (Claude Code writes one the first time the project is opened), that
  exact spelling is used, whatever its slashes or case; a new key is the
  resolved path in forward-slash form.

``~/.claude.json`` is also written by running Claude Code sessions, which
can overwrite a change made underneath them. Link with sessions closed, or
re-run ``wall host link`` after; ``wall host status`` shows what is there.

Stdlib only (DEC-0017). Writes one file, atomically. No network.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

#: The script a stdio wall entry runs; how its entries are recognised.
MCP_SCRIPT = "mcp_server.py"


def claude_config_path(env: dict | None = None) -> Path:
    """``~/.claude.json`` (``$CLAUDE_CONFIG_DIR/.claude.json`` when set)."""
    env = os.environ if env is None else env
    override = (env.get("CLAUDE_CONFIG_DIR") or "").strip()
    if override:
        return Path(override).expanduser() / ".claude.json"
    base = env.get("USERPROFILE") or env.get("HOME") or os.path.expanduser("~")
    return Path(base).expanduser() / ".claude.json"


def wall_stdio_entries(repo: Path) -> dict[str, str]:
    """``{server name: role}`` for every stdio entry of the repo's
    ``.mcp.json`` that runs the wall's MCP server. Empty when there is none,
    or the file is absent or unreadable (nothing to shadow)."""
    try:
        cfg = json.loads((Path(repo) / ".mcp.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    servers = cfg.get("mcpServers") if isinstance(cfg, dict) else None
    out: dict[str, str] = {}
    for name, entry in (servers or {}).items():
        if not isinstance(entry, dict) or entry.get("type") not in (None, "stdio"):
            continue
        args = [str(a) for a in entry.get("args") or []]
        if not any(a.replace("\\", "/").endswith("tools/wall/" + MCP_SCRIPT)
                   for a in args) or "--http" in args:
            continue
        role = "engineer"
        if "--role" in args and args.index("--role") + 1 < len(args):
            role = args[args.index("--role") + 1]
        out[name] = role
    return out


def _norm(path: str) -> str:
    text = path.replace("\\", "/").rstrip("/")
    return text.lower() if os.name == "nt" or (len(text) > 1 and text[1] == ":") else text


def project_key(projects: dict, repo: Path) -> str:
    """The ``projects`` key for ``repo``: Claude Code's own when present."""
    resolved = Path(repo).resolve()
    want = _norm(resolved.as_posix())
    for key in projects:
        if _norm(key) == want:
            return key
    return resolved.as_posix()


def _read(config_path: Path) -> tuple[dict | None, str | None]:
    if not config_path.exists():
        return {}, None
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return None, "%s is unreadable (%s) -- fix it by hand, never by overwrite" % (
            config_path, exc)
    if not isinstance(payload, dict):
        return None, "%s is not a JSON object -- not ours to touch" % config_path
    return payload, None


def _write(config_path: Path, payload: dict) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = config_path.with_name(".tmp-wall-%d-%s" % (os.getpid(), config_path.name))
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    tmp.replace(config_path)


def _ours(entry, host_prefix: str) -> bool:
    return (isinstance(entry, dict) and entry.get("type") == "http"
            and str(entry.get("url") or "").startswith(host_prefix))


def link(repo: Path, base_url: str, host_prefix: str,
         config_path: Path | None = None) -> dict:
    """Write the local-scope HTTP twins of the repo's stdio wall entries.

    ``base_url`` is the repo's root on the host (``.../r/<name>``); each entry
    gets ``<base_url>/mcp/<role>``. ``host_prefix`` (``http://127.0.0.1:<port>/r/``)
    is what marks an entry as the host's. Returns ``{"key", "added",
    "unchanged", "conflicts", "error"}``.
    """
    config_path = config_path or claude_config_path()
    out = {"key": None, "added": [], "unchanged": [], "conflicts": [], "error": None}
    entries = wall_stdio_entries(repo)
    if not entries:
        out["error"] = ("no stdio wall entry in %s -- nothing to shadow"
                        % (Path(repo) / ".mcp.json"))
        return out
    payload, error = _read(config_path)
    if error:
        out["error"] = error
        return out
    projects = payload.setdefault("projects", {})
    if not isinstance(projects, dict):
        out["error"] = "%s: 'projects' is not an object" % config_path
        return out
    key = out["key"] = project_key(projects, repo)
    project = projects.setdefault(key, {})
    servers = project.setdefault("mcpServers", {})
    for name, role in sorted(entries.items()):
        want = {"type": "http", "url": "%s/mcp/%s" % (base_url.rstrip("/"), role)}
        have = servers.get(name)
        if have == want:
            out["unchanged"].append(name)
        elif have is None or _ours(have, host_prefix):
            servers[name] = want
            out["added"].append(name)
        else:
            out["conflicts"].append(name)
    if out["added"]:
        try:
            _write(config_path, payload)
        except OSError as exc:
            out["error"] = "could not write %s: %s" % (config_path, exc)
            out["added"] = []
    return out


def unlink(repo: Path, host_prefix: str, config_path: Path | None = None) -> dict:
    """Remove this repo's local-scope entries that point at the host -- and
    only those. Returns ``{"key", "removed", "error"}``; absent is success."""
    config_path = config_path or claude_config_path()
    out = {"key": None, "removed": [], "error": None}
    payload, error = _read(config_path)
    if error:
        out["error"] = error
        return out
    projects = payload.get("projects")
    if not isinstance(projects, dict):
        return out
    key = out["key"] = project_key(projects, repo)
    servers = (projects.get(key) or {}).get("mcpServers")
    if not isinstance(servers, dict):
        return out
    for name in sorted(servers):
        if _ours(servers[name], host_prefix):
            del servers[name]
            out["removed"].append(name)
    if out["removed"]:
        try:
            _write(config_path, payload)
        except OSError as exc:
            out["error"] = "could not write %s: %s" % (config_path, exc)
            out["removed"] = []
    return out


def unlink_all(host_prefix: str, config_path: Path | None = None) -> dict:
    """``unlink`` for every project at once -- the host's uninstall, which
    must also reach a repo unregistered since it was linked. Returns
    ``{"removed": {key: [names]}, "error"}``."""
    config_path = config_path or claude_config_path()
    out: dict = {"removed": {}, "error": None}
    payload, error = _read(config_path)
    if error:
        out["error"] = error
        return out
    projects = payload.get("projects")
    for key, project in (projects.items() if isinstance(projects, dict) else ()):
        servers = project.get("mcpServers") if isinstance(project, dict) else None
        if not isinstance(servers, dict):
            continue
        gone = sorted(name for name, entry in servers.items() if _ours(entry, host_prefix))
        for name in gone:
            del servers[name]
        if gone:
            out["removed"][key] = gone
    if out["removed"]:
        try:
            _write(config_path, payload)
        except OSError as exc:
            out["error"] = "could not write %s: %s" % (config_path, exc)
            out["removed"] = {}
    return out


def linked(repo: Path, host_prefix: str, config_path: Path | None = None) -> dict[str, str]:
    """``{name: url}`` of this repo's local-scope entries pointing at the host."""
    payload, error = _read(config_path or claude_config_path())
    if error or not isinstance(payload.get("projects"), dict):
        return {}
    projects = payload["projects"]
    servers = (projects.get(project_key(projects, repo)) or {}).get("mcpServers") or {}
    return {name: entry["url"] for name, entry in sorted(servers.items())
            if _ours(entry, host_prefix)}
