# ARCHITECTURE.md

Three pictures of the same system: what the parts are, how one item moves
through them, and why the loop closes without anything polling.

These are the shape, not the contract. The contracts live in
`docs/EVENT_SCHEMA.md` (records), `docs/AGENT_ROSTER_SPEC.md` (roles and
authority) and `docs/WORKFLOW.md` (execution). Where a diagram and a contract
disagree, the contract is right.

---

## 1. Components

Four planes, and they do not overlap. **Cognition** is everything a model does.
**Capture** is code that writes records. **Consolidation** is code that reads
records and produces derived state. **Presentation** is a static file and a
local server. Only the cognition plane costs money, and nothing in it is
allowed to write derived state.

```mermaid
flowchart TB
    Human([Human owner])

    subgraph Cognition
        Maestro[Maestro<br/>the top-level session]
        Builder[Builder]
        Integrator[Integrator<br/>a hat a Builder assumes]
        Reviewer[Reviewer]
        Researcher[Researcher]
        Architect[Architect]
        Adjudicator[Adjudicator]
        Foreman[Foreman<br/>judgment over consolidated state]
    end

    subgraph Capture
        Hooks[Session hooks<br/>run start / run end / tool use]
        Shards[(.wall/events/<br/>per-session shards)]
    end

    subgraph Consolidation
        Courier[courier.py<br/>merge - order - render]
        Shipper[shipper<br/>isolated-index push]
        Derived[(.wall/derived/<br/>ledger - wall.json - heartbeat)]
        Branch[(telemetry branch)]
    end

    subgraph Presentation
        Server[local server<br/>127.0.0.1, no-cache]
        Wall[wall.html]
    end

    Human -->|intent| Maestro
    Maestro -->|dispatch| Builder
    Maestro -->|dispatch| Reviewer
    Maestro -->|dispatch| Researcher
    Maestro -->|question| Architect
    Maestro -->|question| Adjudicator
    Builder -->|slot frees| Integrator
    Builder -.->|every run| Hooks
    Integrator -.-> Hooks
    Reviewer -.-> Hooks
    Researcher -.-> Hooks
    Hooks --> Shards
    Shards --> Courier
    Courier --> Derived
    Courier --> Shipper
    Shipper --> Branch
    Derived --> Server
    Server --> Wall
    Wall --> Human
    Derived --> Foreman
    Foreman --> Maestro
```

Two edges are load-bearing by their absence. No agent writes `Derived` - not
even the Foreman, which **reads** consolidated state and reports judgment back
to Maestro; if an agent could write it, the ledger would stop being
reproducible. And nothing in `Presentation` reaches back into `Cognition`: the
wall is a mirror, so a broken wall cannot stop work, and a stalled crew cannot
fake a healthy wall.

---

## 2. One item's journey

Including the two steps that are easy to leave out of a diagram and expensive to
leave out of a system: a question that blocks part of the work, and the
transplant that turns a finished working copy into a merged change.

```mermaid
sequenceDiagram
    actor Owner
    participant M as Maestro
    participant B as Builder
    participant A as Adjudicator
    participant H as Hooks
    participant CI as Checks
    participant C as Courier

    M->>B: dispatch: key, acceptance, file surface
    H-->>C: run_start
    B->>B: build within the declared surface
    B->>M: question: ambiguity blocks part of the work
    H-->>C: question_raised, item blocked
    M->>A: route the question
    A-->>M: ruling
    M->>M: write docs/decisions/DEC-NNNN.md
    M-->>B: answer
    H-->>C: question_answered, item unblocked
    B->>M: unit complete, gates green in the working copy
    H-->>C: run_end with usage from the harness

    Note over M,B: single pull-request slot frees
    M->>B: assume Integrator: rebase, regenerate, prove, gates LAST
    B->>CI: draft pull request
    CI-->>B: check runs
    B->>M: green - names the check that gates the merge
    M->>CI: read the check directly, then merge
    H-->>C: item_shipped with the merged number
    C-->>Owner: wall reflects merged, not in CI
```

The last two exchanges are the ones that get skipped under time pressure.
Maestro reads the check rather than accepting the report, because a reduced or
draft-scoped run can be green and not be the gate. And the shipping record fires
**at merge**, not at bookkeeping time - otherwise the wall keeps claiming an
open pull request that has already merged, and the next unrelated change
inherits the resulting red.

---

## 3. The closed loop

Nothing polls. Agents are single-shot, so the loop is closed by a timer on one
side and by hooks on the other; the human sits inside it rather than beside it.

```mermaid
flowchart LR
    Timer[machine timer<br/>one per machine] --> Courier[courier run-once]
    Courier --> Derived[(derived snapshot<br/>+ heartbeat)]
    Derived --> Wall[wall.html]
    Wall --> Read{Owner or Maestro<br/>reads the wall}
    Read -->|work to do| Dispatch[dispatch an agent]
    Read -->|nothing to do| Idle[no model calls]
    Dispatch --> Run[agent run]
    Run --> Hooks[hooks write records]
    Hooks --> Shards[(event shards)]
    Shards --> Courier
    Run -->|transition| Courier
    Idle --> Timer
```

Three properties worth naming:

- **The timer is the fallback, not the driver.** Dispatch, completion and merge
  transitions trigger a snapshot directly, because the wall was watched live
  during the reference deployment's first wave and course-corrected the work
  twice mid-flight. A two-minute-stale wall is a wall that gets glanced at
  instead of used.
- **The idle path costs nothing.** A loop with no work runs one Python process
  and makes zero model calls. A design where the loop itself is an agent
  inverts this and spends most when doing least.
- **The heartbeat is what makes the loop honest.** It is written on every run,
  successful or not, and the wall renders its age. Without it a dead timer and a
  quiet project produce the same picture, and the picture is a lie.
