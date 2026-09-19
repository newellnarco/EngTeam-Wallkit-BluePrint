"""Budget trajectory: balance, %-remaining, measured velocity, projected
exhaustion date, and the pace verdict that steers development speed.

Honesty pins dominate: a meter with no usage source must read `unknown` (not
a fabricated healthy bar), zero burn projects no date, and a strict
(hard-list-price) meter turns an early exhaustion into mandatory pacing.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "tools" / "wall"
sys.path.insert(0, str(HERE))

import courier  # noqa: E402

NOW = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)  # mid-month, fixed


def run_end(ts, model, tin, tout, gh=None, cost=None):
    ev = {"event": "run_end", "ts": ts, "model_used": model,
          "tokens": {"in": tin, "out": tout, "cache_read": 0, "cache_write": 0}}
    if gh is not None:
        ev["gh_minutes"] = gh
    if cost is not None:
        ev["cost_usd"] = cost
    return ev


def budget(meters):
    return {"period": "month to date", "meters": meters}


def test_attribution_by_model_substring_counts_in_plus_out_only():
    evs = [run_end("2026-09-14T10:00:00Z", "claude-opus-5", 1000, 500),
           run_end("2026-09-14T11:00:00Z", "claude-sonnet-5", 9999, 9999)]
    b = courier.enrich_budget(
        budget([{"label": "Opus", "used": 100, "limit": 100000, "match_model": "opus"}]),
        evs, NOW)
    m = b["meters"][0]
    assert m["measured"] == 1500          # cache tokens excluded, sonnet excluded
    assert m["used_total"] == 1600        # config baseline + measured


def test_gh_minutes_meter_counts_every_run():
    evs = [run_end("2026-09-14T10:00:00Z", "claude-opus-5", 1, 1, gh=4),
           run_end("2026-09-14T11:00:00Z", "claude-sonnet-5", 1, 1, gh=6)]
    b = courier.enrich_budget(
        budget([{"label": "GH", "used": 0, "limit": 3000, "counts": "gh_minutes"}]),
        evs, NOW)
    assert b["meters"][0]["measured"] == 10


def test_meter_without_a_source_is_unknown_not_healthy():
    b = courier.enrich_budget(
        budget([{"label": "static", "used": 5, "limit": 100}]), [], NOW)
    m = b["meters"][0]
    assert m["measured"] is None
    assert m["pace"]["verdict"] == "unknown"
    assert m["projected_exhaustion"] is None


def test_zero_burn_projects_no_date():
    b = courier.enrich_budget(
        budget([{"label": "Opus", "used": 10, "limit": 100, "match_model": "opus"}]),
        [], NOW)
    m = b["meters"][0]
    assert m["velocity_per_day"] == 0.0
    assert m["projected_exhaustion"] is None
    assert m["pace"]["verdict"] == "idle"


def test_pct_remaining_and_period_bounds():
    b = courier.enrich_budget(budget([{"label": "x", "used": 25, "limit": 100,
                                       "match_model": "nope"}]), [], NOW)
    assert b["meters"][0]["pct_remaining"] == 75.0
    assert b["period_start"].startswith("2026-09-01")
    assert b["period_end"].startswith("2026-10-01")


def test_hot_burn_projects_exhaustion_before_period_end_and_says_slow():
    # 10k/day against 30k remaining -> ~3 days -> exhausts ~Sep 18, before Oct 1
    evs = [run_end(f"2026-09-{d:02d}T10:00:00Z", "claude-opus-5", 9000, 1000)
           for d in range(9, 16)]
    b = courier.enrich_budget(
        budget([{"label": "Opus", "used": 0, "limit": 100000, "match_model": "opus"}]),
        evs, NOW)
    m = b["meters"][0]
    assert m["velocity_per_day"] and m["velocity_per_day"] >= 9000
    assert m["projected_exhaustion"] is not None
    assert m["projected_exhaustion"] < b["period_end"][:10]
    assert m["pace"]["verdict"] == "slow"
    assert "engineer decides" in m["pace"]["detail"]  # overage budget wording


def test_strict_meter_makes_early_exhaustion_a_hard_cap():
    evs = [run_end(f"2026-09-{d:02d}T10:00:00Z", "claude-opus-5", 9000, 1000)
           for d in range(9, 16)]
    b = courier.enrich_budget(
        budget([{"label": "Opus", "used": 0, "limit": 100000,
                 "match_model": "opus", "strict": True}]), evs, NOW)
    assert "hard list-price cap" in b["meters"][0]["pace"]["detail"]


def test_light_burn_with_big_headroom_says_may_speed():
    # tiny velocity, 99%+ remaining at mid-month -> way ahead of the period
    evs = [run_end("2026-09-14T10:00:00Z", "claude-opus-5", 50, 50)]
    b = courier.enrich_budget(
        budget([{"label": "Opus", "used": 0, "limit": 10_000_000,
                 "match_model": "opus"}]), evs, NOW)
    assert b["meters"][0]["pace"]["verdict"] == "may speed"


def test_exhausted_meter_says_so():
    b = courier.enrich_budget(
        budget([{"label": "GH", "used": 3000, "limit": 3000,
                 "counts": "gh_minutes", "strict": True}]),
        [run_end("2026-09-14T10:00:00Z", "x", 1, 1, gh=1)], NOW)
    m = b["meters"][0]
    assert m["pace"]["verdict"] == "exhausted"
    assert "stop the spend line" in m["pace"]["detail"]


def test_enrich_never_mutates_the_config_object():
    src = budget([{"label": "x", "used": 1, "limit": 10, "match_model": "opus"}])
    courier.enrich_budget(src, [], NOW)
    assert "pace" not in src["meters"][0]
    assert "period_start" not in src


def test_snapshot_carries_the_enriched_budget(tmp_path):
    import json
    day = "2026-09-19"
    sh = tmp_path / ".wall" / "events" / day
    sh.mkdir(parents=True)
    evs = [
        {"event_id": "ev_b1", "seq": 1, "ts": f"{day}T10:00:00Z",
         "session_id": "s_b", "event": "run_start", "run_id": "r1",
         "agent_key": "bld_000001", "actor": "bld_000001"},
        {"event_id": "ev_b2", "seq": 2, "ts": f"{day}T11:00:00Z",
         "session_id": "s_b", "event": "run_end", "run_id": "r1",
         "agent_key": "bld_000001", "actor": "bld_000001", "outcome": "pass",
         "model_used": "claude-opus-5",
         "tokens": {"in": 100, "out": 50, "cache_read": 0, "cache_write": 0}},
    ]
    (sh / "s_b.jsonl").write_text(
        "\n".join(json.dumps(e) for e in evs) + "\n", encoding="utf-8")
    cfg = tmp_path / ".wall" / "config"
    cfg.mkdir()
    (cfg / "wall.json").write_text(json.dumps({
        "budget": {"meters": [{"label": "Opus", "used": 0, "limit": 1000,
                               "match_model": "opus"}]}}), encoding="utf-8")
    snap = courier.run_once(tmp_path, rebuild=True)
    m = snap["budget"]["meters"][0]
    assert m["measured"] == 150
    assert "pace" in m and "pct_remaining" in m


def test_wall_template_renders_the_trajectory_on_both_tabs():
    t = (HERE / "render" / "wall_template.html").read_text(encoding="utf-8")
    assert 'id="gaugesAgents"' in t, "AGENTS tab must carry the budget gauges"
    assert "function gaugeHtml" in t, "one shared builder, not two drifting copies"
    assert "pct_remaining" in t and "projected_exhaustion" in t
    for verdict in ("chip--pace-slow", "chip--pace-on-pace", "chip--pace-may-speed",
                    "chip--pace-exhausted"):
        assert verdict in t, f"pace chip style missing: {verdict}"
