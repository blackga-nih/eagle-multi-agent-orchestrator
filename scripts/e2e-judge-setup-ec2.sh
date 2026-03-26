#!/usr/bin/env bash
# One-time setup for running the E2E judge pipeline on the EC2 dev box.
# Installs Playwright, Chromium, and Python dependencies.
#
# Usage:
#   chmod +x scripts/e2e-judge-setup-ec2.sh
#   ./scripts/e2e-judge-setup-ec2.sh

set -euo pipefail

echo "=== E2E Judge — EC2 Setup ==="

# Python dependencies
echo "Installing Python dependencies..."
pip install --upgrade playwright boto3

# Chromium + system dependencies (needed for headless rendering on Linux)
echo "Installing Chromium browser..."
playwright install chromium --with-deps

# Verify
echo ""
echo "Verifying installation..."
python -c "from playwright.sync_api import sync_playwright; print('Playwright OK')"
python -c "import boto3; print('boto3 OK')"

echo ""
echo "=== Setup complete ==="
echo ""
echo "Run tests with:"
echo "  cd server/"
echo "  python -m tests.e2e_judge_orchestrator \\"
echo "    --base-url http://YOUR-ALB-URL \\"
echo "    --auth-email testuser@example.com \\"
echo "    --auth-password 'EagleTest2024!' \\"
echo "    --journeys all"
