"""`wall retro` and `wall rebalance` -- the two learning-loop records.

retro enforces RETROSPECTIVES.md (measured signals, at most three diffs from
the closed list, each with a horizon, every pending Patron input addressed)
before writing `retro_held`. rebalance enforces CAPACITY_REBALANCING.md
section 4 (one knob per cycle; a second reversal of a knob goes to the
Adjudicator) before writing `rebalance_applied`.

Stdlib + pytest.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

import courier
import questions
import wall


def cli(repo: Path, *args: str) -> int:
    old = sys.argv
    sys.argv = ["wall", "--repo", str(repo), *args]
    try:
        return wall.main()
    finally:
        sys.argv = old


def of(repo: Path, kind: str) -> list[dict]:
    return [e for e in wall.fresh_events(repo) if e.get("event") == kind]


SIGNAL = {"role": "builder", "name": "rework_cycles", "value": 3,
          "prior": 5, "source": "ledger"}
DIFF = {"kind": "template", "path": "docs/handoffs/dispatch-brief.md",
        "why": "contracts were thin", "owner": "maestro",
        "signal": "rework_cycles", "horizon": "next wave"}


def record(tmp: Path, **overrides) -> str:
    body = {"signals": [SIGNAL], "diffs": [DIFF], "remeasured": [], "inputs": []}
    body.update(overrides)
    path = tmp / "retro.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    return str(path)


def retro(repo: Path, tmp: Path, wave: str = "w1", **overrides) -> int:
    return cli(repo, "retro", "--wave", wave, "--file", record(tmp, **overrides))


# ----------------------------------------------------------------- retro

def test_retro_writes_retro_held_the_oversight_fold_reads(repo, tmp_path):
    assert retro(repo, tmp_path) == 0
    held = of(repo, "retro_held")
    assert len(held) == 1
    ev = held[0]
    assert ev["wave"] == "w1" and ev["signals"] == [SIGNAL] and ev["diffs"] == [DIFF]
    assert ev["inputs_addressed"] == [] and ev["requeued"] == 0
    snap = courier.run_once(repo)
    assert snap["oversight"]["retro"]["latest"]["wave"] == "w1"


@pytest.mark.parametrize("override,needle", [
    ({"diffs": [DIFF] * 4}, "at most 3"),
    ({"diffs": [dict(DIFF, kind="vibes")]}, "is not one of"),
    ({"diffs": [dict(DIFF, horizon="")]}, "no horizon"),
    ({"diffs": [dict(DIFF, owner="")]}, "no owner"),
    ({"diffs": [dict(DIFF, signal="felt_slow")]}, "no signal attached"),
    ({"signals": [dict(SIGNAL, source="self_report")]}, "come from measurements"),
    ({"signals": []}, "at least one measured signal"),
])
def test_retro_refuses_what_the_discipline_forbids(repo, tmp_path, capsys,
                                                    override, needle):
    assert retro(repo, tmp_path, **override) == 1
    assert needle in capsys.readouterr().err
    assert of(repo, "retro_held") == []


def test_no_change_watching_needs_no_path(repo, tmp_path):
    watch = {"kind": "no_change", "why": "one wave is noise", "owner": "foreman",
             "signal": "rework_cycles", "horizon": "two waves"}
    assert retro(repo, tmp_path, diffs=[watch]) == 0


def test_retro_file_problems_are_usage_errors(repo, tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("[1, 2]")
    assert cli(repo, "retro", "--wave", "w1", "--file", str(bad)) == 2
    assert cli(repo, "retro", "--wave", "w1", "--file", str(tmp_path / "none")) == 2


def test_retro_refuses_an_unaddressed_patron_input(repo, tmp_path, capsys):
    assert cli(repo, "retro-note", "--text", "reviews are slow") == 0
    note = of(repo, "retro_input")[0]
    assert retro(repo, tmp_path) == 1
    err = capsys.readouterr().err
    assert note["event_id"] in err and "silence is not one of the three" in err
    assert of(repo, "retro_held") == []


def test_retro_accepts_each_disposition_and_records_it(repo, tmp_path):
    for text in ("a", "b", "c"):
        cli(repo, "retro-note", "--text", text)
    ids = [e["event_id"] for e in of(repo, "retro_input")]
    inputs = [
        {"input": ids[0], "disposition": "adopted", "diff": DIFF["path"]},
        {"input": ids[1][:8], "disposition": "queued", "item": "ST-9"},
        {"input": ids[2], "disposition": "declined", "reason": "out of scope"},
    ]
    assert retro(repo, tmp_path, inputs=inputs) == 0
    ev = of(repo, "retro_held")[0]
    assert [r["disposition"] for r in ev["inputs_addressed"]] == \
        ["adopted", "queued", "declined"]
    assert ev["inputs_addressed"][1]["input"] == ids[1], "a prefix resolves in full"
    assert ev["requeued"] == 1
    # Consumed: the next retro is not bound to them again.
    assert retro(repo, tmp_path, wave="w2") == 0


@pytest.mark.parametrize("row", [
    {"disposition": "declined"},                     # no reason
    {"disposition": "queued"},                       # no item
    {"disposition": "adopted", "diff": "not/in/this/record.md"},
    {"disposition": "ignored", "reason": "x"},
])
def test_retro_refuses_an_input_addressed_badly(repo, tmp_path, row):
    cli(repo, "retro-note", "--text", "a")
    ref = of(repo, "retro_input")[0]["event_id"]
    assert retro(repo, tmp_path, inputs=[dict(row, input=ref)]) == 1


# ------------------------------------------------------------- rebalance

def rebalance(repo: Path, knob: str, frm: str, to: str, *extra: str) -> int:
    return cli(repo, "rebalance", "--knob", knob, "--from", frm, "--to", to,
               "--signal", "blocked_builders=2", "--signal", "idle_researchers=1",
               "--expect", "blocked time falls", "--horizon", "next wave", *extra)


def test_rebalance_writes_a_reversible_record(repo):
    assert rebalance(repo, "builders", "4", "3") == 0
    ev = of(repo, "rebalance_applied")[0]
    assert ev["knob"] == "builders" and ev["from"] == 4 and ev["to"] == 3
    assert ev["signals"] == [{"name": "blocked_builders", "value": 2},
                             {"name": "idle_researchers", "value": 1}]
    assert ev["expected_effect"] == "blocked time falls"
    assert ev["horizon"] == "next wave"
    assert ev["revert"] == {"knob": "builders", "from": 3, "to": 4}


def test_rebalance_needs_a_signal(repo):
    assert cli(repo, "rebalance", "--knob", "builders", "--from", "4", "--to", "3",
               "--expect", "x", "--horizon", "y") == 2
    assert cli(repo, "rebalance", "--knob", "builders", "--from", "4", "--to", "3",
               "--signal", "noequals", "--expect", "x", "--horizon", "y") == 2


def test_one_knob_per_cycle(repo, tmp_path, capsys):
    assert rebalance(repo, "builders", "4", "3") == 0
    capsys.readouterr()
    assert rebalance(repo, "researchers", "2", "3") == 1
    assert "one knob per cycle" in capsys.readouterr().err
    assert len(of(repo, "rebalance_applied")) == 1
    # A stated reason overrides, and is recorded.
    assert rebalance(repo, "researchers", "2", "3", "--reason", "SLA breach") == 0
    assert of(repo, "rebalance_applied")[-1]["reason"] == "SLA breach"
    # A retro closes the cycle.
    assert retro(repo, tmp_path) == 0
    assert rebalance(repo, "pr_pacing", "2", "1") == 0


def test_second_reversal_goes_to_the_adjudicator(repo, tmp_path, capsys):
    assert rebalance(repo, "builders", "4", "3") == 0
    retro(repo, tmp_path, wave="w1")
    assert rebalance(repo, "builders", "3", "4") == 0       # first reversal
    retro(repo, tmp_path, wave="w2")
    capsys.readouterr()
    assert rebalance(repo, "builders", "4", "3") == 1       # would be the second
    assert "Adjudicator" in capsys.readouterr().err
    assert len(of(repo, "rebalance_applied")) == 2
    qs = questions.fold(wall.fresh_events(repo)).questions
    routed = [q for q in qs.values() if q["ambiguity_class"] == "rebalance_oscillation"]
    assert len(routed) == 1 and routed[0]["tier"] == "adjudicator"
    # Refusing again does not file a second question.
    assert rebalance(repo, "builders", "4", "3", "--reason", "x") == 1
    qs = questions.fold(wall.fresh_events(repo)).questions
    assert len([q for q in qs.values()
                if q["ambiguity_class"] == "rebalance_oscillation"]) == 1
    # A ruling lets it through, and resets the count.
    assert rebalance(repo, "builders", "4", "3", "--adjudication", "DEC-0099") == 0
    assert of(repo, "rebalance_applied")[-1]["adjudication"] == "DEC-0099"


def test_an_oscillation_after_a_ruling_asks_the_adjudicator_again(repo, tmp_path):
    def oscillations():
        qs = questions.fold(wall.fresh_events(repo)).questions
        return sorted(q for q, v in qs.items()
                      if v["ambiguity_class"] == "rebalance_oscillation")
    # Episode one: oscillate, get routed, get a ruling.
    assert rebalance(repo, "builders", "4", "3") == 0
    retro(repo, tmp_path, wave="w1")
    assert rebalance(repo, "builders", "3", "4") == 0
    retro(repo, tmp_path, wave="w2")
    assert rebalance(repo, "builders", "4", "3") == 1
    assert len(oscillations()) == 1
    assert rebalance(repo, "builders", "4", "3", "--adjudication", "DEC-0099") == 0
    # Episode two: the same knob oscillates again after the ruling (the
    # ruling resets the count, so it takes two more reversals to re-trigger).
    retro(repo, tmp_path, wave="w3")
    assert rebalance(repo, "builders", "3", "4") == 0
    retro(repo, tmp_path, wave="w4")
    assert rebalance(repo, "builders", "4", "3") == 0
    retro(repo, tmp_path, wave="w5")
    assert rebalance(repo, "builders", "3", "4") == 1
    assert len(oscillations()) == 2, "a new episode is a new question"


def test_a_new_value_is_not_a_reversal(repo, tmp_path):
    rebalance(repo, "builders", "4", "3")
    retro(repo, tmp_path, wave="w1")
    rebalance(repo, "builders", "3", "4")
    retro(repo, tmp_path, wave="w2")
    assert rebalance(repo, "builders", "4", "5") == 0


def test_summary_reports_the_latest_rebalance(repo, capsys):
    rebalance(repo, "builders", "4", "3")
    courier.run_once(repo)
    capsys.readouterr()
    assert cli(repo, "summary") == 0
    assert "latest rebalance: builders 4 -> 3" in capsys.readouterr().out
    assert cli(repo, "summary", "--json") == 0
    out = json.loads(capsys.readouterr().out)
    assert out["latest_rebalance"]["knob"] == "builders"


def test_summary_says_none_when_no_rebalance(repo, capsys):
    courier.run_once(repo)
    capsys.readouterr()
    cli(repo, "summary")
    assert "latest rebalance: none recorded" in capsys.readouterr().out
