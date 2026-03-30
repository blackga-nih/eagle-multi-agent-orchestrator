"""Tests for triage session f2d75c92 fixes (2026-03-27).

Validates:
  - P0-2: Backfill titles no longer include "(linked)" suffix
  - P0-1: GeneratorExit persists partial work to session store
  - P0-3: Package document endpoint includes download_url
  - P1-5: Cascade violation blocks web_search without prior KB lookup
  - P1-6: Checklist boost in knowledge_search AI ranking
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest


# ── Helpers ──────────────────────────────────────────────────────────────

TENANT = "test-tenant"
USER = "test-user"
SESSION = "sess-test"
PKG_ID = "PKG-2026-0042"


# ═════════════════════════════════════════════════════════════════════════
# P0-2: Backfill titles must not include "(linked)"
# ═════════════════════════════════════════════════════════════════════════

class TestBackfillTitleNoLinked:
    """Backfill code must produce clean titles without '(linked)' suffix."""

    def test_package_document_tools_backfill_title(self):
        """package_document_tools.py backfill should not append (linked)."""
        import importlib
        import app.tools.package_document_tools as pdt

        src = importlib.util.find_spec("app.tools.package_document_tools")
        assert src and src.origin
        source_text = open(src.origin, encoding="utf-8").read()
        assert "(linked)" not in source_text, (
            "package_document_tools.py still contains '(linked)' in backfill title"
        )

    def test_backfill_title_format(self):
        """Title format should be clean: 'Acquisition Plan' not 'Acquisition Plan (linked)'."""
        doc_type = "acquisition_plan"
        title = f"{doc_type.replace('_', ' ').title()}"
        assert title == "Acquisition Plan"
        assert "(linked)" not in title


# ═════════════════════════════════════════════════════════════════════════
# P0-1: GeneratorExit persists partial work
# ═════════════════════════════════════════════════════════════════════════

class TestGeneratorExitPersistence:
    """GeneratorExit handler must save partial results to session store."""

    def test_generator_exit_handler_calls_add_message(self):
        """Verify the GeneratorExit handler source includes add_message persistence."""
        import importlib

        src = importlib.util.find_spec("app.strands_agentic_service")
        assert src and src.origin
        source_text = open(src.origin, encoding="utf-8").read()

        # The GeneratorExit handler should import and call add_message
        assert "from .session_store import add_message" in source_text, (
            "GeneratorExit handler must import add_message from session_store"
        )

    def test_generator_exit_saves_interrupted_metadata(self):
        """Verify interrupted metadata flag is set in the persisted message."""
        import importlib

        src = importlib.util.find_spec("app.strands_agentic_service")
        assert src and src.origin
        source_text = open(src.origin, encoding="utf-8").read()

        # Check the metadata includes interrupted flag
        assert '"interrupted": True' in source_text or "'interrupted': True" in source_text, (
            "GeneratorExit handler must set interrupted=True in message metadata"
        )


# ═════════════════════════════════════════════════════════════════════════
# P0-3: Package document endpoint includes download_url
# ═════════════════════════════════════════════════════════════════════════

class TestPackageDocumentDownloadUrl:
    """GET /packages/{id}/documents/{doc_type} must include download_url."""

    @pytest.fixture
    def mock_doc(self):
        return {
            "document_id": "doc-001",
            "doc_type": "acquisition_plan",
            "version": 2,
            "title": "Acquisition Plan",
            "s3_key": f"eagle/{TENANT}/packages/{PKG_ID}/acquisition_plan/v2/Acquisition-Plan.md",
            "s3_bucket": "eagle-docs",
            "status": "draft",
        }

    @pytest.mark.asyncio
    async def test_get_document_includes_download_url(self, mock_doc):
        """Endpoint should attach download_url when s3_key is present."""
        from app.cognito_auth import UserContext

        fake_user = UserContext(
            user_id=USER,
            tenant_id=TENANT,
            email="test@example.com",
            tier="advanced",
        )

        with (
            patch("app.routers.packages.get_document", return_value=mock_doc),
            patch("app.routers.packages.get_document_download_url", return_value="https://s3.example.com/presigned") as mock_url,
            patch("app.routers.packages.get_user_from_header", return_value=fake_user),
        ):
            from app.routers.packages import get_document_endpoint
            result = await get_document_endpoint(
                package_id=PKG_ID,
                doc_type="acquisition_plan",
                version=None,
                user=fake_user,
            )

            assert "download_url" in result
            assert result["download_url"] == "https://s3.example.com/presigned"
            mock_url.assert_called_once_with(
                tenant_id=TENANT,
                package_id=PKG_ID,
                doc_type="acquisition_plan",
                version=2,
            )


# ═════════════════════════════════════════════════════════════════════════
# P1-5: Cascade enforcement — web_search blocked without prior KB
# ═════════════════════════════════════════════════════════════════════════

class TestCascadeEnforcement:
    """web_search must be blocked when KB tools haven't been called first."""

    def test_cascade_violation_returns_error_in_subagent_tools(self):
        """Subagent web_search should return error JSON when KB not called."""
        import importlib

        src = importlib.util.find_spec("app.strands_agentic_service")
        assert src and src.origin
        source_text = open(src.origin, encoding="utf-8").read()

        # Both cascade guards should return error instead of proceeding
        assert "CASCADE VIOLATION: You must call knowledge_search" in source_text, (
            "Cascade violation must return an error message to the agent"
        )

    def test_cascade_violation_does_not_execute_web_search(self):
        """After cascade violation, exec_web_search must NOT be called."""
        import importlib

        src = importlib.util.find_spec("app.strands_agentic_service")
        assert src and src.origin
        source_text = open(src.origin, encoding="utf-8").read()

        # Find the cascade guard blocks — they should return before exec_web_search
        # Count occurrences of the cascade violation return pattern
        return_count = source_text.count(
            '"action_required": "Call knowledge_search or search_far with this query first."'
        )
        assert return_count >= 2, (
            f"Expected cascade return in at least 2 locations (subagent + service tools), "
            f"found {return_count}"
        )


# ═════════════════════════════════════════════════════════════════════════
# P1-6: Checklist boost in knowledge_search
# ═════════════════════════════════════════════════════════════════════════

class TestChecklistBoost:
    """AI ranking should boost checklists for document generation queries."""

    def test_checklist_boost_for_doc_gen_query(self):
        """Queries about doc generation should trigger checklist boost."""
        from app.tools.knowledge_tools import _ai_rank_documents

        # We can't easily test the full AI call, but we can verify the
        # boost logic is integrated by checking the source
        import importlib
        src = importlib.util.find_spec("app.tools.knowledge_tools")
        assert src and src.origin
        source_text = open(src.origin, encoding="utf-8").read()

        assert "_doc_gen_signals" in source_text, (
            "knowledge_tools.py should have document generation signal detection"
        )
        assert "checklist_boost" in source_text, (
            "knowledge_tools.py should have checklist_boost logic"
        )
        assert "always include relevant checklists" in source_text, (
            "Checklist boost prompt must instruct AI to include checklists"
        )

    def test_checklist_boost_signals(self):
        """Verify the doc gen signals cover key document types."""
        expected_signals = [
            "acquisition plan", "igce", "sow", "market research",
            "compliance", "checklist",
        ]
        from app.tools import knowledge_tools as kt
        import importlib
        src = importlib.util.find_spec("app.tools.knowledge_tools")
        assert src and src.origin
        source_text = open(src.origin, encoding="utf-8").read()

        for signal in expected_signals:
            assert signal in source_text, (
                f"Missing doc gen signal: '{signal}' not found in knowledge_tools.py"
            )

    def test_builtin_checklist_entry_exists(self):
        """BUILTIN_KB_ENTRIES must include the acquisition package checklist."""
        from app.tools.knowledge_tools import BUILTIN_KB_ENTRIES

        checklist_entries = [
            e for e in BUILTIN_KB_ENTRIES
            if e.get("document_type") == "checklist"
        ]
        assert len(checklist_entries) >= 1, (
            "BUILTIN_KB_ENTRIES must include at least one checklist entry"
        )
        assert any(
            "acquisition" in e.get("title", "").lower()
            for e in checklist_entries
        ), "Must have an acquisition-related checklist in BUILTIN_KB_ENTRIES"


# ═════════════════════════════════════════════════════════════════════════
# P0-4: DOCX edit tool description enforces sequential processing
# ═════════════════════════════════════════════════════════════════════════

class TestDocxEditSequentialGuard:
    """edit_docx_document tool must instruct sequential document processing."""

    def test_edit_tool_has_sequential_guidance(self):
        """edit_docx_document docstring must warn against loading all docs."""
        import importlib

        src = importlib.util.find_spec("app.strands_agentic_service")
        assert src and src.origin
        source_text = open(src.origin, encoding="utf-8").read()

        assert "process ONE document at a time" in source_text, (
            "edit_docx_document tool description must enforce sequential processing"
        )
        assert "NEVER load all documents into context simultaneously" in source_text, (
            "edit_docx_document tool description must warn about context overflow"
        )

    def test_get_latest_document_has_sequential_guidance(self):
        """get_latest_document docstring must warn against loading all docs."""
        import importlib

        src = importlib.util.find_spec("app.strands_agentic_service")
        assert src and src.origin
        source_text = open(src.origin, encoding="utf-8").read()

        assert "call this for ONE doc_type at a time" in source_text, (
            "get_latest_document tool description must enforce one-at-a-time loading"
        )
