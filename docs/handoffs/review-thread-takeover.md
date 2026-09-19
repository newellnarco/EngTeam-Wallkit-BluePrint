# Review-thread takeover -- TEMPLATE

> **G8.** Review-thread ownership must be exclusive. The coordinator and a
> builder both answered the same hosted-reviewer thread within minutes, under
> one shared platform identity, and double-replied. One writer per conversation,
> the same rule decisions already follow.
>
> **The unit that owns the PR owns its threads.** This form is the only way that
> changes hands. It is a handshake, not a notification: the takeover is not in
> effect until the owner has acknowledged or has been declared unreachable.

---

## 1. The thread

| Field | Value |
|---|---|
| PR | |
| Thread id / permalink | |
| Lane | hosted reviewer / CI annotation / human |
| Finding summary | one line |
| Opened at | |
| Current owner (agent key / name) | |
| Requesting writer | |

## 2. Why the takeover

Pick one. "It was faster" is not on the list -- that is exactly the reasoning
that produced the double-reply.

- [ ] The owning unit's run has ended and the thread is still open
- [ ] The owning unit is `blocked` on something this thread does not resolve
- [ ] The finding is out of the unit's scope and belongs to another owner
- [ ] The thread needs merge authority, which the unit does not have (G12)
- [ ] The owning run is past its deadline and reads `stale`

**Detail:**

## 3. The handshake

| Step | Value |
|---|---|
| Owner told at | before any reply is posted |
| Owner acknowledged at | or: `unreachable -- run ended at ____` |
| Takeover effective at | |
| Owner stops writing in this thread | from the effective time; **no exceptions** |
| Handing back? | `yes -- at ____` / `no -- thread closes under the new writer` |

If the owner has not acknowledged and its run has not ended, **do not post**.
Two writers with one platform identity is indistinguishable, afterwards, from
one writer contradicting itself.

## 4. The reply the new writer will post (G7)

Verification comes before the reply, for accepting **and** for declining.

| Field | Value |
|---|---|
| Verified against the actual file? | `yes -- ` / `no -- do not reply yet` |
| Verdict | `accepted` / `refuted` / `declined with a better fix` / `lane unavailable` |

**If refuting a truncated-diff finding** -- a registered class; the same false
"this file is truncated" finding was refuted twice in one wave because the
reviewer reported its own truncation boundary as a defect:

```
parse proof: <the read that shows the construct is complete>
```

Never refute by assertion.

**If declining with a better fix** -- legitimate, and it needs the
counterfactual:

```
counterfactual test: <fails under the suggested fix, passes under ours,
                      or the reverse -- shown, not described>
```

**If the lane is out of quota** -- name it as unavailable and move on. A metered
lane is named, not waited on, and it does not hold the PR.

## 5. Record

| Field | Value |
|---|---|
| Reply posted at | |
| Thread state | answered / refuted with proof / declined with counterfactual / unavailable / still open |
| Carried into the wave report | `NEW` section |
| Prevention (if the finding was real) | the rule, the regression test, and the doc that stop the class recurring |
