#!/usr/bin/env python3
"""context_sync -- one tool-agnostic master, generated tool copies.

Every `AGENTS.md` in the repository (the root one and any nested one
beside the code it describes) is the MASTER for its directory. The
tool-specific names agents actually load -- `CLAUDE.md`, `GEMINI.md`,
`.github/copilot-instructions.md`, `.cursor/rules/agents.mdc` -- are
GENERATED copies: a one-line banner (what generated it, from where, do
not edit, and the sha256 of the body it carries) followed by the
master's body. docs/CONTEXT_FILES.md is the strategy; this is the tool.

  sync   write missing copies and refresh stale ones. A target that
         exists WITHOUT the banner is hand-written and is never
         overwritten: it is reported and the run exits 1. `--adopt`
         moves a hand-written copy's content into a new AGENTS.md, only
         where no AGENTS.md exists yet. `--symlink` (opt-in) links
         instead of copying; where that cannot work it copies and says
         so. A second run writes nothing.
  check  exit 0 when every copy matches its master, 1 naming each
         missing / stale / edited / hand-written / orphaned copy.

Drift is detectable from the copy alone: the banner's hash is the hash
of the body that was copied, so a copy whose body no longer hashes to
its own banner was edited; one whose banner hash differs from the
current master's is stale. Files are written LF and compared
normalized, so a CRLF checkout does not make `check` flap.

Config: `.wall/config/wall.json` key `context.targets`, a list of the
target names above; a missing key means `["CLAUDE.md"]`. `CLAUDE.md`
and `GEMINI.md` are written beside every master; the two paths under
`.github/` and `.cursor/` are root-only.

Exit codes: 0 clean, 1 a finding (drift, refusal), 2 a usage error.
Stdlib only (DEC-0017).
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from bootstrap import KIT_OWNED_PREFIXES  # noqa: E402

MASTER = "AGENTS.md"
TOOL = "tools/wall/context_sync.py"
SYNC_COMMAND = f"python {TOOL} sync"

#: Target name -> True when it is written at the repository root only.
TARGET_KINDS: dict[str, bool] = {
    "CLAUDE.md": False,
    "GEMINI.md": False,
    ".github/copilot-instructions.md": True,
    ".cursor/rules/agents.mdc": True,
}
DEFAULT_TARGETS = ("CLAUDE.md",)
CURSOR_TARGET = ".cursor/rules/agents.mdc"
CURSOR_FRONTMATTER = ("---\n"
                      "description: Project instructions for AI agents, "
                      "generated from AGENTS.md\n"
                      "alwaysApply: true\n"
                      "---\n")

BANNER_PREFIX = "<!-- GENERATED from "
HASH_KEY = "master-sha256: "

#: Directory names never searched for masters: VCS, dependency and cache
#: trees. Dot-directories are skipped as a class; the kit's wholly
#: kit-owned subtrees (bootstrap.KIT_OWNED_PREFIXES) are skipped by path.
SKIP_DIRS = frozenset({"node_modules", "__pycache__", "venv", "env",
                       "site-packages", "dist-packages"})


class ConfigError(ValueError):
    """`context.targets` names something this tool cannot write."""


def normalize(text: str) -> str:
    """LF line endings, no byte-order mark: the form that is hashed,
    written and compared, whatever the checkout did to the bytes."""
    return text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")


def read(path: Path) -> str:
    """A file's text, normalized here and nowhere else: bytes decoded
    as-is (no universal-newline translation), so the one normalization
    is the one that is tested."""
    return normalize(path.read_bytes().decode("utf-8"))


def body_hash(body: str) -> str:
    return hashlib.sha256(normalize(body).encode("utf-8")).hexdigest()


def banner(master_rel: str, digest: str) -> str:
    return (f"{BANNER_PREFIX}{master_rel} by {TOOL} -- do not edit this "
            f"copy. Edit {master_rel} and run: {SYNC_COMMAND} -- "
            f"{HASH_KEY}{digest} -->")


def render(target: str, master_rel: str, master_text: str) -> str:
    """The exact bytes (as str) a generated copy holds."""
    body = normalize(master_text)
    out = banner(master_rel, body_hash(body)) + "\n" + body
    if target == CURSOR_TARGET:
        out = CURSOR_FRONTMATTER + out
    return out


def split_generated(target: str, text: str) -> tuple[str, str] | None:
    """(banner hash, body) of a generated copy, or None when the file
    carries no banner where this tool puts one -- i.e. hand-written."""
    text = normalize(text)
    if target == CURSOR_TARGET:
        if not text.startswith(CURSOR_FRONTMATTER):
            return None
        text = text[len(CURSOR_FRONTMATTER):]
    first, _, body = text.partition("\n")
    if not (first.startswith(BANNER_PREFIX) and HASH_KEY in first):
        return None
    digest = first.split(HASH_KEY, 1)[1].split(" ", 1)[0]
    return digest, body


def load_targets(repo: Path) -> list[str]:
    """`context.targets` from .wall/config/wall.json; a missing file or
    key is the default, never an error. An unknown name is an error --
    silently skipping it would leave a tool reading nothing."""
    cfg_path = repo / ".wall" / "config" / "wall.json"
    targets: list[str] = list(DEFAULT_TARGETS)
    if cfg_path.exists():
        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise ConfigError(f"{cfg_path}: not valid JSON ({e})") from e
        ctx = cfg.get("context") if isinstance(cfg, dict) else None
        if isinstance(ctx, dict) and "targets" in ctx:
            raw = ctx["targets"]
            if not isinstance(raw, list) or not all(
                    isinstance(t, str) for t in raw):
                raise ConfigError("context.targets must be a list of names")
            targets = raw
    unknown = [t for t in targets if t not in TARGET_KINDS]
    if unknown:
        raise ConfigError(f"context.targets: unknown {unknown}; supported: "
                          f"{sorted(TARGET_KINDS)}")
    return sorted(dict.fromkeys(targets))


def _skipped(rel: Path) -> bool:
    posix = rel.as_posix()
    return any(posix == p or posix.startswith(p + "/")
               for p in KIT_OWNED_PREFIXES)


def find_dirs(repo: Path, targets: list[str]) -> list[Path]:
    """Every directory (repo-relative) holding a master or a per-directory
    target file: the masters are the work, and a target with no master
    beside it is either an adoption candidate or an orphaned copy."""
    names = {MASTER} | {t for t in targets if not TARGET_KINDS[t]}
    found: set[Path] = {Path(".")}
    for dirpath, dirnames, filenames in os.walk(repo):
        rel = Path(dirpath).relative_to(repo)
        dirnames[:] = sorted(
            d for d in dirnames
            if not d.startswith(".") and d not in SKIP_DIRS
            and not _skipped(rel / d))
        if names & set(filenames):
            found.add(rel)
    return sorted(found, key=lambda p: p.as_posix())


@dataclass
class Entry:
    """One target's verdict. `status` is one of: ok, missing, stale,
    edited, handwritten, foreign, orphan, badmaster."""
    target: str          # repo-relative POSIX path of the copy
    master: str          # repo-relative POSIX path of its master
    status: str
    detail: str = ""


def _rel(p: Path) -> str:
    s = p.as_posix()
    return s[2:] if s.startswith("./") else s


def classify(repo: Path, d: Path, target: str) -> Entry | None:
    """Verdict for one target in directory `d`; None when there is
    nothing there and nothing should be (no master, no file)."""
    master_path = repo / d / MASTER
    tpath = repo / d / target
    master_rel = _rel(d / MASTER)
    trel = _rel(d / target)
    has_master = master_path.is_file()
    if has_master:
        try:
            read(master_path)
        except UnicodeDecodeError:
            return Entry(trel, master_rel, "badmaster",
                         f"{master_rel} is not UTF-8 text -- re-save it as "
                         f"UTF-8; no copy is written from it")
    if tpath.is_symlink():
        if has_master and os.path.realpath(tpath) == os.path.realpath(
                master_path) and target != CURSOR_TARGET:
            return Entry(trel, master_rel, "ok", "symlink to its master")
        return Entry(trel, master_rel, "foreign",
                     f"symlink to {os.readlink(tpath)}, not to {master_rel}")
    if not tpath.exists():
        return Entry(trel, master_rel, "missing") if has_master else None
    try:
        text = read(tpath)
    except UnicodeDecodeError:
        return Entry(trel, master_rel, "handwritten",
                     "not UTF-8 text -- never overwritten")
    parts = split_generated(target, text)
    if parts is None:
        return Entry(trel, master_rel, "handwritten",
                     "no generated banner -- never overwritten")
    digest, body = parts
    if body_hash(body) != digest:
        return Entry(trel, master_rel, "edited",
                     "body no longer matches its own banner hash")
    if not has_master:
        return Entry(trel, master_rel, "orphan",
                     f"generated, but {master_rel} is gone")
    master_text = read(master_path)
    if digest != body_hash(master_text):
        return Entry(trel, master_rel, "stale",
                     f"{master_rel} changed since this copy was generated")
    if normalize(text) != render(target, master_rel, master_text):
        return Entry(trel, master_rel, "edited",
                     "banner or frontmatter differs from the generated form")
    return Entry(trel, master_rel, "ok")


def scan(repo: Path, targets: list[str] | None = None) -> list[Entry]:
    repo = Path(repo)
    targets = load_targets(repo) if targets is None else targets
    entries: list[Entry] = []
    for d in find_dirs(repo, targets):
        for t in targets:
            if TARGET_KINDS[t] and d != Path("."):
                continue
            e = classify(repo, d, t)
            if e is not None:
                entries.append(e)
    return entries


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        path.unlink()
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def _link(repo: Path, e: Entry) -> str | None:
    """Create the relative symlink; returns why it fell back, or None."""
    tpath = repo / e.target
    if e.target.endswith(".mdc"):
        return "a Cursor rule needs frontmatter, so it is always a copy"
    if os.name == "nt":
        return "symlinks are unreliable on Windows checkouts"
    # Link inside a private staging directory this call creates (same
    # parent, so the move is a rename), then move the link over the target:
    # a failure anywhere leaves the existing copy where it was, and nothing
    # this call did not create is ever removed.
    staging = None
    try:
        tpath.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=".context-sync-",
                                        dir=tpath.parent))
        link = staging / tpath.name
        os.symlink(os.path.relpath(repo / e.master, tpath.parent), link)
        os.replace(link, tpath)
    except OSError as exc:
        return f"symlink failed ({exc.strerror or exc})"
    finally:
        if staging is not None:
            with contextlib.suppress(OSError):
                (staging / tpath.name).unlink()
            with contextlib.suppress(OSError):
                staging.rmdir()
    return None


@dataclass
class Result:
    lines: list[str]
    problems: int
    written: int

    @property
    def code(self) -> int:
        return 1 if self.problems else 0


def sync(repo: Path, *, adopt: bool = False, symlink: bool = False,
         apply: bool = True, targets: list[str] | None = None) -> Result:
    """Bring every copy in line with its master. Never overwrites a
    hand-written file; never deletes one. `apply=False` reports only."""
    repo = Path(repo)
    targets = load_targets(repo) if targets is None else targets
    lines: list[str] = []
    problems = written = 0
    adopted: set[str] = set()
    refused: set[str] = set()

    if adopt:
        by_master: dict[str, list[Entry]] = {}
        for e in scan(repo, targets):
            if e.status == "handwritten":
                by_master.setdefault(e.master, []).append(e)
        for master_rel, hand in sorted(by_master.items()):
            names = ", ".join(h.target for h in hand)
            if (repo / master_rel).exists():
                problems += 1
                refused.update(h.target for h in hand)
                lines.append(f"  REFUSE  {names}  --adopt only creates a "
                             f"master; {master_rel} exists. Merge the "
                             f"content into it by hand, delete the copy, "
                             f"re-run sync")
                continue
            if (len(hand) > 1 or hand[0].target.endswith(".mdc")
                    or hand[0].detail.startswith("not UTF-8")):
                problems += 1
                why = ("more than one hand-written candidate" if len(hand) > 1
                       else "a Cursor rule carries frontmatter"
                       if hand[0].target.endswith(".mdc") else "not UTF-8")
                refused.update(h.target for h in hand)
                lines.append(f"  REFUSE  {names}  cannot adopt ({why}); "
                             f"write {master_rel} by hand")
                continue
            lines.append(f"  adopt   {hand[0].target}  -> {master_rel}")
            written += 1
            adopted.add(hand[0].target)
            if apply:
                _write(repo / master_rel, read(repo / hand[0].target))
                (repo / hand[0].target).unlink()

    for e in scan(repo, targets):
        tpath = repo / e.target
        if e.target in refused:
            continue
        if e.target in adopted and not apply:
            written += 1
            lines.append(f"  write   {e.target}  <- {e.master}")
            continue
        if e.status == "ok":
            if symlink and not tpath.is_symlink() and apply:
                reason = _link(repo, e)
                if reason is None:
                    written += 1
                    lines.append(f"  link    {e.target}  -> {e.master}")
                else:
                    lines.append(f"  note    {e.target}: kept the copy, not "
                                 f"linking -- {reason}")
            continue
        if e.status in ("missing", "stale"):
            verb = "write" if e.status == "missing" else "refresh"
            written += 1
            if symlink and apply:
                reason = _link(repo, e)
                if reason is None:
                    lines.append(f"  link    {e.target}  -> {e.master}")
                    continue
                lines.append(f"  note    {e.target}: copying, not linking "
                             f"-- {reason}")
            lines.append(f"  {verb:<7} {e.target}  <- {e.master}")
            if apply:
                master_text = read(repo / e.master)
                _write(tpath, render(_kind(e.target), e.master,
                                     master_text))
            continue
        if e.status == "orphan":
            written += 1
            lines.append(f"  remove  {e.target}  (generated; {e.detail})")
            if apply:
                tpath.unlink()
            continue
        problems += 1
        adopt_hint = (f"merge it into {e.master} by hand, delete it, "
                      f"re-run sync" if (repo / e.master).exists() else
                      f"to make it the master: {SYNC_COMMAND} --adopt")
        advice = {
            "handwritten": f"hand-written; never overwritten -- {adopt_hint}",
            "edited": f"a generated copy was edited ({e.detail}). Move the "
                      f"edit into {e.master}, delete the copy, re-run sync",
            "foreign": f"{e.detail}; not ours to replace",
            "badmaster": e.detail,
        }[e.status]
        lines.append(f"  REFUSE  {e.target}  {advice}")
    return Result(lines, problems, written)


def _kind(target_rel: str) -> str:
    """The TARGET_KINDS key for a repo-relative target path."""
    for kind in TARGET_KINDS:
        if target_rel == kind or target_rel.endswith("/" + kind):
            return kind
    raise ConfigError(f"not a known target: {target_rel}")


def check(repo: Path, targets: list[str] | None = None) -> Result:
    lines: list[str] = []
    problems = 0
    for e in scan(Path(repo), targets):
        if e.status == "ok":
            continue
        problems += 1
        tail = f"  ({e.detail})" if e.detail else ""
        lines.append(f"  {e.status.upper():<11} {e.target}  <- "
                     f"{e.master}{tail}")
    return Result(lines, problems, 0)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="context_sync",
                                description=__doc__.split("\n")[0])
    p.add_argument("--repo", default=".", help="repository root")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sync", help="write missing and refresh stale copies")
    s.add_argument("--adopt", action="store_true",
                   help="move a hand-written copy into a NEW AGENTS.md")
    s.add_argument("--symlink", action="store_true",
                   help="relative symlinks instead of copies (POSIX teams)")
    s.add_argument("--dry-run", action="store_true",
                   help="report what sync would do; write nothing")
    sub.add_parser("check", help="exit 1 naming every copy out of sync")
    a = p.parse_args(argv)
    return run(Path(a.repo), a.cmd, adopt=getattr(a, "adopt", False),
               symlink=getattr(a, "symlink", False),
               dry_run=getattr(a, "dry_run", False))


def run(repo: Path, cmd: str, *, adopt: bool = False, symlink: bool = False,
        dry_run: bool = False) -> int:
    """The CLI body, shared with `wall context`."""
    repo = repo.resolve()
    try:
        if cmd == "check":
            res = check(repo)
            for line in res.lines:
                print(line)
            print(f"context check: {res.problems} problem(s)" if res.problems
                  else "context check: every copy matches its master")
            return res.code
        res = sync(repo, adopt=adopt, symlink=symlink, apply=not dry_run)
    except ConfigError as e:
        print(f"context: {e}", file=sys.stderr)
        return 2
    for line in res.lines:
        print(line)
    if res.problems:
        print(f"context sync: {res.problems} refused -- nothing hand-written "
              f"was overwritten")
    elif res.written == 0:
        print("context sync: nothing to change")
    return res.code


if __name__ == "__main__":
    sys.exit(main())
