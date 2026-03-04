"""
Pytest conftest — auto-persist test results to DynamoDB.

Uses pytest hooks to capture per-test outcomes and write a run summary
after the session finishes. Persistence is non-fatal: if DDB is
unreachable, tests still run normally.

Enable/disable via environment variable:
  EAGLE_PERSIST_TEST_RESULTS=true   (default: true)
  EAGLE_PERSIST_TEST_RESULTS=false  (skip persistence)
"""
import os
import sys
import socket
import time
from datetime import datetime

import pytest

# Ensure server/ is on the path for app.* imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_PERSIST = os.getenv("EAGLE_PERSIST_TEST_RESULTS", "true").lower() == "true"

# Collected results during the session
_results: dict = {}
_session_start: float = 0.0


def pytest_sessionstart(session):
    """Record session start time."""
    global _session_start
    _session_start = time.time()


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Capture test outcome after each test phase (setup/call/teardown)."""
    outcome = yield
    report = outcome.get_result()

    # Only record the 'call' phase (not setup/teardown)
    if report.when != "call":
        return

    nodeid = report.nodeid
    parts = nodeid.split("::")
    test_file = parts[0].split("/")[-1] if parts else ""
    test_name = parts[-1] if parts else nodeid

    if report.passed:
        status = "passed"
    elif report.failed:
        status = "failed"
    elif report.skipped:
        status = "skipped"
    else:
        status = "unknown"

    error_msg = ""
    if report.failed and report.longreprtext:
        error_msg = report.longreprtext

    _results[nodeid] = {
        "test_file": test_file,
        "test_name": test_name,
        "status": status,
        "duration_s": round(report.duration, 3),
        "error": error_msg,
    }


def pytest_sessionfinish(session, exitstatus):
    """Write run summary + individual results to DynamoDB."""
    if not _PERSIST:
        return

    if not _results:
        return

    duration_s = round(time.time() - _session_start, 2)
    timestamp = datetime.utcnow().isoformat() + "Z"
    run_id = timestamp.replace(":", "-").replace(".", "-")

    passed = sum(1 for r in _results.values() if r["status"] == "passed")
    failed = sum(1 for r in _results.values() if r["status"] == "failed")
    skipped = sum(1 for r in _results.values() if r["status"] == "skipped")
    errors = sum(1 for r in _results.values() if r["status"] == "unknown")
    total = len(_results)
    pass_rate = round((passed / total) * 100, 1) if total > 0 else 0

    model = os.getenv("EAGLE_BEDROCK_MODEL_ID", os.getenv("STRANDS_MODEL_ID", "unknown"))

    summary = {
        "timestamp": timestamp,
        "total": total,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "errors": errors,
        "duration_s": duration_s,
        "pass_rate": pass_rate,
        "model": model,
        "trigger": "pytest",
        "hostname": socket.gethostname(),
    }

    try:
        from app.test_result_store import save_test_run, save_test_result

        save_test_run(run_id, summary)
        for nodeid, result in _results.items():
            save_test_result(run_id, nodeid, result)

        print(f"\n[EAGLE] Test results persisted to DynamoDB: run_id={run_id} ({passed}/{total} passed)")
    except Exception as e:
        print(f"\n[EAGLE] Failed to persist test results (non-fatal): {e}")
