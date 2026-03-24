"""Tests for the centralized doc_type registry."""

from __future__ import annotations

import json
from pathlib import Path

from app.doc_type_registry import (
    ALL_DOC_TYPES,
    is_valid_doc_type,
    normalize_doc_type,
    get_template_categories,
)


class TestAllDocTypes:
    """Verify ALL_DOC_TYPES matches the template index."""

    def test_all_22_index_categories_present(self):
        index_path = Path(__file__).resolve().parent.parent.parent / "eagle-plugin" / "data" / "template-metadata" / "_index.json"
        with open(index_path, encoding="utf-8") as f:
            index = json.load(f)
        categories = set(index["by_category"].keys())
        for cat in categories:
            assert cat in ALL_DOC_TYPES, f"Missing category: {cat}"

    def test_minimum_count(self):
        # 22 from index + 4 markdown-only = 26 minimum
        assert len(ALL_DOC_TYPES) >= 26

    def test_markdown_only_types_included(self):
        for dt in ("eval_criteria", "security_checklist", "section_508", "contract_type_justification"):
            assert dt in ALL_DOC_TYPES

    def test_template_categories_excludes_markdown_only(self):
        cats = get_template_categories()
        assert "eval_criteria" not in cats
        assert "sow" in cats


class TestNormalizeDocType:
    """Test normalization of raw doc_type strings."""

    def test_hyphens_to_underscores(self):
        assert normalize_doc_type("acquisition-plan") == "acquisition_plan"

    def test_spaces_to_underscores(self):
        assert normalize_doc_type("market research") == "market_research"

    def test_case_insensitive(self):
        assert normalize_doc_type("SOW") == "sow"
        assert normalize_doc_type("IGCE") == "igce"

    def test_alias_ige(self):
        assert normalize_doc_type("ige") == "igce"

    def test_alias_ja(self):
        assert normalize_doc_type("j&a") == "justification"
        assert normalize_doc_type("ja") == "justification"

    def test_alias_son_products(self):
        assert normalize_doc_type("son-products") == "son_products"
        assert normalize_doc_type("statement_of_need_products") == "son_products"

    def test_alias_son_services(self):
        assert normalize_doc_type("statement_of_need_services") == "son_services"

    def test_alias_cor(self):
        assert normalize_doc_type("cor") == "cor_certification"
        assert normalize_doc_type("cor-appointment") == "cor_certification"

    def test_alias_subk(self):
        assert normalize_doc_type("subcontracting-plan") == "subk_plan"
        assert normalize_doc_type("sub_k_review") == "subk_review"

    def test_alias_bpa(self):
        assert normalize_doc_type("bpa") == "bpa_call_order"

    def test_alias_gfp(self):
        assert normalize_doc_type("gfp") == "gfp_form"

    def test_passthrough_for_valid(self):
        assert normalize_doc_type("sow") == "sow"
        assert normalize_doc_type("buy_american") == "buy_american"

    def test_empty_string(self):
        assert normalize_doc_type("") == ""

    def test_unknown_returns_as_is(self):
        assert normalize_doc_type("random_thing") == "random_thing"


class TestIsValidDocType:
    def test_valid_core_types(self):
        for dt in ("sow", "igce", "market_research", "justification", "acquisition_plan"):
            assert is_valid_doc_type(dt) is True

    def test_valid_extended_types(self):
        for dt in ("son_products", "cor_certification", "buy_american", "subk_plan"):
            assert is_valid_doc_type(dt) is True

    def test_valid_via_alias(self):
        assert is_valid_doc_type("ige") is True
        assert is_valid_doc_type("j&a") is True

    def test_valid_via_hyphen(self):
        assert is_valid_doc_type("acquisition-plan") is True

    def test_invalid(self):
        assert is_valid_doc_type("not_a_real_type") is False
        assert is_valid_doc_type("") is False
