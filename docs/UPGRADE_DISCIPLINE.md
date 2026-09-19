# UPGRADE_DISCIPLINE.md

Dependency upgrades, without the silent breakage. `docs/TECH_EVALUATION.md`
covers a **deliberate swap** - one technology replacing another, measured
before the flip. This covers the other half, which is where the damage
actually accrues: the routine bump nobody evaluated, because staying current is
a goal and blind currency is not.

**The standing rule: always check for upgrades, and establish compatibility
before installing one.** A dependency queue nobody looks at becomes a
dependency wall nobody can climb; a dependency wall climbed in one jump is an
outage.

---

## 1. Classify every available bump

| Class | Shape | Action |
|---|---|---|
| **Patch** (`x.y.Z`) | fixes only, by the publisher's claim | apply routinely, normal change + gates |
| **Minor** (`x.Y.0`) | additive, by the publisher's claim | apply with a changelog skim, normal change + gates |
| **Major** (`X.0.0`) | breaking, by the publisher's claim | **held behind a deliberate review** - see below |

A major bump is **its own narrow change** and never rides along in an unrelated
one. Three things happen before it lands, and each produces evidence a reviewer
can ask for:

1. The migration guide is read, not skimmed for the word that was searched.
2. Every **actual usage** of the changed interfaces is grepped in this
   repository - the count goes in the report. "Probably unaffected" is a guess
   about a population that was never queried.
3. The **rollback pin is named** - the exact version this returns to - before
   the bump is applied, not after it breaks.

The publisher's classification is a claim like any other. A "patch" that
changes a default is a major in everything but the number; treat what it does
as the class, not what it is called.

## 2. The transitive native-wheel class

An **unpinned transitive** dependency can float onto a new major carrying a bad
native artifact, and a native crash produces **no stack trace in the host
language**: the process simply dies, with evidence only in the operating
system's crash record. That combination - a dependency nobody chose, failing in
a way the normal logs cannot see - is why this class has its own rules:

- **A transitive dependency that ships native code is treated as a direct
  major** when it moves majors. Check it explicitly; nothing else will.
- **Pre-arm the evidence before you need it.** A native-crash handler armed to
  a file at process start, and subprocess stderr tails captured into the
  supervising log line, are what make the next occurrence decidable. A crash
  you cannot attribute is a crash you will debug by hand twice.
- **A crash that survives a forced reinstall of the suspect package is a bad
  artifact, not a corrupt install.** Stop reinstalling: pin below the offending
  major, record the pin with its lifting condition, and file the upstream
  issue.

The registry seed for this class is `F-NATIVE-WHEEL-001` in
`FAILURE_PATTERNS.md`.

## 3. The cold soak

**Any dependency change gets a cold soak before it is called good: the real
application, actually running, for long enough to leave the import path.**
Ten minutes is the floor that has caught things; the number matters less than
the property, which is that the process reaches steady state.

`import` succeeding is not the bar. Most native failures happen on first real
use - the first inference, the first codec, the first socket - which is after
every check a package manager runs and after every check a fast test suite
runs. A suite that never loads the heavy path proves the wheel installed, not
that it works.

Record the soak the way anything else is recorded: what ran, for how long, and
what it did. A soak nobody can price did not happen.

## 4. Pins are decisions, and decisions lift

A pin that says only `<PACKAGE>==<VERSION>` is a decision with the reason
deleted. Every deliberate pin below the latest major is recorded in
`OWNER_DECISIONS.md` with:

- the **reason**, in a sentence somebody can disagree with (the upstream issue,
  the broken artifact, the interface that has no replacement yet), and
- the **lifting condition** - the observable event that ends it: a fixed
  release, an upstream issue closing, a replacement interface landing.

Without the lifting condition a pin outlives its reason and nobody notices,
which is how a repository ends up three majors behind for a bug that was fixed
in a fortnight.

## 5. Make the queue visible

Installed-versus-latest is surfaced on a cadence - at install time, or by a
small report tool the timer runs - so bumps arrive as a **queue somebody
reads** rather than as a surprise the day something breaks. The queue is
evidence: it says which majors are outstanding and how long each has been.

## 6. The ship gate

- [ ] No change carries an **unaddressed** major bump. Bumped deliberately or
      pinned deliberately - never implicitly, and never noticed in review.
- [ ] Every dependency added, bumped or removed updated its **licence record**
      in the same change.
- [ ] The **cold soak** ran after the change, on the target that runs it.
- [ ] Any new pin carries its reason and its lifting condition.

## 7. Cross-references

- `docs/TECH_EVALUATION.md` - the deliberate swap, measured before the flip
- `FAILURE_PATTERNS.md` - `F-NATIVE-WHEEL-001` and the class-guard convention
- `OWNER_DECISIONS.md` - pins as recorded decisions with lifting conditions
- `SHIP_CHECKLIST.md` - the dependency item this section gates
