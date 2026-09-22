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

## 1. The nine tabs

| Tab | Answers | Fed by |
|---|---|---|
| **MAIN** | The state of the repo right now — items, in-flight, agents, flags | The whole snapshot |
| **STORIES** | The board: arcs, stories, bugs and their statuses | `item_state` fold |
| **CREW** | Who is live, on what, at what cost; the optional live wave feed | agent events + budget |
| **LEDGER** | The event stream itself, traceable | `derived/ledger.jsonl` |
| **WAITING** | The human queue — asks and unverified ships parked on a person | `human_required` / `verify_requested` |
| **RETRO** | Are the roles learning? Latest retrospective in full; every signal's trend across waves; diffs landed and last wave's re-measured verdicts | `retro_held` (EVENT_SCHEMA "Oversight") |
| **POSTURE** | The security picture: the Warden's latest ruling per subject at each gate, verdict tally, anything blocked or refused — plus the **compliance section** (DEC-0028): every regime (SOC 2, HIPAA/PHI, PCI, PII/privacy, government, sector, NIST, FDA) with its blueprint link, the Patron's applicability selection and its decision log, both-direction challenges, and an **interactive self-attestation popout** per regime — pass / fail / waiver-with-reason per control, the waiver never silent | `warden_ruling` + `compliance_selected` / `compliance_attested` + `tools/wall/compliance.py` |
| **DOCS** | Is every SOP and standard reviewed at its current sha? The documents-of-record registry with per-file state (current / changed-since-review / never-reviewed / feedback-open / missing) plus the decision log | `doc_reviewed` / `doc_feedback` + file hashes + `decisions.index` |
| **FLOW** | The Foreman/Maestro instrument (DEC-0027/0028): velocity, estimate-vs-actual sizing points, bugs filed, and burndown (open at close) per iteration — each iteration row opens a **drill-in popout**: cost (summed `cost_usd`), agents by role, duration, what was delivered, and what was worked but NOT delivered | The existing `item_created` / `item_state` (§8 estimate+actual) / `item_shipped` / `run_end` stream, segmented by `retro_held` |

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
3b. **Sign-off is not the only answer.** `wall ack-doc <path> --feedback
   "..."` records the objection instead — correct, remap, discuss — and the
   doc reads **feedback-open** (outranking every readable state) until a
   NEWER ack lands; the text routes to the Architect as a finding through
   the normal route. Signed documents are the engteam's **context markers**
   (adopt skill, DEC-0027): designs cite them, and every new version voids
   the previous sign-off so each version earns its own review.
3c. **The registry is fed by adoption**: the `/adopt` context hunt maps the
   host's many documents onto the working functions (requirements, design,
   technology, data, integration, environments, security, testing, SOPs,
   diagrams), authors evidence-cited drafts where nothing exists, and
   registers every document of record here — so a fresh assimilation
   arrives with its whole review queue visible.
4. Leadership and external contributors read the same page: the wall binds
   `127.0.0.1` by standing rule (the derived dir holds the ledger), so
   sharing outward is a deliberate host act — the derived `wall.html` is a
   single self-contained file that can be exported, and the documents
   themselves live in the repo where a reviewer's normal PR flow applies.

## 3. What each empty state says

An empty oversight tab is itself information, and each names its emitter:

- RETRO empty → "the wave close writes a `retro_held` event
  (RETROSPECTIVES.md, SESSION_LIFECYCLE §3 step 6)" — and still shows any
  pending `wall retro-note` Patron inputs, which the next retro must
  address.
- FLOW empty → names the item-stream events it reads and fills as work
  flows; "none recorded" in the sizing columns means none recorded, never
  an invented number.
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

## 4b. The compliance loop (DEC-0028)

The regime registry is `tools/wall/compliance.py` (machine) +
`docs/compliance/*.md` (the blueprints, source-cited, translated from the
current authorities — PCI DSS v4.0.1, the HIPAA rules in force with the
2025 NPRM noted, SOC 2 2017 TSC w/2022 PoF, GDPR + CCPA/CPRA 2026,
FedRAMP Rev5/20x + CJIS v6, SOX/GLBA/FERPA); a pin test keeps every
registry control id present in its document. The loop: the Patron selects
applicability with a reason (`wall compliance <regime> ...` — the reason IS
the decision log), the fold **challenges both directions** (selected with
no observed surface; unselected while Warden rulings cite the regime's
keywords) without ever flipping a selection, the popout audit attests
control-by-control (`wall attest ...`, waiver only with its reason), and
the **Warden reviews the register at every checkpoint and wave close**
(warden.md) — selections vs what the wave touched, attestation freshness,
waiver lifting conditions.

## 4b-bis. The regime lifecycle joins the compliance loop (DEC-0030)

The §4b loop gained a front half: the Warden's periodic `wall
compliance-scan` records which regimes the code suggests (with evidence),
the fold names scan-vs-selection tensions as **dispositions** (a regime
disabled against the evidence reads `NOT RECOMMENDED FOR DISABLED`, with a
WHY popout), and the POSTURE rows dispatch ENABLE / DISABLE / REQUEST AUDIT
through the EXECUTE port for the Warden to act on. Audits are
complete-or-refused, every verdict with its proof or reason. Full record:
`docs/decisions/DEC-0030.md`; authoring contract: `COMPLIANCE_POSTURE.md`.

## 4c. The blocked drill-in (Patron direction 2026-09-22)

A `blocked` status chip on any board row is a **button**. Clicking it opens a
dialog that answers "why?" from what the ledger already holds — the item's
`blocked_reason` (or `reason`) field, plus every open ask against the item
from the WAITING feed — and offers two dispatch actions:

- **BUILD A FIX →** enqueues `{directive: "resolve_blocked", mode: "build",
  item_id, reason}` to the host queue.
- **RESEARCH IT →** the same with `mode: "research"`.

Both ride the EXECUTE port: the buttons render only after the same-origin
queue health probe answers ok, so a standalone wall stays read-only,
honestly. Who performs the work is the queue consumer's business, not the
wall's — a Claude Code session pulling through the wall MCP adapter, an
editor agent (Cursor, VS Code) polling the HTTP queue API, or the Maestro
draining it by hand all look identical from here.

An item blocked with **no** recorded reason and **no** open question renders
that fact verbatim — blocked-without-asking is a WORKFLOW §4 escalation, and
the dialog points at `wall trace <item_id>` for the history rather than
inventing a reason.

**The reason contract:** whoever flips an item to `blocked` writes the why in
the same event — snapshot shape `{"status": "blocked", "blocked_reason":
"…"}` or a `{field: "blocked_reason", after: "…"}` delta. The fold carries
any non-envelope key onto the item, so no schema change is involved; the
dialog simply reads what discipline wrote. (`reason` alone is an ENVELOPE
key and does not fold — use `blocked_reason` on items.)

## 5. Cross-references

- `tools/wall/oversight.py` — the folds; `docs/EVENT_SCHEMA.md` "Oversight"
- RETROSPECTIVES.md · DATA_PROTECTION.md · warden.md — the disciplines that emit
- WALL_STANDARDS.md — serve boundary, derived-dir rules
- `tools/wall/render/wall_template.html` — the renderers (`paintRetro` /
  `paintPosture` / `paintDocs`)
