# Government reach — FedRAMP, CJIS, CLOUD Act, export control

**What it is.** The cluster where the customer or the data brings
government obligations. **FedRAMP** authorizes cloud services for US
federal agencies (Rev5 NIST 800-53 baselines; the **20x program's
Consolidated Rules** — early adoption since 2026-07-04, mandatory
2027-01-01 — replace the legacy guidance patchwork). **CJIS Security
Policy v6.x** (v6.1 effective 2026-06) governs criminal justice
information and is now structured on NIST 800-53 families, converging
with FedRAMP. **CLOUD Act / Patriot Act** reach makes provider and
region choices compliance decisions in themselves. **ITAR/EAR** export
control fences defense-related technical data.

**Applies when** federal agencies are customers, criminal justice
information is touched, or the data's sensitivity makes law-enforcement
reach or export control a design constraint.

## Self-attestation checklist (`wall attest government <id>`)

| Id | The Patron attests |
|---|---|
| FR | FedRAMP: authorization path chosen (Rev5 baseline or 20x), boundary defined, continuous monitoring |
| CJ | CJIS Security Policy (v6.x, NIST 800-53 aligned): CJI identified and controls mapped |
| RES | Residency and reach: provider and region choices evaluated against CLOUD Act / Patriot Act exposure |
| EXP | Export control: ITAR/EAR-controlled technical data identified and segregated |

**The kit's intersection:** this regime is why `DATA_PROTECTION.md` §2
says a cloud region choice IS a compliance decision, and why some data
cannot ride commercial clouds at all — the Warden's checkpoint 2 exists
largely for this row. Local-first deployment (the kit's reference
posture) is the strongest RES answer available.

**Waivers.** "No federal customers, no CJI, no export-controlled data"
is a legitimate whole-regime non-applicability — recorded as the
selection decision, challenged if a Warden ruling ever cites these
keywords.

Sources: [FedRAMP 20x and 2026 Consolidated Rules](https://secureframe.com/blog/fedramp-20x),
[FedRAMP Rev5 requirements](https://secureframe.com/hub/fedramp/compliance-requirements),
[CJIS Security Policy (Microsoft compliance summary)](https://learn.microsoft.com/en-us/compliance/regulatory/offering-cjis)
