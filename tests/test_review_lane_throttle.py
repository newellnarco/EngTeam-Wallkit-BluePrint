"""Pins on the kit's CodeRabbit lane throttle (REVIEWER_LANES.md, KI-2026-09-22-e).

CodeRabbit charges one review per push, a push that supersedes a running
review is still charged, and a rate limit arrives as a comment plus a PASSING
check, never an HTTP error. Each setting below reads fine with its value
flipped back, which is the failure mode: the lane keeps running and quietly
spends the allowance on every fix-push again. So each is pinned here, and
flipping one back fails CI (REVIEWER_LANES template, section 3: pin a lane's
draft choice with a test).

Stdlib + pytest only: the config is read line by line, not with a YAML
library the suite does not install.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

KIT = Path(__file__).resolve().parents[1]
CONFIG = KIT / ".coderabbit.yaml"
SCRIPT = KIT / "tools" / "review" / "coderabbit-review.sh"
LANES = KIT / "REVIEWER_LANES.md"
LANES_T = KIT / "templates" / "REVIEWER_LANES.md.template"


def _auto_review_block(text: str) -> dict[str, str]:
    """The scalar keys directly under `reviews.auto_review`."""
    block = re.search(r"(?m)^  auto_review:\n((?:    .*\n|\s*\n)+)", text)
    assert block, "reviews.auto_review is missing from .coderabbit.yaml"
    return dict(re.findall(r"(?m)^    (\w+):[ \t]*([^\s#]+)", block.group(1)))


@pytest.mark.parametrize("key, value", [
    ("enabled", "true"),
    ("auto_incremental_review", "false"),
    ("auto_pause_after_reviewed_commits", "1"),
    ("drafts", "false"),
])
def test_the_lane_reviews_the_opening_push_of_a_ready_pr_only(key, value):
    keys = _auto_review_block(CONFIG.read_text(encoding="utf-8"))
    assert keys.get(key) == value, "auto_review.%s is %r, expected %r" % (
        key, keys.get(key), value)


def test_the_block_reader_sees_a_flip():
    """Mutation, in miniature: the reader must report a flipped value."""
    flipped = "reviews:\n  auto_review:\n    drafts: true\n    enabled: true\n"
    assert _auto_review_block(flipped)["drafts"] == "true"


def test_no_invented_config_key():
    """CodeRabbit has no `request_review_label`; an unknown key is ignored
    silently, so it would read as a control that does nothing."""
    assert "request_review_label" not in CONFIG.read_text(encoding="utf-8")


def test_the_requester_is_executable_and_parses():
    assert SCRIPT.is_file()
    if os.name != "nt":
        assert os.access(SCRIPT, os.X_OK), "coderabbit-review.sh lost its exec bit"
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("no bash on this machine")
    subprocess.run([bash, "-n", str(SCRIPT)], check=True)


@pytest.mark.parametrize("phrase", [
    "review_running",            # checks for a running review before asking
    "rate_limit_wait",           # reads the rate-limit comment
    "RANDOM % 30",               # jitter on the backoff
    'MAX_RETRIES="${CR_MAX_RETRIES:-4}"',   # a retry cap
    "@coderabbitai rate limit",  # the free status check
    "jq -s 'add // []'",         # combines every page of comments before reading them
    'select(.body | test($rl; "i"))',  # weighs every rate-limit notice, not only the latest comment
    "sort_by([(.updated_at // .created_at), .id])",  # latest = last edit, ties broken by comment id
    "(( wait < known )) && wait=$known",  # an untimed backoff never cuts a known cooldown short
    "${hours:-0} * 3600",        # a stated wait in hours counts ("1 hour and 5 minutes")
    "review limit reached",      # CodeRabbit's current notice wording, matched without its HTML marker
])
def test_the_requester_keeps_its_throttle(phrase):
    assert phrase in SCRIPT.read_text(encoding="utf-8"), phrase


def test_the_register_records_the_meter_and_the_requester():
    flat = " ".join(LANES.read_text(encoding="utf-8").split())
    assert "one review per push, not per commit" in flat
    assert "Review rate limited" in flat
    assert "tools/review/coderabbit-review.sh" in flat


def test_the_template_carries_the_rule_to_adopters():
    flat = " ".join(LANES_T.read_text(encoding="utf-8").split())
    assert "A lane billed per push is asked, never pushed at." in flat
    assert "never a re-request on a timer" in flat
