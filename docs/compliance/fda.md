# FDA — regulated software (SaMD/SiMD, QMSR, §524B, Part 11)

**What it is.** The FDA regime for software that is or serves a medical
product: **SaMD** (software that is itself the medical device), **SiMD**
(software embedded in or controlling a device), and software whose
records support an FDA-approved application. The load-bearing pieces:
the **QMSR** (21 CFR 820 as amended, aligned with ISO 13485, in force
since February 2026) for the quality system and design controls;
**IEC 62304** for the software lifecycle by safety class; the premarket
pathways (**510(k) / De Novo / PMA**) with software documentation levels
per the 2023 guidance; **FD&C §524B** cyber-device duties (SBOM,
vulnerability monitoring and coordinated disclosure, updatability);
**21 CFR Part 11** for electronic records and signatures; and postmarket
duties — complaints, Part 803 adverse-event reports, corrections.

**Applies when** the software's function meets the device definition
(diagnosis, treatment, mitigation, prevention), it runs in or drives an
approved or cleared device or hardware, or it produces or maintains
records supporting an approved application (drug, biologic, device).
Deciding it does NOT apply is itself a recorded determination — the
"not a device" call is the one FDA looks at first.

## Self-attestation checklist (POSTURE tab, `wall attest fda <id>`)

| Id | The Patron attests |
|---|---|
| QMS | QMSR quality system with design controls established (ISO 13485-aligned, in force 2026-02) |
| LC | IEC 62304 lifecycle: software safety class assigned; development and maintenance planned to it |
| PMK | Premarket pathway identified (510(k) / De Novo / PMA) with software documentation at the level the 2023 guidance sets |
| CYB | §524B cyber-device duties: SBOM maintained, vulnerabilities monitored and disclosed, updates deliverable |
| P11 | Part 11: electronic records and signatures trustworthy wherever records support a regulated submission |
| PMS | Postmarket: complaint handling, Part 803 adverse-event reporting, corrections and removals ready |
| CHG | Change control: whether a modification needs a new submission is decided in writing; AI/ML-enabled change rides a PCCP |

**How the kit already helps:** design controls want exactly what the kit
already writes — requirements → change → test → release traceability
(`wall trace`), design documents per arc, the single-writer decision
log, and gates that run last; §524B's SBOM and vulnerability duties sit
on the dependency register, the SAST/secrets lane and the diagnostics
loop; Part 11's audit-trail expectation is the append-only ledger's
native shape. The kit is evidence machinery, not a submission — the
regulatory strategy stays with the owner's regulatory professional.

**Waivers.** PMK is attested `waiver` with the reason where the product
is documented as not a device (the determination cited); CHG's PCCP
half is `waiver` where nothing AI/ML-enabled ships. Recorded, never
silent.

Sources: [FDA QMSR final rule](https://www.fda.gov/medical-devices/quality-system-qs-regulationmedical-device-current-good-manufacturing-practices-cgmp/quality-management-system-regulation-qmsr-final-rule),
[FDA device cybersecurity (§524B, 2023 guidance)](https://www.fda.gov/medical-devices/digital-health-center-excellence/cybersecurity),
[21 CFR Part 11](https://www.ecfr.gov/current/title-21/chapter-I/subchapter-A/part-11),
[PCCP guidance for AI-enabled device software](https://www.fda.gov/regulatory-information/search-fda-guidance-documents/marketing-submission-recommendations-predetermined-change-control-plan-artificial-intelligence-enabled-device-software-functions)
