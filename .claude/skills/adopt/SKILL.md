---
name: adopt
description: Parse an existing repository's documents, find everything that already serves an adoption-runbook function (entry point, rules, failure registry, ship checklist, coding standards, decision log, prompt budgets), report the inventory with evidence, and map or consolidate as needed -- pointer stubs over duplication, merges only with the engineer's confirmation. Invoke as /adopt inventory | map | consolidate. The executable half of the README's existing-repo adoption runbook.
---

# adopt -- find what exists, map it, consolidate what drifted

The adoption runbook's first law is **map, do not duplicate**: two copies of a
rule drift, and the next agent reads whichever it found first. This skill is
that law as a procedure a user can invoke in any session, on any repository
the kit is dropped into.

## `inventory` -- parse and classify, change nothing

1. **Sweep the tree for documents** (`*.md`, `*.rst`, `*.txt`, docs/ trees,
   `.github/`, wiki exports), skipping vendored and generated paths.
2. **Classify by FUNCTION, not filename.** For each of the seven functions,
   look for the signatures, not the kit's names:

| Function | Filename hints | Content signatures that outrank filenames |
|---|---|---|
| Entry point | `CLAUDE.md`, `AGENTS.md`, `CONTRIBUTING.md`, README | "read this first", current-state section, a doc index, pointers to rules |
| Standing rules | `RULES.md`, `STANDING_RULES.md`, conventions docs | imperative "never/always" lists, an owner-only change rule, numbered hard rules |
| Failure registry | `KNOWN_FAILURE_PATTERNS.md`, postmortem folders | symptom/root-cause/check triples, incident ids (F-XXX-NNN style), "resolved" sections |
| Ship checklist | `SHIP_CHECKLIST.md`, release runbooks, PR templates | checkbox lists gating a release/merge, "before you ship" |
| Coding standards | `BEST_PRACTICES.md`, style guides, reviewer configs (`.coderabbit.yaml`, copilot instruction files) | rules addressed to a reviewer or author, lint rationale |
| Decision log | `docs/decisions/`, `adr/`, RFC folders | one-file-per-ruling, status/superseded fields, dated verdicts |
| Prompt budgets | almost never exists | any doc naming a token/char cap for a tool |

3. **Report the inventory as a table** -- function, file(s) found, the
   evidence line that classified it, and a verdict per function:
   `covered` / `missing` / `split across N files` / `duplicated` /
   `stale-conflicting`. Multiple files serving one function is the finding
   this skill exists to surface.
4. Write the report to the wall as a note on the adoption arc (or print it,
   pre-kit). **Inventory never edits anything.**

## `map` -- wire the kit's expectations onto what exists

For each function, by inventory verdict:

- **covered** -> write a **pointer stub** at the kit's expected location
  (the README runbook's form: "this project's rules live at X; kit rules
  that document must additionally carry: ..."), and verify the three
  non-negotiables are present in the host's own document -- per-invocation
  identity, coordinator merge authority, gates-last. Missing ones are added
  **to the host's document**, never as a second rulebook.
- **missing** -> copy the kit template and fill it via its question set
  (`docs/TEMPLATE_INTAKE.md` -- required questions first, then the probes).
- **split / duplicated / conflicting** -> queue for `consolidate`; map picks
  the **document of record** provisionally (the one other files already
  point at, else the most-recently-maintained) and says so in the report.

Every stub and edit rides a normal PR. Nothing is force-written over a host
document.

## `consolidate` -- one function, one document of record

For each queued function:

1. **Diff the copies** rule-by-rule: identical (keep once), complementary
   (merge, attributing origin), **conflicting** (the pair goes to the
   engineer -- content conflicts between two live rulebooks are policy, and
   an agent picking a winner silently is exactly the drift this repairs).
2. **Merge into the document of record**; every other copy becomes a pointer
   stub carrying its old location's readers to the record. Never delete a
   file that anything links to -- hollow it to a pointer instead.
3. **Preserve history honestly**: the merge commit's message names every
   source file and what moved; superseded rules are struck through in place
   or moved to a dated appendix, not vaporised (the same
   superseded-not-rewritten discipline as the decision log).
4. Record the consolidation as a `DEC-NNNN` (which file is now the record
   for which function) so the next inventory run reads `covered` with one
   file, and the contradiction check knows where to look.

## Boundaries

- Inventory is read-only; map and consolidate change documents only --
  never code, never CI, never `.wall/` state beyond notes.
- A conflict between two live rule copies is **always** the engineer's call
  (SESSION_LIFECYCLE.md section 4 -- policy conflicts class). The skill
  stages the diff; it does not pick.
- Reviewer-facing configs found during inventory are handed to
  `/reviewer-integration baseline` rather than consolidated here -- one
  procedure per surface.
- The worked precedent: the reference deployment's own adoption found six of
  seven functions covered under its own names and consolidated by mapping,
  which is why the runbook's inventory table lists "common names" at all.
