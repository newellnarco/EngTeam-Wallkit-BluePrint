"""The property the audit trail rests on: a full rebuild equals an incremental
run, byte for byte.

Merge is a union on `event_id` totally ordered by `(ts, session_id, seq)`. If
that ever stops holding, the ledger stops being reproducible and every claim
built on it -- the wall, the rollups, the integrity flags -- becomes a report
nobody can check. So it is pinned here rather than asserted in a README.
"""

from __future__ import annotations

import json

import courier
import items

LEDGER = ".wall/derived/ledger.jsonl"


def run(repo, rebuild=False):
    return courier.run_once(repo, rebuild=rebuild)


def shard(repo, session, rows, day="2026-09-19"):
    path = repo / ".wall" / "events" / day / f"{session}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def ev(session, seq, ts, **kw):
    base = {"schema_version": 1, "event_id": f"{session}-{seq}", "seq": seq,
            "ts": ts, "session_id": session, "event": "run_start",
            "agent_key": "bld_1", "agent_name": "Desmond", "role": "builder",
            "run_id": f"r{seq}", "item_id": "ST-1"}
    base.update(kw)
    return base


def test_full_rebuild_equals_incremental_byte_for_byte(repo):
    shard(repo, "s_a", [ev("s_a", 1, "2026-09-19T12:00:00.000Z"),
                        ev("s_a", 2, "2026-09-19T12:02:00.000Z", event="run_end",
                           outcome="pass")])
    run(repo)

    # A second sweep after more writes: the incremental path reads only the
    # unread tail of each shard.
    shard(repo, "s_b", [ev("s_b", 1, "2026-09-19T12:01:00.000Z")])
    shard(repo, "s_a", [ev("s_a", 3, "2026-09-19T12:05:00.000Z",
                           event="item_state", item_id="ST-1", status="done")])
    run(repo)
    incremental = (repo / LEDGER).read_bytes()

    run(repo, rebuild=True)
    assert (repo / LEDGER).read_bytes() == incremental


def test_shard_read_order_does_not_change_the_ledger(repo, tmp_path):
    rows_a = [ev("s_a", 1, "2026-09-19T12:00:00.000Z"),
              ev("s_a", 2, "2026-09-19T12:03:00.000Z")]
    rows_b = [ev("s_b", 1, "2026-09-19T12:01:00.000Z"),
              ev("s_b", 2, "2026-09-19T12:02:00.000Z")]
    shard(repo, "s_a", rows_a)
    shard(repo, "s_b", rows_b)
    run(repo, rebuild=True)
    forward = (repo / LEDGER).read_bytes()

    other = tmp_path / "mirror"
    (other / ".wall" / "events" / "2026-09-19").mkdir(parents=True)
    shard(other, "s_b", rows_b)
    shard(other, "s_a", rows_a)
    run(other, rebuild=True)
    assert (other / LEDGER).read_bytes() == forward


def test_a_replayed_shard_is_idempotent(repo):
    rows = [ev("s_a", 1, "2026-09-19T12:00:00.000Z"),
            ev("s_a", 2, "2026-09-19T12:01:00.000Z")]
    shard(repo, "s_a", rows)
    run(repo, rebuild=True)
    once = (repo / LEDGER).read_bytes()

    shard(repo, "s_a", rows)          # the same records again, same event_ids
    run(repo)
    assert (repo / LEDGER).read_bytes() == once


def test_a_trailing_partial_line_waits_for_the_next_sweep(repo):
    path = repo / ".wall" / "events" / "2026-09-19" / "s_a.jsonl"
    complete = json.dumps(ev("s_a", 1, "2026-09-19T12:00:00.000Z"))
    partial = json.dumps(ev("s_a", 2, "2026-09-19T12:01:00.000Z"))
    path.write_text(complete + "\n" + partial[:40], encoding="utf-8")
    snapshot = run(repo)
    assert snapshot["courier"]["events"] == 1

    path.write_text(complete + "\n" + partial + "\n", encoding="utf-8")
    assert run(repo)["courier"]["events"] == 2


def test_the_item_fold_is_the_same_view_the_wall_renders(repo):
    shard(repo, "s_a", [
        ev("s_a", 1, "2026-09-19T12:00:00.000Z", event="item_created",
           item_id="ST-1", title="A", kind="story", arc_id="ARC-1"),
        ev("s_a", 2, "2026-09-19T12:01:00.000Z", event="item_state",
           item_id="ST-1", status="active"),
    ])
    snapshot = run(repo, rebuild=True)
    items.rebuild(repo)

    on_wall = snapshot["board"]["arcs"][0]["items"][0]
    on_disk = json.loads((repo / ".wall" / "items" / "ST-1.json").read_text())
    for key in ("item_id", "title", "kind", "status", "arc_id"):
        assert on_wall[key] == on_disk[key]
    assert snapshot["integrity"]["state_drift"] == 0


def test_the_sample_fixture_reproduces_its_own_claims(tmp_path):
    """The sample is the fixture library the whole kit tests against, so its
    advertised conditions are pinned here rather than trusted."""
    import make_sample

    make_sample.main(tmp_path)
    snapshot = run(tmp_path)
    flags = snapshot["integrity"]

    assert len(flags["seq_gaps"]) == 1, "a deleted record leaves a hole"
    assert len(flags["seq_duplicates"]) == 1, "two hooks raced on next_seq"
    assert len(flags["orphan_runs"]) == 2, "started, past deadline, no terminal"
    assert flags["state_drift"] == 2, "ST-110 was edited out of band"
    assert flags["state_drift_checked"] is True
    assert [f["kind"] for f in flags["merged_but_open"]] == ["reopened_after_ship"]

    kinds = {f["kind"] for f in flags["escalations"]}
    assert "blocked_without_question" in kinds
    assert "unassigned_past_sla" in kinds

    stale = {c["agent"] for c in flags["stale_claims"]}
    assert "Nadia" in stale, "a blown deadline reclassifies the agent"

    routed = [a for a in snapshot["crew"]
              if a["model_requested"] != a["model_used"]]
    assert [a["name"] for a in routed] == ["Coretta"]

    # The hook's own provenance survives the merge.
    ledger = [json.loads(line) for line in
              (tmp_path / LEDGER).read_text().splitlines() if line.strip()]
    unresolved = [e for e in ledger
                  if isinstance(e.get("hook"), dict)
                  and e["hook"]["resolution"] == "unresolved"]
    assert len(unresolved) == 1
    assert unresolved[0]["agent_key"] is None, "an unattributed stop is not guessed at"


def test_the_sample_rebuilds_byte_identically(tmp_path):
    import make_sample

    make_sample.main(tmp_path)
    run(tmp_path)
    incremental = (tmp_path / LEDGER).read_bytes()
    run(tmp_path, rebuild=True)
    assert (tmp_path / LEDGER).read_bytes() == incremental


def test_an_item_with_a_null_arc_id_lands_in_unassigned_not_a_crash(tmp_path):
    """items._blank() writes arc_id: None for any item that never set an arc.

    build_snapshot's arc grouping must treat that explicit None like an absent
    field (the `or "unassigned"` form), or the arc sort raises TypeError
    comparing None to str -- which is exactly what the first real board overlay
    hit. Same rule for a null arc_title rendering as the string "None".
    """
    day = "2026-09-19"
    sh = tmp_path / ".wall" / "events" / day
    sh.mkdir(parents=True)
    ev = {"event_id": "ev_nullarc01", "seq": 1, "ts": f"{day}T10:00:00Z",
          "session_id": "s_null", "event": "item_created", "item_id": "ST-900",
          "title": "no arc set", "kind": "story", "actor": "tst_000000"}
    (sh / "s_null.jsonl").write_text(json.dumps(ev) + "\n", encoding="utf-8")
    (tmp_path / ".wall" / "config").mkdir()
    snap = courier.run_once(tmp_path, rebuild=True)
    arcs = {a["arc_id"]: a for a in snap["board"]["arcs"]}
    assert "unassigned" in arcs
    assert all(a["arc_id"] is not None and a["title"] is not None
               for a in arcs.values())
