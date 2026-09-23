#!/usr/bin/env python3
"""wall — the command surface for the agent workforce.

Local-only: no network calls anywhere in this file.

Ledger and workflow, owned here: run-once, doctor, classify, agents, rebuild,
diff-state, trace, why, answer, fast-track. `context` dispatches to
`context_sync.py` (AGENTS.md masters and their generated tool copies).

Plumbing, dispatched: install / register / unregister / verify / uninstall /
serve go to `service.py`; ship / fetch-events go to `shipper.py`. Both imports
are lazy and inside the command, so the CLI keeps working on a machine where
those modules were never installed -- the command prints what it needs instead
of the whole file failing to import.

Exit codes: 0 clean, 1 a real finding (drift, gate failure, refused route),
2 a usage error or a command whose module is not installed on this machine.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

import courier                      # noqa: E402
import decisions as decisions_mod   # noqa: E402
import items as items_mod           # noqa: E402
import questions as questions_mod   # noqa: E402
from agents import AgentRegistry    # noqa: E402


def load_config(repo: Path) -> dict:
    p = repo / ".wall" / "config" / "wall.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    example = HERE / "config" / "wall.example.json"
    print(f"no config at {p}\n  copy the example: {example}", file=sys.stderr)
    return {}


def stub(name: str, needs: str):
    """The honest fallback when a dispatched command's module is absent.

    Not a status label -- `install`, `serve`, `ship` and the rest are live.
    This fires only when the module that implements one is missing from this
    checkout, and says which one and what it does, rather than letting an
    ImportError surface as a traceback.
    """
    raise NotImplementedError(
        f"`wall {name}` cannot run here: its module is not installed.\n"
        f"  Needs: {needs}")


def via_service(name: str, a, needs: str):
    """The seam for the plumbing commands, dispatched to `service.py`.

    `service.py` owns the machine registry, the timer adapters and the local
    server; it exposes `cmd_install` / `cmd_register` / `cmd_unregister` /
    `cmd_verify` / `cmd_uninstall` / `cmd_serve`, each taking the argparse
    namespace and returning an exit code.

    The import is lazy and inside the command, so the whole CLI stays usable
    on a machine where that module was never installed -- the command then
    prints what it needs instead of the file failing to import.
    """
    try:
        import service  # noqa: PLC0415  (deliberately lazy; see docstring)
    except ImportError:
        stub(name, needs)
        return 2
    fn = getattr(service, "cmd_" + name.replace("-", "_"), None)
    if fn is None:
        stub(name, needs + f"\n  (service.py is present but has no cmd_{name})")
        return 2
    return fn(a) or 0


def via_shipper(fn_name: str, a, needs: str):
    """The seam for the isolated-branch shipping commands (`shipper.py`).

    Shards are never committed on the development branch: they ship to a
    dedicated `wall-events` branch through an isolated index, leaving the
    working tree and the current branch untouched (RECONCILIATION Q7).
    """
    try:
        import shipper  # noqa: PLC0415  (deliberately lazy)
    except ImportError:
        stub(fn_name, needs)
        return 2
    fn = getattr(shipper, fn_name, None)
    if fn is None:
        stub(fn_name, needs + f"\n  (shipper.py is present but has no {fn_name})")
        return 2
    branch = getattr(a, "branch", None) or getattr(shipper, "DEFAULT_BRANCH", "wall-events")
    repo = Path(a.repo).resolve()
    if fn_name == "ship":
        return fn(repo, branch)
    outcome = fn(repo, branch)
    print(f"[wall-events] fetch: {'updated' if outcome.get('updated') else 'no-op'}"
          f" -- {outcome.get('reason') or 'nothing to do'}")
    if outcome.get("updated"):
        print(f"  {outcome.get('shards', 0)} shard(s)"
              f"{', snapshot' if outcome.get('snapshot') else ''} materialised — "
              f"run `wall run-once` to fold them in")
    return 0


def _short(value, width: int = 48) -> str:
    text = " ".join(str(value).split())
    return text if len(text) <= width else text[: width - 3] + "..."


def _fmt_secs(seconds: float) -> str:
    seconds = int(max(0, seconds))
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m{seconds % 60:02d}s"
    return f"{seconds // 3600}h{(seconds % 3600) // 60:02d}m"


# ---------------------------------------------------------------- sweep

# The integrity keys that carry findings. `state_drift` is the *count* of
# `state_drift_detail` (the wall template renders it as a number), so counting
# both would report every drift twice.
FLAG_KEYS = ("seq_gaps", "seq_duplicates", "orphan_runs", "duplicates",
             "state_drift_detail", "merged_but_open", "escalations",
             "stale_claims", "fold_problems")


def count_flags(integrity: dict) -> int:
    return sum(len(integrity.get(k) or []) for k in FLAG_KEYS)


def build_doctor_payload(repo: Path) -> dict:
    """Machine-readable doctor state: what wall.json does NOT already carry.

    wall.json holds the board and the integrity detail, and it ships. This
    payload adds the plumbing checks, the roster audit and a per-flag summary,
    so an off-box reader gets the whole health picture from the telemetry
    branch without an interactive session on the machine. Honest absence
    throughout: a section that could not be checked says so instead of
    reading clean.
    """
    repo = Path(repo)
    payload: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "heartbeat": None,
        "integrity_summary": {"checked": False},
        "plumbing": {"checked": False, "reason": "service.py is not installed"},
        "roster": {"checked": False},
    }
    hb = repo / ".wall" / "derived" / "heartbeat.json"
    if hb.exists():
        try:
            payload["heartbeat"] = json.loads(hb.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            payload["heartbeat"] = {"unreadable": True}
    snap_path = repo / ".wall" / "derived" / "wall.json"
    if snap_path.exists():
        try:
            i = json.loads(snap_path.read_text(encoding="utf-8"))["integrity"]
        except (OSError, ValueError, KeyError):
            payload["integrity_summary"] = {"checked": False, "unreadable": True}
        else:
            counts = {}
            for k in FLAG_KEYS:
                v = i.get(k)
                counts["state_drift" if k == "state_drift_detail" else k] = (
                    len(v) if isinstance(v, list) else (v or 0))
            if i.get("state_drift_checked") is False:
                counts["state_drift"] = None  # not checked is not zero
            payload["integrity_summary"] = {"checked": True, "flags": counts}
    try:
        import service  # noqa: PLC0415
    except ImportError:
        pass
    else:
        try:
            payload["plumbing"] = {"checked": True,
                                   "checks": service.doctor_checks(repo)}
        except Exception as exc:  # a doctor that crashes must still report
            payload["plumbing"] = {"checked": False, "reason": repr(exc)}
    try:
        problems = AgentRegistry(repo).audit()
        payload["roster"] = {"checked": True, "problems": problems}
    except Exception as exc:
        payload["roster"] = {"checked": False, "reason": repr(exc)}
    return payload


def write_doctor_json(repo: Path) -> Path | None:
    """Write ``.wall/derived/doctor.json``; None (never an exception) on failure."""
    repo = Path(repo)
    out = repo / ".wall" / "derived" / "doctor.json"
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(build_doctor_payload(repo), indent=1,
                                  sort_keys=True) + "\n", encoding="utf-8")
        return out
    except OSError as exc:
        print(f"doctor.json not written: {exc}", file=sys.stderr)
        return None


def cmd_run_once(a):
    """Merge shards, build the snapshot, render the wall. Fully working."""
    repo = Path(a.repo).resolve()
    snap = courier.run_once(repo, rebuild=a.rebuild)
    n = count_flags(snap["integrity"])
    print(f"swept {snap['courier']['events']} events from "
          f"{snap['courier']['shards']} shards"
          f"{f' — {n} integrity flags' if n else ' — clean'}")
    # Refresh the machine-readable diagnostics on every sweep, so what the
    # shipper carries off-box is never staler than the wall it rides with.
    write_doctor_json(repo)
    return 0


def cmd_summary(a):
    """One-screen human digest of the derived snapshot. The MCP adapter
    serves the same build_summary to agents — one implementation, two
    presentations (DEC-0018). Honest degrade: no snapshot yet is a named
    instruction, never a traceback."""
    import summary as summary_mod
    repo = Path(a.repo).resolve()
    snap_path = repo / ".wall" / "derived" / "wall.json"
    if not snap_path.exists():
        print("no snapshot at .wall/derived/wall.json — run `wall run-once` first")
        return 1
    # A damaged derived file is a NAMED condition with its recovery
    # command, never a traceback — the courier's atomic writes make this
    # rare, but rare is not never. (CodeRabbit finding, accepted.)
    try:
        snap = json.loads(snap_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"wall.json unreadable ({exc}) — run `wall run-once` to "
              f"regenerate it")
        return 1
    hb_path = repo / ".wall" / "derived" / "heartbeat.json"
    try:
        hb = (json.loads(hb_path.read_text(encoding="utf-8"))
              if hb_path.exists() else None)
    except (OSError, json.JSONDecodeError):
        hb = None  # summary says: heartbeat MISSING — run `wall run-once`
    s = summary_mod.build_summary(snap, hb)
    if getattr(a, "as_json", False):
        from dataclasses import asdict
        print(json.dumps(asdict(s), indent=1, sort_keys=True))
    else:
        print(summary_mod.format_summary(s))
    return 0


def cmd_doctor(a):
    """Heartbeat, sequence gaps, orphan runs, roster health. Working."""
    repo = Path(a.repo).resolve()
    if getattr(a, "as_json", False):
        out = write_doctor_json(repo)
        print(json.dumps(build_doctor_payload(repo), indent=1, sort_keys=True))
        return 0 if out else 1
    hb = repo / ".wall" / "derived" / "heartbeat.json"
    print("heartbeat:", json.loads(hb.read_text()) if hb.exists() else "MISSING — courier has never run")

    snap_path = repo / ".wall" / "derived" / "wall.json"
    if snap_path.exists():
        i = json.loads(snap_path.read_text())["integrity"]
        if i.get("state_drift_checked") is False:
            print("  state_drift      not checked — no .wall/items/ yet "
                  "(run `wall rebuild`)")
        for k in FLAG_KEYS:
            if k == "state_drift_detail" and i.get("state_drift_checked") is False:
                continue
            n = len(i.get(k) or [])
            label = "state_drift" if k == "state_drift_detail" else k
            print(f"  {label:<16} {'clean' if not n else str(n) + ' flagged'}")
        for flag in (i.get("escalations") or []):
            print(f"    escalation  {flag['kind']:<26} "
                  f"{flag.get('question_id') or flag.get('item_id')}  "
                  f"{flag.get('detail', '')}")
        for flag in (i.get("merged_but_open") or []):
            print(f"    reconcile   {flag['kind']:<26} {flag['item_id']}  "
                  f"{flag.get('detail', '')}")

    # The plumbing half: timer alive, heartbeat fresh, registry sane, app in
    # sync. `wall verify` calls the same function, so the two agree by
    # construction rather than by two people maintaining one list twice.
    try:
        import service  # noqa: PLC0415  (lazy: the CLI works without it)
    except ImportError:
        print("  plumbing         not checked — service.py is not installed")
    else:
        for check in service.doctor_checks(repo):
            print(f"  {check['name']:<16} {check['status']:<8} {check.get('detail', '')}")

    problems = AgentRegistry(repo).audit()
    print("  roster          ", "clean" if not problems else "; ".join(problems))
    return 0


# ---------------------------------------------------------------- routing

def glob_match(path: str, pattern: str) -> bool:
    """`fnmatch` with `**/` meaning "zero or more directories".

    Plain `fnmatch` reads `**/*.md` as "at least one directory, then
    anything.md", because its `*` already crosses `/`. So a root-level
    `CLAUDE.md` did not match the `**/CLAUDE.md` deny rule that FAST_TRACK.md
    specifically defends, and a root `README.md` did not match the allow list
    either. The first is the dangerous half: a rule everybody believes is
    armed, silently never firing.
    """
    if fnmatch.fnmatch(path, pattern):
        return True
    while "**/" in pattern:
        pattern = pattern.replace("**/", "", 1)
        if fnmatch.fnmatch(path, pattern):
            return True
    return False


def _match(path: str, globs) -> str | None:
    return next((g for g in (globs or []) if glob_match(path, g)), None)


def classify_files(files: list[str], cfg: dict) -> dict:
    """Route a changeset by path alone. Pure, so it is testable without git.

    Deny beats allow, always. Every path outside the allow list is full track;
    there is no mixed mode and no partial credit (FAST_TRACK.md).
    """
    allow, deny = cfg.get("allow", []), cfg.get("deny", [])
    significant = cfg.get("significant", [])
    rows, fast, full, sig = [], [], [], []
    for f in files:
        rule = _match(f, deny)
        if rule:
            full.append(f)
            rows.append({"path": f, "verdict": "deny", "rule": rule})
            continue
        rule = _match(f, allow)
        if rule:
            fast.append(f)
            rows.append({"path": f, "verdict": "allow", "rule": rule})
            if _match(f, significant):
                sig.append(f)
        else:
            full.append(f)
            rows.append({"path": f, "verdict": "deny", "rule": None})
    return {
        "route": "fast_track" if (files and not full) else "full_track",
        "rows": rows, "fast": fast, "full": full,
        "significant": sig, "mixed": bool(fast and full),
    }


#: Ceiling on every local git call this CLI makes. Local plumbing that
#: takes longer than this is stuck, not slow.
GIT_TIMEOUT_S = 30


def changed_files(repo: Path, staged: bool = False) -> list[str]:
    args = ["git", "-C", str(repo), "diff", "--name-only"]
    if staged:
        args.append("--cached")
    # Bounded: a hung git (stale lock, fsmonitor) must fail loudly here --
    # an empty list would silently classify the change set as "nothing
    # changed", which is the dangerous direction for a routing gate.
    try:
        out = subprocess.run(args, capture_output=True, text=True, check=False,
                             timeout=GIT_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        raise SystemExit("git diff timed out after %ss -- cannot classify the "
                         "change set; check for a stuck git process or stale "
                         ".git/index.lock" % GIT_TIMEOUT_S)
    return [f for f in out.stdout.split("\n") if f.strip()]


def print_classification(result: dict) -> None:
    print(f"route: {result['route']}")
    for row in result["rows"]:
        if row["verdict"] == "allow":
            print(f"  {row['path']}\n      allow  matched {row['rule']}")
        elif row["rule"]:
            print(f"  {row['path']}\n      DENY   matched {row['rule']}")
        else:
            print(f"  {row['path']}\n      DENY   matched no allow rule")
    for path in result["significant"]:
        print(f"  {path}\n      NOTE   architecture/decision doc -- "
              f"emits doc_impact for the affected arcs")
    if result["mixed"]:
        print("\nmixed changeset — split it rather than taking an exception.")


def cmd_classify(a):
    """Route a changeset by path. Mechanical — never asserted by an agent."""
    repo = Path(a.repo).resolve()
    cfg = load_config(repo).get("fast_track", {})
    files = changed_files(repo, a.staged)
    if not files:
        print("no changes")
        return 0
    print_classification(classify_files(files, cfg))
    return 0


# ---------------------------------------------------------------- roster

def cmd_agents(a):
    reg = AgentRegistry(Path(a.repo).resolve())
    if a.agents_action == "claim":
        row = reg.claim(a.role, a.session, a.key, a.name)
        print(f"{row['name']}  ({row['key']})")
    elif a.agents_action == "release":
        row = reg.release(a.key)
        print(f"released {row['name']} ({a.key})" if row else f"no live agent {a.key}")
    elif a.agents_action == "whois":
        if not a.name:
            print("whois needs --name")
            return 1
        if a.at:
            try:
                row = reg.holder_at(a.name, a.at)
            except ValueError as e:
                print(str(e))
                return 2
            if not row:
                print(f"no agent held '{a.name}' at {a.at}")
                return 1
            print(f"{row['name']} at {a.at} was {row['key']} ({row['role']}, "
                  f"claimed {row['claimed']}, released {row.get('released') or '—'})")
        else:
            tenures = reg.history(a.name)
            if not tenures:
                print(f"no agent has ever held '{a.name}'")
                return 1
            for r in tenures:
                print(f" {r['key']:<12} {r['role']:<12} "
                      f"claimed {r['claimed']}  released {r.get('released') or '—'}"
                      f"{'  (live)' if r['status'] == 'live' else ''}")
    elif a.agents_action == "audit":
        p = reg.audit()
        print("\n".join(p) if p else "roster clean")
        return 1 if p else 0
    else:
        for r in reg.read():
            print(f" {'●' if r['status'] == 'live' else '○'} "
                  f"{r['name']:<12} {r['key']:<12} {r['role']:<12} {r['status']}")
    return 0


# ------------------------------------------------- materialized item state

def cmd_rebuild(a):
    """Regenerate `.wall/items/` from events alone. Idempotent."""
    repo = Path(a.repo).resolve()
    result = items_mod.rebuild(repo, prune=bool(getattr(a, "prune", False)))
    print(f"rebuilt {result['items']} items: {len(result['written'])} written, "
          f"{len(result['unchanged'])} unchanged"
          + (f", {len(result['removed'])} pruned" if result["removed"] else ""))
    for iid in result["orphans"]:
        print(f"  orphan   {iid}  item file with no event behind it "
              f"(remove with --prune)")
    for p in result["problems"]:
        print(f"  problem  {p.get('kind')}  {p.get('detail', '')}")
    return 1 if (result["problems"] or result["orphans"]) else 0


def cmd_diff_state(a):
    """Ledger-derived item state vs what is on disk."""
    repo = Path(a.repo).resolve()
    result = items_mod.diff_state(repo)
    if not result["checked"]:
        print(f"state drift: not checked — {result['note']}")
        for p in result["problems"]:
            print(f"  problem  {p.get('kind')}  {p.get('detail', '')}")
        return 0
    if not result["drift"] and not result["problems"]:
        print("state drift: none — every item file matches the ledger")
        return 0
    print(f"state drift: {result['count']} difference(s)")
    for d in result["drift"]:
        if d["kind"] == "field_mismatch":
            print(f"  {d['item_id']:<10} {d['field']:<14} "
                  f"ledger={_short(d['expected'], 28)!r:<32} disk={_short(d['found'], 28)!r}")
        else:
            print(f"  {d['item_id']:<10} {d['kind']:<14} {d.get('detail', '')}")
    for p in result["problems"]:
        print(f"  problem  {p.get('kind')}  {p.get('detail', '')}")
    print("\nsomething wrote out of band: an agent bypassing the protocol, or a "
          "bug in a writer.\nreconcile with `wall rebuild`.")
    return 1


# ------------------------------------------------------------------- trace

_TRACE_DETAIL_SKIP = frozenset(items_mod.ENVELOPE_KEYS) | {"trace_id"}


def _trace_detail(e: dict) -> str:
    ev = e.get("event")
    if ev == "run_start":
        bits = [str(e.get("run_id") or "?")]
        if e.get("item_id"):
            bits.append(f"item {e['item_id']}")
        if e.get("model_requested"):
            model = e.get("model_used") or e["model_requested"]
            if e.get("model_used") and e["model_used"] != e["model_requested"]:
                model = f"{e['model_requested']} -> {e['model_used']} (routed)"
            bits.append(model)
        return "  ".join(bits)
    if ev in ("run_end", "run_error"):
        bits = [str(e.get("run_id") or "?"), f"outcome={e.get('outcome')}"]
        hook = e.get("hook")
        if isinstance(hook, dict) and hook.get("resolution") not in (None, "resolved"):
            bits.append(f"hook={hook.get('resolution')}")
        if e.get("error_class"):
            bits.append(f"error={e['error_class']}")
        if e.get("duration_s") is not None:
            bits.append(f"{e['duration_s']}s")
        if e.get("cost_usd"):
            bits.append(f"${e['cost_usd']}")
        return "  ".join(bits)
    if ev == "item_shipped":
        pr = e.get("pr", e.get("pr_number"))
        return f"PR #{pr}" if pr is not None else "shipped"
    if ev in ("item_created", "item_state"):
        if isinstance(e.get("field"), str):
            return f"{e['field']}: {_short(e.get('before'), 20)} -> {_short(e.get('after'), 24)}"
        # Snapshot shape: show what was actually set, not the null padding.
        shown = [(k, v) for k, v in sorted(e.items())
                 if k not in _TRACE_DETAIL_SKIP and v not in (None, "", [], {})]
        return "  ".join(f"{k}={_short(v, 22)}" for k, v in shown)
    if ev == "question_raised":
        bits = [str(e.get("question_id") or "?")]
        if e.get("ambiguity_class"):
            bits.append(str(e["ambiguity_class"]))
        if e.get("blocks_criteria"):
            bits.append("blocks " + ",".join(str(c) for c in e["blocks_criteria"]))
        return "  ".join(bits)
    if ev == "question_assigned":
        return f"{e.get('question_id')} -> {e.get('assignee') or e.get('assigned_to')}"
    if ev == "question_escalated":
        return (f"{e.get('question_id')} -> {e.get('tier')}"
                f"   {_short(e.get('reason') or '', 40)}")
    if ev in ("question_answered", "human_answered"):
        return (f"{e.get('question_id') or e.get('ask_id')} "
                f"source={e.get('source')}  {_short(e.get('answer') or '', 40)}")
    if ev == "human_required":
        return f"{e.get('ask_id')}  {_short(e.get('question') or '', 50)}"
    if ev == "decision_written":
        ids = e.get("decisions_in_context") or []
        return ", ".join(str(i) for i in ids) or str(e.get("decision_id") or "")
    if ev == "route_classified":
        return f"{e.get('route')}  {_short(e.get('rule') or '', 40)}"
    extra = {k: v for k, v in e.items() if k not in _TRACE_DETAIL_SKIP}
    return "  ".join(f"{k}={_short(v, 24)}" for k, v in sorted(extra.items())) or ""


def select_trace(events: list[dict], target: str) -> tuple[list[dict], str | None]:
    """Every event on one work item's journey, in total order.

    Resolution order: an exact trace_id wins; otherwise the target is read as
    an item_id and mapped through the ledger's first trace for that item.
    Events carrying the item but no trace are pulled in too, and so is any
    event sharing a run_id already selected -- a terminal record that lost its
    trace_id must not drop out of the timeline that explains it.
    """
    traces = {e.get("trace_id") for e in events if isinstance(e.get("trace_id"), str)}
    wanted: set[str] = set()
    if target in traces:
        wanted.add(target)
    mapped = items_mod.trace_ids_by_item(events).get(target)
    if mapped:
        wanted.add(mapped)

    selected = [e for e in events
                if (e.get("trace_id") in wanted and wanted) or e.get("item_id") == target]
    run_ids = {e.get("run_id") for e in selected if e.get("run_id")}
    if run_ids:
        by_id = {id(e) for e in selected}
        for e in events:
            if e.get("run_id") in run_ids and id(e) not in by_id:
                selected.append(e)
    selected.sort(key=items_mod.order_key)
    trace_id = next(iter(sorted(wanted)), None)
    return selected, trace_id


def cmd_trace(a):
    """Causal timeline for one item or trace, across agents and sessions."""
    repo = Path(a.repo).resolve()
    if not a.target:
        print("usage: wall trace <item_id|trace_id>", file=sys.stderr)
        return 2
    events = items_mod.load_events(repo)
    if not events:
        print("no events — the ledger is empty and no shards were found")
        return 1
    selected, trace_id = select_trace(events, a.target)
    if not selected:
        print(f"nothing found for {a.target!r}. "
              f"try an item_id (ST-106) or a trace_id (tr_st106).")
        return 1

    parents = {e["run_id"]: e.get("parent_run_id")
               for e in selected if e.get("event") == "run_start" and e.get("run_id")}

    def depth(run_id, guard=0):
        parent = parents.get(run_id)
        if not parent or parent not in parents or guard > 6:
            return 0
        return 1 + depth(parent, guard + 1)

    starts = {e["run_id"]: e for e in selected
              if e.get("event") == "run_start" and e.get("run_id")}
    t0 = items_mod.parse_ts(selected[0].get("ts"))
    tn = items_mod.parse_ts(selected[-1].get("ts"))
    span = _fmt_secs((tn - t0).total_seconds()) if (t0 and tn) else "?"
    sessions = sorted({e.get("session_id") for e in selected if e.get("session_id")})
    agents = sorted({e.get("agent_name") or e.get("agent_key")
                     for e in selected if e.get("agent_key")})
    item_ids = sorted({e["item_id"] for e in selected if e.get("item_id")})

    print(f"trace {trace_id or '(none)'}  ·  item {', '.join(item_ids) or '?'}  ·  "
          f"{len(selected)} events  ·  {len(sessions)} session(s)  ·  span {span}")
    print(f"  agents: {', '.join(agents) or '-'}")
    print()

    for e in selected:
        ts = items_mod.parse_ts(e.get("ts"))
        elapsed = _fmt_secs((ts - t0).total_seconds()) if (ts and t0) else "-"
        clock = e.get("ts", "")[11:23] or "-"
        pad = "  " * depth(e.get("run_id")) if e.get("run_id") else ""
        who = e.get("agent_name") or e.get("agent_key") or "-"
        role = e.get("role") or "-"
        detail = _trace_detail(e)
        if e.get("event") in ("run_end", "run_error") and e.get("duration_s") is None:
            start = starts.get(e.get("run_id"))
            s0 = items_mod.parse_ts(start.get("ts")) if start else None
            if s0 and ts:
                detail += f"  ({_fmt_secs((ts - s0).total_seconds())})"
        mark = " ^ " if e.get("event") == "question_escalated" else "   "
        actor = f"{pad}{role}/{who}" if e.get("agent_key") else f"{pad}(system)"
        print(f"{elapsed:>7}  {clock}{mark}{actor:<26} "
              f"{str(e.get('event')):<18} {detail}")

    hops = [e for e in selected if e.get("event") == "question_escalated"]
    if hops:
        print("\nescalation hops:")
        for h in hops:
            print(f"  {h.get('ts', '')[11:19]}  -> {h.get('tier')}   "
                  f"{_short(h.get('reason') or '', 60)}")
    unfinished = sorted(set(starts) - {e.get("run_id") for e in selected
                                       if e.get("event") in ("run_end", "run_error")})
    if unfinished:
        print("\nunfinished runs in this trace: " + ", ".join(unfinished))
    return 0


# --------------------------------------------------------------------- why

def _item_scopes(item: dict | None, events: list[dict], item_id: str) -> list[str]:
    """Where this item is allowed to write: its declared scope plus any path
    it actually holds a lease on. Leases are the ground truth when the two
    disagree, so both are shown."""
    out: list[str] = []
    scope = (item or {}).get("scope")
    if isinstance(scope, str) and scope.strip():
        out.append(scope.strip())
    elif isinstance(scope, list):
        out += [str(s).strip() for s in scope if str(s).strip()]
    for e in events:
        if e.get("event") != "lease_taken" or e.get("item_id") != item_id:
            continue
        paths = e.get("paths") or e.get("scope") or e.get("path")
        if isinstance(paths, str):
            paths = [paths]
        if isinstance(paths, list):
            out += [str(p).strip() for p in paths if str(p).strip()]
    seen, ordered = set(), []
    for p in out:
        if p not in seen:
            seen.add(p)
            ordered.append(p)
    return ordered


def cmd_why(a):
    """Which decisions govern this item, and which runs actually carried them."""
    repo = Path(a.repo).resolve()
    if not a.target:
        print("usage: wall why <item_id>", file=sys.stderr)
        return 2
    config = load_config(repo)
    events = items_mod.load_events(repo)
    folded = items_mod.fold_items(events)
    item = folded.get(a.target)
    trace_id = (item or {}).get("trace_id") or \
        items_mod.trace_ids_by_item(events).get(a.target)

    if item is None:
        print(f"no item {a.target!r} on the ledger. "
              f"known items: {', '.join(sorted(folded)) or '(none)'}")
        return 1

    print(f"item {item['item_id']}  {item.get('title') or '(untitled)'}")
    print(f"  status {item.get('status') or '-'}   assignee "
          f"{item.get('assignee') or '-'}   trace {trace_id or '-'}")

    scopes = _item_scopes(item, events, a.target)
    print(f"  scope: {', '.join(scopes) if scopes else '(none declared)'}")

    carried: dict[str, list[dict]] = {}
    for e in events:
        if e.get("item_id") != a.target and (not trace_id or e.get("trace_id") != trace_id):
            continue
        for dec_id in (e.get("decisions_in_context") or []):
            if isinstance(dec_id, str):
                carried.setdefault(dec_id, []).append(e)

    index = decisions_mod.index(repo, config)
    if not index.decisions:
        print(f"\nno decision log at "
              f"{decisions_mod.decisions_dir(repo, config)} — nothing to attach")
    effective = decisions_mod.in_effect(index.decisions, scopes, list(carried))

    print(f"\ndecisions in effect ({len(effective)}):")
    for d in effective:
        flag = "" if d["status"] == decisions_mod.ACTIVE else f"  [{d['status']}]"
        print(f"  {d['id']}  {d.get('title') or d['file']}{flag}")
        print(f"      scope {', '.join(d['scope']) or '-'}   "
              f"expert {d.get('expert') or '-'}   decided {d.get('decided') or '-'}")
        runs = carried.get(d["id"], [])
        if runs:
            shown = ", ".join(
                f"{r.get('run_id') or r.get('event')}"
                f"({r.get('agent_name') or r.get('agent_key') or '-'})"
                for r in runs[:6])
            print(f"      carried by: {shown}")
        else:
            print("      NOT carried by any run for this item — in effect but "
                  "never delivered")
    if not effective:
        print("  (none)")

    stray = sorted(set(carried) - {d["id"] for d in effective})
    if stray:
        print("\ncarried but not in the log:")
        for dec_id in stray:
            print(f"  {dec_id}  referenced by "
                  f"{len(carried[dec_id])} run(s), no DEC file found")

    ids = {d["id"] for d in effective} | set(carried)
    touching = [c for c in decisions_mod.contradictions(index.decisions)
                if ids & set(c["ids"])]
    if touching:
        print("\ncontradictions touching these decisions:")
        for c in touching:
            print(f"  {c['kind']:<28} {c['detail']}")
    for p in index.problems:
        print(f"  decision-log problem: {p.get('kind')} "
              f"{p.get('path', '')} {p.get('detail', '')}")
    return 0


# ------------------------------------------------------------------ answer

def cmd_answer(a):
    """Resolve a human-queue ask: write human_answered, optionally a DEC file."""
    repo = Path(a.repo).resolve()
    config = load_config(repo)
    events = items_mod.load_events(repo)
    folded = questions_mod.fold(events).questions

    if not a.target:
        open_qs = questions_mod.open_questions(folded)
        print("usage: wall answer <ask_id|question_id> --text \"...\"")
        print(f"\nopen ({len(open_qs)}):")
        for q in open_qs:
            print(f"  {q.get('ask_id') or q['question_id']:<12} "
                  f"{str(q.get('item_id') or '-'):<10} {q['status']:<15} "
                  f"{_short(q.get('text'), 60)}")
        return 2
    if not a.text:
        print("refusing to answer with nothing: pass --text \"...\"", file=sys.stderr)
        return 2

    q = questions_mod.resolve(folded, a.target)
    if q is None:
        print(f"no question {a.target!r}. open: "
              f"{', '.join(x.get('ask_id') or x['question_id'] for x in questions_mod.open_questions(folded)) or '(none)'}",
              file=sys.stderr)
        return 1
    if not questions_mod.is_open(q):
        print(f"{a.target} was already answered at {q.get('answered_at')} "
              f"(source {q.get('answer_source')}). Not writing a second answer.",
              file=sys.stderr)
        return 1

    dec_id = None
    if a.decision:
        index = decisions_mod.index(repo, config)
        dec_id = decisions_mod.next_id(index.decisions)
        text = decisions_mod.render_skeleton(
            dec_id,
            title=_short(q.get("text"), 60) or f"answer to {a.target}",
            question=q.get("text") or "",
            ruling=a.text,
            scope=(q.get("dependent_scope") or [""])[0] if q.get("dependent_scope") else "",
            asked_by=q.get("raised_by_key") or q.get("raised_by") or "",
            decided=items_mod.now_iso())
        path = decisions_mod.write_decision(repo, dec_id, text, config)
        print(f"wrote {path}")
        if "scope: null" in text:
            print("  scope is null — fill it in, or this ruling can never be "
                  "attached to an item automatically (and the front-matter gate "
                  "will say so)")

    result = questions_mod.answer(repo, a.target, a.text, session_id=a.session,
                                  events=events, decision_id=dec_id)
    record = result["record"]
    print(f"answered {record['ask_id']} on item {record.get('item_id') or '-'}"
          f"  (seq {record['seq']} in {record['session_id']})")
    if dec_id:
        print(f"  decision {dec_id} written — fill in Why and Consequences "
              f"before the next dispatch reads it")
    print("  run `wall run-once` to clear it from the Waiting tab")
    return 0


def cmd_ack_doc(a):
    """Acknowledge a document of record at its CURRENT sha (DOCS tab,
    DEC-0026). Refuses a missing file -- acking what you cannot have read
    is the defect the sha exists to prevent."""
    import oversight as oversight_mod
    repo = Path(a.repo).resolve()
    config = load_config(repo)
    rel = a.path.replace("\\", "/")
    # A prefix strip, not lstrip("./") -- lstrip eats any leading dot, so a
    # dot-directory document (".github/...", ".wall/...") would lose its dot
    # and read "does not exist" forever (host-review finding, CodeRabbit).
    while rel.startswith("./"):
        rel = rel[2:]
    target = repo / rel
    if not target.is_file():
        print(f"refusing: {rel} does not exist in this repo -- an ack records "
              f"a read, and there is nothing to read", file=sys.stderr)
        return 1
    sha = oversight_mod._sha12(target)
    if sha is None:
        print(f"refusing: {rel} could not be hashed", file=sys.stderr)
        return 1
    registry = config.get("documents_of_record") or list(
        oversight_mod.DEFAULT_DOCUMENTS_OF_RECORD)
    note = "" if rel in registry else \
        "  (note: not in documents_of_record -- the DOCS tab will not show it)"
    if a.feedback:
        # The Patron's OTHER answer (DEC-0027): not signed off. The doc
        # stays needs-review (feedback-open outranks every readable state
        # until a NEWER ack lands), and the text routes to the Architect as
        # a finding through the normal route.
        record = items_mod.append_event(repo, a.session, {
            "event": "doc_feedback", "path": rel, "sha": sha, "by": a.by,
            "text": a.feedback, "role": "human", "source": "human",
        })
        print(f"feedback on {rel} at {sha} by {a.by}  (seq {record['seq']} "
              f"in {record['session_id']}){note}")
        print("  the doc reads feedback-open on the DOCS tab until a NEWER "
              "ack lands; route the text to the Architect as a finding "
              "(docs/handoffs/finding-route.md)")
        return 0
    record = items_mod.append_event(repo, a.session, {
        "event": "doc_reviewed", "path": rel, "sha": sha, "by": a.by,
        "role": "human", "source": "human",
    })
    print(f"acked {rel} at {sha} by {a.by}  (seq {record['seq']} in "
          f"{record['session_id']}){note}")
    print("  run `wall run-once` to refresh the DOCS tab")
    return 0


def cmd_retro_note(a):
    """A Patron input the NEXT retrospective must consume (DEC-0027)."""
    repo = Path(a.repo).resolve()
    if not a.text or not a.text.strip():
        print("refusing an empty retro note: pass --text \"...\"",
              file=sys.stderr)
        return 2
    record = items_mod.append_event(repo, a.session, {
        "event": "retro_input", "by": a.by, "text": a.text.strip(),
        "role": "human", "source": "human",
    })
    print(f"retro input recorded by {a.by}  (seq {record['seq']} in "
          f"{record['session_id']})")
    print("  it shows on the RETRO tab until the next retro_held consumes "
          "it; RETROSPECTIVES.md binds that retro to address it")
    return 0


def cmd_compliance(a):
    """Select or deselect a compliance regime (DEC-0028). The selection is a
    decision with a reason, shown on the POSTURE tab's compliance section
    and challenged in BOTH directions by the fold's heuristics."""
    import compliance as compliance_mod
    repo = Path(a.repo).resolve()
    r = compliance_mod.regime(a.regime)
    if r is None:
        print(f"unknown regime {a.regime!r}; known: "
              f"{', '.join(compliance_mod.REGIME_IDS)}", file=sys.stderr)
        return 1
    if a.applicable == a.not_applicable:
        print("pass exactly one of --applicable / --not-applicable",
              file=sys.stderr)
        return 2
    applicable = bool(a.applicable)
    if not a.reason:
        print("refusing a selection without --reason: the reason IS the "
              "decision log entry", file=sys.stderr)
        return 2
    record = items_mod.append_event(repo, a.session, {
        "event": "compliance_selected", "regime": a.regime,
        "applicable": applicable, "reason": a.reason, "by": a.by,
        "role": "human", "source": "human",
    })
    word = "applicable" if applicable else "not applicable"
    print(f"{r['name']}: {word} -- {a.reason}  (seq {record['seq']})")
    print(f"  blueprint: {r['doc']}; attest controls with "
          f"`wall attest {a.regime} <control> --status pass|fail|waiver`")
    return 0


def cmd_attest(a):
    """Record one control's self-attestation for a regime (DEC-0028):
    pass, fail, or waiver -- a waiver is a RECORDED exception and needs
    its reason in --note."""
    import compliance as compliance_mod
    repo = Path(a.repo).resolve()
    r = compliance_mod.regime(a.regime)
    if r is None:
        print(f"unknown regime {a.regime!r}; known: "
              f"{', '.join(compliance_mod.REGIME_IDS)}", file=sys.stderr)
        return 1
    ids = compliance_mod.control_ids(a.regime)
    if a.control not in ids:
        print(f"unknown control {a.control!r} for {a.regime}; controls: "
              f"{', '.join(ids)}", file=sys.stderr)
        return 1
    if a.status not in compliance_mod.ATTEST_STATUSES:
        print(f"status must be one of {compliance_mod.ATTEST_STATUSES}",
              file=sys.stderr)
        return 2
    note = (a.note or "").strip()
    if not note:
        # DEC-0030 tightened this from waiver-only to every verdict: an audit
        # row is pass/fail/waiver PLUS its proof or reason, never a bare word
        # -- and whitespace is a bare word wearing a coat.
        print("refusing an attestation without --note: pass needs its proof, "
              "fail and waiver need their reason -- the note is the record",
              file=sys.stderr)
        return 2
    record = items_mod.append_event(repo, a.session, {
        "event": "compliance_attested", "regime": a.regime,
        "control": a.control, "status": a.status, "note": note,
        "by": a.by, "role": "human", "source": "human",
    })
    print(f"{a.regime} {a.control}: {a.status} -- {note}  (seq {record['seq']})")
    print("  run `wall run-once` to refresh the POSTURE tab")
    return 0


def cmd_compliance_scan(a):
    """The Warden's periodic evidence pass (DEC-0030): scan the tree for each
    regime's signals and record recommended/not per regime WITH the evidence.
    Deterministic and append-only -- the scan never flips a selection; the
    fold turns scan + selection into a disposition the POSTURE tab shows."""
    import compliance as compliance_mod
    repo = Path(a.repo).resolve()
    evidence = compliance_mod.scan_repo(repo)
    rows = [{"regime": rid, "recommended": bool(ev), "evidence": ev}
            for rid, ev in evidence.items()]
    record = items_mod.append_event(repo, a.session, {
        "event": "compliance_scanned", "regimes": rows,
        "by": a.by, "role": "warden", "source": a.source or "warden",
    })
    for row in rows:
        mark = "RECOMMENDED" if row["recommended"] else "no surface found"
        print(f"  {row['regime']:<12} {mark}")
        for ev in row["evidence"]:
            print(f"      {ev}")
    print(f"recorded (seq {record['seq']}); run `wall run-once` to refresh POSTURE")
    return 0


def cmd_audit_regime(a):
    """Record a full Warden audit of ONE regime (DEC-0030). The results file
    maps every control id to {status, note}: pass | fail | waiver, and the
    note is mandatory on every row -- pass carries its proof, fail and waiver
    their reason. A partial audit is refused by name: an audit that skips a
    control is an attestation gap wearing an audit's clothes."""
    import compliance as compliance_mod
    repo = Path(a.repo).resolve()
    r = compliance_mod.regime(a.regime)
    if r is None:
        print(f"unknown regime {a.regime!r}; known: "
              f"{', '.join(compliance_mod.REGIME_IDS)}", file=sys.stderr)
        return 1
    try:
        results = json.loads(Path(a.file).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        print(f"cannot read results file: {e}", file=sys.stderr)
        return 2
    if not isinstance(results, dict):
        print("results file must be an object: {control_id: {status, note}}",
              file=sys.stderr)
        return 2
    ids = compliance_mod.control_ids(a.regime)
    missing = [c for c in ids if c not in results]
    unknown = [c for c in results if c not in ids]
    if missing or unknown:
        if missing:
            print(f"audit incomplete -- controls not covered: "
                  f"{', '.join(missing)}", file=sys.stderr)
        if unknown:
            print(f"unknown controls for {a.regime}: {', '.join(unknown)}",
                  file=sys.stderr)
        return 2
    bad = []
    for cid in ids:
        row = results[cid]
        if (not isinstance(row, dict)
                or row.get("status") not in compliance_mod.ATTEST_STATUSES
                or not str(row.get("note") or "").strip()):
            bad.append(cid)
    if bad:
        print(f"every row needs status in {compliance_mod.ATTEST_STATUSES} "
              f"AND a non-empty note (proof or reason) -- bad: "
              f"{', '.join(bad)}", file=sys.stderr)
        return 2
    # One atomic batch (append_events, single O_APPEND write): a failure
    # while preparing writes NOTHING, so the ledger can never hold a partial
    # audit -- attestations without their completion marker.
    payloads = [{
        "event": "compliance_attested", "regime": a.regime,
        "control": cid, "status": results[cid]["status"],
        "note": str(results[cid]["note"]).strip(),
        "by": a.by, "role": "warden", "source": a.source or "warden",
    } for cid in ids]
    payloads.append({
        "event": "compliance_audited", "regime": a.regime, "by": a.by,
        "role": "warden", "source": a.source or "warden",
    })
    record = items_mod.append_events(repo, a.session, payloads)[-1]
    tally = {}
    for cid in ids:
        s = results[cid]["status"]
        tally[s] = tally.get(s, 0) + 1
    print(f"{a.regime} audited: " +
          " ".join(f"{k}={v}" for k, v in sorted(tally.items())) +
          f"  ({len(ids)} controls, seq {record['seq']})")
    print("  run `wall run-once` to refresh the POSTURE tab")
    return 0


# -------------------------------------------------------------- fast-track

def fast_track_gates(repo: Path, config: dict) -> tuple[list[dict], list[dict]]:
    """The free local gates. Fast-track means no *cloud* minutes, not no
    validation (FAST_TRACK.md). Returns (blocking, warnings)."""
    blocking: list[dict] = []
    warnings: list[dict] = []

    for p in items_mod.ledger_schema_check(Path(repo) / ".wall" / "events"):
        where = p.get("shard") or p.get("session_id") or ""
        detail = p.get("detail") or p.get("field") or p.get("seq")
        blocking.append({"gate": "ledger-schema",
                         "detail": f"{p['kind']}  {where} {detail}".strip()})

    drift = items_mod.diff_state(repo)
    if drift["checked"] and drift["count"]:
        blocking.append({"gate": "item-state",
                         "detail": f"{drift['count']} item field(s) disagree with the "
                                   f"ledger — run `wall diff-state`"})
    for p in drift["problems"]:
        blocking.append({"gate": "item-state",
                         "detail": f"{p.get('kind')} {p.get('detail', '')}"})

    index = decisions_mod.index(repo, config)
    for p in index.problems:
        blocking.append({"gate": "decision-front-matter",
                         "detail": f"{p.get('kind')}  {p.get('path', '')} "
                                   f"{p.get('detail', '')}"})
    for c in decisions_mod.contradictions(index.decisions):
        warnings.append({"gate": "decision-contradiction", "detail": c["detail"]})
    return blocking, warnings


def _git(repo: Path, *args: str) -> tuple[int, str, str]:
    # Bounded: a timeout comes back as an ordinary failure (rc 124) so every
    # caller's existing nonzero-rc handling covers it -- never a hang.
    try:
        out = subprocess.run(["git", "-C", str(repo), *args],
                             capture_output=True, text=True, check=False,
                             timeout=GIT_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return 124, "", "git %s timed out after %ss" % (" ".join(args), GIT_TIMEOUT_S)
    return out.returncode, out.stdout.strip(), out.stderr.strip()


def cmd_fast_track(a):
    """Classify, gate, stage. Never pushes and never merges.

    RECONCILIATION Q8: fast-track is the docs-only *PR* path. The coordinator
    merges it once its scoped checks are green; this command stops at a local
    commit and prints what comes next.
    """
    repo = Path(a.repo).resolve()
    config = load_config(repo)
    cfg = config.get("fast_track", {})

    files = list(a.file) if a.file else changed_files(repo, a.staged)
    if not files:
        print("no changes")
        return 0

    result = classify_files(files, cfg)
    print_classification(result)

    if result["route"] != "fast_track":
        print()
        if result["mixed"]:
            print("refusing a mixed changeset. the split:")
            print("  1. fast-track the docs:")
            print("       wall fast-track " +
                  " ".join(f"--file {p}" for p in result["fast"]))
            print("  2. leave the rest on the full track:")
            for p in result["full"]:
                print(f"       {p}")
        else:
            print("full track: this changeset needs tests, review and CI.")
        return 1

    blocking, warnings = fast_track_gates(repo, config)
    for w in warnings:
        print(f"  warn   {w['gate']}: {w['detail']}")
    if blocking:
        print(f"\n{len(blocking)} local gate failure(s) — fast-track skips CI, "
              f"not validation:")
        for b in blocking:
            print(f"  FAIL   {b['gate']}: {b['detail']}")
        return 1
    print("\nlocal gates: clean (ledger schema, item state, decision front matter)")

    if a.stage or a.commit:
        rc, _, err = _git(repo, "add", "--", *result["fast"])
        if rc != 0:
            print(f"git add failed: {err}", file=sys.stderr)
            return 1
        print(f"staged {len(result['fast'])} file(s)")
        # The ledger event fires even on the fast path: a fast-track commit is
        # still a work item with a trace (FAST_TRACK.md, "what it never skips").
        items_mod.append_event(repo, a.session, {
            "event": "route_classified", "route": "fast_track",
            "item_id": a.item, "trace_id": a.trace, "role": "maestro",
            "rule": "every path matched the allow list",
            "files": result["fast"],
        })
        for path in result["significant"]:
            items_mod.append_event(repo, a.session, {
                "event": "doc_impact", "path": path, "item_id": a.item,
                "trace_id": a.trace, "role": "maestro",
                "detail": "architecture/decision doc changed on the fast path",
            })

    if a.commit:
        branch = _git(repo, "rev-parse", "--abbrev-ref", "HEAD")[1]
        if branch in ("main", "master") and not a.allow_main:
            print(f"\nrefusing to commit on {branch}. fast-track is a PR path "
                  f"(RECONCILIATION Q8).\n  branch first, or pass --allow-main "
                  f"if you really mean it.", file=sys.stderr)
            return 1
        name = (cfg.get("identity") or {}).get("name") or os.environ.get("GIT_AUTHOR_NAME")
        email = (cfg.get("identity") or {}).get("email") or os.environ.get("GIT_AUTHOR_EMAIL")
        if not name or not email:
            print("\nrefusing to commit without an identity. set "
                  "fast_track.identity {name,email} in .wall/config/wall.json, "
                  "or GIT_AUTHOR_NAME / GIT_AUTHOR_EMAIL.\n"
                  "  (agents never write `git config` — it is repo-global and one "
                  "agent's write lands on another agent's commit: RECONCILIATION G1)",
                  file=sys.stderr)
            return 1
        message = a.message or "docs: fast-track"
        rc, out, err = _git(repo, "-c", f"user.name={name}", "-c", f"user.email={email}",
                            "commit", "-m", message)
        if rc != 0:
            print(f"git commit failed: {err or out}", file=sys.stderr)
            return 1
        print(f"committed locally as {name} <{email}>")

    print("\nnext: push this branch and open a PR. fast-track does not push and "
          "does not merge —\n      the coordinator merges once the scoped checks "
          "are green (RECONCILIATION Q8).")
    return 0


# ----------------------------------------- plumbing: timer, server, shipping

_INSTALL_NEEDS = ("a platform adapter in install/. See INSTALL.md — "
                  "Windows uses Register-ScheduledTask with a 2-minute "
                  "repetition trigger, driving `wall run-once` per registered repo.")
_REGISTRY_NEEDS = "the machine-wide registry at %USERPROFILE%\\.wall\\registry.json"


def cmd_context(a):
    """`wall context sync|check`: the context-file sync (context_sync.py),
    lazy like the other dispatched commands."""
    try:
        import context_sync  # noqa: PLC0415  (deliberately lazy)
    except ImportError:
        stub("context", "tools/wall/context_sync.py: AGENTS.md masters "
                        "and their generated tool copies")
        return 2
    return context_sync.run(Path(a.repo), a.action, adopt=a.adopt,
                            symlink=a.symlink, dry_run=a.dry_run)


def cmd_install(a):
    return via_service("install", a, _INSTALL_NEEDS)


def cmd_register(a):
    return via_service("register", a, _REGISTRY_NEEDS)


def cmd_unregister(a):
    return via_service("unregister", a, _REGISTRY_NEEDS)


def cmd_verify(a):
    return via_service("verify", a,
                       "the install adapter, plus --app MANIFEST.sha256 comparison "
                       "against what the repo expects")


def cmd_uninstall(a):
    return via_service("uninstall", a,
                       "the install adapter's teardown: remove the scheduled task "
                       "and leave .wall/ intact")


def cmd_serve(a):
    return via_service("serve", a,
                       "the stdlib server that binds 127.0.0.1 explicitly and sends "
                       "no-cache headers on the polled JSON")


def cmd_ship(a):
    return via_shipper("ship", a,
                       "the isolated-branch shipper: build a tree in a temporary "
                       "GIT_INDEX_FILE and push it by object id, leaving the working "
                       "tree and the current branch untouched")


def cmd_fetch_events(a):
    return via_shipper("fetch", a,
                       "the isolated-branch shipper's freshness-guarded fetch")


# ---------------------------------------------------------------- main

def main() -> int:
    p = argparse.ArgumentParser(prog="wall", description=__doc__.split("\n")[0])
    p.add_argument("--repo", default=".", help="repo root containing .wall/")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("run-once", help="merge shards and render the wall")
    s.add_argument("--rebuild", action="store_true")
    s.set_defaults(fn=cmd_run_once)

    s = sub.add_parser("summary", help="one-screen human digest of the wall")
    s.add_argument("--json", dest="as_json", action="store_true",
                   help="the same summary as machine-readable JSON")
    s.set_defaults(fn=cmd_summary)

    s = sub.add_parser("doctor", help="heartbeat, integrity flags, roster")
    s.add_argument("--json", dest="as_json", action="store_true",
                   help="machine-readable; also writes .wall/derived/doctor.json")
    s.set_defaults(fn=cmd_doctor)

    s = sub.add_parser("classify", help="show the route for the current changeset")
    s.add_argument("--staged", action="store_true")
    s.set_defaults(fn=cmd_classify)

    s = sub.add_parser("agents", help="roster operations")
    s.add_argument("agents_action",
                   choices=["roster", "claim", "release", "whois", "audit"],
                   nargs="?", default="roster")
    s.add_argument("--role", default="builder")
    s.add_argument("--session", default="local")
    s.add_argument("--key")
    s.add_argument("--name")
    s.add_argument("--at", help="whois: resolve the name at this UTC instant")
    s.set_defaults(fn=cmd_agents)

    s = sub.add_parser("rebuild", help="regenerate .wall/items/ from events alone")
    s.add_argument("--prune", action="store_true",
                   help="delete item files no event created")
    s.set_defaults(fn=cmd_rebuild)

    sub.add_parser("diff-state", help="ledger-derived item state vs disk"
                   ).set_defaults(fn=cmd_diff_state)

    s = sub.add_parser("trace", help="causal timeline for an item or trace")
    s.add_argument("target", nargs="?", help="item_id or trace_id")
    s.set_defaults(fn=cmd_trace)

    s = sub.add_parser("why", help="decisions in effect, and which runs saw them")
    s.add_argument("target", nargs="?", help="item_id")
    s.set_defaults(fn=cmd_why)

    s = sub.add_parser("answer", help="resolve a human-queue question")
    s.add_argument("target", nargs="?", help="ask_id or question_id")
    s.add_argument("--text", help="the answer")
    s.add_argument("--decision", action="store_true",
                   help="also write a DEC-NNNN skeleton and reference it")
    s.add_argument("--session", default="s_human", help="shard to append to")
    s.set_defaults(fn=cmd_answer)

    s = sub.add_parser("ack-doc",
                       help="acknowledge a document of record at its current sha")
    s.add_argument("path", help="repo-relative path, e.g. RULES.md")
    s.add_argument("--by", default="engineer", help="who reviewed it")
    s.add_argument("--feedback",
                   help="do NOT sign off: record this correction/remap/"
                        "discussion text instead (stays needs-review)")
    s.add_argument("--session", default="s_human", help="shard to append to")
    s.set_defaults(fn=cmd_ack_doc)

    s = sub.add_parser("compliance",
                       help="select whether a compliance regime applies")
    s.add_argument("regime", help="soc2 | hipaa | pci | privacy | government | sector")
    s.add_argument("--applicable", action="store_true")
    s.add_argument("--not-applicable", action="store_true")
    s.add_argument("--reason", help="why -- this IS the decision log entry")
    s.add_argument("--by", default="engineer")
    s.add_argument("--session", default="s_human")
    s.set_defaults(fn=cmd_compliance)

    s = sub.add_parser("attest",
                       help="self-attest one compliance control: pass/fail/waiver")
    s.add_argument("regime")
    s.add_argument("control", help="e.g. CC6, R3, SR-TEC (see the regime doc)")
    s.add_argument("--status", required=True, choices=["pass", "fail", "waiver"])
    s.add_argument("--note", help="REQUIRED: pass carries its proof, "
                                  "fail and waiver their reason")
    s.add_argument("--by", default="engineer")
    s.add_argument("--session", default="s_human")
    s.set_defaults(fn=cmd_attest)

    s = sub.add_parser("compliance-scan",
                       help="Warden evidence pass: which regimes does the "
                            "code suggest? (DEC-0030)")
    s.add_argument("--by", default="warden")
    s.add_argument("--source", default="warden")
    s.add_argument("--session", default="s_warden")
    s.set_defaults(fn=cmd_compliance_scan)

    s = sub.add_parser("audit",
                       help="record a full Warden audit of one regime: every "
                            "control pass/fail/waiver + proof or reason")
    s.add_argument("regime")
    s.add_argument("--file", required=True,
                   help="JSON: {control_id: {status, note}} covering EVERY control")
    s.add_argument("--by", default="warden")
    s.add_argument("--source", default="warden")
    s.add_argument("--session", default="s_warden")
    s.set_defaults(fn=cmd_audit_regime)

    s = sub.add_parser("retro-note",
                       help="a Patron input the next retrospective must consume")
    s.add_argument("--text", required=True, help="the note")
    s.add_argument("--by", default="engineer", help="who raised it")
    s.add_argument("--session", default="s_human", help="shard to append to")
    s.set_defaults(fn=cmd_retro_note)

    s = sub.add_parser("fast-track", help="classify, run local gates, stage")
    s.add_argument("--staged", action="store_true")
    s.add_argument("--file", action="append", default=[],
                   help="classify these paths instead of the git diff (repeatable)")
    s.add_argument("--stage", action="store_true", help="git add the fast-track subset")
    s.add_argument("--commit", action="store_true", help="commit locally; never pushes")
    s.add_argument("--allow-main", action="store_true")
    s.add_argument("-m", "--message")
    s.add_argument("--item", help="item_id for the ledger event")
    s.add_argument("--trace", help="trace_id for the ledger event")
    s.add_argument("--session", default="s_human")
    s.set_defaults(fn=cmd_fast_track)

    s = sub.add_parser("context", help="AGENTS.md masters -> generated "
                                       "CLAUDE.md and other tool copies")
    s.add_argument("action", choices=["sync", "check"])
    s.add_argument("--adopt", action="store_true",
                   help="sync: move a hand-written copy into a NEW AGENTS.md")
    s.add_argument("--symlink", action="store_true",
                   help="sync: relative symlinks instead of copies")
    s.add_argument("--dry-run", action="store_true",
                   help="sync: report only, write nothing")
    s.set_defaults(fn=cmd_context)

    # ---- plumbing, dispatched to service.py / shipper.py -----------------
    s = sub.add_parser("install", help="create the machine-wide timer")
    s.add_argument("--yes", action="store_true", help="skip the confirmation")
    s.add_argument("--interval", type=int, help="sweep interval in seconds")
    s.add_argument("--system", help="force a platform adapter")
    s.set_defaults(fn=cmd_install)

    s = sub.add_parser("register", help="add this repo to the timer's registry")
    s.add_argument("--name", help="display name for this repo")
    s.set_defaults(fn=cmd_register)

    s = sub.add_parser("unregister", help="drop this repo from the registry")
    s.add_argument("--name", help="display name for this repo")
    s.set_defaults(fn=cmd_unregister)

    s = sub.add_parser("verify", help="timer alive, heartbeat fresh, app in sync")
    s.add_argument("--app", help="deployed app path to compare MANIFEST.sha256 against")
    s.add_argument("--stale-after-s", type=int, dest="stale_after_s",
                   help="seconds before a heartbeat counts as stale")
    s.set_defaults(fn=cmd_verify)

    s = sub.add_parser("uninstall", help="remove the timer, keep .wall/")
    s.add_argument("--purge", action="store_true",
                   help="also remove the sweeper and the machine registry")
    s.add_argument("--system", help="force a platform adapter")
    s.set_defaults(fn=cmd_uninstall)

    s = sub.add_parser("serve", help="serve .wall/derived/ on 127.0.0.1")
    s.add_argument("--port", type=int)
    s.add_argument("--check", action="store_true", help="probe a running server instead")
    s.add_argument("--verbose", action="store_true")
    s.set_defaults(fn=cmd_serve)

    s = sub.add_parser("ship", help="push today's shards to the isolated branch")
    s.add_argument("--branch", help="default: wall-events")
    s.set_defaults(fn=cmd_ship)

    s = sub.add_parser("fetch-events", help="materialise the isolated branch locally")
    s.add_argument("--branch", help="default: wall-events")
    s.set_defaults(fn=cmd_fetch_events)

    a = p.parse_args()
    try:
        return a.fn(a) or 0
    except NotImplementedError as e:
        print(e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
