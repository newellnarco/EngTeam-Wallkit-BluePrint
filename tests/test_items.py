"""The materialized item view: fold, rebuild, drift, and the G9 reconcile."""

from __future__ import annotations

import json

import items


def ev(**kw):
    base = {"schema_version": 1, "event_id": kw.pop("event_id", "e" + str(len(kw))),
            "seq": kw.pop("seq", 1), "ts": kw.pop("ts", "2026-09-19T12:00:00.000Z"),
            "session_id": kw.pop("session_id", "s_a")}
    base.update(kw)
    return base


# ------------------------------------------------------------------- fold

def test_fold_applies_snapshot_and_delta_shapes():
    events = [
        ev(event="item_created", item_id="ST-1", title="A", kind="story",
           trace_id="tr_1", ts="2026-09-19T12:00:00.000Z", seq=1),
        ev(event="item_state", item_id="ST-1", status="ready", assignee="Desmond",
           ts="2026-09-19T12:01:00.000Z", seq=2),
        ev(event="item_state", item_id="ST-1", field="status",
           before="ready", after="active", ts="2026-09-19T12:02:00.000Z", seq=3),
    ]
    item = items.fold(events).items["ST-1"]
    assert item["status"] == "active"        # the delta won, it was later
    assert item["assignee"] == "Desmond"     # the snapshot field survived
    assert item["title"] == "A"
    assert item["trace_id"] == "tr_1"
    assert item["events"] == 3
    assert item["created_at"] == "2026-09-19T12:00:00.000Z"
    assert item["updated_at"] == "2026-09-19T12:02:00.000Z"


def test_fold_is_order_independent():
    events = [
        ev(event="item_state", item_id="ST-1", status="done",
           ts="2026-09-19T12:05:00.000Z", seq=2, event_id="b"),
        ev(event="item_state", item_id="ST-1", status="ready",
           ts="2026-09-19T12:01:00.000Z", seq=1, event_id="a"),
    ]
    assert items.fold(events).items["ST-1"]["status"] == "done"
    assert items.fold(list(reversed(events))).items["ST-1"]["status"] == "done"


def test_fold_refuses_a_delta_that_rewrites_the_envelope():
    result = items.fold([ev(event="item_state", item_id="ST-1",
                            field="item_id", before="ST-1", after="ST-9")])
    assert result.items["ST-1"]["item_id"] == "ST-1"
    assert [p["kind"] for p in result.problems] == ["protected_field_write"]


def test_fold_names_malformed_records_instead_of_crashing():
    result = items.fold(["not an object", 17, None,
                         ev(event="item_state", status="ready")])
    assert {p["kind"] for p in result.problems} == {
        "malformed_event", "item_event_without_id"}
    assert result.items == {}


def test_fold_never_leaves_a_null_where_the_wall_renders_a_string():
    # The template calls .replace() on status; a null there is a blank panel.
    item = items.fold([ev(event="item_created", item_id="ST-1")]).items["ST-1"]
    assert (item["title"], item["kind"], item["status"]) == ("", "", "")


def test_order_key_survives_a_wrong_typed_seq():
    rows = [ev(seq=None, ts="2026-09-19T12:00:00.000Z"),
            ev(seq=2, ts="2026-09-19T12:00:00.000Z")]
    assert sorted(rows, key=items.order_key)[0]["seq"] is None  # sorts, no TypeError


def test_item_shipped_flips_state_at_merge_time():
    item = items.fold([
        ev(event="item_state", item_id="ST-5", status="in_ci", seq=1,
           ts="2026-09-19T12:00:00.000Z"),
        ev(event="item_shipped", item_id="ST-5", pr=1654, seq=2,
           ts="2026-09-19T12:30:00.000Z"),
    ]).items["ST-5"]
    assert item["status"] == "shipped"
    assert item["pr"] == 1654
    assert item["shipped_at"] == "2026-09-19T12:30:00.000Z"


# ---------------------------------------------------------------- rebuild

def test_rebuild_is_idempotent_and_byte_stable(repo, write_shard):
    write_shard("s_a", [{"event": "item_created", "item_id": "ST-1", "title": "A"},
                        {"event": "item_state", "item_id": "ST-1", "status": "ready"}])
    first = items.rebuild(repo)
    path = repo / ".wall" / "items" / "ST-1.json"
    text = path.read_bytes()
    second = items.rebuild(repo)
    assert first["written"] == ["ST-1"]
    assert second["written"] == [] and second["unchanged"] == ["ST-1"]
    assert path.read_bytes() == text


def test_rebuild_reports_orphans_and_only_prunes_when_told(repo, write_shard):
    write_shard("s_a", [{"event": "item_created", "item_id": "ST-1"}])
    items.rebuild(repo)
    stray = repo / ".wall" / "items" / "ST-99.json"
    stray.write_text(json.dumps({"item_id": "ST-99"}), encoding="utf-8")

    assert items.rebuild(repo)["orphans"] == ["ST-99"]
    assert stray.exists(), "a file no event created is reported, not deleted"
    assert items.rebuild(repo, prune=True)["removed"] == ["ST-99"]
    assert not stray.exists()


# -------------------------------------------------------------- diff-state

def test_diff_state_is_not_checked_before_the_first_rebuild(repo, write_shard):
    write_shard("s_a", [{"event": "item_created", "item_id": "ST-1"}])
    result = items.diff_state(repo)
    assert result["checked"] is False and result["count"] == 0
    assert "wall rebuild" in result["note"]


def test_diff_state_catches_an_out_of_band_edit(repo, write_shard):
    write_shard("s_a", [{"event": "item_created", "item_id": "ST-1", "title": "A"},
                        {"event": "item_state", "item_id": "ST-1", "status": "done"}])
    items.rebuild(repo)
    path = repo / ".wall" / "items" / "ST-1.json"
    record = json.loads(path.read_text())
    record["status"] = "active"
    path.write_text(items.serialize_item(record), encoding="utf-8")

    result = items.diff_state(repo)
    assert result["checked"] is True and result["count"] == 1
    drift = result["drift"][0]
    assert (drift["item_id"], drift["field"]) == ("ST-1", "status")
    assert (drift["expected"], drift["found"]) == ("done", "active")


def test_diff_state_names_an_unreadable_item_file(repo, write_shard):
    write_shard("s_a", [{"event": "item_created", "item_id": "ST-1"}])
    items.rebuild(repo)
    (repo / ".wall" / "items" / "ST-1.json").write_text("{ broken", encoding="utf-8")
    result = items.diff_state(repo)
    assert any(p["kind"] == "unreadable_item" for p in result["problems"])
    assert any(d["kind"] == "missing_on_disk" for d in result["drift"])


# ------------------------------------------------------ G9: merged but open

def test_g9_flags_an_item_reopened_after_shipping():
    flags = items.merged_but_open([
        ev(event="item_state", item_id="ST-5", status="in_ci", seq=1,
           ts="2026-09-19T12:00:00.000Z"),
        ev(event="item_shipped", item_id="ST-5", pr=1654, seq=2,
           ts="2026-09-19T12:30:00.000Z"),
        # The compactor catches up late and writes the stale status back.
        ev(event="item_state", item_id="ST-5", status="in_ci", seq=3,
           ts="2026-09-19T12:34:00.000Z"),
    ])
    assert len(flags) == 1
    assert flags[0]["kind"] == "reopened_after_ship"
    assert flags[0]["pr"] == 1654


def test_g9_flags_a_disk_record_still_claiming_an_open_pr():
    events = [ev(event="item_shipped", item_id="ST-5", pr=1654, seq=1)]
    disk = {"ST-5": {"item_id": "ST-5", "status": "in_review", "pr_state": "open"}}
    flags = items.merged_but_open(events, disk)
    assert [f["kind"] for f in flags] == ["disk_open_after_ship"]


def test_g9_is_silent_when_the_bookkeeping_kept_up():
    events = [ev(event="item_shipped", item_id="ST-5", pr=1654, seq=1)]
    disk = {"ST-5": {"item_id": "ST-5", "status": "shipped"}}
    assert items.merged_but_open(events, disk) == []


# --------------------------------------------------------- schema + append

def test_ledger_schema_check_finds_gaps_duplicates_and_bad_lines(repo):
    shard = repo / ".wall" / "events" / "2026-09-19" / "s_a.jsonl"
    rows = [
        {"schema_version": 1, "event_id": "a", "seq": 1, "ts": "t", "session_id": "s_a",
         "event": "run_start"},
        {"schema_version": 1, "event_id": "b", "seq": 3, "ts": "t", "session_id": "s_a",
         "event": "run_end"},
        {"schema_version": 1, "event_id": "c", "seq": 3, "ts": "t", "session_id": "s_a",
         "event": "run_end"},
        {"schema_version": 1, "event_id": "a", "seq": 4, "ts": "t", "session_id": "s_a",
         "event": "run_end"},
        {"seq": 5, "ts": "t", "session_id": "s_a", "event": "run_end"},
    ]
    shard.write_text("".join(json.dumps(r) + "\n" for r in rows) + "{ nope\n",
                     encoding="utf-8")
    kinds = [p["kind"] for p in items.ledger_schema_check(repo / ".wall" / "events")]
    assert kinds.count("seq_gap") == 1            # seq 2 is missing
    assert kinds.count("seq_duplicate") == 1      # two records on seq 3
    assert kinds.count("duplicate_event_id") == 1
    assert kinds.count("missing_field") == 1      # the row with no event_id
    assert kinds.count("unparseable_line") == 1


def test_ledger_schema_check_leaves_a_trailing_partial_line_alone(repo):
    shard = repo / ".wall" / "events" / "2026-09-19" / "s_a.jsonl"
    good = {"schema_version": 1, "event_id": "a", "seq": 1, "ts": "t",
            "session_id": "s_a", "event": "run_start"}
    shard.write_text(json.dumps(good) + "\n" + '{"event_id": "b", "se',
                     encoding="utf-8")
    assert items.ledger_schema_check(repo / ".wall" / "events") == []


def test_append_event_continues_the_session_sequence(repo, write_shard):
    write_shard("s_a", [{"event": "run_start"}, {"event": "run_end"}])
    record = items.append_event(repo, "s_a", {"event": "human_answered"})
    assert record["seq"] == 3
    assert record["event_id"]
    lines = (repo / ".wall" / "events" / record["ts"][:10] / "s_a.jsonl") \
        .read_text().strip().split("\n")
    assert json.loads(lines[-1])["event"] == "human_answered"


def test_append_event_starts_a_new_session_at_one(repo):
    assert items.append_event(repo, "s_new", {"event": "run_start"})["seq"] == 1
