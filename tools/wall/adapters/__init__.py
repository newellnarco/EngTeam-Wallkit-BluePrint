"""adapters -- read an existing project's tracker into the wall's ledger.

The wall is designed to be adopted by a project that is already underway, and
a wall that starts empty tells that project nothing on day one. An adapter
closes that gap: it maps whatever tracker the project already keeps into
`item_created` / `item_state` events, so the STORIES tab shows the real arcs,
stories and bugs from the first sweep.

An adapter never edits the source. It only appends events, and appending twice
changes nothing -- see `board_import.import_board`.

    from adapters import import_board, PROFILE_MAX3
    import_board(repo, "docs/project/board_state.json", PROFILE_MAX3)

    python3 -m adapters.board_import --repo . --source <path> --profile max3

The re-exports below are resolved lazily (PEP 562). Importing the submodule
eagerly here would leave it in `sys.modules` before `python3 -m
adapters.board_import` executes it, which runpy warns about and which would
give the CLI a second copy of the module's globals.

Stdlib only.
"""

from __future__ import annotations

from typing import Any

_EXPORTS = (
    "IMPORT_ACTOR",
    "PROFILE_GENERIC",
    "PROFILE_MAX3",
    "PROFILES",
    "WALL_KINDS",
    "WALL_STATUSES",
    "import_board",
    "load_source",
    "main",
    "map_item",
    "trace_for",
    "validate_profile",
)

__all__ = list(_EXPORTS)


def __getattr__(name: str) -> Any:
    if name in _EXPORTS:
        from . import board_import
        return getattr(board_import, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_EXPORTS))
