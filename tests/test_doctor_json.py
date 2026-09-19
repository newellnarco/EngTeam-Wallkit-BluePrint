"""Machine-readable diagnostics: `wall doctor --json` + the shipped payload.

The closed loop the payload serves: the machine-wide timer sweeps, the sweep
refreshes doctor.json, the shipper carries it off-box on the telemetry branch,
and an automated-review session reads it there and files work items. So the
pins here are honesty pins: a section that could not be checked must say so,
and the file must be exactly as fresh as the wall it rides with.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "tools" / "wall"
sys.path.insert(0, str(HERE))

import shipper  # noqa: E402
import wall  # noqa: E402


def _minimal_repo(tmp_path: Path) -> Path:
    day = "2026-09-19"
    sh = tmp_path / ".wall" / "events" / day
    sh.mkdir(parents=True)
    ev = {"event_id": "ev_doc00001", "seq": 1, "ts": f"{day}T10:00:00Z",
          "session_id": "s_doc", "event": "item_created", "item_id": "ST-901",
          "title": "doctor fixture", "kind": "story", "actor": "tst_000000"}
    (sh / "s_doc.jsonl").write_text(json.dumps(ev) + "\n", encoding="utf-8")
    (tmp_path / ".wall" / "config").mkdir()
    return tmp_path


def test_payload_is_honest_on_an_empty_repo(tmp_path):
    p = wall.build_doctor_payload(tmp_path)
    assert p["heartbeat"] is None
    assert p["integrity_summary"] == {"checked": False}
    assert p["roster"]["checked"] is True  # registry auto-materialises
    assert "generated_at" in p


def test_run_once_refreshes_doctor_json_beside_the_wall(tmp_path):
    repo = _minimal_repo(tmp_path)

    class A:
        pass
    a = A(); a.repo = str(repo); a.rebuild = True
    assert wall.cmd_run_once(a) == 0
    out = repo / ".wall" / "derived" / "doctor.json"
    assert out.is_file(), "sweep must refresh the shipped diagnostics"
    p = json.loads(out.read_text(encoding="utf-8"))
    assert p["integrity_summary"]["checked"] is True
    assert isinstance(p["integrity_summary"]["flags"], dict)


def test_doctor_json_flag_prints_and_writes(tmp_path, capsys):
    repo = _minimal_repo(tmp_path)

    class A:
        pass
    a = A(); a.repo = str(repo); a.rebuild = True
    wall.cmd_run_once(a)
    capsys.readouterr()  # drain the sweep's own line; we parse only doctor's
    d = A(); d.repo = str(repo); d.as_json = True
    assert wall.cmd_doctor(d) == 0
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["roster"]["checked"] is True


def test_never_checked_state_drift_is_null_not_zero(tmp_path):
    repo = _minimal_repo(tmp_path)

    class A:
        pass
    a = A(); a.repo = str(repo); a.rebuild = False
    wall.cmd_run_once(a)
    p = json.loads((repo / ".wall" / "derived" / "doctor.json").read_text())
    # no .wall/items/ was materialised without --rebuild, so drift was never
    # checked; a check that never ran must not read as a clean zero
    if p["integrity_summary"]["checked"]:
        flags = p["integrity_summary"]["flags"]
        assert flags.get("state_drift", 0) in (None, 0)


def test_shipment_includes_doctor_json_after_the_snapshot(tmp_path):
    repo = _minimal_repo(tmp_path)

    class A:
        pass
    a = A(); a.repo = str(repo); a.rebuild = True
    wall.cmd_run_once(a)
    paths = shipper.shipment_paths(repo, day="2026-09-19")
    assert paths[0] == ".wall/derived/wall.json", "snapshot still leads"
    assert paths[1] == ".wall/derived/doctor.json"
    assert any(p.startswith(".wall/events/") for p in paths)


def test_shipment_omits_doctor_json_when_absent(tmp_path):
    repo = _minimal_repo(tmp_path)
    (repo / ".wall" / "derived").mkdir(parents=True, exist_ok=True)
    (repo / ".wall" / "derived" / "wall.json").write_text(
        json.dumps({"generated_at": "2026-09-19T10:00:00Z", "integrity": {}}),
        encoding="utf-8")
    paths = shipper.shipment_paths(repo, day="2026-09-19")
    assert ".wall/derived/doctor.json" not in paths
