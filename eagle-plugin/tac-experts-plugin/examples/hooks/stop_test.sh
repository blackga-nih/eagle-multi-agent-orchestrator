#!/usr/bin/env bash
#
# Stop Domain Handler: Test Validation
# Called by stop_dispatcher.sh when test files have changed.
#
# Conventions (TAC hooks-architecture.md):
#   - Name: stop_{domain}.sh
#   - Single responsibility: validate changed test files
#   - Idempotent: safe to run multiple times
#   - Non-blocking: exit 0 even on non-critical failures
#   - Logs to stdout for agent visibility

set -euo pipefail

echo "[stop-test] Validating changed test files..."

# Find changed test files
CHANGED_TESTS=$(git diff --name-only HEAD 2>/dev/null | grep "test_" | grep '\.py$' | head -10)

if [ -z "$CHANGED_TESTS" ]; then
    echo "[stop-test] No test files in diff, skipping"
    exit 0
fi

PASS=0
FAIL=0

for test_file in $CHANGED_TESTS; do
    if [ ! -f "$test_file" ]; then
        echo "[stop-test] SKIP $test_file (not found)"
        continue
    fi

    # Phase 1: Syntax check (fast — catches parse errors)
    if python -c "import py_compile; py_compile.compile('$test_file', doraise=True)" 2>/dev/null; then
        echo "[stop-test] PASS syntax: $test_file"
    else
        echo "[stop-test] FAIL syntax: $test_file"
        FAIL=$((FAIL + 1))
        continue
    fi

    # Phase 2: Run the test (slower — catches logic errors)
    if python -m pytest "$test_file" -x -q --tb=short 2>/dev/null; then
        echo "[stop-test] PASS tests: $test_file"
        PASS=$((PASS + 1))
    else
        echo "[stop-test] FAIL tests: $test_file"
        FAIL=$((FAIL + 1))
    fi
done

echo "[stop-test] Results: $PASS passed, $FAIL failed"

# Non-blocking: report failures but don't block the agent
if [ "$FAIL" -gt 0 ]; then
    echo "[stop-test] WARNING: $FAIL test file(s) have issues"
fi

exit 0
