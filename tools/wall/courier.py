#!/usr/bin/env python3
"""Courier — consolidates sharded event logs into one snapshot and renders the wall.

Deterministic, stdlib-only, no model calls, no network. Safe to run every two
minutes from a timer, from a hook, or by hand.

Outputs, both written to a temp path and atomically renamed into place:

    .wall/derived/wall.json   the snapshot (contract for any renderer)
    .wall/derived/wall.html   template + snapshot inlined, opens from file://
    .wall/derived/ledger.jsonl  full merged history, for analytics

Updating the look later means replacing render/wall_template.html only.
Updating the data means re-running this. Nothing else has to change.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1
DATA_MARKER = "__WALL_DATA__"
REPO_MARKER = "__REPO_NAME__"

# Advisory only. Nothing in this file stops work; it renders a warning.
DEFAULT_BUDGET = {
    "period": "week to date",
    "advisory": "Budgets are advisory. Nothing here stops work — it tells you when to.",
    "meters": [],
}


# ---------------------------------------------------------------- utilities

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def atomic_write(path: Path, text: str) -> None:
    """Write via temp file + rename so a reader never sees a partial file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-", suffix=path.suffix)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def git(repo: Path, *args: str) -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True, text=True, timeout=10, check=False,
        )
        return out.stdout.strip() if out.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


# ------------------------------------------------------------------- merge

def read_shards(events_dir: Path, checkpoints: dict) -> tuple[list[dict], dict, int]:
    """Read only the unread tail of each shard. Returns (events, checkpoints, shard_count)."""
    events: list[dict] = []
    shards = sorted(events_dir.rglob("*.jsonl"))
    for shard in shards:
        key = str(shard.relative_to(events_dir))
        offset = checkpoints.get(key, 0)
        size = shard.stat().st_size
        if size < offset:      # shard was truncated or replaced; re-read whole file
            offset = 0
        if size == offset:
            continue
        with shard.open("r", encoding="utf-8", errors="replace") as fh:
            fh.seek(offset)
            tail = fh.read()
            consumed = offset + len(tail.encode("utf-8"))
        lines = tail.splitlines()
        # A trailing partial line means a writer is mid-append. Leave it for next run.
        if tail and not tail.endswith("\n"):
            dropped = lines.pop() if lines else ""
            consumed -= len(dropped.encode("utf-8"))
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # surfaced as a sequence gap rather than crashing the sweep
        checkpoints[key] = consumed
    return events, checkpoints, len(shards)


def merge(ledger_path: Path, new_events: list[dict]) -> list[dict]:
    """Union on event_id, sorted by (ts, session_id, seq). Idempotent: a full
    rebuild from shards produces byte-identical output to an incremental run."""
    by_id: dict[str, dict] = {}
    if ledger_path.exists():
        with ledger_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        e = json.loads(line)
                        by_id[e.get("event_id", "")] = e
                    except json.JSONDecodeError:
                        continue
    for e in new_events:
        by_id[e.get("event_id", "")] = e
    return sorted(
        by_id.values(),
        key=lambda e: (e.get("ts", ""), e.get("session_id", ""), e.get("seq", 0)),
    )


# --------------------------------------------------------------- integrity

def check_integrity(events: list[dict], items: dict, stale_after_min: int = 30) -> dict:
    seq_gaps, seen = [], defaultdict(set)
    for e in events:
        if e.get("seq") is not None:
            seen[e.get("session_id")].add(e["seq"])
    for session, nums in seen.items():
        if not nums:
            continue
        expected = set(range(min(nums), max(nums) + 1))
        for missing in sorted(expected - nums):
            seq_gaps.append({"session_id": session, "seq": missing})

    started, finished = {}, set()
    for e in events:
        ev = e.get("event")
        if ev == "run_start":
            started[e.get("run_id")] = e
        elif ev in ("run_end", "run_error"):
            finished.add(e.get("run_id"))
    # A run_start with no terminal event is normal while the agent is still
    # working. It is only an orphan once it has blown its deadline — otherwise
    # every in-flight builder would light up the integrity panel.
    cutoff = time.time() - stale_after_min * 60
    orphans = []
    for rid, e in started.items():
        if rid in finished:
            continue
        try:
            started_at = datetime.fromisoformat(e["ts"].replace("Z", "+00:00")).timestamp()
        except (KeyError, ValueError):
            continue
        if started_at < cutoff:
            orphans.append({"run_id": rid, "agent": e.get("agent_name"),
                            "started": e.get("ts"), "item_id": e.get("item_id")})

    titles = defaultdict(list)
    duplicates = []
    for iid, item in items.items():
        titles[item.get("title", "").strip().lower()].append(iid)
        if item.get("duplicate_of"):
            duplicates.append([iid, item["duplicate_of"]])
    duplicates += [ids for ids in titles.values() if len(ids) > 1]

    return {
        "seq_gaps": seq_gaps,
        "orphan_runs": orphans,
        "duplicates": duplicates,
        "state_drift": 0,      # populated by `wall diff-state`
        "stale_claims": [],    # populated by the Foreman pass
    }


# ---------------------------------------------------------------- snapshot

def build_snapshot(repo: Path, events: list[dict], config: dict, shard_count: int,
                   run_ms: int) -> dict:
    agents: dict[str, dict] = {}
    items: dict[str, dict] = {}
    asks: dict[str, dict] = {}
    sessions: set[str] = set()

    for e in events:
        if e.get("session_id"):
            sessions.add(e["session_id"])

        aid = e.get("agent_key")
        if aid:
            a = agents.setdefault(aid, {
                "agent_key": aid, "name": e.get("agent_name", aid),
                "title": e.get("agent_title", ""), "role": e.get("role", "unknown"),
                "model_requested": e.get("model_requested"), "model_used": e.get("model_used"),
                "status": "idle", "item_id": None, "item_title": None, "since": None,
                "runs": 0, "cost_usd": 0.0, "gh_minutes": None,
                "tokens": {"in": 0, "out": 0, "cache_read": 0, "cache_write": 0},
                "last_event": None,
            })
            for k in ("agent_name", "agent_title", "model_requested", "model_used"):
                if e.get(k):
                    a[k.replace("agent_", "") if k.startswith("agent_") else k] = e[k]
            tk = e.get("tokens") or {}
            for k in a["tokens"]:
                a["tokens"][k] += tk.get(k, 0) or 0
            a["cost_usd"] += e.get("cost_usd", 0) or 0
            if e.get("gh_minutes") is not None:
                a["gh_minutes"] = (a["gh_minutes"] or 0) + e["gh_minutes"]
            a["last_event"] = e.get("ts")

            ev = e.get("event")
            if ev == "run_start":
                a.update(status="working", item_id=e.get("item_id"),
                         item_title=e.get("item_title"), since=e.get("ts"))
            elif ev in ("run_end", "run_error"):
                a["runs"] += 1
                outcome = e.get("outcome", "pass")
                a["status"] = {"blocked": "blocked", "human_required": "waiting"}.get(outcome, "idle")
                if a["status"] == "idle":
                    a.update(item_id=None, item_title=None)
                a["since"] = e.get("ts")

        if e.get("event") == "item_state":
            it = items.setdefault(e["item_id"], {"item_id": e["item_id"]})
            it.update({k: v for k, v in e.items()
                       if k in ("title", "kind", "status", "arc_id", "arc_title",
                                "assignee", "estimate", "actual", "duplicate_of")})
            it["updated_at"] = e.get("ts")

        if e.get("event") == "human_required":
            asks[e["ask_id"]] = {
                "ask_id": e["ask_id"], "question": e.get("question", ""),
                "agent": e.get("agent_name", e.get("agent_key", "")),
                "item_id": e.get("item_id", ""), "since": e.get("ts"),
                "trace_id": e.get("trace_id"),
            }
        elif e.get("event") == "human_answered":
            asks.pop(e.get("ask_id"), None)

    arcs: dict[str, dict] = {}
    for it in items.values():
        arc_id = it.get("arc_id", "unassigned")
        arc = arcs.setdefault(arc_id, {
            "arc_id": arc_id, "title": it.get("arc_title", "Unassigned"), "items": [],
        })
        if it.get("arc_title"):
            arc["title"] = it["arc_title"]
        arc["items"].append(it)
    for arc in arcs.values():
        arc["items"].sort(key=lambda i: i.get("item_id", ""))

    rollup: dict[tuple, dict] = {}
    for a in agents.values():
        key = (a["role"], a.get("model_used") or a.get("model_requested") or "—")
        r = rollup.setdefault(key, {
            "role": key[0], "model": key[1], "runs": 0,
            "tokens_in": 0, "tokens_out": 0, "cache_read": 0, "cost_usd": 0.0,
        })
        r["runs"] += a["runs"]
        r["tokens_in"] += a["tokens"]["in"]
        r["tokens_out"] += a["tokens"]["out"]
        r["cache_read"] += a["tokens"]["cache_read"]
        r["cost_usd"] += a["cost_usd"]

    integrity = check_integrity(events, items, config.get("stale_after_min", 30))

    # An agent whose run blew its deadline is not working, whatever its last
    # event claimed. Evidence outranks self-report.
    orphaned = {o["run_id"] for o in integrity["orphan_runs"]}
    for e in events:
        if e.get("event") == "run_start" and e.get("run_id") in orphaned:
            a = agents.get(e.get("agent_key"))
            if a and a["status"] == "working":
                a["status"] = "stale"
    integrity["stale_claims"] = [
        {"agent": a["name"], "item_id": a.get("item_id"), "since": a.get("since")}
        for a in agents.values() if a["status"] == "stale"
    ]

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now_iso(),
        "repo": {
            "name": config.get("repo_name") or repo.name,
            "path": str(repo),
            "branch": git(repo, "rev-parse", "--abbrev-ref", "HEAD") or "",
        },
        "courier": {"last_run_ms": run_ms, "events": len(events), "shards": shard_count},
        "integrity": integrity,
        "role_limits": config.get("role_limits", {}),
        "crew": sorted(agents.values(), key=lambda a: (a["role"], a["name"])),
        "board": {"arcs": sorted(arcs.values(), key=lambda a: a["arc_id"])},
        "waiting_on_you": sorted(asks.values(), key=lambda a: a["since"] or ""),
        "budget": config.get("budget", DEFAULT_BUDGET),
        "rollup_by_role": sorted(rollup.values(), key=lambda r: (r["role"], r["model"])),
        "sessions": sorted(sessions),
    }


# ------------------------------------------------------------------ render

def render(snapshot: dict, template_path: Path) -> str:
    """Inline the snapshot into the template. Only two markers are substituted,
    so the template can be swapped freely without touching this file."""
    payload = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"))
    # Keep the JSON safe inside <script>: escape the characters that could close it.
    payload = payload.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    html = template_path.read_text(encoding="utf-8")
    if DATA_MARKER not in html:
        raise SystemExit(f"template is missing {DATA_MARKER}: {template_path}")
    return html.replace(DATA_MARKER, payload).replace(
        REPO_MARKER, snapshot["repo"]["name"])


# -------------------------------------------------------------------- main

def run_once(repo: Path, template: Path | None = None, rebuild: bool = False) -> dict:
    started = time.perf_counter()
    wall = repo / ".wall"
    derived = wall / "derived"
    state_path = wall / "derived" / ".courier-state.json"
    ledger = derived / "ledger.jsonl"
    template = template or (Path(__file__).parent / "render" / "wall_template.html")

    config = {}
    cfg_path = wall / "config" / "wall.json"
    if cfg_path.exists():
        config = json.loads(cfg_path.read_text(encoding="utf-8"))

    state = {}
    if state_path.exists() and not rebuild:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    if rebuild:
        ledger.unlink(missing_ok=True)

    events_dir = wall / "events"
    events_dir.mkdir(parents=True, exist_ok=True)
    new_events, checkpoints, shard_count = read_shards(events_dir, state.get("checkpoints", {}))
    all_events = merge(ledger, new_events)

    run_ms = int((time.perf_counter() - started) * 1000)
    snapshot = build_snapshot(repo, all_events, config, shard_count, run_ms)

    atomic_write(ledger, "".join(
        json.dumps(e, ensure_ascii=False, sort_keys=True) + "\n" for e in all_events))
    atomic_write(derived / "wall.json", json.dumps(snapshot, ensure_ascii=False, indent=2))
    atomic_write(derived / "wall.html", render(snapshot, template))
    atomic_write(state_path, json.dumps({"checkpoints": checkpoints}, indent=2))
    atomic_write(wall / "derived" / "heartbeat.json", json.dumps({
        "last_run": snapshot["generated_at"], "run_ms": run_ms,
        "events": len(all_events), "ok": True,
    }, indent=2))
    return snapshot


def main() -> int:
    p = argparse.ArgumentParser(description="Consolidate event shards and render the wall.")
    p.add_argument("--repo", default=".", help="repo root containing .wall/")
    p.add_argument("--template", help="override the HTML template")
    p.add_argument("--rebuild", action="store_true",
                   help="discard checkpoints and rebuild the ledger from shards")
    p.add_argument("--quiet", action="store_true")
    a = p.parse_args()

    repo = Path(a.repo).resolve()
    try:
        snap = run_once(repo, Path(a.template) if a.template else None, a.rebuild)
    except Exception as exc:  # heartbeat must record failures too
        hb = repo / ".wall" / "derived" / "heartbeat.json"
        try:
            atomic_write(hb, json.dumps({"last_run": now_iso(), "ok": False,
                                         "error": str(exc)}, indent=2))
        except OSError:
            pass
        print(f"courier failed: {exc}", file=sys.stderr)
        return 1

    if not a.quiet:
        flags = snap["integrity"]
        n = len(flags["seq_gaps"]) + len(flags["orphan_runs"]) + len(flags["duplicates"])
        print(f"swept {snap['courier']['events']} events from "
              f"{snap['courier']['shards']} shards in {snap['courier']['last_run_ms']}ms"
              f"{f' — {n} integrity flags' if n else ''}")
        print(f"  {repo / '.wall' / 'derived' / 'wall.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
