"""`wall trace` and `wall why`: selection, ordering, and what they report."""

from __future__ import annotations

import argparse

import items
import wall


def ev(seq, **kw):
    base = {"schema_version": 1, "event_id": f"e{seq}", "seq": seq,
            "ts": kw.pop("ts", f"2026-09-19T12:{seq:02d}:00.000Z"),
            "session_id": kw.pop("session_id", "s_a")}
    base.update(kw)
    return base


JOURNEY = [
    ev(1, event="item_created", item_id="ST-1", title="Merge", trace_id="tr_1"),
    ev(2, event="item_state", item_id="ST-1", status="active",
       scope=["backend/ledger/"], assignee="Desmond"),
    ev(3, event="run_start", item_id="ST-1", trace_id="tr_1", run_id="r_bld",
       agent_key="bld_1", agent_name="Desmond", role="builder",
       decisions_in_context=["DEC-0001"]),
    ev(4, event="question_raised", item_id="ST-1", trace_id="tr_1",
       question_id="q_1", agent_key="bld_1", agent_name="Desmond", role="builder"),
    # A different session, a child run: this is the hop a trace exists to show.
    ev(1, session_id="s_b", ts="2026-09-19T12:05:00.000Z", event="run_start",
       item_id="ST-1", trace_id="tr_1", run_id="r_res", parent_run_id="r_bld",
       agent_key="res_1", agent_name="Silas", role="researcher"),
    ev(2, session_id="s_b", ts="2026-09-19T12:06:00.000Z", event="run_end",
       item_id="ST-1", trace_id="tr_1", run_id="r_res", outcome="pass",
       agent_key="res_1", agent_name="Silas", role="researcher",
       decisions_in_context=["DEC-0002"]),
    ev(5, event="question_escalated", item_id="ST-1", trace_id="tr_1",
       question_id="q_1", tier="architect", reason="no ruling"),
]


def args(**kw):
    kw.setdefault("repo", ".")
    return argparse.Namespace(**kw)


# ---------------------------------------------------------------- selection

def test_selects_by_item_id_and_by_trace_id():
    by_item, trace_id = wall.select_trace(JOURNEY, "ST-1")
    by_trace, _ = wall.select_trace(JOURNEY, "tr_1")
    assert trace_id == "tr_1"
    assert len(by_item) == len(JOURNEY)
    # item_state here carries no trace_id, so the trace lookup is one short --
    # and that is honest: it was never stamped.
    assert len(by_trace) == len(JOURNEY) - 1


def test_ordering_is_the_total_order_across_sessions():
    selected, _ = wall.select_trace(JOURNEY, "ST-1")
    stamps = [(e["ts"], e["session_id"], e["seq"]) for e in selected]
    assert stamps == sorted(stamps)
    assert [e["session_id"] for e in selected].count("s_b") == 2


def test_a_terminal_record_missing_its_trace_id_is_still_pulled_in():
    events = JOURNEY + [ev(6, event="run_end", run_id="r_bld", outcome="pass",
                           agent_key="bld_1", agent_name="Desmond", role="builder",
                           ts="2026-09-19T12:09:00.000Z")]
    selected, _ = wall.select_trace(events, "tr_1")
    assert any(e.get("run_id") == "r_bld" and e["event"] == "run_end"
               for e in selected), "a run_end that lost its trace_id must not vanish"


def test_an_unknown_target_selects_nothing():
    selected, trace_id = wall.select_trace(JOURNEY, "ST-999")
    assert selected == [] and trace_id is None


# ------------------------------------------------------------- rendering

def render_trace(repo, events, target):
    (repo / ".wall" / "derived").mkdir(parents=True, exist_ok=True)
    import json
    (repo / ".wall" / "derived" / "ledger.jsonl").write_text(
        "".join(json.dumps(e) + "\n" for e in events), encoding="utf-8")
    return wall.cmd_trace(args(repo=str(repo), target=target))


def test_trace_prints_the_timeline_with_hops_and_durations(repo, capsys):
    assert render_trace(repo, JOURNEY, "ST-1") == 0
    out = capsys.readouterr().out
    assert "trace tr_1" in out
    assert "2 session(s)" in out
    assert "researcher/Silas" in out
    assert "escalation hops:" in out and "-> architect" in out
    assert "unfinished runs in this trace: r_bld" in out
    assert "1m00s" in out          # the child run's own duration


def test_trace_reports_an_unknown_item_without_a_traceback(repo, capsys):
    assert render_trace(repo, JOURNEY, "ST-404") == 1
    assert "nothing found" in capsys.readouterr().out


def test_trace_on_an_empty_repo_says_so(repo, capsys):
    assert wall.cmd_trace(args(repo=str(repo), target="ST-1")) == 1
    assert "ledger is empty" in capsys.readouterr().out


def test_trace_needs_a_target(repo, capsys):
    assert wall.cmd_trace(args(repo=str(repo), target=None)) == 2
    assert "usage" in capsys.readouterr().err


def test_trace_falls_back_to_the_shards_when_no_ledger_exists(repo, write_shard):
    write_shard("s_a", [{"event": "item_created", "item_id": "ST-1",
                         "trace_id": "tr_1", "title": "A"}])
    assert not (repo / ".wall" / "derived" / "ledger.jsonl").exists()
    assert items.load_events(repo)[0]["item_id"] == "ST-1"


# -------------------------------------------------------------------- why

def test_why_names_a_ruling_in_effect_that_no_run_carried(repo, capsys):
    (repo / "docs" / "decisions").mkdir(parents=True)
    for dec_id, scope in (("DEC-0001", "backend/ledger/"),
                          ("DEC-0003", "backend/ledger/merge.py")):
        (repo / "docs" / "decisions" / f"{dec_id}.md").write_text(
            f"---\nid: {dec_id}\nstatus: active\nscope: {scope}\n"
            f"expert: Edmund\n---\n\n# {dec_id} -- ruling\n", encoding="utf-8")
    render_trace(repo, JOURNEY, "ST-1")          # reuse: writes the ledger
    capsys.readouterr()

    assert wall.cmd_why(args(repo=str(repo), target="ST-1")) == 0
    out = capsys.readouterr().out
    assert "scope: backend/ledger/" in out
    assert "DEC-0001" in out and "carried by: r_bld(Desmond)" in out
    assert "DEC-0003" in out and "NOT carried by any run" in out


def test_why_reports_a_carried_decision_with_no_file(repo, capsys):
    render_trace(repo, JOURNEY, "ST-1")
    capsys.readouterr()
    wall.cmd_why(args(repo=str(repo), target="ST-1"))
    out = capsys.readouterr().out
    assert "carried but not in the log:" in out
    assert "DEC-0002" in out


def test_why_on_an_unknown_item_lists_what_it_knows(repo, capsys):
    render_trace(repo, JOURNEY, "ST-1")
    capsys.readouterr()
    assert wall.cmd_why(args(repo=str(repo), target="ST-404")) == 1
    assert "known items: ST-1" in capsys.readouterr().out


def test_why_reads_lease_paths_as_scope(repo, capsys):
    events = JOURNEY + [ev(7, event="lease_taken", item_id="ST-1",
                           paths=["backend/ledger/shard.py"])]
    render_trace(repo, events, "ST-1")
    capsys.readouterr()
    wall.cmd_why(args(repo=str(repo), target="ST-1"))
    assert "backend/ledger/shard.py" in capsys.readouterr().out
