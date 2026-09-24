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
           existing file), generate CLAUDE.md from the AGENTS.md master
           (context_sync.py), stamp the kit source for later upgrades, and
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

  remove   the uninstall (DEC-0022): un-vendor the machine, strip the
           wall's MCP entries and .gitignore block; the ledger survives.

Every mode also MERGES BY ADDING the agent roster (`.claude/`: MAESTRO.md,
agents/, skills/, hooks/ — never `.claude/settings*.json`) and the
versioned git hooks (`tools/git-hooks/`; installing them stays opt-in via
its install.sh): a missing file is added, a host file that differs is
never overwritten and is reported as a COLLISION — a role-name collision
is a decision the host records. The kit's required `.gitignore` lines
(docs/WALL_STANDARDS.md section 2) go in one marked block that upgrade
refreshes and remove strips.

The stamp (.wall/config/kit_source.json) carries a per-file MANIFEST:
the sha256 of every file bootstrap wrote or owns. A kit file whose bytes
no longer match its record is LOCALLY MODIFIED, and upgrade and remove
refuse to overwrite, prune or delete it — they name it and exit 1 —
unless `--force` is said. A file with no record (a stamp written before
the manifest existed) counts as unmodified only when it is byte-identical
to this kit's copy or to the kit's own blob at the stamped commit;
anything else is UNVERIFIABLE and needs `--force` the same way.

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
import contextlib
import filecmp
import fnmatch
import hashlib
import json
import re
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

#: The subset of VENDORED that carries NOTHING of the host's: an upgrade
#: may prune here (a file the kit dropped must not survive as a stale
#: half-upgrade) and a remove deletes exactly these trees. docs/ is
#: copy-only both ways — it mixes host documents, the decision log above
#: all. templates/ is deliberately NOT here: it is a generic root name
#: (Flask/Django hosts keep their web views there), so the kit owns it
#: FILE-BY-FILE — never prune it, and remove deletes only the filenames
#: the kit itself vendored (host-review finding, Gemini).
KIT_OWNED_PREFIXES = ("tools/wall", "frontend/theme")

#: Trees merged BY ADDING in every mode: the agent roster and the
#: versioned git hooks. A host file that differs is never overwritten
#: (reported as a collision, even under --force), and remove deletes only
#: the files the manifest says bootstrap added, and only unmodified.
MERGED = (".claude", "tools/git-hooks")

#: Never copied from the kit's .claude/: settings files are the host's
#: harness configuration (permissions, hooks wiring), not the roster.
NEVER_COPIED = ("settings*.json",)

#: The kit's required ignores (docs/WALL_STANDARDS.md section 2), kept in
#: one marked block so upgrade can refresh it and remove can strip it
#: without touching a host line.
GITIGNORE_LINES = (".wall/derived/", ".wall/events/", ".wall/logs/",
                   ".wall/runs/", ".wall/registry/*.lock")
GITIGNORE_BEGIN = ("# >>> wall kit: required ignores (managed by "
                   "tools/wall/bootstrap.py; edit outside this block) >>>")
GITIGNORE_END = "# <<< wall kit <<<"
_GITIGNORE_BLOCK = re.compile(
    rf"^{re.escape(GITIGNORE_BEGIN)}[ \t]*\n.*?^{re.escape(GITIGNORE_END)}"
    rf"[ \t]*(?:\n|\Z)", re.S | re.M)

STAMP_REL = ".wall/config/kit_source.json"

#: Context documents `fresh` materializes at the product root — only
#: where the target does not already exist.
TEMPLATE_TARGETS = {
    "AGENTS.md.template": "AGENTS.md",
    "RULES.md.template": "RULES.md",
    "FAILURE_PATTERNS.md.template": "FAILURE_PATTERNS.md",
    "KNOWN_ISSUES.md.template": "KNOWN_ISSUES.md",
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
    "entry point": ("AGENTS.md", "CLAUDE.md", "README.md"),
    "standing rules": ("RULES.md", "STANDING_RULES.md", "CONTRIBUTING.md"),
    "failure registry": ("FAILURE_PATTERNS.md", "KNOWN_FAILURE_PATTERNS.md"),
    "known-issues intake": ("KNOWN_ISSUES.md", "docs/KNOWN_ISSUES.md"),
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
            "vendored": list(VENDORED), "merged": list(MERGED)}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_blob_id(path: Path) -> str:
    """The id git gives these bytes (`git hash-object`), so a file can be
    compared with the kit's blob at a stamped commit without checkout."""
    data = path.read_bytes()
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def _git_ls_tree(commit: str) -> dict[str, str]:
    """path -> blob id for every file in the KIT at `commit`; empty when
    git or the commit is unavailable (then nothing verifies this way)."""
    if commit in ("", "unknown"):
        return {}
    try:
        out = subprocess.run(
            ["git", "-C", str(KIT_ROOT), "ls-tree", "-r", "--full-tree",
             commit], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return {}
    blobs: dict[str, str] = {}
    if out.returncode != 0:
        return blobs
    for line in out.stdout.splitlines():
        meta, _, path = line.partition("\t")
        parts = meta.split()
        if len(parts) == 3 and parts[1] == "blob":
            blobs[path] = parts[2]
    return blobs


def _never_copied(rel: str) -> bool:
    """`.claude/settings*.json` is the host's harness config — never the
    kit's to write, at any depth under .claude/."""
    return rel.startswith(".claude/") and any(
        fnmatch.fnmatch(rel.rsplit("/", 1)[-1], pat) for pat in NEVER_COPIED)


def _kit_files(prefix: str, exclude: tuple[str, ...] = ()) -> list[str]:
    """Repo-relative POSIX paths of the kit's files under `prefix`.
    `exclude` names first segments below the prefix to skip (adopt keeps
    the HOST's decision log the host's)."""
    src = KIT_ROOT / prefix
    if not src.is_dir():
        return []
    files = []
    for path in sorted(src.rglob("*")):
        if path.is_dir() or "__pycache__" in path.parts:
            continue
        sub = path.relative_to(src)
        if sub.parts and sub.parts[0] in exclude:
            continue
        rel = f"{prefix}/{sub.as_posix()}"
        if not _never_copied(rel):
            files.append(rel)
    return files


def _read_stamp(repo: Path) -> dict:
    path = repo / STAMP_REL
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


class Ledger:
    """The per-file manifest for one run: what the stamp recorded, what
    this run owns, and which kit files a destructive step must not touch.

    A file's status is 'unmodified' when its bytes match the recorded
    sha256, OR equal this kit's copy (nothing would be lost), OR equal the
    kit's blob at the stamped commit (the legacy fallback for a stamp that
    predates the manifest). A recorded file that matches none of these is
    'modified'; an unrecorded one is 'unverified'. Both need --force."""

    def __init__(self, repo: Path, stamp: dict):
        self.repo = repo
        files = stamp.get("files")
        self.recorded: dict[str, str] = (
            dict(files) if isinstance(files, dict) else {})
        self.legacy = bool(stamp) and not isinstance(files, dict)
        self.old_commit = str(stamp.get("kit_commit") or "unknown")
        self.owned: set[str] = set()    # re-hash these at stamp time
        self.dropped: set[str] = set()  # gone from the manifest
        self.blocked: list[tuple[str, str]] = []
        self._blobs: dict[str, str] | None = None

    def status(self, rel: str) -> str:
        disk, kit = self.repo / rel, KIT_ROOT / rel
        if kit.is_file() and filecmp.cmp(kit, disk, shallow=False):
            return "unmodified"
        rec = self.recorded.get(rel)
        if rec is not None:
            return "unmodified" if _sha256(disk) == rec else "modified"
        if self._blobs is None:
            self._blobs = _git_ls_tree(self.old_commit)
        blob = self._blobs.get(rel)
        if blob and blob == _git_blob_id(disk):
            return "unmodified"
        return "unverified"

    def guard(self, rel: str, strict: bool) -> None:
        """Record `rel` as blocked when a destructive step would lose
        local bytes. `strict` (upgrade, remove) also blocks what cannot
        be verified; fresh/adopt block only a recorded file that was
        edited, so a first install behaves exactly as before."""
        st = self.status(rel)
        if st == "modified" or (strict and st == "unverified"):
            self.blocked.append((rel, st))

    def manifest(self) -> dict[str, str]:
        """The manifest to stamp: prior records carried forward VERBATIM
        (so an untouched local edit is never laundered into the record),
        with the files this run owns re-hashed from disk."""
        out = {rel: h for rel, h in self.recorded.items()
               if rel not in self.dropped and (self.repo / rel).is_file()}
        for rel in self.owned:
            if (self.repo / rel).is_file():
                out[rel] = _sha256(self.repo / rel)
        return dict(sorted(out.items()))


def _refuse(ledger: Ledger, force: bool) -> bool:
    """Print the blocked files; True means stop with nothing changed."""
    if ledger.legacy:
        _say("\nnote: the stamp predates the per-file manifest (no hashes). "
             "A kit file counts as unmodified only when it matches this "
             "kit's copy or the kit's blob at the stamped commit "
             f"({ledger.old_commit[:12]}); anything else is UNVERIFIED.")
    if not ledger.blocked:
        return False
    _say("\nkit files with local bytes (never overwritten, pruned or "
         "deleted without --force):")
    for rel, st in ledger.blocked:
        _say(f"  {st.upper():<10} {rel}")
    if force:
        _say("  --force said: these are replaced or deleted like any other "
             "kit file")
        return False
    _say("refusing: nothing was changed. Upstream the edit and re-vendor, "
         "copy it aside, or re-run with --force to discard it.")
    return True


def _plan_copy(ledger: Ledger, prefix: str, *, merge: bool, strict: bool,
               exclude: tuple[str, ...] = ()) -> list[tuple[str, str]]:
    """Plan kit -> repo for one tree, printing a verdict per file that
    changes. Vendored trees are copied verbatim; MERGED trees only add, and
    a host file that differs is a COLLISION, never overwritten."""
    plan: list[tuple[str, str]] = []
    label_root = Path(prefix).name
    for rel in _kit_files(prefix, exclude):
        dst = ledger.repo / rel
        label = f"{label_root}/{rel[len(prefix) + 1:]}"
        if not dst.exists():
            _say(f"  add  {label}")
            plan.append(("add", rel))
            ledger.owned.add(rel)
            continue
        if filecmp.cmp(KIT_ROOT / rel, dst, shallow=False):
            if not merge or rel in ledger.recorded:
                ledger.owned.add(rel)
            continue
        if merge and rel not in ledger.recorded:
            _say(f"  COLLISION  {prefix}/{rel[len(prefix) + 1:]}  (the host's "
                 f"file differs and is kept; a role-name collision is a "
                 f"decision the host records in docs/decisions/)")
            continue
        ledger.guard(rel, strict)
        _say(f"  update  {label}")
        plan.append(("update", rel))
        ledger.owned.add(rel)
    return plan


def _plan_prune(ledger: Ledger, prefix: str, *,
                merge: bool) -> list[tuple[str, str]]:
    """VERBATIM includes subtraction where the tree is the kit's: a file
    the kit dropped must not survive as a stale half-upgrade. In a MERGED
    tree only the files the manifest says bootstrap added qualify."""
    dst = ledger.repo / prefix
    if not dst.is_dir():
        return []
    kitset = set(_kit_files(prefix))
    plan: list[tuple[str, str]] = []
    for f in sorted(p for p in dst.rglob("*") if p.is_file()):
        if "__pycache__" in f.parts:
            continue
        rel = f.relative_to(ledger.repo).as_posix()
        if rel in kitset or (merge and rel not in ledger.recorded):
            continue
        ledger.guard(rel, strict=True)
        _say(f"  remove  {rel}  (no longer in the kit)")
        plan.append(("remove", rel))
    return plan


def _execute(ledger: Ledger, plan: list[tuple[str, str]],
             apply: bool) -> None:
    if not apply:
        return
    for op, rel in plan:
        dst = ledger.repo / rel
        if op == "remove":
            dst.unlink(missing_ok=True)
            ledger.dropped.add(rel)
            ledger.owned.discard(rel)
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(KIT_ROOT / rel, dst)


def gitignore_block() -> str:
    return "\n".join((GITIGNORE_BEGIN, *GITIGNORE_LINES, GITIGNORE_END)) + "\n"


def _newline_of(path: Path) -> str:
    """The host file's line ending, so a rewrite never restyles its lines:
    read_text() folds CRLF to LF, and write_text() would write the
    platform's ending back over every host line."""
    return "\r\n" if path.is_file() and b"\r\n" in path.read_bytes() else "\n"


def ensure_gitignore(repo: Path, apply: bool) -> bool:
    """Idempotently put the kit's required ignores in the host's
    .gitignore, inside the marked block; a stale block is refreshed in
    place, host lines are never touched. Returns whether it changed."""
    path = repo / ".gitignore"
    nl = _newline_of(path)
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    block = gitignore_block()
    if _GITIGNORE_BLOCK.search(text):
        new = _GITIGNORE_BLOCK.sub(lambda _m: block, text, count=1)
        verb = "refresh"
    else:
        # one blank line sets the block apart from the host's lines
        sep = "" if not text else ("\n" if text.endswith("\n") else "\n\n")
        new = text + sep + block
        verb = "append"
    if new == text:
        _say("  keep    .gitignore  (wall kit block current)")
        return False
    _say(f"  {verb:<7} .gitignore  (wall kit block: "
         f"{', '.join(GITIGNORE_LINES)})")
    if apply:
        path.write_text(new, encoding="utf-8", newline=nl)
    return True


def strip_gitignore(repo: Path, apply: bool) -> None:
    """Remove exactly the marked block (and the blank line that set it
    apart); a .gitignore that held only the block goes with it."""
    path = repo / ".gitignore"
    if not path.is_file():
        return
    nl = _newline_of(path)
    text = path.read_text(encoding="utf-8")
    m = _GITIGNORE_BLOCK.search(text)
    if not m:
        return
    head, tail = text[:m.start()], text[m.end():]
    if head.endswith("\n\n"):  # the blank line the append put before it
        head = head[:-1]
    new = head + tail
    if new.strip():
        _say("  strip   .gitignore  (wall kit block only; host lines kept)")
        if apply:
            path.write_text(new, encoding="utf-8", newline=nl)
    else:
        _say("  remove  .gitignore  (held only the wall kit block)")
        if apply:
            path.unlink()


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
    # sys.executable, not a spelled name: these configs are generated ON
    # the machine that will run them, and the one interpreter preflight
    # actually validated is the one running this script — "python3" does
    # not exist on a stock Windows install (host-review finding).
    server = {"command": sys.executable,
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


def _stamp(repo: Path, apply: bool, ledger: Ledger) -> None:
    stamp = _kit_stamp()
    path = repo / STAMP_REL
    _say(f"  stamp  {STAMP_REL}  (kit {stamp['kit_commit'][:12]}; "
         f"sha256 manifest of every kit file bootstrap wrote or owns)")
    if apply:
        stamp["files"] = ledger.manifest()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(stamp, indent=2) + "\n", encoding="utf-8")


def _plan_merged(ledger: Ledger, strict: bool) -> list[tuple[str, str]]:
    _say("\nagent roster + git hooks (merge by adding; a host file is never "
         "overwritten, .claude/settings*.json never copied; installing the "
         "hooks stays opt-in: tools/git-hooks/install.sh):")
    plan: list[tuple[str, str]] = []
    for prefix in MERGED:
        plan += _plan_copy(ledger, prefix, merge=True, strict=strict)
    return plan


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


def _context():
    """The context-file sync (context_sync.py), imported lazily: it
    imports this module for KIT_OWNED_PREFIXES, so a top-level import
    here would be circular."""
    sys.path.insert(0, str(Path(__file__).parent))
    import context_sync
    return context_sync


def _unmastered(repo: Path) -> list[str]:
    """Hand-written tool files (a CLAUDE.md nobody generated) with no
    AGENTS.md beside them: the entry point exists, under a tool's name."""
    cs = _context()
    try:
        entries = cs.scan(repo)
    except cs.ConfigError:
        return []
    return [e.target for e in entries if e.status == "handwritten"
            and not (repo / e.master).exists()]


def _context_copies(repo: Path, apply: bool, pending: bool = False) -> int:
    """Generate the tool copies from every AGENTS.md (context_sync).
    Hand-written files are reported, never overwritten. `pending` is a
    dry run's AGENTS.md that --apply would write. Returns files written."""
    cs = _context()
    if pending and not apply:
        for target in cs.DEFAULT_TARGETS:
            _say(f"  write   {target}  <- {cs.MASTER}  (generated)")
        return 0
    try:
        res = cs.sync(repo, apply=apply)
    except cs.ConfigError as e:
        _say(f"  skip    context copies: {e}")
        return 0
    for line in res.lines:
        _say(line)
    return res.written


def preflight() -> list[str]:
    """Verify the dependencies the kit actually has (DEC-0022): the kit
    bundles nothing on purpose (DEC-0017 — stdlib only), so 'dependencies
    included' honestly means VERIFIED AND NAMED here, in every install and
    upgrade, rather than silently assumed. Returns the list of problems;
    empty means go."""
    problems: list[str] = []
    _say("preflight — what the kit needs on this machine:")
    py = sys.version_info
    if py < (3, 11):
        problems.append(f"Python {py.major}.{py.minor} < 3.11")
        _say(f"  FAIL  python {py.major}.{py.minor}  (need 3.11+ — StrEnum, "
             f"tomllib; install from python.org or your package manager)")
    else:
        _say(f"  ok    python {py.major}.{py.minor}.{py.micro}")
    try:
        gitv = subprocess.run(["git", "--version"], capture_output=True,
                              text=True, timeout=10).stdout.strip()
        _say(f"  ok    {gitv}  (stamping, `wall ship`, upgrades' delta log)")
    except (OSError, subprocess.SubprocessError):
        # A warning, not a blocker: the stamp degrades to 'unknown'
        # honestly and everything else runs. Only a too-old Python — the
        # one dependency nothing can degrade around — stops an --apply.
        _say("  WARN  git not found — kit_source stamps read 'unknown', "
             "`wall ship` and upgrade deltas need it (git-scm.com)")
    _say("  note  everything else is stdlib — no pip installs, ever "
         "(DEC-0017). Optional surfaces bring their own host: an MCP "
         "editor for the engineer seat, a browser for the wall, a "
         "scheduler for the timer (wall install names each platform's).")
    return problems


# ----------------------------------------------------------------- modes

def cmd_fresh(a) -> int:
    repo = Path(a.into).resolve()
    apply = a.apply
    _say(f"fresh bootstrap into {repo}  "
         f"({'APPLYING' if apply else 'dry run — pass --apply to do it'})")
    if repo == KIT_ROOT:
        _say("refusing: --into is the kit checkout itself")
        return 2
    ledger = Ledger(repo, _read_stamp(repo))
    _say("\nvendor the side-repo subtree (DEC-0021):")
    plan: list[tuple[str, str]] = []
    for prefix in VENDORED:
        plan += _plan_copy(ledger, prefix, merge=False, strict=False)
    plan += _plan_merged(ledger, strict=False)
    if _refuse(ledger, a.force):
        return 1
    _execute(ledger, plan, apply)
    _say("\ncontext documents (missing ones only):")
    unmastered = [t for t in _unmastered(repo) if "/" not in t]
    for template, target in TEMPLATE_TARGETS.items():
        if target == "AGENTS.md" and unmastered:
            _say(f"  skip   AGENTS.md  ({', '.join(unmastered)} is "
                 f"hand-written here; make it the master with: python "
                 f"tools/wall/context_sync.py sync --adopt)")
            continue
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
    ensure_gitignore(repo, apply)
    _say("\nagent context copies (generated from AGENTS.md, "
         "docs/CONTEXT_FILES.md):")
    _context_copies(repo, apply, pending=not unmastered
                    and not (repo / "AGENTS.md").exists())
    _stamp(repo, apply, ledger)
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
    for target in _unmastered(repo):
        _say(f"  NOTE    {target} is hand-written with no AGENTS.md master "
             f"beside it; to make it one (tool-agnostic, generated copies): "
             f"python tools/wall/context_sync.py sync --adopt")
    ledger = Ledger(repo, _read_stamp(repo))
    _say("\nvendor the machine only (tools/wall + process docs + theme; "
         "your documents stay the documents of record, and your decision "
         "log stays YOURS — the kit's own rulings are read upstream):")
    plan: list[tuple[str, str]] = []
    for prefix, exclude in (("tools/wall", ()), ("docs", ("decisions",)),
                            ("frontend/theme", ())):
        plan += _plan_copy(ledger, prefix, merge=False, strict=False,
                           exclude=exclude)
    plan += _plan_merged(ledger, strict=False)
    if _refuse(ledger, a.force):
        return 1
    _execute(ledger, plan, apply)
    example = (KIT_ROOT / "tools" / "wall" / "config" /
               "wall.example.json").read_text(encoding="utf-8")
    _say("\nwall state:")
    _write(repo / ".wall" / "config" / "wall.json", example, apply,
           ".wall/config/wall.json")
    ensure_gitignore(repo, apply)
    _stamp(repo, apply, ledger)
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
    ledger = Ledger(repo, _read_stamp(repo))
    old_commit = ledger.old_commit
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
    _say("\nre-vendor verbatim (host config and host documents untouched; "
         "a locally modified kit file is refused without --force):")
    plan: list[tuple[str, str]] = []
    for prefix in VENDORED:
        if (repo / prefix).exists() or prefix in ("tools/wall",):
            plan += _plan_copy(ledger, prefix, merge=False, strict=True)
    # VERBATIM means subtraction too — but only where the tree is wholly
    # kit-owned: a file the kit dropped or renamed must not survive as a
    # stale half-upgrade (host-review finding). docs/ and templates/ stay
    # copy-only; in a MERGED tree only a file bootstrap added qualifies.
    for prefix in KIT_OWNED_PREFIXES:
        plan += _plan_prune(ledger, prefix, merge=False)
    merged = _plan_merged(ledger, strict=True)
    for prefix in MERGED:
        merged += _plan_prune(ledger, prefix, merge=True)
    plan += merged
    if _refuse(ledger, a.force):
        return 1
    _execute(ledger, plan, apply)
    changed = len(plan)
    _say("\n.gitignore:")
    changed += ensure_gitignore(repo, apply)
    _say("\nagent context copies (regenerable; hand-written files are "
         "never touched):")
    changed += _context_copies(repo, apply)
    if changed == 0:
        _say("  nothing to change — already at this kit")
    _stamp(repo, apply, ledger)
    _say("\nthen: run YOUR pins first, the kit's second; one PR per "
         "upgrade, citing the kit commit range above.")
    return 0


def _timer_registration(repo: Path) -> str | None:
    """The machine registry's row for this repo, if the DEC-0010 timer's
    sweeper still knows it. Read through the sibling service module so
    the WALL_HOME override and the registry shape stay single-sourced;
    an unreadable registry is not ours to rule on (returns None)."""
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        import service
        rows = service.read_registry().get("repos") or []
        for row in rows:
            if Path(row.get("path", "")) == repo:
                return str(service.registry_path())
    except Exception:
        return None
    return None


def _plan_remove(ledger: Ledger) -> tuple[list[str], list[str]]:
    """What a remove deletes: (whole kit-owned trees, single files).
    Every file on the way is guarded — a locally modified or unverifiable
    kit file blocks the remove unless --force. In a MERGED tree only the
    files the manifest says bootstrap added are candidates: a host-authored
    file is never deleted, --force or not."""
    repo = ledger.repo
    trees: list[str] = []
    files: list[str] = []
    for prefix in KIT_OWNED_PREFIXES:
        target = repo / prefix
        if not target.exists():
            continue
        trees.append(prefix)
        _say(f"  remove  {prefix}/")
        for f in sorted(p for p in target.rglob("*") if p.is_file()):
            if "__pycache__" not in f.parts:
                ledger.guard(f.relative_to(repo).as_posix(), strict=True)
    # templates/ is a generic host directory name (a Flask/Django app's
    # web views live there), so it is owned FILE-BY-FILE: delete exactly
    # the filenames the kit vendored, keep anything else, and drop the
    # directory only when that leaves it empty.
    for rel in _kit_files("templates"):
        if (repo / rel).is_file():
            _say(f"  remove  {rel}")
            ledger.guard(rel, strict=True)
            files.append(rel)
    for prefix in MERGED:
        for rel in sorted(r for r in ledger.recorded
                          if r.startswith(prefix + "/")):
            if (repo / rel).is_file():
                _say(f"  remove  {rel}  (added by bootstrap)")
                ledger.guard(rel, strict=True)
                files.append(rel)
    return trees, files


def _prune_empty_dirs(repo: Path, rels: list[str]) -> None:
    """Drop directories a remove emptied, bottom-up, never the repo root
    and never a directory that still holds anything of the host's."""
    dirs = {p for rel in rels for p in (repo / rel).parents
            if p != repo and repo in p.parents}
    for d in sorted(dirs, key=lambda p: len(p.parts), reverse=True):
        if d.is_dir() and not any(d.iterdir()):
            d.rmdir()


def cmd_remove(a) -> int:
    """Uninstall (DEC-0022): the reverse of fresh/adopt, with the audit
    record protected by default. Removes the vendored machine and strips
    the wall's MCP entry; the LEDGER (.wall/) survives unless --purge-state
    is said explicitly — an audit trail deleted by default is not an audit
    trail. Context documents and the host's decision log are NEVER touched:
    by uninstall time they are the host's documents, whoever seeded them.
    A kit file with local edits is never deleted without --force."""
    repo = Path(a.into).resolve()
    apply = a.apply
    _say(f"remove the kit from {repo}  "
         f"({'APPLYING' if apply else 'dry run — pass --apply to do it'})")
    if repo == KIT_ROOT:
        _say("refusing: --into is the kit checkout itself")
        return 2
    still = _timer_registration(repo)
    if still:
        _say(f"\nmachine timer: this repo is STILL registered ({still}).")
        _say("  run `python tools/wall/wall.py uninstall` first — the "
             "uninstall needs the adapter code this remove would delete "
             "(DEC-0022 clause 3 / DEC-0010 consent discipline).")
        if apply:
            _say("refusing --apply until the timer registration is gone.")
            return 2
    stamp = _read_stamp(repo)
    ledger = Ledger(repo, stamp)
    _say("\nun-vendor the machine:")
    trees, files = _plan_remove(ledger)
    if _refuse(ledger, a.force):
        return 1
    if apply:
        for prefix in trees:
            shutil.rmtree(repo / prefix)
        for rel in files:
            (repo / rel).unlink(missing_ok=True)
        _prune_empty_dirs(repo, files)
    for prefix, why in (("templates", "host files present — not the "
                         "kit's to delete"),
                        *((m, "host-authored files — never the kit's to "
                           "delete") for m in MERGED)):
        if (repo / prefix).is_dir() and any(
                p.is_file() and p.relative_to(repo).as_posix() not in files
                for p in (repo / prefix).rglob("*")):
            _say(f"  keep    {prefix}/  ({why})")
    _say("  keep    docs/  (process corpus may be cited by YOUR documents; "
         "delete deliberately, not by script)")
    # ValueError covers context_sync.ConfigError: a bad wall.json must
    # not stop an uninstall, and the copies stay either way.
    with contextlib.suppress(ValueError, OSError):
        for e in _context().scan(repo):
            if e.status in ("ok", "stale", "edited", "orphan") and not (
                    repo / e.target).is_symlink():
                _say(f"  keep    {e.target}  (generated from {e.master}; its "
                     f"banner names tools/wall/context_sync.py, which this "
                     f"remove deletes -- keep, edit or delete it "
                     f"deliberately)")
    strip_gitignore(repo, apply)
    clients = a.mcp or sorted(MCP_CONFIGS)
    _say(f"\nengineer interface entries (only the wall's own; "
         f"{', '.join(clients)}):")
    for client in clients:
        rel, key = MCP_CONFIGS[client]
        path = repo / rel
        if not path.exists():
            continue
        try:
            cfg = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            _say(f"  skip    {rel}  (not valid JSON — not ours to touch)")
            continue
        servers = cfg.get(key) or {}
        if "wall" not in servers:
            continue
        others = {k: v for k, v in servers.items() if k != "wall"}
        if others:
            _say(f"  strip   {rel}  (wall entry only; "
                 f"{len(others)} other server(s) kept)")
            if apply:
                cfg[key] = others
                path.write_text(json.dumps(cfg, indent=2) + "\n",
                                encoding="utf-8")
        else:
            _say(f"  remove  {rel}  (held only the wall)")
            if apply:
                path.unlink()
    _say("\nstate and audit record:")
    wall_dir = repo / ".wall"
    if a.purge_state:
        _say("  PURGE   .wall/  (--purge-state said: the event ledger, "
             "config and registry go — this is the audit trail, and it "
             "does not come back)")
        if apply and wall_dir.exists():
            shutil.rmtree(wall_dir)
    else:
        _say("  keep    .wall/  (the LEDGER is the audit record; pass "
             "--purge-state to delete it too)")
        if apply and stamp:
            # the manifest now names only what is still on disk (docs/)
            stamp["files"] = ledger.manifest()
            (repo / STAMP_REL).write_text(json.dumps(stamp, indent=2) + "\n",
                                          encoding="utf-8")
    _say("\nstill yours to do, because a script must not (DEC-0010):")
    _say("  - the machine timer: `wall uninstall` BEFORE removing "
         "tools/wall (it needs the adapter code), or your platform's "
         "scheduler UI after")
    _say("  - context documents (AGENTS.md, RULES.md, ...) and docs/: "
         "they are your documents now — keep, edit or delete them "
         "deliberately")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="wall-bootstrap",
                                description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    for name, fn, help_ in (
            ("fresh", cmd_fresh, "empty-repo runbook, automated"),
            ("adopt", cmd_adopt, "existing-repo inventory + machine vendor"),
            ("upgrade", cmd_upgrade, "re-vendor a newer kit, verbatim"),
            ("remove", cmd_remove, "uninstall; the ledger survives unless "
                                   "--purge-state")):
        s = sub.add_parser(name, help=help_)
        s.add_argument("--into", required=True,
                       help="the product repository root")
        s.add_argument("--apply", action="store_true",
                       help="do it (default is a dry run that prints "
                            "exactly what would happen)")
        s.add_argument("--mcp", nargs="*", choices=sorted(MCP_CONFIGS),
                       default=[],
                       help=("strip only these clients' wall entries "
                             "(default: all three)") if name == "remove"
                       else "also write these clients' MCP configs "
                            "(--role engineer)")
        s.add_argument("--force", action="store_true",
                       help="replace or delete kit files that carry local "
                            "edits (or cannot be verified against the "
                            "stamp's manifest); never a host-authored "
                            ".claude/ or tools/git-hooks/ file")
        if name == "remove":
            s.add_argument("--purge-state", action="store_true",
                           help="also delete .wall/ — the event ledger is "
                                "the audit record, so this is never implied")
        s.set_defaults(fn=fn)
    a = p.parse_args(argv)
    problems = preflight()
    # Remove runs the same checks but never stops on them: an uninstall
    # needs nothing the checks guard (no stamp to compute, no code to
    # run from the vendored tree), and a machine too old to install on
    # must still be able to take the kit OUT.
    if problems and a.apply and a.cmd != "remove":
        _say(f"\npreflight failed ({'; '.join(problems)}) — fix the "
             f"named dependencies, then re-run")
        return 2
    if problems and a.cmd == "remove":
        _say(f"  note  remove proceeds anyway ({'; '.join(problems)}): "
             f"taking the kit out needs none of it")
    _say("")
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
