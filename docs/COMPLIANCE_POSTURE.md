# COMPLIANCE_POSTURE.md

The kit's mechanisms translated into the control language auditors and
regulated industries use — fintech, healthcare, e-commerce and anywhere else
change control, traceability and segregation of duties are examined rather
than assumed.

**The honest frame first.** The kit is not a certification and does not make a
product compliant. What it does is structural: it makes the delivery process
produce, as a by-product of normal operation, the **evidence trail** those
audits ask for — who changed what, on whose authority, against which
requirement, reviewed by whom, reversible how. Teams usually reconstruct that
trail after the fact; here it is the working state.

---

## 1. Control-family mapping

| Control family (the auditor's ask) | Kit mechanism | Where |
|---|---|---|
| **Segregation of duties** — no actor authors, approves and ships alone | The authority matrix: the Builder cannot merge, the Maestro cannot edit source, the Reviewer alone reads code for correctness, the Foreman cannot assign work, and the **Warden signs off security/compliance without the power to grant access**; enforced as written boundaries + role sheets, visible in every run record | WORKFLOW.md §7, AGENT_ROSTER_SPEC.md |
| **Independent security & compliance sign-off** — design approved by an authority that did not author it | The Warden: mandatory architecture sign-off on in-scope arcs before dispatch, per-use data verdicts (dev and product), wave-close delivery audit; block-without-grant, overrulable only by the engineer in writing with the objection preserved | .claude/agents/warden.md |
| **Data protection across the lifecycle** — classification, residency, and protection evaluated continuously, not at release | The Warden's six checkpoints: regimes named at requirements (PII/PHI/PCI/government/sector), data placement ruled at technology selection, trust boundaries at architecture, synthetic/masked test data, in-build prompt/log spot audits, pre-release verification; exposure mapped per use (walled / containers / LLM / network / public), all three states (rest, motion, in use); every ruling names the compliant way forward | docs/DATA_PROTECTION.md, .claude/agents/warden.md |
| **Change management** — every change requested, approved, tested, traceable | Story → citable acceptance criteria → dispatch brief → PR through one slot → review → merge by the one authority; criteria map to sources *before* code is written | ITEM_AUTHORING.md, WORKFLOW.md §§2–5 |
| **Audit trail / non-repudiation** | Append-only event ledger, idempotent on `event_id`, totally ordered, **byte-reproducible from shards** (verified by test, not asserted); keys are permanent identity; `model_requested` vs `model_used` recorded separately | EVENT_SCHEMA.md, WALL_STANDARDS.md §7 |
| **Traceability** — requirement ↔ change ↔ test ↔ release | `trace_id` through every hop (`wall trace`); `decisions_in_context` on every run; the shipping event carries the merged PR number; `wall why` answers "which rules were in effect and who saw them" | EVENT_SCHEMA.md, LOGGING_AND_AUDIT.md |
| **Access control / least privilege** | Consent-gated installs that print their plan and create nothing without `--yes`; localhost-only serving with a named-file allowlist; researcher network off by default and widened only by the engineer; secrets scoped to the one job that needs them | INSTALL.md, DEPLOYMENT_TARGETS.md |
| **Reversibility / rollback** | Append-only everywhere; decisions superseded, never rewritten; rollback anchors recorded before any force-push; `--force-with-lease` behind a two-sided diff proof; superseded criteria stay visible | WORKFLOW.md §9, ITEM_AUTHORING.md §5 |
| **Irreversible-change control** — the subset a rollback cannot address | The irreversible-surfaces register: an enumerated list of surfaces where "can a revert restore it?" is answered *no*, each with the probe against the real system that must report after a change touches it — a green suite is not accepted as evidence for these | OWNER_DECISIONS template §7, ENGINEERING_STANDARD template (Mindset) |
| **Independent review** | The Reviewer reads the diff cold with no access to the author's reasoning; external reviewer lanes verified by probe; findings closed with evidence, refutations require proof | WORKFLOW.md §§6, 10; reviewer-integration skill |
| **Security testing** | SAST + secrets lane in the definition of done — per-rule promotion so the lane never gets disabled wholesale; secrets findings require rotation, not deletion from the diff | TESTING_STANDARDS.md |
| **Data classification** | The intake's data-security domain: what is handled, what is secret vs private, what must not cross which boundary — answered before design, recorded as decisions | PRODUCT_INTAKE.md |
| **Incident learning / CAPA** | The failure registry + graduation rule: every incident class gets a named entry, a mechanical check, and a checklist line in the same change — corrective *and* preventive, with the recurrence test in CI | FAILURE_PATTERNS template, TESTING_STANDARDS.md |
| **Capacity / availability management** | Measured signals, advisory budgets, recorded from→to rebalances with review horizons; dead timers surface as heartbeat failures, never as silence | CAPACITY_REBALANCING.md, INSTALL.md |
| **Vendor / tool governance** | Reviewer lanes and technology choices enter through recorded evaluations and decisions with re-eval triggers; removal keeps adopted rules and closes open threads with dispositions | reviewer-integration skill, decision log |

## 2. Industry notes

- **Fintech (SOX-style change control, PCI adjacency):** the one-PR-slot +
  merge-authority + criteria-citation chain is the change-control narrative;
  the ledger's total order and reproducibility is the log-integrity story.
  Cardholder-data scoping itself belongs to the host architecture — the
  intake's data-security domain is where it gets asked and pinned.
- **Healthcare (HIPAA-adjacent):** the kit's own surfaces hold *process*
  data, not PHI — keep it that way. Prompts and run artifacts can quote
  repository content, which is why `.wall/logs/` and `.wall/runs/` are
  gitignored with TTLs and never shipped; if the repo itself contains PHI-touching
  code, say so in the data-security domain and treat run artifacts
  as in-scope storage.
- **E-commerce (PCI, consumer-data regulation):** the same two levers —
  data-classification answered at intake, evidence trail from the ledger —
  plus the security escalation class: a finding touching payment or consumer
  data goes straight to the sponsor, never triaged quietly.

## 3. What the kit deliberately does not claim

- It does not implement encryption, retention schedules, or access control
  *inside your product* — those are product requirements, captured at intake
  and built as stories like everything else.
- It does not replace a compliance program, a DPO, or an assessor. It hands
  them a process whose every step already left evidence.
- Its own telemetry (shards, doctor.json) is process metadata; review it once
  against your data-classification answers before first ship, and record the
  verdict as a decision.

## 4. Cross-references

- docs/diagrams/ORG_MAPPING.md — the segregation-of-duties picture
- docs/EVENT_SCHEMA.md — the audit trail's contract
- docs/PRODUCT_INTAKE.md — where regulation enters as requirements
- docs/SESSION_LIFECYCLE.md §4 — the classes only the engineer may decide


## The regime lifecycle (DEC-0030)

The Warden's periodic `wall compliance-scan` records which regimes the code
suggests, with evidence. The POSTURE tab folds scan against selection into a
disposition — `active` / `active (scan found no surface)` /
`recommended -- decide` / `inactive` / **`NOT RECOMMENDED FOR DISABLED`**
(with a WHY popout carrying the evidence) — and its ENABLE / DISABLE /
REQUEST AUDIT buttons dispatch `warden_regime` / `warden_audit` directives
through the EXECUTE port for the Warden to act on. An audit is recorded with
`wall audit <regime> --file results.json`: every control, `pass | fail |
waiver`, each with its proof or reason; partial audits are refused by name.
Full record: `docs/decisions/DEC-0030.md`.
