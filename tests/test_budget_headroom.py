"""`service.budget_headroom()` -- the context-doc budget register, measured.

Reads the host's BUDGETED_DOCS.md register (templates/BUDGETED_DOCS.md.template
shape), measures each document in the unit its Budget cell declares, and
returns per-document headroom. The doctor renders ok / warn (<10% left) /
fail (over budget), and still says "not measured" -- never "fine" -- when
there is no register.

Stdlib + pytest.
"""

from __future__ import annotations

import json
import types
from pathlib import Path

import pytest

import service

HEADER = ("| Document | Consumer | What is counted | Budget | Last measured | "
          "Headroom | Measured on |\n|---|---|---|---|---|---|---|\n")


def row(doc: str, budget: str, counted: str = "whole file") -> str:
    return f"| `{doc}` | review lane | {counted} | {budget} | 0 | 0 | 2026-09-01 |\n"


@pytest.fixture
def host(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setenv("WALL_HOME", str(tmp_path / "wallhome"))
    root = tmp_path / "repo"
    (root / ".wall" / "derived").mkdir(parents=True)
    (root / "a.md").write_text("x" * 50, encoding="utf-8")        # 50 chars
    (root / "b.md").write_text("y" * 95, encoding="utf-8")        # 95 chars
    (root / "c.md").write_text("z" * 120, encoding="utf-8")       # 120 chars
    (root / "d.md").write_text("one\ntwo\nthree\n", encoding="utf-8")
    return root


def adapter():
    return types.SimpleNamespace(verify=lambda **_: {
        "installed": True, "running": True, "last_run": None, "error": None})


def register(root: Path, rows: str, name: str = "BUDGETED_DOCS.md") -> None:
    (root / name).write_text("# BUDGETED_DOCS.md\n\n## The register\n\n" + HEADER
                             + rows + "\nUnits are whatever...\n", encoding="utf-8")


def by_path(rows):
    return {r["path"]: r for r in rows}


def test_no_register_is_not_measured_never_fine(host):
    assert service.budget_headroom(host) is None
    check = {c["name"]: c for c in service.doctor_checks(host, adapter=adapter())}
    assert check["budget"]["status"] == "unknown"
    assert "not measured" in check["budget"]["detail"]
    assert "fine" not in check["budget"]["detail"]


def test_each_document_is_measured_in_its_unit(host):
    register(host, row("a.md", "100 characters") + row("b.md", "100 chars")
             + row("c.md", "100 characters") + row("d.md", "10 lines")
             + row("c.md", "120 bytes")
             + row("a.md", "10 tokens"))
    rows = service.budget_headroom(host)
    assert len(rows) == 6
    a, b, c, d, c_bytes, a_tok = rows
    assert (a["measured"], a["headroom"], a["status"]) == (50, 50, "ok")
    assert (b["measured"], b["headroom"], b["status"]) == (95, 5, "warn")
    assert (c["measured"], c["headroom"], c["status"]) == (120, -20, "fail")
    assert "OVER BUDGET" in c["detail"]
    assert (d["unit"], d["measured"], d["status"]) == ("lines", 3, "ok")
    assert (c_bytes["unit"], c_bytes["headroom"], c_bytes["status"]) == ("bytes", 0, "warn")
    # Tokens are approximated (4 chars each) and say so.
    assert (a_tok["unit"], a_tok["measured"], a_tok["approximate"]) == ("tokens", 13, True)
    assert a_tok["status"] == "fail" and a_tok["detail"].startswith("~")


def test_kilo_suffixes(host):
    register(host, row("a.md", "1 KB") + row("b.md", "1 KiB") + row("c.md", "1k characters"))
    got = [(r["unit"], r["budget"]) for r in service.budget_headroom(host)]
    assert got == [("bytes", 1000), ("bytes", 1024), ("characters", 1000)]


def test_rows_that_cannot_be_measured_honestly_are_unknown(host):
    register(host, row("<PATH_TO_DOC>", "<LIMIT_WITH_UNITS>")
             + row("a.md", "100 widgets")
             + row("a.md", "100 characters", counted="the rules section"))
    rows = service.budget_headroom(host)
    assert [r["status"] for r in rows] == ["unknown"] * 3
    assert "unfilled" in rows[0]["detail"]
    assert "unit" in rows[1]["detail"]
    assert "not measured" in rows[2]["detail"]


def test_a_registered_doc_that_is_missing_warns(host):
    register(host, row("gone.md", "100 characters"))
    assert service.budget_headroom(host)[0]["status"] == "warn"


def test_doctor_renders_worst_status_and_one_line_per_doc(host):
    register(host, row("a.md", "100 characters") + row("c.md", "100 characters"))
    checks = {c["name"]: c for c in service.doctor_checks(host, adapter=adapter())}
    assert checks["budget"]["status"] == "fail"
    assert checks["budget a.md"]["status"] == "ok"
    assert checks["budget c.md"]["status"] == "fail"


def test_doctor_warns_under_ten_percent(host):
    register(host, row("b.md", "100 characters"))
    checks = {c["name"]: c for c in service.doctor_checks(host, adapter=adapter())}
    assert checks["budget"]["status"] == "warn"


def test_empty_register_is_not_measured(host):
    register(host, "")
    assert service.budget_headroom(host) == []
    check = {c["name"]: c for c in service.doctor_checks(host, adapter=adapter())}
    assert check["budget"]["status"] == "unknown"
    assert "not measured" in check["budget"]["detail"]


def test_an_empty_register_does_not_adopt_a_later_table(host):
    (host / "BUDGETED_DOCS.md").write_text(
        "# BUDGETED_DOCS.md\n\n## The register\n\n" + HEADER +
        "\nUnits are whatever...\n\n## History\n\n"
        "| Document | Budget | Note |\n|---|---|---|\n"
        "| `a.md` | 100 characters | an old row, not the register |\n",
        encoding="utf-8")
    assert service.budget_headroom(host) == []
    check = {c["name"]: c for c in service.doctor_checks(host, adapter=adapter())}
    assert "not measured" in check["budget"]["detail"]


def test_config_can_point_at_a_mapped_register(host):
    (host / ".wall" / "config").mkdir(parents=True)
    (host / ".wall" / "config" / "wall.json").write_text(
        json.dumps({"budgeted_docs": "docs/BUDGETS.md"}), encoding="utf-8")
    (host / "docs").mkdir()
    register(host, row("a.md", "100 characters"), name="docs/BUDGETS.md")
    assert service.budget_headroom(host)[0]["status"] == "ok"


def test_a_path_outside_the_repo_is_not_read(host, tmp_path):
    (tmp_path / "outside.md").write_text("q" * 10, encoding="utf-8")
    register(host, row("../outside.md", "100 characters"))
    r = service.budget_headroom(host)[0]
    assert r["measured"] is None and r["status"] == "warn"
