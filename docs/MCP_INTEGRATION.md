# MCP_INTEGRATION.md

The wall as an MCP server: one integration point for every editor and
agent (DEC-0019, DEC-0036, DEC-0037). `tools/wall/mcp_server.py` speaks the Model Context
Protocol over stdio — newline-delimited JSON-RPC, stdlib only — so any
MCP client attaches with three lines of config and gets the same six
tools: `wall_status`, `wall_item`, `wall_waiting`, `wall_trace`,
`wall_answer`, `wall_enqueue`.

The engineer's loop from any surface: **stay up to date**
(`wall_status`, `wall_waiting`), **answer what the team is blocked on**
(`wall_answer` — the human-queue verb, refusals identical to the
terminal's), **hand out new work** (`wall_enqueue`, when the host queue
is configured). Reads are the same folds the `wall summary` CLI and the
wall page serve (DEC-0018: one implementation, N presentations).

This document wires MCP servers the repo has already decided to run.
Whether a discovered server is adopted at all is governed by
`CAPABILITY_TRUST.md` — a discovered capability lands parked, never
auto-adopted, and its manifest and tool descriptions are data, not
instructions.

---

## Claude Code

`.mcp.json` at the repo root (project-scoped, shared via the repo):

```json
{
  "mcpServers": {
    "wall": {
      "command": "python3",
      "args": ["tools/wall/mcp_server.py", "--repo", "."]
    }
  }
}
```

Tools appear as `mcp__wall__wall_status` etc. On Windows use `python`
(or the venv's interpreter) as the command.

## Cursor

`.cursor/mcp.json` in the repo (or `~/.cursor/mcp.json` machine-wide):

```json
{
  "mcpServers": {
    "wall": {
      "command": "python3",
      "args": ["tools/wall/mcp_server.py", "--repo", "."]
    }
  }
}
```

## VS Code

`.vscode/mcp.json`:

```json
{
  "servers": {
    "wall": {
      "type": "stdio",
      "command": "python3",
      "args": ["tools/wall/mcp_server.py", "--repo", "."]
    }
  }
}
```

## One shared server for every client — loopback HTTP (DEC-0036)

Over stdio, **every client session starts its own server** — and with the
engineer and agent seats configured as two entries, that is two
interpreters per open editor or agent session. On a machine with several
clients open, that adds up. The same server can instead run ONCE and serve
them all over MCP Streamable HTTP, bound to loopback:

```
python3 tools/wall/mcp_server.py --repo . --http 127.0.0.1:8124
```

or, from a process that is already resident (a service, a supervisor),
without another interpreter:

```python
server = mcp_server.make_http_server(repo, "127.0.0.1", 8124)
threading.Thread(target=server.serve_forever, daemon=True).start()
```

The role is the path: `/mcp/engineer` (all six tools) and `/mcp/agent`
(the four reads); anything else degrades to `agent`. Client config
(Claude Code shown; Cursor and VS Code take the same `url` shape):

```json
{
  "mcpServers": {
    "wall": {"type": "http", "url": "http://127.0.0.1:8124/mcp/engineer"},
    "wall-agent": {"type": "http", "url": "http://127.0.0.1:8124/mcp/agent"}
  }
}
```

**When NOT to switch a repo's shared config to HTTP:** a client with no
local server behind that URL — a cloud session, a CI runner, a fresh clone
on a machine where nothing hosts it — loses the wall tools entirely. Keep
the committed `.mcp.json` on stdio unless every machine that opens the repo
runs the shared server, and put the HTTP entries in a machine-local config
(Claude Code's user/local scope, `~/.cursor/mcp.json`) on the machine that
does.

### The kit's own host, and how Claude Code finds it (DEC-0037)

You don't have to run the command above yourself. `wall host install --yes`
starts **one resident process per machine** (`tools/wall/host.py`). It
serves every repo in the machine registry on one loopback port, one path per
repo and role, and runs the courier sweep in the same process:

```
POST http://127.0.0.1:8124/r/<name>/mcp/engineer     all six tools
POST http://127.0.0.1:8124/r/<name>/mcp/agent        the four reads
GET  http://127.0.0.1:8124/health                    liveness + served repos
```

`<name>` is the repo's registry name as one URL segment (`wall host status`
prints each). The committed `.mcp.json` **keeps its stdio entries**. On the
machine running the host, `wall host install` (or `wall host link` for one
repo) writes a Claude Code **local-scope** server for each stdio wall entry,
with the **same name** and the same `--role`, into `~/.claude.json` under
`projects[<repo path>].mcpServers`:

```json
"wall":       {"type": "http", "url": "http://127.0.0.1:8124/r/<name>/mcp/engineer"},
"wall-agent": {"type": "http", "url": "http://127.0.0.1:8124/r/<name>/mcp/agent"}
```

The hand-typed equivalent, run from the repo root:

```
claude mcp add --scope local --transport http wall http://127.0.0.1:8124/r/<name>/mcp/engineer
claude mcp remove --scope local wall
```

Claude Code resolves a server name defined in more than one scope **local
first, then project (`.mcp.json`), then user**. So a session on this machine
connects to the host and starts no stdio interpreter for that name, while a
cloud session or another machine, which has no local entry, keeps the
project's stdio server. Tool names do not change (`mcp__wall__wall_status`),
so allow-lists and prompts that name them keep working.

The writer never overwrites an entry it did not write (it reports a
conflict), preserves every other key in the file, and does nothing when the
entry is already right. Running Claude Code sessions also write
`~/.claude.json`, so link with sessions closed, or re-run `wall host link`
afterwards; `wall host status` shows what is linked.

**When the host is down**, the local entry points at a port nothing answers,
so the wall server shows as failed in `/mcp` for sessions on that machine.
Restart it with `wall host start` (the timer's watchdog also restarts it
within five minutes), or return the machine to stdio with `wall host
uninstall`, which removes every local entry pointing at the host. `wall
doctor` flags an enabled host that does not answer.

**Which clients this covers.** Only clients that read Claude Code's
local-scope servers: the Claude Code CLI and IDE extensions, and anything
built on the Agent SDK that loads the user's settings. An SDK-based app that
loads **only** project settings reads `.mcp.json` and nothing else, so it
still starts stdio copies. Give it the HTTP URLs in its own config instead.
Cursor and VS Code keep their own files (`~/.cursor/mcp.json`, user
settings); point them at the same URLs by hand, since the kit writes no
config for them yet.

What the transport guarantees, pinned by tests: it binds loopback only (a
non-loopback host is refused, no flag widens it); a request whose `Origin`
is not a loopback origin is refused, so a web page cannot drive it; it is
stateless and never pushes (`GET` is `405`); notifications answer `202`;
tool calls run one at a time; a malformed body is an error response, never
a dead server.

## Anything else that speaks MCP stdio

Spawn `python3 tools/wall/mcp_server.py --repo <repo-root>` and talk
newline-delimited JSON-RPC: `initialize`, then `tools/list` /
`tools/call`. The tests (`tests/test_mcp_server.py`) speak exactly this
wire protocol against a spawned server and double as a reference
transcript.

---

## claude.ai — deliberately not (yet)

claude.ai custom connectors need a **remote (HTTP) transport**. This
server's HTTP transport is loopback-only, on purpose: remote exposure crosses the
local-only line every deployment document assumes (INSTALL.md,
DEPLOYMENT_TARGETS.md's "never exposed beyond a trusted boundary"), so
adopting it is a superseding decision with an auth story — see
DEC-0036's revisit clause. claude.ai coverage today is via Claude Code
sessions, which run this server locally like any other client.

## The enqueue write

`wall_enqueue` needs the host queue named in `.wall/config/wall.json`:

```json
"queue_api": {
  "origin": "http://127.0.0.1:8123",
  "health": "/api/queue/health", "queue": "/api/queue", "add": "/api/queue/add"
}
```

`origin` + `add` is where the POST goes — in the reference adoption,
the host's wall server, whose own exact-path allowlist (its DEC-0004)
governs the write. No `origin` configured means the tool answers
"not reachable from here, honestly" instead of guessing a port.


## Directive vocabulary — what a queue consumer must handle

`wall_enqueue`, the wall's EXECUTE buttons, the blocked drill-in and the
POSTURE regime controls all converge on the host queue with a typed
`directive` field. A consumer (a Maestro session, an editor agent, anything
polling the HTTP queue API) routes on it:

| `directive` | Enqueued by | Payload beyond `title` | Consumer's job |
|---|---|---|---|
| `execute_item` | wall detail EXECUTE THIS | `target_key` | Work that one item end-to-end |
| `execute_arc` | wall EXECUTE ARC | `arc_id` (+ selected phases) | Work the arc in order |
| `resolve_blocked` | the blocked chip's dialog | `mode: build\|research`, `item_id`, `reason` | Build the fix, or research the blocker and answer the open ask |
| `warden_regime` | POSTURE ENABLE / DISABLE | `action: enable\|disable`, `regime` | **Warden only**: evaluate, then record the selection with its reason — a request judged wrong is answered with a ruling, never silently dropped |
| `warden_audit` | POSTURE REQUEST AUDIT | `regime` | **Warden only**: evaluate every control and record `wall audit` — pass/fail/waiver each with proof or reason |
| `doc_review` | DOCS read-popup APPROVE / REQUEST CHANGES / DENY (DEC-0032) | `action: approve\|changes\|deny`, `path`, `sha` (as read), `reason` (required unless approve) | Approve → `wall ack-doc <path>` at the sha the reviewer read (sha moved since = refuse and re-read, the ack must record what was actually reviewed). Changes/deny → `wall ack-doc <path> --feedback "<reason>"` (deny is carried in the text) AND file the fix as work through the normal finding route, so the doc reads feedback-open until a newer ack lands |

An unknown directive is parked, not guessed at: file it as a question. The
wall itself never mutates state — every button above only ENQUEUES, behind
the same-origin health probe, so a wall served without its host stays
read-only (DEC-0030).

### The review loop across MCP surfaces

`doc_review` is how a verdict rendered anywhere — the wall's read popup, a
Claude Code session, Cursor, VS Code, anything speaking MCP — carries back
into the work stream. Every surface converges on the same host queue:
the wall's popup enqueues the typed payload above, and any MCP client sends
the identical thing via `wall_enqueue` (`directive: "doc_review"` plus
`action`/`path`/`sha`/`reason`). The consumer's job closes the loop: an
approval becomes a `doc_reviewed` event, an objection becomes `doc_feedback`
**plus a filed fix item**, and from that moment every surface can watch the
carry-back — the DOCS fold shows feedback-open, `wall_status`/`wall_item`
show the fix story moving, and `wall_answer` handles any question the fix
raises. No side channel, no bespoke webhook per editor: one queue, one
typed vocabulary, N clients.
