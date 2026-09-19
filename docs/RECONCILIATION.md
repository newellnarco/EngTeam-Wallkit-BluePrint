# RECONCILIATION.md

The kit was designed blind — no access to the MAX3 tree — and says so. This
document closes that loop: every open question answered against the real tree
(2026-09-19, main at `f6b07ef`), plus the gap analysis from the first live
agent wave run on MAX3 (2026-09-18/19: PRs #1647–#1655, six built units, five
merged, one wave stopped by the owner). Everything here is measured, not
argued; each lesson cites the incident that taught it.

---

## Part 1 — the 16 open questions, answered

### Blocking: repo structure (Q1–Q5)

**Q1. `tools/` shipped or repo-only?** Both — MAX3's deployment *is* a clone.
`pull-latest.bat` hard-resets `C:\Dev\MAX3` to `origin/main`, and the box runs
`tools/max3_services.py`, `tools/board_wall_server.py` etc. directly from the
tree. So `tools/wall/` is correct as designed, and anything placed there is
live on the box one auto-pull after merge.

**Q2. `pyproject.toml` scope?** One root `pyproject.toml`, package `max3`,
code under `backend/`. The wall integrity test lands in
`backend/tests/system/` beside its siblings, as designed.

**Q3. `TREE_INTEGRITY_LEDGER.txt` format?** **The file no longer exists.** It
was collapsed into `MANIFEST.sha256` (derived from `git ls-files`, auto-synced
by a pre-commit hook, checked by `tools/regen_manifest.py --check` and
`test_install_hygiene`). Consequence: Q6's dilemma dissolves — every tracked
file is in the manifest automatically and the manifest regenerates per commit,
so "does X belong in the ledger" is no longer a decision anyone makes.

**Q4. Workflow triggers?** `ci.yml` does NOT use `paths-ignore`. It has a
`Detect docs-only change` job plus `tools/ci_tier_scope.py` tier scoping
(draft heads run unit+system; `ready_for_review` fires the full pyramid), and
— as of PR #1655 — static literal job names plus a `Backend pyramid (all
tiers, all shards)` attestation job whose *conclusion* is the merge gate. The
kit's `paths-ignore` + no-op-companion design is **superseded**: the existing
mechanism already achieves zero-wasted-minutes routing and survived five
recurrences of the skipped-job-name failure class (F-CI-025) to get there.
FAST_TRACK.md's *classification* logic stays (it is how `wall classify`
routes agent work); its *CI plumbing* section is replaced by "defer to the
host repo's CI scoping".

**Q5. `DROP_PROTOCOL.md` §5?** The file exists but drops are historical: since
2026-06 MAX3 ships as named PR arcs tracked on the board
(`docs/project/board_state.json` + fragment files), squash-merged one at a
time. The kit's `drop_shipped` event becomes `item_shipped` carrying the
merged PR number. Arcs close without drops (Q9: **yes**).

### Blocking: ledger boundary (Q6–Q7)

**Q6.** Dissolved by Q3 (manifest auto-sync covers all tracked files).

**Q7. `.wall/` in-repo or own repo?** In the *target* repo — but with one
correction learned the hard way: **event shards must not be committed on the
development branch.** MAX3 development happens in cloud sessions pushing a
single designated branch through a one-PR-at-a-time pipeline; high-churn
committed shards would ride every PR and conflict constantly (the F-DERIVED-001
class that board fragments were invented to kill). Instead the kit adopts
MAX3's proven **isolated-branch telemetry pattern** (`ship_agent_status.py`,
verified in production during the first wave): shards live gitignored in the
working tree; the courier ships snapshots to a dedicated `wall-events` branch
via an isolated `GIT_INDEX_FILE` (tree and index untouched); the box's courier
fetches freshness-guarded. Local reproducibility is preserved (merge is still
idempotent on `event_id`); the audit trail is durable on the isolated branch;
no PR ever carries a shard.

### Blocking: routing and gates (Q8–Q10)

**Q8. Fast-track destination?** A PR, never straight to main. MAX3's standing
policy is every change rides a PR opened as `newellnarco`, draft → CI → merge;
docs-only PRs already get the scoped fast pass. "Fast-track" = the docs-only
PR path, merged by the coordinator the moment its (scoped) checks are green.

**Q9.** Yes — arcs close without shipping a drop (see Q5).

**Q10. Researcher network access?** Config-gated allowlist, default
repo-plus-local-docs. In MAX3 cloud sessions, outbound HTTPS goes through the
managed proxy and `WebSearch`/`WebFetch` exist — so the kit exposes
`research.network: "none" | "allowlist" | "session-default"` in
`wall.json`, default `none`, and the roster doc says the Researcher must state
in its findings which mode it ran under. On the box: local-only, matching
MAX3's SSRF-allowlist worker convention.

### Blocking: cost shape (Q11–Q12)

**Q11. Builder tiering?** **Tier.** Measured in the first wave: all-Opus
builders ran 400–720K tokens per unit (six units ≈ 3.0M subagent tokens).
Mechanical work (doc sweeps, fragment filing, board flips, template fills)
does not need Opus. Maestro tags task class at dispatch; the ledger's
`model_requested`/`model_used` split already handles safeguard routing —
which is real: Fable-requested runs were served as configured in this wave,
but the harness reports `last_served_model` separately for exactly this
reason.

**Q12. Budget source?** Static numbers in `wall.json` for limits; **actuals
come free from the harness**: every subagent completion notification carries
`subagent_tokens`, `tool_uses`, `duration_ms`. The dispatcher records them
into the `run_end` event. No estimation needed for the dominant line.

### Non-blocking (Q13–Q16)

**Q13. Name binding?** Instance (current implementation). Keep.

**Q14. What serves :8123?** In MAX3: `tools/board_wall_server.py` inside the
MAX3-Wall Windows service (exact-allowlist relay, `NO_CACHE_FILES`). The kit's
standalone server must copy its two safety properties: bind `127.0.0.1`
explicitly, and no-cache headers on the polled JSON. For empty repos the kit
ships its own stdlib server; the install doc says "if the host repo already
serves a wall, register the kit's files with it instead."

**Q15. Styling?** MAX3 is plain CSS with theme tokens (WarGames / Tron /
JARVIS / MAX themes), no Tailwind. `theme.css` + `primitives.css` are the
right shape. Keep.

**Q16. Real screens?** 16+ panels; the wall is standalone HTML served beside
them (STORIES / INTELLIGENCE / SCOUT / AGENTS tabs today). The kit's wall is
the generalization of that page.

---

## Part 2 — gap analysis: what the live wave proved, corrected, and added

The first wave ran the predecessor roster (orchestrator / max-developer /
max-researcher) for ~7 hours on MAX3. Five PRs merged, ~230 new tests, every
review finding closed or refuted with proof. These are the deltas the kit must
encode; each is a measured incident, not a preference.

### Confirmed by the wave (design validated)

- **G0a. Maestro-is-the-session is not a choice, it is a constraint.** The
  spawned orchestrator found the `Agent` tool disabled inside subagents and
  could only hand a dispatch plan back. The kit's §"Maestro is the session"
  is exactly right — and needs the *degrade path* written down: an
  orchestrator without spawn ability surveys, vets, exports status, and
  returns a dispatch plan (unit · key · acceptance · disjoint file surfaces ·
  merge order); the parent session executes it. A plan reported as a dispatch
  is the failure this prevents.
- **G0b. Evidence over self-report works.** A builder's own draft-CI report
  was superseded twice by reading check runs directly; CodeRabbit/Copilot
  quota exhaustion was "named, not waited on" per the metered-lane rule; the
  attestation job's first live run proved the renderer claim the design
  refused to assume.
- **G0c. Script-not-agent for bookkeeping works.** Status streaming ran all
  night as one Python file pushing an isolated branch, zero model calls.

### Corrections (kit assumptions the wave falsified)

- **G1. Shared working tree is worse than the lease model assumes —
  *identity* is shared too.** `git config user.*` is repo-global: one agent's
  config write changed another agent's in-flight commit authorship
  (observed on PR #1652's first commit). Rule: **agents never write
  `git config`; every commit uses per-invocation `git -c user.name=... -c
  user.email=...` or `GIT_AUTHOR_*`/`GIT_COMMITTER_*` env.** The leases
  design covers *files*; this covers the tree's *shared mutable git state*.
- **G2. The shared scratchpad is shared mutable state.** A sibling overwrote
  another agent's `commitmsg.txt` between write and use; the commit briefly
  carried the wrong unit's message. Rule: **all agent temp files are keyed by
  agent key** (`commitmsg-<key>.txt`). Belongs beside the lease rule.
- **G3. Subagents must not self-schedule.** `send_later`-style check-ins
  registered by a subagent fire into the *parent* session — the builder that
  scheduled one waited forever while its wake-up woke the coordinator
  (observed on PR #1654: draft CI green for 35 minutes before anyone acted).
  Rule: only the Maestro schedules; subagents end their run and rely on the
  parent's event loop. This is the same "agents don't persist" idea applied
  to timers.
- **G4. Worktrees are the right isolation but have a venv seam.** Builder
  worktrees have no `.venv`, so any guard or test resolving `<repo>/.venv`
  produces phantom failures (7 recurring test failures chased independently
  by three agents until documented). Rule: the kit's environment doc names
  this; tests resolve interpreters by injection, never from the checkout; the
  dispatch brief lists known worktree phantoms.
- **G5. The single-PR pipeline needs an explicit *transplant* procedure —
  and it is the wave's core choreography, entirely absent from the kit.**
  Six units built in parallel worktrees, but one branch and one PR slot means
  each unit is later rebased onto moved `main`, derived files regenerated by
  tooling (never hand-merged), a safety proof run before force-with-lease
  (path-filtered diff of the designated ref vs main must show only merged
  content), budget/system gates re-run LAST, then draft PR. The wave executed
  this five times; two compactor-consumed-fragment conflicts and one
  placeholder-lease rejection were handled exactly as the written procedure
  predicted by the third run. The kit gets it as WORKFLOW §"Integration".
- **G6. Gates run LAST.** A worktree unit has no CI between its commit and
  transplant; a gate run before the final edit proves nothing. One unit
  shipped a stale generated file exactly this way, then encoded the rule.
- **G7. Review-lane behavior needs a written posture per lane.** Measured
  across #1652–#1655: truncated-diff reviewers report their own truncation
  boundary as a defect (two refutations of the same false "file is
  truncated" finding — a registered failure class); quota-limited lanes must
  be named-not-waited-on; findings are verified before accepting *or*
  declining, and a suggested fix may be declined for a proven better one
  (three findings closed that way, each with a counterfactual test). The
  Reviewer section gains this; so does a new "hosted reviewer lanes" page.
- **G8. Review-thread ownership must be exclusive.** The coordinator and a
  builder both answered the same Gemini thread within minutes (same shared
  GitHub identity — double-reply observed on #1655). Rule: the unit that owns
  the PR owns its threads; the coordinator takes a thread only by telling the
  unit first. One writer per conversation, same as decisions.
- **G9. A merge can outrun its own bookkeeping.** A PR merged before its
  board fragments were compacted left the wall claiming "in CI" on a merged
  PR, and the *next unrelated* PR inherited the resulting red lint (observed
  between #1654 and #1655). The kit's courier gains a reconcile check:
  item state claiming an open PR that GitHub says is merged/closed is an
  integrity flag, and the shipping event flips state at merge time, not at
  compaction time.
- **G10. The context-budget ratchet is real and nearly bit four units at
  once.** The host repo's reviewer-prompt budget sat 53 chars from a hard
  failure while three parked units each carried new rules into the counted
  sections. Every unit's definition of done gains: "if you extend a
  budget-counted context doc, run its budget check and record the measured
  number." Generalized: **standards files that feed model prompts carry a
  measured budget and a headroom warning**, and the kit's doctor reports it.

### Additions (new roles / seams the wave showed are missing)

- **G11. The Integrator.** Between Builder and merged there is a distinct
  job: rebase, mechanical conflict resolution by regeneration, safety proof,
  budget re-check, PR authoring, review-thread driving. The wave ran it by
  re-invoking each builder with a long transplant brief — workable, but the
  procedure was re-sent five times and drifted (LOGGING.md's location was
  mis-stated once). The kit makes it a first-class role sheet
  (`integrator.md`) a builder *assumes* when the slot frees — same agent,
  explicit hat, one written procedure.
- **G12. Coordinator merge authority is load-bearing and stays human-side.**
  Only the top-level session flips ready and merges; builders report green
  and stop. This held all wave and caught two would-have-been-early merges
  (DRAFT-scoped checks that read green but were not the pyramid).
- **G13. Handoffs are documents, not paraphrases.** Every re-brief this wave
  was hand-written and each drifted slightly. The kit ships handoff templates
  (`docs/handoffs/`): dispatch brief, finding routing, transplant order,
  wave report — with the fields that proved load-bearing (file surface,
  out-of-scope ban, gates-last, identity rule, report shape).
- **G14. The status stream is part of the loop, not decoration.** The owner
  watched the wall's AGENTS tab live and course-corrected twice mid-wave.
  Courier's snapshot must therefore update on every dispatch/completion/merge
  transition (event-driven), with the timer as the fallback — not the other
  way around.

---

## Part 3 — what this kit is, restated after reconciliation

A standalone, dependency-free scaffold that drops into an empty repo (or an
existing one) and gives a Claude Code session everything the first wave had
to improvise: a role roster with written authority boundaries, an event
ledger with integrity checking, a live wall, a closed-loop timer, dispatch /
handoff / transplant procedures with the measured failure classes already
encoded, and the context documents (rules, failure registry, ship checklist,
decision log) that make the next wave start where the last one ended.

MAX3 is the reference deployment and first guinea pig.
