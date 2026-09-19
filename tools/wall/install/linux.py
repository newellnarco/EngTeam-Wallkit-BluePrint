"""Linux adapter -- a systemd user timer, with a cron fallback.

A ``.timer`` plus a oneshot ``.service``, not a service that sleeps in a loop:
systemd then owns restart, catch-up and logging, and ``systemctl --user
list-timers`` answers "is the courier alive?" without anyone having to grep a
process table.

``OnUnitActiveSec`` measures from the end of the last run, so a slow sweep
cannot stack up behind itself. ``Persistent=true`` makes a missed window fire
once on resume rather than being skipped, which matters on a laptop that sleeps.

Where user systemd is unavailable (containers, minimal images, some
enterprise images with lingering disabled) :func:`build_cron_line` gives the
same cadence as a crontab line. Both are built as pure text and asserted by the
tests on any platform.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from . import Runner, run_command

UNIT = "wall-courier"
SERVICE_UNIT = "%s.service" % UNIT
TIMER_UNIT = "%s.timer" % UNIT


def unit_dir(home: Path | str | None = None) -> Path:
    """Where systemd user units live for the current user."""
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(home) if home is not None else (
        Path(xdg) if xdg else Path(os.path.expanduser("~")) / ".config")
    return base / "systemd" / "user"


def build_service_unit(python: str, sweeper: str) -> str:
    """The oneshot service the timer triggers. Pure."""
    return (
        "[Unit]\n"
        "Description=wall courier sweep\n"
        "\n"
        "[Service]\n"
        "Type=oneshot\n"
        "ExecStart=%s %s\n"
        # The sweep is bounded work; a hung git or a wedged filesystem must not
        # leave a courier running into the next trigger.
        "TimeoutStartSec=300\n"
        % (python, sweeper)
    )


def build_timer_unit(interval_seconds: int = 120) -> str:
    """The timer. Pure."""
    seconds = max(1, int(interval_seconds))
    return (
        "[Unit]\n"
        "Description=wall courier sweep every %ds\n"
        "\n"
        "[Timer]\n"
        "OnBootSec=1min\n"
        "OnUnitActiveSec=%ds\n"
        "AccuracySec=15s\n"
        "Persistent=true\n"
        "Unit=%s\n"
        "\n"
        "[Install]\n"
        "WantedBy=timers.target\n"
        % (seconds, seconds, SERVICE_UNIT)
    )


def build_cron_line(python: str, sweeper: str, interval_seconds: int = 120) -> str:
    """The crontab fallback. Pure.

    cron's finest granularity is one minute, so a sub-minute interval becomes
    every minute and anything else is rounded to whole minutes. An interval that
    does not divide 60 is expressed with ``*/n`` anyway: it is a cadence, and a
    cadence that drifts at the top of the hour is still a cadence.
    """
    minutes = max(1, round(interval_seconds / 60))
    spec = "* * * * *" if minutes <= 1 else "*/%d * * * *" % minutes
    return "%s %s %s" % (spec, python, sweeper)


def build_install_commands() -> list[list[str]]:
    """Reload, then enable and start the timer. Pure."""
    return [
        ["systemctl", "--user", "daemon-reload"],
        ["systemctl", "--user", "enable", "--now", TIMER_UNIT],
    ]


def build_verify_command() -> list[str]:
    """Key=value properties, not ``list-timers``: parseable and stable. Pure."""
    return ["systemctl", "--user", "show", TIMER_UNIT,
            "--property=LoadState,ActiveState,LastTriggerUSec,NextElapseUSecRealtime"]


def build_uninstall_command() -> list[str]:
    return ["systemctl", "--user", "disable", "--now", TIMER_UNIT]


def describe_install(python: str, sweeper: str, interval_seconds: int = 120,
                     *, home: Path | str | None = None) -> list[str]:
    """What ``install`` will do here, as consent-surface lines. Pure.

    Every adapter has one, with the same signature, so the install plan is
    written by the thing that will actually run rather than by a summary of it
    that can drift.
    """
    target_dir = unit_dir(home)
    lines = ["  file       %s" % (target_dir / SERVICE_UNIT),
             "  file       %s" % (target_dir / TIMER_UNIT)]
    lines += ["  schedule   %s" % " ".join(cmd) for cmd in build_install_commands()]
    lines.append("  (fallback where user systemd is unavailable: %s)"
                 % build_cron_line(python, sweeper, interval_seconds))
    return lines


def parse_show(stdout: str) -> dict:
    """``systemctl show`` output as ``{installed, running, last_run, error}``. Pure."""
    fields: dict[str, str] = {}
    for line in stdout.splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            fields[key.strip()] = value.strip()
    load_state = fields.get("LoadState", "")
    if load_state != "loaded":
        return {"installed": False, "running": False, "last_run": None,
                "error": "timer %s is %s" % (TIMER_UNIT, load_state or "unknown")}
    active = fields.get("ActiveState", "")
    last = fields.get("LastTriggerUSec") or None
    if last in ("n/a", ""):
        last = None
    return {
        "installed": True,
        "running": active == "active",
        "last_run": last,
        "error": None if active == "active" else "timer is %s" % (active or "unknown"),
    }


# ------------------------------------------------------------------ interface

def install(interval_seconds: int = 120, *, python: str | None = None,
            sweeper: str | None = None, run: Runner = run_command,
            write=None, home: Path | str | None = None) -> str:
    """Write both units and enable the timer. Returns what it created."""
    target_dir = unit_dir(home)
    service_text = build_service_unit(
        python or sys.executable,
        sweeper or str(Path(os.path.expanduser("~")) / ".wall" / "sweep_all.py"))
    timer_text = build_timer_unit(interval_seconds)

    for name, text in ((SERVICE_UNIT, service_text), (TIMER_UNIT, timer_text)):
        path = target_dir / name
        if write is None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        else:
            write(path, text)

    for cmd in build_install_commands():
        outcome = run(cmd)
        if outcome.returncode != 0:
            raise RuntimeError(
                "%s failed: %s\n  units written to %s -- where user systemd is "
                "unavailable, use the cron line instead:\n    %s"
                % (" ".join(cmd), (outcome.stderr or outcome.stdout).strip(), target_dir,
                   build_cron_line(python or sys.executable,
                                   sweeper or "~/.wall/sweep_all.py", interval_seconds)))
    return "systemd user units %s and %s in %s, every %ds" % (
        SERVICE_UNIT, TIMER_UNIT, target_dir, max(1, int(interval_seconds)))


def verify(*, run: Runner = run_command) -> dict:
    """``{installed, running, last_run, error}``. Never raises."""
    outcome = run(build_verify_command())
    if outcome.returncode != 0:
        return {"installed": False, "running": False, "last_run": None,
                "error": (outcome.stderr or outcome.stdout).strip()
                         or "user systemd unavailable"}
    return parse_show(outcome.stdout)


def uninstall(*, run: Runner = run_command, home: Path | str | None = None) -> None:
    """Disable the timer and remove both units. Absent is success."""
    run(build_uninstall_command())
    target_dir = unit_dir(home)
    for name in (TIMER_UNIT, SERVICE_UNIT):
        try:
            (target_dir / name).unlink(missing_ok=True)
        except OSError as exc:
            raise RuntimeError("could not remove %s: %s" % (target_dir / name, exc)) from exc
    run(["systemctl", "--user", "daemon-reload"])
