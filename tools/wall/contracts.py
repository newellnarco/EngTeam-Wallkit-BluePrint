"""The wall's wire contracts, typed once.

Until now the contracts lived as strings in four places: the enqueue
directive in the template's JS, the wave envelope in the host exporter,
the relay failure kinds in the host's wall server, and prose in config
`_` notes. Four copies drift. This module is the one they all pin
against — StrEnums + frozen dataclasses + explicit doc maps (the host's
"type design", adopted): Python consumers import it; the template is
JavaScript, so its tests assert the template's literals against these
values instead — the contract stays code, the page stays static.

Stdlib only (DEC-0017 clause 1). The MCP adapter derives its tool
schemas from here (DEC-0017 clause 4) — never a fifth copy.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

# ------------------------------------------------------------ the enqueue

#: Every wall click carries these; a host queue can rely on them.
ENQUEUE_SOURCE = "wall_click"
ENQUEUE_PRIORITY = "P2"


class Directive(StrEnum):
    """What a wall control or MCP client asks the host queue to do.

    One vocabulary for every surface (DEC-0032): the wall page's buttons
    and `wall_enqueue` over MCP build the same typed payloads, so a review
    verdict or an unblock can come from the wall, Claude Code, Cursor,
    VS Code or any other MCP client and land on the one host queue every
    consumer already reads.
    """

    EXECUTE_ITEM = "execute_item"
    EXECUTE_ARC = "execute_arc"
    RESOLVE_BLOCKED = "resolve_blocked"
    WARDEN_REGIME = "warden_regime"
    WARDEN_AUDIT = "warden_audit"
    DOC_REVIEW = "doc_review"


DIRECTIVE_DOCS: dict[Directive, str] = {
    Directive.EXECUTE_ITEM: "enqueue ONE board item, named by target_key",
    Directive.EXECUTE_ARC: "enqueue a whole arc, named by target_arch",
    Directive.RESOLVE_BLOCKED: ("dispatch the unblock work for item_id -- "
                                "mode 'build' or 'research', reason required"),
    Directive.WARDEN_REGIME: ("Warden only: evaluate then record a regime "
                              "selection -- action 'enable' or 'disable', "
                              "regime required"),
    Directive.WARDEN_AUDIT: ("Warden only: audit every control of the named "
                             "regime and record the results"),
    Directive.DOC_REVIEW: ("a document-of-record verdict -- action 'approve', "
                           "'changes' or 'deny' on path (sha as read); "
                           "approve records the ack, changes/deny record "
                           "feedback AND file the fix as work"),
}


@dataclass(frozen=True)
class EnqueuePayload:
    """The body an EXECUTE click POSTs to the host queue's add endpoint.

    Frozen and validated at construction: a directive without its target
    is a payload the host would half-understand, which is worse than a
    refusal here.
    """

    directive: Directive
    title: str
    target_key: str | None = None
    target_arch: str | None = None
    action: str | None = None
    path: str | None = None
    sha: str | None = None
    reason: str | None = None
    regime: str | None = None
    mode: str | None = None
    item_id: str | None = None
    source: str = ENQUEUE_SOURCE
    priority: str = ENQUEUE_PRIORITY

    def __post_init__(self) -> None:
        # Normalize FIRST: a caller passing the raw string "execute_item"
        # would fail the identity checks below and skip target validation
        # entirely — a half-validated payload sneaking out as valid.
        # (CodeRabbit review finding on the host PR, accepted.)
        try:
            directive = Directive(self.directive)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"unknown directive: {self.directive!r}") from exc
        object.__setattr__(self, "directive", directive)
        if directive is Directive.EXECUTE_ITEM and not self.target_key:
            raise ValueError("execute_item requires target_key")
        if directive is Directive.EXECUTE_ARC and not self.target_arch:
            raise ValueError("execute_arc requires target_arch")
        if directive is Directive.RESOLVE_BLOCKED:
            if self.mode not in ("build", "research"):
                raise ValueError("resolve_blocked requires mode "
                                 "'build' or 'research'")
            if not self.item_id:
                raise ValueError("resolve_blocked requires item_id")
            if not (self.reason or "").strip():
                raise ValueError("resolve_blocked requires a reason -- the "
                                 "dispatched agent starts from it")
        if directive is Directive.WARDEN_REGIME:
            if self.action not in ("enable", "disable"):
                raise ValueError("warden_regime requires action "
                                 "'enable' or 'disable'")
            if not self.regime:
                raise ValueError("warden_regime requires regime")
        if directive is Directive.WARDEN_AUDIT and not self.regime:
            raise ValueError("warden_audit requires regime")
        if directive is Directive.DOC_REVIEW:
            if self.action not in ("approve", "changes", "deny"):
                raise ValueError("doc_review requires action 'approve', "
                                 "'changes' or 'deny'")
            if not self.path:
                raise ValueError("doc_review requires path")
            if not (self.sha or "").strip():
                raise ValueError("doc_review requires the sha that was read "
                                 "-- a verdict unbound to a revision cannot "
                                 "be detected stale")
            if self.action != "approve" and not (self.reason or "").strip():
                raise ValueError("doc_review changes/deny require a reason "
                                 "-- a verdict nobody can act on is noise")
        if not self.title:
            raise ValueError("an enqueue payload carries a human title")

    def to_dict(self) -> dict:
        out: dict = {
            "source": self.source,
            "priority": self.priority,
            "directive": str(self.directive),
            "title": self.title,
        }
        for field in ("target_key", "target_arch", "action", "path", "sha",
                      "reason", "regime", "mode", "item_id"):
            value = getattr(self, field)
            if value is not None:
                out[field] = value
        return out


# ------------------------------------------------------- the relay verdicts

class RelayFailureKind(StrEnum):
    """The three sentences a relay failure needs (the host wall server's
    classification, adopted verbatim — its `_fail` docstring is the prose
    original)."""

    MAX_HTTP_ERROR = "max_http_error"    # the host answered, with an error
    MAX_UNREACHABLE = "max_unreachable"  # nothing answered at all
    RELAY_REFUSED = "relay_refused"      # the relay itself declined


KIND_DOCS: dict[RelayFailureKind, str] = {
    RelayFailureKind.MAX_HTTP_ERROR: "the backend is up; the endpoint erred",
    RelayFailureKind.MAX_UNREACHABLE: "the backend is down or unreachable",
    RelayFailureKind.RELAY_REFUSED: (
        "the relay declined: redirect, size cap, transfer-encoding, "
        "timeout or short read — never forwarded"),
}


# ------------------------------------------------------------- item status

class ItemStatus(StrEnum):
    """The canonical board vocabulary. The template carries the same
    tables in JS (STATUS_CANON / STATUS_ALIAS) because the page must
    stay static; the tests pin the JS against THIS copy, so there is one
    authority and one mirror, never two authorities."""

    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    REVIEW = "review"
    DONE = "done"
    SHIPPED = "shipped"


#: Foreign spellings the wall was taught, folded onto the canon.
STATUS_ALIASES: dict[str, ItemStatus] = {
    "ready": ItemStatus.PLANNED, "triage": ItemStatus.PLANNED,
    "backlog": ItemStatus.PLANNED, "todo": ItemStatus.PLANNED,
    "open": ItemStatus.PLANNED, "queued": ItemStatus.PLANNED,
    "proposed": ItemStatus.PLANNED,
    "active": ItemStatus.IN_PROGRESS, "wip": ItemStatus.IN_PROGRESS,
    "in_flight": ItemStatus.IN_PROGRESS,
    "in_review": ItemStatus.REVIEW, "in_ci": ItemStatus.REVIEW,
    "review_ready": ItemStatus.REVIEW, "needs_review": ItemStatus.REVIEW,
    "merged": ItemStatus.SHIPPED, "released": ItemStatus.SHIPPED,
    "closed": ItemStatus.DONE, "complete": ItemStatus.DONE,
    "completed": ItemStatus.DONE, "resolved": ItemStatus.DONE,
}

#: Live work, after canonicalization.
IN_FLIGHT_STATUSES = frozenset(
    {ItemStatus.IN_PROGRESS, ItemStatus.REVIEW, ItemStatus.BLOCKED})
DONE_LIKE = frozenset({ItemStatus.DONE, ItemStatus.SHIPPED})


def canon_status(raw: object) -> ItemStatus | None:
    """The template's canonStatus(), in Python: lowercase, spaces and
    hyphens to underscores, canon or alias — None for a status the wall
    was not taught (a fact about the project, not an error)."""
    key = "_".join(str("" if raw is None else raw).strip().lower()
                   .replace("-", " ").split())
    try:
        return ItemStatus(key)
    except ValueError:
        return STATUS_ALIASES.get(key)


# -------------------------------------------------------- the agents wave

#: The wave-status envelope every exporter must carry (the CREW tab's
#: Live wave panel and any host AGENTS stream read exactly these).
WAVE_REQUIRED_KEYS = ("updated", "headcount", "completed", "in_progress", "new")
HEADCOUNT_KEYS = ("developers", "researchers", "cap")


@dataclass(frozen=True)
class WaveStatus:
    """One live-wave reading. `in_progress` entries may be plain strings
    or {agent, unit, stage} mappings — both render; the type keeps them
    verbatim rather than guessing a normalization the exporter didn't
    state."""

    updated: str
    developers: int
    researchers: int
    cap: int | str
    completed: tuple = ()
    in_progress: tuple = ()
    new: tuple = ()

    @classmethod
    def from_payload(cls, payload: dict) -> WaveStatus:
        missing = [k for k in WAVE_REQUIRED_KEYS if k not in payload]
        if missing:
            raise ValueError(f"wave status missing keys: {missing}")
        hc = payload["headcount"] or {}
        return cls(
            updated=str(payload["updated"]),
            developers=int(hc.get("developers") or 0),
            researchers=int(hc.get("researchers") or 0),
            cap=hc.get("cap", "?"),
            completed=tuple(payload["completed"] or ()),
            in_progress=tuple(payload["in_progress"] or ()),
            new=tuple(payload["new"] or ()),
        )
