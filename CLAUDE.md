<!-- GENERATED from AGENTS.md by tools/wall/context_sync.py -- do not edit this copy. Edit AGENTS.md and run: python tools/wall/context_sync.py sync -- master-sha256: 629b3f280abbbe0d1eb5128e5842c276aebb52eca95d535de85d08cb68ab0fa0 -->
# AGENTS.md - instructions for AI agents working on the EngTeam Wall Kit

> If you are an agent changing this repository, read this file first, then the
> documents under "Mandatory reading". This file is the **entry point** for the
> kit's own repository. It is not the kit's product: the `AGENTS.md` an adopting
> repository gets is built from `templates/AGENTS.md.template`.

---

## Mandatory reading before any change

1. [`docs/WALL_KIT_GUIDE.md`](docs/WALL_KIT_GUIDE.md) - the consolidated source
   of truth. Every change to the kit's behavior, commands, configuration,
   roles, decisions, install or removal, or its documentation updates it in the
   same pull request, with an entry in its change log (Appendix C), newest
   first. `tests/test_guide_current.py` fails CI when it falls behind.
2. [`docs/RECONCILIATION.md`](docs/RECONCILIATION.md) - binding over the guide
   and every narrower document.
3. [`FAILURE_PATTERNS.md`](FAILURE_PATTERNS.md) - the bug classes this repository
   already paid for. Check your change against it; add a class in the same PR as
   its fix. The library adopting repos start from is
   `templates/FAILURE_PATTERNS.md.template`.
4. [`.claude/MAESTRO.md`](.claude/MAESTRO.md) - the session operating manual.
   The top-level session is the Maestro; `.claude/agents/` are its subagents.

---

## What this project is

A dependency-free blueprint and drop-in kit (stdlib Python, plain HTML and CSS,
no network calls, no build step) that stands up an engineering organization run
by LLM agents, governed by the humans it amplifies. It is a kit and a public
blueprint, not a service. The author does not endorse using it to replace human
decision makers: every gate that routes to "the engineer" stays with a person.

---

## How to check a change

Run what CI runs (`.github/workflows/ci.yml`) before you push:

- `ruff check tools/wall --isolated --select E4,E7,E9,F`
- `ruff check tests --isolated --select F`
- `python -m pytest tests/ -q`
- `bash tools/quality/scan.sh ci` (SAST and secrets; install with
  `bash tools/quality/install.sh`)

---

## Doc index

| Doc | Purpose |
|---|---|
| [`README.md`](README.md) | What the kit is, and the caution before adopting it. |
| [`docs/WALL_KIT_GUIDE.md`](docs/WALL_KIT_GUIDE.md) | The consolidated guide; its section map lists every document. |
| [`docs/RECONCILIATION.md`](docs/RECONCILIATION.md) | Measured lessons from the reference deployment. Binding. |
| [`FAILURE_PATTERNS.md`](FAILURE_PATTERNS.md) | The kit's own failure registry. |
| [`KNOWN_ISSUES.md`](KNOWN_ISSUES.md) | Open problems and their workarounds. |
| [`REVIEWER_LANES.md`](REVIEWER_LANES.md) | Who reviews what, and when a lane is exhausted. |
| [`docs/CONTEXT_FILES.md`](docs/CONTEXT_FILES.md) | Why this file is the master and `CLAUDE.md` is generated. |
| [`docs/decisions/index.md`](docs/decisions/index.md) | The decision log, one `DEC-NNNN` per ruling. |

---

## Avoid

- Editing `CLAUDE.md` (or any generated copy) by hand. Edit this file, then run
  `python tools/wall/context_sync.py sync`.
- Adding a dependency or a network call: the kit is stdlib-only and offline by
  design.
