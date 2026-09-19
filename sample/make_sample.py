#!/usr/bin/env python3
"""Generate sample shards so the wall renders with realistic data.

Also doubles as the --fake-agent fixture source: it exercises the merge,
integrity checks and renderer end to end with zero model calls.
"""

import json
import random
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).parent
DAY = "2026-09-19"
T0 = datetime(2026, 9, 19, 12, 5, tzinfo=timezone.utc)
now = datetime.now(timezone.utc)

CREW = [
    # First names only, unique across the whole project. Distinct initials so
    # they stay unambiguous when you refer to one in passing.
    ("frm_4a91c2", "Alistair", "foreman"),
    ("mst_08de37", "Rosalind", "maestro"),
    ("arc_bb1740", "Edmund",   "architect"),
    ("adj_5c02ea", "Coretta",  "adjudicator"),
    ("bld_a41f09",  "Desmond",  "builder"),
    ("bld_7e33d1",  "Priya",    "builder"),
    ("bld_2fc885",  "Theo",     "builder"),
    ("rev_913b6e",  "Junia",    "reviewer"),
    ("res_d470af",  "Silas",    "researcher"),
    ("res_66c1b3",  "Nadia",    "researcher"),
]

MODELS = {
    "foreman": "claude-sonnet-5", "maestro": "claude-opus-5",
    "architect": "claude-fable-5-1", "adjudicator": "claude-fable-5-1",
    "builder": "claude-opus-5", "reviewer": "claude-sonnet-5",
    "researcher": "claude-sonnet-5",
}
MODELS_BY_KEY = {"bld_2fc885": "claude-sonnet-5"}

ITEMS = [
    ("ARC-01", "Event ledger and consolidation", [
        ("ST-104", "story", "done",        "Desmond"    ,   "M", "M"),
        ("ST-105", "story", "in_review",   "Priya"      , "L", "XL"),
        ("ST-106", "story", "active",      "Desmond"    ,   "M", None),
        ("BG-021", "bug",   "blocked",     "Priya"      , "S", None),
    ]),
    ("ARC-02", "Wall renderer and propagation", [
        ("ST-110", "story", "done",        "Theo"       ,  "S", "S"),
        ("ST-111", "story", "active",      "Theo"       ,  "M", None),
        ("ST-112", "story", "ready",       None,                 "M", None),
    ]),
    ("ARC-03", "Fast-track routing", [
        ("ST-120", "story", "ready",       None,                 "S", None),
        ("ST-121", "story", "ready",       None,                 "M", None),
        ("BG-024", "bug",   "triage",      None,                 "S", None),
    ]),
]

# Which agents are mid-run right now, and on what.
ACTIVE = {
    "bld_a41f09": ("ST-106", "Checkpointed tail reads per shard", 18),
    "bld_2fc885": ("ST-111", "Atomic publish + heartbeat", 6),
    "res_d470af": ("BG-021", "Find prior art on seq-gap recovery", 3),
    "frm_4a91c2": (None, None, 1),
}
BLOCKED = {"bld_7e33d1": ("BG-021", "Duplicate event_id on retry", 41)}


def ev(session, seq, ts, **kw):
    e = {"schema_version": 1, "event_id": str(uuid.uuid4()), "seq": seq,
         "ts": ts.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
         "session_id": session}
    e.update(kw)
    return e


def tokens(rng, scale):
    return {"in": rng.randint(9_000, 24_000) * scale,
            "out": rng.randint(1_200, 4_800) * scale,
            "cache_read": rng.randint(40_000, 160_000) * scale,
            "cache_write": rng.randint(2_000, 9_000) * scale}


def main():
    rng = random.Random(7)
    shards = {"s_7f3a": [], "s_b19e": []}
    counters = {k: 0 for k in shards}
    t = T0

    def emit(session, ts, **kw):
        counters[session] += 1
        shards[session].append(ev(session, counters[session], ts, **kw))

    # Board state
    for arc_id, arc_title, items in ITEMS:
        for iid, kind, status, assignee, est, act in items:
            t += timedelta(seconds=rng.randint(40, 400))
            emit("s_7f3a", t, event="item_state", item_id=iid, kind=kind, status=status,
                 title={"ST-104": "Append-only shard writer",
                        "ST-105": "Deterministic merge with dedupe",
                        "ST-106": "Checkpointed tail reads per shard",
                        "BG-021": "Duplicate event_id on retry",
                        "ST-110": "Self-contained HTML template",
                        "ST-111": "Atomic publish + heartbeat",
                        "ST-112": "Live-poll upgrade path",
                        "ST-120": "Path-based route classifier",
                        "ST-121": "No-op status check for protection",
                        "BG-024": "Mixed changeset takes wrong route"}[iid],
                 arc_id=arc_id, arc_title=arc_title, assignee=assignee,
                 estimate=est, actual=act,
                 duplicate_of="ST-112" if iid == "ST-120" else None)

    # Completed runs
    for i in range(34):
        aid, name, role = rng.choice(CREW)
        model = MODELS_BY_KEY.get(aid, MODELS[role])
        if aid in ACTIVE or aid in BLOCKED:
            continue
        session = "s_7f3a" if i % 3 else "s_b19e"
        t += timedelta(seconds=rng.randint(30, 300))
        run = f"run_{i:03d}"
        scale = 3 if role == "builder" else 1
        # Safeguards occasionally route a Fable request to Opus 5; the ledger
        # must record what actually ran, not what was asked for.
        used = "claude-opus-5" if (model == "claude-fable-5-1" and rng.random() < 0.25) else model
        common = dict(agent_key=aid, agent_name=name, role=role,
                      model_requested=model, model_used=used, run_id=run)
        emit(session, t, event="run_start", item_id="ST-104", item_title="…", **common)
        t += timedelta(seconds=rng.randint(20, 180))
        emit(session, t, event="run_end", outcome="pass", tokens=tokens(rng, scale),
             cost_usd=round(rng.uniform(0.18, 2.6) * scale, 3),
             gh_minutes=rng.choice([None, None, 2, 4]), **common)

    # In-flight runs
    for aid, (item, item_title, mins) in ACTIVE.items():
        agent = next(c for c in CREW if c[0] == aid)
        _, nm, role = agent
        model = MODELS_BY_KEY.get(aid, MODELS[role])
        emit("s_7f3a", now - timedelta(minutes=mins), event="run_start",
             agent_key=aid, agent_name=nm, role=role,
             model_requested=model, model_used=model, run_id=f"run_live_{aid}",
             item_id=item, item_title=item_title)

    # Blocked builder + the question waiting on the human
    for aid, (item, item_title, mins) in BLOCKED.items():
        agent = next(c for c in CREW if c[0] == aid)
        _, nm, role = agent
        model = MODELS_BY_KEY.get(aid, MODELS[role])
        common = dict(agent_key=aid, agent_name=nm, role=role,
                      model_requested=model, model_used=model, run_id=f"run_blk_{aid}")
        emit("s_b19e", now - timedelta(minutes=mins + 4), event="run_start",
             item_id=item, item_title=item_title, **common)
        emit("s_b19e", now - timedelta(minutes=mins), event="run_end", outcome="blocked",
             tokens=tokens(rng, 2), cost_usd=1.42, **common)

    asks = [
        ("ask_0007", "bld_7e33d1", "Priya", "BG-021", 38,
         "Retries reuse the original event_id, so a failed-then-succeeded run collapses to one "
         "record. Should a retry be a new event, or should the ledger keep both and mark the "
         "first superseded?"),
        ("ask_0008", "arc_bb1740", "Edmund", "ST-112", 11,
         "Committing derived/ would give a git-native audit trail but conflicts across parallel "
         "sessions every two minutes. Confirm derived/ stays gitignored?"),
        ("ask_0009", "mst_08de37", "Rosalind", "ARC-03", 4,
         "Fast-track: push straight to main, or open a PR that auto-merges once the no-op check "
         "reports?"),
    ]
    for ask_id, aid, nm, item, mins, q in asks:
        emit("s_b19e", now - timedelta(minutes=mins), event="human_required",
             ask_id=ask_id, agent_key=aid, agent_name=nm, item_id=item, question=q,
             trace_id=f"tr_{item.lower()}")

    # An orphan run, so the integrity panel has something real to show
    emit("s_b19e", now - timedelta(hours=3), event="run_start", agent_key="res_66c1b3",
         agent_name="Nadia", role="researcher",
         model_requested="claude-sonnet-5", model_used="claude-sonnet-5",
         run_id="run_orphan_1", item_id="ST-121", item_title="No-op status check")

    out = ROOT / ".wall" / "events" / DAY
    out.mkdir(parents=True, exist_ok=True)
    for session, rows in shards.items():
        rows.sort(key=lambda e: e["ts"])
        for n, e in enumerate(rows, 1):
            e["seq"] = n
        # Drop one record to leave a sequence gap the integrity panel will catch.
        if session == "s_b19e" and len(rows) > 12:
            rows.pop(9)
        (out / f"{session}.jsonl").write_text(
            "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in rows), encoding="utf-8")

    cfg = ROOT / ".wall" / "config"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "wall.json").write_text(json.dumps({
        "repo_name": "atlas-core",
        "role_limits": {"builder": 4, "researcher": 6, "reviewer": 2},
        "budget": {
            "period": "week of 14 Sep 2026",
            "advisory": "Advisory only. Nothing here stops work — it tells you when to.",
            "meters": [
                {"label": "Claude — Opus 5", "used": 41_200_000, "limit": 60_000_000,
                 "display": "41.2M", "foot": "builders account for 78% of this"},
                {"label": "Claude — Sonnet 5", "used": 12_800_000, "limit": 90_000_000,
                 "display": "12.8M", "foot": "researchers and review"},
                {"label": "Claude — Fable 5.1", "used": 3_100_000, "limit": 20_000_000,
                 "display": "3.1M", "foot": "1 run routed to Opus by safeguards"},
                {"label": "GitHub Actions", "used": 1_412, "limit": 3_000,
                 "display": "1,412 min", "foot": "fast-track saved an estimated 240 min"},
            ],
        },
    }, indent=2), encoding="utf-8")
    print(f"wrote {sum(len(r) for r in shards.values())} events to {out}")


if __name__ == "__main__":
    main()
