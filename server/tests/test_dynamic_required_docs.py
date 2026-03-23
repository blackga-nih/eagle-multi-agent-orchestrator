"""Tests for dynamic required documents (Feature 1) and descriptive titles (Feature 2)."""
import pytest
from decimal import Decimal
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Feature 1 — compute_required_docs
# ---------------------------------------------------------------------------

class TestComputeRequiredDocs:
    """Test compliance-matrix-driven dynamic document requirements."""

    def test_negotiated_ffp_500k_returns_expected_slugs(self):
        """Negotiated FFP at $500K should include SOW, IGCE, market research, AP, SSP, etc."""
        from app.package_store import compute_required_docs

        slugs = compute_required_docs(
            estimated_value=500_000,
            acquisition_method="negotiated",
            contract_type="ffp",
            flags={"is_services": True},
        )
        assert "sow" in slugs
        assert "igce" in slugs
        assert "market-research" in slugs
        assert "acquisition-plan" in slugs
        assert "source-selection-plan" in slugs

    def test_micro_purchase_returns_minimal_list(self):
        """Micro-purchase ($5K) should only require purchase-request and sb-review at most."""
        from app.package_store import compute_required_docs

        slugs = compute_required_docs(
            estimated_value=5_000,
            acquisition_method="micro",
            contract_type="ffp",
        )
        # Micro-purchase: SOW/IGCE/market-research are not required
        assert "sow" not in slugs
        assert "igce" not in slugs
        assert "market-research" not in slugs

    def test_sole_source_includes_justification(self):
        """Sole source acquisition should include justification document."""
        from app.package_store import compute_required_docs

        slugs = compute_required_docs(
            estimated_value=500_000,
            acquisition_method="sole",
            contract_type="ffp",
        )
        assert "justification" in slugs

    def test_it_flags_include_security_and_508(self):
        """IT acquisitions should include security checklist and Section 508."""
        from app.package_store import compute_required_docs

        slugs = compute_required_docs(
            estimated_value=500_000,
            acquisition_method="negotiated",
            contract_type="ffp",
            flags={"is_it": True, "is_services": True},
        )
        assert "security-checklist" in slugs
        assert "section-508" in slugs

    def test_fallback_to_static_on_compliance_error(self):
        """When compliance matrix raises, should fall back to static docs."""
        from app.package_store import compute_required_docs

        with patch("app.compliance_matrix.get_requirements", side_effect=RuntimeError("boom")):
            # This should not raise — it falls back
            slugs = compute_required_docs(
                estimated_value=500_000,
                acquisition_method="negotiated",
                contract_type="ffp",
            )
            # Static full_competition fallback
            assert "sow" in slugs
            assert "igce" in slugs

    def test_all_compliance_doc_names_have_slug_mapping(self):
        """Every document name returned by get_requirements should have a slug mapping."""
        from app.compliance_matrix import get_requirements
        from app.package_store import _COMPLIANCE_DOC_TO_SLUG

        result = get_requirements(
            contract_value=1_000_000,
            acquisition_method="negotiated",
            contract_type="cpff",
            flags={"is_it": True, "is_services": True, "is_human_subjects": True},
        )

        for doc in result["documents_required"]:
            name = doc["name"]
            assert name in _COMPLIANCE_DOC_TO_SLUG, (
                f"Compliance matrix doc '{name}' has no slug mapping"
            )


class TestCreatePackageWithDynamicDocs:
    """Test create_package with dynamic docs parameters."""

    @patch("app.package_store._get_table")
    @patch("app.package_store._next_package_id", return_value="PKG-2026-0001")
    def test_create_with_method_and_type_uses_dynamic_docs(self, mock_id, mock_table):
        """When acquisition_method and contract_type provided, use compliance matrix."""
        from app.package_store import create_package

        mock_table.return_value.put_item = MagicMock()

        result = create_package(
            tenant_id="test-tenant",
            owner_user_id="user-1",
            title="Test",
            requirement_type="services",
            estimated_value=Decimal("500000"),
            acquisition_method="negotiated",
            contract_type="ffp",
            flags={"is_services": True},
        )

        assert "sow" in result["required_documents"]
        assert "acquisition-plan" in result["required_documents"]
        assert result.get("acquisition_method") == "negotiated"
        assert result.get("contract_type") == "ffp"

    @patch("app.package_store._get_table")
    @patch("app.package_store._next_package_id", return_value="PKG-2026-0001")
    def test_create_without_method_falls_back_to_static(self, mock_id, mock_table):
        """Without method/type, should use static pathway-based docs."""
        from app.package_store import create_package

        mock_table.return_value.put_item = MagicMock()

        result = create_package(
            tenant_id="test-tenant",
            owner_user_id="user-1",
            title="Test",
            requirement_type="services",
            estimated_value=Decimal("500000"),
        )

        # Static full_competition docs
        assert result["required_documents"] == ["sow", "igce", "market-research", "acquisition-plan"]


class TestUpdatePackageRecalculation:
    """Test that update_package recalculates docs on method/type change."""

    @patch("app.package_store._get_table")
    @patch("app.package_store.get_package")
    def test_update_acquisition_method_recalculates_docs(self, mock_get, mock_table):
        """Changing acquisition_method should trigger doc recalculation."""
        from app.package_store import update_package

        mock_get.return_value = {
            "package_id": "PKG-2026-0001",
            "estimated_value": "500000",
            "acquisition_method": "sap",
            "contract_type": "ffp",
            "status": "intake",
            "created_at": "2026-01-01T00:00:00Z",
        }
        mock_table.return_value.update_item.return_value = {
            "Attributes": {
                "package_id": "PKG-2026-0001",
                "required_documents": ["sow", "igce", "market-research"],
                "acquisition_method": "negotiated",
            }
        }

        result = update_package(
            "test-tenant", "PKG-2026-0001",
            {"acquisition_method": "negotiated"},
        )

        # update_item should have been called
        mock_table.return_value.update_item.assert_called_once()

    @patch("app.package_store._get_table")
    @patch("app.package_store.get_package")
    def test_update_estimated_value_recalculates_docs(self, mock_get, mock_table):
        """Changing estimated_value should trigger doc recalculation."""
        from app.package_store import update_package

        mock_get.return_value = {
            "package_id": "PKG-2026-0001",
            "estimated_value": "100000",
            "acquisition_method": "negotiated",
            "contract_type": "ffp",
            "status": "intake",
            "created_at": "2026-01-01T00:00:00Z",
        }
        mock_table.return_value.update_item.return_value = {
            "Attributes": {
                "package_id": "PKG-2026-0001",
                "required_documents": ["sow", "igce", "market-research"],
                "estimated_value": Decimal("500000"),
            }
        }

        result = update_package(
            "test-tenant", "PKG-2026-0001",
            {"estimated_value": 500_000},
        )

        mock_table.return_value.update_item.assert_called_once()


# ---------------------------------------------------------------------------
# Feature 2 — Descriptive Package Title
# ---------------------------------------------------------------------------

class TestDescriptiveTitle:
    """Test _generate_descriptive_title helper."""

    def test_generic_title_is_replaced(self):
        from app.package_store import _generate_descriptive_title

        result = _generate_descriptive_title(
            "Acquisition Package", "services", Decimal("500000")
        )
        assert "Services" in result
        assert "$500K" in result

    def test_specific_title_preserved(self):
        from app.package_store import _generate_descriptive_title

        long_title = "Custom Cloud Infrastructure Procurement for NCI CBIIT"
        result = _generate_descriptive_title(long_title, "services", Decimal("1000000"))
        assert result == long_title

    def test_value_formatting_500k_1m_800(self):
        from app.package_store import _generate_descriptive_title

        assert "$500K" in _generate_descriptive_title("Test", "services", Decimal("500000"))
        assert "$1.0M" in _generate_descriptive_title("Test", "services", Decimal("1000000"))
        assert "$800" in _generate_descriptive_title("Test", "supplies", Decimal("800"))

    def test_contract_vehicle_appended(self):
        from app.package_store import _generate_descriptive_title

        result = _generate_descriptive_title(
            "Test", "services", Decimal("500000"), "GSA"
        )
        assert "[GSA]" in result

    @patch("app.package_store._get_table")
    @patch("app.package_store._next_package_id", return_value="PKG-2026-0001")
    def test_original_title_stored(self, mock_id, mock_table):
        """create_package should store the original title."""
        from app.package_store import create_package

        mock_table.return_value.put_item = MagicMock()

        result = create_package(
            tenant_id="t", owner_user_id="u",
            title="Test",
            requirement_type="services",
            estimated_value=Decimal("500000"),
        )
        assert result["original_title"] == "Test"
        assert result["title"] != "Test"  # Should be descriptive
