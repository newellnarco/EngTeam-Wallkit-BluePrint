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
- a run on the default branch is never cancelled or replaced: each gets its
  own group, so neither a later push nor a pull request headed from the
  default branch can drop it.

Actions compares strings, and matches concurrency group names, without regard
to case. The evaluator does the same, and groups are compared with
`same_group`, so a collision that differs only in case is not missed.
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


_TOKEN = re.compile(r"\s*(\|\||&&|==|!=|\(|\)|,|'[^']*'|[A-Za-z_][\w.]*)")


def _tokens(expr: str) -> list[str]:
    out, pos = [], 0
    while pos < len(expr):
        m = _TOKEN.match(expr, pos)
        if not m:
            if expr[pos:].strip():
                raise ValueError("unsupported expression: %r" % expr[pos:])
            break
        out.append(m.group(1))
        pos = m.end()
    return out


def _expr(ctx: dict, expr: str):
    """The subset of the Actions expression language the recipe uses:
    context paths, 'string' literals, format('..{0}..', x), == and !=,
    && and || (both returning an operand, as Actions does), parentheses."""
    toks = _tokens(expr)
    pos = 0

    def peek():
        return toks[pos] if pos < len(toks) else None

    def take():
        nonlocal pos
        pos += 1
        return toks[pos - 1]

    def atom():
        tok = take()
        if tok == "(":
            value = or_()
            assert take() == ")"
            return value
        if tok.startswith("'"):
            return tok[1:-1]
        if tok == "format":
            assert take() == "("
            args = [or_()]
            while peek() == ",":
                take()
                args.append(or_())
            assert take() == ")"
            fmt, rest = args[0], args[1:]
            return re.sub(r"\{(\d+)\}", lambda m: str(rest[int(m.group(1))]), fmt)
        value = _lookup(ctx, tok)
        return "" if value is None else value

    def cmp_():
        left = atom()
        while peek() in ("==", "!="):
            op, right = take(), atom()
            equal = _fold(left) == _fold(right)
            left = equal if op == "==" else not equal
        return left

    def and_():
        left = cmp_()
        while peek() == "&&":
            take()
            right = cmp_()
            left = right if left else left
        return left

    def or_():
        left = and_()
        while peek() == "||":
            take()
            right = and_()
            left = left if left else right
        return left

    value = or_()
    assert pos == len(toks), "trailing tokens in %r" % expr
    return value


def _fold(value):
    """Actions ignores case when it compares strings."""
    return value.casefold() if isinstance(value, str) else value


def same_group(a: str, b: str) -> bool:
    """Actions matches concurrency group names without regard to case."""
    return a.casefold() == b.casefold()


def evaluate(ctx: dict, template: str):
    """Evaluate a `${{ }}` template; a template that is one expression
    returns that expression's own type (as Actions does for booleans)."""
    parts = re.split(r"\$\{\{(.*?)\}\}", template)
    if len(parts) == 3 and not parts[0] and not parts[2]:
        return _expr(ctx, parts[1])
    return "".join(str(_expr(ctx, p)) if i % 2 else p for i, p in enumerate(parts))


def push(branch: str, run_id: int = 100, default: str = "main") -> dict:
    return {"github": {"workflow": "CI", "repository": REPO, "event_name": "push",
                       "run_id": run_id,
                       "ref": "refs/heads/" + branch, "ref_name": branch, "head_ref": "",
                       "event": {"repository": {"default_branch": default}}}}


def pull_request(branch: str, head_repo: str = REPO, number: int = 7,
                 run_id: int = 200) -> dict:
    return {"github": {"workflow": "CI", "repository": REPO, "event_name": "pull_request",
                       "run_id": run_id,
                       "ref": "refs/pull/%d/merge" % number, "ref_name": "%d/merge" % number,
                       "head_ref": branch,
                       "event": {"repository": {"default_branch": "main"},
                                 "pull_request": {"head": {"repo": {"full_name": head_repo}}}}}}


def test_push_and_pull_request_from_one_branch_collapse():
    group, _ = _recipe()
    assert same_group(evaluate(push("feature/x"), group), evaluate(pull_request("feature/x"), group))


def test_a_forks_same_named_branch_gets_its_own_group():
    group, _ = _recipe()
    ours = evaluate(pull_request("patch-1"), group)
    fork = evaluate(pull_request("patch-1", head_repo="someone/kit", number=8), group)
    assert not same_group(ours, fork)
    assert not same_group(evaluate(push("patch-1"), group), fork)


def test_different_branches_never_share_a_group():
    group, _ = _recipe()
    assert not same_group(evaluate(push("a"), group), evaluate(push("b"), group))
    assert not same_group(evaluate(pull_request("a"), group),
                          evaluate(pull_request("b", number=9), group))


def test_each_default_branch_run_has_its_own_group():
    """A group holds one running and one pending run; a shared group would
    let a burst of merges replace the middle one's pending run."""
    group, _ = _recipe()
    first, second = evaluate(push("main", 1), group), evaluate(push("main", 2), group)
    assert not same_group(first, second)
    pr = evaluate(pull_request("main", run_id=3), group)
    assert not same_group(pr, first) and not same_group(pr, second)


def test_no_branch_name_can_spell_a_default_branch_run_group():
    """The run-id suffix uses a character git refuses in branch names, so a
    working branch named like '<default>-<id>' never joins -- and never
    cancels -- a default-branch run."""
    group, _ = _recipe()
    assert not same_group(evaluate(push("main", 1), group), evaluate(push("main-1"), group))
    assert not same_group(evaluate(push("main", 1), group), evaluate(pull_request("main-1"), group))


def test_working_branch_groups_carry_no_run_id():
    """Only the default branch is unique per run; a working branch must still
    collapse across runs, or superseded pushes are never cancelled."""
    group, _ = _recipe()
    assert same_group(evaluate(push("feature/x", 1), group), evaluate(push("feature/x", 2), group))


@pytest.mark.parametrize("ctx,expected", [
    (push("main"), False),
    (push("feature/x"), True),
    (pull_request("feature/x"), True),
])
def test_only_the_default_branch_is_never_cancelled(ctx, expected):
    _, cancel = _recipe()
    assert evaluate(ctx, cancel) is expected


def test_branches_differing_only_in_case_share_a_group():
    """The limit DEC-0035 records: git allows feature/A beside feature/a, but
    Actions matches their groups as one, so their runs cancel each other.
    No recipe can prevent it; the project keeps branch names unique without
    regard to case. Pinned so the recorded limit stays the true one."""
    group, _ = _recipe()
    assert same_group(evaluate(push("feature/A"), group), evaluate(push("feature/a"), group))
    assert same_group(evaluate(push("feature/A"), group),
                      evaluate(pull_request("feature/a"), group))


def test_a_branch_differing_from_the_default_only_in_case_is_kept_like_it():
    """`==` ignores case, so a 'Main' beside default 'main' is read as the
    default branch: its own group per run, never cancelled. That errs toward
    keeping runs, the safe direction, and is recorded rather than hidden."""
    group, cancel = _recipe()
    assert evaluate(push("Main", 1), cancel) is False
    assert not same_group(evaluate(push("Main", 1), group), evaluate(push("Main", 2), group))
    assert not same_group(evaluate(push("Main", 1), group), evaluate(push("main", 2), group))


def test_the_evaluator_compares_strings_as_actions_does():
    assert evaluate(push("x"), "${{ 'Main' == 'main' }}") is True
    assert evaluate(push("x"), "${{ 'Main' != 'main' }}") is False
    assert evaluate(push("x"), "${{ 'main' == 'trunk' }}") is False


def test_the_evaluator_reads_the_old_key_as_the_flaw_it_was():
    """Mutation, in miniature: the branch-name-only key the review found
    unsafe really does put a fork's pull request in our group."""
    old = "${{ github.workflow }}-${{ github.head_ref || github.ref_name }}"
    assert same_group(evaluate(pull_request("patch-1"), old), evaluate(
        pull_request("patch-1", head_repo="someone/kit", number=8), old))
