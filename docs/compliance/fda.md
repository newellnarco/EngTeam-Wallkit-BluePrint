# FDA — regulated software (SaMD/SiMD, QMSR, §524B, Part 11)

**What it is.** The FDA regime for software that is or serves a medical
product: **SaMD** (software that is itself the medical device), **SiMD**
(software embedded in or controlling a device), and software whose
records support an FDA-approved application. The load-bearing pieces:
the **QMSR** (21 CFR 820 as amended, aligned with ISO 13485, in force
since February 2026) for the quality system and design controls;
**IEC 62304** for the software lifecycle by safety class, with
**IEC 81001-5-1** (FDA-recognized consensus standard) carrying the
security activities onto that same lifecycle; the premarket
pathways (**510(k) / De Novo / PMA**) with software documentation levels
per the current premarket guidance; **FD&C §524B** cyber-device duties — SBOM, a secure
product development framework, vulnerability monitoring and coordinated
disclosure, updatability — per the **final cybersecurity guidance of
June 27, 2025**, which replaced the 2023 version and added the 524B
section;
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
| LC | IEC 62304 lifecycle + IEC 81001-5-1 security activities: safety class assigned; secure development and maintenance planned to them |
| PMK | Premarket pathway identified (510(k) / De Novo / PMA) with software documentation at the level the guidance sets |
| CYB | 524B cyber-device duties per the 2025 final guidance: SBOM, secure development framework, vulnerabilities monitored and disclosed, updates deliverable |
| P11 | Part 11: electronic records and signatures trustworthy wherever records support a regulated submission |
| PMS | Postmarket: complaint handling, Part 803 adverse-event reporting, corrections and removals ready |
| CHG | Change control: whether a modification needs a new submission is decided in writing; AI-enabled change rides a PCCP (Dec 2024 final, all AI functions) |

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

Sources: [524B final cyber guidance (2025-06-27, Federal Register)](https://www.federalregister.gov/documents/2025/06/27/2025-11669/cybersecurity-in-medical-devices-quality-system-considerations-and-content-of-premarket-submissions),
[PCCP final guidance (2024-12-04)](https://www.fda.gov/regulatory-information/search-fda-guidance-documents/marketing-submission-recommendations-predetermined-change-control-plan-artificial-intelligence),
[IEC 81001-5-1](https://www.iso.org/standard/76097.html),
[FDA QMSR final rule](https://www.fda.gov/medical-devices/quality-system-qs-regulationmedical-device-current-good-manufacturing-practices-cgmp/quality-management-system-regulation-qmsr-final-rule),
[FDA device cybersecurity hub](https://www.fda.gov/medical-devices/digital-health-center-excellence/cybersecurity),
[21 CFR Part 11](https://www.ecfr.gov/current/title-21/chapter-I/subchapter-A/part-11),
[PCCP guidance for AI-enabled device software](https://www.fda.gov/regulatory-information/search-fda-guidance-documents/marketing-submission-recommendations-predetermined-change-control-plan-artificial-intelligence-enabled-device-software-functions)
