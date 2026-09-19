"""testkit tests.

Every assertion here is written so that deleting the behaviour it names turns it
red -- the property docs/TESTING_STANDARDS.md section 3 requires. Two cases are
called out because they are the ones hand-written fixtures never construct:

* `test_balance_is_deterministic_on_a_tie` -- equal durations. A bare tuple sort
  reaches its second element only on a tie, so the tie is the only input that
  can expose an unstable key.
* `test_needs_rebalance_is_strict_at_the_boundary` -- the threshold value
  itself. `>` and `>=` agree on every other input, so only the boundary kills a
  mutation between them.
"""

from __future__ import annotations

import io
import json
import math
from pathlib import Path

import pytest

import testkit
from testkit import (
    BalanceError,
    DurationsError,
    ShardMapError,
    balance,
    load_shard_map,
    needs_rebalance,
    parse_durations,
    select,
    shard_drift,
    write_shard_map,
)

PYTEST_OUTPUT = """\
============================= slowest durations ==============================
2.50s call     tests/unit/test_a.py::test_slow
0.50s setup    tests/unit/test_a.py::test_slow
1.00s call     tests/unit/test_b.py::test_mid
0.25s call     tests/system/test_c.py::test_fast
0.00s teardown tests/system/test_c.py::test_fast
(3 durations < 0.005s hidden.)
"""


# ------------------------------------------------------------- parse_durations

def test_parses_pytest_output_and_sums_the_three_phases():
    out = parse_durations(PYTEST_OUTPUT)
    assert out == {
        "tests/unit/test_a.py::test_slow": 3.0,   # 2.50 call + 0.50 setup
        "tests/unit/test_b.py::test_mid": 1.0,
        "tests/system/test_c.py::test_fast": 0.25,
    }


def test_header_and_footer_lines_are_not_records():
    out = parse_durations(PYTEST_OUTPUT)
    assert not [k for k in out if "durations" in k or k.startswith("(")]


def test_parses_a_json_object():
    text = json.dumps({"tests/unit/test_a.py::test_x": 1.5})
    assert parse_durations(text) == {"tests/unit/test_a.py::test_x": 1.5}


def test_a_json_suffixed_path_is_parsed_as_json_and_fails_loudly(tmp_path: Path):
    path = tmp_path / "d.json"
    path.write_text("0.10s call tests/unit/test_a.py::test_x\n", encoding="utf-8")
    with pytest.raises(DurationsError) as exc:
        parse_durations(path)
    assert "malformed JSON" in str(exc.value)


def test_path_reads_from_disk(tmp_path: Path):
    path = tmp_path / "durations.txt"
    path.write_text(PYTEST_OUTPUT, encoding="utf-8")
    assert parse_durations(path)["tests/unit/test_b.py::test_mid"] == 1.0


def test_a_str_is_text_never_a_path(tmp_path: Path):
    """Sniffing would make the result depend on what happens to exist on disk."""
    path = tmp_path / "durations.txt"
    path.write_text(PYTEST_OUTPUT, encoding="utf-8")
    assert parse_durations(str(path)) == {}


def test_missing_file_is_an_error_not_an_empty_mapping(tmp_path: Path):
    with pytest.raises(DurationsError) as exc:
        parse_durations(tmp_path / "nope.txt")
    assert "no durations file" in str(exc.value)


def test_empty_text_is_an_empty_mapping():
    assert parse_durations("   \n\n") == {}


def test_non_object_json_is_named():
    with pytest.raises(DurationsError) as exc:
        parse_durations('[["a", 1]]')
    assert "object mapping test id to seconds" in str(exc.value)
    assert "list" in str(exc.value)


@pytest.mark.parametrize("doc,fragment", [
    ('{"t::x": "fast"}', "expected a number"),
    ('{"t::x": true}', "expected a number"),
    ('{"t::x": null}', "expected a number"),
    ('{"t::x": -1.0}', "negative"),
    ('{"t::x": Infinity}', "not finite"),
    ('{"t::x": NaN}', "not finite"),
])
def test_bad_duration_values_are_named(doc, fragment):
    with pytest.raises(DurationsError) as exc:
        parse_durations(doc)
    assert fragment in str(exc.value)
    assert "t::x" in str(exc.value)


def test_an_empty_test_id_is_rejected():
    with pytest.raises(DurationsError) as exc:
        parse_durations('{"  ": 1.0}')
    assert "empty or non-string test id" in str(exc.value)


def test_unparsed_record_shaped_lines_are_reported_not_swallowed():
    problems: list[str] = []
    out = parse_durations("garbage tests/unit/test_a.py::test_x\n", problems=problems)
    assert out == {}
    assert len(problems) == 1
    assert "tests/unit/test_a.py::test_x" in problems[0]


def test_chrome_lines_are_not_reported_as_problems():
    problems: list[str] = []
    parse_durations("===== slowest durations =====\n", problems=problems)
    assert problems == []


def test_a_wrong_source_type_is_named():
    with pytest.raises(DurationsError) as exc:
        parse_durations(42)  # type: ignore[arg-type]
    assert "str (text) or a Path" in str(exc.value)


# -------------------------------------------------------------------- balance

def test_longest_test_goes_into_the_lightest_shard():
    """5 -> s1; 3 -> s2; 2 -> s2 (lighter at 3); 2 -> s1 (tied at 5, first wins).

    Count-balancing would put two tests in each and leave 8s against 4s; packing
    by measured duration leaves 7s against 5s.
    """
    result = balance({"a": 5.0, "b": 3.0, "c": 2.0, "d": 2.0}, 2)
    assert result.shards == [["a", "d"], ["b", "c"]]
    assert result.stats["totals"] == [7.0, 5.0]


def test_balance_is_deterministic_on_a_tie():
    """Equal durations: the only input where the sort reaches its second key."""
    durations = {"z::t": 1.0, "a::t": 1.0, "m::t": 1.0, "b::t": 1.0}
    first = balance(durations, 2).shards
    reversed_insert = balance({k: durations[k] for k in reversed(list(durations))}, 2)
    assert first == reversed_insert.shards
    # And the tie-break is the test id, not insertion order.
    assert first[0][0] == "a::t"


def test_stats_report_the_split():
    stats = balance({"a": 4.0, "b": 2.0, "c": 2.0}, 2).stats
    assert stats["n_shards"] == 2
    assert stats["n_tests"] == 3
    assert stats["counts"] == [1, 2]
    assert stats["total"] == 8.0
    assert stats["max"] == 4.0
    assert stats["min"] == 4.0
    assert stats["median"] == 4.0
    assert stats["imbalance"] == 1.0


def test_an_empty_suite_gives_empty_shards_not_a_crash():
    result = balance({}, 3)
    assert result.shards == [[], [], []]
    assert result.stats["imbalance"] == 1.0
    assert result.stats["n_tests"] == 0


def test_half_empty_shards_report_infinite_imbalance_not_one():
    """A zero median with a non-zero max is the case a rebalance most needs to
    see; reporting 1.0 there would hide it."""
    stats = balance({"a": 9.0}, 4).stats
    assert math.isinf(stats["imbalance"])
    assert needs_rebalance(stats) is True


@pytest.mark.parametrize("n,fragment", [
    (0, ">= 1"),
    (-2, ">= 1"),
    (True, "must be an int"),
    ("4", "must be an int"),
])
def test_bad_shard_counts_are_named(n, fragment):
    with pytest.raises(BalanceError) as exc:
        balance({"a": 1.0}, n)
    assert fragment in str(exc.value)


def test_balance_rejects_a_bad_duration_value():
    with pytest.raises(DurationsError):
        balance({"a": "slow"}, 2)  # type: ignore[dict-item]


def test_balance_rejects_a_non_mapping():
    with pytest.raises(BalanceError) as exc:
        balance([("a", 1.0)], 2)  # type: ignore[arg-type]
    assert "must be a mapping" in str(exc.value)


# ------------------------------------------------------------ needs_rebalance

def test_needs_rebalance_is_strict_at_the_boundary():
    """`>` and `>=` differ on exactly one input: the threshold itself."""
    assert needs_rebalance({"imbalance": 1.5}, 1.5) is False
    assert needs_rebalance({"imbalance": 1.5000001}, 1.5) is True
    assert needs_rebalance({"imbalance": 1.49}, 1.5) is False


def test_needs_rebalance_default_threshold_is_one_and_a_half():
    assert needs_rebalance({"imbalance": 1.5}) is False
    assert needs_rebalance({"imbalance": 1.6}) is True


@pytest.mark.parametrize("stats,fragment", [
    ({}, "no 'imbalance' key"),
    ({"imbalance": "high"}, "must be a number"),
    ({"imbalance": True}, "must be a number"),
    ([], "must be a mapping"),
])
def test_bad_stats_are_named(stats, fragment):
    with pytest.raises(BalanceError) as exc:
        needs_rebalance(stats)
    assert fragment in str(exc.value)


# ------------------------------------------------------------------ shard map

def test_write_then_load_roundtrips(tmp_path: Path):
    shards = [["a::t"], ["b::t", "c::t"]]
    path = write_shard_map(tmp_path, shards)
    assert path == tmp_path / ".wall" / "config" / "shards.json"
    assert load_shard_map(tmp_path) == shards


def test_the_written_map_says_it_is_derived(tmp_path: Path):
    write_shard_map(tmp_path, [["a::t"]])
    doc = json.loads((tmp_path / ".wall" / "config" / "shards.json").read_text())
    assert doc["generator"] == "tools/wall/testkit.py"
    assert "never hand-edit" in doc["note"]


def test_infinite_stats_are_written_as_null_not_as_invalid_json(tmp_path: Path):
    result = balance({"a": 9.0}, 4)
    write_shard_map(tmp_path, result.shards, result.stats)
    raw = (tmp_path / ".wall" / "config" / "shards.json").read_text(encoding="utf-8")
    assert "Infinity" not in raw
    assert json.loads(raw)["stats"]["imbalance"] is None


def test_a_missing_map_is_an_error_not_an_empty_map(tmp_path: Path):
    with pytest.raises(ShardMapError) as exc:
        load_shard_map(tmp_path)
    assert "no shard map at" in str(exc.value)


def test_a_malformed_map_names_the_position(tmp_path: Path):
    path = tmp_path / ".wall" / "config" / "shards.json"
    path.parent.mkdir(parents=True)
    path.write_text('{"shards": [[', encoding="utf-8")
    with pytest.raises(ShardMapError) as exc:
        load_shard_map(tmp_path)
    assert "malformed shard map" in str(exc.value)
    assert "line 1" in str(exc.value)


def test_a_map_document_without_shards_is_named(tmp_path: Path):
    path = tmp_path / ".wall" / "config" / "shards.json"
    path.parent.mkdir(parents=True)
    path.write_text('{"groups": []}', encoding="utf-8")
    with pytest.raises(ShardMapError) as exc:
        load_shard_map(tmp_path)
    assert "no 'shards' key" in str(exc.value)


@pytest.mark.parametrize("shards,fragment", [
    ("a", "list of lists"),
    ([{"a": 1}], "shard 1 must be a list"),
    ([["a::t", 7]], "non-string test id"),
    ([["a::t", "  "]], "non-string test id"),
])
def test_bad_shard_shapes_are_named(shards, fragment, tmp_path: Path):
    with pytest.raises(ShardMapError) as exc:
        write_shard_map(tmp_path, shards)
    assert fragment in str(exc.value)


# --------------------------------------------------------------------- select

def test_select_is_one_based():
    shards = [["a::t"], ["b::t"], ["c::t"]]
    assert select(shards, 1) == ["a::t"]
    assert select(shards, 3) == ["c::t"]


@pytest.mark.parametrize("index", [0, 4, -1])
def test_select_rejects_an_out_of_range_index(index):
    with pytest.raises(ShardMapError) as exc:
        select([["a::t"], ["b::t"], ["c::t"]], index)
    assert "out of range" in str(exc.value)
    assert "1..3" in str(exc.value)


@pytest.mark.parametrize("index", [True, "1", 1.0])
def test_select_rejects_a_non_int_index(index):
    with pytest.raises(ShardMapError) as exc:
        select([["a::t"]], index)
    assert "must be an int" in str(exc.value)


def test_select_accepts_the_written_document(tmp_path: Path):
    write_shard_map(tmp_path, [["a::t"], ["b::t"]])
    doc = json.loads((tmp_path / ".wall" / "config" / "shards.json").read_text())
    assert select(doc, 2) == ["b::t"]


def test_select_returns_a_copy_so_a_caller_cannot_edit_the_map():
    shards = [["a::t"]]
    select(shards, 1).append("b::t")
    assert shards == [["a::t"]]


def test_an_empty_shard_selects_nothing():
    """A correct answer and a trap: pytest with no arguments runs everything."""
    assert select([["a::t"], []], 2) == []


# ---------------------------------------------------------------- shard_drift

def test_drift_reports_both_directions():
    drift = shard_drift([["a::t", "gone::t"]], {"a::t": 1.0, "new::t": 2.0})
    assert drift["mapped_not_measured"] == ["gone::t"]
    assert drift["measured_not_mapped"] == ["new::t"]


def test_no_drift_on_an_exact_match():
    drift = shard_drift([["a::t"], ["b::t"]], {"a::t": 1.0, "b::t": 1.0})
    assert drift == {"mapped_not_measured": [], "measured_not_mapped": []}


# ------------------------------------------------------------------------ CLI

def test_cli_durations_reads_stdin(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO(PYTEST_OUTPUT))
    assert testkit.main(["durations", "--input", "-"]) == 0
    out = capsys.readouterr().out
    assert "tests measured : 3" in out
    assert "3.000s  tests/unit/test_a.py::test_slow" in out


def test_cli_balance_writes_the_map(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO(PYTEST_OUTPUT))
    code = testkit.main(["balance", "--shards", "2", "--input", "-",
                         "--repo", str(tmp_path), "--write"])
    assert code == 0
    assert load_shard_map(tmp_path) == [["tests/unit/test_a.py::test_slow"],
                                        ["tests/unit/test_b.py::test_mid",
                                         "tests/system/test_c.py::test_fast"]]
    assert "wrote" in capsys.readouterr().out


def test_cli_balance_exits_one_when_imbalanced(monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO('{"a::t": 10.0, "b::t": 0.1}'))
    assert testkit.main(["balance", "--shards", "2", "--input", "-"]) == 1


def test_cli_check_is_green_on_a_balanced_map(tmp_path: Path, monkeypatch, capsys):
    write_shard_map(tmp_path, [["a::t"], ["b::t"]])
    monkeypatch.setattr("sys.stdin", io.StringIO('{"a::t": 1.0, "b::t": 1.0}'))
    assert testkit.main(["check", "--repo", str(tmp_path), "--input", "-"]) == 0
    assert "balanced" in capsys.readouterr().out


def test_cli_check_flags_drift_even_when_the_totals_look_even(tmp_path: Path,
                                                              monkeypatch, capsys):
    """A map naming tests that no longer exist runs fewer tests than it says."""
    write_shard_map(tmp_path, [["a::t"], ["gone::t"]])
    monkeypatch.setattr("sys.stdin", io.StringIO('{"a::t": 1.0, "b::t": 1.0}'))
    assert testkit.main(["check", "--repo", str(tmp_path), "--input", "-"]) == 1
    out = capsys.readouterr().out
    assert "drift mapped_not_measured: 1" in out
    assert "drift measured_not_mapped: 1" in out


def test_cli_check_without_durations_refuses_rather_than_guessing(tmp_path: Path,
                                                                  capsys):
    write_shard_map(tmp_path, [["a::t"]])
    assert testkit.main(["check", "--repo", str(tmp_path)]) == 2
    assert "needs measured durations" in capsys.readouterr().err


def test_cli_reports_a_testkit_error_as_exit_two(tmp_path: Path, capsys):
    assert testkit.main(["check", "--repo", str(tmp_path), "--input", "-"]) == 2
    assert "no shard map at" in capsys.readouterr().err
