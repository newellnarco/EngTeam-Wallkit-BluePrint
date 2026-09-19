# TEMPLATE_INTAKE.md

The question sets that fill the root templates. Each template gets two layers:

1. **Required questions** — must be answered (by the engineer, or by a cited
   derivation from the repo) before the document counts as filled. A template
   with placeholders replaced by plausible filler is worse than one left
   blank: it reads as decided when nobody decided.
2. **LLM probes** — the important-but-unasked layer. The session reads the
   repo and the engineer's answers, then probes for what the required set
   could not know to ask. Probes are offered with a proposed default so a
   confirmation costs one word; every probe answer cites what prompted it.

The mechanics are PRODUCT_INTAKE.md's: derive first with evidence, batch the
rest per template onto the human queue, land every answer in the filled
document (and as a `DEC-NNNN` where it is a ruling). The worked examples
below come from the reference deployment ("a local-first AI resident" —
MAX3), with contrasts from three sibling project shapes so the questions read
as a method, not a questionnaire about one product:

| Shape | Example | What it stresses |
|---|---|---|
| Local-first resident app | MAX3 | Privacy defaults, one-box ops, voice latency, a deployed tree beside the repo |
| Network/security appliance | REEF (netsniff) | Captured traffic is sensitive by nature; privileged capture access; passive-vs-active posture |
| Research collective / knowledge repo | MRC | Provenance and citation discipline; licensing of gathered material; multiple contributors |
| Feed/ingestion product | feedhacker | Third-party terms and rate limits; schema drift; dedup; retention of pulled content |

---

## 1. CLAUDE.md.template — the entry point

**Required:**

- Q1.1 What is this project, in one sentence a new session acts on? *(MAX3:
  "a local-first, multi-user, voice-first AI Resident that runs as a single
  Python process on one workstation.")*
- Q1.2 What is it explicitly NOT? *(MAX3: not a SaaS, not multi-tenant, not a
  general agent framework — three refusals that killed whole classes of bad
  PRs before they were written.)*
- Q1.3 Where is the canonical truth when documents disagree? *(MAX3: the
  design document is canonical; the entry point is a derived reference and
  says so — "if they conflict, this file is wrong; flag it.")*
- Q1.4 Where do the rules live, and what is the reading order? *(MAX3: a
  STOP block at the top: standing rules first, then failure registry, then
  checklist — in that order, before any work.)*
- Q1.5 Who is the owner and what is the working cadence? *(MAX3: a solo
  developer, part-time — which sizes waves and explains the autonomy level.)*

**LLM probes:**

- Any predecessor system? Name it and the relationship, or a session will
  conflate them. *(MAX3: HAL, "the predecessor on disk — not the movie
  reference"; a probe nobody would have thought to ask for.)*
- Standing naming/voice directives? *(MAX3: "always 'our AI Resident',
  never 'an AI assistant'" — a user direction that binds all copy; the probe
  is "is there any phrase I must always or never use?")*
- Session-start ritual beyond reading? *(MAX3: verify platform identity,
  run the fleet exchange; probe: "what must a session do before its first
  edit that a README would not say?")*
- Shape contrasts: an appliance's entry point names the capture boundary and
  the lab-vs-live distinction first (REEF); a research repo names the
  citation rule first (MRC); a feed product names the upstreams and their
  terms first (feedhacker).

## 2. RULES.md.template — the hard rules (Part 1 is the engineer's)

**Required:**

- Q2.1 What is the deployment/privacy stance? Local-first, cloud-first, or
  mixed — and what may never leave the machine/boundary? *(MAX3: local-first
  as hard rule 1; cloud is fallback with provenance marked and confidence
  capped.)*
- Q2.2 Dependency policy: licenses allowed, who approves a new one? *(MAX3:
  OSS-only with license named per dependency, every new dep listed in the
  drop notes.)*
- Q2.3 Honesty/stub discipline: how does unfinished work present itself?
  *(MAX3: stubs carry a visible marker and return honest fake data — the
  no-silent-stub rule the kit generalized into its honesty rules.)*
- Q2.4 What data does the system hold about people, and what is the default
  visibility? *(MAX3: multi-user, default-private per user, memory is a hint
  never an authority.)*
- Q2.5 Autonomy boundary: what may the crew do unasked, what needs the
  engineer, and is there an override window? *(MAX3: act-and-audit with a
  30-second override window replacing an approval queue — a written,
  reversible autonomy grant.)*
- Q2.6 The meta-rule: who may change these rules, and how? *(MAX3: only the
  user, in writing. Non-negotiable in every shape.)*
- Q2.7 Reversibility: what must always be undoable, and what is the rollback
  artifact? *(MAX3: every applied optimisation ships with a rollback recipe.)*

**LLM probes:**

- "What would make you rip a merged change out on sight?" — each answer is a
  hard rule not yet written. *(This is how MAX3's confidence+provenance rule
  reads in interview form.)*
- "Which regulatory frames touch this?" — routes to the Warden's corpus
  (COMPLIANCE_POSTURE.md). *(REEF: intercepted traffic may be legally
  sensitive per jurisdiction — the probe is mandatory for an appliance.
  feedhacker: scraping terms + copyright of pulled content. MRC: licensing
  of collected research. MAX3: household members' biometric/voice data.)*
- "Is there a resource the product must never contend with?" *(MAX3: the
  voice loop's latency budget — background work yields, encoded as a hard
  rule with a contention gate. An appliance's equivalent: never drop
  packets; a feed product's: never hammer an upstream past its limits.)*
- "What counts as identity in your data model?" *(MAX3: correlation IDs on
  every event; the probe generalizes to 'what joins your audit trail'.)*

## 3. FAILURE_PATTERNS.md.template — the registry

**Required:**

- Q3.1 What has already failed here? Mine postmortems, issue tracker,
  reverts (`git log --grep` for revert/fix/hotfix), and the engineer's
  memory: "name the last three things that bit you twice." Each becomes an
  entry with symptom, root cause, and the check that would have caught it.
- Q3.2 Which platforms/environments does this ship to? Every platform pair
  is a failure-class family. *(MAX3: Windows PowerShell 5.1 vs 7 cmdlet
  drift, CRLF smudge rules, cp1252 mojibake — a whole family the registry
  carries because the box is Windows and CI is Linux.)*

**LLM probes:**

- First-run/install classes: "what breaks on a clean machine that works on
  yours?" *(MAX3: model files not shipped with the wheel, fetched at
  install; parse-time `%ERRORLEVEL%` in batch scripts.)*
- Shape-specific seeds to offer: appliance — privileged capture setup,
  interface naming drift, pcap rotation filling disks (REEF); feed product —
  upstream schema drift, rate-limit bans, dedup collisions (feedhacker);
  research repo — dead-link rot, citation-format drift (MRC); resident app —
  device/driver churn, audio-stack regressions (MAX3).
- "Does any tool integration have a quota?" — quota exhaustion mid-run is a
  registered class everywhere it exists.

## 4. SHIP_CHECKLIST.md.template — the pre-ship gate

**Required:**

- Q4.1 What does "shipped" mean here — merged? deployed to a box? tagged?
  *(MAX3: merged AND live on the deployed tree one auto-pull later, so the
  checklist includes the deployed-manifest comparison — `wall verify --app`
  exists because of this answer.)*
- Q4.2 What are the non-CI gates? Docs updated in the same PR? Screenshots
  for UI changes? Board/status flips? *(MAX3: docs discipline — every
  user-visible change updates its doc in the same PR; screenshot discipline
  for panels; board fragment rides the PR.)*
- Q4.3 Who may throw a drop back, on what grounds? *(MAX3: the user has
  explicit permission to bounce any drop that skipped a checklist item.)*

**LLM probes:**

- "How do you read a green?" — pin the exact rule for interpreting checks.
  *(MAX3's measured lesson: a scoped draft run can read green without being
  the full pyramid; the checklist's step 0 is HOW to read CI, not just
  'CI green'.)*
- "Is there a step everyone does from memory?" — that step is the next
  checklist item, verbatim.
- Shape contrasts: an appliance ships a capture-safety check (never ship a
  build that defaults to promiscuous capture ON); a feed product ships a
  dry-run against recorded upstream fixtures; a research repo ships a
  link-and-license sweep.

## 5. BEST_PRACTICES.md.template — the shared criteria

**Required:**

- Q5.1 Stack and idiom anchors: which existing files exemplify "how we write
  it here"? (The body's rules cite them.)
- Q5.2 Which graders read this, through what mechanism? *(MAX3: three
  graders, one body — the session via the entry point, one hosted reviewer
  via its knowledge base, another via its own instruction files — with the
  measured directory-scoping trap written down so a rule is verified to
  actually reach each grader.)*
- Q5.3 The project-specific honesty rules beyond the six seeded ones — take
  them from RULES Q2.3's answer so the two documents agree by construction.

**LLM probes:**

- Mine the diff history: "the same fix shape three times" is a candidate
  rule. *(MAX3 grew rules like 'never read a variable inside a paren block
  without delayed expansion' from exactly this mining.)*
- "Which reviewer comment do you keep making by hand?" — that comment is a
  rule that belongs in the body, where every grader makes it for you.

## 6. BUDGETED_DOCS.md.template — the prompt-budget register

**Required:**

- Q6.1 Which documents feed model prompts, and through what loader? (Entry
  point, standards file, reviewer instruction files, role sheets.)
- Q6.2 Each one's hard limit and the measuring command. *(MAX3: a hosted
  reviewer's 110K-token instruction cap — discovered when reviews started
  failing with the entry-point file at ~80% of it; and a 44,000-character
  harvested-prompt budget that once sat 53 characters from failure. Both
  numbers exist because nobody measured until it broke.)*
- Q6.3 The ratchet rule: extending a counted section requires measuring in
  the same change — confirm the engineer wants it enforced (the kit says
  yes; it is theirs to relax in writing).

**LLM probes:**

- "Any tool that silently truncates?" — a truncating loader is worse than a
  failing one (a reviewer that half-reads the rules enforces half the
  rules); register it with a margin, not just a limit.
- Per-lane caps for every reviewer wired via the reviewer-integration skill
  — the skill's step 5 lands here.

---

## Using this document

- **Empty repo:** run the six sections as one batched question round (the
  one moment a batch beats a trickle — README empty-repo runbook step 2).
- **Existing repo:** derive first. Most answers are already in the tree
  under other names; the questions become confirmations with evidence
  attached, and only the genuinely unanswered reach the engineer.
- **Every answer lands twice:** in the filled document, and — where it is a
  ruling rather than a fact — as a `DEC-NNNN` so the contradiction check can
  see it.
- The probes are a floor, not a ceiling: a probe that surfaces something
  important gets added HERE, so the next adoption asks it as a matter of
  course. This document graduates questions the way the failure registry
  graduates bugs.
