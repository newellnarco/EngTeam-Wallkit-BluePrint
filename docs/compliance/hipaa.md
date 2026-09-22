# Healthcare privacy — HIPAA/PHI and the adjacent rules (Part 2, HBNR, info blocking)

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
| P2 | 42 CFR Part 2 (in force 2026-02-16, OCR-enforced): SUD records identified, segregated, consent-tracked; NPP updated |
| HBN | FTC Health Breach Notification Rule (2024): non-HIPAA health data in apps/devices covered, breach clocks known |
| IB | Information blocking + certified health IT (ASTP/ONC): no practice that blocks EHI; certification duties current where the product is certified |

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

**The adjacent rules are attested here because they bite the same data.**
**42 CFR Part 2** (the 2024 final rule, compliance 2026-02-16, with OCR's
civil enforcement program live from that date) aligns SUD-record handling
with HIPAA while keeping the heightened consent protections — the records
are identified and segregated, not blended into "PHI generally". The
**FTC Health Breach Notification Rule** (final effective 2024-07-29) is
the trap for the non-covered: a health app or device outside HIPAA still
owes individuals, the FTC and sometimes the media notice of a breach —
GoodRx and Premom were the first enforcement actions. **Information
blocking** (ASTP/ONC) binds developers of certified health IT and anyone
holding electronic health information: no practice likely to interfere
with access, exchange or use, with the HTI rules moving certification
baselines (USCDI v3 from 2026-01-01) and the TEFCA manner exception. And
the **2025 Security Rule NPRM** — MFA, asset inventories, mandatory
encryption — is pending, with the final currently expected ~2027: track
it, do not attest against it yet.

**Device software is its own regime.** Software that is or serves a
medical device — SaMD/SiMD, or records supporting an approved
application — takes `fda.md` beside this one; HIPAA covers the PHI, not
the device duties.

Sources: [42 CFR Part 2 final rule compliance deadline (2026-02-16)](https://www.hipaajournal.com/february-16-2026-compliance-deadline-part-2-final-rule/),
[FTC Health Breach Notification Rule (2024 final)](https://www.federalregister.gov/documents/2024/05/30/2024-10855/health-breach-notification-rule),
[HIPAA Security Rule NPRM (2025)](https://www.federalregister.gov/documents/2025/01/06/2024-30983/hipaa-security-rule-to-strengthen-the-cybersecurity-of-electronic-protected-health-information),
[ASTP/ONC HTI-1 final rule](https://healthit.gov/regulations/hti-rules/hti-1-final-rule/),
[HIPAA Security Rule update status](https://www.hipaajournal.com/hipaa-updates-hipaa-changes/),
[Proposed Security Rule overhaul (Alston & Bird)](https://www.alston.com/en/insights/publications/2025/11/hipaa-security-rule-overhaul),
[Update delayed until 2027 (Clark Hill)](https://www.clarkhill.com/news-events/news/hipaa-security-rule-update-delayed-until-2027/)
