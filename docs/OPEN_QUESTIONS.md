# OPEN_QUESTIONS.md

What is still undecided, and what has been decided so it is not relitigated.

Settled entries are one line each, pointing at the record. The reasoning lives
in `docs/RECONCILIATION.md` Part 1 and, for the ones with lasting consequences,
in `docs/decisions/`.

---

## Open

Nothing. The sixteen questions the kit was designed around are all answered.

When a new one appears, add it here - the question, what it blocks, and how it
would be answered - and **resolve it before it becomes a convention by
default**. An unanswered question that work quietly routes around is how an
assumption ends up built into six places at once.

Moving one out: write the one-line answer into Settled below, pointing at the
record, and if it has lasting consequences give it a file in
`docs/decisions/`.

---

## Settled

### Repository structure

1. **Is `tools/` shipped, or repository-only?** Shipped - the reference
   deployment *is* a clone, and the box runs scripts straight from the tree, so
   `tools/wall/` is correct **and** is live one pull after merge.
   RECONCILIATION Q1; `WALL_STANDARDS.md` section 1.
2. **Does the root package manifest scope one directory or the whole
   repository?** One root manifest, source under a single package directory, so
   the wall's system test lands beside its siblings in the system tier.
   RECONCILIATION Q2.
3. **What is the integrity ledger's format?** There is no ledger file any more -
   it was collapsed into a manifest derived from the tracked file list and
   auto-synced per commit. RECONCILIATION Q3; `WALL_STANDARDS.md` section 2.
4. **What are the workflow triggers?** No `paths-ignore`. A docs-only detect job
   plus tier scoping by draft state, static literal job names, and an
   attestation job whose conclusion is the merge gate. The kit defers to it.
   RECONCILIATION Q4; `FAST_TRACK.md`.
5. **Does a release protocol fire per arc?** Releases are historical; work ships
   as named pull-request arcs. The shipping event carries the merged pull-request
   number. RECONCILIATION Q5; `WALL_STANDARDS.md` section 4.

### The ledger boundary

6. **Do configuration and the roster belong in the integrity ledger?**
   Dissolved by 3 - every tracked file is covered automatically, so nobody
   decides. RECONCILIATION Q6.
7. **Does `.wall/` live in the target repository, and are shards committed?** In
   the target repository, but shards are **gitignored** and ship to an isolated
   telemetry branch via an isolated index. No pull request ever carries a shard.
   RECONCILIATION Q7; `docs/decisions/DEC-0004.md`.

### Routing and gates

8. **Fast-track destination - default branch, or pull request?** A pull request,
   always. Fast-track is a route, not a destination. RECONCILIATION Q8;
   `docs/decisions/DEC-0005.md`.
9. **Must an arc close with a release?** No. Arcs close without shipping
   ceremony. RECONCILIATION Q9.
10. **Researcher network access?** Config-gated, default `none`, with
    `allowlist` and `session-default` available - and the Researcher states
    which mode it ran under in its findings. RECONCILIATION Q10;
    `docs/decisions/DEC-0006.md`.

### Cost shape

11. **Builder model tiering?** Tier by task class. Measured: all-strongest-model
    builders ran 400,000 to 720,000 tokens per unit, roughly three million
    across six units. RECONCILIATION Q11; `docs/decisions/DEC-0007.md`.
12. **Where do budget numbers come from?** Limits are static configuration;
    **actuals come free from the harness** - tokens, tool uses and duration
    arrive with every completion and are recorded into the `run_end` event.
    Nothing is estimated for the dominant line. RECONCILIATION Q12;
    `docs/decisions/DEC-0008.md`.

### Non-blocking

13. **Name binding - role slot or instance?** Instance. Subagent invocations
    share no memory, and slot binding presents continuity that does not exist.
    RECONCILIATION Q13; `docs/decisions/DEC-0009.md`.
14. **What serves the wall?** The host's server if it already has one - register
    the kit's files with it; otherwise the kit's stdlib server. Either way, bind
    `127.0.0.1` explicitly and send no-cache headers on the polled JSON.
    RECONCILIATION Q14; `INSTALL.md`.
15. **Frontend styling system?** Plain CSS with theme tokens. `theme.css` plus
    `primitives.css` is the right shape; keep. RECONCILIATION Q15.
16. **What are the real screens?** Sixteen or more panels, with the wall served
    beside them as standalone HTML. The kit's wall is the generalization of that
    page. RECONCILIATION Q16.

### Settled during design

- Courier is a script, not an agent - a model in the merge path can silently
  drop or paraphrase records, and the audit trail must be reproducible.
  `docs/decisions/DEC-0001.md`.
- Maestro is the top-level session, not a subagent, because subagents cannot
  spawn subagents. Confirmed live. `docs/decisions/DEC-0002.md`.
- Derived output is gitignored. Committing it conflicts across sessions every
  sweep.
- Keys are identity; names are reusable labels. `docs/decisions/DEC-0003.md`.
- Budget is advisory. Nothing stops work.
- One machine-wide timer, not one per repository.
  `docs/decisions/DEC-0010.md`.

### Settled by the first live wave

- Evidence outranks self-report, including an agent's report of its own checks.
  `docs/decisions/DEC-0011.md`.
- The Integrator is a first-class role - a hat a builder assumes - because the
  transplant procedure drifted every time it was re-typed.
  `docs/decisions/DEC-0012.md`.
- Agents never write repository-level version-control configuration, and every
  agent temp file is keyed by agent key. Both were observed corrupting a
  sibling's work.
- Subagents do not schedule. A check-in registered by a subagent fires into the
  parent session.
- Gates run last, after the final edit.
- Merge authority stays with the coordinator, and the green check's **name**
  must be the one branch protection requires.
- Review threads have exactly one owner.
- Prompt-loading documents carry a measured budget and a headroom warning.
