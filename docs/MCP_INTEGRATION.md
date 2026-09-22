# MCP_INTEGRATION.md

The wall as an MCP server: one integration point for every editor and
agent (DEC-0019). `tools/wall/mcp_server.py` speaks the Model Context
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

## Anything else that speaks MCP stdio

Spawn `python3 tools/wall/mcp_server.py --repo <repo-root>` and talk
newline-delimited JSON-RPC: `initialize`, then `tools/list` /
`tools/call`. The tests (`tests/test_mcp_server.py`) speak exactly this
wire protocol against a spawned server and double as a reference
transcript.

---

## claude.ai — deliberately not (yet)

claude.ai custom connectors need a **remote (HTTP) transport**. This
server is stdio/local only, on purpose: remote exposure crosses the
local-only line every deployment document assumes (INSTALL.md,
DEPLOYMENT_TARGETS.md's "never exposed beyond a trusted boundary"), so
adopting it is a superseding decision with an auth story — see
DEC-0019's revisit clause. claude.ai coverage today is via Claude Code
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

An unknown directive is parked, not guessed at: file it as a question. The
wall itself never mutates state — every button above only ENQUEUES, behind
the same-origin health probe, so a wall served without its host stays
read-only (DEC-0030).
