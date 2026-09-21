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

sys.path.insert(0, str(Path(__file__).parent))

import items as items_mod        # noqa: E402  materialized item view + total order
import questions as questions_mod  # noqa: E402  question lifecycle + invariants
import oversight as oversight_mod  # noqa: E402  RETRO/POSTURE/DOCS folds (DEC-0026)

SCHEMA_VERSION = 1
DATA_MARKER = "__WALL_DATA__"
REPO_MARKER = "__REPO_NAME__"

# Advisory only. Nothing in this file stops work; it renders a warning.
DEFAULT_BUDGET = {
    "period": "week to date",
    "advisory": "Budgets are advisory. Nothing here stops work — it tells you when to.",
    "meters": [],
}


# ----------------------------------------------------------- budget pacing

def _budget_dt(s):
    """Parse an ISO stamp; None on anything else. Zulu accepted."""
    if not isinstance(s, str):
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _meter_usage(meter: dict, ev: dict) -> float | None:
    """How much of THIS meter one run_end event consumed, or None if the meter
    has no usage source configured (a static meter stays static, honestly)."""
    match = meter.get("match_model")
    if match:
        model = (ev.get("model_used") or "").lower()
        if match.lower() in model:
            tok = ev.get("tokens") or {}
            return float((tok.get("in") or 0) + (tok.get("out") or 0))
        return 0.0
    counts = meter.get("counts")
    if counts in ("gh_minutes", "cost_usd"):
        v = ev.get(counts)
        return float(v) if isinstance(v, (int, float)) else 0.0
    return None


def enrich_budget(budget: dict, events: list[dict], now: datetime) -> dict:
    """Balance, %-remaining, measured velocity and a projected exhaustion date
    per meter, plus a pace verdict the rebalancing table consumes.

    Everything here is measured or honestly absent -- a meter with no usage
    source reads `unknown`, a meter with a source but no burn in the window
    reads `idle` with no fabricated date, and `strict: true` (a hard list-price
    cap) turns an early projected exhaustion into a mandatory `slow` rather
    than an advisory one. Pure: no I/O, no clock reads -- `now` is passed in.
    """
    out = json.loads(json.dumps(budget))  # never mutate the caller's config
    period_start = _budget_dt(out.get("period_start")) or now.replace(
        day=1, hour=0, minute=0, second=0, microsecond=0)
    period_end = _budget_dt(out.get("period_end"))
    if period_end is None:
        period_end = (period_start.replace(year=period_start.year + 1, month=1)
                      if period_start.month == 12 else
                      period_start.replace(month=period_start.month + 1))
    total_s = max((period_end - period_start).total_seconds(), 1.0)
    pct_period_remaining = max(0.0, min(100.0,
        (period_end - now).total_seconds() / total_s * 100.0))
    window_s = min(7 * 86400.0, max((now - period_start).total_seconds(), 3600.0))
    window_start = now.__class__.fromtimestamp(now.timestamp() - window_s, tz=now.tzinfo)

    runs = []
    for ev in events:
        if ev.get("event") != "run_end":
            continue
        ts = _budget_dt(ev.get("ts"))
        if ts is not None:
            runs.append((ts, ev))

    for m in out.get("meters", []):
        limit = m.get("limit") or 0
        measured = None
        window_sum = None
        probe = _meter_usage(m, {"event": "run_end"})
        has_source = not (probe is None and not m.get("match_model")
                          and m.get("counts") not in ("gh_minutes", "cost_usd"))
        if m.get("match_model") or m.get("counts") in ("gh_minutes", "cost_usd"):
            measured = 0.0
            window_sum = 0.0
            for ts, ev in runs:
                u = _meter_usage(m, ev)
                if not u:
                    continue
                if ts >= period_start:
                    measured += u
                if ts >= window_start:
                    window_sum += u
        else:
            has_source = False

        used_total = float(m.get("used") or 0) + (measured or 0.0)
        m["measured"] = measured
        m["used_total"] = used_total
        m["pct_remaining"] = (round(max(0.0, (limit - used_total) / limit * 100.0), 1)
                              if limit else None)
        velocity = (round(window_sum / (window_s / 86400.0), 2)
                    if window_sum is not None else None)
        m["velocity_per_day"] = velocity
        m["projected_exhaustion"] = None

        if not limit:
            m["pace"] = {"verdict": "unmetered", "detail": "no limit configured"}
            continue
        if not has_source:
            m["pace"] = {"verdict": "unknown",
                         "detail": "no usage source configured (match_model / counts)"}
            continue
        remaining = limit - used_total
        if remaining <= 0:
            m["pace"] = {"verdict": "exhausted",
                         "detail": ("hard cap reached -- stop the spend line"
                                    if m.get("strict") else
                                    "over budget -- overage is the engineer's call")}
            continue
        if not velocity:
            m["pace"] = {"verdict": "idle",
                         "detail": "no burn in the trailing window; no date projected"}
            continue
        days_left = remaining / velocity
        exhaustion = now.__class__.fromtimestamp(
            now.timestamp() + days_left * 86400.0, tz=now.tzinfo)
        m["projected_exhaustion"] = exhaustion.date().isoformat()
        if exhaustion < period_end:
            m["pace"] = {"verdict": "slow",
                         "detail": ("exhausts ~%s, before the period ends %s -- "
                                    % (exhaustion.date(), period_end.date()))
                         + ("hard list-price cap: pace work to land at the period end"
                            if m.get("strict") else
                            "overage budget: the engineer decides, projection attached")}
        elif (m["pct_remaining"] or 0) - pct_period_remaining > 20:
            m["pace"] = {"verdict": "may speed",
                         "detail": "%.0f%% remaining vs %.0f%% of the period left -- "
                                   "headroom to raise the pace"
                                   % (m["pct_remaining"], pct_period_remaining)}
        else:
            m["pace"] = {"verdict": "on pace",
                         "detail": "burn matches the period at current velocity"}

    out["period_start"] = period_start.isoformat()
    out["period_end"] = period_end.isoformat()
    out["pct_period_remaining"] = round(pct_period_remaining, 1)
    return out


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

def read_shards(events_dir: Path, checkpoints: dict) -> tuple[list[dict], dict, int, int]:
    """Read only the unread tail of each shard.

    Returns (events, checkpoints, shard_count, corrupt_lines). corrupt_lines
    counts complete lines that failed to parse this run -- they are skipped so
    the sweep survives, but they are COUNTED so the heartbeat can say so
    instead of folding "some events were unreadable" into ok: true.
    """
    events: list[dict] = []
    corrupt = 0
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
                record = json.loads(line)
            except json.JSONDecodeError:
                corrupt += 1  # skipped, but counted -- the heartbeat reports it
                continue
            if not isinstance(record, dict):
                # `null`, a bare list or a scalar parse fine and then get
                # silently dropped by merge() -- corrupt in effect, so
                # corrupt in the count, or the heartbeat lies ok.
                corrupt += 1
                continue
            events.append(record)
        checkpoints[key] = consumed
    return events, checkpoints, len(shards), corrupt


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
                    except json.JSONDecodeError:
                        continue
                    if isinstance(e, dict):   # a bare scalar line is not a record
                        by_id[e.get("event_id", "")] = e
    for e in new_events:
        if isinstance(e, dict):
            by_id[e.get("event_id", "")] = e
    # One definition of the total order, in items.order_key, which coerces each
    # component to its declared type so a null seq sorts instead of raising.
    return sorted(by_id.values(), key=items_mod.order_key)


# --------------------------------------------------------------- integrity

def check_integrity(events: list[dict], items: dict, stale_after_min: int = 30,
                    repo: Path | None = None) -> dict:
    # Both directions of the same property. `next_seq` is deliberately not
    # atomic across hook processes: two terminal records written in the same
    # instant can land on one number. That is a concurrency artifact and it is
    # *visible*; a gap is a lost write. Flagging only one of them means the
    # other passes as healthy, so the validator catches both.
    seq_gaps, seq_duplicates = [], []
    seen: dict = defaultdict(lambda: defaultdict(int))
    for e in events:
        seq = e.get("seq")
        if isinstance(seq, int) and not isinstance(seq, bool):
            seen[e.get("session_id")][seq] += 1
    for session in sorted(seen, key=lambda s: str(s)):
        nums = seen[session]
        if not nums:
            continue
        for missing in sorted(set(range(min(nums), max(nums) + 1)) - set(nums)):
            seq_gaps.append({"session_id": session, "seq": missing})
        for seq in sorted(n for n, count in nums.items() if count > 1):
            seq_duplicates.append({"session_id": session, "seq": seq,
                                   "count": nums[seq]})

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
        title = item.get("title")
        # An untitled item is not a duplicate of every other untitled item.
        if isinstance(title, str) and title.strip():
            titles[title.strip().lower()].append(iid)
        if item.get("duplicate_of"):
            duplicates.append([iid, item["duplicate_of"]])
    duplicates += [ids for ids in titles.values() if len(ids) > 1]

    # Materialized item files vs the ledger that derives them. Skipped, with
    # `state_drift_checked: false`, when no rebuild has ever run -- otherwise a
    # fresh repo reports every item as drift, which is noise, not a finding.
    drift = {"checked": False, "count": 0, "drift": [], "problems": []}
    disk_items: dict = {}
    if repo is not None:
        try:
            drift = items_mod.diff_state(repo, events)
            disk_items, _ = items_mod.load_disk_items(repo)
        except OSError as exc:      # a read failure is a flag, not a dead sweep
            drift = {"checked": False, "count": 0, "drift": [],
                     "problems": [{"kind": "diff_state_failed", "detail": str(exc)}]}

    return {
        "seq_gaps": seq_gaps,
        "seq_duplicates": seq_duplicates,
        "orphan_runs": orphans,
        "duplicates": duplicates,
        # An int: the wall template renders this as a count.
        "state_drift": drift["count"],
        "state_drift_checked": drift["checked"],
        "state_drift_detail": drift["drift"],
        "fold_problems": drift.get("problems", []),
        # RECONCILIATION G9 -- a merge can outrun its own bookkeeping.
        "merged_but_open": items_mod.merged_but_open(events, disk_items),
        "escalations": [],     # populated in build_snapshot, once crew is known
        "stale_claims": [],    # populated by the Foreman pass
    }


# ---------------------------------------------------------------- snapshot

def build_snapshot(repo: Path, events: list[dict], config: dict, shard_count: int,
                   run_ms: int) -> dict:
    agents: dict[str, dict] = {}
    asks: dict[str, dict] = {}
    sessions: set[str] = set()

    # The board is the same materialized view `wall rebuild` writes and
    # `wall diff-state` audits. One fold, so the wall and the item files can
    # never disagree about what the ledger says.
    items = items_mod.fold_items(events)

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
        arc_id = it.get("arc_id") or "unassigned"
        arc = arcs.setdefault(arc_id, {
            "arc_id": arc_id, "title": it.get("arc_title") or "Unassigned", "items": [],
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

    integrity = check_integrity(events, items, config.get("stale_after_min", 30), repo)

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

    # WORKFLOW.md Section 4: escalation is an invariant, checked every sweep,
    # so a lapse surfaces whether or not Maestro remembered. Needs the crew,
    # hence here rather than inside check_integrity.
    folded_questions = questions_mod.fold(events).questions
    integrity["escalations"] = questions_mod.escalation_flags(
        folded_questions, items, list(agents.values()),
        config.get("sla_minutes", {}))

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
        "questions": sorted(folded_questions.values(),
                            key=lambda q: (q.get("raised_at") or "", q["question_id"])),
        "budget": enrich_budget(config.get("budget", DEFAULT_BUDGET), events,
                                datetime.now(timezone.utc)),
        # Host integration seams, verbatim from config (None when unset, and
        # the template renders nothing for either): queue_api lights the
        # EXECUTE actions ONLY where the named health endpoint answers ok;
        # agents_feed lights the CREW tab's live-wave section.
        "queue_api": config.get("queue_api"),
        "agents_feed": config.get("agents_feed"),
        "rollup_by_role": sorted(rollup.values(), key=lambda r: (r["role"], r["model"])),
        "sessions": sorted(sessions),
        # RETRO / POSTURE / DOCS tabs (DEC-0026): pure folds over the same
        # ordered event list, plus the documents-of-record registry hashes.
        "oversight": oversight_mod.build_oversight(repo, events, config),
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
    new_events, checkpoints, shard_count, corrupt_lines = read_shards(
        events_dir, state.get("checkpoints", {}))
    all_events = merge(ledger, new_events)

    run_ms = int((time.perf_counter() - started) * 1000)
    snapshot = build_snapshot(repo, all_events, config, shard_count, run_ms)

    atomic_write(ledger, "".join(
        json.dumps(e, ensure_ascii=False, sort_keys=True) + "\n" for e in all_events))
    atomic_write(derived / "wall.json", json.dumps(snapshot, ensure_ascii=False, indent=2))
    atomic_write(derived / "wall.html", render(snapshot, template))
    atomic_write(state_path, json.dumps({"checkpoints": checkpoints}, indent=2))
    # ok is a verdict about THIS run's read health, not a constant: a run that
    # had to skip unparseable shard lines completed, but not cleanly.
    atomic_write(wall / "derived" / "heartbeat.json", json.dumps({
        "last_run": snapshot["generated_at"], "run_ms": run_ms,
        "events": len(all_events), "ok": corrupt_lines == 0,
        "corrupt_lines": corrupt_lines,
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
