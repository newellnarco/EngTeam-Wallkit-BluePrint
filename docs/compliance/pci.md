# PCI DSS v4.0.1 — payment card data

**What it is.** The Payment Card Industry Data Security Standard,
contractually enforced through the card brands and acquirers. The current
version is **v4.0.1**; since **2025-03-31 every requirement is
mandatory** (the future-dated ones included), and all 2026 assessments
run against v4.0.1.

**Applies when** cardholder data (PAN, track data, CVV) is stored,
processed, or transmitted — or the system can *affect the security* of a
payment flow (scripts on a payment page count). Scope containment is the
first move: tokenize, segment, and keep the CDE small. **Requirement
12.5.2 makes scope re-confirmation an annual duty** (six-monthly for
service providers).

## Self-attestation checklist (`wall attest pci <id>`) — the 12 requirements

| Id | The Patron attests |
|---|---|
| R1 | Network security controls installed and maintained |
| R2 | Secure configurations applied to all system components |
| R3 | Stored account data protected (no PAN in logs or fixtures, ever) |
| R4 | Cardholder data encrypted over open, public networks |
| R5 | Malicious software protected against |
| R6 | Secure systems and software developed and maintained |
| R7 | Access restricted by business need to know |
| R8 | Users identified and access authenticated (MFA) |
| R9 | Physical access to cardholder data restricted |
| R10 | Access to system components and cardholder data logged and monitored |
| R11 | Security of systems and networks tested regularly |
| R12 | Information security supported by organizational policies (incl. 12.5.2 scope re-confirmation) |

**The kit's intersection:** R3 is `DATA_PROTECTION.md`'s test-data rule
verbatim (PAN never becomes a fixture); R10 is the ledger discipline
applied to the CDE; R6 is the gates + reviewer lanes. A `fail` on any
row with cardholder data in scope is a Warden `blocked` — PCI has no
self-granted waivers, only compensating controls documented with the
assessor.

Sources: [PCI DSS v4.0.1 (official PDF)](https://www.middlebury.edu/sites/default/files/2025-01/PCI-DSS-v4_0_1.pdf?fv=AKHVQBp6),
[v4.0.1 mandatory in 2026](https://www.sicherten.com/blog-pci-dss-4-0-1-mandatory-2026.html),
[New requirements guide](https://www.securitymetrics.com/blog/a-guide-to-new-requirements-in-pci-dss-4-0-1)
