"""The heartbeat's ok is a verdict, not a constant.

A shard line that fails to parse is skipped so the sweep survives -- but a
heartbeat that still reads ok: true has folded "some events were unreadable"
into "everything is fine", which is the exact defect class the kit's own
FAILURE_PATTERNS registry seeds (unknown-folded-into-ok). Pinned here with the
mutation that kills each assertion: hardcode ok back to True and the corrupt
test fails; drop the corrupt counter and both counts read 0.

The bounded-git contract on wall.py rides in the same file: a hung local git
must surface as a failure, never a hang (rc 124 from _git; a loud SystemExit
from changed_files, because an empty list would silently classify the change
set as "nothing changed").
"""

from __future__ import annotations

import json
import subprocess

import courier
import wall as wall_mod

from test_golden import ev, shard


def _heartbeat(repo):
    return json.loads(
        (repo / ".wall" / "derived" / "heartbeat.json").read_text(encoding="utf-8"))


def test_clean_run_reports_ok_and_zero_corrupt(repo):
    shard(repo, "s_a", [ev("s_a", 1, "2026-09-19T12:00:00.000Z")])
    courier.run_once(repo)
    hb = _heartbeat(repo)
    assert hb["ok"] is True
    assert hb["corrupt_lines"] == 0


def test_corrupt_shard_line_flips_ok_and_is_counted(repo):
    shard(repo, "s_a", [ev("s_a", 1, "2026-09-19T12:00:00.000Z")])
    path = repo / ".wall" / "events" / "2026-09-19" / "s_a.jsonl"
    with path.open("a", encoding="utf-8") as fh:
        fh.write("{this is not json}\n")
    shard(repo, "s_a", [ev("s_a", 2, "2026-09-19T12:01:00.000Z")])

    courier.run_once(repo)
    hb = _heartbeat(repo)
    assert hb["ok"] is False
    assert hb["corrupt_lines"] == 1
    # The parseable events on either side of the corrupt line still landed.
    ledger = (repo / ".wall" / "derived" / "ledger.jsonl").read_text(encoding="utf-8")
    assert "s_a-1" in ledger and "s_a-2" in ledger


def test_next_clean_run_recovers_ok(repo):
    """The verdict is per-run: a past corrupt line already consumed does not
    poison every future heartbeat."""
    path = repo / ".wall" / "events" / "2026-09-19" / "s_a.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{broken\n", encoding="utf-8")
    courier.run_once(repo)
    assert _heartbeat(repo)["ok"] is False

    shard(repo, "s_a", [ev("s_a", 1, "2026-09-19T12:00:00.000Z")])
    courier.run_once(repo)
    hb = _heartbeat(repo)
    assert hb["ok"] is True
    assert hb["corrupt_lines"] == 0


def test_git_helper_reports_timeout_as_failure_not_hang(monkeypatch, tmp_path):
    def hang(*a, **kw):
        raise subprocess.TimeoutExpired(cmd=a[0], timeout=kw.get("timeout", 0))
    monkeypatch.setattr(wall_mod.subprocess, "run", hang)
    rc, out, err = wall_mod._git(tmp_path, "status")
    assert rc == 124
    assert "timed out" in err


def test_changed_files_refuses_to_classify_on_timeout(monkeypatch, tmp_path):
    """An empty list here would route a real change set down the docs fast
    path. A timeout must be loud, never an answer."""
    def hang(*a, **kw):
        raise subprocess.TimeoutExpired(cmd=a[0], timeout=kw.get("timeout", 0))
    monkeypatch.setattr(wall_mod.subprocess, "run", hang)
    try:
        wall_mod.changed_files(tmp_path)
    except SystemExit as exc:
        assert "timed out" in str(exc)
    else:
        raise AssertionError("changed_files returned instead of exiting")


def test_every_git_subprocess_in_wall_is_bounded():
    """Structural pin: no subprocess.run call in wall.py without a timeout."""
    import ast, inspect
    tree = ast.parse(inspect.getsource(wall_mod))
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "run"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "subprocess"):
            kwargs = {k.arg for k in node.keywords}
            assert "timeout" in kwargs, f"unbounded subprocess.run at line {node.lineno}"
