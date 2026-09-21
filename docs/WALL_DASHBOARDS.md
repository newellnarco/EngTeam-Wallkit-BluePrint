# WALL_DASHBOARDS.md

The wall's tab charter: what each dashboard answers, the data that feeds it,
and the honesty rule every tab obeys — **an absent signal is reported absent
with the mechanism that would emit it named; nothing is fabricated to look
healthy.** All tabs render from the one courier-folded `wall.json` snapshot,
so no dashboard can disagree with the ledger or with another tab.

Everything here is host-agnostic: the tabs read events and repo-relative
paths, never a host's own tooling. A repo that never emits an oversight
event simply sees the honest empty state.

---

## 1. The eight tabs

| Tab | Answers | Fed by |
|---|---|---|
| **MAIN** | The state of the repo right now — items, in-flight, agents, flags | The whole snapshot |
| **STORIES** | The board: arcs, stories, bugs and their statuses | `item_state` fold |
| **CREW** | Who is live, on what, at what cost; the optional live wave feed | agent events + budget |
| **LEDGER** | The event stream itself, traceable | `derived/ledger.jsonl` |
| **WAITING** | The human queue — asks and unverified ships parked on a person | `human_required` / `verify_requested` |
| **RETRO** | Are the roles learning? Latest retrospective in full; every signal's trend across waves; diffs landed and last wave's re-measured verdicts | `retro_held` (EVENT_SCHEMA "Oversight") |
| **POSTURE** | The security picture: the Warden's latest ruling per subject at each gate (architecture / data use / test data via `data_use` / playbooks / tech evals / delivery audit), verdict tally, and anything blocked or refused — parked work, front and center | `warden_ruling` |
| **DOCS** | Is every SOP and standard reviewed at its current sha? The documents-of-record registry with per-file state (current / changed-since-review / never-reviewed / missing) plus the decision log | `doc_reviewed` + file hashes + `decisions.index` |

RETRO / POSTURE / DOCS are the **oversight** family (DEC-0026), folded by
`tools/wall/oversight.py` into `snapshot["oversight"]`.

## 2. The review loop the DOCS tab closes

"Reviewable by the Patron" is a mechanism, not a hope:

1. The registry is `documents_of_record` in `wall.json` (empty = the kit
   default: the adoption runbook's seven functions + the engineering
   standard). Hosts add their own — a compliance manual, a runbook, a
   style guide.
2. Every registry file is hashed at each courier run. A file whose hash no
   longer matches its last ack reads **CHANGED since last review** — a hot
   count on the tab, exactly like WAITING.
3. The ack is one command: **`wall ack-doc <path> --by <name>`** hashes the
   file NOW and writes the `doc_reviewed` event with that sha (it refuses a
   missing file — an ack records a read). An ack at a stale sha changes
   nothing — the sha is the point.
4. Leadership and external contributors read the same page: the wall binds
   `127.0.0.1` by standing rule (the derived dir holds the ledger), so
   sharing outward is a deliberate host act — the derived `wall.html` is a
   single self-contained file that can be exported, and the documents
   themselves live in the repo where a reviewer's normal PR flow applies.

## 3. What each empty state says

An empty oversight tab is itself information, and each names its emitter:

- RETRO empty → "the wave close writes a `retro_held` event
  (RETROSPECTIVES.md, SESSION_LIFECYCLE §3 step 6)".
- POSTURE empty → "gates write `warden_ruling` events (warden.md,
  DATA_PROTECTION.md §4) — an empty posture tab on a repo with in-scope
  arcs is itself a finding".
- DOCS with no acks → every row reads never-reviewed, with the
  `doc_reviewed` mechanism named per row.

## 4. Slice 2 — the DESIGN tab (planned, not built)

Requirements / design / mockups / workflows as a dashboard: per arc, its
intent, boundary, design reference, named trajectories (UX_STANDARDS §2),
risk tier, declared data uses, and links to mockups/screenshots. **It is not
built yet because its data contract is not emitted yet:** the item fold
carries title/kind/status only, and arc metadata (design ref, trajectories,
tier) lives in authored item records, not in a folded field. The slice
therefore starts at ITEM_AUTHORING — an `arc_designed` event (or folded item
fields) carrying that metadata — and only then earns a renderer. Building
the tab first would mean scraping prose, which is exactly the
paraphrase-risk the courier-as-script rule exists to prevent.

## 5. Cross-references

- `tools/wall/oversight.py` — the folds; `docs/EVENT_SCHEMA.md` "Oversight"
- RETROSPECTIVES.md · DATA_PROTECTION.md · warden.md — the disciplines that emit
- WALL_STANDARDS.md — serve boundary, derived-dir rules
- `tools/wall/render/wall_template.html` — the renderers (`paintRetro` /
  `paintPosture` / `paintDocs`)
