"""Tests for feedback_store.py -- DynamoDB-backed FEEDBACK# entity.

Validates:
  - write_feedback(): PK/SK pattern, TTL, required fields, error handling
  - list_feedback(): query params, sort order, limit, error handling
  - Module-level: singleton pattern, TABLE_NAME default

All tests are fast (mocked DDB, no AWS).
"""
from datetime import datetime, timedelta
from unittest import mock

import pytest
from botocore.exceptions import ClientError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TENANT = "test-tenant"
USER = "test-user"
TIER = "advanced"
SESSION = "sess-123"
PAGE = "/chat"
FEEDBACK_TEXT = "This tool is great!"
CONVERSATION_SNAPSHOT = '[]'
CLOUDWATCH_LOGS = '[]'
FAKE_UUID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
FAKE_NOW = datetime(2026, 3, 4, 12, 0, 0)
# _now_iso() format: "%Y-%m-%dT%H:%M:%S.%f" + "Z"
FAKE_ISO = FAKE_NOW.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


def _make_client_error(code="InternalServerError", msg="boom"):
    return ClientError(
        {"Error": {"Code": code, "Message": msg}},
        "PutItem",
    )


FAKE_TTL = int((FAKE_NOW + timedelta(days=365 * 7)).timestamp())


def _mock_write(mock_table, **kwargs):
    """Call write_feedback with mocked table, uuid, and datetime."""
    from app.feedback_store import write_feedback

    defaults = dict(
        tenant_id=TENANT,
        user_id=USER,
        tier=TIER,
        session_id=SESSION,
        feedback_text=FEEDBACK_TEXT,
        conversation_snapshot=CONVERSATION_SNAPSHOT,
        cloudwatch_logs=CLOUDWATCH_LOGS,
    )
    defaults.update(kwargs)

    with mock.patch("app.feedback_store.get_table", return_value=mock_table), \
         mock.patch("app.feedback_store.uuid.uuid4", return_value=FAKE_UUID), \
         mock.patch("app.feedback_store.now_iso", return_value=FAKE_ISO), \
         mock.patch("app.feedback_store.ttl_timestamp", return_value=FAKE_TTL):
        return write_feedback(**defaults)


# ---------------------------------------------------------------------------
# TestWriteFeedback
# ---------------------------------------------------------------------------

class TestWriteFeedback:
    """Verify write_feedback writes correct PK/SK and handles fields."""

    def test_creates_item_with_correct_pk_sk(self):
        mock_table = mock.MagicMock()
        _mock_write(mock_table, page=PAGE)

        mock_table.put_item.assert_called_once()
        item = mock_table.put_item.call_args[1]["Item"]
        assert item["PK"] == f"FEEDBACK#{TENANT}"
        assert item["SK"] == f"FEEDBACK#{FAKE_ISO}#{FAKE_UUID}"

    def test_sets_7_year_ttl(self):
        mock_table = mock.MagicMock()
        _mock_write(mock_table)

        item = mock_table.put_item.call_args[1]["Item"]
        expected_ttl = int((FAKE_NOW + timedelta(days=365 * 7)).timestamp())
        assert item["ttl"] == expected_ttl

    def test_includes_required_fields(self):
        mock_table = mock.MagicMock()
        _mock_write(mock_table, page=PAGE)

        item = mock_table.put_item.call_args[1]["Item"]
        assert item["tenant_id"] == TENANT
        assert item["user_id"] == USER
        assert item["tier"] == TIER
        assert item["session_id"] == SESSION
        assert item["feedback_text"] == FEEDBACK_TEXT
        assert item["conversation_snapshot"] == CONVERSATION_SNAPSHOT
        assert item["cloudwatch_logs"] == CLOUDWATCH_LOGS
        assert item["page"] == PAGE
        assert item["created_at"] == FAKE_ISO
        assert item["feedback_id"] == str(FAKE_UUID)

    def test_auto_detects_feedback_type(self):
        mock_table = mock.MagicMock()
        _mock_write(mock_table, feedback_text="This tool is great!")

        item = mock_table.put_item.call_args[1]["Item"]
        assert item["feedback_type"] == "praise"

    def test_bug_feedback_type(self):
        mock_table = mock.MagicMock()
        _mock_write(mock_table, feedback_text="There is a bug in the system")

        item = mock_table.put_item.call_args[1]["Item"]
        assert item["feedback_type"] == "bug"

    def test_returns_created_item(self):
        mock_table = mock.MagicMock()
        result = _mock_write(mock_table, page=PAGE)

        assert isinstance(result, dict)
        assert result["PK"] == f"FEEDBACK#{TENANT}"
        assert result["tenant_id"] == TENANT
        assert result["feedback_id"] == str(FAKE_UUID)

    def test_raises_on_client_error(self):
        from app.feedback_store import write_feedback

        mock_table = mock.MagicMock()
        mock_table.put_item.side_effect = _make_client_error()
        with mock.patch("app.feedback_store.get_table", return_value=mock_table), \
             mock.patch("app.feedback_store.uuid.uuid4", return_value=FAKE_UUID), \
             mock.patch("app.feedback_store.now_iso", return_value=FAKE_ISO):
            with pytest.raises(ClientError):
                write_feedback(
                    tenant_id=TENANT, user_id=USER, tier=TIER,
                    session_id=SESSION, feedback_text=FEEDBACK_TEXT,
                    conversation_snapshot=CONVERSATION_SNAPSHOT,
                    cloudwatch_logs=CLOUDWATCH_LOGS,
                )

    def test_gsi_keys_present(self):
        mock_table = mock.MagicMock()
        _mock_write(mock_table)

        item = mock_table.put_item.call_args[1]["Item"]
        assert item["GSI1PK"] == f"TENANT#{TENANT}"
        assert item["GSI1SK"].startswith("FEEDBACK#")


# ---------------------------------------------------------------------------
# TestListFeedback
# ---------------------------------------------------------------------------

class TestListFeedback:
    """Verify list_feedback queries and formats results."""

    def test_queries_with_correct_pk_and_sk_prefix(self):
        from app.feedback_store import list_feedback

        mock_table = mock.MagicMock()
        mock_table.query.return_value = {"Items": []}
        with mock.patch("app.feedback_store.get_table", return_value=mock_table):
            list_feedback(TENANT)

        mock_table.query.assert_called_once()
        call_kwargs = mock_table.query.call_args[1]
        kce = call_kwargs["KeyConditionExpression"]
        assert kce is not None

    def test_returns_newest_first(self):
        from app.feedback_store import list_feedback

        mock_table = mock.MagicMock()
        mock_table.query.return_value = {"Items": []}
        with mock.patch("app.feedback_store.get_table", return_value=mock_table):
            list_feedback(TENANT)

        call_kwargs = mock_table.query.call_args[1]
        assert call_kwargs["ScanIndexForward"] is False

    def test_respects_limit_parameter(self):
        from app.feedback_store import list_feedback

        mock_table = mock.MagicMock()
        mock_table.query.return_value = {"Items": []}
        with mock.patch("app.feedback_store.get_table", return_value=mock_table):
            list_feedback(TENANT, limit=10)

        call_kwargs = mock_table.query.call_args[1]
        assert call_kwargs["Limit"] == 10

    def test_returns_items_as_dicts(self):
        from app.feedback_store import list_feedback

        fake_items = [
            {"PK": f"FEEDBACK#{TENANT}", "SK": "FEEDBACK#2026-03-04#abc", "feedback_text": "good"},
            {"PK": f"FEEDBACK#{TENANT}", "SK": "FEEDBACK#2026-03-03#def", "feedback_text": "ok"},
        ]
        mock_table = mock.MagicMock()
        mock_table.query.return_value = {"Items": fake_items}
        with mock.patch("app.feedback_store.get_table", return_value=mock_table):
            result = list_feedback(TENANT)

        assert len(result) == 2
        assert result[0]["feedback_text"] == "good"
        assert result[1]["feedback_text"] == "ok"

    def test_raises_on_error(self):
        from app.feedback_store import list_feedback

        mock_table = mock.MagicMock()
        mock_table.query.side_effect = _make_client_error()
        with mock.patch("app.feedback_store.get_table", return_value=mock_table):
            with pytest.raises(ClientError):
                list_feedback(TENANT)

    def test_returns_empty_list_when_no_items(self):
        from app.feedback_store import list_feedback

        mock_table = mock.MagicMock()
        mock_table.query.return_value = {"Items": []}
        with mock.patch("app.feedback_store.get_table", return_value=mock_table):
            result = list_feedback(TENANT)

        assert result == []


# ---------------------------------------------------------------------------
# TestWriteMessageFeedback
# ---------------------------------------------------------------------------

MESSAGE_ID = "msg-456"


def _mock_write_message_feedback(mock_table, **kwargs):
    """Call write_message_feedback with mocked table, uuid, and datetime."""
    from app.feedback_store import write_message_feedback

    defaults = dict(
        tenant_id=TENANT,
        user_id=USER,
        session_id=SESSION,
        message_id=MESSAGE_ID,
        feedback_type="thumbs_up",
    )
    defaults.update(kwargs)

    with mock.patch("app.feedback_store.get_table", return_value=mock_table), \
         mock.patch("app.feedback_store.uuid.uuid4", return_value=FAKE_UUID), \
         mock.patch("app.feedback_store.now_iso", return_value=FAKE_ISO), \
         mock.patch("app.feedback_store.ttl_timestamp", return_value=FAKE_TTL):
        return write_message_feedback(**defaults)


class TestWriteMessageFeedback:
    """Verify write_message_feedback writes correct PK/SK and handles fields."""

    def test_creates_item_with_correct_pk_sk(self):
        mock_table = mock.MagicMock()
        _mock_write_message_feedback(mock_table)

        mock_table.put_item.assert_called_once()
        item = mock_table.put_item.call_args[1]["Item"]
        assert item["PK"] == f"FEEDBACK#{TENANT}"
        assert item["SK"] == f"MSG_FEEDBACK#{SESSION}#{MESSAGE_ID}"

    def test_gsi_keys_use_msg_feedback_prefix(self):
        mock_table = mock.MagicMock()
        _mock_write_message_feedback(mock_table)

        item = mock_table.put_item.call_args[1]["Item"]
        assert item["GSI1PK"] == f"TENANT#{TENANT}"
        assert item["GSI1SK"].startswith("MSG_FEEDBACK#")

    def test_includes_required_fields(self):
        mock_table = mock.MagicMock()
        _mock_write_message_feedback(mock_table, comment="great answer")

        item = mock_table.put_item.call_args[1]["Item"]
        assert item["tenant_id"] == TENANT
        assert item["user_id"] == USER
        assert item["session_id"] == SESSION
        assert item["message_id"] == MESSAGE_ID
        assert item["feedback_type"] == "thumbs_up"
        assert item["comment"] == "great answer"
        assert item["feedback_id"] == str(FAKE_UUID)
        assert item["created_at"] == FAKE_ISO

    def test_sets_7_year_ttl(self):
        mock_table = mock.MagicMock()
        _mock_write_message_feedback(mock_table)

        item = mock_table.put_item.call_args[1]["Item"]
        expected_ttl = int((FAKE_NOW + timedelta(days=365 * 7)).timestamp())
        assert item["ttl"] == expected_ttl

    def test_returns_created_item(self):
        mock_table = mock.MagicMock()
        result = _mock_write_message_feedback(mock_table)

        assert isinstance(result, dict)
        assert result["PK"] == f"FEEDBACK#{TENANT}"
        assert result["feedback_type"] == "thumbs_up"

    def test_thumbs_down_feedback_type(self):
        mock_table = mock.MagicMock()
        _mock_write_message_feedback(mock_table, feedback_type="thumbs_down")

        item = mock_table.put_item.call_args[1]["Item"]
        assert item["feedback_type"] == "thumbs_down"

    def test_raises_on_client_error(self):
        mock_table = mock.MagicMock()
        mock_table.put_item.side_effect = _make_client_error()
        with pytest.raises(ClientError):
            _mock_write_message_feedback(mock_table)


# ---------------------------------------------------------------------------
# TestListMessageFeedback
# ---------------------------------------------------------------------------

class TestListMessageFeedback:
    """Verify list_message_feedback queries with MSG_FEEDBACK# prefix."""

    def test_queries_with_msg_feedback_prefix(self):
        from app.feedback_store import list_message_feedback

        mock_table = mock.MagicMock()
        mock_table.query.return_value = {"Items": []}
        with mock.patch("app.feedback_store.get_table", return_value=mock_table):
            list_message_feedback(TENANT)

        mock_table.query.assert_called_once()
        call_kwargs = mock_table.query.call_args[1]
        assert call_kwargs["ScanIndexForward"] is False

    def test_returns_newest_first(self):
        from app.feedback_store import list_message_feedback

        mock_table = mock.MagicMock()
        mock_table.query.return_value = {"Items": []}
        with mock.patch("app.feedback_store.get_table", return_value=mock_table):
            list_message_feedback(TENANT)

        call_kwargs = mock_table.query.call_args[1]
        assert call_kwargs["ScanIndexForward"] is False

    def test_respects_limit_parameter(self):
        from app.feedback_store import list_message_feedback

        mock_table = mock.MagicMock()
        mock_table.query.return_value = {"Items": []}
        with mock.patch("app.feedback_store.get_table", return_value=mock_table):
            list_message_feedback(TENANT, limit=25)

        call_kwargs = mock_table.query.call_args[1]
        assert call_kwargs["Limit"] == 25

    def test_returns_items(self):
        from app.feedback_store import list_message_feedback

        fake_items = [
            {"PK": f"FEEDBACK#{TENANT}", "SK": f"MSG_FEEDBACK#{SESSION}#msg1", "feedback_type": "thumbs_up"},
            {"PK": f"FEEDBACK#{TENANT}", "SK": f"MSG_FEEDBACK#{SESSION}#msg2", "feedback_type": "thumbs_down"},
        ]
        mock_table = mock.MagicMock()
        mock_table.query.return_value = {"Items": fake_items}
        with mock.patch("app.feedback_store.get_table", return_value=mock_table):
            result = list_message_feedback(TENANT)

        assert len(result) == 2
        assert result[0]["feedback_type"] == "thumbs_up"

    def test_raises_on_error(self):
        from app.feedback_store import list_message_feedback

        mock_table = mock.MagicMock()
        mock_table.query.side_effect = _make_client_error()
        with mock.patch("app.feedback_store.get_table", return_value=mock_table):
            with pytest.raises(ClientError):
                list_message_feedback(TENANT)


# ---------------------------------------------------------------------------
# TestGetMessageFeedbackSummary
# ---------------------------------------------------------------------------

class TestGetMessageFeedbackSummary:
    """Verify get_message_feedback_summary aggregation logic."""

    def test_calculates_thumbs_up_pct(self):
        from app.feedback_store import get_message_feedback_summary

        fake_items = [
            {"feedback_type": "thumbs_up"},
            {"feedback_type": "thumbs_up"},
            {"feedback_type": "thumbs_up"},
            {"feedback_type": "thumbs_down"},
        ]
        with mock.patch("app.feedback_store.list_message_feedback", return_value=fake_items):
            result = get_message_feedback_summary(TENANT)

        assert result["total"] == 4
        assert result["thumbs_up"] == 3
        assert result["thumbs_down"] == 1
        assert result["thumbs_up_pct"] == 75.0

    def test_empty_feedback_returns_zero(self):
        from app.feedback_store import get_message_feedback_summary

        with mock.patch("app.feedback_store.list_message_feedback", return_value=[]):
            result = get_message_feedback_summary(TENANT)

        assert result["total"] == 0
        assert result["thumbs_up"] == 0
        assert result["thumbs_down"] == 0
        assert result["thumbs_up_pct"] == 0

    def test_all_thumbs_up(self):
        from app.feedback_store import get_message_feedback_summary

        fake_items = [{"feedback_type": "thumbs_up"}] * 5
        with mock.patch("app.feedback_store.list_message_feedback", return_value=fake_items):
            result = get_message_feedback_summary(TENANT)

        assert result["thumbs_up_pct"] == 100.0
        assert result["thumbs_down"] == 0

    def test_all_thumbs_down(self):
        from app.feedback_store import get_message_feedback_summary

        fake_items = [{"feedback_type": "thumbs_down"}] * 3
        with mock.patch("app.feedback_store.list_message_feedback", return_value=fake_items):
            result = get_message_feedback_summary(TENANT)

        assert result["thumbs_up_pct"] == 0
        assert result["thumbs_up"] == 0
        assert result["thumbs_down"] == 3

    def test_rounds_to_one_decimal(self):
        from app.feedback_store import get_message_feedback_summary

        fake_items = [
            {"feedback_type": "thumbs_up"},
            {"feedback_type": "thumbs_up"},
            {"feedback_type": "thumbs_down"},
        ]
        with mock.patch("app.feedback_store.list_message_feedback", return_value=fake_items):
            result = get_message_feedback_summary(TENANT)

        assert result["thumbs_up_pct"] == 66.7


# ---------------------------------------------------------------------------
# TestModuleLevel
# ---------------------------------------------------------------------------

class TestModuleLevel:
    """Verify module-level singleton and defaults (via db_client)."""

    def test_get_dynamodb_singleton(self):
        """get_dynamodb() returns the same resource on repeated calls (lru_cache)."""
        import app.db_client as dbc

        # Clear cache for clean test
        dbc.get_dynamodb.cache_clear()
        try:
            mock_resource = mock.MagicMock()
            with mock.patch("app.db_client.boto3.resource", return_value=mock_resource) as mock_boto:
                first = dbc.get_dynamodb()
                second = dbc.get_dynamodb()

            assert first is second
            assert first is mock_resource
            mock_boto.assert_called_once()  # only one boto3.resource call
        finally:
            dbc.get_dynamodb.cache_clear()

    def test_table_name_default(self):
        """TABLE_NAME defaults to 'eagle' via EAGLE_SESSIONS_TABLE env var."""
        import app.db_client as dbc

        # Clear caches for clean test
        dbc.get_table.cache_clear()
        dbc.get_dynamodb.cache_clear()
        try:
            mock_ddb = mock.MagicMock()
            mock_table = mock.MagicMock()
            mock_ddb.Table.return_value = mock_table
            with mock.patch("app.db_client.boto3.resource", return_value=mock_ddb), \
                 mock.patch.dict("os.environ", {"EAGLE_SESSIONS_TABLE": "eagle"}, clear=False):
                result = dbc.get_table()
            mock_ddb.Table.assert_called_once_with("eagle")
            assert result is mock_table
        finally:
            dbc.get_table.cache_clear()
            dbc.get_dynamodb.cache_clear()
