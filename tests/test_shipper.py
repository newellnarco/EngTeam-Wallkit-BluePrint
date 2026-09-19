"""shipper -- isolated-branch shipping, with a fake git runner throughout.

No test in this file runs git. The runner is injected, every call is recorded,
and the assertions are about what would have been run: the isolation env, the
validate-before-push refusal, and the freshness guard on fetch. A test that
shelled out to real git would be testing git.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

WALL_DIR = Path(__file__).resolve().parents[1] / "tools" / "wall"
if str(WALL_DIR) not in sys.path:
    sys.path.insert(0, str(WALL_DIR))

import shipper  # noqa: E402


# ---------------------------------------------------------------- scaffolding

def good_snapshot(generated_at: str = "2026-09-19T12:00:00.000Z") -> dict:
    return {
        "schema_version": 1,
        "generated_at": generated_at,
        "repo": {"name": "demo", "path": "/tmp/demo", "branch": "main"},
        "courier": {"last_run_ms": 3, "events": 2, "shards": 1},
        "integrity": {"seq_gaps": [], "orphan_runs": [], "duplicates": []},
        "crew": [],
        "board": {"arcs": []},
    }


class FakeGit:
    """Records every call; answers from a per-verb script."""

    def __init__(self, script: dict | None = None):
        self.calls: list[dict] = []
        self.script = script or {}

    def __call__(self, repo, *args, env=None):
        verb = args[0] if args else ""
        self.calls.append({"repo": Path(repo), "args": list(args), "env": env})
        rc, out, err = self.script.get(verb, (0, "", ""))
        if callable(out):
            out = out(list(args))
        return subprocess.CompletedProcess(["git", *args], rc, out, err)

    def verbs(self) -> list[str]:
        return [call["args"][0] for call in self.calls]

    def first(self, verb: str) -> dict | None:
        return next((c for c in self.calls if c["args"][0] == verb), None)

    def all(self, verb: str) -> list[dict]:
        return [c for c in self.calls if c["args"][0] == verb]


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    (tmp_path / ".wall" / "derived").mkdir(parents=True)
    (tmp_path / ".wall" / "events" / "2026-09-19").mkdir(parents=True)
    (tmp_path / ".wall" / "derived" / "wall.json").write_text(
        json.dumps(good_snapshot()), encoding="utf-8")
    (tmp_path / ".wall" / "events" / "2026-09-19" / "s_7f3a.jsonl").write_text(
        '{"event_id":"e1","ts":"2026-09-19T11:00:00Z"}\n', encoding="utf-8")
    return tmp_path


# ----------------------------------------------------------------- validation

def test_validate_accepts_a_real_snapshot():
    assert shipper.validate_snapshot(good_snapshot()) is None


@pytest.mark.parametrize("mutate, fragment", [
    (lambda s: s.pop("schema_version"), "schema_version"),
    (lambda s: s.update(generated_at=""), "generated_at"),
    (lambda s: s.update(generated_at="tuesday"), "ISO-8601"),
    (lambda s: s.update(crew={}), "crew"),
    (lambda s: s.update(board={}), "board.arcs"),
    (lambda s: s.update(integrity="clean"), "integrity"),
])
def test_validate_names_the_reason(mutate, fragment):
    snapshot = good_snapshot()
    mutate(snapshot)
    reason = shipper.validate_snapshot(snapshot)
    assert reason is not None and fragment in reason


def test_validate_rejects_a_non_object():
    assert "object" in shipper.validate_snapshot([1, 2, 3])


# -------------------------------------------------------------------- ship

def test_ship_uses_an_isolated_index_and_never_touches_the_tree(repo: Path):
    git = FakeGit({"hash-object": (0, "abc123\n", ""),
                   "write-tree": (0, "tree999\n", ""),
                   "commit-tree": (0, "commit777\n", "")})

    assert shipper.ship(repo, git=git) == 0

    for verb in ("read-tree", "update-index", "write-tree"):
        call = git.first(verb)
        assert call is not None, "%s was never run" % verb
        assert call["env"] is not None and "GIT_INDEX_FILE" in call["env"], \
            "%s ran against the REAL index" % verb
        assert ".ship-wall-events.index" in call["env"]["GIT_INDEX_FILE"]

    # Nothing that mutates the checkout or the branch may appear.
    assert not ({"add", "commit", "checkout", "reset", "stash"} & set(git.verbs()))


def test_ship_pushes_the_commit_object_to_the_isolated_branch(repo: Path):
    git = FakeGit({"hash-object": (0, "abc123\n", ""),
                   "write-tree": (0, "tree999\n", ""),
                   "commit-tree": (0, "commit777\n", "")})
    shipper.ship(repo, git=git)
    push = git.first("push")
    assert push["args"] == ["push", "-f", "origin", "commit777:refs/heads/wall-events"]


def test_ship_stages_the_snapshot_and_the_days_shards(repo: Path):
    git = FakeGit({"hash-object": (0, "abc123\n", ""),
                   "write-tree": (0, "t\n", ""), "commit-tree": (0, "c\n", "")})
    shipper.ship(repo, git=git)
    staged = [c["args"][-1].split(",")[-1] for c in git.all("update-index")]
    assert staged == [".wall/derived/wall.json",
                      ".wall/events/2026-09-19/s_7f3a.jsonl"]


def test_ship_refuses_a_malformed_snapshot_before_touching_git(repo: Path):
    (repo / ".wall" / "derived" / "wall.json").write_text('{"schema_version": 1}',
                                                          encoding="utf-8")
    git = FakeGit()
    assert shipper.ship(repo, git=git) == 1
    assert git.calls == [], "git was invoked for a snapshot we refuse to publish"


def test_ship_refuses_unparseable_json(repo: Path):
    (repo / ".wall" / "derived" / "wall.json").write_text("{not json", encoding="utf-8")
    git = FakeGit()
    assert shipper.ship(repo, git=git) == 1
    assert git.calls == []


def test_ship_is_a_named_no_op_without_a_snapshot(tmp_path: Path):
    git = FakeGit()
    assert shipper.ship(tmp_path, git=git) == 1
    assert git.calls == []


def test_ship_reports_a_failed_push_and_does_not_pretend(repo: Path):
    git = FakeGit({"hash-object": (0, "a\n", ""), "write-tree": (0, "t\n", ""),
                   "commit-tree": (0, "c\n", ""), "push": (1, "", "no upstream")})
    assert shipper.ship(repo, git=git) == 1


def test_ship_cleans_up_the_isolated_index_even_on_failure(repo: Path):
    index = repo / ".wall" / "derived" / ".ship-wall-events.index"
    index.write_text("stale", encoding="utf-8")
    git = FakeGit({"write-tree": (1, "", "boom")})
    assert shipper.ship(repo, git=git) == 1
    assert not index.exists()


def test_shipment_paths_leads_with_the_snapshot(repo: Path):
    paths = shipper.shipment_paths(repo, day="2026-09-19")
    assert paths[0] == ".wall/derived/wall.json"
    assert all("/" in p for p in paths), "paths must be posix-relative for git"


def test_shipment_paths_ignores_other_days(repo: Path):
    other = repo / ".wall" / "events" / "2026-01-01"
    other.mkdir(parents=True)
    (other / "s_old.jsonl").write_text("{}\n", encoding="utf-8")
    assert not any("2026-01-01" in p for p in shipper.shipment_paths(repo, day="2026-09-19"))


# ------------------------------------------------------------------- fetch

def _fetch_git(remote_snapshot, shards=None, listing_rc=0):
    shards = shards or {}

    def blob(args):
        target = args[-1].split(":", 1)[1]
        if target == shipper.SNAPSHOT_REL:
            return remote_snapshot
        return shards.get(target, "")

    names = "\n".join([shipper.SNAPSHOT_REL, *shards])
    return FakeGit({"cat-file": (0, blob, ""), "ls-tree": (listing_rc, names, "")})


def test_fetch_materialises_a_newer_snapshot_and_its_shards(repo: Path):
    remote = json.dumps(good_snapshot("2026-09-19T18:00:00.000Z"))
    shard_rel = ".wall/events/2026-09-19/s_cloud.jsonl"
    git = _fetch_git(remote, {shard_rel: '{"event_id":"e9"}\n'})

    outcome = shipper.fetch(repo, git=git)

    assert outcome["updated"] is True
    assert outcome["shards"] == 1 and outcome["snapshot"] is True
    assert json.loads((repo / shipper.SNAPSHOT_REL).read_text())["generated_at"].startswith(
        "2026-09-19T18")
    assert (repo / shard_rel).read_text() == '{"event_id":"e9"}\n'


def test_fetch_refuses_to_clobber_a_fresher_local_snapshot(repo: Path):
    (repo / shipper.SNAPSHOT_REL).write_text(
        json.dumps(good_snapshot("2026-09-19T23:00:00.000Z")), encoding="utf-8")
    git = _fetch_git(json.dumps(good_snapshot("2026-09-19T12:00:00.000Z")))

    outcome = shipper.fetch(repo, git=git)

    assert outcome["updated"] is False
    assert "fresh" in outcome["reason"]
    assert "T23" in (repo / shipper.SNAPSHOT_REL).read_text()


def test_fetch_refuses_a_malformed_remote_payload_however_new(repo: Path):
    stale = {"schema_version": 1, "generated_at": "2099-01-01T00:00:00Z"}
    git = _fetch_git(json.dumps(stale))
    outcome = shipper.fetch(repo, git=git)
    assert outcome["updated"] is False and "malformed" in outcome["reason"]
    assert json.loads((repo / shipper.SNAPSHOT_REL).read_text())["generated_at"].startswith(
        "2026-09-19T12")


def test_fetch_is_a_named_no_op_without_the_branch(repo: Path):
    git = FakeGit({"fetch": (1, "", "couldn't find remote ref wall-events")})
    outcome = shipper.fetch(repo, git=git)
    assert outcome["updated"] is False
    assert "no wall-events branch" in outcome["reason"]


def test_fetch_keeps_a_longer_local_shard(repo: Path):
    shard_rel = ".wall/events/2026-09-19/s_7f3a.jsonl"
    local = (repo / shard_rel).read_text() + '{"event_id":"e2"}\n'
    (repo / shard_rel).write_text(local, encoding="utf-8")
    git = _fetch_git(json.dumps(good_snapshot("2026-09-19T18:00:00.000Z")),
                     {shard_rel: '{"event_id":"e1"}\n'})

    outcome = shipper.fetch(repo, git=git)

    assert outcome["shards"] == 0
    assert (repo / shard_rel).read_text() == local


def test_fetch_never_writes_outside_the_repo(repo: Path, tmp_path: Path):
    escape = "../../../wall-escape.jsonl"
    git = FakeGit({
        "cat-file": (0, lambda a: json.dumps(good_snapshot("2026-09-19T18:00:00.000Z"))
                     if a[-1].endswith(shipper.SNAPSHOT_REL) else "{}\n", ""),
        "ls-tree": (0, "%s/%s" % (shipper.EVENTS_REL, escape), ""),
    })
    shipper.fetch(repo, git=git)
    assert not (tmp_path.parent / "wall-escape.jsonl").exists()


def test_fetch_survives_an_unusable_listing(repo: Path):
    git = _fetch_git(json.dumps(good_snapshot("2026-09-19T18:00:00.000Z")), listing_rc=128)
    outcome = shipper.fetch(repo, git=git)
    assert outcome["updated"] is True and outcome["shards"] == 0


# --------------------------------------------------------------- heartbeat

def test_heartbeat_age_is_none_when_the_courier_has_never_run(tmp_path: Path):
    assert shipper.heartbeat_age_s(tmp_path) is None


def test_heartbeat_age_is_none_for_an_unreadable_file(repo: Path):
    (repo / ".wall" / "derived" / "heartbeat.json").write_text("{oops", encoding="utf-8")
    assert shipper.heartbeat_age_s(repo) is None


def test_heartbeat_age_measures_from_last_run(repo: Path):
    now = datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc)
    (repo / ".wall" / "derived" / "heartbeat.json").write_text(
        json.dumps({"last_run": (now - timedelta(seconds=90)).isoformat()}),
        encoding="utf-8")
    assert shipper.heartbeat_age_s(repo, now=now) == pytest.approx(90.0)


def test_heartbeat_age_treats_a_naive_stamp_as_utc(repo: Path):
    (repo / ".wall" / "derived" / "heartbeat.json").write_text(
        json.dumps({"last_run": "2026-09-19T11:59:00"}), encoding="utf-8")
    now = datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc)
    assert shipper.heartbeat_age_s(repo, now=now) == pytest.approx(60.0)


def test_heartbeat_age_never_goes_negative(repo: Path):
    (repo / ".wall" / "derived" / "heartbeat.json").write_text(
        json.dumps({"last_run": "2099-01-01T00:00:00Z"}), encoding="utf-8")
    assert shipper.heartbeat_age_s(repo) == 0.0
