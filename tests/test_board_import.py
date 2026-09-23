"""test_board_import.py -- the overlay adapter.

The adapter's whole job is to let the wall be laid over a project that is
already underway without touching that project. So the tests are about the
three properties that makes possible, in the order they matter:

1. **Additive and safe.** It writes events into `.wall/events/` and nothing
   else. The source file is never opened for writing, and a profile that would
   map an item field onto an event envelope key is refused rather than silently
   dropped by the fold.
2. **Idempotent.** A second run writes nothing. A changed source writes one
   `item_state` and no second `item_created`.
3. **Correct on real data.** The slug-keyed profile maps a real slug-keyed
   board -- its statuses, its key-prefix bug heuristic, its `arch` arc families -- and the
   result folds into a board the wall can render.

Stdlib + pytest only.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

KIT = Path(__file__).resolve().parents[1]
WALL = KIT / "tools" / "wall"
if str(WALL) not in sys.path:
    sys.path.insert(0, str(WALL))

import items as items_mod  # noqa: E402
from adapters import board_import as bi  # noqa: E402

#: A real slug-keyed board on this machine, if the environment names one. The
#: real-data test is skipped when it is unset or the file is absent.
REAL_BOARD = Path(os.environ.get("WALL_REAL_BOARD", "") or "/nonexistent/board_state.json")

NOW = "2026-09-19T00:00:00.000Z"


# ------------------------------------------------------------------ fixtures

def generic_source() -> dict:
    return {
        "updated": "2026-09-18",
        "items": [
            {"id": "ARC-7", "title": "Telemetry spine", "type": "epic", "status": "Active"},
            {"id": "ST-70", "title": "Shard writer", "type": "Story", "status": "In Progress",
             "arc": "ARC-7", "arc_title": "Telemetry spine", "assignee": "Desmond",
             "estimate": "M", "parent_id": "ARC-7", "updated_at": "2026-09-18T11:00:00Z"},
            {"id": "BUG-3", "title": "Duplicate on retry", "type": "Bug", "status": "blocked",
             "arc": "ARC-7"},
            {"id": "ST-71", "title": "Loose one", "type": "story", "status": "Shipped"},
            {"id": "ST-72", "title": "Strange one", "type": "story", "status": "gardening-leave"},
            {"title": "no id at all", "status": "todo"},
        ],
    }


def fold_of(repo: Path) -> dict:
    return items_mod.fold_items(bi._read_ledger(repo))


# -------------------------------------------------------- 1. additive + safe

def test_profile_that_writes_the_envelope_is_refused() -> None:
    """A field mapped onto an envelope key would be dropped by the fold. Say so."""
    bad = dict(bi.PROFILE_GENERIC, extra_fields={"source": "origin"})
    with pytest.raises(ValueError, match="envelope"):
        bi.validate_profile(bad)


def test_profile_missing_a_required_mapping_is_refused() -> None:
    bad = dict(bi.PROFILE_GENERIC)
    bad.pop("id_field")
    with pytest.raises(ValueError, match="id_field"):
        bi.validate_profile(bad)


def test_shipped_profiles_are_valid() -> None:
    for profile in bi.PROFILES.values():
        bi.validate_profile(profile)


def test_import_writes_only_into_the_wall(tmp_path: Path) -> None:
    src = tmp_path / "board.json"
    src.write_text(json.dumps(generic_source()), encoding="utf-8")
    before = src.read_bytes()

    result = bi.import_board(tmp_path, src, bi.PROFILE_GENERIC, now=NOW)

    assert src.read_bytes() == before, "the importer modified its source"
    written = {p.relative_to(tmp_path).parts[0] for p in tmp_path.rglob("*") if p.is_file()}
    assert written == {"board.json", ".wall"}
    assert result["imported"] == 5
    assert result["unusable"] == 1, "the row with no id should be counted, not silently dropped"


def test_events_are_one_json_object_per_line(tmp_path: Path) -> None:
    src = tmp_path / "board.json"
    src.write_text(json.dumps(generic_source()), encoding="utf-8")
    bi.import_board(tmp_path, src, bi.PROFILE_GENERIC, now=NOW)

    shards = list((tmp_path / ".wall" / "events").rglob("*.jsonl"))
    assert shards, "no shard written"
    seqs = []
    for shard in shards:
        text = shard.read_text(encoding="utf-8")
        assert text.endswith("\n")
        for line in text.splitlines():
            record = json.loads(line)          # raises if a line is not one object
            assert record["event"] in ("item_created", "item_state")
            assert record["actor"] == bi.IMPORT_ACTOR
            for required in ("schema_version", "event_id", "seq", "ts", "session_id"):
                assert required in record
            seqs.append(record["seq"])
    assert len(set(seqs)) == len(seqs), "seq collided inside one session"


def test_trace_is_deterministic_per_item() -> None:
    assert bi.trace_for("ST-70") == bi.trace_for("ST-70")
    assert bi.trace_for("ST-70") != bi.trace_for("ST-71")
    assert bi.trace_for("ST-70").startswith("tr_imp_")


def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    src = tmp_path / "board.json"
    src.write_text(json.dumps(generic_source()), encoding="utf-8")
    result = bi.import_board(tmp_path, src, bi.PROFILE_GENERIC, dry_run=True, now=NOW)
    assert result["imported"] == 5
    assert result["events"] == 0
    assert not (tmp_path / ".wall").exists()


# --------------------------------------------------------------- 2. idempotent

def test_second_run_writes_nothing(tmp_path: Path) -> None:
    src = tmp_path / "board.json"
    src.write_text(json.dumps(generic_source()), encoding="utf-8")
    first = bi.import_board(tmp_path, src, bi.PROFILE_GENERIC, now=NOW)
    second = bi.import_board(tmp_path, src, bi.PROFILE_GENERIC, now=NOW)

    assert second == dict(first, imported=0, skipped=first["imported"], events=0)


def test_a_moved_status_writes_one_state_event(tmp_path: Path) -> None:
    src = tmp_path / "board.json"
    doc = generic_source()
    src.write_text(json.dumps(doc), encoding="utf-8")
    bi.import_board(tmp_path, src, bi.PROFILE_GENERIC, now=NOW)

    doc["items"][1]["status"] = "Shipped"
    src.write_text(json.dumps(doc), encoding="utf-8")
    second = bi.import_board(tmp_path, src, bi.PROFILE_GENERIC, now=NOW)

    assert second["updated"] == 1
    assert second["imported"] == 0
    assert second["events"] == 1, "an update must not mint a second item_created"

    created = [e for e in bi._read_ledger(tmp_path)
               if e["event"] == "item_created" and e["item_id"] == "ST-70"]
    assert len(created) == 1
    assert fold_of(tmp_path)["ST-70"]["status"] == "shipped"


# ----------------------------------------------------------- 3. the mapping

def test_generic_mapping_covers_the_documented_shape(tmp_path: Path) -> None:
    src = tmp_path / "board.json"
    src.write_text(json.dumps(generic_source()), encoding="utf-8")
    bi.import_board(tmp_path, src, bi.PROFILE_GENERIC, now=NOW)
    folded = fold_of(tmp_path)

    assert folded["ARC-7"]["kind"] == "arc"
    assert folded["BUG-3"]["kind"] == "bug"
    assert folded["ST-70"]["kind"] == "story"

    assert folded["ARC-7"]["status"] == "in_progress"      # "Active"
    assert folded["ST-70"]["status"] == "in_progress"      # "In Progress"
    assert folded["BUG-3"]["status"] == "blocked"
    assert folded["ST-71"]["status"] == "shipped"

    assert folded["ST-70"]["assignee"] == "Desmond"
    assert folded["ST-70"]["estimate"] == "M"
    assert folded["ST-70"]["parent_id"] == "ARC-7"
    assert folded["ST-70"]["arc_id"] == "ARC-7"
    assert folded["ST-70"]["arc_title"] == "Telemetry spine"


def test_an_unknown_status_falls_back_rather_than_dropping_the_item(tmp_path: Path) -> None:
    """The item still lands. The wall renders an unmapped status literally, so
    the failure mode is a visibly odd chip, never a missing row."""
    src = tmp_path / "board.json"
    src.write_text(json.dumps(generic_source()), encoding="utf-8")
    bi.import_board(tmp_path, src, bi.PROFILE_GENERIC, now=NOW)
    assert fold_of(tmp_path)["ST-72"]["status"] == bi.PROFILE_GENERIC["default_status"]


def test_items_with_no_arc_land_in_the_named_bucket(tmp_path: Path) -> None:
    """`arc_id` is always written. Left unset it folds to None, and the board
    grouping then sorts None against a string and dies."""
    src = tmp_path / "board.json"
    src.write_text(json.dumps(generic_source()), encoding="utf-8")
    bi.import_board(tmp_path, src, bi.PROFILE_GENERIC, now=NOW)
    folded = fold_of(tmp_path)
    assert folded["ST-71"]["arc_id"] == bi.UNASSIGNED_ARC_ID
    assert all(isinstance(i["arc_id"], str) for i in folded.values())


def test_placeholder_values_do_not_reach_the_board(tmp_path: Path) -> None:
    src = tmp_path / "board.json"
    src.write_text(json.dumps({"items": [
        {"id": "ST-1", "title": "x", "status": "todo", "pr": "--", "priority": "P1"},
    ]}), encoding="utf-8")
    bi.import_board(tmp_path, src, bi.PROFILE_GENERIC, now=NOW)
    folded = fold_of(tmp_path)["ST-1"]
    assert folded["pr"] is None, "a '--' placeholder was carried onto the wall"
    assert folded["priority"] == "P1"


def test_timestamps_normalise(tmp_path: Path) -> None:
    src = tmp_path / "board.json"
    src.write_text(json.dumps(generic_source()), encoding="utf-8")
    bi.import_board(tmp_path, src, bi.PROFILE_GENERIC, now=NOW)
    folded = fold_of(tmp_path)
    # Per-item timestamp wins ...
    assert folded["ST-70"]["updated_at"] == "2026-09-18T11:00:00.000Z"
    # ... and the document-level one is the fallback for the rest.
    assert folded["BUG-3"]["updated_at"] == "2026-09-18T00:00:00.000Z"


def test_status_normalisation_is_spelling_insensitive() -> None:
    profile = bi.PROFILE_SLUG_KEYED
    for spelling in ("in CI", "In-CI", "in_ci", "  IN CI  "):
        mapped = bi.map_item({"key": "k", "title": "t", "status": spelling},
                             profile, default_ts=NOW)
        assert mapped["fields"]["status"] == "review", spelling


# --------------------------------------------- 4. the slug-keyed profile

def test_slug_keyed_profile_shape() -> None:
    """The mappings the owner specified, asserted directly."""
    p = bi.PROFILE_SLUG_KEYED
    assert p["id_field"] == "key"          # slug keys become item ids verbatim
    assert p["arc_id_field"] == "arch"
    for source, wall in (("Todo", "planned"), ("Backlog", "planned"), ("Planned", "planned"),
                         ("in CI", "review"), ("In Progress", "in_progress"),
                         ("Shipped", "shipped"), ("Done", "done"), ("Deferred", "blocked")):
        mapped = bi.map_item({"key": "k", "title": "t", "status": source}, p, default_ts=NOW)
        assert mapped["fields"]["status"] == wall, f"{source} -> {wall}"
    deferred = bi.map_item({"key": "k", "title": "t", "status": "Deferred"}, p, default_ts=NOW)
    assert "deferred" in deferred["fields"]["note"], "a deferred item must say why it is blocked"


def test_slug_keyed_kind_heuristics() -> None:
    p = bi.PROFILE_SLUG_KEYED
    def kind(key, type_):
        return bi.map_item({"key": key, "title": "t", "status": "Todo", "type": type_},
                           p, default_ts=NOW)["fields"]["kind"]
    assert kind("fix:probe-timeout", "New Feature") == "bug"       # key prefix wins
    assert kind("brain:fibonacci-sequences", "New Feature") == "story"
    assert kind("review:gemini-replacement", "Bug") == "bug"       # type field
    assert kind("steward:home:1", "Enhancement") == "story"


def test_slug_keyed_keys_become_item_ids_verbatim() -> None:
    mapped = bi.map_item({"key": "brain:fibonacci-sequences", "title": "t", "status": "Todo"},
                         bi.PROFILE_SLUG_KEYED, default_ts=NOW)
    assert mapped["item_id"] == "brain:fibonacci-sequences"


@pytest.mark.skipif(not REAL_BOARD.is_file(), reason="no real slug-keyed board (WALL_REAL_BOARD)")
def test_slug_keyed_real_board_imports_and_folds(tmp_path: Path) -> None:
    """The proof on real data: every row lands, nothing is left unusable, and
    the folded board is renderable (every arc_id a string, every status known
    or literal)."""
    source = json.loads(REAL_BOARD.read_text(encoding="utf-8"))
    result = bi.import_board(tmp_path, source, bi.PROFILE_SLUG_KEYED, now=NOW)

    assert result["unusable"] == 0
    assert result["imported"] == len(source["items"])
    assert result["events"] == 2 * result["imported"]

    folded = fold_of(tmp_path)
    assert len(folded) == result["imported"]
    assert all(isinstance(i["arc_id"], str) and i["arc_id"] for i in folded.values())
    assert all(i["kind"] in bi.WALL_KINDS for i in folded.values())
    assert all(i["status"] in bi.WALL_STATUSES for i in folded.values())
    assert all(i["title"] for i in folded.values())

    # Arcs are derived from THIS board, not from one known fixture: every
    # distinct non-blank `arch` becomes an arc, and a blank one lands in the
    # unassigned arc -- whatever board WALL_REAL_BOARD names.
    field = bi.PROFILE_SLUG_KEYED["arc_id_field"]
    raw = [row.get(field) for row in source["items"]]
    expected = {a.strip() for a in raw if isinstance(a, str) and a.strip()}
    if any(not (isinstance(a, str) and a.strip()) for a in raw):
        expected.add(bi.UNASSIGNED_ARC_ID)
    assert {i["arc_id"] for i in folded.values()} == expected


# ------------------------------------------------------------------- 5. CLI

def test_cli_round_trip(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    src = tmp_path / "board.json"
    src.write_text(json.dumps(generic_source()), encoding="utf-8")
    rc = bi.main(["--repo", str(tmp_path), "--source", str(src),
                  "--profile", "generic", "--json"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["imported"] == 5 and out["profile"] == "generic"


def test_cli_offers_the_slug_keyed_profile(tmp_path: Path,
                                           capsys: pytest.CaptureFixture) -> None:
    """The CLI choice is the format's name; the profile it selects is
    PROFILE_SLUG_KEYED. Mutation: rename the PROFILES key and argparse rejects
    the choice (SystemExit), failing here."""
    assert bi.PROFILES["slug-keyed"] is bi.PROFILE_SLUG_KEYED
    src = tmp_path / "board.json"
    src.write_text(json.dumps({"updated": "2026-09-18", "items": [
        {"key": "brain:fibonacci-sequences", "title": "t", "status": "Todo"}]}),
        encoding="utf-8")
    rc = bi.main(["--repo", str(tmp_path), "--source", str(src),
                  "--profile", "slug-keyed", "--json"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["imported"] == 1 and out["profile"] == "slug-keyed"


def test_cli_reports_a_bad_source_without_traceback(tmp_path: Path,
                                                    capsys: pytest.CaptureFixture) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert bi.main(["--repo", str(tmp_path), "--source", str(bad)]) == 1
    assert "board import failed" in capsys.readouterr().err
