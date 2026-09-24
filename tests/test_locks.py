"""The shared O_EXCL lock (agents.acquire_lock / release_lock).

It guards the agent registry (singletons) and open_runs.json (role caps), so
a lock that two holders can hold at once silently bypasses both. Three ways
that used to happen are pinned here:

- a stale threshold shorter than a real hold let a waiter break a live lock;
- two waiters that both saw the same stale lock could each break it, the
  second deleting the first's fresh lock;
- a holder whose lock had been broken and retaken deleted the new holder's
  lock on release.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

import agents


def _age(path: Path, seconds: float) -> None:
    t = time.time() - seconds
    os.utime(path, (t, t))


def test_the_default_stale_age_is_far_above_a_real_hold(tmp_path):
    """Mutation: default stale age back to the timeout (10 s)."""
    assert agents.LOCK_STALE_S >= 120
    lock = tmp_path / "x.lock"
    lock.write_text("live-holder")
    _age(lock, 30)  # a slow but live holder: 30 s into its hold
    with pytest.raises(TimeoutError):
        agents.acquire_lock(lock, timeout=0.2)
    assert lock.read_text() == "live-holder", "a live lock was broken"


def test_a_dead_holders_lock_is_broken_and_retaken(tmp_path):
    lock = tmp_path / "x.lock"
    lock.write_text("dead-holder")
    _age(lock, agents.LOCK_STALE_S + 60)
    token = agents.acquire_lock(lock, timeout=1.0)
    assert lock.read_text() == token
    assert not list(tmp_path.glob("x.lock.stale-*")), "the broken lock is removed"
    agents.release_lock(lock, token)
    assert not lock.exists()


def test_a_second_breaker_cannot_delete_the_first_breakers_fresh_lock(tmp_path, monkeypatch):
    """Mutation: break a stale lock with unlink instead of rename.

    Waiter B sees the stale lock; before B acts, waiter A breaks it and
    creates its own. B's break must then find nothing to take -- with a bare
    unlink it deleted A's live lock and both held it."""
    lock = tmp_path / "x.lock"
    lock.write_text("dead-holder")
    _age(lock, agents.LOCK_STALE_S + 60)
    state = {"a_token": None}
    real_rename = os.rename

    def racing_rename(src, dst):
        if state["a_token"] is None:
            # A wins the break first, then creates its fresh lock.
            real_rename(src, str(dst) + "-a")
            Path(str(dst) + "-a").unlink()
            fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, b"A-fresh")
            os.close(fd)
            state["a_token"] = "A-fresh"
            raise FileNotFoundError(src)  # B's rename of the old lock: gone
        return real_rename(src, dst)

    monkeypatch.setattr(agents.os, "rename", racing_rename)
    with pytest.raises(TimeoutError):
        agents.acquire_lock(lock, timeout=0.3)  # B must wait, not steal
    assert lock.read_text() == "A-fresh", "B deleted A's live lock"


def test_release_leaves_a_lock_that_is_no_longer_ours(tmp_path):
    """Mutation: release_lock ignores the token."""
    lock = tmp_path / "x.lock"
    token = agents.acquire_lock(lock, timeout=1.0)
    lock.write_text("someone-else")  # ours was broken and retaken
    agents.release_lock(lock, token)
    assert lock.read_text() == "someone-else"
    agents.release_lock(lock, "someone-else")
    assert not lock.exists()


def test_the_registry_releases_only_its_own_lock(tmp_path):
    reg = agents.AgentRegistry(tmp_path)
    reg._acquire(timeout=1.0)
    reg.lock.write_text("someone-else")
    reg._release_lock()
    assert reg.lock.read_text() == "someone-else"
