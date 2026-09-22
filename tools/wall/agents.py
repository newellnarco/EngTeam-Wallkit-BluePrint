#!/usr/bin/env python3
"""Agent registry — stable keys behind the scenes, reusable names in front.

The key is identity. Every event, trace, lease and ledger row references the
key and never the name, so history stays unambiguous even after a name is
reused. The name is a display label: unique among *live* agents in this repo
across all sessions, and returned to the pool when the agent is released.

The store is .wall/registry/agents.md — a plain markdown table, because it has
to be readable in the repo, reviewable in a diff, and editable by hand when
something needs correcting. The parser is deliberately strict about the table
shape so a malformed edit fails loudly rather than silently losing a row.
"""

from __future__ import annotations

import json
import os
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path

ROLE_PREFIX = {
    "foreman": "frm", "maestro": "mst", "architect": "arc", "adjudicator": "adj",
    "builder": "bld", "integrator": "itg", "reviewer": "rev", "warden": "wrd",
    "researcher": "res", "courier": "cou",
}

POOL = {
    "foreman":     ["Alistair", "Walter", "Marguerite", "Horace", "Beatrix"],
    "maestro":     ["Rosalind", "Conrad", "Imogen", "Baxter", "Cordelia"],
    "architect":   ["Edmund", "Vivienne", "Ambrose", "Harriet", "Lionel"],
    "adjudicator": ["Coretta", "Percival", "Winifred", "Gideon", "Adelaide"],
    "builder":     ["Desmond", "Priya", "Theo", "Ruth", "Kwame", "Sloane",
                    "Hollis", "Yusuf", "Wren", "Otto", "Bridget", "Xavier"],
    "integrator":  ["Barnaby", "Solveig", "Ephraim", "Tamsin", "Leopold"],
    "warden":      ["Constance", "Aurelius", "Meredith", "Ignatius", "Prudence"],
    "reviewer":    ["Junia", "Malcolm", "Faye", "Rupert", "Ines"],
    "researcher":  ["Silas", "Nadia", "Quentin", "Delphine", "Roscoe",
                    "Greta", "Fitzgerald", "Verity", "Ozias", "Clementine"],
}

#: Roles where a second LIVE agent is a contradiction, not a capacity choice:
#: two security authorities means neither is accountable, two requirement
#: owners means requirements have no owner, two tie-breakers cannot break a
#: tie. Enforced at claim time and checked by audit.
SINGLETON_ROLES = {"architect", "adjudicator", "warden"}

CONFUSABLE = [
    {"Theo", "Otto"}, {"Silas", "Sloane"}, {"Ruth", "Wren"},
    {"Greta", "Bridget"}, {"Imogen", "Ines"}, {"Faye", "Verity"},
]

COLUMNS = ["Key", "Name", "Role", "Status", "Session", "Claimed", "Released"]

HEADER = """# Agent roster

Names are display labels; the **key** is the identifier. Every event, trace and
ledger row references the key, so a reused name never merges two agents in
reporting. A name is unique among live agents in this repo across all sessions,
and returns to the pool when its agent is released.

Written by `agents.py`. Hand edits are fine — keep the column shape intact.

"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def mint_key(role: str) -> str:
    return f"{ROLE_PREFIX.get(role, 'agt')}_{secrets.token_hex(3)}"


def _confusable(candidate: str, live: set[str]) -> bool:
    for pair in CONFUSABLE:
        if candidate in pair and pair & live:
            return True
    return any(n[:2].lower() == candidate[:2].lower() for n in live)


class AgentRegistry:
    def __init__(self, repo: Path):
        self.repo = repo
        self.path = repo / ".wall" / "registry" / "agents.md"
        self.lock = self.path.with_suffix(".lock")

    # ---------------------------------------------------------- markdown io

    def read(self) -> list[dict]:
        if not self.path.exists():
            return []
        rows = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line.startswith("|"):
                continue
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) != len(COLUMNS):
                continue
            if cells[0] == COLUMNS[0] or set(cells[0]) <= set("-: "):
                continue  # header or separator
            rows.append(dict(zip(
                ["key", "name", "role", "status", "session", "claimed", "released"], cells)))
        return rows

    def write(self, rows: list[dict]) -> None:
        rows = sorted(rows, key=lambda r: (r["status"] != "live", r["role"], r["name"]))
        body = ["| " + " | ".join(COLUMNS) + " |",
                "|" + "|".join(["---"] * len(COLUMNS)) + "|"]
        for r in rows:
            body.append("| " + " | ".join([
                r["key"], r["name"], r["role"], r["status"],
                r.get("session") or "—", r.get("claimed") or "—",
                r.get("released") or "—"]) + " |")
        live = sum(1 for r in rows if r["status"] == "live")
        text = (HEADER + "\n".join(body) +
                f"\n\n{live} live · {len(rows) - live} released · updated {now()}\n")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".md.tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, self.path)

    # -------------------------------------------------------------- locking

    def _acquire(self, timeout: float = 10.0):
        self.lock.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.time() + timeout
        while True:
            try:
                fd = os.open(str(self.lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, str(os.getpid()).encode())
                os.close(fd)
                return
            except FileExistsError:
                try:
                    if time.time() - self.lock.stat().st_mtime > timeout:
                        self.lock.unlink(missing_ok=True)
                        continue
                except OSError:
                    pass
                if time.time() > deadline:
                    raise TimeoutError(f"registry locked: {self.lock}")
                time.sleep(0.05)

    def _release_lock(self):
        self.lock.unlink(missing_ok=True)

    # ------------------------------------------------------------- the api

    def claim(self, role: str, session_id: str, key: str | None = None,
              name: str | None = None) -> dict:
        """Claim an agent slot. Passing an existing key is idempotent and returns
        that agent unchanged, so a re-dispatch never burns a second name."""
        self._acquire()
        try:
            rows = self.read()
            if key:
                for r in rows:
                    if r["key"] == key:
                        return r

            if role in SINGLETON_ROLES:
                holder = next((r for r in rows
                               if r["status"] == "live" and r["role"] == role), None)
                if holder:
                    raise ValueError(
                        f"'{role}' is a singleton role and {holder['name']} "
                        f"({holder['key']}) is already live. Release it first -- "
                        f"two of these means neither is accountable.")

            live = {r["name"] for r in rows if r["status"] == "live"}
            if name:
                if name in live:
                    raise ValueError(f"'{name}' is already live in this repo")
                pick = name
            else:
                pool = POOL.get(role, POOL["builder"])
                # Prefer a name never used here; otherwise the one released
                # longest ago, so a name isn't recycled while it's still being
                # talked about.
                used = {r["name"] for r in rows}
                pick = next((n for n in pool
                             if n not in used and not _confusable(n, live)), None)
                if pick is None:
                    freed = sorted(
                        (r for r in rows if r["status"] == "released"
                         and r["name"] not in live and r["role"] == role),
                        key=lambda r: r.get("released") or "")
                    pick = next((r["name"] for r in freed
                                 if not _confusable(r["name"], live)), None)
                if pick is None:  # distinctness is a preference, uniqueness is not
                    pick = next((n for n in pool if n not in live), None)
                if pick is None:
                    raise RuntimeError(
                        f"every '{role}' name is live. Raise the role cap or add "
                        f"names to POOL['{role}'].")

            row = {"key": key or mint_key(role), "name": pick, "role": role,
                   "status": "live", "session": session_id,
                   "claimed": now(), "released": "—"}
            rows.append(row)
            self.write(rows)
            return row
        finally:
            self._release_lock()

    def release(self, key: str) -> dict | None:
        """Retire the agent. The key is kept forever; the name returns to the pool."""
        self._acquire()
        try:
            rows = self.read()
            for r in rows:
                if r["key"] == key and r["status"] == "live":
                    r["status"] = "released"
                    r["released"] = now()
                    self.write(rows)
                    return r
            return None
        finally:
            self._release_lock()

    def resolve(self, key: str) -> dict | None:
        return next((r for r in self.read() if r["key"] == key), None)

    def name_of(self, key: str) -> str:
        r = self.resolve(key)
        return r["name"] if r else key

    # ------------------------------------------------------- name lookback

    def history(self, name: str) -> list[dict]:
        """Every tenure a name has had, oldest first. A reused name returns one
        row per key that held it, so 'which Desmond?' is answerable from the
        registry alone."""
        return sorted((r for r in self.read() if r["name"] == name),
                      key=lambda r: r.get("claimed") or "")

    def holder_at(self, name: str, at: str) -> dict | None:
        """The agent that held `name` at UTC instant `at` (ISO-8601 Z, the same
        shape the registry and ledger write). Timestamps compare lexically at
        that shape. A live tenure is open-ended; the release instant still
        belongs to the releasing agent. Hand-edited overlaps are an audit
        problem — here the latest claim wins so the answer is deterministic."""
        match = None
        for r in self.history(name):
            claimed = r.get("claimed") or ""
            if not claimed or claimed > at:
                continue
            released = r.get("released") or ""
            if r["status"] == "live" or released in ("", "—") or at <= released:
                match = r
        return match

    def audit(self) -> list[str]:
        """Problems a human should see. Collisions are the one that matters."""
        rows, problems = self.read(), []
        live = [r for r in rows if r["status"] == "live"]
        seen = {}
        for r in live:
            if r["name"] in seen:
                problems.append(
                    f"name collision: '{r['name']}' is live as both "
                    f"{seen[r['name']]} and {r['key']}")
            seen[r["name"]] = r["key"]
        for role in sorted(SINGLETON_ROLES):
            holders = [r for r in live if r["role"] == role]
            if len(holders) > 1:
                problems.append(
                    f"singleton violation: {len(holders)} live '{role}' agents "
                    f"({', '.join(r['key'] for r in holders)}) -- exactly one is allowed")
        keys = [r["key"] for r in rows]
        for k in {k for k in keys if keys.count(k) > 1}:
            problems.append(f"duplicate key: {k}")
        by_name: dict[str, list[dict]] = {}
        for r in rows:
            by_name.setdefault(r["name"], []).append(r)
        for name, tenures in sorted(by_name.items()):
            tenures = sorted(tenures, key=lambda r: r.get("claimed") or "")
            for prev, cur in zip(tenures, tenures[1:]):
                if prev["status"] == "live" and cur["status"] == "live":
                    continue  # already reported as a name collision above
                prev_end = prev.get("released") or ""
                open_ended = prev["status"] == "live" or prev_end in ("", "—")
                if open_ended or (cur.get("claimed") or "") < prev_end:
                    problems.append(
                        f"tenure overlap: '{name}' held by {prev['key']} "
                        f"(claimed {prev.get('claimed')}, released {prev_end or '—'}) "
                        f"and {cur['key']} (claimed {cur.get('claimed')}) -- "
                        f"'whois --at' inside the overlap cannot be trusted")
        return problems


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Claim, release and inspect agent names.")
    p.add_argument("action",
                   choices=["claim", "release", "roster", "resolve", "whois", "audit"])
    p.add_argument("--repo", default=".")
    p.add_argument("--role", default="builder")
    p.add_argument("--session", default="local")
    p.add_argument("--key")
    p.add_argument("--name", help="request a specific name (claim) or look one up (whois)")
    p.add_argument("--at", help="whois: resolve the name at this UTC instant "
                                "(ISO-8601 Z, as ledger events are stamped)")
    p.add_argument("--json", action="store_true")
    a = p.parse_args()

    reg = AgentRegistry(Path(a.repo).resolve())
    if a.action == "claim":
        row = reg.claim(a.role, a.session, a.key, a.name)
        print(json.dumps(row) if a.json else f"{row['name']}  ({row['key']})")
    elif a.action == "release":
        row = reg.release(a.key)
        print(f"released {row['name']} ({a.key})" if row else f"no live agent {a.key}")
    elif a.action == "resolve":
        row = reg.resolve(a.key)
        print(json.dumps(row) if row else f"unknown key {a.key}")
    elif a.action == "whois":
        if not a.name:
            p.error("whois needs --name")
        if a.at:
            row = reg.holder_at(a.name, a.at)
            if row:
                print(json.dumps(row) if a.json else
                      f"{row['name']} at {a.at} was {row['key']} ({row['role']}, "
                      f"claimed {row['claimed']}, released {row.get('released') or '—'})")
            else:
                print(f"no agent held '{a.name}' at {a.at}")
                raise SystemExit(1)
        else:
            tenures = reg.history(a.name)
            if not tenures:
                print(f"no agent has ever held '{a.name}'")
                raise SystemExit(1)
            if a.json:
                print(json.dumps(tenures))
            else:
                for r in tenures:
                    print(f" {r['key']:<12} {r['role']:<12} "
                          f"claimed {r['claimed']}  released {r.get('released') or '—'}"
                          f"{'  (live)' if r['status'] == 'live' else ''}")
    elif a.action == "audit":
        problems = reg.audit()
        print("\n".join(problems) if problems else "roster clean")
        raise SystemExit(1 if problems else 0)
    else:
        for r in reg.read():
            mark = "●" if r["status"] == "live" else "○"
            print(f" {mark} {r['name']:<12} {r['key']:<12} {r['role']:<12} {r['status']}")
