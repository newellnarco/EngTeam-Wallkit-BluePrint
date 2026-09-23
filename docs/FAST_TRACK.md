# FAST_TRACK.md

A route for doc-only changes: no CI, no reviewer dispatch, fewest GitHub minutes.

**This is not a new concept.** Most repositories already classify changed files
into doc and source buckets somewhere - a push script, a skill, somebody's head -
and block on source. Fast-track promotes that rule from prose into config so the
courier, CI and the agents read one definition instead of three copies drifting
apart.

---

## Classification is mechanical

Routed on the changed file set alone, computed from `git diff --name-only`.
**Never asserted by an agent.** If agents can self-declare their route, every
builder eventually discovers that calling its work a doc skips the gates.

- Every path matches the allow list -> fast-track.
- Any path falls outside it -> full track.

No mixed mode, no partial credit.

An illustrative config (tune the globs to your host; the shape is what is
fixed):

```json
{
  "fast_track": {
    "allow": ["**/*.md", "docs/**/*.docx", "MANIFEST.sha256"],
    "deny":  ["frontend/src/**", "backend/**/*.py", "**/*.bat", "**/*.ps1",
              ".github/workflows/**", "tools/**", ".wall/config/**",
              "**/CLAUDE.md"]
  }
}
```

**Deny beats allow, always.** Four entries are worth defending:

- `.github/workflows/**` - a builder editing CI to turn its own tests green is
  the classic escape hatch. It is code.
- `**/CLAUDE.md` - it matches `**/*.md`, so the allow glob would fast-track it,
  but it changes the behavior of every future agent. It is code.
- `tools/**` - wall tooling can corrupt the ledger. Not a doc.
- **Every document a generator or prompt-builder consumes** - a standards
  file compiled into a reviewer prompt, a failure registry that seeds
  instruction files, anything a build step reads. An edit there changes a
  generated artifact and can fail the build (a sibling deployment's prompt
  build refused at 862 characters over its ceiling on a "docs-only" edit),
  so it takes the full gate. By construction, every generator-source row in
  the budget register (`BUDGETED_DOCS`) is on this deny list - the two files
  cross-reference.

Three refinements the sibling deployments paid for:

- **The route is a property of the BRANCH, never of the newest commit.**
  Classify from the pull request's whole diff against its base; a code file
  pushed earlier does not become invisible because the latest commit is
  prose.
- **Classify by what a file IS, not what it looks like.** Generated markdown
  a builder writes - a catalog, an index, a glossary queue - is build output,
  not documentation, and takes the content's checks, not the doc lane's.
- **Print the decision, and a red lane expands.** The chosen route and
  everything skipped are printed with reasons on every path, and any red on
  the cheap lane expands to the full gate and prints that it did. A lane is
  proven the way the full gate is: offer the lane's checks every relevant
  mutation.

Mixed changesets **split** rather than get an exception, which is what a good
push routine already tells you to do by hand. `wall fast-track` offers the
split: stage the doc-only subset, fast-track it, leave the rest on the full track.

---

## CI scoping belongs to the host repository

**This section used to specify the plumbing. It no longer does.** The original
design was `paths-ignore` on the documentation globs, plus a companion workflow
on the inverse paths reporting the same check name so branch protection would
not block forever on a check that never ran. That design is **superseded**
(`docs/RECONCILIATION.md` Q4): the reference deployment does not use
`paths-ignore` at all, and what it does instead is both cheaper and harder to
get wrong.

What a mature host looks like, and what to build if yours has nothing yet:

- A **detect-docs-only job** that computes the change class from the file set,
  in the workflow rather than in a filter.
- **Tier scoping by state** - a draft head runs a reduced but honest set of
  tiers; marking ready fires the full pyramid.
- **Static literal job names.** A skipped job's name is rendered before most
  contexts exist, so a name computed from an expression renders as raw
  expression text, and a merge gate matching on name cannot find it. That class
  recurred five times in the reference deployment before it was pinned.
- **An attestation job** whose conclusion is the required check, so the gate is
  one stable name regardless of how many shards or tiers ran underneath it.
- **A scoped lane is validated by its escape rate, and a scope that lets broken
  work through green is retired IN CODE.** Measured: one reduced scope carried
  four broken fixtures and three failing tests through three consecutive green
  checks. The retirement belongs in the selector's own source - a named,
  tested refusal of that scope - because a scope disabled only in configuration
  is one quiet edit away from being back, and nothing announces that edit.
  Configuration can still widen a scope; it must not be able to resurrect one
  that was retired for letting defects through.
- **A scheduled full run stays as the backstop that makes any scoped selector
  safe.** A periodic unscoped pyramid on the mainline bounds how long a
  selector bug can hide: without it, the only evidence a scope is wrong is the
  defect it let out. The scoped lane buys speed; the scheduled run is what makes
  buying it responsible.

The wall does not add path filters beside any of that. Two mechanisms deciding
what runs is how a change ends up with no gate at all.

**What the wall contributes instead** is the classification above - one
definition of the route, read by the courier, the agents and any host job that
wants it - and the honesty rule that goes with it: the route is computed from
the file set and is never asserted by the agent doing the work.

One consequence to carry into every merge: a reduced or draft-scoped run can
report green without being the gate. Confirm the **name** of the green check is
the one branch protection requires before merging. That check caught two
would-have-been-early merges in a single wave.

### The meter is part of the design

CI is metered, and the meter is spent by decisions taken long before anyone
looks at a bill. **Name the question a run answers, and the cheapest meter that
answers it, BEFORE spending it** - an action that cannot name its question is a
guess, and it is billed as one. Five rules follow from that, each earned:

- **Every job carries a `timeout-minutes`.** A hung job does not fail cheaply;
  it bills to the vendor's own ceiling, which is generous because it is not
  your money being defaulted.
- **A `schedule:` trigger must state why the work cannot be event-driven.** A
  schedule pays on the calendar rather than on the change, so the justification
  is written beside the cron line or the trigger becomes a dispatch.
- **Cancelled runs still bill for the time they ran.** Superseding your own
  in-flight run is not free, which is the cost side of never pushing while
  checks are running.
- **Jobs bill rounded up to the minute**, so five twenty-second jobs cost five
  minutes. Splitting a pipeline into many tiny jobs buys parallelism with
  rounding.
- **Measure before optimising, and report the reading beside the result.** A
  meter reading in the log after the fact changes nothing; the same number in
  the report is what makes the next scoping decision cheaper.

Three levers that pay for themselves the day they are set, none of which is a
decision about *what* to run:

- **Scope the push trigger to the default branch and pull requests, never every
  branch.** A pipeline that fires on every push of every work-in-progress
  commit bills the whole pyramid for commits nobody has looked at yet — the
  single biggest blowout in the corpus this kit was mined from. The work-in-
  progress signal is the local gate; the hosted one is for a head somebody is
  asking about. A project may deliberately keep `push` on working branches as
  a second trigger path, so a dropped pull-request event cannot merge a change
  with no CI (DEC-0035) -- but only together with the next lever, one group
  covering both events, and knowing that branches with no pull request then
  bill runs too. This kit's own CI keeps the default-branch scope.
- **One concurrency group per branch, cancelling in progress.** Rapid pushes
  then collapse to one run of the latest head instead of N runs of N heads,
  most of which are already superseded. This is the setting that makes "never
  push while checks are running" a discipline about *review* rather than about
  billing.
- **Cache dependency installs as SPLIT restore and save steps, with the save
  after the install.** A single combined cache action loses the warm cache on
  any cancel — including the cancel the concurrency group above just issued —
  so a timed-out or superseded run leaves the next one paying full price. A
  measured install can drop from tens of minutes to under a minute on a hit,
  which makes it the largest single lever on the list.

And the free lane is the point of all of it: **the local gate costs nothing and
runs offline, so a hosted reviewer finding something the local gate would have
caught is a registered process failure**, not a lucky catch.

Two rules about the levers themselves:

- **A skip rule is either a pre-dispatch gate or an in-context instruction,
  and only the gate saves anything.** A cost-saving exclusion written as
  prose the tool reads cannot prevent the run that reads it; only a
  platform-evaluated filter (path, title, event type) applied before
  dispatch is a cost control - and nothing in the config file distinguishes
  the two, so classify every skip rule explicitly. Then **verify the skip by
  watching one real change get skipped**: a "docs-only" skip is typically
  unsatisfiable because doc changes also touch generated artifacts
  (manifests, indexes) the rule does not name. Measured: thirteen billed
  reviews of an article about review pricing, under a skip rule that could
  never fire.
- **Every cost or speed lever carries a quality floor.** Never adopt a lever
  that cuts wall-clock or spend by raising the escaped-defect rate; price
  the escape (rework, extra runs, extra review rounds) and roll the lever
  back if it nets negative. Normalize every efficiency claim per merged unit
  of work, never per run - a lever that speeds one run but doubles runs is a
  loss that photographs well.

---

## What fast-track never skips

Three things, or the audit story breaks exactly where it matters most:

- The ledger event fires. A fast-track commit is still a work item with a trace,
  and `wall diff-state` must still reconcile.
- The lease is still taken. Two agents editing the same doc concurrently corrupts
  it the same as code.
- The decision log is still written if the change encodes a ruling.

What it *does* skip: Reviewer dispatch, Architect sign-off, test authoring, CI.
That is the whole saving, and it is most of the cost.

Local gates still run and are free: link check, front-matter validation, and a
ledger-schema check on `.wall/events/**`. Fast-track means no **cloud** minutes,
not no validation.

---

## Architecture docs are the exception

A doc-only change by the Architect can silently invalidate work already built
against the old version, and fast-track gives no signal.

Cheap fix without breaking the fast path: fast-track as normal, but if the path
matches `docs/architecture/**` or `docs/decisions/**`, also emit a `doc_impact`
event naming the affected arcs. No review, no CI, no delay - one event write,
surfaced on the wall as a flag for the Foreman to raise.

---

## Surface

```
wall classify [--staged]    # prints route + which rule matched + why
wall fast-track [-m MSG]    # classify, local gates, commit, push
                            # refuses a mixed changeset, offers the split
```

`wall classify` as a dry run is worth more than it sounds: when something takes
the wrong route you want the matching rule named, not to reverse-engineer globs.

---

## Settled: the destination is a pull request

Straight to the default branch was the cheaper option and it lost. Fast-track is
a **route**, not a destination: every change rides a pull request, opened as a
draft under the owner's identity, merged by the coordinator once the scoped
checks are green (`docs/decisions/DEC-0005.md`).

A uniform audit surface is worth more than the seconds saved - one procedure to
learn, one place to look for what happened, and nothing special to remember when
a change turns out to be less doc-only than it looked. It also survives branch
protection cleanly, which the direct-push route does not.

What fast-track still saves is most of the cost: no reviewer dispatch, no
architect sign-off, no test authoring, and whatever CI reduction the host's own
scoping gives a documentation change.
