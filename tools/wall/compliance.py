"""The compliance regime registry -- the machine half of docs/compliance/.

Each regime carries its self-attestation checklist (one row per control
family, the altitude a Patron attests at), the signals that suggest it
applies, and the keywords the challenge heuristic scans Warden rulings for.
The human blueprints live in ``docs/compliance/<id>.md``; a pin test keeps
every control id here present in its document, so the page's popout and the
prose can never disagree about what is being attested.

Grounded against the current authorities (2026-09, DEC-0028; NIST + FDA
and the adjacent-healthcare widening under DEC-0031): PCI DSS v4.0.1
(fully mandatory since 2025-03-31); the HIPAA Security Rule in force
(2013) with the 2025 NPRM final delayed to ~2027; 42 CFR Part 2 in force
and OCR-enforced since 2026-02-16; the FTC HBNR (effective 2024-07-29)
for non-HIPAA health data; ASTP/ONC information blocking + HTI
certification (USCDI v3 baseline 2026-01-01); SOC 2 = 2017 TSC with 2022
Revised Points of Focus; GDPR + CCPA/CPRA with the 2026 California
regulations; FedRAMP Rev5/20x, CJIS v6.x on NIST 800-53; NIST CSF 2.0,
SP 800-171 r3 (2024-05) and SSDF 800-218 as modified in practice by EO
14306 (2025-06); and the FDA stack for regulated software (QMSR in force
2026-02-02, IEC 62304 + IEC 81001-5-1, the 524B final cyber guidance of
2025-06-27 replacing 2023, 21 CFR Part 11, the PCCP final of 2024-12-04
covering all AI-enabled functions).
Translation, not reproduction: the checklists are the kit's
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
        "name": "Healthcare privacy (HIPAA/PHI, Part 2, HBNR, info blocking)",
        "doc": "docs/compliance/hipaa.md",
        "applies_when": "the system creates, receives, maintains or transmits "
                        "protected health information, or serves one that does "
                        "(business associate)",
        "keywords": ("hipaa", "phi", "health", "baa", "business associate",
                     "part 2", "substance use", "information blocking",
                     "health app", "tefca"),
        "controls": (
            ("SR-ADM", "Administrative safeguards (164.308): risk analysis, workforce training, access management, contingency plan"),
            ("SR-PHY", "Physical safeguards (164.310): facility access, workstation and device controls"),
            ("SR-TEC", "Technical safeguards (164.312): access control, audit controls, integrity, transmission security, encryption"),
            ("SR-ORG", "Organizational (164.314): BAAs with every business associate -- a hosted LLM included"),
            ("SR-DOC", "Policies and documentation (164.316): written, retained six years, updated"),
            ("PR-MIN", "Privacy Rule: minimum necessary uses and disclosures"),
            ("BN-NOT", "Breach Notification (164.400s): discovery clocks, individual and HHS notice"),
            ("P2", "42 CFR Part 2 (in force 2026-02-16, OCR-enforced): SUD records identified, segregated, consent-tracked; NPP updated"),
            ("HBN", "FTC Health Breach Notification Rule (2024): non-HIPAA health data in apps/devices covered, breach clocks known"),
            ("IB", "Information blocking + certified health IT (ASTP/ONC): no practice that blocks EHI; certification duties current where the product is certified"),
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
    {
        "id": "nist",
        "name": "NIST (CSF 2.0, SP 800-171 r3, SSDF 800-218)",
        "doc": "docs/compliance/nist.md",
        "applies_when": "a contract, customer or program requires NIST "
                        "alignment: CSF 2.0 as the named framework, 800-171 "
                        "for CUI in a federal supply chain, SSDF attestation "
                        "for software sold to the US government",
        "keywords": ("nist", "csf", "800-53", "800-171", "800-218", "ssdf",
                     "cui", "cybersecurity framework", "sprs"),
        "controls": (
            ("GV", "CSF Govern: risk strategy, roles, policy, oversight and supply-chain risk management established and owned"),
            ("ID", "CSF Identify: assets, risks and improvement opportunities inventoried and assessed"),
            ("PR", "CSF Protect: identity and access, awareness, data security, platform security, resilience"),
            ("DE", "CSF Detect: continuous monitoring and adverse-event analysis in place"),
            ("RS", "CSF Respond: incident management, analysis, reporting and mitigation exercised"),
            ("RC", "CSF Recover: recovery execution and communications planned and tested"),
            ("CUI", "SP 800-171 r3 (conditional): CUI identified, controls mapped, the self-assessment score current and true"),
            ("SSD", "SSDF SP 800-218: secure-development practices mapped for the software produced; attestation ready where a buyer requires it"),
        ),
    },
    {
        "id": "fda",
        "name": "FDA-regulated software (SaMD/SiMD, QMSR, 524B, Part 11)",
        "doc": "docs/compliance/fda.md",
        "applies_when": "the software is a medical device (SaMD), is embedded "
                        "in or controls one (SiMD), or produces records "
                        "supporting an FDA-approved application (drug, "
                        "biologic, device)",
        "keywords": ("fda", "samd", "simd", "medical device", "510(k)", "pma",
                     "de novo", "qmsr", "62304", "part 11", "sbom", "524b",
                     "pccp"),
        "controls": (
            ("QMS", "QMSR quality system with design controls established (ISO 13485-aligned, in force 2026-02)"),
            ("LC", "IEC 62304 lifecycle + IEC 81001-5-1 security activities: safety class assigned; secure development and maintenance planned to them"),
            ("PMK", "Premarket pathway identified (510(k) / De Novo / PMA) with software documentation at the level the guidance sets"),
            ("CYB", "524B cyber-device duties per the 2025 final guidance: SBOM, secure development framework, vulnerabilities monitored and disclosed, updates deliverable"),
            ("P11", "Part 11: electronic records and signatures trustworthy wherever records support a regulated submission"),
            ("PMS", "Postmarket: complaint handling, Part 803 adverse-event reporting, corrections and removals ready"),
            ("CHG", "Change control: whether a modification needs a new submission is decided in writing; AI-enabled change rides a PCCP (Dec 2024 final, all AI functions)"),
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


# ------------------------------------------------------------ the repo scan
# The Warden's periodic evidence pass (DEC-0030): does the CODE suggest a
# regime applies?  Deterministic and dumb on purpose -- it greps tracked text
# for the regime's keywords plus a few code-shaped signals, and reports WHERE
# it matched, so a recommendation always arrives with its evidence and a
# human (or the Warden) argues with the evidence, not with a score.  It never
# flips a selection: the fold turns scan + selection into a disposition and
# the decision stays the Patron's.

#: Code-shaped signals per regime, beyond the ruling keywords: dependency and
#: identifier fragments that show up when the DATA shows up.
SCAN_SIGNALS = {
    "soc2": ("audit log", "access control", "customer data"),
    "hipaa": ("patient", "medical record", "diagnosis", "fhir", "hl7",
              "icd-10", "icd10"),
    "pci": ("stripe", "braintree", "cardholder", "card number", "payment"),
    "privacy": ("personal data", "biometric", "face recognition",
                "speaker id", "voiceprint", "user profile", "email address",
                "consent"),
    "government": ("fedramp", "cjis", "itar", "export control"),
    "sector": ("financial reporting", "student record", "education record",
               "safeguards rule"),
}

#: Paths whose mention of a regime is ABOUT compliance rather than evidence
#: of the data: the vendored kit, the ledger, and the compliance documents
#: themselves.  Without this, every adopting repo would "need" every regime
#: because the blueprints name them all.
SCAN_SKIP_PREFIXES = ("tools/wall/", ".wall/", ".claude/", "docs/compliance/",
                      "docs/decisions/")
SCAN_SKIP_NAME_PARTS = ("compliance", "data_protection")

_SCAN_MAX_BYTES = 512 * 1024
_EVIDENCE_CAP = 5


def _tracked_files(root):
    """git ls-files when the repo has git, a bounded walk when it does not."""
    import subprocess
    from pathlib import Path
    root = Path(root)
    try:
        out = subprocess.run(["git", "ls-files"], cwd=str(root),
                             capture_output=True, text=True, timeout=30)
        if out.returncode == 0:
            return [p for p in out.stdout.splitlines() if p.strip()]
    except (OSError, subprocess.SubprocessError):
        pass
    skip_dirs = {".git", "node_modules", ".venv", "__pycache__", "dist"}
    found = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        if any(part in skip_dirs for part in p.parts):
            continue
        found.append(rel)
    return found


def scan_repo(root) -> dict:
    """Evidence per regime id: a list of 'path -- matched <signal>' strings,
    empty when nothing in the tree suggests the regime.  A regime with any
    evidence is RECOMMENDED; the caller records both, verbatim.

    Signals match on WORD BOUNDARIES: 'pan' must not fire inside 'expand'
    nor 'ear' inside 'research' — a recommendation built on substring noise
    teaches people to ignore the Warden."""
    import re
    from pathlib import Path
    root = Path(root)
    patterns = {}
    for r in REGIMES:
        rid = r["id"]
        words = tuple(dict.fromkeys(tuple(r["keywords"]) +
                                    SCAN_SIGNALS.get(rid, ())))
        patterns[rid] = [
            (w, re.compile(r"(?<![a-z0-9])" +
                           re.escape(w).replace(r"\ ", r"[\s_-]+") +
                           r"(?![a-z0-9])"))
            for w in words]
    evidence = {rid: [] for rid in patterns}
    for rel in _tracked_files(root):
        low = rel.lower()
        if any(low.startswith(p) for p in SCAN_SKIP_PREFIXES):
            continue
        if any(part in low for part in SCAN_SKIP_NAME_PARTS):
            continue
        path = root / rel
        try:
            if path.stat().st_size > _SCAN_MAX_BYTES:
                continue
            text = path.read_text(encoding="utf-8", errors="replace").lower()
        except OSError:
            continue
        for rid, pats in patterns.items():
            if len(evidence[rid]) >= _EVIDENCE_CAP:
                continue
            for w, pat in pats:
                if pat.search(text):
                    evidence[rid].append(f"{rel} -- matched {w!r}")
                    break
    return evidence
