# FAST_TRACK.md

A route for doc-only changes: no CI, no reviewer dispatch, fewest GitHub minutes.

**This is not a new concept.** `max3-docs-push` already classifies changed files
into doc and source buckets and blocks on source. Fast-track promotes that rule
from skill prose into config so Courier, CI and the agents read one definition
instead of three copies drifting apart.

---

## Classification is mechanical

Routed on the changed file set alone, computed from `git diff --name-only`.
**Never asserted by an agent.** If agents can self-declare their route, every
builder eventually discovers that calling its work a doc skips the gates.

- Every path matches the allow list → fast-track.
- Any path falls outside it → full track.

No mixed mode, no partial credit.

```json
{
  "fast_track": {
    "allow": ["**/*.md", "docs/**/*.docx", "TREE_INTEGRITY_LEDGER.txt",
              "MANIFEST.sha256"],
    "deny":  ["frontend/src/**", "backend/**/*.py", "**/*.bat", "**/*.ps1",
              ".github/workflows/**", "tools/**", ".wall/config/**",
              "**/CLAUDE.md"]
  }
}
```

**Deny beats allow, always.** Three entries are worth defending:

- `.github/workflows/**` — a builder editing CI to turn its own tests green is
  the classic escape hatch. It is code.
- `**/CLAUDE.md` — it matches `**/*.md`, so the allow glob would fast-track it,
  but it changes the behavior of every future agent. It is code.
- `tools/**` — wall tooling can corrupt the ledger. Not a doc.

Mixed changesets **split** rather than get an exception, which is what
`max3-docs-push` already tells the user to do. `wall fast-track` offers the
split: stage the doc-only subset, fast-track it, leave the rest on the full track.

---

## Skipping CI without lying about it

The cheapest skip is the one where the run never starts. Path filters beat
`[skip ci]` in the commit message, because with `paths-ignore` GitHub does not
queue a job at all — zero minutes, and no queued-then-cancelled noise.

```yaml
on:
  push:
    paths-ignore: ['**/*.md', 'docs/**', '.wall/events/**']
```

**The catch:** a required status check that never runs blocks the merge forever
under branch protection. Pair the filter with a companion workflow on the
*inverse* paths that does nothing but report success under the same check name.
It runs in a few seconds and unblocks the merge honestly, rather than you
disabling protection or force-merging.

---

## What fast-track never skips

Three things, or the audit story breaks exactly where it matters most:

- The ledger event fires. A fast-track commit is still a work item with a trace,
  and `wall diff-state` must still reconcile.
- The lease is still taken. Two agents editing the same doc concurrently corrupts
  it the same as code.
- The decision log is still written if the change encodes a ruling.

What it *does* skip: Reviewer dispatch, Architect sign-off, test authoring, CI.
That is the whole saving, and it is most of the cost.

Local gates still run and are free: link check, front-matter validation, and a
ledger-schema check on `.wall/events/**`. Fast-track means no **cloud** minutes,
not no validation.

---

## Architecture docs are the exception

A doc-only change by the Architect can silently invalidate work already built
against the old version, and fast-track gives no signal.

Cheap fix without breaking the fast path: fast-track as normal, but if the path
matches `docs/architecture/**` or `docs/decisions/**`, also emit a `doc_impact`
event naming the affected arcs. No review, no CI, no delay — one event write,
surfaced on the wall as a flag for the Foreman to raise.

---

## Surface

```
wall classify [--staged]    # prints route + which rule matched + why
wall fast-track [-m MSG]    # classify, local gates, commit, push
                            # refuses a mixed changeset, offers the split
```

`wall classify` as a dry run is worth more than it sounds: when something takes
the wrong route you want the matching rule named, not to reverse-engineer globs.

---

## Open

Straight to main, or a PR that auto-merges once the no-op check reports? Straight
to main is faster and fewer minutes; auto-merge PR keeps a uniform audit surface
and survives branch protection cleanly. `max3-docs-push` currently merges to main.
