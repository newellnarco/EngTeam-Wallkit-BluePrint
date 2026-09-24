"""The shared lock (agents.acquire_lock / release_lock).

It guards the agent registry (singletons) and open_runs.json (role caps), so
a lock that two holders can hold at once silently bypasses both. The lock is
an OS advisory lock held on an open descriptor, never the lock file's
existence, which removes the three ways a file-existence lock failed:

- a waiter that guessed a live holder was dead broke its lock;
- two waiters breaking the same stale lock could delete each other's;
- a holder releasing by path could delete a lock someone else had retaken.

Here: a live holder is never taken over however long it holds; a holder that
dies frees the lock with no stale age at all; and release acts only on the
holder's own descriptor, never on the path.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

import agents

AGENTS_DIR = Path(agents.__file__).resolve().parent


def test_a_live_holder_is_never_taken_over_however_old(tmp_path):
    """Mutation: acquire ignores the OS lock (plain open)."""
    lock = tmp_path / "x.lock"
    fd = agents.acquire_lock(lock, timeout=1.0)
    old = time.time() - 86400
    os.utime(lock, (old, old))  # age is irrelevant: the holder is alive
    try:
        with pytest.raises(TimeoutError, match="locked"):
            agents.acquire_lock(lock, timeout=0.2)
    finally:
        agents.release_lock(fd)
    agents.release_lock(agents.acquire_lock(lock, timeout=0.2))


def test_a_leftover_lock_file_with_no_holder_is_free(tmp_path):
    lock = tmp_path / "x.lock"
    lock.write_text("left by a crash")
    fd = agents.acquire_lock(lock, timeout=0.2)
    agents.release_lock(fd)


def test_a_holder_that_dies_frees_the_lock_at_once(tmp_path):
    """No stale age: the kernel drops a dead process's lock."""
    lock = tmp_path / "x.lock"
    child = subprocess.Popen(
        [sys.executable, "-c", textwrap.dedent(f"""
            import sys, time
            sys.path.insert(0, {str(AGENTS_DIR)!r})
            import agents
            agents.acquire_lock(__import__("pathlib").Path({str(lock)!r}), 5.0)
            print("held", flush=True)
            time.sleep(60)
        """)], stdout=subprocess.PIPE, text=True)
    try:
        assert child.stdout.readline().strip() == "held"
        with pytest.raises(TimeoutError):
            agents.acquire_lock(lock, timeout=0.2)
        child.kill()
        child.wait(10)
        agents.release_lock(agents.acquire_lock(lock, timeout=2.0))
    finally:
        child.kill()
        child.stdout.close()


def test_release_frees_only_the_holders_own_descriptor(tmp_path):
    """Mutation: release_lock unlinks the lock path.

    Deleting the path would let a newcomer lock a fresh file while the
    current holder still holds the old inode -- two holders at once."""
    lock = tmp_path / "x.lock"
    first = agents.acquire_lock(lock, timeout=1.0)
    agents.release_lock(first)
    second = agents.acquire_lock(lock, timeout=1.0)
    try:
        agents.release_lock(None)  # a holder with nothing to release
        with pytest.raises(TimeoutError):
            agents.acquire_lock(lock, timeout=0.2)
        assert lock.exists(), "the lock file is never removed"
    finally:
        agents.release_lock(second)


def test_the_registry_releases_once_and_only_its_own(tmp_path):
    reg = agents.AgentRegistry(tmp_path)
    reg._acquire(timeout=1.0)
    with pytest.raises(TimeoutError):
        agents.AgentRegistry(tmp_path)._acquire(timeout=0.2)
    reg._release_lock()
    reg._release_lock()  # a second release is a no-op, not a stray close
    other = agents.AgentRegistry(tmp_path)
    other._acquire(timeout=0.2)
    reg._release_lock()  # must not free other's lock
    with pytest.raises(TimeoutError):
        agents.AgentRegistry(tmp_path)._acquire(timeout=0.2)
    other._release_lock()
