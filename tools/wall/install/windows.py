"""Windows adapter — Register-ScheduledTask.

The MAX3 target platform. Repo at C:\\Dev\\gh-repos\\newellnarco\\MAX3,
application at C:\\Dev\\MAX3.

STUB. The PowerShell below is the intended implementation and can be run by hand
today; it is not yet wired up.
"""

import os
from pathlib import Path

TASK_NAME = "WallCourier"
REGISTRY = Path(os.environ.get("USERPROFILE", "~")).expanduser() / ".wall" / "registry.json"

MANUAL = r"""
# One task for the machine. It walks %USERPROFILE%\.wall\registry.json and runs
# `wall run-once` for each registered repo, so adding a repo installs nothing new.

$py      = (Get-Command python).Source
$sweeper = "$env:USERPROFILE\.wall\sweep_all.py"

$action  = New-ScheduledTaskAction -Execute $py -Argument $sweeper
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) `
           -RepetitionInterval (New-TimeSpan -Minutes 2) `
           -RepetitionDuration ([TimeSpan]::MaxValue)
$set     = New-ScheduledTaskSettingsSet -StartWhenAvailable `
           -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 5)

Register-ScheduledTask -TaskName "WallCourier" -Action $action `
    -Trigger $trigger -Settings $set -Description "MAX3 wall courier sweep"

# Verify / remove
Get-ScheduledTask     -TaskName "WallCourier"
Get-ScheduledTaskInfo -TaskName "WallCourier"   # LastRunTime, LastTaskResult
Unregister-ScheduledTask -TaskName "WallCourier" -Confirm:$false
"""


def install(interval_seconds: int = 120) -> str:
    raise NotImplementedError(
        f"Windows adapter is a stub. Run this in PowerShell:\n{MANUAL}\n"
        f"Then add the repo path to {REGISTRY}.")


def verify() -> dict:
    raise NotImplementedError(
        'Not built. Check manually:\n'
        '  Get-ScheduledTaskInfo -TaskName "WallCourier"\n'
        "  and compare heartbeat.json's last_run against now.")


def uninstall() -> None:
    raise NotImplementedError(
        'Not built. Run:\n'
        '  Unregister-ScheduledTask -TaskName "WallCourier" -Confirm:$false')
