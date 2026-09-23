"""context_sync -- one AGENTS.md master per directory, generated copies.

Temp repos only. The properties pinned, each with the mutation that
kills it: copies carry the banner and the master body; a second sync
writes nothing; `check` goes red for an edited copy, an edited master
and a missing copy -- and says WHICH, because the remedy differs; a
hand-written tool file is never overwritten; `--adopt` moves one into a
new master and refuses where a master exists; root-only targets stay at
the root; symlinks are accepted; a CRLF checkout does not flap.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import bootstrap as bs
import context_sync as cs
import wall

KIT = Path(__file__).resolve().parents[1]
ALL = ["CLAUDE.md", "GEMINI.md", ".github/copilot-instructions.md",
       ".cursor/rules/agents.mdc"]


def _repo(tmp_path: Path, targets: list[str] | None = None) -> Path:
    repo = tmp_path / "host"
    (repo / "backend").mkdir(parents=True)
    (repo / "AGENTS.md").write_text("# Root rules\n\nroot body\n",
                                    encoding="utf-8")
    (repo / "backend" / "AGENTS.md").write_text("# Backend\n\nbe body\n",
                                                encoding="utf-8")
    if targets is not None:
        (repo / ".wall" / "config").mkdir(parents=True)
        (repo / ".wall" / "config" / "wall.json").write_text(
            json.dumps({"context": {"targets": targets}}), encoding="utf-8")
    return repo


def _statuses(repo: Path) -> dict[str, str]:
    return {e.target: e.status for e in cs.scan(repo)}


def _snapshot(repo: Path) -> dict[str, bytes]:
    return {p.relative_to(repo).as_posix(): p.read_bytes()
            for p in sorted(repo.rglob("*")) if p.is_file()}


# ------------------------------------------------------------ generation

def test_sync_writes_root_and_nested_copies_with_banner(tmp_path):
    repo = _repo(tmp_path)
    res = cs.sync(repo)
    assert res.code == 0 and res.written == 2
    root = (repo / "CLAUDE.md").read_text(encoding="utf-8")
    first, _, body = root.partition("\n")
    assert first.startswith("<!-- GENERATED from AGENTS.md by "
                            "tools/wall/context_sync.py")
    assert "do not edit" in first and "context_sync.py sync" in first
    assert f"master-sha256: {cs.body_hash(body)} -->" in first
    assert body == "# Root rules\n\nroot body\n"
    nested = (repo / "backend" / "CLAUDE.md").read_text(encoding="utf-8")
    assert nested.startswith("<!-- GENERATED from backend/AGENTS.md ")
    assert nested.endswith("\n# Backend\n\nbe body\n")
    assert root == cs.render("CLAUDE.md", "AGENTS.md",
                             (repo / "AGENTS.md").read_text(encoding="utf-8"))


def test_second_sync_writes_nothing(tmp_path):
    repo = _repo(tmp_path, ALL)
    assert cs.sync(repo).written == 6
    before = _snapshot(repo)
    res = cs.sync(repo)
    assert (res.code, res.written, res.lines) == (0, 0, [])
    assert _snapshot(repo) == before


def test_skips_dependency_dot_and_kit_trees(tmp_path):
    repo = _repo(tmp_path)
    for d in ("node_modules/pkg", ".venv/lib", "tools/wall/sub",
              "frontend/theme"):
        (repo / d).mkdir(parents=True)
        (repo / d / "AGENTS.md").write_text("vendored\n", encoding="utf-8")
    (repo / "frontend" / "app").mkdir(parents=True)
    (repo / "frontend" / "app" / "AGENTS.md").write_text("app\n",
                                                         encoding="utf-8")
    cs.sync(repo)
    assert set(_statuses(repo)) == {"CLAUDE.md", "backend/CLAUDE.md",
                                    "frontend/app/CLAUDE.md"}
    assert not (repo / "tools" / "wall" / "sub" / "CLAUDE.md").exists()
    assert set(cs.KIT_OWNED_PREFIXES) == set(bs.KIT_OWNED_PREFIXES)


# ----------------------------------------------------------------- check

def test_check_green_after_sync(tmp_path):
    repo = _repo(tmp_path)
    cs.sync(repo)
    res = cs.check(repo)
    assert (res.code, res.lines) == (0, [])


def test_check_red_after_editing_a_copy(tmp_path):
    repo = _repo(tmp_path)
    cs.sync(repo)
    copy = repo / "CLAUDE.md"
    copy.write_text(copy.read_text(encoding="utf-8") + "sneaky edit\n",
                    encoding="utf-8")
    res = cs.check(repo)
    assert res.code == 1
    assert res.lines == ["  EDITED      CLAUDE.md  <- AGENTS.md  (body no "
                         "longer matches its own banner hash)"]


def test_check_red_and_stale_after_editing_the_master(tmp_path):
    """Stale, not edited: the remedy is `sync`, which refreshes it.
    Mutation: drop the banner-hash-vs-master comparison and this copy
    reads as EDITED -- which sync refuses -- so the master edit could
    never propagate."""
    repo = _repo(tmp_path)
    cs.sync(repo)
    (repo / "backend" / "AGENTS.md").write_text("# Backend\n\nnew rule\n",
                                                encoding="utf-8")
    assert _statuses(repo)["backend/CLAUDE.md"] == "stale"
    res = cs.check(repo)
    assert res.code == 1 and len(res.lines) == 1
    assert res.lines[0].startswith("  STALE       backend/CLAUDE.md")
    fix = cs.sync(repo)
    assert fix.code == 0 and fix.written == 1
    assert (repo / "backend" / "CLAUDE.md").read_text(
        encoding="utf-8").endswith("\nnew rule\n")


def test_check_red_for_a_missing_copy(tmp_path):
    repo = _repo(tmp_path)
    cs.sync(repo)
    (repo / "backend" / "CLAUDE.md").unlink()
    res = cs.check(repo)
    assert res.code == 1
    assert res.lines == ["  MISSING     backend/CLAUDE.md  <- "
                         "backend/AGENTS.md"]


def test_edited_banner_line_is_caught(tmp_path):
    repo = _repo(tmp_path)
    cs.sync(repo)
    copy = repo / "CLAUDE.md"
    copy.write_text(copy.read_text(encoding="utf-8").replace(
        "do not edit", "feel free to edit"), encoding="utf-8")
    assert _statuses(repo)["CLAUDE.md"] == "edited"


def test_crlf_checkout_does_not_flap(tmp_path):
    repo = _repo(tmp_path)
    (repo / "AGENTS.md").write_bytes(b"# Root\r\n\r\nbody\r\n")
    cs.sync(repo)
    written = (repo / "CLAUDE.md").read_bytes()
    assert b"\r" not in written, "copies are written LF"
    assert cs.check(repo).code == 0
    # the checkout converts the copy too
    (repo / "CLAUDE.md").write_bytes(written.replace(b"\n", b"\r\n"))
    assert cs.check(repo).code == 0
    assert cs.sync(repo).written == 0


# ----------------------------------------------- hand-written, adoption

def test_hand_written_copy_is_never_overwritten(tmp_path):
    """The guard. Mutation: treat a banner-less file as regenerable and
    the byte-identity assertion fails."""
    repo = _repo(tmp_path)
    hand = repo / "CLAUDE.md"
    hand.write_bytes(b"# my own notes\n")
    res = cs.sync(repo)
    assert res.code == 1
    assert hand.read_bytes() == b"# my own notes\n"
    assert any(ln.startswith("  REFUSE  CLAUDE.md  hand-written")
               for ln in res.lines)
    assert (repo / "backend" / "CLAUDE.md").is_file(), (
        "the refusal is per file, not a stop")
    assert cs.check(repo).code == 1


def test_adopt_moves_a_hand_written_file_into_a_new_master(tmp_path):
    repo = tmp_path / "legacy"
    repo.mkdir()
    (repo / "CLAUDE.md").write_bytes(b"# Legacy entry\r\nrules here\r\n")
    plain = cs.sync(repo)
    assert plain.code == 1 and not (repo / "AGENTS.md").exists()
    assert "--adopt" in plain.lines[0]
    dry = cs.sync(repo, adopt=True, apply=False)
    assert dry.code == 0 and not (repo / "AGENTS.md").exists()
    res = cs.sync(repo, adopt=True)
    assert res.code == 0
    assert (repo / "AGENTS.md").read_text(encoding="utf-8") == (
        "# Legacy entry\nrules here\n")
    assert (repo / "CLAUDE.md").read_text(encoding="utf-8").startswith(
        "<!-- GENERATED from AGENTS.md")
    assert cs.check(repo).code == 0


def test_non_utf8_tool_file_is_hand_written_not_a_crash(tmp_path):
    repo = tmp_path / "bin"
    repo.mkdir()
    (repo / "CLAUDE.md").write_bytes(b"\xff\xfe latin-1 \xe9\n")
    assert _statuses(repo) == {"CLAUDE.md": "handwritten"}
    res = cs.sync(repo, adopt=True)
    assert res.code == 1 and "not UTF-8" in res.lines[0]
    assert (repo / "CLAUDE.md").read_bytes() == b"\xff\xfe latin-1 \xe9\n"
    assert not (repo / "AGENTS.md").exists()


def test_adopt_refuses_when_a_master_exists(tmp_path):
    repo = _repo(tmp_path)
    (repo / "CLAUDE.md").write_text("hand\n", encoding="utf-8")
    master = (repo / "AGENTS.md").read_bytes()
    res = cs.sync(repo, adopt=True)
    assert res.code == 1
    assert (repo / "CLAUDE.md").read_text(encoding="utf-8") == "hand\n"
    assert (repo / "AGENTS.md").read_bytes() == master
    assert "--adopt only creates a master" in res.lines[0]
    refusals = [ln for ln in res.lines if "REFUSE" in ln]
    assert res.problems == 1 and len(refusals) == 1, (
        "one refusal per file, not one per pass")


def test_edited_copy_is_refused_and_orphan_copy_removed(tmp_path):
    repo = _repo(tmp_path)
    cs.sync(repo)
    copy = repo / "CLAUDE.md"
    copy.write_text(copy.read_text(encoding="utf-8") + "x\n",
                    encoding="utf-8")
    edited = copy.read_bytes()
    assert cs.sync(repo).code == 1 and copy.read_bytes() == edited
    (repo / "backend" / "AGENTS.md").unlink()
    assert _statuses(repo)["backend/CLAUDE.md"] == "orphan"
    cs.sync(repo)
    assert not (repo / "backend" / "CLAUDE.md").exists()


# ------------------------------------------------------- targets, config

def test_cursor_and_copilot_are_root_only_with_frontmatter(tmp_path):
    repo = _repo(tmp_path, ALL)
    assert cs.sync(repo).code == 0
    mdc = (repo / ".cursor" / "rules" / "agents.mdc").read_text(
        encoding="utf-8")
    assert mdc.startswith("---\ndescription: ")
    assert "\nalwaysApply: true\n---\n<!-- GENERATED from AGENTS.md" in mdc
    assert mdc.endswith("\n# Root rules\n\nroot body\n")
    assert (repo / ".github" / "copilot-instructions.md").read_text(
        encoding="utf-8").startswith("<!-- GENERATED from AGENTS.md")
    assert (repo / "backend" / "GEMINI.md").is_file()
    assert not (repo / "backend" / ".github").exists()
    assert not (repo / "backend" / ".cursor").exists()
    assert cs.check(repo).code == 0


def test_config_defaults_and_rejects_unknown_targets(tmp_path):
    repo = _repo(tmp_path)
    assert cs.load_targets(repo) == ["CLAUDE.md"]
    bad = _repo(tmp_path / "b", ["CLAUDE.md", "COPILOT.md"])
    with pytest.raises(cs.ConfigError, match="COPILOT.md"):
        cs.load_targets(bad)
    assert cs.run(bad, "check") == 2


# ----------------------------------------------------------------- links

@pytest.mark.skipif(os.name == "nt", reason="symlink mode is POSIX-only")
def test_symlink_mode_links_and_check_accepts_it(tmp_path):
    repo = _repo(tmp_path, ["CLAUDE.md", ".cursor/rules/agents.mdc"])
    res = cs.sync(repo, symlink=True)
    assert res.code == 0
    link = repo / "backend" / "CLAUDE.md"
    assert link.is_symlink() and os.readlink(link) == "AGENTS.md"
    mdc = repo / ".cursor" / "rules" / "agents.mdc"
    assert not mdc.is_symlink(), "a Cursor rule needs frontmatter: a copy"
    assert any("copying, not linking" in ln for ln in res.lines)
    assert cs.check(repo).code == 0
    assert cs.sync(repo, symlink=True).written == 0
    assert cs.sync(repo).written == 0, "copy mode keeps a correct link"
    link.unlink()
    os.symlink("../AGENTS.md", link)
    assert _statuses(repo)["backend/CLAUDE.md"] == "foreign"
    assert cs.check(repo).code == 1


def test_symlink_failure_falls_back_to_copy(tmp_path, monkeypatch):
    repo = _repo(tmp_path)

    def boom(*_a, **_k):
        raise OSError(1, "not permitted")
    monkeypatch.setattr(cs.os, "symlink", boom)
    res = cs.sync(repo, symlink=True)
    assert res.code == 0
    assert not (repo / "CLAUDE.md").is_symlink()
    assert any("copying, not linking -- symlink failed" in ln
               for ln in res.lines)
    assert cs.check(repo).code == 0


# ------------------------------------------------------ the contract

def test_banner_render_and_parse_contract():
    b = cs.banner("x/AGENTS.md", "abc")
    assert b.startswith(cs.BANNER_PREFIX + "x/AGENTS.md by " + cs.TOOL)
    assert cs.SYNC_COMMAND in b and b.endswith(cs.HASH_KEY + "abc -->")
    assert "\n" not in b, "the banner is one line"
    out = cs.render(cs.CURSOR_TARGET, "AGENTS.md", "\ufeffhi\r\n")
    assert out.startswith(cs.CURSOR_FRONTMATTER)
    digest, body = cs.split_generated(cs.CURSOR_TARGET, out)
    assert body == cs.normalize("\ufeffhi\r\n") == "hi\n"
    assert digest == cs.body_hash(body)
    assert cs.split_generated("CLAUDE.md", "# plain\n") is None
    assert cs.split_generated(cs.CURSOR_TARGET,
                              out[len(cs.CURSOR_FRONTMATTER):]) is None


def test_discovery_classify_and_result_shapes(tmp_path):
    repo = _repo(tmp_path)
    for d in sorted(cs.SKIP_DIRS):
        (repo / d).mkdir()
        (repo / d / cs.MASTER).write_text("skip\n", encoding="utf-8")
    assert cs.find_dirs(repo, list(cs.DEFAULT_TARGETS)) == [
        Path("."), Path("backend")]
    assert cs.classify(repo, Path("backend"), "CLAUDE.md") == cs.Entry(
        "backend/CLAUDE.md", "backend/AGENTS.md", "missing")
    assert cs.classify(repo, Path("nowhere"), "CLAUDE.md") is None
    assert set(cs.TARGET_KINDS) == set(ALL)
    assert [t for t, root in cs.TARGET_KINDS.items() if root] == [
        ".github/copilot-instructions.md", ".cursor/rules/agents.mdc"]
    (repo / "crlf.md").write_bytes(b"a\r\nb\r\n")
    assert cs.read(repo / "crlf.md") == "a\nb\n"
    assert (cs.Result([], 0, 3).code, cs.Result(["x"], 2, 0).code) == (0, 1)


# ------------------------------------------------------------------- CLI

def test_cli_and_wall_subcommand_exit_codes(tmp_path):
    repo = _repo(tmp_path)
    assert cs.main(["--repo", str(repo), "check"]) == 1
    assert cs.main(["--repo", str(repo), "sync", "--dry-run"]) == 0
    assert not (repo / "CLAUDE.md").exists()
    wall_py = KIT / "tools" / "wall" / "wall.py"
    proc = subprocess.run([sys.executable, str(wall_py), "--repo", str(repo),
                           "context", "sync"],
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    proc = subprocess.run([sys.executable, str(wall_py), "--repo", str(repo),
                           "context", "check"],
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0
    assert "every copy matches its master" in proc.stdout
    ns = argparse.Namespace(repo=str(repo), action="check", adopt=False,
                            symlink=False, dry_run=False)
    assert wall.cmd_context(ns) == 0
    (repo / "CLAUDE.md").unlink()
    assert wall.cmd_context(ns) == 1


# ------------------------------------------------------------- bootstrap

def test_fresh_materializes_agents_md_and_generates_claude_md(tmp_path):
    repo = tmp_path / "new"
    assert bs.main(["fresh", "--into", str(repo), "--apply"]) == 0
    master = (repo / "AGENTS.md").read_text(encoding="utf-8")
    assert master == (KIT / "templates" / "AGENTS.md.template").read_text(
        encoding="utf-8")
    copy = (repo / "CLAUDE.md").read_text(encoding="utf-8")
    assert copy == cs.render("CLAUDE.md", "AGENTS.md", master)
    assert cs.check(repo).code == 0


def test_fresh_with_a_hand_written_claude_md_writes_no_master(tmp_path,
                                                              capsys):
    repo = tmp_path / "host"
    repo.mkdir()
    (repo / "CLAUDE.md").write_text("HOST_SENTINEL", encoding="utf-8")
    assert bs.main(["fresh", "--into", str(repo), "--apply"]) == 0
    assert (repo / "CLAUDE.md").read_text(encoding="utf-8") == "HOST_SENTINEL"
    assert not (repo / "AGENTS.md").exists()
    assert "sync --adopt" in capsys.readouterr().out


def test_adopt_reports_the_sync_adopt_command_and_writes_nothing(tmp_path,
                                                                 capsys):
    repo = tmp_path / "host"
    repo.mkdir()
    (repo / "CLAUDE.md").write_text("HOST entry", encoding="utf-8")
    assert bs.main(["adopt", "--into", str(repo), "--apply"]) == 0
    out = capsys.readouterr().out
    assert "NOTE    CLAUDE.md is hand-written" in out
    assert "context_sync.py sync --adopt" in out
    assert not (repo / "AGENTS.md").exists()
    assert (repo / "CLAUDE.md").read_text(encoding="utf-8") == "HOST entry"


def test_upgrade_refreshes_generated_copies_never_hand_written(tmp_path):
    repo = tmp_path / "up"
    assert bs.main(["fresh", "--into", str(repo), "--apply"]) == 0
    (repo / "AGENTS.md").write_text("# filled in\n", encoding="utf-8")
    (repo / "backend").mkdir()
    (repo / "backend" / "AGENTS.md").write_text("be\n", encoding="utf-8")
    (repo / "backend" / "CLAUDE.md").write_text("hand\n", encoding="utf-8")
    assert bs.main(["upgrade", "--into", str(repo), "--apply"]) == 0
    assert (repo / "CLAUDE.md").read_text(encoding="utf-8").endswith(
        "\n# filled in\n")
    assert (repo / "backend" / "CLAUDE.md").read_text(
        encoding="utf-8") == "hand\n"
    assert bs.main(["remove", "--into", str(repo), "--apply"]) == 0
    assert (repo / "CLAUDE.md").is_file() and (repo / "AGENTS.md").is_file()
    assert (repo / "backend" / "CLAUDE.md").read_text(
        encoding="utf-8") == "hand\n"
