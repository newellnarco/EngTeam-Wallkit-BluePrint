"""The cautionary notice is a standing owner directive: the kit amplifies an
existing team and does not endorse replacing human roles. Pinned so no
rewrite of the README's opening can silently drop it."""

from pathlib import Path

README = Path(__file__).resolve().parents[1] / "README.md"


def test_the_title_says_what_this_really_is():
    head = README.read_text(encoding="utf-8")[:600]
    assert head.startswith("# The AI Engineering Organization"), \
        "the H1 must name the organization blueprint, not the wall"
    flat = " ".join(head.replace("**", "").split())
    assert "governed by the humans it" in flat
    assert "The status wall is just its visible surface" in flat


def test_the_caution_notice_leads_the_readme():
    t = README.read_text(encoding="utf-8")
    head = t[:2500]  # must be at the very top, before any section
    assert "[!CAUTION]" in head, "GitHub red-alert block missing from the README head"
    flat = " ".join(head.replace(">", " ").replace("**", "").split())
    assert "does not endorse" in flat
    for role in ("decision makers", "architects", "designers",
                 "program managers", "engineering", "any other role"):
        assert role in flat, f"notice missing role: {role}"
    assert "existing" in flat and "team" in flat
    assert "quality," in flat and "secure," in flat and "scalable," in flat
    assert "enterprise-grade" in flat
