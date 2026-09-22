# NIST — the framework regime (CSF 2.0, SP 800-171 r3, SSDF SP 800-218)

**What it is.** The NIST family most software organizations actually meet:
**CSF 2.0** (February 2024) as the umbrella framework — six functions,
Govern · Identify · Protect · Detect · Respond · Recover, with Govern new
in 2.0 and supply-chain risk management inside it; **SP 800-171 r3** for
protecting Controlled Unclassified Information (CUI) in nonfederal
systems, with its self-assessment score reported to SPRS in the defense
supply chain; and the **Secure Software Development Framework, SP
800-218**, the practice set behind federal secure-software attestation.
EO 14028 set that in motion; **EO 14306 (June 2025)** then removed the
central CISA validation of attestations — agencies may still request the
March 2024 form, and the enduring requirement is **auditable SSDF
conformance itself**. 800-171 r3 (final May 2024) ships with 800-171A r3
for assessment and a 2025 small-business primer (SP 1352). (SP 800-53 sits underneath
FedRAMP and CJIS — the kit carries those in the government regime.)

**Applies when** a contract, customer or program requires NIST alignment:
CSF as the named security framework (common in insurance questionnaires
and B2B diligence), 800-171 whenever CUI is created or handled for a
federal contract, SSDF attestation when software is sold to the US
government. Voluntary as law, binding as paper.

## Self-attestation checklist (POSTURE tab, `wall attest nist <id>`)

| Id | The Patron attests |
|---|---|
| GV | CSF Govern: risk strategy, roles, policy, oversight and supply-chain risk management established and owned |
| ID | CSF Identify: assets, risks and improvement opportunities inventoried and assessed |
| PR | CSF Protect: identity and access, awareness, data security, platform security, resilience |
| DE | CSF Detect: continuous monitoring and adverse-event analysis in place |
| RS | CSF Respond: incident management, analysis, reporting and mitigation exercised |
| RC | CSF Recover: recovery execution and communications planned and tested |
| CUI | SP 800-171 r3 (conditional): CUI identified, controls mapped, the self-assessment score current and true |
| SSD | SSDF SP 800-218: secure-development practices mapped for the software produced; attestation ready where a buyer requires it |

**How the kit already helps:** the authority matrix, single-writer
decision log and Warden gates are Govern in writing; the ledger + wall
are Detect's continuous-monitoring evidence; the diagnostics loop with
its playbooks is Respond/Recover exercised rather than shelved;
gates-last, mutation evidence, the SAST/secrets lane and
`CAPABILITY_TRUST.md`'s default-deny adoption map directly onto SSDF's
produce-well-secured-software and respond-to-vulnerability practices.
See `COMPLIANCE_POSTURE.md` for the mechanism-to-control mapping.

**Waivers.** CUI is attested `waiver` with the reason "no CUI handled —
no federal contract in scope"; SSD is `waiver` only where the org ships
no software to a buyer who can require the attestation. Both recorded,
never silent.

Sources: [NIST CSF 2.0](https://www.nist.gov/cyberframework),
[SP 800-171A r3 (assessment)](https://csrc.nist.gov/pubs/sp/800/171/a/r3/final),
[SP 800-171 r3](https://csrc.nist.gov/pubs/sp/800/171/r3/final),
[SSDF SP 800-218](https://csrc.nist.gov/Projects/ssdf)
