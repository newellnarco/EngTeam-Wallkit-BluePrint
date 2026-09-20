"""EXECUTE + AGENTS port (host integration seams), pinned.

The host (MAX3, 2026-09-20) directed porting its legacy wall's EXECUTE
enqueue actions and AGENTS live-wave stream onto the kit wall. Both are
config-driven seams: with neither key configured the page renders exactly
as before -- a read-only static wall. Pinned here, each with the mutation
that kills it:

* courier passes `queue_api` / `agents_feed` from config into the snapshot
  verbatim, and None when unset (drop the passthrough -> the config tests
  fail on a missing key);
* the template emits EXECUTE markup only inside `D.queue_api` branches,
  and the buttons are CSS-hidden until the health probe adds
  `body.queue-ok` -- a wall served without its backend stays read-only,
  honestly (make the markup unconditional or drop the probe gate -> the
  source pins fail);
* one click, one directive: a synchronous busy flag plus
  disabled-until-settle plus cooldown (drop the guard -> the re-entrancy
  pin fails);
* the wave painter is gated on `D.agents_feed` AND the crew tab being
  active, so a wall without a feed never fetches;
* every interpolated field (item_id, arc_id, the feed path, agent / unit /
  stage) goes through esc() -- the page inlines its whole dataset and must
  not be an XSS sink.
"""

from __future__ import annotations

import json
from pathlib import Path

import courier


def _template_text() -> str:
    return (Path(courier.__file__).parent / "render" /
            "wall_template.html").read_text(encoding="utf-8")


def _render(snapshot):
    template = Path(courier.__file__).parent / "render" / "wall_template.html"
    return courier.render(snapshot, template)


QUEUE_API = {"health": "/api/queue/health", "queue": "/api/queue",
             "add": "/api/queue/add"}


def _repo(tmp_path: Path, config: dict | None) -> Path:
    day = "2026-09-19"
    sh = tmp_path / ".wall" / "events" / day
    sh.mkdir(parents=True)
    ev = {"event_id": "ev_execport1", "seq": 1, "ts": f"{day}T10:00:00Z",
          "session_id": "s_exec", "event": "item_created", "item_id": "ST-1",
          "title": "probe", "kind": "story", "actor": "tst_000000"}
    (sh / "s_exec.jsonl").write_text(json.dumps(ev) + "\n", encoding="utf-8")
    cfg_dir = tmp_path / ".wall" / "config"
    cfg_dir.mkdir()
    if config is not None:
        (cfg_dir / "wall.json").write_text(json.dumps(config), encoding="utf-8")
    return tmp_path


# ---- courier passthrough ---------------------------------------------------

def test_courier_passes_both_seams_from_config(tmp_path):
    repo = _repo(tmp_path, {"queue_api": QUEUE_API,
                            "agents_feed": "./agent_wave_status.json"})
    snap = courier.run_once(repo, rebuild=True)
    assert snap["queue_api"] == QUEUE_API
    assert snap["agents_feed"] == "./agent_wave_status.json"
    # and they survive into the derived snapshot on disk, which is what the
    # served page polls
    on_disk = json.loads((repo / ".wall" / "derived" / "wall.json")
                         .read_text(encoding="utf-8"))
    assert on_disk["queue_api"] == QUEUE_API
    assert on_disk["agents_feed"] == "./agent_wave_status.json"


def test_courier_defaults_both_seams_to_none_when_unset(tmp_path):
    snap = courier.run_once(_repo(tmp_path, None), rebuild=True)
    assert snap["queue_api"] is None
    assert snap["agents_feed"] is None


# ---- template: EXECUTE is conditional and probe-gated ----------------------

def test_exec_markup_only_inside_queue_api_branches():
    """Rows are built client-side, so pin the CONDITION in the source: the
    detail row's exec bar and the arc header's EXECUTE ARC exist only under
    D.queue_api, with the interpolated ids escaped."""
    t = _template_text()
    detail = t.split("function detailRow")[1].split("function itemRow")[0]
    assert "var exec = D.queue_api" in detail
    assert "esc(it.item_id)" in detail
    assert 'data-exec="item"' in detail

    arcs = t.split("function paintArcs")[1].split("function paintCrew")[0] \
        if "function paintArcs" in t else t
    assert "var execArc = D.queue_api" in arcs
    assert "esc(arc.arc_id)" in arcs
    assert 'data-exec="arc"' in arcs


def test_probe_gate_and_css_reveal():
    """Buttons render display:none and only body.queue-ok reveals them; the
    probe adds that class only after the health endpoint answered ok, and
    removes it on any failure."""
    t = _template_text()
    assert "if (!D.queue_api || !D.queue_api.health) return;" in t
    assert "document.body.classList.add('queue-ok')" in t
    assert "document.body.classList.remove('queue-ok')" in t
    # CSS: hidden by default, revealed only by the probe's class
    assert "display: none" in t.split(".exec-btn {")[1].split("}")[0]
    assert "body.queue-ok .exec-btn { display: inline-block; }" in t


def test_enqueue_reentrancy_guard():
    t = _template_text()
    assert "b.dataset.busy === '1'" in t
    assert "b.disabled = true;" in t
    assert "}, 1500);" in t  # cooldown before the button re-arms
    # the payload contract the host queue expects
    assert "directive: 'execute_item', target_key: key" in t
    assert "directive: 'execute_arc', target_arch: arcId" in t
    assert "{ source: 'wall_click', priority: 'P2' }" in t


# ---- template: AGENTS wave is conditional, gated, escaped ------------------

def test_wave_painter_gated_on_feed_and_crew_tab():
    t = _template_text()
    assert "if (!D.agents_feed || active !== 'crew') return;" in t
    assert "setInterval(paintWave, 5000);" in t
    # cache-busted, never cached
    assert "Date.now()" in t.split("function paintWave")[1].split("$('tabs')")[0]


def test_wave_fields_are_escaped_and_absence_is_honest():
    t = _template_text()
    wave = t.split("function waveList")[1].split("function paintWave")[0]
    assert "esc(x.agent" in wave
    assert "esc(x.unit" in wave
    assert "esc(x.stage)" in wave
    assert "esc(String(x))" in wave
    painter = t.split("function paintWave")[1].split("$('tabs')")[0]
    assert "esc(D.agents_feed)" in painter          # the failure note's path
    assert "nothing streaming" in painter           # honest degrade, not blank


# ---- rendered page ---------------------------------------------------------

def _snapshot(extra: dict) -> dict:
    base = {
        "schema_version": 1, "generated_at": "2026-09-20T00:00:00.000Z",
        "generated_epoch": 0, "stale_after_s": 300,
        "repo": {"name": "ProbeRepo", "branch": "main"},
        "integrity": {"flags": []}, "role_limits": {},
        "crew": [], "board": {"arcs": []},
        "waiting_on_you": [], "questions": [],
        "budget": {"meters": []}, "rollup_by_role": [], "sessions": [],
    }
    base.update(extra)
    return base


def test_rendered_page_carries_seams_only_when_configured():
    with_seams = _render(_snapshot({"queue_api": QUEUE_API,
                                    "agents_feed": "./agent_wave_status.json"}))
    assert "/api/queue/health" in with_seams
    assert "./agent_wave_status.json" in with_seams

    without = _render(_snapshot({"queue_api": None, "agents_feed": None}))
    assert "/api/queue/health" not in without
    assert "agent_wave_status.json" not in without


def test_strip_and_wave_panel_ship_hidden():
    """The static markup always carries both containers, hidden -- only the
    probe / painter reveal them. A page whose backend never answers shows
    neither."""
    html = _render(_snapshot({}))
    assert 'id="queueStrip" hidden' in html
    assert 'id="wavePanel" hidden' in html
