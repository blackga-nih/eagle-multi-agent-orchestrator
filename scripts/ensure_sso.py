"""Ensure AWS SSO session is valid with >= 10 min remaining.

Usage: python3 scripts/ensure_sso.py [PROFILE]
Exit 0 = ready, Exit 1 = login failed.
Called by: just ensure-sso
"""
import glob
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

MIN_REMAINING_SEC = 600  # 10 minutes
profile = sys.argv[1] if len(sys.argv) > 1 else "eagle"
os.environ["AWS_PROFILE"] = profile


def check_token_expiry():
    """Return seconds remaining on the newest SSO cache token, or -1."""
    cache_dir = Path.home() / ".aws" / "sso" / "cache"
    if not cache_dir.is_dir():
        return -1
    tokens = sorted(cache_dir.glob("*.json"), key=os.path.getmtime, reverse=True)
    for token_path in tokens:
        try:
            data = json.loads(token_path.read_text())
            expires_at = data.get("expiresAt", "")
            if not expires_at:
                continue
            exp_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            return (exp_dt - datetime.now(timezone.utc)).total_seconds()
        except Exception:
            continue
    return -1


def sso_login():
    """Run aws sso login and return True on success."""
    print(f"  Running: aws sso login --profile {profile}")
    rc = subprocess.call(["aws", "sso", "login", "--profile", profile])
    return rc == 0


def verify_sts():
    """Quick STS identity check."""
    return subprocess.call(
        ["aws", "sts", "get-caller-identity"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ) == 0


remaining = check_token_expiry()

if remaining >= MIN_REMAINING_SEC:
    mins = int(remaining // 60)
    print(f"[OK] AWS SSO active ({profile}) - {mins}m remaining")
    sys.exit(0)

if remaining > 0:
    print(f"[WARN] SSO token expires in {int(remaining)}s (< 10 min) - refreshing...")
elif remaining == -1:
    print("[WARN] No SSO token found - logging in...")
else:
    print("[WARN] SSO token expired - logging in...")

if not sso_login():
    print("ERROR: aws sso login failed.")
    sys.exit(1)

if not verify_sts():
    print("ERROR: SSO login completed but sts check failed.")
    sys.exit(1)

print(f"[OK] AWS SSO active ({profile})")
