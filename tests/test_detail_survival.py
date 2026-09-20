"""The board's long-form detail survives onto the wall -- end to end.

The adoption requirement (host direction, 2026-09-20): every arc, story,
status AND detail must survive the move to the kit wall's layout. Three
layers, each pinned with the mutation that kills it:

* PROFILE_MAX3 maps `detail` (drop the extra_fields entry -> mapping test fails);
* the template renders a toggle + panel for items that carry detail, and none
  for items that do not (drop the detailRow call -> render tests fail);
* the detail text is HTML-ESCAPED into the panel -- item prose routinely
  quotes code and markup, and an unescaped panel is an XSS sink on a page
  that inlines its whole dataset (drop esc() -> the script-tag test fails).
"""

from __future__ import annotations

import json

import courier
from adapters import board_import as bi

TEMPLATE = None  # resolved lazily via courier's default


def _render(snapshot):
    from pathlib import Path
    import courier as c
    template = Path(c.__file__).parent / "render" / "wall_template.html"
    return c.render(snapshot, template)


def _snapshot_with_items(items):
    return {
        "schema_version": 1, "generated_at": "2026-09-20T00:00:00.000Z",
        "generated_epoch": 0, "stale_after_s": 300,
        "repo": {"name": "ProbeRepo", "branch": "main"},
        "integrity": {"flags": []}, "role_limits": {},
        "crew": [], "board": {"arcs": [{"arc_id": "ARC-X", "title": "Arc X",
                                        "items": items}]},
        "waiting_on_you": [], "questions": [],
        "budget": {"meters": []}, "rollup_by_role": [], "sessions": [],
    }


def test_profile_max3_maps_detail():
    row = {"key": "brain:probe", "title": "Probe", "status": "Shipped",
           "arch": "BRAIN", "detail": "the long-form as-built prose"}
    mapped = bi.map_item(row, bi.PROFILE_MAX3, default_ts="2026-09-20T00:00:00.000Z")
    assert mapped["fields"]["detail"] == "the long-form as-built prose"


def test_item_with_detail_renders_toggle_and_panel():
    html = _render(_snapshot_with_items([
        {"item_id": "ST-1", "title": "Has detail", "kind": "story",
         "status": "shipped", "detail": "DETAIL_SENTINEL_TEXT",
         "pr": "#1656", "updated_at": "2026-09-20T00:00:00.000Z"},
    ]))
    assert "dtoggle" in html
    assert "DETAIL_SENTINEL_TEXT" in html
    assert "#1656" in html  # the meta chip line carries pr


def test_toggle_is_conditional_on_detail_in_the_row_builder():
    """Rows are built client-side, so the server render cannot be asserted on
    directly -- pin the CONDITION instead: itemRow only emits the toggle and
    the sibling row inside its hasDetail branch. Mutation that kills this:
    make the toggle unconditional, and the hasDetail guard disappears from
    the source between the two markers."""
    from pathlib import Path
    import courier as c
    template = (Path(c.__file__).parent / "render" / "wall_template.html").read_text(encoding="utf-8")
    body = template.split("function itemRow")[1].split("function nestedRows")[0]
    assert "hasDetail ? '<button class=\"dtoggle\"" in body
    assert "if (hasDetail) row += detailRow(it);" in body


def test_detail_is_escaped_not_injected():
    html = _render(_snapshot_with_items([
        {"item_id": "ST-3", "title": "Sneaky", "kind": "story",
         "status": "planned", "detail": "<script>alert(1)</script>",
         "updated_at": "2026-09-20T00:00:00.000Z"},
    ]))
    # courier.render escapes <> in the inlined JSON payload; the template's
    # esc() escapes again at DOM-build time. The raw tag must never appear.
    assert "<script>alert(1)</script>" not in html


def test_template_carries_the_page_marker():
    from pathlib import Path
    import courier as c
    template = Path(c.__file__).parent / "render" / "wall_template.html"
    assert "<!-- engteam-wall -->" in template.read_text(encoding="utf-8")


def test_clearing_a_field_on_the_board_clears_it_on_the_wall(repo):
    """The omitted-key hole (review finding, MAX3 #1658): a field cleared on
    the source board must not survive on the wall. Mutation that kills this:
    go back to omitting blank fields in map_item and both asserts fail --
    the idempotence check re-reports the item unchanged and the fold keeps
    the stale detail and the stale deferred note."""
    board = {"updated": "2026-09-20", "items": [
        {"key": "infra:clearing", "title": "Clearing probe", "status": "Deferred",
         "arch": "INFRA", "pr": "#7", "detail": "SOON_GONE"},
    ]}
    bi.import_board(repo, board, bi.PROFILE_MAX3)
    board["items"][0]["detail"] = ""      # cleared on the tracker
    board["items"][0]["pr"] = "--"        # reset to the null token
    board["items"][0]["status"] = "in CI" # leaves the noted status too
    result = bi.import_board(repo, board, bi.PROFILE_MAX3)
    assert result["updated"] == 1, "the clear must register as a change"

    import items as items_mod
    folded = items_mod.fold_items(bi._read_ledger(repo))
    it = folded["infra:clearing"]
    assert it["detail"] is None
    assert it["pr"] is None
    assert it["note"] is None, "the deferred note must not outlive the status"


def test_non_dict_json_lines_count_as_corrupt(repo):
    """`null` and bare scalars parse fine and then vanish in merge();
    without this they left the heartbeat reading ok (review finding,
    MAX3 #1658). Mutation: drop the isinstance check and ok reads true."""
    import json as _json
    path = repo / ".wall" / "events" / "2026-09-19" / "s_a.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("null\n[1, 2]\n\"scalar\"\n", encoding="utf-8")
    courier.run_once(repo)
    hb = _json.loads(
        (repo / ".wall" / "derived" / "heartbeat.json").read_text(encoding="utf-8"))
    assert hb["ok"] is False
    assert hb["corrupt_lines"] == 3


def test_import_to_render_roundtrip_carries_detail(repo):
    """The full path a real adoption takes: tracker JSON -> import_board ->
    courier sweep -> rendered wall.html containing the detail text."""
    board = {"updated": "2026-09-20", "items": [
        {"key": "infra:probe", "title": "Probe item", "status": "in CI",
         "arch": "INFRA", "pr": "#1656", "priority": "P1",
         "detail": "ROUNDTRIP_DETAIL_SENTINEL"},
    ]}
    result = bi.import_board(repo, board, bi.PROFILE_MAX3)
    assert result["imported"] == 1
    courier.run_once(repo)
    html = (repo / ".wall" / "derived" / "wall.html").read_text(encoding="utf-8")
    assert "ROUNDTRIP_DETAIL_SENTINEL" in html
    snapshot = json.loads((repo / ".wall" / "derived" / "wall.json").read_text(encoding="utf-8"))
    arcs = {a["arc_id"]: a for a in snapshot["board"]["arcs"]}
    item = arcs["INFRA"]["items"][0]
    assert item["detail"] == "ROUNDTRIP_DETAIL_SENTINEL"
    assert item["status"] == "review"  # in CI -> review per the profile
