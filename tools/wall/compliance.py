"""The compliance regime registry -- the machine half of docs/compliance/.

Each regime carries its self-attestation checklist (one row per control
family, the altitude a Patron attests at), the signals that suggest it
applies, and the keywords the challenge heuristic scans Warden rulings for.
The human blueprints live in ``docs/compliance/<id>.md``; a pin test keeps
every control id here present in its document, so the page's popout and the
prose can never disagree about what is being attested.

Grounded against the current authorities (2026-09, DEC-0028): PCI DSS
v4.0.1 (fully mandatory since 2025-03-31), the HIPAA Security Rule in force
(2013) with the 2025 NPRM noted as pending (~2027), SOC 2 = 2017 Trust
Services Criteria with 2022 Revised Points of Focus, GDPR + CCPA/CPRA with
the 2026 California regulations, FedRAMP Rev5/20x, CJIS v6.x on NIST
800-53. Translation, not reproduction: the checklists are the kit's
self-attestation framing of public structures, and the documents cite the
sources.

Verdicts a control can hold: ``pass`` | ``fail`` | ``waiver`` (a waiver is
a RECORDED exception with its reason -- never silence).
"""

from __future__ import annotations

ATTEST_STATUSES = ("pass", "fail", "waiver")

REGIMES = (
    {
        "id": "soc2",
        "name": "SOC 2 (2017 TSC, 2022 Points of Focus)",
        "doc": "docs/compliance/soc2.md",
        "applies_when": "customers or partners ask for assurance over the "
                        "service's security posture; B2B SaaS almost always",
        "keywords": ("soc 2", "soc2", "trust services", "aicpa"),
        "controls": (
            ("CC1", "Control environment: integrity, oversight, accountability are real and assigned"),
            ("CC2", "Communication and information: policies reach the people they bind"),
            ("CC3", "Risk assessment: risks identified, analyzed, and responded to on a cadence"),
            ("CC4", "Monitoring: controls are evaluated and deficiencies reach the right people"),
            ("CC5", "Control activities: controls exist at the process level, not just on paper"),
            ("CC6", "Logical and physical access: least privilege, credential lifecycle, boundary protection"),
            ("CC7", "System operations: anomaly detection, incident response, recovery"),
            ("CC8", "Change management: changes authorized, tested, approved, tracked"),
            ("CC9", "Risk mitigation: vendor and business-disruption risk handled"),
            ("A1", "Availability (optional category): capacity, backup, recovery objectives met"),
            ("PI1", "Processing integrity (optional): processing is complete, valid, accurate, timely"),
            ("C1", "Confidentiality (optional): confidential data identified and protected to disposal"),
            ("P1", "Privacy (optional): personal information handled per the privacy notice"),
        ),
    },
    {
        "id": "hipaa",
        "name": "HIPAA / PHI (Security, Privacy, Breach Rules)",
        "doc": "docs/compliance/hipaa.md",
        "applies_when": "the system creates, receives, maintains or transmits "
                        "protected health information, or serves one that does "
                        "(business associate)",
        "keywords": ("hipaa", "phi", "health", "baa", "business associate"),
        "controls": (
            ("SR-ADM", "Administrative safeguards (164.308): risk analysis, workforce training, access management, contingency plan"),
            ("SR-PHY", "Physical safeguards (164.310): facility access, workstation and device controls"),
            ("SR-TEC", "Technical safeguards (164.312): access control, audit controls, integrity, transmission security, encryption"),
            ("SR-ORG", "Organizational (164.314): BAAs with every business associate -- a hosted LLM included"),
            ("SR-DOC", "Policies and documentation (164.316): written, retained six years, updated"),
            ("PR-MIN", "Privacy Rule: minimum necessary uses and disclosures"),
            ("BN-NOT", "Breach Notification (164.400s): discovery clocks, individual and HHS notice"),
        ),
    },
    {
        "id": "pci",
        "name": "PCI DSS v4.0.1",
        "doc": "docs/compliance/pci.md",
        "applies_when": "cardholder data is stored, processed or transmitted, "
                        "or the system can affect the security of a payment flow",
        "keywords": ("pci", "cardholder", "pan", "payment"),
        "controls": (
            ("R1", "Network security controls installed and maintained"),
            ("R2", "Secure configurations applied to all system components"),
            ("R3", "Stored account data protected (no PAN in logs or fixtures, ever)"),
            ("R4", "Cardholder data encrypted over open, public networks"),
            ("R5", "Malicious software protected against"),
            ("R6", "Secure systems and software developed and maintained"),
            ("R7", "Access restricted by business need to know"),
            ("R8", "Users identified and access authenticated (MFA)"),
            ("R9", "Physical access to cardholder data restricted"),
            ("R10", "Access to system components and cardholder data logged and monitored"),
            ("R11", "Security of systems and networks tested regularly"),
            ("R12", "Information security supported by organizational policies (incl. 12.5.2 scope re-confirmation)"),
        ),
    },
    {
        "id": "privacy",
        "name": "PII / Privacy (GDPR, CCPA/CPRA, state laws)",
        "doc": "docs/compliance/privacy.md",
        "applies_when": "personal information of EU residents (GDPR) or of "
                        "residents of California and ~20 other US states is "
                        "collected or processed",
        "keywords": ("gdpr", "ccpa", "cpra", "pii", "personal data",
                     "privacy", "data subject"),
        "controls": (
            ("LB", "Lawful basis and notice: a named basis (GDPR) or compliant notice + opt-out (CCPA/CPRA) per processing purpose"),
            ("MIN", "Minimization and purpose limitation: collect what the purpose needs, nothing more"),
            ("RTS", "Subject rights served: access, deletion, correction, portability, opt-out of sale/share"),
            ("SEC", "Security of processing (GDPR art. 32): appropriate technical and organizational measures"),
            ("XFR", "Cross-border transfers: residency and transfer mechanisms per jurisdiction"),
            ("BRK", "Breach clocks: 72-hour authority notice (GDPR) and state-law equivalents"),
            ("VND", "Processor contracts: DPAs with every processor -- a hosted LLM included"),
            ("ADM", "Automated decision-making: risk assessments and opt-outs (CPRA 2026 regulations)"),
        ),
    },
    {
        "id": "government",
        "name": "Government reach (FedRAMP, CJIS, CLOUD Act, export)",
        "doc": "docs/compliance/government.md",
        "applies_when": "US federal agencies are customers (FedRAMP), criminal "
                        "justice information is touched (CJIS), or data faces "
                        "law-enforcement reach / export control",
        "keywords": ("fedramp", "cjis", "cloud act", "itar", "ear",
                     "federal", "government"),
        "controls": (
            ("FR", "FedRAMP: authorization path chosen (Rev5 baseline or 20x), boundary defined, continuous monitoring"),
            ("CJ", "CJIS Security Policy (v6.x, NIST 800-53 aligned): CJI identified and controls mapped"),
            ("RES", "Residency and reach: provider and region choices evaluated against CLOUD Act / Patriot Act exposure"),
            ("EXP", "Export control: ITAR/EAR-controlled technical data identified and segregated"),
        ),
    },
    {
        "id": "sector",
        "name": "Sector rules (SOX, GLBA, FERPA)",
        "doc": "docs/compliance/sector.md",
        "applies_when": "public-company financial reporting (SOX), consumer "
                        "financial data (GLBA), or education records (FERPA) "
                        "are in scope",
        "keywords": ("sox", "glba", "ferpa", "financial reporting",
                     "education records", "safeguards rule"),
        "controls": (
            ("SOX", "SOX ICFR: change control and access evidence over systems feeding financial reports"),
            ("GLB", "GLBA Safeguards Rule: written infosec program, risk assessment, MFA, encryption, vendor oversight"),
            ("FER", "FERPA: education records identified, disclosures consent-gated, directory-info opt-outs honored"),
        ),
    },
)

REGIME_IDS = tuple(r["id"] for r in REGIMES)


def regime(regime_id: str):
    for r in REGIMES:
        if r["id"] == regime_id:
            return r
    return None


def control_ids(regime_id: str) -> tuple:
    r = regime(regime_id)
    return tuple(c[0] for c in r["controls"]) if r else ()
