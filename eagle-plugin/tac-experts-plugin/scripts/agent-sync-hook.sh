#!/usr/bin/env bash
# Agent Sync Hook — PostToolUse hook for automatic Obsidian sync
#
# Watches for new/modified .claude/agents/*.md files and syncs them
# to AI-Agent-KB with MTG card assignment.
#
# Configure in settings.json:
# {
#   "hooks": {
#     "PostToolUse": [
#       {
#         "matcher": "Write|Edit",
#         "hooks": [
#           {
#             "type": "command",
#             "command": "bash /path/to/tac-experts-plugin/scripts/agent-sync-hook.sh"
#           }
#         ]
#       }
#     ]
#   }
# }
#
# Reads tool_input from stdin (JSON) and checks if the file path
# matches an agent, skill, or hook pattern.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYNC_SCRIPT="$SCRIPT_DIR/sync-to-obsidian.py"
KB_ROOT="C:/Users/gblac/OneDrive/Desktop/obsidian/Gbautomation/AI-Agent-KB"

# Read hook event from stdin
INPUT=$(cat)

# Extract file_path from the tool input JSON
# PostToolUse events include tool_input with file_path for Write/Edit
FILE_PATH=$(echo "$INPUT" | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    # Navigate to the file_path in tool_input
    tool_input = data.get('tool_input', data.get('input', {}))
    if isinstance(tool_input, str):
        import json as j
        tool_input = j.loads(tool_input)
    path = tool_input.get('file_path', tool_input.get('path', ''))
    print(path)
except Exception:
    print('')
" 2>/dev/null || echo "")

if [ -z "$FILE_PATH" ]; then
    exit 0  # No file path, nothing to sync
fi

# Normalize path separators
FILE_PATH=$(echo "$FILE_PATH" | sed 's|\\|/|g')

# Check if file matches sync patterns
SHOULD_SYNC=false
COMP_TYPE=""

case "$FILE_PATH" in
    */.claude/agents/*.md)
        SHOULD_SYNC=true
        COMP_TYPE="agent"
        ;;
    */.claude/commands/experts/*/*)
        SHOULD_SYNC=true
        COMP_TYPE="expert"
        ;;
    */skills/*/SKILL.md)
        SHOULD_SYNC=true
        COMP_TYPE="skill"
        ;;
    */.claude/hooks/*.py|*/.claude/hooks/*.sh)
        SHOULD_SYNC=true
        COMP_TYPE="hook"
        ;;
esac

if [ "$SHOULD_SYNC" = false ]; then
    exit 0  # Not a syncable file
fi

# Verify KB exists
if [ ! -d "$KB_ROOT" ]; then
    exit 0  # KB not available, skip silently
fi

# Verify sync script exists
if [ ! -f "$SYNC_SCRIPT" ]; then
    echo "[agent-sync-hook] Warning: sync-to-obsidian.py not found" >&2
    exit 0
fi

# Run sync (with --no-banners to avoid slow Scryfall calls during editing)
echo "[agent-sync-hook] Syncing $COMP_TYPE: $(basename "$FILE_PATH")" >&2
python "$SYNC_SCRIPT" "$FILE_PATH" --no-banners 2>&1 | while read -r line; do
    echo "[agent-sync-hook] $line" >&2
done

exit 0
