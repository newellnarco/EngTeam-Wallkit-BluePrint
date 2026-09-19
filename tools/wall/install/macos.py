"""macOS adapter -- one LaunchAgent running the registry sweeper.

``StartInterval`` rather than a calendar interval: the sweep is a cadence, not
an appointment, and ``StartInterval`` survives sleep sanely (launchd fires once
on wake rather than replaying every missed slot).

``RunAtLoad`` is true so the first sweep happens at login instead of one
interval later, which is what makes the heartbeat fresh by the time anyone
looks at the wall.

The plist is built as a string by :func:`build_plist` -- pure, and asserted by
the tests on any platform. Writing it and calling ``launchctl`` are the two
side effects, both injectable.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from . import Runner, current_uid, run_command

LABEL = "com.wallkit.courier"


def plist_path(home: Path | str | None = None) -> Path:
    """Where the LaunchAgent lives for the current user."""
    base = Path(home) if home is not None else Path(os.path.expanduser("~"))
    return base / "Library" / "LaunchAgents" / ("%s.plist" % LABEL)


def build_plist(python: str, sweeper: str, interval_seconds: int = 120,
                *, log_dir: str | None = None) -> str:
    """The LaunchAgent plist, as text. Pure.

    XML-escaped: a user directory containing ``&`` is ordinary and would
    otherwise produce a plist launchd refuses to load, at login, silently.
    """
    logs = Path(log_dir) if log_dir else Path(os.path.expanduser("~")) / ".wall"
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0">\n'
        "<dict>\n"
        "  <key>Label</key>\n"
        "  <string>%s</string>\n"
        "  <key>ProgramArguments</key>\n"
        "  <array>\n"
        "    <string>%s</string>\n"
        "    <string>%s</string>\n"
        "  </array>\n"
        "  <key>StartInterval</key>\n"
        "  <integer>%d</integer>\n"
        "  <key>RunAtLoad</key>\n"
        "  <true/>\n"
        "  <key>StandardOutPath</key>\n"
        "  <string>%s</string>\n"
        "  <key>StandardErrorPath</key>\n"
        "  <string>%s</string>\n"
        "</dict>\n"
        "</plist>\n"
        % (_xml(LABEL), _xml(python), _xml(sweeper), max(1, int(interval_seconds)),
           _xml(str(logs / "courier.log")), _xml(str(logs / "courier.log")))
    )


def _xml(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;").replace('"', "&quot;"))


def build_install_command(path: Path | str, uid: str | None = None) -> list[str]:
    """``launchctl bootstrap`` for the current GUI domain. Pure."""
    return ["launchctl", "bootstrap", "gui/%s" % (uid or current_uid()), str(path)]


def build_verify_command(uid: str | None = None) -> list[str]:
    return ["launchctl", "print", "gui/%s/%s" % (uid or current_uid(), LABEL)]


def build_uninstall_command(uid: str | None = None) -> list[str]:
    return ["launchctl", "bootout", "gui/%s/%s" % (uid or current_uid(), LABEL)]


def describe_install(python: str, sweeper: str, interval_seconds: int = 120,
                     *, home: Path | str | None = None) -> list[str]:
    """What ``install`` will do here, as consent-surface lines. Pure.

    Every adapter has one, with the same signature, so the install plan is
    written by the thing that will actually run rather than by a summary of it
    that can drift.
    """
    target = plist_path(home)
    return [
        "  file       %s" % target,
        "  schedule   %s" % " ".join(build_install_command(target)),
        "  (LaunchAgent %s, StartInterval %ds, RunAtLoad)"
        % (LABEL, max(1, int(interval_seconds))),
    ]


def parse_print(stdout: str) -> dict:
    """``launchctl print`` output as ``{installed, running, last_run, error}``. Pure.

    ``last_run`` is None on purpose: ``launchctl print`` reports a last exit
    code, not a last run time. The courier's own ``heartbeat.json`` is the
    authority on when it last ran, and inventing a timestamp here would put a
    second, wronger answer beside it.
    """
    state = ""
    exit_code = None
    for line in stdout.splitlines():
        stripped = line.strip()
        if stripped.startswith("state = "):
            state = stripped.split("=", 1)[1].strip()
        elif stripped.startswith("last exit code = "):
            exit_code = stripped.split("=", 1)[1].strip()
    error = None
    if exit_code not in (None, "0", "(never exited)"):
        error = "last exit code %s" % exit_code
    return {"installed": True, "running": state == "running",
            "last_run": None, "error": error}


# ------------------------------------------------------------------ interface

def install(interval_seconds: int = 120, *, python: str | None = None,
            sweeper: str | None = None, run: Runner = run_command,
            write=None, home: Path | str | None = None) -> str:
    """Write the plist and bootstrap it. Returns what it created."""
    target = plist_path(home)
    text = build_plist(
        python or sys.executable,
        sweeper or str(Path(os.path.expanduser("~")) / ".wall" / "sweep_all.py"),
        interval_seconds)
    if write is None:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    else:
        write(target, text)
    # bootout first so a re-install replaces rather than colliding with itself;
    # an absent agent makes this a no-op and its failure is not interesting.
    run(build_uninstall_command())
    outcome = run(build_install_command(target))
    if outcome.returncode != 0:
        raise RuntimeError("launchctl bootstrap failed: %s\n  plist written to %s"
                           % ((outcome.stderr or outcome.stdout).strip(), target))
    return "LaunchAgent %s at %s, every %ds" % (LABEL, target, max(1, int(interval_seconds)))


def verify(*, run: Runner = run_command) -> dict:
    """``{installed, running, last_run, error}``. Never raises."""
    outcome = run(build_verify_command())
    if outcome.returncode != 0:
        return {"installed": False, "running": False, "last_run": None,
                "error": (outcome.stderr or outcome.stdout).strip()
                         or "no %s agent loaded" % LABEL}
    return parse_print(outcome.stdout)


def uninstall(*, run: Runner = run_command, home: Path | str | None = None) -> None:
    """Bootout the agent and remove the plist. Absent is success."""
    run(build_uninstall_command())
    try:
        plist_path(home).unlink(missing_ok=True)
    except OSError as exc:
        raise RuntimeError("could not remove %s: %s" % (plist_path(home), exc)) from exc
