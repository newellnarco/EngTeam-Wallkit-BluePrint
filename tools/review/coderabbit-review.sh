#!/usr/bin/env bash
# coderabbit-review.sh - request a CodeRabbit review without tripping the Fair Usage "slow lane".
# The kit's CodeRabbit lane and why it is throttled: REVIEWER_LANES.md (CodeRabbit block).
#
# CodeRabbit never answers a comment with HTTP 429: when a push or request is over the limit it
# posts a rate-limit COMMENT and a passing check titled "Review rate limited". This script reads
# those signals instead of guessing:
#   1. waits while a CodeRabbit review is still running (pushing/requesting inside that window
#      supersedes the running review, which is still charged);
#   2. if the latest CodeRabbit comment is a rate-limit notice, sleeps until the time it names
#      (or an exponential backoff with jitter when it names none);
#   3. posts "@coderabbitai review" once, then confirms CodeRabbit picked it up.
# `--status` posts "@coderabbitai rate limit" (free: it does not consume a review), at most once
# per hour per PR.
#
# Usage: tools/review/coderabbit-review.sh <pr-number> [--repo owner/name] [--full] [--status] [--dry-run]
# Needs: gh (authenticated), jq.
set -euo pipefail

PR="${1:-${PR_NUMBER:-}}"
[[ -z "$PR" ]] && { echo "usage: $0 <pr-number> [--repo owner/name] [--full] [--status] [--dry-run]" >&2; exit 2; }
shift || true
REPO=""
CMD="@coderabbitai review"
STATUS=0
DRY=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo) REPO="$2"; shift 2 ;;
    --full) CMD="@coderabbitai full review"; shift ;;
    --status) STATUS=1; shift ;;
    --dry-run) DRY=1; shift ;;
    *) echo "unknown option $1" >&2; exit 2 ;;
  esac
done

MAX_RETRIES="${CR_MAX_RETRIES:-4}"
BASE_DELAY="${CR_BASE_DELAY:-120}"      # seconds; reviews take ~5 min, so start at 2 min
MAX_DELAY="${CR_MAX_DELAY:-3600}"       # never wait more than an hour per attempt
BOT_RE='^coderabbitai(\[bot\])?$'

# gh with --repo only when one was given (set -u safe).
ghr() { if [[ -n "$REPO" ]]; then gh "$@" --repo "$REPO"; else gh "$@"; fi; }
NWO="${REPO:-$(gh repo view --json nameWithOwner -q .nameWithOwner)}"

# Latest CodeRabbit issue comment on the PR: "<created_at>\t<body>".
last_cr_comment() {
  gh api "repos/$NWO/issues/$PR/comments?per_page=100" --paginate \
    | jq -r --arg re "$BOT_RE" '[.[] | select(.user.login | test($re))] | last | if . then "\(.created_at)\t\(.body|gsub("\n";" "))" else "" end'
}

# Is a CodeRabbit check still running on the PR head?
review_running() {
  local sha
  sha="$(ghr pr view "$PR" --json headRefOid -q .headRefOid)"
  gh api "repos/$NWO/commits/$sha/check-runs?per_page=100" \
    | jq -e '[.check_runs[] | select((.app.slug // "" | test("coderabbit"; "i")) or (.name | test("coderabbit"; "i"))) | select(.status != "completed")] | length > 0' >/dev/null
}

# Seconds to wait if the latest CodeRabbit comment is a rate-limit notice, else 0.
rate_limit_wait() {
  local line body ts
  line="$(last_cr_comment)"
  [[ -z "$line" ]] && { echo 0; return; }
  ts="${line%%$'\t'*}"; body="${line#*$'\t'}"
  if ! grep -qiE 'rate limit|rate-limited|review rate limited|reviews? (are|is) (currently )?unavailable' <<<"$body"; then echo 0; return; fi
  local mins secs wait now posted
  mins="$(grep -oiE '([0-9]+) ?minutes?' <<<"$body" | head -1 | grep -oE '[0-9]+' || true)"
  secs="$(grep -oiE '([0-9]+) ?seconds?' <<<"$body" | head -1 | grep -oE '[0-9]+' || true)"
  wait=$(( ${mins:-0} * 60 + ${secs:-0} ))
  [[ $wait -eq 0 ]] && { echo -1; return; }   # limited, but no time given
  now="$(date -u +%s)"; posted="$(date -u -d "$ts" +%s 2>/dev/null || date -u -j -f '%Y-%m-%dT%H:%M:%SZ' "$ts" +%s)"
  local left=$(( posted + wait + 30 - now ))
  (( left > 0 )) && echo "$left" || echo 0
}

say() { printf '%s %s\n' "$(date -u +%H:%M:%S)" "$*"; }
post() { if (( DRY )); then say "[dry-run] would comment: $1"; else ghr pr comment "$PR" --body "$1" >/dev/null; fi; }

if (( STATUS )); then
  line="$(last_cr_comment)"
  if grep -q '@coderabbitai rate limit' <<<"$(gh api "repos/$NWO/issues/$PR/comments?per_page=100" --paginate | jq -r --arg since "$(date -u -d '-1 hour' +%FT%TZ 2>/dev/null || date -u -v-1H +%FT%TZ)" '.[] | select(.created_at > $since) | .body')"; then
    say "A rate-limit check was already posted in the last hour; latest CodeRabbit reply:"; echo "${line#*$'\t'}"; exit 0
  fi
  post "@coderabbitai rate limit"; say "Posted a rate-limit check (does not consume a review)."; exit 0
fi

attempt=1
while (( attempt <= MAX_RETRIES )); do
  while review_running; do say "CodeRabbit review still running on the head commit; waiting 60s (a new request now would supersede it)."; sleep 60; done
  wait="$(rate_limit_wait)"
  if [[ "$wait" == "-1" ]]; then
    wait=$(( BASE_DELAY * (2 ** (attempt - 1)) + RANDOM % 30 ))
    (( wait > MAX_DELAY )) && wait=$MAX_DELAY
    say "Rate limited (slow lane) with no time given; backing off ${wait}s (attempt $attempt/$MAX_RETRIES)."
    sleep "$wait"; attempt=$((attempt + 1)); continue
  elif (( wait > 0 )); then
    (( wait > MAX_DELAY )) && wait=$MAX_DELAY
    say "Rate limited; CodeRabbit says capacity returns in ~${wait}s. Waiting (attempt $attempt/$MAX_RETRIES)."
    sleep "$wait"; attempt=$((attempt + 1)); continue
  fi
  before="$(last_cr_comment | cut -f1)"
  post "$CMD"
  say "Requested: $CMD"
  (( DRY )) && exit 0
  # Confirm pickup: a new CodeRabbit comment or a running CodeRabbit check within ~3 minutes.
  for _ in $(seq 1 18); do
    sleep 10
    if review_running; then say "CodeRabbit is reviewing."; exit 0; fi
    now_line="$(last_cr_comment)"; now_ts="${now_line%%$'\t'*}"
    if [[ -n "$now_ts" && "$now_ts" != "$before" ]]; then
      if grep -qiE 'rate limit|rate-limited' <<<"${now_line#*$'\t'}"; then break; fi
      say "CodeRabbit responded."; exit 0
    fi
  done
  say "No pickup yet, or rate limited; will re-check before retrying."
  attempt=$((attempt + 1))
done
say "Gave up after $MAX_RETRIES attempts to stay out of the slow lane. Try later, or check with --status."
exit 1
