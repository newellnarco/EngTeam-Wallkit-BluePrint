"""The decision log: tolerant front-matter parsing and contradiction checks."""

from __future__ import annotations

import decisions


def write(repo, dec_id, body):
    d = repo / "docs" / "decisions"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{dec_id}.md").write_text(body, encoding="utf-8")


def fm(dec_id, **fields):
    lines = [f"{k}: {v}" for k, v in fields.items()]
    return "---\nid: %s\n%s\n---\n\n# %s -- ruling\n" % (
        dec_id, "\n".join(lines), dec_id)


# ------------------------------------------------------------ front matter

def test_parses_scalars_nulls_quotes_and_lists():
    fields, problems = decisions.parse_front_matter(
        '---\n'
        'id: DEC-0001\n'
        'superseded_by: null\n'
        'title: "A ruling: with a colon"\n'
        'scope: [backend/, tools/]\n'
        'tags:\n'
        '  - ledger\n'
        '  - merge\n'
        '# a comment line\n'
        '---\nbody\n')
    assert problems == []
    assert fields["superseded_by"] is None
    assert fields["title"] == "A ruling: with a colon"
    assert fields["scope"] == ["backend/", "tools/"]
    assert fields["tags"] == ["ledger", "merge"]


def test_a_file_with_no_front_matter_is_a_named_problem(repo):
    write(repo, "DEC-0099", "# notes from the call\n\nwe agreed something.\n")
    index = decisions.index(repo)
    assert index.decisions == {}
    assert index.problems[0]["kind"] == "front_matter"
    assert "does not open with" in index.problems[0]["detail"]


def test_an_unclosed_fence_is_reported_but_still_parsed():
    fields, problems = decisions.parse_front_matter("---\nid: DEC-0001\nstatus: active\n")
    assert fields["id"] == "DEC-0001"
    assert any("not closed" in p for p in problems)


def test_an_unparseable_line_is_skipped_not_fatal():
    fields, problems = decisions.parse_front_matter(
        "---\nid: DEC-0001\nthis line has no colon\nstatus: active\n---\n")
    assert fields["status"] == "active"
    assert any("unparseable" in p for p in problems)


def test_id_mismatch_and_unknown_status_are_reported(repo):
    write(repo, "DEC-0007", fm("DEC-0008", status="probably", scope="backend/"))
    index = decisions.index(repo)
    kinds = {p["kind"] for p in index.problems}
    assert "id_mismatch" in kinds and "unknown_status" in kinds
    assert "DEC-0008" in index.decisions      # front matter wins over the filename


def test_a_decision_with_no_scope_says_so(repo):
    write(repo, "DEC-0001", fm("DEC-0001", status="active"))
    assert any(p["kind"] == "no_scope" for p in decisions.index(repo).problems)


def test_missing_decisions_directory_is_not_a_problem(repo):
    index = decisions.index(repo)
    assert index.decisions == {} and index.problems == []


# ---------------------------------------------------------- contradictions

def test_supersedes_a_decision_that_is_still_active(repo):
    write(repo, "DEC-0001", fm("DEC-0001", status="active", scope="a/"))
    write(repo, "DEC-0002", fm("DEC-0002", status="active", scope="b/",
                               supersedes="DEC-0001"))
    kinds = [c["kind"] for c in decisions.contradictions(decisions.index(repo).decisions)]
    assert "supersedes_active" in kinds


def test_supersedes_something_that_does_not_exist(repo):
    write(repo, "DEC-0002", fm("DEC-0002", status="active", scope="b/",
                               supersedes="DEC-0001"))
    kinds = [c["kind"] for c in decisions.contradictions(decisions.index(repo).decisions)]
    assert "supersedes_missing" in kinds


def test_superseded_with_no_successor(repo):
    write(repo, "DEC-0001", fm("DEC-0001", status="superseded", scope="a/"))
    kinds = [c["kind"] for c in decisions.contradictions(decisions.index(repo).decisions)]
    assert "superseded_without_successor" in kinds


def test_active_while_naming_a_successor(repo):
    write(repo, "DEC-0001", fm("DEC-0001", status="active", scope="a/",
                               superseded_by="DEC-0002"))
    write(repo, "DEC-0002", fm("DEC-0002", status="active", scope="b/"))
    kinds = [c["kind"] for c in decisions.contradictions(decisions.index(repo).decisions)]
    assert "active_but_superseded" in kinds


def test_two_active_rulings_over_overlapping_scope(repo):
    write(repo, "DEC-0001", fm("DEC-0001", status="active", scope="backend/ledger/"))
    write(repo, "DEC-0002", fm("DEC-0002", status="active",
                               scope="backend/ledger/merge.py"))
    hits = [c for c in decisions.contradictions(decisions.index(repo).decisions)
            if c["kind"] == "overlapping_scope"]
    assert len(hits) == 1 and set(hits[0]["ids"]) == {"DEC-0001", "DEC-0002"}


def test_a_clean_supersession_chain_is_quiet(repo):
    write(repo, "DEC-0001", fm("DEC-0001", status="superseded", scope="a/",
                               superseded_by="DEC-0002"))
    write(repo, "DEC-0002", fm("DEC-0002", status="active", scope="a/",
                               supersedes="DEC-0001"))
    assert decisions.contradictions(decisions.index(repo).decisions) == []


def test_a_supersession_cycle_is_reported_once(repo):
    write(repo, "DEC-0001", fm("DEC-0001", status="superseded", scope="a/",
                               superseded_by="DEC-0002"))
    write(repo, "DEC-0002", fm("DEC-0002", status="superseded", scope="b/",
                               superseded_by="DEC-0001"))
    cycles = [c for c in decisions.contradictions(decisions.index(repo).decisions)
              if c["kind"] == "supersession_cycle"]
    assert len(cycles) == 1


def test_scopes_overlap_rules():
    assert decisions.scopes_overlap("backend/", "backend/ledger/merge.py")
    assert decisions.scopes_overlap("backend/**", "backend/ledger/merge.py")
    assert decisions.scopes_overlap("a/b/", "a/b/")
    assert not decisions.scopes_overlap("backend/", "frontend/")
    assert not decisions.scopes_overlap("", "backend/")
    # A prefix must stop at a path boundary, or backend/ would own backendfoo/.
    assert not decisions.scopes_overlap("backend", "backendfoo/x.py")


# --------------------------------------------------------------- in effect

def test_in_effect_matches_scope_and_keeps_referenced_superseded_rulings(repo):
    write(repo, "DEC-0001", fm("DEC-0001", status="superseded", scope="backend/",
                               superseded_by="DEC-0002"))
    write(repo, "DEC-0002", fm("DEC-0002", status="active", scope="backend/",
                               supersedes="DEC-0001"))
    write(repo, "DEC-0003", fm("DEC-0003", status="active", scope="frontend/"))
    index = decisions.index(repo)

    by_scope = [d["id"] for d in decisions.in_effect(index.decisions, ["backend/ledger/"])]
    assert by_scope == ["DEC-0002"]

    # A run that carried a superseded ruling is exactly what `wall why` has to
    # show, so an explicit reference pulls it back in.
    carried = [d["id"] for d in decisions.in_effect(
        index.decisions, ["backend/ledger/"], ["DEC-0001"])]
    assert carried == ["DEC-0001", "DEC-0002"]


def test_next_id_continues_the_numbering(repo):
    assert decisions.next_id({}) == "DEC-0001"
    write(repo, "DEC-0042", fm("DEC-0042", status="active", scope="a/"))
    assert decisions.next_id(decisions.index(repo).decisions) == "DEC-0043"


def test_write_decision_never_overwrites(repo):
    import pytest
    decisions.write_decision(repo, "DEC-0001",
                             decisions.render_skeleton("DEC-0001", "t", "q", "r"))
    with pytest.raises(FileExistsError):
        decisions.write_decision(repo, "DEC-0001", "different")


def test_a_written_skeleton_parses_back(repo):
    text = decisions.render_skeleton("DEC-0001", "A ruling", "why?", "because",
                                     scope="backend/", expert="Edmund")
    decisions.write_decision(repo, "DEC-0001", text)
    index = decisions.index(repo)
    assert index.problems == []
    assert index.decisions["DEC-0001"]["scope"] == ["backend/"]
    assert index.decisions["DEC-0001"]["status"] == "active"
