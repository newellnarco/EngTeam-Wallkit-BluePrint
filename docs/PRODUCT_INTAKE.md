# PRODUCT_INTAKE.md

How the workforce gets its product definition: through question and answer
with the driving engineer, at the start or injected mid-flight — and how it
**derives what already exists in a repo first** so the engineer is only ever
asked what nothing on disk can answer.

The contract this document exists to keep: the loop runs autonomously, and the
engineer's required inputs reduce to exactly two kinds —

1. **Effort variables** — how big the effort is allowed to be.
2. **Product clarification and specificity** — what is being built, made
   precise enough to author against.

Everything else the machine derives, asks once and records, or decides inside
its written authority. An intake answer, like every engineer answer, is
durable: it lands as a decision record and in the product brief, so the same
question is never asked twice across sessions.

---

## 1. The two input classes

### Effort variables (numbers, set once, changeable any time)

| Variable | Lands in | Default when unanswered |
|---|---|---|
| Wave scope (whole backlog / named arcs) | dispatch plan | Ask — never assumed (SESSION_LIFECYCLE Q1) |
| Role caps (builders / researchers / reviewers) | `.wall/config/wall.json` `role_limits` | Config ships a working set |
| Budget meters and period | `wall.json` `budget` | Advisory defaults; meters warn, never stop |
| Deadline / cadence expectations | wave brief | None — absence means "steady state" |

### Product definition (the Q&A domains)

Six domains, each a short question set. Together they are the initial product
requirements design; individually each can be answered, derived, or parked.

| Domain | What it pins down | Examples of what a question looks like |
|---|---|---|
| **Product requirements** | What the product does, for whom, and what done means at the product level | "Users and their top three jobs?" "What must v1 refuse to do?" |
| **Data security requirements** | Classification of the data handled, retention, boundaries data must not cross | "Does any user data leave the machine?" "What is secret vs merely private?" |
| **Hosting locations** | Where it runs: local-only, one box, a cloud region, a customer's premises | "Is local-first a requirement or a preference?" |
| **Technology choices** | Languages, frameworks, storage, the dependency policy | "Stdlib-only, or is a dependency with license X acceptable?" |
| **Architecture choices** | Process shape, boundaries, integration points, the contracts between components | "One process or several?" "What is the API surface of record?" |
| **End-user experience** | The surfaces users touch and the qualities they must have | "CLI, web, voice?" "What must never take more than a second?" |

## 2. Derive first, ask second

Before any question reaches the engineer, the intake pass reads the repo. On
an existing repository, most of the six domains are already answered by
artifacts nobody wrote for this purpose:

| Evidence read | What it derives |
|---|---|
| README, entry-point context doc (`CLAUDE.md` or equivalent) | Product requirements, naming, non-goals |
| Dependency manifests, lockfiles, language versions | Technology choices, dependency policy |
| CI workflows, deploy scripts, install adapters | Hosting locations, release shape |
| Existing architecture docs, module layout | Architecture choices |
| Security policy, secrets handling, network config, license file | Data security requirements |
| UI code, templates, CLI surfaces | End-user experience |
| `docs/decisions/` | Anything already ruled — **binding, not re-derivable** |

Three honesty rules govern a derivation, and they are the same rules findings
follow (researcher.md §3):

1. **Every derived answer cites its evidence** — file and line, doc section,
   config key. A derivation with no citation is a guess and becomes a question.
2. **Strong evidence records; weak evidence asks.** A lockfile pins the
   language version — record it. A README implying an audience — ask, with
   the inference offered as the default: *"README suggests X; confirm or
   correct."* The engineer confirms in one word instead of authoring from
   scratch.
3. **A derivation that contradicts a live decision goes to the Adjudicator**,
   never silently wins. The repo drifting from its own decision log is a
   finding, not a new truth.

On an **empty repository** nothing derives, so the six domains run as a plain
question round — that is the empty-repo runbook's step 2 made interactive, and
it is the one moment the engineer should expect a batch of questions rather
than a trickle.

## 3. Where answers land

```
engineer answer (or strong derivation)
  ├─ DEC-NNNN                      the durable ruling, searchable, supersedable
  ├─ docs/PRODUCT_BRIEF.md         the living product definition, one section
  │                                per domain, every line citing its DEC or
  │                                its derivation evidence
  └─ the Architect's design brief  arcs and stories are authored FROM the
                                   brief, so criteria inherit citability
```

The product brief is generated and maintained, not hand-curated: each section
states the current answer, its source (decision id or evidence citation), and
its open questions. The Architect designs from the brief; a story criterion
citing "PRODUCT_BRIEF §3" is citing a chain that ends at either a DEC or a
file-and-line derivation. A domain with open questions is marked open —
honest absence, never a fabricated default.

## 4. Injection — at the start or in progress

The engineer may add or change constraints at any time, not only at intake:

- **At start:** answers and unprompted constraints arrive together; anything
  volunteered is recorded exactly as if it had been asked for.
- **Mid-flight:** an injected constraint is an **amendment**
  (ITEM_AUTHORING §5): the Maestro records the decision, the brief updates,
  `doc_impact` names the affected arcs, in-flight stories on those arcs get
  the delta by re-dispatch, and untouched arcs never notice. An injection
  parks what it invalidates — never the wave.
- **Late answers:** a domain parked at intake unparks its dependent arcs when
  its answer lands (the waiting-tab flow, SESSION_LIFECYCLE §4). Work that
  never depended on it was never blocked.

## 5. Question mechanics

Intake questions ride the same machinery as every other engineer escalation —
one queue, one habit, one audit trail:

- Batched by domain, filed as `human_required` asks on the **waiting tab**;
  answered with `wall answer`, which writes `human_answered` + the DEC.
- Each question carries the derivation attempt: what was searched, what was
  found, the proposed default. The engineer rules; the crew does the staff
  work (SESSION_LIFECYCLE §4).
- Only what a domain blocks is parked. Product-requirement gaps park design;
  a hosting question parks only deploy-shaped arcs; the rest of the wave runs.
- **No answer is not an answer.** An unanswered domain stays open on the
  brief and its arcs stay parked — the loop never fills in the engineer's
  half of the conversation.

## 6. Cross-references

- `docs/TEMPLATE_INTAKE.md` — the per-template question sets this discipline
  drives (required + probes, worked examples across four project shapes)

- `docs/diagrams/AGENT_TOPOLOGY.md` — where intake sits in the node/edge map
- `docs/SESSION_LIFECYCLE.md` — startup questions, the human queue, escalation
- `docs/ITEM_AUTHORING.md` — how brief sections become citable criteria
- `README.md` — empty-repo runbook step 2 (the non-interactive floor of this)
- `.claude/agents/researcher.md` §3 — the findings shape derivations follow
