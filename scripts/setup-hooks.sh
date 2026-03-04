#!/usr/bin/env bash
# scripts/setup-hooks.sh
# Copies project git hooks from scripts/hooks/ into .git/hooks/ and makes them executable.
# Run once after cloning: bash scripts/setup-hooks.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
HOOKS_SRC="$SCRIPT_DIR/hooks"
HOOKS_DEST="$REPO_ROOT/.git/hooks"

if [ ! -d "$HOOKS_SRC" ]; then
  echo "No hooks directory found at $HOOKS_SRC" >&2
  exit 1
fi

if [ ! -d "$HOOKS_DEST" ]; then
  echo "Not inside a git repository (missing .git/hooks/)" >&2
  exit 1
fi

echo "Installing git hooks from scripts/hooks/ → .git/hooks/"

for hook in "$HOOKS_SRC"/*; do
  name="$(basename "$hook")"
  dest="$HOOKS_DEST/$name"
  cp "$hook" "$dest"
  chmod +x "$dest"
  echo "  ✓ $name"
done

echo "Done. $(ls "$HOOKS_SRC" | wc -l | tr -d ' ') hook(s) installed."
