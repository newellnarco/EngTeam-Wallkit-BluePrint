"""The oversight folds (DEC-0026): RETRO / POSTURE / DOCS.

Fold behaviour proven on real event lists (empty, well-formed, malformed,
last-write-wins), the sha-carrying review loop proven both ways (ack at the
current sha -> current; file edited after the ack -> changed-since-review),
and the template/schema registration pinned.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KIT / "tools" / "wall"))

spec = importlib.util.spec_from_file_location(
    "oversight", KIT / "tools" / "wall" / "oversight.py")
oversight = importlib.util.module_from_spec(spec)
spec.loader.exec_module(oversight)

TEMPLATE = (KIT / "tools" / "wall" / "render" / "wall_template.html").read_text(
    encoding="utf-8")
SCHEMA = (KIT / "docs" / "EVENT_SCHEMA.md").read_text(encoding="utf-8")


def _ruling(subject, verdict, gate="architecture", **kw):
    e = {"event": "warden_ruling", "gate": gate, "subject": subject,
         "verdict": verdict, "ts": kw.pop("ts", "2026-09-21T18:00:00.000Z")}
    e.update(kw)
    return e


# ------------------------------------------------------------------ posture

def test_posture_empty_is_honest():
    p = oversight.fold_posture([])
    assert p["total_rulings"] == 0
    assert p["rulings"] == [] and p["blocked"] == [] and p["tally"] == {}
    assert p["last_delivery_audit"] is None


def test_posture_latest_ruling_per_subject_wins():
    events = [
        _ruling("ARC-1", "blocked", ts="2026-09-21T18:00:00.000Z"),
        _ruling("ARC-1", "approved", ts="2026-09-21T18:05:00.000Z"),
        _ruling("fixtures", "refused", gate="data_use"),
    ]
    p = oversight.fold_posture(events)
    assert p["tally"] == {"approved": 1, "refused": 1}
    assert [b["subject"] for b in p["blocked"]] == ["fixtures"]


def test_posture_refused_and_blocked_both_park_work():
    p = oversight.fold_posture([_ruling("a", "blocked"),
                                _ruling("b", "refused", gate="data_use")])
    assert {b["verdict"] for b in p["blocked"]} == {"blocked", "refused"}


def test_posture_malformed_ruling_counted_never_dropped_silently():
    p = oversight.fold_posture([
        {"event": "warden_ruling", "gate": "architecture"},  # no subject/verdict
        _ruling("ok", "approved"),
    ])
    assert p["malformed"] == 1 and p["total_rulings"] == 2
    assert len(p["rulings"]) == 1


def test_posture_delivery_audit_surfaces():
    p = oversight.fold_posture(
        [_ruling("wave-7 close", "clean", gate="delivery_audit")])
    assert p["last_delivery_audit"]["subject"] == "wave-7 close"


def test_posture_non_dict_and_foreign_events_ignored():
    p = oversight.fold_posture([None, "x", {"event": "run_start"}])
    assert p["total_rulings"] == 0


# -------------------------------------------------------------------- retro

def _retro(wave, rework, **kw):
    return {"event": "retro_held", "wave": wave,
            "signals": [{"role": "builder", "name": "rework_cycles",
                         "value": rework}],
            "diffs": kw.get("diffs", []), "remeasured": kw.get("remeasured", []),
            "requeued": kw.get("requeued", 0), "ts": kw.get("ts", "")}


def test_retro_empty_is_honest():
    r = oversight.fold_retro([])
    assert r == {"held": 0, "latest": None, "trends": [],
                 "pending_inputs": [], "rebalances": []}


def test_retro_trend_series_across_waves():
    r = oversight.fold_retro([_retro("w7", 3), _retro("w8", 2)])
    assert r["held"] == 2
    assert r["latest"]["wave"] == "w8"
    assert r["trends"][0]["series"] == [3, 2]


def test_retro_non_numeric_signal_kept_in_latest_but_not_trended():
    r = oversight.fold_retro([{
        "event": "retro_held", "wave": "w9",
        "signals": [{"role": "process", "name": "note", "value": "improving"}],
    }])
    assert r["latest"]["signals"][0]["value"] == "improving"
    assert r["trends"][0]["series"] == []


def test_retro_trend_series_is_capped():
    events = [_retro(f"w{i}", i) for i in range(20)]
    r = oversight.fold_retro(events)
    assert len(r["trends"][0]["series"]) == oversight._TREND_POINTS


# --------------------------------------------------------------------- docs

def test_docs_sha_review_loop_both_ways(tmp_path):
    (tmp_path / "RULES.md").write_text("v1", encoding="utf-8")
    sha = oversight._sha12(tmp_path / "RULES.md")
    cfg = {"documents_of_record": ["RULES.md", "GONE.md"]}
    ack = {"event": "doc_reviewed", "path": "RULES.md", "sha": sha,
           "by": "the-patron", "ts": "2026-09-21T18:00:00.000Z"}

    d = oversight.fold_docs(tmp_path, [ack], cfg)
    states = {r["path"]: r["state"] for r in d["registry"]}
    assert states == {"RULES.md": "current", "GONE.md": "missing"}
    assert d["needs_review"] == 0  # missing is an adoption gap, not a review gap

    (tmp_path / "RULES.md").write_text("v2 -- edited after the ack",
                                       encoding="utf-8")
    d = oversight.fold_docs(tmp_path, [ack], cfg)
    assert {r["path"]: r["state"] for r in d["registry"]}["RULES.md"] == \
        "changed-since-review"
    assert d["needs_review"] == 1


def test_docs_never_reviewed_and_default_registry(tmp_path):
    d = oversight.fold_docs(tmp_path, [], {})
    assert len(d["registry"]) == len(oversight.DEFAULT_DOCUMENTS_OF_RECORD)
    assert all(r["state"] == "missing" for r in d["registry"])
    (tmp_path / "RULES.md").write_text("x", encoding="utf-8")
    d = oversight.fold_docs(tmp_path, [], {})
    assert {r["path"]: r["state"] for r in d["registry"]}["RULES.md"] == \
        "never-reviewed"
    assert d["needs_review"] == 1


def test_docs_ack_at_stale_sha_does_not_make_current(tmp_path):
    (tmp_path / "RULES.md").write_text("current text", encoding="utf-8")
    ack = {"event": "doc_reviewed", "path": "RULES.md",
           "sha": "not-the-real-sha", "by": "x"}
    d = oversight.fold_docs(tmp_path, [ack],
                            {"documents_of_record": ["RULES.md"]})
    assert d["registry"][0]["state"] == "changed-since-review"


def test_docs_decision_log_folded(tmp_path):
    dec = tmp_path / "docs" / "decisions"
    dec.mkdir(parents=True)
    (dec / "DEC-0001.md").write_text(
        "---\nid: DEC-0001\nstatus: active\nscope: x\n---\n\n# A ruling\n",
        encoding="utf-8")
    d = oversight.fold_docs(tmp_path, [], {"documents_of_record": ["RULES.md"]})
    assert d["decisions"]["count"] == 1
    assert d["decisions"]["recent"][0]["id"] == "DEC-0001"


# ------------------------------------------------------------- registration

def test_template_carries_the_three_tabs_and_painters():
    for needle in ("panel-retro", "panel-posture", "panel-docs",
                   "paintRetro", "paintPosture", "paintDocs",
                   "'RETRO'", "'POSTURE'", "'DOCS'"):
        assert needle in TEMPLATE, f"template missing {needle}"


def test_template_empty_states_name_their_emitters():
    assert "retro_held" in TEMPLATE
    assert "warden_ruling" in TEMPLATE
    # DOCS rows name the human-usable emitter path (the CLI verb) per row.
    assert "ack-doc" in TEMPLATE
    assert "itself a finding" in TEMPLATE  # empty POSTURE on in-scope arcs


def test_schema_documents_the_three_events():
    for ev in ("`warden_ruling`", "`retro_held`", "`doc_reviewed`"):
        assert ev in SCHEMA, f"EVENT_SCHEMA missing {ev}"
    assert "an ack at a stale sha does not make a changed document current" in \
        SCHEMA.lower().replace("\n", " ") or "stale sha" in SCHEMA


def test_courier_snapshot_carries_oversight():
    courier_src = (KIT / "tools" / "wall" / "courier.py").read_text(
        encoding="utf-8")
    assert "import oversight as oversight_mod" in courier_src
    assert '"oversight": oversight_mod.build_oversight' in courier_src


def test_charter_and_decision_registered():
    assert (KIT / "docs" / "WALL_DASHBOARDS.md").exists()
    readme = (KIT / "README.md").read_text(encoding="utf-8")
    assert "`WALL_DASHBOARDS.md`" in readme
    idx = (KIT / "docs" / "decisions" / "index.md").read_text(encoding="utf-8")
    assert "DEC-0026" in idx


def test_wall_cli_registers_ack_doc():
    wall_src = (KIT / "tools" / "wall" / "wall.py").read_text(encoding="utf-8")
    assert 'sub.add_parser("ack-doc"' in wall_src
    assert "def cmd_ack_doc" in wall_src
    assert "refusing" in wall_src  # the missing-file refusal path


def test_ack_doc_refuses_missing_file(tmp_path):
    import subprocess
    (tmp_path / ".wall" / "events").mkdir(parents=True)
    (tmp_path / ".wall" / "config").mkdir(parents=True)
    (tmp_path / ".wall" / "config" / "wall.json").write_text("{}",
                                                            encoding="utf-8")
    r = subprocess.run(
        [sys.executable, str(KIT / "tools" / "wall" / "wall.py"),
         "--repo", str(tmp_path), "ack-doc", "MISSING.md"],
        capture_output=True, text=True)
    assert r.returncode == 1
    assert "refusing" in r.stderr


def test_ack_doc_writes_the_event_with_the_current_sha(tmp_path):
    import json
    import subprocess
    (tmp_path / ".wall" / "events").mkdir(parents=True)
    (tmp_path / ".wall" / "config").mkdir(parents=True)
    (tmp_path / ".wall" / "config" / "wall.json").write_text("{}",
                                                            encoding="utf-8")
    (tmp_path / "RULES.md").write_text("the rules", encoding="utf-8")
    r = subprocess.run(
        [sys.executable, str(KIT / "tools" / "wall" / "wall.py"),
         "--repo", str(tmp_path), "ack-doc", "RULES.md", "--by", "the-patron"],
        capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    shards = list((tmp_path / ".wall" / "events").rglob("s_human*.jsonl"))
    assert shards, "no s_human shard written"
    rec = json.loads(
        shards[0].read_text(encoding="utf-8").strip().splitlines()[-1])
    assert rec["event"] == "doc_reviewed"
    assert rec["path"] == "RULES.md" and rec["by"] == "the-patron"
    assert rec["sha"] == oversight._sha12(tmp_path / "RULES.md")


# ---------------------------------------------- DEC-0027: feedback / inputs

def test_feedback_outranks_and_only_newer_ack_clears(tmp_path):
    (tmp_path / "RULES.md").write_text("v1", encoding="utf-8")
    sha = oversight._sha12(tmp_path / "RULES.md")
    cfg = {"documents_of_record": ["RULES.md"]}
    ack = {"event": "doc_reviewed", "path": "RULES.md", "sha": sha, "by": "p"}
    fb = {"event": "doc_feedback", "path": "RULES.md", "sha": sha, "by": "p",
          "text": "remap section 3"}

    # feedback after an ack: feedback-open wins, counted as needs_review
    d = oversight.fold_docs(tmp_path, [ack, fb], cfg)
    assert d["registry"][0]["state"] == "feedback-open"
    assert d["registry"][0]["feedback"]["text"] == "remap section 3"
    assert d["needs_review"] == 1

    # a NEWER ack clears it
    d = oversight.fold_docs(tmp_path, [ack, fb, dict(ack)], cfg)
    assert d["registry"][0]["state"] == "current"
    assert d["registry"][0]["feedback"] is None


def test_pending_retro_inputs_until_consumed():
    note = {"event": "retro_input", "by": "the-patron", "text": "add a check"}
    r = oversight.fold_retro([note])
    assert [i["text"] for i in r["pending_inputs"]] == ["add a check"]
    # a retro AFTER the note consumes it
    r = oversight.fold_retro([note, _retro("w1", 1)])
    assert r["pending_inputs"] == []
    # a note AFTER the retro pends again
    r = oversight.fold_retro([_retro("w1", 1), note])
    assert [i["text"] for i in r["pending_inputs"]] == ["add a check"]


def test_empty_retro_input_text_is_not_a_note():
    r = oversight.fold_retro([{"event": "retro_input", "by": "x", "text": ""}])
    assert r["pending_inputs"] == []


# --------------------------------------------------------- DEC-0027: flow

def _flow_events():
    return [
        {"event": "item_created", "item_id": "ST-1", "kind": "story"},
        {"event": "item_state", "item_id": "ST-1", "estimate": "M"},
        {"event": "item_state", "item_id": "ST-1", "actual": "L",
         "status": "done"},
        {"event": "item_shipped", "item_id": "ST-1", "pr": 1},
        {"event": "item_created", "item_id": "BG-1", "kind": "bug"},
        {"event": "retro_held", "wave": "w1", "ts": "2026-09-21T18:00:00Z"},
        {"event": "item_created", "item_id": "ST-2", "kind": "story"},
        {"event": "item_shipped", "item_id": "ST-2", "pr": 2},
    ]


def test_flow_empty_is_honest():
    f = oversight.fold_flow([])
    assert f["measured"] is False and f["open_now"] == 0


def test_flow_iteration_velocity_sizing_bugs_burndown():
    f = oversight.fold_flow(_flow_events())
    w1 = [i for i in f["iterations"] if i["iteration"] == "w1"][0]
    assert w1["shipped"] == 1
    assert w1["estimate_points"] == 3 and w1["actual_points"] == 5
    assert w1["bugs_filed"] == 1
    assert w1["open_at_close"] == 1  # BG-1 still open at the retro
    cur = [i for i in f["iterations"] if i["current"]][0]
    assert cur["shipped"] == 1
    assert cur["estimate_points"] is None  # ST-2 unsized: none recorded
    assert f["open_now"] == 1
    assert f["velocity_series"] == [1]


def test_flow_unsized_items_say_none_recorded_never_zero():
    f = oversight.fold_flow([
        {"event": "item_created", "item_id": "A", "kind": "story"},
        {"event": "item_shipped", "item_id": "A", "pr": 3},
    ])
    cur = f["iterations"][-1]
    assert cur["shipped"] == 1
    assert cur["estimate_points"] is None and cur["actual_points"] is None


def test_flow_actual_read_from_item_state_per_schema_s8():
    # actual lands on item_state at close (EVENT_SCHEMA section 8), not on
    # item_shipped; the fold must pick it up from there.
    f = oversight.fold_flow([
        {"event": "item_created", "item_id": "A", "kind": "story"},
        {"event": "item_state", "item_id": "A", "estimate": "S"},
        {"event": "item_state", "item_id": "A", "actual": "M"},
        {"event": "item_shipped", "item_id": "A", "pr": 4},
    ])
    cur = f["iterations"][-1]
    assert cur["estimate_points"] == 2 and cur["actual_points"] == 3


def test_flow_field_after_status_spelling_counts_for_burndown():
    f = oversight.fold_flow([
        {"event": "item_created", "item_id": "A", "kind": "story"},
        {"event": "item_state", "item_id": "A", "field": "status",
         "after": "cancelled"},
    ])
    assert f["open_now"] == 0  # the two-spellings rule honoured


# ------------------------------------------------- DEC-0027: registration

def test_wall_cli_registers_feedback_and_retro_note():
    wall_src = (KIT / "tools" / "wall" / "wall.py").read_text(encoding="utf-8")
    assert '"--feedback"' in wall_src
    assert 'sub.add_parser("retro-note"' in wall_src
    assert "def cmd_retro_note" in wall_src


def test_template_carries_flow_tab_and_new_states():
    for needle in ("panel-flow", "paintFlow", "'FLOW'", "feedback-open",
                   "Patron inputs"):
        assert needle in TEMPLATE, f"template missing {needle}"


def test_schema_documents_feedback_input_and_flow():
    for s in ("`doc_feedback`", "`retro_input`"):
        assert s in SCHEMA
    assert "The FLOW tab (DEC-0027) adds **no** events" in SCHEMA


def test_adopt_skill_carries_the_context_hunt():
    adopt = (KIT / ".claude" / "skills" / "adopt" / "SKILL.md").read_text(
        encoding="utf-8")
    assert "The context hunt (DEC-0027)" in adopt
    for fn in ("Requirements", "Design / architecture", "Technology / stack",
               "Data", "Integration", "Environments", "Security", "Testing",
               "SOPs / runbooks", "Diagrams"):
        assert fn in adopt, f"context function missing: {fn}"
    flat = " ".join(adopt.split())
    assert "author it" in flat
    assert "never invented facts" in flat
    assert "context markers" in flat


def test_retrospectives_bind_patron_inputs():
    retro = (KIT / "docs" / "RETROSPECTIVES.md").read_text(encoding="utf-8")
    flat = " ".join(retro.split())
    assert "retro-note" in flat
    assert "must address every pending input in its record" in flat
    assert "Silence is not one of the three" in flat


def test_oversight_loads_standalone_with_a_clean_sys_path():
    """A host's integrity suite loads vendored modules by explicit path with
    no kit dirs on sys.path; the sibling imports must self-resolve (the
    mcp_server shim, mirrored). Run in a clean interpreter so this file's
    own sys.path insert cannot mask an order dependence."""
    import subprocess
    code = (
        "import importlib.util, pathlib;"
        f"p = pathlib.Path(r'{KIT}') / 'tools' / 'wall' / 'oversight.py';"
        "spec = importlib.util.spec_from_file_location('probe_ov', p);"
        "m = importlib.util.module_from_spec(spec);"
        "spec.loader.exec_module(m);"
        "snap = m.build_oversight(pathlib.Path('.'), [], {});"
        "assert set(snap) == {'posture','retro','docs','flow','compliance'};"
        "print('ok')"
    )
    r = subprocess.run([sys.executable, "-c", code],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "ok" in r.stdout
