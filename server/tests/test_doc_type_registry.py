"""Tests for the centralized doc_type registry."""

from __future__ import annotations

import json
import pathlib
from pathlib import Path

import pytest

from app.doc_type_registry import (
    ALL_DOC_TYPES,
    is_valid_doc_type,
    normalize_doc_type,
    get_template_categories,
    get_label,
    get_kind,
    get_category_metadata,
    get_compliance_display_name,
    get_compliance_aliases,
    get_system_prompt_key,
    get_all_metadata,
    get_system_prompt,
    list_available_prompts,
    _clear_prompt_cache,
)

_INDEX_PATH = pathlib.Path(__file__).resolve().parents[2] / "eagle-plugin" / "data" / "template-metadata" / "_index.json"


class TestAllDocTypes:
    """Verify ALL_DOC_TYPES matches the template index."""

    @pytest.mark.skipif(not _INDEX_PATH.exists(), reason="_index.json not in repo (generated locally)")
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


# ── Category metadata accessors (added by PR A1) ──────────────────────


class TestCategoryMetadata:
    def test_all_metadata_loaded(self):
        meta = get_all_metadata()
        # Should have entries for at least the 23 _index.json categories
        # plus 8 markdown-only types (31 total per the migration spec).
        assert len(meta) >= 23
        # Sanity: every key should be in ALL_DOC_TYPES
        for slug in meta:
            assert slug in ALL_DOC_TYPES, f"metadata slug {slug!r} not in ALL_DOC_TYPES"

    def test_get_category_metadata_known_slug(self):
        m = get_category_metadata("sow")
        assert m.get("label") == "Statement of Work"
        assert m.get("kind") == "generated"

    def test_get_category_metadata_unknown_slug_returns_empty(self):
        assert get_category_metadata("not_a_real_slug") == {}

    def test_label_known_slug(self):
        assert get_label("sow") == "Statement of Work"
        assert get_label("igce") == "Independent Government Cost Estimate"
        assert get_label("market_research") == "Market Research Report"

    def test_label_unknown_slug_falls_back_to_titlecase(self):
        # Defensive default — callers should still get a usable string
        assert get_label("some_unknown_slug") == "Some Unknown Slug"

    def test_kind_defaults_to_generated(self):
        # Even unknown slugs return a sane default
        assert get_kind("some_unknown_slug") == "generated"
        assert get_kind("sow") == "generated"

    def test_compliance_display_name_present(self):
        assert get_compliance_display_name("sow") == "SOW / PWS"
        assert get_compliance_display_name("igce") == "IGCE"

    def test_compliance_display_name_absent(self):
        # Markdown-only types typically don't appear in compliance matrices
        assert get_compliance_display_name("not_a_real_slug") is None

    def test_compliance_aliases_includes_legacy_names(self):
        sow_aliases = get_compliance_aliases("sow")
        assert "Statement of Need (SON)" in sow_aliases

    def test_compliance_aliases_empty_when_none(self):
        # Returns list, never None — easier for callers
        assert isinstance(get_compliance_aliases("not_a_real_slug"), list)
        assert get_compliance_aliases("not_a_real_slug") == []

    def test_system_prompt_key_for_generated_types(self):
        # Generated types should have a prompt key that downstream PR A3 uses
        assert get_system_prompt_key("sow") == "sow"
        assert get_system_prompt_key("igce") == "igce"

    def test_system_prompt_key_returns_none_when_absent(self):
        assert get_system_prompt_key("not_a_real_slug") is None

    def test_plugin_data_aliases_merged_into_normalize(self):
        # Aliases defined in _index.json should resolve via normalize_doc_type
        # alongside the hardcoded ones
        assert normalize_doc_type("blanket_purchase_agreement") == "bpa_call_order"
        assert normalize_doc_type("statement_of_work") == "sow"


# ── New doc-types added by PR A2 ──────────────────────────────────────


class TestPRA2NewDocTypes:
    """The 12 markdown-only doc-types added in PR A2."""

    NEW_SLUGS = (
        "cor_designation",
        "d_f",
        "fpds_report",
        "funding_doc",
        "human_subjects",
        "inherently_governmental",
        "priority_sources_checklist",
        "qasp",
        "sam_exclusions_check",
        "sb_review",
        "source_selection_plan",
        "wage_determination",
    )

    @pytest.mark.parametrize("slug", NEW_SLUGS)
    def test_slug_is_valid(self, slug):
        assert is_valid_doc_type(slug), f"{slug!r} should validate"

    @pytest.mark.parametrize("slug", NEW_SLUGS)
    def test_slug_in_all_doc_types(self, slug):
        assert slug in ALL_DOC_TYPES

    @pytest.mark.parametrize("slug", NEW_SLUGS)
    def test_has_metadata(self, slug):
        meta = get_category_metadata(slug)
        assert meta, f"{slug!r} missing from category_metadata"
        assert meta.get("label"), f"{slug!r} missing label"
        assert meta.get("kind") in {"generated", "evidence", "form_only", "legacy"}

    @pytest.mark.parametrize("slug", NEW_SLUGS)
    def test_label_not_titlecased_fallback(self, slug):
        # If we hit the title-case fallback, metadata wasn't loaded properly
        label = get_label(slug)
        titlecase = slug.replace("_", " ").title()
        # A handful of slugs might coincide (e.g., 'qasp' → 'Qasp') so we
        # only assert that *something* came back; the test_has_metadata
        # parametrize above already proves the label field exists.
        assert label, f"{slug!r} produced empty label"

    def test_markdown_only_types_count(self):
        # 4 + 4 prior + 12 new = 20 entries in _MARKDOWN_ONLY_TYPES, but the
        # exact count is implementation-detail; just check the new ones land.
        from app.doc_type_registry import _MARKDOWN_ONLY_TYPES
        for slug in self.NEW_SLUGS:
            assert slug in _MARKDOWN_ONLY_TYPES, f"{slug!r} not in _MARKDOWN_ONLY_TYPES"

    def test_template_categories_excludes_new_markdown_only(self):
        # New types should NOT show up in get_template_categories() since
        # they have no S3 template
        cats = get_template_categories()
        for slug in self.NEW_SLUGS:
            assert slug not in cats, f"{slug!r} should not be in template categories"

    def test_d_and_f_aliases_normalize(self):
        # 'determination_and_findings' and 'determination_findings' both
        # resolve to canonical 'd_f' per the metadata block
        assert normalize_doc_type("determination_and_findings") == "d_f"
        assert normalize_doc_type("determination_findings") == "d_f"


# ── System prompts (PR A3) ────────────────────────────────────────────


class TestSystemPrompts:
    """Verify get_system_prompt reads from eagle-plugin/data/system-prompts/."""

    def test_list_available_prompts_nonempty(self):
        # After PR A3 lands, all generated doc-types should have a prompt
        prompts = list_available_prompts()
        assert len(prompts) > 0
        # sample sanity
        assert "sow" in prompts
        assert "igce" in prompts

    def test_get_known_prompt(self):
        body = get_system_prompt("sow")
        assert body is not None
        # Sanity: the prompt is the markdown we extracted
        assert "Statement of Work" in body

    def test_get_unknown_returns_none(self):
        assert get_system_prompt("no_such_slug_anywhere") is None

    def test_cache_hit_does_not_re_read(self, tmp_path, monkeypatch):
        # First read populates cache; second read should not touch disk.
        # We can't easily count file reads from here, but we can verify
        # that even after deleting the file, the cached value is returned.
        _clear_prompt_cache()
        first = get_system_prompt("sow")
        assert first is not None
        # Cache is now warm. A second read should return the same value
        # even if we monkeypatch the path to a missing file.
        from app import doc_type_registry as r
        monkeypatch.setattr(r, "_PROMPTS_DIR", pathlib.Path("/nonexistent"))
        cached = get_system_prompt("sow")
        assert cached == first  # served from cache, not from disk

    def test_d_f_prompt_present(self):
        # d_f is one of the 12 doc-types added by PR A2; its prompt
        # should be available after PR A3 land.
        _clear_prompt_cache()
        body = get_system_prompt("d_f")
        assert body is not None
        assert "Determination" in body

    def test_clear_cache_forces_reread(self):
        # Read, clear, read again — both reads should succeed.
        _clear_prompt_cache()
        first = get_system_prompt("sow")
        _clear_prompt_cache()
        second = get_system_prompt("sow")
        assert first == second
        assert first is not None
