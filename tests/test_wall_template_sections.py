"""The wall template's learning-loop sections, rendered from a snapshot.

The RETRO tab prints `oversight.retro.rebalances`; the WAITING tab prints the
owner-verification queue (`verify_waiting`) with the `wall verified` command,
never `wall answer`; and the integrity panel carries `over_cap`,
`dropped_findings` and `verify_overdue` beside the older flags. An absent
signal reads as absent ("not measured"), never as "clean".

The page's script is executed for real under node against a minimal DOM stub
(every element is a record of what the script wrote into it), so these tests
check what the page paints, not what the source happens to contain. Skipped
where node is not installed.

Stdlib + pytest only.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

KIT = Path(__file__).resolve().parents[1]
TEMPLATE = KIT / "tools" / "wall" / "render" / "wall_template.html"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")

# A DOM just large enough for the page's script: elements remember what was
# written into them, everything else is a no-op. After the synchronous paint
# the harness prints every element's innerHTML / textContent as JSON.
HARNESS = r"""
const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8');
const data = fs.readFileSync(process.argv[3], 'utf8');
const els = {};
function el(id){
  if (!els[id]) els[id] = {
    id: id, innerHTML: '', textContent: '', hidden: false, style: {}, value: '',
    dataset: {}, children: [],
    classList: {add(){}, remove(){}, toggle(){}, contains(){ return false; }},
    addEventListener(){}, removeEventListener(){}, setAttribute(){}, getAttribute(){ return null; },
    removeAttribute(){}, contains(){ return false; }, focus(){}, blur(){}, click(){},
    querySelector(){ return el('__q'); }, querySelectorAll(){ return []; },
    appendChild(){}, closest(){ return null; },
  };
  return els[id];
}
el('wall-data').textContent = data;
global.document = {
  getElementById: el, querySelector(){ return el('__q'); }, querySelectorAll(){ return []; },
  addEventListener(){}, body: el('__body'), hidden: false, activeElement: null,
  createElement(){ return el('__new'); }, title: '',
};
global.window = global;
global.location = {protocol: 'file:', hash: '', search: '', href: 'file:///wall.html', reload(){}};
global.sessionStorage = {getItem(){ return null; }, setItem(){}};
global.localStorage = global.sessionStorage;
global.setInterval = function(){ return 0; };
global.setTimeout = function(){ return 0; };
global.fetch = function(){ return Promise.reject(new Error('offline')); };
global.history = {replaceState(){}, pushState(){}};
const m = src.match(/<script>([\s\S]*?)<\/script>/);
eval(m[1]);
const out = {};
for (const k of Object.keys(els)) out[k] = {html: els[k].innerHTML, text: els[k].textContent,
                                            hidden: els[k].hidden};
process.stdout.write(JSON.stringify(out));
"""


def paint(snapshot: dict, tmp_path: Path) -> dict:
    harness = tmp_path / "harness.js"
    harness.write_text(HARNESS, encoding="utf-8")
    data = tmp_path / "wall.json"
    data.write_text(json.dumps(snapshot), encoding="utf-8")
    proc = subprocess.run([NODE, str(harness), str(TEMPLATE), str(data)],
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    banner = out.get("errorBanner", {})
    assert not banner.get("html"), f"the page failed to render: {banner.get('html')}"
    return out


def text_of(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).replace("&gt;", ">") \
        .replace("&lt;", "<").replace("&amp;", "&").strip()


def base(**extra) -> dict:
    snap = {"schema_version": 1, "generated_at": "2026-09-24T10:00:00.000Z",
            "repo": {"name": "demo", "branch": "main"},
            "courier": {"events": 3, "shards": 1, "last_run_ms": 5},
            "sessions": [], "crew": [], "board": {"arcs": []},
            "waiting_on_you": [], "questions": [], "integrity": {},
            "oversight": {}}
    snap.update(extra)
    return snap


FULL_INTEGRITY = {
    "seq_gaps": [], "orphan_runs": [], "state_drift": 0, "duplicates": [],
    "stale_claims": [], "merged_but_open": [],
    "over_cap": [{"role": "builder", "limit": 2, "open": 3,
                  "run_ids": ["r0", "r1", "r2"], "reasons": ["prod hotfix"],
                  "detail": "3 open builder runs against a cap of 2"}],
    "dropped_findings": [{"finding_ref": "ev_f1", "signature": "boom <n>",
                          "snapshot_ref": "s1", "age_min": 90.0, "sla_min": 60,
                          "detail": "routed story_filed; no story_filed names it"}],
    "verify_overdue": [{"request_ref": "ev_v1", "item_id": "ST-9",
                        "what_changed": "login", "verify_steps": ["open /login"],
                        "since": "2026-09-01T00:00:00.000Z", "age_days": 23.0,
                        "overdue": True}],
}

VERIFY_ROWS = [
    {"request_ref": "ev_v1", "item_id": "ST-9", "what_changed": "the login form",
     "verify_steps": ["open /login", "sign in twice"],
     "since": "2026-09-01T00:00:00.000Z", "age_days": 23.0, "overdue": True},
    {"request_ref": "ev_v2", "item_id": "ST-10", "what_changed": "export button",
     "verify_steps": ["click export"],
     "since": "2026-09-24T09:00:00.000Z", "age_days": 0.0, "overdue": False},
]

REBALANCE = {"knob": "role_limits.builder", "from": 2, "to": 3,
             "signals": [{"name": "queue_wait_min", "value": 42}],
             "expected_effect": "queue wait under 15 min", "horizon": "next wave",
             "reason": None, "by": "maestro", "ts": "2026-09-23T08:00:00.000Z"}


# ------------------------------------------------------------- integrity

def flag_rows(out: dict) -> dict:
    html = out["integrity"]["html"]
    rows = re.findall(r'data-flag="([^"]+)"><span class="k([^"]*)">[^<]*</span>'
                      r'<span class="v">([^<]*)</span>', html)
    return {k: (cls.strip(), text_of(v)) for k, cls, v in rows}


def test_new_integrity_flags_render_with_their_details(tmp_path):
    rows = flag_rows(paint(base(integrity=FULL_INTEGRITY), tmp_path))
    for key in ("over_cap", "dropped_findings", "verify_overdue"):
        assert key in rows, key
        assert rows[key][0] == "", f"{key} is raised, so not marked ok"
    assert "builder 3/2" in rows["over_cap"][1]
    assert "prod hotfix" in rows["over_cap"][1]
    assert "1 finding routed story_filed" in rows["dropped_findings"][1]
    assert "ST-9" in rows["verify_overdue"][1]
    assert rows["seq_gaps"] == ("ok", "clean")


def test_empty_flags_read_clean_absent_flags_read_not_measured(tmp_path):
    present = dict(FULL_INTEGRITY, over_cap=[], dropped_findings=[])
    present.pop("verify_overdue")
    rows = flag_rows(paint(base(integrity=present), tmp_path))
    assert rows["over_cap"] == ("ok", "clean")
    assert rows["dropped_findings"] == ("ok", "clean")
    assert rows["verify_overdue"][0] == "absent"
    assert "not measured" in rows["verify_overdue"][1]
    assert "clean" not in rows["verify_overdue"][1]


def test_main_counts_the_new_flags(tmp_path):
    out = paint(base(integrity=FULL_INTEGRITY), tmp_path)
    assert "Integrity flags 3" in text_of(out["mainStats"]["html"])


# --------------------------------------------------------------- waiting

def test_verify_queue_renders_with_the_verified_command(tmp_path):
    out = paint(base(verify_waiting=VERIFY_ROWS), tmp_path)
    html = out["verifyWaiting"]["html"]
    text = text_of(html)
    for row in VERIFY_ROWS:
        assert (f"wall verified --item {row['item_id']} --verdict "
                "confirmed|confirmed_with_findings") in text
        assert row["what_changed"] in text
    assert "sign in twice" in text
    assert "wall answer" not in html
    # Overdue is distinct: only the overdue row carries the mark.
    blocks = re.findall(r'<div class="ask([^"]*)" data-verify="([^"]+)"', html)
    assert dict((iid, cls) for cls, iid in blocks) == {"ST-9": " overdue", "ST-10": ""}
    assert html.count("OVERDUE") == 1
    # With no questions open, the asks panel must not claim nothing needs you.
    assert "Nothing needs you" not in out["asks"]["html"]
    assert "2 verification requests" in text_of(out["asks"]["html"])


def test_verify_queue_empty_and_absent_are_different(tmp_path):
    empty = paint(base(verify_waiting=[]), tmp_path)["verifyWaiting"]["html"]
    assert "No verification requests open" in empty
    absent = paint(base(), tmp_path)["verifyWaiting"]["html"]
    assert "Not measured" in absent and "No verification requests" not in absent


# ----------------------------------------------------------------- retro

def test_rebalances_render_every_field(tmp_path):
    retro = {"held": 1, "latest": {"wave": "w3", "diffs": [], "remeasured": []},
             "trends": [], "pending_inputs": [],
             "rebalances": [REBALANCE, dict(REBALANCE, knob="stale_after_min",
                                            **{"from": 30, "to": 45},
                                            expected_effect=None, horizon=None,
                                            signals=[], ts=None)]}
    html = paint(base(oversight={"retro": retro}), tmp_path)["retroBody"]["html"]
    text = text_of(html)
    assert "Rebalances applied" in text
    assert "role_limits.builder 2 → 3" in text
    assert "queue_wait_min=42" in text
    assert "expected effect: queue wait under 15 min" in text
    assert "re-measure: next wave" in text
    assert "written 2026-09-23T08:00:00.000Z" in text
    # Newest first; the one missing fields says so rather than going blank.
    assert text.index("stale_after_min") < text.index("role_limits.builder")
    second = text[text.index("stale_after_min"):text.index("role_limits.builder")]
    assert "signals: none recorded" in second
    assert "expected effect: none recorded" in second
    assert "re-measure: none recorded" in second
    assert "at an unrecorded time" in second


def test_rebalances_show_before_any_retro_and_absent_reads_absent(tmp_path):
    retro = {"held": 0, "latest": None, "trends": [], "pending_inputs": [],
             "rebalances": [REBALANCE]}
    html = paint(base(oversight={"retro": retro}), tmp_path)["retroBody"]["html"]
    assert "role_limits.builder" in html and "No retrospective recorded yet" in html
    retro_empty = dict(retro, rebalances=[])
    html = paint(base(oversight={"retro": retro_empty}), tmp_path)["retroBody"]["html"]
    assert "No rebalance applied yet" in html
    old = dict(retro)
    old.pop("rebalances")
    html = paint(base(oversight={"retro": old}), tmp_path)["retroBody"]["html"]
    assert "Not measured" in html and "No rebalance applied yet" not in html


def test_a_real_courier_snapshot_paints_the_new_sections(repo, write_shard, tmp_path):
    """End to end: events -> courier.build -> template, no hand-built snapshot."""
    import courier
    write_shard("s1", [
        {"event": "rebalance_applied", "knob": "role_limits.builder", "from": 2,
         "to": 3, "signals": [{"name": "queue_wait_min", "value": 42}],
         "expected_effect": "shorter queue", "horizon": "next wave", "by": "maestro",
         "ts": "2026-09-23T08:00:00.000Z"},
        {"event": "verify_requested", "item_id": "ST-7", "what_changed": "search",
         "verify_steps": ["type a query"], "ts": "2026-09-01T00:00:00.000Z"},
    ])
    snap = courier.run_once(repo)
    out = paint(snap, tmp_path)
    assert "shorter queue" in out["retroBody"]["html"]
    assert "wall verified --item ST-7" in out["verifyWaiting"]["html"]
    assert "OVERDUE" in out["verifyWaiting"]["html"]
    rows = flag_rows(out)
    assert rows["verify_overdue"][0] == "" and "ST-7" in rows["verify_overdue"][1]
    assert rows["over_cap"] == ("ok", "clean")
