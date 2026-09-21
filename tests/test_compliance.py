"""The compliance register (DEC-0028): registry↔doc sync, the selection +
challenge fold, the attestation rules, and the FLOW drill-in enrichment."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KIT / "tools" / "wall"))


def _load(name):
    spec = importlib.util.spec_from_file_location(
        name, KIT / "tools" / "wall" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


compliance = _load("compliance")
oversight = _load("oversight")

TEMPLATE = (KIT / "tools" / "wall" / "render" / "wall_template.html").read_text(
    encoding="utf-8")


# ------------------------------------------------------- registry <-> docs

def test_every_regime_has_its_blueprint_with_every_control_id():
    for r in compliance.REGIMES:
        doc = KIT / r["doc"]
        assert doc.is_file(), f"{r['id']}: blueprint missing at {r['doc']}"
        text = doc.read_text(encoding="utf-8")
        for cid, _ in r["controls"]:
            assert f"| {cid} |" in text, \
                f"{r['id']}: control {cid} absent from {r['doc']}"
        assert "Sources:" in text, f"{r['id']}: blueprint cites no sources"
        assert f"wall attest {r['id']}" in text, \
            f"{r['id']}: blueprint does not name its attest verb"


def test_registry_shape_and_the_named_regimes():
    assert set(compliance.REGIME_IDS) == {
        "soc2", "hipaa", "pci", "privacy", "government", "sector"}
    assert compliance.ATTEST_STATUSES == ("pass", "fail", "waiver")
    # PCI carries exactly the 12 requirements of v4.0.1
    assert compliance.control_ids("pci") == tuple(
        f"R{i}" for i in range(1, 13))
    assert compliance.regime("nope") is None
    assert compliance.control_ids("nope") == ()


# ------------------------------------------------------------ fold: select

def _sel(regime, applicable, reason="because", by="the-patron"):
    return {"event": "compliance_selected", "regime": regime,
            "applicable": applicable, "reason": reason, "by": by}


def _att(regime, control, status, note=""):
    return {"event": "compliance_attested", "regime": regime,
            "control": control, "status": status, "note": note, "by": "p"}


def test_unanswered_regime_is_asked_not_assumed():
    c = oversight.fold_compliance([])
    assert c["any_selected"] is False
    for r in c["regimes"]:
        assert r["applicable"] is None
        assert "unanswered" in r["challenge"]


def test_last_selection_wins_and_log_keeps_history():
    c = oversight.fold_compliance([_sel("pci", True), _sel("pci", False)])
    pci = [r for r in c["regimes"] if r["id"] == "pci"][0]
    assert pci["applicable"] is False
    assert len(c["decision_log"]) == 2  # the log is history, not state


def test_challenge_selected_with_no_surface():
    c = oversight.fold_compliance([_sel("soc2", True)])
    soc2 = [r for r in c["regimes"] if r["id"] == "soc2"][0]
    assert "no observed surface" in soc2["challenge"]
    # attesting anything clears that challenge
    c = oversight.fold_compliance([_sel("soc2", True),
                                   _att("soc2", "CC1", "pass")])
    soc2 = [r for r in c["regimes"] if r["id"] == "soc2"][0]
    assert soc2["challenge"] is None


def test_challenge_not_applicable_but_rulings_cite_it():
    ruling = {"event": "warden_ruling", "gate": "data_use",
              "subject": "prod PHI extract in fixtures", "verdict": "refused",
              "obligation": "HIPAA minimum necessary"}
    c = oversight.fold_compliance([_sel("hipaa", False), ruling])
    hipaa = [r for r in c["regimes"] if r["id"] == "hipaa"][0]
    assert hipaa["applicable"] is False  # never auto-flipped
    assert "revisit the selection" in hipaa["challenge"]


def test_unselected_but_cited_is_the_loudest_ask():
    ruling = {"event": "warden_ruling", "gate": "architecture",
              "subject": "cardholder flow", "verdict": "approved",
              "obligation": "PCI scope containment"}
    c = oversight.fold_compliance([ruling])
    pci = [r for r in c["regimes"] if r["id"] == "pci"][0]
    assert "UNSELECTED but Warden rulings cite it" in pci["challenge"]


def test_attestation_counts_and_last_write_wins():
    c = oversight.fold_compliance([
        _sel("privacy", True),
        _att("privacy", "VND", "fail"),
        _att("privacy", "VND", "pass", "DPA signed"),
        _att("privacy", "BRK", "waiver", "no EU customers yet"),
    ])
    pv = [r for r in c["regimes"] if r["id"] == "privacy"][0]
    assert pv["counts"] == {"pass": 1, "fail": 0, "waiver": 1,
                            "unattested": len(pv["controls"]) - 2}
    vnd = [ct for ct in pv["controls"] if ct["id"] == "VND"][0]
    assert vnd["status"] == "pass" and vnd["note"] == "DPA signed"


# ------------------------------------------------------------- CLI guards

def _wall(tmp_path, *args):
    (tmp_path / ".wall" / "events").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".wall" / "config").mkdir(parents=True, exist_ok=True)
    cfg = tmp_path / ".wall" / "config" / "wall.json"
    if not cfg.exists():
        cfg.write_text("{}", encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(KIT / "tools" / "wall" / "wall.py"),
         "--repo", str(tmp_path), *args], capture_output=True, text=True)


def test_cli_selection_requires_a_reason(tmp_path):
    r = _wall(tmp_path, "compliance", "soc2", "--applicable")
    assert r.returncode == 2 and "reason IS the decision" in r.stderr


def test_cli_waiver_requires_its_note(tmp_path):
    r = _wall(tmp_path, "attest", "pci", "R3", "--status", "waiver")
    assert r.returncode == 2 and "recorded" in r.stderr


def test_cli_unknown_regime_and_control_refused(tmp_path):
    assert _wall(tmp_path, "compliance", "nope", "--applicable",
                 "--reason", "x").returncode == 1
    assert _wall(tmp_path, "attest", "pci", "R99",
                 "--status", "pass").returncode == 1


def test_cli_happy_path_writes_both_events(tmp_path):
    r = _wall(tmp_path, "compliance", "pci", "--not-applicable",
              "--reason", "no cardholder data", "--by", "the-patron")
    assert r.returncode == 0, r.stderr
    r = _wall(tmp_path, "attest", "soc2", "CC8", "--status", "pass",
              "--by", "the-patron")
    assert r.returncode == 0, r.stderr
    shards = list((tmp_path / ".wall" / "events").rglob("s_human*.jsonl"))
    lines = [json.loads(x) for s in shards
             for x in s.read_text(encoding="utf-8").strip().splitlines()]
    events = {e["event"] for e in lines}
    assert {"compliance_selected", "compliance_attested"} <= events


# ------------------------------------------------------- FLOW drill-in

def test_flow_drill_in_cost_agents_duration_delivered_and_not():
    events = [
        {"event": "item_created", "item_id": "ST-1", "kind": "story",
         "title": "ship the thing", "ts": "2026-09-21T10:00:00Z",
         "agent_key": "bld_1", "role": "builder"},
        {"event": "item_created", "item_id": "ST-2", "kind": "story",
         "title": "the one that slipped", "ts": "2026-09-21T10:05:00Z",
         "agent_key": "arc_1", "role": "architect"},
        {"event": "run_end", "item_id": "ST-1", "cost_usd": 1.25,
         "ts": "2026-09-21T10:30:00Z", "agent_key": "bld_1",
         "role": "builder"},
        {"event": "item_shipped", "item_id": "ST-1", "pr": 7,
         "ts": "2026-09-21T11:00:00Z", "agent_key": "bld_1",
         "role": "builder"},
        {"event": "retro_held", "wave": "w1", "ts": "2026-09-21T12:00:00Z"},
    ]
    f = oversight.fold_flow(events)
    w1 = [i for i in f["iterations"] if i["iteration"] == "w1"][0]
    assert w1["cost_usd"] == 1.25
    assert w1["agents"] == {"architect": 1, "builder": 1}
    assert w1["duration_min"] == 120.0
    assert w1["delivered"] == [{"item_id": "ST-1", "title": "ship the thing",
                                "kind": "story"}]
    assert w1["not_delivered"] == [{"item_id": "ST-2",
                                    "title": "the one that slipped",
                                    "kind": "story"}]


def test_flow_drill_in_absent_signals_say_none_recorded():
    f = oversight.fold_flow([
        {"event": "item_created", "item_id": "A", "kind": "story"},
        {"event": "item_shipped", "item_id": "A", "pr": 1},
    ])
    cur = f["iterations"][-1]
    assert cur["cost_usd"] is None
    assert cur["duration_min"] is None
    assert cur["agents"] == {}


# ----------------------------------------------------------- registration

def test_template_carries_the_two_popouts():
    for needle in ("openRegimeAudit", "openIteration", "data-regime",
                   "data-iteration", "modalBody", "open audit",
                   "Worked but NOT delivered"):
        assert needle in TEMPLATE, f"template missing {needle}"


def test_schema_and_charter_registered():
    schema = (KIT / "docs" / "EVENT_SCHEMA.md").read_text(encoding="utf-8")
    assert "`compliance_selected`" in schema
    assert "`compliance_attested`" in schema
    charter = (KIT / "docs" / "WALL_DASHBOARDS.md").read_text(encoding="utf-8")
    assert "The compliance loop (DEC-0028)" in charter
    warden = (KIT / ".claude" / "agents" / "warden.md").read_text(
        encoding="utf-8")
    flat = " ".join(warden.split())
    assert "The compliance register is yours to keep honest, every phase" in flat
    assert "never a silent re-selection" in flat
