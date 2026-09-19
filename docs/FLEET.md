# FLEET.md

The mechanics of running this kit across more than one adopting repository.
None of it is needed for the first adoption; all of it is decided badly by
default at the second.

## What this document does NOT do

It does not merge repositories, does not make one repository's rules binding on
another, and does not give any session write access to a sibling's mainline. It
describes an **exchange**: an offer in one direction, a disposition in the
other, and one artifact both ends agree is identical. Everything else stays
local, on purpose.

---

## 1. The verdict is an exit code

A cross-repository check reports three states and never two: **0** in sync,
**1** diverged and acted on, **2** UNKNOWN. **UNKNOWN is never a pass.** A
comparison that could not fetch, could not parse, or could not find the block
it was told to compare knows nothing about agreement, and reporting it as
agreement is the one failure that guarantees nobody looks again.

**And detection is not action: a run is not an action.** A checker can run
perfectly on schedule, report correctly every time, and sit beside a shared
artifact that drifts hundreds of lines behind - because reporting drift is not
the same as filing the work that closes it. Every non-zero verdict ends in a
tracked item with an owner, or the check is decoration with good hygiene.

## 2. The exchange runs at both ends of a session, in a spin-off that ENDS

The exchange runs at session **start** and session **end**. The outbound half -
offering what this repository learned - has no natural trigger anywhere and
competes directly with wanting to be finished, which is why it is written down
as a step rather than left to judgment.

It runs in a **one-time spin-off session** with the sibling repositories
checked out beside each other, and **that session ends when the exchange is
done**. A lingering spin-off becomes a second workplace with its own half-state,
and the working session stops being isolated to one repository. A parent session
cannot read a spin-off's transcript, so the exchange is measured in artifacts -
pull requests, ledger rows, board items - never in a summary.

## 3. Exactly one artifact is byte-identical

One shared block - the agreed core - is byte-identical across every adopter and
hash-pinned. **Everything else is harvested, read back and answered**, never
copied. Syncing a failure registry verbatim fails the moment two stacks differ,
because half the entries then describe platforms the receiving repository does
not have.

A distributed canonical document carries a **local bindings zone**: the fleet
body is not editable locally, and every local number, path and threshold lives
only in that zone, so no second copy of the shared text exists to drift. **A
local hash proves no local edit, not fleet agreement** - it says nobody changed
this copy, not that the copies match.

## 4. Delivery is a draft pull request, never a push

An offer arrives in the receiving repository as a draft pull request, so it runs
that repository's own gates and **that repository merges it**. Nobody pushes to
a sibling's mainline; a rule that cannot survive the receiver's gates is not
ready to be a fleet rule.

Check the sibling's **inbound pull requests before hand-syncing anything** - a
hand-sync that duplicates a byte-identical delivery already in flight produces
two changes claiming the same authority.

## 5. Answers

- **An answer riding an unmerged branch is not an answer.** It is pending until
  it is on the sibling's mainline, where the next session will actually read it.
- **A rewording that changes the claim is a decline in costume.** Only the
  contributor can run the "I recognise my rule in the result" test, so a
  reworded adoption goes back to them before it counts as adopted.
- **"Answered" is a stated disposition, never a comment count.** The three
  dispositions are **adopted**, **reworded**, **declined-with-reason**;
  **silence is not one of the three**. Where several repositories share one
  account, activity is not evidence of anyone having decided anything.
- **An absent row is invisible to a checker that only refuses unanswered rows.**
  Enumerate from the offer side, not from the ledger side, or an item that was
  never recorded passes every check that exists.

## 6. Belt and suspenders

Two checks, deliberately overlapping: a **scheduled** cross-repository check
with a read-only token that goes **RED when it cannot compare** (an unreachable
sibling is a red, not a skip), and a **session-time** check that honestly
reports UNKNOWN when it cannot look. The scheduled one bounds how long a drift
can hide; the session-time one is what a session actually reads.

**Escalation is event-driven, not scheduled.** Name the events that escalate -
a shared block edited locally, a repeated UNKNOWN, an offer unanswered past a
stated horizon, a sibling's gates rejecting a delivery, a rule declined by every
receiver - and fire on them. A scheduled escalation review is a meeting; an
event-driven one is a mechanism.

---

Related: `README.md` ("Looking ahead: more than one adopting repository"),
`docs/RECONCILIATION.md`, `templates/OWNER_DECISIONS.md.template` (a sibling's
declined rule is a local decision, recorded once, not re-offered forever).
