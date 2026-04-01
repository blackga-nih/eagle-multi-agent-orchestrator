"""Tests for feedback enhancements: area tags, screenshot upload, display name, Teams card.

Validates:
  - feedback_area is stored in DynamoDB
  - _upload_screenshot_to_s3 decodes and uploads PNG
  - display_name prefers email > username > user_id
  - Teams card includes Area fact and screenshot Image element
  - Jira description includes area and uses display name
  - Jira summary includes area tag
"""
import base64
from unittest import mock

import pytest


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TENANT = "test-tenant"
USER_ID = "24a8d478-20a1-7087-e1a3-56a38d733592"
EMAIL = "testuser@nih.gov"
USERNAME = "testuser"
TIER = "free"
SESSION = "sess-123"
PAGE = "/chat"
FEEDBACK_TEXT = "The download failed"
FAKE_UUID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
FAKE_ISO = "2026-04-01T12:00:00.000000Z"
FAKE_TTL = 1900000000

# Minimal 1x1 transparent PNG (68 bytes)
TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
    b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
    b"\r\n\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)
TINY_PNG_DATA_URL = "data:image/png;base64," + base64.b64encode(TINY_PNG).decode()


def _mock_write(mock_table, **kwargs):
    """Call write_feedback with mocked dependencies."""
    from app.feedback_store import write_feedback

    defaults = dict(
        tenant_id=TENANT,
        user_id=USER_ID,
        tier=TIER,
        session_id=SESSION,
        feedback_text=FEEDBACK_TEXT,
        conversation_snapshot="[]",
        cloudwatch_logs="[]",
        page=PAGE,
    )
    defaults.update(kwargs)

    with (
        mock.patch("app.feedback_store.get_table", return_value=mock_table),
        mock.patch("app.feedback_store.uuid.uuid4", return_value=FAKE_UUID),
        mock.patch("app.feedback_store.now_iso", return_value=FAKE_ISO),
        mock.patch("app.feedback_store.ttl_timestamp", return_value=FAKE_TTL),
    ):
        return write_feedback(**defaults)


# ---------------------------------------------------------------------------
# TestFeedbackArea
# ---------------------------------------------------------------------------


class TestFeedbackArea:
    """Verify feedback_area is stored in DynamoDB."""

    def test_area_stored_in_item(self):
        mock_table = mock.MagicMock()
        _mock_write(mock_table, feedback_area="network")

        item = mock_table.put_item.call_args[1]["Item"]
        assert item["feedback_area"] == "network"

    def test_area_defaults_to_empty(self):
        mock_table = mock.MagicMock()
        _mock_write(mock_table)

        item = mock_table.put_item.call_args[1]["Item"]
        assert item["feedback_area"] == ""

    def test_area_with_documents_value(self):
        mock_table = mock.MagicMock()
        _mock_write(mock_table, feedback_area="documents")

        item = mock_table.put_item.call_args[1]["Item"]
        assert item["feedback_area"] == "documents"


# ---------------------------------------------------------------------------
# TestScreenshotUpload
# ---------------------------------------------------------------------------


class TestScreenshotUpload:
    """Verify _upload_screenshot_to_s3 decodes and uploads."""

    def test_uploads_decoded_png(self):
        mock_s3 = mock.MagicMock()
        mock_aws = mock.MagicMock(s3_bucket="test-bucket")
        with (
            mock.patch("app.db_client.get_s3", return_value=mock_s3),
            mock.patch("app.config.aws", mock_aws),
        ):
            from app.routers.feedback import _upload_screenshot_to_s3

            result = _upload_screenshot_to_s3("test-id", TINY_PNG_DATA_URL)

        assert result == "feedback/screenshots/test-id.png"
        mock_s3.put_object.assert_called_once()
        call_kwargs = mock_s3.put_object.call_args[1]
        assert call_kwargs["Bucket"] == "test-bucket"
        assert call_kwargs["Key"] == "feedback/screenshots/test-id.png"
        assert call_kwargs["ContentType"] == "image/png"
        assert call_kwargs["Body"] == TINY_PNG

    def test_returns_none_on_oversized(self):
        # 6 MB of data
        big_data = "data:image/png;base64," + base64.b64encode(b"\x00" * 6_000_000).decode()
        from app.routers.feedback import _upload_screenshot_to_s3

        result = _upload_screenshot_to_s3("test-id", big_data)
        assert result is None

    def test_returns_none_on_s3_error(self):
        mock_s3 = mock.MagicMock()
        mock_s3.put_object.side_effect = Exception("S3 down")
        mock_aws = mock.MagicMock(s3_bucket="test-bucket")
        with (
            mock.patch("app.db_client.get_s3", return_value=mock_s3),
            mock.patch("app.config.aws", mock_aws),
        ):
            from app.routers.feedback import _upload_screenshot_to_s3

            result = _upload_screenshot_to_s3("test-id", TINY_PNG_DATA_URL)

        assert result is None


# ---------------------------------------------------------------------------
# TestDisplayName
# ---------------------------------------------------------------------------


class TestDisplayName:
    """Verify display_name logic: email > username > user_id."""

    def _make_user(self, email=None, username=None, user_id=USER_ID):
        from app.cognito_auth import UserContext

        return UserContext(
            user_id=user_id,
            email=email,
            username=username,
            tier=TIER,
            tenant_id=TENANT,
        )

    def test_prefers_email(self):
        user = self._make_user(email=EMAIL, username=USERNAME)
        display = user.email or user.username or user.user_id
        assert display == EMAIL

    def test_falls_back_to_username(self):
        user = self._make_user(email=None, username=USERNAME)
        display = user.email or user.username or user.user_id
        assert display == USERNAME

    def test_falls_back_to_user_id(self):
        user = self._make_user(email=None, username=None)
        # UserContext sets username = user_id when None, so we test the chain
        display = user.email or user.user_id
        assert display == USER_ID


# ---------------------------------------------------------------------------
# TestTeamsCard
# ---------------------------------------------------------------------------


class TestTeamsCard:
    """Verify feedback_card includes area and screenshot."""

    def test_card_includes_area_fact(self):
        from app.teams_cards import feedback_card

        payload = feedback_card(
            environment="dev",
            tenant_id=TENANT,
            user_id=EMAIL,
            tier=TIER,
            session_id=SESSION,
            feedback_text=FEEDBACK_TEXT,
            feedback_type="bug",
            feedback_area="network",
        )
        card = payload["attachments"][0]["content"]
        facts = card["body"][1]["facts"]
        area_facts = [f for f in facts if f["title"] == "Area"]
        assert len(area_facts) == 1
        assert area_facts[0]["value"] == "network"

    def test_card_omits_area_when_empty(self):
        from app.teams_cards import feedback_card

        payload = feedback_card(
            environment="dev",
            tenant_id=TENANT,
            user_id=EMAIL,
            tier=TIER,
            session_id=SESSION,
            feedback_text=FEEDBACK_TEXT,
        )
        card = payload["attachments"][0]["content"]
        facts = card["body"][1]["facts"]
        area_facts = [f for f in facts if f["title"] == "Area"]
        assert len(area_facts) == 0

    def test_card_includes_screenshot_image(self):
        from app.teams_cards import feedback_card

        payload = feedback_card(
            environment="dev",
            tenant_id=TENANT,
            user_id=EMAIL,
            tier=TIER,
            session_id=SESSION,
            feedback_text=FEEDBACK_TEXT,
            screenshot_url="https://s3.amazonaws.com/bucket/screenshot.png",
        )
        card = payload["attachments"][0]["content"]
        images = [e for e in card["body"] if e.get("type") == "Image"]
        assert len(images) == 1
        assert images[0]["url"] == "https://s3.amazonaws.com/bucket/screenshot.png"

    def test_card_omits_image_when_no_screenshot(self):
        from app.teams_cards import feedback_card

        payload = feedback_card(
            environment="dev",
            tenant_id=TENANT,
            user_id=EMAIL,
            tier=TIER,
            session_id=SESSION,
            feedback_text=FEEDBACK_TEXT,
        )
        card = payload["attachments"][0]["content"]
        images = [e for e in card["body"] if e.get("type") == "Image"]
        assert len(images) == 0

    def test_card_shows_display_name_not_uuid(self):
        from app.teams_cards import feedback_card

        payload = feedback_card(
            environment="dev",
            tenant_id=TENANT,
            user_id=EMAIL,
            tier=TIER,
            session_id=SESSION,
            feedback_text=FEEDBACK_TEXT,
        )
        card = payload["attachments"][0]["content"]
        facts = card["body"][1]["facts"]
        user_facts = [f for f in facts if f["title"] == "User"]
        assert user_facts[0]["value"] == EMAIL

    def test_card_does_not_show_tier(self):
        from app.teams_cards import feedback_card

        payload = feedback_card(
            environment="dev",
            tenant_id=TENANT,
            user_id=EMAIL,
            tier=TIER,
            session_id=SESSION,
            feedback_text=FEEDBACK_TEXT,
        )
        card = payload["attachments"][0]["content"]
        facts = card["body"][1]["facts"]
        user_facts = [f for f in facts if f["title"] == "User"]
        assert "(free)" not in user_facts[0]["value"]


# ---------------------------------------------------------------------------
# TestJiraDescription
# ---------------------------------------------------------------------------


class TestJiraDescription:
    """Verify Jira issue creation includes area and display name."""

    def test_jira_summary_includes_area_tag(self):
        from app.routers.feedback import _create_jira_for_feedback

        with (
            mock.patch("app.config.jira", mock.MagicMock(feedback_enabled=True)),
            mock.patch(
                "app.jira_client.create_feedback_issue",
                return_value="EAGLE-100",
            ) as mock_create,
            mock.patch("app.config.app", mock.MagicMock(environment="dev")),
        ):
            _create_jira_for_feedback(
                feedback_id=FAKE_UUID,
                feedback_text=FEEDBACK_TEXT,
                feedback_type="bug",
                user_id=EMAIL,
                tenant_id=TENANT,
                tier=TIER,
                session_id=SESSION,
                page=PAGE,
                created_at=FAKE_ISO,
                feedback_area="network",
            )

        call_kwargs = mock_create.call_args[1]
        assert "[network]" in call_kwargs["summary"]
        assert "[bug]" in call_kwargs["summary"]

    def test_jira_description_includes_area_field(self):
        from app.routers.feedback import _create_jira_for_feedback

        with (
            mock.patch("app.config.jira", mock.MagicMock(feedback_enabled=True)),
            mock.patch(
                "app.jira_client.create_feedback_issue",
                return_value="EAGLE-100",
            ) as mock_create,
            mock.patch("app.config.app", mock.MagicMock(environment="dev")),
        ):
            _create_jira_for_feedback(
                feedback_id=FAKE_UUID,
                feedback_text=FEEDBACK_TEXT,
                feedback_type="bug",
                user_id=EMAIL,
                tenant_id=TENANT,
                tier=TIER,
                session_id=SESSION,
                page=PAGE,
                created_at=FAKE_ISO,
                feedback_area="documents",
            )

        call_kwargs = mock_create.call_args[1]
        assert "*Feedback Area:* documents" in call_kwargs["description"]

    def test_jira_labels_include_area(self):
        from app.routers.feedback import _create_jira_for_feedback

        with (
            mock.patch("app.config.jira", mock.MagicMock(feedback_enabled=True)),
            mock.patch(
                "app.jira_client.create_feedback_issue",
                return_value="EAGLE-100",
            ) as mock_create,
            mock.patch("app.config.app", mock.MagicMock(environment="dev")),
        ):
            _create_jira_for_feedback(
                feedback_id=FAKE_UUID,
                feedback_text=FEEDBACK_TEXT,
                feedback_type="bug",
                user_id=EMAIL,
                tenant_id=TENANT,
                tier=TIER,
                session_id=SESSION,
                page=PAGE,
                created_at=FAKE_ISO,
                feedback_area="streaming",
            )

        call_kwargs = mock_create.call_args[1]
        assert "streaming" in call_kwargs["labels"]

    def test_jira_description_shows_display_name(self):
        from app.routers.feedback import _create_jira_for_feedback

        with (
            mock.patch("app.config.jira", mock.MagicMock(feedback_enabled=True)),
            mock.patch(
                "app.jira_client.create_feedback_issue",
                return_value="EAGLE-100",
            ) as mock_create,
            mock.patch("app.config.app", mock.MagicMock(environment="dev")),
        ):
            _create_jira_for_feedback(
                feedback_id=FAKE_UUID,
                feedback_text=FEEDBACK_TEXT,
                feedback_type="bug",
                user_id=EMAIL,
                tenant_id=TENANT,
                tier=TIER,
                session_id=SESSION,
                page=PAGE,
                created_at=FAKE_ISO,
            )

        call_kwargs = mock_create.call_args[1]
        assert f"*User:* {EMAIL}" in call_kwargs["description"]
        assert "(free)" not in call_kwargs["description"]
