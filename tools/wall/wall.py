#!/usr/bin/env python3
"""wall — the command surface for the agent workforce.

Commands marked STUB raise NotImplementedError with a note on what they need.
Everything else works today. `wall run-once` in particular is fully functional,
so the whole system can be driven by hand or from a git hook while the scheduled
task adapters are still stubs.

Local-only: no network calls anywhere in this file.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

import courier                      # noqa: E402
from agents import AgentRegistry    # noqa: E402


def load_config(repo: Path) -> dict:
    p = repo / ".wall" / "config" / "wall.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    example = HERE / "config" / "wall.example.json"
    print(f"no config at {p}\n  copy the example: {example}", file=sys.stderr)
    return {}


def stub(name: str, needs: str):
    raise NotImplementedError(f"`wall {name}` is not built yet.\n  Needs: {needs}")


# ---------------------------------------------------------------- sweep

def cmd_run_once(a):
    """Merge shards, build the snapshot, render the wall. Fully working."""
    snap = courier.run_once(Path(a.repo).resolve(), rebuild=a.rebuild)
    flags = snap["integrity"]
    n = sum(len(v) for v in flags.values() if isinstance(v, list))
    print(f"swept {snap['courier']['events']} events from "
          f"{snap['courier']['shards']} shards"
          f"{f' — {n} integrity flags' if n else ' — clean'}")
    return 0


def cmd_doctor(a):
    """Heartbeat, sequence gaps, orphan runs, roster health. Working."""
    repo = Path(a.repo).resolve()
    hb = repo / ".wall" / "derived" / "heartbeat.json"
    print("heartbeat:", json.loads(hb.read_text()) if hb.exists() else "MISSING — courier has never run")

    snap_path = repo / ".wall" / "derived" / "wall.json"
    if snap_path.exists():
        i = json.loads(snap_path.read_text())["integrity"]
        for k, v in i.items():
            n = len(v) if isinstance(v, list) else v
            print(f"  {k:<16} {'clean' if not n else str(n) + ' flagged'}")

    problems = AgentRegistry(repo).audit()
    print("  roster          ", "clean" if not problems else "; ".join(problems))
    return 0


# ---------------------------------------------------------------- routing

def cmd_classify(a):
    """Route a changeset by path. Mechanical — never asserted by an agent."""
    repo = Path(a.repo).resolve()
    cfg = load_config(repo).get("fast_track", {})
    allow, deny = cfg.get("allow", []), cfg.get("deny", [])

    args = ["git", "-C", str(repo), "diff", "--name-only"]
    if a.staged:
        args.append("--cached")
    files = [f for f in subprocess.run(args, capture_output=True, text=True).stdout.split("\n") if f]

    if not files:
        print("no changes")
        return 0

    def match(path, globs):
        return next((g for g in globs if fnmatch.fnmatch(path, g)), None)

    verdict, reasons = "fast_track", []
    for f in files:
        d = match(f, deny)
        if d:
            verdict = "full_track"
            reasons.append(f"  {f}\n      DENY   matched {d}")
            continue
        al = match(f, allow)
        if al:
            reasons.append(f"  {f}\n      allow  matched {al}")
        else:
            verdict = "full_track"
            reasons.append(f"  {f}\n      DENY   matched no allow rule")

    print(f"route: {verdict}\n" + "\n".join(reasons))
    if verdict == "full_track" and any("allow" in r for r in reasons):
        print("\nmixed changeset — split it rather than taking an exception.")
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
    elif a.agents_action == "audit":
        p = reg.audit()
        print("\n".join(p) if p else "roster clean")
        return 1 if p else 0
    else:
        for r in reg.read():
            print(f" {'●' if r['status'] == 'live' else '○'} "
                  f"{r['name']:<12} {r['key']:<12} {r['role']:<12} {r['status']}")
    return 0


# ---------------------------------------------------------------- stubs

def cmd_install(a):
    stub("install", "a platform adapter in install/. See INSTALL.md — "
                    "Windows uses Register-ScheduledTask with a 2-minute "
                    "repetition trigger, driving `wall run-once` per registered repo.")


def cmd_register(a):
    stub("register", "the machine-wide registry at %USERPROFILE%\\.wall\\registry.json")


def cmd_verify(a):
    stub("verify", "the install adapter, plus --app MANIFEST.sha256 comparison "
                   "against what the repo expects")


def cmd_trace(a):
    stub("trace", "trace_id threading through dispatch. Read the ledger, filter "
                  "by trace_id, order by (ts, session_id, seq).")


def cmd_why(a):
    stub("why", "decisions_in_context on run records plus docs/decisions/ index")


def cmd_diff_state(a):
    stub("diff-state", "`wall rebuild` — regenerate .wall/items/ from events "
                       "alone, then diff against disk. Populates integrity.state_drift.")


def cmd_fast_track(a):
    stub("fast-track", "classify (built) + local gates + staged commit + push. "
                       "Must refuse a mixed changeset and offer the split.")


def cmd_answer(a):
    stub("answer", "the human queue: resolve an ask_id, write human_answered, "
                   "write DEC-NNNN, signal Maestro to resume the parked item.")


# ---------------------------------------------------------------- main

def main() -> int:
    p = argparse.ArgumentParser(prog="wall", description=__doc__.split("\n")[0])
    p.add_argument("--repo", default=".", help="repo root containing .wall/")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("run-once", help="merge shards and render the wall")
    s.add_argument("--rebuild", action="store_true")
    s.set_defaults(fn=cmd_run_once)

    sub.add_parser("doctor", help="heartbeat, integrity flags, roster").set_defaults(fn=cmd_doctor)

    s = sub.add_parser("classify", help="show the route for the current changeset")
    s.add_argument("--staged", action="store_true")
    s.set_defaults(fn=cmd_classify)

    s = sub.add_parser("agents", help="roster operations")
    s.add_argument("agents_action", choices=["roster", "claim", "release", "audit"],
                   nargs="?", default="roster")
    s.add_argument("--role", default="builder")
    s.add_argument("--session", default="local")
    s.add_argument("--key")
    s.add_argument("--name")
    s.set_defaults(fn=cmd_agents)

    for name, fn, helptext in [
        ("install",    cmd_install,    "STUB — create the machine-wide timer"),
        ("register",   cmd_register,   "STUB — add this repo to the timer's registry"),
        ("verify",     cmd_verify,     "STUB — timer alive, heartbeat fresh, app in sync"),
        ("trace",      cmd_trace,      "STUB — causal timeline for an item"),
        ("why",        cmd_why,        "STUB — decisions in effect and who saw them"),
        ("diff-state", cmd_diff_state, "STUB — ledger-derived state vs disk"),
        ("fast-track", cmd_fast_track, "STUB — classify, gate, commit, push"),
        ("answer",     cmd_answer,     "STUB — resolve a human-queue question"),
    ]:
        sp = sub.add_parser(name, help=helptext)
        sp.add_argument("target", nargs="?")
        sp.set_defaults(fn=fn)

    a = p.parse_args()
    try:
        return a.fn(a) or 0
    except NotImplementedError as e:
        print(e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
