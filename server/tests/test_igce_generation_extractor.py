"""Tests for IGCE generation data extractor."""

import pytest

from app.igce_generation_extractor import (
    IGCEExtractionResult,
    extract_igce_data_from_text,
    extract_igce_generation_data,
    _normalize_labor_category,
    _parse_hourly_rate,
    _parse_hours,
    _parse_money,
    _parse_period_months,
    _parse_contract_type,
)


class TestParsingHelpers:
    """Tests for individual parsing functions."""

    def test_parse_money_simple(self):
        assert _parse_money("$100") == 100.0
        assert _parse_money("$1,000") == 1000.0
        assert _parse_money("$1,234.56") == 1234.56

    def test_parse_money_with_suffix(self):
        assert _parse_money("$100K") == 100_000.0
        assert _parse_money("$1.5M") == 1_500_000.0
        assert _parse_money("$2m") == 2_000_000.0

    def test_parse_money_no_match(self):
        assert _parse_money("no money here") is None
        assert _parse_money("100 dollars") is None

    def test_parse_hourly_rate(self):
        assert _parse_hourly_rate("$150/hour") == 150.0
        assert _parse_hourly_rate("$175/hr") == 175.0
        assert _parse_hourly_rate("$200 per hour") == 200.0
        assert _parse_hourly_rate("$125 hourly") == 125.0

    def test_parse_hourly_rate_no_match(self):
        assert _parse_hourly_rate("$150") is None
        assert _parse_hourly_rate("150/hour") is None

    def test_parse_hours(self):
        assert _parse_hours("500 hours") == 500
        assert _parse_hours("1,000 hrs") == 1000
        assert _parse_hours("2000 hours/year") == 2000

    def test_parse_hours_no_match(self):
        assert _parse_hours("500") is None
        assert _parse_hours("five hundred hours") is None

    def test_parse_period_months(self):
        assert _parse_period_months("12 months") == 12
        assert _parse_period_months("24-month") == 24
        assert _parse_period_months("2 years") == 24
        assert _parse_period_months("3-year contract") == 36

    def test_parse_period_months_no_match(self):
        assert _parse_period_months("no period") is None

    def test_parse_contract_type(self):
        assert _parse_contract_type("FFP contract") == "FFP"
        assert _parse_contract_type("firm fixed price") == "FFP"
        assert _parse_contract_type("T&M basis") == "T&M"
        assert _parse_contract_type("time and materials") == "T&M"
        assert _parse_contract_type("CPFF") == "CPFF"
        assert _parse_contract_type("IDIQ vehicle") == "IDIQ"

    def test_parse_contract_type_no_match(self):
        assert _parse_contract_type("some contract") is None


class TestLaborCategoryNormalization:
    """Tests for labor category normalization."""

    def test_normalize_known_categories(self):
        assert _normalize_labor_category("pm") == "project manager"
        assert _normalize_labor_category("PM") == "project manager"
        assert _normalize_labor_category("senior dev") == "senior software engineer"
        assert _normalize_labor_category("sre") == "devops engineer"

    def test_normalize_unknown_categories(self):
        assert _normalize_labor_category("Custom Role") == "Custom Role"
        assert _normalize_labor_category("specialist") == "Specialist"


class TestExtractIgceDataFromText:
    """Tests for the main extraction function."""

    def test_extract_labor_line_items(self):
        text = """
        - Project Manager: $175/hour, 500 hours
        - Senior Developer: $200/hr, 1000 hours
        - QA Engineer @ $125 per hour, 300 hours
        """
        result = extract_igce_data_from_text(text)

        assert len(result.line_items) == 3

        pm = result.line_items[0]
        assert pm["description"] == "project manager"
        assert pm["rate"] == 175.0
        assert pm["hours"] == 500

        dev = result.line_items[1]
        assert dev["description"] == "senior software engineer"
        assert dev["rate"] == 200.0
        assert dev["hours"] == 1000

    def test_extract_goods_items(self):
        text = """
        Equipment:
        - 5 servers at $10,000 each
        - 20 licenses
        - 10 laptops at $1,500 each
        """
        result = extract_igce_data_from_text(text)

        assert len(result.goods_items) >= 2

        servers = next((g for g in result.goods_items if g["product_name"] == "Server"), None)
        assert servers is not None
        assert servers["quantity"] == 5
        assert servers["unit_price"] == 10000.0

    def test_extract_contract_metadata(self):
        text = """
        12-month FFP contract with a total budget of $500,000
        """
        result = extract_igce_data_from_text(text)

        assert result.contract_type == "FFP"
        assert result.period_months == 12
        assert result.estimated_value == 500000.0

    def test_extract_prose_labor_and_delivery_context(self):
        text = """
        We need 3 developers at $150/hr for 1000 hours each on a 12-month T&M effort.
        Delivery date is 2026-09-30.
        """
        result = extract_igce_data_from_text(text)

        assert len(result.line_items) >= 1
        labor = result.line_items[0]
        assert labor["description"] == "software engineer"
        assert labor["rate"] == 150.0
        assert labor["hours"] == 3000
        assert result.contract_type == "T&M"
        assert result.period_months == 12
        assert result.delivery_date == "2026-09-30"

    def test_extract_goods_lines_with_named_products(self):
        text = """
        - AWS Licensing, 12 MO at $15,000/month
        - FedRAMP Scanner, 3 units at $2,500/unit
        """
        result = extract_igce_data_from_text(text)

        aws = next((g for g in result.goods_items if g["product_name"] == "AWS Licensing"), None)
        scanner = next((g for g in result.goods_items if g["product_name"] == "FedRAMP Scanner"), None)

        assert aws is not None
        assert aws["quantity"] == 12
        assert aws["unit_price"] == 15000.0
        assert scanner is not None
        assert scanner["quantity"] == 3
        assert scanner["unit_price"] == 2500.0

    def test_skip_non_labor_items(self):
        text = """
        - Equipment needed: various
        - Total budget: $1M
        - Contract type: FFP
        - Project Manager: $150/hr, 400 hours
        """
        result = extract_igce_data_from_text(text)

        # Should only have Project Manager, not equipment/budget/contract
        assert len(result.line_items) == 1
        assert result.line_items[0]["description"] == "project manager"

    def test_empty_text(self):
        result = extract_igce_data_from_text("")

        assert result.line_items == []
        assert result.goods_items == []
        assert result.contract_type is None
        assert result.period_months is None


class TestExtractIgceGenerationData:
    """Tests for the data merging function."""

    def test_merge_with_existing_data(self):
        existing = {
            "title": "Cloud Migration IGCE",
            "description": "Cloud migration project",
        }
        context = [
            "We need 3 developers at $150/hr for 1000 hours each",
            "12-month FFP contract",
        ]

        result = extract_igce_generation_data(existing, context_messages=context)

        # Should preserve existing data
        assert result["title"] == "Cloud Migration IGCE"
        assert result["description"] == "Cloud migration project"

        # Should add extracted data
        assert result["contract_type"] == "FFP"
        assert result["period_months"] == 12
        assert len(result.get("line_items", [])) >= 1

    def test_no_overwrite_existing_values(self):
        existing = {
            "contract_type": "T&M",
            "period_months": 24,
        }
        context = ["FFP contract for 12 months"]

        result = extract_igce_generation_data(existing, context_messages=context)

        # Should NOT overwrite existing values
        assert result["contract_type"] == "T&M"
        assert result["period_months"] == 24

    def test_no_context(self):
        existing = {"title": "Test IGCE"}

        result = extract_igce_generation_data(existing)

        # Should return existing data unchanged
        assert result == existing


class TestIGCEExtractionResult:
    """Tests for the extraction result dataclass."""

    def test_to_dict_filters_empty(self):
        result = IGCEExtractionResult(
            line_items=[{"description": "PM", "rate": 100}],
            contract_type="FFP",
        )

        d = result.to_dict()

        assert "line_items" in d
        assert "contract_type" in d
        assert "goods_items" not in d  # Empty list filtered
        assert "period_months" not in d  # None filtered


class TestBuildContextFillIntents:
    """Tests for building intents from stored source_data."""

    @pytest.fixture
    def mock_workbook(self):
        """Create a mock workbook context with empty cells."""
        from app.igce_xlsx_edit_resolver import (
            CommercialIgceWorkbookContext,
            WorkbookItem,
            WorkbookFieldTargets,
            BoundCell,
        )

        return CommercialIgceWorkbookContext(
            summary_sheet_id="0:igce",
            services_sheet_id="1:it-services",
            goods_sheet_id="2:it-goods",
            items=[
                WorkbookItem(
                    name="Cloud Architect",
                    kind="labor",
                    summary_hours=BoundCell("0:igce", "C7", "", "", True),
                    summary_rate=BoundCell("0:igce", "E7", "", "", True),
                    current_hours=None,
                    current_rate=None,
                ),
                WorkbookItem(
                    name="DevOps Engineer",
                    kind="labor",
                    summary_hours=BoundCell("0:igce", "C8", "", "", True),
                    summary_rate=BoundCell("0:igce", "E8", "", "", True),
                    current_hours=None,
                    current_rate=None,
                ),
                WorkbookItem(
                    name="AWS Licensing",
                    kind="goods",
                    goods_quantity=BoundCell("2:it-goods", "E10", "", "", True),
                    goods_unit_price=BoundCell("2:it-goods", "F10", "", "", True),
                    current_quantity=None,
                    current_unit_price=None,
                ),
            ],
            fields=WorkbookFieldTargets(
                summary_period=BoundCell("0:igce", "C5", "", "", True),
                services_contract_type=BoundCell("1:it-services", "B5", "", "", True),
                goods_contract_type=BoundCell("2:it-goods", "B5", "", "", True),
            ),
        )

    def test_fills_empty_labor_cells(self, mock_workbook):
        from app.igce_xlsx_edit_resolver import build_context_fill_intents

        source_data = {
            "line_items": [
                {"description": "Cloud Architect", "rate": 200, "hours": 1500},
            ],
            "contract_type": "FFP",
        }

        result = build_context_fill_intents(source_data, mock_workbook)

        # Should have intents for rate and hours
        intent_types = {i.intent_type for i in result.intents}
        assert "update_labor_rate" in intent_types
        assert "update_labor_hours" in intent_types

    def test_skips_filled_cells(self):
        from app.igce_xlsx_edit_resolver import (
            build_context_fill_intents,
            CommercialIgceWorkbookContext,
            WorkbookItem,
            WorkbookFieldTargets,
            BoundCell,
        )

        # Workbook with existing values
        workbook = CommercialIgceWorkbookContext(
            summary_sheet_id="0:igce",
            services_sheet_id="1:it-services",
            goods_sheet_id="2:it-goods",
            items=[
                WorkbookItem(
                    name="Cloud Architect",
                    kind="labor",
                    summary_hours=BoundCell("0:igce", "C7", "2080", "2080", True),
                    summary_rate=BoundCell("0:igce", "E7", "175", "175", True),
                    current_hours=2080,  # Already filled
                    current_rate=175,  # Already filled
                ),
            ],
            fields=WorkbookFieldTargets(
                summary_period=BoundCell("0:igce", "C5", "12", "12", True),
                services_contract_type=BoundCell("1:it-services", "B5", "FFP", "FFP", True),
            ),
        )

        source_data = {
            "line_items": [
                {"description": "Cloud Architect", "rate": 200, "hours": 1500},
            ],
            "contract_type": "T&M",
            "period_months": 18,
        }

        result = build_context_fill_intents(source_data, workbook)

        # Should have no intents (all cells already filled)
        assert len(result.intents) == 0
        # Should report skipped fields
        assert len(result.skipped_fields) > 0
        skip_reasons = {s["reason"] for s in result.skipped_fields}
        assert "already has value" in skip_reasons

    def test_reports_missing_context(self):
        from app.igce_xlsx_edit_resolver import build_context_fill_intents

        result = build_context_fill_intents(None, None)

        assert len(result.intents) == 0
        assert len(result.skipped_fields) == 1
        assert result.skipped_fields[0]["reason"] == "No origin context available"

    def test_fills_contract_type_and_period(self, mock_workbook):
        from app.igce_xlsx_edit_resolver import build_context_fill_intents

        source_data = {
            "contract_type": "Time & Materials",
            "period_months": 24,
        }

        result = build_context_fill_intents(source_data, mock_workbook)

        intent_types = {i.intent_type for i in result.intents}
        assert "update_contract_type" in intent_types
        assert "update_period_of_performance" in intent_types
