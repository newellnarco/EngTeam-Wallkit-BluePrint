"""contracts.py — the wall's wire contracts, typed once (DEC-0018 clause 2).

The template is JavaScript and must stay static, so it cannot import the
module; instead its literals are PINNED here against the module's values.
That is the one-authority-one-mirror rule: change a contract in
contracts.py and every stale JS copy fails by name; change the JS alone
and the same pins fail. Mutations that kill each block are named on the
tests.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import contracts as c
import courier

TEMPLATE = (Path(courier.__file__).parent / "render" /
            "wall_template.html").read_text(encoding="utf-8")


# ------------------------------------------------------------ the enqueue

def test_enqueue_payload_item_happy_path():
    p = c.EnqueuePayload(directive=c.Directive.EXECUTE_ITEM,
                         target_key="brain:probe", title="Execute brain:probe")
    assert p.to_dict() == {
        "source": "wall_click", "priority": "P2",
        "directive": "execute_item", "target_key": "brain:probe",
        "title": "Execute brain:probe",
    }


def test_enqueue_payload_arc_happy_path():
    p = c.EnqueuePayload(directive=c.Directive.EXECUTE_ARC,
                         target_arch="BRAIN", title="Execute arc BRAIN")
    d = p.to_dict()
    assert d["directive"] == "execute_arc"
    assert d["target_arch"] == "BRAIN"
    assert "target_key" not in d


def test_enqueue_payload_refuses_a_directive_without_its_target():
    """A payload the host would half-understand is refused at construction.
    Mutation: drop either __post_init__ guard and its case passes silently."""
    with pytest.raises(ValueError, match="target_key"):
        c.EnqueuePayload(directive=c.Directive.EXECUTE_ITEM, title="x")
    with pytest.raises(ValueError, match="target_arch"):
        c.EnqueuePayload(directive=c.Directive.EXECUTE_ARC, title="x")
    with pytest.raises(ValueError, match="title"):
        c.EnqueuePayload(directive=c.Directive.EXECUTE_ITEM,
                         target_key="k", title="")


def test_template_enqueue_literals_mirror_contracts():
    """The EXECUTE port's JS builds the same payload this module types.
    Assertions are DERIVED from the module's values — never re-typed
    strings — so editing the contract moves the pin with it."""
    assert ("directive: '%s', target_key: key" % c.Directive.EXECUTE_ITEM) in TEMPLATE
    assert ("directive: '%s', target_arch: arcId" % c.Directive.EXECUTE_ARC) in TEMPLATE
    assert ("{ source: '%s', priority: '%s' }"
            % (c.ENQUEUE_SOURCE, c.ENQUEUE_PRIORITY)) in TEMPLATE


# ------------------------------------------------------------- item status

def test_canon_status_folds_aliases_and_spellings():
    assert c.canon_status("In Review") is c.ItemStatus.REVIEW
    assert c.canon_status("in-CI") is c.ItemStatus.REVIEW
    assert c.canon_status("Active") is c.ItemStatus.IN_PROGRESS
    assert c.canon_status("shipped") is c.ItemStatus.SHIPPED
    assert c.canon_status("triage") is c.ItemStatus.PLANNED
    assert c.canon_status("some exotic state") is None
    assert c.canon_status(None) is None


def test_template_status_tables_mirror_contracts():
    """STATUS_CANON / STATUS_ALIAS in the page are the pinned JS mirror of
    ItemStatus / STATUS_ALIASES here. Mutation: add an alias to either
    side alone and the missing twin is named."""
    for status in c.ItemStatus:
        assert f"{status.value}: 1" in TEMPLATE, (
            f"template STATUS_CANON lost {status.value!r}")
    for alias, target in c.STATUS_ALIASES.items():
        assert f"{alias}: '{target.value}'" in TEMPLATE, (
            f"template STATUS_ALIAS lost {alias!r} -> {target.value!r}")


def test_template_declares_no_alias_contracts_lacks():
    """The mirror must not GROW on its own either: every alias pair in the
    template's STATUS_ALIAS block exists in contracts."""
    block = TEMPLATE.split("var STATUS_ALIAS = {")[1].split("};")[0]
    import re
    pairs = re.findall(r"(\w+):\s*'(\w+)'", block)
    assert pairs, "could not read the template's alias table"
    for alias, target in pairs:
        assert c.STATUS_ALIASES.get(alias) == c.ItemStatus(target), (
            f"template alias {alias!r} -> {target!r} missing from contracts")


def test_in_flight_and_done_partition():
    assert c.IN_FLIGHT_STATUSES.isdisjoint(c.DONE_LIKE)
    assert c.ItemStatus.PLANNED not in c.IN_FLIGHT_STATUSES


# -------------------------------------------------------- the agents wave

def test_wave_status_from_payload_roundtrip():
    w = c.WaveStatus.from_payload({
        "updated": "2026-09-20T18:00:00Z",
        "headcount": {"developers": 6, "researchers": 2, "cap": 9},
        "completed": ["U1"], "in_progress": [{"agent": "a", "unit": "U2"}],
        "new": [],
    })
    assert (w.developers, w.researchers, w.cap) == (6, 2, 9)
    assert w.completed == ("U1",)
    assert w.in_progress[0]["unit"] == "U2"


def test_wave_status_names_missing_keys():
    with pytest.raises(ValueError, match="in_progress"):
        c.WaveStatus.from_payload({"updated": "t", "headcount": {},
                                   "completed": [], "new": []})


def test_template_reads_exactly_the_wave_keys():
    """paintWave reads w.<key> for every required key — a key renamed in
    the envelope alone leaves the panel silently blank."""
    painter = TEMPLATE.split("function paintWave")[1].split("$('tabs')")[0]
    for key in c.WAVE_REQUIRED_KEYS:
        assert (f"w.{key}" in painter) or (f"w['{key}']" in painter), (
            f"paintWave no longer reads {key!r}")


# ------------------------------------------------------------ doc maps

def test_doc_maps_are_complete():
    """MAX's type-design discipline: every enum member carries its doc.
    Mutation: add a Directive or kind without documenting it."""
    assert set(c.DIRECTIVE_DOCS) == set(c.Directive)
    assert set(c.KIND_DOCS) == set(c.RelayFailureKind)


def test_relay_failure_kinds_are_the_three_sentences():
    assert {k.value for k in c.RelayFailureKind} == {
        "max_http_error", "max_unreachable", "relay_refused"}


def test_enqueue_payload_normalizes_a_raw_string_directive():
    """CodeRabbit finding (accepted): a raw "execute_item" string used to
    slip past the identity checks and skip target validation entirely.
    Now it normalizes to the enum — and still demands its target."""
    p = c.EnqueuePayload(directive="execute_item",
                         target_key="k", title="t")
    assert p.directive is c.Directive.EXECUTE_ITEM
    with pytest.raises(ValueError, match="target_key"):
        c.EnqueuePayload(directive="execute_item", title="t")
    with pytest.raises(ValueError, match="unknown directive"):
        c.EnqueuePayload(directive="delete_everything", title="t")
