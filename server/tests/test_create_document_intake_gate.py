"""Tests for the intake-approval refusal guard in exec_create_document.

PR1.3 of the jolly-snacking-narwhal plan. The guard is feature-flagged via
EAGLE_INTAKE_GATE_ENABLED so this commit is behaviour-neutral until the
approval tooling (PR1.2) and supervisor wiring (PR1.5) land. These tests
exercise both the off (default, today's behaviour) and on (post-flip)
paths so the regression contract is captured up front.
"""
from unittest import mock

import pytest


TENANT = "test-tenant"
PACKAGE_ID = "PKG-2026-0001"


# ---------------------------------------------------------------------------
# Flag helper
# ---------------------------------------------------------------------------


class TestIntakeGateFlag:
    def test_flag_off_by_default(self, monkeypatch):
        monkeypatch.delenv("EAGLE_INTAKE_GATE_ENABLED", raising=False)
        from app.tools.document_generation import _intake_gate_enabled

        assert _intake_gate_enabled() is False

    @pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on", "True"])
    def test_flag_on_for_truthy_values(self, monkeypatch, value):
        monkeypatch.setenv("EAGLE_INTAKE_GATE_ENABLED", value)
        from app.tools.document_generation import _intake_gate_enabled

        assert _intake_gate_enabled() is True

    @pytest.mark.parametrize("value", ["", "0", "false", "no", "off", "anything"])
    def test_flag_off_for_falsy_values(self, monkeypatch, value):
        monkeypatch.setenv("EAGLE_INTAKE_GATE_ENABLED", value)
        from app.tools.document_generation import _intake_gate_enabled

        assert _intake_gate_enabled() is False


# ---------------------------------------------------------------------------
# Refusal guard
# ---------------------------------------------------------------------------


class TestExecCreateDocumentGate:
    """When the flag is on, package-scoped doc gen must refuse without approval."""

    def test_refuses_when_flag_on_and_intake_not_approved(self, monkeypatch):
        from app.tools import document_generation as dg

        monkeypatch.setenv("EAGLE_INTAKE_GATE_ENABLED", "1")

        unapproved_pkg = {
            "package_id": PACKAGE_ID,
            "tenant_id": TENANT,
            "status": "intake",
            "intake_approved_at": None,
        }

        with mock.patch(
            "app.package_store.get_package", return_value=unapproved_pkg
        ):
            result = dg.exec_create_document(
                {"doc_type": "sow", "title": "Test", "package_id": PACKAGE_ID},
                tenant_id=TENANT,
            )

        assert isinstance(result, dict)
        assert result["error"] == "intake_not_approved"
        assert result["package_id"] == PACKAGE_ID
        assert "submit_intake_for_approval" in result["message"]
        assert result["package_status"] == "intake"

    def test_refuses_when_flag_on_and_package_missing(self, monkeypatch):
        from app.tools import document_generation as dg

        monkeypatch.setenv("EAGLE_INTAKE_GATE_ENABLED", "1")

        with mock.patch("app.package_store.get_package", return_value=None):
            result = dg.exec_create_document(
                {"doc_type": "sow", "title": "Test", "package_id": "PKG-MISSING"},
                tenant_id=TENANT,
            )

        assert result["error"] == "package_not_found"
        assert "PKG-MISSING" in result["package_id"]

    def test_passes_through_when_flag_off(self, monkeypatch):
        """Flag off (default): unapproved package should NOT trigger gate refusal.

        We verify by patching downstream so the call advances past the gate
        and into the augment step, where we abort cleanly. Reaching that
        patch proves the gate did not return the refusal payload.
        """
        from app.tools import document_generation as dg

        monkeypatch.delenv("EAGLE_INTAKE_GATE_ENABLED", raising=False)

        unapproved_pkg = {
            "package_id": PACKAGE_ID,
            "status": "intake",
            "intake_approved_at": None,
        }

        sentinel = RuntimeError("reached past-gate code")
        with (
            mock.patch("app.package_store.get_package", return_value=unapproved_pkg),
            mock.patch.object(
                dg,
                "_augment_document_data_from_context",
                side_effect=sentinel,
            ),
        ):
            with pytest.raises(RuntimeError, match="reached past-gate code"):
                dg.exec_create_document(
                    {"doc_type": "sow", "title": "Test", "package_id": PACKAGE_ID},
                    tenant_id=TENANT,
                )

    def test_passes_through_when_flag_on_but_intake_approved(self, monkeypatch):
        from app.tools import document_generation as dg

        monkeypatch.setenv("EAGLE_INTAKE_GATE_ENABLED", "1")

        approved_pkg = {
            "package_id": PACKAGE_ID,
            "status": "drafting",
            "intake_approved_at": "2026-04-30T12:00:00+00:00",
            "intake_approval_source": "user_confirmation",
        }

        sentinel = RuntimeError("reached past-gate code")
        with (
            mock.patch("app.package_store.get_package", return_value=approved_pkg),
            mock.patch.object(
                dg,
                "_augment_document_data_from_context",
                side_effect=sentinel,
            ),
        ):
            with pytest.raises(RuntimeError, match="reached past-gate code"):
                dg.exec_create_document(
                    {"doc_type": "sow", "title": "Test", "package_id": PACKAGE_ID},
                    tenant_id=TENANT,
                )

    def test_passes_through_when_flag_on_and_legacy_backfill(self, monkeypatch):
        """Legacy backfill (drafting+ pkg without explicit approval) — _serialize
        synthesises intake_approved_at on read, so the gate sees a non-empty
        value and lets the call through. This is the migration safety net."""
        from app.tools import document_generation as dg

        monkeypatch.setenv("EAGLE_INTAKE_GATE_ENABLED", "1")

        # Simulate what _serialize would return for a legacy in-flight package
        legacy_pkg = {
            "package_id": PACKAGE_ID,
            "status": "drafting",
            "created_at": "2026-03-15T09:30:00+00:00",
            "intake_approved_at": "2026-03-15T09:30:00+00:00",
            "intake_approval_source": "legacy_backfill",
        }

        sentinel = RuntimeError("reached past-gate code")
        with (
            mock.patch("app.package_store.get_package", return_value=legacy_pkg),
            mock.patch.object(
                dg,
                "_augment_document_data_from_context",
                side_effect=sentinel,
            ),
        ):
            with pytest.raises(RuntimeError, match="reached past-gate code"):
                dg.exec_create_document(
                    {"doc_type": "sow", "title": "Test", "package_id": PACKAGE_ID},
                    tenant_id=TENANT,
                )

    def test_workspace_mode_no_package_id_bypasses_gate(self, monkeypatch):
        """Calls without a package_id are workspace-scoped and never gated."""
        from app.tools import document_generation as dg

        monkeypatch.setenv("EAGLE_INTAKE_GATE_ENABLED", "1")

        sentinel = RuntimeError("reached past-gate code")
        with (
            mock.patch("app.package_store.get_package") as mock_get,
            mock.patch.object(
                dg,
                "_augment_document_data_from_context",
                side_effect=sentinel,
            ),
        ):
            with pytest.raises(RuntimeError, match="reached past-gate code"):
                dg.exec_create_document(
                    {"doc_type": "sow", "title": "Test"},  # no package_id
                    tenant_id=TENANT,
                )
            mock_get.assert_not_called()

    def test_update_existing_key_path_is_not_gated(self, monkeypatch):
        """Existing-doc updates (update_existing_key) bypass the gate — they're
        amendments to an already-generated doc, not new creation."""
        from app.tools import document_generation as dg

        monkeypatch.setenv("EAGLE_INTAKE_GATE_ENABLED", "1")

        with (
            mock.patch.object(
                dg,
                "_update_document_content",
                return_value={"updated": True},
            ),
            mock.patch("app.package_store.get_package") as mock_get,
        ):
            result = dg.exec_create_document(
                {
                    "update_existing_key": "eagle/x/y.md",
                    "content": "new body",
                    "package_id": PACKAGE_ID,  # present but irrelevant for update
                },
                tenant_id=TENANT,
            )
            assert result == {"updated": True}
            mock_get.assert_not_called()
