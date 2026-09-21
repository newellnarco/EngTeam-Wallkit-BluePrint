"""Oversight folds -- the data behind the RETRO / POSTURE / DOCS wall tabs.

Pure functions over the ordered event list the courier already holds, plus
one disk read (the documents-of-record registry hashes). No clock decisions,
no network, no model. Honesty rules match the rest of the wall: an absent
signal is reported absent with the mechanism that would emit it named --
never fabricated, never hidden.

Event contracts (EVENT_SCHEMA.md section "Oversight"):

* ``warden_ruling`` -- gate (architecture | data_use | delivery_audit |
  playbook | tech_eval), subject, verdict, optional tier / obligation.
* ``retro_held`` -- wave, signals [{role, name, value, prior?}],
  diffs [{path, why, horizon?}], remeasured [{path, verdict}], requeued.
* ``doc_reviewed`` -- path, sha, by. The ack that turns a document of
  record from changed-since-review back to current.
* ``doc_feedback`` -- path, sha, by, text (DEC-0027). The Patron's OTHER
  answer to a review: not signed off -- correct / remap / discuss. Routed
  to the Architect as a finding; the DOCS tab shows it beside the state.
* ``retro_input`` -- by, text (DEC-0027). A Patron note the NEXT retro must
  consume; pending inputs surface on the RETRO tab until a retro_held
  follows them.

The FLOW fold (DEC-0027) invents no events: iterations are the segments
between ``retro_held`` records, and velocity / sizing / quality / burndown
read the existing ``item_created`` / ``item_state`` / ``item_shipped``
stream (EVENT_SCHEMA sections 3 and 8).

Design charter: docs/WALL_DASHBOARDS.md (kit DEC-0026/0027).
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

# The same shim mcp_server.py carries: a standalone path-load (a host's
# integrity suite, a probe) must resolve the sibling modules without
# depending on whoever imported something else first (measured: an
# order-dependent pass on the reference adoption, 2026-09-21).
_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

try:  # courier imports these as siblings (sys.path includes tools/wall)
    import compliance as compliance_mod
    import decisions as decisions_mod
    import items as items_mod
except ImportError:  # pragma: no cover - direct package-style import
    from . import compliance as compliance_mod  # type: ignore
    from . import decisions as decisions_mod  # type: ignore
    from . import items as items_mod  # type: ignore

# The default documents-of-record registry: the adoption runbook's seven
# functions plus the method doc. A host overrides the whole list with
# ``documents_of_record`` in wall.json; a listed file that does not exist
# renders as ``missing`` -- absence is a state, not a filter.
DEFAULT_DOCUMENTS_OF_RECORD = (
    "RULES.md",
    "FAILURE_PATTERNS.md",
    "SHIP_CHECKLIST.md",
    "BEST_PRACTICES.md",
    "OWNER_DECISIONS.md",
    "REVIEWER_LANES.md",
    "BUDGETED_DOCS.md",
    "DOCS_MAP.md",
    "docs/ENGINEERING_STANDARD.md",
)

WARDEN_GATES = ("architecture", "data_use", "delivery_audit", "playbook",
                "tech_eval")

_RULINGS_SHOWN = 30
_TREND_POINTS = 12
_RECENT_DECISIONS = 8


def _s(value) -> str:
    return value if isinstance(value, str) else ""


# ------------------------------------------------------------------ posture

def fold_posture(events: list) -> dict:
    """Latest Warden ruling per (gate, subject); events arrive ledger-ordered,
    so last write wins. A malformed ruling (no subject or verdict) is counted
    as such rather than dropped silently."""
    latest: dict[tuple[str, str], dict] = {}
    malformed = 0
    total = 0
    for e in events:
        if not isinstance(e, dict) or e.get("event") != "warden_ruling":
            continue
        total += 1
        gate = _s(e.get("gate")) or "unspecified"
        subject = _s(e.get("subject"))
        verdict = _s(e.get("verdict"))
        if not subject or not verdict:
            malformed += 1
            continue
        latest[(gate, subject)] = {
            "gate": gate, "subject": subject, "verdict": verdict,
            "tier": _s(e.get("tier")) or None,
            "obligation": _s(e.get("obligation")) or None,
            "ts": _s(e.get("ts")) or None,
        }
    rulings = list(latest.values())
    rulings.sort(key=lambda r: r["ts"] or "", reverse=True)
    tally: dict[str, int] = {}
    for r in rulings:
        tally[r["verdict"]] = tally.get(r["verdict"], 0) + 1
    blocked = [r for r in rulings if r["verdict"] in ("blocked", "refused")]
    audits = [r for r in rulings if r["gate"] == "delivery_audit"]
    return {
        "rulings": rulings[:_RULINGS_SHOWN],
        "tally": tally,
        "blocked": blocked,
        "last_delivery_audit": audits[0] if audits else None,
        "total_rulings": total,
        "malformed": malformed,
    }


# -------------------------------------------------------------------- retro

def fold_retro(events: list) -> dict:
    """Every retro in ledger order; the latest in full, the rest as trend
    series per (role, signal-name). A signal value that is not a number is
    kept verbatim in the latest view but excluded from the numeric trend."""
    retros = [e for e in events
              if isinstance(e, dict) and e.get("event") == "retro_held"]
    trends: dict[tuple[str, str], dict] = {}
    for e in retros:
        for sig in e.get("signals") or []:
            if not isinstance(sig, dict):
                continue
            role = _s(sig.get("role")) or "process"
            name = _s(sig.get("name"))
            if not name:
                continue
            t = trends.setdefault((role, name), {
                "role": role, "name": name, "series": []})
            value = sig.get("value")
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                t["series"].append(value)
    # Patron inputs (retro_input) not yet consumed by a retro: everything
    # after the LAST retro_held is pending; RETROSPECTIVES.md binds the next
    # retro to address each one in its record.
    pending_inputs = []
    for e in reversed(events):
        if not isinstance(e, dict):
            continue
        if e.get("event") == "retro_held":
            break
        if e.get("event") == "retro_input":
            text = _s(e.get("text"))
            if text:
                pending_inputs.append({"by": _s(e.get("by")) or "?",
                                       "text": text,
                                       "ts": _s(e.get("ts")) or None})
    pending_inputs.reverse()

    latest = retros[-1] if retros else None
    latest_view = None
    if latest is not None:
        latest_view = {
            "wave": _s(latest.get("wave")) or None,
            "ts": _s(latest.get("ts")) or None,
            "signals": [s for s in (latest.get("signals") or [])
                        if isinstance(s, dict)],
            "diffs": [d for d in (latest.get("diffs") or [])
                      if isinstance(d, dict)],
            "remeasured": [r for r in (latest.get("remeasured") or [])
                           if isinstance(r, dict)],
            "requeued": latest.get("requeued")
            if isinstance(latest.get("requeued"), int) else None,
        }
    trend_rows = sorted(trends.values(), key=lambda t: (t["role"], t["name"]))
    for t in trend_rows:
        t["series"] = t["series"][-_TREND_POINTS:]
    return {"held": len(retros), "latest": latest_view, "trends": trend_rows,
            "pending_inputs": pending_inputs}


# --------------------------------------------------------------------- docs

def _sha12(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()[:12]
    except OSError:
        return None


def fold_docs(repo: Path, events: list, config: dict) -> dict:
    """The documents-of-record review registry plus the decision log.

    State per document: ``missing`` | ``never-reviewed`` |
    ``changed-since-review`` | ``current``. The ack that moves a document is
    a ``doc_reviewed`` event carrying the sha it was reviewed AT -- an ack
    for a stale sha does not make a changed document current, which is the
    whole point of carrying the sha.
    """
    repo = Path(repo)
    registry = config.get("documents_of_record")
    if not isinstance(registry, list) or not registry:
        registry = list(DEFAULT_DOCUMENTS_OF_RECORD)

    reviews: dict[str, dict] = {}
    feedback: dict[str, dict] = {}
    for e in events:  # ledger order; last review / last feedback per path win
        if not isinstance(e, dict):
            continue
        path = _s(e.get("path"))
        if not path:
            continue
        if e.get("event") == "doc_reviewed":
            reviews[path] = {"sha": _s(e.get("sha")) or None,
                             "by": _s(e.get("by")) or None,
                             "ts": _s(e.get("ts")) or None}
            # an ack answers any earlier feedback on this path
            feedback.pop(path, None)
        elif e.get("event") == "doc_feedback":
            feedback[path] = {"sha": _s(e.get("sha")) or None,
                              "by": _s(e.get("by")) or None,
                              "text": _s(e.get("text")) or None,
                              "ts": _s(e.get("ts")) or None}

    rows = []
    needs_review = 0
    for rel in registry:
        rel = _s(rel)
        if not rel:
            continue
        p = repo / rel
        sha = _sha12(p) if p.is_file() else None
        review = reviews.get(rel)
        fb = feedback.get(rel)
        if sha is None:
            state = "missing"
        elif fb is not None:
            # Open feedback outranks everything readable: the Patron spoke
            # and nobody has addressed it. Only a NEWER ack clears it.
            state = "feedback-open"
        elif review is None:
            state = "never-reviewed"
        elif review.get("sha") == sha:
            state = "current"
        else:
            state = "changed-since-review"
        if state in ("never-reviewed", "changed-since-review",
                     "feedback-open"):
            needs_review += 1
        rows.append({"path": rel, "sha": sha, "state": state,
                     "review": review, "feedback": fb})

    idx = decisions_mod.index(repo, config)
    recent = sorted(idx.decisions.values(), key=lambda d: d["id"],
                    reverse=True)[:_RECENT_DECISIONS]
    return {
        "registry": rows,
        "needs_review": needs_review,
        "decisions": {
            "count": len(idx.decisions),
            "problems": len(idx.problems),
            "recent": [{"id": d["id"], "status": d.get("status"),
                        "title": d.get("title"), "scope": d.get("scope")}
                       for d in recent],
        },
    }


# --------------------------------------------------------------- compliance

def fold_compliance(events: list) -> dict:
    """The POSTURE tab's compliance section (DEC-0028): per regime, the
    Patron's applicability selection (a decision with a reason), the
    self-attestation state per control, and the CHALLENGE heuristics in
    both directions -- selected-with-no-surface and
    unselected-but-rulings-cite-it. Challenges are questions, never
    auto-flips: the selection stays the Patron's."""
    selections: dict[str, dict] = {}
    selection_log: list[dict] = []
    attest: dict[tuple[str, str], dict] = {}
    ruling_text: list[str] = []
    for e in events:
        if not isinstance(e, dict):
            continue
        ev = e.get("event")
        if ev == "compliance_selected":
            regime_id = _s(e.get("regime"))
            if not regime_id:
                continue
            rec = {"regime": regime_id,
                   "applicable": bool(e.get("applicable")),
                   "reason": _s(e.get("reason")) or None,
                   "by": _s(e.get("by")) or None,
                   "ts": _s(e.get("ts")) or None}
            selections[regime_id] = rec
            selection_log.append(rec)
        elif ev == "compliance_attested":
            regime_id = _s(e.get("regime"))
            control = _s(e.get("control"))
            if regime_id and control:
                attest[(regime_id, control)] = {
                    "status": _s(e.get("status")) or None,
                    "note": _s(e.get("note")) or None,
                    "by": _s(e.get("by")) or None,
                    "ts": _s(e.get("ts")) or None}
        elif ev == "warden_ruling":
            ruling_text.append((_s(e.get("subject")) + " " +
                                _s(e.get("obligation"))).lower())

    corpus = " \n ".join(ruling_text)
    regimes = []
    for r in compliance_mod.REGIMES:
        sel = selections.get(r["id"])
        cited = any(k in corpus for k in r["keywords"]) if corpus else False
        controls = []
        counts = {"pass": 0, "fail": 0, "waiver": 0, "unattested": 0}
        for cid, statement in r["controls"]:
            a = attest.get((r["id"], cid))
            status = a["status"] if a else None
            if status in counts:
                counts[status] += 1
            else:
                counts["unattested"] += 1
            controls.append({"id": cid, "statement": statement,
                             "status": status,
                             "note": a["note"] if a else None,
                             "by": a["by"] if a else None,
                             "ts": a["ts"] if a else None})
        attested_any = any(c["status"] for c in controls)
        if sel is None:
            challenge = ("unanswered -- select applicable or not "
                         "(`wall compliance " + r["id"] + " ...`)")
            if cited:
                challenge = ("UNSELECTED but Warden rulings cite it -- "
                             "decide, do not drift")
        elif sel["applicable"] and not attested_any and not cited:
            challenge = ("selected with no observed surface yet -- confirm "
                         "it truly applies, then attest")
        elif not sel["applicable"] and cited:
            challenge = ("marked NOT applicable but Warden rulings cite "
                         "it -- revisit the selection")
        else:
            challenge = None
        regimes.append({
            "id": r["id"], "name": r["name"], "doc": r["doc"],
            "applies_when": r["applies_when"],
            "applicable": sel["applicable"] if sel else None,
            "selected_by": sel["by"] if sel else None,
            "reason": sel["reason"] if sel else None,
            "challenge": challenge,
            "counts": counts,
            "controls": controls,
        })
    return {"regimes": regimes,
            "decision_log": selection_log[-20:],
            "any_selected": bool(selections)}


# --------------------------------------------------------------------- flow

# Sizing scale from EVENT_SCHEMA section 8, mapped to points so
# estimate-vs-actual has arithmetic. The mapping is a convention, not a
# truth; what matters is that both columns use the same one.
SIZE_POINTS = {"XS": 1, "S": 2, "M": 3, "L": 5, "XL": 8}
_FLOW_ITERATIONS_SHOWN = 12


def _points(value) -> int | None:
    if isinstance(value, str):
        return SIZE_POINTS.get(value.strip().upper())
    return None


def fold_flow(events: list) -> dict:
    """Velocity / sizing / quality / burndown per iteration, for the
    Foreman's measurement and the Maestro's pacing (DEC-0027).

    An iteration is the segment between two ``retro_held`` records (the
    wave-close boundary the kit already has); the tail segment after the
    last retro is the ``current`` iteration. Everything is counted from the
    existing item stream -- shipped items (velocity), estimate-vs-actual
    points on items that carry both (sizing), bugs filed (quality proxy),
    and the open-item count at each boundary (burndown). No estimates
    recorded means the sizing columns say so instead of inventing numbers.
    """
    open_items: set[str] = set()
    ever: set[str] = set()
    seg = {"shipped": 0, "bugs_filed": 0, "est_points": 0, "act_points": 0,
           "sized": 0, "cost_usd": 0.0}
    seg_agents: dict[str, set] = {}
    seg_delivered: list[dict] = []
    seg_touched: set[str] = set()
    seg_first_ts: list = [None]
    seg_last_ts: list = [None]
    iterations: list[dict] = []
    item_kind: dict[str, str] = {}
    item_title: dict[str, str] = {}
    item_est: dict[str, int] = {}
    item_act: dict[str, int] = {}

    def _item_row(iid: str) -> dict:
        return {"item_id": iid, "title": item_title.get(iid) or None,
                "kind": item_kind.get(iid) or None}

    def close_segment(name: str | None, ts: str | None, current: bool):
        dur = None
        if seg_first_ts[0] and seg_last_ts[0]:
            a = items_mod.parse_ts(seg_first_ts[0])
            b = items_mod.parse_ts(seg_last_ts[0])
            if a and b:
                dur = round((b - a).total_seconds() / 60.0, 1)
        not_delivered = sorted(seg_touched & open_items)
        iterations.append({
            "iteration": name or ("current" if current else "(unnamed)"),
            "current": current,
            "shipped": seg["shipped"],
            "bugs_filed": seg["bugs_filed"],
            "estimate_points": seg["est_points"] if seg["sized"] else None,
            "actual_points": seg["act_points"] if seg["sized"] else None,
            "sized_items": seg["sized"],
            "open_at_close": len(open_items),
            "closed_at": ts,
            # drill-in (DEC-0028): what the iteration cost and carried
            "cost_usd": round(seg["cost_usd"], 4) if seg["cost_usd"] else None,
            "agents": {role: len(keys)
                       for role, keys in sorted(seg_agents.items())},
            "duration_min": dur,
            "delivered": list(seg_delivered),
            "not_delivered": [_item_row(i) for i in not_delivered],
        })
        for k in ("shipped", "bugs_filed", "est_points", "act_points",
                  "sized"):
            seg[k] = 0
        seg["cost_usd"] = 0.0
        seg_agents.clear()
        seg_delivered.clear()
        seg_touched.clear()
        seg_first_ts[0] = None
        seg_last_ts[0] = None

    for e in events:
        if not isinstance(e, dict):
            continue
        ev = e.get("event")
        iid = e.get("item_id") if isinstance(e.get("item_id"), str) else None
        ts = e.get("ts") if isinstance(e.get("ts"), str) else None
        if ts:
            if seg_first_ts[0] is None:
                seg_first_ts[0] = ts
            seg_last_ts[0] = ts
        akey = e.get("agent_key") if isinstance(e.get("agent_key"), str) \
            else None
        if akey:
            role = _s(e.get("role")) or "unknown"
            seg_agents.setdefault(role, set()).add(akey)
        cost = e.get("cost_usd")
        if isinstance(cost, (int, float)) and not isinstance(cost, bool):
            seg["cost_usd"] += float(cost)
        if iid:
            seg_touched.add(iid)
        if ev == "item_created" and iid:
            open_items.add(iid)
            ever.add(iid)
            kind = _s(e.get("kind")).lower()
            item_kind[iid] = kind
            title = _s(e.get("title"))
            if title:
                item_title[iid] = title
            if kind == "bug":
                seg["bugs_filed"] += 1
        elif ev == "item_state" and iid:
            est = _points(e.get("estimate"))
            if est is not None:
                item_est[iid] = est
            act = _points(e.get("actual"))
            if act is not None:
                item_act[iid] = act
            status = e.get("status")
            if status is None and isinstance(e.get("field"), str) and \
                    e.get("field") == "status":
                status = e.get("after")
            if items_mod.is_terminal(status):
                open_items.discard(iid)
        elif ev == "item_shipped" and iid:
            if iid in open_items or iid in ever:
                open_items.discard(iid)
            seg["shipped"] += 1
            seg_delivered.append(_item_row(iid))
            est = item_est.get(iid)
            # EVENT_SCHEMA section 8: actual lands on item_state at close;
            # a shipped record carrying it directly is honored as fallback.
            act = item_act.get(iid)
            if act is None:
                act = _points(e.get("actual"))
            if est is not None and act is not None:
                seg["est_points"] += est
                seg["act_points"] += act
                seg["sized"] += 1
        elif ev == "retro_held":
            close_segment(_s(e.get("wave")) or None,
                          _s(e.get("ts")) or None, current=False)

    close_segment(None, None, current=True)
    shown = iterations[-_FLOW_ITERATIONS_SHOWN:]
    closed = [i for i in shown if not i["current"]]
    velocity = [i["shipped"] for i in closed]
    return {
        "iterations": shown,
        "velocity_series": velocity,
        "open_now": len(open_items),
        "measured": bool(ever),
    }


# ------------------------------------------------------------------- entry

def build_oversight(repo: Path, events: list, config: dict) -> dict:
    return {
        "posture": fold_posture(events),
        "retro": fold_retro(events),
        "docs": fold_docs(repo, events, config),
        "flow": fold_flow(events),
        "compliance": fold_compliance(events),
    }
