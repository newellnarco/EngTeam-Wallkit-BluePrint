#!/usr/bin/env bash
# The structural-scan lane (docs/TESTING_STANDARDS.md section 5.1): one script,
# run identically by CI, the pre-push hook and a builder's gates-last step.
#
#   bash tools/quality/scan.sh ci      a missing scanner FAILS (CI installs them)
#   bash tools/quality/scan.sh local   a missing scanner WARNS and is skipped --
#                                      the hosted pipeline stays the real gate
#
# Blocking is per rule: a rule is report-only until promoted in
# tools/quality/quality.json. Exit 1 means a definite, blocking failure.
set -u
mode="${1:-local}"
root="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$root" || exit 2
py="$(command -v python3 || command -v python)"
q="$py tools/wall/quality.py"
fail=0
skipped=0

missing() {
  if [ "$mode" = ci ]; then
    echo "scan: $1 is not installed -- run tools/quality/install.sh" >&2
    fail=1
  else
    skipped=$((skipped + 1))
    echo "scan: $1 not installed; skipped (install: bash tools/quality/install.sh)" >&2
  fi
}

# 1. Derived rules in sync with the failure registry. Needs only python.
$q rules --check || fail=1

# 2 + 3. ast-grep: every rule can go red, then the scan itself.
if command -v ast-grep >/dev/null 2>&1; then
  ast-grep test --skip-snapshot-tests || fail=1
  errs=()
  while IFS= read -r rid; do [ -n "$rid" ] && errs+=("--error=$rid"); done \
    < <($q promoted ast-grep)
  fmt=()
  [ -n "${GITHUB_ACTIONS:-}" ] && fmt=(--format github)
  ast-grep scan "${fmt[@]}" "${errs[@]}" || fail=1
else
  missing ast-grep
fi

# Custom rules and the fixture proving each (docs/SCAN_LANE.md). A rule with
# no fixture, or a fixture with no rule, fails here; the fixtures themselves
# are run below by the scanner that owns them.
proofs="$($q proofs)" || fail=1

# 4. SkillSpector, static only (--no-llm): no API key, no content leaves the
#    machine, same answer on every run. Custom YARA rules and per-target
#    baselines join in when present.
if command -v skillspector >/dev/null 2>&1; then
  out="$(mktemp -d)"
  yara=()
  compgen -G ".skillspector/yara/*.yar*" >/dev/null && yara=(--yara-rules-dir .skillspector/yara)
  while read -r kind rule fx; do
    [ "$kind" = yara ] || continue
    skillspector scan "$fx" --no-llm "${yara[@]}" --format json -o "$out/proof.json" >/dev/null 2>&1
    if ! grep -q "YARA rule '$rule'" "$out/proof.json" 2>/dev/null; then
      echo "scan: YARA rule $rule did not fire on its fixture $fx" >&2
      fail=1
    fi
    rm -f "$out/proof.json"
  done <<< "$proofs"
  n=0
  while IFS= read -r target; do
    for t in $target; do            # unquoted on purpose: expands the glob
      [ -e "$t" ] || continue
      n=$((n + 1))
      base=()
      bp="$($q baseline-path "$t")"
      [ -f "$bp" ] && base=(--baseline "$bp")
      skillspector scan "$t" --no-llm "${yara[@]}" "${base[@]}" --format json \
        -o "$out/$n.json" >/dev/null 2>"$out/$n.err"
      rc=$?
      if [ "$rc" -ge 2 ] || [ ! -s "$out/$n.json" ]; then
        echo "scan: skillspector could not scan $t (exit $rc)" >&2
        tail -n 5 "$out/$n.err" >&2
        fail=1
        rm -f "$out/$n.json"
      fi
    done
  done < <($py -c 'import json;[print(t) for t in json.load(open("tools/quality/quality.json"))["skillspector"]["targets"]]')
  reports=("$out"/*.json)
  if [ -e "${reports[0]}" ]; then
    $q gate-skillspector "${reports[@]}" || fail=1
  fi
  rm -rf "$out"
else
  missing skillspector
fi

# 5. gitleaks over the whole history (seconds at this size). Always blocking:
#    a secrets finding is never report-only. False positives are suppressed by
#    fingerprint in .gitleaksignore, each under a dated reason.
$q suppressions || fail=1
if command -v gitleaks >/dev/null 2>&1; then
  if [ "$(git rev-parse --is-shallow-repository 2>/dev/null)" = true ]; then
    echo "scan: shallow clone -- gitleaks sees only the fetched history (CI uses fetch-depth: 0)" >&2
  fi
  gitleaks git --no-banner --redact --log-level warn . || fail=1
  # Each custom rule must fire on its fake fixture. Scanned from inside the
  # fixture directory so the config's fixture allowlist does not apply.
  while read -r kind rule fx; do
    [ "$kind" = gitleaks ] || continue
    if ! (cd "$(dirname "$fx")" && gitleaks dir "$(basename "$fx")" --config "$root/.gitleaks.toml" \
          --no-banner --log-level error --report-format json --report-path - 2>/dev/null) \
        | grep -q "\"RuleID\": *\"$rule\""; then
      echo "scan: gitleaks rule $rule did not fire on its fixture $fx" >&2
      fail=1
    fi
  done <<< "$proofs"
else
  missing gitleaks
fi

# 6. ruff's security rules (S, the bandit set). Promoted rules block; the full
#    set reports.
if command -v ruff >/dev/null 2>&1; then
  rtargets=()                       # bash 3.2 (macOS) has no mapfile
  while IFS= read -r rt; do rtargets+=("$rt"); done \
    < <($py -c 'import json;[print(t) for t in json.load(open("tools/quality/quality.json"))["ruff"]["targets"]]')
  rsel="$($py -c 'import json;print(",".join(json.load(open("tools/quality/quality.json"))["ruff"]["select"]))')"
  rfmt=()
  [ -n "${GITHUB_ACTIONS:-}" ] && rfmt=(--output-format github)
  rblock="$($q promoted ruff | paste -sd, -)"
  if [ -n "$rblock" ]; then
    ruff check --isolated --select "$rblock" "${rfmt[@]}" "${rtargets[@]}" || fail=1
  fi
  echo "scan: ruff security rules (report-only unless promoted):"
  ruff check --isolated --select "$rsel" --exit-zero --statistics "${rtargets[@]}"
else
  missing ruff
fi

# 7. actionlint and zizmor over the workflows, when there are any.
if [ -d .github/workflows ]; then
  if command -v actionlint >/dev/null 2>&1; then
    if $q promoted actionlint | grep -qx '\*'; then
      actionlint || fail=1
    else
      actionlint || echo "scan: actionlint findings above are report-only"
    fi
  else
    missing actionlint
  fi
  if command -v zizmor >/dev/null 2>&1; then
    zout="$(mktemp)"
    zizmor --offline --no-exit-codes --format json .github/workflows > "$zout" 2>/dev/null
    $q gate-zizmor "$zout" || fail=1
    rm -f "$zout"
  else
    missing zizmor
  fi
fi

# Three states, never two (F-STATUS-001): a skipped scanner is not "clean".
if [ "$fail" != 0 ]; then
  echo "scan: BLOCKING findings above" >&2
elif [ "$skipped" != 0 ]; then
  echo "scan: no blocking findings, but $skipped scanner(s) did not run -- UNKNOWN, not clean"
else
  echo "scan: clean"
fi
exit "$fail"
