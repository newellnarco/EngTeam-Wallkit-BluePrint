"""Windows adapter -- one scheduled task, driving the registry sweeper.

Registers one machine-wide scheduled task driving `wall run-once` for every
registered repo (e.g. repo at C:\\Repos\\your-repo, deployed copy elsewhere).

``schtasks.exe`` rather than PowerShell's ``Register-ScheduledTask``. Both can
create the task; ``schtasks.exe`` is a plain argv with no quoting layer between
us and the scheduler, and no dependency on which PowerShell is on PATH. That
second point is a measured one in this tree (F-PS-001: Windows 10/11 default to
PowerShell 5.1, whose cmdlets differ from 7's, and scripts that assumed
otherwise shipped broken). The equivalent PowerShell is kept below as
``MANUAL`` so the task can still be created by hand.

``/SC MINUTE /MO <n>`` is the two-minute repetition: schtasks expresses the
cadence in whole minutes, so a sub-minute interval is rounded up to one rather
than silently becoming "every minute" or failing.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from . import Runner, run_command

TASK_NAME = "WallCourier"

REGISTRY = Path(os.environ.get("USERPROFILE", "~")).expanduser() / ".wall" / "registry.json"

MANUAL = r"""
# The PowerShell equivalent, if you would rather create the task by hand.
# pythonw.exe, not python.exe: the console binary flashes a command window
# at the desktop on every firing (windowless_python below has the full why).
# Non-terminating lookup with a python fallback, mirroring windowless_python:
# a stripped install without pythonw still gets a working (visible) courier.
$py_cmd  = Get-Command pythonw -ErrorAction SilentlyContinue
if (-not $py_cmd) { $py_cmd = Get-Command python }
$py      = $py_cmd.Source
$sweeper = "$env:USERPROFILE\.wall\sweep_all.py"

$action  = New-ScheduledTaskAction -Execute $py -Argument $sweeper
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) `
           -RepetitionInterval (New-TimeSpan -Minutes 2) `
           -RepetitionDuration ([TimeSpan]::MaxValue)
$set     = New-ScheduledTaskSettingsSet -StartWhenAvailable `
           -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 5)

Register-ScheduledTask -TaskName "WallCourier" -Action $action `
    -Trigger $trigger -Settings $set -Description "wall courier sweep"

Get-ScheduledTaskInfo -TaskName "WallCourier"   # LastRunTime, LastTaskResult
Unregister-ScheduledTask -TaskName "WallCourier" -Confirm:$false
"""


def interval_minutes(interval_seconds: int) -> int:
    """Whole minutes for ``/MO``. Rounds up; never below 1."""
    return max(1, round(interval_seconds / 60))


def windowless_python(python: str) -> str:
    """The interpreter the TASK should launch: ``pythonw.exe`` when it exists
    beside the given ``python.exe``, else the given interpreter unchanged.

    ``python.exe`` is a CONSOLE-subsystem binary: a scheduled task that
    launches it on an interactive desktop flashes a command window at the
    user on EVERY firing -- at the default two-minute cadence, that is a
    console popping "every little bit" (owner report on the reference
    deployment, 2026-09-22; the same host had already paid for this class
    once with its own auto-pull task and fixed it with a hidden launcher).
    ``pythonw.exe`` ships beside ``python.exe`` in every CPython install and
    venv, is the same interpreter built for the GUI subsystem, and opens no
    window. The sweeper writes its outcome to the ledger and heartbeat, so
    losing the (never-seen) console output costs nothing. When ``pythonw``
    is genuinely absent, the visible interpreter is still a working courier,
    so we degrade to it rather than refusing to install.
    """
    candidate = Path(python).with_name("pythonw.exe")
    if candidate.is_file():
        return str(candidate)
    return python


def task_command(python: str, sweeper: str) -> str:
    """The ``/TR`` string: the interpreter and the sweeper, each quoted.

    Both paths routinely contain spaces on Windows (``C:\\Program Files``,
    ``C:\\Users\\First Last``), and ``/TR`` is one string the scheduler splits
    itself, so the quotes are load-bearing rather than decorative. The
    interpreter goes through ``windowless_python`` so the recurring task
    never flashes a console at whoever is using the desktop.
    """
    return '"%s" "%s"' % (windowless_python(python), sweeper)


def build_install_command(python: str, sweeper: str, interval_seconds: int = 120) -> list[str]:
    """The exact argv that creates the machine-wide task. Pure."""
    return [
        "schtasks.exe", "/Create",
        "/TN", TASK_NAME,
        "/TR", task_command(python, sweeper),
        "/SC", "MINUTE",
        "/MO", str(interval_minutes(interval_seconds)),
        "/F",  # idempotent: replace an existing task rather than erroring
    ]


def build_verify_command() -> list[str]:
    """Query the task in parseable list form. Pure."""
    return ["schtasks.exe", "/Query", "/TN", TASK_NAME, "/FO", "LIST", "/V"]


def build_uninstall_command() -> list[str]:
    """Delete the task without prompting. Pure."""
    return ["schtasks.exe", "/Delete", "/TN", TASK_NAME, "/F"]


def describe_install(python: str, sweeper: str, interval_seconds: int = 120) -> list[str]:
    """What ``install`` will do here, as consent-surface lines. Pure.

    Every adapter has one, with the same signature, so the install plan is
    written by the thing that will actually run rather than by a summary of it
    that can drift.
    """
    return [
        "  schedule   %s" % " ".join(build_install_command(python, sweeper, interval_seconds)),
        "  (one task named %s, replacing any existing task of that name)" % TASK_NAME,
    ]


def parse_query(stdout: str) -> dict:
    """``schtasks /FO LIST`` output as ``{installed, running, last_run, error}``.

    Pure, and deliberately tolerant: the field set differs across Windows
    builds and locales, so an unrecognised field is ignored and a missing one
    leaves its value None rather than failing the verify.
    """
    fields: dict[str, str] = {}
    for line in stdout.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        fields[key.strip().lower()] = value.strip()
    if not fields.get("taskname"):
        return {"installed": False, "running": False, "last_run": None,
                "error": "no %s task in the scheduler" % TASK_NAME}
    status = fields.get("status", "").lower()
    last_run = fields.get("last run time") or None
    if last_run in ("N/A", "n/a", ""):
        last_run = None
    result_code = fields.get("last result")
    error = None
    if result_code not in (None, "", "0", "0x0", "267011"):  # 267011 = has not run yet
        error = "last run returned %s" % result_code
    return {
        "installed": True,
        "running": status in ("ready", "running"),
        "last_run": last_run,
        "error": error,
    }


# ------------------------------------------------------------------ interface

def install(interval_seconds: int = 120, *, python: str | None = None,
            sweeper: str | None = None, run: Runner = run_command) -> str:
    """Create (or replace) the one machine task. Returns what it created."""
    cmd = build_install_command(
        python or sys.executable,
        sweeper or str(Path(os.environ.get("USERPROFILE", "~")).expanduser()
                       / ".wall" / "sweep_all.py"),
        interval_seconds)
    outcome = run(cmd)
    if outcome.returncode != 0:
        raise RuntimeError(
            "schtasks could not create %s: %s\nCreate it by hand instead:%s"
            % (TASK_NAME, (outcome.stderr or outcome.stdout).strip(), MANUAL))
    return "scheduled task %s, every %d minute(s)" % (
        TASK_NAME, interval_minutes(interval_seconds))


def verify(*, run: Runner = run_command) -> dict:
    """``{installed, running, last_run, error}``. Never raises."""
    outcome = run(build_verify_command())
    if outcome.returncode != 0:
        return {"installed": False, "running": False, "last_run": None,
                "error": (outcome.stderr or outcome.stdout).strip()
                         or "no %s task in the scheduler" % TASK_NAME}
    return parse_query(outcome.stdout)


def uninstall(*, run: Runner = run_command) -> None:
    """Delete the task. Absent is success."""
    outcome = run(build_uninstall_command())
    if outcome.returncode != 0 and "cannot find" not in (outcome.stderr or "").lower():
        raise RuntimeError("could not delete %s: %s"
                           % (TASK_NAME, (outcome.stderr or outcome.stdout).strip()))
