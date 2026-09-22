#!/usr/bin/env bash
# Step 0 of provisioning (docs/GIT_HOOKS.md section 1): copy the versioned
# hooks into this clone's hooks directory. Tests for the file (-f), not the
# executable bit, so a checkout that lost +x still installs.
set -u
root="$(cd "$(dirname "$0")/../.." && pwd)"
dest="$(git -C "$root" rev-parse --git-path hooks)"
case "$dest" in /*) ;; *) dest="$root/$dest" ;; esac
mkdir -p "$dest"
for h in pre-commit pre-push; do
  if [ -f "$root/tools/git-hooks/$h" ]; then
    cp "$root/tools/git-hooks/$h" "$dest/$h" && chmod +x "$dest/$h"
    echo "hooks: installed $h"
  fi
done
