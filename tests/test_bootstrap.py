"""bootstrap — the runbooks as one command (DEC-0021), pinned.

The three modes are exercised against real temp repos; the properties
under test are the CONSENT and BOUNDARY rules, each with the mutation
that kills it: a dry run writes nothing; an existing file is never
overwritten by fresh; adopt keeps the host's documents (its decision
log above all); upgrade is verbatim and never touches host config; the
result actually RUNS (`wall run-once` + `summary` on the bootstrapped
repo, in a subprocess, so a missing vendored file fails here and not
on an adopter's laptop).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import bootstrap as bs

KIT = Path(__file__).resolve().parents[1]


def run(mode: str, into: Path, *extra: str) -> int:
    return bs.main([mode, "--into", str(into), *extra])


# ------------------------------------------------------------------ fresh

def test_fresh_dry_run_writes_nothing(tmp_path, capsys):
    assert run("fresh", tmp_path) == 0
    out = capsys.readouterr().out
    assert "dry run" in out and "add  wall/wall.py" in out
    assert list(tmp_path.iterdir()) == [], "a dry run wrote files"


def test_fresh_refuses_the_kit_checkout_itself(capsys):
    assert run("fresh", KIT) == 2
    assert "refusing" in capsys.readouterr().out


def test_fresh_apply_lands_a_working_side_repo(tmp_path, capsys):
    assert run("fresh", tmp_path, "--apply", "--mcp", "claude-code") == 0
    # the bounded subtree (DEC-0021 clause 1)
    assert (tmp_path / "tools" / "wall" / "wall.py").is_file()
    assert (tmp_path / "docs" / "WORKFLOW.md").is_file()
    assert (tmp_path / "templates").is_dir()
    assert (tmp_path / ".wall" / "config" / "wall.json").is_file()
    # the stamp for later upgrades
    stamp = json.loads((tmp_path / ".wall" / "config" / "kit_source.json")
                       .read_text(encoding="utf-8"))
    assert stamp["kit_commit"]
    # context documents materialized
    assert (tmp_path / "RULES.md").is_file()
    # the engineer's seat (DEC-0019)
    mcp = json.loads((tmp_path / ".mcp.json").read_text(encoding="utf-8"))
    assert mcp["mcpServers"]["wall"]["args"][-2:] == ["--role", "engineer"]
    # and the result RUNS — the runbook's own step 2, executed
    for cmd in (["run-once"], ["summary"]):
        proc = subprocess.run(
            [sys.executable, str(tmp_path / "tools" / "wall" / "wall.py"),
             "--repo", str(tmp_path), *cmd],
            capture_output=True, text=True, timeout=60)
        assert proc.returncode == 0, proc.stdout + proc.stderr


def test_fresh_never_overwrites_an_existing_context_document(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("HOST_SENTINEL", encoding="utf-8")
    assert run("fresh", tmp_path, "--apply") == 0
    assert (tmp_path / "CLAUDE.md").read_text(encoding="utf-8") == "HOST_SENTINEL"


def test_mcp_merge_preserves_other_servers_and_skips_bad_json(tmp_path, capsys):
    cfg = tmp_path / ".mcp.json"
    cfg.write_text(json.dumps(
        {"mcpServers": {"other": {"command": "x"}}}), encoding="utf-8")
    bs.emit_mcp_configs(tmp_path, ["claude-code"], apply=True)
    merged = json.loads(cfg.read_text(encoding="utf-8"))
    assert set(merged["mcpServers"]) == {"other", "wall"}

    bad = tmp_path / ".cursor" / "mcp.json"
    bad.parent.mkdir()
    bad.write_text("{not json", encoding="utf-8")
    bs.emit_mcp_configs(tmp_path, ["cursor"], apply=True)
    assert bad.read_text(encoding="utf-8") == "{not json"  # untouched
    assert "not valid JSON" in capsys.readouterr().out


# ------------------------------------------------------------------ adopt

def _host(tmp_path: Path) -> Path:
    repo = tmp_path / "host"
    (repo / "docs" / "decisions").mkdir(parents=True)
    (repo / "CLAUDE.md").write_text("HOST entry", encoding="utf-8")
    (repo / "KNOWN_FAILURE_PATTERNS.md").write_text("HOST kfp", encoding="utf-8")
    (repo / "docs" / "decisions" / "index.md").write_text(
        "HOST_DECISION_INDEX", encoding="utf-8")
    return repo


def test_adopt_maps_by_the_names_things_go_by(tmp_path, capsys):
    repo = _host(tmp_path)
    assert run("adopt", repo) == 0
    out = capsys.readouterr().out
    assert "MAPPED  entry point" in out and "CLAUDE.md" in out
    assert "MAPPED  failure registry" in out
    assert "MAPPED  decision log" in out
    assert "GAP     prompt budgets" in out
    assert not (repo / "tools" / "wall").exists()  # dry run wrote nothing


def test_adopt_apply_keeps_every_host_document(tmp_path):
    """The boundary rule (DEC-0021 clause 2): the machine lands, the
    host's documents — its decision log above all — stay byte-identical.
    Mutation: drop the docs/decisions exclusion and the index pin fails."""
    repo = _host(tmp_path)
    assert run("adopt", repo, "--apply") == 0
    assert (repo / "tools" / "wall" / "wall.py").is_file()
    assert (repo / "docs" / "WORKFLOW.md").is_file()  # process corpus lands
    assert (repo / "CLAUDE.md").read_text(encoding="utf-8") == "HOST entry"
    assert ((repo / "docs" / "decisions" / "index.md")
            .read_text(encoding="utf-8") == "HOST_DECISION_INDEX")
    assert not (repo / "docs" / "decisions" / "DEC-0001.md").exists(), (
        "the kit's own rulings must not colonize the host's decision log")
    assert not (repo / "RULES.md").exists(), (
        "adopt never materializes templates — gaps are REPORTED")


# ---------------------------------------------------------------- upgrade

def test_upgrade_is_verbatim_and_leaves_host_config_alone(tmp_path, capsys):
    repo = tmp_path / "adopted"
    assert run("fresh", repo, "--apply") == 0
    # host binds its config; a vendored file drifts locally
    cfg = repo / ".wall" / "config" / "wall.json"
    cfg.write_text('{"repo_name": "HOST_BOUND"}', encoding="utf-8")
    drifted = repo / "tools" / "wall" / "summary.py"
    drifted.write_text("# local fork — drift with a byline\n", encoding="utf-8")

    capsys.readouterr()
    assert run("upgrade", repo) == 0
    out = capsys.readouterr().out
    assert "update  wall/summary.py" in out
    assert "decisions/index.md" in out or "DECISIONS first" in out
    assert drifted.read_text(encoding="utf-8").startswith("# local fork"), (
        "a dry run must not re-vendor")

    assert run("upgrade", repo, "--apply") == 0
    assert (drifted.read_text(encoding="utf-8")
            == (KIT / "tools" / "wall" / "summary.py")
            .read_text(encoding="utf-8")), "re-vendor is VERBATIM"
    assert cfg.read_text(encoding="utf-8") == '{"repo_name": "HOST_BOUND"}', (
        "upgrade touched host config")
    stamp = json.loads((repo / ".wall" / "config" / "kit_source.json")
                       .read_text(encoding="utf-8"))
    assert stamp["kit_commit"]


def test_upgrade_noop_says_so(tmp_path, capsys):
    repo = tmp_path / "adopted"
    assert run("fresh", repo, "--apply") == 0
    capsys.readouterr()
    assert run("upgrade", repo, "--apply") == 0
    assert "nothing to change" in capsys.readouterr().out


# ---------------------------------------------------- preflight + remove

def test_preflight_names_the_dependency_surface(capsys):
    """DEC-0022 clause 1: verified and named, never assumed. On this
    interpreter (3.11+) it passes; the pins are the NAMES."""
    assert bs.preflight() == []
    out = capsys.readouterr().out
    assert "python 3." in out
    assert "git" in out
    assert "no pip installs" in out


def test_remove_keeps_the_ledger_by_default_and_strips_only_the_wall(tmp_path, capsys):
    """DEC-0022 clause 2. Mutations: purge .wall/ without the flag, or
    delete a config that holds other servers."""
    repo = tmp_path / "r"
    assert run("fresh", repo, "--apply", "--mcp", "claude-code") == 0
    mcp = repo / ".mcp.json"
    cfg = json.loads(mcp.read_text(encoding="utf-8"))
    cfg["mcpServers"]["other"] = {"command": "x"}
    mcp.write_text(json.dumps(cfg), encoding="utf-8")
    (repo / ".wall" / "events").mkdir(parents=True, exist_ok=True)
    (repo / ".wall" / "events" / "probe.jsonl").write_text("{}\n", encoding="utf-8")

    capsys.readouterr()
    assert run("remove", repo) == 0  # dry run
    assert (repo / "tools" / "wall").exists(), "a dry run removed files"

    assert run("remove", repo, "--apply") == 0
    assert not (repo / "tools" / "wall").exists()
    assert not (repo / "templates").exists()
    assert (repo / ".wall" / "events" / "probe.jsonl").exists(), (
        "the LEDGER must survive a default remove")
    assert (repo / "RULES.md").exists(), "context documents are the host's"
    assert (repo / "docs").exists(), "docs/ is never script-deleted"
    left = json.loads(mcp.read_text(encoding="utf-8"))
    assert list(left["mcpServers"]) == ["other"], (
        "remove strips exactly the wall's entry")


def test_remove_purge_state_deletes_the_ledger_only_when_said(tmp_path):
    repo = tmp_path / "r"
    assert run("fresh", repo, "--apply") == 0
    assert run("remove", repo, "--apply", "--purge-state") == 0
    assert not (repo / ".wall").exists()
    assert (repo / "RULES.md").exists()
