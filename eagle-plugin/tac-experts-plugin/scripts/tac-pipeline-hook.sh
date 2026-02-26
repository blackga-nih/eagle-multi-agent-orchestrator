#!/usr/bin/env bash
# TAC Pipeline Hook
#
# Thin wrapper called by the youtube-tac-extract pipeline (Step 5.5)
# after repos are cloned/updated. Calls archive-repo.py to update
# the plugin catalog.
#
# Usage:
#   ./scripts/tac-pipeline-hook.sh /path/to/repo [lesson_number]
#
# Called by: consulting-co/.claude/commands/agp/youtube-tac-extract.md
# Calls:    scripts/archive-repo.py

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_DIR="$(dirname "$SCRIPT_DIR")"
ARCHIVE_SCRIPT="$SCRIPT_DIR/archive-repo.py"

REPO_PATH="${1:?Usage: tac-pipeline-hook.sh /path/to/repo [lesson_number]}"
LESSON="${2:-auto}"

if [ ! -d "$REPO_PATH" ]; then
    echo "[tac-pipeline-hook] Error: $REPO_PATH does not exist"
    exit 1
fi

if [ ! -f "$ARCHIVE_SCRIPT" ]; then
    echo "[tac-pipeline-hook] Error: archive-repo.py not found at $ARCHIVE_SCRIPT"
    exit 1
fi

REPO_NAME=$(basename "$REPO_PATH")
echo "[tac-pipeline-hook] Archiving: $REPO_NAME (lesson: $LESSON)"

python "$ARCHIVE_SCRIPT" "$REPO_PATH" --lesson "$LESSON"

EXIT_CODE=$?
if [ $EXIT_CODE -eq 0 ]; then
    echo "[tac-pipeline-hook] Success: $REPO_NAME archived to plugin catalog"
else
    echo "[tac-pipeline-hook] Warning: archive-repo.py exited with code $EXIT_CODE"
fi

exit $EXIT_CODE
