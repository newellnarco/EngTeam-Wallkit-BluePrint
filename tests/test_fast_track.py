"""`wall classify` and `wall fast-track`: routing, refusal, and local gates.

No test here runs git. Classification is pure and the command takes explicit
`--file` paths, which is also how a human takes the split the command offers.
"""

from __future__ import annotations

import argparse
import json

import items
import wall

CFG = {
    "allow": ["**/*.md", "MANIFEST.sha256"],
    "deny": ["backend/**/*.py", "tools/**", ".github/workflows/**", "**/CLAUDE.md"],
    "significant": ["docs/architecture/**", "docs/decisions/**"],
}


def args(repo, **kw):
    kw.setdefault("file", [])
    kw.setdefault("staged", False)
    kw.setdefault("stage", False)
    kw.setdefault("commit", False)
    kw.setdefault("allow_main", False)
    kw.setdefault("message", None)
    kw.setdefault("item", None)
    kw.setdefault("trace", None)
    kw.setdefault("session", "s_human")
    return argparse.Namespace(repo=str(repo), **kw)


# ------------------------------------------------------------ classification

def test_docs_only_takes_the_fast_track():
    result = wall.classify_files(["README.md", "docs/md/NOTES.md"], CFG)
    assert result["route"] == "fast_track"
    assert result["mixed"] is False
    assert all(r["verdict"] == "allow" for r in result["rows"])


def test_deny_beats_allow_for_claude_md():
    # It matches **/*.md, but it changes the behaviour of every future agent.
    result = wall.classify_files(["CLAUDE.md"], CFG)
    assert result["route"] == "full_track"
    assert result["rows"][0]["rule"] == "**/CLAUDE.md"


def test_double_star_matches_zero_directories():
    # Plain fnmatch reads '**/x' as "at least one directory, then x", so a
    # root-level CLAUDE.md slipped past the deny rule the docs defend.
    assert wall.glob_match("CLAUDE.md", "**/CLAUDE.md")
    assert wall.glob_match("backend/CLAUDE.md", "**/CLAUDE.md")
    assert wall.glob_match("README.md", "**/*.md")
    assert wall.glob_match("docs/a.docx", "docs/**/*.docx")
    assert not wall.glob_match("notes.txt", "**/*.md")


def test_workflow_edits_never_fast_track():
    result = wall.classify_files([".github/workflows/ci.yml"], CFG)
    assert result["route"] == "full_track"


def test_a_path_matching_no_rule_is_full_track_not_a_default_pass():
    result = wall.classify_files(["src/unknown.rs"], CFG)
    assert result["route"] == "full_track"
    assert result["rows"][0]["rule"] is None


def test_a_mixed_changeset_is_mixed_and_full_track():
    result = wall.classify_files(["README.md", "backend/ledger/merge.py"], CFG)
    assert result["route"] == "full_track" and result["mixed"] is True
    assert result["fast"] == ["README.md"]
    assert result["full"] == ["backend/ledger/merge.py"]


def test_architecture_docs_are_flagged_significant():
    result = wall.classify_files(["docs/architecture/LEDGER.md"], CFG)
    assert result["route"] == "fast_track"
    assert result["significant"] == ["docs/architecture/LEDGER.md"]


def test_no_files_is_not_a_fast_track():
    assert wall.classify_files([], CFG)["route"] == "full_track"


# -------------------------------------------------------------- the command

def clean_repo(repo, config):
    config({"fast_track": CFG, "decisions_dir": "docs/decisions"})
    (repo / "README.md").write_text("hi\n", encoding="utf-8")
    items.append_event(repo, "s_a", {"event": "item_created", "item_id": "ST-1"})
    items.rebuild(repo)


def test_fast_track_passes_the_gates_on_a_clean_repo(repo, config, capsys):
    clean_repo(repo, config)
    assert wall.cmd_fast_track(args(repo, file=["README.md"])) == 0
    out = capsys.readouterr().out
    assert "route: fast_track" in out
    assert "local gates: clean" in out
    assert "does not push and does not merge" in out


def test_fast_track_refuses_a_mixed_changeset_and_offers_the_split(repo, config, capsys):
    clean_repo(repo, config)
    rc = wall.cmd_fast_track(args(repo, file=["README.md", "backend/x.py"]))
    out = capsys.readouterr().out
    assert rc == 1
    assert "refusing a mixed changeset" in out
    assert "wall fast-track --file README.md" in out
    assert "backend/x.py" in out


def test_fast_track_blocks_on_a_ledger_schema_failure(repo, config, capsys):
    clean_repo(repo, config)
    shard = repo / ".wall" / "events" / "2026-09-19" / "s_b.jsonl"
    shard.write_text(json.dumps({"schema_version": 1, "event_id": "x", "seq": 1,
                                 "ts": "t", "session_id": "s_b", "event": "run_start"})
                     + "\n"
                     + json.dumps({"schema_version": 1, "event_id": "y", "seq": 3,
                                   "ts": "t", "session_id": "s_b", "event": "run_end"})
                     + "\n", encoding="utf-8")
    assert wall.cmd_fast_track(args(repo, file=["README.md"])) == 1
    assert "ledger-schema: seq_gap" in capsys.readouterr().out


def test_fast_track_blocks_on_item_state_drift(repo, config, capsys):
    clean_repo(repo, config)
    path = repo / ".wall" / "items" / "ST-1.json"
    record = json.loads(path.read_text())
    record["status"] = "invented"
    path.write_text(items.serialize_item(record), encoding="utf-8")
    assert wall.cmd_fast_track(args(repo, file=["README.md"])) == 1
    assert "item-state:" in capsys.readouterr().out


def test_fast_track_blocks_on_broken_decision_front_matter(repo, config, capsys):
    clean_repo(repo, config)
    (repo / "docs" / "decisions").mkdir(parents=True)
    (repo / "docs" / "decisions" / "DEC-0001.md").write_text(
        "# no front matter here\n", encoding="utf-8")
    assert wall.cmd_fast_track(args(repo, file=["README.md"])) == 1
    assert "decision-front-matter" in capsys.readouterr().out


def test_a_contradiction_warns_but_does_not_block(repo, config, capsys):
    clean_repo(repo, config)
    (repo / "docs" / "decisions").mkdir(parents=True)
    for dec_id in ("DEC-0001", "DEC-0002"):
        (repo / "docs" / "decisions" / f"{dec_id}.md").write_text(
            f"---\nid: {dec_id}\nstatus: active\nscope: backend/\n---\n\n# {dec_id}\n",
            encoding="utf-8")
    assert wall.cmd_fast_track(args(repo, file=["README.md"])) == 0
    out = capsys.readouterr().out
    assert "warn   decision-contradiction" in out
    assert "local gates: clean" in out


def test_no_changes_is_a_clean_no_op(repo, config, capsys):
    clean_repo(repo, config)
    # No --file and no git repo: `git diff` returns nothing, which is honest.
    assert wall.cmd_fast_track(args(repo)) == 0
    assert "no changes" in capsys.readouterr().out


def test_gates_report_both_directions_of_the_seq_property(repo, config):
    clean_repo(repo, config)
    shard = repo / ".wall" / "events" / "2026-09-19" / "s_b.jsonl"
    rows = [{"schema_version": 1, "event_id": e, "seq": s, "ts": "t",
             "session_id": "s_b", "event": "run_end"}
            for e, s in (("a", 1), ("b", 2), ("c", 2))]
    shard.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    blocking, _ = wall.fast_track_gates(repo, {"decisions_dir": "docs/decisions"})
    assert any("seq_duplicate" in b["detail"] for b in blocking)
