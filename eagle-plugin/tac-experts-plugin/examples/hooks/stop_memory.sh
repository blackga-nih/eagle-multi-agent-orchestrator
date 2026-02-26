#!/usr/bin/env bash
#
# Stop Domain Handler: Turn-by-Turn Memory
# Called by stop_dispatcher.sh on every turn.
# Appends a timestamped diff summary to session memory.
#
# This creates a running log of what the agent did each turn,
# useful for session continuity and debugging.

MEMORY_FILE=".claude/session-memory.md"

# Create memory file if it doesn't exist
if [ ! -f "$MEMORY_FILE" ]; then
    mkdir -p "$(dirname "$MEMORY_FILE")"
    echo "# Session Memory" > "$MEMORY_FILE"
    echo "" >> "$MEMORY_FILE"
fi

# Append turn summary
echo "## Turn $(date +%H:%M:%S)" >> "$MEMORY_FILE"
DIFF_STAT=$(git diff --stat HEAD 2>/dev/null || echo "no git changes")
echo "$DIFF_STAT" >> "$MEMORY_FILE"
echo "" >> "$MEMORY_FILE"

echo "[stop-memory] Turn recorded"
exit 0
