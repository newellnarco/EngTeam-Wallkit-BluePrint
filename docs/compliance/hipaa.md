# HIPAA / PHI — health information (Security, Privacy, Breach Rules)

**What it is.** US federal law governing **protected health information
(PHI)**. Three operative rules: the **Security Rule** (45 CFR 164.302–318
— administrative, physical, technical safeguards for electronic PHI), the
**Privacy Rule** (uses, disclosures, minimum necessary), and **Breach
Notification** (164.400s). Binds covered entities AND their **business
associates** — a vendor that touches PHI, a hosted LLM endpoint included,
needs a **BAA**.

**Status note (2026-09, keep current):** the rule in force is the 2013
Security Rule. A January 2025 NPRM proposes the first overhaul since —
removing the "addressable" category, mandating encryption, MFA, asset
inventories, and more — but final action has slipped to **~July 2027** on
HHS's agenda. Attest against the current rule; track the NPRM as a
`Revisit if` on the applicability decision.

## Self-attestation checklist (`wall attest hipaa <id>`)

| Id | The Patron attests |
|---|---|
| SR-ADM | Administrative safeguards (164.308): risk analysis, workforce training, access management, contingency plan |
| SR-PHY | Physical safeguards (164.310): facility access, workstation and device controls |
| SR-TEC | Technical safeguards (164.312): access control, audit controls, integrity, transmission security, encryption |
| SR-ORG | Organizational (164.314): BAAs with every business associate — a hosted LLM included |
| SR-DOC | Policies and documentation (164.316): written, retained six years, updated |
| PR-MIN | Privacy Rule: minimum necessary uses and disclosures |
| BN-NOT | Breach Notification (164.400s): discovery clocks, individual and HHS notice |

**The kit's data charter intersection:** `DATA_PROTECTION.md` §2 puts PHI
at the top of the regime table — a hosted model prompt carrying PHI is a
business-associate disclosure, which is why the Warden's checkpoint 2
rules on model endpoints *before* the tech-eval reads DECIDED, and why
`synthetic-only` is the default test-data verdict for anything
health-shaped.

**Waivers.** HIPAA has no optional safeguards; a `waiver` here records a
compensating control with its rationale (the 2013 rule's "addressable"
mechanism) — the NPRM would remove that flexibility, so every waiver
carries a lifting plan.

**Device software is its own regime.** Software that is or serves a
medical device — SaMD/SiMD, or records supporting an approved
application — takes `fda.md` beside this one; HIPAA covers the PHI, not
the device duties.

Sources: [HIPAA Security Rule update status](https://www.hipaajournal.com/hipaa-updates-hipaa-changes/),
[Proposed Security Rule overhaul (Alston & Bird)](https://www.alston.com/en/insights/publications/2025/11/hipaa-security-rule-overhaul),
[Update delayed until 2027 (Clark Hill)](https://www.clarkhill.com/news-events/news/hipaa-security-rule-update-delayed-until-2027/)
