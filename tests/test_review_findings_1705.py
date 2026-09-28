"""CodeRabbit findings on the kit as vendored into a host repo, pinned.

Each test fails with its fix reverted:
- an upgrade of an ADOPTED repo re-vendored `docs/` without adopt's
  `docs/decisions` exclusion, so the host's decision log was refused or
  (with --force) overwritten;
- a JSON-RPC request with an explicit `"id": null` ran the method;
- `gate-skillspector` died with a traceback on an unreadable or non-object
  report instead of the "not clean, unknown" verdict `gate-zizmor` gives;
- `_parse_budget` read "12 kib" as k x "ib" and dropped the row;
- `validate_retro` raised TypeError on a non-string name/path/signal/diff;
- the WAITING count read an omitted `verify_waiting` as zero.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import bootstrap as bs
import mcp_server as srv
import quality
import service
import wall
from test_wall_template_sections import base, paint, text_of

KIT = Path(__file__).resolve().parents[1]
SAMPLE = KIT / "sample"


def _boot(mode: str, into: Path, *extra: str) -> int:
    return bs.main([mode, "--into", str(into), *extra])


# ------------------------------------------------------------ bootstrap


def _adopted(tmp_path: Path) -> Path:
    repo = tmp_path / "host"
    decisions = repo / "docs" / "decisions"
    decisions.mkdir(parents=True)
    (decisions / "index.md").write_text("# HOST decision log\n", encoding="utf-8")
    (decisions / "DEC-0001.md").write_text("# host's own ruling\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(repo)], check=True, timeout=30)
    assert _boot("adopt", repo, "--apply") == 0
    return repo


def test_adopt_records_the_decisions_exclusion_in_the_stamp(tmp_path):
    repo = _adopted(tmp_path)
    stamp = json.loads((repo / bs.STAMP_REL).read_text(encoding="utf-8"))
    assert stamp["excluded"] == {"docs": ["decisions"]}


def test_upgrade_of_an_adoption_leaves_the_host_decision_log_alone(tmp_path):
    repo = _adopted(tmp_path)
    assert _boot("upgrade", repo, "--apply") == 0, (
        "the host's own decision files blocked the upgrade")
    decisions = repo / "docs" / "decisions"
    assert (decisions / "index.md").read_text(encoding="utf-8") == "# HOST decision log\n"
    assert (decisions / "DEC-0001.md").read_text(encoding="utf-8") == "# host's own ruling\n"
    kit_only = {p.name for p in (KIT / "docs" / "decisions").iterdir()} - {
        "index.md", "DEC-0001.md"}
    assert not kit_only & {p.name for p in decisions.iterdir()}, (
        "the kit's rulings were added to the host's decision log")


def test_a_pre_exclusion_stamp_still_protects_host_decisions(tmp_path):
    repo = _adopted(tmp_path)
    path = repo / bs.STAMP_REL
    stamp = json.loads(path.read_text(encoding="utf-8"))
    del stamp["excluded"]  # a stamp written before this fix
    path.write_text(json.dumps(stamp), encoding="utf-8")
    assert _boot("upgrade", repo, "--apply") == 0
    assert (repo / "docs" / "decisions" / "index.md").read_text(
        encoding="utf-8") == "# HOST decision log\n"
    assert json.loads(path.read_text(encoding="utf-8"))["excluded"] == {
        "docs": ["decisions"]}, "the upgrade must record what it inferred"


# ------------------------------------------------------------ mcp_server


def test_an_explicit_null_id_is_an_invalid_request_and_runs_nothing(monkeypatch):
    ran = []
    monkeypatch.setattr(srv, "handle_request", lambda *a, **k: ran.append(a) or {})
    out = srv._dispatch_one(SAMPLE, {"jsonrpc": "2.0", "id": None,
                                     "method": "tools/list"}, "agent")
    assert out["error"]["code"] == srv.INVALID_REQUEST and out["id"] is None
    assert not ran, "the method ran for a null-id request"
    srv._dispatch_one(SAMPLE, {"jsonrpc": "2.0", "method": "notifications/x"}, "agent")
    assert len(ran) == 1, "an omitted id is still a notification"


# ------------------------------------------------------------ quality


def test_an_unreadable_skillspector_report_is_not_clean_unknown(tmp_path, capsys):
    bad = tmp_path / "r.json"
    bad.write_text("{truncated", encoding="utf-8")
    assert quality.main(["gate-skillspector", str(bad)]) == 1
    assert "not clean, unknown" in capsys.readouterr().err
    assert quality.main(["gate-skillspector", str(tmp_path / "missing.json")]) == 1
    listed = tmp_path / "l.json"
    listed.write_text("[]", encoding="utf-8")
    assert quality.main(["gate-skillspector", str(listed)]) == 1
    assert "not a JSON object" in capsys.readouterr().err


# ------------------------------------------------------------ service


def test_a_lowercase_kib_budget_is_measured():
    assert service._parse_budget("12 kib") == (12 * 1024, "bytes")
    assert service._parse_budget("12kib") == (12 * 1024, "bytes")
    assert service._parse_budget("12 KiB") == (12 * 1024, "bytes")
    assert service._parse_budget("12k tokens") == (12000, "tokens")
    assert service._parse_budget("12ktokens") == (12000, "tokens")
    assert service._parse_budget("12 kb") == (12000, "bytes")
    assert service._parse_budget("12k") is None


# ------------------------------------------------------------ wall


def test_retro_values_of_the_wrong_type_are_problems_not_a_traceback():
    payload = {
        "signals": [{"name": ["x"], "value": 1, "source": "ledger"}],
        "diffs": [{"kind": "rule", "path": ["a"], "signal": {}, "horizon": "h",
                   "why": "w", "owner": "o"}],
        "inputs": [],
    }
    problems, _, _ = wall.validate_retro(payload, [])
    text = " ".join(problems)
    assert "signals[0]: no name" in text
    assert "diffs[0]: no path" in text
    assert "diffs[0]: signal" in text


# ------------------------------------------------------------ template


def test_an_unmeasured_verify_queue_is_not_counted_as_zero(tmp_path):
    snap = base()
    assert "verify_waiting" not in snap
    out = paint(snap, tmp_path)
    assert "Waiting on you 0+?" in text_of(out["mainStats"]["html"])
    assert "Nothing needs you" not in text_of(out["asks"]["html"])
    assert "not measured" in text_of(out["asks"]["html"])
    out = paint(base(verify_waiting=[]), tmp_path)
    assert "Waiting on you 0" in text_of(out["mainStats"]["html"])
    assert "Nothing needs you" in text_of(out["asks"]["html"])
