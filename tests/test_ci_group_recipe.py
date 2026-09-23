"""The DEC-0035 concurrency recipe, evaluated under each event payload.

DEC-0035 lets a project add `push` on working branches beside
`pull_request`, provided both events for one branch share ONE cancelling
concurrency group. The recipe lives in the decision record; this test reads
it from there and evaluates it, so the text an adopter copies is the text
that was proven:

- a push and a pull request from the same branch of this repository collapse
  into one group (the point of the recipe);
- a fork's pull request from a same-named branch gets a different group, so
  it can never cancel this repository's run;
- two different branches never share a group;
- a run on the default branch is never cancelled.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

KIT = Path(__file__).resolve().parents[1]
DEC = KIT / "docs" / "decisions" / "DEC-0035.md"
REPO = "owner/kit"


def _recipe() -> tuple[str, str]:
    text = DEC.read_text(encoding="utf-8")
    group = re.search(r"^\s*group:\s*(.+)$", text, re.M)
    cancel = re.search(r"^\s*cancel-in-progress:\s*(.+)$", text, re.M)
    assert group and cancel, "DEC-0035 lost its concurrency recipe"
    return group.group(1).strip(), cancel.group(1).strip()


def _lookup(ctx: dict, dotted: str):
    node = ctx
    for part in dotted.split("."):
        node = node.get(part) if isinstance(node, dict) else None
    return node


def _expr(ctx: dict, expr: str):
    """The subset of the Actions expression language the recipe uses:
    context paths, `a || b` (first truthy) and `a != b`."""
    expr = expr.strip()
    if "!=" in expr:
        left, right = expr.split("!=", 1)
        return _expr(ctx, left) != _expr(ctx, right)
    for part in expr.split("||"):
        value = _lookup(ctx, part.strip())
        if value:
            return value
    return ""


def evaluate(ctx: dict, template: str):
    """Evaluate a `${{ }}` template; a template that is one expression
    returns that expression's own type (as Actions does for booleans)."""
    parts = re.split(r"\$\{\{(.*?)\}\}", template)
    if len(parts) == 3 and not parts[0] and not parts[2]:
        return _expr(ctx, parts[1])
    return "".join(str(_expr(ctx, p)) if i % 2 else p for i, p in enumerate(parts))


def push(branch: str) -> dict:
    return {"github": {"workflow": "CI", "repository": REPO, "event_name": "push",
                       "ref": "refs/heads/" + branch, "ref_name": branch, "head_ref": "",
                       "event": {"repository": {"default_branch": "main"}}}}


def pull_request(branch: str, head_repo: str = REPO, number: int = 7) -> dict:
    return {"github": {"workflow": "CI", "repository": REPO, "event_name": "pull_request",
                       "ref": "refs/pull/%d/merge" % number, "ref_name": "%d/merge" % number,
                       "head_ref": branch,
                       "event": {"repository": {"default_branch": "main"},
                                 "pull_request": {"head": {"repo": {"full_name": head_repo}}}}}}


def test_push_and_pull_request_from_one_branch_collapse():
    group, _ = _recipe()
    assert evaluate(push("feature/x"), group) == evaluate(pull_request("feature/x"), group)


def test_a_forks_same_named_branch_gets_its_own_group():
    group, _ = _recipe()
    ours = evaluate(pull_request("patch-1"), group)
    fork = evaluate(pull_request("patch-1", head_repo="someone/kit", number=8), group)
    assert ours != fork
    assert evaluate(push("patch-1"), group) != fork


def test_different_branches_never_share_a_group():
    group, _ = _recipe()
    assert evaluate(push("a"), group) != evaluate(push("b"), group)
    assert evaluate(pull_request("a"), group) != evaluate(pull_request("b", number=9), group)


@pytest.mark.parametrize("ctx,expected", [
    (push("main"), False),
    (push("feature/x"), True),
    (pull_request("feature/x"), True),
])
def test_only_the_default_branch_is_never_cancelled(ctx, expected):
    _, cancel = _recipe()
    assert evaluate(ctx, cancel) is expected


def test_the_evaluator_reads_the_old_key_as_the_flaw_it_was():
    """Mutation, in miniature: the branch-name-only key the review found
    unsafe really does put a fork's pull request in our group."""
    old = "${{ github.workflow }}-${{ github.head_ref || github.ref_name }}"
    assert evaluate(pull_request("patch-1"), old) == evaluate(
        pull_request("patch-1", head_repo="someone/kit", number=8), old)
