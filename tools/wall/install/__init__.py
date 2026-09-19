"""Platform adapters for the machine-wide courier timer.

One interface, three methods. See docs/INSTALL.md for why this is a single
machine-wide task walking a repo registry, rather than one task per repo:
ten repos means ten tasks and ten chances for an orphan pointing at a deleted
directory firing every two minutes forever and failing silently.

    install(interval_seconds, *, python, sweeper, run) -> str
    verify(*, run)                                     -> dict
    uninstall(*, run)                                  -> None

``install`` returns a human-readable description of what it created.
``verify`` returns ``{installed, running, last_run, error}`` and never raises.
``uninstall`` is idempotent: removing an absent task is a success.

**Every adapter separates command construction from execution.** The
``build_*`` functions are pure -- they take a python path, a sweeper path and
an interval and return the exact argv, plist or unit file as data. That is what
the tests assert, on any platform, without a scheduler anywhere near them. The
three interface methods are thin wrappers that hand those commands to an
injectable ``run``. A scheduler command that is wrong is then a test failure and
not a mystery on someone's box.

``wall run-once`` works without any adapter, so this whole directory is a
convenience and never a dependency.
"""

from __future__ import annotations

import os
import platform
import subprocess
from collections.abc import Callable

#: Signature of an injectable command runner.
Runner = Callable[..., "subprocess.CompletedProcess[str]"]

#: Wall-clock bound on every scheduler call. These are local control-plane
#: commands; anything slower than this is hung, and a hung install looks
#: identical to a slow one.
COMMAND_TIMEOUT_S = 30


def run_command(cmd: list[str], *, timeout: int = COMMAND_TIMEOUT_S
                ) -> subprocess.CompletedProcess[str]:
    """Run one scheduler command: captured, windowless, utf-8 pinned, bounded.

    A timeout or a missing executable comes back as a non-zero result with the
    reason on stderr, never as an exception -- ``verify`` in particular is
    documented not to raise.
    """
    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(
            cmd, returncode=124, stdout="",
            stderr="%s timed out after %ss" % (cmd[0] if cmd else "command", timeout))
    except (OSError, ValueError) as exc:
        return subprocess.CompletedProcess(
            cmd, returncode=127, stdout="", stderr="could not run %r: %s" % (cmd, exc))


def current_uid() -> str:
    """The launchctl/systemd user id, as a string. ``"0"`` where there is none.

    Windows has no ``os.getuid``; the macOS and Linux command builders still
    have to be constructible there so their tests can run anywhere.
    """
    getuid = getattr(os, "getuid", None)
    return str(getuid()) if callable(getuid) else "0"


def get_adapter(system: str | None = None):
    """The adapter for ``system`` (default: this machine). Importable anywhere."""
    name = (system or platform.system()).strip()
    if name == "Windows":
        from . import windows
        return windows
    if name == "Darwin":
        from . import macos
        return macos
    from . import linux
    return linux
