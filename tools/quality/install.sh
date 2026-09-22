#!/usr/bin/env bash
# Install the structural-scan lane's tools at their pins (default) or at the
# latest release (--latest, used by the scanner-bump canary). Prints before it
# installs; nothing here touches the system outside the chosen installer.
#   bash tools/quality/install.sh [--latest]
set -eu
root="$(cd "$(dirname "$0")/../.." && pwd)"
py="$(command -v python3 || command -v python)"
q="$py $root/tools/wall/quality.py"
if [ "${1:-}" = --latest ]; then
  ag="ast-grep-cli"
  ss="skillspector @ git+https://github.com/NVIDIA/skillspector.git"
else
  ag="ast-grep-cli==$($q pin ast-grep)"
  ss="skillspector @ git+https://github.com/NVIDIA/skillspector.git@$($q pin skillspector)"
fi
echo "install: $ag"
echo "install: $ss  (needs Python >= 3.12)"
if command -v uv >/dev/null 2>&1 && [ -z "${CI:-}" ]; then
  uv tool install --force "$ag"
  uv tool install --force --python 3.12 "$ss"
else
  "$py" -m pip install --quiet "$ag" "$ss"
fi
