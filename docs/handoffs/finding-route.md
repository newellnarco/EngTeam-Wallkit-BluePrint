# Finding route -- TEMPLATE

> **G13.** A routed question is a document. Paraphrasing it is how the class,
> the scopes and the blocked criteria get lost.
>
> Use this for both shapes that come back from a unit: an **open question**
> (the unit is stuck on an ambiguity) and a **finding** (the unit saw something
> outside its scope and correctly did not fix it).

---

## 1. Provenance

| Field | Value |
|---|---|
| Kind | `question` / `finding` |
| Raised by | agent key + name |
| Item / run | `item_id`, `run_id` |
| `trace_id` | carry it through every hop, or the multi-agent chain is invisible |
| Raised at | |

## 2. The question or finding

**Statement (verbatim from the unit, not summarised):**

**Evidence:** file and line, command output, check-run name -- whatever grounds
it. A finding with no evidence is an impression.

## 3. If it is a question

| Field | Value |
|---|---|
| Ambiguity class | `missing_requirement` / `conflicting_decisions` / `undefined_interface` / `unclear_acceptance` / `unspecified_edge_case` / `dependency_unknown` |
| Blocked criteria | AC-n, AC-n |
| `dependent_scope` | files the answer could change |
| `independent_scope` | files it cannot |
| Unit's `outcome_hint` | `partial` / `blocked` |
| **Maestro's decision** | `partial` if the scopes are file-disjoint, `blocked` if they overlap -- **the dispatcher decides, not the unit** |

A `blocked` unit releases its slot. A `partial` unit keeps it. Collapsing
`partial` into `blocked` wastes a builder slot every time anyone asks anything.

## 4. Decision log searched FIRST

Before spending a researcher. A hit answers at near-zero cost and is the
project's most honest "tokens saved" number (`EVENT_SCHEMA.md` section 5).

| Field | Value |
|---|---|
| Searched | `docs/decisions/` -- terms used: |
| Result | `hit: DEC-____` / `miss` |
| If hit | log `question_answered` with `source: decision_log` and stop here |

## 5. Routing

```
Researcher -> second researcher pass -> Architect direct
           -> Adjudicator (if the answer conflicts with a live decision)
           -> the human queue
```

Escalation is **time-driven, not attempt-driven**. Every hop writes
`question_escalated` with a reason, so the trace shows the full path when
something took six hours.

| Hop | Default SLA | Dispatched at | Escalated at | Reason |
|---|---|---|---|---|
| Assignment after `question_raised` | 5 min | | | |
| Researcher first run | 10 min | | | |
| Researcher to Architect | 30 min | | | |
| Architect to Adjudicator or human | 60 min | | | |

## 6. For the Researcher

| Field | Value |
|---|---|
| `research.network` mode | `none` / `allowlist` / `session-default` -- **state it in the findings** |
| Allowlist (if any) | |
| Must expand, not contradict | any near-miss `DEC-NNNN` found |

A conflict with a live decision goes to the Adjudicator through this session --
never quietly into a second, contradicting record.

## 7. For a finding (no question)

| Field | Value |
|---|---|
| Disposition | `filed as item ____` / `dispatched now` / `declined -- reason:` |
| Owner | |
| Priority | |

A finding is the cheapest thing a unit produces and the easiest to lose. Close
it explicitly, including "declined" with a reason. Silence is not a disposition.

## 8. The answer, once it lands

| Field | Value |
|---|---|
| Answered by | `decision_log` / `researcher` / `architect` / `adjudicator` / `human` |
| Decision written | `DEC-____` -- **the Maestro writes it; one writer for decisions** |
| Re-dispatched | unit, with the decision attached and recorded in `decisions_in_context` |
| Supersedes | any decision this narrows or replaces |
