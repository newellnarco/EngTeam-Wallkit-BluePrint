#!/usr/bin/env bash
# Install the structural-scan lane's tools at their pins (tools/quality/quality.json).
# Prints each install before it runs. Python tools go through uv (locally) or
# pip (CI); gitleaks is a release binary, verified against the release's own
# checksum file before it is unpacked.
#   bash tools/quality/install.sh
# Binaries land in $QUALITY_BIN (default ~/.local/bin); on GitHub Actions that
# directory is added to the job's PATH.
set -eu
root="$(cd "$(dirname "$0")/../.." && pwd)"
py="$(command -v python3 || command -v python)"
bin="${QUALITY_BIN:-$HOME/.local/bin}"
mkdir -p "$bin"
[ -n "${GITHUB_PATH:-}" ] && echo "$bin" >> "$GITHUB_PATH"

sha256() { if command -v sha256sum >/dev/null; then sha256sum "$1"; else shasum -a 256 "$1"; fi; }

release() {                         # release <owner/repo> <version>
  repo="$1" v="$2" name="${1#*/}"
  case "$(uname -s)" in Linux) os=linux ;; Darwin) os=darwin ;;
    *) echo "install: $name: no release build for $(uname -s); install it by hand" >&2; return 0 ;; esac
  case "$(uname -m)" in x86_64|amd64) arch=x64 ;; arm64|aarch64) arch=arm64 ;;
    *) echo "install: $name: no release build for $(uname -m)" >&2; return 0 ;; esac
  asset="${name}_${v}_${os}_${arch}.tar.gz"
  base="https://github.com/$repo/releases/download/v$v"
  tmp="$(mktemp -d)"
  echo "install: $repo v$v ($asset)"
  curl -sSfL -o "$tmp/$asset" "$base/$asset"
  curl -sSfL -o "$tmp/sums" "$base/${name}_${v}_checksums.txt"
  want="$(grep " $asset\$" "$tmp/sums" | cut -d' ' -f1)"
  got="$(sha256 "$tmp/$asset" | cut -d' ' -f1)"
  if [ -z "$want" ] || [ "$want" != "$got" ]; then
    echo "install: $asset checksum mismatch (want ${want:-none}, got $got) -- refusing" >&2
    rm -rf "$tmp"; return 1
  fi
  tar -xzf "$tmp/$asset" -C "$tmp" "$name"
  install -m 0755 "$tmp/$name" "$bin/$name"
  rm -rf "$tmp"
}

pips=()
while IFS= read -r line; do
  case "$line" in
    "pip "*) pips+=("${line#pip }") ;;
    "release "*) set -- ${line#release }; release "$1" "$2" ;;
  esac
done < <("$py" "$root/tools/wall/quality.py" install-plan)

for spec in "${pips[@]}"; do echo "install: $spec"; done
if command -v uv >/dev/null 2>&1 && [ -z "${CI:-}" ]; then
  # SkillSpector needs Python >= 3.12; uv fetches one if the machine lacks it.
  for spec in "${pips[@]}"; do uv tool install --quiet --force --python 3.12 "$spec"; done
else
  "$py" -m pip install --quiet "${pips[@]}"
fi
