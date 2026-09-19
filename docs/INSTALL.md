# INSTALL.md

Getting the courier running on a schedule, the wall in front of you, and the
event ledger off the box -- as built.

Adapters ship for **Windows** (scheduled task), **macOS** (LaunchAgent) and
**Linux** (systemd user timer, cron fallback), all exercised by the same tests.
Examples below use `~/code/your-repo` for the repository and
`/opt/deployed-app` for a separately deployed copy, where one exists.

---

## One machine-wide timer, not one per repo

The instinct is for `wall install` to register a timer for this repo. Do not.
Ten repos means ten scheduled tasks, ten chances for an orphan pointing at a
deleted directory firing every two minutes forever and failing silently.

Instead:

```
%USERPROFILE%\.wall\          (or ~/.wall on macOS and Linux)
  registry.json     {"repos": [{path, name, installed_version, last_seen}]}
  sweep_all.py      written by `wall install`; what the one task runs
  heartbeat.json    machine-level: last sweep, per-repo results
  courier.log       one line per repo per sweep, trimmed at 1 MB
```

**One task on the machine.** It wakes every two minutes, walks the registry, and
runs `wall run-once` for each live repo. A repo whose path no longer exists is
dropped from the registry on that pass, so an orphan cannot fire forever.
Install = "write the sweeper, append to the registry, ensure the one task
exists." Adding a tenth repo installs nothing new -- `wall register` is a plain
file write.

This also solves something a per-repo design structurally cannot: Claude and
GitHub quotas are **account-level**, not repo-level. A per-repo wall cannot show
true remaining budget. The machine-wide walker can, and the cross-repo rollup
comes free.

`WALL_HOME` overrides the location of that directory. It exists so the tests can
exercise a real install against a temporary directory instead of writing into
whoever's home ran them; it is equally useful for a second, isolated install.

---

## Consent, once per machine

A subagent silently registering a persistent background service at SessionStart
is exactly what a local-only operating preference guards against.

- **SessionStart hook: detect only.** Check registry membership, marker version,
  heartbeat age (`shipper.heartbeat_age_s(repo)`). Never write a system task.
- If anything is missing or stale, Maestro surfaces it in chat with the exact
  command and what it will create, then waits.
- `wall install` **prints its full plan and then stops.** It creates nothing
  without `--yes`, and it exits non-zero when it created nothing, so a script
  cannot mistake the consent print for an install.

The plan is written by the adapter that will actually run, not by a summary of
it, so the two cannot drift. On Linux it reads:

```
wall install would create:
  directory  /home/j/.wall
  file       /home/j/.wall/registry.json
  file       /home/j/.wall/sweep_all.py
  file       /home/j/.config/systemd/user/wall-courier.service
  file       /home/j/.config/systemd/user/wall-courier.timer
  schedule   systemctl --user daemon-reload
  schedule   systemctl --user enable --now wall-courier.timer
  (fallback where user systemd is unavailable: */2 * * * * ...)

  registering repo  /home/j/code/your-repo
  sweep interval    every 120s

The schedule is ONE task for this machine. It walks the registry and
sweeps every live repo, so adding another repo installs nothing new.
Nothing here reaches the network.

Nothing was created. Re-run with --yes to proceed:
  wall install --yes
```

After the first yes on a machine, adding a repo only touches the registry -- a
plain file write needing no further approval. One consent per machine, not one
per project.

`wall install --yes` is **idempotent**: the sweeper is rewritten, the repo row
is refreshed rather than duplicated, and each adapter replaces its own task in
place (`schtasks /F`, `launchctl bootout` then `bootstrap`, `systemctl enable
--now`).

If the scheduler step fails -- no privileges, no user systemd, a locked-down
box -- the command exits non-zero and **says what did survive**: the registry
and the sweeper are in place, so `wall run-once` and a hand-made task both work.
The failure is named, never swallowed.

Courier itself is stdlib Python, local file I/O only, zero model calls and zero
network. The one command that reaches the network is `wall ship` (below), which
is separately invoked and separately gated.

---

## Serving the wall

Two delivery modes, one file -- `courier.py` handles both automatically.

**Served** (`wall serve`, `http://127.0.0.1:8123/wall.html`): the page removes
its meta refresh, polls `wall.json` every 10 seconds, and repaints in place.
Scroll position, active tab and focus survive. Polling pauses when the tab is
hidden and fires once on refocus.

**File** (`file://`, no server): the page uses the snapshot inlined at render
time and a 30-second meta refresh. No server, no port, no CORS, no process to
supervise.

```
wall serve                     foreground, 127.0.0.1:8123
wall serve --port 9123
wall serve --check             probe an already-running server, exit non-zero if unhealthy
wall serve --verbose           log every request to stderr
```

Four properties, all asserted over a real socket in `tests/test_server.py`:

1. **The bind is `127.0.0.1`, and there is no `--host` flag.**
   `.wall/derived/` also contains `ledger.jsonl` and `heartbeat.json`, so a
   `0.0.0.0` bind makes the full event history readable by anything on the
   network. That is not a flag anyone should be able to pass by accident.
2. **No-store on `wall.html` and every `.json` / `.jsonl`.** A cached snapshot
   shows a finished wave as still running, which is the one thing a live status
   board must never do.
3. **Path-traversal safe.** Every request resolves to a real path and is refused
   unless that path is inside `.wall/derived/` -- which also catches a symlink
   planted inside the directory, not just `../` in the URL.
4. **A four-name allowlist**: `wall.html`, `wall.json`, `heartbeat.json`,
   `ledger.jsonl`. Not a prefix rule and no directory listing. The derived
   directory is a working area, and a rule that serves whatever lands there is a
   rule that serves the next thing that lands there.

GET and HEAD only; a POST is 501 whatever the path.

`wall serve --check` is stricter than "did something answer". It passes only if
the response parses as a wall snapshot **and** carries `no-store`: a server
handing out the snapshot cacheable is serving a wall that can go quietly stale.

**If the host repo already serves a wall or status page**, register the kit's
files with it instead of running a second server: add `wall.json` and
`heartbeat.json` to its no-cache set and point it at `.wall/derived/`. (The
reference deployment did exactly this with its existing board server on the
same port.)

---

## CLI surface

```
wall install [--yes] [--interval 120]   consent-gated; prints the plan, creates on --yes
wall register [--repo PATH] [--name N]  adds a repo to the registry; no privileges
wall unregister [--repo PATH]
wall verify [--app PATH]                timer alive? heartbeat fresh? registry sane? app in sync?
wall uninstall [--purge]                removes the task; --purge also removes registry + sweeper
wall serve [--port 8123] [--check]      the local wall server
wall run-once                           what the timer calls; also manual/CI entry point
wall doctor                             heartbeat, integrity flags, roster, plumbing
```

`wall.py` keeps its own argument parsing and lazily imports `service.py` for the
install family. The seam is six functions, each taking the argparse namespace
and returning an exit code:

```python
service.cmd_install(args)     service.cmd_verify(args)
service.cmd_register(args)    service.cmd_uninstall(args)
service.cmd_unregister(args)  service.cmd_serve(args)
```

Only `args.repo` is guaranteed to exist; every other attribute is read with
`getattr` and a default, so a bare namespace works and a stub parser that adds
no flags cannot crash the command. `service.doctor_checks(repo)` is the seventh
export -- `wall doctor` calls it through the same lazy import, so doctor and
verify report the same checks by construction rather than by two people
maintaining the same list twice.

Adapters sit behind one interface with three methods -- `install`, `verify`,
`uninstall` -- and each one **separates command construction from execution**:

- **Windows** -- `schtasks.exe /Create /TN WallCourier /SC MINUTE /MO 2 /F`.
  Not PowerShell: `schtasks` is plain argv with no quoting layer between us and
  the scheduler, and no dependency on which PowerShell is on PATH (F-PS-001 --
  Windows 10/11 default to 5.1, whose cmdlets differ from 7's). The
  `Register-ScheduledTask` equivalent is kept in `install/windows.py` as
  `MANUAL` and is printed when the adapter fails.
- **macOS** -- LaunchAgent `com.wallkit.courier`, `StartInterval 120`,
  `RunAtLoad`, `launchctl bootstrap gui/<uid>`.
- **Linux** -- systemd user `wall-courier.timer` + `.service`,
  `OnUnitActiveSec=120s`, `Persistent=true`; a cron line is offered where user
  systemd is unavailable.

The `build_*` functions are pure -- they return the exact argv, plist text or
unit file as data -- so `tests/test_install_adapters.py` asserts all three
platforms' commands on any platform, without a scheduler anywhere near them. A
wrong scheduler command is then a test failure on CI rather than a mystery on
someone's workstation two weeks later.

`wall run-once` works with no adapter installed at all, which means the whole
system can be driven by hand or from a git hook.

On a Windows-driven repository, ship the `wall.bat` shim beside the host's
other `.bat` entry points so the CLI matches how the repo is already driven,
rather than assuming a POSIX shell.

---

## Shipping the ledger off the box

Per **RECONCILIATION Q7**: event shards must never ride a development PR. They
are high-churn append-only files; committed on the working branch they conflict
on every parallel unit -- the F-DERIVED-001 class that board fragments were
invented to kill. So shards live gitignored in the working tree and travel on
their own branch.

`tools/wall/shipper.py` is that path, modelled directly on the plumbing the
reference deployment ran in production during its first agent wave:

```
python tools/wall/shipper.py --repo . --ship     # push the day's shards + snapshot
python tools/wall/shipper.py --repo . --fetch    # materialise the branch (box side)
python tools/wall/shipper.py --repo .            # validate the local snapshot only
```

`ship()` builds a tree in an isolated `GIT_INDEX_FILE` and pushes it by object
id to `refs/heads/wall-events`. **The working tree, the real index and the
current branch are never touched**, so it cannot collide with the box's checkout
or a session's PR pushes. The branch is overwritten each ship -- latest state
only, no history bloat -- and the shards are append-only, so nothing is lost by
that.

Its guards are the measured ones:

- **Validate before push.** The bytes on disk get published, and `ship` is not
  their only writer. A malformed snapshot is refused before git is invoked at
  all.
- **Bounded git.** 60-second wall clock on every call; a timeout returns
  non-zero rather than raising. An unbounded fetch against an unreachable remote
  hangs the two-minute sweep, and a hang looks exactly like working.
- **Encoding pinned to utf-8.** `text=True` otherwise decodes with the locale
  codec, which on Windows outside a PYTHONUTF8 environment is a legacy code
  page; `cat-file blob` returns shipped JSON, so a mojibake decode corrupts an
  event.
- **Honest no-op.** No branch, no network, malformed payload: the caller keeps
  what it had and is told why. Nothing in the module raises.

`fetch()` is freshness-guarded in both directions. It refuses a shipped snapshot
that is older than the local one (a wave running **on** the box writes shards
directly, and a stale branch must never clobber a live stream), it shape-checks
the payload before letting a newer stamp win anything, it refuses to write any
path that resolves outside the repo, and it replaces a local shard only when the
remote one is strictly longer.

`shipper.heartbeat_age_s(repo)` is the shared staleness helper -- used by
`wall verify`, `doctor_checks`, and the SessionStart detection. It returns
`None` for "cannot tell", never `0` and never a guess.

### The two-cadence split, for any job with a metered half

A periodic job that has a **free local half** and a **metered remote half** --
rendering a view locally versus reconciling against a hosted service's API --
is split into two cadences rather than run whole on the fast one. The local half
runs **every tick**, offline-safe, zero API calls, so the surface a human opens
is always current even with no network. The metered half runs only when the
subject **actually moved** (a real fetch landed, a head advanced, a state
changed), and never on a no-op tick.

Three properties make the metered half safe to leave running unattended:

- **A minimum interval batches bursts.** Ten merges in four minutes are one
  sweep, not ten. The interval is configuration, not a constant somebody tuned
  once.
- **A sentinel range, not a sentinel point.** The job records the last point it
  successfully swept **to**, and the next run sweeps from there. A skipped or
  failed sweep leaves the sentinel untouched, so the next real run covers the
  missed range automatically -- self-healing, with no retry loop.
- **A within-interval skip is a skip, not a failure.** It does not advance the
  sentinel and it does not retry; retrying every tick against an exhausted quota
  is how a helpful sync job becomes the reason the quota is exhausted. Measured
  in the reference deployment: a two-minute sweep sharing the owner's API token
  consumed the hour's budget, and splitting the cadences ended it.

The same shape applies to any partner-metered periodic work -- issue sync,
status mirroring, dashboard reconciliation -- not only to the ledger.

---

## The failure mode to design for

A dead timer is the one failure that is invisible, because a stale wall looks
identical to a quiet project. Four defenses, all built:

1. Courier writes `.wall/derived/heartbeat.json` on every run, successful or
   not; `sweep_all.py` writes a machine-level `~/.wall/heartbeat.json` with a
   per-repo result list beside it.
2. `generated_at` renders on the wall and goes red past five minutes.
3. `wall verify` fails -- non-zero, with the age in seconds -- when the
   heartbeat is missing or older than `DEFAULT_STALE_AFTER_S` (300s). **A
   heartbeat that cannot be read is `fail`, never `ok`**; unknown is a distinct
   status and does not collapse into green.
4. The SessionStart hook checks heartbeat age and, if stale, tells Maestro to
   surface it rather than letting a frozen grid be read as truth.

Same evidence-over-self-report principle, applied to the plumbing.

`wall verify` output:

```
wall verify  /home/j/code/your-repo
  ok   heartbeat  last sweep 47s ago
  ok   registry   3 repo(s), this one included
  ok   timer      installed and running; scheduler last run Sat 2026-09-19 11:58:00 UTC
  ??   budget     not measured (no budget-counted context doc wired yet)
  all checks passed
```

The `budget` row is deliberately `??` and not `ok`. RECONCILIATION G10: the host
repo's reviewer-prompt budget sat 53 characters from a hard failure while three
parked units each added rules to the counted sections, and the doctor is meant
to report that headroom. `service.budget_headroom()` is the hook, it returns
`None` today, and the doctor renders `None` as "not measured" -- never as
"fine".

---

## Verification the repo cannot do

Some hosts deploy the repo as a separate tree (`/opt/deployed-app` in these
examples). An arc is not really done because CI went green; it is done when the
installed app behaves.

```
wall verify --app /opt/deployed-app
```

compares the deployed `MANIFEST.sha256` against the repo's and reports `match`,
`differs` (with the count of differing entries, and "the deployed app is not
this tree") or `missing`. That catches a failure class the reference deployment
paid for: a release's manifest entries shipped but its install script never
ran, so the deployed tree silently lagged the repo.
