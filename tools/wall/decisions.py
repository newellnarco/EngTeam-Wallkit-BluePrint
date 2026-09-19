#!/usr/bin/env python3
"""decisions.py -- the decision log: parse, index, check for contradiction.

One file per decision, `docs/decisions/DEC-NNNN.md`, exactly as WALL_STANDARDS
Section 6 specifies. Front matter carries what the contradiction check needs;
free-text markdown stops scaling around a hundred entries, which is why status
and supersession live in structured fields rather than prose.

    ---
    id: DEC-0042
    status: active          # active | superseded
    supersedes: DEC-0018
    superseded_by: null
    scope: backend/ledger/
    expert: Edmund
    expert_key: arc_bb1740
    asked_by: bld_7e33d1
    decided: 2026-09-19T14:03Z
    ---

The front-matter parser is a deliberate minimum: `key: value`, `null`, quoted
strings, inline `[a, b]` lists and `- item` blocks. No YAML dependency, because
the kit's promise is stdlib only -- and because a decision file that needs
anchors and multi-line flow scalars has stopped being a decision record.

Every parse failure becomes a named problem on the index, never an exception.
An unreadable decision is a finding, not a crash: the whole point of the log is
that Maestro searches it before spending a researcher, so a log that refuses to
load must say so loudly rather than quietly answering "no decisions found".
"""

from __future__ import annotations

import fnmatch
import re
from pathlib import Path
from typing import Any, NamedTuple

DEFAULT_DIR = "docs/decisions"
FILE_GLOB = "DEC-*.md"
ID_RE = re.compile(r"^DEC-(\d{1,6})$")
FENCE = "---"

ACTIVE = "active"
SUPERSEDED = "superseded"
KNOWN_STATUSES = (ACTIVE, SUPERSEDED, "draft", "rejected")

# Fields the contradiction check reads. Anything else in the front matter is
# preserved verbatim under `extra` -- the log is allowed to grow fields.
CORE_FIELDS = ("id", "status", "supersedes", "superseded_by", "scope",
               "expert", "expert_key", "asked_by", "decided", "title")


class DecisionIndex(NamedTuple):
    decisions: dict[str, dict]
    problems: list[dict]


# ------------------------------------------------------------ front matter

def _scalar(raw: str) -> Any:
    v = raw.strip()
    if not v:
        return None
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        return v[1:-1]
    low = v.lower()
    if low in ("null", "~", "none"):
        return None
    if low == "true":
        return True
    if low == "false":
        return False
    if v.startswith("[") and v.endswith("]"):
        inner = v[1:-1].strip()
        if not inner:
            return []
        return [_scalar(part) for part in inner.split(",")]
    return v


def parse_front_matter(text: str) -> tuple[dict, list[str]]:
    """Return (fields, problems). Never raises.

    Tolerates a missing closing fence (everything after the opener is treated
    as front matter and the omission is reported), duplicate keys (last wins,
    reported), and unparseable lines (reported, skipped).
    """
    problems: list[str] = []
    lines = text.splitlines()
    start = 0
    while start < len(lines) and not lines[start].strip():
        start += 1
    if start >= len(lines) or lines[start].strip() != FENCE:
        return {}, ["no front matter: file does not open with a '---' fence"]

    body: list[str] = []
    closed = False
    for line in lines[start + 1:]:
        if line.strip() == FENCE:
            closed = True
            break
        body.append(line)
    if not closed:
        problems.append("front matter is not closed by a '---' fence")

    fields: dict[str, Any] = {}
    last_key: str | None = None
    for raw in body:
        line = raw.rstrip()
        if not line.strip() or line.strip().startswith("#"):
            continue
        if line.lstrip().startswith("- ") and last_key:
            fields.setdefault(last_key, [])
            if not isinstance(fields[last_key], list):
                fields[last_key] = [] if fields[last_key] is None else [fields[last_key]]
            fields[last_key].append(_scalar(line.lstrip()[2:]))
            continue
        if ":" not in line:
            problems.append(f"unparseable front-matter line: {line.strip()!r}")
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        if not key:
            problems.append(f"unparseable front-matter line: {line.strip()!r}")
            continue
        if key in fields:
            problems.append(f"duplicate front-matter key: {key!r} (last wins)")
        fields[key] = _scalar(value)
        last_key = key
    return fields, problems


def _title_of(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return ""


def parse_decision_file(path: Path) -> tuple[dict | None, list[dict]]:
    """Parse one DEC file. Returns (record or None, problems)."""
    path = Path(path)
    problems: list[dict] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return None, [{"kind": "unreadable_decision", "path": path.name, "detail": str(exc)}]

    fields, fm_problems = parse_front_matter(text)
    for p in fm_problems:
        problems.append({"kind": "front_matter", "path": path.name, "detail": p})
    if not fields:
        return None, problems

    dec_id = fields.get("id")
    if not isinstance(dec_id, str) or not ID_RE.match(dec_id.strip()):
        problems.append({"kind": "bad_id", "path": path.name,
                         "detail": f"id {dec_id!r} is not of the form DEC-NNNN; "
                                   f"falling back to the filename"})
        dec_id = path.stem
    dec_id = dec_id.strip()
    if dec_id != path.stem:
        problems.append({"kind": "id_mismatch", "path": path.name, "id": dec_id,
                         "detail": f"front matter says {dec_id}, filename says {path.stem}"})

    status = fields.get("status")
    status = status.strip().lower() if isinstance(status, str) else ACTIVE
    if status not in KNOWN_STATUSES:
        problems.append({"kind": "unknown_status", "path": path.name, "id": dec_id,
                         "detail": f"status {status!r} is not one of "
                                   f"{', '.join(KNOWN_STATUSES)}"})

    scope = fields.get("scope")
    if isinstance(scope, str):
        scopes = [scope.strip()] if scope.strip() else []
    elif isinstance(scope, list):
        scopes = [str(s).strip() for s in scope if str(s).strip()]
    else:
        scopes = []
    if not scopes:
        problems.append({"kind": "no_scope", "path": path.name, "id": dec_id,
                         "detail": "decision has no scope; it can never be attached "
                                   "to an item automatically"})

    record = {
        "id": dec_id,
        "path": str(path),
        "file": path.name,
        "title": fields.get("title") or _title_of(text),
        "status": status,
        "supersedes": fields.get("supersedes"),
        "superseded_by": fields.get("superseded_by"),
        "scope": scopes,
        "expert": fields.get("expert"),
        "expert_key": fields.get("expert_key"),
        "asked_by": fields.get("asked_by"),
        "decided": fields.get("decided"),
        "extra": {k: v for k, v in fields.items() if k not in CORE_FIELDS},
    }
    return record, problems


def decisions_dir(repo: Path, config: dict | None = None) -> Path:
    sub = (config or {}).get("decisions_dir") or DEFAULT_DIR
    return Path(repo) / sub


def index(repo: Path, config: dict | None = None) -> DecisionIndex:
    """Index every `DEC-*.md`. Missing directory is not a problem -- a project
    with no decisions yet is a normal state, not a broken one."""
    d = decisions_dir(repo, config)
    decisions: dict[str, dict] = {}
    problems: list[dict] = []
    if not d.is_dir():
        return DecisionIndex(decisions, problems)
    for path in sorted(d.glob(FILE_GLOB)):
        record, file_problems = parse_decision_file(path)
        problems.extend(file_problems)
        if record is None:
            continue
        if record["id"] in decisions:
            problems.append({"kind": "duplicate_id", "id": record["id"],
                             "detail": f"{decisions[record['id']]['file']} and {record['file']}"})
            continue
        decisions[record["id"]] = record
    return DecisionIndex(decisions, problems)


# ------------------------------------------------------------ contradiction

def _norm_scope(scope: str) -> str:
    return scope.strip().lstrip("./")


def scopes_overlap(a: str, b: str) -> bool:
    """Two scopes overlap when one is a prefix of the other, or either glob
    matches the other's literal prefix. Conservative on purpose: a missed
    overlap is a contradiction nobody sees."""
    a, b = _norm_scope(a), _norm_scope(b)
    if not a or not b:
        return False
    if a == b:
        return True
    if any(ch in a for ch in "*?[") or any(ch in b for ch in "*?["):
        return fnmatch.fnmatch(b, a) or fnmatch.fnmatch(a, b)
    return a.startswith(b.rstrip("/") + "/") or b.startswith(a.rstrip("/") + "/")


def contradictions(decisions: dict[str, dict]) -> list[dict]:
    """Structural contradictions in the log. WALL_STANDARDS Section 6.

    These are the checks that do not need a model: supersession that points at
    nothing, supersession that was never applied, a decision claiming to be
    superseded by nobody, and two *active* decisions ruling on overlapping
    scope. The last one is a candidate, not a verdict -- two active rulings on
    the same directory may be complementary. It is flagged so a human or the
    Adjudicator looks, which is the whole job of this check.
    """
    out: list[dict] = []
    for dec_id in sorted(decisions):
        d = decisions[dec_id]
        sup = d.get("supersedes")
        for target in ([sup] if isinstance(sup, str) else (sup or [])):
            if not isinstance(target, str) or not target:
                continue
            other = decisions.get(target)
            if other is None:
                out.append({"kind": "supersedes_missing", "ids": [dec_id, target],
                            "detail": f"{dec_id} supersedes {target}, which is not in the log"})
            elif other.get("status") == ACTIVE:
                out.append({"kind": "supersedes_active", "ids": [dec_id, target],
                            "detail": f"{dec_id} supersedes {target}, but {target} is "
                                      f"still marked active"})
            elif other.get("superseded_by") not in (dec_id, None):
                out.append({"kind": "supersession_mismatch", "ids": [dec_id, target],
                            "detail": f"{target}.superseded_by is "
                                      f"{other.get('superseded_by')!r}, not {dec_id}"})
        by = d.get("superseded_by")
        if isinstance(by, str) and by:
            if by not in decisions:
                out.append({"kind": "superseded_by_missing", "ids": [dec_id, by],
                            "detail": f"{dec_id} is superseded by {by}, which is not in the log"})
            if d.get("status") == ACTIVE:
                out.append({"kind": "active_but_superseded", "ids": [dec_id],
                            "detail": f"{dec_id} names a successor but is still active"})
        elif d.get("status") == SUPERSEDED:
            out.append({"kind": "superseded_without_successor", "ids": [dec_id],
                        "detail": f"{dec_id} is marked superseded with no superseded_by"})

    active = [decisions[i] for i in sorted(decisions) if decisions[i].get("status") == ACTIVE]
    for i, a in enumerate(active):
        for b in active[i + 1:]:
            hit = next(((x, y) for x in a["scope"] for y in b["scope"]
                        if scopes_overlap(x, y)), None)
            if hit:
                out.append({"kind": "overlapping_scope", "ids": [a["id"], b["id"]],
                            "scope": [hit[0], hit[1]],
                            "detail": f"{a['id']} and {b['id']} are both active over "
                                      f"overlapping scope ({hit[0]} / {hit[1]})"})
    # Supersession cycles: a chain that never terminates.
    for dec_id in sorted(decisions):
        seen, cur = [], dec_id
        while isinstance(cur, str) and cur in decisions:
            if cur in seen:
                out.append({"kind": "supersession_cycle", "ids": seen + [cur],
                            "detail": " -> ".join(seen + [cur])})
                break
            seen.append(cur)
            cur = decisions[cur].get("superseded_by")
    # One cycle produces one flag per member; collapse to the first spelling.
    deduped, seen_sets = [], set()
    for flag in out:
        if flag["kind"] != "supersession_cycle":
            deduped.append(flag)
            continue
        key = frozenset(flag["ids"])
        if key not in seen_sets:
            seen_sets.add(key)
            deduped.append(flag)
    return deduped


# -------------------------------------------------------------- in effect

def in_effect(decisions: dict[str, dict], scopes: list[str],
              referenced: list[str] | None = None) -> list[dict]:
    """Decisions that govern these paths, plus any explicitly referenced.

    Superseded decisions are excluded from the scope match but kept when a run
    actually carried one -- "a builder was handed a ruling that had already
    been replaced" is exactly the kind of thing `wall why` exists to show.
    """
    referenced = referenced or []
    hits: dict[str, dict] = {}
    for dec_id in sorted(decisions):
        d = decisions[dec_id]
        if d.get("status") != ACTIVE:
            continue
        for want in scopes:
            if any(scopes_overlap(want, have) for have in d["scope"]):
                hits[dec_id] = d
                break
    for dec_id in referenced:
        if dec_id in decisions:
            hits.setdefault(dec_id, decisions[dec_id])
    return [hits[k] for k in sorted(hits)]


def next_id(decisions: dict[str, dict]) -> str:
    highest = 0
    for dec_id in decisions:
        m = ID_RE.match(dec_id)
        if m:
            highest = max(highest, int(m.group(1)))
    return f"DEC-{highest + 1:04d}"


SKELETON = """---
id: {dec_id}
status: active
supersedes: null
superseded_by: null
scope: {scope}
expert: {expert}
expert_key: {expert_key}
asked_by: {asked_by}
decided: {decided}
---

# {dec_id} -- {title}

## Question

{question}

## Ruling

{ruling}

## Why

<!-- The reasoning. A ruling without it gets relitigated every time somebody
     new reads it. -->

## Consequences

<!-- What now has to change, and what is now forbidden. -->
"""


def render_skeleton(dec_id: str, title: str, question: str, ruling: str,
                    scope: str = "", expert: str = "", expert_key: str = "",
                    asked_by: str = "", decided: str = "") -> str:
    return SKELETON.format(
        dec_id=dec_id, title=title or "(title)",
        question=question or "(what was asked)",
        ruling=ruling or "(the answer, stated so it can be followed)",
        scope=scope or "null", expert=expert or "null",
        expert_key=expert_key or "null", asked_by=asked_by or "null",
        decided=decided or "null")


def write_decision(repo: Path, dec_id: str, text: str,
                   config: dict | None = None) -> Path:
    """Write a decision file. Refuses to overwrite: decision records are
    never rewritten, exactly like PATCH_NOTES."""
    d = decisions_dir(repo, config)
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{dec_id}.md"
    if path.exists():
        raise FileExistsError(str(path))
    path.write_text(text, encoding="utf-8")
    return path
