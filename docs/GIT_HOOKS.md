# GIT_HOOKS.md

The local gate. Hooks are not cloned with a repository, so every one of these
rules exists because a hook that was "installed" on one machine was absent on
the next and nobody could tell from the outside.

The kit ships no hook scripts for version control: what a pre-commit must
regenerate and what a pre-push must run are the host's, not the kit's. What is
portable is the shape, and the shape is what keeps the free gate free.

---

## 1. Versioned, installed, never remembered

Hooks live **in version control** (`tools/git-hooks/` or the host's equivalent)
and a one-shot installer copies them into `.git/hooks/`. The installer runs in
every fresh clone and from every provisioning path.

**Hook install is step 0 of provisioning - before any step that can fail.** A
dependency install that aborts must never take the hook install with it, or the
first commit of that session ships a stale derived artifact and spends a full
CI cycle finding out. The ordering is the whole rule; everything else in a
provisioning script can be reordered freely.

```
# provisioning, step 0 - before the failable steps
bash scripts/setup-git-hooks.sh && note "git hooks installed" \
  || degrade "git hooks install failed"
```

Install with an explicit interpreter and a file test (`-f`), not an
executable-bit test (`-x`): a checkout that lost the executable bit still has
to be able to install its own hooks.

## 2. What each hook is for

- **pre-commit** - regenerate and re-stage derived artifacts inside the commit,
  so "stale derived file" failures become structurally impossible. It **never
  blocks**: missing tooling warns and proceeds. A pre-commit that can refuse a
  commit gets uninstalled by the first person it inconveniences.
- **pre-push** - two jobs. (1) **Block a direct push to the default branch.**
  (2) Run the **free local gate** over the outgoing commits: lint the changed
  files, typecheck if the stack has one, check derived-artifact sync, run the
  scoped tests. **Only definite failures block**; missing tooling, a timeout,
  or a change set too broad to scope warns through, because the hosted pipeline
  remains the authoritative gate and a local gate that blocks on its own
  breakage teaches people to bypass it.

The economics are the point: the cheapest check is the one that never spends a
metered minute, and a hosted reviewer raising something the local gate would
have caught is a registered process failure (`docs/FAST_TRACK.md`).

## 3. Never bypass with `--no-verify`

`--no-verify` skips **every** hook, invisibly, and leaves nothing greppable
behind. Every hook therefore exposes a **named** environment-variable escape
hatch instead - one per hook, scoped to that hook:

```
SKIP_PUSH_GATE=1 git push        # named, greppable, scoped to one hook
git push --no-verify             # never
```

The difference is not politeness. A named variable appears in shell history and
in a session transcript, so a bypass is a fact somebody can find later; a
`--no-verify` is a decision that leaves no record and is indistinguishable from
a hook that was never installed.

## 4. Line endings, where a byte-exact artifact exists

If the repository carries **any** byte-exact derived artifact - a content-hash
manifest, a checksummed lockfile, a golden file compared by digest - then
silent line-ending conversion corrupts it on every cross-platform clone. Pin it
in `.gitattributes`:

```
* text=auto eol=lf
*.bat text eol=crlf
*.cmd text eol=crlf
*.ps1 text eol=crlf
```

Two notes that are the actual lesson. This is a **derived-artifact integrity**
requirement, not a platform footnote: a manifest generated on one platform and
verified on another fails in the hosted pipeline, not on somebody's laptop. And
changing `.gitattributes` does **not** re-normalize files whose working-tree
bytes already match the index - recover with
`git add --renormalize .`, and re-smudge during provisioning.

## 5. Adopt a new local check with a baseline ratchet

A new lint over an existing corpus reports hundreds of findings on its first
run, and a gate that is red on arrival gets disabled rather than burned down.
Adopt it as a **ratchet**: record the current findings in a baseline file, fail
only on **new** drift, and let the old drift burn down as the files are touched
anyway.

Three properties keep a ratchet honest:

- The baseline is **committed**, so everyone gates against the same population.
- Adding to the baseline is a **visible change in the diff**, not a side effect
  of running the tool. A tool that silently re-baselines has turned the gate
  off.
- The baseline **shrinks** - a number that only ever grows is a suppression
  list with a progress bar.

## 6. Cross-references

- `docs/INSTALL.md` - machine-wide timer and provisioning
- `docs/FAST_TRACK.md` - the meter economics the local gate protects
- `docs/TESTING_STANDARDS.md` - what the scoped gate runs
- `.claude/hooks/README.md` - the session hooks, a different layer entirely
  (facts about agent runs, not a gate on commits)
