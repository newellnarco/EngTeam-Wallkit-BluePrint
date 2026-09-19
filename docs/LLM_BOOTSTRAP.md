# LLM_BOOTSTRAP.md

The blueprint an LLM session follows to establish and run this entire process
in a repository **on its own** — with the local user-engineer asked only to
**run** the steps the session must not run itself, and to **verify** the
results the session cannot see. If you are an LLM session reading this in a
repository that contains the kit: this is your day-zero procedure. Work it top
to bottom; every phase ends with an exit condition you can check.

**The order is the rule (user direction).** Guardrails, scaffolding,
metrics, quality and security machinery, and the requirements and
architecture come FIRST — in a new repo or an existing one — before building
or delivering ANY product line of code. The phases below are that order, and
Phase 4 is gated on it: a session that starts writing product code with the
foundation half-laid has not saved time, it has borrowed it at interest from
every future wave.

Two standing rules frame everything below:

- **You ask; you do not assume.** Every "ASK THE ENGINEER" block below is a
  real stop: present the exact command, what it will create, and what you need
  back. No answer is not an answer (SESSION_LIFECYCLE.md section 4).
- **You derive; you do not re-ask.** Anything the repo, the config or the
  decision log already answers is not a question (PRODUCT_INTAKE.md section 2).
  Record what you derived, with the evidence cited.

---

## Phase 0 — Orient (no writes)

1. Read, in order: `README.md` (the path table), `.claude/MAESTRO.md` (you are
   the Maestro — the session, not a subagent), `docs/SESSION_LIFECYCLE.md`,
   `docs/WORKFLOW.md`, `docs/RECONCILIATION.md` Part 2 (the measured failure
   classes — each one cost a real wave something).
2. Determine which runbook applies: empty repository (README empty-repo
   runbook) or existing project (adoption runbook). The test is whether the
   repo already has context documents by function — entry point, rules,
   failure registry, checklist, standards, decision log.
3. Verify your identity setup: which committer identity does the host require?
   Confirm per-invocation identity only (`git -c`), never `git config` (G1).

**Exit:** you can state which runbook applies, what exists, and what is
missing — with file paths as evidence.

## Phase 1 — Lay the files down

1. Empty repo: copy the kit directories in, copy each template to the root and
   fill it via its question set (`docs/TEMPLATE_INTAKE.md`: required questions
   first, then probe for the unasked-but-important with your derivations as
   defaults) — never fill placeholders by guessing (`RULES.md` Part 1 is the one needing real thought —
   draft it and flag it for the engineer's confirmation rather than inventing
   hard rules unilaterally). Existing repo: run `/adopt inventory`
   then `/adopt map` — classify by function with evidence, pointer stubs over
   duplication, the three non-negotiable rules added to the host's own
   documents; duplicated rulebooks go through `/adopt consolidate` with the
   engineer ruling on conflicts.
2. Run the whole kit test suite if present, or `wall run-once` at minimum, and
   fix or report anything red before proceeding. You are the first user; a
   broken base is yours to catch now.
3. Commit the scaffolding as the base commit every future unit rebases onto.

> **ASK THE ENGINEER (verify):** show the filled `RULES.md` Part 1 (or the
> mapped rule additions) and the definition-of-done in `.wall/config/wall.json`
> for a yes/no/edit. These bind every future agent; they are the engineer's
> rules, drafted by you, never the reverse.

**Exit:** base commit exists; suite green; rules confirmed or explicitly
pending with a parked marker.

## Phase 2 — Start the machinery

1. `wall run-once` then `wall doctor` — both work with nothing installed.
2. Claim the roster for your first roles (`wall agents claim`).
3. Serve the wall: `wall serve` (binds `127.0.0.1` only, by design).

> **ASK THE ENGINEER (run):** the machine-wide timer is a **system mutation
> behind a consent gate you must not bypass**. Present exactly:
> `python3 tools/wall/wall.py install` (prints the full plan, creates
> nothing), then ask them to review the plan and run
> `... install --yes` themselves — or paste the plan output back to you and
> tell you to proceed. On a container/VM/cluster target, present the
> `docs/DEPLOYMENT_TARGETS.md` equivalent instead. Never schedule anything
> silently, and never work around a declined install — `wall run-once` from
> your own session loop is the honest degrade.

> **ASK THE ENGINEER (verify):** after the install, have them run
> `wall verify` (or run it yourself if you can) and confirm: timer alive,
> heartbeat fresh, registry sane. A heartbeat that cannot be read is a fail,
> never an ok.

**Exit:** wall live; `wall verify` clean, or the degrade path recorded.

## Phase 3 — Product intake

Run `docs/PRODUCT_INTAKE.md` exactly: derive the six domains from the repo
first with cited evidence; batch what remains into one question set on the
human queue (`human_required` asks; the engineer answers via `wall answer`).
Write the product brief; every engineer answer becomes a `DEC-NNNN`.

> **ASK THE ENGINEER (answer):** the effort variables — wave scope, role caps,
> budget — plus whichever of the six product domains (requirements, data
> security, hosting, technology, architecture, end-user experience) the repo
> could not answer. Offer your derivation as the default so a confirmation
> costs one word.

**Exit:** product brief exists; open domains are marked open and park only the
arcs that depend on them.

## Phase 4 — Author and run the first wave

> **THE FOUNDATION GATE.** Phase 4 does not open until the exit conditions
> of Phases 1–3 hold: rules confirmed, suite green, wall live (or its
> degrade recorded), intake's product brief written with the data-security
> domain answered or its arcs parked, and the Warden's corpus seeded from
> it. **No product story dispatches before this gate** — the first wave's
> product work waits behind any foundation item still missing, and building
> the missing item IS the wave until then.

1. As Maestro, dispatch the Architect with the brief; land the first arc and
   its citable stories (ITEM_AUTHORING.md). Import any existing board through
   `adapters/board_import.py` instead of re-authoring it.
2. Run the wave per `.claude/skills/wave/SKILL.md`: session-start SOP,
   dispatch on disjoint leases, mediated questions, serial integration through
   the one PR slot, merge authority yours alone, session-close SOP with the
   wave report.
3. First wave in a new org: keep it small — one arc, two or three stories —
   because its real product is the first entries in the failure registry.

> **ASK THE ENGINEER (verify):** the first merged PR. One review of the first
> unit calibrates every later one; ask for it explicitly.

**Exit:** first PR merged; wave report written; wall reflects reality.

## Phase 5 — Full implementation (the compounding layer)

In any order, as the project's needs surface them:

- **Graders:** wire external reviewer lanes via
  `.claude/skills/reviewer-integration/` (adding or removing a lane is an
  engineer decision; ask with the trigger-cost numbers).
- **Telemetry:** confirm shards + `doctor.json` ship on the timer
  (`wall ship`), so an off-box session can review the machine's health and
  file work items from evidence.
- **Rebalancing:** after two or three waves there are enough measurements to
  work `docs/CAPACITY_REBALANCING.md` — one knob per cycle.
- **Evaluations:** competing technology choices go through a recorded
  evaluation with a decision record and re-eval triggers, never a silent swap.
- **Learning:** every finding graduates — rule + test + checklist line in the
  same change. This is the mechanism by which wave N+1 starts smarter than
  wave N, and it is the part that must never be skipped to save time.

**Exit:** there is no exit. This phase is the operating state.

---

## The ask/verify ledger

Everything the engineer is ever asked to run or verify, in one place — if you
find yourself asking for something not on this list, check whether you are
about to bypass a boundary:

| Phase | Ask | Kind |
|---|---|---|
| 1 | Confirm drafted hard rules + definition of done | verify |
| 2 | Run `wall install --yes` after reading its printed plan | **run** |
| 2 | Confirm `wall verify` is clean | verify |
| 3 | Effort variables + unanswered product domains | answer |
| 4 | Review the first merged PR | verify |
| 5 | Approve adding/removing a reviewer lane; widen researcher network; raise caps/budgets | answer |
| any | Grant a data use or access the Warden routed up; overrule a Warden block (in writing) | answer |
| any | The six escalation classes (SESSION_LIFECYCLE.md section 4) | answer |

Everything else, you do — and record.
