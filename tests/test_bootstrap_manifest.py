"""bootstrap — the merged trees, the .gitignore block and the manifest.

The properties pinned here, each with the mutation that kills it:

- `.claude/` and `tools/git-hooks/` land in every mode by ADDING: a
  host file that differs is a collision, kept byte-identical, even under
  --force; `.claude/settings*.json` is never copied.
- The kit's required ignores live in one marked block: appended once,
  refreshed by upgrade, stripped by remove back to the host's bytes.
- The stamp carries a sha256 per kit file. Upgrade and remove refuse to
  overwrite, prune or delete a file whose bytes left the record (or that
  cannot be verified at all) unless --force, and change NOTHING when
  they refuse. A file that matches its record is handled as before.
- `remove --mcp` strips only the named clients; preflight runs for remove
  and never stops it.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest

import bootstrap as bs

KIT = Path(__file__).resolve().parents[1]


def run(mode: str, into: Path, *extra: str) -> int:
    return bs.main([mode, "--into", str(into), *extra])


def snapshot(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): hashlib.sha256(
        p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*")) if p.is_file()}


def stamp_of(repo: Path) -> dict:
    return json.loads((repo / bs.STAMP_REL).read_text(encoding="utf-8"))


def write_stamp(repo: Path, stamp: dict) -> None:
    (repo / bs.STAMP_REL).write_text(json.dumps(stamp), encoding="utf-8")


def fresh(tmp_path: Path, name: str = "r", *extra: str) -> Path:
    repo = tmp_path / name
    assert run("fresh", repo, "--apply", *extra) == 0
    return repo


# ------------------------------------------------------- the merged trees

def test_fresh_lands_the_roster_and_the_hooks_uninstalled(tmp_path):
    """Mutation: drop MERGED from fresh and none of this lands."""
    repo = fresh(tmp_path)
    for rel in (".claude/MAESTRO.md", ".claude/agents/builder.md",
                ".claude/skills/wave/SKILL.md", ".claude/hooks/tool_use.py",
                "tools/git-hooks/install.sh", "tools/git-hooks/pre-commit"):
        assert (repo / rel).read_bytes() == (KIT / rel).read_bytes(), rel
    # the mode travels with the bytes (a hook that lost +x does not run)
    hook = repo / "tools" / "git-hooks" / "pre-commit"
    assert hook.stat().st_mode == (KIT / "tools/git-hooks/pre-commit").stat().st_mode
    # installing the hooks stays opt-in: nothing touched a hooks directory
    assert not (repo / ".git").exists()


def test_fresh_dry_run_names_the_merged_trees_and_gitignore(tmp_path, capsys):
    assert run("fresh", tmp_path) == 0
    out = capsys.readouterr().out
    assert "add  .claude/MAESTRO.md" in out
    assert "add  git-hooks/install.sh" in out
    assert "append  .gitignore" in out
    assert list(tmp_path.iterdir()) == [], "a dry run wrote files"


def _host_with_roster(tmp_path: Path) -> Path:
    repo = tmp_path / "host"
    agents = repo / ".claude" / "agents"
    agents.mkdir(parents=True)
    (agents / "builder.md").write_text("HOST builder", encoding="utf-8")
    (agents / "host_role.md").write_text("HOST role", encoding="utf-8")
    (repo / ".claude" / "settings.json").write_text('{"host": 1}',
                                                   encoding="utf-8")
    return repo


def test_adopt_merges_by_adding_and_reports_collisions(tmp_path, capsys):
    """Mutation: let a differing host file fall through to 'update' and
    the host's role sheet is replaced."""
    repo = _host_with_roster(tmp_path)
    assert run("adopt", repo, "--apply") == 0
    out = capsys.readouterr().out
    assert "COLLISION  .claude/agents/builder.md" in out
    assert "decision the host records" in out
    agents = repo / ".claude" / "agents"
    assert (agents / "builder.md").read_text(encoding="utf-8") == "HOST builder"
    assert (agents / "host_role.md").read_text(encoding="utf-8") == "HOST role"
    assert (agents / "reviewer.md").is_file(), "missing kit roles are added"
    assert (repo / ".claude" / "settings.json").read_text(
        encoding="utf-8") == '{"host": 1}'
    files = stamp_of(repo)["files"]
    assert ".claude/agents/reviewer.md" in files
    assert ".claude/agents/builder.md" not in files, (
        "a collision is the host's file, never on the kit's manifest")
    assert ".claude/agents/host_role.md" not in files


def test_force_never_overrides_a_collision_and_remove_keeps_host_files(
        tmp_path, capsys):
    """--force discards local edits to KIT files; a host-authored file is
    never the kit's, so neither --force upgrade nor --force remove may
    touch it. Mutation: delete every file under .claude/ on remove."""
    repo = _host_with_roster(tmp_path)
    assert run("adopt", repo, "--apply") == 0
    assert run("upgrade", repo, "--apply", "--force") == 0
    assert (repo / ".claude/agents/builder.md").read_text(
        encoding="utf-8") == "HOST builder"
    capsys.readouterr()
    assert run("remove", repo, "--apply", "--force") == 0
    assert "keep    .claude/" in capsys.readouterr().out
    assert (repo / ".claude/agents/builder.md").read_text(
        encoding="utf-8") == "HOST builder"
    assert (repo / ".claude/agents/host_role.md").is_file()
    assert (repo / ".claude/settings.json").is_file()
    assert not (repo / ".claude/agents/reviewer.md").exists()
    assert not (repo / ".claude/MAESTRO.md").exists()
    assert not (repo / "tools/git-hooks").exists()


def test_remove_drops_a_roster_it_wholly_added(tmp_path):
    repo = fresh(tmp_path)
    assert run("remove", repo, "--apply") == 0
    assert not (repo / ".claude").exists()
    assert not (repo / "tools").exists()


def test_settings_files_are_never_copied(tmp_path, monkeypatch):
    """Mutation: drop the _never_copied filter from _kit_files."""
    kit = tmp_path / "kit"
    for rel in (".claude/settings.json", ".claude/settings.local.json",
                ".claude/hooks/settings.json", ".claude/agents/a.md"):
        (kit / rel).parent.mkdir(parents=True, exist_ok=True)
        (kit / rel).write_text("x", encoding="utf-8")
    monkeypatch.setattr(bs, "KIT_ROOT", kit)
    assert bs._kit_files(".claude") == [".claude/agents/a.md"]
    assert not bs._never_copied("tools/wall/settings.json")


# --------------------------------------------------------------- .gitignore

def test_gitignore_block_is_appended_once_refreshed_and_stripped(tmp_path):
    """Mutations: append without looking for the block (duplicates),
    or strip more than the block (host lines lost)."""
    repo = tmp_path / "r"
    repo.mkdir()
    host = "node_modules/\n*.log\n"
    (repo / ".gitignore").write_text(host, encoding="utf-8")
    assert run("fresh", repo, "--apply") == 0
    text = (repo / ".gitignore").read_text(encoding="utf-8")
    assert text.startswith(host)
    for line in bs.GITIGNORE_LINES:
        assert line in text.splitlines()
    assert run("fresh", repo, "--apply") == 0
    assert run("upgrade", repo, "--apply") == 0
    assert (repo / ".gitignore").read_text(encoding="utf-8") == text, (
        "the block must be idempotent")
    # a hand edit inside the block is refreshed by upgrade; outside is kept
    tampered = text.replace(".wall/runs/\n", "") + "dist/\n"
    (repo / ".gitignore").write_text(tampered, encoding="utf-8")
    assert run("upgrade", repo, "--apply") == 0
    assert (repo / ".gitignore").read_text(encoding="utf-8") == text + "dist/\n"
    assert run("remove", repo, "--apply") == 0
    assert (repo / ".gitignore").read_text(encoding="utf-8") == host + "dist/\n"


@pytest.mark.parametrize("nl", [b"\r\n", b"\n"])
def test_gitignore_keeps_the_hosts_line_endings_byte_for_byte(tmp_path, nl):
    """Mutation: rewrite with the platform ending. read_text() folds CRLF to
    LF, so only a byte-level comparison sees every host line restyled."""
    repo = tmp_path / "r"
    repo.mkdir()
    host = b"node_modules/" + nl + b"*.log" + nl
    (repo / ".gitignore").write_bytes(host)
    assert run("fresh", repo, "--apply") == 0
    raw = (repo / ".gitignore").read_bytes()
    assert raw.startswith(host)
    if nl == b"\r\n":
        assert b"\n" not in raw.replace(b"\r\n", b""), "a bare LF crept in"
    else:
        assert b"\r\n" not in raw, "a CRLF crept in"
    assert run("remove", repo, "--apply") == 0
    assert (repo / ".gitignore").read_bytes() == host


def test_gitignore_the_kit_created_goes_on_remove(tmp_path):
    repo = fresh(tmp_path)
    assert (repo / ".gitignore").read_text(
        encoding="utf-8") == bs.gitignore_block()
    assert run("remove", repo, "--apply") == 0
    assert not (repo / ".gitignore").exists()


def test_gitignore_lines_match_the_standard():
    """The block is the WALL_STANDARDS section 2 list, not a copy that
    drifts from it."""
    std = (KIT / "docs" / "WALL_STANDARDS.md").read_text(encoding="utf-8")
    fence = std.split("Add to `.gitignore`:", 1)[1].split("```")[1]
    assert tuple(fence.split()) == bs.GITIGNORE_LINES


# ----------------------------------------------------------------- manifest

def test_stamp_records_a_sha256_per_kit_file(tmp_path):
    repo = fresh(tmp_path)
    files = stamp_of(repo)["files"]
    for rel in ("tools/wall/wall.py", "docs/WORKFLOW.md",
                "templates/RULES.md.template", ".claude/MAESTRO.md",
                "tools/git-hooks/install.sh"):
        assert files[rel] == bs._sha256(repo / rel), rel
    # context documents are the host's from the moment they are written
    assert "RULES.md" not in files and ".wall/config/wall.json" not in files


def test_upgrade_overwrites_a_file_that_matches_its_record(tmp_path):
    """An older kit's bytes, still exactly as recorded, are upgraded as
    before — no --force. Mutation: guard on 'differs from the kit'
    instead of 'differs from the record'."""
    repo = fresh(tmp_path)
    old = repo / "tools" / "wall" / "summary.py"
    old.write_text("# the previous kit's summary\n", encoding="utf-8")
    stamp = stamp_of(repo)
    stamp["files"]["tools/wall/summary.py"] = bs._sha256(old)
    write_stamp(repo, stamp)
    assert run("upgrade", repo, "--apply") == 0
    assert old.read_bytes() == (KIT / "tools/wall/summary.py").read_bytes()
    assert stamp_of(repo)["files"]["tools/wall/summary.py"] == bs._sha256(old)


def test_upgrade_refuses_a_modified_roster_file_and_changes_nothing(
        tmp_path, capsys):
    """All-or-nothing: one blocked file means no other file moves
    either. Mutation: execute the plan before the refusal check."""
    repo = fresh(tmp_path)
    edited = repo / ".claude" / "agents" / "builder.md"
    edited.write_text("local edit\n", encoding="utf-8")
    other = repo / "tools" / "wall" / "summary.py"
    stamp = stamp_of(repo)
    other.write_text("# previous kit\n", encoding="utf-8")
    stamp["files"]["tools/wall/summary.py"] = bs._sha256(other)
    write_stamp(repo, stamp)
    before = snapshot(repo)
    capsys.readouterr()
    assert run("upgrade", repo, "--apply") == 1
    out = capsys.readouterr().out
    assert "MODIFIED   .claude/agents/builder.md" in out
    assert "refusing: nothing was changed" in out
    assert snapshot(repo) == before
    assert run("upgrade", repo, "--apply", "--force") == 0
    assert edited.read_bytes() == (KIT / ".claude/agents/builder.md").read_bytes()


def test_upgrade_will_not_prune_an_unrecorded_stray_without_force(
        tmp_path, capsys):
    """Mutation: skip the guard in _plan_prune."""
    repo = fresh(tmp_path)
    stray = repo / "tools" / "wall" / "host_plugin.py"
    stray.write_text("# who wrote this?\n", encoding="utf-8")
    capsys.readouterr()
    assert run("upgrade", repo, "--apply") == 1
    assert "UNVERIFIED tools/wall/host_plugin.py" in capsys.readouterr().out
    assert stray.exists()
    assert run("upgrade", repo, "--apply", "--force") == 0
    assert not stray.exists()


def test_rerunning_fresh_does_not_launder_a_local_edit(tmp_path, capsys):
    """fresh/adopt block only a RECORDED file that was edited, so a first
    install is unchanged but a re-run cannot silently overwrite."""
    repo = fresh(tmp_path)
    edited = repo / "tools" / "wall" / "summary.py"
    edited.write_text("# mine\n", encoding="utf-8")
    capsys.readouterr()
    assert run("fresh", repo, "--apply") == 1
    assert "MODIFIED   tools/wall/summary.py" in capsys.readouterr().out
    assert edited.read_text(encoding="utf-8") == "# mine\n"
    assert run("adopt", repo, "--apply") == 1
    assert edited.read_text(encoding="utf-8") == "# mine\n"


def test_remove_refuses_a_modified_kit_file_and_changes_nothing(
        tmp_path, capsys):
    """Mutations: rmtree without guarding, or strip MCP/.gitignore before
    the refusal."""
    repo = fresh(tmp_path, "r", "--mcp", "claude-code")
    edited = repo / "tools" / "wall" / "summary.py"
    edited.write_text("# mine\n", encoding="utf-8")
    kit_added = repo / ".claude" / "agents" / "reviewer.md"
    kit_added.write_text("my reviewer\n", encoding="utf-8")
    template = repo / "templates" / "RULES.md.template"
    template.write_text("my template\n", encoding="utf-8")
    before = snapshot(repo)
    capsys.readouterr()
    assert run("remove", repo) == 1  # the dry run names the same refusal
    assert run("remove", repo, "--apply") == 1
    out = capsys.readouterr().out
    for rel in ("tools/wall/summary.py", ".claude/agents/reviewer.md",
                "templates/RULES.md.template"):
        assert f"MODIFIED   {rel}" in out
    assert snapshot(repo) == before, "a refused remove changed files"
    assert run("remove", repo, "--apply", "--force") == 0
    assert not (repo / "tools" / "wall").exists()
    assert not kit_added.exists() and not template.exists()
    assert (repo / "docs" / "WORKFLOW.md").is_file()
    files = stamp_of(repo)["files"]
    assert files and all(rel.startswith("docs/") for rel in files), (
        "after remove the manifest names only what is still on disk")


def test_remove_on_an_old_stamp_verifies_against_the_kit(tmp_path, capsys):
    """A stamp from before the manifest: a file identical to this kit's
    copy is safe to delete (nothing is lost); one that is not cannot be
    verified and needs --force. Mutation: treat 'no record' as safe."""
    repo = fresh(tmp_path)
    stamp = stamp_of(repo)
    del stamp["files"]
    write_stamp(repo, stamp)
    before = snapshot(repo)
    assert run("remove", repo, "--apply") == 0
    assert not (repo / "tools" / "wall").exists()
    # a .claude/ file is never the kit's without a record: the legacy
    # bootstrap never wrote one, so a copy there is the host's
    assert (repo / ".claude" / "MAESTRO.md").is_file()
    assert before  # the fresh tree existed

    repo2 = fresh(tmp_path, "r2")
    stamp = stamp_of(repo2)
    del stamp["files"]
    write_stamp(repo2, stamp)
    (repo2 / "tools" / "wall" / "summary.py").write_text("# ?\n",
                                                        encoding="utf-8")
    capsys.readouterr()
    assert run("upgrade", repo2, "--apply") == 1
    out = capsys.readouterr().out
    assert "predates the per-file manifest" in out
    assert "UNVERIFIED tools/wall/summary.py" in out
    assert run("remove", repo2, "--apply") == 1
    assert (repo2 / "tools" / "wall").exists()


def test_old_stamp_verifies_against_the_kit_blob_at_the_stamped_commit(
        tmp_path, monkeypatch):
    """The legacy fallback: bytes equal to the kit's blob at the stamped
    commit are an older kit, not a local edit. Mutation: drop the blob
    comparison from Ledger.status."""
    repo = fresh(tmp_path)
    older = repo / "tools" / "wall" / "summary.py"
    older.write_text("# the stamped kit's summary\n", encoding="utf-8")
    stamp = stamp_of(repo)
    del stamp["files"]
    write_stamp(repo, stamp)
    blob = bs._git_blob_id(older)
    monkeypatch.setattr(bs, "_git_ls_tree",
                        lambda commit: {"tools/wall/summary.py": blob})
    assert run("upgrade", repo, "--apply") == 0
    assert older.read_bytes() == (KIT / "tools/wall/summary.py").read_bytes()
    assert "files" in stamp_of(repo), "the upgrade writes the manifest"


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_git_blob_id_is_what_git_computes(tmp_path):
    f = tmp_path / "f.txt"
    f.write_bytes(b"line one\nline two\n")
    out = subprocess.run(["git", "hash-object", str(f)], capture_output=True,
                         text=True, check=True).stdout.strip()
    assert bs._git_blob_id(f) == out


def test_upgrade_dry_run_writes_nothing(tmp_path):
    repo = fresh(tmp_path)
    (repo / ".claude" / "MAESTRO.md").unlink()
    (repo / ".gitignore").write_text("host\n", encoding="utf-8")
    before = snapshot(repo)
    assert run("upgrade", repo) == 0
    assert snapshot(repo) == before


# ---------------------------------------------------------- remove --mcp

ALL = ("claude-code", "cursor", "vscode")


def test_remove_mcp_strips_only_the_named_clients(tmp_path):
    """Mutation: loop over every MCP_CONFIGS entry regardless of --mcp."""
    repo = fresh(tmp_path, "r", "--mcp", *ALL)
    assert run("remove", repo, "--apply", "--mcp", "cursor") == 0
    assert not (repo / ".cursor" / "mcp.json").exists()
    assert "wall" in json.loads(
        (repo / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]
    assert "wall" in json.loads(
        (repo / ".vscode" / "mcp.json").read_text(encoding="utf-8"))["servers"]


def test_remove_without_mcp_strips_all_three(tmp_path):
    repo = fresh(tmp_path, "r", "--mcp", *ALL)
    assert run("remove", repo, "--apply") == 0
    for rel in (".mcp.json", ".cursor/mcp.json", ".vscode/mcp.json"):
        assert not (repo / rel).exists(), rel


# ------------------------------------------------------ preflight + remove

def test_remove_runs_preflight(tmp_path, capsys):
    repo = fresh(tmp_path)
    capsys.readouterr()
    assert run("remove", repo) == 0
    out = capsys.readouterr().out
    assert "preflight" in out and "python 3." in out


def test_preflight_problems_never_stop_a_remove(tmp_path, monkeypatch,
                                                capsys):
    """An install on a too-old machine refuses; taking the kit OUT of one
    must not. Mutation: make the preflight gate apply to remove too."""
    repo = fresh(tmp_path)
    monkeypatch.setattr(bs, "preflight", lambda: ["Python 3.9 < 3.11"])
    assert run("fresh", tmp_path / "other", "--apply") == 2
    capsys.readouterr()
    assert run("remove", repo, "--apply") == 0
    assert "remove proceeds anyway" in capsys.readouterr().out
    assert not (repo / "tools" / "wall").exists()
