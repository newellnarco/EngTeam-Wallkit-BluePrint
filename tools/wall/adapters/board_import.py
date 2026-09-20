#!/usr/bin/env python3
"""board_import.py -- lay the wall over a project that is already underway.

A fresh wall is an empty wall, and an empty wall tells a team nothing on the
day they adopt it. This importer reads a project's existing tracker and files
it into the ledger as ordinary `item_created` / `item_state` events, so the
STORIES tab shows the real arcs, stories and bugs from the first sweep.

Three properties it has to hold:

* **Additive.** It writes events, nothing else. It never edits `board_state.json`
  or any other file belonging to the source project, and it never rewrites a
  shard -- one JSON line per record, `O_APPEND`, into this session's shard
  (EVENT_SCHEMA.md Sections 2 and 6).
* **Idempotent.** Re-running it is a no-op. The ledger is folded first; an item
  whose current state already matches the source is skipped, an item whose
  fields moved gets one `item_state` delta, and only a genuinely new item gets
  an `item_created`.
* **Declarative.** A tracker is described by a profile dict -- which key holds
  the id, which holds the title, how its statuses and types map onto the wall's
  vocabulary. Supporting a new tracker is a dict, not a subclass.

Two profiles ship: `PROFILE_GENERIC` (the documented shape) and `PROFILE_MAX3`
(MAX3's `docs/project/board_state.json`).

    python3 -m adapters.board_import --repo . --source board_state.json --profile max3

Run it from `tools/wall/`, so that `adapters` is an importable package.
Stdlib only. No network. No model calls.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import items as items_mod  # noqa: E402  -- read-only: the fold and the envelope

SCHEMA_VERSION = 1

#: The actor recorded on every event this importer writes. One key, so the
#: ledger can always answer "which rows did the overlay put here?".
IMPORT_ACTOR = "imp_boardimp"

#: Default shard. Deterministic, so a second run appends to the same session
#: and `seq` stays monotonic for it.
DEFAULT_SESSION = "s_boardimp"

#: The wall's status vocabulary. A profile may map onto anything, but these are
#: the six the template styles; anything else renders literally in a neutral
#: chip rather than being dropped.
WALL_STATUSES = ("planned", "in_progress", "blocked", "review", "done", "shipped")

#: The wall's item kinds.
WALL_KINDS = ("arc", "story", "bug")

#: Where an item with no arc goes. The courier uses the same sentinel when it
#: groups the board, and the STORIES tab renders this bucket as the loose
#: stories and bugs below the arcs. It is written explicitly rather than left
#: unset: the fold blanks `arc_id` to None, and a None sorts against no string.
UNASSIGNED_ARC_ID = "unassigned"
UNASSIGNED_ARC_TITLE = "Unassigned"

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

#: Placeholders trackers write where they mean "nothing". MAX3's board uses
#: `--` in its `pr` column; carrying that through would put a literal `--` on
#: the wall as if it were a PR reference.
NULL_TOKENS = frozenset({"", "-", "--", "---", "n/a", "na", "none", "null", "tbd", "?"})


def _is_blank(value: Any) -> bool:
    if value is None or value == [] or value == {}:
        return True
    return isinstance(value, str) and value.strip().lower() in NULL_TOKENS


# ------------------------------------------------------------------ profiles

PROFILE_GENERIC: dict[str, Any] = {
    "name": "generic",
    # Where the item list lives inside the source document. [] means the
    # document itself is the list.
    "items_path": ["items"],
    # Document-level fallback for "when was this last touched".
    "source_updated_field": "updated",

    # ---- field mappings: wall field <- source key -------------------------
    "id_field": "id",
    "title_field": "title",
    "status_field": "status",
    "type_field": "type",
    "updated_field": "updated_at",
    "arc_id_field": "arc",
    "arc_title_field": "arc_title",
    "assignee_field": "assignee",
    "estimate_field": "estimate",
    "actual_field": "actual",
    "parent_field": "parent_id",
    # Copied through verbatim as item fields: {wall field: source key}.
    "extra_fields": {"pr": "pr", "priority": "priority", "area": "area"},

    # ---- vocabulary -------------------------------------------------------
    # Keys are lowercased and whitespace/dash-normalised before lookup.
    "status_map": {
        "planned": "planned", "todo": "planned", "backlog": "planned",
        "open": "planned", "new": "planned", "ready": "planned",
        "in_progress": "in_progress", "active": "in_progress", "wip": "in_progress",
        "blocked": "blocked",
        "review": "review", "in_review": "review", "needs_review": "review",
        "done": "done", "closed": "done", "complete": "done", "completed": "done",
        "shipped": "shipped", "merged": "shipped", "released": "shipped",
    },
    "default_status": "planned",
    # A status that also deserves a human-readable note on the item.
    "status_notes": {},

    "type_map": {
        "bug": "bug", "defect": "bug", "fix": "bug",
        "arc": "arc", "epic": "arc",
    },
    "default_kind": "story",
    # Checked before `type_map`: (id prefix, kind). First match wins.
    "kind_from_id": [("bug", "bug"), ("fix", "bug")],
}


PROFILE_MAX3: dict[str, Any] = {
    "name": "max3",
    "items_path": ["items"],
    "source_updated_field": "updated",

    # MAX3 keys the board on a stable slug (`brain:fibonacci-sequences`) and
    # that slug is what every other MAX3 tool refers to, so it becomes the
    # item id verbatim rather than being renumbered into something new.
    "id_field": "key",
    "title_field": "title",
    "status_field": "status",
    "type_field": "type",
    # No per-item timestamp on the MAX3 board; the document-level `updated`
    # carries the whole file's last touch, which is the honest answer.
    "updated_field": None,
    # `arch` is MAX3's arc family -- PR-COG, DUCK-MIG, QA-LIVE.
    "arc_id_field": "arch",
    "arc_title_field": None,
    "assignee_field": None,
    "estimate_field": "size",
    "actual_field": None,
    "parent_field": None,
    # `detail` is MAX3's long-form item prose (design notes, as-builts --
    # routinely kilobytes). It rides through verbatim: the wall's STORIES tab
    # renders it behind a per-row toggle, and dropping it would violate the
    # adoption requirement that every item's detail survives the new wall.
    "extra_fields": {"pr": "pr", "priority": "priority", "area": "area",
                     "issue": "issue", "phase": "phase", "detail": "detail"},

    "status_map": {
        "todo": "planned", "backlog": "planned", "planned": "planned",
        "in_ci": "review",
        "in_progress": "in_progress",
        "shipped": "shipped",
        "done": "done",
        # MAX3's "Deferred" is not "blocked by a dependency" -- it is a
        # deliberate parking. It maps to blocked so it reads as not-moving,
        # and carries the reason so the board does not lie about why.
        "deferred": "blocked",
        "closed_no_op": "done",
    },
    "default_status": "planned",
    "status_notes": {
        "deferred": "deferred on the source board",
        "closed_no_op": "closed as a no-op on the source board",
    },

    "type_map": {
        "bug": "bug", "bug_fix": "bug", "fix": "bug", "defect": "bug",
    },
    "default_kind": "story",
    # MAX3's board has no arc rows -- arcs come from the `arch` grouping field,
    # so this heuristic only has to separate bugs from stories.
    "kind_from_id": [("fix", "bug"), ("bug", "bug"), ("qa", "bug")],
}


PROFILES: dict[str, dict[str, Any]] = {
    "generic": PROFILE_GENERIC,
    "max3": PROFILE_MAX3,
}


# ------------------------------------------------------------------ helpers

def _norm(value: Any) -> str:
    """Lowercase, trim, and fold whitespace/dashes to underscores.

    `in CI`, `In-CI` and `in_ci` are the same status written three ways; a
    vocabulary that only recognises one of them silently mislabels the board.
    """
    return re.sub(r"[\s\-/]+", "_", str(value or "").strip().lower())


def _iso(value: Any, fallback: str) -> str:
    """Normalise a source timestamp to the ledger's format, or fall back.

    A date with no time is midnight UTC -- stated, not guessed at render time.
    """
    if isinstance(value, str) and value.strip():
        text = value.strip()
        if _ISO_DATE.match(text):
            return f"{text}T00:00:00.000Z"
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return fallback
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    return fallback


def trace_for(item_id: str) -> str:
    """A deterministic trace id per item.

    The same item imported into two clones gets the same trace, so
    `wall trace <item_id>` resolves identically on both -- and a re-import
    cannot mint a second trace for work that already has one.
    """
    digest = hashlib.sha1(item_id.encode("utf-8")).hexdigest()[:10]
    return f"tr_imp_{digest}"


def validate_profile(profile: dict) -> None:
    """Refuse a profile that would write into the event envelope.

    `source`, `actor` and `reason` are envelope keys: a profile mapping an item
    field onto one of them would have the fold quietly discard it
    (EVENT_SCHEMA.md Section 3). Better to say so here than to debug a blank
    column later.
    """
    if not isinstance(profile, dict):
        raise TypeError("profile must be a dict")
    for required in ("id_field", "title_field", "status_field"):
        if not profile.get(required):
            raise ValueError(f"profile is missing {required!r}")
    clashes = sorted(set(profile.get("extra_fields") or {}) & items_mod.ENVELOPE_KEYS)
    if clashes:
        raise ValueError(
            f"profile maps item fields onto event envelope keys: {clashes}; "
            "the fold would discard them -- rename the wall-side field"
        )


def load_source(source: Any, profile: dict) -> tuple[list[dict], dict]:
    """Return (items, document). `source` is a path or an already-parsed object."""
    if isinstance(source, (str, Path)):
        doc = json.loads(Path(source).read_text(encoding="utf-8"))
    else:
        doc = source
    node: Any = doc
    for step in profile.get("items_path") or []:
        if not isinstance(node, dict):
            raise ValueError(f"items_path {profile['items_path']!r} does not resolve in the source")
        node = node.get(step)
    if node is None and not (profile.get("items_path") or []):
        node = doc
    if not isinstance(node, list):
        raise ValueError(f"items_path {profile.get('items_path')!r} did not resolve to a list")
    items = [row for row in node if isinstance(row, dict)]
    return items, (doc if isinstance(doc, dict) else {})


# ------------------------------------------------------------------ mapping

def map_item(raw: dict, profile: dict, *, default_ts: str) -> dict | None:
    """One source row -> the wall fields for it. `None` if it has no usable id.

    Pure: no I/O, no clock. Everything time-dependent arrives as `default_ts`,
    so the same row maps the same way every run.
    """
    item_id = raw.get(profile["id_field"])
    if not isinstance(item_id, str) or not item_id.strip():
        return None
    item_id = item_id.strip()

    raw_status = raw.get(profile["status_field"])
    key = _norm(raw_status)
    status = (profile.get("status_map") or {}).get(key) or profile.get("default_status", "planned")

    kind = None
    for prefix, mapped in profile.get("kind_from_id") or []:
        if _norm(item_id).startswith(_norm(prefix)):
            kind = mapped
            break
    if kind is None and profile.get("type_field"):
        kind = (profile.get("type_map") or {}).get(_norm(raw.get(profile["type_field"])))
    if kind is None:
        kind = profile.get("default_kind", "story")

    fields: dict[str, Any] = {
        "title": str(raw.get(profile["title_field"]) or item_id),
        "kind": kind,
        "status": status,
    }

    # Always present, None when there is nothing to say: a status that HAD a
    # note (deferred) and moved to one that does not must CLEAR the note on
    # the wall, and an omitted key clears nothing -- the fold keeps the old
    # value and the idempotence check never sees the difference.
    fields["note"] = (profile.get("status_notes") or {}).get(key)

    arc_id = raw.get(profile["arc_id_field"]) if profile.get("arc_id_field") else None
    if isinstance(arc_id, str) and arc_id.strip():
        fields["arc_id"] = arc_id.strip()
        arc_title = raw.get(profile["arc_title_field"]) if profile.get("arc_title_field") else None
        fields["arc_title"] = (arc_title.strip()
                               if isinstance(arc_title, str) and arc_title.strip()
                               else arc_id.strip())
    else:
        fields["arc_id"] = UNASSIGNED_ARC_ID
        fields["arc_title"] = UNASSIGNED_ARC_TITLE

    # Importer-owned optional fields are ALWAYS emitted, as None when blank.
    # Omitting a blank key looks tidier but is a data-integrity hole: an item
    # whose `detail` (or pr, or assignee) was cleared on the source board
    # would keep its old value on the wall forever -- the idempotence check
    # compares only the keys present, and the fold preserves what a snapshot
    # event does not mention.
    for wall_field, source_key in (
        ("assignee", profile.get("assignee_field")),
        ("estimate", profile.get("estimate_field")),
        ("actual", profile.get("actual_field")),
        ("parent_id", profile.get("parent_field")),
    ):
        if not source_key:
            continue
        value = raw.get(source_key)
        fields[wall_field] = None if _is_blank(value) else value

    for wall_field, source_key in (profile.get("extra_fields") or {}).items():
        value = raw.get(source_key)
        fields[wall_field] = None if _is_blank(value) else value

    updated = raw.get(profile["updated_field"]) if profile.get("updated_field") else None
    return {
        "item_id": item_id,
        "ts": _iso(updated, default_ts),
        "fields": fields,
        "source_status": "" if raw_status is None else str(raw_status),
    }


# ------------------------------------------------------------------ writing

def _append(repo: Path, session_id: str, seq: int, ts: str, payload: dict) -> dict:
    """One record, one line, `O_APPEND`, into this session's shard for the day.

    Written here rather than through `items.append_event` for one reason: that
    helper rescans every shard for the session on each call to find the next
    `seq`, which is correct for a handful of events and quadratic for a
    thousand. The seq is seeded once from the same scan and carried forward.
    """
    record = {
        "schema_version": SCHEMA_VERSION,
        "event_id": str(uuid.uuid4()),
        "seq": seq,
        "ts": ts,
        "session_id": session_id,
    }
    record.update({k: v for k, v in payload.items() if k not in record})
    shard = repo / ".wall" / "events" / ts[:10] / f"{session_id}.jsonl"
    shard.parent.mkdir(parents=True, exist_ok=True)
    line = (json.dumps(record, ensure_ascii=False) + "\n").encode("utf-8")
    fd = os.open(str(shard), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        os.write(fd, line)
    finally:
        os.close(fd)
    return record


def import_board(repo: str | Path, source_json: Any, profile: dict, *,
                 session_id: str = DEFAULT_SESSION, dry_run: bool = False,
                 now: str | None = None) -> dict:
    """Fold an existing tracker into the wall's ledger.

    Returns `{"imported", "skipped", "updated", "events", "unusable", "items",
    "session_id"}`. `imported` counts items minted this run, `updated` counts
    items whose fields moved, `skipped` counts items already matching.
    """
    validate_profile(profile)
    repo = Path(repo)
    default_ts = now or items_mod.now_iso()

    rows, doc = load_source(source_json, profile)
    doc_updated = doc.get(profile.get("source_updated_field") or "") if doc else None
    default_ts = _iso(doc_updated, default_ts)

    mapped: list[dict] = []
    unusable = 0
    for raw in rows:
        one = map_item(raw, profile, default_ts=default_ts)
        if one is None:
            unusable += 1
        else:
            mapped.append(one)

    # Shards, not the derived ledger: the courier may not have swept since the
    # last import, and an idempotence check against a stale view would re-write
    # every item it could not see.
    existing = items_mod.fold_items(_read_ledger(repo))

    seq = items_mod.next_seq(repo, session_id)
    imported = updated = skipped = events = 0

    for one in mapped:
        item_id, fields = one["item_id"], one["fields"]
        current = existing.get(item_id)
        if current is not None:
            # Idempotent: compare only the fields this importer owns.
            if all(current.get(k) == v for k, v in fields.items()):
                skipped += 1
                continue
            updated += 1
        else:
            imported += 1

        if dry_run:
            continue

        if current is None:
            _append(repo, session_id, seq, one["ts"], {
                "event": "item_created",
                "item_id": item_id,
                "trace_id": trace_for(item_id),
                "actor": IMPORT_ACTOR,
                "agent_key": IMPORT_ACTOR,
                "role": "courier",
                "title": fields["title"],
                "kind": fields["kind"],
                "imported_from": profile.get("name", "unknown"),
            })
            seq += 1
            events += 1

        payload = {"event": "item_state", "item_id": item_id, "actor": IMPORT_ACTOR}
        payload.update(fields)
        _append(repo, session_id, seq, one["ts"], payload)
        seq += 1
        events += 1

    return {
        "imported": imported,
        "updated": updated,
        "skipped": skipped,
        "events": events,
        "unusable": unusable,
        "items": len(mapped),
        "session_id": session_id,
        "profile": profile.get("name", "unknown"),
        "dry_run": bool(dry_run),
    }


def _read_ledger(repo: Path) -> list[dict]:
    """Every event already in this repo's shards, for the idempotence check.

    Reads the shards rather than `derived/ledger.jsonl`, so a re-import is
    correct even when the courier has not swept since the last one.
    """
    out: list[dict] = []
    events_dir = Path(repo) / ".wall" / "events"
    if not events_dir.is_dir():
        return out
    for shard in sorted(events_dir.rglob("*.jsonl")):
        try:
            text = shard.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict):
                out.append(record)
    return out


# --------------------------------------------------------------------- main

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="adapters.board_import",
        description="Import an existing project tracker into the wall's ledger.")
    p.add_argument("--repo", default=".", help="repo root that holds .wall/")
    p.add_argument("--source", required=True, help="path to the tracker JSON")
    p.add_argument("--profile", default="generic", choices=sorted(PROFILES),
                   help="which tracker shape the source is")
    p.add_argument("--session", default=DEFAULT_SESSION, help="shard to append to")
    p.add_argument("--dry-run", action="store_true",
                   help="report what would be written without writing it")
    p.add_argument("--json", action="store_true", help="print the result as JSON")
    a = p.parse_args(argv)

    try:
        result = import_board(Path(a.repo).resolve(), a.source, PROFILES[a.profile],
                              session_id=a.session, dry_run=a.dry_run)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print(f"board import failed: {exc}", file=sys.stderr)
        return 1

    if a.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"{result['profile']}: {result['imported']} imported, "
              f"{result['updated']} updated, {result['skipped']} unchanged, "
              f"{result['events']} events"
              + (" (dry run)" if result["dry_run"] else "")
              + (f", {result['unusable']} rows had no usable id" if result["unusable"] else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
