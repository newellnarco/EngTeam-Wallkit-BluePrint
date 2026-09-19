"""Platform adapters for the machine-wide courier timer.

One interface, three methods. See docs/INSTALL.md for why this is a single
machine-wide task walking a repo registry, rather than one task per repo.

    install(interval_seconds) -> str    # returns the path of what it created
    verify()                  -> dict   # {installed, running, last_run, error}
    uninstall()               -> None

Every adapter is currently a stub that raises with the manual command printed.
`wall run-once` works without any of them, so the system is usable today and the
adapters are a convenience, not a dependency.
"""

import platform


def get_adapter():
    system = platform.system()
    if system == "Windows":
        from . import windows
        return windows
    if system == "Darwin":
        from . import macos
        return macos
    from . import linux
    return linux
