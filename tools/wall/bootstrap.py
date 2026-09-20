#!/usr/bin/env python3
"""wall-bootstrap — the runbooks as one command (DEC-0021).

Patron direction (2026-09-20): a new environment or session — local PC,
VM, Docker, cluster or cloud — and the engineer's preferred integration
interface must not require more than running a script: load the kit as
a SIDE REPO — a bounded subtree, separated from but inside the same
repository as the product — with clear extra steps for assimilating an
existing setup, and a scripted upgrade path.

Three subcommands, each the executable form of a runbook the README
carries in prose:

  fresh    the empty-repo runbook, steps 1-2 automated: vendor
           tools/wall/ + the process corpus + frontend theme into the
           product repo, materialize .wall/{config,registry}, copy the
           context-document templates that are MISSING (never over an
           existing file), stamp the kit source for later upgrades, and
           emit the engineer's MCP client configs.
  adopt    the existing-repo runbook's INVENTORY, automated: detect
           what already serves each adoption function (entry point,
           rules, failure registry, checklist, standards, decision log,
           budgets, roster) by the names those things actually go by,
           report the mapping, and vendor only the machine — templates
           are listed as gaps, never written over a host's documents.
  upgrade  the README's "Upgrading an adoption", automated: re-vendor
           the kit subtree VERBATIM from a newer kit checkout, show
           what changed and the decision-index delta since the stamped
           source, and refresh the stamp. Host config is never touched.

Every mode is DRY-RUN by default and prints exactly what it would do;
`--apply` does it. That is the kit's consent discipline: the script
prepares, the engineer says go. Stdlib only (DEC-0017); the script runs
from the kit checkout it vendors, so there is nothing to install first.

The human's remaining steps are the ones that are DECISIONS by design
and stay manual on purpose: filling RULES.md Part 1, `wall install`
(the machine timer needs explicit say-so, DEC-0010), and arming
`queue_api` against a real host endpoint.
"""

from __future__ import annotations

import argparse
import difflib
import filecmp
import json
import shutil
import subprocess
import sys
from pathlib import Path

KIT_ROOT = Path(__file__).resolve().parents[2]

#: The side-repo subtree (DEC-0021): what `fresh` vendors and `upgrade`
#: re-vendors, relative to both the kit and the product repo. Bounded on
#: purpose — the kit never scatters files outside these prefixes plus
#: the root context documents the templates become.
VENDORED = ("tools/wall", "docs", "frontend/theme", "templates")

#: Context documents `fresh` materializes at the product root — only
#: where the target does not already exist.
TEMPLATE_TARGETS = {
    "CLAUDE.md.template": "CLAUDE.md",
    "RULES.md.template": "RULES.md",
    "FAILURE_PATTERNS.md.template": "FAILURE_PATTERNS.md",
    "SHIP_CHECKLIST.md.template": "SHIP_CHECKLIST.md",
    "BEST_PRACTICES.md.template": "BEST_PRACTICES.md",
    "DOCS_MAP.md.template": "DOCS_MAP.md",
    "BUDGETED_DOCS.md.template": "BUDGETED_DOCS.md",
    "OWNER_DECISIONS.md.template": "OWNER_DECISIONS.md",
    "REVIEWER_LANES.md.template": "REVIEWER_LANES.md",
    "ENGINEERING_STANDARD.md.template": "docs/ENGINEERING_STANDARD.md",
}

#: The adoption functions and the names they actually go by in the wild.
#: Used by `adopt` to answer "what already serves this?" per the README's
#: existing-repo runbook — detection is a report, never a judgment.
ADOPTION_FUNCTIONS: dict[str, tuple[str, ...]] = {
    "entry point": ("CLAUDE.md", "AGENTS.md", "README.md"),
    "standing rules": ("RULES.md", "STANDING_RULES.md", "CONTRIBUTING.md"),
    "failure registry": ("FAILURE_PATTERNS.md", "KNOWN_FAILURE_PATTERNS.md"),
    "ship checklist": ("SHIP_CHECKLIST.md", "CLAUDE_SHIP_CHECKLIST.md",
                       "RELEASE_CHECKLIST.md"),
    "coding standards": ("BEST_PRACTICES.md", "best_practices.md",
                         "CODING_STANDARDS.md", "STYLE.md"),
    "decision log": ("docs/decisions", "docs/adr", "adr", "doc/adr"),
    "prompt budgets": ("BUDGETED_DOCS.md",),
    "agent roster": (".claude/agents",),
}

MCP_CONFIGS = {
    "claude-code": (".mcp.json", "mcpServers"),
    "cursor": (".cursor/mcp.json", "mcpServers"),
    "vscode": (".vscode/mcp.json", "servers"),
}


def _say(msg: str) -> None:
    print(msg)


def _kit_stamp() -> dict:
    """Identify the kit source being vendored: commit when the kit
    checkout is a git repo, honestly 'unknown' when it is a bare copy."""
    try:
        commit = subprocess.run(
            ["git", "-C", str(KIT_ROOT), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        commit = ""
    return {"kit_commit": commit or "unknown",
            "vendored": list(VENDORED)}


def _copy_tree(src: Path, dst: Path, apply: bool,
               exclude: tuple[str, ...] = ()) -> int:
    """Copy src over dst (files verbatim, verdict per file). Returns the
    number of files that are new or differ — the honest 'what changed'
    count a dry run reports. `exclude` names relative first-segments to
    skip (adopt mode uses it to keep the HOST's decision log the host's)."""
    changed = 0
    for path in sorted(src.rglob("*")):
        if path.is_dir() or "__pycache__" in path.parts:
            continue
        rel = path.relative_to(src)
        if rel.parts and rel.parts[0] in exclude:
            continue
        target = dst / rel
        if target.exists() and filecmp.cmp(path, target, shallow=False):
            continue
        changed += 1
        verb = "update" if target.exists() else "add"
        _say(f"  {verb}  {dst.name}/{rel}" if dst.name else f"  {verb}  {rel}")
        if apply:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
    return changed


def _write(path: Path, text: str, apply: bool, label: str) -> None:
    exists = path.exists()
    _say(f"  {'keep ' if exists else 'write'}  {label}"
         + ("  (exists — never overwritten)" if exists else ""))
    if apply and not exists:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def emit_mcp_configs(repo: Path, clients: list[str], apply: bool) -> None:
    """The engineer's preferred interface, configured: three lines per
    client, --role engineer (DEC-0019 — this is the human's seat)."""
    server = {"command": "python3",
              "args": ["tools/wall/mcp_server.py", "--repo", ".",
                       "--role", "engineer"]}
    for client in clients:
        rel, key = MCP_CONFIGS[client]
        path = repo / rel
        payload = {key: {"wall": dict(server)}}
        if client == "vscode":
            payload[key]["wall"]["type"] = "stdio"
        if path.exists():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                _say(f"  skip   {rel}  (exists but is not valid JSON — "
                     f"fix it by hand, not by overwrite)")
                continue
            if "wall" in (existing.get(key) or {}):
                _say(f"  keep   {rel}  (wall server already configured)")
                continue
            existing.setdefault(key, {})["wall"] = payload[key]["wall"]
            _say(f"  merge  {rel}  (+ wall server)")
            if apply:
                path.write_text(json.dumps(existing, indent=2) + "\n",
                                encoding="utf-8")
            continue
        _say(f"  write  {rel}")
        if apply:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload, indent=2) + "\n",
                            encoding="utf-8")


def _stamp(repo: Path, apply: bool) -> None:
    stamp = _kit_stamp()
    path = repo / ".wall" / "config" / "kit_source.json"
    _say(f"  stamp  .wall/config/kit_source.json  "
         f"(kit {stamp['kit_commit'][:12]})")
    if apply:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(stamp, indent=2) + "\n", encoding="utf-8")


def _next_steps(repo: Path, mode: str) -> None:
    _say("\nwhat stays yours, on purpose:")
    if mode == "fresh":
        _say("  1. Fill RULES.md Part 1 — the hard rules need real thought; "
             "everything else starts thin (docs/TEMPLATE_INTAKE.md has the "
             "question sets).")
    if mode == "adopt":
        _say("  1. For each MAPPED function above: keep the host's document "
             "and add only what the adoption checklist names as missing, "
             "THERE (README existing-repo runbook). For each GAP: copy the "
             "named template.")
    _say(f"  2. First render:  python3 tools/wall/wall.py --repo "
         f"{repo} run-once   then   ... summary")
    _say("  3. The machine timer needs your explicit say-so (DEC-0010):  "
         "wall install")
    _say("  4. Docker / VM / Kubernetes: docs/DEPLOYMENT_TARGETS.md — same "
         "files, only who runs the timer and serves changes.")
    _say("  5. To arm EXECUTE/enqueue against a real backend: set "
         "queue_api in .wall/config/wall.json (docs/MCP_INTEGRATION.md).")


# ----------------------------------------------------------------- modes

def cmd_fresh(a) -> int:
    repo = Path(a.into).resolve()
    apply = a.apply
    _say(f"fresh bootstrap into {repo}  "
         f"({'APPLYING' if apply else 'dry run — pass --apply to do it'})")
    if repo == KIT_ROOT:
        _say("refusing: --into is the kit checkout itself")
        return 2
    _say("\nvendor the side-repo subtree (DEC-0021):")
    for prefix in VENDORED:
        _copy_tree(KIT_ROOT / prefix, repo / prefix, apply)
    _say("\ncontext documents (missing ones only):")
    for template, target in TEMPLATE_TARGETS.items():
        src = KIT_ROOT / "templates" / template
        _write(repo / target, src.read_text(encoding="utf-8"), apply, target)
    _say("\nwall state:")
    example = (KIT_ROOT / "tools" / "wall" / "config" /
               "wall.example.json").read_text(encoding="utf-8")
    _write(repo / ".wall" / "config" / "wall.json", example, apply,
           ".wall/config/wall.json  (from wall.example.json — bind the "
           "values to YOUR rules)")
    _write(repo / ".wall" / "registry" / "agents.md",
           "# Agent roster\n\n(claim with `wall agents claim`)\n", apply,
           ".wall/registry/agents.md")
    _stamp(repo, apply)
    if a.mcp:
        _say("\nengineer interface configs (--role engineer, DEC-0019):")
        emit_mcp_configs(repo, a.mcp, apply)
    _next_steps(repo, "fresh")
    return 0


def cmd_adopt(a) -> int:
    repo = Path(a.into).resolve()
    apply = a.apply
    _say(f"adoption inventory of {repo}  "
         f"({'APPLYING the machine' if apply else 'dry run'})")
    _say("\nwhat already serves each function (kept, never overwritten):")
    gaps: list[str] = []
    for function, names in ADOPTION_FUNCTIONS.items():
        hit = next((n for n in names if (repo / n).exists()), None)
        if hit:
            _say(f"  MAPPED  {function:<18} -> {hit}")
        else:
            gaps.append(function)
            _say(f"  GAP     {function:<18} -> none found "
                 f"(looked for: {', '.join(names)})")
    _say("\nvendor the machine only (tools/wall + process docs + theme; "
         "your documents stay the documents of record, and your decision "
         "log stays YOURS — the kit's own rulings are read upstream):")
    for prefix, exclude in (("tools/wall", ()), ("docs", ("decisions",)),
                            ("frontend/theme", ())):
        _copy_tree(KIT_ROOT / prefix, repo / prefix, apply, exclude=exclude)
    example = (KIT_ROOT / "tools" / "wall" / "config" /
               "wall.example.json").read_text(encoding="utf-8")
    _write(repo / ".wall" / "config" / "wall.json", example, apply,
           ".wall/config/wall.json")
    _stamp(repo, apply)
    if a.mcp:
        _say("\nengineer interface configs:")
        emit_mcp_configs(repo, a.mcp, apply)
    if gaps:
        _say(f"\ngaps to fill from templates/ ({len(gaps)}): "
             + ", ".join(gaps))
    _next_steps(repo, "adopt")
    return 0


def cmd_upgrade(a) -> int:
    repo = Path(a.into).resolve()
    apply = a.apply
    _say(f"upgrade {repo} from kit at {KIT_ROOT}  "
         f"({'APPLYING' if apply else 'dry run'})")
    stamp_path = repo / ".wall" / "config" / "kit_source.json"
    old_commit = "unknown"
    if stamp_path.exists():
        try:
            old_commit = json.loads(
                stamp_path.read_text(encoding="utf-8")).get(
                    "kit_commit", "unknown")
        except json.JSONDecodeError:
            pass
    new_commit = _kit_stamp()["kit_commit"]
    _say(f"  stamped source: {old_commit[:12]}  ->  this kit: {new_commit[:12]}")
    _say("  read the delta as DECISIONS first: docs/decisions/index.md "
         "in the kit — a new DEC can bind you where no vendored file "
         "changed (README: Upgrading an adoption).")
    if old_commit not in ("unknown", "") and new_commit != "unknown":
        try:
            log = subprocess.run(
                ["git", "-C", str(KIT_ROOT), "log", "--oneline",
                 f"{old_commit}..{new_commit}"],
                capture_output=True, text=True, timeout=10).stdout.strip()
            if log:
                _say("  upstream commits since the stamp:")
                for line in log.splitlines()[:20]:
                    _say(f"    {line}")
        except (OSError, subprocess.SubprocessError):
            pass
    _say("\nre-vendor verbatim (host config and host documents untouched):")
    changed = 0
    for prefix in VENDORED:
        src = KIT_ROOT / prefix
        if (repo / prefix).exists() or prefix in ("tools/wall",):
            changed += _copy_tree(src, repo / prefix, apply)
    if changed == 0:
        _say("  nothing to change — already at this kit")
    _stamp(repo, apply)
    _say("\nthen: run YOUR pins first, the kit's second; one PR per "
         "upgrade, citing the kit commit range above.")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="wall-bootstrap",
                                description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    for name, fn, help_ in (
            ("fresh", cmd_fresh, "empty-repo runbook, automated"),
            ("adopt", cmd_adopt, "existing-repo inventory + machine vendor"),
            ("upgrade", cmd_upgrade, "re-vendor a newer kit, verbatim")):
        s = sub.add_parser(name, help=help_)
        s.add_argument("--into", required=True,
                       help="the product repository root")
        s.add_argument("--apply", action="store_true",
                       help="do it (default is a dry run that prints "
                            "exactly what would happen)")
        s.add_argument("--mcp", nargs="*", choices=sorted(MCP_CONFIGS),
                       default=[],
                       help="also write these clients' MCP configs "
                            "(--role engineer)")
        s.set_defaults(fn=fn)
    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
