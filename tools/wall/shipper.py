#!/usr/bin/env python3
"""Shipper -- the event ledger's isolated-branch telemetry, per RECONCILIATION Q7.

Event shards must never ride a development PR. They are high-churn append-only
files; committed on the working branch they would conflict on every parallel
unit (the F-DERIVED-001 class that board fragments were invented to kill). So
shards live gitignored in the working tree and travel on a dedicated branch
instead, written with an isolated ``GIT_INDEX_FILE`` so the checkout, the real
index and the current branch are never touched.

This is the same plumbing MAX3's ``tools/ship_agent_status.py`` ran in
production overnight on 2026-09-18/19; the guards below are its measured
lessons, restated:

* **validate before push.** The bytes on disk are what gets published, and this
  module is not their only writer. A malformed snapshot reaching the branch
  breaks every consumer of it, so the payload is shape-checked first.
* **bounded git.** Every call has a wall-clock timeout and reports a timeout as
  a non-zero result rather than raising. An unbounded ``fetch`` against an
  unreachable remote hangs the two-minute sweep, and a hang looks exactly like
  working.
* **encoding pinned.** ``text=True`` otherwise decodes with the locale codec,
  which on Windows outside a PYTHONUTF8 environment is a legacy code page.
  ``cat-file blob`` returns shipped JSON, so a mojibake decode would corrupt an
  event and a stray byte would raise out of a function documented not to raise.
* **honest no-op.** No branch, no network, no remote, malformed payload, stale
  payload: the caller keeps what it had and is told why. Nothing here raises.
* **freshness guard on fetch.** A wave running ON the box writes shards
  directly; a stale shipped snapshot must never clobber a live local stream.

Nothing in this file is called automatically. ``ship`` is an explicit,
separately-gated command -- it is the one code path in the wall kit that
touches the network.

CLI::

    python shipper.py --repo . --ship
    python shipper.py --repo . --fetch
    python shipper.py --repo .            # validate the local snapshot only
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import subprocess
import sys
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

#: Where the courier writes the snapshot every sweep.
SNAPSHOT_REL = ".wall/derived/wall.json"

#: Root of the day-rolled event shards (EVENT_SCHEMA section 6).
EVENTS_REL = ".wall/events"

#: The isolated branch shards and snapshots travel on. Overwritten each ship.
DEFAULT_BRANCH = "wall-events"

#: Wall-clock bound on every git call. Generous against a push of a few small
#: files, far under the two-minute sweep cadence this can run inside.
GIT_TIMEOUT_S = 60

#: Signature of an injectable git runner: (repo, *args, env=...) -> completed.
GitRunner = Callable[..., "subprocess.CompletedProcess[str]"]

_MODE_BLOB = "100644"


# ------------------------------------------------------------------ plumbing

def _git(repo: Path, *args: str, env: dict | None = None) -> subprocess.CompletedProcess[str]:
    """Run git inside ``repo``: captured, windowless, utf-8 pinned, BOUNDED.

    A timeout comes back as returncode 124 rather than an exception, so every
    caller's existing "did it work?" branch handles it.
    """
    cmd = ["git", *args]
    try:
        return subprocess.run(
            cmd,
            cwd=str(repo),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=GIT_TIMEOUT_S,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(
            cmd, returncode=124, stdout="",
            stderr="git %s timed out after %ss" % (args[0] if args else "", GIT_TIMEOUT_S),
        )
    except (OSError, ValueError) as exc:
        # git missing, cwd gone, bad argv: a named failure, never a traceback
        # out of a module whose whole contract is the honest no-op.
        return subprocess.CompletedProcess(
            cmd, returncode=127, stdout="", stderr="could not run git: %s" % exc)


def _say(message: str) -> None:
    print("[wall-events] %s" % message, file=sys.stderr)


# ---------------------------------------------------------------- validation

def validate_snapshot(snapshot: Any) -> str | None:
    """The reason ``snapshot`` is not a well-formed wall snapshot, or None.

    Shape only. The wall renders whatever honest content the sections carry;
    this exists so a half-written or foreign file cannot be published as one.
    """
    if not isinstance(snapshot, dict):
        return "snapshot must be an object, got %s" % type(snapshot).__name__
    if not isinstance(snapshot.get("schema_version"), int):
        return "schema_version must be an integer"
    stamp = snapshot.get("generated_at")
    if not isinstance(stamp, str) or not stamp.strip():
        return "generated_at must be a non-empty ISO-8601 string"
    if parse_stamp(stamp) is None:
        return "generated_at is not parseable as ISO-8601: %r" % stamp
    if not isinstance(snapshot.get("repo"), dict):
        return "repo must be an object"
    if not isinstance(snapshot.get("integrity"), dict):
        return "integrity must be an object"
    if not isinstance(snapshot.get("crew"), list):
        return "crew must be a list"
    board = snapshot.get("board")
    if not isinstance(board, dict) or not isinstance(board.get("arcs"), list):
        return "board.arcs must be a list"
    return None


def parse_stamp(raw: str | None) -> datetime | None:
    """An ISO-8601 stamp as an aware datetime, or None when unreadable.

    Naive stamps compare as UTC: every writer in this kit stamps UTC.
    """
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _snapshot_stamp(raw: str | bytes | None) -> datetime | None:
    """The ``generated_at`` inside a snapshot payload, or None."""
    if raw is None:
        return None
    try:
        return parse_stamp(json.loads(raw).get("generated_at"))
    except (ValueError, TypeError, AttributeError):
        return None


# ------------------------------------------------------------------ heartbeat

def heartbeat_age_s(repo: Path | str, *, now: datetime | None = None) -> float | None:
    """Seconds since the courier last wrote ``heartbeat.json``, or None.

    None means "cannot tell" -- no heartbeat file, unreadable, or an unparseable
    stamp. A caller must render that as unknown, never as fresh: a dead timer is
    the one failure that looks identical to a quiet project (INSTALL.md).

    Never raises. Used by ``wall verify``, the doctor, and SessionStart
    detection.
    """
    path = Path(repo) / ".wall" / "derived" / "heartbeat.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    stamp = parse_stamp(payload.get("last_run"))
    if stamp is None:
        return None
    reference = now or datetime.now(timezone.utc)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    return max(0.0, (reference - stamp).total_seconds())


# ----------------------------------------------------------------- shipping

def _shard_day(snapshot: dict) -> str:
    """The day directory to ship, taken from the snapshot's own stamp."""
    stamp = parse_stamp(snapshot.get("generated_at"))
    return (stamp or datetime.now(timezone.utc)).strftime("%Y-%m-%d")


def shipment_paths(repo: Path, *, day: str | None = None) -> list[str]:
    """Repo-relative, posix, sorted: the snapshot plus one day of shards.

    Pure apart from the directory listing. The snapshot always leads so a
    consumer reading the tree top-down sees the summary before the detail.
    """
    repo = Path(repo)
    snapshot_path = repo / SNAPSHOT_REL
    paths: list[str] = []
    if snapshot_path.is_file():
        paths.append(SNAPSHOT_REL)
    if day is None:
        try:
            snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            snapshot = {}
        day = _shard_day(snapshot if isinstance(snapshot, dict) else {})
    shard_dir = repo / EVENTS_REL / day
    if shard_dir.is_dir():
        for shard in sorted(shard_dir.glob("*.jsonl")):
            if shard.is_file():
                paths.append(shard.relative_to(repo).as_posix())
    return paths


def ship(repo: Path | str, branch: str = DEFAULT_BRANCH, *,
         git: GitRunner | None = None, day: str | None = None) -> int:
    """Force-push the day's shards plus the snapshot to ``branch``. 0 on success.

    The working tree, the real index and the current branch are untouched: the
    tree is built in an isolated ``GIT_INDEX_FILE`` and pushed by object id. The
    branch is overwritten every ship -- latest state only, no history bloat, and
    the shards themselves are append-only so nothing is lost by it.

    Returns 1 with the reason on stderr for every failure. Never raises.
    """
    repo = Path(repo).resolve()
    run = git or _git

    snapshot_file = repo / SNAPSHOT_REL
    try:
        payload = json.loads(snapshot_file.read_text(encoding="utf-8"))
    except OSError as exc:
        _say("nothing to ship -- cannot read %s: %s" % (SNAPSHOT_REL, exc))
        return 1
    except ValueError as exc:
        _say("refusing to ship -- %s is not valid JSON: %s" % (SNAPSHOT_REL, exc))
        return 1

    # Validate what is about to be PUBLISHED, not what some earlier call wrote.
    # git accepts any bytes; without this an invalid snapshot reaches the branch
    # and every consumer of it renders an empty wall over live work.
    reason = validate_snapshot(payload)
    if reason is not None:
        _say("refusing to ship an invalid snapshot: %s" % reason)
        return 1

    paths = shipment_paths(repo, day=day or _shard_day(payload))
    if not paths:
        _say("nothing to ship -- no snapshot and no shards")
        return 1

    index_file = repo / ".wall" / "derived" / (".ship-%s.index" % branch)
    try:
        index_file.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        _say("cannot create the isolated index directory: %s" % exc)
        return 1
    env = {**os.environ, "GIT_INDEX_FILE": str(index_file)}

    try:
        empty = run(repo, "read-tree", "--empty", env=env)
        if empty.returncode != 0:
            _say("read-tree failed: %s" % empty.stderr.strip())
            return 1
        for rel in paths:
            blob = run(repo, "hash-object", "-w", "--", rel)
            if blob.returncode != 0:
                _say("hash-object failed for %s: %s" % (rel, blob.stderr.strip()))
                return 1
            staged = run(
                repo, "update-index", "--add", "--cacheinfo",
                "%s,%s,%s" % (_MODE_BLOB, blob.stdout.strip(), rel), env=env,
            )
            if staged.returncode != 0:
                _say("update-index failed for %s: %s" % (rel, staged.stderr.strip()))
                return 1
        tree = run(repo, "write-tree", env=env)
        if tree.returncode != 0:
            _say("write-tree failed: %s" % tree.stderr.strip())
            return 1
    finally:
        with contextlib.suppress(OSError):
            index_file.unlink()

    message = "wall events %s (%d file%s)" % (
        datetime.now(timezone.utc).isoformat(timespec="seconds"),
        len(paths), "" if len(paths) == 1 else "s")
    commit = run(repo, "commit-tree", tree.stdout.strip(), "-m", message)
    if commit.returncode != 0:
        _say("commit-tree failed: %s" % commit.stderr.strip())
        return 1
    pushed = run(repo, "push", "-f", "origin",
                 "%s:refs/heads/%s" % (commit.stdout.strip(), branch))
    if pushed.returncode != 0:
        _say("push failed: %s" % pushed.stderr.strip())
        return 1
    _say("pushed %d file(s) to origin/%s (tree and index untouched)" % (len(paths), branch))
    return 0


# ------------------------------------------------------------------ fetching

def fetch(repo: Path | str, branch: str = DEFAULT_BRANCH, *,
          git: GitRunner | None = None) -> dict:
    """Materialise ``origin/<branch>`` into the local tree, freshness-guarded.

    Returns ``{"updated": bool, "reason": str, "shards": int, "snapshot": bool}``.
    ``updated`` is True only when something on disk actually changed.

    Honest no-op on: no branch or no network, an unreadable or malformed
    payload, and -- the guard that matters -- a shipped snapshot the local one
    already supersedes. A wave running on this machine writes shards directly,
    and a stale branch must never clobber a live local stream.

    Shards are append-only, so a remote shard replaces a local one of the same
    name only when it is strictly longer. Merging stays idempotent on
    ``event_id`` either way; this just refuses to trade a longer local file for
    a shorter remote one.

    Never raises.
    """
    repo = Path(repo).resolve()
    run = git or _git
    result = {"updated": False, "reason": "", "shards": 0, "snapshot": False}

    fetched = run(repo, "fetch", "--quiet", "origin", branch)
    if fetched.returncode != 0:
        result["reason"] = "no %s branch or no network: %s" % (
            branch, fetched.stderr.strip() or "fetch failed")
        return result

    shown = run(repo, "cat-file", "blob", "FETCH_HEAD:%s" % SNAPSHOT_REL)
    if shown.returncode != 0:
        result["reason"] = "branch carries no %s" % SNAPSHOT_REL
        return result

    try:
        remote_payload = json.loads(shown.stdout)
    except ValueError as exc:
        result["reason"] = "shipped snapshot is not valid JSON: %s" % exc
        return result

    # A payload can carry a newer stamp and still be malformed everywhere else;
    # shape-check before letting it replace anything.
    reason = validate_snapshot(remote_payload)
    if reason is not None:
        result["reason"] = "shipped snapshot is malformed: %s" % reason
        return result

    remote_dt = parse_stamp(remote_payload.get("generated_at"))
    local_path = repo / SNAPSHOT_REL
    local_raw: str | None = None
    with contextlib.suppress(OSError):
        local_raw = local_path.read_text(encoding="utf-8")
    local_dt = _snapshot_stamp(local_raw)
    if local_dt is not None and remote_dt is not None and local_dt >= remote_dt:
        result["reason"] = "local snapshot is at least as fresh (%s >= %s)" % (
            local_dt.isoformat(), remote_dt.isoformat())
        return result

    listing = run(repo, "ls-tree", "-r", "--name-only", "FETCH_HEAD")
    shard_rels = [
        line.strip() for line in listing.stdout.splitlines()
        if line.strip().startswith(EVENTS_REL + "/") and line.strip().endswith(".jsonl")
    ] if listing.returncode == 0 else []

    for rel in shard_rels:
        blob = run(repo, "cat-file", "blob", "FETCH_HEAD:%s" % rel)
        if blob.returncode != 0:
            continue
        target = repo / rel
        if not _within(repo, target):
            continue  # a branch is untrusted input; never write outside the repo
        remote_bytes = blob.stdout.encode("utf-8")
        try:
            if target.is_file() and target.stat().st_size >= len(remote_bytes):
                continue
        except OSError:
            continue
        if _atomic_write(target, blob.stdout):
            result["shards"] += 1

    if _atomic_write(local_path, shown.stdout):
        result["snapshot"] = True

    result["updated"] = bool(result["shards"] or result["snapshot"])
    if not result["updated"]:
        result["reason"] = "nothing on the branch was newer than what is on disk"
    else:
        result["reason"] = "materialised %d shard(s)%s" % (
            result["shards"], " and the snapshot" if result["snapshot"] else "")
    return result


def _within(root: Path, candidate: Path) -> bool:
    """True when ``candidate`` resolves inside ``root``."""
    try:
        candidate.resolve().relative_to(root.resolve())
    except (ValueError, OSError):
        return False
    return True


def _atomic_write(path: Path, text: str) -> bool:
    """Write via a uniquely-named temp file plus rename. False on any failure."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(".tmp-wallship-%d-%s" % (os.getpid(), path.name))
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(path)
    except OSError:
        return False
    return True


# ---------------------------------------------------------------------- main

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="shipper",
        description="Ship wall event shards on an isolated branch (RECONCILIATION Q7).")
    parser.add_argument("--repo", default=".", help="repo root containing .wall/")
    parser.add_argument("--branch", default=DEFAULT_BRANCH)
    parser.add_argument("--ship", action="store_true", help="push the day's shards")
    parser.add_argument("--fetch", action="store_true", help="materialise the branch")
    args = parser.parse_args(argv)

    repo = Path(args.repo).resolve()
    if args.ship:
        return ship(repo, args.branch)
    if args.fetch:
        outcome = fetch(repo, args.branch)
        print("[wall-events] fetch: %s -- %s" % (
            "updated" if outcome["updated"] else "no-op", outcome["reason"]))
        return 0

    snapshot_file = repo / SNAPSHOT_REL
    try:
        reason = validate_snapshot(json.loads(snapshot_file.read_text(encoding="utf-8")))
    except (OSError, ValueError) as exc:
        reason = "unreadable: %s" % exc
    print("[wall-events] %s: %s" % (
        SNAPSHOT_REL, "valid" if reason is None else "INVALID -- %s" % reason))
    return 0 if reason is None else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
