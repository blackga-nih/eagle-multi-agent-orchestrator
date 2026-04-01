"""Tests for AWS operations tool handlers — S3, DynamoDB, CloudWatch Logs."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import BotoCoreError, ClientError

import app.tools.aws_ops_tools as aot

TENANT = "test-tenant"
SESSION_ID = "test-tenant#standard#test-user#sess-001"


def _assert_keys(result: dict, *keys: str) -> None:
    for key in keys:
        assert key in result, f"Missing key '{key}' in {list(result.keys())}"


def _client_error(code: str = "AccessDenied", message: str = "denied") -> ClientError:
    return ClientError(
        {"Error": {"Code": code, "Message": message}}, "TestOp"
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_s3(monkeypatch):
    client = MagicMock()
    monkeypatch.setattr(aot, "get_s3", lambda: client)
    return client


@pytest.fixture()
def mock_ddb(monkeypatch):
    resource = MagicMock()
    monkeypatch.setattr(aot, "get_dynamodb", lambda: resource)
    return resource


@pytest.fixture()
def mock_logs(monkeypatch):
    client = MagicMock()
    monkeypatch.setattr(aot, "get_logs", lambda: client)
    return client


# ===========================================================================
# S3 Document Ops
# ===========================================================================


class TestS3DocumentOps:
    """Tests for exec_s3_document_ops — all 9 sub-operations."""

    # -- Happy paths --

    def test_list_returns_schema(self, mock_s3):
        mock_s3.list_objects_v2.return_value = {
            "Contents": [
                {
                    "Key": "eagle/test-tenant/test-user/docs/file.txt",
                    "Size": 42,
                    "LastModified": datetime(2026, 1, 1),
                }
            ]
        }
        result = aot.exec_s3_document_ops(
            {"operation": "list"}, TENANT, SESSION_ID
        )
        _assert_keys(result, "operation", "bucket", "prefix", "file_count", "files")
        assert result["operation"] == "list"
        assert result["file_count"] == 1
        assert result["files"][0]["size_bytes"] == 42

    def test_read_returns_schema(self, mock_s3):
        body = MagicMock()
        body.read.return_value = b"hello world"
        mock_s3.get_object.return_value = {
            "Body": body,
            "ContentType": "text/plain",
            "ContentLength": 11,
        }
        result = aot.exec_s3_document_ops(
            {"operation": "read", "key": "eagle/test-tenant/test-user/doc.txt"},
            TENANT,
            SESSION_ID,
        )
        _assert_keys(result, "operation", "key", "content_type", "size_bytes", "content")
        assert result["content"] == "hello world"

    def test_write_returns_schema(self, mock_s3):
        result = aot.exec_s3_document_ops(
            {"operation": "write", "key": "doc.txt", "content": "data"},
            TENANT,
            SESSION_ID,
        )
        _assert_keys(result, "operation", "key", "bucket", "size_bytes", "status")
        assert result["status"] == "success"
        assert result["size_bytes"] == len("data".encode("utf-8"))

    def test_delete_returns_schema(self, mock_s3):
        result = aot.exec_s3_document_ops(
            {"operation": "delete", "key": "doc.txt"}, TENANT, SESSION_ID
        )
        _assert_keys(result, "operation", "key", "bucket", "status")
        assert result["status"] == "success"

    def test_copy_returns_schema(self, mock_s3):
        result = aot.exec_s3_document_ops(
            {"operation": "copy", "key": "a.txt", "destination_key": "b.txt"},
            TENANT,
            SESSION_ID,
        )
        _assert_keys(result, "operation", "source_key", "destination_key", "bucket", "status")
        assert result["status"] == "success"

    def test_rename_returns_schema(self, mock_s3):
        result = aot.exec_s3_document_ops(
            {"operation": "rename", "key": "a.txt", "destination_key": "b.txt"},
            TENANT,
            SESSION_ID,
        )
        _assert_keys(result, "operation", "source_key", "destination_key", "bucket", "status")
        assert result["operation"] == "rename"
        # rename = copy + delete
        mock_s3.copy_object.assert_called_once()
        mock_s3.delete_object.assert_called_once()

    def test_exists_found_returns_schema(self, mock_s3):
        mock_s3.head_object.return_value = {
            "ContentLength": 100,
            "LastModified": datetime(2026, 3, 1),
            "ContentType": "application/pdf",
        }
        result = aot.exec_s3_document_ops(
            {"operation": "exists", "key": "doc.pdf"}, TENANT, SESSION_ID
        )
        _assert_keys(result, "operation", "key", "exists", "size_bytes", "content_type")
        assert result["exists"] is True
        assert result["size_bytes"] == 100

    def test_exists_not_found_returns_false(self, mock_s3):
        mock_s3.head_object.side_effect = _client_error("404", "Not Found")
        result = aot.exec_s3_document_ops(
            {"operation": "exists", "key": "nope.txt"}, TENANT, SESSION_ID
        )
        assert result["exists"] is False

    def test_presign_returns_schema(self, mock_s3):
        mock_s3.generate_presigned_url.return_value = "https://s3.example.com/signed"
        result = aot.exec_s3_document_ops(
            {"operation": "presign", "key": "doc.pdf", "expiry_seconds": 7200},
            TENANT,
            SESSION_ID,
        )
        _assert_keys(result, "operation", "key", "bucket", "url", "expires_in_seconds")
        assert result["url"] == "https://s3.example.com/signed"
        assert result["expires_in_seconds"] == 7200

    # -- Param validation --

    def test_read_missing_key(self, mock_s3):
        result = aot.exec_s3_document_ops(
            {"operation": "read"}, TENANT, SESSION_ID
        )
        assert "error" in result

    def test_write_missing_key(self, mock_s3):
        result = aot.exec_s3_document_ops(
            {"operation": "write", "content": "data"}, TENANT, SESSION_ID
        )
        assert "error" in result

    def test_write_missing_content(self, mock_s3):
        result = aot.exec_s3_document_ops(
            {"operation": "write", "key": "doc.txt"}, TENANT, SESSION_ID
        )
        assert "error" in result

    def test_delete_missing_key(self, mock_s3):
        result = aot.exec_s3_document_ops(
            {"operation": "delete"}, TENANT, SESSION_ID
        )
        assert "error" in result

    def test_copy_missing_source(self, mock_s3):
        result = aot.exec_s3_document_ops(
            {"operation": "copy", "destination_key": "b.txt"}, TENANT, SESSION_ID
        )
        assert "error" in result

    def test_copy_missing_dest(self, mock_s3):
        result = aot.exec_s3_document_ops(
            {"operation": "copy", "key": "a.txt"}, TENANT, SESSION_ID
        )
        assert "error" in result

    def test_rename_missing_source(self, mock_s3):
        result = aot.exec_s3_document_ops(
            {"operation": "rename", "destination_key": "b.txt"}, TENANT, SESSION_ID
        )
        assert "error" in result

    def test_rename_missing_dest(self, mock_s3):
        result = aot.exec_s3_document_ops(
            {"operation": "rename", "key": "a.txt"}, TENANT, SESSION_ID
        )
        assert "error" in result

    def test_presign_missing_key(self, mock_s3):
        result = aot.exec_s3_document_ops(
            {"operation": "presign"}, TENANT, SESSION_ID
        )
        assert "error" in result

    def test_unknown_operation_returns_error(self, mock_s3):
        result = aot.exec_s3_document_ops(
            {"operation": "purge"}, TENANT, SESSION_ID
        )
        assert "error" in result
        assert "purge" in result["error"]

    # -- AWS errors --

    def test_access_denied_returns_permission_error(self, mock_s3):
        mock_s3.list_objects_v2.side_effect = _client_error("AccessDenied", "No access")
        result = aot.exec_s3_document_ops(
            {"operation": "list"}, TENANT, SESSION_ID
        )
        _assert_keys(result, "error", "detail", "suggestion")
        assert "permission denied" in result["error"].lower()

    def test_no_such_key_returns_not_found(self, mock_s3):
        body = MagicMock()
        mock_s3.get_object.side_effect = _client_error("NoSuchKey", "Not found")
        result = aot.exec_s3_document_ops(
            {"operation": "read", "key": "eagle/test-tenant/test-user/gone.txt"},
            TENANT,
            SESSION_ID,
        )
        assert "error" in result
        assert "not found" in result["error"].lower()

    def test_no_such_bucket_returns_bucket_not_found(self, mock_s3):
        mock_s3.list_objects_v2.side_effect = _client_error(
            "NoSuchBucket", "Bucket gone"
        )
        result = aot.exec_s3_document_ops(
            {"operation": "list"}, TENANT, SESSION_ID
        )
        assert "error" in result
        assert "Bucket not found" in result["error"]

    def test_botocore_error_returns_connection_error(self, mock_s3):
        mock_s3.list_objects_v2.side_effect = BotoCoreError()
        result = aot.exec_s3_document_ops(
            {"operation": "list"}, TENANT, SESSION_ID
        )
        assert "error" in result
        assert "connection" in result["error"].lower()

    # -- Tenant scoping --

    def test_unscoped_key_gets_prefixed(self, mock_s3):
        body = MagicMock()
        body.read.return_value = b"data"
        mock_s3.get_object.return_value = {
            "Body": body,
            "ContentType": "text/plain",
            "ContentLength": 4,
        }
        result = aot.exec_s3_document_ops(
            {"operation": "read", "key": "docs/file.txt"}, TENANT, SESSION_ID
        )
        # Key should be auto-prefixed
        assert result["key"].startswith("eagle/test-tenant/test-user/")

    def test_already_scoped_key_not_double_prefixed(self, mock_s3):
        scoped_key = "eagle/test-tenant/test-user/docs/file.txt"
        body = MagicMock()
        body.read.return_value = b"data"
        mock_s3.get_object.return_value = {
            "Body": body,
            "ContentType": "text/plain",
            "ContentLength": 4,
        }
        result = aot.exec_s3_document_ops(
            {"operation": "read", "key": scoped_key}, TENANT, SESSION_ID
        )
        assert result["key"] == scoped_key


# ===========================================================================
# DynamoDB Intake
# ===========================================================================


class TestDynamoDBIntake:
    """Tests for exec_dynamodb_intake — all 9 sub-operations."""

    def _table(self, mock_ddb):
        table = MagicMock()
        mock_ddb.Table.return_value = table
        return table

    # -- Happy paths --

    def test_create_returns_schema(self, mock_ddb):
        table = self._table(mock_ddb)
        result = aot.exec_dynamodb_intake(
            {"operation": "create", "item_id": "i1", "data": {"title": "Test"}},
            TENANT,
        )
        _assert_keys(result, "operation", "item_id", "status", "item")
        assert result["operation"] == "create"
        assert result["status"] == "created"
        table.put_item.assert_called_once()

    def test_create_auto_generates_item_id(self, mock_ddb):
        self._table(mock_ddb)
        result = aot.exec_dynamodb_intake(
            {"operation": "create", "data": {"title": "Test"}}, TENANT
        )
        assert result["item_id"]  # Should be non-empty auto-generated
        assert len(result["item_id"]) == 8

    def test_read_returns_schema(self, mock_ddb):
        table = self._table(mock_ddb)
        table.get_item.return_value = {
            "Item": {"PK": f"INTAKE#{TENANT}", "SK": "INTAKE#i1", "title": "Test"}
        }
        result = aot.exec_dynamodb_intake(
            {"operation": "read", "item_id": "i1"}, TENANT
        )
        _assert_keys(result, "operation", "item")
        assert result["operation"] == "read"

    def test_update_returns_schema(self, mock_ddb):
        table = self._table(mock_ddb)
        result = aot.exec_dynamodb_intake(
            {"operation": "update", "item_id": "i1", "data": {"title": "Updated"}},
            TENANT,
        )
        _assert_keys(result, "operation", "item_id", "status", "fields_updated")
        assert result["status"] == "updated"
        assert "title" in result["fields_updated"]

    def test_list_returns_schema(self, mock_ddb):
        table = self._table(mock_ddb)
        table.query.return_value = {
            "Items": [{"PK": f"INTAKE#{TENANT}", "title": "A"}]
        }
        result = aot.exec_dynamodb_intake(
            {"operation": "list"}, TENANT
        )
        _assert_keys(result, "operation", "tenant_id", "count", "items")
        assert result["count"] == 1

    def test_delete_returns_schema(self, mock_ddb):
        table = self._table(mock_ddb)
        result = aot.exec_dynamodb_intake(
            {"operation": "delete", "item_id": "i1"}, TENANT
        )
        _assert_keys(result, "operation", "item_id", "status")
        assert result["status"] == "deleted"

    def test_count_returns_schema(self, mock_ddb):
        table = self._table(mock_ddb)
        table.query.return_value = {"Count": 5}
        result = aot.exec_dynamodb_intake(
            {"operation": "count"}, TENANT
        )
        _assert_keys(result, "operation", "tenant_id", "count")
        assert result["count"] == 5

    def test_batch_get_returns_schema(self, mock_ddb):
        mock_ddb.batch_get_item.return_value = {
            "Responses": {"eagle": [{"item_id": "i1"}, {"item_id": "i2"}]}
        }
        self._table(mock_ddb)
        result = aot.exec_dynamodb_intake(
            {"operation": "batch_get", "item_ids": "i1,i2"}, TENANT
        )
        _assert_keys(result, "operation", "requested", "found", "items")
        assert result["requested"] == 2
        assert result["found"] == 2

    def test_batch_write_returns_schema(self, mock_ddb):
        self._table(mock_ddb)
        result = aot.exec_dynamodb_intake(
            {"operation": "batch_write", "items": [{"title": "A"}, {"title": "B"}]},
            TENANT,
        )
        _assert_keys(result, "operation", "count", "status")
        assert result["status"] == "created"
        assert result["count"] == 2

    def test_batch_write_json_string_items(self, mock_ddb):
        """batch_write accepts items as a JSON string."""
        self._table(mock_ddb)
        import json
        items_json = json.dumps([{"title": "X"}])
        result = aot.exec_dynamodb_intake(
            {"operation": "batch_write", "items": items_json}, TENANT
        )
        assert result["status"] == "created"

    # -- Param validation --

    def test_read_missing_item_id(self, mock_ddb):
        self._table(mock_ddb)
        result = aot.exec_dynamodb_intake({"operation": "read"}, TENANT)
        assert "error" in result

    def test_read_not_found(self, mock_ddb):
        table = self._table(mock_ddb)
        table.get_item.return_value = {}
        result = aot.exec_dynamodb_intake(
            {"operation": "read", "item_id": "gone"}, TENANT
        )
        assert "error" in result
        assert "not found" in result["error"].lower()

    def test_update_missing_item_id(self, mock_ddb):
        self._table(mock_ddb)
        result = aot.exec_dynamodb_intake(
            {"operation": "update", "data": {"x": 1}}, TENANT
        )
        assert "error" in result

    def test_update_missing_data(self, mock_ddb):
        self._table(mock_ddb)
        result = aot.exec_dynamodb_intake(
            {"operation": "update", "item_id": "i1"}, TENANT
        )
        assert "error" in result

    def test_delete_missing_item_id(self, mock_ddb):
        self._table(mock_ddb)
        result = aot.exec_dynamodb_intake({"operation": "delete"}, TENANT)
        assert "error" in result

    def test_batch_get_missing_item_ids(self, mock_ddb):
        self._table(mock_ddb)
        result = aot.exec_dynamodb_intake({"operation": "batch_get"}, TENANT)
        assert "error" in result

    def test_batch_get_over_100(self, mock_ddb):
        self._table(mock_ddb)
        ids = ",".join([f"id{i}" for i in range(101)])
        result = aot.exec_dynamodb_intake(
            {"operation": "batch_get", "item_ids": ids}, TENANT
        )
        assert "error" in result
        assert "100" in result["error"]

    def test_batch_write_missing_items(self, mock_ddb):
        self._table(mock_ddb)
        result = aot.exec_dynamodb_intake({"operation": "batch_write"}, TENANT)
        assert "error" in result

    def test_batch_write_over_25(self, mock_ddb):
        self._table(mock_ddb)
        items = [{"title": f"item{i}"} for i in range(26)]
        result = aot.exec_dynamodb_intake(
            {"operation": "batch_write", "items": items}, TENANT
        )
        assert "error" in result
        assert "25" in result["error"]

    def test_batch_write_invalid_json(self, mock_ddb):
        self._table(mock_ddb)
        result = aot.exec_dynamodb_intake(
            {"operation": "batch_write", "items": "not json{"}, TENANT
        )
        assert "error" in result
        assert "JSON" in result["error"]

    def test_unknown_operation(self, mock_ddb):
        self._table(mock_ddb)
        result = aot.exec_dynamodb_intake({"operation": "truncate"}, TENANT)
        assert "error" in result
        assert "truncate" in result["error"]

    # -- AWS errors --

    def test_access_denied(self, mock_ddb):
        table = self._table(mock_ddb)
        table.query.side_effect = _client_error("AccessDenied", "No access")
        result = aot.exec_dynamodb_intake({"operation": "list"}, TENANT)
        _assert_keys(result, "error", "detail", "suggestion")

    def test_resource_not_found(self, mock_ddb):
        table = self._table(mock_ddb)
        table.query.side_effect = _client_error(
            "ResourceNotFoundException", "Table gone"
        )
        result = aot.exec_dynamodb_intake({"operation": "list"}, TENANT)
        assert "error" in result
        assert "not found" in result["error"].lower()

    def test_botocore_error(self, mock_ddb):
        table = self._table(mock_ddb)
        table.query.side_effect = BotoCoreError()
        result = aot.exec_dynamodb_intake({"operation": "list"}, TENANT)
        assert "connection" in result["error"].lower()

    # -- Serialization --

    def test_decimal_values_serialized(self, mock_ddb):
        table = self._table(mock_ddb)
        table.get_item.return_value = {
            "Item": {
                "PK": "INTAKE#t",
                "SK": "INTAKE#i",
                "integer_val": Decimal("42"),
                "float_val": Decimal("3.14"),
            }
        }
        result = aot.exec_dynamodb_intake(
            {"operation": "read", "item_id": "i"}, TENANT
        )
        item = result["item"]
        assert item["integer_val"] == 42
        assert isinstance(item["integer_val"], int)
        assert item["float_val"] == 3.14
        assert isinstance(item["float_val"], float)


# ===========================================================================
# CloudWatch Logs
# ===========================================================================


class TestCloudWatchLogs:
    """Tests for exec_cloudwatch_logs — all 5 sub-operations."""

    # -- Happy paths --

    def test_search_returns_schema(self, mock_logs):
        mock_logs.filter_log_events.return_value = {
            "events": [
                {
                    "timestamp": 1700000000000,
                    "message": "test log message",
                    "logStreamName": "stream-1",
                }
            ]
        }
        result = aot.exec_cloudwatch_logs(
            {"operation": "search", "filter_pattern": "ERROR"}, TENANT
        )
        _assert_keys(result, "operation", "log_group", "filter_pattern", "event_count", "events")
        assert result["operation"] == "search"
        assert result["event_count"] == 1

    def test_recent_returns_schema(self, mock_logs):
        mock_logs.filter_log_events.return_value = {"events": []}
        result = aot.exec_cloudwatch_logs(
            {"operation": "recent"}, TENANT
        )
        _assert_keys(result, "operation", "log_group", "event_count", "events")
        assert result["operation"] == "recent"

    def test_recent_with_user_id(self, mock_logs):
        mock_logs.filter_log_events.return_value = {"events": []}
        result = aot.exec_cloudwatch_logs(
            {"operation": "recent", "user_id": "bob"}, TENANT
        )
        _assert_keys(result, "user_id_filter")
        assert result["user_id_filter"] == "bob"

    def test_get_stream_returns_schema(self, mock_logs):
        mock_logs.describe_log_streams.return_value = {
            "logStreams": [
                {"logStreamName": "stream-a", "lastEventTimestamp": 1700000000000}
            ]
        }
        result = aot.exec_cloudwatch_logs(
            {"operation": "get_stream"}, TENANT
        )
        _assert_keys(result, "operation", "log_group", "streams")
        assert len(result["streams"]) == 1

    @patch("time.sleep")
    def test_insights_returns_schema(self, mock_sleep, mock_logs):
        mock_logs.start_query.return_value = {"queryId": "q-123"}
        mock_logs.get_query_results.return_value = {
            "status": "Complete",
            "results": [
                [
                    {"field": "@timestamp", "value": "2026-01-01"},
                    {"field": "@message", "value": "hello"},
                ]
            ],
        }
        result = aot.exec_cloudwatch_logs(
            {"operation": "insights", "query": "fields @message"}, TENANT
        )
        _assert_keys(result, "operation", "log_group", "query", "status", "result_count", "results")
        assert result["status"] == "Complete"
        assert result["result_count"] == 1

    def test_list_groups_returns_schema(self, mock_logs):
        mock_logs.describe_log_groups.return_value = {
            "logGroups": [
                {
                    "logGroupName": "/eagle/app",
                    "storedBytes": 1024,
                    "retentionInDays": 30,
                    "creationTime": 1700000000000,
                }
            ]
        }
        result = aot.exec_cloudwatch_logs(
            {"operation": "list_groups"}, TENANT
        )
        _assert_keys(result, "operation", "count", "log_groups")
        assert result["count"] == 1

    # -- Param validation --

    def test_unknown_operation(self, mock_logs):
        result = aot.exec_cloudwatch_logs({"operation": "purge"}, TENANT)
        assert "error" in result
        assert "purge" in result["error"]

    def test_insights_missing_query(self, mock_logs):
        result = aot.exec_cloudwatch_logs(
            {"operation": "insights"}, TENANT
        )
        assert "error" in result
        assert "query" in result["error"].lower()

    # -- AWS errors --

    def test_access_denied(self, mock_logs):
        mock_logs.filter_log_events.side_effect = _client_error(
            "AccessDenied", "No access"
        )
        result = aot.exec_cloudwatch_logs(
            {"operation": "recent"}, TENANT
        )
        _assert_keys(result, "error", "detail", "suggestion")

    def test_resource_not_found(self, mock_logs):
        mock_logs.filter_log_events.side_effect = _client_error(
            "ResourceNotFoundException", "Log group gone"
        )
        result = aot.exec_cloudwatch_logs(
            {"operation": "recent"}, TENANT
        )
        assert "error" in result
        assert "not found" in result["error"].lower()

    def test_botocore_error(self, mock_logs):
        mock_logs.filter_log_events.side_effect = BotoCoreError()
        result = aot.exec_cloudwatch_logs(
            {"operation": "recent"}, TENANT
        )
        assert "connection" in result["error"].lower()

    # -- Time parsing --

    def test_relative_start_time_hours(self, mock_logs):
        """'-2h' should set start_time ~2 hours ago."""
        mock_logs.filter_log_events.return_value = {"events": []}
        result = aot.exec_cloudwatch_logs(
            {"operation": "recent", "start_time": "-2h"}, TENANT
        )
        assert result["operation"] == "recent"
        # Verify filter_log_events was called (no error)
        mock_logs.filter_log_events.assert_called_once()

    def test_relative_start_time_minutes(self, mock_logs):
        mock_logs.filter_log_events.return_value = {"events": []}
        result = aot.exec_cloudwatch_logs(
            {"operation": "recent", "start_time": "-30m"}, TENANT
        )
        assert result["operation"] == "recent"

    def test_relative_start_time_days(self, mock_logs):
        mock_logs.filter_log_events.return_value = {"events": []}
        result = aot.exec_cloudwatch_logs(
            {"operation": "recent", "start_time": "-7d"}, TENANT
        )
        assert result["operation"] == "recent"

    # -- Message truncation --

    def test_event_messages_truncated_to_500(self, mock_logs):
        long_msg = "x" * 1000
        mock_logs.filter_log_events.return_value = {
            "events": [
                {"timestamp": 1700000000000, "message": long_msg, "logStreamName": "s"}
            ]
        }
        result = aot.exec_cloudwatch_logs(
            {"operation": "recent"}, TENANT
        )
        assert len(result["events"][0]["message"]) == 500
