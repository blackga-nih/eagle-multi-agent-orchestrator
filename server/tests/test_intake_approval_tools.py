"""Tests for exec_submit_intake_for_approval and exec_confirm_intake_approval.

PR1.2 of the jolly-snacking-narwhal plan. Validates the regex-based
free-form classifier and the two dispatch handlers that wrap the
package_store gate primitives. Both handlers are mocked end-to-end —
no DDB, no Bedrock.
"""
from unittest import mock

import pytest


TENANT = "test-tenant"
USER = "test-user"
PACKAGE_ID = "PKG-2026-0001"


SUMMARY = {
    "requirement_description": "CT scanner for radiology",
    "estimated_value": "500000",
    "required_documents": ["sow", "igce", "acquisition_plan"],
}


# ---------------------------------------------------------------------------
# Classifier — regex precedence: revise > decline > approve
# ---------------------------------------------------------------------------


class TestClassifyResponse:
    @pytest.mark.parametrize(
        "text",
        [
            "yes",
            "approve",
            "approved",
            "looks good",
            "lgtm",
            "go ahead",
            "sounds good, ship it",
            "ok, proceed",
            "Yes please",
        ],
    )
    def test_approve_patterns(self, text):
        from app.tools.intake_approval_tools import _classify_response

        assert _classify_response(text)["decision"] == "approve"

    @pytest.mark.parametrize(
        "text",
        [
            "no",
            "stop",
            "cancel",
            "nope",
            "don't approve",
            "do not generate",
            "abort",
            "nevermind",
        ],
    )
    def test_decline_patterns(self, text):
        from app.tools.intake_approval_tools import _classify_response

        assert _classify_response(text)["decision"] == "decline"

    @pytest.mark.parametrize(
        "text",
        [
            "change the value to $300K",
            "update the requirement type to services",
            "revise the vehicle",
            "actually it should be GSA Schedule",
            "set the threshold to micro-purchase",
            "the value needs to be 250000",
        ],
    )
    def test_revise_patterns(self, text):
        from app.tools.intake_approval_tools import _classify_response

        assert _classify_response(text)["decision"] == "revise"

    def test_revise_beats_approve_when_both_match(self):
        """'approve, but change the value' is revise — user wants edits first."""
        from app.tools.intake_approval_tools import _classify_response

        result = _classify_response("approve, but change the value to $300K")
        assert result["decision"] == "revise"

    def test_decline_beats_approve_when_only_decline_matches(self):
        from app.tools.intake_approval_tools import _classify_response

        result = _classify_response("no, don't approve this")
        assert result["decision"] == "decline"

    def test_unclear_for_empty(self):
        from app.tools.intake_approval_tools import _classify_response

        assert _classify_response("")["decision"] == "unclear"
        assert _classify_response("   ")["decision"] == "unclear"

    def test_unclear_for_unrelated_text(self):
        from app.tools.intake_approval_tools import _classify_response

        result = _classify_response("what does FAR Part 8 cover?")
        assert result["decision"] == "unclear"


# ---------------------------------------------------------------------------
# exec_submit_intake_for_approval
# ---------------------------------------------------------------------------


class TestSubmitIntakeForApproval:
    def test_happy_path_writes_proposed_summary(self):
        from app.tools.intake_approval_tools import exec_submit_intake_for_approval

        pkg = {"package_id": PACKAGE_ID, "status": "intake"}
        captured: dict = {}

        def fake_update(tenant, pkg_id, updates):
            captured["updates"] = updates
            return {**pkg, **updates}

        with (
            mock.patch("app.tools.intake_approval_tools.get_package", return_value=pkg),
            mock.patch("app.tools.intake_approval_tools.update_package", side_effect=fake_update),
        ):
            result = exec_submit_intake_for_approval(
                {"package_id": PACKAGE_ID, "summary": SUMMARY}, tenant_id=TENANT
            )

        assert result["status"] == "intake_proposed"
        assert result["package_id"] == PACKAGE_ID
        assert result["intake_proposed_summary"] == SUMMARY
        assert captured["updates"] == {"intake_proposed_summary": SUMMARY}

    def test_missing_package_id(self):
        from app.tools.intake_approval_tools import exec_submit_intake_for_approval

        result = exec_submit_intake_for_approval({}, tenant_id=TENANT)
        assert result["error"] == "missing_package_id"

    def test_invalid_summary_type(self):
        from app.tools.intake_approval_tools import exec_submit_intake_for_approval

        result = exec_submit_intake_for_approval(
            {"package_id": PACKAGE_ID, "summary": "not a dict"}, tenant_id=TENANT
        )
        assert result["error"] == "invalid_summary"

    def test_package_not_found(self):
        from app.tools.intake_approval_tools import exec_submit_intake_for_approval

        with mock.patch("app.tools.intake_approval_tools.get_package", return_value=None):
            result = exec_submit_intake_for_approval(
                {"package_id": PACKAGE_ID, "summary": SUMMARY}, tenant_id=TENANT
            )
        assert result["error"] == "package_not_found"

    def test_already_approved_short_circuits(self):
        from app.tools.intake_approval_tools import exec_submit_intake_for_approval

        approved_pkg = {
            "package_id": PACKAGE_ID,
            "status": "drafting",
            "intake_approved_at": "2026-04-30T10:00:00+00:00",
            "intake_approval_source": "user_confirmation",
        }
        with (
            mock.patch("app.tools.intake_approval_tools.get_package", return_value=approved_pkg),
            mock.patch("app.tools.intake_approval_tools.update_package") as mock_update,
        ):
            result = exec_submit_intake_for_approval(
                {"package_id": PACKAGE_ID, "summary": SUMMARY}, tenant_id=TENANT
            )

        assert result["status"] == "already_approved"
        mock_update.assert_not_called()

    def test_legacy_backfill_pkg_can_still_propose(self):
        """A legacy_backfill record is NOT a real approval — submit must proceed."""
        from app.tools.intake_approval_tools import exec_submit_intake_for_approval

        legacy_pkg = {
            "package_id": PACKAGE_ID,
            "status": "drafting",
            "intake_approved_at": "2026-03-15T09:30:00+00:00",
            "intake_approval_source": "legacy_backfill",
        }
        with (
            mock.patch("app.tools.intake_approval_tools.get_package", return_value=legacy_pkg),
            mock.patch(
                "app.tools.intake_approval_tools.update_package",
                return_value={**legacy_pkg, "intake_proposed_summary": SUMMARY},
            ),
        ):
            result = exec_submit_intake_for_approval(
                {"package_id": PACKAGE_ID, "summary": SUMMARY}, tenant_id=TENANT
            )

        # Did not short-circuit — the legacy backfill is upgradeable
        assert result["status"] == "intake_proposed"


# ---------------------------------------------------------------------------
# exec_confirm_intake_approval
# ---------------------------------------------------------------------------


class TestConfirmIntakeApproval:
    def test_approve_path_calls_mark_intake_approved(self):
        from app.tools.intake_approval_tools import exec_confirm_intake_approval

        pkg = {
            "package_id": PACKAGE_ID,
            "status": "intake",
            "intake_proposed_summary": SUMMARY,
        }
        approved = {
            **pkg,
            "status": "drafting",
            "intake_approved_at": "2026-05-01T15:00:00+00:00",
        }

        with (
            mock.patch("app.tools.intake_approval_tools.get_package", return_value=pkg),
            mock.patch(
                "app.tools.intake_approval_tools.mark_intake_approved",
                return_value=approved,
            ) as mock_mark,
        ):
            result = exec_confirm_intake_approval(
                {
                    "package_id": PACKAGE_ID,
                    "user_response": "approve",
                    "actor_user_id": USER,
                },
                tenant_id=TENANT,
            )

        assert result["decision"] == "approve"
        assert result["status"] == "drafting"
        assert result["intake_approved_at"] == "2026-05-01T15:00:00+00:00"

        mock_mark.assert_called_once()
        kwargs = mock_mark.call_args.kwargs
        assert kwargs["tenant_id"] == TENANT
        assert kwargs["package_id"] == PACKAGE_ID
        assert kwargs["user_id"] == USER
        assert kwargs["summary"] == SUMMARY
        assert kwargs["source"] == "user_confirmation"

    def test_revise_path_returns_proposed_summary_unchanged(self):
        from app.tools.intake_approval_tools import exec_confirm_intake_approval

        pkg = {
            "package_id": PACKAGE_ID,
            "status": "intake",
            "intake_proposed_summary": SUMMARY,
        }
        with (
            mock.patch("app.tools.intake_approval_tools.get_package", return_value=pkg),
            mock.patch("app.tools.intake_approval_tools.mark_intake_approved") as mock_mark,
        ):
            result = exec_confirm_intake_approval(
                {
                    "package_id": PACKAGE_ID,
                    "user_response": "change the value to $300K",
                    "actor_user_id": USER,
                },
                tenant_id=TENANT,
            )

        assert result["decision"] == "revise"
        assert result["proposed_summary"] == SUMMARY
        assert "300K" in result["user_revisions_text"]
        mock_mark.assert_not_called()

    def test_decline_path_does_not_approve(self):
        from app.tools.intake_approval_tools import exec_confirm_intake_approval

        with (
            mock.patch(
                "app.tools.intake_approval_tools.get_package",
                return_value={"package_id": PACKAGE_ID, "status": "intake"},
            ),
            mock.patch("app.tools.intake_approval_tools.mark_intake_approved") as mock_mark,
        ):
            result = exec_confirm_intake_approval(
                {
                    "package_id": PACKAGE_ID,
                    "user_response": "no, cancel this",
                    "actor_user_id": USER,
                },
                tenant_id=TENANT,
            )

        assert result["decision"] == "decline"
        mock_mark.assert_not_called()

    def test_unclear_path_does_not_approve(self):
        from app.tools.intake_approval_tools import exec_confirm_intake_approval

        with (
            mock.patch(
                "app.tools.intake_approval_tools.get_package",
                return_value={"package_id": PACKAGE_ID, "status": "intake"},
            ),
            mock.patch("app.tools.intake_approval_tools.mark_intake_approved") as mock_mark,
        ):
            result = exec_confirm_intake_approval(
                {
                    "package_id": PACKAGE_ID,
                    "user_response": "what's a SOW?",
                    "actor_user_id": USER,
                },
                tenant_id=TENANT,
            )

        assert result["decision"] == "unclear"
        mock_mark.assert_not_called()

    def test_slash_bypass_source_is_passed_through(self):
        from app.tools.intake_approval_tools import exec_confirm_intake_approval

        pkg = {"package_id": PACKAGE_ID, "intake_proposed_summary": {}}
        with (
            mock.patch("app.tools.intake_approval_tools.get_package", return_value=pkg),
            mock.patch(
                "app.tools.intake_approval_tools.mark_intake_approved",
                return_value={**pkg, "status": "drafting"},
            ) as mock_mark,
        ):
            exec_confirm_intake_approval(
                {
                    "package_id": PACKAGE_ID,
                    "user_response": "approve",
                    "actor_user_id": USER,
                    "source": "slash_bypass",
                },
                tenant_id=TENANT,
            )

        assert mock_mark.call_args.kwargs["source"] == "slash_bypass"

    def test_missing_package_id(self):
        from app.tools.intake_approval_tools import exec_confirm_intake_approval

        result = exec_confirm_intake_approval(
            {"user_response": "yes", "actor_user_id": USER}, tenant_id=TENANT
        )
        assert result["error"] == "missing_package_id"

    def test_missing_actor_user_id(self):
        from app.tools.intake_approval_tools import exec_confirm_intake_approval

        result = exec_confirm_intake_approval(
            {"package_id": PACKAGE_ID, "user_response": "yes"}, tenant_id=TENANT
        )
        assert result["error"] == "missing_actor_user_id"

    def test_package_not_found(self):
        from app.tools.intake_approval_tools import exec_confirm_intake_approval

        with mock.patch("app.tools.intake_approval_tools.get_package", return_value=None):
            result = exec_confirm_intake_approval(
                {
                    "package_id": "PKG-MISSING",
                    "user_response": "yes",
                    "actor_user_id": USER,
                },
                tenant_id=TENANT,
            )
        assert result["error"] == "package_not_found"


# ---------------------------------------------------------------------------
# Dispatch registration
# ---------------------------------------------------------------------------


class TestDispatchRegistration:
    def test_handlers_are_registered_in_tool_dispatch(self):
        from app.tools.legacy_dispatch import get_tool_dispatch

        dispatch = get_tool_dispatch()
        assert "submit_intake_for_approval" in dispatch
        assert "confirm_intake_approval" in dispatch

    def test_handlers_listed_in_tools_needing_session(self):
        from app.tools.legacy_dispatch import TOOLS_NEEDING_SESSION

        assert "submit_intake_for_approval" in TOOLS_NEEDING_SESSION
        assert "confirm_intake_approval" in TOOLS_NEEDING_SESSION
