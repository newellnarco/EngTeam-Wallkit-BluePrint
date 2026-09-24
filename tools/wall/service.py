#!/usr/bin/env python3
"""Service -- the machine-wide registry, the consent-gated install, verify, serve.

``wall.py`` keeps its stubs and lazily imports this module for the six commands
below. The seam is exact:

    cmd_install(args)    -> int
    cmd_register(args)   -> int
    cmd_unregister(args) -> int
    cmd_verify(args)     -> int
    cmd_uninstall(args)  -> int
    cmd_serve(args)      -> int

Each takes the argparse namespace (``.repo`` is the only attribute guaranteed
to exist; everything else is read with ``getattr`` and a default) and returns a
process exit code. None of them raise.

Three ideas carry the design.

**One timer per machine, not per repo.** Ten repos would mean ten scheduled
tasks and ten chances for an orphan pointing at a deleted directory firing every
two minutes forever, failing silently. Instead one task walks
``~/.wall/registry.json`` and sweeps each live repo; a repo whose path no longer
exists is dropped on the next pass. Adding a tenth repo installs nothing new.
It also buys the thing a per-repo design structurally cannot have: Claude and
GitHub quotas are account-level, so only a machine-wide walker can report true
remaining budget.

**Consent once per machine.** A subagent silently registering a persistent
background service is exactly what a local-only operating preference guards
against. ``install`` prints every path and command it would create and then
stops unless ``--yes`` was passed. After that first yes, adding a repo is a
plain file write in ``~/.wall/`` and needs no further approval.

**Never green over a failed read.** A missing heartbeat is unknown, not fresh.
A registry that will not parse is a flagged failure, not an empty list. A dead
timer is the one failure that is invisible, because a stale wall looks exactly
like a quiet project.

Local-only: nothing in this module reaches the network. The one command that
does is ``shipper.ship``, which is separately invoked and separately gated.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import server                          # noqa: E402
import shipper                         # noqa: E402
from install import get_adapter        # noqa: E402

#: Stamped into each registry row so a later kit can tell what wrote it.
INSTALLED_VERSION = "wall-kit/1"

#: The sweeper the one machine task runs. Written into the wall home at install.
SWEEPER_NAME = "sweep_all.py"

#: How long since the last sweep before the wall is not to be trusted. The page
#: turns its ``generated_at`` red at five minutes for the same reason.
DEFAULT_STALE_AFTER_S = 300

DEFAULT_INTERVAL_S = 120


# ------------------------------------------------------------------ wall home

def wall_home(env: dict | None = None) -> Path:
    """The machine-wide wall directory: ``~/.wall`` unless ``WALL_HOME`` says else.

    ``WALL_HOME`` names the directory itself, not its parent. It exists so the
    tests can exercise a real install against a temporary directory instead of
    writing into whoever's home ran them.
    """
    env = os.environ if env is None else env
    override = (env.get("WALL_HOME") or "").strip()
    if override:
        return Path(override).expanduser()
    base = env.get("USERPROFILE") or env.get("HOME") or os.path.expanduser("~")
    return Path(base).expanduser() / ".wall"


def registry_path(env: dict | None = None) -> Path:
    return wall_home(env) / "registry.json"


def sweeper_path(env: dict | None = None) -> Path:
    return wall_home(env) / SWEEPER_NAME


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _atomic_write(path: Path, text: str) -> None:
    """Write via a uniquely-named temp file plus rename. Raises on failure."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(".tmp-wallsvc-%d-%s" % (os.getpid(), path.name))
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


# ------------------------------------------------------------------ registry

def read_registry(env: dict | None = None) -> dict:
    """The registry, always as ``{"repos": [...]}``. Never raises.

    A registry that cannot be read carries ``_error`` naming why. Callers must
    surface that rather than treating it as "no repos registered": an unreadable
    registry and an empty one look identical from the outside and mean opposite
    things.
    """
    path = registry_path(env)
    if not path.exists():
        return {"repos": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {"repos": [], "_error": "%s is unreadable: %s" % (path, exc)}
    if not isinstance(payload, dict) or not isinstance(payload.get("repos"), list):
        return {"repos": [], "_error": "%s is not a registry object" % path}
    rows = [row for row in payload["repos"] if isinstance(row, dict) and row.get("path")]
    dropped = len(payload["repos"]) - len(rows)
    out = {"repos": rows}
    if dropped:
        out["_error"] = "%d malformed row(s) ignored in %s" % (dropped, path)
    return out


def write_registry(registry: dict, env: dict | None = None) -> Path:
    """Write the registry atomically. Returns its path."""
    path = registry_path(env)
    _atomic_write(path, json.dumps({"repos": registry.get("repos", [])}, indent=2) + "\n")
    return path


def prune_registry(registry: dict) -> tuple[dict, list[str]]:
    """Drop rows whose path no longer exists. Returns ``(registry, dropped)``.

    This is the orphan defence: a repo that was deleted stops being swept on the
    next pass rather than failing every two minutes forever.
    """
    kept, dropped = [], []
    for row in registry.get("repos", []):
        if Path(row["path"]).is_dir():
            kept.append(row)
        else:
            dropped.append(row["path"])
    return {"repos": kept}, dropped


def register_repo(repo: Path | str, *, name: str | None = None,
                  env: dict | None = None) -> dict:
    """Add (or refresh) a repo row. Idempotent on the resolved path.

    Returns ``{"added", "path", "registry", "error"}``. ``added`` is False when
    the repo was already registered -- that is a success, not a failure.
    """
    resolved = Path(repo).resolve()
    out = {"added": False, "path": str(resolved),
           "registry": str(registry_path(env)), "error": None}
    if not resolved.is_dir():
        out["error"] = "%s is not a directory" % resolved
        return out
    registry = read_registry(env)
    if registry.get("_error"):
        out["error"] = registry["_error"]
        return out
    rows = registry["repos"]
    for row in rows:
        if Path(row["path"]) == resolved:
            row["name"] = name or row.get("name") or resolved.name
            row["installed_version"] = INSTALLED_VERSION
            try:
                write_registry({"repos": rows}, env)
            except OSError as exc:
                out["error"] = "could not write the registry: %s" % exc
            return out
    rows.append({
        "path": str(resolved),
        "name": name or resolved.name,
        "installed_version": INSTALLED_VERSION,
        "last_seen": None,
    })
    try:
        write_registry({"repos": rows}, env)
    except OSError as exc:
        out["error"] = "could not write the registry: %s" % exc
        return out
    out["added"] = True
    return out


def unregister_repo(repo: Path | str, *, env: dict | None = None) -> dict:
    """Remove a repo row. Returns ``{"removed", "path", "error"}``.

    Removing a repo that was never registered is a success with
    ``removed=False``: the desired end state holds either way.
    """
    resolved = Path(repo).resolve()
    out = {"removed": False, "path": str(resolved), "error": None}
    registry = read_registry(env)
    if registry.get("_error"):
        out["error"] = registry["_error"]
        return out
    kept = [row for row in registry["repos"] if Path(row["path"]) != resolved]
    out["removed"] = len(kept) != len(registry["repos"])
    if out["removed"]:
        try:
            write_registry({"repos": kept}, env)
        except OSError as exc:
            out["error"] = "could not write the registry: %s" % exc
            out["removed"] = False
    return out


def is_registered(repo: Path | str, env: dict | None = None) -> bool:
    resolved = Path(repo).resolve()
    return any(Path(row["path"]) == resolved for row in read_registry(env)["repos"])


# ------------------------------------------------------------------- sweeper

SWEEPER_SOURCE = '''#!/usr/bin/env python3
"""sweep_all -- what the one machine-wide timer runs. Generated by `wall install`.

Walks the registry beside this file and runs `wall run-once` for each live repo.
A repo whose path no longer exists is dropped, so an orphan cannot fire forever.
Stdlib only, local only, no model calls, no network.
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HOME = Path(__file__).resolve().parent
REGISTRY = HOME / "registry.json"
HEARTBEAT = HOME / "heartbeat.json"
LOG = HOME / "courier.log"
SWEEP_TIMEOUT_S = 240
LOG_MAX_BYTES = 1000000


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def log(line):
    try:
        if LOG.exists() and LOG.stat().st_size > LOG_MAX_BYTES:
            tail = LOG.read_text(encoding="utf-8", errors="replace").splitlines()[-2000:]
            LOG.write_text("\\n".join(tail) + "\\n", encoding="utf-8")
        with LOG.open("a", encoding="utf-8") as handle:
            handle.write("%s %s\\n" % (now(), line))
    except OSError:
        pass


def write_json(path, payload):
    try:
        tmp = path.with_name(".tmp-sweep-%d-%s" % (os.getpid(), path.name))
        tmp.write_text(json.dumps(payload, indent=2) + "\\n", encoding="utf-8")
        tmp.replace(path)
    except OSError:
        pass


def main():
    try:
        registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
        rows = [r for r in registry.get("repos", []) if isinstance(r, dict) and r.get("path")]
    except (OSError, ValueError) as exc:
        log("registry unreadable: %s" % exc)
        write_json(HEARTBEAT, {"last_sweep": now(), "ok": False, "error": str(exc)})
        return 1

    kept, results = [], []
    for row in rows:
        repo = Path(row["path"])
        if not repo.is_dir():
            log("dropped %s -- path no longer exists" % repo)
            continue
        kept.append(row)
        wall_py = repo / "tools" / "wall" / "wall.py"
        if not wall_py.is_file():
            results.append({"path": str(repo), "ok": False, "detail": "no tools/wall/wall.py"})
            log("%s: no tools/wall/wall.py" % repo)
            continue
        try:
            done = subprocess.run(
                [sys.executable, str(wall_py), "--repo", str(repo), "run-once"],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=SWEEP_TIMEOUT_S, check=False)
            ok = done.returncode == 0
            detail = (done.stdout or done.stderr).strip().splitlines()
            detail = detail[-1] if detail else "no output"
        except subprocess.TimeoutExpired:
            ok, detail = False, "timed out after %ss" % SWEEP_TIMEOUT_S
        except (OSError, ValueError) as exc:
            ok, detail = False, "could not run: %s" % exc
        results.append({"path": str(repo), "ok": ok, "detail": detail})
        log("%s: %s -- %s" % (repo, "ok" if ok else "FAILED", detail))
        if ok:
            row["last_seen"] = now()

    write_json(REGISTRY, {"repos": kept})
    write_json(HEARTBEAT, {
        "last_sweep": now(),
        "ok": all(r["ok"] for r in results) if results else True,
        "repos": len(kept),
        "results": results,
    })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''


def write_sweeper(env: dict | None = None) -> Path:
    """Write ``sweep_all.py`` into the wall home. Idempotent."""
    path = sweeper_path(env)
    _atomic_write(path, SWEEPER_SOURCE)
    return path


# ------------------------------------------------------------------- consent

def install_plan(repo: Path | str, *, interval_seconds: int = DEFAULT_INTERVAL_S,
                 env: dict | None = None, system: str | None = None) -> list[str]:
    """Exactly what ``wall install`` would create, as printable lines.

    Pure apart from reading the registry. This is the consent surface: a person
    approves what this says, so it must name every file and the literal
    scheduler command, not a summary of them.
    """
    resolved = Path(repo).resolve()
    home = wall_home(env)
    adapter = get_adapter(system)
    python = sys.executable
    sweeper = str(sweeper_path(env))

    try:
        scheduler = list(adapter.describe_install(python, sweeper, interval_seconds))
    except Exception as exc:  # an adapter must never block the consent print
        scheduler = ["  schedule   could not be described by the %s adapter: %s"
                     % (getattr(adapter, "__name__", "?"), exc)]

    return [
        "wall install would create:",
        "  directory  %s" % home,
        "  file       %s" % (home / "registry.json"),
        "  file       %s" % sweeper,
    ] + scheduler + [
        "",
        "  registering repo  %s" % resolved,
        "  sweep interval    every %ds" % interval_seconds,
        "",
        "The schedule is ONE task for this machine. It walks the registry and",
        "sweeps every live repo, so adding another repo installs nothing new.",
        "Nothing here reaches the network.",
    ]


# ------------------------------------------------------------------- checks

def manifest_compare(repo: Path | str, app: Path | str) -> dict:
    """Compare the repo's ``MANIFEST.sha256`` against a deployed application's.

    This is the verification the repo cannot do for itself. CI going green says
    the code is correct; it says nothing about whether the box is running it.
    The failure this catches is real and has a name in this tree: a drop whose
    manifest entries shipped but whose install never ran.

    Returns ``{"status": "match"|"differs"|"missing", "detail": str}``.
    """
    repo_manifest = Path(repo).resolve() / "MANIFEST.sha256"
    app_manifest = Path(app).expanduser() / "MANIFEST.sha256"
    missing = [str(p) for p in (repo_manifest, app_manifest) if not p.is_file()]
    if missing:
        return {"status": "missing", "detail": "no manifest at %s" % ", ".join(missing)}
    try:
        repo_lines = repo_manifest.read_text(encoding="utf-8", errors="replace").splitlines()
        app_lines = app_manifest.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        return {"status": "missing", "detail": "could not read a manifest: %s" % exc}
    if repo_lines == app_lines:
        return {"status": "match", "detail": "%d entries identical" % len(repo_lines)}
    differing = len(set(repo_lines).symmetric_difference(app_lines))
    return {"status": "differs",
            "detail": "%d entr(ies) differ -- the deployed app is not this tree"
                      % differing}


#: Where the register lives unless wall.json names another path
#: (``budgeted_docs``): the template says copy it to the repo root.
BUDGET_REGISTER = "BUDGETED_DOCS.md"

#: Under this share of the budget left, a document warns (the template's
#: <WARNING_THRESHOLD>, defaulted).
BUDGET_WARN_PCT = 10.0

#: Unit spellings -> (measured unit, multiplier on the stated number).
#: Tokens are approximated at four characters each and marked approximate:
#: the kit carries no tokenizer, and a converted number is an estimate.
_BUDGET_UNITS = {
    "character": ("characters", 1), "characters": ("characters", 1),
    "char": ("characters", 1), "chars": ("characters", 1),
    "byte": ("bytes", 1), "bytes": ("bytes", 1), "b": ("bytes", 1),
    "kb": ("bytes", 1000), "kib": ("bytes", 1024),
    "line": ("lines", 1), "lines": ("lines", 1),
    "token": ("tokens", 1), "tokens": ("tokens", 1), "tok": ("tokens", 1),
}

_WHOLE_FILE = ("", "whole file", "whole", "file", "entire file", "all")


def _register_rows(text: str) -> list[dict]:
    """The register table's rows keyed by lower-cased header. Only the first
    table whose header names both a document and a budget column is read."""
    header, rows = None, []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            if header is not None and rows:
                break
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if header is None:
            low = [c.lower() for c in cells]
            if any(c.startswith("document") for c in low) and "budget" in low:
                header = low
            continue
        if all(set(c) <= set("-: ") for c in cells):
            continue
        rows.append(dict(zip(header, cells)))
    return rows


def _parse_budget(cell: str) -> tuple[float, str] | None:
    m = re.match(r"^\s*~?\s*([\d][\d,_]*(?:\.\d+)?)\s*(k)?\s*([A-Za-z]+)\s*$",
                 cell.replace("`", ""))
    if not m:
        return None
    unit = _BUDGET_UNITS.get(m.group(3).lower())
    if unit is None:
        return None
    value = float(m.group(1).replace(",", "").replace("_", ""))
    if m.group(2):
        value *= 1000
    return value * unit[1], unit[0]


def _measure(path: Path, unit: str) -> int:
    if unit == "bytes":
        return path.stat().st_size
    text = path.read_text(encoding="utf-8", errors="replace")
    if unit == "lines":
        return len(text.splitlines())
    if unit == "tokens":
        return -(-len(text) // 4)
    return len(text)


def budget_headroom(repo: Path | str) -> list[dict] | None:
    """Headroom on every budget-counted context doc in the host's register.

    G10 in RECONCILIATION: the host repo's reviewer-prompt budget sat 53
    characters from a hard failure while three parked units each added rules to
    the counted sections. This reads ``BUDGETED_DOCS.md`` (or wall.json's
    ``budgeted_docs``), measures each registered document in the unit its
    Budget cell declares -- characters, bytes (B / KB / KiB), lines, or tokens
    (approximated at 4 characters each, and marked so) -- and returns one row
    per document: ``{path, consumer, unit, budget, measured, headroom,
    headroom_pct, approximate, status, detail}``.

    ``status``: ``fail`` over budget, ``warn`` under 10% headroom, ``ok``
    otherwise, ``unknown`` for a row that cannot be measured honestly (an
    unfilled placeholder, an unrecognised unit, a section-scoped count).
    Returns None when no register exists -- the doctor renders that as "not
    measured", never as "fine".
    """
    repo = Path(repo).resolve()
    rel = BUDGET_REGISTER
    try:
        cfg = json.loads((repo / ".wall" / "config" / "wall.json").read_text(
            encoding="utf-8"))
        if isinstance(cfg, dict) and isinstance(cfg.get("budgeted_docs"), str) \
                and cfg["budgeted_docs"].strip():
            rel = cfg["budgeted_docs"].strip()
    except (OSError, ValueError):
        pass
    register = repo / rel
    try:
        text = register.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    out: list[dict] = []
    for row in _register_rows(text):
        doc_key = next((k for k in row if k.startswith("document")), None)
        doc = (row.get(doc_key) or "").strip().strip("`").strip()
        entry = {"path": doc, "consumer": row.get("consumer") or None,
                 "unit": None, "budget": None, "measured": None, "headroom": None,
                 "headroom_pct": None, "approximate": False,
                 "status": "unknown", "detail": ""}
        out.append(entry)
        if not doc or "<" in doc:
            entry["detail"] = "unfilled register row"
            continue
        counted = (row.get("what is counted") or "").strip().lower()
        if counted not in _WHOLE_FILE:
            entry["detail"] = ("counts %r, not the whole file -- not measured "
                               "mechanically" % counted)
            continue
        parsed = _parse_budget(row.get("budget") or "")
        if parsed is None:
            entry["detail"] = ("budget %r has no recognised unit (characters, "
                               "bytes, lines, tokens)" % (row.get("budget") or ""))
            continue
        budget, unit = parsed
        entry.update(unit=unit, budget=budget, approximate=unit == "tokens")
        target = (repo / doc).resolve()
        if not target.is_relative_to(repo) or not target.is_file():
            entry.update(status="warn",
                         detail="registered but missing in this repo")
            continue
        try:
            measured = _measure(target, unit)
        except OSError as exc:
            entry["detail"] = "could not read: %s" % exc
            continue
        headroom = budget - measured
        pct = headroom / budget * 100.0 if budget else 0.0
        status = ("fail" if headroom < 0 else
                  "warn" if pct < BUDGET_WARN_PCT else "ok")
        approx = "~" if unit == "tokens" else ""
        entry.update(measured=measured, headroom=headroom,
                     headroom_pct=round(pct, 1), status=status,
                     detail="%s%d / %d %s, %s%d left (%.1f%%)%s" % (
                         approx, measured, budget, unit, approx, headroom, pct,
                         " -- OVER BUDGET" if status == "fail" else ""))
    return out


def doctor_checks(repo: Path | str, *, env: dict | None = None,
                  app: Path | str | None = None,
                  stale_after_s: int = DEFAULT_STALE_AFTER_S,
                  adapter=None) -> list[dict]:
    """The plumbing checks, as ``[{"name", "status", "detail"}]``. Never raises.

    ``status`` is one of ``ok`` / ``warn`` / ``fail`` / ``unknown``. ``unknown``
    is a real answer and never collapses into ``ok``: a heartbeat that cannot be
    read is not a fresh one.

    ``wall doctor`` and ``wall verify`` both call this, so the two agree by
    construction rather than by two people maintaining the same list twice.
    """
    resolved = Path(repo).resolve()
    checks: list[dict] = []

    age = shipper.heartbeat_age_s(resolved)
    if age is None:
        checks.append({"name": "heartbeat", "status": "fail",
                       "detail": "no readable %s -- the courier has never run here"
                                 % (resolved / ".wall" / "derived" / "heartbeat.json")})
    elif age > stale_after_s:
        checks.append({"name": "heartbeat", "status": "fail",
                       "detail": "last sweep was %ds ago (stale past %ds) -- the timer "
                                 "may be dead; a stale wall looks exactly like a quiet "
                                 "project" % (int(age), stale_after_s)})
    else:
        checks.append({"name": "heartbeat", "status": "ok",
                       "detail": "last sweep %ds ago" % int(age)})

    registry = read_registry(env)
    if registry.get("_error"):
        checks.append({"name": "registry", "status": "fail", "detail": registry["_error"]})
    else:
        _, dropped = prune_registry(registry)
        if not registry["repos"]:
            checks.append({"name": "registry", "status": "warn",
                           "detail": "no repos registered -- run `wall register`"})
        elif not is_registered(resolved, env):
            checks.append({"name": "registry", "status": "warn",
                           "detail": "%d repo(s) registered, but not this one" % len(
                               registry["repos"])})
        elif dropped:
            checks.append({"name": "registry", "status": "warn",
                           "detail": "%d dead path(s) will be dropped on the next sweep: %s"
                                     % (len(dropped), ", ".join(dropped))})
        else:
            checks.append({"name": "registry", "status": "ok",
                           "detail": "%d repo(s), this one included" % len(registry["repos"])})

    module = adapter if adapter is not None else get_adapter()
    try:
        state = module.verify()
    except Exception as exc:  # an adapter is third-party-shaped; never let it escape
        state = {"installed": False, "running": False, "last_run": None,
                 "error": "%s: %s" % (type(exc).__name__, exc)}
    if not isinstance(state, dict):
        state = {"installed": False, "running": False, "last_run": None,
                 "error": "adapter returned %s" % type(state).__name__}
    if not state.get("installed"):
        checks.append({"name": "timer", "status": "fail",
                       "detail": state.get("error") or "no machine timer installed"})
    elif not state.get("running"):
        checks.append({"name": "timer", "status": "fail",
                       "detail": state.get("error") or "timer installed but not running"})
    else:
        detail = "installed and running"
        if state.get("last_run"):
            detail += "; scheduler last run %s" % state["last_run"]
        status = "warn" if state.get("error") else "ok"
        if state.get("error"):
            detail += "; %s" % state["error"]
        checks.append({"name": "timer", "status": status, "detail": detail})

    headroom = budget_headroom(resolved)
    if headroom is None:
        checks.append({"name": "budget", "status": "unknown",
                       "detail": "not measured (no %s register in this repo)"
                                 % BUDGET_REGISTER})
    elif not headroom:
        checks.append({"name": "budget", "status": "unknown",
                       "detail": "not measured (the register lists no documents)"})
    else:
        rank = {"ok": 0, "unknown": 1, "warn": 2, "fail": 3}
        worst = max((row["status"] for row in headroom), key=rank.get)
        counts = {}
        for row in headroom:
            counts[row["status"]] = counts.get(row["status"], 0) + 1
        checks.append({"name": "budget", "status": worst,
                       "detail": "%d registered doc(s): %s" % (
                           len(headroom), ", ".join(
                               "%d %s" % (n, k) for k, n in sorted(counts.items())))})
        for row in headroom:
            checks.append({"name": "budget " + (row["path"] or "?"),
                           "status": row["status"], "detail": row["detail"]})

    if app is not None:
        outcome = manifest_compare(resolved, app)
        checks.append({"name": "app",
                       "status": {"match": "ok", "differs": "fail"}.get(
                           outcome["status"], "unknown"),
                       "detail": outcome["detail"]})
    return checks


def _print_checks(checks: list[dict]) -> int:
    glyph = {"ok": "ok  ", "warn": "WARN", "fail": "FAIL", "unknown": "??  "}
    for check in checks:
        print("  %s %-10s %s" % (glyph.get(check["status"], "??  "),
                                 check["name"], check["detail"]))
    return 1 if any(c["status"] == "fail" for c in checks) else 0


# ------------------------------------------------------------------ commands

def _repo(args) -> Path:
    return Path(getattr(args, "repo", ".") or ".").resolve()


def cmd_install(args) -> int:
    """Consent-gated machine install. Prints the plan; ``--yes`` proceeds."""
    repo = _repo(args)
    interval = int(getattr(args, "interval", None) or DEFAULT_INTERVAL_S)
    env = getattr(args, "env", None)

    for line in install_plan(repo, interval_seconds=interval, env=env):
        print(line)

    if not getattr(args, "yes", False):
        print("")
        print("Nothing was created. Re-run with --yes to proceed:")
        print("  wall install --yes%s" % ("" if interval == DEFAULT_INTERVAL_S
                                          else " --interval %d" % interval))
        return 1

    try:
        home = wall_home(env)
        home.mkdir(parents=True, exist_ok=True)
        sweeper = write_sweeper(env)
    except OSError as exc:
        print("could not prepare %s: %s" % (wall_home(env), exc), file=sys.stderr)
        return 1

    registered = register_repo(repo, env=env)
    if registered["error"]:
        print("registry: %s" % registered["error"], file=sys.stderr)
        return 1
    print("")
    print("  registry   %s (%s)" % (registered["registry"],
                                    "added" if registered["added"] else "already present"))
    print("  sweeper    %s" % sweeper)

    adapter = get_adapter(getattr(args, "system", None))
    try:
        created = adapter.install(interval, python=sys.executable, sweeper=str(sweeper))
    except (RuntimeError, NotImplementedError, OSError) as exc:
        print("  schedule   NOT created: %s" % exc, file=sys.stderr)
        print("", file=sys.stderr)
        print("The registry and sweeper above ARE in place, so `wall run-once` and a "
              "hand-made task both work. Only the scheduler step failed.", file=sys.stderr)
        return 1
    print("  schedule   %s" % created)
    print("")
    print("Installed. Verify with: wall verify")
    return 0


def cmd_register(args) -> int:
    """Add this repo to the machine registry. No privileges, no scheduler."""
    env = getattr(args, "env", None)
    outcome = register_repo(_repo(args), name=getattr(args, "name", None), env=env)
    if outcome["error"]:
        print("register failed: %s" % outcome["error"], file=sys.stderr)
        return 1
    print("%s %s\n  registry %s" % ("registered" if outcome["added"] else "already registered",
                                    outcome["path"], outcome["registry"]))
    if not sweeper_path(env).is_file():
        print("  note: no sweeper at %s yet -- run `wall install --yes` once per machine"
              % sweeper_path(env))
    return 0


def cmd_unregister(args) -> int:
    """Remove this repo from the machine registry. Absent is success."""
    outcome = unregister_repo(_repo(args), env=getattr(args, "env", None))
    if outcome["error"]:
        print("unregister failed: %s" % outcome["error"], file=sys.stderr)
        return 1
    print("%s %s" % ("unregistered" if outcome["removed"] else "was not registered:",
                     outcome["path"]))
    return 0


def cmd_verify(args) -> int:
    """Timer alive? Heartbeat fresh? Registry sane? Deployed app in sync?"""
    repo = _repo(args)
    app = getattr(args, "app", None)
    print("wall verify  %s" % repo)
    checks = doctor_checks(repo, env=getattr(args, "env", None), app=app,
                           stale_after_s=int(getattr(args, "stale_after_s", None)
                                             or DEFAULT_STALE_AFTER_S))
    code = _print_checks(checks)
    print("  %s" % ("all checks passed" if code == 0 else "one or more checks FAILED"))
    return code


def cmd_uninstall(args) -> int:
    """Remove the machine timer. The registry and sweeper stay unless --purge."""
    env = getattr(args, "env", None)
    adapter = get_adapter(getattr(args, "system", None))
    code = 0
    try:
        adapter.uninstall()
        print("removed the machine timer")
    except (RuntimeError, NotImplementedError, OSError) as exc:
        print("could not remove the timer: %s" % exc, file=sys.stderr)
        code = 1
    if getattr(args, "purge", False):
        for path in (sweeper_path(env), registry_path(env)):
            try:
                path.unlink(missing_ok=True)
                print("removed %s" % path)
            except OSError as exc:
                print("could not remove %s: %s" % (path, exc), file=sys.stderr)
                code = 1
    else:
        print("kept %s -- pass --purge to remove it too" % registry_path(env))
    return code


def cmd_serve(args) -> int:
    """Serve .wall/derived/ on 127.0.0.1, or probe a server already running."""
    port = int(getattr(args, "port", None) or server.DEFAULT_PORT)
    if getattr(args, "check", False):
        outcome = server.check(port)
        print("[wall-server] %s -- %s" % ("ok" if outcome["ok"] else "FAIL",
                                          outcome["reason"]))
        return 0 if outcome["ok"] else 1
    return server.serve(_repo(args), port, quiet=not getattr(args, "verbose", False))


# ---------------------------------------------------------------------- main

def main(argv: list[str] | None = None) -> int:
    """Standalone entry point. ``wall.py`` calls the ``cmd_*`` functions directly."""
    parser = argparse.ArgumentParser(
        prog="wall-service",
        description="Machine registry, timer install, and the local wall server.")
    parser.add_argument("--repo", default=".")
    sub = parser.add_subparsers(dest="cmd", required=True)

    install_parser = sub.add_parser("install", help="consent-gated machine install")
    install_parser.add_argument("--yes", action="store_true")
    install_parser.add_argument("--interval", type=int, default=DEFAULT_INTERVAL_S)
    install_parser.set_defaults(fn=cmd_install)

    register_parser = sub.add_parser("register")
    register_parser.add_argument("--name")
    register_parser.set_defaults(fn=cmd_register)

    sub.add_parser("unregister").set_defaults(fn=cmd_unregister)

    verify_parser = sub.add_parser("verify")
    verify_parser.add_argument("--app", help="deployed application root to compare")
    verify_parser.set_defaults(fn=cmd_verify)

    uninstall_parser = sub.add_parser("uninstall")
    uninstall_parser.add_argument("--purge", action="store_true")
    uninstall_parser.set_defaults(fn=cmd_uninstall)

    serve_parser = sub.add_parser("serve")
    serve_parser.add_argument("--port", type=int, default=server.DEFAULT_PORT)
    serve_parser.add_argument("--check", action="store_true")
    serve_parser.add_argument("--verbose", action="store_true")
    serve_parser.set_defaults(fn=cmd_serve)

    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
