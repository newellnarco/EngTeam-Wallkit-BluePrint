#!/usr/bin/env python3
"""questions.py -- the question lifecycle, folded from the ledger.

A question is the one thing in the system that can stall a builder for hours
without anybody noticing, because the failure is an *absence*: nobody picked it
up, nobody ran, nobody escalated. WORKFLOW.md Section 4 answers that by making
escalation an invariant rather than a habit -- Courier checks the same five
conditions every sweep, so the wall catches a lapse whether or not Maestro
behaved.

This module folds the lifecycle:

    question_raised -> question_assigned -> question_answered
                    -> question_escalated (a hop, not a terminus)
                    -> human_required -> human_answered

and evaluates the invariants against the SLAs in `.wall/config/wall.json`.

Keys: `question_raised` and friends carry `question_id`; the human queue events
carry `ask_id`. Both are indexed, and a record carries whichever it was given,
so `wall answer <ask_id>` and `wall trace <question_id>` both resolve.

Stdlib only. Tolerant: a malformed record is a named problem, never a crash.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, NamedTuple

import items as _items

order_key = _items.order_key
parse_ts = _items.parse_ts

QUESTION_EVENTS = (
    "question_raised", "question_assigned", "question_answered",
    "question_escalated", "human_required", "human_answered",
)

# A question is finished only when somebody answered it.
CLOSED_STATUSES = frozenset({"answered"})

# Item statuses that mean a builder is parked on an unanswered question.
BLOCKED_STATUSES = frozenset({"blocked", "parked", "stalled"})

DEFAULT_SLA_MINUTES = {
    "question_assigned": 5,
    "researcher_first_run": 10,
    "escalate_to_architect": 30,
    "escalate_to_human": 60,
    "question_open_escalate": 60,
}

# The ladder from WORKFLOW.md Section 4, in order.
LADDER = ("researcher", "second_researcher", "architect", "adjudicator", "human")


class FoldResult(NamedTuple):
    questions: dict[str, dict]
    problems: list[dict]


def _blank(qid: str) -> dict:
    return {
        "question_id": qid,
        "ask_id": None,
        "item_id": None,
        "trace_id": None,
        "text": "",
        "ambiguity_class": None,
        "status": "open",
        "raised_at": None,
        "raised_by": None,
        "raised_by_key": None,
        "assigned_to": None,
        "assigned_to_key": None,
        "assigned_at": None,
        "first_run_at": None,
        "escalations": [],
        "tier": LADDER[0],
        "answered_at": None,
        "answer_source": None,
        "answer": None,
        "blocks_criteria": [],
        "dependent_scope": [],
        "independent_scope": [],
        "outcome_hint": None,
        "events": 0,
    }


def _qid(event: dict) -> str | None:
    for key in ("question_id", "ask_id"):
        v = event.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def _first(event: dict, *keys: str) -> Any:
    for k in keys:
        v = event.get(k)
        if v not in (None, ""):
            return v
    return None


def fold(events: list) -> FoldResult:
    """Fold the question lifecycle. Pure; deterministic on the total order."""
    problems: list[dict] = []
    clean = [e for e in events if isinstance(e, dict)]
    if len(clean) != len(events):
        problems.append({"kind": "malformed_event",
                         "detail": f"{len(events) - len(clean)} non-object records ignored"})

    qs: dict[str, dict] = {}
    by_ask: dict[str, str] = {}
    for e in sorted(clean, key=order_key):
        ev = e.get("event")
        if ev not in QUESTION_EVENTS:
            continue
        qid = _qid(e)
        if not qid:
            problems.append({"kind": "question_event_without_id", "event": ev,
                             "event_id": e.get("event_id"),
                             "detail": "no question_id and no ask_id"})
            continue
        q = qs.setdefault(qid, _blank(qid))
        q["events"] += 1
        ts = e.get("ts") if isinstance(e.get("ts"), str) else None

        if isinstance(e.get("ask_id"), str) and e["ask_id"]:
            q["ask_id"] = e["ask_id"]
            by_ask[e["ask_id"]] = qid
        for field, keys in (
            ("item_id", ("item_id",)),
            ("trace_id", ("trace_id",)),
            ("ambiguity_class", ("ambiguity_class",)),
            ("outcome_hint", ("outcome_hint",)),
        ):
            v = _first(e, *keys)
            if v is not None:
                q[field] = v
        text = _first(e, "question", "text")
        if isinstance(text, str) and text and not q["text"]:
            q["text"] = text
        for field in ("blocks_criteria", "dependent_scope", "independent_scope"):
            v = e.get(field)
            if isinstance(v, list):
                q[field] = v

        if ev == "question_raised":
            q["raised_at"] = q["raised_at"] or ts
            q["raised_by"] = q["raised_by"] or e.get("agent_name") or e.get("agent_key")
            q["raised_by_key"] = q["raised_by_key"] or e.get("agent_key")
            if q["status"] == "open":
                q["status"] = "open"
        elif ev == "question_assigned":
            q["assigned_at"] = q["assigned_at"] or ts
            q["assigned_to"] = _first(e, "assignee", "assigned_to", "agent_name") or q["assigned_to"]
            q["assigned_to_key"] = _first(e, "assignee_key", "assigned_to_key",
                                          "agent_key") or q["assigned_to_key"]
            if q["status"] not in CLOSED_STATUSES:
                q["status"] = "assigned"
        elif ev == "question_escalated":
            tier = _first(e, "tier", "to", "escalated_to")
            q["escalations"].append({
                "at": ts,
                "reason": _first(e, "reason", "why") or "",
                "tier": tier if isinstance(tier, str) else None,
            })
            if isinstance(tier, str) and tier:
                q["tier"] = tier
            if q["status"] not in CLOSED_STATUSES:
                q["status"] = "escalated"
        elif ev == "human_required":
            q["ask_id"] = q["ask_id"] or qid
            by_ask[q["ask_id"]] = qid
            q["raised_at"] = q["raised_at"] or ts
            q["raised_by"] = q["raised_by"] or e.get("agent_name") or e.get("agent_key")
            q["tier"] = "human"
            if q["status"] not in CLOSED_STATUSES:
                q["status"] = "human_required"
        elif ev in ("question_answered", "human_answered"):
            q["answered_at"] = ts
            q["answer_source"] = _first(e, "source") or (
                "human" if ev == "human_answered" else "researcher")
            answer = _first(e, "answer", "resolution", "text")
            if isinstance(answer, str) and answer:
                q["answer"] = answer
            q["status"] = "answered"

    # `Assigned, no researcher run_start past SLA` needs the run stream too.
    for e in sorted(clean, key=order_key):
        if e.get("event") != "run_start":
            continue
        ts = e.get("ts") if isinstance(e.get("ts"), str) else None
        qid = _qid(e)
        target = qs.get(qid) if qid else None
        if target is None:
            # Fall back to a researcher run on the same item after assignment.
            iid = e.get("item_id")
            if not isinstance(iid, str) or e.get("role") != "researcher":
                continue
            for q in qs.values():
                if q["item_id"] == iid and q["assigned_at"] and not q["first_run_at"]:
                    if ts and ts >= q["assigned_at"]:
                        q["first_run_at"] = ts
            continue
        if not target["first_run_at"]:
            target["first_run_at"] = ts

    for q in qs.values():
        if q["ask_id"] is None and q["question_id"] in by_ask:
            q["ask_id"] = q["question_id"]
    return FoldResult(qs, problems)


def fold_questions(events: list) -> dict[str, dict]:
    return fold(events).questions


def is_open(question: dict) -> bool:
    return question.get("status") not in CLOSED_STATUSES


def open_questions(questions: dict[str, dict]) -> list[dict]:
    return sorted((q for q in questions.values() if is_open(q)),
                  key=lambda q: (q.get("raised_at") or "", q["question_id"]))


def resolve(questions: dict[str, dict], target: str) -> dict | None:
    """Resolve a question by question_id or ask_id. Exact match only --
    guessing which question a human meant is not a thing to be clever about."""
    if target in questions:
        return questions[target]
    for q in questions.values():
        if q.get("ask_id") == target:
            return q
    return None


# ------------------------------------------------------- the five invariants

def _age_min(when: Any, now: datetime) -> float | None:
    dt = parse_ts(when)
    if dt is None:
        return None
    return (now - dt).total_seconds() / 60.0


def escalation_flags(questions: dict[str, dict], items: dict[str, dict],
                     agents: list[dict] | None = None,
                     sla: dict | None = None,
                     now: datetime | None = None) -> list[dict]:
    """WORKFLOW.md Section 4, mechanically.

    | Item blocked, no open question            | blocked_without_question   |
    | Open question, no assignment past SLA     | unassigned_past_sla        |
    | Assigned, no researcher run past SLA      | assigned_no_run            |
    | Builder blocked while a researcher is idle| capacity_wasted            |
    | Question open past threshold              | escalate                   |

    Every flag names the item or question, the age, and the SLA it broke, so
    the wall shows a lapse rather than a mood.
    """
    now = now or datetime.now(timezone.utc)
    s = dict(DEFAULT_SLA_MINUTES)
    s.update({k: v for k, v in (sla or {}).items() if isinstance(v, (int, float))})
    flags: list[dict] = []

    live = [q for q in questions.values() if is_open(q)]
    by_item: dict[str, list[dict]] = {}
    for q in live:
        if isinstance(q.get("item_id"), str) and q["item_id"]:
            by_item.setdefault(q["item_id"], []).append(q)

    blocked_items = sorted(
        iid for iid, it in (items or {}).items()
        if isinstance(it.get("status"), str) and it["status"].lower() in BLOCKED_STATUSES)

    for iid in blocked_items:
        if not by_item.get(iid):
            flags.append({"kind": "blocked_without_question", "item_id": iid,
                          "detail": "item is blocked with no open question -- "
                                    "blocked without asking"})

    for q in sorted(live, key=lambda q: q["question_id"]):
        age = _age_min(q.get("raised_at"), now)
        if q.get("assigned_at") is None and q.get("status") != "human_required":
            limit = s["question_assigned"]
            if age is not None and age > limit:
                flags.append({"kind": "unassigned_past_sla",
                              "question_id": q["question_id"], "item_id": q.get("item_id"),
                              "age_min": round(age, 1), "sla_min": limit,
                              "detail": "nobody picked it up"})
        elif q.get("assigned_at") and not q.get("first_run_at"):
            since = _age_min(q["assigned_at"], now)
            limit = s["researcher_first_run"]
            if since is not None and since > limit:
                flags.append({"kind": "assigned_no_run",
                              "question_id": q["question_id"], "item_id": q.get("item_id"),
                              "assignee": q.get("assigned_to"),
                              "age_min": round(since, 1), "sla_min": limit,
                              "detail": "assigned on paper only"})
        limit = s["question_open_escalate"]
        if age is not None and age > limit and q.get("tier") != "human":
            flags.append({"kind": "escalate", "question_id": q["question_id"],
                          "item_id": q.get("item_id"), "tier": q.get("tier"),
                          "age_min": round(age, 1), "sla_min": limit,
                          "detail": f"open {round(age)} min at tier "
                                    f"'{q.get('tier')}' -- escalate a tier"})

    idle_researchers = [a for a in (agents or [])
                        if a.get("role") == "researcher" and a.get("status") == "idle"]
    if idle_researchers and blocked_items:
        names = ", ".join(sorted(a.get("name") or a.get("agent_key", "?")
                                 for a in idle_researchers))
        for iid in blocked_items:
            flags.append({"kind": "capacity_wasted", "item_id": iid,
                          "idle_researchers": len(idle_researchers),
                          "detail": f"builder blocked while researcher(s) idle: {names}"})
    return flags


# --------------------------------------------------------------- the answer

def answer(repo, target: str, text: str, session_id: str = "s_human",
           events: list | None = None, decision_id: str | None = None,
           now_ts: str | None = None) -> dict:
    """Write `human_answered` for an ask, clearing it from the Waiting tab.

    Returns the appended record plus the question it closed. Raises
    LookupError when the ask is unknown, which the CLI turns into a list of
    what *is* open rather than a traceback.
    """
    events = _items.load_events(repo) if events is None else events
    questions = fold(events).questions
    q = resolve(questions, target)
    if q is None:
        raise LookupError(target)
    payload = {
        "event": "human_answered",
        "ask_id": q.get("ask_id") or q["question_id"],
        "question_id": q["question_id"],
        "item_id": q.get("item_id"),
        "trace_id": q.get("trace_id"),
        "role": "human",
        "source": "human",
        "answer": text,
        "outcome": "pass",
    }
    if decision_id:
        payload["decisions_in_context"] = [decision_id]
    record = _items.append_event(repo, session_id, payload, ts=now_ts)
    return {"record": record, "question": q}
