# INSTALL.md

Getting the courier running on a schedule, and the wall in front of you.

Target environment for MAX3: **Windows**, repo at
`C:\Dev\gh-repos\newellnarco\MAX3`, application at `C:\Dev\MAX3`.

---

## One machine-wide timer, not one per repo

The instinct is for `wall install` to register a timer for this repo. Do not. Ten
repos means ten scheduled tasks, ten chances for an orphan pointing at a deleted
directory firing every two minutes forever and failing silently.

Instead:

```
%USERPROFILE%\.wall\
  registry.json     {repos: [{path, name, installed_version, last_seen}]}
  courier.log
  heartbeat.json
```

**One task on the machine.** It wakes every two minutes, walks the registry, and
runs consolidation for each live repo. A repo whose path no longer exists is
dropped automatically. Install = "append to registry, ensure the one task
exists." Adding a tenth repo installs nothing new.

This also solves something a per-repo design structurally cannot: Claude and
GitHub quotas are **account-level**, not repo-level. A per-repo wall cannot show
true remaining budget. The machine-wide walker can, and the cross-repo rollup
comes free.

---

## Consent, once per machine

A subagent silently registering a persistent background service at SessionStart
is exactly what a local-only operating preference guards against.

- **SessionStart hook: detect only.** Check registry membership, marker version,
  heartbeat age. Never write a system task.
- If anything is missing or stale, Maestro surfaces it in chat with the exact
  command and what it will create, then waits.
- `wall install` runs on explicit say-so, prints the task it wrote, and is
  idempotent.

After the first yes on a machine, adding a repo only touches
`%USERPROFILE%\.wall\registry.json` — a plain file write needing no further
approval. One consent per machine, not one per project.

Courier itself is stdlib Python, local file I/O only, zero model calls and zero
network. The only step that may reach the network is propagation, if the snapshot
is ever published somewhere. That stays a separate, separately-gated command.

---

## Serving the wall

Two delivery modes, one file — `courier.py` handles both automatically.

**Served** (current MAX3 setup, `http://127.0.0.1:8123/wall.html`): the page
removes its meta refresh, polls `wall.json` every 10 seconds, and repaints in
place. Scroll position, active tab and focus survive. Polling pauses when the tab
is hidden and fires once on refocus.

**File** (`file://`, no server): the page uses the snapshot inlined at render
time and a 30-second meta refresh. No server, no port, no CORS, no process to
supervise.

Keep the bind on `127.0.0.1` explicitly. `.wall/derived/` also contains
`ledger.jsonl` and `heartbeat.json`, so a `0.0.0.0` bind makes the full event
history readable by anything on the network.

---

## CLI surface

```
wall install [--interval 120]   consent-gated; creates the machine task
wall register [--repo PATH]     adds a repo to the registry; no privileges
wall unregister [--repo PATH]
wall verify                     task alive? heartbeat fresh? registry sane?
wall run-once                   what the timer calls; also manual/CI entry point
wall status                     per-repo: last sweep, event count, flags
wall uninstall
```

Adapters sit behind one interface with three methods — `install`, `verify`,
`uninstall`:

- **Windows** — `Register-ScheduledTask` with a two-minute repetition trigger.
- **macOS** — LaunchAgent plist, `StartInterval 120`, `launchctl bootstrap`.
- **Linux** — systemd user `.timer` + `.service`, `OnUnitActiveSec=2min`, cron
  fallback where user systemd is unavailable.

Each stub raises with a printed manual command, so the system is fully usable
before any adapter is real. `wall run-once` works everywhere from day one, which
means the whole thing can be driven by hand or from a git hook while the adapters
are still stubs.

Ship a `wall.bat` shim beside `push-to-github.bat` and `pull-to-local.bat` so the
CLI matches how MAX3 is already driven, rather than assuming a POSIX shell.

---

## The failure mode to design for

A dead timer is the one failure that is invisible, because a stale wall looks
identical to a quiet project. Three cheap defenses:

1. Courier writes `heartbeat.json` on every run, successful or not.
2. `generated_at` renders on the wall and goes red past five minutes.
3. The SessionStart hook checks heartbeat age and, if stale, tells Maestro to
   surface it rather than letting a frozen grid be read as truth.

Same evidence-over-self-report principle, applied to the plumbing.

---

## Verification the repo cannot do

`C:\Dev\MAX3` is the deployed application. An arc is not really done because CI
went green; it is done when the installed app behaves.

`wall verify --app C:\Dev\MAX3` should check the deployed `MANIFEST.sha256`
against what the repo expects. That catches the exact failure `max3-docs-sync`
was written to recover from: a drop's ledger entries shipped but its install bat
never ran.
