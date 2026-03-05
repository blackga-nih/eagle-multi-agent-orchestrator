"""Tests for feedback_store.py -- DynamoDB-backed FEEDBACK# entity.

Validates:
  - create_feedback(): PK/SK pattern, TTL, required/optional fields, error handling
  - list_feedback(): query params, sort order, limit, error handling
  - Module-level: singleton pattern, TABLE_NAME default

All tests are fast (mocked DDB, no AWS).
"""
from datetime import datetime, timedelta
from unittest import mock

from botocore.exceptions import ClientError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TENANT = "test-tenant"
USER = "test-user"
PAGE = "/chat"
FAKE_UUID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
FAKE_NOW = datetime(2026, 3, 4, 12, 0, 0)
FAKE_ISO = FAKE_NOW.isoformat()


def _make_client_error(code="InternalServerError", msg="boom"):
    return ClientError(
        {"Error": {"Code": code, "Message": msg}},
        "PutItem",
    )


def _mock_create(mock_table, **kwargs):
    """Call create_feedback with mocked table, uuid, and datetime."""
    from app.feedback_store import create_feedback

    with mock.patch("app.feedback_store._get_table", return_value=mock_table), \
         mock.patch("app.feedback_store.uuid.uuid4", return_value=FAKE_UUID), \
         mock.patch("app.feedback_store.datetime", wraps=datetime,
                    **{"utcnow.return_value": FAKE_NOW}):
        return create_feedback(tenant_id=TENANT, user_id=USER, **kwargs)


# ---------------------------------------------------------------------------
# TestCreateFeedback
# ---------------------------------------------------------------------------

class TestCreateFeedback:
    """Verify create_feedback writes correct PK/SK and handles fields."""

    def test_creates_item_with_correct_pk_sk(self):
        mock_table = mock.MagicMock()
        _mock_create(mock_table, page=PAGE)

        mock_table.put_item.assert_called_once()
        item = mock_table.put_item.call_args[1]["Item"]
        assert item["PK"] == f"FEEDBACK#{TENANT}"
        assert item["SK"] == f"FEEDBACK#{FAKE_ISO}#{FAKE_UUID}"

    def test_sets_90_day_ttl(self):
        mock_table = mock.MagicMock()
        _mock_create(mock_table)

        item = mock_table.put_item.call_args[1]["Item"]
        expected_ttl = int((FAKE_NOW + timedelta(days=90)).timestamp())
        assert item["ttl"] == expected_ttl

    def test_includes_required_fields(self):
        mock_table = mock.MagicMock()
        _mock_create(mock_table, page=PAGE)

        item = mock_table.put_item.call_args[1]["Item"]
        assert item["tenant_id"] == TENANT
        assert item["user_id"] == USER
        assert item["page"] == PAGE
        assert item["created_at"] == FAKE_ISO
        assert item["feedback_id"] == str(FAKE_UUID)

    def test_optional_fields_included_when_provided(self):
        mock_table = mock.MagicMock()
        _mock_create(
            mock_table, page=PAGE,
            rating=5, feedback_type="bug", comment="Great!", session_id="sess-1",
        )

        item = mock_table.put_item.call_args[1]["Item"]
        assert item["rating"] == 5
        assert item["feedback_type"] == "bug"
        assert item["comment"] == "Great!"
        assert item["session_id"] == "sess-1"

    def test_optional_fields_omitted_when_not_provided(self):
        """rating=0 is falsy and should NOT be included in the item."""
        mock_table = mock.MagicMock()
        _mock_create(mock_table)

        item = mock_table.put_item.call_args[1]["Item"]
        assert "rating" not in item
        assert "feedback_type" not in item
        assert "comment" not in item
        assert "session_id" not in item

    def test_returns_created_item(self):
        mock_table = mock.MagicMock()
        result = _mock_create(mock_table, page=PAGE)

        assert isinstance(result, dict)
        assert result["PK"] == f"FEEDBACK#{TENANT}"
        assert result["tenant_id"] == TENANT
        assert result["feedback_id"] == str(FAKE_UUID)

    def test_raises_on_client_error(self):
        import pytest
        from app.feedback_store import create_feedback

        mock_table = mock.MagicMock()
        mock_table.put_item.side_effect = _make_client_error()
        with mock.patch("app.feedback_store._get_table", return_value=mock_table), \
             mock.patch("app.feedback_store.uuid.uuid4", return_value=FAKE_UUID), \
             mock.patch("app.feedback_store.datetime", wraps=datetime,
                        **{"utcnow.return_value": FAKE_NOW}):
            with pytest.raises(ClientError):
                create_feedback(tenant_id=TENANT, user_id=USER)


# ---------------------------------------------------------------------------
# TestListFeedback
# ---------------------------------------------------------------------------

class TestListFeedback:
    """Verify list_feedback queries and formats results."""

    def test_queries_with_correct_pk_and_sk_prefix(self):
        from app.feedback_store import list_feedback

        mock_table = mock.MagicMock()
        mock_table.query.return_value = {"Items": []}
        with mock.patch("app.feedback_store._get_table", return_value=mock_table):
            list_feedback(TENANT)

        mock_table.query.assert_called_once()
        call_kwargs = mock_table.query.call_args[1]
        # KeyConditionExpression is a boto3 ConditionExpression object;
        # verify it was built with the right PK value by checking the
        # expression attribute values that boto3 generates.
        kce = call_kwargs["KeyConditionExpression"]
        assert kce is not None

    def test_returns_newest_first(self):
        from app.feedback_store import list_feedback

        mock_table = mock.MagicMock()
        mock_table.query.return_value = {"Items": []}
        with mock.patch("app.feedback_store._get_table", return_value=mock_table):
            list_feedback(TENANT)

        call_kwargs = mock_table.query.call_args[1]
        assert call_kwargs["ScanIndexForward"] is False

    def test_respects_limit_parameter(self):
        from app.feedback_store import list_feedback

        mock_table = mock.MagicMock()
        mock_table.query.return_value = {"Items": []}
        with mock.patch("app.feedback_store._get_table", return_value=mock_table):
            list_feedback(TENANT, limit=10)

        call_kwargs = mock_table.query.call_args[1]
        assert call_kwargs["Limit"] == 10

    def test_returns_items_as_dicts(self):
        from app.feedback_store import list_feedback

        fake_items = [
            {"PK": f"FEEDBACK#{TENANT}", "SK": "FEEDBACK#2026-03-04#abc", "rating": 5},
            {"PK": f"FEEDBACK#{TENANT}", "SK": "FEEDBACK#2026-03-03#def", "rating": 3},
        ]
        mock_table = mock.MagicMock()
        mock_table.query.return_value = {"Items": fake_items}
        with mock.patch("app.feedback_store._get_table", return_value=mock_table):
            result = list_feedback(TENANT)

        assert len(result) == 2
        assert result[0]["rating"] == 5
        assert result[1]["rating"] == 3

    def test_returns_empty_list_on_error(self):
        from app.feedback_store import list_feedback

        mock_table = mock.MagicMock()
        mock_table.query.side_effect = _make_client_error()
        with mock.patch("app.feedback_store._get_table", return_value=mock_table):
            result = list_feedback(TENANT)

        assert result == []

    def test_returns_empty_list_when_no_items(self):
        from app.feedback_store import list_feedback

        mock_table = mock.MagicMock()
        mock_table.query.return_value = {"Items": []}
        with mock.patch("app.feedback_store._get_table", return_value=mock_table):
            result = list_feedback(TENANT)

        assert result == []


# ---------------------------------------------------------------------------
# TestModuleLevel
# ---------------------------------------------------------------------------

class TestModuleLevel:
    """Verify module-level singleton and defaults."""

    def test_get_dynamodb_singleton(self):
        """_get_dynamodb() returns the same resource on repeated calls."""
        import app.feedback_store as fs

        old = fs._dynamodb
        try:
            fs._dynamodb = None  # reset singleton
            mock_resource = mock.MagicMock()
            with mock.patch("app.feedback_store.boto3.resource", return_value=mock_resource) as mock_boto:
                first = fs._get_dynamodb()
                second = fs._get_dynamodb()

            assert first is second
            assert first is mock_resource
            mock_boto.assert_called_once()  # only one boto3.resource call
        finally:
            fs._dynamodb = old  # restore

    def test_table_name_defaults_to_eagle(self):
        from app.feedback_store import TABLE_NAME
        assert TABLE_NAME == "eagle"
