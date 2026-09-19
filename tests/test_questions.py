"""The question lifecycle and the five escalation invariants."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import questions

NOW = datetime(2026, 9, 19, 15, 0, tzinfo=timezone.utc)


def at(minutes_ago: float) -> str:
    return (NOW - timedelta(minutes=minutes_ago)).isoformat(
        timespec="milliseconds").replace("+00:00", "Z")


def ev(seq, **kw):
    base = {"schema_version": 1, "event_id": f"e{seq}", "seq": seq,
            "ts": kw.pop("ts", at(0)), "session_id": kw.pop("session_id", "s_a")}
    base.update(kw)
    return base


def raised(minutes_ago=30, qid="q_1", item="ST-1", **kw):
    kw.setdefault("ts", at(minutes_ago))
    return ev(1, event="question_raised", question_id=qid, item_id=item,
              agent_key="bld_1", agent_name="Desmond",
              role="builder", question="which is it?",
              ambiguity_class="unclear_acceptance", **kw)


# ------------------------------------------------------------------- fold

def test_fold_walks_the_whole_lifecycle():
    events = [
        raised(60),
        ev(2, event="question_assigned", question_id="q_1", item_id="ST-1",
           assignee="Silas", assignee_key="res_1", ts=at(58)),
        ev(3, event="run_start", question_id="q_1", run_id="r1", role="researcher",
           agent_key="res_1", item_id="ST-1", ts=at(55)),
        ev(4, event="question_escalated", question_id="q_1", tier="architect",
           reason="no ruling found", ts=at(30)),
        ev(5, event="question_answered", question_id="q_1", source="architect",
           answer="per shard", ts=at(10)),
    ]
    q = questions.fold(events).questions["q_1"]
    assert q["status"] == "answered"
    assert q["assigned_to"] == "Silas"
    assert q["first_run_at"] == at(55)
    assert [h["tier"] for h in q["escalations"]] == ["architect"]
    assert q["tier"] == "architect"
    assert q["answer_source"] == "architect"
    assert not questions.is_open(q)


def test_escalation_moves_the_tier_without_closing_the_question():
    q = questions.fold([
        raised(60),
        ev(2, event="question_escalated", question_id="q_1", tier="human",
           reason="stuck", ts=at(5)),
    ]).questions["q_1"]
    assert questions.is_open(q) and q["tier"] == "human"


def test_human_required_and_answered_join_on_ask_id():
    folded = questions.fold([
        ev(1, event="human_required", ask_id="ask_7", item_id="BG-1",
           question="which?", ts=at(20)),
        ev(2, event="human_answered", ask_id="ask_7", answer="this one", ts=at(2)),
    ]).questions
    q = questions.resolve(folded, "ask_7")
    assert q["status"] == "answered" and q["answer"] == "this one"
    assert q["answer_source"] == "human"


def test_a_question_event_with_no_id_is_a_named_problem():
    result = questions.fold([ev(1, event="question_raised", item_id="ST-1")])
    assert [p["kind"] for p in result.problems] == ["question_event_without_id"]
    assert result.questions == {}


def test_fold_tolerates_non_objects():
    result = questions.fold(["nope", None, raised(5)])
    assert len(result.questions) == 1
    assert result.problems[0]["kind"] == "malformed_event"


def test_a_researcher_run_on_the_item_counts_as_the_first_run():
    # The run carries no question_id, which is the common case: the hook
    # writes run_start, the dispatcher knows the question.
    q = questions.fold([
        raised(60),
        ev(2, event="question_assigned", question_id="q_1", item_id="ST-1",
           assignee="Silas", ts=at(58)),
        ev(3, event="run_start", role="researcher", agent_key="res_1",
           item_id="ST-1", run_id="r1", ts=at(50)),
    ]).questions["q_1"]
    assert q["first_run_at"] == at(50)


# ------------------------------------------------------- the invariants

def flags(events, items=None, agents=None, sla=None):
    folded = questions.fold(events).questions
    return questions.escalation_flags(folded, items or {}, agents,
                                      sla or {}, now=NOW)


def test_blocked_without_an_open_question():
    kinds = [f["kind"] for f in flags([], {"BG-1": {"status": "blocked"}})]
    assert kinds == ["blocked_without_question"]


def test_a_blocked_item_with_an_open_question_is_not_flagged():
    got = flags([raised(3, item="BG-1")], {"BG-1": {"status": "blocked"}})
    assert [f["kind"] for f in got] == []


def test_an_answered_question_no_longer_covers_a_blocked_item():
    got = flags([raised(30, item="BG-1"),
                 ev(2, event="question_answered", question_id="q_1",
                    source="researcher", ts=at(5))],
                {"BG-1": {"status": "blocked"}})
    assert [f["kind"] for f in got] == ["blocked_without_question"]


def test_unassigned_past_sla():
    got = flags([raised(30)], sla={"question_assigned": 5,
                                   "question_open_escalate": 600})
    assert [f["kind"] for f in got] == ["unassigned_past_sla"]
    assert got[0]["age_min"] == 30.0 and got[0]["sla_min"] == 5


def test_unassigned_inside_the_sla_is_quiet():
    assert flags([raised(2)], sla={"question_assigned": 5,
                                   "question_open_escalate": 600}) == []


def test_assigned_but_nobody_ran():
    got = flags([raised(40),
                 ev(2, event="question_assigned", question_id="q_1",
                    assignee="Silas", item_id="ST-1", ts=at(35))],
                sla={"researcher_first_run": 10, "question_open_escalate": 600})
    assert [f["kind"] for f in got] == ["assigned_no_run"]
    assert got[0]["assignee"] == "Silas"


def test_open_past_the_threshold_asks_for_a_tier():
    got = flags([raised(200),
                 ev(2, event="question_assigned", question_id="q_1",
                    assignee="Silas", ts=at(199)),
                 ev(3, event="run_start", question_id="q_1", run_id="r1",
                    role="researcher", ts=at(198))],
                sla={"question_open_escalate": 60})
    assert [f["kind"] for f in got] == ["escalate"]


def test_a_question_already_at_the_human_tier_is_not_escalated_again():
    got = flags([ev(1, event="human_required", ask_id="ask_1", item_id="ST-1",
                    question="?", ts=at(500))],
                sla={"question_open_escalate": 60})
    assert [f["kind"] for f in got] == []


def test_capacity_wasted_when_a_builder_is_blocked_and_a_researcher_idles():
    got = flags([raised(2, item="BG-1")],
                items={"BG-1": {"status": "blocked"}},
                agents=[{"role": "researcher", "status": "idle", "name": "Silas"},
                        {"role": "builder", "status": "working", "name": "Theo"}])
    assert [f["kind"] for f in got] == ["capacity_wasted"]
    assert "Silas" in got[0]["detail"]


def test_no_capacity_flag_when_every_researcher_is_busy():
    got = flags([raised(2, item="BG-1")],
                items={"BG-1": {"status": "blocked"}},
                agents=[{"role": "researcher", "status": "working", "name": "Silas"}])
    assert [f["kind"] for f in got] == []


def test_an_unparseable_timestamp_never_invents_an_age():
    got = flags([raised(5, ts="not-a-timestamp")])
    assert got == []


# ----------------------------------------------------------------- answer

def test_answer_appends_human_answered_and_closes_the_ask(repo, write_shard):
    write_shard("s_a", [{"event": "human_required", "ask_id": "ask_7",
                         "item_id": "BG-1", "question": "which?",
                         "trace_id": "tr_bg1"}])
    events = items_events(repo)
    result = questions.answer(repo, "ask_7", "this one", events=events)
    assert result["record"]["event"] == "human_answered"
    assert result["record"]["trace_id"] == "tr_bg1"

    folded = questions.fold(items_events(repo)).questions
    assert folded["ask_7"]["status"] == "answered"


def test_answer_refuses_an_unknown_ask(repo):
    import pytest
    with pytest.raises(LookupError):
        questions.answer(repo, "ask_nope", "x", events=[])


def items_events(repo):
    import items
    return items.load_events(repo)
