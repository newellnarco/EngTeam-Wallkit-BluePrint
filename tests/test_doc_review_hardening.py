"""Review-round hardening on DEC-0032 (CodeRabbit on the reference
deployment's #1674): the docs payload must not read outside the repo, the
content cap is a byte budget, verdict controls exist only for a document the
reviewer actually read, one pending verdict locks its whole bar, and a
resolve_blocked dispatch carries the reason its agent starts from.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

import contracts as c
import courier

TEMPLATE = (Path(courier.__file__).parent / "render" /
            "wall_template.html").read_text(encoding="utf-8")


# --------------------------------------------------------------- contracts

class TestResolveBlockedReason:
    def test_a_blank_reason_is_refused(self):
        with pytest.raises(ValueError, match="reason"):
            c.EnqueuePayload(directive=c.Directive.RESOLVE_BLOCKED,
                             mode="build", item_id="x:1", reason="  ",
                             title="Unblock x:1")

    def test_a_real_reason_passes_and_serializes(self):
        p = c.EnqueuePayload(directive=c.Directive.RESOLVE_BLOCKED,
                             mode="research", item_id="x:1",
                             reason="upstream API undocumented",
                             title="Research x:1 blocker")
        assert p.to_dict()["reason"] == "upstream API undocumented"


class TestDocReviewShaBinding:
    """A verdict must name the revision that was read: without the sha, a
    document edited between fetch and verdict cannot be detected stale."""

    def test_a_missing_sha_is_refused(self):
        with pytest.raises(ValueError, match="sha"):
            c.EnqueuePayload(directive=c.Directive.DOC_REVIEW,
                             action="approve", path="RULES.md",
                             title="Approve document RULES.md")

    def test_a_blank_sha_is_refused(self):
        with pytest.raises(ValueError, match="sha"):
            c.EnqueuePayload(directive=c.Directive.DOC_REVIEW,
                             action="deny", path="RULES.md", sha="  ",
                             reason="stale guidance",
                             title="Deny document RULES.md")

    def test_a_bound_verdict_passes(self):
        p = c.EnqueuePayload(directive=c.Directive.DOC_REVIEW,
                             action="approve", path="RULES.md",
                             sha="abc123def456",
                             title="Approve document RULES.md")
        assert p.to_dict()["sha"] == "abc123def456"


# ------------------------------------------------------- docs.json payload

def _payload(repo, registry):
    return courier.build_docs_payload(
        Path(repo), {"documents_of_record": registry})["docs"]


class TestDocsPayloadContainment:
    """docs.json is SERVED, so the registry must not be able to publish a
    file from outside the repository."""

    def test_an_absolute_path_is_refused_not_read(self, tmp_path):
        secret = tmp_path / "outside.txt"
        secret.write_text("host secret", encoding="utf-8")
        repo = tmp_path / "repo"
        repo.mkdir()
        (d,) = _payload(repo, [str(secret)])
        assert d["content"] is None and d["sha"] is None
        assert "repository-relative" in d["note"]

    def test_a_dotdot_escape_is_refused_not_read(self, tmp_path):
        (tmp_path / "outside.txt").write_text("host secret", encoding="utf-8")
        repo = tmp_path / "repo"
        repo.mkdir()
        (d,) = _payload(repo, ["../outside.txt"])
        assert d["content"] is None
        assert "outside this repo" in d["note"]

    def test_a_symlink_pointing_outside_is_refused(self, tmp_path):
        (tmp_path / "outside.txt").write_text("host secret", encoding="utf-8")
        repo = tmp_path / "repo"
        repo.mkdir()
        link = repo / "RULES.md"
        try:
            os.symlink(tmp_path / "outside.txt", link)
        except (OSError, NotImplementedError):  # pragma: no cover - no symlink priv
            pytest.skip("symlinks unavailable here")
        (d,) = _payload(repo, ["RULES.md"])
        assert d["content"] is None
        assert "outside this repo" in d["note"]

    def test_an_ordinary_repo_file_still_reads(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "RULES.md").write_text("the rules", encoding="utf-8")
        (d,) = _payload(repo, ["RULES.md"])
        assert d["content"] == "the rules" and d["sha"]


class TestDocsPayloadByteCap:
    def test_the_cap_bounds_encoded_bytes_not_characters(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        # 3 bytes per character: fewer CHARACTERS than the cap, more BYTES.
        chars = courier.DOC_CONTENT_CAP // 3 + 100
        (repo / "big.md").write_bytes(("—" * chars).encode("utf-8"))
        (d,) = _payload(repo, ["big.md"])
        assert d["truncated"] is True
        assert len(d["content"].encode("utf-8")) <= courier.DOC_CONTENT_CAP + 3
        assert isinstance(d["content"], str)  # boundary split decodes, never raises


# ---------------------------------------------------------------- template

class TestVerdictBarDiscipline:
    def test_controls_render_only_for_readable_fetched_content(self):
        # the loading modal carries no bar, and the ONLY call site passes the
        # FETCHED doc (the second occurrence is the function definition)
        assert "loading document\\u2026</div>');" in TEMPLATE
        assert "d.content !== null ? docReviewBar(d)" in TEMPLATE
        assert TEMPLATE.count("docReviewBar(") == 2

    def test_busy_locks_the_bar_not_one_button(self):
        handler = TEMPLATE[TEMPLATE.index("[data-doc-act]'"):
                           TEMPLATE.index("function paintPosture")]
        assert "bar.dataset.busy === '1'" in handler
        assert "bar.dataset.busy = '1'" in handler
        assert "b.dataset.busy" not in handler
