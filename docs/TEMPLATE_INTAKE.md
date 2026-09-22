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
- "How does the crew adopt a tool, server or skill it discovered?" — the
  answer is a default-deny gate or it is a standing incident
  (`docs/CAPABILITY_TRUST.md`; RULES template 2.13). Lookalike-repository
  campaigns target exactly the autonomous-agent README-reader; every shape
  that searches public ecosystems carries this rule.
- "Can the product ACT on the world, or only observe it?" — an active
  posture is its own rule set: outward-acting steps go through one loop
  (observe with evidence → concrete options tagged by blast-radius tier →
  explicit owner approval, stronger auth plus automatic pre-mutation backup
  for destructive tiers → execute the one approved action through the
  narrowest interface → return a **machine-readable undo artifact** whose
  reversal is its own gated endpoint). Never autonomous by default; an
  auto-mode, if ever added, is a per-rule owner choice, still logged and
  undoable. *(REEF's standing incident: an armed auto-resolve executor
  severed the whole LAN once — taking down the network AND the tool that
  would have undone it — and no revert brought it back.)*
- "Does any component sit on a trust boundary with privileged access?" — the
  safety ladder, safest to forbidden: scoped API → named, parameterized,
  allow-listed server-side actions → read-only telemetry sidecar → separate
  probe host → **never a general command channel on the boundary**, because
  an inbound shell on the perimeter is the exact attack pattern such a
  system exists to detect. A need that seems to require a shell is the
  signal to add a named action and revisit the decision record, not to work
  around it. *(REEF: ADR-grade, "root RCE on the perimeter".)*

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
- "When the published output IS the product, what checks the serving side?"
  — a green deploy proves the deploy script exited 0, nothing more; the
  checklist's section K (fetch the published surfaces, compare served bytes,
  probe private paths, re-probe on a schedule) exists because five new pages
  404'd for an hour in the field while the release reported success, and
  header-level protections existed only in what the host sent — invisible to
  every repository-reading check.
- "Which cheap lane exists, and is its skip a gate or an instruction?" — a
  docs-only or content-only lane is decided from the whole branch diff, per
  file, printed with reasons, expanding to the full gate on any red
  (FAST_TRACK.md); and each of its cost-saving skip rules is verified by
  watching one real change get skipped.
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
- "What may the crew hand the owner unverified?" — nothing executable: a
  command goes out run-here-first or labeled "I have not run this"
  (BEST_PRACTICES 3.21). The probe is "when did the owner last test a
  command of yours that didn't run?" — the incident behind the rule cost two
  round trips.

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
- "Who may raise a ceiling, and what must be filed when one is raised
  twice?" — never to green a failing check; compress first, and a second
  raise within days files the durable alternative (curated exports or
  retrieval) as a work item (template rule 6). *(MAX3's second raise in
  three days came only after the tripping rule was compressed and the
  retrieval item filed.)*
- "Which counted documents feed a GENERATOR rather than a session?" — every
  generator-source row belongs on the fast-track deny list, because an edit
  there changes build output and can fail the build (FAST_TRACK.md).
- "What is the plan for the day the register outgrows the window?" — a
  registry grows and a context window does not; decide curation or
  retrieval before the cap forces a silent eviction (template rule 7).

## 7. DOCS_MAP.md.template — the change-kind → doc-surfaces map

**Required:**

- Q7.1 Which change kinds exist HERE? Walk the seeded 13 and strike or add:
  what does this repo ship that changes a user-visible surface? *(MAX3: a new
  panel obligates the README views table + a design doc + the screenshot
  script + the status registry — four surfaces from one change kind.)*
- Q7.2 For each kind, which doc surfaces must move in the same change? Name
  files, not "the docs".
- Q7.3 What enforces each row? A row with no gate (lint, test, checklist
  line, review rule) is a wish — say which mechanism, or mark it
  honestly unenforced.

**LLM probes:**

- Mine merged changes: "the last five PRs that changed X — which docs moved
  with them, and which should have?" The misses are rows.
- "Which doc do people complain is always stale?" — that doc is missing from
  some kind's row, by definition.
- "Which document is authoritative for live state, and which for history?"
  — two documents both reading as current is worse than one plainly stale
  (template §3.6); and "which facts render on more than one surface, and
  what compares the surfaces where they land?" (TESTING_STANDARDS §8.6 —
  the one-fact-two-paths class no per-surface check can see).
- Shape contrasts: an appliance maps config-surface changes to its install/
  upgrade notes (REEF); a research repo maps article changes to its catalog
  and index (MRC); an extension maps permission changes to store listings
  and privacy notes (feedhacker).

## 8. OWNER_DECISIONS.md.template — what is off on purpose

**Required:**

- Q8.1 What is currently switched off, deferred or retired **on purpose**?
  Walk the surfaces that look broken and separate the three states: working,
  broken, and off-by-decision. *(REEF: a capture feature left disabled on a
  production appliance reads as a defect to every reviewer who meets it.)*
- Q8.2 For each one: the **reason**, in a sentence somebody could disagree
  with. "Not now" is not a reason; "it pages the owner at 3am for a condition
  that self-heals" is.
- Q8.3 For each one: the **lifting condition** — the observable event that ends
  the decision. Both Q8.2 and Q8.3 are required, and an entry missing either is
  ignored loudly rather than applied.
- Q8.4 Which entries cover a subject some other surface still **promises**?
  *(feedhacker: a retired feature that the help text still describes. The sweep
  for those promises lands with the entry, not after it.)*

**LLM probes:**

- Mine **closed-wontfix issues**: each one is a decision nobody wrote down, and
  the issue tracker is the wrong home for a standing suppression because
  nothing consults it before filing the same finding again.
- Mine **disabled config flags and commented-out code**: a flag set to off with
  no comment is either a decision or a bug, and only the owner knows which.
  Offer each as a proposed entry with a candidate lifting condition.
- Mine **recurring review findings that keep getting declined**: a finding
  declined three times is an unrecorded owner decision paying rent every round.
- "Is there anything here that a new reviewer always flags and you always wave
  off?" — that is the registry's first entry, in the owner's own words.
- Shape contrasts: an appliance defers hardware-dependent checks it cannot run
  in the lab (REEF); a research repo defers link-rot sweeps over an archive it
  does not control (MRC); a feed product disables an upstream whose terms
  changed (feedhacker).

## 9. REVIEWER_LANES.md.template — the review-lane register

**Required:**

- Q9.1 Which automated review lanes exist here today, and what fires each one
  (every push? open and ready only?)?
- Q9.2 Which lanes existed and **died** — and what exactly disqualified each?
  An exact disqualifier is re-checkable in a minute; "did not work out" makes
  the next session re-run the whole evaluation. *(All three sibling shapes
  carry cancelled lanes whose verdict text propagated fleet-wide precisely
  because it was exact.)*
- Q9.3 Each live lane's **meter shape** — a throttle that reopens after a
  window, or a hard stop that does not reopen until the period rolls — plus its
  measured ceiling and current headroom.
- Q9.4 What is still **owed by the owner** for each lane: an app to uninstall,
  a dashboard-side setting, a branch-protection change. A cancellation an agent
  cannot finish is tracked, never assumed.
- Q9.5 For each cancelled lane, what now covers the finding classes it used to
  catch? "Nothing yet" is an honest answer and a backlog item.

**LLM probes:**

- **Dashboard-side settings that are not in the repository at all** — the repo
  cannot derive what it does not hold, so ask the engineer to export or paste
  them; a lane configured only off-repo looks unconfigured to every check here.
- "Has any lane's config silently reverted to defaults?" — a policy-grown
  config field that crosses a vendor cap can be rejected wholesale while the
  tool keeps reviewing on its defaults, which looks entirely normal.
- "Does any lane skip the state your work sits in?" — a draft-skipping lane on
  a repo that reviews drafts is silently disabled; whichever way that is
  decided, pin it with a test in both directions.
- "What is the lane's billable event, and how many of it does YOUR workflow
  generate?" — two different questions; an agent loop produces several times
  more priced units per unit of intent than intuition predicts, and the only
  valid cost figure is one read off the vendor's meter after one real unit
  of work (TECH_EVALUATION §3b). Ask in the same breath where the lane's
  compute runs (a "free" lane can bill your CI minutes) and whether billing
  keys on the pull-request author (then automation authors as the covered
  identity, agents in Co-Authored-By).
- "What happens the day the vendor withdraws the lane?" — a free tier is a
  dependency with no contract; name the break-glass replacement kept
  installed-but-disabled, and re-count lanes on every subscription change,
  because a bundled tool can arrive with a plan upgrade unasked. *(A sibling
  shape's only active reviewer was sunset by its vendor mid-tenure.)*
- "What does each lane catch that the others don't?" — a second lane is
  bought for corroboration and mechanistic disjointness, and is
  disqualified by redundancy even on a better score (TECH_EVALUATION §3c).
- "How do this lane's findings arrive?" — anchored, replyable, resolvable
  items, required in configuration where the tool supports it; a lane that
  writes into author-owned surfaces is effectively silent.
- Shape contrasts: a repo may deliberately run **no** AI review lane at all
  (feedhacker) — that is a recorded posture with a reason, not an empty file.

*(`EVAL_RECORD.md.template` deliberately has no section here: it is filled
per evaluation via `docs/TECH_EVALUATION.md`, not at adoption time.)*

## 10. ENGINEERING_STANDARD.md.template — the method

This template is required and is never thinned: everything above its Bindings
zone is taken verbatim, and the adoption work is the zone itself. A repository
that edits the shared body has started the third copy the document exists to
prevent (`docs/FLEET.md` §3).

**Required:**

- Q10.1 What binds each Bindings slot — the failure registry, the root-cause
  register, the enforcer, the guidance consumers, the unit/integration/system/
  security levels, the two mutation slots, the session log? Name files and
  commands, never "the tests".
- Q10.2 **Which surfaces here are irreversible** — the ones where a revert does
  not restore the state? Each becomes a row in the register
  (`OWNER_DECISIONS.md` §7) with the **probe** that must report after a change
  touches it. *(An empty answer is the first gap to close, not an exemption:
  every shape has at least one — an appliance's captured traffic and any
  active-mode packet it emits; a research repo's published citations and
  anything already fetched under a licence; a feed product's writes to an
  upstream and any content it has already redistributed; a resident app's
  accumulated learning and the household data behind it.)*
- Q10.3 Who are the **guidance consumers** — every surface a rule must reach to
  count as landed? A lesson that reaches one of three graders has landed for
  one of three.

**LLM probes:**

- "Which of the three parked conflicts does this repository need ruled?" The
  template carries them as explicit markers rather than a silent default;
  surface each to the engineer with both positions quoted, and record the
  ruling as a `DEC-NNNN` before the first wave depends on it.
- "Is there a slot with nothing to bind to?" — that is the intake's most
  valuable answer, because it names a mechanism the repository does not have
  yet rather than a document it has not filled in.
- "Does anything else in this tree already claim to be the method?" A partial
  standard in a contributing guide or a role sheet is a copy that will drift;
  map it to this document and delete the overlap (the adopt skill's law).
- "What ENFORCES the consumer list?" Q10.3 names who a rule must reach; the
  harder question is what goes red when the copies disagree — "change a rule
  in one, change it in all" held by discipline is held by nothing. A test
  asserts the rule-bearing surfaces still agree and still name files that
  exist, and the checker's file list is DERIVED, not remembered: a suite
  says loudly that every file it reads is honest, and nothing about WHICH
  files it reads, so the standing question for every new rule-bearing file
  (a skill, a prompt, a config) is "what reads this, and what would go red
  if it were softened?" *(MRC: a whole class was deleted from a reviewer
  config while every suite stayed green — the file was open in the suite for
  other clauses, and outside the scan for that one.)*
- "Are requirements written about outcomes or about existence?" A
  requirement of the form "the checks exist and fail soft" yields tests
  about presence, green while the thing the mechanism exists for has never
  happened once (ITEM_AUTHORING writing rule 8).

## 11. DESIGN_DOC.md.template — the per-arc design

**Required:**

- Q11.1 Where do design documents live here — one directory, named how? The
  stories cite it by section, so the path shape is part of the contract.
- Q11.2 Which sections does this repository add or strike? The slice plan, the
  rollback story and the declared data uses are load-bearing (the first is what
  makes one story one pull request; the second is what a design is not done
  without; the third gates dispatch on in-scope arcs).
- Q11.3 Who may mark an arc's design *agreed*, and what does agreement bind —
  every criterion its stories cite, or only the approach?

**LLM probes:**

- Mine the last few completed arcs: "which decision did a Builder have to
  re-derive mid-story?" Each one is a section the design should have carried.
- "Has an arc ever shipped without a rollback story?" — if the answer is yes
  and nothing broke, that is luck, and the section stays required anyway.
- "Is the whole system exercisable end-to-end today?" — if not, which
  subsystem is *absent* rather than shallow? The skeleton-before-depth law
  (DESIGN_DOC §7) wants every subsystem present and wired, honest stubs
  included, before any is deep — and "what consumes this slice's output,
  and is the consumer in the plan?" is asked of every producer slice.
- Shape contrasts: an appliance's design names the capture boundary and the
  lab-versus-live split in its constraints; a research repo names licensing of
  anything gathered; a feed product names the upstream's terms and rate limits,
  because those bound the design before any code does.

---

## Using this document

- **Empty repo:** run the eleven sections as one batched question round (the
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

---

## How this set grows

The twelve templates are the kit's current answer to "what documents does a
disciplined repo need" — the answer is allowed to be incomplete, and the
adoption path is how it stops being incomplete:

1. **Every `/adopt inventory` reports unmapped kinds** — host documents
   serving a real function the kit has no slot for — as findings with
   evidence, beside the covered/missing verdicts.
2. **A kind graduates to a template** when it recurs across adoptions or the
   engineer names it wanted: the template is authored from the best field
   specimen (never invented speculatively), gets its section HERE with a
   question set, a row in the README docs table, and a `DEC-NNNN` recording
   why it earned a slot.
3. **The same rule in reverse:** a template no adoption has filled in three
   rounds is a candidate for removal — a slot nobody needs is drift with a
   byline, the same law as the Architect's stale-document rule.

One candidate kind is already on record from the field: the **operator cheat
sheet** — a one-page muscle-memory surface with the three-or-four commands
actually run daily, an exact-symptom → exact-fix table keyed to
failure-registry classes, a don't-do list, and the start/end-of-session
rituals; deliberately redundant with the deep documents it links. One
adoption carries the specimen (MAX3); per rule 2 it graduates when a second
adoption needs it or the engineer names it wanted.

This is the failure-registry discipline applied to the template set itself:
the field teaches, the kit graduates the lesson, and the next adoption starts
smarter than the last one did.
