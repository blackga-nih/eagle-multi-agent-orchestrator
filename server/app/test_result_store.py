"""
Test Result Store — DynamoDB persistence for pytest run results.

Uses the shared `eagle` single-table with PK/SK patterns:
  - Run summary:  PK=TESTRUN#system  SK=RUN#{iso_timestamp}
  - Test result:  PK=TESTRUN#RUN#{run_id}  SK=RESULT#{nodeid}

Non-fatal: all writes are best-effort so test runs never fail due to persistence.
"""
import os
import time
import logging
from datetime import datetime
from typing import Any, Dict, List
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

logger = logging.getLogger("eagle.test_results")

TABLE_NAME = os.getenv("EAGLE_SESSIONS_TABLE", "eagle")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

_dynamodb = None


def _get_dynamodb():
    global _dynamodb
    if _dynamodb is None:
        _dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
    return _dynamodb


def _get_table():
    return _get_dynamodb().Table(TABLE_NAME)


def _decimal_safe(obj):
    """Convert floats to Decimal for DynamoDB."""
    if isinstance(obj, float):
        return Decimal(str(round(obj, 6)))
    if isinstance(obj, dict):
        return {k: _decimal_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_decimal_safe(i) for i in obj]
    return obj


# ── Write Operations ────────────────────────────────────────────────


def save_test_run(run_id: str, summary: Dict[str, Any]) -> bool:
    """Save a test run summary to DynamoDB.

    PK: TESTRUN#system
    SK: RUN#{run_id}
    """
    try:
        table = _get_table()
        item = _decimal_safe({
            "PK": "TESTRUN#system",
            "SK": f"RUN#{run_id}",
            "run_id": run_id,
            "timestamp": summary.get("timestamp", datetime.utcnow().isoformat()),
            "total": summary.get("total", 0),
            "passed": summary.get("passed", 0),
            "failed": summary.get("failed", 0),
            "skipped": summary.get("skipped", 0),
            "errors": summary.get("errors", 0),
            "duration_s": summary.get("duration_s", 0),
            "pass_rate": summary.get("pass_rate", 0),
            "model": summary.get("model", "unknown"),
            "trigger": summary.get("trigger", "manual"),
            "hostname": summary.get("hostname", "unknown"),
            "ttl": int(time.time()) + 90 * 86400,  # 90-day TTL
        })
        table.put_item(Item=item)
        logger.info("Saved test run %s: %d passed, %d failed", run_id, summary.get("passed", 0), summary.get("failed", 0))
        return True
    except (ClientError, Exception) as e:
        logger.warning("Failed to save test run %s: %s", run_id, e)
        return False


def save_test_result(run_id: str, nodeid: str, result: Dict[str, Any]) -> bool:
    """Save an individual test result.

    PK: TESTRUN#RUN#{run_id}
    SK: RESULT#{nodeid}
    """
    try:
        table = _get_table()
        # Truncate long error messages to stay under 400KB item limit
        error_msg = result.get("error", "")
        if len(error_msg) > 2000:
            error_msg = error_msg[:2000] + "... [truncated]"

        item = _decimal_safe({
            "PK": f"TESTRUN#RUN#{run_id}",
            "SK": f"RESULT#{nodeid}",
            "run_id": run_id,
            "nodeid": nodeid,
            "test_file": result.get("test_file", ""),
            "test_name": result.get("test_name", ""),
            "status": result.get("status", "unknown"),
            "duration_s": result.get("duration_s", 0),
            "error": error_msg,
            "ttl": int(time.time()) + 90 * 86400,
        })
        table.put_item(Item=item)
        return True
    except (ClientError, Exception) as e:
        logger.warning("Failed to save test result %s/%s: %s", run_id, nodeid, e)
        return False


# ── Read Operations ─────────────────────────────────────────────────


def list_test_runs(limit: int = 20) -> List[Dict[str, Any]]:
    """List recent test runs, newest first."""
    try:
        table = _get_table()
        resp = table.query(
            KeyConditionExpression=Key("PK").eq("TESTRUN#system"),
            ScanIndexForward=False,  # newest first
            Limit=limit,
        )
        runs = []
        for item in resp.get("Items", []):
            runs.append({
                "run_id": item.get("run_id", ""),
                "timestamp": item.get("timestamp", ""),
                "total": int(item.get("total", 0)),
                "passed": int(item.get("passed", 0)),
                "failed": int(item.get("failed", 0)),
                "skipped": int(item.get("skipped", 0)),
                "errors": int(item.get("errors", 0)),
                "duration_s": float(item.get("duration_s", 0)),
                "pass_rate": float(item.get("pass_rate", 0)),
                "model": item.get("model", "unknown"),
                "trigger": item.get("trigger", "manual"),
            })
        return runs
    except (ClientError, Exception) as e:
        logger.warning("Failed to list test runs: %s", e)
        return []


def get_test_run_results(run_id: str) -> List[Dict[str, Any]]:
    """Get all individual test results for a specific run."""
    try:
        table = _get_table()
        resp = table.query(
            KeyConditionExpression=(
                Key("PK").eq(f"TESTRUN#RUN#{run_id}") &
                Key("SK").begins_with("RESULT#")
            ),
        )
        results = []
        for item in resp.get("Items", []):
            results.append({
                "nodeid": item.get("nodeid", ""),
                "test_file": item.get("test_file", ""),
                "test_name": item.get("test_name", ""),
                "status": item.get("status", "unknown"),
                "duration_s": float(item.get("duration_s", 0)),
                "error": item.get("error", ""),
            })
        return sorted(results, key=lambda r: r["nodeid"])
    except (ClientError, Exception) as e:
        logger.warning("Failed to get test run results for %s: %s", run_id, e)
        return []
