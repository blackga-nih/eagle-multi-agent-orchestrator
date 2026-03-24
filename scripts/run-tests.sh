#!/usr/bin/env bash
# Run the EAGLE test suite with AWS SSO login guard.
# Usage: bash scripts/run-tests.sh [pytest-args...]
# Example: bash scripts/run-tests.sh tests/test_document_binary_endpoints.py -v

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVER_DIR="$(cd "$SCRIPT_DIR/../server" && pwd)"

# ── Ensure SSO session is valid ──────────────────────────────────────
echo "=== Checking AWS SSO session ==="
python3 "$SCRIPT_DIR/ensure_sso.py" eagle

# ── Lint checks ──────────────────────────────────────────────────────
echo ""
echo "=== Ruff lint ==="
cd "$SERVER_DIR"
python -m ruff check app/

echo ""
echo "=== TypeScript check ==="
cd "$SERVER_DIR/../client"
npx tsc --noEmit

# ── Pytest ───────────────────────────────────────────────────────────
echo ""
echo "=== Pytest ==="
cd "$SERVER_DIR"
python -m pytest "${@:-tests/ -v}"
