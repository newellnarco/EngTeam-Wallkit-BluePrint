"""Name lookback: a reused name must stay resolvable to the key that did the
work. The registry keeps every tenure row forever; `history` and `holder_at`
are the queries the Foreman and Maestro use to disambiguate, and `audit` flags
the one shape (overlapping tenures) that would make the answer untrustworthy.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from agents import AgentRegistry

AGENTS_PY = Path(__file__).resolve().parent.parent / "tools" / "wall" / "agents.py"


@pytest.fixture
def reused_name(repo):
    """Desmond serves two tenures under two keys, with a gap between them."""
    reg = AgentRegistry(repo)
    first = reg.claim("builder", "sess-1", name="Desmond")
    reg.release(first["key"])
    rows = reg.read()
    for r in rows:
        if r["key"] == first["key"]:
            r["claimed"], r["released"] = "2026-09-20T10:00:00Z", "2026-09-20T12:00:00Z"
    reg.write(rows)
    second = reg.claim("builder", "sess-2", name="Desmond")
    rows = reg.read()
    for r in rows:
        if r["key"] == second["key"]:
            r["claimed"] = "2026-09-21T09:00:00Z"
    reg.write(rows)
    return reg, first["key"], second["key"]


class TestHistory:
    def test_reused_name_returns_both_tenures_oldest_first(self, reused_name):
        reg, first_key, second_key = reused_name
        assert [r["key"] for r in reg.history("Desmond")] == [first_key, second_key]

    def test_unknown_name_is_empty_not_an_error(self, repo):
        assert AgentRegistry(repo).history("Nobody") == []


class TestHolderAt:
    def test_each_tenure_window_resolves_to_its_own_key(self, reused_name):
        reg, first_key, second_key = reused_name
        assert reg.holder_at("Desmond", "2026-09-20T11:00:00Z")["key"] == first_key
        assert reg.holder_at("Desmond", "2026-09-21T10:00:00Z")["key"] == second_key

    def test_the_gap_between_tenures_resolves_to_nobody(self, reused_name):
        reg, _, _ = reused_name
        assert reg.holder_at("Desmond", "2026-09-20T18:00:00Z") is None

    def test_before_the_first_claim_resolves_to_nobody(self, reused_name):
        reg, _, _ = reused_name
        assert reg.holder_at("Desmond", "2026-09-19T00:00:00Z") is None

    def test_the_release_instant_still_belongs_to_the_releasing_agent(self, reused_name):
        reg, first_key, _ = reused_name
        assert reg.holder_at("Desmond", "2026-09-20T12:00:00Z")["key"] == first_key

    def test_a_live_tenure_is_open_ended(self, reused_name):
        reg, _, second_key = reused_name
        assert reg.holder_at("Desmond", "2099-01-01T00:00:00Z")["key"] == second_key


class TestAuditTenureOverlap:
    def test_clean_reuse_is_not_a_problem(self, reused_name):
        reg, _, _ = reused_name
        assert reg.audit() == []

    def test_overlapping_released_tenures_are_flagged(self, reused_name):
        reg, first_key, _ = reused_name
        rows = reg.read()
        for r in rows:  # hand-edit: second tenure claimed inside the first
            if r["key"] != first_key and r["name"] == "Desmond":
                r["claimed"] = "2026-09-20T11:00:00Z"
                r["status"], r["released"] = "released", "2026-09-20T11:30:00Z"
        reg.write(rows)
        problems = reg.audit()
        assert any("tenure overlap" in p and "Desmond" in p for p in problems)

    def test_a_claim_during_a_live_tenure_of_a_released_row_is_flagged(self, repo):
        reg = AgentRegistry(repo)
        live = reg.claim("builder", "sess-1", name="Priya")
        rows = reg.read()
        for r in rows:  # open-ended live tenure starts before the hand edit below
            if r["key"] == live["key"]:
                r["claimed"] = "2026-09-21T09:00:00Z"
        rows.append({"key": "bld_999999", "name": "Priya", "role": "builder",
                     "status": "released", "session": "sess-2",
                     "claimed": "2026-09-21T10:00:00Z",
                     "released": "2026-09-21T11:00:00Z"})
        reg.write(rows)
        assert live["status"] == "live"
        assert any("tenure overlap" in p for p in reg.audit())


class TestWhoisCli:
    def run(self, repo, *args):
        return subprocess.run(
            [sys.executable, str(AGENTS_PY), "whois", "--repo", str(repo), *args],
            capture_output=True, text=True)

    def test_history_lists_every_key_that_held_the_name(self, reused_name):
        reg, first_key, second_key = reused_name
        out = self.run(reg.repo, "--name", "Desmond")
        assert out.returncode == 0
        assert first_key in out.stdout and second_key in out.stdout

    def test_at_resolves_the_single_key_for_that_instant(self, reused_name):
        reg, first_key, second_key = reused_name
        out = self.run(reg.repo, "--name", "Desmond", "--at", "2026-09-20T11:00:00Z")
        assert out.returncode == 0
        assert first_key in out.stdout and second_key not in out.stdout

    def test_a_miss_exits_nonzero_so_scripts_notice(self, repo):
        out = self.run(repo, "--name", "Nobody")
        assert out.returncode == 1
