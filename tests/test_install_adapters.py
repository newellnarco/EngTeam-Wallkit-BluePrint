"""install adapters -- the constructed commands, on any platform.

Every adapter splits command CONSTRUCTION (pure: argv, plist text, unit files)
from EXECUTION (one injectable runner). That split is the whole point of this
file: a scheduler command that is wrong is a test failure here, on a Linux CI
box, rather than a mystery on a Windows workstation two weeks later.

Nothing here touches a real scheduler or a real home directory.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

WALL_DIR = Path(__file__).resolve().parents[1] / "tools" / "wall"
if str(WALL_DIR) not in sys.path:
    sys.path.insert(0, str(WALL_DIR))

import install  # noqa: E402
from install import linux, macos, windows  # noqa: E402

ADAPTERS = (windows, macos, linux)

PY = r"C:\Program Files\Python312\python.exe"
SWEEPER = r"C:\Users\First Last\.wall\sweep_all.py"


class Recorder:
    """An injectable runner that records argv and answers from a script."""

    def __init__(self, script=None):
        self.cmds: list[list[str]] = []
        self.script = script or {}

    def __call__(self, cmd, **kwargs):
        self.cmds.append(list(cmd))
        rc, out, err = self.script.get(tuple(cmd), self.script.get("*", (0, "", "")))
        return subprocess.CompletedProcess(cmd, rc, out, err)


class Writer:
    def __init__(self):
        self.files: dict[str, str] = {}

    def __call__(self, path, text):
        self.files[str(path)] = text


# ------------------------------------------------------------------ interface

@pytest.mark.parametrize("adapter", ADAPTERS)
def test_every_adapter_implements_the_three_methods(adapter):
    for name in ("install", "verify", "uninstall"):
        assert callable(getattr(adapter, name)), "%s lacks %s" % (adapter.__name__, name)


@pytest.mark.parametrize("adapter", ADAPTERS)
def test_every_adapter_can_describe_its_install_without_running_it(adapter):
    lines = adapter.describe_install(PY, SWEEPER, 120)
    assert lines and all(isinstance(line, str) for line in lines)
    assert any("schedule" in line for line in lines)


@pytest.mark.parametrize("system, expected", [
    ("Windows", windows), ("Darwin", macos), ("Linux", linux), ("FreeBSD", linux),
])
def test_get_adapter_routes_by_system(system, expected):
    assert install.get_adapter(system) is expected


def test_run_command_reports_a_missing_binary_instead_of_raising():
    outcome = install.run_command(["definitely-not-a-real-binary-xyz"])
    assert outcome.returncode == 127 and "could not run" in outcome.stderr


def test_current_uid_is_a_string_everywhere():
    assert isinstance(install.current_uid(), str)


# -------------------------------------------------------------------- windows

def test_windows_install_command_is_exact():
    assert windows.build_install_command(PY, SWEEPER, 120) == [
        "schtasks.exe", "/Create",
        "/TN", "WallCourier",
        "/TR", '"%s" "%s"' % (PY, SWEEPER),
        "/SC", "MINUTE",
        "/MO", "2",
        "/F",
    ]


def test_windows_quotes_both_paths():
    # Both routinely contain spaces; /TR is one string the scheduler re-splits.
    assert windows.task_command(PY, SWEEPER).count('"') == 4


@pytest.mark.parametrize("seconds, minutes", [(120, 2), (60, 1), (30, 1), (1, 1),
                                              (300, 5), (90, 2)])
def test_windows_interval_never_rounds_to_zero(seconds, minutes):
    assert windows.interval_minutes(seconds) == minutes


def test_windows_install_replaces_rather_than_erroring():
    assert "/F" in windows.build_install_command(PY, SWEEPER)


def test_windows_install_runs_exactly_that_command():
    run = Recorder()
    created = windows.install(120, python=PY, sweeper=SWEEPER, run=run)
    assert run.cmds == [windows.build_install_command(PY, SWEEPER, 120)]
    assert "WallCourier" in created


def test_windows_install_raises_with_the_manual_fallback():
    run = Recorder({"*": (1, "", "Access is denied.")})
    with pytest.raises(RuntimeError) as caught:
        windows.install(120, python=PY, sweeper=SWEEPER, run=run)
    assert "Access is denied." in str(caught.value)
    assert "Register-ScheduledTask" in str(caught.value)


def test_windows_verify_parses_a_healthy_query():
    stdout = ("TaskName:      \\WallCourier\n"
              "Status:        Ready\n"
              "Last Run Time: 9/19/2026 11:58:00 AM\n"
              "Last Result:   0\n")
    assert windows.parse_query(stdout) == {
        "installed": True, "running": True,
        "last_run": "9/19/2026 11:58:00 AM", "error": None}


def test_windows_verify_reports_a_failing_last_result():
    stdout = ("TaskName: \\WallCourier\nStatus: Ready\n"
              "Last Run Time: N/A\nLast Result: 1\n")
    parsed = windows.parse_query(stdout)
    assert parsed["last_run"] is None and "1" in parsed["error"]


def test_windows_verify_on_an_absent_task_is_not_green():
    run = Recorder({"*": (1, "", "ERROR: The system cannot find the file specified.")})
    parsed = windows.verify(run=run)
    assert parsed["installed"] is False and parsed["error"]


def test_windows_uninstall_is_idempotent():
    run = Recorder({"*": (1, "", "ERROR: The system cannot find the task.")})
    windows.uninstall(run=run)  # must not raise
    assert run.cmds == [["schtasks.exe", "/Delete", "/TN", "WallCourier", "/F"]]


# --------------------------------------------------------------------- macos

def test_macos_plist_carries_the_interval_and_both_arguments():
    plist = macos.build_plist("/usr/bin/python3", "/Users/j/.wall/sweep_all.py", 120)
    assert "<key>StartInterval</key>" in plist and "<integer>120</integer>" in plist
    assert "<string>/usr/bin/python3</string>" in plist
    assert "<string>/Users/j/.wall/sweep_all.py</string>" in plist
    assert "<key>RunAtLoad</key>" in plist and "<true/>" in plist
    assert plist.startswith("<?xml")


def test_macos_plist_escapes_xml_in_paths():
    plist = macos.build_plist("/usr/bin/python3", "/Users/a&b/.wall/sweep_all.py")
    assert "a&amp;b" in plist and "a&b" not in plist


def test_macos_plist_interval_is_never_zero():
    assert "<integer>1</integer>" in macos.build_plist("py", "s", 0)


def test_macos_launchctl_commands_use_the_gui_domain():
    assert macos.build_install_command("/tmp/x.plist", uid="501") == [
        "launchctl", "bootstrap", "gui/501", "/tmp/x.plist"]
    assert macos.build_verify_command(uid="501") == [
        "launchctl", "print", "gui/501/com.wallkit.courier"]
    assert macos.build_uninstall_command(uid="501") == [
        "launchctl", "bootout", "gui/501/com.wallkit.courier"]


def test_macos_install_writes_the_plist_then_bootstraps_it(tmp_path: Path):
    run, write = Recorder(), Writer()
    macos.install(120, python="py", sweeper="s", run=run, write=write, home=tmp_path)
    assert list(write.files) == [str(macos.plist_path(tmp_path))]
    assert run.cmds[0][:2] == ["launchctl", "bootout"], "re-install must replace"
    assert run.cmds[1][:2] == ["launchctl", "bootstrap"]


def test_macos_install_names_the_plist_when_bootstrap_fails(tmp_path: Path):
    run = Recorder({"*": (1, "", "Load failed: 5: Input/output error")})
    with pytest.raises(RuntimeError) as caught:
        macos.install(120, python="py", sweeper="s", run=run, write=Writer(), home=tmp_path)
    assert str(macos.plist_path(tmp_path)) in str(caught.value)


def test_macos_verify_parses_launchctl_print():
    parsed = macos.parse_print("  state = running\n  last exit code = 0\n")
    assert parsed["installed"] and parsed["running"] and parsed["error"] is None


def test_macos_verify_does_not_invent_a_last_run():
    # launchctl reports an exit code, not a time. heartbeat.json is the
    # authority on when the courier last ran.
    assert macos.parse_print("  state = running\n")["last_run"] is None


def test_macos_verify_surfaces_a_bad_exit_code():
    assert "2" in macos.parse_print("state = waiting\nlast exit code = 2\n")["error"]


# --------------------------------------------------------------------- linux

def test_linux_service_unit_is_a_bounded_oneshot():
    unit = linux.build_service_unit("/usr/bin/python3", "/home/j/.wall/sweep_all.py")
    assert "Type=oneshot" in unit
    assert "ExecStart=/usr/bin/python3 /home/j/.wall/sweep_all.py" in unit
    assert "TimeoutStartSec=" in unit


def test_linux_timer_measures_from_the_end_of_the_last_run():
    timer = linux.build_timer_unit(120)
    assert "OnUnitActiveSec=120s" in timer, "OnCalendar would stack slow sweeps"
    assert "Persistent=true" in timer
    assert "Unit=wall-courier.service" in timer
    assert "WantedBy=timers.target" in timer


@pytest.mark.parametrize("seconds, spec", [
    (120, "*/2 * * * *"), (60, "* * * * *"), (30, "* * * * *"), (600, "*/10 * * * *"),
])
def test_linux_cron_fallback_spec(seconds, spec):
    line = linux.build_cron_line("/usr/bin/python3", "/home/j/.wall/sweep_all.py", seconds)
    assert line.startswith(spec + " ")
    assert line.endswith("/usr/bin/python3 /home/j/.wall/sweep_all.py")


def test_linux_install_commands_reload_before_enabling():
    assert linux.build_install_commands() == [
        ["systemctl", "--user", "daemon-reload"],
        ["systemctl", "--user", "enable", "--now", "wall-courier.timer"],
    ]


def test_linux_verify_command_asks_for_parseable_properties():
    cmd = linux.build_verify_command()
    assert cmd[:3] == ["systemctl", "--user", "show"]
    assert any(arg.startswith("--property=") for arg in cmd)


def test_linux_install_writes_both_units(tmp_path: Path):
    run, write = Recorder(), Writer()
    created = linux.install(120, python="py", sweeper="s", run=run, write=write,
                            home=tmp_path)
    assert set(write.files) == {
        str(linux.unit_dir(tmp_path) / "wall-courier.service"),
        str(linux.unit_dir(tmp_path) / "wall-courier.timer"),
    }
    assert run.cmds == linux.build_install_commands()
    assert "wall-courier.timer" in created


def test_linux_install_failure_offers_the_cron_line(tmp_path: Path):
    run = Recorder({"*": (1, "", "Failed to connect to bus")})
    with pytest.raises(RuntimeError) as caught:
        linux.install(120, python="py", sweeper="s", run=run, write=Writer(), home=tmp_path)
    assert "*/2 * * * *" in str(caught.value)


def test_linux_verify_parses_an_active_timer():
    parsed = linux.parse_show(
        "LoadState=loaded\nActiveState=active\n"
        "LastTriggerUSec=Sat 2026-09-19 11:58:00 UTC\n")
    assert parsed["installed"] and parsed["running"]
    assert parsed["last_run"].startswith("Sat 2026-09-19")


def test_linux_verify_on_a_missing_unit_is_not_green():
    parsed = linux.parse_show("LoadState=not-found\nActiveState=inactive\n")
    assert parsed["installed"] is False and "not-found" in parsed["error"]


def test_linux_verify_flags_an_installed_but_stopped_timer():
    parsed = linux.parse_show("LoadState=loaded\nActiveState=inactive\n")
    assert parsed["installed"] is True and parsed["running"] is False and parsed["error"]


def test_linux_uninstall_removes_both_units(tmp_path: Path):
    unit_dir = linux.unit_dir(tmp_path)
    unit_dir.mkdir(parents=True)
    for name in ("wall-courier.timer", "wall-courier.service"):
        (unit_dir / name).write_text("x", encoding="utf-8")
    run = Recorder()
    linux.uninstall(run=run, home=tmp_path)
    assert not any(unit_dir.iterdir())
    assert run.cmds[0] == linux.build_uninstall_command()


def test_linux_uninstall_of_an_absent_timer_is_success(tmp_path: Path):
    linux.uninstall(run=Recorder({"*": (1, "", "not loaded")}), home=tmp_path)
