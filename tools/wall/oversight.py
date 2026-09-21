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

Design charter: docs/WALL_DASHBOARDS.md (kit DEC-0026).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

try:  # courier imports these as siblings (sys.path includes tools/wall)
    import decisions as decisions_mod
except ImportError:  # pragma: no cover - direct package-style import
    from . import decisions as decisions_mod  # type: ignore

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
    return {"held": len(retros), "latest": latest_view, "trends": trend_rows}


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
    for e in events:  # ledger order; last review per path wins
        if not isinstance(e, dict) or e.get("event") != "doc_reviewed":
            continue
        path = _s(e.get("path"))
        if not path:
            continue
        reviews[path] = {"sha": _s(e.get("sha")) or None,
                         "by": _s(e.get("by")) or None,
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
        if sha is None:
            state = "missing"
        elif review is None:
            state = "never-reviewed"
        elif review.get("sha") == sha:
            state = "current"
        else:
            state = "changed-since-review"
        if state in ("never-reviewed", "changed-since-review"):
            needs_review += 1
        rows.append({"path": rel, "sha": sha, "state": state,
                     "review": review})

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


# ------------------------------------------------------------------- entry

def build_oversight(repo: Path, events: list, config: dict) -> dict:
    return {
        "posture": fold_posture(events),
        "retro": fold_retro(events),
        "docs": fold_docs(repo, events, config),
    }
