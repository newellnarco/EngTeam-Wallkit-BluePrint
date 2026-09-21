# PII / Privacy — GDPR, CCPA/CPRA, and the US state laws

**What it is.** The personal-information regimes. **GDPR** (EU, 2018)
binds any organization processing EU residents' data wherever it sits:
named lawful basis, minimization, subject rights, 72-hour breach notice,
processor contracts (DPAs), transfer mechanisms. **CCPA/CPRA**
(California) is opt-out-shaped with its own enforcement agency; the
**2026 regulations added mandatory cybersecurity audits, risk
assessments for automated decision-making, and the Delete Act's
broker opt-out platform**. Roughly **20 US states** now run comparable
comprehensive laws (Virginia, Colorado, ... Indiana/Kentucky/Rhode
Island effective 2026-01-01).

**Applies when** personal information of EU residents or covered-state
residents is collected or processed — thresholds vary (CCPA: $25M
revenue, or 100k residents' data, or 50% revenue from selling data).

## Self-attestation checklist (`wall attest privacy <id>`)

| Id | The Patron attests |
|---|---|
| LB | Lawful basis and notice: a named basis (GDPR) or compliant notice + opt-out (CCPA/CPRA) per processing purpose |
| MIN | Minimization and purpose limitation: collect what the purpose needs, nothing more |
| RTS | Subject rights served: access, deletion, correction, portability, opt-out of sale/share |
| SEC | Security of processing (GDPR art. 32): appropriate technical and organizational measures |
| XFR | Cross-border transfers: residency and transfer mechanisms per jurisdiction |
| BRK | Breach clocks: 72-hour authority notice (GDPR) and state-law equivalents |
| VND | Processor contracts: DPAs with every processor — a hosted LLM included |
| ADM | Automated decision-making: risk assessments and opt-outs (CPRA 2026 regulations) |

**The kit's intersection:** MIN is the data charter's first
ways-forward entry (minimize before you protect); VND is the exposure
ladder's in-the-LLM rung — a hosted model processing personal data is a
processor needing paper; XFR is why "encrypted" does not answer "may it
leave Germany" (`DATA_PROTECTION.md` §2).

**Waivers.** A right not applicable to the data actually held (e.g.
portability where no account data exists) is a `waiver` with that
reasoning — the reasoning is what an authority asks for first.

Sources: [Data privacy laws 2026 (Osano)](https://www.osano.com/articles/data-privacy-laws),
[CCPA requirements 2026](https://secureprivacy.ai/blog/ccpa-requirements-2026-complete-compliance-guide),
[GDPR vs CCPA](https://usercentrics.com/knowledge-hub/gdpr-vs-ccpa-compliance/)
