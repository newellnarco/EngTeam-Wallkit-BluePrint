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
        Hooks[Session hooks<br/>run end / tool use]
        CLI[wall CLI writers<br/>run-start - run-end - retro - rebalance<br/>finding - story-filed - verify-request - verified<br/>each validates before it writes]
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
        Summary[wall summary<br/>CLI digest]
        MCP[mcp_server.py<br/>stdio, role-gated<br/>DEC-0019]
        Editors([VS Code / Cursor /<br/>Claude Code])
    end

    Human -->|intent| Maestro
    Maestro -->|dispatch| Builder
    Maestro -->|dispatch| Reviewer
    Maestro -->|dispatch| Researcher
    Maestro -->|question| Architect
    Maestro -->|question| Adjudicator
    Builder -->|unit complete| Integrator
    Builder -.->|every run| Hooks
    Integrator -.-> Hooks
    Reviewer -.-> Hooks
    Researcher -.-> Hooks
    Maestro -->|"run-start: cap check<br/>retro - rebalance - finding"| CLI
    Hooks --> Shards
    CLI --> Shards
    Shards --> Courier
    Courier --> Derived
    Courier --> Shipper
    Shipper --> Branch
    Derived --> Server
    Server --> Wall
    Wall --> Human
    Derived --> Summary
    Derived --> MCP
    MCP --> Editors
    Editors --> Human
    Human -->|answer / enqueue| MCP
    Wall -.->|"dispatch: enqueue directives<br/>(probe-gated, DEC-0030)"| Maestro
    Derived --> Foreman
    Foreman --> Maestro
```

The **Capture** plane has two writers. The hooks record what a run did; the
`wall` CLI writers record what the Maestro and the owner decided, and each one
refuses a record that breaks its rule before anything reaches a shard:
`run-start` refuses a run past `role_limits[role]`, `retro` refuses a
retrospective that leaves a Patron input unaddressed or carries more than
three diffs, `rebalance` refuses a second knob in one cycle. The courier then
flags what was written around them (`over_cap`, `dropped_findings`,
`verify_overdue`). The full command list is `docs/INSTALL.md` "CLI surface".

Two edges are load-bearing by their absence. No agent writes `Derived` - not
even the Foreman, which **reads** consolidated state and reports judgment back
to Maestro; if an agent could write it, the ledger would stop being
reproducible. And `Presentation` reaches back into `Cognition` through exactly
one narrow door: the wall's dispatch buttons (EXECUTE, the blocked drill-in,
the POSTURE regime controls) ENQUEUE directives onto the host queue for the
crew to consume — the human's existing verbs carried over http, gated on the
same-origin health probe, so a wall served without its host stays read-only.
The wall still writes no state of its own and can stop nothing: a broken
wall cannot stop work, and a stalled crew cannot fake a healthy wall.

The three presentation surfaces are one fold worn three ways (DEC-0018):
`wall.html`, `wall summary` and the MCP server's `wall_status` all derive
from the same `Derived` snapshot — none holds facts of its own. The MCP
server is the ENGINEER'S SEAT made portable (DEC-0019), not a new role:
its `answer`/`enqueue` verbs are the human's existing verbs carried over
stdio into whatever editor the human is sitting in, and an agent-role
attachment gets the reads only.

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

    M->>C: wall run-start: role cap checked, run_start written
    Note over M,C: past role_limits the run is refused (exit 1)<br/>unless an over-cap reason is recorded
    M->>B: dispatch: key, acceptance, file surface
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

    Note over M,B: its own PR, beside others on disjoint leased surfaces (DEC-0016)
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
    Timer[machine timer<br/>one per machine] --> Courier[courier run-once<br/>flags: over_cap - dropped_findings<br/>verify_overdue]
    Courier --> Derived[(derived snapshot<br/>+ heartbeat)]
    Derived --> Wall[wall.html]
    Wall --> Read{Owner or Maestro<br/>reads the wall}
    Read -->|work to do| Start[wall run-start<br/>role cap check]
    Start -->|"under cap, or over-cap reason recorded"| Dispatch[dispatch an agent]
    Start -->|over cap| Refused[refused, exit 1]
    Read -->|nothing to do| Idle[no model calls]
    Dispatch --> Run[agent run]
    Run --> Hooks[hooks write records<br/>or wall run-end]
    Hooks --> Shards[(event shards)]
    Read -->|a finding| Finding[wall finding - story-filed<br/>verify-request - verified]
    Read -->|wave close| Retro[wall retro<br/>validated retro_held]
    Retro --> Rebalance[wall rebalance<br/>one knob per cycle]
    Finding --> Shards
    Retro --> Shards
    Rebalance --> Shards
    Shards --> Courier
    Run -->|transition| Courier
    Idle --> Timer
```

The learning half of the loop writes through the same validated commands:
a retrospective is refused while any Patron `retro_input` is unaddressed or
when it carries more than three diffs, a second knob before the next
`retro_held` is refused, and a second reversal of the same knob is routed to
the Adjudicator. What gets written around the commands is caught on the next
sweep: the courier flags a run over its role cap, a finding with no filed
story or route, and a verification request left unanswered.

Three properties worth naming (a fourth, the validated writers, is above):

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
