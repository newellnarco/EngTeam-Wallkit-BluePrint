#!/usr/bin/env bash
# coderabbit-review.sh - request a CodeRabbit review without tripping the Fair Usage "slow lane".
# The kit's CodeRabbit lane and why it is throttled: REVIEWER_LANES.md (CodeRabbit block).
#
# CodeRabbit never answers a comment with HTTP 429: when a push or request is over the limit it
# posts a rate-limit COMMENT and a passing check titled "Review rate limited". This script reads
# those signals instead of guessing:
#   1. waits while a CodeRabbit review is still running (pushing/requesting inside that window
#      supersedes the running review, which is still charged);
#   2. while any CodeRabbit rate-limit notice's stated wait is still running, sleeps it out (timed
#      from the notice's last edit), but only when the limit clears within CR_MAX_WAIT (20 min,
#      every rate-limit wait in the run counted). A longer limit, or a latest notice naming no
#      time, exits 4 at once with nothing posted: proceed without a CodeRabbit review. With
#      CR_MAX_WAIT=0 there is no cap, and an untimed notice backs off exponentially with jitter;
#   3. posts "@coderabbitai review" once, then confirms CodeRabbit picked it up.
# `--status` posts "@coderabbitai rate limit" (free: it does not consume a review), at most once
# per hour per PR.
#
# Usage: tools/review/coderabbit-review.sh <pr-number> [--repo owner/name] [--full] [--status] [--dry-run]
# Exit:  0 requested (or picked up) - 1 gave up - 2 usage - 4 rate limited past CR_MAX_WAIT:
#        not an error, proceed without a CodeRabbit review.
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
MAX_WAIT="${CR_MAX_WAIT:-1200}"         # wait out a rate limit only when it ends inside this (0 = no cap)
BOT_RE='^coderabbitai(\[bot\])?$'

# gh with --repo only when one was given (set -u safe).
ghr() { if [[ -n "$REPO" ]]; then gh "$@" --repo "$REPO"; else gh "$@"; fi; }
NWO="${REPO:-$(gh repo view --json nameWithOwner -q .nameWithOwner)}"

RL_RE='rate limit|rate-limited|review rate limited|review limit reached|reviews? (are|is) (currently )?unavailable'

# All issue comments on the PR as ONE array (`gh --paginate` prints one JSON array per page).
all_comments() {
  gh api "repos/$NWO/issues/$PR/comments?per_page=100" --paginate | jq -s 'add // []'
}

# Latest CodeRabbit activity on the PR: "<id>@<updated_at>\t<body>" (body flattened to one line).
# CodeRabbit edits its comments in place, so "latest" is the highest updated_at, ties broken by
# comment id; the <id>@<updated_at> key changes on a new comment AND on an edit.
last_cr_comment() {
  all_comments \
    | jq -r --arg re "$BOT_RE" '[.[] | select(.user.login | test($re))] | sort_by([(.updated_at // .created_at), .id]) | last
        | if . then "\(.id)@\(.updated_at // .created_at)\t\(.body|gsub("[\n\r\t]";" "))" else "" end'
}

to_epoch() { date -u -d "$1" +%s 2>/dev/null || date -u -j -f '%Y-%m-%dT%H:%M:%SZ' "$1" +%s; }

# Is a CodeRabbit check still running on the PR head?
review_running() {
  local sha
  sha="$(ghr pr view "$PR" --json headRefOid -q .headRefOid)"
  gh api "repos/$NWO/commits/$sha/check-runs?per_page=100" \
    | jq -e '[.check_runs[] | select((.app.slug // "" | test("coderabbit"; "i")) or (.name | test("coderabbit"; "i"))) | select(.status != "completed")] | length > 0' >/dev/null
}

# Prints "<wait> <untimed>": <wait> is the longest cooldown still running across ALL CodeRabbit
# rate-limit notices, timed from each notice's updated_at (notices are edited in place), so a newer
# ordinary comment cannot hide one; <untimed> is 1 when the latest CodeRabbit activity is a
# rate-limit notice that names no time (the caller then backs off, never for less than <wait>).
rate_limit_wait() {
  local now latest best=0 untimed=0 key ts body hours mins secs wait left
  now="$(date -u +%s)"
  latest="$(last_cr_comment | cut -f1)"
  while IFS=$'\t' read -r key body; do
    [[ -z "$key" ]] && continue
    ts="${key#*@}"
    hours="$(grep -oiE '([0-9]+) ?hours?' <<<"$body" | head -1 | grep -oE '[0-9]+' || true)"
    mins="$(grep -oiE '([0-9]+) ?minutes?' <<<"$body" | head -1 | grep -oE '[0-9]+' || true)"
    secs="$(grep -oiE '([0-9]+) ?seconds?' <<<"$body" | head -1 | grep -oE '[0-9]+' || true)"
    wait=$(( ${hours:-0} * 3600 + ${mins:-0} * 60 + ${secs:-0} ))
    if (( wait == 0 )); then [[ "$key" == "$latest" ]] && untimed=1; continue; fi
    left=$(( $(to_epoch "$ts") + wait + 30 - now ))
    if (( left > best )); then best=$left; fi
  done < <(all_comments | jq -r --arg re "$BOT_RE" --arg rl "$RL_RE" \
    '.[] | select(.user.login | test($re)) | select(.body | test($rl; "i"))
       | "\(.id)@\(.updated_at // .created_at)\t\(.body|gsub("[\n\r\t]";" "))"')
  echo "$best $untimed"
}

say() { printf '%s %s\n' "$(date -u +%H:%M:%S)" "$*"; }
post() { if (( DRY )); then say "[dry-run] would comment: $1"; else ghr pr comment "$PR" --body "$1" >/dev/null; fi; }

if (( STATUS )); then
  line="$(last_cr_comment)"
  if grep -q '@coderabbitai rate limit' <<<"$(all_comments | jq -r --arg since "$(date -u -d '-1 hour' +%FT%TZ 2>/dev/null || date -u -v-1H +%FT%TZ)" '.[] | select(.created_at > $since) | .body')"; then
    say "A rate-limit check was already posted in the last hour; latest CodeRabbit reply:"; echo "${line#*$'\t'}"; exit 0
  fi
  post "@coderabbitai rate limit"; say "Posted a rate-limit check (does not consume a review)."; exit 0
fi

attempt=1
limit_slept=0
while (( attempt <= MAX_RETRIES )); do
  while review_running; do say "CodeRabbit review still running on the head commit; waiting 60s (a new request now would supersede it)."; sleep 60; done
  read -r known untimed <<<"$(rate_limit_wait)"
  # Owner rule: a rate limit that clears within CR_MAX_WAIT (20 min) in total is waited out;
  # a longer one, or one naming no time, is not: the work proceeds without CodeRabbit.
  if (( MAX_WAIT > 0 )) && (( untimed )); then
    say "Rate limited and CodeRabbit names no time. Not waiting: proceed without a CodeRabbit review."
    exit 4
  elif (( MAX_WAIT > 0 && known > 0 && limit_slept + known > MAX_WAIT )); then
    say "Rate limited for ~${known}s more; with ${limit_slept}s already waited that passes CR_MAX_WAIT (${MAX_WAIT}s). Not waiting: proceed without a CodeRabbit review."
    exit 4
  elif (( untimed )); then
    wait=$(( BASE_DELAY * (2 ** (attempt - 1)) + RANDOM % 30 ))
    (( wait < known )) && wait=$known
    (( wait > MAX_DELAY )) && wait=$MAX_DELAY
    say "Rate limited (slow lane) with no time given; backing off ${wait}s (attempt $attempt/$MAX_RETRIES)."
    sleep "$wait"; attempt=$((attempt + 1)); continue
  elif (( known > 0 )); then
    wait=$known
    (( wait > MAX_DELAY )) && wait=$MAX_DELAY
    say "Rate limited; CodeRabbit says capacity returns in ~${wait}s. Waiting (attempt $attempt/$MAX_RETRIES)."
    sleep "$wait"; limit_slept=$(( limit_slept + wait )); attempt=$((attempt + 1)); continue
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
      if grep -qiE "$RL_RE" <<<"${now_line#*$'\t'}"; then break; fi
      say "CodeRabbit responded."; exit 0
    fi
  done
  say "No pickup yet, or rate limited; will re-check before retrying."
  attempt=$((attempt + 1))
done
say "Gave up after $MAX_RETRIES attempts to stay out of the slow lane. Try later, or check with --status."
exit 1
