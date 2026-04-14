"""
Tests for the unify-document-tracking refactor (cozy-hugging-harbor plan).

Covers the new single-source-of-truth checklist derivation, the user-editable
required_documents_custom flag (Option D), the PATCH /required-docs surface,
the allowed-doc-type assertion guarding create_package_document_version, and
the renamed _sync_completed_documents_cache helper.

Run: pytest server/tests/test_unify_document_tracking.py -v
"""

import os
import sys
from decimal import Decimal
from unittest.mock import patch

import pytest

# Ensure server/ is on sys.path so "app.*" resolves
_server_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _server_dir not in sys.path:
    sys.path.insert(0, _server_dir)


# ══════════════════════════════════════════════════════════════════════
# Phase D — allowed_doc_types union & manifest
# ══════════════════════════════════════════════════════════════════════


class TestAllowedDocTypes:
    def test_returns_union_of_pathway_and_compliance_slugs(self):
        from app.package_store import _COMPLIANCE_DOC_TO_SLUG, _REQUIRED_DOCS, allowed_doc_types

        slugs = allowed_doc_types()
        assert isinstance(slugs, list)
        assert len(slugs) > 0
        # No duplicates
        assert len(slugs) == len(set(slugs))
        # Every pathway baseline slug must be present
        for pathway_slugs in _REQUIRED_DOCS.values():
            for slug in pathway_slugs:
                assert slug in slugs, f"pathway slug {slug!r} missing from union"
        # Every compliance-matrix slug must be present
        for slug in _COMPLIANCE_DOC_TO_SLUG.values():
            assert slug in slugs, f"compliance slug {slug!r} missing from union"

    def test_returns_sorted_list(self):
        from app.package_store import allowed_doc_types

        slugs = allowed_doc_types()
        assert slugs == sorted(slugs)

    def test_known_baselines_present(self):
        from app.package_store import allowed_doc_types

        slugs = set(allowed_doc_types())
        # Sanity check that the major doc types are recognised.
        for expected in ("sow", "igce", "market_research", "acquisition_plan"):
            assert expected in slugs


class TestDocTypeManifest:
    def test_returns_slug_label_pairs(self):
        from app.package_store import doc_type_manifest

        manifest = doc_type_manifest()
        assert isinstance(manifest, list)
        assert len(manifest) > 0
        for entry in manifest:
            assert "slug" in entry
            assert "label" in entry
            assert isinstance(entry["slug"], str)
            assert isinstance(entry["label"], str)
            assert entry["label"]  # non-empty

    def test_manifest_matches_allowed_doc_types(self):
        from app.package_store import allowed_doc_types, doc_type_manifest

        manifest_slugs = [e["slug"] for e in doc_type_manifest()]
        assert manifest_slugs == allowed_doc_types()


# ══════════════════════════════════════════════════════════════════════
# Phase B — get_package_checklist derives from DOCUMENT#
# ══════════════════════════════════════════════════════════════════════


class TestGetPackageChecklist:
    BASE_PKG = {
        "package_id": "PKG-2026-9001",
        "title": "Test Package",
        "acquisition_pathway": "full_competition",
        "required_documents": ["sow", "igce", "market_research", "acquisition_plan"],
        "required_documents_custom": False,
    }

    def _doc(self, doc_type, version=1, document_id=None):
        return {
            "doc_type": doc_type,
            "version": version,
            "document_id": document_id or f"DOC-{doc_type}-{version}",
            "status": "draft",
            "created_at": "2026-04-13T10:00:00Z",
        }

    @patch("app.package_store.get_package")
    def test_empty_when_package_missing(self, mock_get):
        from app.package_store import get_package_checklist

        mock_get.return_value = None
        result = get_package_checklist("t", "missing-pkg")
        assert result["required"] == []
        assert result["items"] == []
        assert result["extra"] == []
        assert result["complete"] is False
        assert result["custom"] is False

    @patch("app.package_store.get_package")
    def test_derives_completed_from_docs_arg(self, mock_get):
        from app.package_store import get_package_checklist

        mock_get.return_value = dict(self.BASE_PKG)
        # sow + igce exist, market_research + acquisition_plan don't
        docs = [self._doc("sow"), self._doc("igce")]

        result = get_package_checklist("t", "PKG-2026-9001", docs=docs)

        assert result["completed"] == ["sow", "igce"]
        assert result["missing"] == ["market_research", "acquisition_plan"]
        assert result["complete"] is False
        # required preserves the package's order
        assert result["required"] == ["sow", "igce", "market_research", "acquisition_plan"]

    @patch("app.package_store.get_package")
    def test_items_have_rich_shape(self, mock_get):
        from app.package_store import get_package_checklist

        mock_get.return_value = dict(self.BASE_PKG)
        docs = [self._doc("sow", version=3, document_id="DOC-sow-final")]

        result = get_package_checklist("t", "PKG-2026-9001", docs=docs)

        items_by_slug = {i["slug"]: i for i in result["items"]}
        assert items_by_slug["sow"]["status"] == "completed"
        assert items_by_slug["sow"]["document_id"] == "DOC-sow-final"
        assert items_by_slug["sow"]["version"] == 3
        assert items_by_slug["sow"]["updated_at"] == "2026-04-13T10:00:00Z"
        assert items_by_slug["sow"]["label"]  # friendly label populated
        # Pending items must not have a document_id
        assert items_by_slug["igce"]["status"] == "pending"
        assert "document_id" not in items_by_slug["igce"]

    @patch("app.package_store.get_package")
    def test_off_script_docs_surface_in_extra(self, mock_get):
        from app.package_store import get_package_checklist

        mock_get.return_value = dict(self.BASE_PKG)
        # qasp is allowed but not in required → must appear in extra[]
        docs = [self._doc("sow"), self._doc("qasp")]

        result = get_package_checklist("t", "PKG-2026-9001", docs=docs)

        extra_slugs = {e["slug"] for e in result["extra"]}
        assert "qasp" in extra_slugs
        assert "sow" not in extra_slugs  # required, not extra
        # Extras carry the same rich shape
        qasp_entry = next(e for e in result["extra"] if e["slug"] == "qasp")
        assert qasp_entry["status"] == "completed"
        assert qasp_entry["document_id"] == "DOC-qasp-1"

    @patch("app.package_store.get_package")
    def test_complete_true_when_all_required_present(self, mock_get):
        from app.package_store import get_package_checklist

        mock_get.return_value = dict(self.BASE_PKG)
        docs = [
            self._doc("sow"),
            self._doc("igce"),
            self._doc("market_research"),
            self._doc("acquisition_plan"),
        ]
        result = get_package_checklist("t", "PKG-2026-9001", docs=docs)
        assert result["complete"] is True
        assert result["missing"] == []

    @patch("app.package_store.get_package")
    def test_custom_flag_surfaced(self, mock_get):
        from app.package_store import get_package_checklist

        pkg = dict(self.BASE_PKG)
        pkg["required_documents_custom"] = True
        mock_get.return_value = pkg

        result = get_package_checklist("t", "PKG-2026-9001", docs=[])
        assert result["custom"] is True

    @patch("app.package_store.get_package")
    def test_pathway_and_title_surfaced(self, mock_get):
        from app.package_store import get_package_checklist

        mock_get.return_value = dict(self.BASE_PKG)
        result = get_package_checklist("t", "PKG-2026-9001", docs=[])
        assert result["pathway"] == "full_competition"
        assert result["title"] == "Test Package"


# ══════════════════════════════════════════════════════════════════════
# Phase B — _sync_completed_documents_cache no longer mutates required
# ══════════════════════════════════════════════════════════════════════


class TestSyncCompletedDocumentsCache:
    BASE_PKG = {
        "package_id": "PKG-2026-9002",
        "required_documents": ["sow", "igce"],
        "completed_documents": [],
    }

    @patch("app.document_service.update_package")
    @patch("app.package_document_store.list_package_documents")
    @patch("app.document_service.get_package")
    def test_writes_intersection_of_required_and_existing_docs(
        self, mock_get_pkg, mock_list_docs, mock_update
    ):
        from app.document_service import _sync_completed_documents_cache

        mock_get_pkg.return_value = dict(self.BASE_PKG)
        mock_list_docs.return_value = [
            {"doc_type": "sow", "version": 1},
            {"doc_type": "qasp", "version": 1},  # off-script — must NOT be added to required
        ]

        _sync_completed_documents_cache("t", "PKG-2026-9002")

        # update_package called once with completed_documents only — NOT with required_documents
        mock_update.assert_called_once()
        _, _, kwargs_or_payload = (
            mock_update.call_args.args[0],
            mock_update.call_args.args[1],
            mock_update.call_args.args[2],
        )
        assert "completed_documents" in kwargs_or_payload
        assert kwargs_or_payload["completed_documents"] == ["sow"]
        # Critical: required_documents must NOT be in the update payload
        assert "required_documents" not in kwargs_or_payload

    @patch("app.document_service.update_package")
    @patch("app.package_document_store.list_package_documents")
    @patch("app.document_service.get_package")
    def test_skips_write_when_cache_already_aligned(
        self, mock_get_pkg, mock_list_docs, mock_update
    ):
        from app.document_service import _sync_completed_documents_cache

        pkg = dict(self.BASE_PKG)
        pkg["completed_documents"] = ["sow"]
        mock_get_pkg.return_value = pkg
        mock_list_docs.return_value = [{"doc_type": "sow", "version": 1}]

        _sync_completed_documents_cache("t", "PKG-2026-9002")

        # No write — cache already matches.
        mock_update.assert_not_called()

    @patch("app.document_service.get_package")
    def test_noop_when_package_missing(self, mock_get_pkg):
        from app.document_service import _sync_completed_documents_cache

        mock_get_pkg.return_value = None
        # Must not raise
        _sync_completed_documents_cache("t", "missing")


# ══════════════════════════════════════════════════════════════════════
# Phase B′ — update_package respects required_documents_custom
# ══════════════════════════════════════════════════════════════════════


class TestUpdatePackageCustomFlagGuard:
    @patch("app.package_store.get_table")
    @patch("app.package_store.get_package")
    def test_custom_true_skips_required_docs_recompute(self, mock_get, mock_table):
        from app.package_store import update_package

        mock_get.return_value = {
            "package_id": "PKG-2026-9003",
            "estimated_value": "100000",
            "acquisition_method": "negotiated",
            "contract_type": "ffp",
            "required_documents": ["sow", "qasp"],  # user-curated
            "required_documents_custom": True,
            "status": "intake",
            "created_at": "2026-01-01T00:00:00Z",
        }
        mock_table.return_value.update_item.return_value = {
            "Attributes": {"package_id": "PKG-2026-9003"}
        }

        update_package("t", "PKG-2026-9003", {"estimated_value": 800_000})

        # Inspect what update_item was called with. update_package builds the
        # SET clause as `#f0 = :v0, #f1 = :v1, ...`, so the field names live in
        # ExpressionAttributeNames.values(), not in the placeholder keys.
        call = mock_table.return_value.update_item.call_args
        attr_names = call.kwargs.get("ExpressionAttributeNames", {})
        names_set = set(attr_names.values())

        # required_documents must NOT be in the payload — custom flag protects it
        assert "required_documents" not in names_set
        # Policy facts must STILL recompute when custom=True
        assert "acquisition_pathway" in names_set, (
            "policy fact (acquisition_pathway) should still recompute when custom=True"
        )

    @patch("app.package_store.get_table")
    @patch("app.package_store.get_package")
    def test_custom_false_clobbers_required_docs(self, mock_get, mock_table):
        from app.package_store import update_package

        mock_get.return_value = {
            "package_id": "PKG-2026-9004",
            "estimated_value": "100000",
            "acquisition_method": "negotiated",
            "contract_type": "ffp",
            "required_documents": ["sow"],
            "required_documents_custom": False,
            "status": "intake",
            "created_at": "2026-01-01T00:00:00Z",
        }
        mock_table.return_value.update_item.return_value = {
            "Attributes": {"package_id": "PKG-2026-9004"}
        }

        update_package("t", "PKG-2026-9004", {"estimated_value": 800_000})

        call = mock_table.return_value.update_item.call_args
        attr_names = call.kwargs.get("ExpressionAttributeNames", {})
        names_set = set(attr_names.values())
        # required_documents MUST be in the payload — recomputed from compliance matrix
        assert "required_documents" in names_set, (
            "required_documents should be recomputed when custom=False"
        )


# ══════════════════════════════════════════════════════════════════════
# Phase B′ — patch_required_docs add/remove/reset
# ══════════════════════════════════════════════════════════════════════


class TestPatchRequiredDocs:
    BASE_PKG = {
        "package_id": "PKG-2026-9005",
        "estimated_value": Decimal("500000"),
        "acquisition_method": "negotiated",
        "contract_type": "ffp",
        "acquisition_pathway": "full_competition",
        "required_documents": ["sow", "igce", "market_research", "acquisition_plan"],
        "required_documents_custom": False,
    }

    @patch("app.package_document_store.list_package_documents")
    @patch("app.package_store.update_package")
    @patch("app.package_store.get_package")
    def test_returns_none_when_package_missing(self, mock_get, mock_update, mock_list):
        from app.package_store import patch_required_docs

        mock_get.return_value = None
        result = patch_required_docs("t", "missing", add=["qasp"])
        assert result is None
        mock_update.assert_not_called()

    @patch("app.package_document_store.list_package_documents")
    @patch("app.package_store.update_package")
    @patch("app.package_store.get_package")
    def test_add_unknown_slug_raises(self, mock_get, mock_update, mock_list):
        from app.package_store import PatchRequiredDocsError, patch_required_docs

        mock_get.return_value = dict(self.BASE_PKG)
        with pytest.raises(PatchRequiredDocsError):
            patch_required_docs("t", "PKG-2026-9005", add=["totally_invented_slug"])
        mock_update.assert_not_called()

    @patch("app.package_document_store.list_package_documents")
    @patch("app.package_store.update_package")
    @patch("app.package_store.get_package")
    def test_add_appends_and_sets_custom_true(self, mock_get, mock_update, mock_list):
        from app.package_store import patch_required_docs

        # First call (top of patch_required_docs) returns the base package.
        # Second call (from get_package_checklist after the update) returns
        # the package with the new required_documents in place.
        updated_pkg = dict(self.BASE_PKG)
        updated_pkg["required_documents"] = [
            "sow", "igce", "market_research", "acquisition_plan", "qasp",
        ]
        updated_pkg["required_documents_custom"] = True
        mock_get.side_effect = [dict(self.BASE_PKG), updated_pkg]
        mock_list.return_value = []

        result = patch_required_docs("t", "PKG-2026-9005", add=["qasp"])

        assert result is not None
        # update_package should be invoked once with the new required list +
        # required_documents_custom=True.
        mock_update.assert_called_once()
        payload = mock_update.call_args.args[2]
        assert payload["required_documents"] == [
            "sow", "igce", "market_research", "acquisition_plan", "qasp",
        ]
        assert payload["required_documents_custom"] is True
        # Returned checklist has the new slug
        assert "qasp" in result["required"]
        assert result["custom"] is True
        # No remove warnings on add-only
        assert result["warnings"] == []

    @patch("app.package_document_store.list_package_documents")
    @patch("app.package_store.update_package")
    @patch("app.package_store.get_package")
    def test_remove_drops_slug(self, mock_get, mock_update, mock_list):
        from app.package_store import patch_required_docs

        updated_pkg = dict(self.BASE_PKG)
        updated_pkg["required_documents"] = ["sow", "market_research", "acquisition_plan"]
        updated_pkg["required_documents_custom"] = True
        mock_get.side_effect = [dict(self.BASE_PKG), updated_pkg]
        mock_list.return_value = []

        result = patch_required_docs("t", "PKG-2026-9005", remove=["igce"])

        payload = mock_update.call_args.args[2]
        assert "igce" not in payload["required_documents"]
        assert payload["required_documents_custom"] is True
        assert "igce" not in result["required"]
        assert result["warnings"] == []  # no backing doc → no warning

    @patch("app.package_document_store.list_package_documents")
    @patch("app.package_store.update_package")
    @patch("app.package_store.get_package")
    def test_remove_warns_when_doc_exists(self, mock_get, mock_update, mock_list):
        from app.package_store import patch_required_docs

        updated_pkg = dict(self.BASE_PKG)
        updated_pkg["required_documents"] = ["igce", "market_research", "acquisition_plan"]
        updated_pkg["required_documents_custom"] = True
        mock_get.side_effect = [dict(self.BASE_PKG), updated_pkg]
        mock_list.return_value = [{"doc_type": "sow", "version": 1, "document_id": "D1"}]

        result = patch_required_docs("t", "PKG-2026-9005", remove=["sow"])

        assert result["warnings"], "removing a slug with an existing doc must warn"
        assert any("sow" in w for w in result["warnings"])

    @patch("app.package_document_store.list_package_documents")
    @patch("app.package_store.update_package")
    @patch("app.package_store.get_package")
    def test_reset_clears_custom_and_recomputes(self, mock_get, mock_update, mock_list):
        from app.package_store import patch_required_docs

        custom_pkg = dict(self.BASE_PKG)
        custom_pkg["required_documents"] = ["sow", "qasp"]
        custom_pkg["required_documents_custom"] = True

        # After reset, package is back to the policy baseline.
        reset_pkg = dict(self.BASE_PKG)
        reset_pkg["required_documents_custom"] = False
        mock_get.side_effect = [custom_pkg, reset_pkg]
        mock_list.return_value = []

        result = patch_required_docs("t", "PKG-2026-9005", reset=True)

        mock_update.assert_called_once()
        payload = mock_update.call_args.args[2]
        assert payload["required_documents_custom"] is False
        # required_documents should be present in the reset payload
        assert "required_documents" in payload
        assert result["custom"] is False


# ══════════════════════════════════════════════════════════════════════
# Phase D — create_package_document_version rejects invented slugs
# ══════════════════════════════════════════════════════════════════════


class TestCreatePackageDocumentVersionAllowedSlugs:
    @patch("app.document_service.get_package")
    def test_rejects_unknown_doc_type(self, mock_get_pkg):
        from app.document_service import create_package_document_version

        mock_get_pkg.return_value = {
            "package_id": "PKG-2026-9006",
            "required_documents": ["sow"],
        }

        result = create_package_document_version(
            tenant_id="t",
            package_id="PKG-2026-9006",
            doc_type="totally_invented_slug",
            content="# hi",
            title="Bogus",
            file_type="md",
        )

        assert result.success is False
        assert "Unknown doc_type" in (result.error or "")

    @patch("app.document_service.get_package")
    def test_rejects_missing_package_before_doc_type_check(self, mock_get_pkg):
        from app.document_service import create_package_document_version

        mock_get_pkg.return_value = None

        result = create_package_document_version(
            tenant_id="t",
            package_id="missing",
            doc_type="sow",  # would be valid otherwise
            content="# hi",
            title="x",
            file_type="md",
        )

        assert result.success is False
        assert "not found" in (result.error or "").lower()
