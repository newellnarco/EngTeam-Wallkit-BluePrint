#!/usr/bin/env python3
"""Generate sample shards so the wall renders with realistic data.

Also doubles as the --fake-agent fixture source: it exercises the merge,
integrity checks and renderer end to end with zero model calls.

The sample is deliberately unhealthy. Every condition below is one the system
has to survive, and each is a real incident shape rather than a decoration:

  sequence gap            a record was lost; a hole, not a silent vanish
  duplicate seq           two hooks raced on a non-atomic next_seq
  unattributed terminal   the hook could not resolve an agent; says so
  orphan runs             started, past deadline, no terminal event
  stale reclassification  evidence outranks an agent's own status claim
  routed model            requested Fable, safeguards served Opus
  question lifecycle      raised -> assigned -> researcher run -> escalated
                          -> answered, across three sessions (wall trace)
  unassigned past SLA     nobody picked it up (WORKFLOW Section 4)
  blocked, no question    blocked without asking
  state drift             an item file edited out of band (wall diff-state)
  merged but open         RECONCILIATION G9: a merge outran its bookkeeping
  decision log            active, superseded, contradictory and malformed

Run it, then `courier.py --repo .`, then `wall doctor`.
"""

import json
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT.parent / "tools" / "wall"))
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
        # Blocked with nothing on the question queue: WORKFLOW Section 4's
        # first invariant, "blocked without asking".
        ("BG-025", "bug",   "blocked",     "Theo",               "S", None),
    ]),
]

TITLES = {
    "ST-104": "Append-only shard writer",
    "ST-105": "Deterministic merge with dedupe",
    "ST-106": "Checkpointed tail reads per shard",
    "BG-021": "Duplicate event_id on retry",
    "ST-110": "Self-contained HTML template",
    "ST-111": "Atomic publish + heartbeat",
    "ST-112": "Live-poll upgrade path",
    "ST-120": "Path-based route classifier",
    "ST-121": "No-op status check for protection",
    "BG-024": "Mixed changeset takes wrong route",
    "BG-025": "Lease TTL never expires on a crashed agent",
}

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


DECISIONS = {
    # Clean supersession chain: 0018 was replaced by 0042 and says so.
    "DEC-0018": ("""---
id: DEC-0018
status: superseded
supersedes: null
superseded_by: DEC-0042
scope: backend/ledger/
expert: Edmund
expert_key: arc_bb1740
asked_by: bld_a41f09
decided: 2026-09-12T10:41Z
---

# DEC-0018 -- Retries reuse the original event_id

## Ruling

A retried run keeps the event_id of the attempt it replaces.

## Why

Superseded by DEC-0042: it collapses a failed-then-succeeded run into one
record, which is the bug BG-021 reports.
"""),
    "DEC-0042": ("""---
id: DEC-0042
status: active
supersedes: DEC-0018
superseded_by: null
scope: backend/ledger/
expert: Edmund
expert_key: arc_bb1740
asked_by: bld_7e33d1
decided: 2026-09-19T14:03Z
---

# DEC-0042 -- A retry is a new event; the first is marked superseded

## Ruling

Every attempt writes its own record with its own event_id. The failed attempt
carries `superseded_by` pointing at the retry.

## Why

Idempotent merge is keyed on event_id. Reusing one makes the ledger lose a
record that actually happened, which defeats the property the whole audit
trail rests on.
"""),
    # Two active rulings over the same directory: a contradiction candidate,
    # flagged for a human rather than auto-resolved.
    "DEC-0043": ("""---
id: DEC-0043
status: active
supersedes: null
superseded_by: null
scope: backend/ledger/merge.py
expert: Vivienne
expert_key: arc_77ce10
asked_by: bld_a41f09
decided: 2026-09-19T15:20Z
---

# DEC-0043 -- Merge sorts on (ts, session_id, seq) and nothing else

## Ruling

No tiebreak beyond those three. Adding one makes rebuild order-dependent.
"""),
    # No front matter at all: the parser must name this, not swallow it.
    "DEC-0099": ("""# DEC-0099 -- notes from the call

We agreed the courier should probably do the thing. Someone write this up
properly.
"""),
}


def write_decisions(root: Path) -> None:
    d = root / "docs" / "decisions"
    d.mkdir(parents=True, exist_ok=True)
    for dec_id, text in DECISIONS.items():
        (d / f"{dec_id}.md").write_text(text, encoding="utf-8")


def main(root: Path = ROOT):
    root = Path(root)
    rng = random.Random(7)
    # A third session so `wall trace` has a genuine cross-session hop to show:
    # the researcher and the architect ran in their own sessions.
    shards = {"s_7f3a": [], "s_b19e": [], "s_c22d": []}
    counters = {k: 0 for k in shards}
    t = T0

    def emit(session, ts, **kw):
        counters[session] += 1
        shards[session].append(ev(session, counters[session], ts, **kw))

    # Board state
    for arc_id, arc_title, items in ITEMS:
        for iid, kind, status, assignee, est, act in items:
            t += timedelta(seconds=rng.randint(40, 400))
            emit("s_7f3a", t, event="item_created", item_id=iid, kind=kind,
                 title=TITLES[iid], arc_id=arc_id, arc_title=arc_title,
                 trace_id=f"tr_{iid.lower().replace('-', '')}")
            t += timedelta(seconds=rng.randint(10, 90))
            emit("s_7f3a", t, event="item_state", item_id=iid, kind=kind, status=status,
                 title=TITLES[iid],
                 arc_id=arc_id, arc_title=arc_title, assignee=assignee,
                 estimate=est, actual=act,
                 scope=["backend/ledger/"] if arc_id == "ARC-01" else [],
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
        # Safeguards route some Fable requests to Opus 5; the ledger must
        # record what actually ran, not what was asked for. Pinned to one
        # agent rather than sampled, so the fixture's claim ("Coretta shows
        # requested -> routed") stays true whatever else moves upstream.
        used = "claude-opus-5" if aid == "adj_5c02ea" else model
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

    # ---- question lifecycle, three sessions, one trace ------------------
    # ST-106: Desmond hits an unclear acceptance criterion, keeps its lease
    # because the scopes are file-disjoint (outcome_hint "partial"), Maestro
    # assigns Silas, Silas runs, it ages past the architect SLA and escalates,
    # Edmund rules, the answer lands. This is the chain `wall trace` exists to
    # show, and it deliberately crosses s_7f3a -> s_c22d.
    q_t = T0 + timedelta(hours=2)
    emit("s_7f3a", q_t, event="question_raised", question_id="q_0042",
         item_id="ST-106", trace_id="tr_st106", agent_key="bld_a41f09",
         agent_name="Desmond", role="builder", ambiguity_class="unclear_acceptance",
         question="AC-3 says the checkpoint is per shard; AC-4 says per session. "
                  "Which survives a shard being replaced?",
         blocks_criteria=["AC-3", "AC-4"],
         dependent_scope=["backend/ledger/merge.py", "backend/tests/test_merge.py"],
         independent_scope=["backend/ledger/shard.py"], outcome_hint="partial")
    emit("s_7f3a", q_t + timedelta(minutes=3), event="question_assigned",
         question_id="q_0042", item_id="ST-106", trace_id="tr_st106",
         agent_key="mst_08de37", agent_name="Rosalind", role="maestro",
         assignee="Silas", assignee_key="res_d470af")
    emit("s_c22d", q_t + timedelta(minutes=9), event="run_start",
         question_id="q_0042", item_id="ST-106", trace_id="tr_st106",
         agent_key="res_d470af", agent_name="Silas", role="researcher",
         model_requested="claude-sonnet-5", model_used="claude-sonnet-5",
         run_id="run_res_0042", parent_run_id="run_live_bld_a41f09")
    emit("s_c22d", q_t + timedelta(minutes=21), event="run_end",
         question_id="q_0042", item_id="ST-106", trace_id="tr_st106",
         agent_key="res_d470af", agent_name="Silas", role="researcher",
         model_requested="claude-sonnet-5", model_used="claude-sonnet-5",
         run_id="run_res_0042", outcome="partial", duration_s=720,
         error_class="ambiguous_requirement", cost_usd=0.41,
         tokens=tokens(rng, 1), decisions_in_context=["DEC-0018"],
         hook={"source": "SubagentStop", "resolution": "resolved",
               "agent_reported": True})
    # A terminal record the hook could not attribute: the agent never wrote
    # one, and the stop carried no key. It is logged with agent_key null and
    # resolution "unresolved" rather than guessed at, so the run surfaces as
    # an orphan instead of being quietly filed under whoever ran last.
    emit("s_c22d", q_t + timedelta(minutes=27), event="run_error",
         run_id="run_unattributed", agent_key=None, item_id="ST-112",
         outcome="error", error_class="tool_error",
         hook={"source": "SubagentStop", "resolution": "unresolved",
               "agent_reported": False})
    emit("s_c22d", q_t + timedelta(minutes=34), event="question_escalated",
         question_id="q_0042", item_id="ST-106", trace_id="tr_st106",
         agent_key="mst_08de37", agent_name="Rosalind", role="maestro",
         tier="architect", reason="researcher pass found prior art but no ruling")
    emit("s_c22d", q_t + timedelta(minutes=48), event="question_answered",
         question_id="q_0042", item_id="ST-106", trace_id="tr_st106",
         agent_key="arc_bb1740", agent_name="Edmund", role="architect",
         source="architect", answer="Checkpoint per shard; a replaced shard "
                                    "resets its own offset and nothing else.",
         decisions_in_context=["DEC-0042"])
    emit("s_c22d", q_t + timedelta(minutes=49), event="decision_written",
         item_id="ST-106", trace_id="tr_st106", agent_key="mst_08de37",
         agent_name="Rosalind", role="maestro", decision_id="DEC-0042",
         decisions_in_context=["DEC-0042"])

    # ST-112: raised and never picked up. `unassigned_past_sla` -- nobody's
    # fault in particular, which is exactly why it has to be mechanical.
    emit("s_7f3a", now - timedelta(minutes=45), event="question_raised",
         question_id="q_0051", item_id="ST-112", trace_id="tr_st112",
         agent_key="bld_2fc885", agent_name="Theo", role="builder",
         ambiguity_class="undefined_interface",
         question="Does the live-poll upgrade read wall.json or subscribe to a "
                  "socket? No interface is specified either way.",
         blocks_criteria=["AC-1"], outcome_hint="blocked")

    # ---- G9: the merge outran its own bookkeeping -----------------------
    # ST-105 ships as PR 1654, and a lagging compactor then writes the item
    # back to in_review. The fold is faithful to the ledger; the ledger now
    # contradicts itself, which is the flag.
    ship_t = T0 + timedelta(hours=3)
    emit("s_7f3a", ship_t, event="item_shipped", item_id="ST-105",
         trace_id="tr_st105", pr=1654, agent_key="mst_08de37",
         agent_name="Rosalind", role="maestro", actual="XL")
    emit("s_7f3a", ship_t + timedelta(minutes=4), event="item_state",
         item_id="ST-105", status="in_review", pr_state="open",
         agent_key="frm_4a91c2", agent_name="Alistair", role="foreman")

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
             trace_id=f"tr_{item.lower().replace('-', '')}")

    # An orphan run, so the integrity panel has something real to show
    emit("s_b19e", now - timedelta(hours=3), event="run_start", agent_key="res_66c1b3",
         agent_name="Nadia", role="researcher",
         model_requested="claude-sonnet-5", model_used="claude-sonnet-5",
         run_id="run_orphan_1", item_id="ST-121", item_title="No-op status check")

    out = root / ".wall" / "events" / DAY
    out.mkdir(parents=True, exist_ok=True)
    for session, rows in shards.items():
        rows.sort(key=lambda e: e["ts"])
        for n, e in enumerate(rows, 1):
            e["seq"] = n
        # Drop one record to leave a sequence gap the integrity panel will
        # catch. Deliberately a run_end: a lost write is worst when it is the
        # terminal record, because the run then also reads as an orphan and
        # the agent that finished it reclassifies to stale. Targeted by event
        # type rather than by index so the fixture keeps meaning what it says
        # when anything upstream shifts the stream.
        if session == "s_b19e" and len(rows) > 12:
            victim = next((n for n, e in enumerate(rows)
                           if n >= 9 and e.get("event") == "run_end"), 9)
            rows.pop(victim)
        # And the other direction: two hooks computed next_seq in the same
        # instant and both wrote. `next_seq` is deliberately not atomic across
        # processes -- a duplicate is visible, a gap is a lost write -- so the
        # validator has to catch both. Shift the tail so this is a clean
        # duplicate with no hole beside it.
        if session == "s_c22d" and len(rows) > 4:
            for e in rows[3:]:
                e["seq"] -= 1
        (out / f"{session}.jsonl").write_text(
            "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in rows), encoding="utf-8")

    cfg = root / ".wall" / "config"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "wall.json").write_text(json.dumps({
        "repo_name": "Atlas-Core",
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
                 "display": "3.1M", "foot": "adjudicator runs routed to Opus by safeguards"},
                {"label": "GitHub Actions", "used": 1_412, "limit": 3_000,
                 "display": "1,412 min", "foot": "fast-track saved an estimated 240 min"},
            ],
        },
        "sla_minutes": {
            "question_assigned": 5,
            "researcher_first_run": 10,
            "escalate_to_architect": 30,
            "escalate_to_human": 60,
            "question_open_escalate": 60,
        },
        "decisions_dir": "docs/decisions",
        "fast_track": {
            "allow": ["**/*.md", "docs/**/*.docx", "MANIFEST.sha256"],
            "deny": ["frontend/src/**", "backend/**/*.py", "**/*.bat", "**/*.ps1",
                     ".github/workflows/**", "tools/**", ".wall/config/**",
                     "**/CLAUDE.md"],
            "significant": ["docs/architecture/**", "docs/decisions/**"],
        },
    }, indent=2), encoding="utf-8")

    write_decisions(root)

    # Materialize the item files, then edit one behind the ledger's back. An
    # out-of-band write is the condition `wall diff-state` exists to catch, so
    # the sample has to contain one or the check is never exercised.
    import items as items_mod   # tools/wall is on sys.path (see header)

    events = [json.loads(line)
              for shard in sorted(out.glob("*.jsonl"))
              for line in shard.read_text(encoding="utf-8").splitlines() if line.strip()]
    items_mod.rebuild(root, events)
    tampered = root / ".wall" / "items" / "ST-110.json"
    record = json.loads(tampered.read_text(encoding="utf-8"))
    record["status"] = "active"
    record["assignee"] = "Hollis"
    tampered.write_text(items_mod.serialize_item(record), encoding="utf-8")

    print(f"wrote {sum(len(r) for r in shards.values())} events to {out}")
    print(f"  {len(DECISIONS)} decisions, {len(items_mod.fold_items(events))} item files, "
          f"1 edited out of band (ST-110)")


if __name__ == "__main__":
    main()
