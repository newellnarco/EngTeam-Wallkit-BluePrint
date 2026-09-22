# DATA_PROTECTION.md

The Warden's data charter: **where the data actually is, what regime binds
it, and the compliant way forward** — asked continuously from requirements to
release, not once before code is written. The posture is the point: this
discipline exists to **apply and recommend ways forward within the rules** of
the host's environment, industry, country and stack — a block is the
exception, reserved for a use with no compliant path as declared, and even a
block names the smallest compliant alternative visible.

The verdicts and gates themselves live in the Warden's role sheet
(`.claude/agents/warden.md`); this document is the map the verdicts are made
from.

---

## 1. The exposure map — where data can be

Every declared data use names its exposure, because "we handle it carefully"
is not a location. The ladder, from walled to loose:

| Exposure | What it means | The standing question |
|---|---|---|
| **Walled** | Inside the protected boundary: the local box, an access-controlled store, an encrypted volume with held keys | Is the wall real — access-controlled, encrypted at rest, audited? |
| **In containers** | Inside images, volumes, orchestrator secrets, layer caches | Do images or layers bake data in? Do volumes outlive the workload? Who reads the orchestrator's secret store? |
| **In the LLM** | In a prompt, a context window, a fixture an agent pastes, a tool result — **a prompt to a hosted model is an egress to a third party.** Local inference keeps it walled; a hosted endpoint is a processor relationship (DPA/BAA, retention and training-use terms) | What enters prompts, under what agreement, with what retention? The kit's own rule stands: anything an agent sends to a model is a data use and is evaluated like one |
| **Loose on a network** | Crossing segments unencrypted, on shared storage, in telemetry, in logs shipped off-box | Which hops? Encrypted in motion? Who else is on that segment? |
| **In public** | Repos, artifact stores, telemetry branches, error trackers, package registries, screenshots | Assumed permanent and indexed the moment it lands. The redaction audit exists because this row exists |

Movement DOWN this ladder is always a Warden question. The kit's own
machinery is on the map too: event shards, diagnostics snapshots and the
telemetry branch are metrics-and-states only — that rule is audited, not
assumed.

## 2. The regimes — what binds the data

Classification is not generic "sensitive": it names the regime, because the
regime dictates the obligations. The starting table — the host names ITS
regimes at intake (PRODUCT_INTAKE data-security domain), and the Warden never
guesses jurisdiction:

| Class | Regime examples | Obligations that follow |
|---|---|---|
| **PII** | GDPR, CCPA/CPRA, national privacy acts | Lawful basis, minimization, subject rights, breach clocks, cross-border transfer rules |
| **PHI** | HIPAA (+ state health law) | BAAs with every processor — a hosted LLM included; minimum necessary; audit trails |
| **Medical-device / FDA-regulated** | QMSR (21 CFR 820), IEC 62304, FD&C §524B, 21 CFR Part 11 | Design controls and lifecycle by safety class; SBOM + vulnerability duties; trustworthy records where they support an approved application; change control with submissions decided in writing |
| **PCI** | PCI-DSS | Scope containment, tokenization over storage, segmentation, no PAN in logs or fixtures ever |
| **Government / law-enforcement reach** | Patriot Act / CLOUD Act exposure, CJIS, FedRAMP, ITAR/EAR | Residency and provider constraints; a cloud region choice IS a compliance decision; some data cannot ride commercial clouds at all |
| **Regulated-industry** | SOX, GLBA, FERPA, NIST-bound contracts (CSF 2.0, SP 800-171 for CUI, SSDF attestation), sector rules the intake names | Change-control evidence, retention schedules, access separation; CUI segregated where a federal contract reaches |
| **Contract-bound** | NDAs, DPAs, customer terms | Whatever the paper says — read it, cite it |

One datum can carry several classes; the strictest obligation wins. Residency
is part of classification: **country and jurisdiction are named per class**,
because "encrypted" does not answer "may it leave Germany".

## 3. States and protections

Every class is evaluated in all three states — a dataset encrypted at rest
and pasted into a prompt is protected in one state and exposed in another:

| State | Covers | Baseline expectations |
|---|---|---|
| **At rest** | Stores, volumes, backups, caches, container layers | Encryption with named key custody; retention with a schedule; deletion that actually deletes (backups included) |
| **In motion** | Every hop, internal ones included | TLS or better; no plaintext credentials in transit; segment boundaries known |
| **In use** | Prompts, logs, fixtures, run artifacts, debug output, screenshots | The leakiest state and the least audited — this is where the LLM row, the test-data rule and the redaction audit live |

The ways-forward catalog the Warden recommends from, in rough order of
preference: **minimize** (don't collect it), **synthesize** (generated data
develops as well as real), **mask/tokenize** (named fields stripped before
any development use), **encrypt** (rest and motion, keys held rightly),
**segment** (walls between scopes), **localize** (local inference, on-prem,
in-region), **paper** (DPA/BAA/zero-retention terms where a processor is
unavoidable). A recommendation names which of these and why it satisfies the
regime.

**Sensitive-by-nature data gets the architectural split, not per-field
care.** Where the product's core data is sensitive by its nature — captured
traffic, recordings, household activity, clinical detail — the full-detail
store is architecturally confined to the walled row: interfaces bind to
loopback by default, writes stay on a gated local path, and the only thing
that ever leaves is a **derived, redacted operational snapshot**, masked at
the *publishing* side (never trusted to the reader), on an **opt-in channel
installed separately** so that nothing leaves by default. (The appliance
shape's posture; the kit's own telemetry branch already follows it.)

**State a protection's scope honestly: enforced absolutely, or raised in
cost.** A posture separates the controls a platform enforces absolutely
(framing restrictions, cross-origin reads) from those that only raise the
cost of abuse (crawler directives, hotlink rules, agent-string blocks — a
request, not a control), and writes the boundary down. A posture that mixes
the two overstates what is protected and misdirects the response when
something is taken anyway. And every claim a control's own documentation
makes ("allow-list", "fails closed") is a claim some check compares to the
code, not a fact.

## 4. The six checkpoints — continuous, not a gate at the end

The Warden's question is asked at every stage, sized to the stage. Not a full
stop at any of them: each checkpoint's deliverable is the compliant way
forward for THIS host — its industry, its country, cloud or local, its LLM
setup.

| Checkpoint | The Warden's question | Typical way forward |
|---|---|---|
| **1. Requirements** | What data does this product touch, what classes and regimes, what residency? (the intake's data-security domain — unanswered blocks that domain's arcs by construction) | Name the regimes as decisions; park only what is genuinely unanswerable |
| **2. Technology selection** | Where does the candidate PUT data — its cloud, its region, its telemetry, its model endpoint, its retention? | Prefer the candidate that keeps data walled; where it can't, name the paper (DPA/BAA) and flags (zero-retention) that make it compliant; record in the tech-eval before it reads DECIDED |
| **3. Architecture** | Trust boundaries drawn against the exposure map; flows consistent with class and residency; fail closed (Gate 1) | approved / approved-with-conditions — conditions become citable acceptance criteria on the stories |
| **4. Test development** | What enters fixtures, seeds and CI? Production data never becomes test data by convenience | synthetic-only or masked verdicts; a fixture with real PII is a finding whoever wrote it |
| **5. Building** | What are agents pasting into prompts, logs and run artifacts right now? | Spot-audit under act-and-audit; the standing defaults (no secrets in fixtures, prompts, artifacts, ledger) enforced without being asked |
| **6. Before release** | Does what ships match what was signed — every in-scope arc's verdicts present, no scope drifted past its tier, redaction audit clean? (Gate 3) | Discrepancies are findings on the wave report; a repeated class graduates to the failure registry |

Checkpoints 1, 2 and 4 are what this charter adds to the gates that already
existed (3, 5-as-spot-audit, 6): the Warden is in the room **at requirements,
during technology selection and when test data is designed** — the three
places a data liability is cheapest to prevent and likeliest to be created
silently.

## 5. The ruling, shaped forward

Every data ruling carries: the class and regime it rests on (cite the corpus
— a ruling with no citable obligation is an opinion), the exposure it
evaluates, the state(s) at issue, the verdict — and **the way forward**: the
catalog entries that make the use compliant here, in this environment, under
these rules. `refused` remains available, and keeps its shape: no compliant
path exists *as declared*, with the smallest redesign that would change that
named in the same ruling.

## 6. Cross-references

- `.claude/agents/warden.md` — the authority, gates and verdict table
- PRODUCT_INTAKE.md — the data-security domain this charter deepens
- TECH_EVALUATION.md — checkpoint 2's home; the Warden line on every record
- CAPABILITY_TRUST.md — checkpoint 2's sibling question for anything
  discovered: who published it, and what pins it
- TESTING_STANDARDS.md — the SAST/secrets lane; checkpoint 4's test-data rule
- ITEM_AUTHORING.md §3.6–3.7 — risk tier and declared data uses on every arc
- DIAGNOSTICS_LOOP.md — the redaction audit; COMPLIANCE_POSTURE.md — auditor language
