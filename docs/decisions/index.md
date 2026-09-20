# Decision log

One file per decision, never rewritten. A decision that changes is **superseded**
by a new file, and both ends of the link are recorded. This index is navigation;
the files are the record.

Format and front-matter contract: `docs/WALL_STANDARDS.md` section 6.

| ID | Status | Decision | Scope | Decided |
|---|---|---|---|---|
| [DEC-0001](DEC-0001.md) | active | Courier is a script, not an agent | `tools/wall/` | 2026-09-19 |
| [DEC-0002](DEC-0002.md) | active | Maestro is the session, not a subagent | crew | 2026-09-19 |
| [DEC-0003](DEC-0003.md) | active | Keys are identity; names are labels | `.wall/registry/` | 2026-09-19 |
| [DEC-0004](DEC-0004.md) | active | Event shards ship on an isolated branch | `.wall/events/` | 2026-09-19 |
| [DEC-0005](DEC-0005.md) | active | Fast-track ends in a pull request | routing | 2026-09-19 |
| [DEC-0006](DEC-0006.md) | active | Researcher network access defaults to none | `research.*` | 2026-09-19 |
| [DEC-0007](DEC-0007.md) | active | Builders are tiered by task class | cost | 2026-09-19 |
| [DEC-0008](DEC-0008.md) | active | Budget actuals come from harness usage | `.wall/events/` | 2026-09-19 |
| [DEC-0009](DEC-0009.md) | active | Names bind to the instance, not the role slot | `.wall/registry/` | 2026-09-19 |
| [DEC-0010](DEC-0010.md) | active | One machine-wide timer, not one per repository | install | 2026-09-19 |
| [DEC-0011](DEC-0011.md) | active | Evidence outranks self-report | crew | 2026-09-19 |
| [DEC-0012](DEC-0012.md) | active | The Integrator is a first-class role | crew | 2026-09-19 |
| [DEC-0013](DEC-0013.md) | active | Draft-PR auto-review: per-lane pin, default OFF for metered lanes | review lanes | 2026-09-19 |
| [DEC-0014](DEC-0014.md) | active | Scoped CI only where escape-rate-validated; the pyramid gates the merge | CI | 2026-09-19 |
| [DEC-0015](DEC-0015.md) | active | Leases are the invariant; worktrees recommended for git-writing builders | isolation | 2026-09-19 |
| [DEC-0016](DEC-0016.md) | active | Cooperative parallel PRs; merges + per-PR pushes stay serialized | integration | 2026-09-19 |
| [DEC-0017](DEC-0017.md) | active | Portability is a standing requirement, mechanically ratcheted | portability | 2026-09-20 |
| [DEC-0018](DEC-0018.md) | active | One source of truth, derived presentations, reporting rides existing actions | reporting | 2026-09-20 |
| [DEC-0019](DEC-0019.md) | active | The wall speaks MCP: six tools exactly, stdio only, role-gated, schemas from contracts | integration | 2026-09-20 |

---

## Writing a decision

- Allocate the next number. Numbers are never reused, even for a file that is
  later superseded.
- Front matter carries `id`, `status`, `supersedes`, `superseded_by`, `scope`,
  `expert`, `expert_key`, `asked_by`, `decided`. The structured fields exist so
  the contradiction check can read them; prose does not scale past about a
  hundred entries.
- Body: **Question**, **Decision**, **Why**, **What this rules out**, and
  **Revisit if** - the last one is what keeps a settled decision from becoming
  dogma.
- Superseding a decision edits exactly two fields in the old file
  (`status: superseded`, `superseded_by:`) and nothing else. The old reasoning
  stays readable.
- Add the row here in the same change.

## Status values

| Status | Meaning |
|---|---|
| `active` | In force. Cite it; do not relitigate it. |
| `superseded` | Replaced. Read it for the reasoning, follow `superseded_by`. |
