"""service -- registry, consent-gated install, verify, doctor checks.

The machine registry is written to a temporary WALL_HOME throughout; no test
here touches a real home directory, a real scheduler, or the network. The
scheduler adapter is injected wherever one is needed.
"""

from __future__ import annotations

import json
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

WALL_DIR = Path(__file__).resolve().parents[1] / "tools" / "wall"
if str(WALL_DIR) not in sys.path:
    sys.path.insert(0, str(WALL_DIR))

import service  # noqa: E402


# ---------------------------------------------------------------- scaffolding

@pytest.fixture()
def home(tmp_path: Path, monkeypatch) -> Path:
    target = tmp_path / "wallhome"
    monkeypatch.setenv("WALL_HOME", str(target))
    return target


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "tools" / "wall").mkdir(parents=True)
    (root / "tools" / "wall" / "wall.py").write_text("# wall", encoding="utf-8")
    (root / ".wall" / "derived").mkdir(parents=True)
    return root


def heartbeat(repo: Path, age_s: float) -> None:
    stamp = datetime.now(timezone.utc) - timedelta(seconds=age_s)
    (repo / ".wall" / "derived" / "heartbeat.json").write_text(
        json.dumps({"last_run": stamp.isoformat().replace("+00:00", "Z"), "ok": True}),
        encoding="utf-8")


def fake_adapter(*, installed=True, running=True, last_run="just now", error=None,
                 install_raises=None, uninstall_raises=None):
    record = {"installed": [], "uninstalled": 0}

    def _install(interval_seconds=120, *, python=None, sweeper=None, run=None):
        if install_raises:
            raise install_raises
        record["installed"].append((interval_seconds, python, sweeper))
        return "fake timer every %ds" % interval_seconds

    def _verify(*, run=None):
        return {"installed": installed, "running": running,
                "last_run": last_run, "error": error}

    def _uninstall(*, run=None):
        if uninstall_raises:
            raise uninstall_raises
        record["uninstalled"] += 1

    return types.SimpleNamespace(
        __name__="fake", install=_install, verify=_verify, uninstall=_uninstall,
        describe_install=lambda py, sw, iv=120: ["  schedule   fake --every %d" % iv],
        record=record)


def args(**kwargs):
    kwargs.setdefault("repo", ".")
    return types.SimpleNamespace(**kwargs)


# -------------------------------------------------------------------- paths

def test_wall_home_honours_the_override(home: Path):
    assert service.wall_home() == home
    assert service.registry_path() == home / "registry.json"
    assert service.sweeper_path() == home / "sweep_all.py"


def test_wall_home_defaults_under_the_user_profile(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("WALL_HOME", raising=False)
    assert service.wall_home({"HOME": str(tmp_path)}) == tmp_path / ".wall"
    assert service.wall_home({"USERPROFILE": str(tmp_path)}) == tmp_path / ".wall"


# ----------------------------------------------------------------- registry

def test_registry_starts_empty_without_error(home: Path):
    assert service.read_registry() == {"repos": []}


def test_register_is_idempotent_on_the_resolved_path(home: Path, repo: Path):
    first = service.register_repo(repo)
    second = service.register_repo(repo)
    assert first["added"] is True and second["added"] is False
    assert len(service.read_registry()["repos"]) == 1


def test_register_records_the_four_documented_fields(home: Path, repo: Path):
    service.register_repo(repo, name="demo")
    row = service.read_registry()["repos"][0]
    assert set(row) == {"path", "name", "installed_version", "last_seen"}
    assert row["name"] == "demo" and row["last_seen"] is None


def test_register_refuses_a_path_that_is_not_a_directory(home: Path, tmp_path: Path):
    ghost = tmp_path / "nope"
    outcome = service.register_repo(ghost)
    assert outcome["added"] is False and "not a directory" in outcome["error"]


def test_unregister_removes_and_is_idempotent(home: Path, repo: Path):
    service.register_repo(repo)
    assert service.unregister_repo(repo)["removed"] is True
    assert service.unregister_repo(repo)["removed"] is False
    assert service.read_registry()["repos"] == []


def test_prune_drops_dead_paths(tmp_path: Path):
    alive = tmp_path / "alive"
    alive.mkdir()
    registry = {"repos": [{"path": str(alive)}, {"path": str(tmp_path / "gone")}]}
    pruned, dropped = service.prune_registry(registry)
    assert [r["path"] for r in pruned["repos"]] == [str(alive)]
    assert dropped == [str(tmp_path / "gone")]


def test_a_corrupt_registry_is_an_error_not_an_empty_list(home: Path):
    home.mkdir(parents=True)
    (home / "registry.json").write_text("{not json", encoding="utf-8")
    registry = service.read_registry()
    assert registry["repos"] == [] and "unreadable" in registry["_error"]


def test_a_registry_of_the_wrong_shape_is_flagged(home: Path):
    home.mkdir(parents=True)
    (home / "registry.json").write_text('["a", "b"]', encoding="utf-8")
    assert "not a registry object" in service.read_registry()["_error"]


def test_malformed_rows_are_ignored_and_counted(home: Path, repo: Path):
    home.mkdir(parents=True)
    (home / "registry.json").write_text(
        json.dumps({"repos": [{"path": str(repo)}, "junk", {"name": "no path"}]}),
        encoding="utf-8")
    registry = service.read_registry()
    assert len(registry["repos"]) == 1 and "2 malformed row(s)" in registry["_error"]


def test_register_refuses_to_write_over_a_corrupt_registry(home: Path, repo: Path):
    home.mkdir(parents=True)
    (home / "registry.json").write_text("{not json", encoding="utf-8")
    outcome = service.register_repo(repo)
    assert outcome["added"] is False and outcome["error"]
    assert (home / "registry.json").read_text() == "{not json"


# ------------------------------------------------------------------ sweeper

def test_sweeper_source_is_valid_python():
    compile(service.SWEEPER_SOURCE, "sweep_all.py", "exec")


def test_sweeper_is_written_into_the_wall_home(home: Path):
    path = service.write_sweeper()
    assert path == home / "sweep_all.py"
    assert "registry.json" in path.read_text(encoding="utf-8")


def test_sweeper_drops_dead_paths_and_writes_a_heartbeat():
    source = service.SWEEPER_SOURCE
    assert "path no longer exists" in source
    assert "HEARTBEAT" in source and "SWEEP_TIMEOUT_S" in source


def test_sweeper_makes_no_network_call():
    banned = ("urllib", "requests", "http.client", "socket")
    assert not [word for word in banned if word in service.SWEEPER_SOURCE]


# ------------------------------------------------------------------ consent

def test_install_plan_names_every_path_and_the_command(home: Path, repo: Path,
                                                       monkeypatch):
    monkeypatch.setattr(service, "get_adapter", lambda system=None: fake_adapter())
    text = "\n".join(service.install_plan(repo))
    assert str(home) in text
    assert str(home / "registry.json") in text
    assert str(home / "sweep_all.py") in text
    assert "fake --every 120" in text
    assert str(repo.resolve()) in text
    assert "network" in text


def test_install_without_yes_creates_nothing(home: Path, repo: Path, monkeypatch, capsys):
    monkeypatch.setattr(service, "get_adapter", lambda system=None: fake_adapter())
    code = service.cmd_install(args(repo=str(repo)))
    assert code == 1
    assert "--yes" in capsys.readouterr().out
    assert not home.exists(), "the consent print must not create anything"


def test_install_with_yes_creates_all_three_and_registers(home: Path, repo: Path,
                                                          monkeypatch):
    adapter = fake_adapter()
    monkeypatch.setattr(service, "get_adapter", lambda system=None: adapter)
    assert service.cmd_install(args(repo=str(repo), yes=True)) == 0
    assert (home / "registry.json").is_file()
    assert (home / "sweep_all.py").is_file()
    assert service.is_registered(repo)
    assert adapter.record["installed"] == [(120, sys.executable, str(home / "sweep_all.py"))]


def test_install_is_idempotent(home: Path, repo: Path, monkeypatch):
    adapter = fake_adapter()
    monkeypatch.setattr(service, "get_adapter", lambda system=None: adapter)
    service.cmd_install(args(repo=str(repo), yes=True))
    service.cmd_install(args(repo=str(repo), yes=True))
    assert len(service.read_registry()["repos"]) == 1
    assert len(adapter.record["installed"]) == 2  # the adapter itself replaces in place


def test_install_honours_a_custom_interval(home: Path, repo: Path, monkeypatch):
    adapter = fake_adapter()
    monkeypatch.setattr(service, "get_adapter", lambda system=None: adapter)
    service.cmd_install(args(repo=str(repo), yes=True, interval=300))
    assert adapter.record["installed"][0][0] == 300


def test_a_failed_scheduler_step_is_non_zero_and_says_what_survived(
        home: Path, repo: Path, monkeypatch, capsys):
    adapter = fake_adapter(install_raises=RuntimeError("schtasks: Access is denied."))
    monkeypatch.setattr(service, "get_adapter", lambda system=None: adapter)
    assert service.cmd_install(args(repo=str(repo), yes=True)) == 1
    err = capsys.readouterr().err
    assert "Access is denied." in err and "run-once" in err
    assert (home / "sweep_all.py").is_file(), "the parts that did work must remain"


# ------------------------------------------------------------- register cmds

def test_cmd_register_and_unregister(home: Path, repo: Path, capsys):
    assert service.cmd_register(args(repo=str(repo))) == 0
    assert "registered" in capsys.readouterr().out
    assert service.cmd_unregister(args(repo=str(repo))) == 0
    assert service.read_registry()["repos"] == []


def test_unregister_name_drops_the_named_row_not_this_repo(home: Path, repo: Path,
                                                           tmp_path: Path):
    other = tmp_path / "other"
    other.mkdir()
    service.register_repo(repo, name="here")
    service.register_repo(other, name="gone-checkout")
    # Run from `repo`, name the other row: the name wins over the path.
    assert service.cmd_unregister(args(repo=str(repo), name="gone-checkout")) == 0
    rows = service.read_registry()["repos"]
    assert [r["name"] for r in rows] == ["here"]
    # A name no row carries is the desired end state already: success, no-op.
    assert service.unregister_repo(repo, name="nobody")["removed"] is False
    assert [r["name"] for r in service.read_registry()["repos"]] == ["here"]


def test_unregister_name_matching_two_rows_is_refused(home: Path, repo: Path,
                                                      tmp_path: Path, capsys):
    other = tmp_path / "other"
    other.mkdir()
    service.register_repo(repo, name="twin")
    service.register_repo(other, name="twin")
    assert service.cmd_unregister(args(repo=str(repo), name="twin")) == 1
    assert "matches 2 rows" in capsys.readouterr().err
    assert len(service.read_registry()["repos"]) == 2


def test_wall_cli_passes_unregister_name_through(home: Path, repo: Path, tmp_path: Path):
    import wall
    other = tmp_path / "other"
    other.mkdir()
    service.register_repo(repo, name="here")
    service.register_repo(other, name="gone-checkout")
    old = sys.argv
    sys.argv = ["wall", "--repo", str(repo), "unregister", "--name", "gone-checkout"]
    try:
        assert wall.main() == 0
    finally:
        sys.argv = old
    assert [r["name"] for r in service.read_registry()["repos"]] == ["here"]


def test_cmd_register_warns_when_no_sweeper_exists_yet(home: Path, repo: Path, capsys):
    service.cmd_register(args(repo=str(repo)))
    assert "wall install --yes" in capsys.readouterr().out


def test_cmd_register_reports_a_corrupt_registry(home: Path, repo: Path, capsys):
    home.mkdir(parents=True)
    (home / "registry.json").write_text("{", encoding="utf-8")
    assert service.cmd_register(args(repo=str(repo))) == 1
    assert "register failed" in capsys.readouterr().err


# ------------------------------------------------------------- doctor checks

def test_doctor_is_all_green_on_a_healthy_install(home: Path, repo: Path):
    service.register_repo(repo)
    heartbeat(repo, 30)
    checks = service.doctor_checks(repo, adapter=fake_adapter())
    by_name = {c["name"]: c for c in checks}
    assert by_name["heartbeat"]["status"] == "ok"
    assert by_name["registry"]["status"] == "ok"
    assert by_name["timer"]["status"] == "ok"
    assert not [c for c in checks if c["status"] == "fail"]


def test_a_missing_heartbeat_is_a_failure_not_a_pass(home: Path, repo: Path):
    checks = {c["name"]: c for c in service.doctor_checks(repo, adapter=fake_adapter())}
    assert checks["heartbeat"]["status"] == "fail"
    assert "never run" in checks["heartbeat"]["detail"]


def test_a_stale_heartbeat_fails_with_the_age(home: Path, repo: Path):
    heartbeat(repo, 900)
    check = {c["name"]: c for c in service.doctor_checks(
        repo, adapter=fake_adapter(), stale_after_s=300)}["heartbeat"]
    assert check["status"] == "fail" and "900" in check["detail"]


def test_a_dead_timer_fails_even_with_a_fresh_heartbeat(home: Path, repo: Path):
    service.register_repo(repo)
    heartbeat(repo, 10)
    checks = {c["name"]: c for c in service.doctor_checks(
        repo, adapter=fake_adapter(installed=False, running=False,
                                   error="no WallCourier task"))}
    assert checks["timer"]["status"] == "fail"
    assert "WallCourier" in checks["timer"]["detail"]


def test_an_adapter_that_raises_does_not_take_the_doctor_down(home: Path, repo: Path):
    boom = types.SimpleNamespace(verify=lambda: (_ for _ in ()).throw(OSError("dbus")))
    check = {c["name"]: c for c in service.doctor_checks(repo, adapter=boom)}["timer"]
    assert check["status"] == "fail" and "dbus" in check["detail"]


def test_an_adapter_returning_nonsense_is_not_green(home: Path, repo: Path):
    weird = types.SimpleNamespace(verify=lambda: "fine!")
    check = {c["name"]: c for c in service.doctor_checks(repo, adapter=weird)}["timer"]
    assert check["status"] == "fail"


def test_an_unregistered_repo_is_warned_about(home: Path, repo: Path, tmp_path: Path):
    other = tmp_path / "other"
    other.mkdir()
    service.register_repo(other)
    check = {c["name"]: c for c in service.doctor_checks(
        repo, adapter=fake_adapter())}["registry"]
    assert check["status"] == "warn" and "not this one" in check["detail"]


def test_dead_registry_paths_are_surfaced(home: Path, repo: Path, tmp_path: Path):
    ghost = tmp_path / "ghost"
    ghost.mkdir()
    service.register_repo(repo)
    service.register_repo(ghost)
    ghost.rmdir()
    check = {c["name"]: c for c in service.doctor_checks(
        repo, adapter=fake_adapter())}["registry"]
    assert check["status"] == "warn" and "dead path" in check["detail"]


def test_budget_headroom_is_unknown_not_ok(home: Path, repo: Path):
    assert service.budget_headroom(repo) is None
    check = {c["name"]: c for c in service.doctor_checks(repo, adapter=fake_adapter())}
    assert check["budget"]["status"] == "unknown"
    assert "not measured" in check["budget"]["detail"]


# ------------------------------------------------------------------ manifest

def test_manifest_match(repo: Path, tmp_path: Path):
    app = tmp_path / "app"
    app.mkdir()
    for root in (repo, app):
        (root / "MANIFEST.sha256").write_text("abc  a.py\ndef  b.py\n", encoding="utf-8")
    assert service.manifest_compare(repo, app)["status"] == "match"


def test_manifest_differs_names_the_count(repo: Path, tmp_path: Path):
    app = tmp_path / "app"
    app.mkdir()
    (repo / "MANIFEST.sha256").write_text("abc  a.py\ndef  b.py\n", encoding="utf-8")
    (app / "MANIFEST.sha256").write_text("abc  a.py\n", encoding="utf-8")
    outcome = service.manifest_compare(repo, app)
    assert outcome["status"] == "differs" and "not this tree" in outcome["detail"]


def test_manifest_missing_is_not_a_match(repo: Path, tmp_path: Path):
    outcome = service.manifest_compare(repo, tmp_path / "nowhere")
    assert outcome["status"] == "missing" and "no manifest" in outcome["detail"]


def test_verify_with_app_reports_the_comparison(home: Path, repo: Path, tmp_path: Path,
                                                monkeypatch, capsys):
    app = tmp_path / "app"
    app.mkdir()
    (repo / "MANIFEST.sha256").write_text("abc  a.py\n", encoding="utf-8")
    (app / "MANIFEST.sha256").write_text("zzz  a.py\n", encoding="utf-8")
    service.register_repo(repo)
    heartbeat(repo, 10)
    monkeypatch.setattr(service, "get_adapter", lambda system=None: fake_adapter())
    assert service.cmd_verify(args(repo=str(repo), app=str(app))) == 1
    assert "not this tree" in capsys.readouterr().out


# -------------------------------------------------------------- verify / cmd

def test_cmd_verify_is_zero_when_everything_passes(home: Path, repo: Path, monkeypatch,
                                                   capsys):
    service.register_repo(repo)
    heartbeat(repo, 10)
    monkeypatch.setattr(service, "get_adapter", lambda system=None: fake_adapter())
    assert service.cmd_verify(args(repo=str(repo))) == 0
    assert "all checks passed" in capsys.readouterr().out


def test_cmd_verify_is_non_zero_when_the_timer_is_dead(home: Path, repo: Path,
                                                       monkeypatch, capsys):
    heartbeat(repo, 10)
    monkeypatch.setattr(service, "get_adapter",
                        lambda system=None: fake_adapter(installed=False))
    assert service.cmd_verify(args(repo=str(repo))) == 1
    assert "FAILED" in capsys.readouterr().out


# ---------------------------------------------------------------- uninstall

def test_cmd_uninstall_keeps_the_registry_by_default(home: Path, repo: Path, monkeypatch):
    adapter = fake_adapter()
    monkeypatch.setattr(service, "get_adapter", lambda system=None: adapter)
    service.cmd_install(args(repo=str(repo), yes=True))
    assert service.cmd_uninstall(args(repo=str(repo))) == 0
    assert adapter.record["uninstalled"] == 1
    assert (home / "registry.json").is_file()


def test_cmd_uninstall_purge_removes_the_registry_and_sweeper(home: Path, repo: Path,
                                                              monkeypatch):
    monkeypatch.setattr(service, "get_adapter", lambda system=None: fake_adapter())
    service.cmd_install(args(repo=str(repo), yes=True))
    assert service.cmd_uninstall(args(repo=str(repo), purge=True)) == 0
    assert not (home / "registry.json").exists()
    assert not (home / "sweep_all.py").exists()


def test_cmd_uninstall_reports_a_failing_adapter(home: Path, repo: Path, monkeypatch,
                                                 capsys):
    monkeypatch.setattr(service, "get_adapter",
                        lambda system=None: fake_adapter(uninstall_raises=RuntimeError("denied")))
    assert service.cmd_uninstall(args(repo=str(repo))) == 1
    assert "denied" in capsys.readouterr().err


# -------------------------------------------------------------------- serve

def test_cmd_serve_check_fails_when_nothing_is_listening(repo: Path, capsys):
    import socket
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        free = probe.getsockname()[1]
    assert service.cmd_serve(args(repo=str(repo), check=True, port=free)) == 1
    assert "FAIL" in capsys.readouterr().out


def test_cmd_serve_refuses_before_the_first_sweep(tmp_path: Path, capsys):
    assert service.cmd_serve(args(repo=str(tmp_path), port=0)) == 1
    assert "run-once" in capsys.readouterr().err


# --------------------------------------------------------------------- seam

@pytest.mark.parametrize("name", ["cmd_install", "cmd_register", "cmd_unregister",
                                  "cmd_verify", "cmd_uninstall", "cmd_serve"])
def test_the_lazy_import_seam_is_intact(name):
    """wall.py imports these six by name. Renaming one silently breaks the CLI."""
    fn = getattr(service, name, None)
    assert callable(fn), "%s is missing from the seam" % name


@pytest.mark.parametrize("name", ["cmd_register", "cmd_unregister", "cmd_verify"])
def test_seam_functions_need_only_dot_repo(home: Path, repo: Path, monkeypatch, name):
    """A bare namespace with only .repo must work: wall.py's stub parsers add no
    other attribute, so every optional flag is read with getattr and a default."""
    monkeypatch.setattr(service, "get_adapter", lambda system=None: fake_adapter())
    assert getattr(service, name)(types.SimpleNamespace(repo=str(repo))) in (0, 1)
