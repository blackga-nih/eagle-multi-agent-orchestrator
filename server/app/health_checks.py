"""Health check helpers for dependency diagnostics."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

import boto3
from botocore.config import Config


@lru_cache(maxsize=1)
def _health_cfg() -> Config:
    return Config(connect_timeout=1, read_timeout=1, retries={"max_attempts": 1})


@lru_cache(maxsize=1)
def _health_dynamodb():
    return boto3.client(
        "dynamodb",
        region_name=os.getenv("AWS_REGION", "us-east-1"),
        config=_health_cfg(),
    )


@lru_cache(maxsize=1)
def _health_s3():
    return boto3.client(
        "s3",
        region_name=os.getenv("AWS_REGION", "us-east-1"),
        config=_health_cfg(),
    )


def check_knowledge_base_health() -> dict[str, Any]:
    """Return KB dependency health for metadata table (DynamoDB) and docs bucket (S3)."""
    metadata_table = os.getenv("METADATA_TABLE", "eagle-document-metadata-dev")
    document_bucket = os.getenv("DOCUMENT_BUCKET", os.getenv("S3_BUCKET", ""))

    kb_status: dict[str, Any] = {
        "metadata_table": {"ok": False, "table": metadata_table},
        "document_bucket": {"ok": False, "bucket": document_bucket},
    }

    try:
        _health_dynamodb().describe_table(TableName=metadata_table)
        kb_status["metadata_table"]["ok"] = True
    except Exception as exc:
        kb_status["metadata_table"]["error"] = str(exc)

    if not document_bucket:
        kb_status["document_bucket"]["error"] = (
            "DOCUMENT_BUCKET or S3_BUCKET is not configured"
        )
        return kb_status

    try:
        _health_s3().head_bucket(Bucket=document_bucket)
        kb_status["document_bucket"]["ok"] = True
    except Exception as exc:
        kb_status["document_bucket"]["error"] = str(exc)

    return kb_status
