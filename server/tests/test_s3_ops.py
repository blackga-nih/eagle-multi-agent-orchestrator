"""
S3 Document Operations Integration Tests

Tests the s3_document_ops tool handler in agentic_service.py directly,
then confirms via boto3.  Covers SDK eval test 16 (s3_document_ops tool dispatch)
from the UI/service integration angle.

Scope:
  - write  → object appears in S3 under eagle/{tenant}/{user}/
  - list   → returns file_count and finds the written key
  - read   → content round-trips correctly
  - multi-tenant isolation: two tenants cannot read each other's keys
  - boto3  → head_object confirms object exists and has correct size
  - cleanup: deletes test objects after each test

Requirements:
  - S3_BUCKET env var pointing to the dev-account bucket
    (NEVER eagle-documents-695681773636-dev — that is the client account)
  - AWS credentials for account 274487662938

Skip with: SKIP_INTEGRATION_TESTS=true pytest
       OR: S3_BUCKET unset (tests auto-skip when bucket is empty)
Run with:  pytest server/tests/test_s3_ops.py -v
"""

import json
import os
import sys
import uuid
import pytest
import boto3
from botocore.exceptions import ClientError

# ── Path setup ────────────────────────────────────────────────────────
_server_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, _server_dir)
sys.path.insert(0, os.path.join(_server_dir, "app"))

from agentic_service import execute_tool

# ── Skip markers ──────────────────────────────────────────────────────
BUCKET = os.environ.get("S3_BUCKET", "")

skip_integration = pytest.mark.skipif(
    os.environ.get("SKIP_INTEGRATION_TESTS", "").lower() == "true",
    reason="SKIP_INTEGRATION_TESTS=true",
)
skip_no_bucket = pytest.mark.skipif(
    not BUCKET,
    reason="S3_BUCKET env var not set — skipping S3 integration tests",
)

# ── Constants ─────────────────────────────────────────────────────────
# execute_tool uses _extract_tenant_id → "demo-tenant" and _extract_user_id → "demo-user"
TENANT_PREFIX = "eagle/demo-tenant/demo-user/"
SESSION_ID    = "test-s3-session-001"


def _test_key(suffix: str = "") -> str:
    return f"test_{uuid.uuid4().hex[:8]}{suffix}.md"


def _s3_cleanup(bucket: str, full_key: str):
    """Best-effort S3 object deletion for test cleanup."""
    try:
        boto3.client("s3", region_name="us-east-1").delete_object(
            Bucket=bucket, Key=full_key
        )
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════
# 1. Write → list → read round-trip
# ═══════════════════════════════════════════════════════════════════

@skip_integration
@skip_no_bucket
def test_s3_write_returns_success():
    """write operation returns status=success and echoes the full S3 key."""
    key = _test_key()
    content = f"# S3 Write Test\nGenerated for integration test — key={key}"

    result = json.loads(execute_tool("s3_document_ops", {
        "operation": "write",
        "key": key,
        "content": content,
    }, SESSION_ID))

    full_key = result.get("key", "")
    try:
        assert result.get("status") == "success", f"Unexpected result: {result}"
        assert full_key.startswith(TENANT_PREFIX), (
            f"Key {full_key!r} should be under {TENANT_PREFIX!r}"
        )
        assert result.get("size_bytes", 0) > 0
    finally:
        _s3_cleanup(BUCKET, full_key)


@skip_integration
@skip_no_bucket
def test_s3_write_then_list_finds_key():
    """Written key appears in the list response."""
    key = _test_key()
    content = "List test document content."

    write_result = json.loads(execute_tool("s3_document_ops", {
        "operation": "write",
        "key": key,
        "content": content,
    }, SESSION_ID))
    full_key = write_result.get("key", "")

    try:
        list_result = json.loads(execute_tool("s3_document_ops", {
            "operation": "list",
        }, SESSION_ID))

        assert "error" not in list_result, f"list error: {list_result}"
        file_keys = [f["key"] for f in list_result.get("files", [])]
        assert any(key in k for k in file_keys), (
            f"{key!r} not found in listed keys: {file_keys}"
        )
        assert list_result.get("file_count", 0) >= 1
    finally:
        _s3_cleanup(BUCKET, full_key)


@skip_integration
@skip_no_bucket
def test_s3_write_then_read_content_match():
    """Content written to S3 is returned verbatim on read."""
    key = _test_key()
    content = f"# Read Test\nUnique marker: {uuid.uuid4().hex}"

    write_result = json.loads(execute_tool("s3_document_ops", {
        "operation": "write",
        "key": key,
        "content": content,
    }, SESSION_ID))
    full_key = write_result.get("key", "")

    try:
        read_result = json.loads(execute_tool("s3_document_ops", {
            "operation": "read",
            "key": key,
        }, SESSION_ID))

        assert "error" not in read_result, f"read error: {read_result}"
        assert content in read_result.get("content", ""), (
            "Written content not found in read response"
        )
        assert read_result.get("size_bytes", 0) > 0
    finally:
        _s3_cleanup(BUCKET, full_key)


# ═══════════════════════════════════════════════════════════════════
# 2. boto3 confirmation — head_object verifies object exists in S3
# ═══════════════════════════════════════════════════════════════════

@skip_integration
@skip_no_bucket
def test_s3_write_boto3_confirm():
    """boto3 head_object confirms the written object is in S3 with correct size."""
    key = _test_key()
    content = "boto3 confirmation test content — must be unique: " + uuid.uuid4().hex

    write_result = json.loads(execute_tool("s3_document_ops", {
        "operation": "write",
        "key": key,
        "content": content,
    }, SESSION_ID))
    full_key = write_result.get("key", "")

    try:
        assert write_result.get("status") == "success"
        s3 = boto3.client("s3", region_name="us-east-1")
        head = s3.head_object(Bucket=BUCKET, Key=full_key)
        assert head["ContentLength"] == len(content.encode("utf-8")), (
            f"ContentLength mismatch: S3={head['ContentLength']}, "
            f"expected={len(content.encode('utf-8'))}"
        )
    finally:
        _s3_cleanup(BUCKET, full_key)


# ═══════════════════════════════════════════════════════════════════
# 3. Multi-tenant path isolation
# ═══════════════════════════════════════════════════════════════════

@skip_integration
@skip_no_bucket
def test_s3_key_always_scoped_to_tenant_prefix():
    """All keys are prefixed with eagle/{tenant}/{user}/ — never bare."""
    key = "bare-key-no-prefix.md"
    content = "Isolation test"

    write_result = json.loads(execute_tool("s3_document_ops", {
        "operation": "write",
        "key": key,
        "content": content,
    }, SESSION_ID))
    full_key = write_result.get("key", "")

    try:
        assert full_key.startswith(TENANT_PREFIX), (
            f"Key {full_key!r} missing tenant prefix {TENANT_PREFIX!r}"
        )
        # Raw bare key should NOT exist as a top-level S3 object
        s3 = boto3.client("s3", region_name="us-east-1")
        with pytest.raises(ClientError) as exc:
            s3.head_object(Bucket=BUCKET, Key=key)  # bare key — should not exist
        assert exc.value.response["Error"]["Code"] in ("404", "NoSuchKey")
    finally:
        _s3_cleanup(BUCKET, full_key)


# ═══════════════════════════════════════════════════════════════════
# 4. Error handling
# ═══════════════════════════════════════════════════════════════════

@skip_integration
@skip_no_bucket
def test_s3_read_missing_key_returns_error():
    """Reading a non-existent key returns an error dict, not an exception."""
    result = json.loads(execute_tool("s3_document_ops", {
        "operation": "read",
        "key": "this-key-does-not-exist-99999.md",
    }, SESSION_ID))
    assert "error" in result, f"Expected error key in result: {result}"


@skip_integration
@skip_no_bucket
def test_s3_write_missing_key_returns_error():
    """Write with empty key returns an error dict."""
    result = json.loads(execute_tool("s3_document_ops", {
        "operation": "write",
        "key": "",
        "content": "some content",
    }, SESSION_ID))
    assert "error" in result, f"Expected error key in result: {result}"


@skip_integration
@skip_no_bucket
def test_s3_write_missing_content_returns_error():
    """Write with empty content returns an error dict."""
    result = json.loads(execute_tool("s3_document_ops", {
        "operation": "write",
        "key": "test-empty-content.md",
        "content": "",
    }, SESSION_ID))
    assert "error" in result, f"Expected error key in result: {result}"


@skip_integration
@skip_no_bucket
def test_s3_unknown_operation_returns_error():
    """Unknown operation returns an error dict, not an exception."""
    result = json.loads(execute_tool("s3_document_ops", {
        "operation": "delete",  # not supported
        "key": "any.md",
    }, SESSION_ID))
    assert "error" in result, f"Expected error key in result: {result}"
