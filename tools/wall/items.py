#!/usr/bin/env python3
"""items.py -- the materialized item view, and the one safe append primitive.

Item files under `.wall/items/<item_id>.json` are a **derived** artifact. The
event ledger is the primary record; `wall rebuild` regenerates every item file
from events alone and `wall diff-state` compares that regeneration against what
is on disk. A non-empty diff means something wrote out of band -- an agent
bypassing the protocol, or a bug in a writer. Both are worth knowing without
anyone having to notice (LOGGING_AND_AUDIT.md, "Auditing is a different
property than logging").

Three properties this module has to hold:

* **Deterministic.** The fold is a pure function of the event list. Same
  events in any read order produce byte-identical item files, because events
  are re-sorted on the total order `(ts, session_id, seq)` before folding.
* **Tolerant.** A malformed record is a named problem in the returned
  `problems` list, never an exception and never a silent skip. The sweep that
  calls this runs unattended every two minutes; a crash there is worse than a
  flag.
* **Additive.** Nothing here writes to a shard except `append_event`, which
  appends exactly one line with `O_APPEND`, so concurrent writers never
  interleave (EVENT_SCHEMA.md Section 6).

Stdlib only. No network. No model calls.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, NamedTuple

SCHEMA_VERSION = 1

# Events that move item state. Everything else is ignored by the fold.
ITEM_EVENTS = ("item_created", "item_state", "item_shipped")

# Keys that belong to the event envelope rather than to the item. Anything
# else on an item event is treated as an item field, so a new field needs no
# code change here -- which is the point, since the ledger outlives this file.
# `trace_id` is deliberately NOT in this set: an item keeps the trace it was
# minted under, and `wall trace <item_id>` resolves through it.
ENVELOPE_KEYS = frozenset({
    "schema_version", "event_id", "seq", "ts", "session_id", "event",
    "item_id", "agent_key", "agent_name", "agent_title", "role",
    "model_requested", "model_used", "run_id", "parent_run_id",
    "outcome", "error_class", "tokens", "cost_usd", "gh_minutes",
    "duration_s", "decisions_in_context", "field", "before", "after",
    "actor", "question_id", "ask_id", "question", "reason", "tier", "source",
    # Written by the SubagentStop hook, about the record rather than the item.
    "hook",
})

# A status that means the item is finished. Used by the G9 reconcile check.
TERMINAL_STATUSES = frozenset({
    "shipped", "merged", "closed", "done", "cancelled", "canceled", "abandoned",
})

# Fields the wall template indexes into as strings. They are never None.
STRING_FIELDS = ("title", "kind", "status")

# Required on every ledger record (EVENT_SCHEMA.md Section 2).
REQUIRED_EVENT_KEYS = ("event_id", "seq", "ts", "session_id", "event")


class FoldResult(NamedTuple):
    items: dict[str, dict]
    problems: list[dict]


# ------------------------------------------------------------------ ordering

def order_key(event: Any) -> tuple[str, str, int]:
    """The total order from EVENT_SCHEMA.md Section 6: (ts, session_id, seq).

    Coerces every component to its declared type. A shard with a null `seq` or
    a numeric `session_id` then sorts deterministically instead of raising
    TypeError halfway through a sweep.
    """
    if not isinstance(event, dict):
        return ("", "", 0)
    ts = event.get("ts")
    sid = event.get("session_id")
    seq = event.get("seq")
    return (
        ts if isinstance(ts, str) else "",
        sid if isinstance(sid, str) else "",
        seq if isinstance(seq, int) and not isinstance(seq, bool) else 0,
    )


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _ts_of(event: dict) -> str | None:
    ts = event.get("ts")
    return ts if isinstance(ts, str) and ts else None


def parse_ts(value: Any) -> datetime | None:
    """Parse an ISO-8601 ledger timestamp. Returns None rather than raising."""
    if not isinstance(value, str) or not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def is_terminal(status: Any) -> bool:
    return isinstance(status, str) and status.strip().lower() in TERMINAL_STATUSES


# ---------------------------------------------------------------- the fold

def _blank(item_id: str) -> dict:
    return {
        "item_id": item_id,
        "title": "",
        "kind": "",
        "status": "",
        "arc_id": None,
        "arc_title": None,
        "assignee": None,
        "estimate": None,
        "actual": None,
        "duplicate_of": None,
        "trace_id": None,
        "scope": [],
        "pr": None,
        "shipped_at": None,
        "created_at": None,
        "updated_at": None,
        "events": 0,
    }


def trace_ids_by_item(events: list) -> dict[str, str]:
    """First trace_id seen for each item, across every event kind.

    Item events do not always carry the trace; run records almost always do.
    Resolving `wall trace <item_id>` needs the union.
    """
    out: dict[str, str] = {}
    for e in sorted((e for e in events if isinstance(e, dict)), key=order_key):
        iid, tid = e.get("item_id"), e.get("trace_id")
        if isinstance(iid, str) and iid and isinstance(tid, str) and tid:
            out.setdefault(iid, tid)
    return out


def fold(events: list) -> FoldResult:
    """Regenerate item state from events alone. Pure and deterministic."""
    problems: list[dict] = []
    clean: list[dict] = []
    for e in events:
        if isinstance(e, dict):
            clean.append(e)
        else:
            problems.append({"kind": "malformed_event",
                             "detail": f"record is {type(e).__name__}, not an object"})

    items: dict[str, dict] = {}
    for e in sorted(clean, key=order_key):
        ev = e.get("event")
        if ev not in ITEM_EVENTS:
            continue
        iid = e.get("item_id")
        if not isinstance(iid, str) or not iid.strip():
            problems.append({"kind": "item_event_without_id", "event": ev,
                             "event_id": e.get("event_id"),
                             "detail": "item event carries no usable item_id"})
            continue
        iid = iid.strip()
        rec = items.setdefault(iid, _blank(iid))
        rec["events"] += 1
        ts = _ts_of(e)

        if ev == "item_created" and rec["created_at"] is None:
            rec["created_at"] = ts

        field = e.get("field")
        if isinstance(field, str) and field and "after" in e:
            # Delta shape: {field, before, after}. EVENT_SCHEMA.md Section 3.
            if field in ("item_id", "event", "ts", "event_id", "seq", "session_id"):
                problems.append({"kind": "protected_field_write", "item_id": iid,
                                 "field": field, "event_id": e.get("event_id"),
                                 "detail": "a delta may not rewrite the envelope"})
            else:
                rec[field] = e["after"]
        else:
            # Snapshot shape: every non-envelope key is an item field.
            for k, v in e.items():
                if k in ENVELOPE_KEYS:
                    continue
                rec[k] = v

        if ev == "item_shipped":
            pr = e.get("pr", e.get("pr_number"))
            if pr is not None:
                rec["pr"] = pr
            rec["shipped_at"] = ts or rec["shipped_at"]
            # G9: the shipping event flips state at merge time, not whenever
            # the bookkeeping catches up.
            if not is_terminal(rec.get("status")):
                rec["status"] = "shipped"

        if ts:
            rec["updated_at"] = ts

    traces = trace_ids_by_item(clean)
    for iid, rec in items.items():
        if not rec.get("trace_id") and traces.get(iid):
            rec["trace_id"] = traces[iid]
        for key in STRING_FIELDS:
            if not isinstance(rec.get(key), str):
                rec[key] = "" if rec.get(key) is None else str(rec[key])
        if rec.get("created_at") is None:
            rec["created_at"] = rec.get("updated_at")

    return FoldResult(items, problems)


def fold_items(events: list) -> dict[str, dict]:
    """Convenience wrapper for callers that do not inspect problems."""
    return fold(events).items


# ---------------------------------------------------------------- disk view

def items_dir(repo: Path) -> Path:
    return Path(repo) / ".wall" / "items"


def serialize_item(record: dict) -> str:
    """One canonical spelling per item, so a rebuild is byte-stable."""
    return json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _safe_name(item_id: str) -> str:
    """Item ids are human-typeable (ARC-01, ST-104). Anything that could walk
    out of the directory is refused rather than sanitised into a collision."""
    return "".join(c for c in item_id if c.isalnum() or c in "-_.")


def load_disk_items(repo: Path) -> tuple[dict[str, dict], list[dict]]:
    """Read `.wall/items/*.json`. An unreadable file is a named problem."""
    found: dict[str, dict] = {}
    problems: list[dict] = []
    d = items_dir(repo)
    if not d.is_dir():
        return found, problems
    for path in sorted(d.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            problems.append({"kind": "unreadable_item", "path": path.name,
                             "detail": str(exc)})
            continue
        if not isinstance(data, dict):
            problems.append({"kind": "unreadable_item", "path": path.name,
                             "detail": "item file is not a JSON object"})
            continue
        iid = data.get("item_id")
        if not isinstance(iid, str) or not iid:
            iid = path.stem
            problems.append({"kind": "item_id_missing", "path": path.name,
                             "detail": f"no item_id in file; keyed on stem {path.stem}"})
        found[iid] = data
    return found, problems


def diff_items(derived: dict[str, dict], disk: dict[str, dict]) -> list[dict]:
    """Field-level diff of the ledger-derived view against disk.

    Sorted, so the same drift renders the same way every sweep.
    """
    drift: list[dict] = []
    for iid in sorted(set(derived) | set(disk)):
        want, have = derived.get(iid), disk.get(iid)
        if want is not None and have is None:
            drift.append({"item_id": iid, "kind": "missing_on_disk",
                          "detail": "the ledger knows this item; no item file exists"})
            continue
        if want is None and have is not None:
            drift.append({"item_id": iid, "kind": "extra_on_disk",
                          "detail": "an item file exists that no event created"})
            continue
        assert want is not None and have is not None  # both present
        for key in sorted(set(want) | set(have)):
            a, b = want.get(key, None), have.get(key, None)
            if a != b:
                drift.append({"item_id": iid, "kind": "field_mismatch",
                              "field": key, "expected": a, "found": b})
    return drift


def diff_state(repo: Path, events: list | None = None) -> dict:
    """Compare ledger-derived item state against disk.

    Honest degrade: when `.wall/items/` does not exist at all, nothing has
    ever been rebuilt, so every item would read as drift. That is noise, not
    a finding -- report `checked: False` and a drift count of zero instead.
    """
    repo = Path(repo)
    if events is None:
        events = load_events(repo)
    derived, fold_problems = fold(events)
    if not items_dir(repo).is_dir():
        return {"checked": False, "count": 0, "drift": [],
                "problems": fold_problems,
                "note": "no .wall/items/ directory; run `wall rebuild` to materialize it"}
    disk, disk_problems = load_disk_items(repo)
    drift = diff_items(derived, disk)
    return {"checked": True, "count": len(drift), "drift": drift,
            "problems": fold_problems + disk_problems, "note": ""}


def rebuild(repo: Path, events: list | None = None, prune: bool = False) -> dict:
    """Write `.wall/items/<id>.json` from events alone.

    Idempotent: re-running with the same events rewrites byte-identical files
    and reports everything unchanged. Files on disk that no event created are
    reported and only removed with `prune=True` -- deleting somebody's work
    because the ledger has not caught up is worse than a stale file.
    """
    repo = Path(repo)
    if events is None:
        events = load_events(repo)
    derived, problems = fold(events)
    d = items_dir(repo)
    d.mkdir(parents=True, exist_ok=True)

    written, unchanged, skipped = [], [], []
    for iid in sorted(derived):
        name = _safe_name(iid)
        if not name:
            skipped.append(iid)
            problems.append({"kind": "unwritable_item_id", "item_id": iid,
                             "detail": "item_id has no filesystem-safe characters"})
            continue
        path = d / f"{name}.json"
        text = serialize_item(derived[iid])
        try:
            current = path.read_text(encoding="utf-8")
        except OSError:
            current = None
        if current == text:
            unchanged.append(iid)
            continue
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
        written.append(iid)

    disk, disk_problems = load_disk_items(repo)
    problems += disk_problems
    orphans = sorted(set(disk) - set(derived))
    removed = []
    if prune:
        for iid in orphans:
            path = d / f"{_safe_name(iid)}.json"
            try:
                path.unlink()
                removed.append(iid)
            except OSError as exc:
                problems.append({"kind": "unremovable_item", "item_id": iid,
                                 "detail": str(exc)})
    return {"written": written, "unchanged": unchanged, "removed": removed,
            "orphans": [] if prune else orphans, "skipped": skipped,
            "problems": problems, "items": len(derived)}


# ------------------------------------------------- G9: merged but still open

def merged_but_open(events: list, disk: dict[str, dict] | None = None) -> list[dict]:
    """RECONCILIATION G9 -- a merge can outrun its own bookkeeping.

    Observed between PRs #1654 and #1655: a PR merged before its board
    fragments were compacted left the wall claiming "in CI" on a merged PR.
    Two shapes of that contradiction are detectable from the ledger:

    * `reopened_after_ship` -- a terminal `item_shipped` exists, yet a *later*
      `item_state` puts the item back into a non-terminal status. The fold is
      faithful; the bookkeeping is wrong.
    * `disk_open_after_ship` -- the ledger says shipped, the item file on disk
      still claims an open PR or a non-terminal status.

    Returns one flag per item, so a lagging compactor is one line, not two.
    """
    derived, _ = fold(events)
    shipped_at: dict[str, str] = {}
    shipped_pr: dict[str, Any] = {}
    for e in sorted((e for e in events if isinstance(e, dict)), key=order_key):
        if e.get("event") != "item_shipped":
            continue
        iid = e.get("item_id")
        if isinstance(iid, str) and iid:
            shipped_at[iid] = _ts_of(e) or shipped_at.get(iid, "")
            pr = e.get("pr", e.get("pr_number"))
            if pr is not None:
                shipped_pr[iid] = pr

    flags: list[dict] = []
    for iid in sorted(shipped_at):
        rec = derived.get(iid, {})
        pr = shipped_pr.get(iid, rec.get("pr"))
        if not is_terminal(rec.get("status")):
            flags.append({
                "item_id": iid, "kind": "reopened_after_ship", "pr": pr,
                "status": rec.get("status"), "shipped_at": shipped_at[iid],
                "detail": "item_shipped is on the ledger but a later event put "
                          "the item back to a non-terminal status",
            })
            continue
        have = (disk or {}).get(iid)
        if have is None:
            continue
        open_pr = have.get("pr_state") == "open" or have.get("pr_open") is True
        if open_pr or not is_terminal(have.get("status")):
            flags.append({
                "item_id": iid, "kind": "disk_open_after_ship", "pr": pr,
                "status": have.get("status"), "shipped_at": shipped_at[iid],
                "detail": "the ledger shipped this item; the item file on disk "
                          "still claims it is open",
            })
    return flags


# -------------------------------------------------------- ledger schema gate

def ledger_schema_check(events_dir: Path) -> list[dict]:
    """Validate every line under `.wall/events/**` against EVENT_SCHEMA.md.

    This is the free local gate fast-track runs instead of CI. It reads the
    shards directly rather than the merged ledger, because the point is to
    catch a bad *write* before it is shipped anywhere.
    """
    problems: list[dict] = []
    events_dir = Path(events_dir)
    if not events_dir.is_dir():
        return problems
    seen_ids: dict[str, str] = {}
    seqs: dict[str, dict[int, int]] = {}
    for shard in sorted(events_dir.rglob("*.jsonl")):
        rel = str(shard.relative_to(events_dir))
        try:
            text = shard.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            problems.append({"kind": "unreadable_shard", "shard": rel, "detail": str(exc)})
            continue
        lines = text.splitlines()
        # A trailing partial line means a writer is mid-append, not corruption.
        trailing_partial = bool(text) and not text.endswith("\n")
        for n, line in enumerate(lines, 1):
            if trailing_partial and n == len(lines):
                continue
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except json.JSONDecodeError as exc:
                problems.append({"kind": "unparseable_line", "shard": rel,
                                 "line": n, "detail": str(exc)})
                continue
            if not isinstance(e, dict):
                problems.append({"kind": "unparseable_line", "shard": rel, "line": n,
                                 "detail": "line is not a JSON object"})
                continue
            for key in REQUIRED_EVENT_KEYS:
                if e.get(key) in (None, ""):
                    problems.append({"kind": "missing_field", "shard": rel,
                                     "line": n, "field": key})
            eid = e.get("event_id")
            if isinstance(eid, str) and eid:
                where = f"{rel}:{n}"
                if eid in seen_ids:
                    problems.append({"kind": "duplicate_event_id", "event_id": eid,
                                     "detail": f"{seen_ids[eid]} and {where}"})
                else:
                    seen_ids[eid] = where
            sid, seq = e.get("session_id"), e.get("seq")
            if isinstance(sid, str) and isinstance(seq, int) and not isinstance(seq, bool):
                counts = seqs.setdefault(sid, {})
                counts[seq] = counts.get(seq, 0) + 1
    for sid in sorted(seqs):
        nums = seqs[sid]
        if not nums:
            continue
        for missing in sorted(set(range(min(nums), max(nums) + 1)) - set(nums)):
            problems.append({"kind": "seq_gap", "session_id": sid, "seq": missing})
        # A gap is a lost write; a duplicate is two hooks racing on a
        # deliberately non-atomic next_seq. Both are reported, because
        # catching one and not the other lets the other pass as healthy.
        for seq in sorted(n for n, count in nums.items() if count > 1):
            problems.append({"kind": "seq_duplicate", "session_id": sid,
                             "seq": seq, "detail": f"{nums[seq]} records share "
                                                   f"seq {seq} in {sid}"})
    return problems


# ------------------------------------------------------------ reading events

def load_events(repo: Path) -> list[dict]:
    """Every event the repo knows about, in total order.

    Prefers the merged ledger Courier already wrote; falls back to reading the
    shards directly so `wall trace` works before the first sweep. Ordering and
    dedupe come from courier.merge so there is exactly one definition of the
    total order in the kit.
    """
    repo = Path(repo)
    ledger = repo / ".wall" / "derived" / "ledger.jsonl"
    events: list[dict] = []
    if ledger.exists():
        try:
            for line in ledger.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(e, dict):
                    events.append(e)
        except OSError:
            events = []
    if events:
        return sorted(events, key=order_key)

    import courier  # local import: courier imports this module at load time

    events_dir = repo / ".wall" / "events"
    if not events_dir.is_dir():
        return []
    fresh, _, _ = courier.read_shards(events_dir, {})
    return courier.merge(repo / ".wall" / "derived" / "__absent__.jsonl", fresh)


# ------------------------------------------------------------ writing events

def next_seq(repo: Path, session_id: str) -> int:
    """`seq` is monotonic per session across days, so every shard for that
    session is scanned. A gap is corruption; a collision is worse."""
    highest = 0
    events_dir = Path(repo) / ".wall" / "events"
    if not events_dir.is_dir():
        return 1
    for shard in events_dir.rglob(f"{session_id}.jsonl"):
        try:
            text = shard.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            seq = e.get("seq") if isinstance(e, dict) else None
            if isinstance(seq, int) and not isinstance(seq, bool) and seq > highest:
                highest = seq
    return highest + 1


def append_event(repo: Path, session_id: str, payload: dict,
                 ts: str | None = None, day: str | None = None) -> dict:
    """Append exactly one record to this session's shard for the day.

    One `write()` under `O_APPEND`, so concurrent writers never interleave
    (EVENT_SCHEMA.md Section 6). Shards are never rewritten.
    """
    repo = Path(repo)
    ts = ts or now_iso()
    day = day or ts[:10]
    record = {
        "schema_version": SCHEMA_VERSION,
        "event_id": str(uuid.uuid4()),
        "seq": next_seq(repo, session_id),
        "ts": ts,
        "session_id": session_id,
    }
    record.update({k: v for k, v in payload.items() if k not in record})
    shard = repo / ".wall" / "events" / day / f"{session_id}.jsonl"
    shard.parent.mkdir(parents=True, exist_ok=True)
    line = (json.dumps(record, ensure_ascii=False) + "\n").encode("utf-8")
    fd = os.open(str(shard), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        os.write(fd, line)
    finally:
        os.close(fd)
    return record
