"""Tests for create_document auto-create package reuse logic.

Verifies that when create_document is called without a package_id,
it reuses an existing session package instead of creating duplicates.
"""

from __future__ import annotations

import json

import app.tools.legacy_dispatch as legacy_dispatch
from app.strands_agentic_service import _build_all_service_tools


SESSION_ID = "test-tenant#advanced#test-user#sess-001"
TENANT_ID = "test-tenant"
EXISTING_PKG_ID = "PKG-2026-0099"

# Content long enough to satisfy the document_prerequisites guardrail
# (requirement_description check accepts content > 100 chars).
_SUFFICIENT_CONTENT = (
    "This Statement of Work covers IT modernization services for NCI. "
    "The contractor shall provide cloud migration, DevOps, and application "
    "development support for a 12-month base period with two option years."
)


def _get_create_document_tool(monkeypatch, list_packages_return, create_package_return=None):
    """Helper: build tools with mocked package_store and patched get_tool_dispatch."""

    # Mock list_packages
    monkeypatch.setattr(
        "app.package_store.list_packages",
        lambda tenant_id, owner_user_id=None: list_packages_return,
    )

    # Mock create_package (only called when no session package exists)
    _create_calls = []

    def _fake_create_package(**kwargs):
        _create_calls.append(kwargs)
        return create_package_return or {}

    monkeypatch.setattr("app.package_store.create_package", _fake_create_package)

    # Patch get_tool_dispatch to inject fake handlers used by create_document_tool
    def fake_create_document(params, tenant_id, session_id):
        return {
            "status": "saved",
            "document_type": params.get("doc_type"),
            "title": params.get("title", ""),
            "package_id": params.get("package_id", ""),
        }

    def fake_get_latest_document(params, tenant_id):
        return {"document": None}

    real_get_tool_dispatch = legacy_dispatch.get_tool_dispatch

    def patched_get_tool_dispatch():
        dispatch = real_get_tool_dispatch()
        dispatch["create_document"] = fake_create_document
        dispatch["get_latest_document"] = fake_get_latest_document
        return dispatch

    monkeypatch.setattr(legacy_dispatch, "get_tool_dispatch", patched_get_tool_dispatch)

    # Bypass the template auto-search guardrail so it doesn't hit real KB
    monkeypatch.setattr(
        "app.tools.knowledge_tools.exec_knowledge_search",
        lambda params, tenant_id, session_id=None: {"results": []},
    )

    tools = _build_all_service_tools(
        tenant_id=TENANT_ID,
        user_id="test-user",
        session_id=SESSION_ID,
        prompt_context="",
        package_context=None,
        result_queue=None,
        loop=None,
    )
    create_doc_tool = next(t for t in tools if t.tool_name == "create_document")
    return create_doc_tool, _create_calls


def test_reuses_existing_session_package(monkeypatch):
    """When a package already exists for this session, reuse it instead of creating a new one."""
    existing_packages = [
        {"package_id": EXISTING_PKG_ID, "session_id": SESSION_ID, "owner_user_id": "test-user"},
    ]

    create_doc_tool, create_calls = _get_create_document_tool(
        monkeypatch,
        list_packages_return=existing_packages,
    )

    result_json = create_doc_tool(doc_type="sow", title="Statement of Work", content=_SUFFICIENT_CONTENT)
    result = json.loads(result_json)

    # Should reuse existing package, not create a new one
    assert len(create_calls) == 0
    assert result["package_id"] == EXISTING_PKG_ID


def test_creates_new_package_when_none_exists_for_session(monkeypatch):
    """When no package exists for this session, create a new one."""
    new_pkg_id = "PKG-2026-NEW"

    create_doc_tool, create_calls = _get_create_document_tool(
        monkeypatch,
        list_packages_return=[],  # No existing packages
        create_package_return={"package_id": new_pkg_id, "status": "draft"},
    )

    result_json = create_doc_tool(doc_type="sow", title="Statement of Work", content=_SUFFICIENT_CONTENT)
    result = json.loads(result_json)

    # Should have created a new package
    assert len(create_calls) == 1
    assert create_calls[0]["session_id"] == SESSION_ID
    assert result["package_id"] == new_pkg_id


def test_ignores_packages_from_different_sessions(monkeypatch):
    """Packages from other sessions should not be reused."""
    new_pkg_id = "PKG-2026-NEW2"
    other_session_packages = [
        {"package_id": "PKG-OTHER", "session_id": "test-tenant#advanced#test-user#sess-OTHER", "owner_user_id": "test-user"},
    ]

    create_doc_tool, create_calls = _get_create_document_tool(
        monkeypatch,
        list_packages_return=other_session_packages,
        create_package_return={"package_id": new_pkg_id, "status": "draft"},
    )

    result_json = create_doc_tool(doc_type="sow", title="Statement of Work", content=_SUFFICIENT_CONTENT)
    result = json.loads(result_json)

    # Should NOT reuse the other session's package — should create new
    assert len(create_calls) == 1
    assert result["package_id"] == new_pkg_id


def test_skips_lookup_when_package_id_already_provided(monkeypatch):
    """When package_id is explicitly passed, skip the auto-create/reuse logic entirely."""
    explicit_pkg_id = "PKG-EXPLICIT"
    list_called = []

    monkeypatch.setattr(
        "app.package_store.list_packages",
        lambda tenant_id, owner_user_id=None: list_called.append(1) or [],
    )
    monkeypatch.setattr(
        "app.package_store.create_package",
        lambda **kw: {},
    )

    def fake_create_document(params, tenant_id, session_id):
        return {
            "status": "saved",
            "document_type": params.get("doc_type"),
            "package_id": params.get("package_id", ""),
        }

    def fake_get_latest_document(params, tenant_id):
        return {"document": None}

    real_get_tool_dispatch = legacy_dispatch.get_tool_dispatch

    def patched_get_tool_dispatch():
        dispatch = real_get_tool_dispatch()
        dispatch["create_document"] = fake_create_document
        dispatch["get_latest_document"] = fake_get_latest_document
        return dispatch

    monkeypatch.setattr(legacy_dispatch, "get_tool_dispatch", patched_get_tool_dispatch)

    # Bypass template auto-search
    monkeypatch.setattr(
        "app.tools.knowledge_tools.exec_knowledge_search",
        lambda params, tenant_id, session_id=None: {"results": []},
    )

    tools = _build_all_service_tools(
        tenant_id=TENANT_ID,
        user_id="test-user",
        session_id=SESSION_ID,
        prompt_context="",
        package_context=None,
        result_queue=None,
        loop=None,
    )
    create_doc_tool = next(t for t in tools if t.tool_name == "create_document")

    result_json = create_doc_tool(doc_type="sow", title="SOW", content=_SUFFICIENT_CONTENT, package_id=explicit_pkg_id)
    result = json.loads(result_json)

    # list_packages should never have been called
    assert len(list_called) == 0
    assert result["package_id"] == explicit_pkg_id


def test_owner_user_id_passed_to_list_packages(monkeypatch):
    """list_packages should be called with owner_user_id extracted from session_id."""
    captured_calls = []

    def tracking_list_packages(tenant_id, owner_user_id=None):
        captured_calls.append({"tenant_id": tenant_id, "owner_user_id": owner_user_id})
        return [{"package_id": EXISTING_PKG_ID, "session_id": SESSION_ID, "owner_user_id": "test-user"}]

    monkeypatch.setattr("app.package_store.list_packages", tracking_list_packages)
    monkeypatch.setattr("app.package_store.create_package", lambda **kw: {})

    def fake_create_document(params, tenant_id, session_id):
        return {"status": "saved", "document_type": params.get("doc_type"), "package_id": params.get("package_id", "")}

    def fake_get_latest_document(params, tenant_id):
        return {"document": None}

    real_get_tool_dispatch = legacy_dispatch.get_tool_dispatch

    def patched_get_tool_dispatch():
        dispatch = real_get_tool_dispatch()
        dispatch["create_document"] = fake_create_document
        dispatch["get_latest_document"] = fake_get_latest_document
        return dispatch

    monkeypatch.setattr(legacy_dispatch, "get_tool_dispatch", patched_get_tool_dispatch)

    # Bypass template auto-search
    monkeypatch.setattr(
        "app.tools.knowledge_tools.exec_knowledge_search",
        lambda params, tenant_id, session_id=None: {"results": []},
    )

    tools = _build_all_service_tools(
        tenant_id=TENANT_ID,
        user_id="test-user",
        session_id=SESSION_ID,
        prompt_context="",
        package_context=None,
        result_queue=None,
        loop=None,
    )
    create_doc_tool = next(t for t in tools if t.tool_name == "create_document")
    create_doc_tool(doc_type="sow", title="SOW", content=_SUFFICIENT_CONTENT)

    assert len(captured_calls) == 1
    assert captured_calls[0]["tenant_id"] == TENANT_ID
    assert captured_calls[0]["owner_user_id"] == "test-user"
