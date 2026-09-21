# Sector rules — SOX, GLBA, FERPA

**What it is.** Three US sector regimes the kit meets often enough to
name. **SOX** (public companies): internal control over financial
reporting — for engineering, that means change-control and access
EVIDENCE over any system feeding the financial statements. **GLBA
Safeguards Rule** (consumer financial data): a written information
security program, risk assessment, access controls, MFA, encryption,
vendor oversight, incident response. **FERPA** (education records):
consent-gated disclosures, directory-information opt-outs.

**Applies when** the host's business is in one of these sectors — the
intake's data-security domain names it (a regime is never guessed,
`DATA_PROTECTION.md` §2).

## Self-attestation checklist (`wall attest sector <id>`)

| Id | The Patron attests |
|---|---|
| SOX | SOX ICFR: change control and access evidence over systems feeding financial reports |
| GLB | GLBA Safeguards Rule: written infosec program, risk assessment, MFA, encryption, vendor oversight |
| FER | FERPA: education records identified, disclosures consent-gated, directory-info opt-outs honored |

**The kit's intersection:** SOX is the regime the kit satisfies most
naturally — the ledger, the single merge authority, branch
serialization, and the authority matrix ARE change-control evidence
(`COMPLIANCE_POSTURE.md` maps them row by row). GLBA's written-program
requirement maps onto the Warden's corpus; FERPA rides the same
classification machinery as PII.

**Waivers.** Out-of-sector rows are whole-regime non-applicability at
selection time; a mixed business (a fintech with an education product)
selects the regime and waives the inapplicable row with the reason.

Sources: [Data privacy laws by state/sector (CDP)](https://cdp.com/basics/international-u-s-data-privacy-laws-and-regulations-you-need-to-know/),
[Osano 2026 privacy-law overview](https://www.osano.com/articles/data-privacy-laws)
