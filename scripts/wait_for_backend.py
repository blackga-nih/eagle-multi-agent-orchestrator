#!/usr/bin/env python
"""Wait for the local backend to become healthy.

Polls http://localhost:8000/health every 2 seconds for up to 60 seconds.
Exits 0 when the backend responds, exits 1 on timeout.
"""

import sys
import time
import urllib.request
import urllib.error

URL = "http://localhost:8000/api/health"
MAX_ATTEMPTS = 30
INTERVAL = 2

print(f"Waiting for backend at {URL} ...")
for i in range(MAX_ATTEMPTS):
    try:
        resp = urllib.request.urlopen(URL, timeout=3)
        print(f"  Backend ready (HTTP {resp.status})")
        sys.exit(0)
    except Exception as e:
        print(f"  [{i + 1}/{MAX_ATTEMPTS}] not ready — {e}")
        time.sleep(INTERVAL)

print(f"ERROR: backend did not become ready after {MAX_ATTEMPTS * INTERVAL}s")
print("Check logs with: docker compose -f deployment/docker-compose.dev.yml logs backend")
sys.exit(1)
