# SOC 2 — the assurance regime (2017 TSC, 2022 Revised Points of Focus)

**What it is.** An AICPA attestation framework: an independent auditor
reports on controls against the five **Trust Services Criteria** —
Security (mandatory in every SOC 2), Availability, Processing Integrity,
Confidentiality, Privacy. The current basis is the **2017 TSC with the
2022 Revised Points of Focus** (the criteria unchanged; the points of
focus refreshed for modern threats). Type I reports on design at a point
in time; Type II on operating effectiveness over a period.

**Applies when** customers or partners ask for assurance over the
service — B2B SaaS almost always ends up here. It is voluntary but
contract-driven: nobody fines you, deals just require it.

## Self-attestation checklist (POSTURE tab, `wall attest soc2 <id>`)

| Id | The Patron attests |
|---|---|
| CC1 | Control environment: integrity, oversight, accountability are real and assigned |
| CC2 | Communication and information: policies reach the people they bind |
| CC3 | Risk assessment: risks identified, analyzed, and responded to on a cadence |
| CC4 | Monitoring: controls are evaluated and deficiencies reach the right people |
| CC5 | Control activities: controls exist at the process level, not just on paper |
| CC6 | Logical and physical access: least privilege, credential lifecycle, boundary protection |
| CC7 | System operations: anomaly detection, incident response, recovery |
| CC8 | Change management: changes authorized, tested, approved, tracked |
| CC9 | Risk mitigation: vendor and business-disruption risk handled |
| A1 | Availability (optional category): capacity, backup, recovery objectives met |
| PI1 | Processing integrity (optional): processing is complete, valid, accurate, timely |
| C1 | Confidentiality (optional): confidential data identified and protected to disposal |
| P1 | Privacy (optional): personal information handled per the privacy notice |

**How the kit already helps:** the ledger + wall are CC4 monitoring
evidence; the authority matrix is segregation of duties (CC1/CC5); the
single-writer decision log and dispatch briefs are CC2; branch
serialization + gates-last + the merge-authority rule are CC8 change
management; the Warden's gates are CC3/CC9 in writing. See
`COMPLIANCE_POSTURE.md` for the full mechanism-to-control mapping.

**Waivers.** An optional category not contracted (A1/PI1/C1/P1) is
attested `waiver` with the reason "category not in scope of the
report" — recorded, never silent.

Sources: [AICPA 2017 TSC with Revised Points of Focus (2022)](https://www.aicpa-cima.com/resources/download/2017-trust-services-criteria-with-revised-points-of-focus-2022),
[Trust Services Criteria guide](https://linfordco.com/blog/trust-services-critieria-principles-soc-2/)
