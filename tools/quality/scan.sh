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

# 4. SkillSpector, static only (--no-llm): no API key, no content leaves the
#    machine, same answer on every run.
if command -v skillspector >/dev/null 2>&1; then
  out="$(mktemp -d)"
  n=0
  while IFS= read -r target; do
    for t in $target; do            # unquoted on purpose: expands the glob
      [ -e "$t" ] || continue
      n=$((n + 1))
      skillspector scan "$t" --no-llm --format json -o "$out/$n.json" \
        >/dev/null 2>"$out/$n.err"
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

# Three states, never two (F-STATUS-001): a skipped scanner is not "clean".
if [ "$fail" != 0 ]; then
  echo "scan: BLOCKING findings above" >&2
elif [ "$skipped" != 0 ]; then
  echo "scan: no blocking findings, but $skipped scanner(s) did not run -- UNKNOWN, not clean"
else
  echo "scan: clean"
fi
exit "$fail"
