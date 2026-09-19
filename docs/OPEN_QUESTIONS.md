# OPEN_QUESTIONS.md

Decisions still needed before this becomes normative. Grouped by what they block.

---

## Blocking: verify the repo structure

Everything in `WALL_STANDARDS.md` marked *(inferred)* was reconstructed from the
five `max3-*` skill files, not from reading the tree. GitHub blocks automated
fetching and the local checkout was not reachable from the design session.

| # | Question | Blocks | How to answer |
|---|---|---|---|
| 1 | Is `tools/` shipped to users, or repo-only? | Where `tools/wall/` lives | `git ls-files tools/` |
| 2 | Does root `pyproject.toml` scope `backend/`, or the whole repo? | Where `test_wall_integrity.py` lands | Read `pyproject.toml` |
| 3 | Exact `TREE_INTEGRITY_LEDGER.txt` section format | Wall integrity test must match | First 40 lines |
| 4 | Current workflow triggers | Writing `paths-ignore` + the no-op companion check | `.github/workflows/*.yml` |
| 5 | `DROP_PROTOCOL.md` §5 verbatim | Arc→drop mapping | Read it |

---

## Blocking: the ledger boundary

**6. Do `.wall/config/**` and `agents.md` belong in `TREE_INTEGRITY_LEDGER.txt`?**

Argument for: roster and config drift is exactly the kind of silent change the
ledger exists to catch.

Argument against: `agents.md` changes whenever an agent is claimed or released —
far more often than a drop. Per-drop hashing may be too coarse, and a ledger that
fails on every sweep trains you to ignore the one test that catches real drift.

The honest alternative is treating the roster like leases: committed but
unledgered. `WALL_STANDARDS.md` currently puts it **in** the ledger. Low
confidence.

**7. Does `.wall/` live in the MAX3 repo, or its own repo?**

Inside MAX3 is simpler to install and co-locates the audit trail with the code it
describes. A separate repo makes the cross-repo budget view honest but adds a
second thing to keep in sync. Recommendation: start inside MAX3, split if a
second project appears. Easier to choose now than to migrate the ledger later.

---

## Blocking: routing and gates

**8. Fast-track destination — straight to main, or auto-merge PR?**
Straight to main is faster and fewer minutes. Auto-merge PR keeps a uniform audit
surface and survives branch protection cleanly. `max3-docs-push` currently merges
to main.

**9. Must an arc close with a drop, or can arcs close without shipping?**
Determines whether `DROP_PROTOCOL.md` §5 fires on every arc completion.

**10. Researcher network access.** The original outline has researchers searching
GitHub and the internet. The stated operating preference is local-only without
permission. Needs an explicit allowlist, or researchers are scoped to repo and
local docs. **Decide before the first run.**

---

## Blocking: cost shape

**11. Builder model tiering — keep all-Opus, or tier by task class?**
All-Opus builders are roughly 3–5× a tiered scheme, and builders are the dominant
cost line. Budget is advisory so this will not stop anything, but the history you
accumulate will be dominated by whichever choice is in place when you start.
Decide before real data lands.

**12. Where do budget limits come from?**
`.wall/config/wall.json` currently holds them as static numbers. Alternatives: a
live quota call, or manual monthly entry. Affects how honest the Ledger tab is.

---

## Non-blocking, worth deciding

**13. Name binding — role slot or agent instance?**
Binding to a role slot means builder-1 is always Desmond, which is better for
cross-session reporting and for talking about the crew naturally. Binding to the
instance is more honest that subagent invocations share no memory. Current
implementation binds to the instance and reuses names after release.

**14. What serves `127.0.0.1:8123`?** A `.bat`, a PowerShell one-liner, something
in the app? Needed to fold the server into the install adapter so the timer and
the server come up together.

**15. Frontend styling system.** Tailwind, CSS modules, styled-components? Decides
whether `frontend/theme/primitives.css` is useful or noise. The token layer in
`theme.css` works regardless.

**16. What are MAX3's actual screens?** `preview.html` invents plausible ones.
Real screens would test whether the type scale and density hold up.

---

## Settled during design

For the record, so they are not relitigated:

- Courier is a script, not an agent. A model consolidating the ledger could
  silently drop or paraphrase records; the audit trail must be reproducible.
- Maestro is the top-level session, not a subagent, because subagents cannot
  spawn subagents.
- Event shards stay **out** of the tree-integrity ledger. They change by design
  every minute.
- `derived/` is gitignored. Committing it conflicts across sessions every two
  minutes.
- Keys are identity; names are reusable labels.
- Budget is advisory. Nothing stops work.
- Foreman runs Sonnet 5.
