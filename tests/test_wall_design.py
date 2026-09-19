"""test_wall_design.py -- the wall's design contract.

The wall is a single self-contained HTML file: it is opened from `file://` as
often as it is served, so there is no stylesheet for it to link. The design
system therefore has to be *embedded*, and an embedded copy is a copy that can
drift. These tests are the sync guard.

Three properties, each one a thing that has silently broken before in pages
built this way:

1. **No drift.** Every custom property defined in `frontend/theme/theme.css`
   appears in the template's style block. Adding a token to the theme without
   re-embedding fails here rather than at the next screenshot.
2. **No raw colour.** Outside the embedded token block, the template's CSS
   contains no hex literal. A colour that bypasses the tokens is a colour that
   does not follow light mode.
3. **It still renders.** The rendered sample wall carries the four tab labels,
   a chip for every distinct status the sample ledger contains, and the arc
   grouping -- so a theme edit that breaks the markup is caught here too.

Stdlib + pytest only.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

KIT = Path(__file__).resolve().parents[1]
TEMPLATE = KIT / "tools" / "wall" / "render" / "wall_template.html"
THEME_CSS = KIT / "frontend" / "theme" / "theme.css"
SAMPLE_SNAPSHOT = KIT / "sample" / ".wall" / "derived" / "wall.json"

BEGIN_MARK = "==== BEGIN theme.css"
END_MARK = "==== END theme.css"

# The tab labels the owner named. They are the page's contract with whoever is
# looking at it; renaming one is a deliberate act, not a refactor.
TAB_LABELS = ("STORIES", "AGENTS", "LEDGER", "WAITING")

# The closed status set. Each gets exactly one chip class; anything else falls
# back to `chip--st-unknown` and is still rendered literally.
CANONICAL_STATUSES = ("planned", "in_progress", "blocked", "review", "done", "shipped")

HEX = re.compile(r"#[0-9a-fA-F]{3,8}\b")
CUSTOM_PROP = re.compile(r"(--[a-zA-Z0-9_-]+)\s*:")


# ------------------------------------------------------------------ fixtures

@pytest.fixture(scope="module")
def template_text() -> str:
    assert TEMPLATE.is_file(), f"missing template: {TEMPLATE}"
    return TEMPLATE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def style_block(template_text: str) -> str:
    """Everything between the first <style> and its </style>."""
    start = template_text.index("<style>") + len("<style>")
    end = template_text.index("</style>", start)
    return template_text[start:end]


@pytest.fixture(scope="module")
def rendered_sample() -> str:
    """The sample snapshot pushed through the real renderer.

    Uses `courier.render`, not a re-implementation, so the test exercises the
    path the box actually runs. Pure: nothing under sample/ is written.
    """
    if not SAMPLE_SNAPSHOT.is_file():
        pytest.skip(
            "sample snapshot absent -- run: "
            "cd sample && python3 make_sample.py && python3 ../tools/wall/courier.py --repo ."
        )
    wall_dir = KIT / "tools" / "wall"
    if str(wall_dir) not in sys.path:
        sys.path.insert(0, str(wall_dir))
    import courier  # noqa: E402  -- read-only use of another unit's module

    snapshot = json.loads(SAMPLE_SNAPSHOT.read_text(encoding="utf-8"))
    return courier.render(snapshot, TEMPLATE)


@pytest.fixture(scope="module")
def sample_snapshot() -> dict:
    if not SAMPLE_SNAPSHOT.is_file():
        pytest.skip("sample snapshot absent")
    return json.loads(SAMPLE_SNAPSHOT.read_text(encoding="utf-8"))


# ------------------------------------------------- 1. the embed cannot drift

def test_theme_block_is_marked(style_block: str) -> None:
    """The embed is delimited, so both the test and a human can find it."""
    assert BEGIN_MARK in style_block
    assert END_MARK in style_block
    assert style_block.index(BEGIN_MARK) < style_block.index(END_MARK)


def test_every_theme_token_is_embedded(style_block: str) -> None:
    """Every custom property NAME defined in theme.css appears in the template.

    This is the sync guard: a token added to the theme and not re-embedded is a
    token the wall resolves to nothing, which renders as an invisible element
    rather than as an error.
    """
    theme = THEME_CSS.read_text(encoding="utf-8")
    defined = {m.group(1) for m in CUSTOM_PROP.finditer(theme)}
    assert defined, "theme.css defines no custom properties -- wrong file?"
    missing = sorted(name for name in defined if name not in style_block)
    assert not missing, (
        "theme.css tokens missing from the embedded block in wall_template.html: "
        + ", ".join(missing)
        + " -- re-embed theme.css between the BEGIN/END markers."
    )


def test_theme_block_is_verbatim(style_block: str) -> None:
    """The embedded block is theme.css itself, not a paraphrase of it."""
    theme = THEME_CSS.read_text(encoding="utf-8").strip()
    start = style_block.index(BEGIN_MARK)
    start = style_block.index("\n", start) + 1
    end = style_block.index(END_MARK)
    end = style_block.rindex("/*", start, end)
    embedded = style_block[start:end].strip()
    assert embedded == theme, (
        "the embedded theme block differs from frontend/theme/theme.css; "
        "re-copy the file between the markers"
    )


def test_every_var_reference_resolves(style_block: str) -> None:
    """No component rule reaches for a token nothing defines."""
    defined = {m.group(1) for m in CUSTOM_PROP.finditer(style_block)}
    used = set(re.findall(r"var\(\s*(--[a-zA-Z0-9_-]+)", style_block))
    unresolved = sorted(used - defined)
    assert not unresolved, f"var() references with no definition: {unresolved}"


# ------------------------------------------------------- 2. no raw colour

def test_no_raw_hex_outside_the_token_block(style_block: str) -> None:
    """Every colour below the token block comes from a token.

    A hex literal in a component rule is a colour that will not follow light
    mode, which is exactly the bug the token layer exists to prevent.
    """
    end = style_block.index(END_MARK)
    component_css = style_block[end:]
    offenders = sorted(set(HEX.findall(component_css)))
    assert not offenders, (
        "raw hex colours outside the embedded token block: "
        + ", ".join(offenders)
        + " -- use a semantic token, or add one to theme.css."
    )


def test_light_and_dark_come_from_the_theme(style_block: str) -> None:
    """The wall never redefines a colour for a mode; theme.css owns both."""
    end = style_block.index(END_MARK)
    assert "prefers-color-scheme" in style_block[:end], "theme block lost its light mode"
    component_css = style_block[end:]
    assert "prefers-color-scheme: light" not in component_css
    assert "prefers-color-scheme:light" not in component_css


def test_status_classes_cover_the_closed_set(style_block: str) -> None:
    """One class per status in the closed set, plus the tolerant fallback."""
    for status in CANONICAL_STATUSES:
        assert f".chip--st-{status}" in style_block, f"no chip class for status {status!r}"
    assert ".chip--st-unknown" in style_block, "no neutral fallback chip class"


# ------------------------------------------------------ 3. it still renders

def test_courier_markers_survive(template_text: str) -> None:
    """The renderer substitutes exactly two markers. Losing one is a dead wall."""
    assert "__WALL_DATA__" in template_text
    assert "__REPO_NAME__" in template_text


def test_rendered_sample_has_the_four_tabs(rendered_sample: str) -> None:
    """The tab strip is painted client-side, so what the file has to carry is
    the four labels in the tab table -- in the owner's order."""
    positions = []
    for label in TAB_LABELS:
        needle = f"label:'{label}'"
        assert needle in rendered_sample, f"tab label {label!r} not in the rendered wall"
        positions.append(rendered_sample.index(needle))
    assert positions == sorted(positions), "tabs are not in STORIES / AGENTS / LEDGER / WAITING order"


def test_rendered_sample_defines_the_tab_panels(rendered_sample: str) -> None:
    for panel in ("panel-board", "panel-crew", "panel-ledger", "panel-waiting"):
        assert f'id="{panel}"' in rendered_sample


def test_every_sample_status_has_a_chip(rendered_sample: str, sample_snapshot: dict) -> None:
    """A status the wall was not taught is still shown, spelled as the ledger
    spelled it. The chips carry `data-status` with the literal value, so this
    test can prove no status was silently dropped."""
    statuses = {
        item.get("status")
        for arc in sample_snapshot.get("board", {}).get("arcs", [])
        for item in arc.get("items", [])
    }
    assert statuses, "sample board has no items -- regenerate the sample"
    # The chips are built client-side, so what the rendered file has to carry is
    # the data plus the vocabulary that renders it.
    payload = rendered_sample[rendered_sample.index('id="wall-data"'):]
    for status in sorted(s for s in statuses if s):
        assert f'"status":"{status}"' in payload, f"status {status!r} lost from the snapshot"
    assert "data-status=" in rendered_sample, "status chips carry no literal status"
    assert "canonStatus" in rendered_sample and "STATUS_ALIAS" in rendered_sample


def test_rendered_sample_groups_by_arc(rendered_sample: str, sample_snapshot: dict) -> None:
    """The STORIES tab is arc-first; the arcs have to reach the page."""
    arcs = [a for a in sample_snapshot.get("board", {}).get("arcs", [])
            if a.get("arc_id") and a["arc_id"] != "unassigned"]
    assert arcs, "sample has no real arcs -- regenerate the sample"
    payload = rendered_sample[rendered_sample.index('id="wall-data"'):]
    for arc in arcs:
        assert f'"arc_id":"{arc["arc_id"]}"' in payload
    assert 'id="arcs"' in rendered_sample
    assert "paintStories" in rendered_sample
    assert "nestedRows" in rendered_sample, "arc children do not nest"


def test_malformed_snapshot_shows_a_banner_not_a_blank_page(template_text: str) -> None:
    """Honest degrade: the parse is guarded and the failure is visible."""
    assert 'id="errorBanner"' in template_text
    assert "JSON.parse" in template_text
    assert "catch" in template_text
    assert "function fail(" in template_text
