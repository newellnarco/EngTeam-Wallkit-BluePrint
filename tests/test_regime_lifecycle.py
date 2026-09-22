"""DEC-0030 — the Warden's regime lifecycle: the scan recommends with
evidence, the fold names the scan-vs-selection tension as a disposition, the
dashboard dispatches enable/disable/audit through the queue port, and an
audit is complete-or-refused with proof or reason on every row.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import compliance
import oversight

KIT = Path(__file__).resolve().parent.parent
TEMPLATE = (KIT / "tools" / "wall" / "render" / "wall_template.html").read_text(
    encoding="utf-8")


# ------------------------------------------------------------------ the scan

class TestScan:
    def test_evidence_is_found_on_word_boundaries_only(self, tmp_path):
        (tmp_path / "notes.md").write_text(
            "we expand our research this year", encoding="utf-8")
        (tmp_path / "billing.py").write_text(
            "charge = stripe.Charge.create(amount)", encoding="utf-8")
        ev = compliance.scan_repo(tmp_path)
        assert not ev["government"], "'ear' fired inside 'research'/'year'"
        assert not ev["pci"] or all("stripe" in e for e in ev["pci"]), \
            "'pan' must not fire inside 'expand'"
        assert any("stripe" in e for e in ev["pci"])

    def test_compliance_docs_and_process_trees_are_not_evidence(self, tmp_path):
        for rel in ("docs/compliance/hipaa.md", ".claude/agents/warden.md",
                    "tools/wall/compliance.py", "docs/decisions/DEC-0030.md"):
            p = tmp_path / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("hipaa phi cardholder gdpr fedramp sox", encoding="utf-8")
        ev = compliance.scan_repo(tmp_path)
        assert all(not v for v in ev.values()), \
            "the blueprints naming every regime made every regime 'needed'"

    def test_every_evidence_line_names_its_file_and_signal(self, tmp_path):
        (tmp_path / "records.py").write_text(
            "def load_patient(rec): ...", encoding="utf-8")
        ev = compliance.scan_repo(tmp_path)
        assert ev["hipaa"] and "records.py" in ev["hipaa"][0] \
            and "patient" in ev["hipaa"][0]


# ------------------------------------------------------------------ the fold

def _scan_event(rows, ts="2026-09-22T10:00:00Z"):
    return {"event": "compliance_scanned", "ts": ts, "by": "warden",
            "regimes": rows}


def _sel(regime, applicable, ts="2026-09-22T11:00:00Z"):
    return {"event": "compliance_selected", "regime": regime,
            "applicable": applicable, "reason": "r", "by": "patron", "ts": ts}


def _regime(fold, rid):
    return next(r for r in fold["regimes"] if r["id"] == rid)


class TestDispositions:
    def test_disabling_a_recommended_regime_is_named_loudly(self):
        fold = oversight.fold_compliance([
            _scan_event([{"regime": "hipaa", "recommended": True,
                          "evidence": ["records.py -- matched 'patient'"]}]),
            _sel("hipaa", False),
        ])
        r = _regime(fold, "hipaa")
        assert r["disposition"] == "NOT RECOMMENDED FOR DISABLED"
        assert r["evidence"] == ["records.py -- matched 'patient'"]

    def test_recommended_but_undecided_asks_for_a_decision(self):
        fold = oversight.fold_compliance([
            _scan_event([{"regime": "pci", "recommended": True,
                          "evidence": ["billing.py -- matched 'stripe'"]}]),
        ])
        assert _regime(fold, "pci")["disposition"] == "recommended -- decide"

    def test_enabled_with_no_scan_surface_says_so_softly(self):
        fold = oversight.fold_compliance([
            _scan_event([{"regime": "soc2", "recommended": False,
                          "evidence": []}]),
            _sel("soc2", True),
        ])
        assert _regime(fold, "soc2")["disposition"] == \
            "active (scan found no surface)"

    def test_enabled_and_recommended_is_simply_active(self):
        fold = oversight.fold_compliance([
            _scan_event([{"regime": "soc2", "recommended": True,
                          "evidence": ["x -- matched 'customer data'"]}]),
            _sel("soc2", True),
        ])
        assert _regime(fold, "soc2")["disposition"] == "active"

    def test_no_scan_at_all_keeps_dec0028_behaviour(self):
        fold = oversight.fold_compliance([_sel("pci", True)])
        r = _regime(fold, "pci")
        assert r["disposition"] == "active" and r["evidence"] == []

    def test_last_audit_marker_is_folded(self):
        fold = oversight.fold_compliance([
            {"event": "compliance_audited", "regime": "pci",
             "by": "warden", "ts": "2026-09-22T12:00:00Z"},
        ])
        assert _regime(fold, "pci")["last_audit"]["by"] == "warden"


# ------------------------------------------------------------------- the CLI

def _wall(tmp_path, *args):
    (tmp_path / ".wall" / "events").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".wall" / "config").mkdir(parents=True, exist_ok=True)
    cfg = tmp_path / ".wall" / "config" / "wall.json"
    if not cfg.exists():
        cfg.write_text("{}", encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(KIT / "tools" / "wall" / "wall.py"),
         "--repo", str(tmp_path), *args], capture_output=True, text=True)


def _events(tmp_path):
    return [json.loads(x)
            for s in (tmp_path / ".wall" / "events").rglob("*.jsonl")
            for x in s.read_text(encoding="utf-8").strip().splitlines()]


class TestScanVerb:
    def test_scan_records_one_event_with_every_regime(self, tmp_path):
        (tmp_path / "billing.py").write_text("import stripe", encoding="utf-8")
        r = _wall(tmp_path, "compliance-scan")
        assert r.returncode == 0, r.stderr
        scans = [e for e in _events(tmp_path)
                 if e["event"] == "compliance_scanned"]
        assert len(scans) == 1
        rows = {row["regime"]: row for row in scans[0]["regimes"]}
        assert set(rows) == set(compliance.REGIME_IDS)
        assert rows["pci"]["recommended"] and rows["pci"]["evidence"]


class TestAuditVerb:
    def _full(self, regime, status="pass", note="verified in review"):
        return {c: {"status": status, "note": note}
                for c in compliance.control_ids(regime)}

    def test_partial_audit_is_refused_naming_the_gap(self, tmp_path):
        results = self._full("sector")
        results.pop("FER")
        f = tmp_path / "res.json"
        f.write_text(json.dumps(results), encoding="utf-8")
        r = _wall(tmp_path, "audit", "sector", "--file", str(f))
        assert r.returncode == 2 and "FER" in r.stderr

    def test_a_row_without_proof_or_reason_is_refused(self, tmp_path):
        results = self._full("sector")
        results["SOX"]["note"] = "  "
        f = tmp_path / "res.json"
        f.write_text(json.dumps(results), encoding="utf-8")
        r = _wall(tmp_path, "audit", "sector", "--file", str(f))
        assert r.returncode == 2 and "SOX" in r.stderr

    def test_complete_audit_writes_every_attestation_plus_the_marker(self, tmp_path):
        results = self._full("sector")
        results["GLB"] = {"status": "waiver",
                          "note": "no consumer financial data this quarter"}
        f = tmp_path / "res.json"
        f.write_text(json.dumps(results), encoding="utf-8")
        r = _wall(tmp_path, "audit", "sector", "--file", str(f), "--by", "warden")
        assert r.returncode == 0, r.stderr
        ev = _events(tmp_path)
        attests = [e for e in ev if e["event"] == "compliance_attested"]
        assert len(attests) == len(compliance.control_ids("sector"))
        assert all(e["note"].strip() for e in attests)
        assert any(e["event"] == "compliance_audited" and e["regime"] == "sector"
                   for e in ev)


# -------------------------------------------------------------- the template

class TestPostureSurface:
    def test_disposition_and_why_render(self):
        assert "NOT RECOMMENDED FOR DISABLED" in TEMPLATE
        assert "data-regime-why" in TEMPLATE

    def test_dispatch_buttons_ride_the_queue_gate(self):
        for act in ("enable", "disable", "audit"):
            assert f'data-regime-act="{act}"' in TEMPLATE
        # exec-btn class puts them behind body.queue-ok automatically
        i = TEMPLATE.index('data-regime-act="enable"')
        assert "exec-btn" in TEMPLATE[TEMPLATE.rindex("<button", 0, i):i]

    def test_directives_are_the_warden_ones(self):
        assert "'warden_audit'" in TEMPLATE
        assert "'warden_regime'" in TEMPLATE


class TestScanKeywordPrecision:
    def test_the_word_health_alone_is_not_hipaa_evidence(self, tmp_path):
        (tmp_path / "ops.md").write_text(
            "the health check endpoint returns 200", encoding="utf-8")
        assert not compliance.scan_repo(tmp_path)["hipaa"]

    def test_node_modules_is_pruned_not_walked(self, tmp_path):
        deep = tmp_path / "node_modules" / "some-pkg"
        deep.mkdir(parents=True)
        (deep / "billing.js").write_text("stripe cardholder pan", encoding="utf-8")
        assert not compliance.scan_repo(tmp_path)["pci"]


class TestAttestNoteStrip:
    def test_whitespace_only_note_is_refused(self, tmp_path):
        r = _wall(tmp_path, "attest", "pci", "R3", "--status", "pass",
                  "--note", "   ")
        assert r.returncode == 2 and "note is the record" in r.stderr


class TestAuditAtomicity:
    def test_the_batch_is_one_write_with_sequential_seqs(self, tmp_path):
        import items as items_mod
        (tmp_path / ".wall" / "events").mkdir(parents=True)
        recs = items_mod.append_events(tmp_path, "s_warden", [
            {"event": "compliance_attested", "regime": "pci", "control": "R1",
             "status": "pass", "note": "n"},
            {"event": "compliance_audited", "regime": "pci"},
        ])
        assert [r["seq"] for r in recs] == [recs[0]["seq"], recs[0]["seq"] + 1]
        lines = _events(tmp_path)
        assert [e["event"] for e in lines] == [
            "compliance_attested", "compliance_audited"]

    def test_audit_verb_lands_marker_with_attestations_or_nothing(self, tmp_path, monkeypatch):
        # the marker rides the same single write as the attestations
        results = {c: {"status": "pass", "note": "verified"}
                   for c in compliance.control_ids("sector")}
        f = tmp_path / "res.json"
        f.write_text(json.dumps(results), encoding="utf-8")
        r = _wall(tmp_path, "audit", "sector", "--file", str(f))
        assert r.returncode == 0, r.stderr
        ev = _events(tmp_path)
        attests = [e for e in ev if e["event"] == "compliance_attested"]
        markers = [e for e in ev if e["event"] == "compliance_audited"]
        assert len(markers) == 1 and len(attests) == len(
            compliance.control_ids("sector"))
        # every record in the batch shares one ts — the single-write signature
        assert len({e["ts"] for e in attests + markers}) == 1
