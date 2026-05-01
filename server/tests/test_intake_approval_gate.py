"""Tests for the intake-approval gate primitives in package_store.

Validates:
  - _serialize() backfills intake_approved_at for legacy drafting+ packages
    so the new gate doesn't reject in-flight work
  - mark_intake_approved() stamps the four gate fields, transitions
    intake → drafting, and writes an audit event
  - mark_intake_approved() is idempotent (no-op on already-approved)
  - mark_intake_approved() upgrades a legacy-backfilled package to a real
    user_confirmation approval
  - mark_intake_approved() returns None for missing packages
"""
from unittest import mock

TENANT = "test-tenant"
USER = "test-user"
PACKAGE_ID = "PKG-2026-0001"

INTAKE_PACKAGE = {
    "package_id": PACKAGE_ID,
    "tenant_id": TENANT,
    "title": "Test Acquisition",
    "status": "intake",
    "estimated_value": "5000",
    "created_at": "2026-04-01T12:00:00+00:00",
}

LEGACY_DRAFTING_PACKAGE = {
    "package_id": PACKAGE_ID,
    "tenant_id": TENANT,
    "title": "Legacy Acquisition",
    "status": "drafting",
    "estimated_value": "5000",
    "created_at": "2026-03-15T09:30:00+00:00",
    # No intake_approved_at — pre-dates the new field
}


# ---------------------------------------------------------------------------
# TestSerializeBackfill
# ---------------------------------------------------------------------------


class TestSerializeBackfill:
    """_serialize() must derive intake_approved_at for legacy drafting+ pkgs."""

    def test_intake_status_does_not_backfill(self):
        from app.package_store import _serialize

        out = _serialize(dict(INTAKE_PACKAGE))
        # Status=intake → no auto-approval. Gate should still refuse generation.
        assert out.get("intake_approved_at") is None
        assert out.get("intake_approval_source") is None

    def test_drafting_status_backfills_from_created_at(self):
        from app.package_store import _serialize

        out = _serialize(dict(LEGACY_DRAFTING_PACKAGE))
        assert out["intake_approved_at"] == LEGACY_DRAFTING_PACKAGE["created_at"]
        assert out["intake_approval_source"] == "legacy_backfill"

    def test_finalizing_review_approved_all_backfill(self):
        from app.package_store import _serialize

        for status in ("finalizing", "review", "approved"):
            pkg = dict(LEGACY_DRAFTING_PACKAGE, status=status)
            out = _serialize(pkg)
            assert out["intake_approved_at"] == pkg["created_at"], status
            assert out["intake_approval_source"] == "legacy_backfill", status

    def test_existing_intake_approved_at_is_preserved(self):
        """If a real approval already exists, backfill must not overwrite it."""
        from app.package_store import _serialize

        pkg = dict(
            LEGACY_DRAFTING_PACKAGE,
            intake_approved_at="2026-04-30T10:00:00+00:00",
            intake_approval_source="user_confirmation",
        )
        out = _serialize(pkg)
        assert out["intake_approved_at"] == "2026-04-30T10:00:00+00:00"
        assert out["intake_approval_source"] == "user_confirmation"


# ---------------------------------------------------------------------------
# TestMarkIntakeApproved
# ---------------------------------------------------------------------------


class TestMarkIntakeApproved:
    """mark_intake_approved() must stamp gate fields, advance status, audit."""

    def test_happy_path_stamps_fields_and_transitions_status(self):
        from app.package_store import mark_intake_approved

        summary = {
            "requirement_description": "CT scanner",
            "estimated_value": "500000",
            "required_documents": ["sow", "igce"],
        }
        captured: dict = {}

        def fake_update(tenant, pkg_id, updates):
            captured["updates"] = updates
            return {**INTAKE_PACKAGE, **updates}

        with (
            mock.patch("app.package_store.get_package", return_value=dict(INTAKE_PACKAGE)),
            mock.patch("app.package_store.update_package", side_effect=fake_update),
            mock.patch("app.audit_store.write_audit") as mock_audit,
        ):
            result = mark_intake_approved(TENANT, PACKAGE_ID, USER, summary)

        assert result is not None
        assert captured["updates"]["intake_approved_by"] == USER
        assert captured["updates"]["intake_summary"] == summary
        assert captured["updates"]["intake_approval_source"] == "user_confirmation"
        assert captured["updates"]["status"] == "drafting"
        assert "intake_approved_at" in captured["updates"]

        mock_audit.assert_called_once()
        audit_kwargs = mock_audit.call_args.kwargs
        assert audit_kwargs["event_type"] == "intake_approved"
        assert audit_kwargs["entity_type"] == "package"
        assert audit_kwargs["entity_name"] == PACKAGE_ID
        assert audit_kwargs["actor_user_id"] == USER
        assert audit_kwargs["metadata"]["source"] == "user_confirmation"

    def test_returns_none_when_package_missing(self):
        from app.package_store import mark_intake_approved

        with mock.patch("app.package_store.get_package", return_value=None):
            result = mark_intake_approved(TENANT, "PKG-MISSING", USER, {})

        assert result is None

    def test_idempotent_when_already_approved(self):
        """A second user_confirmation call on an approved package is a no-op."""
        from app.package_store import mark_intake_approved

        already_approved = dict(
            INTAKE_PACKAGE,
            status="drafting",
            intake_approved_at="2026-04-30T10:00:00+00:00",
            intake_approval_source="user_confirmation",
        )
        with (
            mock.patch("app.package_store.get_package", return_value=already_approved),
            mock.patch("app.package_store.update_package") as mock_update,
            mock.patch("app.audit_store.write_audit"),
        ):
            result = mark_intake_approved(TENANT, PACKAGE_ID, USER, {})

        # Existing record returned untouched; no UPDATE issued
        assert result == already_approved
        mock_update.assert_not_called()

    def test_legacy_backfilled_package_is_upgraded_to_real_approval(self):
        """A legacy_backfill source must NOT block a real user_confirmation."""
        from app.package_store import mark_intake_approved

        legacy = dict(
            LEGACY_DRAFTING_PACKAGE,
            intake_approved_at="2026-03-15T09:30:00+00:00",
            intake_approval_source="legacy_backfill",
        )

        captured: dict = {}

        def fake_update(tenant, pkg_id, updates):
            captured["updates"] = updates
            return {**legacy, **updates}

        with (
            mock.patch("app.package_store.get_package", return_value=legacy),
            mock.patch("app.package_store.update_package", side_effect=fake_update),
            mock.patch("app.audit_store.write_audit"),
        ):
            result = mark_intake_approved(
                TENANT, PACKAGE_ID, USER, {"requirement_description": "x"}
            )

        assert result is not None
        # Real approval overwrote the synthetic one
        assert captured["updates"]["intake_approval_source"] == "user_confirmation"
        assert captured["updates"]["intake_approved_by"] == USER
        # status was already drafting — no transition needed
        assert "status" not in captured["updates"]

    def test_slash_bypass_source_is_recorded(self):
        from app.package_store import mark_intake_approved

        captured: dict = {}

        def fake_update(tenant, pkg_id, updates):
            captured["updates"] = updates
            return {**INTAKE_PACKAGE, **updates}

        with (
            mock.patch("app.package_store.get_package", return_value=dict(INTAKE_PACKAGE)),
            mock.patch("app.package_store.update_package", side_effect=fake_update),
            mock.patch("app.audit_store.write_audit") as mock_audit,
        ):
            mark_intake_approved(TENANT, PACKAGE_ID, USER, {}, source="slash_bypass")

        assert captured["updates"]["intake_approval_source"] == "slash_bypass"
        assert mock_audit.call_args.kwargs["metadata"]["source"] == "slash_bypass"

    def test_audit_failure_does_not_break_approval(self):
        """An audit-store outage must not block the gate from opening."""
        from app.package_store import mark_intake_approved

        with (
            mock.patch("app.package_store.get_package", return_value=dict(INTAKE_PACKAGE)),
            mock.patch(
                "app.package_store.update_package",
                return_value=dict(INTAKE_PACKAGE, status="drafting"),
            ),
            mock.patch(
                "app.audit_store.write_audit", side_effect=RuntimeError("ddb down")
            ),
        ):
            result = mark_intake_approved(TENANT, PACKAGE_ID, USER, {})

        assert result is not None  # approval succeeded despite audit failure


# ---------------------------------------------------------------------------
# TestUpdatableFields
# ---------------------------------------------------------------------------


class TestUpdatableFields:
    """The new intake-approval fields must be in the _UPDATABLE_FIELDS allowlist."""

    def test_intake_approval_fields_are_updatable(self):
        from app.package_store import _UPDATABLE_FIELDS

        for field in (
            "intake_approved_at",
            "intake_approved_by",
            "intake_summary",
            "intake_approval_source",
            "intake_proposed_summary",
        ):
            assert field in _UPDATABLE_FIELDS, f"{field} missing from _UPDATABLE_FIELDS"
