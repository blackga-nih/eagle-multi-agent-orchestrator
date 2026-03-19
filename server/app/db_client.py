"""
Centralized AWS client management for EAGLE.

All store modules should import from here instead of creating their own clients.
This eliminates ~400 lines of duplicated singleton patterns across 20+ files.

Created: 2026-03-19 (Phase 2 refactor)

Usage:
    from app.db_client import get_table, get_s3, get_logs, item_to_dict, now_iso
"""
import os
from datetime import datetime, timezone
from decimal import Decimal
from functools import lru_cache
from typing import Any

import boto3

# ── Configuration ────────────────────────────────────────────────────────────
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
EAGLE_TABLE_NAME = os.getenv("EAGLE_SESSIONS_TABLE", "eagle")
EAGLE_S3_BUCKET = os.getenv("EAGLE_S3_BUCKET", "eagle-documents")


# ── AWS Clients (cached singletons) ──────────────────────────────────────────

@lru_cache(maxsize=1)
def get_dynamodb():
    """Get shared DynamoDB resource. Cached for connection reuse."""
    return boto3.resource("dynamodb", region_name=AWS_REGION)


@lru_cache(maxsize=1)
def get_s3():
    """Get shared S3 client. Cached for connection reuse."""
    return boto3.client("s3", region_name=AWS_REGION)


@lru_cache(maxsize=1)
def get_logs():
    """Get shared CloudWatch Logs client. Cached for connection reuse."""
    return boto3.client("logs", region_name=AWS_REGION)


@lru_cache(maxsize=1)
def get_table():
    """Get the main EAGLE DynamoDB table."""
    return get_dynamodb().Table(EAGLE_TABLE_NAME)


# ── Utility Functions ────────────────────────────────────────────────────────

def item_to_dict(item: dict) -> dict:
    """
    Convert DynamoDB item to plain dict, handling Decimal types.

    DynamoDB returns numbers as Decimal objects which aren't JSON serializable.
    This recursively converts them to int or float as appropriate.
    """
    def convert(obj: Any) -> Any:
        if isinstance(obj, Decimal):
            # Convert to int if it's a whole number, otherwise float
            return int(obj) if obj % 1 == 0 else float(obj)
        elif isinstance(obj, dict):
            return {k: convert(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [convert(i) for i in obj]
        return obj

    return convert(item)


def now_iso() -> str:
    """Return current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat()


def ttl_timestamp(days: int) -> int:
    """
    Return a TTL timestamp (seconds since epoch) for DynamoDB TTL attribute.

    Args:
        days: Number of days from now until expiration

    Returns:
        Unix timestamp in seconds
    """
    from datetime import timedelta
    return int((datetime.now(timezone.utc) + timedelta(days=days)).timestamp())
