#!/usr/bin/env bash
#
# Stop Dispatcher — Routes to domain handlers based on changed files.
# Demonstrates the Dispatcher Routing pattern (TAC hooks-architecture.md).
#
# This is the single entry point for all Stop hooks. It reads git diff
# to determine which domain handlers to invoke. Each handler owns one
# concern and runs independently.
#
# Configure in settings.json:
# {
#   "hooks": {
#     "Stop": [
#       {
#         "matcher": "",
#         "hooks": [{
#           "type": "command",
#           "command": "bash .claude/hooks/stop_dispatcher.sh"
#         }]
#       }
#     ]
#   }
# }

set -euo pipefail

# ── Guard: prevent recursive execution ─────────────────
if [ -n "${STOP_HOOK_ACTIVE:-}" ]; then
    exit 0
fi
export STOP_HOOK_ACTIVE=1

HOOKS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHANGED_FILES=$(git diff --name-only HEAD 2>/dev/null || echo "")

echo "[stop-dispatcher] Checking changed files..."

# ── Route to domain handlers ───────────────────────────
HANDLERS_RUN=0

# Always run lint on Python changes
if echo "$CHANGED_FILES" | grep -q '\.py$'; then
    echo "[stop-dispatcher] Python changes detected -> running lint"
    bash "$HOOKS_DIR/stop_lint.sh" || echo "[stop-dispatcher] lint handler returned non-zero (non-fatal)"
    HANDLERS_RUN=$((HANDLERS_RUN + 1))
fi

# Run tests if test files changed
if echo "$CHANGED_FILES" | grep -q 'test_'; then
    echo "[stop-dispatcher] Test files changed -> running test validation"
    bash "$HOOKS_DIR/stop_test.sh" || echo "[stop-dispatcher] test handler returned non-zero (non-fatal)"
    HANDLERS_RUN=$((HANDLERS_RUN + 1))
fi

# Update expertise if expertise.md changed
if echo "$CHANGED_FILES" | grep -q 'expertise\.md'; then
    echo "[stop-dispatcher] Expertise file changed -> running expertise sync"
    bash "$HOOKS_DIR/stop_expertise.sh" 2>/dev/null || echo "[stop-dispatcher] expertise handler not found (skipped)"
    HANDLERS_RUN=$((HANDLERS_RUN + 1))
fi

# Append to session memory (always)
bash "$HOOKS_DIR/stop_memory.sh" 2>/dev/null || true
HANDLERS_RUN=$((HANDLERS_RUN + 1))

echo "[stop-dispatcher] Complete: $HANDLERS_RUN handlers executed"
exit 0
