"""One wall summary, two presentations (Patron direction, 2026-09-20:
"add a wall status summary tool for humans too").

`build_summary` folds the derived snapshot into a typed `WallSummary`;
`format_summary` prints it for a terminal. The MCP adapter serves the
SAME `build_summary` to agents — deriving both presentations from one
function is what makes it impossible for the human view and the agent
view to disagree about what the wall says (the Patron's one-source-of-
truth rule; see DEC-0018). Pure: no I/O, no clock — the CLI wrapper in
wall.py does the reading and passes `now` for the age line.

Stdlib only (DEC-0017).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from contracts import IN_FLIGHT_STATUSES, ItemStatus, canon_status

#: Triage order for the in-flight list: blocked first, then review, then
#: work simply in progress.
_TRIAGE_ORDER = (ItemStatus.BLOCKED, ItemStatus.REVIEW, ItemStatus.IN_PROGRESS)


@dataclass(frozen=True)
class WallSummary:
    repo: str
    branch: str
    generated_at: str
    arcs: int
    items_total: int
    by_status: dict = field(default_factory=dict)
    in_flight: tuple = ()          # "ST-1  title  [status · assignee]"
    waiting_on_you: tuple = ()     # "ask_0007  (Priya, BG-021): question…"
    questions_open: int = 0
    integrity_flags: int = 0
    budget_lines: tuple = ()       # "label  pace-verdict  (pct% left)"
    heartbeat_ok: bool | None = None
    heartbeat_events: int | None = None
    heartbeat_corrupt: int | None = None


def _flag_count(integrity: dict) -> int:
    n = 0
    for v in integrity.values():
        if isinstance(v, list):
            n += len(v)
    return n


def _clip(text: str, width: int = 64) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= width else text[: width - 1] + "…"


def build_summary(snapshot: dict, heartbeat: dict | None = None) -> WallSummary:
    board = snapshot.get("board") or {}
    arcs = board.get("arcs") or []
    by_status: dict = {}
    in_flight = []
    for arc in arcs:
        for it in arc.get("items") or []:
            raw = it.get("status") or "unset"
            canon = canon_status(raw)
            # Count under the canonical name so two spellings of one state
            # never read as two states; an untaught status stays verbatim.
            key = str(canon) if canon else str(raw)
            by_status[key] = by_status.get(key, 0) + 1
            if canon in IN_FLIGHT_STATUSES:
                who = it.get("assignee")
                tail = str(canon) + (f" · {who}" if who else "")
                in_flight.append((_TRIAGE_ORDER.index(canon),
                                  f"{it.get('item_id', '?'):<8}"
                                  f"{_clip(it.get('title', ''), 48):<50}"
                                  f"[{tail}]"))
    in_flight.sort()

    waiting = tuple(
        f"{w.get('ask_id', '?')}  ({w.get('agent', '?')}, {w.get('item_id', '?')}): "
        f"{_clip(w.get('question', ''), 72)}"
        for w in snapshot.get("waiting_on_you") or [])

    questions_open = sum(
        1 for q in snapshot.get("questions") or []
        if (q.get("status") or "") not in ("answered", "closed"))

    budget_lines = []
    for m in (snapshot.get("budget") or {}).get("meters") or []:
        pace = (m.get("pace") or {}).get("verdict", "unknown")
        pct = m.get("pct_remaining")
        left = f"  ({pct}% left)" if pct is not None else ""
        budget_lines.append(f"{m.get('label', '?'):<24}{pace}{left}")

    hb_ok = hb_events = hb_corrupt = None
    if heartbeat:
        hb_ok = bool(heartbeat.get("ok"))
        hb_events = heartbeat.get("events")
        hb_corrupt = heartbeat.get("corrupt_lines")

    return WallSummary(
        repo=(snapshot.get("repo") or {}).get("name", "?"),
        branch=(snapshot.get("repo") or {}).get("branch", "?"),
        generated_at=snapshot.get("generated_at", ""),
        arcs=len(arcs),
        items_total=sum(by_status.values()),
        by_status=by_status,
        in_flight=tuple(line for _, line in in_flight),
        waiting_on_you=waiting,
        questions_open=questions_open,
        integrity_flags=_flag_count(snapshot.get("integrity") or {}),
        budget_lines=tuple(budget_lines),
        heartbeat_ok=hb_ok,
        heartbeat_events=hb_events,
        heartbeat_corrupt=hb_corrupt,
    )


def _age(iso: str, now: datetime) -> str:
    try:
        then = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return "unknown age"
    if then.tzinfo is None:
        # A naive timestamp parses fine and then CRASHES the subtraction
        # against aware `now` (TypeError, which the except above rightly
        # does not swallow — it is not a parse failure). A host snapshot
        # that omits the offset means UTC here by every producer's
        # convention, so say so instead of crashing the summary over it.
        # (Gemini review finding on the host PR, accepted.)
        then = then.replace(tzinfo=UTC)
    s = max(0, (now - then).total_seconds())
    if s < 90:
        return "just now"
    if s < 3600:
        return f"{int(s // 60)}m ago"
    if s < 86400:
        return f"{int(s // 3600)}h ago"
    return f"{int(s // 86400)}d ago"


def format_summary(s: WallSummary, now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    lines = [
        f"{s.repo} · {s.branch} — wall as of {_age(s.generated_at, now)}",
    ]
    if s.heartbeat_ok is not None:
        health = "ok" if s.heartbeat_ok else (
            f"DEGRADED — {s.heartbeat_corrupt} corrupt ledger line(s)")
        lines.append(f"courier: {health} · {s.heartbeat_events} events")
    counts = " · ".join(
        f"{k} {v}" for k, v in sorted(s.by_status.items(),
                                      key=lambda kv: -kv[1]))
    lines.append(f"board: {s.items_total} items / {s.arcs} arcs — {counts}")
    if s.integrity_flags:
        lines.append(f"integrity: {s.integrity_flags} flag(s) — run `wall doctor`")
    if s.in_flight:
        lines.append("")
        lines.append("in flight:")
        lines.extend("  " + x for x in s.in_flight)
    if s.waiting_on_you:
        lines.append("")
        lines.append(f"waiting on you ({len(s.waiting_on_you)}):")
        lines.extend("  " + x for x in s.waiting_on_you)
    if s.questions_open:
        lines.append(f"open questions: {s.questions_open}")
    if s.budget_lines:
        lines.append("")
        lines.append("budget pace:")
        lines.extend("  " + x for x in s.budget_lines)
    return "\n".join(lines)
