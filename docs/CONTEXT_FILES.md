# CONTEXT_FILES.md

Agent context files: the documents an agent tool loads into every session
before it reads anything else. Each tool looks for its own name - `CLAUDE.md`,
`GEMINI.md`, `.github/copilot-instructions.md`, a Cursor rule - and a team
running more than one tool ends up with several copies of the same
instructions, which drift apart the first week. This document is the kit's
answer: one master per directory, generated copies, a check that fails on
drift.

---

## 1. One master, generated copies

The master is **`AGENTS.md`**: a tool-agnostic name, written once, in the
repository root (`templates/AGENTS.md.template`). Every tool-specific file is
**generated** from it by `tools/wall/context_sync.py` and is never edited by
hand.

Each generated copy starts with a one-line banner:

```
<!-- GENERATED from AGENTS.md by tools/wall/context_sync.py -- do not edit
this copy. Edit AGENTS.md and run: python tools/wall/context_sync.py sync --
master-sha256: <sha256 of the body> -->
```

(one line in the file; wrapped here). The banner does two jobs. It tells the
next reader - human or agent - where the real file is, which stops the edit
before it happens. And its hash is the hash of the body it carries, so drift
is detectable from the copy alone:

- body no longer hashes to its own banner -> the copy was **edited**;
- banner hash differs from the current master's -> the copy is **stale**;
- a tool file with no banner -> **hand-written**, and never overwritten.

A Cursor rule (`.cursor/rules/agents.mdc`) must open with its frontmatter
(`description`, `alwaysApply: true`), so there the banner is the first line
after it.

### Copies by default, symlinks opt-in

A symlink is the lighter answer on one POSIX machine and the wrong default for
a team:

- a Windows checkout without developer mode materializes a symlink as a
  one-line text file holding the target path;
- some CI checkouts, archive exports and zip downloads drop symlinks or
  flatten them the same way;
- a symlink carries no banner, so nothing tells a reader it is not the master.

So `sync` writes **copies**. `sync --symlink` writes relative symlinks for a
team that is POSIX-only end to end; `check` accepts either a correct copy or a
symlink that resolves to the right master. Where a symlink cannot be made (on
Windows, on a failed call, for a Cursor rule that needs frontmatter) the tool
copies instead and says so.

Line endings: copies are written LF and compared after normalizing CRLF, so a
checkout that converted line endings does not make `check` flap.

---

## 2. A modular hierarchy

The root `AGENTS.md` holds what is true **everywhere**: what the project is,
the current state, where the rules live, the doc index, the few preferences
and prohibitions that apply to every change.

A directory with technical truths of its own gets its **own** `AGENTS.md`,
next to the code it describes:

```
AGENTS.md              project-wide: state, rules pointer, doc index
backend/AGENTS.md      migrations, the ORM's traps, the backend test command
frontend/AGENTS.md     component conventions, the design tokens, the UI tests
```

An agent working under `backend/` reads the root file, then the nested one;
the nested file wins on its own subtree. `sync` finds every `AGENTS.md` and
writes the per-directory copies (`CLAUDE.md`, `GEMINI.md`) beside each one.

What belongs where:

| Root `AGENTS.md` | Nested `AGENTS.md` |
|---|---|
| What the project is and is not | How this directory's code is built and tested |
| Current state, roadmap, doc index | Invariants only this subtree has |
| Pointers to `RULES.md`, the failure registry, the checklist | Commands scoped to this directory |
| Preferences that hold for every change | Preferences that hold only here |

A rule that is only true under one directory, written in the root, is loaded
into every session that never touches that directory.

---

## 3. Progressive, task-specific scoping

The root file is loaded on every run and is budget-counted
(`BUDGETED_DOCS.md`). Keep it short, and shape it so an agent can find the
part its task touches without reading the rest:

- **Clear headers.** `## Preferred` and `## Avoid` hold one-line bullets, each
  with its reason. An agent looking for "may I do X" reads two short lists,
  not a page of prose.
- **Commands in code blocks.** The test, lint and check commands are copied,
  not paraphrased; a command in a sentence gets retyped wrong.
- **Detail lives where the task is.** Directory-specific material goes in the
  nested `AGENTS.md`; reference material goes in a linked document. The root
  links; it does not inline.
- **Start small.** A new root file is the template's sections filled with
  facts. Add a rule when a change got it wrong, not in anticipation.

---

## 4. Commands

```
python tools/wall/context_sync.py sync             # write missing, refresh stale
python tools/wall/context_sync.py sync --dry-run   # report only
python tools/wall/context_sync.py sync --adopt     # hand-written CLAUDE.md -> new AGENTS.md
python tools/wall/context_sync.py sync --symlink   # POSIX teams only
python tools/wall/context_sync.py check            # exit 1 on any drift
```

The same verbs run as `python tools/wall/wall.py context sync|check`.

- `sync` never overwrites a hand-written file and never deletes one. It
  refuses, names the file, and exits 1. A second run writes nothing.
- `sync --adopt` is the migration for a repository whose entry point is
  already a hand-written `CLAUDE.md` (or `GEMINI.md`, or a Copilot file): the
  content moves into a **new** `AGENTS.md`, and the tool file is regenerated
  from it. Where an `AGENTS.md` already exists it refuses; merge the two by
  hand.
- An edited copy is refused, not overwritten: move the edit into the master,
  delete the copy, re-run `sync`.
- A generated copy whose master was deleted is removed by `sync`.
- `check` exits 0 when every copy matches its master and 1 naming each copy
  that is missing, stale, edited, hand-written or orphaned. Its output
  carries no timestamps.

Configuration: `.wall/config/wall.json`, key `context.targets`. Absent means
`["CLAUDE.md"]`.

```json
{"context": {"targets": ["CLAUDE.md", "GEMINI.md",
                         ".github/copilot-instructions.md",
                         ".cursor/rules/agents.mdc"]}}
```

`CLAUDE.md` and `GEMINI.md` are written beside every `AGENTS.md`; the Copilot
and Cursor files are root-only, because those tools read one file per
repository. An unknown name is an error, not a skip.

Directories never searched: dot-directories, dependency and cache trees
(`node_modules`, `__pycache__`, virtualenvs) and the kit's own subtrees
(`tools/wall`, `frontend/theme`).

---

## 5. Where the check runs

- **Host hooks** (docs/GIT_HOOKS.md): the kit installs no hook for this.
  A host's pre-commit should run `sync` and re-stage the copies, warning on
  a refusal; a host's pre-push should run `check`, which blocks on a
  definite finding only.
- **Host CI**: a host's static gates should run `check`. The kit's own CI
  does not, because the kit carries no `AGENTS.md` of its own.
- **Ship checklist**: one line in section D, derived files.
- **Bootstrap**: `fresh` materializes `AGENTS.md` and generates `CLAUDE.md`;
  `adopt` reports a hand-written `CLAUDE.md` and the `sync --adopt` command
  but writes nothing; `upgrade` refreshes regenerable copies; `remove` keeps
  every copy and names the generated ones.

Edits to `AGENTS.md` and `CLAUDE.md` are never fast-tracked
(`FAST_TRACK.md`): they change the behavior of every future agent.
